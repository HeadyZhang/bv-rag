"""Maritime terminology mapping for query enhancement.

Bridges the gap between colloquial Chinese queries and the English-language
IMO regulation text stored in the vector database.
"""
import logging
import re

logger = logging.getLogger(__name__)

# Chinese colloquial term -> English IMO terminology
TERMINOLOGY_MAP: dict[str, list[str]] = {
    # Life-saving appliances
    "救生筏": ["liferaft", "life-raft", "inflatable liferaft"],
    "救生艇": ["lifeboat", "survival craft"],
    "释放设备": ["launching appliance", "release mechanism", "davit", "launching device"],
    "吊车": ["davit", "crane", "launching appliance"],
    "降落设备": ["davit", "launching appliance", "launching device"],
    "抛投式": ["throw-overboard", "inflatable liferaft"],
    "自由降落": ["free-fall", "free fall lifeboat"],
    "登乘梯": ["embarkation ladder", "boarding ladder"],
    "救生圈": ["lifebuoy", "life buoy"],
    "救生衣": ["lifejacket", "life-jacket"],
    "起降落": ["launching appliance", "davit", "launching device"],
    # Fire safety
    "灭火器": ["fire extinguisher", "portable extinguisher"],
    "消防泵": ["fire pump", "fire main"],
    "喷淋系统": ["sprinkler system", "water spraying system", "fixed fire-extinguishing"],
    "防火门": ["fire door", "fire-resistant division", "A-class division"],
    "烟雾探测": ["smoke detector", "fire detection", "smoke detection system"],
    "探火系统": ["fire detection system", "fire alarm"],
    "灭火系统": ["fire-extinguishing system", "fire fighting"],
    # Structure / access
    "通道": ["access", "means of access", "passage", "gangway"],
    "开口": ["opening", "clear opening", "hatchway"],
    "双壳": ["double hull", "double skin", "double bottom"],
    "水密门": ["watertight door", "watertight"],
    "舱壁": ["bulkhead", "watertight bulkhead"],
    "干舷": ["freeboard"],
    # Ship types
    "散货船": ["bulk carrier", "bulker"],
    "油轮": ["oil tanker", "tanker"],
    "客船": ["passenger ship", "passenger vessel"],
    "货船": ["cargo ship", "cargo vessel"],
    "集装箱船": ["container ship", "container vessel"],
    "化学品船": ["chemical tanker", "chemical carrier"],
    "气体船": ["gas carrier", "LNG carrier", "LPG carrier"],
    "滚装船": ["ro-ro ship", "roll-on roll-off"],
    # Dimensions
    "船长": ["length", "length overall", "LOA"],
    "总吨": ["gross tonnage", "GT"],
    "载重吨": ["deadweight", "DWT"],
    # Navigation / radio
    "导航": ["navigation", "navigational"],
    "雷达": ["radar", "ARPA"],
    "无线电": ["radio", "GMDSS"],
}

# Detected topic keywords -> relevant SOLAS/MARPOL chapters
TOPIC_TO_REGULATIONS: dict[str, list[str]] = {
    "liferaft": ["SOLAS III", "LSA Code"],
    "lifeboat": ["SOLAS III", "LSA Code"],
    "davit": ["SOLAS III", "LSA Code Chapter 6"],
    "launching appliance": ["SOLAS III", "LSA Code Chapter 6"],
    "davit-launched liferaft": ["SOLAS III/31", "SOLAS III/16", "LSA Code Chapter 6"],
    "free-fall": ["SOLAS III/31", "LSA Code Chapter 6"],
    "fire": ["SOLAS II-2", "FSS Code"],
    "stability": ["SOLAS II-1"],
    "pollution": ["MARPOL"],
    "access": ["SOLAS II-1/3-6"],
    "navigation": ["SOLAS V", "COLREG"],
    "radio": ["SOLAS IV", "GMDSS"],
    "cargo ship": ["SOLAS III/31", "SOLAS III/32"],
    "passenger ship": ["SOLAS III/21", "SOLAS III/22"],
}

# Keywords indicating LSA equipment in query
_LSA_KEYWORDS = [
    "救生筏", "救生艇", "liferaft", "lifeboat",
    "起降", "davit", "释放", "降落", "launching",
]

_LENGTH_RE = re.compile(r"(\d+)\s*[米m]", re.IGNORECASE)
_APPLICABILITY_KW = ["是否", "需不需要", "是否需要", "必须", "要不要", "需要",
                     "do I need", "is it required", "must", "required"]


class QueryEnhancer:
    """Enhance colloquial Chinese queries with English maritime terminology."""

    def enhance(self, query: str) -> str:
        """Return an enhanced query with injected English terms and regulation refs.

        The original query is kept intact; extra terms are appended after a
        pipe separator so both the original and the expanded terms contribute
        to embedding similarity and BM25 matching.
        """
        enhanced_parts = [query]
        matched_terms: set[str] = set()
        relevant_regs: set[str] = set()

        # Step 1: terminology mapping
        for zh_term, en_terms in TERMINOLOGY_MAP.items():
            if zh_term in query:
                matched_terms.update(en_terms)

        # Step 2: topic -> regulation chapter mapping
        for en_term in matched_terms:
            for topic, regs in TOPIC_TO_REGULATIONS.items():
                if topic in en_term.lower():
                    relevant_regs.update(regs)

        # Step 3: ship-type → configuration regulations
        has_lsa = any(kw in query for kw in _LSA_KEYWORDS)

        if any(kw in query for kw in ["货船", "cargo"]):
            relevant_regs.update(["SOLAS III/31", "SOLAS III/32"])
            if has_lsa:
                relevant_regs.update(["SOLAS III/16", "LSA Code Chapter 6"])
                matched_terms.add("davit-launched liferaft")
                matched_terms.add("free-fall lifeboat")

        if any(kw in query for kw in ["客船", "passenger"]):
            relevant_regs.update(["SOLAS III/21", "SOLAS III/22", "SOLAS III/16"])

        # Step 4: ship length → configuration thresholds
        length_match = _LENGTH_RE.search(query)
        if length_match:
            length = int(length_match.group(1))
            if has_lsa:
                if length >= 85:
                    # 85m+ cargo ships: davit-launched liferaft required
                    relevant_regs.add("SOLAS III/31")
                    matched_terms.add("davit-launched liferaft")
                    matched_terms.add("85 metres")
                    matched_terms.add("free-fall lifeboat")
                if length >= 80:
                    relevant_regs.add("SOLAS III/16")
                relevant_regs.add("LSA Code Chapter 6")

            # "国际航行" + length → likely cargo ship needing SOLAS III/31
            if "国际航行" in query or "international" in query.lower():
                relevant_regs.add("SOLAS III/31")

        if matched_terms:
            enhanced_parts.append(" ".join(sorted(matched_terms)))

        if relevant_regs:
            enhanced_parts.append(" ".join(sorted(relevant_regs)))

        enhanced_query = " | ".join(enhanced_parts) if len(enhanced_parts) > 1 else query

        logger.info(f"[QueryEnhancer] Original: {query}")
        logger.info(f"[QueryEnhancer] Matched terms: {matched_terms}")
        logger.info(f"[QueryEnhancer] Relevant regs: {relevant_regs}")
        logger.info(f"[QueryEnhancer] Enhanced: {enhanced_query}")

        return enhanced_query
