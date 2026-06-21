#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : mcp_ticket_server.py
@Function: 票务 MCP Server（双模式：MySQL虚拟数据 + API预留）
- 模式1（默认）：从MySQL查询虚拟票务数据，实现功能演示
- 模式2（预留）：通过 REAL_API_ENABLED=true 切换到真实API调用
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
from configs.llm_config import mysql_config, ticket_api

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ===== 开关：设为 true 则调用真实 API（待接入）=====
REAL_API_ENABLED = os.getenv("REAL_TICKET_API", "false").lower() == "true"


class DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.strftime('%Y-%m-%d %H:%M:%S') if isinstance(obj, datetime) else obj.strftime('%Y-%m-%d')
        if isinstance(obj, timedelta):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


class TicketService:
    """
    票务服务 - 双模式设计
    - MySQL 模式：从本地数据库查询虚拟数据（默认，可演示）
    - API 模式：调用携程/12306/大麦真实接口（待接入，需 api_key）
    """

    def __init__(self):
        self.conn = mysql.connector.connect(**mysql_config) if not REAL_API_ENABLED else None
        logger.info(f"票务服务初始化: {'API模式' if REAL_API_ENABLED else 'MySQL演示模式'}")

    # ==================== 模式1: MySQL 虚拟数据查询 ====================

    def execute_query(self, sql: str) -> str:
        """执行 SQL 查询（MySQL 模式）"""
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
                else {"status": "no_data", "message": "未找到票务数据，请确认查询条件。"},
                cls=DateEncoder, ensure_ascii=False
            )
        except Exception as e:
            logger.error(f"票务查询错误: {str(e)}")
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

    # ==================== 模式2: 真实 API 预留接口 ====================

    def query_trains_12306(self, departure: str, arrival: str, date_str: str) -> dict:
        """
        TODO: 对接 12306 官方API 查询火车票
        接入条件：获取 12306 开发者 API Key
        返回格式：{"status": "success", "data": [{"train_number":"Gxxx", "departure_time":"...", ...}]}
        """
        raise NotImplementedError(
            "12306 API 未接入。请设置环境变量 CTRIP_API_KEY 获取访问权限，"
            "或使用默认 MySQL 模式（不设置 REAL_TICKET_API=true）"
        )

    def query_flights_ctrip(self, departure: str, arrival: str, date_str: str) -> dict:
        """
        TODO: 对接携程机票 API
        接入条件：获取携程开放平台 API Key
        """
        raise NotImplementedError(
            "携程 API 未接入。请设置环境变量 CTRIP_API_KEY 获取访问权限"
        )

    def query_concerts_damai(self, city: str, keyword: str = "", date_str: str = "") -> dict:
        """
        TODO: 对接大麦演唱会 API
        接入条件：获取大麦开放平台 API Key
        """
        raise NotImplementedError(
            "大麦 API 未接入。请设置环境变量 DAMAI_API_KEY 获取访问权限"
        )

    def query_tickets_fallback(self, sql: str) -> str:
        """
        统一票务查询入口：
        - REAL_API_ENABLED=true 时调用真实API（待实现）
        - 否则降级到 MySQL 虚拟数据
        """
        if REAL_API_ENABLED:
            # 未来这里解析 sql 参数中的意图，分发到对应的真实API
            return json.dumps({
                "status": "api_not_ready",
                "message": "真实票务API待接入，当前为预留接口。请先设置 REAL_TICKET_API=false 使用演示模式。"
            }, ensure_ascii=False)
        return self.execute_query(sql)


def create_ticket_mcp_server():
    ticket_mcp = FastMCP(
        name="TicketTools",
        description="票务查询工具（演示模式：MySQL虚拟数据 | API模式：携程/12306/大麦）",
        version="2.0.0"
    )
    service = TicketService()

    @ticket_mcp.tool(
        name="query_tickets",
        description=(
            "查询票务数据。参数: sql - SELECT 语句。"
            "支持表: train_tickets(高铁), flight_tickets(机票), concert_tickets(演唱会)"
            "示例: SELECT * FROM train_tickets WHERE departure_city = '深圳' AND arrival_city = '广州'"
        )
    )
    def query_tickets(sql: str) -> str:
        logger.info(f"执行票务查询: {sql}")
        return service.query_tickets_fallback(sql)

    port = 6002
    app = create_fastapi_app(ticket_mcp)
    logger.info(f"启动票务 MCP 服务器于 http://localhost:{port}（{'API模式' if REAL_API_ENABLED else 'MySQL演示模式'}）")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    create_ticket_mcp_server()
