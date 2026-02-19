"""Ingest batch-2 curated chunks — fixing 6 audit misses.

Fixes:
  #6  ODME oil discharge (MARPOL Annex I Reg.34)
  #7  Liferaft davit (SOLAS III/31)
  #8  A/B-class fire division definitions (SOLAS II-2/3)
  #12 NOx emission tiers (MARPOL Annex VI Reg.13)
  #13 SOx / ECA sulphur limits (MARPOL Annex VI Reg.14)
  #20 Firefighting systems (SOLAS II-2/10)

Usage:
    python -m scripts.ingest_batch2_audit_fixes
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

CURATED_BATCH2_DATA = [
    # ================================================================
    # Chunk 1: MARPOL Annex I Reg.34 — ODME (fix #6)
    # ================================================================
    {
        "id": "marpol-annexi-reg34-odme",
        "source": "MARPOL Annex I",
        "document": "MARPOL",
        "chapter": "Annex I",
        "regulation": "MARPOL Annex I Regulation 34",
        "title": "MARPOL Annex I Reg.34 – Oil Discharge Monitoring and Control (ODME) system",
        "breadcrumb": "MARPOL > Annex I > Regulation 34 > ODME",
        "body_text": (
            "MARPOL Annex I – Regulations for the Prevention of Pollution by Oil\n"
            "Regulation 34 – Oil Discharge Monitoring and Control System and "
            "Oily-Water Separating and Oil Filtering Equipment\n\n"
            "APPLICABILITY:\n"
            "- Oil tankers of 150 gross tonnage and above\n"
            "- Ships other than oil tankers of 400 gross tonnage and above\n\n"
            "OIL TANKER DISCHARGE LIMITS (Regulation 34.1 + Regulation 29):\n"
            "| Parameter | Requirement | Reference |\n"
            "|-----------|------------|----------|\n"
            "| Instantaneous rate of discharge | Not exceeding 30 litres per nautical mile | MARPOL Annex I Reg.29 |\n"
            "| Total quantity per voyage | Not exceeding 1/30,000 of total cargo capacity | MARPOL Annex I Reg.29 |\n"
            "| Discharge location | More than 50 nautical miles from nearest land | MARPOL Annex I Reg.29 |\n"
            "| Ship underway | Ship must be en route (proceeding) | MARPOL Annex I Reg.29 |\n"
            "| ODME system | Must be in operation during discharge | MARPOL Annex I Reg.34 |\n\n"
            'THE "1/30,000" RULE:\n'
            "The total quantity of oil discharged into the sea during a ballast voyage must not "
            "exceed 1/30,000 of the total quantity of the particular cargo of which the residue "
            "formed a part.\n"
            "Example: A tanker with 100,000 m\u00b3 cargo capacity may discharge at most "
            "100,000 / 30,000 = 3.33 m\u00b3 of oil during the entire ballast voyage.\n\n"
            "ODME SYSTEM REQUIREMENTS:\n"
            "- Continuously monitors and records oil content of effluent\n"
            "- Automatically stops discharge when oil content exceeds permitted level\n"
            "- Must be approved by the Administration (type-approved)\n"
            "- Connected to automatic stopping device for overboard discharge\n\n"
            "NON-OIL-TANKER REQUIREMENTS (Regulation 34.2 + Regulation 15):\n"
            "| Parameter | Requirement |\n"
            "|-----------|------------|\n"
            "| Oily water separator | Must achieve < 15 ppm oil content in effluent |\n"
            "| Oil filtering equipment | Required for ships of 10,000 GT and above |\n"
            "| Oil content meter | Required with automatic stopping device |\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Prevents oil pollution of the sea during tanker ballast voyages "
            "and normal ship operations\n"
            "- Survey points: (1) ODME type-approval certificate valid; (2) Test automatic "
            "stopping function; (3) Oil Record Book entries correct; (4) Check Oil Discharge "
            "Monitoring Equipment (ODME) calibration date; (5) For non-tankers: test oily water "
            "separator, verify < 15 ppm\n"
            "- Typical scenario: PSC inspector reviews Oil Record Book on a tanker and compares "
            "ODME recordings against logged discharge quantities. If cumulative discharge exceeds "
            "1/30,000 of cargo capacity, this is a MARPOL violation.\n\n"
            "COMMON ERROR: Confusing tanker discharge limits (1/30,000 of cargo capacity) with "
            "non-tanker limits (< 15 ppm oil content). They are different requirements under "
            "different regulations."
        ),
        "metadata_extra": {
            "topic": "pollution_prevention",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "MARPOL Annex I", "Regulation 34", "Regulation 29", "ODME",
            "oil discharge monitoring", "1/30000", "30 litres per nautical mile",
            "oil content", "oily water separator", "15 ppm", "Oil Record Book",
            "oil tanker", "discharge limit",
        ],
        "keywords_zh": [
            "油污染", "排油监控", "油水分离器", "油类记录簿", "油轮", "排放限制",
        ],
    },
    # ================================================================
    # Chunk 2: SOLAS III/31 — Liferaft davit (fix #7)
    # ================================================================
    {
        "id": "solas-iii-reg31-liferaft-davit",
        "source": "SOLAS III",
        "document": "SOLAS",
        "chapter": "III",
        "regulation": "SOLAS III/31",
        "title": "SOLAS III/31 – Cargo ship lifeboat and liferaft requirements including davit-launched liferafts",
        "breadcrumb": "SOLAS > Chapter III > Regulation 31 > Cargo ship survival craft",
        "body_text": (
            "SOLAS Chapter III – Life-Saving Appliances and Arrangements\n"
            "Regulation 31 – Survival craft and rescue boats (Cargo ships)\n\n"
            "CARGO SHIP LIFEBOAT/LIFERAFT REQUIREMENTS:\n\n"
            "1. Lifeboat requirement:\n"
            "- Cargo ships shall carry one or more lifeboats on EACH SIDE capable of "
            "accommodating total number of persons on board\n"
            "- OR a free-fall lifeboat at the stern capable of accommodating total persons\n\n"
            "2. DAVIT-LAUNCHED LIFERAFT requirement (SOLAS III/31.1.4):\n"
            "In ADDITION to lifeboats, cargo ships must carry:\n"
            "- At least ONE davit-launched liferaft on at least one side\n"
            "- This is in addition to the liferafts required by regulation 31.1.3\n\n"
            "WHY DAVIT-LAUNCHED?\n"
            "- A davit-launched liferaft can be lowered with people already inside "
            "(unlike throw-over rafts)\n"
            "- Required for situations where the ship's list prevents launching lifeboats "
            "on one side\n"
            "- Ensures at least one means of evacuation by davit is available\n\n"
            "LIFERAFT QUANTITIES (SOLAS III/31.1.3):\n"
            "| Ship Type | Requirement |\n"
            "|-----------|------------|\n"
            "| Cargo ship with lifeboats on each side | Liferafts for 100% of persons on board |\n"
            "| Cargo ship with free-fall lifeboat only | Additional liferafts for 100% on each side |\n"
            "| All cargo ships | At least 1 davit-launched liferaft |\n\n"
            "RELATED: LSA Code Chapter IV specifies technical requirements for liferafts "
            "(capacity, equipment, survival pack contents).\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Ensures redundant evacuation capability even when ship is "
            "listing heavily\n"
            "- Survey points: (1) At least one davit-launched liferaft present; (2) Davit "
            "annual load test; (3) Liferaft hydrostatic release unit (HRU) within service "
            "date; (4) Liferaft service station certificate (serviced within 12 months)\n"
            "- Typical scenario: Surveyor checks a cargo ship with free-fall lifeboat at "
            "stern. Must also verify davit-launched liferaft is fitted — if missing, this "
            "is a SOLAS deficiency."
        ),
        "metadata_extra": {
            "topic": "life_saving",
            "ship_type": "cargo_ship",
            "curated": True,
        },
        "keywords_en": [
            "SOLAS III", "Regulation 31", "SOLAS III/31", "lifeboat", "liferaft",
            "davit", "davit-launched", "cargo ship", "free-fall lifeboat",
            "survival craft", "rescue boat", "LSA Code", "life-saving",
        ],
        "keywords_zh": [
            "救生艇", "救生筏", "吊架", "货船", "自由降落救生艇", "救生设备",
        ],
    },
    # ================================================================
    # Chunk 3: SOLAS II-2/3 — A/B-class fire division definitions (fix #8)
    # ================================================================
    {
        "id": "solas-ii2-reg3-fire-division-definitions",
        "source": "SOLAS II-2/3",
        "document": "SOLAS",
        "chapter": "II-2",
        "regulation": "SOLAS II-2/3",
        "title": "SOLAS II-2/3 – Definitions: A-class, B-class and C-class fire divisions",
        "breadcrumb": "SOLAS > Chapter II-2 > Regulation 3 > Fire division definitions",
        "body_text": (
            "SOLAS Chapter II-2, Regulation 3 – Definitions\n\n"
            '3.2 "A" CLASS DIVISIONS:\n'
            "Bulkheads and decks which comply with ALL of the following:\n"
            "1. Constructed of STEEL or other equivalent material\n"
            "2. Suitably stiffened\n"
            "3. Capable of preventing passage of smoke and flame to the END of the "
            "one-hour standard fire test\n"
            "4. Insulated with approved non-combustible materials such that:\n\n"
            "| Division | Max temp rise on unexposed side |\n"
            "|----------|-------------------------------|\n"
            "| A-60 | Average \u2264 140\u00b0C, any point \u2264 180\u00b0C after 60 minutes |\n"
            "| A-30 | Average \u2264 140\u00b0C, any point \u2264 180\u00b0C after 30 minutes |\n"
            "| A-15 | Average \u2264 140\u00b0C, any point \u2264 180\u00b0C after 15 minutes |\n"
            "| A-0 | Average \u2264 140\u00b0C, any point \u2264 180\u00b0C after 0 minutes "
            "(i.e., steel with no insulation requirement) |\n\n"
            "NOTE: ALL A-class divisions must be steel and prevent smoke/flame for 60 minutes. "
            "The number (0/15/30/60) indicates when the TEMPERATURE limit must be met.\n\n"
            '3.4 "B" CLASS DIVISIONS:\n'
            "Bulkheads, decks, ceilings or linings which comply with ALL of the following:\n"
            "1. Constructed of approved non-combustible materials\n"
            "2. Capable of preventing passage of flame to the END of the first half hour "
            "of the standard fire test\n"
            "3. Insulation value such that:\n\n"
            "| Division | Max temp rise on unexposed side |\n"
            "|----------|-------------------------------|\n"
            "| B-15 | Average \u2264 140\u00b0C, any point \u2264 225\u00b0C after 15 minutes |\n"
            "| B-0 | Average \u2264 140\u00b0C, any point \u2264 225\u00b0C after 0 minutes |\n\n"
            "NOTE: B-class need NOT be steel — approved non-combustible materials suffice. "
            "Flame integrity is 30 minutes (vs 60 for A-class).\n\n"
            '3.10 "C" CLASS DIVISIONS:\n'
            "Constructed of approved non-combustible materials. No requirements for smoke, "
            "flame, or temperature rise.\n\n"
            "KEY DIFFERENCES SUMMARY:\n"
            "| Feature | A-class | B-class | C-class |\n"
            "|---------|---------|---------|--------|\n"
            "| Material | Steel or equivalent | Non-combustible | Non-combustible |\n"
            "| Flame integrity | 60 minutes | 30 minutes | None |\n"
            "| Smoke integrity | 60 minutes | 30 minutes | None |\n"
            "| Temperature limit | Yes (varies by rating) | Yes (varies by rating) | None |\n"
            "| Typical use | Main fire zone boundaries, stairway enclosures, machinery spaces "
            "| Cabin partitions, corridor boundaries | Minor partitions |\n\n"
            '"STEEL OR OTHER EQUIVALENT MATERIAL" (Reg.3.43):\n'
            "A material which by itself or due to insulation provided is not combustible, and "
            "has structural integrity and fire integrity at least equal to steel at the end of "
            "the applicable exposure to the standard fire test.\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Creates fire zones that limit fire spread and protect escape routes\n"
            "- Survey points: (1) Check material certificates match required division class; "
            "(2) Verify insulation type and thickness; (3) Inspect penetrations (pipes, cables, "
            "ducts) — each must maintain the division's integrity; (4) Fire doors must be "
            "self-closing and match the surrounding division class\n"
            "- Typical scenario: Surveyor inspects machinery space boundary. Division is marked "
            "as A-60. Checks: steel construction, insulation, cable transit sealed, fire door "
            "self-closing. If a cable penetration is unsealed, the A-60 integrity is compromised "
            "— deficiency."
        ),
        "metadata_extra": {
            "topic": "fire_protection",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "SOLAS II-2/3", "A-class", "B-class", "C-class", "A-60", "A-30",
            "A-15", "A-0", "B-15", "B-0", "fire division", "fire integrity",
            "bulkhead", "deck", "steel", "non-combustible", "standard fire test",
            "insulation", "140 degrees", "180 degrees", "fire zone", "definition",
        ],
        "keywords_zh": [
            "防火分隔", "A级", "B级", "C级", "钢质", "不燃材料",
            "标准耐火试验", "隔热", "防火定义",
        ],
    },
    # ================================================================
    # Chunk 4: MARPOL Annex VI Reg.13 — NOx tiers (fix #12)
    # ================================================================
    {
        "id": "marpol-annexvi-reg13-nox-tiers",
        "source": "MARPOL Annex VI",
        "document": "MARPOL",
        "chapter": "Annex VI",
        "regulation": "MARPOL Annex VI Regulation 13",
        "title": "MARPOL Annex VI Reg.13 – NOx emission limits (Tier I/II/III)",
        "breadcrumb": "MARPOL > Annex VI > Regulation 13 > NOx",
        "body_text": (
            "MARPOL Annex VI – Prevention of Air Pollution from Ships\n"
            "Regulation 13 – Nitrogen Oxides (NOx)\n\n"
            "APPLICABILITY:\n"
            "Applies to each marine diesel engine with power output > 130 kW installed on a ship.\n"
            "Does NOT apply to emergency engines used solely during emergencies.\n\n"
            "NOx EMISSION LIMITS — Three tiers based on ship construction date:\n\n"
            "| Tier | Ship Construction Date | n < 130 rpm | 130 \u2264 n < 2000 rpm | n \u2265 2000 rpm |\n"
            "|------|----------------------|-------------|-------------------|-------------|\n"
            "| Tier I | 1 Jan 2000 – 31 Dec 2010 | 17.0 g/kWh | 45 \u00d7 n^(-0.2) g/kWh | 9.8 g/kWh |\n"
            "| Tier II | 1 Jan 2011 onwards | 14.4 g/kWh | 44 \u00d7 n^(-0.23) g/kWh | 7.7 g/kWh |\n"
            "| Tier III | 1 Jan 2016 onwards (ECA only) | 3.4 g/kWh | 9 \u00d7 n^(-0.2) g/kWh | 2.0 g/kWh |\n\n"
            "CRITICAL NOTES:\n"
            "1. Tier III applies ONLY when operating in a NOx Emission Control Area (ECA)\n"
            "2. Outside ECA, Tier II applies (for post-2011 ships)\n"
            "3. NOx ECAs currently designated: North American ECA, US Caribbean Sea ECA, "
            "Baltic Sea and North Sea (from 2021)\n"
            "4. EIAPP Certificate (Engine International Air Pollution Prevention) required for "
            "each engine\n\n"
            "COMPLIANCE METHODS for Tier III:\n"
            "- Selective Catalytic Reduction (SCR)\n"
            "- Exhaust Gas Recirculation (EGR)\n"
            "- LNG or other gas fuels (inherently low-NOx)\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Reduces NOx emissions that cause acid rain and respiratory illness\n"
            "- Survey points: (1) EIAPP certificate valid and matches engine; (2) NOx Technical "
            "File on board; (3) For Tier III: SCR/EGR operational and maintenance records current; "
            "(4) Engine parameters within Technical File limits\n"
            "- Typical scenario: 2020-built cargo ship enters North American ECA. Must meet "
            "Tier III (e.g., 3.4 g/kWh at low speed). If SCR system fails, ship must repair "
            "or avoid ECA."
        ),
        "metadata_extra": {
            "topic": "air_pollution",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "MARPOL Annex VI", "Regulation 13", "NOx", "nitrogen oxides",
            "Tier I", "Tier II", "Tier III", "ECA", "emission control area",
            "EIAPP", "SCR", "EGR", "marine diesel engine", "g/kWh",
        ],
        "keywords_zh": [
            "氮氧化物", "排放", "排放控制区", "排放等级",
        ],
    },
    # ================================================================
    # Chunk 5: MARPOL Annex VI Reg.14 — SOx / sulphur (fix #13)
    # ================================================================
    {
        "id": "marpol-annexvi-reg14-sox-sulphur",
        "source": "MARPOL Annex VI",
        "document": "MARPOL",
        "chapter": "Annex VI",
        "regulation": "MARPOL Annex VI Regulation 14",
        "title": "MARPOL Annex VI Reg.14 – Sulphur content of fuel oil (SOx) and emission control areas",
        "breadcrumb": "MARPOL > Annex VI > Regulation 14 > SOx / Sulphur",
        "body_text": (
            "MARPOL Annex VI – Prevention of Air Pollution from Ships\n"
            "Regulation 14 – Sulphur Oxides (SOx) and Particulate Matter\n\n"
            "SULPHUR CONTENT LIMITS:\n\n"
            "| Date | Global Limit | ECA/SECA Limit |\n"
            "|------|-------------|---------------|\n"
            "| Before 1 Jan 2012 | 4.50% m/m | 1.50% m/m |\n"
            "| 1 Jan 2012 – 31 Dec 2019 | 3.50% m/m | 1.00% (2012-2014), 0.10% (from 2015) |\n"
            "| 1 Jan 2020 onwards | 0.50% m/m | 0.10% m/m |\n\n"
            "CURRENT LIMITS (IMO 2020):\n"
            "- GLOBAL: 0.50% sulphur by mass (the 'IMO 2020' rule)\n"
            "- INSIDE ECA/SECA: 0.10% sulphur by mass\n\n"
            "SULPHUR EMISSION CONTROL AREAS (SECAs):\n"
            "1. Baltic Sea area\n"
            "2. North Sea area (including English Channel)\n"
            "3. North American ECA (200 nautical miles from US/Canada coast)\n"
            "4. United States Caribbean Sea ECA\n\n"
            "COMPLIANCE OPTIONS:\n"
            "| Method | Description |\n"
            "|--------|------------|\n"
            "| Low-sulphur fuel (VLSFO) | Use fuel with \u2264 0.50% (global) or \u2264 0.10% (ECA) sulphur |\n"
            "| Scrubber (EGCS) | Exhaust gas cleaning system — can use high-sulphur fuel |\n"
            "| Alternative fuels (LNG, methanol) | Must achieve equivalent SOx reduction |\n\n"
            "FUEL OIL DOCUMENTATION:\n"
            "- Bunker Delivery Note (BDN): must state sulphur content — retained 3 years\n"
            "- MARPOL representative sample: sealed by supplier — retained 12 months\n"
            "- Fuel changeover procedure must be documented when entering/leaving ECA\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Reduces SOx emissions causing acid rain and respiratory disease\n"
            "- Survey points: (1) BDN sulphur content \u2264 0.50% (or \u2264 0.10% in ECA); "
            "(2) MARPOL sample sealed and labelled; (3) If scrubber: washwater monitoring "
            "records; (4) Fuel changeover log when entering ECA\n"
            "- Typical scenario: Ship approaches Baltic Sea SECA burning 0.50% VLSFO. Must "
            "switch to 0.10% fuel before entering SECA boundary. Changeover time and tank "
            "levels logged."
        ),
        "metadata_extra": {
            "topic": "air_pollution",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "MARPOL Annex VI", "Regulation 14", "SOx", "sulphur", "sulfur",
            "fuel oil", "0.50", "0.10", "ECA", "SECA", "emission control area",
            "scrubber", "EGCS", "IMO 2020", "VLSFO", "BDN", "bunker delivery note",
        ],
        "keywords_zh": [
            "硫氧化物", "硫含量", "排放控制区", "低硫燃油", "洗涤器",
        ],
    },
    # ================================================================
    # Chunk 6: SOLAS II-2/10 — Firefighting (fix #20)
    # ================================================================
    {
        "id": "solas-ii2-reg10-firefighting-overview",
        "source": "SOLAS II-2/10",
        "document": "SOLAS",
        "chapter": "II-2",
        "regulation": "SOLAS II-2/10",
        "title": "SOLAS II-2/10 – Firefighting: fire mains, extinguishers, fixed CO2 and foam systems",
        "breadcrumb": "SOLAS > Chapter II-2 > Regulation 10 > Firefighting",
        "body_text": (
            "SOLAS Chapter II-2, Regulation 10 – Firefighting\n\n"
            "Regulation 10 covers ALL firefighting equipment and systems.\n\n"
            "KEY SUB-SECTIONS:\n"
            "| Section | Topic | Key Requirement |\n"
            "|---------|-------|----------------|\n"
            "| 10.2 | Fire main and hydrants | At least 2 fire pumps; pressure 0.27 MPa "
            "(passenger) / 0.25 MPa (cargo) at most remote hydrant |\n"
            "| 10.3 | Portable fire extinguishers | At least 5 in accommodation/service "
            "spaces (cargo ships) |\n"
            "| 10.4 | Fixed fire-extinguishing systems (general) | Required in machinery "
            "spaces, cargo pump rooms, cargo holds |\n"
            "| 10.5 | Fixed gas (CO2) systems | CO2 volume \u2265 40% of largest machinery "
            "space; 85% released within 2 minutes |\n"
            "| 10.6 | Fixed foam systems | For machinery spaces and helicopter facilities |\n"
            "| 10.7 | Fixed pressure water-spraying | For machinery spaces |\n"
            "| 10.8 | Automatic sprinkler systems | Required in passenger ship accommodation "
            "and service spaces |\n"
            "| 10.9 | Fixed fire detection | Required in machinery spaces of Category A |\n"
            "| 10.10 | Fireman's outfit | At least 2 sets (cargo ships), 4+ sets "
            "(passenger ships) |\n\n"
            "FIXED CO2 SYSTEM REQUIREMENTS (10.5 + FSS Code Ch.5):\n"
            "- Machinery spaces: free gas volume \u2265 40% of gross volume (or 35% including casing)\n"
            "- 85% of required quantity discharged within 2 minutes\n"
            "- Audible alarm MUST sound BEFORE CO2 release in any manned space\n"
            "- Time delay between alarm and release: sufficient for crew evacuation\n"
            "- Two independent means of control (in and outside the protected space)\n\n"
            "FIRE MAIN REQUIREMENTS (10.2):\n"
            "- At least 2 fire pumps (not counting the emergency fire pump)\n"
            "- International shore connection: standard flange for port fire brigade connection\n"
            "- Fire hoses: sufficient length to reach any part of each space\n\n"
            "PORTABLE EXTINGUISHER TYPES:\n"
            "| Type | Suitable For |\n"
            "|------|-------------|\n"
            "| Foam / Water spray | Class A (solid materials) |\n"
            "| CO2 | Class B (liquids), Class C (electrical) |\n"
            "| Dry chemical | Class B and C |\n"
            "| Foam (AFFF) | Class A and B |\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Provides layered fire suppression from portable to fixed systems\n"
            "- Survey points: (1) Fire pump test: measure pressure at most remote hydrant "
            "(\u2265 0.25 MPa cargo); (2) CO2 bottles: check weight/pressure records; (3) CO2 "
            "alarm test: audible throughout protected space; (4) Extinguisher inspection dates "
            "within 12 months; (5) International shore connection accessible\n"
            "- Typical scenario: Annual survey — surveyor tests fire pump and measures 0.22 MPa "
            "at most remote hydrant (below 0.25 MPa minimum). Deficiency — pump or piping "
            "needs repair before certificate renewal."
        ),
        "metadata_extra": {
            "topic": "fire_protection",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "SOLAS II-2/10", "firefighting", "fire main", "fire pump", "hydrant",
            "fire extinguisher", "CO2", "carbon dioxide", "foam", "sprinkler",
            "water spray", "fixed fire extinguishing", "FSS Code", "0.25 MPa",
            "40 percent", "fireman outfit", "international shore connection",
        ],
        "keywords_zh": [
            "灭火", "消防总管", "消防泵", "消火栓", "灭火器",
            "二氧化碳", "泡沫", "喷淋", "固定灭火系统",
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
    text_for_embedding = (
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
    """Insert curated batch-2 data into PostgreSQL."""
    logger.info("Ingesting batch-2 curated chunks to PostgreSQL...")
    for entry in CURATED_BATCH2_DATA:
        reg = _build_regulation_row(entry)
        db.insert_regulation(reg)
        chunk = _build_chunk_row(entry)
        db.insert_chunk(chunk)
        logger.info(f"  PG: {entry['id']}")
    db.conn.commit()
    logger.info(
        f"PostgreSQL: {len(CURATED_BATCH2_DATA)} regulations + chunks inserted"
    )


def ingest_to_qdrant():
    """Embed curated batch-2 data and upsert into Qdrant."""
    logger.info("Ingesting batch-2 curated chunks to Qdrant...")
    client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60,
    )
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    collection = "imo_regulations"
    if not client.collection_exists(collection):
        logger.error(f"Collection '{collection}' does not exist in Qdrant")
        sys.exit(1)

    info = client.get_collection(collection)
    base_id = (info.points_count or 0) + 50000  # offset to avoid collisions

    points = []
    for i, entry in enumerate(CURATED_BATCH2_DATA):
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
    logger.info(f"Qdrant: {len(points)} curated batch-2 points upserted")


def verify_postgres(db: PostgresDB):
    """Verify batch-2 chunks exist in PostgreSQL."""
    expected_ids = [e["id"] for e in CURATED_BATCH2_DATA]
    cur = db.conn.cursor()
    placeholders = ",".join(["%s"] * len(expected_ids))
    cur.execute(
        f"SELECT doc_id FROM regulations WHERE doc_id IN ({placeholders})",
        expected_ids,
    )
    found = {r[0] for r in cur.fetchall()}
    logger.info(f"\n=== PostgreSQL Verification ===")
    for doc_id in expected_ids:
        status = "OK" if doc_id in found else "MISSING"
        logger.info(f"  {status}: {doc_id}")
    logger.info(f"PostgreSQL: {len(found)}/{len(expected_ids)} found")
    return len(found) == len(expected_ids)


def verify_qdrant_search():
    """Run 6 vector search tests to confirm retrieval quality."""
    logger.info("\n=== Qdrant Vector Search Verification ===")
    client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60,
    )
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    test_queries = [
        ("MARPOL Annex I ODME oil discharge 1/30000", "marpol-annexi-reg34-odme"),
        ("cargo ship liferaft davit requirement SOLAS", "solas-iii-reg31-liferaft-davit"),
        ("A-class A-60 fire division definition SOLAS", "solas-ii2-reg3-fire-division-definitions"),
        ("NOx emission tier MARPOL Annex VI", "marpol-annexvi-reg13-nox-tiers"),
        ("sulphur content ECA SECA MARPOL", "marpol-annexvi-reg14-sox-sulphur"),
        ("CO2 fire extinguishing system SOLAS", "solas-ii2-reg10-firefighting-overview"),
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
    logger.info("=== Curated Batch-2 Audit Fixes Ingestion ===\n")

    # Ingest
    db = PostgresDB(settings.database_url)
    try:
        ingest_to_postgres(db)
        pg_ok = verify_postgres(db)
    finally:
        db.close()

    ingest_to_qdrant()

    # Verify
    qdrant_ok = verify_qdrant_search()

    if pg_ok and qdrant_ok:
        logger.info("\nAll verifications PASSED.")
    else:
        logger.warning("\nSome verifications FAILED — check output above.")


if __name__ == "__main__":
    main()
