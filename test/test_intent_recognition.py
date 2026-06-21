#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : test_intent_recognition.py
@Function: 意图识别单元测试（迁移自 SmartVoyage 9_main_intent.py，适配新架构）
- 覆盖所有意图类型（weather/flight/train/concert/attraction/visual）
- 测试完整输入、缺失槽位追问、组合意图
"""
import json
import sys
import os
from datetime import datetime
import pytz
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.llm_config import main_llm

llm = ChatOpenAI(**main_llm)

intent_prompt = ChatPromptTemplate.from_template("""
系统提示：您是一个专业的旅行意图识别专家，基于用户查询和对话历史，识别意图并提取槽位。
支持意图：['weather', 'flight', 'train', 'concert', 'attraction', 'visual']
如果超出范围，返回 'out_of_scope'。
输出严格为JSON格式。

当前日期：{current_date}
对话历史：{conversation_history}
用户查询：{query}
""")


def recognize_intent(conversation_history, query, current_date):
    chain = intent_prompt | llm
    response = chain.invoke({
        "conversation_history": conversation_history,
        "query": query,
        "current_date": current_date
    }).content.strip()
    try:
        return json.loads(response)
    except json.JSONDecodeError as e:
        return {"error": f"JSON解析失败: {e}", "raw": response}


if __name__ == '__main__':
    print("=== Etraval-agent 意图识别测试 ===\n")
    current_date = "2026-06-20"
    history = ""

    tests = [
        ("weather完整", "北京明天天气",
         lambda r: "weather" in r["intents"] and r["slots"]["weather"]["city"] == "北京"),
        ("weather缺失", "天气",
         lambda r: "weather" in r["intents"] and "missing_slots" in r),
        ("flight完整", "深圳到北京的机票 2026-06-22",
         lambda r: "flight" in r["intents"] and r["slots"]["flight"]["departure_city"] == "深圳"),
        ("train完整", "深圳到广州的高铁 2026-06-21 二等座",
         lambda r: "train" in r["intents"] and r["slots"]["train"]["departure_city"] == "深圳"),
        ("concert完整", "深圳周杰伦演唱会 2026-06-23 VIP",
         lambda r: "concert" in r["intents"] and r["slots"]["concert"]["artist"] == "周杰伦"),
        ("attraction", "推荐北京的文化景点",
         lambda r: "attraction" in r["intents"] and r["slots"]["attraction"]["city"] == "北京"),
        ("组合意图", "北京明天天气和深圳到上海的机票",
         lambda r: set(r["intents"]) == {"weather", "flight"}),
        ("超出范围", "你好，你会什么",
         lambda r: "out_of_scope" in r["intents"]),
    ]

    passed = 0
    for name, query, check in tests:
        result = recognize_intent(history, query, current_date)
        try:
            assert check(result), f"断言失败: {result}"
            print(f"✅ {name}: {query} → {result.get('intents', [])}")
            passed += 1
        except AssertionError as e:
            print(f"❌ {name}: {query} → {result} | {e}")

    print(f"\n{'='*40}")
    print(f"结果: {passed}/{len(tests)} 通过")
