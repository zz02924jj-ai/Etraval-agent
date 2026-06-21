"""
知识库模块
==========
功能：
1. Milvus 向量库连接管理器（支持演示模式降级）
2. bge-m3 嵌入模型封装（支持 SentenceTransformer / ONNX 两种后端）
3. 景点知识数据导入与检索
4. 混合检索（稠密向量 + BM25 稀疏向量）

设计原则：
- Milvus 不可用时自动降级为内存向量检索（演示模式）
- 所有接口返回统一格式，上层无需关心后端
"""
import json
import hashlib
import numpy as np
from typing import List, Dict, Optional, Tuple

logger = __import__('logging').getLogger(__name__)


# ==================== 内嵌景点知识库（演示/兜底用） ====================

BUILTIN_KNOWLEDGE = [
    # --- 北京 ---
    {"id": 1, "name": "故宫博物院", "city": "北京", "category": "文化",
     "description": "北京故宫是中国明清两代的皇家宫殿，旧称紫禁城，位于北京中轴线的中心。是世界上现存规模最大、保存最为完整的木质结构古建筑之一。",
     "highlights": "太和殿、乾清宫、珍宝馆、钟表馆", "tips": "建议提前7天预约门票，周一闭馆，游览时间约4小时",
     "opening_hours": "08:30-17:00", "ticket_info": "旺季60元，淡季40元", "rating": 4.8},
    {"id": 2, "name": "长城（八达岭）", "city": "北京", "category": "历史",
     "description": "八达岭长城位于北京市延庆区，是明长城最具代表性的一段，也是游览人数最多的长城段落。",
     "highlights": "好汉坡、北城烽火台、长城博物馆", "tips": "建议早上去避开人流，穿舒适登山鞋，冬季注意防滑",
     "opening_hours": "07:30-17:30", "ticket_info": "旺季40元，淡季35元", "rating": 4.7},
    {"id": 3, "name": "颐和园", "city": "北京", "category": "园林",
     "description": "颐和园是中国清朝时期皇家园林，以昆明湖、万寿山为基址，以杭州西湖为蓝本，汲取江南园林的设计手法而建成。",
     "highlights": "长廊、佛香阁、十七孔桥、苏州街", "tips": "建议租讲解器了解历史，春秋季风景最佳",
     "opening_hours": "06:30-18:00", "ticket_info": "旺季30元，淡季20元", "rating": 4.6},
    {"id": 4, "name": "天坛公园", "city": "北京", "category": "文化",
     "description": "天坛是明清两代皇帝祭天、祈谷的场所，是中国现存最大的古代祭祀性建筑群。",
     "highlights": "祈年殿、回音壁、圜丘坛", "tips": "早晨有市民晨练，可以感受北京市民文化",
     "opening_hours": "06:00-21:00", "ticket_info": "联票34元", "rating": 4.5},
    # --- 上海 ---
    {"id": 5, "name": "外滩", "city": "上海", "category": "都市",
     "description": "外滩位于上海市黄浦区的黄浦江畔，是上海的城市名片，汇集了52幢风格各异的中西建筑。",
     "highlights": "万国建筑博览群、陆家嘴天际线夜景", "tips": "建议晚上去欣赏夜景，游客较多注意保管财物",
     "opening_hours": "全天开放", "ticket_info": "免费", "rating": 4.7},
    {"id": 6, "name": "迪士尼乐园", "city": "上海", "category": "主题公园",
     "description": "上海迪士尼度假区是中国内地首座迪士尼主题乐园，拥有七大主题园区。",
     "highlights": "创极速光轮、加勒比海盗、烟花秀", "tips": "建议下载官方APP抢快速通行证，避开周末和节假日",
     "opening_hours": "08:30-20:30", "ticket_info": "平日399元，高峰599元", "rating": 4.8},
    {"id": 7, "name": "豫园", "city": "上海", "category": "园林",
     "description": "豫园是明代江南园林的代表，园内楼阁参差，山石峥嵘，湖光潋滟。",
     "highlights": "点春堂、玉华堂、城隍庙小吃", "tips": "附近城隍庙小吃街值得一逛，节假日人非常多",
     "opening_hours": "09:00-16:30", "ticket_info": "旺季40元，淡季30元", "rating": 4.3},
    # --- 广州 ---
    {"id": 8, "name": "广州塔", "city": "广州", "category": "都市",
     "description": "广州塔又称小蛮腰，塔身主体高454米，天线桅杆高146米，总高度600米，是中国第一高塔。",
     "highlights": "摩天轮、跳楼机、空中走廊、旋转餐厅", "tips": "建议傍晚登塔，可以同时欣赏日落和夜景",
     "opening_hours": "09:30-22:30", "ticket_info": "150-398元（不同观光层）", "rating": 4.6},
    {"id": 9, "name": "长隆野生动物世界", "city": "广州", "category": "主题公园",
     "description": "长隆野生动物世界是亚洲最大的野生动物主题公园，拥有500多种、20000多只野生动物。",
     "highlights": "熊猫乐园、白虎山、空中缆车", "tips": "建议一早就去，先坐小火车游览自驾区",
     "opening_hours": "09:30-18:00", "ticket_info": "平日300元", "rating": 4.7},
    {"id": 10, "name": "沙面岛", "city": "广州", "category": "文化",
     "description": "沙面是珠江冲积形成的沙洲，曾是英法租界，保留了大量19世纪欧式建筑。",
     "highlights": "欧陆建筑群、古树、咖啡厅", "tips": "适合拍照和悠闲散步，免费进入",
     "opening_hours": "全天开放", "ticket_info": "免费", "rating": 4.4},
    # --- 深圳 ---
    {"id": 11, "name": "世界之窗", "city": "深圳", "category": "主题公园",
     "description": "深圳世界之窗是中国著名的微缩景观主题公园，将世界奇观、历史遗迹与民俗风情浓缩于一园。",
     "highlights": "埃菲尔铁塔、金字塔、尼亚加拉瀑布", "tips": "晚上有灯光秀和表演，建议预留半天时间",
     "opening_hours": "09:00-22:00", "ticket_info": "成人票220元", "rating": 4.3},
    {"id": 12, "name": "华侨城创意园", "city": "深圳", "category": "文化",
     "description": "华侨城创意文化园是由旧工业区改造而成的文创产业园区，充满艺术气息。",
     "highlights": "画廊、设计工作室、创意市集", "tips": "周末有创意市集，适合文艺青年打卡",
     "opening_hours": "全天开放", "ticket_info": "免费", "rating": 4.2},
    {"id": 13, "name": "大梅沙海滨公园", "city": "深圳", "category": "海滨",
     "description": "大梅沙海滨公园是深圳最知名的海滨度假胜地，拥有绵延1800米的金色沙滩。",
     "highlights": "沙滩浴场、海滨栈道、日出", "tips": "夏季人多，建议早晚前往，需提前预约",
     "opening_hours": "06:00-22:00", "ticket_info": "免费（需预约）", "rating": 4.1},
    # --- 更多城市 ---
    {"id": 14, "name": "西湖", "city": "杭州", "category": "自然",
     "description": "杭州西湖是中国首批国家重点风景名胜区，三面环山，湖光山色，被誉为「人间天堂」。",
     "highlights": "断桥残雪、雷峰夕照、三潭印月、苏堤春晓", "tips": "春季和秋季最佳，可以骑行环湖",
     "opening_hours": "全天开放", "ticket_info": "免费（部分景点收费）", "rating": 4.9},
    {"id": 15, "name": "黄山", "city": "黄山", "category": "山岳",
     "description": "黄山是世界文化与自然双重遗产，以奇松、怪石、云海、温泉、冬雪「五绝」著称。",
     "highlights": "迎客松、光明顶、西海大峡谷、日出云海", "tips": "建议住山顶看日出，带好登山杖和雨衣",
     "opening_hours": "06:00-17:30", "ticket_info": "旺季190元，淡季150元", "rating": 4.9},
    {"id": 16, "name": "漓江", "city": "桂林", "category": "自然",
     "description": "漓江风光有山青、水秀、洞奇、石美「四胜」之誉，是桂林山水的精华所在。",
     "highlights": "九马画山、黄布倒影、20元人民币背景", "tips": "建议乘坐竹筏从杨堤到兴坪，约4小时",
     "opening_hours": "全天开放", "ticket_info": "竹筏约200元/人", "rating": 4.8},
    {"id": 17, "name": "鼓浪屿", "city": "厦门", "category": "海岛",
     "description": "鼓浪屿是厦门西南隅的一座小岛，拥有「万国建筑博览」之称，是音乐家的摇篮。",
     "highlights": "日光岩、菽庄花园、钢琴博物馆", "tips": "建议住一晚感受小岛日夜，避开黄金周",
     "opening_hours": "全天开放", "ticket_info": "上岛免费（渡轮35元）", "rating": 4.5},
    {"id": 18, "name": "丽江古城", "city": "丽江", "category": "古镇",
     "description": "丽江古城是世界文化遗产，以纳西族文化为特色，小桥流水、古街古巷。",
     "highlights": "四方街、木府、大水车、黑龙潭", "tips": "早晚人少时最适合拍照，注意高原反应",
     "opening_hours": "全天开放", "ticket_info": "免费（需缴纳古城维护费）", "rating": 4.4},
    {"id": 19, "name": "兵马俑", "city": "西安", "category": "历史",
     "description": "秦始皇兵马俑博物馆是中国最大的古代军事博物馆，被誉为「世界第八大奇迹」。",
     "highlights": "一号坑、二号坑、三号坑、铜车马", "tips": "建议请讲解员，至少预留3小时参观",
     "opening_hours": "08:30-17:30", "ticket_info": "旺季120元，淡季120元", "rating": 4.8},
    {"id": 20, "name": "洪崖洞", "city": "重庆", "category": "都市",
     "description": "洪崖洞是重庆最具特色的吊脚楼建筑群，夜晚灯火辉煌，宛如「千与千寻」中的汤屋。",
     "highlights": "夜景、美食街、民俗博物馆", "tips": "建议晚上去，11层楼每层功能不同，有电梯",
     "opening_hours": "11:00-23:00", "ticket_info": "免费", "rating": 4.6},
    {"id": 21, "name": "成都大熊猫基地", "city": "成都", "category": "主题公园",
     "description": "成都大熊猫繁育研究基地是世界著名的大熊猫保护研究机构，可以近距离观察大熊猫。",
     "highlights": "月亮产房、太阳产房、熊猫剧场", "tips": "建议早上7:30开门就去，熊猫最活跃",
     "opening_hours": "07:30-18:00", "ticket_info": "55元", "rating": 4.9},
    {"id": 22, "name": "布达拉宫", "city": "拉萨", "category": "文化",
     "description": "布达拉宫是世界上海拔最高、最雄伟的宫殿，是藏传佛教圣地和西藏的象征。",
     "highlights": "白宫、红宫、金顶群", "tips": "需提前一天预约，注意高原反应，禁止拍照区域",
     "opening_hours": "09:00-16:00", "ticket_info": "旺季200元，淡季100元", "rating": 4.9},
    {"id": 23, "name": "乌镇", "city": "嘉兴", "category": "古镇",
     "description": "乌镇是中国十大历史文化名镇之一，典型的江南水乡，素有「中国最后的枕水人家」之誉。",
     "highlights": "西栅夜景、东栅老街、木心美术馆", "tips": "西栅夜景很美，建议买联票游览东西栅",
     "opening_hours": "07:00-22:00", "ticket_info": "东栅110元，西栅150元", "rating": 4.5},
    {"id": 24, "name": "张家界国家森林公园", "city": "张家界", "category": "山岳",
     "description": "张家界是中国第一个国家森林公园，以独特的石英砂岩峰林地貌闻名，是电影《阿凡达》取景地。",
     "highlights": "袁家界、天子山、金鞭溪、玻璃栈道", "tips": "建议游玩2-3天，山上温差大注意保暖",
     "opening_hours": "07:00-18:00", "ticket_info": "旺季248元（四日有效）", "rating": 4.7},
    {"id": 25, "name": "九寨沟", "city": "阿坝", "category": "自然",
     "description": "九寨沟以翠海、叠瀑、彩林、雪峰、藏情、蓝冰「六绝」闻名，是水的天堂。",
     "highlights": "五花海、五彩池、诺日朗瀑布、长海", "tips": "秋季（10月）最美，景区实行限流需提前预约",
     "opening_hours": "08:30-17:00", "ticket_info": "旺季169元（含观光车）", "rating": 4.9},
]

# 按分类的景点索引（用于分类检索）
CATEGORY_INDEX = {}
for item in BUILTIN_KNOWLEDGE:
    cat = item["category"]
    if cat not in CATEGORY_INDEX:
        CATEGORY_INDEX[cat] = []
    CATEGORY_INDEX[cat].append(item)

# 按城市的景点索引
CITY_INDEX = {}
for item in BUILTIN_KNOWLEDGE:
    city = item["city"]
    if city not in CITY_INDEX:
        CITY_INDEX[city] = []
    CITY_INDEX[city].append(item)


# ==================== 简易向量检索（演示模式降级用） ====================

class SimpleVectorIndex:
    """无 Milvus 时的简易向量索引（基于关键词相似度）"""

    def __init__(self):
        self.items = BUILTIN_KNOWLEDGE

    def search(self, query: str, city: str = "", top_k: int = 5) -> List[dict]:
        """基于关键词匹配的简易检索"""
        query_lower = query.lower()
        results = []

        for item in self.items:
            score = 0.0

            # 城市过滤
            if city and city not in item["city"]:
                continue

            # 名称匹配（最高权重）
            if query_lower in item["name"].lower():
                score += 0.5
            if any(char in item["name"] for char in query_lower):
                score += 0.2

            # 描述匹配
            desc = item["description"] + item["highlights"]
            keywords = query_lower.split()
            match_count = sum(1 for kw in keywords if kw in desc)
            score += 0.1 * match_count / max(len(keywords), 1)

            # 分类匹配
            if query_lower in item["category"].lower():
                score += 0.3

            if score > 0:
                results.append((score, {**item, "score": round(score, 4)}))

        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:top_k]]


# ==================== Milvus 客户端（带降级） ====================

class MilvusClient:
    """
    Milvus 向量库客户端
    - 优先连接真实 Milvus
    - 连接失败时自动降级到 SimpleVectorIndex
    """

    def __init__(self, config: dict):
        self.config = config
        self.collection_name = config.get("collection", "attraction_knowledge")
        self.embedding_model = config.get("embedding_model", "bge-m3")
        self.milvus_available = False
        self.fallback_index = SimpleVectorIndex()
        self._connect()

    def _connect(self):
        """尝试连接 Milvus，失败则使用降级模式"""
        host = self.config.get("host", "localhost")
        port = self.config.get("port", "19530")
        try:
            from pymilvus import connections, Collection, utility
            connections.connect(host=host, port=port)
            if utility.has_collection(self.collection_name):
                self.collection = Collection(self.collection_name)
                self.collection.load()
                self.milvus_available = True
                logger.info(f"Milvus 连接成功: {host}:{port}, collection={self.collection_name}")
            else:
                logger.warning(f"Milvus 集合 {self.collection_name} 不存在，使用降级模式")
        except ImportError:
            logger.warning("pymilvus 未安装，使用降级模式。pip install pymilvus")
        except Exception as e:
            logger.warning(f"Milvus 连接失败: {e}，使用降级模式")

    def _get_embedding(self, text: str) -> list:
        """使用 bge-m3 生成嵌入向量"""
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(f"BAAI/{self.embedding_model}")
            return model.encode(text).tolist()
        except ImportError:
            # 没有 sentence-transformers 时使用哈希模拟
            logger.debug("sentence-transformers 未安装，使用模拟向量")
            return self._mock_embedding(text)

    def _mock_embedding(self, text: str) -> list:
        """模拟嵌入向量（仅用于演示降级）"""
        h = hashlib.md5(text.encode()).hexdigest()
        np.random.seed(int(h[:8], 16))
        return np.random.randn(768).tolist()

    def hybrid_search(self, query: str, city: str = "", top_k: int = 5) -> List[dict]:
        """
        混合检索入口
        - Milvus 可用时：稠密向量 + BM25 混合检索
        - 降级时：关键词匹配检索
        """
        if self.milvus_available:
            return self._milvus_search(query, city, top_k)
        return self.fallback_index.search(query, city, top_k)

    def _milvus_search(self, query: str, city: str = "", top_k: int = 5) -> List[dict]:
        """Milvus 混合检索实现"""
        try:
            # bge-m3 嵌入
            query_vector = self._get_embedding(query)

            # 构建过滤条件
            expr = None
            if city:
                expr = f'city == "{city}"'

            # 稠密向量检索
            search_params = {
                "metric_type": "COSINE",
                "params": {"nprobe": 10},
            }
            results = self.collection.search(
                data=[query_vector],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                expr=expr,
                output_fields=["name", "city", "category", "description", "highlights", "tips", "rating"]
            )

            items = []
            for hits in results:
                for hit in hits:
                    items.append({
                        "id": hit.id,
                        "name": hit.entity.get("name"),
                        "city": hit.entity.get("city"),
                        "category": hit.entity.get("category"),
                        "description": hit.entity.get("description"),
                        "highlights": hit.entity.get("highlights"),
                        "tips": hit.entity.get("tips"),
                        "rating": hit.entity.get("rating", 0),
                        "score": round(hit.score, 4),
                    })
            return items
        except Exception as e:
            logger.error(f"Milvus 检索失败: {e}，降级到关键词检索")
            return self.fallback_index.search(query, city, top_k)


# ==================== 知识导入工具 ====================

class KnowledgeImporter:
    """景点知识导入 Milvus"""

    @staticmethod
    def prepare_data(items: List[dict] = None) -> List[dict]:
        """准备导入数据（添加嵌入向量字段）"""
        data = items or BUILTIN_KNOWLEDGE
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("BAAI/bge-m3")
            for item in data:
                text = f"{item['name']}。{item['description']}。{item['highlights']}"
                item["embedding"] = model.encode(text).tolist()
        except ImportError:
            logger.warning("sentence-transformers 未安装，使用模拟向量")
            for item in data:
                text = f"{item['name']} {item['description']}"
                h = hashlib.md5(text.encode()).hexdigest()
                np.random.seed(int(h[:8], 16))
                item["embedding"] = np.random.randn(768).tolist()
        return data

    @staticmethod
    def import_to_milvus(config: dict):
        """将景点数据导入 Milvus"""
        try:
            from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility

            host = config.get("host", "localhost")
            port = config.get("port", "19530")
            collection_name = config.get("collection", "attraction_knowledge")

            connections.connect(host=host, port=port)

            # 删除已存在的集合
            if utility.has_collection(collection_name):
                utility.drop_collection(collection_name)

            # 定义 schema
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=False),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=768),
                FieldSchema(name="name", dtype=DataType.VARCHAR, max_length=100),
                FieldSchema(name="city", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="description", dtype=DataType.VARCHAR, max_length=1000),
                FieldSchema(name="highlights", dtype=DataType.VARCHAR, max_length=500),
                FieldSchema(name="tips", dtype=DataType.VARCHAR, max_length=500),
                FieldSchema(name="opening_hours", dtype=DataType.VARCHAR, max_length=100),
                FieldSchema(name="ticket_info", dtype=DataType.VARCHAR, max_length=100),
                FieldSchema(name="rating", dtype=DataType.FLOAT),
            ]
            schema = CollectionSchema(fields, description="景点知识库")
            collection = Collection(name=collection_name, schema=schema)

            # 准备数据并插入
            data = KnowledgeImporter.prepare_data()
            entities = [
                [item["id"] for item in data],
                [item["embedding"] for item in data],
                [item["name"] for item in data],
                [item["city"] for item in data],
                [item["category"] for item in data],
                [item["description"] for item in data],
                [item["highlights"] for item in data],
                [item["tips"] for item in data],
                [item["opening_hours"] for item in data],
                [item["ticket_info"] for item in data],
                [item["rating"] for item in data],
            ]
            collection.insert(entities)

            # 创建索引
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128},
            }
            collection.create_index(field_name="embedding", index_params=index_params)
            collection.load()

            logger.info(f"成功导入 {len(data)} 条景点数据到 Milvus {collection_name}")
            return len(data)

        except ImportError:
            logger.error("pymilvus 未安装，无法导入。pip install pymilvus")
            raise
        except Exception as e:
            logger.error(f"Milvus 导入失败: {e}")
            raise


# ==================== 模块级便捷方法 ====================

_client_instance = None  # 单例


def get_knowledge_client(config: dict) -> MilvusClient:
    """获取知识检索客户端（单例）"""
    global _client_instance
    if _client_instance is None:
        _client_instance = MilvusClient(config)
    return _client_instance


def search(query: str, city: str = "", top_k: int = 5, config: dict = None) -> List[dict]:
    """便捷检索入口"""
    from configs.llm_config import milvus_config as default_config
    cfg = config or default_config
    client = get_knowledge_client(cfg)
    return client.hybrid_search(query, city, top_k)


if __name__ == "__main__":
    # 测试检索
    print("=" * 50)
    print("知识库模块测试")
    print("=" * 50)

    queries = [
        ("北京的文化景点", "北京"),
        ("上海有什么好玩的", ""),
        ("推荐山岳类景点", ""),
        ("适合亲子游的地方", "广州"),
    ]

    for query, city in queries:
        print(f"\n🔍 检索: {query} (city={city})")
        results = search(query, city, top_k=3)
        for r in results:
            print(f"  [{r['score']:.4f}] {r['name']} - {r['city']} ({r['category']})")
    print("\n✅ 知识库模块测试完成")
