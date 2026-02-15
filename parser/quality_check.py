"""Quality check for parsed regulations."""
import json
import os
import sys
from collections import Counter

from rich.console import Console
from rich.table import Table

console = Console()


def run_quality_check(input_path: str = "data/parsed/regulations.jsonl"):
    if not os.path.exists(input_path):
        console.print(f"[red]File not found: {input_path}[/red]")
        sys.exit(1)

    docs = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            docs.append(json.loads(line))

    total = len(docs)
    console.print(f"\n[bold blue]Quality Report for {total} documents[/bold blue]\n")

    collection_counts = Counter(d["collection"] for d in docs)
    document_counts = Counter(d["document"] for d in docs if d["document"])
    page_type_counts = Counter(d["page_type"] for d in docs)

    empty_body = [d for d in docs if not d["body_text"].strip()]
    empty_breadcrumb = [d for d in docs if not d["breadcrumb"].strip()]
    no_collection = [d for d in docs if not d["collection"]]
    no_document = [d for d in docs if not d["document"]]

    table = Table(title="Distribution by Collection")
    table.add_column("Collection", style="cyan")
    table.add_column("Count", justify="right")
    for coll, count in collection_counts.most_common():
        table.add_row(coll or "(empty)", str(count))
    console.print(table)

    table2 = Table(title="Top 20 Documents")
    table2.add_column("Document", style="cyan")
    table2.add_column("Count", justify="right")
    for doc, count in document_counts.most_common(20):
        table2.add_row(doc, str(count))
    console.print(table2)

    table3 = Table(title="Page Types")
    table3.add_column("Type", style="cyan")
    table3.add_column("Count", justify="right")
    for pt, count in page_type_counts.most_common():
        table3.add_row(pt or "(empty)", str(count))
    console.print(table3)

    console.print(f"\n[bold]Quality Issues:[/bold]")
    console.print(f"  Empty body_text: [yellow]{len(empty_body)}[/yellow] ({len(empty_body)*100//total}%)")
    console.print(f"  Empty breadcrumb: [yellow]{len(empty_breadcrumb)}[/yellow] ({len(empty_breadcrumb)*100//total}%)")
    console.print(f"  No collection: [yellow]{len(no_collection)}[/yellow]")
    console.print(f"  No document: [yellow]{len(no_document)}[/yellow]")

    content_docs = [d for d in docs if d["page_type"] == "content" and d["body_text"]]
    if content_docs:
        lengths = [len(d["body_text"]) for d in content_docs]
        avg_len = sum(lengths) // len(lengths)
        console.print(f"\n[bold]Content Pages Stats:[/bold]")
        console.print(f"  Count: {len(content_docs)}")
        console.print(f"  Avg body length: {avg_len} chars")
        console.print(f"  Min: {min(lengths)}, Max: {max(lengths)}")


if __name__ == "__main__":
    run_quality_check()
