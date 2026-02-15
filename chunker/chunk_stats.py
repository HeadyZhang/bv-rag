"""Statistics report for chunked data."""
import json
import os
import sys
from collections import Counter

from rich.console import Console
from rich.table import Table

console = Console()


def run_stats(input_path: str = "data/chunks/chunks.jsonl"):
    if not os.path.exists(input_path):
        console.print(f"[red]File not found: {input_path}[/red]")
        sys.exit(1)

    chunks = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))

    total = len(chunks)
    token_counts = [c["token_count"] for c in chunks if c.get("token_count")]
    empty_chunks = [c for c in chunks if len(c.get("text", "").strip()) < 20]

    console.print(f"\n[bold blue]Chunk Statistics ({total} chunks)[/bold blue]\n")

    if token_counts:
        sorted_tokens = sorted(token_counts)
        median = sorted_tokens[len(sorted_tokens) // 2]
        console.print(f"  Avg tokens: {sum(token_counts) // len(token_counts)}")
        console.print(f"  Median tokens: {median}")
        console.print(f"  Min tokens: {min(token_counts)}")
        console.print(f"  Max tokens: {max(token_counts)}")
        console.print(f"  Total tokens: {sum(token_counts):,}")

    console.print(f"  Empty chunks (text<20): [yellow]{len(empty_chunks)}[/yellow]")

    doc_counts = Counter(c["metadata"].get("document", "") for c in chunks)
    table = Table(title="Chunks by Document (top 20)")
    table.add_column("Document", style="cyan")
    table.add_column("Chunks", justify="right")
    for doc, count in doc_counts.most_common(20):
        table.add_row(doc or "(none)", str(count))
    console.print(table)

    coll_counts = Counter(c["metadata"].get("collection", "") for c in chunks)
    table2 = Table(title="Chunks by Collection")
    table2.add_column("Collection", style="cyan")
    table2.add_column("Chunks", justify="right")
    for coll, count in coll_counts.most_common():
        table2.add_row(coll or "(none)", str(count))
    console.print(table2)


if __name__ == "__main__":
    run_stats()
