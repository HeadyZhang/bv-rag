"""Ingest curated IBC Code Chapter 15 chunks.

Hand-crafted high-quality chunks for IBC Code special requirements that
PDF chunking typically destroys or fails to retrieve — especially the
critical toxic products venting requirements (Section 15.12).

Usage:
    python -m scripts.ingest_ibc_code
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

CURATED_IBC_DATA = [
    # === Chunk 1: IBC Code 15.12 Toxic Products (core fix) ===
    {
        "id": "ibc-ch15-s15.12-toxic-products",
        "source": "IBC Code Chapter 15",
        "document": "IBC Code",
        "chapter": "Chapter 15",
        "regulation": "IBC Code 15.12",
        "title": "IBC Code 15.12 – Toxic products: special requirements for tank venting and cargo stowage",
        "breadcrumb": "IBC Code > Chapter 15 > 15.12 Toxic Products",
        "body_text": (
            "IBC Code Chapter 15 – Special Requirements, Section 15.12 – Toxic Products\n\n"
            "15.12.1 Exhaust openings of tank vent systems shall be located:\n\n"
            ".1 at a height of B/3 or 6 m, whichever is greater, above the weather deck or, "
            "in the case of a deck tank, the access gangway;\n\n"
            ".2 not less than 6 m above the fore-and-aft gangway, if fitted within 6 m "
            "of the gangway;\n\n"
            ".3 15 m from any opening or air intake to any accommodation and service spaces; "
            "and\n\n"
            ".4 the vent height may be reduced to 3 m above the deck or fore-and-aft gangway, "
            "as applicable, provided high-velocity vent valves of an approved type, directing "
            "the vapour/air mixture upwards in an unimpeded jet with an exit velocity of at "
            "least 30 m/s, are fitted.\n\n"
            "15.12.2 Tank venting systems shall be provided with a connection for a "
            "vapour-return line to the shore installation.\n\n"
            "15.12.3 Products shall:\n"
            ".1 not be stowed adjacent to oil fuel tanks;\n\n"
            "CRITICAL CLARIFICATION on the '15 metre' requirement:\n"
            "- WHAT must be 15m away: the EXHAUST OPENINGS of tank vent systems "
            "(货舱透气管排气口)\n"
            "- 15m away FROM WHAT: any OPENING or AIR INTAKE to accommodation and "
            "service spaces (住舱和服务处所的任何开口或空气入口)\n"
            "- This is about preventing toxic vapour from cargo tank vents from entering "
            "crew spaces\n"
            "- It is NOT about cabin entrances being 15m from the cargo area in general\n\n"
            "COMMON ERROR: Citing 'IBC Code 4.3.2' for this requirement. There is NO "
            "Section 4.3.2 in the IBC Code. Chapter 4 of IBC Code covers 'Cargo containment' "
            "(tank types, materials, design). The 15m vent distance requirement is in "
            "Chapter 15, Section 15.12.\n\n"
            "Summary table:\n"
            "| Requirement | Value | IBC Code Reference |\n"
            "| Vent height above weather deck | >= B/3 or 6m (greater) | 15.12.1.1 |\n"
            "| Vent height if near gangway | >= 6m above gangway | 15.12.1.2 |\n"
            "| Distance from accommodation openings | >= 15m | 15.12.1.3 |\n"
            "| Reduced height with high-velocity valve | >= 3m (exit velocity >= 30 m/s) | 15.12.1.4 |\n"
            "| Vapour return line | Required | 15.12.2 |\n"
            "| Not adjacent to fuel tanks | Required | 15.12.3.1 |"
        ),
        "metadata_extra": {
            "topic": "chemical_tanker",
            "ship_type": "chemical_tanker",
            "curated": True,
            "regulation_type": "IMO_Code",
        },
    },
    # === Chunk 2: IBC Code Chapter 15 overview ===
    {
        "id": "ibc-ch15-overview",
        "source": "IBC Code Chapter 15",
        "document": "IBC Code",
        "chapter": "Chapter 15",
        "regulation": "IBC Code Ch.15",
        "title": "IBC Code Chapter 15 – Special requirements overview",
        "breadcrumb": "IBC Code > Chapter 15 > Overview",
        "body_text": (
            "IBC Code Chapter 15 – Special Requirements (Overview)\n\n"
            "Chapter 15 contains product-specific special requirements that go beyond "
            "the general provisions of Chapters 1-14. Each section addresses a specific "
            "category of dangerous chemical cargo:\n\n"
            "| Section | Product Category | Key Requirements |\n"
            "| 15.1 | General | Applicability rules |\n"
            "| 15.2 | Ammonium nitrate solution (93%+) | Tank location, temperature control |\n"
            "| 15.3 | Carbon disulphide | Inerting, temperature, isolation |\n"
            "| 15.4 | Diethyl ether | Inerting, electrical safety |\n"
            "| 15.5 | Hydrogen peroxide solutions | Materials compatibility, venting |\n"
            "| 15.6 | Motor fuel anti-knock compounds | Toxicity protection, decontamination |\n"
            "| 15.7 | Phosphorus, yellow or white | Inerting with nitrogen, temperature |\n"
            "| 15.8 | Propylene oxide / ethylene oxide | Inerting, refrigeration, materials |\n"
            "| 15.9 | Sodium chlorate solution | Segregation from combustibles |\n"
            "| 15.10 | Sulphur (molten) | Temperature control, H2S detection |\n"
            "| 15.11 | Acids | Materials, venting, tank coating |\n"
            "| 15.12 | Toxic products | Vent distance 15m, vent height B/3 or 6m |\n"
            "| 15.13 | Cargoes protected by additives | Additive monitoring |\n"
            "| 15.14 | Cargoes with vapour pressure > 1.013 bar | Pressure relief, cargo cooling |\n"
            "| 15.15 | H2S detection | Detector placement, alarm levels |\n"
            "| 15.16 | Cargo contamination | Cleaning procedures |\n"
            "| 15.17 | Increased ventilation | Additional ventilation requirements |\n"
            "| 15.18 | Special cargo pump-room requirements | Pump-room safety |\n"
            "| 15.19 | Overflow control | Tank overflow prevention |\n\n"
            "IMPORTANT: When a user asks about requirements for a SPECIFIC type of "
            "chemical cargo, the answer is most likely in Chapter 15 (Special requirements), "
            "NOT in Chapter 4 (Cargo containment).\n\n"
            "Chapter 4 covers general tank location and structural requirements.\n"
            "Chapter 15 covers product-specific operational and safety requirements."
        ),
        "metadata_extra": {
            "topic": "chemical_tanker",
            "ship_type": "chemical_tanker",
            "curated": True,
            "regulation_type": "IMO_Code",
        },
    },
    # === Chunk 3: IBC Code chapter structure index ===
    {
        "id": "ibc-code-chapter-index",
        "source": "IBC Code",
        "document": "IBC Code",
        "chapter": "",
        "regulation": "IBC Code",
        "title": "IBC Code – Chapter structure index (for correct chapter identification)",
        "breadcrumb": "IBC Code > Chapter Index",
        "body_text": (
            "IBC Code – International Code for the Construction and Equipment of Ships "
            "Carrying Dangerous Chemicals in Bulk\n\n"
            "Chapter Structure:\n"
            "| Chapter | Title | Covers |\n"
            "| 1 | General | Scope, definitions, application |\n"
            "| 2 | Ship survival capability and location of cargo tanks | Damage stability, tank location |\n"
            "| 3 | Ship arrangements | Cargo segregation from other spaces |\n"
            "| 4 | Cargo containment | Tank types (1/2/3), materials, design |\n"
            "| 5 | Cargo transfer | Piping, pumps, loading/unloading |\n"
            "| 6 | Materials of construction | Corrosion resistance, compatibility |\n"
            "| 7 | Cargo temperature control | Heating/cooling systems |\n"
            "| 8 | Cargo tank venting and gas-freeing | General venting requirements |\n"
            "| 9 | Environmental control | Inerting, padding, drying |\n"
            "| 10 | Electrical installations | Hazardous area classification |\n"
            "| 11 | Fire protection and fire extinction | Fire safety for chemical tankers |\n"
            "| 12 | Mechanical ventilation in cargo area | Pump-room and cargo area ventilation |\n"
            "| 13 | Instrumentation | Gauging, alarms, temperature measurement |\n"
            "| 14 | Personnel protection | PPE, safety equipment, decontamination |\n"
            "| 15 | Special requirements | PRODUCT-SPECIFIC requirements (see 15.1-15.19) |\n"
            "| 16 | Operational requirements | Cargo information, training, procedures |\n"
            "| 17 | Summary of minimum requirements | Product-by-product lookup table |\n\n"
            "ROUTING GUIDE for answering IBC Code questions:\n"
            "- 'What are the requirements for [specific chemical]?' -> Chapter 15 + Chapter 17\n"
            "- 'What type of tank is required?' -> Chapter 4\n"
            "- 'What is the venting requirement for toxic cargo?' -> Chapter 15.12 (NOT Chapter 8)\n"
            "- 'What fire protection is needed?' -> Chapter 11\n"
            "- 'What PPE is needed?' -> Chapter 14\n"
            "- 'What is the cargo compatibility?' -> Chapter 6 + Chapter 17\n\n"
            "CRITICAL: Chapter 4 is about TANK CONTAINMENT (tank types, structural design), "
            "NOT about operational requirements for specific cargo types. Do NOT cite Chapter 4 "
            "for product-specific questions — use Chapter 15 instead."
        ),
        "metadata_extra": {
            "topic": "chemical_tanker",
            "ship_type": "chemical_tanker",
            "curated": True,
            "regulation_type": "IMO_Code",
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
        "toxic products", "toxic cargo", "tank vent", "vent height",
        "exhaust opening", "15 metres", "15m", "accommodation",
        "air intake", "high velocity vent valve", "30 m/s",
        "vapour return", "IBC Code", "Chapter 15", "15.12",
        "chemical tanker", "special requirements", "cargo containment",
        "chapter index", "tank type",
    ]
    keywords_zh = [
        "有毒货物", "有毒产品", "透气管", "排气口", "通风口高度",
        "15米", "住舱", "空气入口", "高速透气阀", "化学品船",
        "IBC规则", "特殊要求", "第15章",
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
    """Insert curated IBC Code data into PostgreSQL."""
    logger.info("Ingesting curated IBC Code chunks to PostgreSQL...")
    for entry in CURATED_IBC_DATA:
        reg = _build_regulation_row(entry)
        db.insert_regulation(reg)
        chunk = _build_chunk_row(entry)
        db.insert_chunk(chunk)
        logger.info(f"  PG: {entry['id']}")
    db.conn.commit()
    logger.info(f"PostgreSQL: {len(CURATED_IBC_DATA)} regulations + chunks inserted")


def ingest_to_qdrant():
    """Embed curated IBC Code data and upsert into Qdrant."""
    logger.info("Ingesting curated IBC Code chunks to Qdrant...")
    client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60,
    )
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    collection = "imo_regulations"
    if not client.collection_exists(collection):
        logger.error(f"Collection '{collection}' does not exist in Qdrant")
        sys.exit(1)

    info = client.get_collection(collection)
    base_id = (info.points_count or 0) + 30000  # offset to avoid collisions

    points = []
    for i, entry in enumerate(CURATED_IBC_DATA):
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
    logger.info(f"Qdrant: {len(points)} curated IBC Code points upserted")


def main():
    logger.info("=== Curated IBC Code Chapter 15 Ingestion ===\n")

    db = PostgresDB(settings.database_url)
    try:
        ingest_to_postgres(db)
    finally:
        db.close()

    ingest_to_qdrant()

    logger.info("\nDone! Run verification queries to confirm retrieval quality.")


if __name__ == "__main__":
    main()
