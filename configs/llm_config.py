#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author  : Vincent
@Time    : 2026/6/20
@File    : llm_config.py
@Function: Etraval-agent LLM & service configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()


# ===================== LLM 配置 =====================
# 使用 Deepseek API（写死配置，无需 .env 文件）
# 如需切换模型或 API，直接修改这里的值即可

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# 主模型 (意图识别、Agent决策)
main_llm = dict(
    model=os.getenv("GLM_MODEL", "deepseek-chat"),
    api_key=os.getenv("GLM_API_KEY", DEEPSEEK_API_KEY),
    base_url=os.getenv("GLM_BASE_URL", DEEPSEEK_BASE_URL),
    temperature=0,
)

# 天气查询 Agent LLM
weather_llm = dict(
    model=os.getenv("GLM_MODEL", "deepseek-chat"),
    api_key=os.getenv("GLM_API_KEY", DEEPSEEK_API_KEY),
    base_url=os.getenv("GLM_BASE_URL", DEEPSEEK_BASE_URL),
    temperature=0,
    streaming=True,
)

# 票务查询 Agent LLM (react 模式)
ticket_llm = dict(
    model=os.getenv("GLM_MODEL", "deepseek-chat"),
    api_key=os.getenv("GLM_API_KEY", DEEPSEEK_API_KEY),
    base_url=os.getenv("GLM_BASE_URL", DEEPSEEK_BASE_URL),
    temperature=0,
    streaming=True,
)

# A2A Router LLM
a2a_llm = dict(
    model=os.getenv("GLM_MODEL", "deepseek-chat"),
    api_key=os.getenv("GLM_API_KEY", DEEPSEEK_API_KEY),
    base_url=os.getenv("GLM_BASE_URL", DEEPSEEK_BASE_URL),
    temperature=0,
)

# 景点介绍 Agent LLM
attraction_llm = dict(
    model=os.getenv("GLM_MODEL", "deepseek-chat"),
    api_key=os.getenv("GLM_API_KEY", DEEPSEEK_API_KEY),
    base_url=os.getenv("GLM_BASE_URL", DEEPSEEK_BASE_URL),
    temperature=0.3,
    streaming=True,
)

# 多模态视觉 Agent LLM（Deepseek 无视觉模型，会自动降级到 OCR+关键词）
visual_llm = dict(
    model=os.getenv("GLM_4V_MODEL", "deepseek-chat"),
    api_key=os.getenv("GLM_API_KEY", DEEPSEEK_API_KEY),
    base_url=os.getenv("GLM_BASE_URL", DEEPSEEK_BASE_URL),
    temperature=0,
)


# ===================== MCP 服务地址 =====================

mcp_services = dict(
    weather=os.getenv("MCP_WEATHER_URL", "http://localhost:6001"),
    ticket=os.getenv("MCP_TICKET_URL", "http://localhost:6002"),
    knowledge=os.getenv("MCP_KNOWLEDGE_URL", "http://localhost:6003"),
    review=os.getenv("MCP_REVIEW_URL", "http://localhost:6004"),
)

# A2A Agent 地址
a2a_agents = dict(
    weather=os.getenv("A2A_WEATHER_URL", "http://localhost:5005"),
    ticket=os.getenv("A2A_TICKET_URL", "http://localhost:5006"),
    router=os.getenv("A2A_ROUTER_URL", "http://localhost:6666"),
    attraction=os.getenv("A2A_ATTRACTION_URL", "http://localhost:5007"),
    visual=os.getenv("A2A_VISUAL_URL", "http://localhost:5008"),
)


# ===================== 外部 API 配置 =====================

# 和风天气 API
weather_api = dict(
    key=os.getenv("QW_API_KEY", ""),
    base_url="https://api.qweather.com/v7",
)

# 携程 / 12306 / 大麦 API（占位，需对接真实接口）
ticket_api = dict(
    ctrip_base_url=os.getenv("CTRIP_API_URL", ""),
    ctrip_key=os.getenv("CTRIP_API_KEY", ""),
    damai_base_url=os.getenv("DAMAI_API_URL", ""),
    damai_key=os.getenv("DAMAI_API_KEY", ""),
)


# ===================== Milvus 向量库配置 =====================

milvus_config = dict(
    host=os.getenv("MILVUS_HOST", "localhost"),
    port=os.getenv("MILVUS_PORT", "19530"),
    collection="attraction_knowledge",
    embedding_model="bge-m3",
    top_k=5,
)


# ===================== MySQL 数据库配置 =====================
# 本地开发直接写死，Docker 部署时通过环境变量覆盖

mysql_config = dict(
    host=os.getenv("MYSQL_HOST", "127.0.0.1"),
    port=int(os.getenv("MYSQL_PORT", "3306")),
    user="root",
    password=os.getenv("MYSQL_PASSWORD", "12345678"),
    database="etraval_agent",
)


# ===================== A2A 协议配置 =====================

a2a_protocol = dict(
    task_timeout=30,          # 任务超时（秒）
    max_retries=3,            # 最大重试次数
    retry_delay=1.0,          # 重试间隔（秒）
    storage_backend="memory", # 任务存储后端：memory / redis
)
