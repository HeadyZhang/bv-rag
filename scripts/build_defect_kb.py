#!/usr/bin/env python3
"""Build defect_kb.json with 100 PSC defect entries.

Based on:
- Paris MOU THETIS deficiency codes (2023-2024)
- Tokyo MOU annual report statistics (2023-2024)
- SOLAS, MARPOL, STCW, MLC, ISM, ISPS conventions
"""
import json
from datetime import date

defects = []

def d(id_, cat, subcat, triggers_zh, text_en, text_zh, refs, ship_types, areas,
      inspections, risk, freq, pmu_code=None, tmu_code=None, variants=None):
    """Shorthand defect builder."""
    entry = {
        "id": id_,
        "category": cat,
        "subcategory": subcat,
        "chinese_triggers": triggers_zh,
        "standard_text_en": text_en,
        "standard_text_zh": text_zh,
        "regulation_refs": [{"convention": r[0], "ref": r[1], "full_text": r[2]} for r in refs],
        "applicable_ship_types": ship_types,
        "applicable_areas": areas,
        "applicable_inspections": inspections,
        "detention_risk": risk,
        "frequency_rank": freq,
    }
    if pmu_code:
        entry["paris_mou_code"] = pmu_code
    if tmu_code:
        entry["tokyo_mou_code"] = tmu_code
    if variants:
        entry["variants"] = variants
    defects.append(entry)


# ============================================================
# FIRE SAFETY (15 entries) DEF-001 ~ DEF-015
# Paris MOU: 17.2% of all deficiencies (2024), #1 category
# Tokyo MOU: 15,406 deficiencies (2024), #1 category
# ============================================================

d("DEF-001", "fire_safety", "fire_doors",
  ["防火门", "防火门关不上", "防火门损坏", "自闭装置", "防火门无法关闭"],
  "Fire door(s) / opening(s) in fire-resisting division found not self-closing / unable to be closed properly.",
  "防火分隔上的防火门/开口无法自闭/无法正常关闭。",
  [("SOLAS", "Reg II-2/9.4.1", "Doors in fire-resisting divisions"),
   ("FSS Code", "Chapter 11", "Fire door testing procedures")],
  ["all"], ["accommodation", "engine_room", "deck"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "high", 1, "07105", "0701",
  [{"condition": "held open without release mechanism",
    "text_en": "Fire door(s) found held open by unauthorized means (hook/wedge) without approved hold-back system.",
    "text_zh": "防火门被未经批准的方式（钩子/楔子）固定在开启位置，无认可的自动释放装置。"},
   {"condition": "damaged/corroded",
    "text_en": "Fire door frame/seal found damaged/corroded, integrity of fire-resisting division compromised.",
    "text_zh": "防火门框/密封件损坏/锈蚀，防火分隔完整性受损。"}])

d("DEF-002", "fire_safety", "fire_detection",
  ["火警探测", "火灾报警", "烟感", "烟雾探测器", "感烟探测器", "火警系统", "探测器故障"],
  "Fire detection and fire alarm system found defective / not operational.",
  "火灾探测和报警系统故障/不能正常工作。",
  [("SOLAS", "Reg II-2/7", "Detection and alarm"),
   ("FSS Code", "Chapter 9", "Fire detection and alarm systems")],
  ["all"], ["engine_room", "bridge", "accommodation", "cargo_hold"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "high", 2, "07109", "0702",
  [{"condition": "detectors missing/covered",
    "text_en": "Fire/smoke detector(s) found missing from designated location(s) / covered/painted over.",
    "text_zh": "火灾/烟雾探测器在指定位置缺失/被遮盖/被油漆覆盖。"},
   {"condition": "alarm panel defective",
    "text_en": "Fire alarm panel found with fault indication(s) / unable to identify zone of detection.",
    "text_zh": "火灾报警控制面板显示故障/无法识别探测区域。"}])

d("DEF-003", "fire_safety", "fire_extinguisher",
  ["灭火器", "灭火器过期", "灭火器压力不足", "灭火器缺失", "手提灭火器"],
  "Portable fire extinguisher(s) found expired / not maintained as required.",
  "手提式灭火器超过检验有效期/未按要求维护保养。",
  [("SOLAS", "Reg II-2/10.3", "Portable fire extinguishers"),
   ("FSS Code", "Chapter 4", "Fire extinguishers")],
  ["all"], ["engine_room", "bridge", "accommodation", "deck"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "medium", 5, "07112", "0703",
  [{"condition": "missing from designated location",
    "text_en": "Required portable fire extinguisher(s) found missing from designated location.",
    "text_zh": "指定位置的手提式灭火器缺失。"},
   {"condition": "pressure gauge indicating low/discharged",
    "text_en": "Portable fire extinguisher(s) found with pressure gauge indicating discharge / low pressure.",
    "text_zh": "手提式灭火器压力表显示已释放/压力不足。"}])

d("DEF-004", "fire_safety", "fire_hose",
  ["消防水带", "消防栓", "消防水枪", "消防水龙带", "消防软管"],
  "Fire hose(s) and/or nozzle(s) found in poor condition / not readily available.",
  "消防水带和/或水枪状况不良/无法随时使用。",
  [("SOLAS", "Reg II-2/10.2", "Fire mains, fire pumps and hydrants"),
   ("FSS Code", "Chapter 4", "Fire extinguishers")],
  ["all"], ["engine_room", "deck", "accommodation"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "medium", 8, "07113", "0704",
  [{"condition": "deteriorated/leaking",
    "text_en": "Fire hose(s) found deteriorated / leaking when pressurized during testing.",
    "text_zh": "消防水带老化/加压测试时渗漏。"},
   {"condition": "coupling defective",
    "text_en": "Fire hose coupling(s) found corroded / unable to connect to hydrant.",
    "text_zh": "消防水带接头锈蚀/无法连接消防栓。"}])

d("DEF-005", "fire_safety", "fire_pump",
  ["消防泵", "应急消防泵", "消防泵故障", "消防泵无法启动"],
  "Emergency fire pump failed to start / not operational on testing.",
  "应急消防泵无法启动/测试时不能正常运行。",
  [("SOLAS", "Reg II-2/10.2.2", "Emergency fire pumps"),
   ("FSS Code", "Chapter 12", "Fixed water-based fire-fighting systems")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "high", 4, "07114", "0705")

d("DEF-006", "fire_safety", "fixed_fire_fighting",
  ["固定灭火系统", "CO2灭火", "泡沫灭火", "干粉灭火", "水喷雾", "灭火系统"],
  "Fixed fire-extinguishing installation found defective / not properly maintained.",
  "固定灭火系统故障/未正确维护保养。",
  [("SOLAS", "Reg II-2/10.4", "Fixed fire-extinguishing systems"),
   ("FSS Code", "Chapter 5", "Fixed gas fire-extinguishing systems")],
  ["all"], ["engine_room", "cargo_hold"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "high", 3, "07115", "0706",
  [{"condition": "CO2 bottles underweight",
    "text_en": "CO2 bottles for fixed fire-extinguishing system found underweight / below required charge level.",
    "text_zh": "固定CO2灭火系统钢瓶重量不足/低于要求的充装量。"},
   {"condition": "release mechanism defective",
    "text_en": "Release mechanism of fixed fire-extinguishing system found inoperable / not tested.",
    "text_zh": "固定灭火系统释放装置无法操作/未进行测试。"}])

d("DEF-007", "fire_safety", "inert_gas_system",
  ["惰性气体系统", "惰气系统", "IG系统", "惰性气体"],
  "Inert gas system found defective / not maintaining required positive pressure in cargo tanks.",
  "惰性气体系统故障/无法维持货舱内要求的正压。",
  [("SOLAS", "Reg II-2/4.5.5", "Inert gas systems"),
   ("FSS Code", "Chapter 15", "Inert gas systems")],
  ["oil_tanker", "chemical_tanker"], ["cargo_hold", "engine_room"],
  ["PSC", "FSI", "annual_survey"],
  "high", 6, "07102", "0707",
  [{"condition": "O2 content high",
    "text_en": "Inert gas system unable to maintain O2 content below 8% by volume in cargo tanks.",
    "text_zh": "惰性气体系统无法将货舱内氧含量维持在8%以下。"},
   {"condition": "deck seal defective",
    "text_en": "Inert gas system deck water seal found defective / water level not maintained.",
    "text_zh": "惰性气体系统甲板水封故障/水位未能维持。"}])

d("DEF-008", "fire_safety", "fire_damper",
  ["防火风闸", "防火阀", "风闸", "通风防火挡板"],
  "Fire damper(s) found not operational / seized in open position.",
  "防火风闸无法操作/卡在开启位置。",
  [("SOLAS", "Reg II-2/9.7", "Ventilation systems"),
   ("SOLAS", "Reg II-2/9.2.3", "Fire integrity of bulkheads and decks")],
  ["all"], ["engine_room", "accommodation"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "high", 10, "07107", "0708")

d("DEF-009", "fire_safety", "means_of_escape",
  ["逃生通道", "逃生路线", "紧急出口", "逃生梯", "安全通道堵塞"],
  "Means of escape found obstructed / not clearly marked / not readily accessible.",
  "逃生通道被堵塞/未清晰标识/无法随时通行。",
  [("SOLAS", "Reg II-2/13", "Means of escape"),
   ("FSS Code", "Chapter 11", "Fire control plans")],
  ["all"], ["engine_room", "accommodation", "deck"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "high", 9, "07118", "0709",
  [{"condition": "emergency escape locked",
    "text_en": "Emergency escape from engine room found locked / blocked, unable to open from inside.",
    "text_zh": "机舱紧急逃生通道被锁闭/堵塞，无法从内部打开。"}])

d("DEF-010", "fire_safety", "fire_control_plan",
  ["消防控制图", "防火控制图", "消防布置图"],
  "Fire control plan not posted / not up to date / not corresponding to actual arrangement on board.",
  "消防控制图未张贴/未更新/与船上实际布置不符。",
  [("SOLAS", "Reg II-2/15.2.4", "Fire control plans")],
  ["all"], ["bridge", "accommodation"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "low", 18, "07120", "0710")

d("DEF-011", "fire_safety", "exhaust_insulation",
  ["排烟管隔热", "排气管绝缘", "废气管隔热", "排烟管", "高温管路隔热"],
  "Insulation of exhaust pipe / high-temperature surface found deteriorated / missing in engine room.",
  "机舱排烟管/高温表面的隔热层老化脱落/缺失。",
  [("SOLAS", "Reg II-2/4.5", "Ignition sources"),
   ("SOLAS", "Reg II-2/5.2", "Protection of machinery spaces")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "medium", 14, "07106", "0711")

d("DEF-012", "fire_safety", "quick_closing_valve",
  ["速闭阀", "快关阀", "油柜速闭阀", "燃油速闭阀", "遥控速闭阀"],
  "Quick-closing valve(s) on fuel/oil tank(s) found not operational from remote position.",
  "燃油/滑油柜速闭阀无法从遥控位置操作。",
  [("SOLAS", "Reg II-2/4.5.7", "Fuel oil installations"),
   ("SOLAS", "Reg II-2/4.5.10", "Arrangement for oil fuel")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "high", 11, "07108", "0712")

d("DEF-013", "fire_safety", "ventilation_fire_safety",
  ["机舱通风", "通风关闭", "通风停止", "机舱风机遥控"],
  "Ventilation fan(s) for engine room unable to be stopped from remote position outside the space.",
  "机舱通风风机无法从舱外遥控位置停止。",
  [("SOLAS", "Reg II-2/9.7.5", "Ventilation stop for machinery spaces")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "high", 13, "07107", "0713")

d("DEF-014", "fire_safety", "galley_equipment",
  ["厨房灭火", "厨房灭火毯", "油烟管道", "厨房排油烟"],
  "Galley exhaust duct not fitted with grease trap / fire damper; fire blanket missing.",
  "厨房排油烟管道未安装油脂收集器/防火阀；灭火毯缺失。",
  [("SOLAS", "Reg II-2/9.7.3", "Galley ventilation ducts"),
   ("SOLAS", "Reg II-2/10.6.1", "Galley fire safety")],
  ["all"], ["accommodation"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "medium", 22, "07119", "0714")

d("DEF-015", "fire_safety", "fire_drill",
  ["消防演习", "消防训练", "应急演练", "消防演习记录"],
  "Fire drill not conducted as required / crew not familiar with duties as per muster list.",
  "未按要求进行消防演习/船员不熟悉应变部署表中的职责。",
  [("SOLAS", "Reg III/19.3", "Emergency training and drills"),
   ("ISM Code", "Section 8", "Emergency preparedness")],
  ["all"], ["all_areas"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 15, "04112", "0415")


# ============================================================
# LIFE-SAVING APPLIANCES (12 entries) DEF-016 ~ DEF-027
# Tokyo MOU: 10,263 deficiencies (2024), #2 category
# ============================================================

d("DEF-016", "life_saving", "lifeboat_general",
  ["救生艇", "救生艇状况", "救生艇维护"],
  "Lifeboat(s) found in poor condition / not properly maintained.",
  "救生艇状况不良/未正确维护保养。",
  [("SOLAS", "Reg III/20", "Operational readiness, maintenance and inspections"),
   ("LSA Code", "Chapter IV", "Survival craft")],
  ["all"], ["life_saving"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "high", 7, "11101", "1101",
  [{"condition": "engine failed to start",
    "text_en": "Lifeboat engine failed to start / not operational on testing.",
    "text_zh": "救生艇发动机无法启动/测试时不能正常运行。"},
   {"condition": "hull damage",
    "text_en": "Lifeboat hull found with cracks / holes / damage affecting watertight integrity.",
    "text_zh": "救生艇艇体发现裂缝/破洞/影响水密完整性的损坏。"}])

d("DEF-017", "life_saving", "lifeboat_launching",
  ["救生艇释放", "救生艇降放", "吊艇架", "吊艇钢丝", "艇钩释放"],
  "Lifeboat launching appliance / on-load release gear found defective / not properly maintained.",
  "救生艇降放装置/承载释放钩故障/未正确维护。",
  [("SOLAS", "Reg III/20.11", "On-load release mechanisms"),
   ("LSA Code", "Chapter VI", "Launching and embarkation appliances"),
   ("MSC.1/Circ.1206/Rev.2", "", "Measures to prevent accidents with lifeboats")],
  ["all"], ["life_saving"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "high", 6, "11103", "1102",
  [{"condition": "wire rope deteriorated",
    "text_en": "Lifeboat davit wire rope found with broken strands / corrosion beyond acceptable limits.",
    "text_zh": "吊艇架钢丝绳发现断丝/锈蚀超出允许范围。"},
   {"condition": "winch brake defective",
    "text_en": "Lifeboat winch brake found unable to hold the load / slipping.",
    "text_zh": "救生艇绞车刹车无法保持负荷/打滑。"}])

d("DEF-018", "life_saving", "liferaft_servicing",
  ["救生筏", "救生筏检验", "救生筏过期", "气胀救生筏"],
  "Inflatable liferaft(s) found with service certificate expired / not serviced at approved station.",
  "气胀式救生筏检验证书过期/未在认可的检修站进行检修。",
  [("SOLAS", "Reg III/20.8", "Periodic servicing of inflatable liferafts"),
   ("LSA Code", "Chapter VI", "Launching and embarkation appliances")],
  ["all"], ["life_saving", "deck"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "high", 12, "11108", "1103")

d("DEF-019", "life_saving", "liferaft_hydrostatic",
  ["救生筏静水压力释放", "静水压力释放器", "筏架绑扎"],
  "Hydrostatic release unit (HRU) of liferaft found expired / not properly fitted.",
  "救生筏静水压力释放器过期/未正确安装。",
  [("SOLAS", "Reg III/13.4", "Stowage of survival craft"),
   ("LSA Code", "Section 4.1.6", "Float-free arrangements")],
  ["all"], ["life_saving", "deck"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "medium", 16, "11108", "1104")

d("DEF-020", "life_saving", "rescue_boat",
  ["救助艇", "救助艇故障", "救助艇发动机"],
  "Rescue boat found not operational / engine failed to start on testing.",
  "救助艇无法使用/发动机测试时无法启动。",
  [("SOLAS", "Reg III/17.1", "Rescue boats"),
   ("LSA Code", "Chapter V", "Rescue boats")],
  ["all"], ["life_saving"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "high", 17, "11104", "1105")

d("DEF-021", "life_saving", "lifejacket",
  ["救生衣", "救生衣不足", "救生衣损坏", "救生衣灯"],
  "Lifejacket(s) found insufficient in number / not properly stowed / light not functioning.",
  "救生衣数量不足/未正确存放/救生衣灯不亮。",
  [("SOLAS", "Reg III/7.2", "Personal life-saving appliances"),
   ("LSA Code", "Section 2.2", "Lifejackets")],
  ["all"], ["accommodation", "bridge"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "medium", 19, "11109", "1106")

d("DEF-022", "life_saving", "immersion_suit",
  ["保温救生服", "浸水保温服", "保温服"],
  "Immersion suit(s) found insufficient in number / torn / not properly stowed.",
  "保温救生服数量不足/破损/未正确存放。",
  [("SOLAS", "Reg III/22.4", "Immersion suits"),
   ("LSA Code", "Section 2.3", "Immersion suits")],
  ["all"], ["accommodation"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "medium", 25, "11116", "1107")

d("DEF-023", "life_saving", "lifebuoy",
  ["救生圈", "救生圈灯", "自亮浮灯", "救生圈缺失"],
  "Lifebuoy(s) found missing / self-igniting light not functioning / self-activating smoke signal expired.",
  "救生圈缺失/自亮浮灯不亮/自动烟雾信号过期。",
  [("SOLAS", "Reg III/7.1", "Personal life-saving appliances"),
   ("LSA Code", "Section 2.1", "Lifebuoys")],
  ["all"], ["deck"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "low", 24, "11117", "1108")

d("DEF-024", "life_saving", "epirb",
  ["EPIRB", "应急示位标", "卫星示位标", "应急无线电示位标"],
  "EPIRB found not properly registered / battery expired / HRU expired / stowage improper.",
  "EPIRB未正确注册/电池过期/静水压力释放器过期/存放不当。",
  [("SOLAS", "Reg IV/7.1.6", "Radio equipment — EPIRB"),
   ("SOLAS", "Reg III/6.2.4", "Communication equipment")],
  ["all"], ["bridge", "deck"],
  ["PSC", "FSI", "radio_survey"],
  "medium", 20, "05108", "0508")

d("DEF-025", "life_saving", "sart",
  ["SART", "搜救雷达应答器", "AIS-SART"],
  "SART / AIS-SART found defective / battery expired / not tested.",
  "搜救雷达应答器(SART)/AIS-SART故障/电池过期/未测试。",
  [("SOLAS", "Reg III/6.2.2", "Radar transponder"),
   ("SOLAS", "Reg IV/7.1.3", "Radio equipment")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "radio_survey"],
  "low", 30, "05109", "0509")

d("DEF-026", "life_saving", "line_throwing",
  ["撇缆枪", "抛绳器", "抛绳设备"],
  "Line-throwing appliance found expired / not maintained / stowed improperly.",
  "抛绳设备过期/未维护/存放不当。",
  [("SOLAS", "Reg III/18", "Line-throwing appliances"),
   ("LSA Code", "Section 7.1", "Line-throwing appliances")],
  ["all"], ["bridge", "deck"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "low", 35, "11128", "1109")

d("DEF-027", "life_saving", "lsa_maintenance",
  ["救生设备维护", "救生设备保养", "救生设备检查记录"],
  "Maintenance of life-saving appliances not carried out as required / records incomplete.",
  "救生设备未按要求进行维护保养/记录不完整。",
  [("SOLAS", "Reg III/20.6", "Maintenance of life-saving appliances"),
   ("MSC.1/Circ.1206/Rev.2", "", "Measures to prevent accidents with lifeboats")],
  ["all"], ["life_saving"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "medium", 21, "11132", "1110")


# ============================================================
# SAFETY OF NAVIGATION (10 entries) DEF-028 ~ DEF-037
# Tokyo MOU: 8,066 deficiencies (2024), #4 category
# ============================================================

d("DEF-028", "navigation", "nautical_charts",
  ["海图", "海图未改正", "航海图", "电子海图", "海图过期"],
  "Nautical charts not corrected and up to date / insufficient for the intended voyage.",
  "海图未改正至最新/不能满足预定航次的需要。",
  [("SOLAS", "Reg V/19.2.1.4", "Nautical charts and nautical publications"),
   ("SOLAS", "Reg V/27", "Nautical charts and nautical publications")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 23, "10104", "1001",
  [{"condition": "no chart correction records",
    "text_en": "No records of chart corrections maintained / Notices to Mariners not received on board.",
    "text_zh": "未保存海图改正记录/船上未收到航海通告。"}])

d("DEF-029", "navigation", "ecdis",
  ["ECDIS", "电子海图显示系统", "ECDIS故障", "ECDIS未更新"],
  "ECDIS found not functioning properly / not updated / crew not trained in its use.",
  "ECDIS功能异常/未更新/船员未接受操作培训。",
  [("SOLAS", "Reg V/19.2.10", "ECDIS"),
   ("IMO Res. MSC.232(82)", "", "Performance standards for ECDIS")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 26, "10108", "1002")

d("DEF-030", "navigation", "magnetic_compass",
  ["磁罗经", "标准罗经", "罗经自差表", "罗经校正"],
  "Magnetic compass found defective / deviation card not up to date.",
  "磁罗经故障/自差表未更新。",
  [("SOLAS", "Reg V/19.2.1", "Magnetic compass"),
   ("IMO Res. A.382(X)", "", "Magnetic compass requirements")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "annual_survey"],
  "low", 32, "10101", "1003")

d("DEF-031", "navigation", "ais",
  ["AIS", "船舶自动识别系统", "AIS故障", "AIS关闭"],
  "AIS not operational / not transmitting correct data.",
  "AIS未工作/未发送正确数据。",
  [("SOLAS", "Reg V/19.2.4", "AIS"),
   ("IMO Res. A.1106(29)", "", "Performance standards for AIS")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 28, "10116", "1004")

d("DEF-032", "navigation", "vdr",
  ["VDR", "航行数据记录仪", "黑匣子", "S-VDR"],
  "VDR/S-VDR found not operational / annual performance test overdue.",
  "VDR/S-VDR未工作/年度性能测试过期。",
  [("SOLAS", "Reg V/20", "Voyage data recorders"),
   ("IMO Res. MSC.333(90)", "", "Performance standards for VDR")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 33, "10115", "1005")

d("DEF-033", "navigation", "navigation_lights",
  ["航行灯", "信号灯", "号灯", "号型"],
  "Navigation light(s) found not operational / not compliant with COLREG requirements.",
  "航行灯不工作/不符合COLREG要求。",
  [("COLREG", "Rule 20-31", "Lights and shapes"),
   ("SOLAS", "Reg V/19.2.3", "Signalling equipment")],
  ["all"], ["deck", "bridge"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 27, "10110", "1006")

d("DEF-034", "navigation", "radar",
  ["雷达", "雷达故障", "ARPA", "雷达标绘"],
  "Radar/ARPA found not operational / performance degraded.",
  "雷达/ARPA不工作/性能下降。",
  [("SOLAS", "Reg V/19.2.3", "Radar equipment"),
   ("SOLAS", "Reg V/19.2.8", "Automatic radar plotting aid (ARPA)")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "annual_survey"],
  "high", 29, "10107", "1007")

d("DEF-035", "navigation", "sound_signal",
  ["号笛", "雾号", "声号设备", "音响信号"],
  "Sound signalling equipment (whistle) found not operational / audibility insufficient.",
  "音响信号设备（号笛）不工作/可听距离不足。",
  [("COLREG", "Rule 33", "Equipment for sound signals"),
   ("SOLAS", "Reg V/19.2.1.7", "Sound reception system")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "annual_survey"],
  "low", 40, "10111", "1008")

d("DEF-036", "navigation", "pilot_transfer",
  ["引水梯", "引航梯", "引水员梯", "引航员软梯", "舷梯"],
  "Pilot transfer arrangements found not compliant / not maintained in safe condition.",
  "引航员登离船装置不符合要求/未保持安全状态。",
  [("SOLAS", "Reg V/23", "Pilot transfer arrangements"),
   ("IMO Res. A.1045(27)", "", "Pilot transfer arrangements")],
  ["all"], ["deck"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 31, "10119", "1009",
  [{"condition": "ladder defective",
    "text_en": "Pilot ladder found with broken/damaged steps / spreaders missing / side ropes deteriorated.",
    "text_zh": "引航员软梯踏板断裂/损坏/撑杆缺失/边绳老化。"}])

d("DEF-037", "navigation", "bridge_visibility",
  ["驾驶台视野", "前方视野", "盲区"],
  "Bridge visibility found obstructed / clear view not maintained in all conditions.",
  "驾驶台视野被遮挡/未能在所有条件下保持清晰视野。",
  [("SOLAS", "Reg V/22", "Visibility from the navigating bridge"),
   ("IMO Res. MSC.192(79)", "", "Bridge visibility performance standards")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "annual_survey"],
  "low", 45, "10120", "1010")


# ============================================================
# ISM CODE (5 entries) DEF-038 ~ DEF-042
# Paris MOU: ISM 4.6% of all deficiencies (2024)
# ============================================================

d("DEF-038", "ism_code", "procedures_not_followed",
  ["ISM", "安全管理体系", "SMS", "体系程序未执行"],
  "ISM Code — procedures and instructions for key shipboard operations not followed.",
  "ISM规则——船上关键操作的程序和说明未被执行。",
  [("ISM Code", "Section 7", "Development of plans for shipboard operations"),
   ("SOLAS", "Reg IX/3", "Safety management requirements")],
  ["all"], ["all_areas"],
  ["PSC", "FSI", "ISM_audit"],
  "high", 34, "15150", "1501")

d("DEF-039", "ism_code", "nonconformities",
  ["不符合项", "ISM不符合", "纠正措施", "不符合项未关闭"],
  "ISM Code — non-conformities identified but corrective actions not implemented / not effective.",
  "ISM规则——已识别的不符合项但纠正措施未实施/未见效。",
  [("ISM Code", "Section 9", "Reports and analysis of non-conformities"),
   ("ISM Code", "Section 10", "Maintenance of ship and equipment")],
  ["all"], ["all_areas"],
  ["PSC", "FSI", "ISM_audit"],
  "high", 36, "15150", "1502")

d("DEF-040", "ism_code", "documentation",
  ["SMS文件", "安全管理手册", "体系文件过期"],
  "ISM Code — SMS documentation not maintained / not reflecting actual practices on board.",
  "ISM规则——安全管理体系文件未维护/与船上实际操作不一致。",
  [("ISM Code", "Section 11", "Documentation"),
   ("ISM Code", "Section 1.4", "Functional requirements")],
  ["all"], ["all_areas"],
  ["PSC", "FSI", "ISM_audit"],
  "medium", 38, "15150", "1503")

d("DEF-041", "ism_code", "internal_audit",
  ["内部审核", "内审", "ISM审核", "公司审核"],
  "ISM Code — internal audits not carried out as required / findings not addressed.",
  "ISM规则——内部审核未按要求执行/审核发现未处理。",
  [("ISM Code", "Section 12", "Company verification, review and evaluation"),
   ("SOLAS", "Reg IX/6", "Verification and control")],
  ["all"], ["all_areas"],
  ["PSC", "FSI", "ISM_audit"],
  "medium", 42, "15150", "1504")

d("DEF-042", "ism_code", "master_authority",
  ["船长权力", "船长否决权", "船长决定权"],
  "ISM Code — master's overriding authority and responsibility not clearly defined / not implemented.",
  "ISM规则——船长的最高权力和责任未明确/未得到落实。",
  [("ISM Code", "Section 5", "Master's responsibility and authority"),
   ("SOLAS", "Reg IX/3.2", "Master's authority")],
  ["all"], ["all_areas"],
  ["PSC", "FSI", "ISM_audit"],
  "high", 43, "15150", "1505")


# ============================================================
# ISPS CODE (3 entries) DEF-043 ~ DEF-045
# ============================================================

d("DEF-043", "isps_code", "security_plan",
  ["ISPS", "船舶保安计划", "保安计划", "SSP"],
  "ISPS Code — Ship Security Plan not followed / security measures not implemented as required.",
  "ISPS规则——船舶保安计划未执行/保安措施未按要求实施。",
  [("ISPS Code", "Part A/9", "Ship security plan"),
   ("SOLAS", "Reg XI-2/4", "Requirements for ships")],
  ["all"], ["all_areas"],
  ["PSC", "ISPS_verification"],
  "high", 44, "16101", "1601")

d("DEF-044", "isps_code", "security_drills",
  ["保安演习", "保安演练", "保安训练"],
  "ISPS Code — security drills and exercises not conducted as required.",
  "ISPS规则——保安演习和训练未按要求开展。",
  [("ISPS Code", "Part A/13", "Security drills and exercises"),
   ("SOLAS", "Reg XI-2/8", "Master's discretion for ship safety and security")],
  ["all"], ["all_areas"],
  ["PSC", "ISPS_verification"],
  "medium", 50, "16105", "1602")

d("DEF-045", "isps_code", "access_control",
  ["登船控制", "出入控制", "访客管理", "舷梯值班"],
  "ISPS Code — access control to the ship not maintained / gangway watch not posted.",
  "ISPS规则——船舶出入控制未落实/舷梯无人值守。",
  [("ISPS Code", "Part A/9.4", "Access control"),
   ("SOLAS", "Reg XI-2/4", "Requirements for ships")],
  ["all"], ["deck"],
  ["PSC", "ISPS_verification"],
  "medium", 48, "16102", "1603")


# ============================================================
# CERTIFICATES & DOCUMENTATION (5 entries) DEF-046 ~ DEF-050
# ============================================================

d("DEF-046", "certificates", "safety_certificates",
  ["安全证书", "证书过期", "安全设备证书", "安全构造证书"],
  "Ship safety certificate(s) expired / not valid / not on board.",
  "船舶安全证书过期/无效/不在船上。",
  [("SOLAS", "Reg I/12", "Issue of certificates"),
   ("SOLAS", "Reg I/14", "Duration and validity of certificates")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "annual_survey"],
  "high", 37, "01101", "0101")

d("DEF-047", "certificates", "classification",
  ["船级证书", "入级证书", "船级社", "分级证书"],
  "Classification certificate expired / conditions of class not complied with.",
  "船级证书过期/船级附加条件未满足。",
  [("SOLAS", "Reg II-1/3-1", "Structural, mechanical and electrical requirements"),
   ("SOLAS", "Reg XI-1/1", "Authorization of recognized organizations")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "annual_survey"],
  "high", 39, "01102", "0102")

d("DEF-048", "certificates", "oil_record_book",
  ["油类记录簿", "ORB", "油类记录", "机舱油类记录"],
  "Oil Record Book Part I found with incomplete / incorrect entries.",
  "油类记录簿第一部分记录不完整/不正确。",
  [("MARPOL", "Annex I, Reg 17", "Oil Record Book Part I"),
   ("MARPOL", "Annex I, Reg 36", "Oil Record Book Part II (oil tankers)")],
  ["all"], ["engine_room", "bridge"],
  ["PSC", "FSI", "IOPP_survey"],
  "high", 41, "01324", "0103",
  [{"condition": "entries not corresponding to OWS operation",
    "text_en": "Oil Record Book entries not corresponding to actual OWS/bilge pump operations.",
    "text_zh": "油类记录簿记录与油水分离器/舱底泵的实际操作不符。"}])

d("DEF-049", "certificates", "cargo_securing_manual",
  ["货物系固手册", "系固手册", "绑扎手册", "CSM"],
  "Cargo Securing Manual not on board / not approved / not followed.",
  "货物系固手册不在船上/未经批准/未被遵循。",
  [("SOLAS", "Reg VI/5.6", "Cargo securing"),
   ("CSS Code", "Annex 13", "Methods to assess cargo securing")],
  ["general_cargo", "container_ship", "bulk_carrier"], ["bridge", "cargo_hold"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 46, "01331", "0104")

d("DEF-050", "certificates", "stability_information",
  ["稳性资料", "装载手册", "稳性计算书"],
  "Stability information booklet not on board / not approved / not accessible.",
  "稳性资料不在船上/未经批准/无法查阅。",
  [("SOLAS", "Reg II-1/22", "Stability information"),
   ("LL Convention", "Reg 10", "Stability information")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 47, "01319", "0105")


# ============================================================
# STRUCTURAL CONDITION (8 entries) DEF-051 ~ DEF-058
# Paris MOU: 11.3% of all deficiencies (SOLAS Ch. II-1)
# ============================================================

d("DEF-051", "structural", "hull_corrosion",
  ["船体腐蚀", "船壳锈蚀", "外板锈蚀", "船体减薄"],
  "Hull found with excessive corrosion / wastage affecting structural integrity.",
  "船体发现严重腐蚀/减薄，影响结构强度。",
  [("SOLAS", "Reg II-1/3-1", "Structural requirements"),
   ("LL Convention", "Reg 1", "Strength and intact stability")],
  ["all"], ["deck", "cargo_hold"],
  ["PSC", "FSI", "special_survey"],
  "high", 49, "02101", "0201")

d("DEF-052", "structural", "deck_corrosion",
  ["甲板锈蚀", "甲板腐蚀", "甲板开裂", "甲板变形"],
  "Deck plating found with excessive corrosion / cracks / deformation.",
  "甲板板发现严重锈蚀/裂纹/变形。",
  [("SOLAS", "Reg II-1/3-1", "Structural requirements"),
   ("LL Convention", "Reg 1", "Strength and intact stability")],
  ["all"], ["deck"],
  ["PSC", "FSI", "special_survey"],
  "high", 55, "02102", "0202")

d("DEF-053", "structural", "piping_corrosion",
  ["锈蚀", "腐蚀", "锈穿", "锈烂", "管子锈了", "管路腐蚀", "管路锈蚀"],
  "Piping in engine room found with excessive corrosion and wastage.",
  "机舱管路发现严重锈蚀及减薄。",
  [("SOLAS", "Reg II-1/3-2.2", "Corrosion prevention")],
  ["all"], ["engine_room", "cargo_hold", "ballast_tank"],
  ["PSC", "FSI", "annual_survey"],
  "high", 51, "02103", "0203",
  [{"condition": "with perforation",
    "text_en": "Piping in engine room found with severe corrosion and wastage, with localized perforation noted.",
    "text_zh": "机舱管路发现严重锈蚀及减薄，局部已穿孔。",
    "additional_refs": ["Classification Society structural survey requirements"]},
   {"condition": "temporary repair",
    "text_en": "Piping found with temporary/cement box repair on corroded section, permanent repair required.",
    "text_zh": "管路锈蚀部位使用临时/水泥箱修复，需进行永久性修理。",
    "additional_refs": ["SOLAS Reg II-1/3-2.2", "Class requirements"]}])

d("DEF-054", "structural", "ballast_tank_coating",
  ["压载舱涂层", "压载舱防腐", "涂层脱落", "压载舱锈蚀"],
  "Ballast tank protective coating found in POOR condition / extensive breakdown.",
  "压载舱保护涂层状况不良/大面积脱落。",
  [("SOLAS", "Reg II-1/3-2.2", "Corrosion prevention of seawater ballast tanks"),
   ("IMO Res. MSC.215(82)", "", "Performance standard for protective coatings")],
  ["all"], ["ballast_tank"],
  ["PSC", "FSI", "special_survey"],
  "medium", 56, "02115", "0204")

d("DEF-055", "structural", "hatch_cover",
  ["舱口盖", "舱盖", "舱口盖水密", "舱盖密封", "舱盖橡皮"],
  "Hatch cover(s) found not weathertight / sealing gaskets deteriorated / securing arrangements defective.",
  "舱口盖不能保持风雨密/密封橡皮老化/锁紧装置故障。",
  [("LL Convention", "Reg 15-16", "Hatchways closed by weathertight covers"),
   ("SOLAS", "Reg II-1/3-6.2", "Access to and within spaces in cargo area of bulk carriers")],
  ["bulk_carrier", "general_cargo"], ["cargo_hold", "deck"],
  ["PSC", "FSI", "annual_survey"],
  "high", 52, "03106", "0301",
  [{"condition": "ultrasonic test failed",
    "text_en": "Hatch covers failed ultrasonic tightness test — significant gaps found between cover and coaming.",
    "text_zh": "舱口盖超声波密性试验不合格——盖板与围板之间存在明显间隙。"},
   {"condition": "cleats/securing defective",
    "text_en": "Hatch cover cleats / cross-joint wedges found wasted / missing / not effective.",
    "text_zh": "舱口盖压紧装置/十字接缝楔块磨损/缺失/失效。"}])

d("DEF-056", "structural", "watertight_doors",
  ["水密门", "水密门故障", "水密门关闭"],
  "Watertight door(s) found not operational / unable to close properly from both local and remote positions.",
  "水密门无法操作/不能从本地和遥控位置正常关闭。",
  [("SOLAS", "Reg II-1/13", "Openings in the watertight bulkhead below the bulkhead deck"),
   ("SOLAS", "Reg II-1/22", "Information on stability for the master")],
  ["all"], ["engine_room", "cargo_hold"],
  ["PSC", "FSI", "annual_survey"],
  "high", 53, "03110", "0302")

d("DEF-057", "structural", "air_pipes_ventilators",
  ["空气管", "透气管", "通风筒", "关闭装置"],
  "Air pipe(s) / ventilator(s) closing devices found not operational / corroded / missing.",
  "空气管/通风筒关闭装置无法操作/锈蚀/缺失。",
  [("LL Convention", "Reg 19-20", "Ventilators and air pipes"),
   ("SOLAS", "Reg II-1/3-6.3", "Ventilation on bulk carriers")],
  ["all"], ["deck"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 57, "03109", "0303")

d("DEF-058", "structural", "freeboard_marks",
  ["载重线标志", "干舷标志", "载重线", "吃水标记"],
  "Freeboard marks found not clearly visible / ship loaded beyond permitted marks.",
  "载重线标志不清晰可见/船舶超载超过许可标志。",
  [("LL Convention", "Reg 5", "Freeboard marks"),
   ("LL Convention", "Reg 6", "Deck line")],
  ["all"], ["deck"],
  ["PSC", "FSI", "annual_survey"],
  "high", 58, "03101", "0304")


# ============================================================
# ENGINE ROOM / MACHINERY (12 entries) DEF-059 ~ DEF-070
# ============================================================

d("DEF-059", "machinery", "oily_water_separator",
  ["油水分离器", "OWS", "油水分离", "15ppm", "排油监控"],
  "Oily water separator found defective / unable to maintain 15ppm discharge limit.",
  "油水分离器故障/无法维持15ppm排放限值。",
  [("MARPOL", "Annex I, Reg 14", "Oil filtering equipment"),
   ("IMO Res. MEPC.107(49)", "", "OWS performance standards")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "IOPP_survey"],
  "high", 54, "14115", "1401",
  [{"condition": "bypassed",
    "text_en": "Evidence of oily water separator being bypassed — direct overboard discharge arrangement found.",
    "text_zh": "发现油水分离器被旁通的证据——存在直接舷外排放装置。"},
   {"condition": "alarm defective",
    "text_en": "Oil content meter / 15ppm bilge alarm found defective / not calibrated.",
    "text_zh": "含油量计/15ppm舱底水报警装置故障/未校准。"}])

d("DEF-060", "machinery", "odme",
  ["排油监控装置", "ODME", "排油监控"],
  "Oil discharge monitoring equipment (ODME) found defective / not operational (oil tankers).",
  "排油监控装置(ODME)故障/不能正常工作（油轮）。",
  [("MARPOL", "Annex I, Reg 31", "Oil discharge monitoring and control system"),
   ("IMO Res. MEPC.108(49)", "", "ODME performance standards")],
  ["oil_tanker"], ["engine_room", "cargo_hold"],
  ["PSC", "FSI", "IOPP_survey"],
  "high", 60, "14113", "1402")

d("DEF-061", "machinery", "emergency_generator",
  ["应急发电机", "应急电源", "应急发电机故障", "应急柴油机"],
  "Emergency generator failed to start automatically / not maintaining required capacity.",
  "应急发电机无法自动启动/无法维持要求的容量。",
  [("SOLAS", "Reg II-1/44", "Emergency source of electrical power"),
   ("SOLAS", "Reg II-1/42", "Main source of electrical power")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "high", 59, "13106", "1301",
  [{"condition": "fuel tank level low",
    "text_en": "Emergency generator fuel tank found with insufficient fuel for required running period.",
    "text_zh": "应急发电机油柜燃油量不足以维持要求的运行时间。"}])

d("DEF-062", "machinery", "steering_gear",
  ["舵机", "应急舵", "操舵装置", "舵机故障", "操舵测试"],
  "Steering gear found defective / emergency steering not tested / changeover procedure not posted.",
  "舵机故障/应急操舵未测试/转换程序未张贴。",
  [("SOLAS", "Reg V/26", "Steering gear testing and drills"),
   ("SOLAS", "Reg II-1/29", "Steering gear")],
  ["all"], ["engine_room", "bridge"],
  ["PSC", "FSI", "annual_survey"],
  "high", 61, "13101", "1302",
  [{"condition": "hydraulic leak",
    "text_en": "Steering gear hydraulic system found with significant oil leak(s) / low oil level.",
    "text_zh": "舵机液压系统发现明显漏油/油位偏低。"}])

d("DEF-063", "machinery", "bilge_pumping",
  ["舱底泵", "排水系统", "舱底排水", "应急舱底泵"],
  "Bilge pumping system found defective / bilge wells not accessible / suction strainers blocked.",
  "舱底排水系统故障/舱底污水井不可触及/吸入滤器堵塞。",
  [("SOLAS", "Reg II-1/35-1", "Bilge pumping arrangements"),
   ("LL Convention", "Reg 22", "Bilge pump arrangements")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 62, "13102", "1303")

d("DEF-064", "machinery", "main_engine_safety",
  ["主机安全装置", "主机超速保护", "主机联锁", "主机安全"],
  "Main engine safety devices (overspeed trip / low pressure alarm) found defective / not tested.",
  "主机安全装置（超速保护/低压报警）故障/未测试。",
  [("SOLAS", "Reg II-1/26.3", "Machinery in periodically unattended machinery spaces"),
   ("SOLAS", "Reg II-1/31", "Automation")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "annual_survey"],
  "high", 63, "13103", "1304")

d("DEF-065", "machinery", "auxiliary_boiler",
  ["辅助锅炉", "锅炉安全阀", "锅炉水位", "废气锅炉"],
  "Auxiliary boiler safety valve(s) found defective / water level gauge not operational / alarms not functioning.",
  "辅助锅炉安全阀故障/水位计不工作/报警装置失灵。",
  [("SOLAS", "Reg II-1/26.3", "Machinery in periodically unattended machinery spaces"),
   ("SOLAS", "Reg II-1/30", "Boiler safety")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 64, "13104", "1305")

d("DEF-066", "machinery", "electrical_insulation",
  ["电气绝缘", "绝缘电阻", "电缆老化", "电线裸露"],
  "Electrical installation(s) found with low insulation resistance / exposed wiring / deteriorated cables.",
  "电气设备绝缘电阻偏低/电线裸露/电缆老化。",
  [("SOLAS", "Reg II-1/45", "Precautions against electrical shock"),
   ("IEC 60092", "", "Electrical installations in ships")],
  ["all"], ["engine_room", "accommodation"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 65, "13110", "1306")

d("DEF-067", "machinery", "emergency_power",
  ["应急电源", "应急照明", "应急蓄电池", "应急灯"],
  "Emergency source of electrical power / emergency lighting found not operational / batteries discharged.",
  "应急电源/应急照明不工作/蓄电池放电。",
  [("SOLAS", "Reg II-1/44", "Emergency source of electrical power"),
   ("SOLAS", "Reg II-2/13.3.2.5", "Emergency lighting in means of escape")],
  ["all"], ["engine_room", "accommodation", "bridge"],
  ["PSC", "FSI", "safety_equipment_survey"],
  "medium", 66, "04103", "0403")

d("DEF-068", "machinery", "fuel_oil_system",
  ["燃油系统", "油管漏油", "燃油泄漏", "燃油管路", "高压油管"],
  "Fuel oil system found with leakage / piping not properly shielded / fire hazard identified.",
  "燃油系统渗漏/管路未正确防护/存在火灾隐患。",
  [("SOLAS", "Reg II-2/4.5.2", "Arrangement for oil fuel"),
   ("SOLAS", "Reg II-2/4.5.4", "Protection against oil fuel spray")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "annual_survey"],
  "high", 67, "13112", "1307",
  [{"condition": "high pressure pipe without double wall/shielding",
    "text_en": "High pressure fuel oil pipe(s) not fitted with double wall / spray shield as required.",
    "text_zh": "高压燃油管路未按要求安装双层壁/防喷罩。"}])

d("DEF-069", "machinery", "sewage_treatment",
  ["生活污水处理", "污水处理装置", "黑水", "生活污水"],
  "Sewage treatment plant found not operational / effluent quality not meeting discharge standards.",
  "生活污水处理装置不工作/排放水质不达标。",
  [("MARPOL", "Annex IV, Reg 9", "Sewage systems"),
   ("IMO Res. MEPC.227(64)", "", "Sewage treatment plant performance standards")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "IOPP_survey"],
  "medium", 68, "14402", "1401")

d("DEF-070", "machinery", "engine_room_cleanliness",
  ["机舱卫生", "机舱清洁", "机舱油污", "舱底油污"],
  "Engine room found in poor housekeeping condition / excessive oil accumulation in bilges.",
  "机舱卫生状况差/舱底积油过多。",
  [("SOLAS", "Reg II-2/4.5", "Ignition sources — prevention of fire"),
   ("ISM Code", "Section 10", "Maintenance of ship and equipment")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 69, "09217", "0901")


# ============================================================
# POLLUTION PREVENTION / MARPOL (10 entries) DEF-071 ~ DEF-080
# ============================================================

d("DEF-071", "pollution_prevention", "marpol_annex_i",
  ["油污防止", "含油污水", "油类排放", "IOPP"],
  "MARPOL Annex I — oil pollution prevention equipment not maintained / IOPP certificate deficiencies.",
  "MARPOL附则I——防油污设备未维护/IOPP证书存在缺陷。",
  [("MARPOL", "Annex I, Reg 14", "Oil filtering equipment"),
   ("MARPOL", "Annex I, Reg 6", "IOPP Certificate")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "IOPP_survey"],
  "high", 70, "14101", "1403")

d("DEF-072", "pollution_prevention", "sbt_cbt",
  ["SBT", "CBT", "专用压载舱", "清洁压载舱"],
  "Segregated ballast tank (SBT) / clean ballast tank (CBT) system not properly maintained (oil tankers).",
  "专用压载舱(SBT)/清洁压载舱(CBT)系统未正确维护（油轮）。",
  [("MARPOL", "Annex I, Reg 18", "Segregated ballast tanks"),
   ("MARPOL", "Annex I, Reg 19", "Double hull and double bottom requirements")],
  ["oil_tanker"], ["ballast_tank", "cargo_hold"],
  ["PSC", "FSI", "IOPP_survey"],
  "medium", 75, "14116", "1404")

d("DEF-073", "pollution_prevention", "marpol_annex_ii",
  ["NLS", "有毒液体物质", "洗舱", "化学品"],
  "MARPOL Annex II — NLS residue discharge / tank washing procedures not complied with.",
  "MARPOL附则II——有毒液体物质残余排放/洗舱程序不符合要求。",
  [("MARPOL", "Annex II, Reg 13", "Control of discharge of residues of NLS"),
   ("MARPOL", "Annex II, Reg 8", "Procedures and Arrangements Manual (P&A)")],
  ["chemical_tanker"], ["cargo_hold"],
  ["PSC", "FSI", "annual_survey"],
  "high", 76, "14201", "1405")

d("DEF-074", "pollution_prevention", "marpol_annex_iv",
  ["生活污水", "MARPOL附则IV", "污水排放"],
  "MARPOL Annex IV — sewage discharge requirements not complied with / system not operational.",
  "MARPOL附则IV——生活污水排放要求不符合/系统不工作。",
  [("MARPOL", "Annex IV, Reg 11", "Discharge of sewage"),
   ("MARPOL", "Annex IV, Reg 9", "Sewage systems")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "IOPP_survey"],
  "medium", 77, "14402", "1406")

d("DEF-075", "pollution_prevention", "garbage_management",
  ["垃圾管理", "垃圾处理", "垃圾记录簿", "MARPOL附则V"],
  "MARPOL Annex V — Garbage Management Plan not followed / Garbage Record Book incomplete.",
  "MARPOL附则V——垃圾管理计划未执行/垃圾记录簿不完整。",
  [("MARPOL", "Annex V, Reg 10", "Garbage Management Plan and Garbage Record Book"),
   ("MARPOL", "Annex V, Reg 4", "Discharge of garbage outside special areas")],
  ["all"], ["deck", "accommodation"],
  ["PSC", "FSI", "annual_survey"],
  "low", 71, "14501", "1407")

d("DEF-076", "pollution_prevention", "marpol_annex_vi_sox",
  ["硫排放", "SOx", "燃油含硫量", "脱硫塔", "低硫油"],
  "MARPOL Annex VI — fuel oil sulphur content exceeding limit / scrubber not operational.",
  "MARPOL附则VI——燃油含硫量超标/脱硫塔不工作。",
  [("MARPOL", "Annex VI, Reg 14", "Sulphur oxides (SOx) and particulate matter"),
   ("MARPOL", "Annex VI, Reg 4", "Equivalents — EGCS")],
  ["all"], ["engine_room"],
  ["PSC", "FSI", "annual_survey"],
  "high", 72, "14601", "1408")

d("DEF-077", "pollution_prevention", "fuel_changeover",
  ["换油", "燃油转换", "ECA换油", "低硫油转换"],
  "MARPOL Annex VI — fuel oil changeover procedure not properly documented / not carried out before entering ECA.",
  "MARPOL附则VI——燃油转换程序未正确记录/进入排放控制区前未完成转换。",
  [("MARPOL", "Annex VI, Reg 14.6", "Fuel oil changeover"),
   ("MARPOL", "Annex VI, Reg 18.6", "Fuel oil changeover records")],
  ["all"], ["engine_room", "bridge"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 73, "14603", "1409")

d("DEF-078", "pollution_prevention", "ballast_water",
  ["压载水管理", "BWM", "压载水处理", "压载水置换"],
  "Ballast Water Management Plan not followed / BWMS not operational / records incomplete.",
  "压载水管理计划未执行/压载水处理系统不工作/记录不完整。",
  [("BWM Convention", "Reg B-1", "Ballast Water Management Plan"),
   ("BWM Convention", "Reg D-2", "Ballast water performance standard")],
  ["all"], ["engine_room", "ballast_tank"],
  ["PSC", "FSI", "annual_survey"],
  "high", 74, "14801", "1410")

d("DEF-079", "pollution_prevention", "anti_fouling",
  ["防污底漆", "AFS", "有机锡", "TBT"],
  "Anti-fouling system not compliant / AFS Certificate or Declaration not on board.",
  "防污底系统不符合要求/AFS证书或声明不在船上。",
  [("AFS Convention", "Reg 1", "Control of anti-fouling systems"),
   ("AFS Convention", "Annex 4", "Survey and certification requirements")],
  ["all"], ["deck"],
  ["PSC", "FSI", "annual_survey"],
  "low", 78, "14701", "1411")

d("DEF-080", "pollution_prevention", "orb_part_i",
  ["油类记录簿", "ORB第一部分", "机舱操作记录"],
  "Oil Record Book Part I — entries for machinery space operations not properly maintained.",
  "油类记录簿第一部分——机器处所操作记录未正确保持。",
  [("MARPOL", "Annex I, Reg 17", "Oil Record Book Part I"),
   ("MARPOL", "Annex I, Reg 15", "Control of discharge of oil")],
  ["all"], ["engine_room", "bridge"],
  ["PSC", "FSI", "IOPP_survey"],
  "medium", 79, "01324", "0103")


# ============================================================
# RADIO COMMUNICATIONS (4 entries) DEF-081 ~ DEF-084
# ============================================================

d("DEF-081", "radio_communications", "gmdss",
  ["GMDSS", "全球海上遇险与安全系统", "海上通信设备"],
  "GMDSS equipment not operational / required sea area coverage not maintained.",
  "GMDSS设备不工作/无法覆盖要求的海区。",
  [("SOLAS", "Reg IV/7", "Radio equipment — General"),
   ("SOLAS", "Reg IV/9", "Equipment for sea areas A1 and A2")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "radio_survey"],
  "high", 80, "05101", "0501")

d("DEF-082", "radio_communications", "distress_alert",
  ["遇险报警", "DSC", "遇险频率"],
  "Distress alerting equipment found not functioning properly / DSC not tested.",
  "遇险报警设备功能异常/DSC未测试。",
  [("SOLAS", "Reg IV/6.2", "Distress alerting"),
   ("SOLAS", "Reg IV/15", "Maintenance requirements")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "radio_survey"],
  "high", 81, "05103", "0502")

d("DEF-083", "radio_communications", "radio_log",
  ["无线电日志", "通信记录", "GMDSS日志"],
  "Radio log / GMDSS log not maintained as required.",
  "无线电日志/GMDSS日志未按要求保持。",
  [("SOLAS", "Reg IV/17", "Radio records"),
   ("Radio Regulations", "Article 18", "Radio log requirements")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "radio_survey"],
  "low", 82, "05110", "0503")

d("DEF-084", "radio_communications", "radio_battery",
  ["无线电蓄电池", "通信电池", "GMDSS电池"],
  "Reserve source of energy (battery) for radio equipment found with insufficient capacity / not tested.",
  "无线电设备备用电源（蓄电池）容量不足/未测试。",
  [("SOLAS", "Reg IV/13.2", "Sources of energy"),
   ("SOLAS", "Reg IV/15.5", "Maintenance — reserve source of energy")],
  ["all"], ["bridge"],
  ["PSC", "FSI", "radio_survey"],
  "medium", 83, "05111", "0504")


# ============================================================
# WORKING & LIVING CONDITIONS / MLC (8 entries) DEF-085 ~ DEF-092
# Paris MOU: MLC Title IV 10.4% of all deficiencies (2024)
# Tokyo MOU: Working/living conditions 8,193 deficiencies (2024), #3
# ============================================================

d("DEF-085", "working_living_conditions", "hours_of_rest",
  ["休息时间", "工作时间", "疲劳", "值班安排", "休息记录"],
  "Hours of rest not complied with / records not properly maintained.",
  "休息时间不符合要求/记录未正确保持。",
  [("MLC 2006", "Reg 2.3", "Hours of work and hours of rest"),
   ("STCW", "Reg VIII/1", "Fitness for duty")],
  ["all"], ["all_areas"],
  ["PSC", "MLC_inspection"],
  "high", 84, "18202", "1801")

d("DEF-086", "working_living_conditions", "sea_employment",
  ["雇佣协议", "船员合同", "SEA", "船员雇佣"],
  "Seafarers' Employment Agreement(s) not on board / not compliant with MLC requirements.",
  "船员雇佣协议不在船上/不符合MLC要求。",
  [("MLC 2006", "Reg 2.1", "Seafarers' employment agreements"),
   ("MLC 2006", "Standard A2.1", "Seafarers' employment agreements")],
  ["all"], ["all_areas"],
  ["PSC", "MLC_inspection"],
  "high", 85, "18201", "1802")

d("DEF-087", "working_living_conditions", "sanitary_facilities",
  ["卫生设施", "厕所", "洗浴设施", "居住条件"],
  "Accommodation — sanitary facilities found in poor condition / not properly maintained.",
  "居住处所——卫生设施状况不良/未正确维护。",
  [("MLC 2006", "Reg 3.1", "Accommodation and recreational facilities"),
   ("MLC 2006", "Standard A3.1.11", "Sanitary facilities")],
  ["all"], ["accommodation"],
  ["PSC", "MLC_inspection"],
  "medium", 86, "18307", "1803")

d("DEF-088", "working_living_conditions", "food_catering",
  ["伙食", "食品", "厨房卫生", "饮用水"],
  "Food and catering — provisions insufficient / drinking water quality not tested / galley hygiene poor.",
  "伙食供应——食品不充足/饮用水水质未检测/厨房卫生差。",
  [("MLC 2006", "Reg 3.2", "Food and catering"),
   ("MLC 2006", "Standard A3.2", "Food and catering")],
  ["all"], ["accommodation"],
  ["PSC", "MLC_inspection"],
  "medium", 87, "18312", "1804")

d("DEF-089", "working_living_conditions", "medical_equipment",
  ["医疗设备", "药品箱", "医药", "急救箱", "医疗"],
  "Medical equipment / medicine chest found incomplete / medicines expired.",
  "医疗设备/药品箱不齐全/药品过期。",
  [("MLC 2006", "Reg 4.1", "Medical care on board ship and ashore"),
   ("SOLAS", "Reg IV/4.1", "Radio equipment — Medical advice")],
  ["all"], ["accommodation", "bridge"],
  ["PSC", "MLC_inspection"],
  "medium", 88, "18401", "1805")

d("DEF-090", "working_living_conditions", "safe_access",
  ["安全通道", "舷梯", "跳板", "登船通道"],
  "Safe means of access to the ship not provided / gangway/accommodation ladder not properly rigged.",
  "未提供安全的登船通道/舷梯/梯子未正确布置。",
  [("MLC 2006", "Reg 4.3.1", "Health and safety protection"),
   ("SOLAS", "Reg II-1/3-9", "Means of access")],
  ["all"], ["deck"],
  ["PSC", "MLC_inspection"],
  "medium", 89, "09219", "0902")

d("DEF-091", "working_living_conditions", "ppe",
  ["个人防护", "PPE", "安全帽", "安全鞋", "防护用品"],
  "Personal protective equipment (PPE) not available / insufficient / crew not wearing PPE.",
  "个人防护设备(PPE)不可用/不充足/船员未穿戴PPE。",
  [("MLC 2006", "Reg 4.3", "Health and safety protection and accident prevention"),
   ("ILO Code of Practice", "", "Safety and health in shipboard work")],
  ["all"], ["engine_room", "deck"],
  ["PSC", "MLC_inspection"],
  "low", 90, "09208", "0903")

d("DEF-092", "working_living_conditions", "wages",
  ["船员工资", "工资支付", "工资记录"],
  "Seafarers' wages not paid as per employment agreement / payment records not maintained.",
  "船员工资未按雇佣协议支付/工资记录未保持。",
  [("MLC 2006", "Reg 2.2", "Wages"),
   ("MLC 2006", "Standard A2.2", "Wages")],
  ["all"], ["all_areas"],
  ["PSC", "MLC_inspection"],
  "medium", 91, "18204", "1806")


# ============================================================
# CARGO OPERATIONS (5 entries) DEF-093 ~ DEF-097
# ============================================================

d("DEF-093", "cargo_operations", "cargo_securing",
  ["货物系固", "货物绑扎", "系固件", "绑扎力"],
  "Cargo securing arrangements found inadequate / lashings not properly applied.",
  "货物系固装置不足/绑扎未正确施加。",
  [("SOLAS", "Reg VI/5", "Stowage and securing"),
   ("CSS Code", "Annex 13", "Methods to assess cargo securing arrangements")],
  ["general_cargo", "container_ship"], ["cargo_hold", "deck"],
  ["PSC", "FSI", "annual_survey"],
  "high", 92, "06102", "0601")

d("DEF-094", "cargo_operations", "dangerous_goods",
  ["危险货物", "IMDG", "危险品", "危货"],
  "Dangerous goods not stowed / segregated / marked as per IMDG Code.",
  "危险货物未按IMDG规则装载/隔离/标记。",
  [("SOLAS", "Reg VII/5", "Dangerous goods in packaged form"),
   ("IMDG Code", "Part 7", "Provisions concerning transport operations")],
  ["container_ship", "general_cargo"], ["cargo_hold", "deck"],
  ["PSC", "FSI", "annual_survey"],
  "high", 93, "12101", "1201")

d("DEF-095", "cargo_operations", "loading_instrument",
  ["装载仪", "装载计算机", "装载电脑"],
  "Loading instrument (loading computer) not operational / not type-approved / not tested.",
  "装载仪（装载计算机）不工作/未经型式认可/未测试。",
  [("SOLAS", "Reg XII/11", "Loading instrument"),
   ("SOLAS", "Reg II-1/22", "Stability information for the master")],
  ["bulk_carrier"], ["bridge"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 94, "06108", "0602")

d("DEF-096", "cargo_operations", "atmosphere_testing",
  ["测氧仪", "测爆仪", "有毒气体检测", "封闭处所进入"],
  "Atmosphere testing equipment for enclosed space entry found defective / not calibrated / crew not trained.",
  "封闭处所进入用气体检测设备故障/未校准/船员未接受培训。",
  [("SOLAS", "Reg XI-1/7", "Atmosphere testing instrument for enclosed spaces"),
   ("IMO Res. A.1050(27)", "", "Recommendations for entering enclosed spaces")],
  ["all"], ["cargo_hold", "engine_room", "ballast_tank"],
  ["PSC", "FSI", "annual_survey"],
  "high", 95, "09213", "0904")

d("DEF-097", "cargo_operations", "cargo_documentation",
  ["货物资料", "货物申报", "积载图"],
  "Cargo information / documentation not available / not properly maintained.",
  "货物信息/文件不可用/未正确保持。",
  [("SOLAS", "Reg VI/2", "Cargo information"),
   ("SOLAS", "Reg VI/7.3", "Loading and unloading of bulk cargoes")],
  ["bulk_carrier", "general_cargo", "container_ship"], ["bridge", "cargo_hold"],
  ["PSC", "FSI", "annual_survey"],
  "low", 96, "06101", "0603")


# ============================================================
# SHIP-TYPE SPECIFIC (3 entries) DEF-098 ~ DEF-100
# ============================================================

d("DEF-098", "tanker_specific", "cargo_manifold",
  ["货油总管", "装卸管路", "货油管路", "歧管"],
  "Cargo manifold / piping found with leakage / not properly maintained (tankers).",
  "货油总管/管路渗漏/未正确维护（油轮）。",
  [("SOLAS", "Reg II-2/4.5.6", "Oil fuel piping and fittings"),
   ("MARPOL", "Annex I, Reg 28", "Shipboard oil pollution emergency plan")],
  ["oil_tanker", "chemical_tanker"], ["deck", "cargo_hold"],
  ["PSC", "FSI", "annual_survey"],
  "high", 97, "06109", "0604")

d("DEF-099", "tanker_specific", "pv_valves",
  ["PV阀", "压力真空阀", "透气阀", "货舱透气"],
  "Pressure/vacuum (P/V) valve(s) found defective / flame screen corroded/blocked (tankers).",
  "压力/真空阀(PV阀)故障/防火网锈蚀/堵塞（油轮）。",
  [("SOLAS", "Reg II-2/4.5.3", "Protection of cargo tanks"),
   ("SOLAS", "Reg II-2/11.6", "Cargo tank venting")],
  ["oil_tanker", "chemical_tanker"], ["deck", "cargo_hold"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 98, "06110", "0605")

d("DEF-100", "tanker_specific", "pa_manual",
  ["P&A手册", "操作手册", "程序与布置手册"],
  "Procedures and Arrangements (P&A) Manual not on board / not approved / not followed (chemical tankers).",
  "程序与布置(P&A)手册不在船上/未经批准/未遵循（化学品船）。",
  [("MARPOL", "Annex II, Reg 8", "Procedures and Arrangements Manual"),
   ("IBC Code", "Chapter 16", "Operational requirements")],
  ["chemical_tanker"], ["bridge", "cargo_hold"],
  ["PSC", "FSI", "annual_survey"],
  "medium", 99, "14208", "1406")


# ============================================================
# BUILD INDEXES
# ============================================================

by_area = {}
by_ship_type = {}
by_category = {}
chinese_keyword_map = {}

for defect in defects:
    did = defect["id"]
    # Index by area
    for area in defect["applicable_areas"]:
        by_area.setdefault(area, []).append(did)
    # Index by ship type
    for st in defect["applicable_ship_types"]:
        by_ship_type.setdefault(st, []).append(did)
    # Index by category
    cat = defect["category"]
    by_category.setdefault(cat, []).append(did)
    # Index by chinese keywords
    for trigger in defect["chinese_triggers"]:
        chinese_keyword_map.setdefault(trigger, []).append(did)

index = {
    "by_area": by_area,
    "by_ship_type": by_ship_type,
    "by_category": by_category,
    "chinese_keyword_map": chinese_keyword_map,
}

kb = {
    "version": "1.0.0",
    "updated_at": str(date.today()),
    "defect_count": len(defects),
    "defects": defects,
    "index": index,
}

out_path = "data/defect_kb.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(kb, f, ensure_ascii=False, indent=2)

print(f"Written {len(defects)} defects to {out_path}")
print(f"Categories: {list(by_category.keys())}")
print(f"Areas: {list(by_area.keys())}")
print(f"Ship types: {list(by_ship_type.keys())}")
print(f"Chinese keywords: {len(chinese_keyword_map)}")

# Validate
for defect in defects:
    assert defect["id"].startswith("DEF-"), f"Bad ID: {defect['id']}"
    assert defect["category"], f"No category: {defect['id']}"
    assert len(defect["chinese_triggers"]) >= 2, f"Need >=2 triggers: {defect['id']}"
    assert defect["standard_text_en"], f"No EN text: {defect['id']}"
    assert defect["standard_text_zh"], f"No ZH text: {defect['id']}"
    assert len(defect["regulation_refs"]) >= 1, f"No refs: {defect['id']}"
print("All validations passed!")
