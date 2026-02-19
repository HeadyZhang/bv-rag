"""Ingest curated BV NR467 electrical installation chunks.

Hand-crafted high-quality chunks for BV Rules NR467 Part C (Electrical
Installations) that PDF chunking typically destroys or fails to retrieve.

Usage:
    python -m scripts.ingest_bv_electrical
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

CURATED_BV_ELECTRICAL = [
    {
        "id": "nr467-partc-ch2-governor-parallel",
        "source": "BV NR467 Part C, Chapter 2",
        "document": "BV NR467",
        "chapter": "Part C, Chapter 2",
        "regulation": "NR467 2.7.6(g)",
        "title": "BV NR467 Part C 2.7.6(g) – Governor requirements for AC generating sets in parallel operation",
        "breadcrumb": "BV NR467 > Part C > Chapter 2 > 2.7.6(g) Governor Parallel Operation",
        "body_text": (
            "BV NR467 Part C, Chapter 2, Section 2.7.6(g): Governor requirements for "
            "alternating current generating sets operating in parallel.\n\n"
            "ORIGINAL TEXT:\n"
            "\"For alternating current generating sets operating in parallel, the governing "
            "characteristics of the prime movers are to be such that, within the limits of "
            "20% and 100% total load, the load on any generating set will not normally differ "
            "from its proportionate share of the total load by more than 15% of the rated "
            "power in kW of the largest machine or 25% of the rated power in kW of the "
            "individual machine in question, whichever is the lesser.\"\n\n"
            "\"For alternating current generating sets intended to operate in parallel, "
            "facilities are to be provided to adjust the governor sufficiently finely to "
            "permit an adjustment of load not exceeding 5% of the rated load at normal "
            "frequency.\"\n\n"
            "KEY VALUES SUMMARY:\n"
            "| Parameter | Limit |\n"
            "| Load sharing deviation (option A) | 15% of rated power (kW) of the LARGEST machine |\n"
            "| Load sharing deviation (option B) | 25% of rated power (kW) of the INDIVIDUAL machine |\n"
            "| Which applies | Whichever is the LESSER |\n"
            "| Load range | Between 20% and 100% total load |\n"
            "| Governor fine adjustment | Not exceeding 5% of rated load at normal frequency |\n\n"
            "CALCULATION EXAMPLE:\n"
            "Two generators in parallel: G1 = 500 kW, G2 = 300 kW\n"
            "Total load = 600 kW, proportionate share: G1 = 375 kW, G2 = 225 kW\n"
            "- For G2: Option A = 15% x 500 kW = 75 kW; Option B = 25% x 300 kW = 75 kW\n"
            "- Lesser = 75 kW, so G2 load must be within 225 +/- 75 kW (150~300 kW)\n"
            "- For unequal machines: Option A (largest) is often the lesser, "
            "constraining the smaller machine more tightly.\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- Ensures stable parallel operation without one generator being overloaded\n"
            "- Governors must have fine adjustment capability (5% precision) "
            "for load balancing during parallel operation\n"
            "- During survey: verify governor response curves, load sharing test records, "
            "and automatic load-sharing equipment calibration\n"
            "- Common deficiency: governors not calibrated after overhaul, "
            "causing uneven load distribution during parallel operation"
        ),
        "metadata_extra": {
            "topic": "electrical_installation",
            "ship_type": "all",
            "curated": True,
            "regulation_type": "BV_Rules",
        },
    },
    {
        "id": "nr467-partc-ch2-generators-overview",
        "source": "BV NR467 Part C, Chapter 2",
        "document": "BV NR467",
        "chapter": "Part C, Chapter 2",
        "regulation": "NR467 2.7",
        "title": "BV NR467 Part C 2.7 – General requirements for generators and generating sets",
        "breadcrumb": "BV NR467 > Part C > Chapter 2 > 2.7 Generators Overview",
        "body_text": (
            "BV NR467 Part C, Chapter 2, Section 2.7: General requirements for "
            "generators and generating sets on classified steel ships.\n\n"
            "KEY REQUIREMENTS OVERVIEW:\n\n"
            "1. RATED POWER:\n"
            "- The aggregate rated power of generators must be sufficient to supply "
            "all services necessary for normal operational conditions without use of "
            "the emergency source of power.\n"
            "- With any one generator out of service, the remaining generators must "
            "supply services necessary for safe navigation and propulsion.\n\n"
            "2. VOLTAGE REGULATION:\n"
            "- Generator voltage regulation must maintain steady-state voltage within "
            "+/-2.5% of rated voltage from no-load to full load.\n"
            "- Transient voltage dip must not exceed -15% and must recover to within "
            "+/-3% within 1.5 seconds.\n\n"
            "3. FREQUENCY REGULATION:\n"
            "- Steady-state frequency must be maintained within +/-5% of rated frequency.\n"
            "- Transient frequency variation must not exceed +/-10% and must recover "
            "to within +/-5% within 5 seconds.\n\n"
            "4. PROTECTION DEVICES:\n"
            "- Generators must have overcurrent protection, short-circuit protection, "
            "reverse power protection (for parallel operation), and overvoltage protection.\n"
            "- Emergency generators must have independent starting means.\n\n"
            "5. PARALLEL OPERATION (Section 2.7.6):\n"
            "- See 2.7.6(g) for governor load sharing requirements (15%/25% rule).\n"
            "- Automatic synchronizing or manual synchronizing with check relay required.\n"
            "- Preference tripping system required to shed non-essential loads "
            "in case of generator overload.\n\n"
            "PRACTICAL SIGNIFICANCE:\n"
            "- These are BV's classification requirements (NR467), separate from SOLAS.\n"
            "- Ships classed by BV must comply with NR467 in addition to SOLAS requirements.\n"
            "- Survey focus: verify generator test reports, voltage/frequency regulation "
            "certificates, and protection device settings."
        ),
        "metadata_extra": {
            "topic": "electrical_installation",
            "ship_type": "all",
            "curated": True,
            "regulation_type": "BV_Rules",
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
        "part": "Part C",
        "regulation": entry["regulation"],
        "paragraph": "",
        "body_text": entry["body_text"],
        "page_type": "curated",
        "version": "curated-v1",
    }


def _build_chunk_row(entry: dict) -> dict:
    """Build a dict matching the chunks table schema."""
    keywords_en = [
        "governor", "generating set", "parallel operation", "NR467",
        "load sharing", "power distribution", "voltage regulation",
        "frequency regulation", "generator", "alternating current",
        "BV Rules", "classification", "electrical installation",
    ]
    keywords_zh = [
        "调速器", "发电机", "并联运行", "功率分配", "负荷分配",
        "电压调节", "频率调节", "交流发电机组", "BV规范", "入级",
        "电气装置", "NR467",
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
    """Insert curated BV electrical data into PostgreSQL."""
    logger.info("Ingesting curated BV NR467 electrical chunks to PostgreSQL...")
    for entry in CURATED_BV_ELECTRICAL:
        reg = _build_regulation_row(entry)
        db.insert_regulation(reg)
        chunk = _build_chunk_row(entry)
        db.insert_chunk(chunk)
        logger.info(f"  PG: {entry['id']}")
    db.conn.commit()
    logger.info(f"PostgreSQL: {len(CURATED_BV_ELECTRICAL)} regulations + chunks inserted")


def ingest_to_qdrant():
    """Embed curated BV electrical data and upsert into Qdrant."""
    logger.info("Ingesting curated BV NR467 electrical chunks to Qdrant...")
    client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60,
    )
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    collection = "imo_regulations"
    if not client.collection_exists(collection):
        logger.error(f"Collection '{collection}' does not exist in Qdrant")
        sys.exit(1)

    info = client.get_collection(collection)
    base_id = (info.points_count or 0) + 20000  # offset to avoid collisions

    points = []
    for i, entry in enumerate(CURATED_BV_ELECTRICAL):
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
    logger.info(f"Qdrant: {len(points)} curated BV electrical points upserted")


def main():
    logger.info("=== Curated BV NR467 Electrical Ingestion ===\n")

    db = PostgresDB(settings.database_url)
    try:
        ingest_to_postgres(db)
    finally:
        db.close()

    ingest_to_qdrant()

    logger.info("\nDone! Run verification queries to confirm retrieval quality.")


if __name__ == "__main__":
    main()
