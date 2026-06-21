#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : mcp_weather_server.py
@Function: 天气 MCP Server（迁移自 SmartVoyage）
- 提供天气数据库查询接口（只读 SELECT）
- 对接和风天气 API 实时数据
- 统一 MCP 工具规范
"""
import os
import sys
import json
import logging
import mysql.connector
from datetime import date, datetime, timedelta
from decimal import Decimal
from python_a2a.mcp import FastMCP, create_fastapi_app
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.llm_config import mysql_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.strftime('%Y-%m-%d %H:%M:%S') if isinstance(obj, datetime) else obj.strftime('%Y-%m-%d')
        if isinstance(obj, timedelta):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


class WeatherService:
    def __init__(self):
        self.conn = mysql.connector.connect(**mysql_config)

    def execute_query(self, sql: str) -> str:
        try:
            cursor = self.conn.cursor(dictionary=True)
            cursor.execute(sql)
            results = cursor.fetchall()
            cursor.close()
            for result in results:
                for key, value in result.items():
                    if isinstance(value, (date, datetime, timedelta, Decimal)):
                        result[key] = self._encode(value)
            return json.dumps(
                {"status": "success", "data": results} if results
                else {"status": "no_data", "message": "未找到天气数据，请确认城市和日期。"},
                cls=DateEncoder, ensure_ascii=False
            )
        except Exception as e:
            logger.error(f"天气查询错误: {str(e)}")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    def _encode(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        if isinstance(obj, timedelta):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        return obj


def create_weather_mcp_server():
    """创建天气 MCP 服务器"""
    weather_mcp = FastMCP(
        name="WeatherTools",
        description="天气查询工具，基于 weather_data 表，提供城市天气预报数据查询。",
        version="2.0.0"
    )
    service = WeatherService()

    @weather_mcp.tool(
        name="query_weather",
        description=(
            "查询天气数据。参数: sql - SELECT 语句。"
            "表结构: weather_data(city, fx_date, temp_max, temp_min, text_day, text_night, humidity, wind_dir_day, precip)"
            "示例: SELECT * FROM weather_data WHERE city = '北京' AND fx_date = '2025-07-30'"
        )
    )
    def query_weather(sql: str) -> str:
        logger.info(f"执行天气查询: {sql}")
        return service.execute_query(sql)

    logger.info("=== 天气 MCP 服务器信息 ===")
    logger.info(f"名称: {weather_mcp.name}")
    logger.info(f"描述: {weather_mcp.description}")

    port = 6001
    app = create_fastapi_app(weather_mcp)
    logger.info(f"启动天气 MCP 服务器于 http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    create_weather_mcp_server()
