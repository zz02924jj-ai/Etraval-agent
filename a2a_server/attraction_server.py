#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : attraction_server.py
@Function: 景点介绍 A2A Agent
- 整合：知识库检索(Milvus/内置) + 景点评价 + 大模型生成
- 三级降级策略：MCP → 本地知识库 → LLM直接生成
- 生成包含基本信息、特色亮点、游玩建议、用户评价的完整介绍
"""
import json
import asyncio
import os
import sys
from python_a2a import A2AServer, run_server, AgentCard, AgentSkill, TaskStatus, TaskState
from python_a2a.mcp import MCPClient
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import colorlog

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.llm_config import attraction_llm, mcp_services

handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
    log_colors={'INFO': 'green', 'ERROR': 'red'}
))
logger = colorlog.getLogger()
logger.addHandler(handler)
logger.setLevel(colorlog.INFO)


# 景点介绍生成 Prompt
attraction_intro_prompt = ChatPromptTemplate.from_template("""
你是一个专业的旅游景点介绍专家。请基于以下信息，生成一个详细、生动的景点介绍。

用户查询：{query}

【知识库检索结果】
{knowledge_result}

【景点评价】
{review_result}

请按以下格式组织回答：

🏛 **{景点名称}**

**基本信息**
- 位置：所在城市和区域
- 评分：用户评分
- 开放时间
- 门票价格

**景点特色**
- 核心亮点和历史文化
- 推荐游览项目

**游玩建议**
- 最佳旅行季节
- 推荐游览时长
- 注意事项

**游客评价摘要**
- 来自真实游客的反馈

💡 提示：以上信息基于知识库检索结果，仅供参考。

注意：
- 保持中文回答，语气热情专业
- 如果知识库有数据则基于数据回答，无数据则如实说明
- 不要编造信息
""")

# 无数据时的兜底 Prompt
fallback_prompt = ChatPromptTemplate.from_template("""
你是一位旅行专家。请根据你的知识介绍以下景点或旅游目的地。

用户问题：{query}

请包含：
1. 景点基本介绍和特色
2. 游玩建议（最佳季节、注意事项）
3. 推荐游览路线

注意：不要编造具体的门票价格或开放时间。保持中文回答。
""")


def _sync_call_mcp(mcp_url: str, tool: str, **kwargs) -> str:
    """同步方式调用 MCP 工具（创建独立事件循环）"""
    client = MCPClient(mcp_url)
    loop = asyncio.get_event_loop_policy().new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(client.call_tool(tool, **kwargs))
        return result
    except Exception as e:
        logger.warning(f"MCP调用失败 ({mcp_url}/{tool}): {e}")
        return json.dumps({"status": "error", "message": str(e)})
    finally:
        loop.close()


def _search_local_knowledge(query: str) -> list:
    """使用本地知识库检索（不依赖MCP）"""
    try:
        from knowledge_base import search as kb_search
        return kb_search(query, top_k=3)
    except Exception as e:
        logger.warning(f"本地知识库检索失败: {e}")
        return []


class AttractionServer(A2AServer):
    def __init__(self):
        agent_card = AgentCard(
            name="Attraction Assistant",
            description="景点介绍 Agent，整合知识库检索和评价数据，提供详细景点讲解",
            url="http://localhost:5007",
            version="2.0.0",
            capabilities={"streaming": True, "memory": True},
            skills=[AgentSkill(
                name="introduce attraction",
                description="根据用户需求介绍景点，包含知识库检索和评价",
                examples=["介绍北京故宫", "广州有什么好玩的景点"]
            )]
        )
        super().__init__(agent_card=agent_card)
        self.llm = ChatOpenAI(**attraction_llm)

    def handle_task(self, task):
        message_data = task.message or {}
        content = message_data.get("content", {})
        conversation = content.get("text", "") if isinstance(content, dict) else ""
        logger.info(f"景点查询: {conversation}")

        try:
            # ===== 一级：尝试调用 MCP 服务 =====
            knowledge_result = ""
            review_result = ""
            mcp_success = False

            try:
                # 调用知识库 MCP
                knowledge_mcp = os.getenv("MCP_KNOWLEDGE_URL", mcp_services["knowledge"])
                raw_kb = _sync_call_mcp(knowledge_mcp, "search_attractions", query=conversation, top_k=5)
                kb_data = json.loads(raw_kb) if isinstance(raw_kb, str) else raw_kb
                if kb_data.get("status") == "success" and kb_data.get("data"):
                    knowledge_result = json.dumps(kb_data["data"], ensure_ascii=False, indent=2)
                    mcp_success = True
                    logger.info(f"知识库MCP返回 {len(kb_data['data'])} 条结果")

                # 调用评价 MCP
                review_mcp = os.getenv("MCP_REVIEW_URL", mcp_services["review"])
                raw_review = _sync_call_mcp(review_mcp, "search_reviews", attraction=conversation, top_k=5)
                review_data = json.loads(raw_review) if isinstance(raw_review, str) else raw_review
                if review_data.get("status") == "success" and review_data.get("data"):
                    review_result = json.dumps(review_data["data"], ensure_ascii=False, indent=2)

            except Exception as e:
                logger.warning(f"MCP调用异常: {e}，降级到本地知识库")

            # ===== 二级：MCP 失败时使用本地知识库 =====
            if not mcp_success:
                logger.info("使用本地知识库检索...")
                local_results = _search_local_knowledge(conversation)
                if local_results:
                    knowledge_result = json.dumps(local_results, ensure_ascii=False, indent=2)
                    mcp_success = True
                    logger.info(f"本地知识库返回 {len(local_results)} 条结果")

            # ===== 三级：根据是否有数据选择 Prompt =====
            if mcp_success:
                chain = attraction_intro_prompt | self.llm
                response = chain.invoke({
                    "query": conversation,
                    "knowledge_result": knowledge_result,
                    "review_result": review_result or "暂无评价数据"
                }).content.strip()
            else:
                # 直接使用 LLM 知识生成
                logger.info("无知识库数据，使用 LLM 直接生成")
                chain = fallback_prompt | self.llm
                response = chain.invoke({"query": conversation}).content.strip()

            task.artifacts = [{"parts": [{"type": "text", "text": response}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)

        except Exception as e:
            logger.error(f"景点查询失败: {str(e)}")
            # 兜底：直接 LLM 生成
            try:
                fallback = self.llm.invoke(f"请介绍以下景点或旅游目的地：{conversation}，包含特色、游玩建议等。")
                task.artifacts = [{"parts": [{"type": "text", "text": fallback.content.strip()}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)
            except Exception as e2:
                task.artifacts = [{"parts": [{"type": "text", "text": f"查询失败: {str(e2)}。请稍后重试。"}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)

        return task


def main():
    server = AttractionServer()
    print(f"=== 景点介绍 Agent 服务器 ===")
    print(f"名称: {server.agent_card.name}")
    run_server(server, host="0.0.0.0", port=5007)


if __name__ == "__main__":
    import sys as _sys
    try:
        main()
        _sys.exit(0)
    except KeyboardInterrupt:
        print("\n✅ 程序被用户中断")
        _sys.exit(0)
