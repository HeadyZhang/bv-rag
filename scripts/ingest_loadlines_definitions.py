"""Ingest curated ICLL (Load Lines Convention) definition chunks.

These are hand-crafted high-quality chunks for load line definitions that
expose "definition traps" — where legal definitions are narrower than
everyday usage (e.g. superstructure = first tier only).

Fixes T105-class problems: strict legal definition vs colloquial usage.

Usage:
    python -m scripts.ingest_loadlines_definitions
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

CURATED_LOADLINES_DATA = [
    {
        "id": "icll-reg3-superstructure-definition",
        "source": "ICLL 1966/1988 Regulation 3",
        "document": "ICLL",
        "chapter": "Regulation 3",
        "regulation": "Regulation 3(10)",
        "title": "Superstructure – Strict legal definition (CRITICAL for air pipe heights)",
        "breadcrumb": "ICLL 1966/1988 > Regulation 3 > 3(10) Superstructure Definition",
        "body_text": (
            'Load Lines Convention 1966/1988, Regulation 3(10) – Definition of Superstructure:\n\n'
            '"A superstructure is a decked structure on the FREEBOARD DECK, extending from '
            'side to side of the ship or with the side plating not being inboard of the '
            'shell plating more than 4 per cent of the breadth (B)."\n\n'
            'CRITICAL INTERPRETATION:\n'
            '1. A superstructure is ONLY the FIRST tier of enclosed structure built directly '
            'ON the freeboard deck\n'
            '2. The second tier, third tier, and above are NOT "superstructures" under this '
            'definition\n'
            '3. These upper tiers are typically classified as "deckhouses" or simply "tiers '
            'above superstructure"\n'
            '4. The term "superstructure deck" in Regulation 20 refers ONLY to the deck of '
            'this first-tier structure\n\n'
            'PRACTICAL CONSEQUENCE FOR AIR PIPE HEIGHTS (Regulation 20):\n'
            '- Regulation 20 specifies heights for TWO locations only:\n'
            '  (a) On the FREEBOARD DECK: minimum 760 mm\n'
            '  (b) On the SUPERSTRUCTURE DECK (= top of first tier only): minimum 450 mm\n'
            '- Locations ABOVE the superstructure deck (2nd tier, 3rd tier, bridge deck, '
            'etc.) are NOT covered by Regulation 20\'s mandatory height requirements\n'
            '- For a ship with 3 tiers above freeboard deck (each 3m high):\n'
            '  * 1st tier deck (3m above freeboard deck) = superstructure deck -> 450mm applies\n'
            '  * 2nd tier deck (6m above freeboard deck) = NOT superstructure deck -> no mandatory height\n'
            '  * 3rd tier deck (9m above freeboard deck) = NOT superstructure deck -> no mandatory height\n\n'
            'WHY THIS MATTERS:\n'
            'The higher above the waterline, the less likely green seas will reach the air pipe opening. '
            'The 760mm and 450mm requirements exist to prevent sea water ingress. At 9+ meters above '
            'the freeboard deck, this risk is negligible, so the convention does not impose a mandatory height.\n\n'
            'However, air pipes at any height must still comply with:\n'
            '- Regulation 20(3): automatic closing devices required\n'
            '- General construction standards: substantial construction, adequate wall thickness\n'
            '- Classification society rules may impose additional requirements\n\n'
            'COMMON ERROR: Treating ALL decks above freeboard deck as "superstructure deck" and '
            'applying the 450mm requirement universally. This is INCORRECT. Only the first tier '
            'qualifies as superstructure.'
        ),
        "metadata_extra": {
            "convention": "ICLL",
            "topic": "load_lines",
            "definition_type": "strict_legal",
            "commonly_confused": True,
            "curated": True,
        },
    },
    {
        "id": "icll-reg20-air-pipes-complete",
        "source": "ICLL 1966/1988 Regulation 20",
        "document": "ICLL",
        "chapter": "Regulation 20",
        "regulation": "Regulation 20",
        "title": "Air pipes – Height requirements with boundary conditions and exceptions",
        "breadcrumb": "ICLL 1966/1988 > Regulation 20 > Air Pipes",
        "body_text": (
            'Load Lines Convention 1966/1988, Regulation 20 – Air Pipes (Complete Analysis):\n\n'
            'REGULATION TEXT (Regulation 20(1)):\n'
            '"Where air pipes to ballast and other tanks extend above the freeboard or '
            'superstructure decks, the exposed parts of the pipes shall be of substantial '
            'construction; the height from the deck to the point where water may have access '
            'below shall be at least 760 mm on the freeboard deck and 450 mm on the '
            'superstructure deck."\n\n'
            'STRUCTURED INTERPRETATION:\n\n'
            'Height Requirements by Location:\n'
            '| Location | Minimum Height | Regulation |\n'
            '|----------|---------------|------------|\n'
            '| Freeboard deck | 760 mm | Reg.20(1) |\n'
            '| Superstructure deck (1st tier ONLY) | 450 mm | Reg.20(1) |\n'
            '| 2nd tier and above | No mandatory height under ICLL | Not covered by Reg.20 |\n'
            '| Within enclosed spaces | No mandatory height | Not exposed to weather |\n\n'
            'Note: "No mandatory height" under the Load Lines Convention does not mean no '
            'requirements at all. Classification society rules, flag state requirements, and '
            'good engineering practice still apply. The air pipe must still have automatic '
            'closing devices per Reg.20(3).\n\n'
            'REDUCTION IN HEIGHT (Regulation 20(2)):\n'
            'If the 760mm or 450mm height interferes with ship working, the Administration '
            'may approve a lower height, provided closing arrangements justify it.\n\n'
            'CLOSING DEVICES (Regulation 20(3)):\n'
            'All air pipes must be fitted with automatic closing devices.\n\n'
            'DECISION TREE for air pipe height determination:\n'
            '1. Is the air pipe on the freeboard deck? -> YES -> minimum 760mm\n'
            '2. Is the air pipe on the superstructure deck (first tier above freeboard deck, '
            'meeting Reg.3(10) definition)? -> YES -> minimum 450mm\n'
            '3. Is the air pipe on a higher tier (2nd, 3rd, bridge deck, etc.)? -> YES -> '
            'No mandatory minimum height under ICLL; check classification society rules\n'
            '4. Is the air pipe within an enclosed space? -> YES -> No height requirement\n\n'
            'COMMON EXAM/SURVEY TRAP:\n'
            'Questions about air pipes on "the 3rd tier above freeboard deck" or "9 meters above '
            'freeboard deck" are testing whether the surveyor knows that Regulation 20\'s height '
            'requirements only apply to freeboard deck and superstructure deck (1st tier). '
            'The correct answer for higher locations is "no mandatory height requirement under '
            'the Load Lines Convention."'
        ),
        "metadata_extra": {
            "convention": "ICLL",
            "topic": "load_lines",
            "has_boundary_conditions": True,
            "has_decision_tree": True,
            "curated": True,
        },
    },
    {
        "id": "icll-reg3-freeboard-deck-definition",
        "source": "ICLL 1966/1988 Regulation 3",
        "document": "ICLL",
        "chapter": "Regulation 3",
        "regulation": "Regulation 3(9)",
        "title": "Freeboard deck – Definition and identification",
        "breadcrumb": "ICLL 1966/1988 > Regulation 3 > 3(9) Freeboard Deck",
        "body_text": (
            'Load Lines Convention 1966/1988, Regulation 3(9) – Freeboard Deck:\n\n'
            '"The freeboard deck is normally the uppermost complete deck exposed to weather '
            'and sea, which has permanent means of closing all openings in the weather part '
            'thereof, and below which all openings in the sides of the ship are fitted with '
            'permanent means of watertight closing."\n\n'
            'KEY POINTS:\n'
            '1. It is the reference datum for measuring freeboard (distance from waterline to deck)\n'
            '2. All heights in Regulation 20 (air pipes), Regulation 22 (ventilators), etc. '
            'are measured FROM this deck\n'
            '3. In a multi-deck ship, the owner may request a lower deck to be designated as '
            'the freeboard deck (proviso), but this increases the freeboard assignment\n\n'
            'RELATIONSHIP TO OTHER DECKS:\n'
            '- Freeboard deck = base reference level (0m)\n'
            '- Superstructure deck = top of first tier of superstructure built ON freeboard '
            'deck (Reg.3(10))\n'
            '- Upper tiers (2nd, 3rd, bridge) = above superstructure; different/no height '
            'requirements for fittings\n\n'
            'PRACTICAL IDENTIFICATION:\n'
            'On most cargo ships, the freeboard deck is the main deck (upper continuous deck). '
            'The load line marks are calculated from this deck\'s position.'
        ),
        "metadata_extra": {
            "convention": "ICLL",
            "topic": "load_lines",
            "definition_type": "strict_legal",
            "curated": True,
        },
    },
    {
        "id": "icll-reg13-position-definitions",
        "source": "ICLL 1966/1988 Regulation 13",
        "document": "ICLL",
        "chapter": "Regulation 13",
        "regulation": "Regulation 13",
        "title": "Position 1 and Position 2 – Definitions affecting closing appliance strength",
        "breadcrumb": "ICLL 1966/1988 > Regulation 13 > Position Definitions",
        "body_text": (
            'Load Lines Convention 1966/1988, Regulation 13 – Position 1 and Position 2:\n\n'
            'Position 1: On the freeboard deck, on raised quarter decks, and on exposed '
            'superstructure decks situated forward of a point located a quarter of the ship\'s '
            'length from the forward perpendicular.\n\n'
            'Position 2: On exposed superstructure decks situated abaft a quarter of the ship\'s '
            'length from the forward perpendicular.\n\n'
            'SIGNIFICANCE:\n'
            'These positions determine the STRENGTH requirements for closing appliances '
            '(doors, hatches, ventilator closings):\n'
            '- Position 1: More exposed to heavy seas -> stronger closing appliances required\n'
            '- Position 2: Less exposed -> standard closing appliances acceptable\n\n'
            'RELATED TO SUPERSTRUCTURE DEFINITION:\n'
            'Note that these positions reference "superstructure decks" — which per '
            'Regulation 3(10) means only the FIRST tier above the freeboard deck. Higher tiers '
            'are not "exposed superstructure decks" in this context.\n\n'
            'COMMON APPLICATION:\n'
            '- Hatch covers on freeboard deck forward = Position 1 -> heavy-duty\n'
            '- Doors on accommodation block aft first tier = Position 2 -> standard\n'
            '- Equipment on 3rd tier bridge deck = above superstructure -> different rules apply'
        ),
        "metadata_extra": {
            "convention": "ICLL",
            "topic": "load_lines",
            "definition_type": "strict_legal",
            "curated": True,
        },
    },
    {
        "id": "icll-reg-enclosed-superstructure",
        "source": "ICLL 1966/1988 Regulation 12, 37",
        "document": "ICLL",
        "chapter": "Regulations 12, 37",
        "regulation": "Regulations 12, 37",
        "title": "Enclosed superstructure vs non-enclosed – Effect on freeboard deduction",
        "breadcrumb": "ICLL 1966/1988 > Regulation 12, 37 > Enclosed Superstructure",
        "body_text": (
            'Load Lines Convention – Enclosed vs Non-enclosed Superstructure:\n\n'
            'Regulation 12 defines conditions for a superstructure to be "enclosed":\n'
            '1. Construction is of adequate strength\n'
            '2. Exposed openings are fitted with weathertight closing appliances '
            '(doors, companionways)\n'
            '3. Access openings in bulkheads meet specific standards\n'
            '4. All other openings in sides/ends have efficient weathertight means of closing\n\n'
            'ONLY enclosed superstructures (per Reg.3(10) definition — first tier only) '
            'contribute to freeboard deduction under Regulation 37.\n\n'
            'CRITICAL DISTINCTIONS:\n'
            '| Structure | Superstructure? | Can reduce freeboard? |\n'
            '|-----------|----------------|----------------------|\n'
            '| 1st tier, full-width, enclosed | YES | YES (Reg.37) |\n'
            '| 1st tier, full-width, NOT enclosed | YES | NO |\n'
            '| 1st tier, narrow (>4% inboard of shell) | NO (= deckhouse) | NO |\n'
            '| 2nd tier and above | NO | NO |\n\n'
            'PRACTICAL IMPACT:\n'
            'A surveyor calculating freeboard must correctly identify which structures qualify '
            'as "enclosed superstructures." Incorrectly treating a 2nd-tier structure or a '
            'deckhouse as an enclosed superstructure would understate the required freeboard, '
            'creating a safety risk.\n\n'
            'COMMON ERROR: Including upper tiers in superstructure length calculations for '
            'freeboard deduction. Only the first tier meeting Regulation 3(10) definition counts.'
        ),
        "metadata_extra": {
            "convention": "ICLL",
            "topic": "load_lines",
            "definition_type": "strict_legal",
            "commonly_confused": True,
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
        "superstructure", "superstructure deck", "deckhouse",
        "freeboard deck", "air pipe", "vent pipe", "air pipe height",
        "760mm", "450mm", "Regulation 20", "Regulation 3",
        "enclosed superstructure", "Position 1", "Position 2",
        "freeboard deduction", "first tier", "load lines",
    ]
    keywords_zh = [
        "上层建筑", "甲板室", "干舷甲板", "透气管", "透气管高度",
        "开口高度", "围蔽", "载重线", "第一层", "第二层", "第三层",
        "位置1", "位置2", "干舷折减",
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
    """Insert curated load lines data into PostgreSQL regulations + chunks."""
    logger.info("Ingesting curated load lines definitions to PostgreSQL...")
    for entry in CURATED_LOADLINES_DATA:
        reg = _build_regulation_row(entry)
        db.insert_regulation(reg)
        chunk = _build_chunk_row(entry)
        db.insert_chunk(chunk)
        logger.info(f"  PG: {entry['id']}")
    db.conn.commit()
    logger.info(f"PostgreSQL: {len(CURATED_LOADLINES_DATA)} regulations + chunks inserted")


def ingest_to_qdrant():
    """Embed curated load lines data and upsert into Qdrant."""
    logger.info("Ingesting curated load lines definitions to Qdrant...")
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60)
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    collection = "imo_regulations"
    if not client.collection_exists(collection):
        logger.error(f"Collection '{collection}' does not exist in Qdrant")
        sys.exit(1)

    info = client.get_collection(collection)
    base_id = (info.points_count or 0) + 20000  # offset to avoid collisions with fire table chunks

    points = []
    for i, entry in enumerate(CURATED_LOADLINES_DATA):
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
    logger.info(f"Qdrant: {len(points)} curated load lines points upserted")


def main():
    logger.info("=== Curated Load Lines Definition Ingestion ===\n")

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
