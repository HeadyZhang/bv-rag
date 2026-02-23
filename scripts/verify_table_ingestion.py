"""Verify structured table ingestion quality in Qdrant.

For each table in data/structured_tables.json, runs multiple natural language
queries and checks whether the table appears in the top-N results.

Usage:
    python -m scripts.verify_table_ingestion
    python -m scripts.verify_table_ingestion --batch 1
    python -m scripts.verify_table_ingestion --top-n 5
"""
import argparse
import json
import logging
import sys
from pathlib import Path

import openai
from qdrant_client import QdrantClient

from config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "structured_tables.json"
COLLECTION = "imo_regulations"


def load_tables(path: Path, batch_filter: int | None = None) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        tables = json.load(f)
    if batch_filter is not None:
        tables = [t for t in tables if t.get("batch") == batch_filter]
    return tables


def verify(tables: list[dict], top_n: int = 5) -> bool:
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=120,
    )
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    total_pass = 0
    total_fail = 0
    results_summary: list[dict] = []

    for table in tables:
        table_id = table["table_id"]
        queries = table.get("verify_queries", [table["title"]])
        hits = 0

        for query in queries:
            try:
                resp = oai.embeddings.create(
                    model=settings.embedding_model,
                    input=[query],
                    dimensions=settings.embedding_dimensions,
                )
                results = client.query_points(
                    collection_name=COLLECTION,
                    query=resp.data[0].embedding,
                    limit=top_n,
                    with_payload=["table_id", "doc_id", "content_type"],
                )
                top_ids = [r.payload.get("table_id", "") for r in results.points]
                content_types = [
                    r.payload.get("content_type", "") for r in results.points
                ]

                if table_id in top_ids:
                    rank = top_ids.index(table_id) + 1
                    is_structured = content_types[rank - 1] == "structured_table"
                    hits += 1
                    logger.info(
                        "  PASS: '%s' -> %s at rank %d (structured=%s)",
                        query[:50], table_id, rank, is_structured,
                    )
                else:
                    logger.warning(
                        "  FAIL: '%s' -> %s NOT in top-%d (got: %s)",
                        query[:50], table_id, top_n, top_ids[:3],
                    )
            except Exception as exc:
                logger.error("  ERROR querying '%s': %s", query[:50], exc)

        # Allow 1 miss per table
        min_hits = max(1, len(queries) - 1)
        passed = hits >= min_hits
        status = "PASS" if passed else "FAIL"
        if passed:
            total_pass += 1
        else:
            total_fail += 1

        results_summary.append({
            "table_id": table_id,
            "queries": len(queries),
            "hits": hits,
            "status": status,
        })
        logger.info(
            "  TABLE %s: %d/%d queries hit -> %s",
            table_id, hits, len(queries), status,
        )

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("VERIFICATION SUMMARY")
    logger.info("=" * 60)
    for r in results_summary:
        logger.info(
            "  %s  %s  (%d/%d hits)",
            r["status"], r["table_id"], r["hits"], r["queries"],
        )
    logger.info("-" * 60)
    logger.info(
        "  TOTAL: %d PASS, %d FAIL out of %d tables",
        total_pass, total_fail, len(tables),
    )

    return total_fail == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify table ingestion")
    parser.add_argument("--batch", type=int, default=None)
    parser.add_argument("--top-n", type=int, default=5)
    args = parser.parse_args()

    if not DATA_FILE.exists():
        logger.error("Data file not found: %s", DATA_FILE)
        sys.exit(1)

    tables = load_tables(DATA_FILE, batch_filter=args.batch)
    if not tables:
        logger.error("No tables to verify")
        sys.exit(1)

    logger.info("Verifying %d table(s) (top-%d)...\n", len(tables), args.top_n)
    ok = verify(tables, top_n=args.top_n)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
