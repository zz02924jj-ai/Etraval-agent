#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : visual_server.py
@Function: 多模态视觉理解 A2A Agent
- 识别流程：OCR优先(PaddleOCR) → 多模态地标识别(GLM-4V-9B) → 关键词兜底
- 识别成功后联动景点介绍 Agent 生成详细讲解
- 通过知识库推荐同类目的地
- 三层兜底逻辑确保系统可用
"""
import json
import asyncio
import os
import sys
import logging
from python_a2a import A2AServer, run_server, AgentCard, AgentSkill, TaskStatus, TaskState
from python_a2a.mcp import MCPClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.llm_config import a2a_agents, mcp_services
from multi_modal import recognize_scene, OCREngine, VLMEngine, keyword_fallback_match, LANDMARK_KEYWORDS
from knowledge_base import search as kb_search

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class VisualRecognitionAgent(A2AServer):
    """
    多模态视觉理解 Agent
    处理流程：
    1. 接收图片URL或base64 → 2. OCR优先提取文字 → 3. 无文字则GLM-4V-9B地标识别
    4. 识别成功→联动Agent讲解+同类推荐 → 5. 失败→兜底逻辑
    """

    def __init__(self):
        agent_card = AgentCard(
            name="Visual Recognition Agent",
            description="基于 GLM-4V-9B + PaddleOCR 的景点识别与讲解 Agent",
            url="http://localhost:5008",
            version="2.0.0",
            capabilities={"streaming": False, "memory": True, "vision": True},
            skills=[
                AgentSkill(name="recognize scenic spot",
                           description="识别风景照片中的景点并生成详细讲解",
                           examples=["这张照片是哪里？", "帮我识别这个景点"]),
                AgentSkill(name="recommend similar attractions",
                           description="推荐同类风格的目的地",
                           examples=["推荐类似的山岳景点", "还有哪些海滨古镇？"]),
            ]
        )
        super().__init__(agent_card=agent_card)
        # 初始化引擎（自动探测可用性）
        self.ocr = OCREngine()
        self.vlm = VLMEngine()
        logger.info(f"视觉Agent初始化: OCR={'✅' if self.ocr.available else '❌'} VLM={'✅' if self.vlm.available else '❌'}")

    def _call_attraction_agent(self, spot_name: str) -> str:
        """联动景点介绍 Agent 获取详细讲解"""
        try:
            from python_a2a import A2AClient
            agent_url = os.getenv("A2A_ATTRACTION_URL", a2a_agents.get("attraction", "http://localhost:5007"))
            client = A2AClient(agent_url)
            # 直接向景点 Agent 发送查询
            result = client.ask(f"详细介绍{spot_name}")
            return str(result)
        except Exception as e:
            logger.warning(f"联动景点Agent失败: {e}")
            return ""

    def _get_similar_recommendations(self, spot_name: str, spot_type: str = "") -> list:
        """获取同类推荐"""
        try:
            if spot_type:
                results = kb_search(f"{spot_type}类景点 推荐", top_k=5)
            else:
                results = kb_search(f"类似{spot_name}的景点", top_k=5)
            # 过滤掉自身
            return [r for r in results if r["name"] != spot_name][:3]
        except Exception as e:
            logger.warning(f"同类推荐失败: {e}")
            return []

    def handle_task(self, task):
        message_data = task.message or {}
        content = message_data.get("content", {})
        text = content.get("text", "") if isinstance(content, dict) else ""
        logger.info(f"视觉识别请求: {text[:200]}")

        try:
            # 解析参数: "visual <image_url> [描述]" 或 "visual <base64> [描述]"
            parts = text.strip().split(maxsplit=2)
            if len(parts) < 2:
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={"role": "agent", "content": {
                        "text": "🌄 **请上传一张风景照片**\n\n我可以帮您：\n"
                                "1. 识别照片中的景点名称\n"
                                "2. 生成详细景点讲解\n"
                                "3. 推荐同类风格目的地\n\n"
                                "格式示例：`visual https://example.com/photo.jpg`\n"
                                "或直接输入景点名称让我介绍。"
                    }}
                )
                return task

            image_source = parts[1]
            user_description = parts[2] if len(parts) > 2 else ""

            # ===== 一站式景点识别 =====
            logger.info(f"开始识别: source_type={'URL' if image_source.startswith('http') else 'base64'}, desc={user_description[:50] if user_description else '无'}")
            rec_result = recognize_scene(image_source, user_description)

            # ===== 处理结果 =====
            if rec_result["success"]:
                spot_name = rec_result["name"]
                method = rec_result["method"]
                confidence = rec_result["confidence"]
                city = rec_result.get("city", "")
                spot_type = rec_result.get("type", "")

                method_icons = {"ocr": "🔤", "vlm": "🧠", "keyword_fallback": "🔑"}
                method_names = {"ocr": "OCR文字识别", "vlm": "GLM-4V-9B地标识别", "keyword_fallback": "关键词匹配"}
                method_icon = method_icons.get(method, "✅")

                # 构建响应
                response_parts = [
                    f"{method_icon} **识别成功！**",
                    f"",
                    f"**景点：{spot_name}**",
                    f"识别方式：{method_names.get(method, method)}",
                    f"置信度：{confidence:.0%}",
                ]

                if city:
                    response_parts.append(f"所在城市：{city}")
                if spot_type:
                    response_parts.append(f"类型：{spot_type}")

                response_parts.append("")

                # 联动景点介绍 Agent 获取详细讲解
                logger.info(f"联动景点Agent获取{spot_name}的详细讲解...")
                # 先用知识库检索
                kb_results = kb_search(spot_name, city, top_k=3)
                if kb_results:
                    best = kb_results[0]
                    response_parts.append(f"📖 **{best['name']}**")
                    response_parts.append(f"_{best['description']}_")
                    if best.get("highlights"):
                        response_parts.append(f"✨ 亮点：{best['highlights']}")
                    if best.get("tips"):
                        response_parts.append(f"💡 建议：{best['tips']}")
                    if best.get("opening_hours"):
                        response_parts.append(f"🕐 开放时间：{best['opening_hours']}")
                    if best.get("ticket_info"):
                        response_parts.append(f"🎫 门票：{best['ticket_info']}")
                else:
                    # 尝试调用景点 Agent
                    agent_detail = self._call_attraction_agent(spot_name)
                    if agent_detail:
                        response_parts.append(agent_detail[:500])

                # 同类推荐
                similar = self._get_similar_recommendations(spot_name, spot_type)
                if similar:
                    response_parts.append(f"\n🏆 **同类景点推荐**：")
                    for s in similar:
                        score = s.get("score", 0)
                        star = "⭐" * min(int(score * 10) if score > 0 else 4, 5)
                        response_parts.append(f"- {s['name']}（{s.get('city', '')}）{star}")

                # OCR 提取的文字
                if rec_result.get("raw_ocr"):
                    response_parts.append(f"\n📝 图片中识别到的文字：_{rec_result['raw_ocr'][:100]}_")

                response_text = "\n".join(response_parts)

            else:
                # ===== 兜底逻辑 =====
                if user_description:
                    # 尝试从描述中匹配关键词
                    landmark = keyword_fallback_match(user_description)
                    if landmark:
                        response_text = (
                            f"🔑 **根据您的描述，我找到了相关景点！**\n\n"
                            f"**{landmark['name']}**\n"
                            f"所在城市：{landmark.get('city', '')}\n\n"
                            f"💡 您可以直接告诉我景点名称，我为您详细介绍。\n"
                            f"或者重新上传一张包含路牌/石碑标志的照片。"
                        )
                    else:
                        response_text = (
                            f"😅 **暂时无法从图片中识别出景点**\n\n"
                            f"根据您的描述「{user_description}」，\n\n"
                            f"**可能原因：**\n"
                            f"1. 图片不够清晰或光线不足\n"
                            f"2. 拍摄角度未能包含标志性建筑\n"
                            f"3. 该景点暂未收录\n\n"
                            f"**建议：**\n"
                            f"- 重新拍摄一张包含**景点名称路牌**的照片\n"
                            f"- 或直接告诉我景点名称，我为您详细介绍\n"
                            f"- 或上传到图床后重新发送"
                        )
                else:
                    response_text = (
                        "😅 **无法从图片中识别出具体景点**\n\n"
                        "**可能原因：**\n"
                        "1. 图片不够清晰或光线不足\n"
                        "2. 拍摄角度未能包含标志性建筑\n"
                        "3. 该景点暂未收录在知识库中\n\n"
                        "**建议：**\n"
                        "- 重新拍摄一张包含**景点名称路牌**的照片\n"
                        "- 或直接告诉我景点名称，我为您介绍\n"
                        "- 或补充一些描述帮助我识别"
                    )

            task.artifacts = [{"parts": [{"type": "text", "text": response_text}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)

        except Exception as e:
            logger.error(f"视觉识别失败: {str(e)}")
            task.artifacts = [{"parts": [{"type": "text", "text": f"识别失败: {str(e)}。请重试或直接输入景点名称查询。"}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)

        return task


def main():
    server = VisualRecognitionAgent()
    print(f"=== 多模态视觉 Agent 服务器 ===")
    print(f"名称: {server.agent_card.name}")
    run_server(server, host="0.0.0.0", port=5008)


if __name__ == "__main__":
    import sys as _sys
    try:
        main()
        _sys.exit(0)
    except KeyboardInterrupt:
        print("\n✅ 程序被用户中断")
        _sys.exit(0)
