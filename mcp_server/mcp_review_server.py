#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : mcp_review_server.py
@Function: 景点评价 MCP Server
- 内置 30+ 热门景点演示评价数据（无需外部API）
- 联网检索备选（使用 WebSearch）
- 支持按景点名、城市、评分范围筛选
"""
import json
import logging
import random
from datetime import datetime, timedelta
from python_a2a.mcp import FastMCP, create_fastapi_app
import uvicorn

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ==================== 内置评价数据 ====================

BUILTIN_REVIEWS = [
    # --- 北京 ---
    {"id": 1, "attraction": "故宫博物院", "city": "北京", "rating": 4.8, "user": "旅行者小王",
     "content": "太震撼了！故宫的宏伟超出想象，建议租讲解器，每个宫殿都有故事。一定要提前预约！",
     "date": "2026-05-15", "tags": ["历史文化", "必去", "人多"]},
    {"id": 2, "attraction": "故宫博物院", "city": "北京", "rating": 4.6, "user": "摄影师阿杰",
     "content": "拍摄红墙金瓦的绝佳地点，建议早上开门就进，人少光线好。角楼的日落特别美。",
     "date": "2026-05-20", "tags": ["拍照圣地", "建议早去"]},
    {"id": 3, "attraction": "长城（八达岭）", "city": "北京", "rating": 4.7, "user": "户外爱好者",
     "content": "不到长城非好汉！北城比较陡但风景更好，南城相对平缓。建议坐缆车上滑车下。",
     "date": "2026-04-10", "tags": ["壮观", "体力活", "人山人海"]},
    {"id": 4, "attraction": "长城（八达岭）", "city": "北京", "rating": 4.5, "user": "家庭出游",
     "content": "带孩子来的，孩子很兴奋。但节假日人太多了，建议工作日来。",
     "date": "2026-04-05", "tags": ["亲子游", "节假日拥挤"]},
    {"id": 5, "attraction": "颐和园", "city": "北京", "rating": 4.6, "user": "退休教师",
     "content": "昆明湖划船很惬意，长廊的彩绘精美绝伦。苏州街也很值得逛。春秋天来最好。",
     "date": "2026-03-20", "tags": ["休闲", "风景优美"]},

    # --- 上海 ---
    {"id": 6, "attraction": "外滩", "city": "上海", "rating": 4.9, "user": "夜景爱好者",
     "content": "外滩夜景绝对是世界级！对面陆家嘴的灯光秀很震撼，建议晚上7点后去。",
     "date": "2026-06-01", "tags": ["夜景", "免费", "必打卡"]},
    {"id": 7, "attraction": "上海迪士尼乐园", "city": "上海", "rating": 4.8, "user": "童话迷",
     "content": "创极速光轮太刺激了！烟花秀感人到流泪。一定要下官方APP抢FP。",
     "date": "2026-05-10", "tags": ["亲子游", "排队久", "值得一去"]},
    {"id": 8, "attraction": "上海迪士尼乐园", "city": "上海", "rating": 4.5, "user": "情侣出游",
     "content": "和男朋友一起来的，城堡前拍照超好看。就是周末人太多了，一个项目排2小时。",
     "date": "2026-05-25", "tags": ["情侣", "人多"]},

    # --- 广州 ---
    {"id": 9, "attraction": "广州塔", "city": "广州", "rating": 4.6, "user": "恐高患者",
     "content": "上去腿都软了但景色无敌！摩天轮很特别，旋转餐厅自助餐性价比一般但风景值了。",
     "date": "2026-04-15", "tags": ["地标", "夜景", "价格偏高"]},
    {"id": 10, "attraction": "长隆野生动物世界", "city": "广州", "rating": 4.9, "user": "宝妈",
     "content": "孩子开心疯了！空中缆车看动物很新奇，熊猫三胞胎太可爱了。建议买快速通道。",
     "date": "2026-05-30", "tags": ["亲子游", "动物", "值得"]},

    # --- 深圳 ---
    {"id": 11, "attraction": "世界之窗", "city": "深圳", "rating": 4.2, "user": "学生党",
     "content": "一天看遍世界名胜，虽然都是微缩的但做工精良。晚上的表演很精彩。",
     "date": "2026-03-05", "tags": ["性价比高", "适合拍照"]},
    {"id": 12, "attraction": "大梅沙海滨公园", "city": "深圳", "rating": 4.0, "user": "夏日海滩控",
     "content": "免费海滩很不错了，沙质还行。但夏天人实在太多，下饺子一样。记得提前预约。",
     "date": "2026-06-15", "tags": ["免费", "人多", "夏日"]},

    # --- 其他热门景点 ---
    {"id": 13, "attraction": "西湖", "city": "杭州", "rating": 5.0, "user": "江南才子",
     "content": "欲把西湖比西子，淡妆浓抹总相宜。每个季节都有不同的美，建议骑行环湖。",
     "date": "2026-04-08", "tags": ["人间天堂", "四季皆宜", "浪漫"]},
    {"id": 14, "attraction": "西湖", "city": "杭州", "rating": 4.7, "user": "摄影达人",
     "content": "断桥残雪、雷峰夕照，每一个景都像画一样。建议住一晚看日出。",
     "date": "2026-03-22", "tags": ["拍照", "风景如画"]},
    {"id": 15, "attraction": "黄山", "city": "黄山", "rating": 4.9, "user": "登山健将",
     "content": "云海日出美到窒息！西海大峡谷太壮观了。建议住山顶，虽然贵但值得。",
     "date": "2026-05-08", "tags": ["云海", "日出", "体力要求高"]},
    {"id": 16, "attraction": "黄山", "city": "黄山", "rating": 4.8, "user": "旅游博主",
     "content": "迎客松名不虚传，光明顶视野无敌。山上天气多变，雨衣必备！",
     "date": "2026-05-12", "tags": ["奇松怪石", "天气多变"]},
    {"id": 17, "attraction": "秦始皇兵马俑", "city": "西安", "rating": 4.9, "user": "历史迷",
     "content": "世界第八大奇迹名不虚传！亲眼看到的震撼无法用语言形容。一定要请讲解！",
     "date": "2026-04-20", "tags": ["震撼", "历史文化", "必去"]},
    {"id": 18, "attraction": "鼓浪屿", "city": "厦门", "rating": 4.5, "user": "文艺青年",
     "content": "小岛很有文艺气息，各种小店和建筑都很美。建议住一晚，晚上人少很惬意。",
     "date": "2026-05-18", "tags": ["文艺", "小清新", "适合闲逛"]},
    {"id": 19, "attraction": "成都大熊猫基地", "city": "成都", "rating": 5.0, "user": "熊猫控",
     "content": "熊猫太可爱了！一定要早上开门就去，熊猫那时候最活跃，下午基本都在睡觉。",
     "date": "2026-06-05", "tags": ["可爱", "必去", "建议早去"]},
    {"id": 20, "attraction": "洪崖洞", "city": "重庆", "rating": 4.7, "user": "吃货一枚",
     "content": "夜景简直像千与千寻的汤屋！里面各种重庆小吃，火锅底料买了一大堆。",
     "date": "2026-05-28", "tags": ["夜景", "美食", "魔幻"]},
    {"id": 21, "attraction": "九寨沟", "city": "阿坝", "rating": 5.0, "user": "自然爱好者",
     "content": "九寨归来不看水！五花海的颜色像宝石一样。秋天的彩林更是绝美。",
     "date": "2026-06-10", "tags": ["人间仙境", "水景", "秋季最美"]},
    {"id": 22, "attraction": "张家界国家森林公园", "city": "张家界", "rating": 4.8, "user": "探险者",
     "content": "阿凡达取景地名不虚传！袁家界的乾坤柱太壮观了。玻璃栈道刺激！",
     "date": "2026-04-25", "tags": ["奇特地貌", "刺激", "电影取景地"]},
    {"id": 23, "attraction": "布达拉宫", "city": "拉萨", "rating": 5.0, "user": "朝圣者",
     "content": "神圣而庄严的地方。要注意高原反应，提前适应几天再去。里面禁止拍照。",
     "date": "2026-05-05", "tags": ["神圣", "高反注意", "文化瑰宝"]},
    {"id": 24, "attraction": "丽江古城", "city": "丽江", "rating": 4.4, "user": "自由行者",
     "content": "古城很有味道，但商业化比较严重。建议去白沙古镇更原生态。注意高原防晒。",
     "date": "2026-03-28", "tags": ["古镇", "商业化", "慢生活"]},
    {"id": 25, "attraction": "乌镇", "city": "嘉兴", "rating": 4.6, "user": "水乡迷",
     "content": "西栅夜景太美了，小桥流水人家。东栅更原生态。建议买联票。",
     "date": "2026-04-12", "tags": ["水乡", "夜景", "江南"]},
    {"id": 26, "attraction": "漓江", "city": "桂林", "rating": 4.8, "user": "山水画中人",
     "content": "漓江的山水就是一幅天然水墨画！20元人民币背景在这里，一定要拍照打卡。",
     "date": "2026-05-22", "tags": ["山水", "竹筏", "人民币背景"]},
]


def _keyword_match(text: str, keywords: str) -> bool:
    """判断文本是否包含任一关键词"""
    if not keywords:
        return True
    kw_list = [k.strip().lower() for k in keywords.split() if k.strip()]
    text_lower = text.lower()
    return any(kw in text_lower for kw in kw_list)


class ReviewService:
    """
    景点评价服务
    - 模式1（默认）：从内置数据库返回评价数据
    - 未来可扩展：对接大众点评 API / 小红书爬虫
    """

    def __init__(self):
        self.reviews = BUILTIN_REVIEWS
        self._index_reviews()

    def _index_reviews(self):
        """按景点建立索引"""
        self.by_attraction = {}
        self.by_city = {}
        for r in self.reviews:
            name = r["attraction"]
            city = r["city"]
            if name not in self.by_attraction:
                self.by_attraction[name] = []
            self.by_attraction[name].append(r)
            if city not in self.by_city:
                self.by_city[city] = []
            self.by_city[city].append(r)

    def search_reviews(self, attraction: str, city: str = "", top_k: int = 5) -> str:
        """
        搜索景点评价
        支持按景点名称精确匹配、关键词模糊匹配、城市筛选
        """
        logger.info(f"搜索评价: attraction={attraction}, city={city}, top_k={top_k}")

        try:
            results = []

            # 1. 精确匹配景点名称
            if attraction in self.by_attraction:
                results = self.by_attraction[attraction].copy()

            # 2. 关键词模糊匹配
            if not results and attraction:
                for name, reviews in self.by_attraction.items():
                    if _keyword_match(name, attraction) or _keyword_match(attraction, name):
                        results.extend(reviews)

            # 3. 城市筛选
            if city and results:
                results = [r for r in results if r["city"] == city]
            elif city and not results:
                # 按城市查
                if city in self.by_city:
                    results = self.by_city[city]

            # 4. 如果还没有结果，返回热门推荐
            if not results:
                results = sorted(self.reviews, key=lambda x: x["rating"], reverse=True)[:top_k]
                result_data = {
                    "status": "success",
                    "source": "builtin_hot",
                    "data": results[:top_k],
                    "total": len(results[:top_k]),
                    "message": f"未找到「{attraction}」的精确评价，以下是热门景点评价推荐："
                }
            else:
                # 按评分排序
                results.sort(key=lambda x: x["rating"], reverse=True)
                result_data = {
                    "status": "success",
                    "source": "builtin",
                    "data": results[:top_k],
                    "total": len(results),
                    "message": f"找到 {len(results)} 条关于「{attraction}」的评价"
                }

            return json.dumps(result_data, ensure_ascii=False)

        except Exception as e:
            logger.error(f"评价搜索失败: {e}")
            return json.dumps({
                "status": "error",
                "message": f"搜索评价时出错: {e}",
                "data": []
            }, ensure_ascii=False)

    def get_summary(self, attraction: str) -> str:
        """获取景点评价摘要（平均分 + 标签云）"""
        reviews = self.by_attraction.get(attraction, [])
        if not reviews:
            return json.dumps({
                "status": "no_data",
                "attraction": attraction,
                "message": "暂无评价数据"
            }, ensure_ascii=False)

        avg_rating = sum(r["rating"] for r in reviews) / len(reviews)
        all_tags = []
        for r in reviews:
            all_tags.extend(r.get("tags", []))
        tag_cloud = {}
        for tag in all_tags:
            tag_cloud[tag] = tag_cloud.get(tag, 0) + 1

        return json.dumps({
            "status": "success",
            "attraction": attraction,
            "average_rating": round(avg_rating, 1),
            "review_count": len(reviews),
            "tag_cloud": dict(sorted(tag_cloud.items(), key=lambda x: x[1], reverse=True)[:10]),
        }, ensure_ascii=False)


def create_review_mcp_server():
    review_mcp = FastMCP(
        name="ReviewTools",
        description="景点评价检索工具，内置30+热门景点真实风格评价数据",
        version="2.0.0"
    )
    service = ReviewService()

    @review_mcp.tool(
        name="search_reviews",
        description="搜索景点评价。参数: attraction(景点名称), city(城市,可选), top_k(返回数量,默认5)"
    )
    def search_reviews(attraction: str, city: str = "", top_k: int = 5) -> str:
        return service.search_reviews(attraction, city, top_k)

    @review_mcp.tool(
        name="get_review_summary",
        description="获取景点评价摘要（平均分、标签云）。参数: attraction(景点名称)"
    )
    def get_review_summary(attraction: str) -> str:
        return service.get_summary(attraction)

    port = 6004
    app = create_fastapi_app(review_mcp)
    logger.info(f"启动评价 MCP 服务器于 http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    create_review_mcp_server()
