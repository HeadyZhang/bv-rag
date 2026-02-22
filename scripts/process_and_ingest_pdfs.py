"""
End-to-end PDF processing pipeline: Parse → Chunk → Ingest.

Processes BV Rules and IACS PDFs:
1. Parse PDFs with pdfplumber/Docling → parsed JSONL
2. Chunk parsed entries → chunks JSONL
3. Ingest chunks into PostgreSQL + Qdrant

Usage:
    python scripts/process_and_ingest_pdfs.py --bv-only
    python scripts/process_and_ingest_pdfs.py --iacs-only
    python scripts/process_and_ingest_pdfs.py            # both
    python scripts/process_and_ingest_pdfs.py --parse-only  # skip ingestion
"""
import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.progress import track
from rich.table import Table

console = Console()
logger = logging.getLogger(__name__)

# Directories
BV_PDF_DIR = Path("data/bv_rules/raw_pdfs")
BV_PARSED_DIR = Path("data/bv_rules/parsed_markdown")
BV_CHUNKS_DIR = Path("data/bv_rules/chunks")

IACS_PDF_DIR = Path("data/iacs/raw_pdfs")
IACS_PARSED_DIR = Path("data/iacs/parsed_markdown")
IACS_CHUNKS_DIR = Path("data/iacs/chunks")

# Skip patterns
SKIP_PATTERNS = [
    "General_20Conditions",
    "BV_20MO",
    "MainChanges",
]


def _is_valid_pdf(path: Path) -> bool:
    """Check if file is a valid PDF (starts with %PDF)."""
    try:
        with open(path, "rb") as f:
            header = f.read(5)
        return header.startswith(b"%PDF")
    except Exception:
        return False


def _should_skip(filename: str) -> bool:
    """Check if file should be skipped (General Conditions, MainChanges, etc.)."""
    return any(pat in filename for pat in SKIP_PATTERNS)


def _get_valid_pdfs(pdf_dir: Path) -> list[Path]:
    """Get list of valid, non-skipped PDFs in directory."""
    if not pdf_dir.exists():
        return []
    pdfs = []
    for f in sorted(pdf_dir.glob("*.pdf")):
        if _should_skip(f.name):
            continue
        if _is_valid_pdf(f):
            pdfs.append(f)
        else:
            console.print(f"  [yellow]Skip (invalid): {f.name}[/yellow]")
    return pdfs


def parse_bv_pdfs(pdfs: list[Path]) -> Path:
    """Parse BV PDFs to JSONL."""
    from parser.pdf_parser import PDFParser

    BV_PARSED_DIR.mkdir(parents=True, exist_ok=True)
    output_file = BV_PARSED_DIR / "bv_regulations.jsonl"

    parser = PDFParser()
    total_entries = 0
    errors = 0

    with open(output_file, "w", encoding="utf-8") as fout:
        for pdf_path in track(pdfs, description="Parsing BV PDFs"):
            try:
                entries = parser.parse_pdf(str(pdf_path), source="BV")
                for entry in entries:
                    fout.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
                    total_entries += 1
            except Exception as exc:
                logger.error("Failed to parse %s: %s", pdf_path.name, exc)
                errors += 1

    console.print(f"  Parsed: {total_entries} entries from {len(pdfs)} PDFs ({errors} errors)")
    return output_file


def parse_iacs_pdfs(pdfs: list[Path]) -> Path:
    """Parse IACS PDFs to JSONL."""
    from parser.iacs_pdf_parser import IACSPDFParser

    IACS_PARSED_DIR.mkdir(parents=True, exist_ok=True)
    output_file = IACS_PARSED_DIR / "iacs_regulations.jsonl"

    parser = IACSPDFParser()
    total_entries = 0
    errors = 0

    with open(output_file, "w", encoding="utf-8") as fout:
        for pdf_path in track(pdfs, description="Parsing IACS PDFs"):
            try:
                entries = parser.parse_pdf(str(pdf_path), source="IACS")
                for entry in entries:
                    fout.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
                    total_entries += 1
            except Exception as exc:
                logger.error("Failed to parse %s: %s", pdf_path.name, exc)
                errors += 1

    console.print(f"  Parsed: {total_entries} entries from {len(pdfs)} PDFs ({errors} errors)")
    return output_file


def chunk_parsed_entries(parsed_file: Path, chunks_dir: Path, source: str) -> Path:
    """Chunk parsed JSONL into smaller chunks for embedding."""
    from chunker.pdf_chunker import PDFChunker

    chunks_dir.mkdir(parents=True, exist_ok=True)
    output_file = chunks_dir / f"{source}_chunks.jsonl"

    chunker = PDFChunker(
        target_tokens=512,
        max_tokens=1024,
        overlap_tokens=64,
        table_cell_expansion=True,
    )

    total_entries = sum(1 for _ in open(parsed_file, encoding="utf-8"))
    total_chunks = 0
    skipped = 0
    seen_ids: set[str] = set()

    with open(parsed_file, "r", encoding="utf-8") as fin, \
         open(output_file, "w", encoding="utf-8") as fout:

        for line in track(fin, total=total_entries, description=f"Chunking {source}"):
            entry = json.loads(line)
            chunks = chunker.chunk_regulation(entry)

            for chunk in chunks:
                if len(chunk.text.strip()) < 20:
                    skipped += 1
                    continue
                if chunk.chunk_id in seen_ids:
                    continue
                seen_ids.add(chunk.chunk_id)

                chunk_dict = chunker.to_dict(chunk)
                # Also add fields expected by ingest_external.py
                chunk_dict["doc_id"] = chunk.chunk_id.rsplit("_c", 1)[0].rsplit("_t", 1)[0]
                chunk_dict["body_text"] = chunk.text
                chunk_dict["collection"] = source
                chunk_dict["document"] = chunk.document
                chunk_dict["url"] = chunk.url
                chunk_dict["page_type"] = "regulation"

                fout.write(json.dumps(chunk_dict, ensure_ascii=False) + "\n")
                total_chunks += 1

    console.print(f"  Chunks: {total_chunks} ({skipped} empty skipped)")
    return output_file


def ingest_to_rag(chunks_file: Path, collection: str, source_type: str, authority: str):
    """Ingest chunks JSONL into PostgreSQL + Qdrant."""
    from pipeline.ingest_external import ExternalDataIngestor

    ingestor = ExternalDataIngestor()
    try:
        ingestor.ensure_collections()
        stats = ingestor.ingest_chunks(
            chunks_path=str(chunks_file),
            collection_name=collection,
            source_type=source_type,
            authority_level=authority,
        )
        console.print(f"  Ingested: {stats}")
        return stats
    finally:
        ingestor.close()


def print_summary(bv_stats: dict | None, iacs_stats: dict | None):
    """Print final summary table."""
    table = Table(title="Ingestion Summary")
    table.add_column("Source", style="cyan")
    table.add_column("Total Chunks", justify="right")
    table.add_column("New", justify="right", style="green")
    table.add_column("Skipped", justify="right", style="yellow")
    table.add_column("Errors", justify="right", style="red")

    if bv_stats:
        table.add_row(
            "BV Rules",
            str(bv_stats.get("total", 0)),
            str(bv_stats.get("new", 0)),
            str(bv_stats.get("skipped", 0)),
            str(bv_stats.get("errors", 0)),
        )
    if iacs_stats:
        table.add_row(
            "IACS",
            str(iacs_stats.get("total", 0)),
            str(iacs_stats.get("new", 0)),
            str(iacs_stats.get("skipped", 0)),
            str(iacs_stats.get("errors", 0)),
        )

    console.print(table)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="PDF processing + ingestion pipeline")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--bv-only", action="store_true")
    group.add_argument("--iacs-only", action="store_true")
    parser.add_argument("--parse-only", action="store_true",
                        help="Only parse and chunk, skip ingestion")
    args = parser.parse_args()

    console.print("[bold blue]BV-RAG PDF Processing Pipeline[/bold blue]")
    console.print()
    start = time.monotonic()

    bv_stats = None
    iacs_stats = None

    # === BV Rules ===
    if not args.iacs_only:
        console.print("[bold]Phase 1: BV Rules[/bold]")
        bv_pdfs = _get_valid_pdfs(BV_PDF_DIR)
        console.print(f"  Found {len(bv_pdfs)} valid BV PDFs")

        if bv_pdfs:
            # Parse
            console.print("\n  [yellow]Step 1/3: Parsing PDFs...[/yellow]")
            bv_parsed = parse_bv_pdfs(bv_pdfs)

            # Chunk
            console.print("\n  [yellow]Step 2/3: Chunking...[/yellow]")
            bv_chunks = chunk_parsed_entries(bv_parsed, BV_CHUNKS_DIR, "bv_rules")

            # Ingest
            if not args.parse_only:
                console.print("\n  [yellow]Step 3/3: Ingesting into RAG...[/yellow]")
                bv_stats = ingest_to_rag(
                    bv_chunks, "bv_rules", "bv_rules", "classification_rule",
                )
        else:
            console.print("  [red]No valid BV PDFs found[/red]")

    # === IACS ===
    if not args.bv_only:
        console.print("\n[bold]Phase 2: IACS[/bold]")
        iacs_pdfs = _get_valid_pdfs(IACS_PDF_DIR)
        console.print(f"  Found {len(iacs_pdfs)} valid IACS PDFs")

        if iacs_pdfs:
            # Parse
            console.print("\n  [yellow]Step 1/3: Parsing PDFs...[/yellow]")
            iacs_parsed = parse_iacs_pdfs(iacs_pdfs)

            # Chunk
            console.print("\n  [yellow]Step 2/3: Chunking...[/yellow]")
            iacs_chunks = chunk_parsed_entries(iacs_parsed, IACS_CHUNKS_DIR, "iacs")

            # Ingest
            if not args.parse_only:
                console.print("\n  [yellow]Step 3/3: Ingesting into RAG...[/yellow]")
                iacs_stats = ingest_to_rag(
                    iacs_chunks, "iacs_resolutions", "iacs_ur", "iacs_ur",
                )
        else:
            console.print("  [yellow]No valid IACS PDFs found (IACS crawler may still be running)[/yellow]")

    elapsed = time.monotonic() - start

    console.print(f"\n{'=' * 50}")
    console.print(f"[bold green]Pipeline complete in {elapsed:.1f}s[/bold green]")

    if not args.parse_only:
        print_summary(bv_stats, iacs_stats)


if __name__ == "__main__":
    main()
