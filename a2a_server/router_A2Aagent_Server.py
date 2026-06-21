#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : router_A2Aagent_Server.py
@Function: A2A 路由器 Agent（迁移自 SmartVoyage）
- 将 LangChain ChatOpenAI 包装为 A2A Server
- 作为意图识别的 LLM 路由引擎
"""
import logging
import asyncio
import sys
import os
from langchain_openai import ChatOpenAI
from python_a2a import run_server
from python_a2a.langchain import to_a2a_server

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.llm_config import a2a_llm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    llm = ChatOpenAI(**a2a_llm)
    llm_server = to_a2a_server(llm)
    print(llm_server.agent_card)
    run_server(llm_server, port=6666)


if __name__ == '__main__':
    asyncio.run(main())
