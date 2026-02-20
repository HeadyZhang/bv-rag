"""Ingest curated SOLAS II-2/4.5.5 inert gas system chunks.

Fixes bad case where system cited obsolete SOLAS II-2/60 and missed the
8,000 DWT threshold and COW requirement for inert gas systems.

Usage:
    python -m scripts.ingest_solas_inert_gas
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

CURATED_INERT_GAS_DATA = [
    # ================================================================
    # Chunk 1: SOLAS II-2/4.5.5 — Inert gas system requirements
    # ================================================================
    {
        "id": "solas-ii2-reg4.5.5-inert-gas-system",
        "source": "SOLAS II-2/4",
        "document": "SOLAS",
        "chapter": "II-2",
        "regulation": "SOLAS II-2/4.5.5",
        "title": "SOLAS II-2/4.5.5 – Inert gas system requirements: which ships must be equipped",
        "breadcrumb": "SOLAS > Chapter II-2 > Regulation 4 > 4.5.5 Inert gas systems",
        "body_text": (
            "SOLAS Chapter II-2, Regulation 4 – Probability of Ignition\n"
            "Section 4.5 – Cargo area arrangements for tankers\n"
            "Sub-section 4.5.5 – Inert gas systems\n\n"
            "WHICH SHIPS MUST HAVE AN INERT GAS SYSTEM?\n\n"
            "Three conditions — ANY ONE triggers the requirement:\n\n"
            "| # | Condition | DWT Threshold | Construction Date | Reference |\n"
            "|---|-----------|--------------|-------------------|----------|\n"
            "| 1 | Oil tanker (OLD ships) | \u2265 20,000 DWT | Built BEFORE 1 July 2002 | SOLAS II-2/4.5.5.1 |\n"
            "| 2 | Oil tanker (NEW ships) | \u2265 8,000 DWT | Built ON OR AFTER 1 July 2002 | SOLAS II-2/4.5.5.2 |\n"
            "| 3 | Crude Oil Washing (COW) | Any DWT | Any date — if COW system is fitted | SOLAS II-2/4.5.5.3 |\n\n"
            "DETAILED BREAKDOWN:\n\n"
            "Condition 1 — Old ships (built before 1 July 2002):\n"
            "Oil tankers of 20,000 deadweight tonnage and above shall be fitted with an "
            "inert gas system.\n\n"
            "Condition 2 — New ships (built on or after 1 July 2002):\n"
            "Oil tankers of 8,000 deadweight tonnage and above shall be fitted with an "
            "inert gas system.\n"
            "NOTE: The threshold was REDUCED from 20,000 to 8,000 DWT for ships built from "
            "2002 onwards. This is the MOST IMPORTANT current requirement as virtually all "
            "trading tankers are now post-2002 or have been retrofitted.\n\n"
            "Condition 3 — Crude Oil Washing:\n"
            "Any oil tanker fitted with a crude oil washing (COW) system must have an inert "
            "gas system, regardless of DWT.\n\n"
            "WHY COW REQUIRES INERT GAS:\n"
            "Crude oil washing uses the cargo itself to wash residual oil from tank walls. "
            "During this process:\n"
            "- High-pressure crude oil jets spray the tank walls\n"
            "- The splashing creates large volumes of hydrocarbon vapour (oil gas/mist)\n"
            "- In an enclosed cargo tank, this vapour can easily reach explosive concentrations\n"
            "- Inert gas maintains oxygen content below 8% by volume, preventing ignition\n"
            "- Without inerting, a spark (static electricity, metal-on-metal) could cause "
            "catastrophic explosion\n\n"
            "INERT GAS SYSTEM PERFORMANCE REQUIREMENTS:\n"
            "- Must maintain oxygen content < 8% by volume in cargo tanks at all times\n"
            "- Must be capable of inerting empty cargo tanks (reducing O\u2082 from 21% to < 8%)\n"
            "- Must be capable of purging cargo tanks before gas-freeing\n"
            "- Must maintain positive pressure in cargo tanks to prevent air ingress\n"
            "- System components: flue gas system or nitrogen generator, scrubber, deck water "
            "seal, P/V breaker, distribution piping, O\u2082 analyzers\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Design purpose: Prevents catastrophic cargo tank explosions during loading, "
            "discharge, tank cleaning, and crude oil washing by eliminating oxygen from the "
            "fire triangle\n"
            "- Survey points: (1) Check if ship meets any of the 3 conditions — must have IGS; "
            "(2) Verify O\u2082 content maintained < 8%; (3) Test deck water seal; (4) Check O\u2082 "
            "analyzer calibration; (5) Review IGS operation log during last cargo operations; "
            "(6) For COW-equipped ships: verify IGS operates during washing\n"
            "- Typical scenario: PSC inspector boards a 12,000 DWT product tanker built in 2015. "
            "Since it is \u2265 8,000 DWT and built after 2002, an inert gas system is MANDATORY "
            "per SOLAS II-2/4.5.5.2. If no IGS is fitted — major deficiency — possible detention.\n\n"
            "CRITICAL WARNING — OBSOLETE REGULATION NUMBERS:\n"
            '- "SOLAS II-2/60" and "SOLAS II-2/62" are from pre-2004 editions of SOLAS\n'
            "- Current SOLAS II-2 has only Regulations 1 through 20\n"
            "- The inert gas requirement is now in Regulation 4, sub-section 4.5.5\n"
            "- MSC/Circular.485 references old Regulation numbers — it applies to ships built "
            "before 1984 and is largely historical\n"
            "- Always cite SOLAS II-2/4.5.5 for current requirements\n\n"
            "COMMON ERRORS:\n"
            "1. Saying only \u226520,000 DWT tankers need IGS — WRONG for post-2002 ships "
            "(threshold is 8,000 DWT)\n"
            '2. Citing "SOLAS II-2/60" or "II-2/62" — these are obsolete regulation numbers '
            "from pre-2004 SOLAS\n"
            "3. Forgetting the COW requirement — any tanker with crude oil washing needs IGS "
            "regardless of size\n"
            "4. Confusing chemical tanker inerting (IBC Code Chapter 9) with oil tanker IGS "
            "(SOLAS II-2/4.5.5)"
        ),
        "metadata_extra": {
            "topic": "fire_protection",
            "ship_type": "tanker",
            "curated": True,
        },
        "keywords_en": [
            "inert gas system", "IGS", "SOLAS II-2/4.5.5", "Regulation 4",
            "oil tanker", "8000 DWT", "20000 DWT", "crude oil washing", "COW",
            "oxygen content", "8 percent", "inerting", "cargo tank",
            "explosion prevention", "flue gas", "nitrogen generator",
            "deck water seal",
        ],
        "keywords_zh": [
            "惰气系统", "惰性气体", "油轮", "八千载重吨", "两万载重吨",
            "原油洗舱", "氧含量", "防爆", "烟气系统", "氮气发生器", "甲板水封",
        ],
    },
    # ================================================================
    # Chunk 2: SOLAS II-2/4 — Regulation 4 overview
    # ================================================================
    {
        "id": "solas-ii2-reg4-ignition-overview",
        "source": "SOLAS II-2/4",
        "document": "SOLAS",
        "chapter": "II-2",
        "regulation": "SOLAS II-2/4",
        "title": "SOLAS II-2/4 – Probability of ignition: structure overview (fuel, electrical, cargo area)",
        "breadcrumb": "SOLAS > Chapter II-2 > Regulation 4 > Overview",
        "body_text": (
            "SOLAS Chapter II-2, Regulation 4 – Probability of Ignition (Overview)\n\n"
            "Regulation 4 aims to reduce the probability of ignition by controlling fuel "
            "sources, electrical installations, and cargo area arrangements.\n\n"
            "Structure:\n"
            "| Section | Topic | Key Requirements |\n"
            "|---------|-------|------------------|\n"
            "| 4.1 | Purpose | Reduce ignition probability |\n"
            "| 4.2 | Arrangement of fuel oil systems | Fuel tank location, piping, ventilation |\n"
            "| 4.3 | Electrical installations (general) | Certified equipment, wiring standards |\n"
            "| 4.4 | Electrical installations in hazardous areas | Explosion-proof / intrinsically safe equipment |\n"
            "| 4.5 | CARGO AREA ARRANGEMENTS FOR TANKERS | Cargo pumps, piping, INERT GAS SYSTEMS |\n"
            "| 4.5.1 | Cargo pump rooms | Ventilation, gas detection |\n"
            "| 4.5.2 | Cargo piping | Materials, testing |\n"
            "| 4.5.3 | Cargo tank venting | P/V valves, vent mast |\n"
            "| 4.5.4 | Cargo tank purging/gas-freeing | Procedures for entry |\n"
            "| 4.5.5 | INERT GAS SYSTEMS | Which ships need IGS: \u22658,000 DWT (post-2002) or "
            "\u226520,000 DWT (pre-2002) or COW |\n"
            "| 4.5.6 | Cargo area lighting | Safe lighting in hazardous zones |\n"
            "| 4.5.7 | Cargo tank cleaning | Procedures and safety |\n\n"
            "ROUTING GUIDE:\n"
            '- "inert gas system requirement" \u2192 4.5.5\n'
            '- "cargo pump room ventilation" \u2192 4.5.1\n'
            '- "cargo tank venting / P/V valve" \u2192 4.5.3 (also see Reg.11.6 for pressure alarm)\n'
            '- "fuel oil tank arrangement" \u2192 4.2\n'
            '- "hazardous area electrical equipment" \u2192 4.4\n'
            '- "gas-freeing procedure" \u2192 4.5.4\n\n'
            "IMPORTANT: Regulation 4 is about PREVENTION (reducing ignition probability).\n"
            "Compare with:\n"
            "- Regulation 9: CONTAINMENT (fire integrity divisions)\n"
            "- Regulation 10: SUPPRESSION (firefighting equipment)\n"
            "- Regulation 11: SPECIAL requirements for dangerous goods ships"
        ),
        "metadata_extra": {
            "topic": "fire_protection",
            "ship_type": "tanker",
            "curated": True,
        },
        "keywords_en": [
            "SOLAS II-2/4", "probability of ignition", "fuel oil", "electrical",
            "cargo area", "tanker", "inert gas", "cargo pump", "venting",
            "hazardous area",
        ],
        "keywords_zh": [
            "点火概率", "燃油", "电气", "货物区域", "油轮", "惰气",
            "货物泵", "透气", "危险区域",
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
    """Insert curated inert gas data into PostgreSQL."""
    logger.info("Ingesting curated SOLAS II-2/4.5.5 inert gas chunks to PostgreSQL...")
    for entry in CURATED_INERT_GAS_DATA:
        reg = _build_regulation_row(entry)
        db.insert_regulation(reg)
        chunk = _build_chunk_row(entry)
        db.insert_chunk(chunk)
        logger.info(f"  PG: {entry['id']}")
    db.conn.commit()
    logger.info(
        f"PostgreSQL: {len(CURATED_INERT_GAS_DATA)} regulations + chunks inserted"
    )


def ingest_to_qdrant():
    """Embed curated inert gas data and upsert into Qdrant."""
    logger.info("Ingesting curated inert gas chunks to Qdrant...")
    client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60,
    )
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    collection = "imo_regulations"
    if not client.collection_exists(collection):
        logger.error(f"Collection '{collection}' does not exist in Qdrant")
        sys.exit(1)

    info = client.get_collection(collection)
    base_id = (info.points_count or 0) + 60000  # offset to avoid collisions

    points = []
    for i, entry in enumerate(CURATED_INERT_GAS_DATA):
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
    logger.info(f"Qdrant: {len(points)} curated inert gas points upserted")


def main():
    logger.info("=== Curated SOLAS II-2/4.5.5 Inert Gas Ingestion ===\n")

    db = PostgresDB(settings.database_url)
    try:
        ingest_to_postgres(db)
    finally:
        db.close()

    ingest_to_qdrant()

    logger.info("\nDone! Run verification queries to confirm retrieval quality.")


if __name__ == "__main__":
    main()
