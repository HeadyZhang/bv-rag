"""Ingest curated SOLAS II-2/9 fire integrity table chunks.

These are hand-crafted high-quality chunks for fire division tables that
PDF chunking typically destroys. They go into both PostgreSQL (for BM25)
and Qdrant (for vector search).

Usage:
    python -m scripts.ingest_fire_tables
"""
import json
import logging
import sys
import uuid

import openai
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from config.settings import settings
from db.postgres import PostgresDB

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CURATED_FIRE_DATA = [
    {
        "id": "curated-solas-ii2-9-table9.5",
        "source": "SOLAS II-2/9",
        "document": "SOLAS",
        "chapter": "II-2",
        "regulation": "Regulation 9",
        "title": "SOLAS II-2/9 Table 9.5 – Fire integrity of bulkheads (cargo ships)",
        "breadcrumb": "SOLAS > Chapter II-2 > Regulation 9 > Table 9.5",
        "body_text": (
            "SOLAS II-2/9 Table 9.5: Fire integrity of bulkheads separating "
            "adjacent spaces for CARGO SHIPS (not carrying more than 36 passengers).\n\n"
            "This table specifies the minimum fire integrity standards for bulkheads "
            "between adjacent spaces on cargo ships.\n\n"
            "Space categories for cargo ships (SOLAS II-2/9.2.3):\n"
            "- Category (1): Control stations\n"
            "- Category (2): Corridors\n"
            "- Category (3): Accommodation spaces\n"
            "- Category (4): Stairways\n"
            "- Category (5): Service spaces (low risk)\n"
            "- Category (6): Machinery spaces of Category A\n"
            "- Category (7): Other machinery spaces\n"
            "- Category (8): Cargo spaces\n"
            "- Category (9): Service spaces (high risk) – includes galleys/kitchens "
            "containing cooking appliances\n"
            "- Category (10): Open decks\n"
            "- Category (11): Cargo areas with high fire risk (tankers)\n\n"
            "Key lookup results from Table 9.5:\n"
            "- Category (9) [galley/kitchen] vs Category (2) [corridor] = A-0\n"
            "- Category (1) [control station] vs Category (3) [accommodation] = A-60\n"
            "- Category (1) [control station] vs Category (6) [machinery Cat A] = A-60\n"
            "- Category (1) [control station] vs Category (9) [service high risk] = A-60\n"
            "- Category (6) [machinery Cat A] vs Category (3) [accommodation] = A-60\n"
            "- Category (6) [machinery Cat A] vs Category (2) [corridor] = A-0\n"
            "- Category (3) [accommodation] vs Category (2) [corridor] = B-0 or C\n"
            "- Category (9) [service high risk] vs Category (3) [accommodation] = A-0\n"
            "- Category (9) [service high risk] vs Category (9) [service high risk] = A-0\n\n"
            "IMPORTANT: Galleys/kitchens are classified as Category (9) 'Service spaces "
            "(high risk)' on cargo ships, NOT as Category (3) accommodation spaces.\n\n"
            "Note: For passenger ships carrying more than 36 passengers, use Table 9.1. "
            "For passenger ships carrying not more than 36 passengers, use Table 9.2."
        ),
        "metadata_extra": {
            "table": "9.5",
            "ship_type": "cargo_ship",
            "topic": "fire_protection",
            "curated": True,
        },
    },
    {
        "id": "curated-solas-ii2-9-table9.1",
        "source": "SOLAS II-2/9",
        "document": "SOLAS",
        "chapter": "II-2",
        "regulation": "Regulation 9",
        "title": "SOLAS II-2/9 Table 9.1 – Fire integrity of bulkheads (passenger ships >36 pax)",
        "breadcrumb": "SOLAS > Chapter II-2 > Regulation 9 > Table 9.1",
        "body_text": (
            "SOLAS II-2/9 Table 9.1: Fire integrity of bulkheads separating "
            "adjacent spaces for PASSENGER SHIPS carrying MORE THAN 36 passengers.\n\n"
            "Space categories for passenger ships (>36 passengers):\n"
            "- Category (1): Control stations\n"
            "- Category (2): Corridors\n"
            "- Category (3): Accommodation spaces (low fire risk)\n"
            "- Category (4): Stairways\n"
            "- Category (5): Service spaces (low risk)\n"
            "- Category (6): Machinery spaces of Category A\n"
            "- Category (7): Other machinery spaces\n"
            "- Category (8): Cargo spaces\n"
            "- Category (9): Service spaces (high risk) – includes galleys\n"
            "- Category (10): Open decks\n"
            "- Category (11): Sanitary and similar spaces (low risk)\n"
            "- Category (12): Tanks, voids, and auxiliary machinery spaces\n"
            "- Category (13): Cargo deck spaces on ro-ro ships\n"
            "- Category (14): Vehicle/ro-ro cargo spaces\n\n"
            "Key lookup results from Table 9.1:\n"
            "- Category (9) [galley/kitchen] vs Category (2) [corridor] = B-15\n"
            "- Category (1) [control station] vs Category (3) [accommodation] = A-60\n"
            "- Category (1) [control station] vs Category (6) [machinery Cat A] = A-60\n"
            "- Category (6) [machinery Cat A] vs Category (3) [accommodation] = A-60\n\n"
            "IMPORTANT: On passenger ships (>36 pax), galley vs corridor = B-15, "
            "which is DIFFERENT from cargo ships where it is A-0."
        ),
        "metadata_extra": {
            "table": "9.1",
            "ship_type": "passenger_ship_gt36",
            "topic": "fire_protection",
            "curated": True,
        },
    },
    {
        "id": "curated-solas-ii2-9-deck-tables",
        "source": "SOLAS II-2/9",
        "document": "SOLAS",
        "chapter": "II-2",
        "regulation": "Regulation 9",
        "title": "SOLAS II-2/9 Tables 9.3/9.6 – Fire integrity of DECKS",
        "breadcrumb": "SOLAS > Chapter II-2 > Regulation 9 > Tables 9.3/9.6 (Decks)",
        "body_text": (
            "SOLAS II-2/9 Tables 9.3 and 9.6: Fire integrity of DECKS "
            "(horizontal fire divisions) separating spaces above and below.\n\n"
            "Table 9.3 applies to passenger ships (>36 pax). "
            "Table 9.6 applies to cargo ships.\n\n"
            "These tables govern the fire rating of DECKS (not bulkheads) "
            "between vertically adjacent spaces.\n\n"
            "Critical universal requirements (applies to ALL ship types):\n"
            "- Category (1) [Control station] above or below "
            "Category (3/6/7/8) [Accommodation / Machinery] = A-60\n"
            "- Control stations (bridge, wheelhouse, radio room, fire control) "
            "are ALWAYS Category (1)\n"
            "- Category (1) vs ANY accommodation space = A-60 regardless of ship type\n\n"
            "Example: Wheelhouse/bridge (Category 1, Control station) above or below "
            "crew cabin (Category 3, Accommodation) = A-60 on ALL ship types.\n\n"
            "This A-60 requirement between control stations and accommodation is "
            "UNIVERSAL across:\n"
            "- Cargo ships (Table 9.6)\n"
            "- Passenger ships >36 pax (Table 9.3)\n"
            "- Passenger ships ≤36 pax (Table 9.4)\n"
            "- Tankers\n\n"
            "The logic: Control stations must remain operational during fire "
            "emergencies; A-60 (60 minutes fire resistance) provides maximum protection."
        ),
        "metadata_extra": {
            "table": "9.3/9.6",
            "ship_type": "all",
            "topic": "fire_protection",
            "curated": True,
        },
    },
    {
        "id": "curated-solas-ii2-9-categories",
        "source": "SOLAS II-2/9",
        "document": "SOLAS",
        "chapter": "II-2",
        "regulation": "Regulation 9.2.3",
        "title": "SOLAS II-2/9.2.3 – Space category definitions for fire integrity tables",
        "breadcrumb": "SOLAS > Chapter II-2 > Regulation 9 > 9.2.3 Space Categories",
        "body_text": (
            "SOLAS II-2/9.2.3: Definition of space categories used in fire "
            "integrity tables.\n\n"
            "Category (1) - Control stations:\n"
            "Spaces containing emergency sources of power, wheelhouse/bridge, "
            "radio rooms, fire control stations, ship control rooms. "
            "These are the most safety-critical spaces.\n\n"
            "Category (2) - Corridors:\n"
            "Corridors, lobbies, and halls used as escape routes or general access.\n\n"
            "Category (3) - Accommodation spaces:\n"
            "Living quarters, offices, hospitals, recreation rooms, "
            "pantries without cooking appliances, similar spaces.\n\n"
            "Category (5) - Service spaces (low risk):\n"
            "Lockers, store rooms, workshops, pantries without cooking appliances, "
            "laundries, similar spaces of small fire risk.\n\n"
            "Category (6) - Machinery spaces of Category A:\n"
            "Spaces containing internal combustion machinery for main propulsion, "
            "boilers, oil fuel units, steam engines, similar high-risk machinery.\n\n"
            "Category (9) - Service spaces (HIGH risk):\n"
            "Galleys, pantries CONTAINING COOKING APPLIANCES, paint lockers, "
            "lamp rooms, flammable liquid storage.\n\n"
            "CRITICAL DISTINCTION:\n"
            "- A galley/kitchen WITH cooking equipment = Category (9) HIGH RISK\n"
            "- A pantry WITHOUT cooking equipment = Category (3) or (5) LOW RISK\n"
            "This distinction directly affects the fire integrity requirement "
            "(e.g., galley vs corridor = A-0 on cargo ships, but pantry vs "
            "corridor = B-0 or less)."
        ),
        "metadata_extra": {
            "table": "definitions",
            "ship_type": "all",
            "topic": "fire_protection",
            "curated": True,
        },
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
    keywords_en = [
        "fire integrity", "bulkhead", "deck", "fire division",
        "Category 1", "Category 2", "Category 3", "Category 6", "Category 9",
        "control station", "corridor", "accommodation", "galley", "machinery",
    ]
    keywords_zh = [
        "防火分隔", "舱壁", "甲板", "厨房", "走廊", "驾驶室", "住舱", "机舱",
        "分类", "类别", "A-0", "A-60", "B-15",
    ]
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
    """Insert curated fire table data into PostgreSQL regulations + chunks."""
    logger.info("Ingesting curated fire tables to PostgreSQL...")
    for entry in CURATED_FIRE_DATA:
        reg = _build_regulation_row(entry)
        db.insert_regulation(reg)
        chunk = _build_chunk_row(entry)
        db.insert_chunk(chunk)
        logger.info(f"  PG: {entry['id']}")
    db.conn.commit()
    logger.info(f"PostgreSQL: {len(CURATED_FIRE_DATA)} regulations + chunks inserted")


def ingest_to_qdrant():
    """Embed curated fire table data and upsert into Qdrant."""
    logger.info("Ingesting curated fire tables to Qdrant...")
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60)
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    collection = "imo_regulations"
    if not client.collection_exists(collection):
        logger.error(f"Collection '{collection}' does not exist in Qdrant")
        sys.exit(1)

    # Get current max point ID to avoid collisions
    info = client.get_collection(collection)
    base_id = (info.points_count or 0) + 10000  # offset to avoid collisions

    points = []
    for i, entry in enumerate(CURATED_FIRE_DATA):
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
    logger.info(f"Qdrant: {len(points)} curated fire table points upserted")


def main():
    logger.info("=== Curated Fire Table Ingestion ===\n")

    # PostgreSQL
    db = PostgresDB(settings.database_url)
    try:
        ingest_to_postgres(db)
    finally:
        db.close()

    # Qdrant
    ingest_to_qdrant()

    logger.info("\nDone! Run verification queries to confirm retrieval quality.")


if __name__ == "__main__":
    main()
