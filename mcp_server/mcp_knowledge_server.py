#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : mcp_knowledge_server.py
@Function: 知识检索 MCP Server
- 基于 Milvus + bge-m3 的向量混合检索（有 Milvus 时）
- 降级为内置景点知识库关键词检索（无 Milvus 时）
- 支持语义检索 + 分类筛选 + 城市过滤
- 内置 25+ 热门景点知识数据（无需外部依赖即可演示）
"""
import os
import sys
import json
import logging
from python_a2a.mcp import FastMCP, create_fastapi_app
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.llm_config import milvus_config
from knowledge_base import MilvusClient, BUILTIN_KNOWLEDGE, CATEGORY_INDEX, CITY_INDEX

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class KnowledgeService:
    def __init__(self):
        # 初始化检索客户端（自动探测 Milvus 可用性）
        self.client = MilvusClient(milvus_config)
        self._mode = "milvus" if self.client.milvus_available else "builtin_keyword"
        logger.info(f"知识检索服务初始化: mode={self._mode}, collection={milvus_config['collection']}")

    def _format_results(self, results: list, query: str, city: str) -> str:
        """统一格式化检索结果"""
        return json.dumps({
            "status": "success",
            "mode": self._mode,
            "query": query,
            "city": city,
            "total": len(results),
            "data": results,
        }, ensure_ascii=False)

    def hybrid_search(self, query: str, city: str = "", top_k: int = 5) -> str:
        """
        混合检索知识库
        1. Milvus 可用时：bge-m3 稠密向量 + BM25 稀疏向量
        2. 降级时：关键词匹配 + 分类/城市过滤
        """
        logger.info(f"知识检索: query={query}, city={city}, top_k={top_k}")
        try:
            results = self.client.hybrid_search(query, city, top_k)
            return self._format_results(results, query, city)
        except Exception as e:
            logger.error(f"知识检索失败: {e}")
            return json.dumps({
                "status": "error",
                "message": str(e),
                "query": query,
                "city": city,
                "data": []
            }, ensure_ascii=False)

    def get_by_category(self, category: str, top_k: int = 10) -> str:
        """按分类检索景点"""
        items = CATEGORY_INDEX.get(category, [])
        items = sorted(items, key=lambda x: x["rating"], reverse=True)[:top_k]
        return json.dumps({
            "status": "success",
            "category": category,
            "total": len(items),
            "data": items,
        }, ensure_ascii=False)

    def get_by_city(self, city: str, top_k: int = 10) -> str:
        """按城市检索景点"""
        items = CITY_INDEX.get(city, [])
        items = sorted(items, key=lambda x: x["rating"], reverse=True)[:top_k]
        return json.dumps({
            "status": "success",
            "city": city,
            "total": len(items),
            "data": items,
        }, ensure_ascii=False)

    def get_categories(self) -> str:
        """获取所有景点分类"""
        categories = list(CATEGORY_INDEX.keys())
        return json.dumps({
            "status": "success",
            "categories": categories,
            "counts": {cat: len(items) for cat, items in CATEGORY_INDEX.items()}
        }, ensure_ascii=False)


def create_knowledge_mcp_server():
    knowledge_mcp = FastMCP(
        name="KnowledgeTools",
        description="旅游知识检索工具。支持 Milvus + bge-m3 向量检索（自动降级为关键词检索），提供景点知识、路线推荐。",
        version="2.0.0"
    )
    service = KnowledgeService()

    @knowledge_mcp.tool(
        name="search_attractions",
        description="搜索景点知识。参数: query(搜索关键词), city(城市,可选), top_k(返回数量,默认5)"
    )
    def search_attractions(query: str, city: str = "", top_k: int = 5) -> str:
        return service.hybrid_search(query, city, top_k)

    @knowledge_mcp.tool(
        name="get_travel_routes",
        description="获取旅游路线推荐。参数: query(需求描述), top_k(返回数量)"
    )
    def get_travel_routes(query: str, top_k: int = 3) -> str:
        return service.hybrid_search(query, top_k=top_k)

    @knowledge_mcp.tool(
        name="get_attractions_by_city",
        description="按城市获取景点列表。参数: city(城市名称), top_k(返回数量)"
    )
    def get_attractions_by_city(city: str, top_k: int = 10) -> str:
        return service.get_by_city(city, top_k)

    @knowledge_mcp.tool(
        name="get_attractions_by_category",
        description="按分类获取景点列表。分类: 文化/自然/山岳/海滨/古镇/都市/主题公园/历史/海岛/园林。参数: category(分类名), top_k(返回数量)"
    )
    def get_attractions_by_category(category: str, top_k: int = 10) -> str:
        return service.get_by_category(category, top_k)

    @knowledge_mcp.tool(
        name="get_categories",
        description="获取所有景点分类列表"
    )
    def get_categories() -> str:
        return service.get_categories()

    port = 6003
    app = create_fastapi_app(knowledge_mcp)
    logger.info(f"启动知识检索 MCP 服务器于 http://localhost:{port} (mode={service._mode})")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    create_knowledge_mcp_server()
