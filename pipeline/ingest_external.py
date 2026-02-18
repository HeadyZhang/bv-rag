"""Ingest BV Rules and IACS data into PostgreSQL and Qdrant.

Separate from the existing ingest.py to avoid affecting IMO regulation data.
Supports incremental ingestion (skips existing doc_ids).
"""
import json
import logging
import time
from pathlib import Path

import openai
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    VectorParams,
)
from tqdm import tqdm

from config.settings import settings
from db.postgres import PostgresDB

logger = logging.getLogger(__name__)

# Collection configs with authority-level weighting
COLLECTIONS = {
    "imo_regulations": {
        "description": "IMO conventions and codes (SOLAS, MARPOL, etc.)",
        "authority_weight": 1.0,
    },
    "bv_rules": {
        "description": "Bureau Veritas classification rules and guidance",
        "authority_weight": 0.7,
    },
    "iacs_resolutions": {
        "description": "IACS unified requirements and interpretations",
        "authority_weight": 0.85,
    },
}

BATCH_SIZE = 100
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMS = 1024


class ExternalDataIngestor:
    """Ingest BV Rules and IACS data into the RAG system."""

    def __init__(self):
        self.db = PostgresDB(settings.database_url)
        self.qdrant = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        self.oai = openai.OpenAI(api_key=settings.openai_api_key)

    def close(self):
        self.db.close()

    def ensure_collections(self) -> None:
        """Create Qdrant collections if they don't exist."""
        for name in COLLECTIONS:
            try:
                if not self.qdrant.collection_exists(name):
                    self.qdrant.create_collection(
                        collection_name=name,
                        vectors_config=VectorParams(
                            size=EMBEDDING_DIMS,
                            distance=Distance.COSINE,
                        ),
                        quantization_config=ScalarQuantization(
                            scalar=ScalarQuantizationConfig(type=ScalarType.INT8)
                        ),
                    )
                    logger.info(f"Created Qdrant collection: {name}")
                else:
                    info = self.qdrant.get_collection(name)
                    logger.info(f"Collection {name} exists: {info.points_count} points")
            except Exception as exc:
                logger.error(f"Failed to create collection {name}: {exc}")

    def ingest_chunks(
        self,
        chunks_path: str,
        collection_name: str,
        source_type: str,
        authority_level: str,
    ) -> dict:
        """Ingest chunks from a JSONL file into PostgreSQL and Qdrant.

        Args:
            chunks_path: Path to chunks JSONL file.
            collection_name: Target Qdrant collection.
            source_type: e.g., 'bv_rules', 'iacs_ur'.
            authority_level: e.g., 'classification_rule', 'iacs_ur'.

        Returns:
            Stats dict with counts.
        """
        chunks_file = Path(chunks_path)
        if not chunks_file.exists():
            logger.error(f"Chunks file not found: {chunks_path}")
            return {"error": "file not found"}

        chunks = []
        with open(chunks_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    chunks.append(json.loads(line))

        logger.info(f"Loaded {len(chunks)} chunks from {chunks_path}")

        # Filter out already-existing doc_ids
        existing = set()
        try:
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT doc_id FROM regulations WHERE source_type = %s", (source_type,))
            existing = {row[0] for row in cursor.fetchall()}
            cursor.close()
        except Exception:
            pass

        new_chunks = [c for c in chunks if c.get("doc_id", c.get("chunk_id", "")) not in existing]
        logger.info(f"New chunks to ingest: {len(new_chunks)} (skipped {len(chunks) - len(new_chunks)} existing)")

        if not new_chunks:
            return {"total": len(chunks), "new": 0, "skipped": len(chunks)}

        # Batch process: embed + write to PG + write to Qdrant
        stats = {"total": len(chunks), "new": 0, "errors": 0, "skipped": len(chunks) - len(new_chunks)}

        for batch_start in tqdm(range(0, len(new_chunks), BATCH_SIZE), desc=f"Ingesting {source_type}"):
            batch = new_chunks[batch_start:batch_start + BATCH_SIZE]

            # Generate embeddings
            texts_for_embed = [c.get("text_for_embedding", c.get("text", ""))[:8000] for c in batch]
            try:
                response = self.oai.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=texts_for_embed,
                    dimensions=EMBEDDING_DIMS,
                )
                embeddings = [item.embedding for item in response.data]
            except Exception as exc:
                logger.error(f"Embedding batch failed: {exc}")
                stats["errors"] += len(batch)
                time.sleep(5)
                continue

            # Write to PostgreSQL regulations table
            for chunk in batch:
                doc_id = chunk.get("doc_id", chunk.get("chunk_id", ""))
                try:
                    self.db.conn.cursor().execute(
                        """INSERT INTO regulations
                        (doc_id, url, title, breadcrumb, collection, document,
                         body_text, page_type, source_type, authority_level, parent_doc_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (doc_id) DO NOTHING""",
                        (
                            doc_id,
                            chunk.get("url", ""),
                            chunk.get("title", ""),
                            chunk.get("breadcrumb", ""),
                            chunk.get("collection", source_type),
                            chunk.get("document", ""),
                            chunk.get("body_text", chunk.get("text", "")),
                            chunk.get("page_type", "regulation"),
                            source_type,
                            authority_level,
                            chunk.get("parent_doc_id", ""),
                        ),
                    )
                except Exception as exc:
                    logger.error(f"PG insert failed for {doc_id}: {exc}")
                    stats["errors"] += 1

            self.db.conn.commit()

            # Write to Qdrant
            points = []
            for i, chunk in enumerate(batch):
                chunk_id = chunk.get("chunk_id", chunk.get("doc_id", ""))
                payload = {
                    "chunk_id": chunk_id,
                    "text": chunk.get("text", "")[:2000],
                    "text_for_embedding": texts_for_embed[i][:500],
                    "document": chunk.get("document", ""),
                    "title": chunk.get("title", ""),
                    "breadcrumb": chunk.get("breadcrumb", ""),
                    "url": chunk.get("url", ""),
                    "source_type": source_type,
                    "authority_level": authority_level,
                    "collection": chunk.get("collection", source_type),
                }
                points.append(PointStruct(
                    id=abs(hash(chunk_id)) % (2**63),
                    vector=embeddings[i],
                    payload=payload,
                ))

            try:
                self.qdrant.upsert(collection_name=collection_name, points=points)
                stats["new"] += len(batch)
            except Exception as exc:
                logger.error(f"Qdrant upsert failed: {exc}")
                stats["errors"] += len(batch)

            time.sleep(0.5)

        logger.info(f"Ingestion complete: {stats}")
        return stats

    def ingest_bv_rules(self, chunks_dir: str = "data/bv_rules/chunks") -> dict:
        """Ingest all BV Rules chunk files."""
        return self._ingest_directory(
            chunks_dir, "bv_rules", "bv_rules", "classification_rule",
        )

    def ingest_iacs(self, chunks_dir: str = "data/iacs/chunks") -> dict:
        """Ingest all IACS chunk files."""
        return self._ingest_directory(
            chunks_dir, "iacs_resolutions", "iacs_ur", "iacs_ur",
        )

    def _ingest_directory(
        self, chunks_dir: str, collection: str, source_type: str, authority: str,
    ) -> dict:
        """Ingest all JSONL files in a directory."""
        path = Path(chunks_dir)
        if not path.exists():
            logger.error(f"Directory not found: {chunks_dir}")
            return {"error": "directory not found"}

        jsonl_files = list(path.glob("*.jsonl"))
        if not jsonl_files:
            logger.warning(f"No JSONL files in {chunks_dir}")
            return {"files": 0}

        total_stats = {"files": len(jsonl_files), "total": 0, "new": 0, "errors": 0}
        for f in jsonl_files:
            stats = self.ingest_chunks(str(f), collection, source_type, authority)
            total_stats["total"] += stats.get("total", 0)
            total_stats["new"] += stats.get("new", 0)
            total_stats["errors"] += stats.get("errors", 0)

        logger.info(f"Directory ingestion complete: {total_stats}")
        return total_stats


def main():
    """Run external data ingestion."""
    from rich.console import Console
    console = Console()

    console.print("[bold blue]BV-RAG External Data Ingestion[/bold blue]")

    ingestor = ExternalDataIngestor()
    try:
        console.print("Creating Qdrant collections...")
        ingestor.ensure_collections()

        console.print("\n[yellow]Ingesting BV Rules...[/yellow]")
        bv_stats = ingestor.ingest_bv_rules()
        console.print(f"  BV Rules: {bv_stats}")

        console.print("\n[yellow]Ingesting IACS...[/yellow]")
        iacs_stats = ingestor.ingest_iacs()
        console.print(f"  IACS: {iacs_stats}")

        console.print("\n[green]Ingestion complete![/green]")
    finally:
        ingestor.close()


if __name__ == "__main__":
    main()
