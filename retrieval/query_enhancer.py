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
    # Fire safety - equipment
    "灭火器": ["fire extinguisher", "portable extinguisher"],
    "消防泵": ["fire pump", "fire main"],
    "喷淋系统": ["sprinkler system", "water spraying system", "fixed fire-extinguishing"],
    "防火门": ["fire door", "fire-resistant division", "A-class division"],
    "烟雾探测": ["smoke detector", "fire detection", "smoke detection system"],
    "探火系统": ["fire detection system", "fire alarm"],
    "灭火系统": ["fire-extinguishing system", "fire fighting"],
    # Fire safety - structural
    "防火分隔": ["fire division", "fire integrity", "A-class division", "B-class division", "structural fire protection"],
    "防火等级": ["fire rating", "fire integrity", "structural fire protection"],
    "厨房": ["galley", "cooking area", "service space high risk", "Category 9"],
    "走廊": ["corridor", "passageway", "escape route", "Category 2"],
    "驾驶室": ["wheelhouse", "navigation bridge", "control station", "Category 1"],
    "住舱": ["accommodation space", "cabin", "crew quarters", "Category 3"],
    "控制站": ["control station", "fire control station", "Category 1"],
    "机舱": ["engine room", "machinery space", "machinery space of Category A", "Category 6"],
    "甲板": ["deck", "fire integrity of decks"],
    # Structure / access
    "通道": ["access", "means of access", "passage", "gangway"],
    "开口": ["opening", "clear opening", "hatchway"],
    "双壳": ["double hull", "double skin", "double bottom"],
    "水密门": ["watertight door", "watertight"],
    "舱壁": ["bulkhead", "watertight bulkhead", "fire integrity of bulkheads"],
    "干舷": ["freeboard", "freeboard deck"],
    "干舷甲板": ["freeboard deck"],
    # MARPOL - discharge
    "排油": ["oil discharge", "ODME", "discharge monitoring", "oily mixture"],
    "排油监控": ["ODME", "oil discharge monitoring and control system"],
    "排油量": ["oil discharge quantity", "total oil discharge", "discharge limit"],
    "排放": ["discharge", "disposal"],
    "油水分离": ["OWS", "oily water separator", "15 ppm"],
    "舱底水": ["bilge water", "bilge", "engine room bilge"],
    # Load Lines - ventilation / structures
    "透气管": ["air pipe", "vent pipe", "tank vent", "Regulation 20"],
    "上层建筑": ["superstructure", "superstructure deck", "first tier", "Regulation 3(10)"],
    "甲板室": ["deckhouse", "deck house"],
    "围蔽": ["enclosed", "enclosed superstructure", "weathertight"],
    "开口高度": ["opening height", "height above deck", "air pipe height"],
    "通风筒": ["ventilator", "ventilation opening"],
    "舱口盖": ["hatch cover", "hatchway"],
    "风雨密": ["weathertight", "weathertight closing"],
    "水密": ["watertight", "watertight closing"],
    "载重线": ["load line", "load lines convention", "ICLL"],
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
    # BV Rules terminology
    "入级": ["classification", "class", "NR467", "BV Rules for Classification of Steel Ships"],
    "船级社": ["classification society", "Bureau Veritas", "BV"],
    "调速器": ["governor", "speed governor", "governing characteristics"],
    "并联运行": ["parallel operation", "operating in parallel", "load sharing"],
    "功率分配": ["load sharing", "power distribution", "proportionate share"],
    "发电机": ["generator", "generating set", "alternating current generating set"],
    "NR467": ["BV Rules for Classification of Steel Ships", "NR467", "BV NR467"],
    "NR670": ["BV Rules for Classification of Methanol-fuelled Ships", "NR670", "BV NR670"],
    "入级检验": ["classification survey", "initial survey", "renewal survey"],
    "附加标志": ["additional class notation", "notation", "class notation"],
    "结构强度": ["structural strength", "scantling", "hull girder"],
    "腐蚀余量": ["corrosion addition", "corrosion allowance", "wastage"],
    "疲劳强度": ["fatigue strength", "fatigue assessment", "fatigue life"],
    "有限元分析": ["finite element analysis", "FEA", "direct calculation"],
    "许用应力": ["allowable stress", "permissible stress"],
    "最小板厚": ["minimum thickness", "minimum plate thickness"],
    # IACS terminology
    "统一要求": ["unified requirement", "UR", "IACS UR"],
    "统一解释": ["unified interpretation", "UI", "IACS UI"],
    "共同结构规范": ["common structural rules", "CSR", "CSR BC&OT"],
    "极地船舶": ["polar class", "polar ship", "ice class"],
    "网络安全": ["cyber resilience", "UR E26", "UR E27", "cybersecurity"],
    # IBC Code terminology
    "有毒货物": ["toxic products", "toxic cargo", "toxic chemical", "IBC Code 15.12"],
    "有毒产品": ["toxic products", "toxic cargo", "IBC Code 15.12"],
    "透气管排气口": ["exhaust opening", "tank vent outlet", "vent outlet", "IBC Code 15.12"],
    "高速透气阀": ["high velocity vent valve", "high-velocity vent valve", "30 m/s"],
    "蒸汽回收": ["vapour return", "vapour-return line", "shore installation"],
    "IBC": ["IBC Code", "International Code for Construction and Equipment of Ships Carrying Dangerous Chemicals in Bulk"],
    "IBC规则": ["IBC Code", "chemical tanker code"],
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
    "fire division": ["SOLAS II-2/9", "SOLAS II-2/3"],
    "fire integrity": ["SOLAS II-2/9", "SOLAS II-2/3"],
    "fire rating": ["SOLAS II-2/9", "SOLAS II-2/3"],
    "galley": ["SOLAS II-2/9"],
    "corridor": ["SOLAS II-2/9"],
    "control station": ["SOLAS II-2/9"],
    "oil discharge": ["MARPOL Annex I/Reg.34", "MARPOL Annex I/Reg.15"],
    "ODME": ["MARPOL Annex I/Reg.34", "MEPC.108(49)"],
    "oil discharge monitoring": ["MARPOL Annex I/Reg.34", "MEPC.108(49)"],
    "bilge": ["MARPOL Annex I/Reg.15"],
    "oily water separator": ["MARPOL Annex I/Reg.15"],
    "engine room": ["SOLAS II-2/9", "SOLAS II-1"],
    "machinery space": ["SOLAS II-2/9", "SOLAS II-1"],
    "accommodation": ["SOLAS II-2/9"],
    "Category 9": ["SOLAS II-2/9"],
    "Category 1": ["SOLAS II-2/9"],
    "Category 6": ["SOLAS II-2/9"],
    "deck": ["SOLAS II-2/9"],
    "air pipe": ["Load Lines Reg.20", "ICLL 1966/1988"],
    "air pipe height": ["Load Lines Reg.20", "ICLL Reg.20"],
    "vent pipe": ["Load Lines Reg.20", "ICLL 1966/1988"],
    "freeboard deck": ["Load Lines Convention", "ICLL 1966/1988"],
    "superstructure": ["ICLL Reg.3(10)", "ICLL Reg.20", "Load Lines Convention"],
    "deckhouse": ["ICLL Reg.3", "Load Lines Convention"],
    "freeboard": ["ICLL", "Load Lines Convention"],
    "enclosed superstructure": ["ICLL Reg.12", "ICLL Reg.37"],
    "ventilator": ["Load Lines Reg.22", "ICLL 1966/1988"],
    "hatch cover": ["ICLL Reg.13-16", "Load Lines Convention"],
    "weathertight": ["ICLL Reg.12", "ICLL Reg.18"],
    "load line": ["ICLL 1966/1988", "Load Lines Convention"],
    "stability": ["SOLAS II-1"],
    "pollution": ["MARPOL"],
    "access": ["SOLAS II-1/3-6"],
    "navigation": ["SOLAS V", "COLREG"],
    "radio": ["SOLAS IV", "GMDSS"],
    "cargo ship": ["SOLAS III/31", "SOLAS III/32"],
    "passenger ship": ["SOLAS III/21", "SOLAS III/22"],
    # BV Rules
    "classification": ["BV NR467", "IACS UR Z"],
    "structural strength": ["BV NR467 Pt.B", "IACS UR S", "CSR"],
    "scantling": ["BV NR467 Pt.B", "IACS UR S"],
    "materials welding": ["BV NR216", "IACS UR W"],
    "corrosion": ["BV NR467 Pt.B", "IACS UR S"],
    "fatigue": ["BV NR467 Pt.B Ch.7", "IACS UR S"],
    # IACS UR -> IMO convention links
    "mooring": ["IACS UR A", "SOLAS II-1"],
    "anchoring": ["IACS UR A", "SOLAS II-1"],
    "fire protection iacs": ["IACS UR F", "SOLAS II-2"],
    "polar": ["IACS UR I", "Polar Code"],
    "cyber": ["IACS UR E26", "IACS UR E27"],
    "survey certification": ["IACS UR Z", "SOLAS XI"],
    # BV Rules — specific NR numbers
    "governor": ["BV NR467 Part C", "BV NR467 2.7.6"],
    "generating set": ["BV NR467 Part C", "BV NR467 2.7"],
    "parallel operation": ["BV NR467 Part C", "BV NR467 2.7.6"],
    "load sharing": ["BV NR467 Part C", "BV NR467 2.7.6"],
    "NR467": ["BV NR467", "BV Rules for Classification of Steel Ships"],
    "NR670": ["BV NR670", "BV Rules for Classification of Methanol-fuelled Ships"],
    "methanol": ["BV NR670", "IGF Code"],
    "electrical installation": ["BV NR467 Part C", "SOLAS II-1"],
    # IBC Code
    "toxic cargo": ["IBC Code 15.12", "IBC Code Ch.15"],
    "toxic products": ["IBC Code 15.12", "IBC Code Ch.15"],
    "chemical tanker": ["IBC Code", "SOLAS VII"],
    "tank vent": ["IBC Code 15.12", "IBC Code Ch.8"],
    "exhaust opening": ["IBC Code 15.12"],
    "IBC Code": ["IBC Code Ch.15", "IBC Code Ch.17"],
    "vapour return": ["IBC Code 15.12"],
}

# Keywords indicating LSA equipment in query
_LSA_KEYWORDS = [
    "救生筏", "救生艇", "liferaft", "lifeboat",
    "起降", "davit", "释放", "降落", "launching",
]

_LENGTH_RE = re.compile(r"(\d+)\s*[米m]", re.IGNORECASE)
_APPLICABILITY_KW = ["是否", "需不需要", "是否需要", "必须", "要不要", "需要",
                     "do I need", "is it required", "must", "required"]
_BILATERAL_KW = [
    "两边", "两舷", "每舷", "双侧", "两侧", "左右",
    "both sides", "each side", "port and starboard",
]


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

        # Step 3: ship-type -> configuration regulations
        has_lsa = any(kw in query for kw in _LSA_KEYWORDS)

        if any(kw in query for kw in ["货船", "cargo"]):
            relevant_regs.update(["SOLAS III/31", "SOLAS III/32"])
            if has_lsa:
                relevant_regs.update(["SOLAS III/16", "LSA Code Chapter 6"])
                matched_terms.add("davit-launched liferaft")
                matched_terms.add("free-fall lifeboat")

        if any(kw in query for kw in ["客船", "passenger"]):
            relevant_regs.update(["SOLAS III/21", "SOLAS III/22", "SOLAS III/16"])

        # Step 4: ship length -> configuration thresholds
        length_match = _LENGTH_RE.search(query)
        if length_match:
            length = int(length_match.group(1))
            if has_lsa:
                if length >= 85:
                    relevant_regs.add("SOLAS III/31")
                    matched_terms.add("davit-launched liferaft")
                    matched_terms.add("85 metres")
                    matched_terms.add("free-fall lifeboat")
                if length >= 80:
                    relevant_regs.add("SOLAS III/16")
                relevant_regs.add("LSA Code Chapter 6")

            if "国际航行" in query or "international" in query.lower():
                relevant_regs.add("SOLAS III/31")

        # Step 5: bilateral/both-sides -> inject configuration combination terms
        has_bilateral = any(kw in query for kw in _BILATERAL_KW)
        if has_bilateral and has_lsa:
            matched_terms.add("throw-overboard liferaft")
            matched_terms.add("davit-launched liferaft")
            matched_terms.add("each side")
            matched_terms.add("hydrostatic release")
            relevant_regs.add("SOLAS III/31.1.4")
            relevant_regs.add("SOLAS III/31.1.3")

        # Step 6: topic-specific keyword injection
        # Fire division -> inject table keywords for better retrieval
        if any(kw in query for kw in ["防火分隔", "防火等级", "厨房", "走廊", "驾驶室", "住舱", "机舱"]):
            fire_tables = [
                "fire integrity of bulkheads and decks",
                "structural fire protection",
            ]
            # Inject ship-type-specific tables
            if any(kw in query for kw in ["货船", "cargo"]):
                fire_tables.extend(["Table 9.5", "Table 9.6"])
            elif any(kw in query for kw in ["客船", "passenger"]):
                fire_tables.extend(["Table 9.1", "Table 9.2", "Table 9.3", "Table 9.4"])
            else:
                # Default: inject most common tables (cargo + passenger >36)
                fire_tables.extend(["Table 9.1", "Table 9.5"])
            matched_terms.update(fire_tables)
            relevant_regs.update(["SOLAS II-2/9", "SOLAS II-2/3"])

        # Oil discharge -> inject Reg.34 key data terms
        if any(kw in query for kw in ["排油", "ODME"]):
            matched_terms.update([
                "Regulation 34", "1/30000", "discharge limit",
                "30 litres per nautical mile",
            ])
            relevant_regs.update(["MARPOL Annex I/Reg.34"])

        # Air pipe -> inject position classification + definition boundary keywords
        if any(kw in query for kw in ["透气管", "air pipe", "开口高度"]):
            matched_terms.update([
                "position 1", "position 2", "760 mm", "450 mm",
                "freeboard deck", "superstructure deck",
                "first tier", "Regulation 20", "Regulation 3(10)",
            ])
            relevant_regs.update(["Load Lines Reg.20", "ICLL Reg.3(10)"])
            # If query mentions tiers above 1st, inject boundary condition terms
            if any(kw in query for kw in ["第二层", "第三层", "第2层", "第3层",
                                          "2nd tier", "3rd tier", "上方"]):
                matched_terms.update([
                    "no mandatory height", "not covered by Reg.20",
                    "deckhouse", "above superstructure",
                ])

        # Load lines / superstructure definition -> inject ICLL terms
        if any(kw in query for kw in ["上层建筑", "甲板室", "载重线"]):
            matched_terms.update([
                "superstructure definition", "first tier",
                "freeboard deck", "deckhouse",
            ])
            relevant_regs.update(["ICLL Reg.3(10)", "Load Lines Convention"])

        # IBC Code / chemical tanker -> inject IBC-specific terms
        if any(kw in query for kw in ["有毒货物", "有毒产品", "化学品船", "IBC", "toxic cargo",
                                       "toxic products", "chemical tanker"]):
            matched_terms.update([
                "IBC Code", "Chapter 15", "15.12", "toxic products",
                "exhaust opening", "tank vent", "15 metres",
                "accommodation", "air intake",
            ])
            relevant_regs.update(["IBC Code 15.12", "IBC Code Ch.15"])

        if matched_terms:
            enhanced_parts.append(" ".join(sorted(matched_terms)))

        if relevant_regs:
            enhanced_parts.append(" ".join(sorted(relevant_regs)))

        enhanced_query = " | ".join(enhanced_parts) if len(enhanced_parts) > 1 else query

        # Store on instance for external access
        self._last_matched_terms = matched_terms
        self._last_relevant_regs = relevant_regs

        logger.info(f"[ENHANCE] 匹配术语: {matched_terms}")
        logger.info(f"[ENHANCE] 关联法规: {relevant_regs}")
        logger.info(f"[ENHANCE] 增强查询: {enhanced_query[:200]}")

        return enhanced_query
