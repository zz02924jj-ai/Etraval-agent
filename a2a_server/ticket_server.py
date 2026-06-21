#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : ticket_server.py
@Function: 票务查询 A2A Agent（react 模式，迁移自 SmartVoyage）
- 使用 LLM 进行意图分类 + SQL生成
- 调用票务 MCP Server 获取数据
- 支持三种票务：高铁(train)、机票(flight)、演唱会(concert)
"""
import json
import os
import sys
import re
from python_a2a import A2AServer, run_server, AgentCard, AgentSkill
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import colorlog
import logging
from datetime import datetime
import pytz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.llm_config import ticket_llm, mcp_services

# 彩色日志
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
    log_colors={'INFO': 'green', 'ERROR': 'red'}
))
logger = colorlog.getLogger()
logger.addHandler(handler)
logger.setLevel(colorlog.INFO)


# 票务数据库 Schema
DATABASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS train_tickets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    departure_city VARCHAR(50), arrival_city VARCHAR(50),
    departure_time DATETIME NOT NULL, arrival_time DATETIME NOT NULL,
    train_number VARCHAR(20) NOT NULL, seat_type VARCHAR(20),
    total_seats INT NOT NULL, remaining_seats INT NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    UNIQUE KEY unique_train (departure_time, train_number)
);
CREATE TABLE IF NOT EXISTS flight_tickets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    departure_city VARCHAR(50), arrival_city VARCHAR(50),
    departure_time DATETIME NOT NULL, arrival_time DATETIME NOT NULL,
    flight_number VARCHAR(20) NOT NULL, cabin_type VARCHAR(20),
    total_seats INT NOT NULL, remaining_seats INT NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    UNIQUE KEY unique_flight (departure_time, flight_number)
);
CREATE TABLE IF NOT EXISTS concert_tickets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    artist VARCHAR(100), city VARCHAR(50), venue VARCHAR(100),
    start_time DATETIME NOT NULL, end_time DATETIME NOT NULL,
    ticket_type VARCHAR(20), total_seats INT NOT NULL,
    remaining_seats INT NOT NULL, price DECIMAL(10, 2) NOT NULL,
    UNIQUE KEY unique_concert (start_time, artist, ticket_type)
);
"""

# react 模式 Prompt：先分类再生成SQL
sql_prompt = ChatPromptTemplate.from_template("""
系统提示：你是一个专业的票务SQL生成器，根据对话历史：
1. 分类查询类型（train: 火车/高铁, flight: 机票, concert: 演唱会），输出：{{"type": "train"}}
2. 根据分类，生成对应表的 SELECT 语句
3. 如果无法分类或缺少必要信息，输出追问JSON
4. 无结果不编造
5. 不要包含 ```json 或 ```sql

schema：
{schema}

示例：
- user: 火车票 深圳 广州 2026-06-21 二等座
  输出:
  {{"type": "train"}}
  SELECT id, departure_city, arrival_city, departure_time, arrival_time, train_number, seat_type, price, remaining_seats FROM train_tickets WHERE departure_city = '深圳' AND arrival_city = '广州' AND DATE(departure_time) = '2026-06-21' AND seat_type = '二等座'

- user: 机票 深圳 北京 2026-06-22 经济舱
  输出:
  {{"type": "flight"}}
  SELECT id, departure_city, arrival_city, departure_time, arrival_time, flight_number, cabin_type, price, remaining_seats FROM flight_tickets WHERE departure_city = '深圳' AND arrival_city = '北京' AND DATE(departure_time) = '2026-06-22' AND cabin_type = '经济舱'

- user: 演唱会 深圳 周杰伦 2026-06-23 VIP
  输出:
  {{"type": "concert"}}
  SELECT id, artist, city, venue, start_time, end_time, ticket_type, price, remaining_seats FROM concert_tickets WHERE city = '深圳' AND artist = '周杰伦' AND DATE(start_time) = '2026-06-23' AND ticket_type = 'VIP'

- user: 你好
  输出: {{"status": "input_required", "message": "请提供票务类型（如火车票、机票、演唱会）和必要信息。"}}

对话历史: {conversation}
当前日期: {current_date} (Asia/Shanghai)
""")


class TicketQueryServer(A2AServer):
    def __init__(self):
        agent_card = AgentCard(
            name="Ticket Query Assistant",
            description="基于 GLM-4-32B (react模式) 提供票务查询服务的助手",
            url="http://localhost:5006",
            version="2.0.0",
            capabilities={"streaming": True, "memory": True},
            skills=[AgentSkill(
                name="execute ticket query",
                description="根据客户端提供的输入执行票务查询，支持自然语言输入",
                examples=["火车票 深圳 广州 2026-06-21 二等座", "机票 深圳 北京 经济舱", "演唱会 深圳 周杰伦"]
            )]
        )
        super().__init__(agent_card=agent_card)
        self.llm = ChatOpenAI(**ticket_llm)
        self.sql_prompt = sql_prompt
        self.schema = DATABASE_SCHEMA

    def generate_sql_query(self, conversation: str) -> dict:
        """react 模式：先分类意图，再生成 SQL"""
        try:
            current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
            chain = self.sql_prompt | self.llm
            output = chain.invoke(
                {"schema": self.schema, "conversation": conversation, "current_date": current_date}
            ).content.strip()
            logger.info(f"原始 LLM 输出: {output}")

            lines = output.split('\n')
            type_line = lines[0].strip()
            if type_line.startswith('```json'):
                type_line = lines[1].strip()
                sql_lines = lines[3:-1] if lines[-1].strip() == '```' else lines[3:]
            else:
                sql_lines = lines[1:] if len(lines) > 1 else []

            if type_line.startswith('{"type":'):
                query_type = json.loads(type_line)["type"]
                sql_query = ' '.join([line.strip() for line in sql_lines if line.strip() and not line.startswith('```')])
                return {"status": "sql", "type": query_type, "sql": sql_query}
            elif 'input_required' in type_line:
                return json.loads(type_line)
            else:
                return {"status": "input_required", "message": "无法解析查询，请提供更明确的信息。"}
        except Exception as e:
            logger.error(f"SQL 生成失败: {str(e)}")
            return {"status": "input_required", "message": "查询无效，请提供票务相关信息。"}

    def handle_message(self, message):
        """处理消息 - 被框架自动调用"""
        conversation = message.content.text if hasattr(message.content, 'text') else str(message.content)
        logger.info(f"票务查询输入: {conversation}")

        try:
            gen_result = self.generate_sql_query(conversation)
            if gen_result.get("status") == "input_required":
                from python_a2a import Message as RespMessage, TextContent, MessageRole
                return RespMessage(
                    content=TextContent(text=gen_result.get("message", "请提供票务相关信息。")),
                    role=MessageRole.AGENT
                )

            sql_query = gen_result["sql"]
            query_type = gen_result["type"]
            logger.info(f"SQL: {sql_query} (类型: {query_type})")

            # 直接调用数据库服务
            from mcp_server.mcp_ticket_server import TicketService
            service = TicketService()
            ticket_result = service.query_tickets_fallback(sql_query)

            response = json.loads(ticket_result) if isinstance(ticket_result, str) else ticket_result
            logger.info(f"MCP 返回: {response}")

            if response.get("status") == "no_data":
                response_text = f"{response.get('message', '未找到数据')} 如果需要其他日期，请补充。"
            else:
                data = response.get("data", [])
                response_text = ""
                for d in data:
                    if query_type == "train":
                        response_text += f"{d['departure_city']}→{d['arrival_city']} {d['departure_time']}: 车次 {d['train_number']}，{d['seat_type']}，票价 {d['price']}元，余 {d['remaining_seats']}张\n"
                    elif query_type == "flight":
                        response_text += f"{d['departure_city']}→{d['arrival_city']} {d['departure_time']}: 航班 {d['flight_number']}，{d['cabin_type']}，票价 {d['price']}元，余 {d['remaining_seats']}张\n"
                    elif query_type == "concert":
                        response_text += f"{d['city']} {d['start_time']}: {d['artist']}演唱会，{d['ticket_type']}，场地 {d['venue']}，票价 {d['price']}元，余 {d['remaining_seats']}张\n"
                if not response_text:
                    response_text = "无结果。"

            from python_a2a import Message as RespMessage, TextContent, MessageRole
            return RespMessage(
                content=TextContent(text=response_text.strip()),
                role=MessageRole.AGENT
            )
        except Exception as e:
            logger.error(f"查询失败: {str(e)}")
            from python_a2a import Message as RespMessage, TextContent, MessageRole
            return RespMessage(
                content=TextContent(text=f"查询失败: {str(e)} 请重试。"),
                role=MessageRole.AGENT
            )


def main():
    ticket_server = TicketQueryServer()
    print(f"=== 票务 Agent 服务器 ===")
    print(f"名称: {ticket_server.agent_card.name}")
    run_server(ticket_server, host="0.0.0.0", port=5006)


if __name__ == "__main__":
    import sys as _sys
    try:
        main()
        _sys.exit(0)
    except KeyboardInterrupt:
        print("\n✅ 程序被用户中断")
        _sys.exit(0)
