#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : evaluator.py
@Function: 端到端自动化评估工具（迁移自 SmartVoyage，适配新架构）
- 意图识别准确率
- 响应关键词匹配率
- LLM 质量评分
"""
import json
import logging
import os
import time
import sys
import re
from datetime import datetime
from typing import Dict, List, Any
import pytz
from python_a2a import A2AClient, AgentNetwork, AIAgentRouter
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.llm_config import main_llm, a2a_agents

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# 意图识别 Prompt（与 main.py 保持一致）
intent_prompt = ChatPromptTemplate.from_template("""
系统提示：您是一个专业的旅行意图识别专家。支持意图：
['weather', 'flight', 'train', 'concert', 'attraction', 'visual'] 或其组合。
如果意图超出范围，返回 'out_of_scope'。
输出严格JSON格式。

当前日期：{current_date}
对话历史：{conversation_history}
用户查询：{query}
""")

# 评估 Prompt
response_eval_prompt = ChatPromptTemplate.from_template("""
评分标准：
1. 流畅性：回答是否自然通顺
2. 准确性：信息是否准确
3. 帮助性：是否解决用户问题

用户查询: {user_query}
智能体响应: {agent_response}

请以JSON格式返回评估结果：{{"score": 4.5, "reason": "..."}}
""")


summarize_weather_prompt = ChatPromptTemplate.from_template("""
系统提示：您是一位专业的天气预报员。基于查询和结果总结天气信息。
查询：{query}
结果：{raw_response}
""")

summarize_ticket_prompt = ChatPromptTemplate.from_template("""
系统提示：您是一位专业的旅行顾问。基于查询和结果总结票务信息。
查询：{query}
结果：{raw_response}
""")

attraction_prompt = ChatPromptTemplate.from_template("""
系统提示：您是一位旅行专家，基于用户查询生成景点推荐。
查询：{query}
槽位：{slots}
""")


class AgentEvaluator:
    def __init__(self):
        self.llm = ChatOpenAI(**main_llm)
        self.intent_chain = intent_prompt | self.llm
        self.eval_chain = response_eval_prompt | self.llm
        self.summarize_weather_chain = summarize_weather_prompt | self.llm
        self.summarize_ticket_chain = summarize_ticket_prompt | self.llm
        self.attraction_chain = attraction_prompt | self.llm

        self.network = AgentNetwork(name="Etraval Network")
        self.network.add("Weather Query Assistant", a2a_agents["weather"])
        self.network.add("Ticket Query Assistant", a2a_agents["ticket"])
        self.network.add("Attraction Assistant", a2a_agents["attraction"])

    def simulate_response(self, user_query: str, current_date: str) -> str:
        intent_response = self.intent_chain.invoke({
            "conversation_history": "", "query": user_query, "current_date": current_date
        }).content.strip()
        intent_response = re.sub(r'^```json\s*|\s*```$', '', intent_response).strip()
        intent_output = json.loads(intent_response)
        intents = intent_output.get("intents", [])
        slots = intent_output.get("slots", {})
        missing_slots = intent_output.get("missing_slots", {})

        if "out_of_scope" in intents:
            return "您好！我是Etraval智能旅行助手..."
        elif missing_slots:
            return intent_output.get("follow_up_message", "请提供更多信息。")

        responses = []
        for intent in intents:
            agent_name = {
                "weather": "Weather Query Assistant",
                "flight": "Ticket Query Assistant",
                "train": "Ticket Query Assistant",
                "concert": "Ticket Query Assistant",
                "attraction": "Attraction Assistant",
            }.get(intent)

            if intent == "attraction":
                rec = self.attraction_chain.invoke({
                    "query": user_query,
                    "slots": json.dumps(slots.get(intent, {}), ensure_ascii=False)
                }).content.strip()
                responses.append(rec)
            elif agent_name:
                intent_slots = slots.get(intent, {})
                if intent == "weather":
                    query_str = f"{intent_slots.get('city', '北京,上海,广州,深圳')} {intent_slots.get('date', current_date)}"
                else:
                    query_str = f"{intent} {intent_slots.get('departure_city', '')} {intent_slots.get('arrival_city', '')} {intent_slots.get('date', current_date)} {intent_slots.get('seat_type', '')}".strip()

                agent = self.network.get_agent(agent_name)
                raw_response = agent.ask(query_str)

                chain = self.summarize_weather_chain if intent == "weather" else self.summarize_ticket_chain
                sum_resp = chain.invoke({"query": query_str, "raw_response": raw_response}).content.strip()
                responses.append(sum_resp)

        return "\n\n".join(responses)

    def evaluate_test_cases(self, test_cases: List[Dict[str, Any]]):
        results = {
            "total_tests": len(test_cases),
            "correct_intent": 0,
            "correct_response_keywords": 0,
            "latency_sum": 0.0,
            "llm_score_sum": 0.0,
            "failures": []
        }
        current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')

        for i, case in enumerate(test_cases):
            user_query = case["query"]
            expected_intent = case["expected_intent"]
            expected_keywords = case.get("expected_keywords", [])
            logger.info(f"--- 用例 {i + 1}/{results['total_tests']}: {user_query} ---")

            start = time.time()
            try:
                # 意图识别
                resp = self.intent_chain.invoke({
                    "conversation_history": "", "query": user_query, "current_date": current_date
                }).content.strip()
                resp = re.sub(r'^```json\s*|\s*```$', '', resp).strip()
                output = json.loads(resp)
                detected = output.get("intents", [])
                if expected_intent in detected:
                    results["correct_intent"] += 1

                # 端到端响应
                final = self.simulate_response(user_query, current_date)
                latency = time.time() - start
                results["latency_sum"] += latency

                if all(kw in final for kw in expected_keywords):
                    results["correct_response_keywords"] += 1

                # LLM 评分
                eval_resp = self.eval_chain.invoke({
                    "user_query": user_query, "agent_response": final
                }).content.strip()
                eval_resp = re.sub(r'^```json\s*|\s*```$', '', eval_resp).strip()
                eval_out = json.loads(eval_resp)
                results["llm_score_sum"] += eval_out.get("score", 0.0)

                logger.info(f"预期: {expected_intent}, 实际: {detected}, 耗时:{latency:.2f}s, 评分:{eval_out.get('score', 0):.1f}")

                if expected_intent not in detected or not all(kw in final for kw in expected_keywords):
                    results["failures"].append({"query": user_query, "reason": "Intent or keyword mismatch"})
            except Exception as e:
                logger.error(f"用例失败: {e}")
                results["failures"].append({"query": user_query, "reason": str(e)})

        return results

    def print_summary(self, results: Dict[str, Any]):
        total = results['total_tests']
        print(f"\n\n--- Etraval-agent 评估报告 ---")
        print(f"总测试用例: {total}")
        print(f"意图识别准确率: {results['correct_intent'] / total:.2%} ({results['correct_intent']}/{total})")
        print(f"关键词匹配率: {results['correct_response_keywords'] / total:.2%}")
        print(f"平均响应时间: {results['latency_sum'] / total:.2f}s")
        print(f"LLM平均分: {results['llm_score_sum'] / total:.2f}/5.0")
        if results['failures']:
            print(f"\n失败: {len(results['failures'])}/{total}")


if __name__ == "__main__":
    test_cases = [
        {"query": "北京明天天气如何？", "expected_intent": "weather", "expected_keywords": ["北京", "天气"]},
        {"query": "查一下明天深圳到广州的高铁，二等座", "expected_intent": "train", "expected_keywords": ["高铁", "深圳", "广州"]},
        {"query": "深圳最近一周的演唱会", "expected_intent": "concert", "expected_keywords": ["演唱会"]},
        {"query": "推荐北京的文化景点", "expected_intent": "attraction", "expected_keywords": ["北京", "景点"]},
        {"query": "你好，你可以做什么？", "expected_intent": "out_of_scope", "expected_keywords": ["Etraval", "助手"]},
        {"query": "北京的天气和明天去上海的高铁票", "expected_intent": "weather", "expected_keywords": ["北京", "上海"]},
    ]

    evaluator = AgentEvaluator()
    results = evaluator.evaluate_test_cases(test_cases)
    evaluator.print_summary(results)
