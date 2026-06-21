#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : weather_server.py
@Function: 天气查询 A2A Agent（迁移自 SmartVoyage，基于 GLM-4-32B）
- 使用 LLM 将自然语言转化为 SQL
- 调用天气 MCP Server 获取数据
- 支持多轮对话上下文理解
"""
import json
import os
import sys
from python_a2a import A2AServer, run_server, AgentCard, AgentSkill
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import colorlog
from datetime import datetime, timedelta
import pytz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.llm_config import weather_llm
from mcp_server.mcp_weather_server import WeatherService, DateEncoder

# 彩色日志
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
    log_colors={'INFO': 'green', 'ERROR': 'red'}
))
logger = colorlog.getLogger()
logger.addHandler(handler)
logger.setLevel(colorlog.INFO)


# 天气数据表 Schema
DATABASE_SCHEMA = """CREATE TABLE IF NOT EXISTS weather_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    city VARCHAR(50) NOT NULL COMMENT '城市名称',
    fx_date DATE NOT NULL COMMENT '预报日期',
    sunrise TIME COMMENT '日出时间', sunset TIME COMMENT '日落时间',
    moonrise TIME COMMENT '月升时间', moonset TIME COMMENT '月落时间',
    moon_phase VARCHAR(20) COMMENT '月相名称', moon_phase_icon VARCHAR(10) COMMENT '月相图标代码',
    temp_max INT COMMENT '最高温度', temp_min INT COMMENT '最低温度',
    icon_day VARCHAR(10) COMMENT '白天天气图标代码', text_day VARCHAR(20) COMMENT '白天天气描述',
    icon_night VARCHAR(10) COMMENT '夜间天气图标代码', text_night VARCHAR(20) COMMENT '夜间天气描述',
    wind360_day INT COMMENT '白天风向360角度', wind_dir_day VARCHAR(20) COMMENT '白天风向',
    wind_scale_day VARCHAR(10) COMMENT '白天风力等级', wind_speed_day INT COMMENT '白天风速 (km/h)',
    wind360_night INT COMMENT '夜间风向360角度', wind_dir_night VARCHAR(20) COMMENT '夜间风向',
    wind_scale_night VARCHAR(10) COMMENT '夜间风力等级', wind_speed_night INT COMMENT '夜间风速 (km/h)',
    precip DECIMAL(5,1) COMMENT '降水量 (mm)', uv_index INT COMMENT '紫外线指数',
    humidity INT COMMENT '相对湿度 (%)', pressure INT COMMENT '大气压强 (hPa)',
    vis INT COMMENT '能见度 (km)', cloud INT COMMENT '云量 (%)',
    update_time DATETIME COMMENT '数据更新时间',
    UNIQUE KEY unique_city_date (city, fx_date)
) ENGINE=INNODB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='天气数据表';"""


sql_prompt = ChatPromptTemplate.from_template("""
系统提示：你是一个专业的天气SQL生成器，仅基于weather_data表生成SELECT语句。
- 无结果不编造。
- 输出纯SQL，不要任何额外内容。

数据库的建表语句如下：
{schema}

示例：
- user: 北京 2025-07-30
  输出: SELECT city, fx_date, temp_max, temp_min, text_day, text_night, humidity, wind_dir_day, precip FROM weather_data WHERE city = '北京' AND fx_date = '2025-07-30'
- user: 上海未来3天
  输出: SELECT city, fx_date, temp_max, temp_min, text_day, text_night, humidity, wind_dir_day, precip FROM weather_data WHERE city = '上海' AND fx_date BETWEEN '2025-07-30' AND '2025-08-01' ORDER BY fx_date
- user: 你好
  输出: {{"status": "input_required", "message": "请提供城市和日期，例如 '北京 2025-07-30'。"}}
- user: 今天
  输出: {{"status": "input_required", "message": "请提供天气相关查询，包括城市和日期。"}}

对话历史: {conversation}
当前日期: {current_date} (Asia/Shanghai)
""")


class WeatherQueryServer(A2AServer):
    def __init__(self):
        agent_card = AgentCard(
            name="Weather Query Assistant",
            description="基于 GLM-4-32B 提供天气查询服务的助手",
            url="http://localhost:5005",
            version="2.0.0",
            capabilities={"streaming": True, "memory": True},
            skills=[AgentSkill(
                name="execute weather query",
                description="执行天气查询，返回天气数据库结果，支持自然语言输入",
                examples=["北京 2025-07-30 天气", "上海未来5天", "今天天气如何"]
            )]
        )
        super().__init__(agent_card=agent_card)
        self.llm = ChatOpenAI(**weather_llm)
        self.sql_prompt = sql_prompt
        self.schema = DATABASE_SCHEMA

    def generate_sql_query(self, conversation: str) -> dict:
        try:
            current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
            chain = self.sql_prompt | self.llm
            output = chain.invoke(
                {"conversation": conversation, "current_date": current_date, "schema": self.schema}
            ).content.strip()
            if output.startswith('{'):
                return json.loads(output)
            return {"status": "sql", "sql": output}
        except Exception as e:
            logger.error(f"SQL生成失败: {str(e)}")
            return {"status": "input_required", "message": "查询无效，请提供城市和日期。"}

    def handle_message(self, message):
        """处理消息 - 被框架自动调用，message 是 Message 对象"""
        conversation = message.content.text if hasattr(message.content, 'text') else str(message.content)
        logger.info(f"天气查询输入: {conversation}")

        try:
            gen_result = self.generate_sql_query(conversation)
            if gen_result.get("status") == "input_required":
                from python_a2a import Message as RespMessage, TextContent, MessageRole
                return RespMessage(
                    content=TextContent(text=gen_result.get("message", "请提供城市和日期。")),
                    role=MessageRole.AGENT
                )

            sql_query = gen_result["sql"]
            logger.info(f"SQL: {sql_query}")

            # 直接调用数据库服务
            service = WeatherService()
            weather_result = service.execute_query(sql_query)

            response = json.loads(weather_result) if isinstance(weather_result, str) else weather_result
            if response.get("status") == "no_data":
                response_text = f"{response.get('message', '未找到数据')} 如果需要其他日期，请补充。"
            else:
                data = response.get("data", [])
                response_text = "\n".join([
                    f"{d['city']} {d['fx_date']}: {d['text_day']}（夜间 {d['text_night']}），"
                    f"温度 {d['temp_min']}-{d['temp_max']}°C，湿度 {d['humidity']}%，"
                    f"风向 {d['wind_dir_day']}，降水 {d['precip']}mm"
                    for d in data
                ])

            from python_a2a import Message as RespMessage, TextContent, MessageRole
            return RespMessage(
                content=TextContent(text=response_text),
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
    weather_server = WeatherQueryServer()
    print(f"=== 天气 Agent 服务器 ===")
    print(f"名称: {weather_server.agent_card.name}")
    run_server(weather_server, host="0.0.0.0", port=5005)


if __name__ == "__main__":
    import sys as _sys
    try:
        main()
        _sys.exit(0)
    except KeyboardInterrupt:
        print("\n✅ 程序被用户中断")
        _sys.exit(0)
