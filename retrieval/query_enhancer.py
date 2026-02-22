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
    "灭火系统": ["fire-extinguishing system", "fire fighting", "firefighting system", "CO2 system"],
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
    # MARPOL Annex VI — air pollution
    "氮氧化物": ["NOx", "nitrogen oxides", "emission"],
    "硫氧化物": ["SOx", "sulphur oxides", "sulfur oxides"],
    "排放控制区": ["ECA", "SECA", "emission control area"],
    "低硫燃油": ["VLSFO", "LSFO", "low sulphur fuel oil", "low sulfur"],
    # Firefighting / fire division definitions
    "消防总管": ["fire main", "fire pump", "hydrant"],
    "防火分隔定义": ["A-class division", "B-class division", "fire division definition"],
    # OWS (separate from 油水分离)
    "油水分离器": ["oily water separator", "OWS", "15 ppm"],
    # Inert gas system (SOLAS II-2/4.5.5)
    "惰气系统": ["inert gas system", "IGS", "inerting system"],
    "惰性气体": ["inert gas", "IG", "nitrogen"],
    "原油洗舱": ["crude oil washing", "COW"],
    "甲板水封": ["deck water seal"],
    # Tanker cargo tank protection (SOLAS II-2/11.6)
    "货舱保护": ["cargo tank protection", "tank protection"],
    "压力真空阀": ["pressure vacuum valve", "P/V valve", "PV valve"],
    "压力报警": ["pressure alarm", "overpressure alarm", "high pressure alarm"],
    "真空报警": ["vacuum alarm", "underpressure alarm", "low pressure alarm"],
    # === Batch-3 numerical chunk terms (Workflow 2) ===
    # SOLAS III/32 — personal LSA
    "浸水服": ["immersion suit"],
    "保温用具": ["thermal protective aid"],
    "火箭降落伞信号": ["rocket parachute flare"],
    "自亮灯": ["self-igniting light"],
    "自发烟雾信号": ["self-activating smoke signal", "buoyant smoke signal"],
    "儿童救生衣": ["child lifejacket", "infant lifejacket"],
    "个人救生设备": ["personal life-saving appliance", "personal LSA"],
    # SOLAS V/19 — navigation equipment
    "电子海图": ["ECDIS", "electronic chart display"],
    "航行数据记录仪": ["VDR", "voyage data recorder"],
    "自动识别系统": ["AIS", "automatic identification system"],
    "航行设备": ["navigation equipment", "navigational equipment"],
    "回声测深仪": ["echo sounder", "echo-sounding device"],
    "陀螺罗经": ["gyro compass", "gyroscopic compass"],
    "磁罗经": ["magnetic compass"],
    "测速仪": ["speed log", "speed and distance measuring device"],
    # SOLAS II-1/29 — steering gear
    "舵机": ["steering gear", "rudder"],
    "操舵装置": ["steering gear", "steering apparatus"],
    "主舵机": ["main steering gear"],
    "辅助舵机": ["auxiliary steering gear"],
    "应急舵机": ["emergency steering gear"],
    "转舵时间": ["rudder angle time", "35 degrees to 30 degrees"],
    # SOLAS II-2/7 — fire detection
    "烟感探测器": ["smoke detector"],
    "温感探测器": ["heat detector", "thermal detector"],
    "探测器间距": ["detector spacing", "37 square metres"],
    "手动报警按钮": ["manual call point", "manual alarm"],
    "报警确认时间": ["alarm confirmation time", "2 minutes"],
    "火灾报警系统": ["fire alarm system"],
    # MARPOL Annex IV — sewage
    "生活污水": ["sewage", "black water"],
    "污水处理装置": ["sewage treatment plant", "STP"],
    "污水排放": ["sewage discharge"],
    "黑水": ["black water", "sewage"],
    # MARPOL Annex V — garbage
    "垃圾排放": ["garbage discharge", "garbage disposal"],
    "垃圾管理计划": ["garbage management plan"],
    "垃圾记录簿": ["garbage record book"],
    "食物废弃物": ["food waste"],
    "塑料禁排": ["plastic prohibition", "no plastic discharge"],
    "货物残余": ["cargo residue"],
    # SOLAS II-1/22 — watertight doors
    "水密完整性": ["watertight integrity", "subdivision integrity"],
    "远程关闭": ["remote closing", "central closing"],
    # === Workflow 6 routing terms ===
    "航行安全": ["safety of navigation"],
    "弃船": ["abandon ship"],
    "集合站": ["muster station", "assembly station"],
    "登乘站": ["embarkation station"],
    "油类记录簿": ["Oil Record Book", "ORB"],
    "安全管理": ["safety management", "ISM"],
    "船舶安保": ["ship security", "ISPS"],
}

# Detected topic keywords -> relevant SOLAS/MARPOL chapters
TOPIC_TO_REGULATIONS: dict[str, list[str]] = {
    "liferaft": ["SOLAS III", "SOLAS III/31", "LSA Code"],
    "lifeboat": ["SOLAS III", "LSA Code"],
    "davit": ["SOLAS III", "SOLAS III/31", "LSA Code Chapter 6"],
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
    # Batch-2 audit fixes
    "1/30000": ["MARPOL Annex I/Reg.29", "MARPOL Annex I/Reg.34"],
    "NOx": ["MARPOL Annex VI/Reg.13"],
    "SOx": ["MARPOL Annex VI/Reg.14"],
    "sulphur content": ["MARPOL Annex VI/Reg.14"],
    "ECA": ["MARPOL Annex VI"],
    "SECA": ["MARPOL Annex VI"],
    "A-class": ["SOLAS II-2/3", "SOLAS II-2/9"],
    "B-class": ["SOLAS II-2/3", "SOLAS II-2/9"],
    "A-60": ["SOLAS II-2/3", "SOLAS II-2/9"],
    "fire division definition": ["SOLAS II-2/3"],
    "CO2 system": ["SOLAS II-2/10", "FSS Code"],
    "fire extinguishing": ["SOLAS II-2/10", "FSS Code"],
    "fire main": ["SOLAS II-2/10"],
    # Tanker cargo tank protection (SOLAS II-2/11.6)
    "pressure alarm": ["SOLAS II-2/11.6", "SOLAS II-2/11"],
    "P/V valve": ["SOLAS II-2/11.6", "SOLAS II-2/11"],
    "cargo tank protection": ["SOLAS II-2/11.6", "SOLAS II-2/11"],
    "tanker venting": ["SOLAS II-2/11.6", "SOLAS II-2/11"],
    "cargo tank pressure": ["SOLAS II-2/11.6", "SOLAS II-2/11"],
    "vacuum protection": ["SOLAS II-2/11.6", "SOLAS II-2/11"],
    # Inert gas system (SOLAS II-2/4.5.5)
    "inert gas": ["SOLAS II-2/4.5.5"],
    "IGS": ["SOLAS II-2/4.5.5"],
    "inerting": ["SOLAS II-2/4.5.5"],
    "crude oil washing": ["SOLAS II-2/4.5.5"],
    "COW": ["SOLAS II-2/4.5.5"],
    "8000 DWT": ["SOLAS II-2/4.5.5"],
    # === Batch-3 topic mappings (Workflow 2) ===
    "lifebuoy": ["SOLAS III/32"],
    "lifejacket": ["SOLAS III/32"],
    "immersion suit": ["SOLAS III/32"],
    "personal LSA": ["SOLAS III/32"],
    "rocket parachute flare": ["SOLAS III/32"],
    "ECDIS": ["SOLAS V/19"],
    "AIS": ["SOLAS V/19"],
    "VDR": ["SOLAS V/20"],
    "voyage data recorder": ["SOLAS V/20"],
    "gyro compass": ["SOLAS V/19"],
    "echo sounder": ["SOLAS V/19"],
    "BNWAS": ["SOLAS V/19"],
    "steering gear": ["SOLAS II-1/29"],
    "rudder": ["SOLAS II-1/29"],
    "smoke detector": ["SOLAS II-2/7", "FSS Code Ch.9"],
    "heat detector": ["SOLAS II-2/7", "FSS Code Ch.9"],
    "fire detection": ["SOLAS II-2/7"],
    "fire alarm": ["SOLAS II-2/7"],
    "detector spacing": ["SOLAS II-2/7", "FSS Code Ch.9"],
    "bilge water": ["MARPOL Annex I/Reg.15"],
    "oily water separator": ["MARPOL Annex I/Reg.15"],
    "15 ppm": ["MARPOL Annex I/Reg.15"],
    "sewage": ["MARPOL Annex IV/Reg.11"],
    "sewage treatment": ["MARPOL Annex IV/Reg.11"],
    "STP": ["MARPOL Annex IV/Reg.11"],
    "garbage": ["MARPOL Annex V/Reg.4"],
    "garbage discharge": ["MARPOL Annex V/Reg.4"],
    "plastic": ["MARPOL Annex V/Reg.4"],
    "garbage record book": ["MARPOL Annex V"],
    "watertight door": ["SOLAS II-1/22"],
    "watertight bulkhead": ["SOLAS II-1/22"],
    # === Workflow 6 routing topic mappings ===
    "safety of navigation": ["SOLAS V"],
    "ISM": ["SOLAS IX", "ISM Code"],
    "ISPS": ["SOLAS XI-2", "ISPS Code"],
    "muster station": ["SOLAS III/11", "SOLAS III/25"],
    "abandon ship": ["SOLAS III"],
    "Oil Record Book": ["MARPOL Annex I"],
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
            # Inject ship-type-specific tables based on detected ship type
            detected_ship = self.extract_ship_type_from_query(query)
            if detected_ship == "tanker":
                fire_tables.extend(["Table 9.7", "Table 9.8", "Regulation 9/2.4 Tankers"])
            elif detected_ship == "passenger_ship":
                fire_tables.extend(["Table 9.1", "Table 9.2", "Table 9.3", "Table 9.4"])
            elif detected_ship == "cargo_ship_non_tanker":
                fire_tables.extend(["Table 9.5", "Table 9.6", "Regulation 9/2.3"])
            else:
                # No ship type detected: inject most common tables
                fire_tables.extend(["Table 9.1", "Table 9.5", "Table 9.7"])
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

        # Tanker cargo tank pressure/vacuum protection -> inject SOLAS II-2/11.6 terms
        if any(kw in query for kw in ["货舱保护", "压力真空阀", "压力报警", "真空报警",
                                       "cargo tank protection", "P/V valve", "pressure alarm",
                                       "vacuum alarm", "cargo tank pressure", "tanker venting",
                                       "vacuum protection", "overpressure"]):
            matched_terms.update([
                "SOLAS II-2/11.6", "cargo tank protection",
                "pressure vacuum valve", "P/V valve",
                "pressure alarm", "vacuum alarm",
                "overpressure", "underpressure",
                "pressure sensor", "cargo control room",
            ])
            relevant_regs.update(["SOLAS II-2/11.6", "SOLAS II-2/11"])

        # Steering gear -> inject SOLAS II-1/29 terms
        if any(kw in query for kw in ["舵机", "操舵装置", "主舵机", "辅助舵机", "转舵",
                                       "steering gear", "rudder angle"]):
            matched_terms.update([
                "steering gear", "rudder", "35 degrees", "28 seconds",
                "auxiliary steering", "main steering gear",
                "power actuating system", "tanker steering",
            ])
            relevant_regs.update(["SOLAS II-1/29"])

        # Fire detection -> inject SOLAS II-2/7 + FSS Code terms
        if any(kw in query for kw in ["烟感探测器", "温感探测器", "探测器间距", "火灾探测",
                                       "探火系统", "手动报警", "fire detection", "smoke detector",
                                       "detector spacing"]):
            matched_terms.update([
                "SOLAS II-2/7", "fire detection", "smoke detector",
                "heat detector", "37 square metres", "11 metres",
                "manual call point", "FSS Code Chapter 9",
            ])
            relevant_regs.update(["SOLAS II-2/7", "FSS Code Ch.9"])

        # Sewage -> inject MARPOL Annex IV terms
        if any(kw in query for kw in ["生活污水", "污水处理", "污水排放", "黑水",
                                       "sewage", "STP", "black water"]):
            matched_terms.update([
                "sewage", "sewage treatment plant", "STP",
                "12 nautical miles", "3 nautical miles", "holding tank",
                "comminuting", "disinfecting",
            ])
            relevant_regs.update(["MARPOL Annex IV/Reg.11"])

        # Garbage -> inject MARPOL Annex V terms
        if any(kw in query for kw in ["垃圾排放", "垃圾管理", "垃圾记录簿", "食物废弃物",
                                       "塑料禁排", "garbage", "plastic prohibition"]):
            matched_terms.update([
                "garbage", "garbage discharge", "garbage management plan",
                "garbage record book", "plastic", "food waste",
                "special area", "12 nautical miles",
            ])
            relevant_regs.update(["MARPOL Annex V/Reg.4"])

        # Watertight doors -> inject SOLAS II-1/22 terms
        if any(kw in query for kw in ["水密门", "水密舱壁", "水密完整性", "远程关闭",
                                       "watertight door", "watertight bulkhead"]):
            matched_terms.update([
                "watertight door", "watertight bulkhead",
                "40 seconds", "central closing", "bridge indicator",
                "sliding door", "power operated", "weekly test",
            ])
            relevant_regs.update(["SOLAS II-1/22"])

        # Navigation equipment -> inject SOLAS V/19 terms
        if any(kw in query for kw in ["电子海图", "航行设备", "航行数据记录仪",
                                       "自动识别系统", "ECDIS", "VDR", "AIS carriage",
                                       "navigation equipment carriage"]):
            matched_terms.update([
                "SOLAS V/19", "ECDIS", "AIS", "VDR", "S-VDR",
                "radar", "gyro compass", "echo sounder", "BNWAS",
                "carriage requirements", "300 GT", "3000 GT",
            ])
            relevant_regs.update(["SOLAS V/19", "SOLAS V/20"])

        # Personal LSA -> inject SOLAS III/32 terms
        if any(kw in query for kw in ["救生圈", "救生衣", "浸水服", "个人救生设备",
                                       "lifebuoy", "lifejacket", "immersion suit"]):
            matched_terms.update([
                "lifebuoy", "lifejacket", "immersion suit",
                "thermal protective aid", "rocket parachute flare",
                "self-igniting light", "personal LSA",
            ])
            relevant_regs.update(["SOLAS III/32"])

        # Inert gas system -> inject SOLAS II-2/4.5.5 terms
        if any(kw in query for kw in ["惰气系统", "惰性气体", "原油洗舱", "甲板水封",
                                       "inert gas", "IGS", "inerting",
                                       "crude oil washing", "COW"]):
            matched_terms.update([
                "SOLAS II-2/4.5.5", "inert gas system", "IGS",
                "8000 DWT", "20000 DWT", "crude oil washing", "COW",
                "oxygen content", "cargo tank explosion",
                "deck water seal", "nitrogen generator",
            ])
            relevant_regs.update(["SOLAS II-2/4.5.5", "SOLAS II-2/4"])

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

    @staticmethod
    def extract_ship_type_from_query(query: str) -> str | None:
        """Extract ship type from a user query (Chinese or English).

        Returns one of:
          - "tanker"
          - "passenger_ship"
          - "cargo_ship_non_tanker"
          - None (cannot determine)
        """
        lower = query.lower()

        # --- Tanker detection (highest priority — SOLAS Ch I, Reg 2(h)) ---
        # Explicit tanker keywords
        cn_tanker = ["油轮", "化学品船", "成品油轮", "原油轮", "tanker"]
        if any(kw in lower for kw in cn_tanker):
            return "tanker"

        # Descriptive phrases: "运输可燃液体货物的轮船"
        if "可燃" in lower and ("液体" in lower or "液货" in lower):
            return "tanker"
        if "运输" in lower and "液体" in lower and "货物" in lower:
            return "tanker"

        en_tanker = [
            "oil tanker", "chemical tanker", "product tanker",
            "flammable liquid", "inflammable liquid",
            "oil carrier", "chemical carrier",
        ]
        if any(kw in lower for kw in en_tanker):
            return "tanker"

        # --- Passenger ship detection ---
        cn_passenger = ["客船", "客轮", "邮轮", "cruise"]
        if any(kw in lower for kw in cn_passenger):
            return "passenger_ship"
        if "passenger" in lower:
            return "passenger_ship"

        # --- Non-tanker cargo ship detection ---
        cn_cargo_non_tanker = [
            "散货船", "集装箱船", "杂货船", "多用途船",
            "bulk carrier", "container ship", "general cargo",
        ]
        if any(kw in lower for kw in cn_cargo_non_tanker):
            return "cargo_ship_non_tanker"

        # Generic "cargo ship" without further qualification → non-tanker
        if "货船" in lower or "cargo ship" in lower:
            return "cargo_ship_non_tanker"

        return None
