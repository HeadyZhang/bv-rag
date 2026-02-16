"""Query intent classification with ship info extraction."""
import logging
import re

logger = logging.getLogger(__name__)

INTENT_TYPES = {
    "applicability": {
        "triggers_zh": [
            "是否需要", "需不需要", "是否适用", "适用于", "要不要",
            "必须", "强制", "需要配备", "是否要求",
        ],
        "triggers_en": [
            "do I need", "is it required", "does it apply",
            "must I", "is it mandatory", "applicable to",
        ],
        "retrieval_strategy": "broad",
        "model": "primary",
        "top_k": 12,
    },
    "specification": {
        "triggers_zh": [
            "最小", "最大", "多少", "尺寸", "数量", "间距",
            "高度", "宽度", "面积", "速度", "时间",
        ],
        "triggers_en": [
            "minimum", "maximum", "how many", "dimension",
            "size", "spacing", "height", "width",
        ],
        "retrieval_strategy": "precise",
        "model": "fast",
        "top_k": 5,
    },
    "procedure": {
        "triggers_zh": ["怎么", "如何", "步骤", "流程", "程序", "操作"],
        "triggers_en": ["how to", "procedure", "steps", "process"],
        "retrieval_strategy": "normal",
        "model": "primary",
        "top_k": 8,
    },
    "comparison": {
        "triggers_zh": ["区别", "不同", "比较", "对比"],
        "triggers_en": ["difference", "compare", "versus", "vs"],
        "retrieval_strategy": "broad",
        "model": "primary",
        "top_k": 10,
    },
    "definition": {
        "triggers_zh": ["什么是", "定义", "解释", "含义", "是什么意思"],
        "triggers_en": ["what is", "define", "meaning of", "explanation"],
        "retrieval_strategy": "precise",
        "model": "fast",
        "top_k": 5,
    },
}

_TYPE_MAP = {
    "货船": "cargo ship", "客船": "passenger ship",
    "油轮": "oil tanker", "散货船": "bulk carrier",
    "集装箱船": "container ship", "化学品船": "chemical tanker",
    "气体船": "gas carrier", "滚装船": "ro-ro ship",
    "cargo": "cargo ship", "passenger": "passenger ship",
    "tanker": "oil tanker", "bulk": "bulk carrier",
}

_LENGTH_RE = re.compile(r"(\d+)\s*(米|m|metres)", re.IGNORECASE)
_TONNAGE_RE = re.compile(r"(\d+)\s*(吨|GT|总吨|gross tonnage)", re.IGNORECASE)


class QueryClassifier:
    """Classify user query intent and extract ship parameters."""

    def classify(self, query: str) -> dict:
        query_lower = query.lower()

        # Score each intent
        intent = "general"
        max_score = 0
        for intent_name, config in INTENT_TYPES.items():
            score = sum(
                1
                for t in config.get("triggers_zh", []) + config.get("triggers_en", [])
                if t in query_lower
            )
            if score > max_score:
                max_score = score
                intent = intent_name

        # Extract ship info
        ship_info = self._extract_ship_info(query)

        # Force applicability when ship dimensions + requirement question
        # (ship type alone is not enough — avoids capturing comparison queries)
        has_dimensions = ship_info.get("length") or ship_info.get("tonnage")
        if has_dimensions and any(kw in query_lower for kw in [
            "是否", "需不需要", "需要", "要不要", "必须", "need", "require", "must",
        ]):
            intent = "applicability"

        config = INTENT_TYPES.get(intent, {})
        result = {
            "intent": intent,
            "ship_info": ship_info,
            "retrieval_strategy": config.get("retrieval_strategy", "normal"),
            "model": config.get("model", "auto"),
            "top_k": config.get("top_k", 8),
        }
        logger.info(f"[QueryClassifier] intent={intent}, ship_info={ship_info}")
        return result

    @staticmethod
    def _extract_ship_info(query: str) -> dict:
        info: dict = {"type": None, "length": None, "tonnage": None}

        for zh, en in _TYPE_MAP.items():
            if zh in query.lower():
                info["type"] = en
                break

        # "国际航行" without explicit type → assume cargo ship
        if not info["type"] and "国际航行" in query:
            info["type"] = "cargo ship"

        m = _LENGTH_RE.search(query)
        if m:
            info["length"] = int(m.group(1))

        m = _TONNAGE_RE.search(query)
        if m:
            info["tonnage"] = int(m.group(1))

        return info
