"""Full data ingestion pipeline: parsed docs + chunks → PostgreSQL + Qdrant."""
import json
import logging
import os
import sys
import time

import openai
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    PointStruct,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    VectorParams,
)
from rich.console import Console

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import settings
from db.postgres import PostgresDB

console = Console()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

COLLECTION_NAME = "imo_regulations"


def load_jsonl(path: str) -> list[dict]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            items.append(json.loads(line))
    return items


def ingest_to_postgres(db: PostgresDB, regulations: list[dict], chunks: list[dict]):
    console.print("[bold]Step 1: Initializing PostgreSQL schema...[/bold]")
    db.init_schema()

    console.print(f"[bold]Step 2: Inserting {len(regulations)} regulations...[/bold]")
    db.batch_insert_regulations(regulations)

    console.print("[bold]Step 3: Batch inserting cross-references...[/bold]")
    db.batch_insert_cross_references(regulations)

    console.print("[bold]Step 4: Batch linking concepts...[/bold]")
    db.batch_link_concepts(regulations)

    console.print(f"[bold]Step 5: Inserting {len(chunks)} chunks...[/bold]")
    db.batch_insert_chunks(chunks)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=120),
    retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)),
    before_sleep=lambda retry_state: console.print(
        f"  [yellow]Retry {retry_state.attempt_number}/5 after {retry_state.outcome.exception().__class__.__name__}, "
        f"waiting {retry_state.next_action.sleep:.0f}s...[/yellow]"
    ),
)
def embed_batch(oai_client, texts: list[str]) -> tuple:
    """Generate embeddings for a batch of texts with retry."""
    response = oai_client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
        dimensions=settings.embedding_dimensions,
    )
    return response.data, response.usage.total_tokens


def ingest_to_qdrant(chunks: list[dict]):
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60)
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    console.print("[bold]Step 6: Creating Qdrant collection...[/bold]")
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in collections:
        console.print(f"  Collection '{COLLECTION_NAME}' exists, recreating...")
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=settings.embedding_dimensions,
            distance=Distance.COSINE,
        ),
        quantization_config=ScalarQuantization(
            scalar=ScalarQuantizationConfig(
                type=ScalarType.INT8,
                always_ram=True,
            )
        ),
    )

    # Estimate cost upfront
    total_tokens_est = sum(c.get("token_count", 0) for c in chunks)
    est_cost = total_tokens_est / 1_000_000 * 0.13
    console.print(f"  Estimated tokens: {total_tokens_est:,} (~${est_cost:.2f})")

    console.print(f"[bold]Step 7: Generating embeddings & uploading ({len(chunks)} chunks)...[/bold]")
    batch_size = 100
    total_uploaded = 0
    total_cost_tokens = 0

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c["text_for_embedding"] for c in batch]

        embeddings, batch_tokens = embed_batch(oai, texts)
        total_cost_tokens += batch_tokens

        points = []
        for j, (chunk, emb_data) in enumerate(zip(batch, embeddings)):
            point_id = i + j
            payload = {**chunk.get("metadata", {})}
            payload["chunk_id"] = chunk["chunk_id"]
            payload["doc_id"] = chunk["doc_id"]
            payload["text"] = chunk["text"]
            payload["text_for_embedding"] = chunk["text_for_embedding"]
            payload["token_count"] = chunk.get("token_count", 0)

            points.append(PointStruct(
                id=point_id,
                vector=emb_data.embedding,
                payload=payload,
            ))

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        total_uploaded += len(points)

        if total_uploaded % 500 < batch_size or total_uploaded == len(chunks):
            pct = total_uploaded * 100 // len(chunks)
            cost_so_far = total_cost_tokens / 1_000_000 * 0.13
            console.print(f"  [{pct:3d}%] {total_uploaded}/{len(chunks)} points | tokens: {total_cost_tokens:,} | ~${cost_so_far:.3f}")

    console.print("[bold]Step 8: Creating payload indices...[/bold]")
    for field in ["collection", "document", "chapter", "regulation_number"]:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception as e:
            logger.warning(f"Index creation for {field}: {e}")

    estimated_cost = total_cost_tokens / 1_000_000 * 0.13
    console.print("\n[bold green]Qdrant ingestion complete![/bold green]")
    console.print(f"  Total points: {total_uploaded}")
    console.print(f"  Embedding tokens: {total_cost_tokens:,}")
    console.print(f"  Estimated embedding cost: ${estimated_cost:.4f}")

    return total_uploaded


def main():
    start_time = time.time()

    regs_path = "data/parsed/regulations.jsonl"
    chunks_path = "data/chunks/chunks.jsonl"

    if not os.path.exists(regs_path):
        console.print(f"[red]File not found: {regs_path}[/red]")
        sys.exit(1)
    if not os.path.exists(chunks_path):
        console.print(f"[red]File not found: {chunks_path}[/red]")
        sys.exit(1)

    console.print("[bold blue]BV-RAG Data Ingestion Pipeline[/bold blue]\n")

    regulations = load_jsonl(regs_path)
    chunks = load_jsonl(chunks_path)
    console.print(f"Loaded {len(regulations)} regulations, {len(chunks)} chunks\n")

    db = PostgresDB(settings.database_url)
    try:
        ingest_to_postgres(db, regulations, chunks)
        pg_stats = db.get_stats()
    finally:
        db.close()

    qdrant_points = ingest_to_qdrant(chunks)

    elapsed = time.time() - start_time
    console.print(f"\n[bold green]Ingestion complete in {elapsed:.1f}s[/bold green]")
    console.print(f"  PostgreSQL regulations: {pg_stats['total_regulations']}")
    console.print(f"  PostgreSQL chunks: {pg_stats['total_chunks']}")
    console.print(f"  PostgreSQL cross-refs: {pg_stats['total_cross_references']}")
    console.print(f"  Qdrant points: {qdrant_points}")


if __name__ == "__main__":
    main()
