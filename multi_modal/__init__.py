"""
多模态模块
==========
功能：
1. PaddleOCR 封装 - 图片文字提取（路牌/石碑识别）
2. GLM-4V-9B 多模态客户端 - 地标识别
3. 图片预处理工具 - URL下载、base64解码、格式转换

设计原则：
- 所有组件均有"可用"和"降级"两种状态
- 依赖未安装时自动降级，不抛 ImportError
- OCR 置信度 >= 98% 才算有效，VLM 地标识别 >= 85%
"""
import os
import base64
import json
import tempfile
import logging
from io import BytesIO
from typing import Optional, Tuple, Dict, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ==================== 内置地标知识（VLM 不可用时的兜底） ====================

# 常见地标关键词库（用于纯文本匹配兜底）
LANDMARK_KEYWORDS = {
    "天安门": {"name": "天安门广场", "city": "北京", "type": "文化"},
    "故宫": {"name": "故宫博物院", "city": "北京", "type": "文化"},
    "长城": {"name": "长城（八达岭）", "city": "北京", "type": "历史"},
    "鸟巢": {"name": "国家体育场（鸟巢）", "city": "北京", "type": "都市"},
    "水立方": {"name": "国家游泳中心（水立方）", "city": "北京", "type": "都市"},
    "东方明珠": {"name": "东方明珠广播电视塔", "city": "上海", "type": "都市"},
    "外滩": {"name": "外滩", "city": "上海", "type": "都市"},
    "迪士尼": {"name": "上海迪士尼乐园", "city": "上海", "type": "主题公园"},
    "广州塔": {"name": "广州塔（小蛮腰）", "city": "广州", "type": "都市"},
    "小蛮腰": {"name": "广州塔（小蛮腰）", "city": "广州", "type": "都市"},
    "世界之窗": {"name": "世界之窗", "city": "深圳", "type": "主题公园"},
    "西湖": {"name": "西湖", "city": "杭州", "type": "自然"},
    "黄山": {"name": "黄山", "city": "黄山", "type": "山岳"},
    "兵马俑": {"name": "秦始皇兵马俑", "city": "西安", "type": "历史"},
    "洪崖洞": {"name": "洪崖洞", "city": "重庆", "type": "都市"},
    "布达拉宫": {"name": "布达拉宫", "city": "拉萨", "type": "文化"},
    "鼓浪屿": {"name": "鼓浪屿", "city": "厦门", "type": "海岛"},
    "九寨沟": {"name": "九寨沟", "city": "阿坝", "type": "自然"},
    "张家界": {"name": "张家界国家森林公园", "city": "张家界", "type": "山岳"},
    "大熊猫": {"name": "成都大熊猫基地", "city": "成都", "type": "主题公园"},
    "丽江": {"name": "丽江古城", "city": "丽江", "type": "古镇"},
    "乌镇": {"name": "乌镇", "city": "嘉兴", "type": "古镇"},
}


# ==================== 图片预处理 ====================

class ImageProcessor:
    """图片预处理工具"""

    @staticmethod
    def load_image(source: str) -> Tuple[Optional[bytes], Optional[str]]:
        """
        从 URL 或 base64 加载图片
        返回: (image_bytes, format) 或 (None, error_msg)
        """
        try:
            if source.startswith(('http://', 'https://')):
                return ImageProcessor._from_url(source)
            elif source.startswith('data:image'):
                return ImageProcessor._from_base64(source)
            elif source.startswith('/') or source.startswith(('C:', 'D:', '\\')):
                return ImageProcessor._from_file(source)
            else:
                # 尝试当作 base64 处理
                return ImageProcessor._from_base64(source)
        except Exception as e:
            return None, f"图片加载失败: {e}"

    @staticmethod
    def _from_url(url: str) -> Tuple[Optional[bytes], Optional[str]]:
        """从 URL 下载图片"""
        import requests
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        content_type = resp.headers.get('content-type', '')
        fmt = 'png' if 'png' in content_type else 'jpeg'
        return resp.content, fmt

    @staticmethod
    def _from_base64(data: str) -> Tuple[Optional[bytes], Optional[str]]:
        """从 base64 解码图片"""
        if ',' in data:
            header, data = data.split(',', 1)
            fmt = 'png' if 'png' in header else 'jpeg'
        else:
            fmt = 'jpeg'
        image_bytes = base64.b64decode(data)
        return image_bytes, fmt

    @staticmethod
    def _from_file(path: str) -> Tuple[Optional[bytes], Optional[str]]:
        """从本地文件读取图片"""
        with open(path, 'rb') as f:
            return f.read(), os.path.splitext(path)[1].lstrip('.')

    @staticmethod
    def to_base64(image_bytes: bytes, fmt: str = 'jpeg') -> str:
        """将图片字节转为 base64 字符串"""
        return base64.b64encode(image_bytes).decode('utf-8')

    @staticmethod
    def to_data_url(image_bytes: bytes, fmt: str = 'jpeg') -> str:
        """将图片字节转为 data URL"""
        b64 = ImageProcessor.to_base64(image_bytes, fmt)
        mime = f"image/{'png' if fmt == 'png' else 'jpeg'}"
        return f"data:{mime};base64,{b64}"


# ==================== PaddleOCR 封装 ====================

class OCREngine:
    """
    PaddleOCR 引擎封装
    - 优先使用 PaddleOCR（准确率 >= 98%）
    - 不可用时返回空结果（走 VLM 或兜底）
    - 支持中英文文字识别
    """

    def __init__(self):
        self.available = False
        self.ocr = None
        self._init_engine()

    def _init_engine(self):
        """初始化 PaddleOCR"""
        try:
            from paddleocr import PaddleOCR
            self.ocr = PaddleOCR(
                use_angle_cls=True,
                lang='ch',
                show_log=False,
                use_gpu=False,
            )
            self.available = True
            logger.info("PaddleOCR 初始化成功")
        except ImportError:
            logger.warning("paddleocr 未安装，OCR 不可用。pip install paddleocr")
        except Exception as e:
            logger.warning(f"PaddleOCR 初始化失败: {e}")

    def recognize(self, image_bytes: bytes) -> Dict:
        """
        识别图片中的文字
        返回: {"text": "识别的文字", "confidence": 0.98, "boxes": [...]}
        """
        if not self.available or not self.ocr:
            return {"text": "", "confidence": 0, "boxes": [], "method": "ocr_unavailable"}

        try:
            # 保存为临时文件（PaddleOCR 需要文件路径）
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp.write(image_bytes)
                tmp_path = tmp.name

            result = self.ocr.ocr(tmp_path, cls=True)
            os.unlink(tmp_path)

            if not result or not result[0]:
                return {"text": "", "confidence": 0, "boxes": [], "method": "ocr_no_result"}

            texts = []
            confidences = []
            boxes = []
            for line in result[0]:
                box, (text, conf) = line
                texts.append(text)
                confidences.append(conf)
                boxes.append(box)

            all_text = "".join(texts)
            avg_conf = sum(confidences) / len(confidences) if confidences else 0

            return {
                "text": all_text,
                "confidence": round(avg_conf, 4),
                "boxes": boxes,
                "method": "ocr"
            }
        except Exception as e:
            logger.error(f"OCR 识别失败: {e}")
            return {"text": "", "confidence": 0, "boxes": [], "method": "ocr_error"}


# ==================== GLM-4V-9B 多模态客户端 ====================

class VLMEngine:
    """
    GLM-4V-9B 多模态视觉语言模型客户端
    - 地标识别（覆盖 3000+ 5A/4A 景区及国际知名地标）
    - 使用智谱 GLM-4V-9B 模型
    """

    def __init__(self):
        self.available = False
        self.client = None
        self.model = os.getenv("GLM_4V_MODEL", "glm-4v-9b")
        self.api_key = os.getenv("GLM_API_KEY", "")
        self.base_url = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
        self._init_client()

    def _init_client(self):
        """初始化 GLM-4V 客户端"""
        if not self.api_key:
            logger.warning("GLM_API_KEY 未设置，VLM 不可用")
            return
        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
            self.available = True
            logger.info(f"GLM-4V-9B 客户端初始化成功 (model={self.model})")
        except ImportError:
            logger.warning("openai 库未安装，VLM 不可用。pip install openai")
        except Exception as e:
            logger.warning(f"GLM-4V-9B 初始化失败: {e}")

    def recognize_landmark(self, image_data_url: str) -> Dict:
        """
        识别图片中的地标景点
        返回: {"name": "景点名", "confidence": 0.92, "city": "北京", "type": "文化"}
        """
        if not self.available or not self.client:
            return {"name": "", "confidence": 0, "city": "", "type": "", "method": "vlm_unavailable"}

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_url}
                        },
                        {
                            "type": "text",
                            "text": (
                                "请识别这张图片中的景点/地标名称。如果确定是某个知名景点，"
                                "请按以下JSON格式回答："
                                '{"name": "景点名称", "city": "所在城市", "type": "景点类型（山岳/海滨/古镇/文化/都市/自然/主题公园/历史/海岛）", '
                                '"confidence": 0-1之间的置信度}'
                                "如果不确定，请回答：{\"name\": \"\"}"
                            )
                        }
                    ]
                }],
                temperature=0,
                max_tokens=256,
            )

            content = response.choices[0].message.content.strip()
            # 尝试解析 JSON
            if '{' in content:
                json_str = content[content.index('{'):content.rindex('}') + 1]
                result = json.loads(json_str)
                if result.get("name"):
                    result["method"] = "vlm"
                    return result

            return {"name": "", "confidence": 0, "city": "", "type": "", "method": "vlm_no_match"}

        except Exception as e:
            logger.error(f"VLM 识别失败: {e}")
            return {"name": "", "confidence": 0, "city": "", "type": "", "method": "vlm_error"}


# ==================== 关键词兜底匹配 ====================

def keyword_fallback_match(text: str) -> Optional[Dict]:
    """
    关键词兜底匹配
    当 OCR 和 VLM 都失败时，从提取的文字或用户描述中匹配已知地标
    """
    if not text:
        return None

    best_match = None
    best_len = 0

    for keyword, info in LANDMARK_KEYWORDS.items():
        if keyword in text and len(keyword) > best_len:
            best_match = {**info, "confidence": 0.7, "method": "keyword_fallback"}
            best_len = len(keyword)

    if best_match:
        logger.info(f"关键词兜底匹配成功: {text} -> {best_match['name']}")

    return best_match


# ==================== 模块级便捷方法 ====================

_ocr_instance = None
_vlm_instance = None


def get_ocr() -> OCREngine:
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = OCREngine()
    return _ocr_instance


def get_vlm() -> VLMEngine:
    global _vlm_instance
    if _vlm_instance is None:
        _vlm_instance = VLMEngine()
    return _vlm_instance


def recognize_scene(image_source: str, user_description: str = "") -> Dict:
    """
    一站式景点识别
    策略：OCR优先 → VLM地标识别 → 关键词兜底 → 返回结果

    返回: {
        "success": True/False,
        "name": "景点名称",
        "confidence": 0.95,
        "method": "ocr/vlm/keyword_fallback/none",
        "city": "所在城市",
        "type": "景点类型",
        "raw_ocr": "OCR提取的文字",
        "message": "描述信息"
    }
    """
    result = {
        "success": False,
        "name": "",
        "confidence": 0,
        "method": "none",
        "city": "",
        "type": "",
        "raw_ocr": "",
        "message": "",
    }

    # 1. 加载图片
    image_bytes, fmt = ImageProcessor.load_image(image_source)
    if image_bytes is None:
        result["message"] = fmt  # fmt 此时是错误信息
        return result

    # 2. OCR 识别（优先）
    ocr = get_ocr()
    ocr_result = ocr.recognize(image_bytes)
    result["raw_ocr"] = ocr_result["text"]

    if ocr_result["confidence"] >= 0.98 and ocr_result["text"].strip():
        # OCR 高置信度 → 检查是否匹配地标关键词
        landmark = keyword_fallback_match(ocr_result["text"])
        if landmark:
            result["success"] = True
            result["name"] = landmark["name"]
            result["city"] = landmark.get("city", "")
            result["type"] = landmark.get("type", "")
            result["confidence"] = 0.98
            result["method"] = "ocr"
            result["message"] = f"通过 OCR 识别路牌文字成功"
            return result

    # 3. VLM 地标识别
    vlm = get_vlm()
    if vlm.available:
        data_url = ImageProcessor.to_data_url(image_bytes, fmt)
        vlm_result = vlm.recognize_landmark(data_url)
        if vlm_result.get("confidence", 0) >= 0.85 and vlm_result.get("name"):
            result["success"] = True
            result["name"] = vlm_result["name"]
            result["city"] = vlm_result.get("city", "")
            result["type"] = vlm_result.get("type", "")
            result["confidence"] = vlm_result["confidence"]
            result["method"] = "vlm"
            result["message"] = f"通过 GLM-4V-9B 地标识别成功"
            return result

    # 4. 关键词兜底（使用 OCR 文字 + 用户描述）
    match_text = (ocr_result["text"] + " " + user_description).strip()
    landmark = keyword_fallback_match(match_text)
    if landmark:
        result["success"] = True
        result["name"] = landmark["name"]
        result["city"] = landmark.get("city", "")
        result["type"] = landmark.get("type", "")
        result["confidence"] = 0.7
        result["method"] = "keyword_fallback"
        result["message"] = f"通过关键词匹配识别"
        return result

    # 5. 全失败
    result["message"] = "无法识别图片中的景点"
    return result


if __name__ == "__main__":
    print("=" * 50)
    print("多模态模块测试")
    print("=" * 50)

    # 测试 OCR 初始化
    ocr = get_ocr()
    print(f"\nOCR 可用: {ocr.available}")

    # 测试 VLM 初始化
    vlm = get_vlm()
    print(f"VLM 可用: {vlm.available}")

    # 测试关键词匹配
    print("\n关键词兜底匹配测试:")
    for text in ["故宫", "广州塔小蛮腰夜景", "上海外滩风景"]:
        match = keyword_fallback_match(text)
        if match:
            print(f"  {text} -> {match['name']} ({match['city']})")
        else:
            print(f"  {text} -> 无匹配")

    # 测试图片加载
    print("\n图片加载测试:")
    url = "https://example.com/test.jpg"
    img_bytes, err = ImageProcessor.load_image(url)
    print(f"  URL加载: {'失败' if err else '成功'} ({err})")

    print("\n✅ 多模态模块测试完成")
