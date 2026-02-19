"""Ingest curated SOLAS II-2/11 (tanker cargo tank protection) chunks.

Hand-crafted high-quality chunks for SOLAS Regulation 11 special requirements
for ships carrying dangerous goods — especially cargo tank pressure/vacuum
protection (Section 11.6) which was previously a retrieval failure.

Usage:
    python -m scripts.ingest_solas_ii2_reg11
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

CURATED_SOLAS_II2_REG11_DATA = [
    # === Chunk 1: SOLAS II-2/11.6 Cargo tank protection (core fix) ===
    {
        "id": "solas-ii2-reg11.6-cargo-tank-protection",
        "source": "SOLAS II-2/11",
        "document": "SOLAS",
        "chapter": "II-2",
        "regulation": "SOLAS II-2/11.6",
        "title": "Cargo tank protection – Pressure/vacuum relief and alarms for tankers",
        "breadcrumb": "SOLAS > Chapter II-2 > Regulation 11 > 11.6 Cargo tank protection",
        "body_text": (
            "SOLAS Chapter II-2, Regulation 11 – Special requirements for ships carrying dangerous goods\n"
            "Section 11.6 – Cargo tank protection\n\n"
            "11.6.3 Cargo tank venting and pressure protection requirements:\n\n"
            "11.6.3.1 Primary pressure/vacuum relief:\n"
            "Tank venting systems shall be provided with pressure/vacuum (P/V) valves to prevent "
            "overpressure and underpressure in cargo tanks.\n\n"
            '11.6.3.2 Secondary means for pressure/vacuum relief:\n'
            '"A secondary means of allowing full flow relief of vapour, air or inert gas mixtures '
            "shall be provided to prevent over-pressure or under-pressure in the event of failure "
            'of the arrangements in paragraph 6.1.2."\n\n'
            "For tankers constructed on or after 1 January 2017: the secondary means shall also be "
            "capable of preventing over-pressure or under-pressure in the event of damage to, or "
            "inadvertent closing of, the means of isolation required in regulation 4.5.3.2.2.\n\n"
            "ALTERNATIVE to dual P/V systems:\n"
            '"Alternatively, pressure sensors may be fitted in each tank protected by the arrangement '
            "required in paragraph 6.1.2, with a monitoring system in the ship's cargo control room "
            "or the position from which cargo operations are normally carried out. Such monitoring "
            "equipment shall also provide an alarm facility which is activated by detection of "
            'over-pressure or under-pressure conditions within a tank."\n\n'
            "11.6.3.3 Bypasses in vent mains:\n"
            "Pressure/vacuum valves required by paragraph 6.1.1 may be provided with a bypass "
            "arrangement when they are located in a vent main or masthead riser. Where such an "
            "arrangement is provided there shall be suitable indicators to show whether the bypass "
            "is open or closed.\n\n"
            "SUMMARY OF TWO OPTIONS:\n"
            "| Option | Configuration | Key Components |\n"
            "|--------|--------------|----------------|\n"
            "| Option A | Two independent P/V protection systems | Dual P/V valves providing full redundancy |\n"
            "| Option B | One P/V system + Pressure sensors + Alarm | Sensor in each tank + monitoring in cargo control room + alarm |\n\n"
            "IS PRESSURE ALARM COMPULSORY?\n"
            "YES — under Option B, if a tanker uses a single P/V protection system, then ALL of the "
            "following are COMPULSORY per SOLAS II-2/11.6.3.2:\n"
            "- Pressure sensors fitted in EACH cargo tank\n"
            "- Monitoring system in the cargo control room (or position for cargo operations)\n"
            "- Over-pressure alarm (high pressure alarm)\n"
            "- Under-pressure/vacuum alarm (low pressure alarm)\n\n"
            "Even under Option A (dual P/V systems), the P/V valves themselves are compulsory safety devices.\n\n"
            "WHY BOTH HIGH PRESSURE AND VACUUM PROTECTION:\n"
            "- HIGH PRESSURE risk: Liquid cargo (oil, chemicals) is volatile. Evaporation increases "
            "vapour pressure inside the cargo tank. Without relief, the tank could rupture.\n"
            "- VACUUM risk: During cargo discharge (unloading), if venting is insufficient, the tank "
            "develops negative pressure (vacuum). This can cause structural collapse of the tank.\n"
            "- The P/V valve protects against BOTH directions — it opens to relieve overpressure AND "
            "opens to admit air when vacuum develops.\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Prevents catastrophic tank failure from overpressure or vacuum collapse "
            "during loading, discharge, and voyage\n"
            "- Survey points: (1) Verify P/V valve certification and set pressures; (2) If Option B: "
            "test pressure sensors, monitoring display in cargo control room, alarm activation at set "
            "points; (3) Check bypass indicators (11.6.3.3) are functional\n"
            "- Typical scenario: During PSC inspection, surveyor checks whether tanker has dual P/V "
            "systems (Option A) or single P/V + alarm (Option B). If Option B, all sensors and alarms "
            "must be tested and calibrated.\n\n"
            "COMMON ERRORS:\n"
            "1. Saying 'pressure alarms are NOT compulsory under SOLAS' — WRONG. SOLAS II-2/11.6.3.2 "
            "explicitly requires them under Option B.\n"
            "2. Citing 'IBC Code 4.3.2' for this requirement — WRONG. IBC Code 4.3.2 does not exist. "
            "The correct reference is SOLAS II-2/11.6.3.2.\n"
            "3. Confusing this with IBC Code Chapter 15 requirements — Chapter 15 covers product-specific "
            "requirements (like toxic cargo venting distance). SOLAS II-2/11.6 covers the general cargo "
            "tank pressure protection applicable to ALL tankers."
        ),
        "metadata_extra": {
            "topic": "fire_protection",
            "ship_type": "tanker",
            "curated": True,
        },
        "keywords_en": [
            "cargo tank protection", "pressure vacuum", "P/V valve", "PV valve",
            "pressure alarm", "vacuum alarm", "overpressure", "underpressure",
            "tanker", "oil tanker", "chemical tanker", "SOLAS II-2/11",
            "SOLAS II-2/11.6", "11.6.3.2", "Regulation 11", "cargo tank venting",
            "secondary means", "pressure sensor", "monitoring system",
            "cargo control room",
        ],
        "keywords_zh": [
            "货舱保护", "压力真空阀", "压力报警", "真空报警", "超压", "负压",
            "油轮", "化学品船", "货舱透气", "压力传感器", "货控室", "二次保护",
        ],
    },
    # === Chunk 2: SOLAS II-2/11 Overview ===
    {
        "id": "solas-ii2-reg11-overview",
        "source": "SOLAS II-2/11",
        "document": "SOLAS",
        "chapter": "II-2",
        "regulation": "SOLAS II-2/11",
        "title": "SOLAS II-2/11 – Special requirements for ships carrying dangerous goods (overview)",
        "breadcrumb": "SOLAS > Chapter II-2 > Regulation 11 > Overview",
        "body_text": (
            "SOLAS Chapter II-2, Regulation 11 – Special Requirements for Ships Carrying "
            "Dangerous Goods (Overview)\n\n"
            "This regulation applies to: oil tankers, chemical tankers, gas carriers, and other "
            "ships carrying dangerous goods in bulk or packaged form.\n\n"
            "Structure of Regulation 11:\n"
            "| Section | Topic | Key Requirements |\n"
            "|---------|-------|------------------|\n"
            "| 11.1 | Purpose | Fire safety objectives for ships carrying dangerous goods |\n"
            "| 11.2 | Cargo ships carrying dangerous goods in packaged form | Stowage, segregation, ventilation |\n"
            "| 11.3 | Ships carrying solid dangerous goods in bulk | Fire protection for cargo holds |\n"
            "| 11.4 | Ships carrying dangerous liquids with flashpoint < 60 deg C | Enhanced fire protection measures |\n"
            "| 11.5 | Ship's cargo area | Definition of cargo area and its boundaries |\n"
            "| 11.6 | CARGO TANK PROTECTION | P/V relief valves, pressure/vacuum alarms, overflow protection |\n"
            "| 11.7 | Cargo pump-rooms | Ventilation, fire detection, gas detection for pump rooms |\n"
            "| 11.8 | Cargo handling spaces | Access, ventilation, fire protection |\n\n"
            "ROUTING GUIDE — when users ask about:\n"
            '- "tanker cargo tank pressure/vacuum protection" -> Section 11.6\n'
            '- "tanker pump room requirements" -> Section 11.7\n'
            '- "dangerous goods in packaged form" -> Section 11.2\n'
            '- "flashpoint below 60 degrees" -> Section 11.4\n'
            '- "cargo area definition/boundaries" -> Section 11.5\n'
            '- "cargo handling space requirements" -> Section 11.8\n\n'
            "IMPORTANT: Regulation 11 is the SOLAS-level requirement for tanker fire safety. "
            "The IBC Code and IGC Code provide ADDITIONAL product-specific requirements beyond "
            "SOLAS. When asked about tanker requirements 'under SOLAS', Regulation 11 is the "
            "primary reference. IBC/IGC are separate instruments (adopted under SOLAS Chapter VII, "
            "not Chapter II-2)."
        ),
        "metadata_extra": {
            "topic": "fire_protection",
            "ship_type": "tanker",
            "curated": True,
        },
        "keywords_en": [
            "SOLAS II-2/11", "special requirements", "dangerous goods", "tanker",
            "oil tanker", "chemical tanker", "gas carrier", "cargo tank",
            "pump room", "flashpoint", "cargo area", "packaged dangerous goods",
        ],
        "keywords_zh": [
            "危险货物特殊要求", "油轮", "化学品船", "气体船", "货舱",
            "泵舱", "闪点", "货物区域", "包装危险货物",
        ],
    },
    # === Chunk 3: SOLAS II-2 Chapter Structure Index ===
    {
        "id": "solas-ii2-chapter-structure",
        "source": "SOLAS II-2",
        "document": "SOLAS",
        "chapter": "II-2",
        "regulation": "SOLAS II-2",
        "title": "SOLAS Chapter II-2 – Fire protection: Complete regulation structure index",
        "breadcrumb": "SOLAS > Chapter II-2 > Regulation Structure Index",
        "body_text": (
            "SOLAS Chapter II-2 – Construction: Fire Protection, Fire Detection and Fire Extinction\n"
            "Complete Regulation Structure Index\n\n"
            "| Regulation | Title | Covers |\n"
            "|-----------|-------|--------|\n"
            "| Reg.1 | Application | Scope — which ships, which dates |\n"
            "| Reg.2 | Fire safety objectives and functional requirements | Performance goals |\n"
            "| Reg.3 | DEFINITIONS | A-class, B-class, C-class divisions; steel or equivalent material |\n"
            "| Reg.4 | Probability of ignition | Arrangement of fuel oil systems, electrical installations, cargo area ventilation |\n"
            "| Reg.5 | Fire growth potential | Restriction of combustible materials, surface flammability |\n"
            "| Reg.6 | Smoke generation potential and toxicity | Material testing for smoke and toxicity |\n"
            "| Reg.7 | Detection and alarm | Fixed fire detection systems, manual call points, alarm timing |\n"
            "| Reg.8 | Control of smoke spread | Ventilation systems in fire zones, smoke extraction |\n"
            "| Reg.9 | CONTAINMENT OF FIRE | Fire integrity of bulkheads and decks, Tables 9.1-9.6, space categories |\n"
            "| Reg.10 | FIREFIGHTING | Fixed fire-extinguishing systems, fire mains, portable extinguishers, sprinklers |\n"
            "| Reg.11 | SPECIAL REQUIREMENTS — DANGEROUS GOODS | Tanker cargo tank protection (11.6), P/V valves, pump rooms (11.7) |\n"
            "| Reg.12 | Notification of crew and passengers | General alarm, PA system |\n"
            "| Reg.13 | MEANS OF ESCAPE | Escape routes, stairways, emergency lighting, width requirements |\n"
            "| Reg.14 | Operational readiness and maintenance | Inspection and testing schedules for fire equipment |\n"
            "| Reg.15 | Instructions, on-board training and drills | Fire training requirements |\n"
            "| Reg.16 | Operations | Hot work procedures, galley exhaust ducts, flammable stores |\n"
            "| Reg.17 | Alternative design and arrangements | Performance-based fire safety design |\n"
            "| Reg.18 | Helicopter facilities | Fire protection for helidecks |\n"
            "| Reg.19 | Carriage of dangerous goods | Additional fire protection when carrying DG in packaged form |\n"
            "| Reg.20 | Protection of vehicle, special category and ro-ro spaces | Vehicle deck fire safety, ventilation |\n\n"
            "ROUTING GUIDE for answering SOLAS II-2 questions:\n"
            '- "fire division / fire integrity / A-0 / A-60 / B-15 / Table 9" -> Reg.9\n'
            '- "A-class definition / B-class definition / steel equivalent" -> Reg.3\n'
            '- "fire detector / smoke detector / alarm spacing" -> Reg.7\n'
            '- "fire extinguisher / CO2 system / sprinkler / fire main" -> Reg.10\n'
            '- "tanker / oil tanker / P/V valve / cargo tank pressure" -> Reg.11\n'
            '- "escape route / emergency exit / means of escape" -> Reg.13\n'
            '- "ro-ro / vehicle deck / car carrier fire" -> Reg.20\n'
            '- "dangerous goods fire protection (packaged)" -> Reg.19\n'
            '- "fire drill / fire training" -> Reg.15\n'
            '- "ventilation / smoke control" -> Reg.8\n\n'
            "CRITICAL: SOLAS II-2 has 20 regulations covering very different topics. When answering "
            "questions about SOLAS II-2, always identify which specific regulation is relevant. Do NOT "
            'cite "SOLAS II-2" generically — cite the specific regulation number (e.g., "SOLAS II-2/9" '
            'or "SOLAS II-2/11.6.3.2").'
        ),
        "metadata_extra": {
            "topic": "fire_protection",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "SOLAS II-2", "fire protection", "fire detection", "fire extinction",
            "Chapter II-2", "regulation index", "fire integrity", "containment",
            "dangerous goods", "tanker", "escape", "firefighting", "A-class",
            "B-class", "Table 9", "means of escape",
        ],
        "keywords_zh": [
            "SOLAS防火", "火灾探测", "灭火", "防火分隔", "危险货物",
            "油轮", "逃生", "消防", "防火定义", "章节索引",
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
    """Insert curated SOLAS II-2/11 data into PostgreSQL."""
    logger.info("Ingesting curated SOLAS II-2/11 chunks to PostgreSQL...")
    for entry in CURATED_SOLAS_II2_REG11_DATA:
        reg = _build_regulation_row(entry)
        db.insert_regulation(reg)
        chunk = _build_chunk_row(entry)
        db.insert_chunk(chunk)
        logger.info(f"  PG: {entry['id']}")
    db.conn.commit()
    logger.info(
        f"PostgreSQL: {len(CURATED_SOLAS_II2_REG11_DATA)} regulations + chunks inserted"
    )


def ingest_to_qdrant():
    """Embed curated SOLAS II-2/11 data and upsert into Qdrant."""
    logger.info("Ingesting curated SOLAS II-2/11 chunks to Qdrant...")
    client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60,
    )
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    collection = "imo_regulations"
    if not client.collection_exists(collection):
        logger.error(f"Collection '{collection}' does not exist in Qdrant")
        sys.exit(1)

    info = client.get_collection(collection)
    base_id = (info.points_count or 0) + 40000  # offset to avoid collisions

    points = []
    for i, entry in enumerate(CURATED_SOLAS_II2_REG11_DATA):
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
    logger.info(f"Qdrant: {len(points)} curated SOLAS II-2/11 points upserted")


def main():
    logger.info("=== Curated SOLAS II-2/11 Ingestion ===\n")

    db = PostgresDB(settings.database_url)
    try:
        ingest_to_postgres(db)
    finally:
        db.close()

    ingest_to_qdrant()

    logger.info("\nDone! Run verification queries to confirm retrieval quality.")


if __name__ == "__main__":
    main()
