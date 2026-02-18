"""Check if a query needs clarification before retrieval.

Maritime regulatory answers depend on multiple conditional dimensions:
ship type, tonnage, construction date, voyage type, etc.
This module detects when critical dimensions are missing and generates
targeted clarification questions.

Strategy: "tiered answer" (分档回答) over clarification.
Most queries should be answered directly with scenario tiers rather than
asking for more information. Clarification is a last resort.
"""
import re

# Required dimensional slots per intent type
REQUIRED_SLOTS: dict[str, dict[str, list[str]]] = {
    "applicability": {
        "critical": ["ship_type"],
        "important": ["tonnage_or_length"],
        "optional": ["construction_date", "voyage_type"],
    },
    "specification": {
        "critical": [],
        "important": ["ship_type", "tonnage_or_length"],
        "optional": [],
    },
    "procedure": {
        "critical": [],
        "important": [],
        "optional": ["ship_type"],
    },
    "comparison": {
        "critical": [],
        "important": ["ship_type"],
        "optional": [],
    },
    "definition": {
        "critical": [],
        "important": [],
        "optional": [],
    },
}

# Topic-specific additional slots
TOPIC_EXTRA_SLOTS: dict[str, dict[str, list[str]]] = {
    "fire_division": {
        "critical": ["ship_type"],
        "important": ["construction_date"],
    },
    "oil_discharge": {
        "critical": ["discharge_source"],
        "important": ["delivery_date"],
    },
    "equipment_requirement": {
        "critical": ["ship_type", "tonnage_or_length"],
        "important": ["voyage_type"],
    },
    "air_pipe": {
        "critical": [],
        "important": [],
        "override_base": True,  # ILLC air pipe rules apply to all ship types
    },
}

# Topic detection patterns
TOPIC_TRIGGERS: dict[str, list[str]] = {
    "fire_division": [
        "防火分隔", "防火等级", "A级", "B级", "A-0", "A-15", "A-30", "A-60",
        "B-0", "B-15", "fire division", "fire integrity", "fire rating",
    ],
    "oil_discharge": [
        "排油", "ODME", "排放.*油", "discharge.*oil", "cargo tank.*discharge",
    ],
    "equipment_requirement": [
        "是否需要配备", "需要多少", "配置要求",
    ],
    "air_pipe": [
        "透气管", "air pipe", "vent pipe", "tank vent",
    ],
}

# Clarification question templates
CLARIFICATION_TEMPLATES: dict[str, dict] = {
    "ship_type": {
        "question": "请问您说的是哪类船舶？不同船型的法规要求可能完全不同。",
        "options": ["货船(非tanker)", "客船(>36人)", "客船(<=36人)", "油轮(tanker)", "散货船", "其他"],
    },
    "tonnage_or_length": {
        "question": "请问船舶的总吨位(GT)或船长(m)大约是多少？很多法规有吨位/船长阈值。",
        "options": None,
    },
    "construction_date": {
        "question": "请问船舶大约是什么时候建造的（合同日期或安放龙骨日期）？不同年代适用不同版本的法规。",
        "options": ["2010年之后", "2002-2010年", "1994-2002年", "1994年之前"],
    },
    "voyage_type": {
        "question": "是国际航行还是国内航行？",
        "options": ["国际航行", "国内航行"],
    },
    "discharge_source": {
        "question": "请问您问的是货舱区排油还是机舱舱底水排放？两者的标准完全不同。",
        "options": ["货舱区排油(MARPOL Reg.34)", "机舱舱底水(MARPOL Reg.15)"],
    },
    "delivery_date": {
        "question": "船舶是1979年12月31日之前交付还是之后？这决定排油限制是1/15,000还是1/30,000。",
        "options": ["1979年12月31日之前", "1979年12月31日之后"],
    },
}

# Patterns that indicate a slot is already filled
_SHIP_TYPE_PATTERNS = [
    "货船", "客船", "油轮", "散货船", "集装箱船", "滚装船", "化学品船", "气体船",
    "cargo ship", "passenger ship", "tanker", "bulk carrier", "container",
    "FPSO", "FSO", "MODU",
]

# When a specific regulation section is referenced, ship type context is implicit
_SPECIFIC_REG_RE = re.compile(
    r"SOLAS\s+[IVX]{1,4}-?\d+[/.\-]\d*"
    r"|MARPOL\s+Annex\s+[IVX]+"
    r"|IACS\s+UR\s+[A-Z]"
    r"|LSA\s+Code|FSS\s+Code"
    r"|COLREG|STCW|ISM\s+Code|ISPS",
    re.IGNORECASE,
)
_DIMENSION_PATTERNS = re.compile(r"\d+\s*(米|m|吨|GT|DWT|总吨|载重吨)", re.IGNORECASE)
_DATE_PATTERNS = re.compile(r"(19|20)\d{2}\s*年|built\s*(in|before|after)\s*\d{4}", re.IGNORECASE)
_VOYAGE_PATTERNS = ["国际航行", "国内航行", "international", "domestic"]

# Space category keywords for detecting universal fire division pairs
_SPACE_CATEGORY_MAP = {
    "control_station": [
        "驾驶室", "控制站", "控制室", "消防控制",
        "wheelhouse", "bridge", "control station", "radio room",
    ],
    "accommodation": [
        "住舱", "起居", "船员舱", "船员住舱",
        "accommodation", "cabin", "crew quarters", "living quarters",
    ],
    "machinery_cat_a": [
        "机舱", "机器处所", "主机", "锅炉",
        "engine room", "machinery space", "boiler room",
    ],
    "galley_high_risk": [
        "厨房", "烹饪", "galley", "kitchen", "cooking",
    ],
    "corridor": [
        "走廊", "通道", "corridor", "passageway",
    ],
}

# Fire division pairs where the answer is the SAME regardless of ship type
_UNIVERSAL_FIRE_PAIRS: dict[tuple[str, str], str] = {
    ("control_station", "accommodation"): "A-60",
    ("control_station", "machinery_cat_a"): "A-60",
    ("machinery_cat_a", "accommodation"): "A-60",
}


def _detect_space_categories(query: str) -> list[str]:
    """Detect which space categories are mentioned in the query."""
    query_lower = query.lower()
    found = []
    for category, keywords in _SPACE_CATEGORY_MAP.items():
        if any(kw in query_lower for kw in keywords):
            found.append(category)
    return found


def _is_universal_fire_answer(query: str) -> bool:
    """Check if the fire division question involves a universal pair.

    Some space-category pairs always have the same fire rating regardless
    of ship type (e.g. control station vs accommodation = A-60 on ALL ships).
    """
    categories = _detect_space_categories(query)
    if len(categories) < 2:
        return False
    # Check all pairs
    for i in range(len(categories)):
        for j in range(i + 1, len(categories)):
            pair = tuple(sorted([categories[i], categories[j]]))
            if pair in _UNIVERSAL_FIRE_PAIRS:
                return True
    return False


class ClarificationChecker:
    """Detect missing dimensional slots and generate clarification questions."""

    def detect_topic(self, query: str) -> str | None:
        """Detect the regulatory topic from query text."""
        query_lower = query.lower()
        for topic, triggers in TOPIC_TRIGGERS.items():
            for trigger in triggers:
                if trigger.lower() in query_lower:
                    return topic
        return None

    def check(
        self,
        intent: str,
        ship_info: dict,
        query: str,
        topic: str | None = None,
    ) -> tuple[bool, list[dict]]:
        """Check if clarification is needed.

        Strategy: "tiered answer" (分档回答) is preferred over clarification.
        The system should answer directly with scenario tiers in most cases.
        Clarification is only used as a last resort for extremely vague queries.

        Returns (needs_clarification, questions) where questions is a list of
        dicts with 'slot', 'question', and optional 'options' keys.
        """
        # If query contains clarification supplement, skip re-asking
        if "补充信息" in query or "补充：" in query:
            return False, []

        # Rule 1: If the fire division answer is universal (same for all ship types),
        # NEVER clarify — just answer directly
        if topic == "fire_division" and _is_universal_fire_answer(query):
            return False, []

        # Rule 2: If the user provided a ship type, NEVER clarify
        # (the system can give a tiered answer for the remaining unknowns)
        if ship_info.get("type"):
            return False, []

        # Rule 3: If the user mentioned specific space types for fire division,
        # answer with tiers rather than clarifying
        if topic == "fire_division":
            categories = _detect_space_categories(query)
            if len(categories) >= 2:
                return False, []

        # Rule 4: specification intent should answer with tiers, not clarify
        if intent == "specification":
            return False, []

        # Merge intent slots + topic-specific slots
        base_slots = REQUIRED_SLOTS.get(intent, {})
        critical = list(base_slots.get("critical", []))
        important = list(base_slots.get("important", []))

        if topic and topic in TOPIC_EXTRA_SLOTS:
            extra = TOPIC_EXTRA_SLOTS[topic]
            if extra.get("override_base"):
                critical = list(extra.get("critical", []))
                important = list(extra.get("important", []))
            elif intent in ("definition", "comparison"):
                for s in extra.get("critical", []):
                    if s not in important:
                        important.append(s)
            else:
                for s in extra.get("critical", []):
                    if s not in critical:
                        critical.append(s)
                for s in extra.get("important", []):
                    if s not in important:
                        important.append(s)

        # Check which critical slots are missing
        missing_critical = [s for s in critical if not self._has_slot(s, ship_info, query)]

        if not missing_critical:
            return False, []

        # Rule 5: Even if critical slots are missing, prefer tiered answers
        # Only clarify when the query is so vague that listing all scenarios
        # would produce too many different answers (>5 branches)
        if len(missing_critical) <= 1:
            # A single missing slot can be handled by a 2-4 row tier table
            return False, []

        questions = []
        for slot in missing_critical:
            template = CLARIFICATION_TEMPLATES.get(slot, {})
            questions.append({
                "slot": slot,
                "question": template.get("question", f"请提供 {slot} 信息"),
                "options": template.get("options"),
            })

        return True, questions

    def _has_slot(self, slot: str, ship_info: dict, query: str) -> bool:
        """Check if a dimensional slot is present in ship_info or query text."""
        if slot == "ship_type":
            if ship_info.get("type"):
                return True
            if any(p in query for p in _SHIP_TYPE_PATTERNS):
                return True
            # A specific regulation reference implies the user knows the context
            if _SPECIFIC_REG_RE.search(query):
                return True
            return False

        if slot == "tonnage_or_length":
            if ship_info.get("tonnage") or ship_info.get("length"):
                return True
            return bool(_DIMENSION_PATTERNS.search(query))

        if slot == "construction_date":
            return bool(_DATE_PATTERNS.search(query))

        if slot == "voyage_type":
            return any(p in query for p in _VOYAGE_PATTERNS)

        if slot == "discharge_source":
            query_lower = query.lower()
            # ODME is specifically a cargo tank discharge monitoring system
            discharge_indicators = [
                "货舱", "cargo tank", "机舱", "engine room", "舱底水", "bilge",
                "odme", "排油监控", "洗舱", "slop tank", "ows", "油水分离",
            ]
            return any(p in query_lower for p in discharge_indicators)

        if slot == "delivery_date":
            return bool(re.search(r"197[0-9]|198[0-9]|delivered|交付", query, re.IGNORECASE))

        return False
