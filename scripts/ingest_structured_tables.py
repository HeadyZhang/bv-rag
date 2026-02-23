"""Batch ingest structured regulation tables into Qdrant + PostgreSQL.

Reads data/structured_tables.json and upserts each table as a single
high-quality chunk.  Supports three modes:

  --dry-run   Validate JSON structure, print summary, skip writes
  --verify    After ingestion, search Qdrant for each table to confirm hits
  --batch N   Only ingest tables whose "batch" field matches N

Deduplication: before inserting, deletes any existing Qdrant points whose
payload.table_id matches the incoming table_id.

Usage:
    python -m scripts.ingest_structured_tables
    python -m scripts.ingest_structured_tables --dry-run
    python -m scripts.ingest_structured_tables --verify
    python -m scripts.ingest_structured_tables --batch 1
"""
import argparse
import json
import logging
import sys
from pathlib import Path

import time

import openai
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)

from config.settings import settings
from db.postgres import PostgresDB

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "structured_tables.json"
COLLECTION = "imo_regulations"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_tables(path: Path, batch_filter: int | None = None) -> list[dict]:
    """Load and optionally filter structured table records."""
    with open(path, encoding="utf-8") as f:
        tables = json.load(f)
    if batch_filter is not None:
        tables = [t for t in tables if t.get("batch") == batch_filter]
    logger.info("Loaded %d table(s) from %s", len(tables), path.name)
    return tables


def validate_table(table: dict, idx: int) -> list[str]:
    """Return list of validation errors for a single table record."""
    errors: list[str] = []
    required = ["id", "table_id", "title", "text", "metadata"]
    for field in required:
        if field not in table:
            errors.append(f"[{idx}] missing required field '{field}'")
    meta = table.get("metadata", {})
    if "content_type" not in meta:
        errors.append(f"[{idx}] metadata missing 'content_type'")
    if "source" not in meta:
        errors.append(f"[{idx}] metadata missing 'source'")
    return errors


def build_embedding_text(table: dict) -> str:
    """Compose the text sent to the embedding model."""
    parts = []
    if table.get("embedding_prefix"):
        parts.append(table["embedding_prefix"])
    parts.append(table["title"])
    parts.append(table["text"])
    kw_en = table.get("keywords_en", [])
    kw_zh = table.get("keywords_zh", [])
    if kw_en or kw_zh:
        parts.append("Keywords: " + " ".join(kw_en) + " " + " ".join(kw_zh))
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Qdrant operations
# ---------------------------------------------------------------------------

def ensure_table_id_index(client: QdrantClient) -> None:
    """Create a keyword payload index on table_id if it doesn't exist."""
    try:
        from qdrant_client.models import PayloadSchemaType
        client.create_payload_index(
            collection_name=COLLECTION,
            field_name="table_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        logger.info("Created payload index on 'table_id'")
    except Exception:
        pass  # already exists or other non-critical error


def delete_existing_by_table_id(client: QdrantClient, table_id: str) -> int:
    """Delete Qdrant points matching a table_id. Returns count deleted."""
    try:
        client.delete(
            collection_name=COLLECTION,
            points_selector=Filter(
                must=[FieldCondition(key="table_id", match=MatchValue(value=table_id))]
            ),
        )
        logger.info("  Deleted existing points with table_id='%s'", table_id)
    except Exception as exc:
        logger.debug("  No existing points for table_id='%s': %s", table_id, exc)
    return 0


def ingest_to_qdrant(
    tables: list[dict],
    dry_run: bool = False,
) -> list[PointStruct]:
    """Embed and upsert tables into Qdrant. Returns the points created."""
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=120,
    )
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    if not client.collection_exists(COLLECTION):
        logger.error("Collection '%s' does not exist in Qdrant", COLLECTION)
        sys.exit(1)

    info = client.get_collection(COLLECTION)
    base_id = (info.points_count or 0) + 100_000

    if not dry_run:
        ensure_table_id_index(client)

    points: list[PointStruct] = []
    for i, table in enumerate(tables):
        table_id = table["table_id"]
        embed_text = build_embedding_text(table)

        if not dry_run:
            # Remove old version first
            delete_existing_by_table_id(client, table_id)

            # Embed with retry for rate limits
            for attempt in range(5):
                try:
                    resp = oai.embeddings.create(
                        model=settings.embedding_model,
                        input=[embed_text],
                        dimensions=settings.embedding_dimensions,
                    )
                    vector = resp.data[0].embedding
                    break
                except openai.RateLimitError:
                    wait = 2 ** attempt * 2
                    logger.warning("  Rate limited, waiting %ds...", wait)
                    time.sleep(wait)
            else:
                raise RuntimeError(f"Embedding failed after 5 retries for {table_id}")
        else:
            vector = [0.0] * settings.embedding_dimensions

        payload = {**table["metadata"]}
        payload["table_id"] = table_id
        payload["doc_id"] = table["id"]
        payload["text"] = table["text"]
        payload["text_for_embedding"] = embed_text
        payload["token_count"] = len(embed_text) // 4

        point = PointStruct(id=base_id + i, vector=vector, payload=payload)
        points.append(point)

        mode = "DRY-RUN" if dry_run else "EMBED"
        logger.info(
            "  [%s] %s — %s (%d tokens)",
            mode, table_id, table["title"][:60], payload["token_count"],
        )

    if not dry_run and points:
        client.upsert(collection_name=COLLECTION, points=points)
        logger.info("Qdrant: %d points upserted", len(points))

    return points


def ingest_to_postgres(tables: list[dict], dry_run: bool = False) -> None:
    """Insert structured tables into PostgreSQL regulations + chunks tables."""
    if dry_run:
        logger.info("PostgreSQL: DRY-RUN — skipping")
        return

    db = PostgresDB(settings.database_url)
    try:
        for table in tables:
            embed_text = build_embedding_text(table)
            reg = {
                "doc_id": table["id"],
                "url": table.get("source_url", ""),
                "title": table["title"],
                "breadcrumb": table.get("breadcrumb", ""),
                "collection": COLLECTION,
                "document": table["metadata"].get("source", ""),
                "chapter": table["metadata"].get("chapter", ""),
                "part": "",
                "regulation": table["metadata"].get("regulation", ""),
                "paragraph": table["metadata"].get("section", ""),
                "body_text": table["text"],
                "page_type": "structured_table",
                "version": "structured-v1",
            }
            chunk = {
                "chunk_id": f"chunk-{table['id']}",
                "doc_id": table["id"],
                "url": table.get("source_url", ""),
                "text": table["text"],
                "text_for_embedding": embed_text,
                "metadata": table["metadata"],
                "token_count": len(embed_text) // 4,
            }
            db.insert_regulation(reg)
            db.insert_chunk(chunk)
            logger.info("  PG: %s", table["id"])
        db.conn.commit()
        logger.info("PostgreSQL: %d records inserted", len(tables))
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_qdrant(tables: list[dict]) -> bool:
    """Search Qdrant for each table using its verification queries."""
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=120,
    )
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    all_pass = True
    for table in tables:
        table_id = table["table_id"]
        queries = table.get("verify_queries", [table["title"]])

        hits = 0
        for query in queries:
            resp = oai.embeddings.create(
                model=settings.embedding_model,
                input=[query],
                dimensions=settings.embedding_dimensions,
            )
            results = client.query_points(
                collection_name=COLLECTION,
                query=resp.data[0].embedding,
                limit=5,
                with_payload=["table_id", "doc_id"],
            )
            top_ids = [
                r.payload.get("table_id", "")
                for r in results.points
            ]
            if table_id in top_ids:
                rank = top_ids.index(table_id) + 1
                hits += 1
                logger.info(
                    "  PASS: '%s' → %s at rank %d",
                    query[:60], table_id, rank,
                )
            else:
                logger.warning(
                    "  FAIL: '%s' → %s NOT in top-5 (got: %s)",
                    query[:60], table_id, top_ids[:3],
                )

        passed = hits >= max(1, len(queries) - 1)  # allow 1 miss
        if not passed:
            all_pass = False
            logger.warning(
                "  TABLE %s: %d/%d queries hit — FAIL",
                table_id, hits, len(queries),
            )
        else:
            logger.info(
                "  TABLE %s: %d/%d queries hit — PASS",
                table_id, hits, len(queries),
            )

    return all_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest structured tables")
    parser.add_argument("--dry-run", action="store_true", help="Validate only")
    parser.add_argument("--verify", action="store_true", help="Verify after ingest")
    parser.add_argument("--batch", type=int, default=None, help="Filter by batch number")
    args = parser.parse_args()

    if not DATA_FILE.exists():
        logger.error("Data file not found: %s", DATA_FILE)
        sys.exit(1)

    tables = load_tables(DATA_FILE, batch_filter=args.batch)
    if not tables:
        logger.error("No tables to ingest")
        sys.exit(1)

    # Validate
    all_errors: list[str] = []
    for i, t in enumerate(tables):
        all_errors.extend(validate_table(t, i))
    if all_errors:
        for err in all_errors:
            logger.error("Validation: %s", err)
        sys.exit(1)
    logger.info("Validation passed for %d table(s)", len(tables))

    if args.dry_run:
        logger.info("\n=== DRY RUN — no writes ===")
        ingest_to_qdrant(tables, dry_run=True)
        logger.info("Dry run complete.")
        return

    # Ingest
    logger.info("\n=== Ingesting %d table(s) ===", len(tables))
    ingest_to_postgres(tables)
    ingest_to_qdrant(tables)

    # Verify
    if args.verify:
        logger.info("\n=== Verification ===")
        ok = verify_qdrant(tables)
        if ok:
            logger.info("\nAll verifications PASSED.")
        else:
            logger.warning("\nSome verifications FAILED.")


if __name__ == "__main__":
    main()
