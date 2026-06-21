#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Etraval-agent 主入口 - FastAPI 后端服务
基于 SmartVoyage app.py 二次开发，适配新版多智能体架构

主要变更：
  1. 意图识别引入问题改写模块
  2. 支持多模态视觉 Agent
  3. A2A 协议增加超时重试机制
  4. 新增景点介绍 Agent 路由
"""
import json
import os
import re
import logging
from datetime import datetime
import pytz
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware

from python_a2a import AgentNetwork
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

from configs.llm_config import main_llm, a2a_agents, a2a_protocol

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Etraval-agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局变量
agent_network = None
llm = None
conversation_history = ""


# ===================== Prompt 模板（继承自 SmartVoyage，扩展意图） =====================

intent_prompt = ChatPromptTemplate.from_template("""
系统提示：您是一个专业的旅行意图识别专家，基于用户查询和对话历史，识别意图并提取槽位。严格遵守规则：
- 支持意图：
  'weather' (天气查询), 'flight' (机票查询), 'train' (高铁/火车票查询),
  'concert' (演唱会票查询), 'attraction' (景点介绍/推荐), 'visual' (图片识别景点)
  或其组合（如 ['weather', 'flight']）。
- 如果意图超出范围，返回意图 'out_of_scope'。
- 对于 'visual' 意图，当用户上传图片或描述图片内容时触发。
- 提取槽位：
  - weather: city (城市，多个用逗号分隔), date (日期)
  - flight/train: departure_city, arrival_city, date, seat_type
  - concert: city, artist, date, ticket_type
  - attraction: city, preferences, query
  - visual: image_url (图片URL), description (用户描述)
- 如果意图为组合，只提取公共槽位，后续分别填充。
- 如果槽位缺失，返回 'missing_slots' 和追问消息。
- 输出严格为JSON，不要添加额外文本！
- 当前日期：{current_date} (Asia/Shanghai)。
- 基于整个对话历史填充槽位，优先最新查询。

对话历史：{conversation_history}
用户查询：{query}
""")

# 问题改写 Prompt（新功能）
query_rewrite_prompt = ChatPromptTemplate.from_template("""
系统提示：你是一个旅行查询改写专家。根据对话历史，将用户的当前问题改写为完整、独立的自包含查询。
- 补全省略的上下文信息（如"明天"→补全具体日期，"那里"→补全地点）
- 保持原始意图不变
- 输出仅返回改写后的查询文本，不要额外内容

对话历史：{conversation_history}
当前日期：{current_date}
用户问题：{query}
改写结果：
""")

summarize_weather_prompt = ChatPromptTemplate.from_template("""
系统提示：您是一位专业的天气预报员，以生动、准确的风格总结天气信息。
- 核心：城市、日期、温度范围、天气描述、湿度、风向、降水。
- 如果结果为空，提示"未找到数据"。
- 保持中文，100-150字。

查询：{query}
结果：{raw_response}
""")

summarize_ticket_prompt = ChatPromptTemplate.from_template("""
系统提示：您是一位专业的旅行顾问，以热情、精确的风格总结票务信息。
- 核心：出发/到达、时间、类型、价格、剩余座位。
- 如果结果为空，提示"未找到数据"。
- 保持中文，100-150字。

查询：{query}
结果：{raw_response}
""")

attraction_prompt = ChatPromptTemplate.from_template("""
系统提示：您是一位旅行专家，基于用户查询生成景点介绍/推荐。
- 推荐3-5个景点，包含描述、理由、注意事项。
- 语气：热情推荐。
- 保持中文，150-250字。

查询：{query}
槽位：{slots}
""")


# ===================== 请求/响应模型 =====================

class ChatRequest(BaseModel):
    prompt: str
    conversation_history: Optional[str] = ""

class ChatResponse(BaseModel):
    response: str
    conversation_history: str
    routed_agents: List[str] = []


@app.on_event("startup")
def startup_event():
    global agent_network, llm

    # 初始化 A2A 代理网络
    network = AgentNetwork(name="Etraval Travel Network")
    for name, url in [("Weather Query Assistant", a2a_agents["weather"]),
                       ("Ticket Query Assistant", a2a_agents["ticket"]),
                       ("Attraction Assistant", a2a_agents["attraction"]),
                       ("Visual Recognition Agent", a2a_agents["visual"])]:
        try:
            network.add(name, url)
            logger.info(f"Agent {name} added ({url})")
        except Exception as e:
            logger.warning(f"Agent {name} not available ({url}): {e}")
    agent_network = network

    # 初始化 LLM
    llm = ChatOpenAI(**main_llm)
    logger.info("Etraval-agent system initialized")


def rewrite_query(query: str, history: str) -> str:
    """问题改写：补全上下文，生成独立查询"""
    try:
        current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
        chain = query_rewrite_prompt | llm
        rewritten = chain.invoke({
            "conversation_history": history,
            "current_date": current_date,
            "query": query
        }).content.strip()
        logger.info(f"问题改写: {query} -> {rewritten}")
        return rewritten
    except Exception as e:
        logger.warning(f"问题改写失败，使用原始查询: {e}")
        return query


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    global conversation_history, llm, agent_network

    prompt = request.prompt
    current_history = request.conversation_history or ""
    current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')

    try:
        # ===== 步骤1: 问题改写 =====
        rewritten_query = rewrite_query(prompt, current_history)

        # ===== 步骤2: 意图识别 =====
        chain = intent_prompt | llm
        intent_response = chain.invoke({
            "conversation_history": current_history,
            "query": rewritten_query,
            "current_date": current_date
        }).content.strip()
        logger.info(f"意图识别原始: {intent_response}")

        intent_response = re.sub(r'^```json\s*|\s*```$', '', intent_response).strip()
        intent_output = json.loads(intent_response)
        logger.info(f"意图解析: {json.dumps(intent_output, ensure_ascii=False)}")

        # 兼容多种意图格式
        # 格式A: {"intents": ["weather"], "slots": {"weather": {"city": "北京"}}}
        # 格式B: {"intent": "weather", "slots": {"city": "北京", "date": "2026-06-22"}}
        # 格式C: {"intent": "weather"}
        intents = intent_output.get("intents", [])
        if not intents and "intent" in intent_output:
            intent_val = intent_output["intent"]
            intents = [intent_val] if isinstance(intent_val, str) else (intent_val or [])

        slots = intent_output.get("slots", {})
        # 格式B处理：扁平slots {"city":"北京"} -> 嵌套 {"weather":{"city":"北京"}}
        has_nested = any(k in slots for k in ["weather", "flight", "train", "concert", "attraction", "visual"])
        if slots and not has_nested and intents:
            nested = {}
            for intent in intents:
                nested[intent] = dict(slots)
            slots = nested

        missing_slots = intent_output.get("missing_slots", {})
        follow_up_message = intent_output.get("follow_up_message", "")
        logger.info(f"处理后: intents={intents}, slots={json.dumps(slots, ensure_ascii=False)}, missing={missing_slots}")

        response = ""
        routed_agents = []

        # 判断缺失槽位是否为真正的必填字段
        # 缺失date可默认填充今天；seat_type/ticket_type为可选
        required_fields = {
            "weather": {"city"},
            "train": {"departure_city", "arrival_city"},
            "flight": {"departure_city", "arrival_city"},
            "concert": {"city"},
            "attraction": {"city"},
            "visual": set(),
        }
        # 收集平铺的missing_slots
        if isinstance(missing_slots, dict):
            flat_missing = set()
            for v in missing_slots.values():
                if isinstance(v, list):
                    flat_missing.update(v)
        elif isinstance(missing_slots, list):
            flat_missing = set(missing_slots)
        else:
            flat_missing = set()

        # 对每个 intent，检查是否缺必填字段
        truly_required_missing = False
        for intent in intents:
            req = required_fields.get(intent, set())
            intent_missing = {s for s in flat_missing if s in req}
            if intent_missing:
                truly_required_missing = True
                break

        if "out_of_scope" in intents:
            response = "您好！我是Etraval智能旅行助手，可以为您查询天气、车票、机票、演唱会门票、介绍景点、识别风景照片等。请告诉我您的需求！"
        elif missing_slots and truly_required_missing:
            response = follow_up_message or "请提供更多信息。"
        else:
            responses = []
            for intent in intents:
                agent_name = None
                if intent == "weather":
                    agent_name = "Weather Query Assistant"
                elif intent in ["flight", "train", "concert"]:
                    agent_name = "Ticket Query Assistant"
                elif intent == "attraction":
                    agent_name = "Attraction Assistant"
                elif intent == "visual":
                    agent_name = "Visual Recognition Agent"

                if intent == "attraction":
                    chain = attraction_prompt | llm
                    rec_response = chain.invoke({
                        "query": rewritten_query,
                        "slots": json.dumps(slots.get(intent, {}), ensure_ascii=False)
                    }).content.strip()
                    responses.append(rec_response)
                elif agent_name:
                    intent_slots = slots.get(intent, {})
                    if intent == "weather":
                        if not intent_slots.get("city"):
                            intent_slots["city"] = "北京,上海,广州,深圳"
                        if not intent_slots.get("date"):
                            intent_slots["date"] = current_date
                        query_str = f"{intent_slots['city']} {intent_slots['date']}"
                    elif intent == "visual":
                        query_str = f"visual {intent_slots.get('image_url', '')} {intent_slots.get('description', '')}".strip()
                    else:
                        query_str = f"{intent} {intent_slots.get('departure_city', '')} {intent_slots.get('arrival_city', '')} {intent_slots.get('date', current_date)} {intent_slots.get('seat_type', '')}".strip()
                        if intent == "concert":
                            query_str = f"演唱会 {intent_slots.get('city', '')} {intent_slots.get('artist', '')} {intent_slots.get('date', current_date)} {intent_slots.get('ticket_type', '')}".strip()

                    agent = agent_network.get_agent(agent_name)
                    raw_response = agent.ask(query_str)

                    if intent == "weather":
                        chain = summarize_weather_prompt | llm
                        sum_response = chain.invoke({"query": query_str, "raw_response": raw_response}).content.strip()
                    else:
                        chain = summarize_ticket_prompt | llm
                        sum_response = chain.invoke({"query": query_str, "raw_response": raw_response}).content.strip()

                    responses.append(sum_response)
                    routed_agents.append(agent_name)
                else:
                    responses.append("暂不支持此意图。")

            response = "\n\n".join(responses)

        new_history = current_history + f"\nUser: {prompt}\nAssistant: {response}"

        return ChatResponse(
            response=response,
            conversation_history=new_history,
            routed_agents=list(set(routed_agents))
        )

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
