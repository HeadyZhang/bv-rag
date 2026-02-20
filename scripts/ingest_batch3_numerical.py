"""Ingest batch-3 curated chunks — high-value numerical regulation data.

Covers 8 regulation areas with critical decision-making numbers that
surveyors frequently query.

Usage:
    python -m scripts.ingest_batch3_numerical
"""
import logging
import sys

import openai
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from config.settings import settings
from db.postgres import PostgresDB

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CURATED_BATCH3_DATA = [
    # ================================================================
    # Chunk 1: SOLAS III/32 — Personal life-saving appliances
    # ================================================================
    {
        "id": "solas-iii-reg32-personal-lsa",
        "source": "SOLAS III",
        "document": "SOLAS",
        "chapter": "III",
        "regulation": "SOLAS III/32",
        "title": "SOLAS III/32 – Personal life-saving appliances: lifebuoys, lifejackets, immersion suits",
        "breadcrumb": "SOLAS > Chapter III > Regulation 32 > Personal LSA",
        "body_text": (
            "SOLAS Chapter III, Regulation 32 – Personal Life-Saving Appliances\n\n"
            "LIFEBUOY REQUIREMENTS:\n"
            "| Ship Type | Minimum Number of Lifebuoys |\n"
            "|-----------|---------------------------|\n"
            "| Cargo ship < 100m | 8 |\n"
            "| Cargo ship 100-150m | 10 |\n"
            "| Cargo ship 150-200m | 12 |\n"
            "| Cargo ship >= 200m | 14 |\n"
            "| Passenger ship | Based on ship length (up to 30) |\n\n"
            "Lifebuoy accessories:\n"
            "- At least HALF fitted with self-igniting lights\n"
            "- At least 2 fitted with self-activating smoke signals (buoyant)\n"
            "- At least 2 with buoyant lifelines (≥30m)\n"
            "- Distributed on BOTH sides of the ship\n\n"
            "LIFEJACKET REQUIREMENTS:\n"
            "- One lifejacket for EACH person on board\n"
            "- Additional 10% of total (for watchkeeping positions)\n"
            "- Child lifejackets: sufficient for number of children on board\n"
            "- Lifejackets at muster stations, watchkeeping positions, and remote stations\n\n"
            "IMMERSION SUIT / THERMAL PROTECTIVE AID:\n"
            "- One immersion suit for EACH person assigned to rescue boat crew\n"
            "- One immersion suit for EACH person on board (cargo ships)\n"
            "  OR thermal protective aids for persons in survival craft not in immersion suits\n"
            "- Passenger ships: sufficient for all persons on watch + those not in survival craft\n\n"
            "ROCKET PARACHUTE FLARES:\n"
            "- Cargo ships: at least 12 rocket parachute flares on the navigation bridge\n"
            "- Passenger ships: at least 12 rocket parachute flares\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Ensures personal survival equipment for every person on board "
            "in case of abandon ship or man overboard\n"
            "- Survey points: (1) Count lifebuoys vs ship length table; (2) Check self-igniting "
            "lights on at least half; (3) Verify lifejacket count ≥ persons + 10%; (4) Immersion "
            "suits condition and expiry; (5) Rocket flares expiry date (max 3 years)\n"
            "- Typical scenario: Annual survey — surveyor counts 7 lifebuoys on a 120m cargo ship. "
            "Minimum is 10. Deficiency issued."
        ),
        "metadata_extra": {
            "topic": "life_saving",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "SOLAS III", "Regulation 32", "SOLAS III/32", "lifebuoy", "lifejacket",
            "immersion suit", "thermal protective aid", "rocket parachute flare",
            "personal life-saving", "self-igniting light", "smoke signal",
        ],
        "keywords_zh": [
            "救生圈", "救生衣", "浸水服", "保温用具", "火箭降落伞信号", "自亮灯",
            "自发烟雾信号", "儿童救生衣", "救生设备数量", "个人救生设备",
        ],
    },
    # ================================================================
    # Chunk 2: SOLAS V/19 — Navigation equipment carriage requirements
    # ================================================================
    {
        "id": "solas-v-reg19-navigation-equipment",
        "source": "SOLAS V",
        "document": "SOLAS",
        "chapter": "V",
        "regulation": "SOLAS V/19",
        "title": "SOLAS V/19 – Carriage requirements for shipborne navigational systems and equipment",
        "breadcrumb": "SOLAS > Chapter V > Regulation 19 > Navigation equipment",
        "body_text": (
            "SOLAS Chapter V, Regulation 19 – Carriage Requirements for Shipborne "
            "Navigational Systems and Equipment\n\n"
            "EQUIPMENT CARRIAGE TABLE:\n"
            "| Equipment | Ship Applicability |\n"
            "|-----------|-------------------|\n"
            "| Magnetic compass (or equivalent) | All ships |\n"
            "| Gyro compass + repeaters | ≥ 500 GT |\n"
            "| Gyro heading indicator (THD) | ≥ 500 GT |\n"
            "| Echo-sounding device | ≥ 300 GT |\n"
            "| Speed and distance measuring device | ≥ 300 GT (through water); ≥ 50,000 GT (over ground) |\n"
            "| Radar 9 GHz | ≥ 300 GT |\n"
            "| Radar 3 GHz (second radar) | ≥ 3,000 GT |\n"
            "| ARPA (with one radar) | ≥ 10,000 GT |\n"
            "| AIS (Automatic Identification System) | ≥ 300 GT international; ≥ 500 GT non-international |\n"
            "| LRIT | All SOLAS ships |\n"
            "| VDR (Voyage Data Recorder) | All passenger ships; cargo ships ≥ 3,000 GT (new) |\n"
            "| S-VDR (Simplified VDR) | Existing cargo ships ≥ 3,000 GT |\n"
            "| ECDIS (Electronic Chart Display) | Phased implementation by ship type and build date |\n"
            "| BNWAS (Bridge Navigational Watch Alarm) | All ships ≥ 150 GT |\n\n"
            "ECDIS PHASED IMPLEMENTATION:\n"
            "| Ship Type | New ships from | Existing ships by |\n"
            "|-----------|---------------|------------------|\n"
            "| Passenger ships | 1 Jul 2012 | 1 Jul 2014 – 1 Jul 2018 |\n"
            "| Tankers ≥ 3,000 GT | 1 Jul 2012 | 1 Jul 2015 – 1 Jul 2018 |\n"
            "| Cargo ships ≥ 10,000 GT | 1 Jul 2013 | 1 Jul 2016 – 1 Jul 2018 |\n"
            "| Cargo ships 3,000-10,000 GT | 1 Jul 2014 | 1 Jul 2017 – 1 Jul 2018 |\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Ensures adequate navigation equipment for safe passage\n"
            "- Survey points: (1) AIS operational and transmitting correct data; (2) VDR/S-VDR "
            "annual performance test by approved service provider; (3) ECDIS chart database "
            "updated; (4) Gyro error log maintained; (5) BNWAS tested during survey\n"
            "- Typical scenario: PSC inspects 2,500 GT cargo ship — requires 9 GHz radar, "
            "echo sounder, AIS, magnetic compass, gyro. If gyro compass not fitted (≥500 GT "
            "requirement), deficiency."
        ),
        "metadata_extra": {
            "topic": "navigation",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "SOLAS V", "Regulation 19", "SOLAS V/19", "navigation equipment",
            "AIS", "ECDIS", "VDR", "S-VDR", "radar", "gyro compass",
            "echo sounder", "LRIT", "BNWAS", "carriage requirements",
        ],
        "keywords_zh": [
            "航行设备", "自动识别系统", "电子海图", "航行数据记录仪",
            "回声测深仪", "测速仪", "陀螺罗经", "磁罗经", "船载航行设备配备",
        ],
    },
    # ================================================================
    # Chunk 3: SOLAS II-1/29 — Steering gear
    # ================================================================
    {
        "id": "solas-ii1-reg29-steering-gear",
        "source": "SOLAS II-1",
        "document": "SOLAS",
        "chapter": "II-1",
        "regulation": "SOLAS II-1/29",
        "title": "SOLAS II-1/29 – Steering gear: main and auxiliary requirements",
        "breadcrumb": "SOLAS > Chapter II-1 > Regulation 29 > Steering gear",
        "body_text": (
            "SOLAS Chapter II-1, Regulation 29 – Steering Gear\n\n"
            "MAIN STEERING GEAR REQUIREMENTS:\n"
            "| Parameter | Requirement |\n"
            "|-----------|------------|\n"
            "| Rudder angle range | 35° one side to 35° other side |\n"
            "| Speed requirement | 35° to 30° opposite side in ≤ 28 seconds |\n"
            "| Operating condition | Maximum ahead service speed, deepest seagoing draught |\n"
            "| Power units | Two or more where practicable |\n\n"
            "AUXILIARY STEERING GEAR REQUIREMENTS:\n"
            "| Parameter | Requirement |\n"
            "|-----------|------------|\n"
            "| Rudder angle range | 15° one side to 15° other side |\n"
            "| Time requirement | Must achieve this within 60 seconds |\n"
            "| Operating condition | Maximum ahead service speed or 7 knots (whichever greater) |\n\n"
            "TANKER-SPECIFIC REQUIREMENTS (≥ 10,000 GT):\n"
            "- Main steering gear: TWO independent power actuating systems\n"
            "- Each system capable of independently operating the rudder\n"
            "- Single failure in one system shall not render the other inoperable\n"
            "- Applies to: oil tankers, chemical tankers, gas carriers ≥ 10,000 GT\n\n"
            "EMERGENCY STEERING:\n"
            "- Means to steer the ship from a position in the steering gear compartment\n"
            "- Communication between navigation bridge and steering gear compartment required\n"
            "- Emergency power supply: within 45 seconds of main power failure\n\n"
            "TESTING REQUIREMENTS:\n"
            "- Steering gear drills: at least once every 3 months\n"
            "- Full movement test: port to starboard and back\n"
            "- Emergency steering transfer test\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Ensures ship can maintain steerage in all conditions\n"
            "- Survey points: (1) Measure 35°-to-30° time (≤28s for main); (2) Check "
            "hydraulic oil level and condition; (3) Test auxiliary/emergency steering changeover; "
            "(4) Verify tanker dual power unit independence; (5) Review drill log\n"
            "- Typical scenario: On a 15,000 GT oil tanker, surveyor tests steering gear. "
            "Only one power unit operational — second unit pump seized. Critical deficiency."
        ),
        "metadata_extra": {
            "topic": "machinery",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "SOLAS II-1", "Regulation 29", "SOLAS II-1/29", "steering gear",
            "rudder", "main steering", "auxiliary steering", "28 seconds",
            "35 degrees", "15 degrees", "60 seconds", "tanker steering",
            "power actuating system", "emergency steering",
        ],
        "keywords_zh": [
            "舵机", "主舵机", "辅助舵机", "应急舵机", "操舵装置",
            "舵角", "35度", "28秒", "转舵时间", "独立动力系统",
        ],
    },
    # ================================================================
    # Chunk 4: SOLAS II-2/7 — Fire detection systems
    # ================================================================
    {
        "id": "solas-ii2-reg7-fire-detection",
        "source": "SOLAS II-2/7",
        "document": "SOLAS",
        "chapter": "II-2",
        "regulation": "SOLAS II-2/7",
        "title": "SOLAS II-2/7 – Fire detection and alarm systems (with FSS Code Ch.9 spacing)",
        "breadcrumb": "SOLAS > Chapter II-2 > Regulation 7 > Fire detection and alarm",
        "body_text": (
            "SOLAS Chapter II-2, Regulation 7 – Detection and Alarm\n\n"
            "FIRE DETECTION SYSTEM REQUIREMENTS:\n"
            "- Fixed fire detection and alarm system required in:\n"
            "  * All accommodation and service spaces\n"
            "  * All control stations\n"
            "  * Machinery spaces of Category A\n"
            "  * Cargo pump rooms on tankers\n\n"
            "DETECTOR SPACING (FSS Code Chapter 9):\n"
            "| Detector Type | Maximum Coverage Area | Maximum Spacing |\n"
            "|--------------|---------------------|-----------------|\n"
            "| Smoke detector | 37 m² per detector | ~6.1m between detectors |\n"
            "| Heat detector | 37 m² per detector | ~6.1m between detectors |\n"
            "| Corridor detectors | N/A | ≤ 11m apart |\n"
            "| Distance from bulkhead | ≤ half the spacing | ~3m from any bulkhead |\n\n"
            "ALARM AND INDICATION REQUIREMENTS:\n"
            "| Requirement | Detail |\n"
            "|------------|--------|\n"
            "| Alarm confirmation time | Within 2 minutes of any detector activation |\n"
            "| Indication location | Navigation bridge (continuously manned) |\n"
            "| Zone identification | Each zone separately identified at panel |\n"
            "| Manual call points | At least 1 per deck at escape routes |\n"
            "| Audible alarm | Throughout accommodation/service/control spaces |\n\n"
            "FIRE PATROL vs DETECTION:\n"
            "- Passenger ships may use fire patrols in lieu of fixed detection in some areas\n"
            "- But machinery spaces of Category A always require fixed detection\n"
            "- Cargo ships: fixed detection system is the standard requirement\n\n"
            "SAMPLE EXTRACTION SYSTEMS:\n"
            "- Permitted as alternative to individual point detectors\n"
            "- Suction pipes must extract samples from each protected space\n"
            "- Response time: smoke detected within 2 minutes of entering suction pipe\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Early fire detection to enable quick response and evacuation\n"
            "- Survey points: (1) Test each zone — activation → bridge indication within 2 min; "
            "(2) Check detector spacing ≤ 37 m² per detector; (3) Corridor detectors ≤ 11m apart; "
            "(4) Manual call points at each escape route per deck; (5) Audible alarm test\n"
            "- Typical scenario: Surveyor tests fire detection panel. Zone 3 (accommodation) "
            "activated but no bridge alarm within 2 minutes — wiring fault. Deficiency."
        ),
        "metadata_extra": {
            "topic": "fire_protection",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "SOLAS II-2/7", "fire detection", "fire alarm", "smoke detector",
            "heat detector", "detector spacing", "37 square metres", "11 metres",
            "manual call point", "FSS Code Chapter 9", "sample extraction",
            "2 minutes", "fire patrol",
        ],
        "keywords_zh": [
            "火灾探测", "烟感探测器", "温感探测器", "探测器间距",
            "手动报警按钮", "报警确认时间", "火灾报警系统", "探火系统",
        ],
    },
    # ================================================================
    # Chunk 5: MARPOL Annex I/15 — Bilge water discharge
    # ================================================================
    {
        "id": "marpol-annexi-reg15-bilge-water",
        "source": "MARPOL Annex I",
        "document": "MARPOL",
        "chapter": "Annex I",
        "regulation": "MARPOL Annex I Regulation 15",
        "title": "MARPOL Annex I Reg.15 – Bilge water and oily mixture discharge from machinery spaces",
        "breadcrumb": "MARPOL > Annex I > Regulation 15 > Bilge water discharge",
        "body_text": (
            "MARPOL Annex I, Regulation 15 – Control of Discharge of Oil from "
            "Machinery Spaces of All Ships\n\n"
            "APPLICABILITY: Ships of 400 gross tonnage and above (all types, not just tankers)\n\n"
            "DISCHARGE CONDITIONS:\n"
            "| Condition | Requirement |\n"
            "|-----------|------------|\n"
            "| Oil content of effluent | ≤ 15 ppm (through OWS/filtering equipment) |\n"
            "| Ship status | Ship is en route (proceeding) |\n"
            "| Equipment | Oil filtering equipment with 15 ppm alarm and automatic stop |\n"
            "| Not in special area | See special area restrictions below |\n\n"
            "OWS (OILY WATER SEPARATOR) REQUIREMENTS:\n"
            "- Ships of 400 GT and above: OWS or oil filtering equipment required\n"
            "- Ships of 10,000 GT and above: oil filtering equipment with oil content meter "
            "and automatic stopping device\n"
            "- Must achieve effluent oil content ≤ 15 ppm\n"
            "- Alarm at 15 ppm; automatic stop of discharge\n\n"
            "SPECIAL AREAS (more restrictive):\n"
            "- Mediterranean Sea, Baltic Sea, Black Sea, Red Sea, Gulf area, "
            "Antarctic area, North-West European Waters, Oman Sea\n"
            "- In special areas: same 15 ppm requirement applies, plus stricter "
            "recordkeeping\n\n"
            "OIL RECORD BOOK (PART I — Machinery space operations):\n"
            "- Required for all ships ≥ 400 GT\n"
            "- Records: ballasting/cleaning of fuel tanks, discharge of dirty ballast, "
            "disposal of residues, discharge overboard of bilge water\n"
            "- Retained on board for 3 years\n\n"
            "IMPORTANT DISTINCTION:\n"
            "- Reg.15: Machinery space bilge water (ALL ships ≥ 400 GT) — 15 ppm limit\n"
            "- Reg.34: Cargo area oil tanker discharge — 1/30,000 limit, ODME required\n"
            "DO NOT confuse these two entirely different discharge regimes.\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Prevents oil pollution from engine room bilge water\n"
            "- Survey points: (1) OWS test run — verify 15 ppm alarm triggers; (2) Oil content "
            "meter calibration; (3) Automatic stopping device test; (4) Oil Record Book Part I "
            "properly completed; (5) No illegal bypass piping (check in bilge area)\n"
            "- Typical scenario: PSC inspection — officer tests OWS, measures 22 ppm in "
            "effluent. Equipment deficient. Also checks piping for illegal '3-way valve' bypass."
        ),
        "metadata_extra": {
            "topic": "pollution_prevention",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "MARPOL Annex I", "Regulation 15", "bilge water", "oily water separator",
            "OWS", "15 ppm", "oil filtering equipment", "oil content meter",
            "Oil Record Book", "machinery space", "special area",
        ],
        "keywords_zh": [
            "舱底水", "机舱舱底水", "油水分离器", "含油污水",
            "15ppm", "油类记录簿", "机舱油污水排放", "含油舱底水",
        ],
    },
    # ================================================================
    # Chunk 6: MARPOL Annex IV/11 — Sewage discharge
    # ================================================================
    {
        "id": "marpol-annexiv-reg11-sewage",
        "source": "MARPOL Annex IV",
        "document": "MARPOL",
        "chapter": "Annex IV",
        "regulation": "MARPOL Annex IV Regulation 11",
        "title": "MARPOL Annex IV Reg.11 – Sewage discharge requirements",
        "breadcrumb": "MARPOL > Annex IV > Regulation 11 > Sewage discharge",
        "body_text": (
            "MARPOL Annex IV, Regulation 11 – Discharge of Sewage\n\n"
            "APPLICABILITY:\n"
            "- Ships of 400 GT and above\n"
            "- Ships less than 400 GT certified to carry more than 15 persons\n\n"
            "EQUIPMENT OPTIONS:\n"
            "| Option | Equipment |\n"
            "|--------|----------|\n"
            "| Treatment | Approved sewage treatment plant (STP) |\n"
            "| Comminution/disinfection | Comminuting and disinfecting system |\n"
            "| Holding tank | Adequate capacity for all persons on board |\n\n"
            "DISCHARGE CONDITIONS:\n"
            "| Sewage Type | Condition |\n"
            "|-------------|----------|\n"
            "| Treated (approved STP) | May discharge anywhere (effluent must meet standards) |\n"
            "| Comminuted/disinfected | Distance from nearest land > 3 nautical miles |\n"
            "| Untreated sewage | Distance from nearest land > 12 nautical miles |\n"
            "| Untreated discharge rate | Ship speed > 4 knots, discharge rate approved |\n"
            "| All discharges | Ship is en route, not causing visible floating solids |\n\n"
            "BALTIC SEA SPECIAL AREA (MEPC.275(69)):\n"
            "- Passenger ships in the Baltic Sea: more restrictive from 2021\n"
            "- New passenger ships (keel laid from 1 Jun 2021): must have approved STP "
            "or holding tank with adequate port reception\n"
            "- Existing passenger ships: comply by 1 Jun 2023\n"
            "- Nutrient removal (nitrogen/phosphorus) required for STP effluent in Baltic\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Prevents sewage pollution of the marine environment\n"
            "- Survey points: (1) STP type-approval certificate valid; (2) Test STP operation "
            "and effluent quality; (3) Holding tank capacity adequate; (4) Check discharge "
            "piping — no direct overboard bypass; (5) Shore connection flange fitted\n"
            "- Typical scenario: Ship in port — sewage treatment plant not operational. Must "
            "use holding tank and discharge to port reception facility. If holding tank also "
            "deficient, deficiency raised."
        ),
        "metadata_extra": {
            "topic": "pollution_prevention",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "MARPOL Annex IV", "Regulation 11", "sewage", "sewage treatment plant",
            "STP", "comminuting", "disinfecting", "holding tank", "12 nautical miles",
            "3 nautical miles", "4 knots", "Baltic Sea",
        ],
        "keywords_zh": [
            "生活污水", "污水处理装置", "污水排放", "黑水",
            "灰水", "12海里", "4节", "波罗的海特殊区域",
        ],
    },
    # ================================================================
    # Chunk 7: MARPOL Annex V/4 — Garbage discharge
    # ================================================================
    {
        "id": "marpol-annexv-reg4-garbage",
        "source": "MARPOL Annex V",
        "document": "MARPOL",
        "chapter": "Annex V",
        "regulation": "MARPOL Annex V Regulation 4",
        "title": "MARPOL Annex V Reg.4 – Garbage discharge restrictions",
        "breadcrumb": "MARPOL > Annex V > Regulation 4 > Garbage discharge",
        "body_text": (
            "MARPOL Annex V, Regulation 4 – Discharge of Garbage Outside Special Areas\n\n"
            "FUNDAMENTAL PROHIBITION:\n"
            "ALL discharge of garbage into the sea is PROHIBITED except as permitted below.\n"
            "PLASTICS: Absolutely prohibited — NO discharge into the sea under any circumstances.\n\n"
            "PERMITTED DISCHARGES (outside special areas):\n"
            "| Garbage Category | Minimum Distance from Land |\n"
            "|-----------------|-------------------------|\n"
            "| Food waste (comminuted, < 25mm) | > 3 nautical miles |\n"
            "| Food waste (not comminuted) | > 12 nautical miles |\n"
            "| Cargo residues (non-HME*) | > 12 nautical miles |\n"
            "| Animal carcasses | As far as possible, max depth area |\n"
            "| Cleaning agents/additives | Not harmful to marine environment |\n"
            "| ALL OTHER garbage | Discharge to port reception facilities |\n\n"
            "* HME = Harmful to the Marine Environment (as classified in IMSBC/IMDG Code)\n\n"
            "SPECIAL AREAS (stricter requirements):\n"
            "- Mediterranean, Baltic, Black Sea, Red Sea, Gulf area, North Sea, "
            "Antarctic, Wider Caribbean, South Africa\n"
            "- In special areas: ONLY food waste may be discharged (> 12 nm from land, comminuted)\n"
            "- NO cargo residues in special areas\n\n"
            "GARBAGE RECORD BOOK:\n"
            "- Required for: all ships ≥ 400 GT or certified for ≥ 15 persons\n"
            "- Records: each discharge to sea, to port reception, or incineration\n"
            "- Retained for 2 years from last entry\n\n"
            "GARBAGE MANAGEMENT PLAN:\n"
            "- Required for all ships ≥ 100 GT and all fixed/floating platforms\n"
            "- Must include: collection, storage, processing, disposal procedures\n"
            "- Posted in working language of crew + English/French/Spanish\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Prevents marine pollution from ship-generated garbage\n"
            "- Survey points: (1) Garbage Management Plan posted; (2) Garbage Record Book "
            "up to date; (3) Segregation bins provided; (4) Placards displayed in mess "
            "areas; (5) No plastic discharge evidence\n"
            "- Typical scenario: PSC checks Garbage Record Book — finds no entries for 3 weeks "
            "despite vessel at sea. Suggests garbage dumped without recording. Investigation "
            "and possible detention."
        ),
        "metadata_extra": {
            "topic": "pollution_prevention",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "MARPOL Annex V", "Regulation 4", "garbage", "garbage discharge",
            "plastic", "food waste", "cargo residue", "special area",
            "garbage record book", "garbage management plan", "12 nautical miles",
            "3 nautical miles", "comminuted",
        ],
        "keywords_zh": [
            "垃圾排放", "垃圾管理计划", "垃圾记录簿",
            "食物废弃物", "塑料禁排", "货物残余", "特殊区域",
        ],
    },
    # ================================================================
    # Chunk 8: SOLAS II-1/22 — Watertight doors
    # ================================================================
    {
        "id": "solas-ii1-reg22-watertight-doors",
        "source": "SOLAS II-1",
        "document": "SOLAS",
        "chapter": "II-1",
        "regulation": "SOLAS II-1/22",
        "title": "SOLAS II-1/22 – Watertight doors: types, operation, testing requirements",
        "breadcrumb": "SOLAS > Chapter II-1 > Regulation 22 > Watertight doors",
        "body_text": (
            "SOLAS Chapter II-1, Regulation 22 – Openings in Watertight Bulkheads and "
            "Internal Decks in Cargo Ships\n\n"
            "WATERTIGHT DOOR TYPES:\n"
            "| Type | Operation | Typical Location |\n"
            "|------|-----------|----------------|\n"
            "| Class 1 — Hinged | Manual only | Spaces not normally accessed at sea |\n"
            "| Class 2 — Sliding (manual) | Manual sliding | Cargo ships, limited access |\n"
            "| Class 3 — Sliding (power) | Power + manual, remote from bridge | Frequently used passages |\n\n"
            "CLOSURE TIME REQUIREMENTS:\n"
            "| Parameter | Requirement |\n"
            "|-----------|------------|\n"
            "| Power-operated sliding doors | Close in ≤ 40 seconds |\n"
            "| Under 60 second water head pressure | Must remain closed and watertight |\n"
            "| Central closing system | Close ALL power-operated doors from bridge |\n"
            "| Sequential closing | Doors close sequentially, not simultaneously |\n\n"
            "BRIDGE INDICATION AND CONTROL:\n"
            "- Open/closed status indicator for EACH watertight door on the navigation bridge\n"
            "- Audible alarm sounds at the door location for at least 5 seconds before closing\n"
            "- Central operating console on the bridge with individual and group controls\n\n"
            "OPERATING REQUIREMENTS:\n"
            "- During navigation: watertight doors kept CLOSED (except for passage)\n"
            "- When open for operational necessity: ready for immediate closure\n"
            "- Local manual operation: operable from both sides of the bulkhead\n\n"
            "TESTING REQUIREMENTS:\n"
            "| Test | Frequency |\n"
            "|------|----------|\n"
            "| Operation test (each door) | Weekly |\n"
            "| Central closing test (from bridge) | Weekly |\n"
            "| Full operation test during drills | Every 3 months (at least) |\n"
            "| Indicator and alarm test | With each operation test |\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Maintains watertight integrity to prevent progressive flooding\n"
            "- Survey points: (1) Close ALL doors from bridge — time each (≤40s); (2) Check "
            "bridge indicators match actual door state; (3) Test local manual operation from "
            "both sides; (4) Verify audible alarm sounds ≥5 seconds; (5) Review weekly test log\n"
            "- Typical scenario: Annual survey — surveyor operates central closing from bridge. "
            "Door #3 in engine room does not close (hydraulic leak). Critical deficiency — "
            "affects subdivision integrity."
        ),
        "metadata_extra": {
            "topic": "structure_subdivision",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "SOLAS II-1/22", "watertight door", "watertight bulkhead",
            "sliding door", "power operated", "40 seconds", "bridge indicator",
            "central closing", "manual operation", "weekly test",
            "subdivision", "progressive flooding",
        ],
        "keywords_zh": [
            "水密门", "水密舱壁", "水密开口", "滑动水密门",
            "远程关闭", "40秒", "驾驶室指示器", "水密完整性",
        ],
    },
]


def _build_regulation_row(entry: dict) -> dict:
    """Build a dict matching the regulations table schema."""
    return {
        "doc_id": entry["id"],
        "url": "",
        "title": entry["title"],
        "breadcrumb": entry["breadcrumb"],
        "collection": "imo_regulations",
        "document": entry["document"],
        "chapter": entry["chapter"],
        "part": "",
        "regulation": entry["regulation"],
        "paragraph": "",
        "body_text": entry["body_text"],
        "page_type": "curated",
        "version": "curated-v1",
    }


def _build_chunk_row(entry: dict) -> dict:
    """Build a dict matching the chunks table schema."""
    keywords_en = entry.get("keywords_en", [])
    keywords_zh = entry.get("keywords_zh", [])
    prefix = entry.get("embedding_prefix", "")
    text_for_embedding = (
        f"{prefix}\n\n" if prefix else ""
    ) + (
        f"{entry['title']}\n\n{entry['body_text']}\n\n"
        f"Keywords: {' '.join(keywords_en)} {' '.join(keywords_zh)}"
    )
    metadata = {
        "title": entry["title"],
        "breadcrumb": entry["breadcrumb"],
        "collection": "imo_regulations",
        "document": entry["document"],
        "regulation_number": entry["regulation"],
        "url": "",
    }
    metadata.update(entry.get("metadata_extra", {}))
    return {
        "chunk_id": f"chunk-{entry['id']}",
        "doc_id": entry["id"],
        "url": "",
        "text": entry["body_text"],
        "text_for_embedding": text_for_embedding,
        "metadata": metadata,
        "token_count": len(text_for_embedding) // 4,
    }


def ingest_to_postgres(db: PostgresDB):
    """Insert curated batch-3 data into PostgreSQL."""
    logger.info("Ingesting batch-3 curated chunks to PostgreSQL...")
    for entry in CURATED_BATCH3_DATA:
        reg = _build_regulation_row(entry)
        db.insert_regulation(reg)
        chunk = _build_chunk_row(entry)
        db.insert_chunk(chunk)
        logger.info(f"  PG: {entry['id']}")
    db.conn.commit()
    logger.info(
        f"PostgreSQL: {len(CURATED_BATCH3_DATA)} regulations + chunks inserted"
    )


def ingest_to_qdrant():
    """Embed curated batch-3 data and upsert into Qdrant."""
    logger.info("Ingesting batch-3 curated chunks to Qdrant...")
    client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60,
    )
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    collection = "imo_regulations"
    if not client.collection_exists(collection):
        logger.error(f"Collection '{collection}' does not exist in Qdrant")
        sys.exit(1)

    base_id = 70000  # batch-3 offset

    points = []
    for i, entry in enumerate(CURATED_BATCH3_DATA):
        chunk = _build_chunk_row(entry)
        text = chunk["text_for_embedding"]

        response = oai.embeddings.create(
            model=settings.embedding_model,
            input=[text],
            dimensions=settings.embedding_dimensions,
        )
        vector = response.data[0].embedding

        payload = {**chunk["metadata"]}
        payload["chunk_id"] = chunk["chunk_id"]
        payload["doc_id"] = chunk["doc_id"]
        payload["text"] = chunk["text"]
        payload["text_for_embedding"] = chunk["text_for_embedding"]
        payload["token_count"] = chunk["token_count"]

        points.append(PointStruct(
            id=base_id + i,
            vector=vector,
            payload=payload,
        ))
        logger.info(f"  Qdrant: embedded {entry['id']} ({len(vector)} dims)")

    client.upsert(collection_name=collection, points=points)
    logger.info(f"Qdrant: {len(points)} curated batch-3 points upserted")


def verify_postgres(db: PostgresDB):
    """Verify batch-3 chunks exist in PostgreSQL."""
    expected_ids = [e["id"] for e in CURATED_BATCH3_DATA]
    cur = db.conn.cursor()
    placeholders = ",".join(["%s"] * len(expected_ids))
    cur.execute(
        f"SELECT doc_id FROM regulations WHERE doc_id IN ({placeholders})",
        expected_ids,
    )
    found = {r[0] for r in cur.fetchall()}
    logger.info("\n=== PostgreSQL Verification ===")
    for doc_id in expected_ids:
        status = "OK" if doc_id in found else "MISSING"
        logger.info(f"  {status}: {doc_id}")
    logger.info(f"PostgreSQL: {len(found)}/{len(expected_ids)} found")
    return len(found) == len(expected_ids)


def verify_qdrant_search():
    """Run vector search tests to confirm retrieval quality."""
    logger.info("\n=== Qdrant Vector Search Verification ===")
    client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60,
    )
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    test_queries = [
        # EN + ZH pairs for each chunk
        ("cargo ship lifebuoy lifejacket number requirement SOLAS", "solas-iii-reg32-personal-lsa"),
        ("货船救生圈救生衣数量要求", "solas-iii-reg32-personal-lsa"),
        ("ECDIS AIS VDR carriage requirements SOLAS V", "solas-v-reg19-navigation-equipment"),
        ("电子海图 AIS VDR 配备要求", "solas-v-reg19-navigation-equipment"),
        ("steering gear rudder angle time requirement SOLAS", "solas-ii1-reg29-steering-gear"),
        ("舵机转舵角度时间要求", "solas-ii1-reg29-steering-gear"),
        ("fire detector smoke detector spacing FSS Code", "solas-ii2-reg7-fire-detection"),
        ("烟感探测器间距要求", "solas-ii2-reg7-fire-detection"),
        ("bilge water oily water separator 15 ppm MARPOL", "marpol-annexi-reg15-bilge-water"),
        ("舱底水油水分离器排放限制", "marpol-annexi-reg15-bilge-water"),
        ("sewage discharge 12 nautical miles MARPOL Annex IV", "marpol-annexiv-reg11-sewage"),
        ("生活污水排放距离要求", "marpol-annexiv-reg11-sewage"),
        ("garbage disposal plastic prohibition MARPOL Annex V", "marpol-annexv-reg4-garbage"),
        ("垃圾排放塑料禁止排海", "marpol-annexv-reg4-garbage"),
        ("watertight door closure time requirement SOLAS", "solas-ii1-reg22-watertight-doors"),
        ("水密门关闭时间要求", "solas-ii1-reg22-watertight-doors"),
    ]

    all_pass = True
    for query, expected_doc_id in test_queries:
        resp = oai.embeddings.create(
            model=settings.embedding_model,
            input=[query],
            dimensions=settings.embedding_dimensions,
        )
        vec = resp.data[0].embedding
        results = client.query_points(
            collection_name="imo_regulations",
            query=vec,
            limit=3,
            with_payload=["doc_id"],
        )
        top3_ids = [r.payload.get("doc_id", "") for r in results.points]
        hit = expected_doc_id in top3_ids
        rank = top3_ids.index(expected_doc_id) + 1 if hit else "-"
        score = next(
            (r.score for r in results.points if r.payload.get("doc_id") == expected_doc_id),
            0,
        )
        status = "PASS" if hit else "FAIL"
        if not hit:
            all_pass = False
        logger.info(
            f"  {status}: \"{query[:50]}\" -> rank={rank}, score={score:.4f}"
        )
        if not hit:
            logger.info(f"         top-3: {top3_ids}")

    logger.info(f"\nVector search: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    return all_pass


def main():
    logger.info("=== Curated Batch-3 Numerical Chunks Ingestion ===\n")

    db = PostgresDB(settings.database_url)
    try:
        ingest_to_postgres(db)
        pg_ok = verify_postgres(db)
    finally:
        db.close()

    ingest_to_qdrant()
    qdrant_ok = verify_qdrant_search()

    if pg_ok and qdrant_ok:
        logger.info("\nAll verifications PASSED.")
    else:
        logger.warning("\nSome verifications FAILED — check output above.")


if __name__ == "__main__":
    main()
