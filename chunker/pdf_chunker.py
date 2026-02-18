"""PDF-aware chunker compatible with existing regulation_chunker output format."""
import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass, field

import tiktoken
from rich.console import Console
from rich.progress import track

logger = logging.getLogger(__name__)
console = Console()

CLAUSE_BOUNDARY_PATTERN = re.compile(r"^(\d+\.\d+(?:\.\d+)*)\s+", re.MULTILINE)
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?;])\s+")


@dataclass
class PDFChunk:
    """A single chunk from a PDF-parsed regulation, compatible with chunks.jsonl."""

    chunk_id: str
    text: str
    text_for_embedding: str
    document: str
    regulation_number: str
    breadcrumb: str
    url: str
    title: str
    source_type: str
    authority_level: str
    chunk_type: str
    token_count: int = 0
    metadata: dict = field(default_factory=dict)


class PDFChunker:
    """Chunker for PDF-parsed regulation entries.

    Produces chunks compatible with the existing chunks.jsonl format
    used by RegulationChunker, with additional support for:
    - Table-aware chunking (Markdown + cell expansion)
    - Regulation clause boundary splitting
    - Long paragraph sentence-boundary splitting
    """

    def __init__(
        self,
        target_tokens: int = 512,
        max_tokens: int = 1024,
        overlap_tokens: int = 64,
        table_cell_expansion: bool = True,
    ):
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.table_cell_expansion = table_cell_expansion
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using cl100k_base encoding."""
        return len(self.encoder.encode(text))

    def chunk_regulation(self, entry: dict) -> list[PDFChunk]:
        """Chunk a single parsed PDF regulation entry.

        Args:
            entry: A dict from parsed PDF output (ParsedPDFRegulation.to_dict()).

        Returns:
            List of PDFChunk objects ready for JSONL serialization.
        """
        body_text = entry.get("body_text", "").strip()
        tables = entry.get("tables", [])
        doc_id = entry.get("doc_id", "")
        document = entry.get("document", "")
        regulation_number = entry.get("regulation_number", "")
        breadcrumb = entry.get("breadcrumb", "")
        title = entry.get("title", "")
        source_type = entry.get("source_type", "bv_rules")
        metadata = entry.get("metadata", {})
        authority_level = metadata.get("authority_level", "classification_rule")

        chunks = []
        chunk_counter = 0

        if body_text:
            text_chunks = self._chunk_body_text(
                body_text=body_text,
                doc_id=doc_id,
                document=document,
                regulation_number=regulation_number,
                breadcrumb=breadcrumb,
                title=title,
                source_type=source_type,
                authority_level=authority_level,
                start_index=chunk_counter,
            )
            chunks.extend(text_chunks)
            chunk_counter += len(text_chunks)

        for table in tables:
            if self._is_empty_table_chunk(table):
                continue
            table_chunks = self._chunk_table(
                table=table,
                doc_id=doc_id,
                document=document,
                regulation_number=regulation_number,
                breadcrumb=breadcrumb,
                title=title,
                source_type=source_type,
                authority_level=authority_level,
                start_index=chunk_counter,
            )
            chunks.extend(table_chunks)
            chunk_counter += len(table_chunks)

        for chunk in chunks:
            chunk.metadata = {
                **metadata,
                "chunk_type": chunk.chunk_type,
                "document": document,
                "regulation_number": regulation_number,
                "breadcrumb": breadcrumb,
                "title": title,
                "source_type": source_type,
            }

        return chunks

    def _chunk_body_text(
        self,
        body_text: str,
        doc_id: str,
        document: str,
        regulation_number: str,
        breadcrumb: str,
        title: str,
        source_type: str,
        authority_level: str,
        start_index: int,
    ) -> list[PDFChunk]:
        """Chunk body text by clause boundaries, then by sentence if needed."""
        clause_sections = self._split_by_clauses(body_text)

        if not clause_sections:
            clause_sections = [body_text]

        chunks = []
        chunk_idx = start_index

        for section_text in clause_sections:
            section_text = section_text.strip()
            if not section_text:
                continue

            token_count = self.count_tokens(section_text)

            if token_count <= self.target_tokens:
                embedding_text = self._build_embedding_text(
                    document, breadcrumb, title, section_text,
                )
                chunk = PDFChunk(
                    chunk_id=f"{doc_id}_c{chunk_idx}",
                    text=section_text,
                    text_for_embedding=embedding_text,
                    document=document,
                    regulation_number=regulation_number,
                    breadcrumb=breadcrumb,
                    url="",
                    title=title,
                    source_type=source_type,
                    authority_level=authority_level,
                    chunk_type="regulation",
                    token_count=token_count,
                )
                chunks.append(chunk)
                chunk_idx += 1

            elif token_count <= self.max_tokens:
                embedding_text = self._build_embedding_text(
                    document, breadcrumb, title, section_text,
                )
                chunk = PDFChunk(
                    chunk_id=f"{doc_id}_c{chunk_idx}",
                    text=section_text,
                    text_for_embedding=embedding_text,
                    document=document,
                    regulation_number=regulation_number,
                    breadcrumb=breadcrumb,
                    url="",
                    title=title,
                    source_type=source_type,
                    authority_level=authority_level,
                    chunk_type="regulation",
                    token_count=token_count,
                )
                chunks.append(chunk)
                chunk_idx += 1

            else:
                sentence_chunks = self._split_at_sentences(
                    text=section_text,
                    doc_id=doc_id,
                    document=document,
                    regulation_number=regulation_number,
                    breadcrumb=breadcrumb,
                    title=title,
                    source_type=source_type,
                    authority_level=authority_level,
                    start_index=chunk_idx,
                )
                chunks.extend(sentence_chunks)
                chunk_idx += len(sentence_chunks)

        return chunks

    def _split_by_clauses(self, text: str) -> list[str]:
        """Split text at clause number boundaries (1.1, 1.2, etc.)."""
        matches = list(CLAUSE_BOUNDARY_PATTERN.finditer(text))
        if len(matches) < 2:
            return [text] if text.strip() else []

        sections = []

        if matches[0].start() > 0:
            preamble = text[:matches[0].start()].strip()
            if preamble:
                sections.append(preamble)

        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section = text[start:end].strip()
            if section:
                sections.append(section)

        return sections

    def _split_at_sentences(
        self,
        text: str,
        doc_id: str,
        document: str,
        regulation_number: str,
        breadcrumb: str,
        title: str,
        source_type: str,
        authority_level: str,
        start_index: int,
    ) -> list[PDFChunk]:
        """Split long text at sentence boundaries to stay under target_tokens."""
        sentences = SENTENCE_SPLIT_PATTERN.split(text)
        chunks = []
        current_sentences = []
        current_tokens = 0
        chunk_idx = start_index
        overlap_sentence = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sent_tokens = self.count_tokens(sentence)

            if sent_tokens > self.max_tokens:
                if current_sentences:
                    chunks.append(
                        self._finalize_text_chunk(
                            current_sentences, doc_id, document,
                            regulation_number, breadcrumb, title,
                            source_type, authority_level, chunk_idx,
                        ),
                    )
                    chunk_idx += 1
                    current_sentences = []
                    current_tokens = 0

                hard_chunks = self._hard_split(
                    sentence, doc_id, document, regulation_number,
                    breadcrumb, title, source_type, authority_level,
                    chunk_idx,
                )
                chunks.extend(hard_chunks)
                chunk_idx += len(hard_chunks)
                continue

            if (
                current_tokens + sent_tokens > self.target_tokens
                and current_sentences
            ):
                chunks.append(
                    self._finalize_text_chunk(
                        current_sentences, doc_id, document,
                        regulation_number, breadcrumb, title,
                        source_type, authority_level, chunk_idx,
                    ),
                )
                chunk_idx += 1

                overlap_sentence = current_sentences[-1] if current_sentences else ""
                current_sentences = (
                    [overlap_sentence] if overlap_sentence else []
                )
                current_tokens = (
                    self.count_tokens(overlap_sentence)
                    if overlap_sentence
                    else 0
                )

            current_sentences.append(sentence)
            current_tokens += sent_tokens

        if current_sentences:
            chunks.append(
                self._finalize_text_chunk(
                    current_sentences, doc_id, document,
                    regulation_number, breadcrumb, title,
                    source_type, authority_level, chunk_idx,
                ),
            )

        return chunks

    def _hard_split(
        self,
        text: str,
        doc_id: str,
        document: str,
        regulation_number: str,
        breadcrumb: str,
        title: str,
        source_type: str,
        authority_level: str,
        start_index: int,
    ) -> list[PDFChunk]:
        """Last-resort hard split by token count for extremely long text."""
        tokens = self.encoder.encode(text)
        chunks = []
        chunk_idx = start_index

        for i in range(0, len(tokens), self.target_tokens):
            part = self.encoder.decode(tokens[i:i + self.target_tokens])
            embedding_text = self._build_embedding_text(
                document, breadcrumb, title, part,
            )
            token_count = min(self.target_tokens, len(tokens) - i)
            chunk = PDFChunk(
                chunk_id=f"{doc_id}_c{chunk_idx}",
                text=part,
                text_for_embedding=embedding_text,
                document=document,
                regulation_number=regulation_number,
                breadcrumb=breadcrumb,
                url="",
                title=title,
                source_type=source_type,
                authority_level=authority_level,
                chunk_type="regulation",
                token_count=token_count,
            )
            chunks.append(chunk)
            chunk_idx += 1

        return chunks

    def _finalize_text_chunk(
        self,
        sentences: list[str],
        doc_id: str,
        document: str,
        regulation_number: str,
        breadcrumb: str,
        title: str,
        source_type: str,
        authority_level: str,
        chunk_idx: int,
    ) -> PDFChunk:
        """Build a PDFChunk from accumulated sentences."""
        text = " ".join(sentences)
        embedding_text = self._build_embedding_text(
            document, breadcrumb, title, text,
        )
        return PDFChunk(
            chunk_id=f"{doc_id}_c{chunk_idx}",
            text=text,
            text_for_embedding=embedding_text,
            document=document,
            regulation_number=regulation_number,
            breadcrumb=breadcrumb,
            url="",
            title=title,
            source_type=source_type,
            authority_level=authority_level,
            chunk_type="regulation",
            token_count=self.count_tokens(text),
        )

    def _is_empty_table_chunk(self, table: dict) -> bool:
        """Check if a table has no meaningful content for chunking."""
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        if not rows and not headers:
            return True

        non_empty = sum(
            1 for h in headers if str(h).strip() and str(h).strip() not in ("-", "—")
        )
        for row in rows:
            non_empty += sum(
                1 for cell in row if str(cell).strip() and str(cell).strip() not in ("-", "—")
            )
        if non_empty < 2:
            return True

        total = len(headers) + sum(len(row) for row in rows)
        if total > 4 and non_empty / total < 0.1:
            return True

        return False

    def _chunk_table(
        self,
        table: dict,
        doc_id: str,
        document: str,
        regulation_number: str,
        breadcrumb: str,
        title: str,
        source_type: str,
        authority_level: str,
        start_index: int,
    ) -> list[PDFChunk]:
        """Chunk a table into searchable pieces.

        Strategy:
        1. Full table as one Markdown chunk (if under max_tokens)
        2. If over max_tokens, split by row groups
        3. Each cell combination expanded as separate chunk (for fire tables)
        """
        chunks = []
        chunk_idx = start_index

        markdown = table.get("markdown", "")
        if markdown:
            md_tokens = self.count_tokens(markdown)

            if md_tokens <= self.max_tokens:
                embedding_text = self._build_embedding_text(
                    document, breadcrumb, title, markdown,
                )
                chunk = PDFChunk(
                    chunk_id=f"{doc_id}_t{table.get('table_index', 0)}_c{chunk_idx}",
                    text=markdown,
                    text_for_embedding=embedding_text,
                    document=document,
                    regulation_number=regulation_number,
                    breadcrumb=breadcrumb,
                    url="",
                    title=f"{title} (Table)" if title else "Table",
                    source_type=source_type,
                    authority_level=authority_level,
                    chunk_type="table",
                    token_count=md_tokens,
                )
                chunks.append(chunk)
                chunk_idx += 1
            else:
                row_group_chunks = self._split_table_by_rows(
                    table=table,
                    doc_id=doc_id,
                    document=document,
                    regulation_number=regulation_number,
                    breadcrumb=breadcrumb,
                    title=title,
                    source_type=source_type,
                    authority_level=authority_level,
                    start_index=chunk_idx,
                )
                chunks.extend(row_group_chunks)
                chunk_idx += len(row_group_chunks)

        if self.table_cell_expansion:
            descriptions = table.get("descriptions", [])
            for desc in descriptions:
                desc = desc.strip()
                if not desc:
                    continue

                desc_with_source = f"{document} {regulation_number}: {desc}"
                embedding_text = self._build_embedding_text(
                    document, breadcrumb, title, desc_with_source,
                )
                token_count = self.count_tokens(desc_with_source)

                chunk = PDFChunk(
                    chunk_id=f"{doc_id}_t{table.get('table_index', 0)}_cell{chunk_idx}",
                    text=desc_with_source,
                    text_for_embedding=embedding_text,
                    document=document,
                    regulation_number=regulation_number,
                    breadcrumb=breadcrumb,
                    url="",
                    title=f"{title} (Table Cell)" if title else "Table Cell",
                    source_type=source_type,
                    authority_level=authority_level,
                    chunk_type="table_cell",
                    token_count=token_count,
                )
                chunks.append(chunk)
                chunk_idx += 1

        return chunks

    def _split_table_by_rows(
        self,
        table: dict,
        doc_id: str,
        document: str,
        regulation_number: str,
        breadcrumb: str,
        title: str,
        source_type: str,
        authority_level: str,
        start_index: int,
    ) -> list[PDFChunk]:
        """Split a large table into row-group chunks under target_tokens."""
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        table_index = table.get("table_index", 0)

        if not headers:
            return []

        header_line = "| " + " | ".join(str(h) for h in headers) + " |"
        separator = "| " + " | ".join("---" for _ in headers) + " |"
        header_block = f"{header_line}\n{separator}\n"
        header_tokens = self.count_tokens(header_block)

        chunks = []
        chunk_idx = start_index
        current_rows = []
        current_tokens = header_tokens

        for row in rows:
            cells = [str(cell) for cell in row]
            while len(cells) < len(headers):
                cells.append("")
            row_line = "| " + " | ".join(cells) + " |"
            row_tokens = self.count_tokens(row_line)

            if (
                current_tokens + row_tokens > self.target_tokens
                and current_rows
            ):
                table_text = header_block + "\n".join(current_rows)
                embedding_text = self._build_embedding_text(
                    document, breadcrumb, title, table_text,
                )
                chunk = PDFChunk(
                    chunk_id=f"{doc_id}_t{table_index}_rg{chunk_idx}",
                    text=table_text,
                    text_for_embedding=embedding_text,
                    document=document,
                    regulation_number=regulation_number,
                    breadcrumb=breadcrumb,
                    url="",
                    title=f"{title} (Table rows)" if title else "Table rows",
                    source_type=source_type,
                    authority_level=authority_level,
                    chunk_type="table",
                    token_count=self.count_tokens(table_text),
                )
                chunks.append(chunk)
                chunk_idx += 1
                current_rows = []
                current_tokens = header_tokens

            current_rows.append(row_line)
            current_tokens += row_tokens

        if current_rows:
            table_text = header_block + "\n".join(current_rows)
            embedding_text = self._build_embedding_text(
                document, breadcrumb, title, table_text,
            )
            chunk = PDFChunk(
                chunk_id=f"{doc_id}_t{table_index}_rg{chunk_idx}",
                text=table_text,
                text_for_embedding=embedding_text,
                document=document,
                regulation_number=regulation_number,
                breadcrumb=breadcrumb,
                url="",
                title=f"{title} (Table rows)" if title else "Table rows",
                source_type=source_type,
                authority_level=authority_level,
                chunk_type="table",
                token_count=self.count_tokens(table_text),
            )
            chunks.append(chunk)

        return chunks

    def _build_embedding_text(
        self,
        document: str,
        breadcrumb: str,
        title: str,
        text: str,
    ) -> str:
        """Build the text_for_embedding with document context prefix.

        Format: "BV NR467 Part B Chapter 1: <text>"
        """
        prefix_parts = []
        if document:
            prefix_parts.append(document)
        if breadcrumb:
            bc_short = breadcrumb.replace(" > ", " ")
            if bc_short != document:
                prefix_parts.append(bc_short)
        if title and title not in " ".join(prefix_parts):
            prefix_parts.append(title)

        prefix = " ".join(prefix_parts)
        if prefix:
            return f"{prefix}: {text}"
        return text

    def to_dict(self, chunk: PDFChunk) -> dict:
        """Convert PDFChunk to dict for JSONL output."""
        return asdict(chunk)

    def to_legacy_format(self, chunk: PDFChunk) -> dict:
        """Convert PDFChunk to format compatible with existing chunks.jsonl.

        Maps PDFChunk fields to the Chunk format used by RegulationChunker.
        """
        return {
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.chunk_id.rsplit("_c", 1)[0].rsplit("_t", 1)[0],
            "url": chunk.url,
            "text": chunk.text,
            "text_for_embedding": chunk.text_for_embedding,
            "metadata": {
                **chunk.metadata,
                "document": chunk.document,
                "regulation_number": chunk.regulation_number,
                "breadcrumb": chunk.breadcrumb,
                "title": chunk.title,
                "source_type": chunk.source_type,
                "authority_level": chunk.authority_level,
                "chunk_type": chunk.chunk_type,
                "has_table": chunk.chunk_type in ("table", "table_cell"),
            },
            "token_count": chunk.token_count,
        }


def main():
    """CLI entry point: chunk PDF-parsed regulation entries."""
    input_path = "data/parsed/pdf_regulations.jsonl"
    output_path = "data/chunks/pdf_chunks.jsonl"

    if not os.path.exists(input_path):
        console.print(f"[red]Input file not found: {input_path}[/red]")
        sys.exit(1)

    os.makedirs("data/chunks", exist_ok=True)

    chunker = PDFChunker()
    total = sum(1 for _ in open(input_path, encoding="utf-8"))
    total_chunks = 0
    skipped_empty = 0
    seen_ids = set()

    console.print(f"[bold blue]Chunking {total} PDF-parsed entries...[/bold blue]")

    with open(input_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:
        for line in track(fin, total=total, description="Chunking PDFs"):
            entry = json.loads(line)
            chunks = chunker.chunk_regulation(entry)
            for chunk in chunks:
                if len(chunk.text.strip()) < 20:
                    skipped_empty += 1
                    continue
                if chunk.chunk_id in seen_ids:
                    continue
                seen_ids.add(chunk.chunk_id)
                fout.write(
                    json.dumps(chunker.to_dict(chunk), ensure_ascii=False)
                    + "\n",
                )
                total_chunks += 1

    console.print(
        f"[green]Done! {total_chunks} chunks saved to {output_path}[/green]",
    )
    if skipped_empty:
        console.print(
            f"  Skipped {skipped_empty} empty chunks (text < 20 chars)",
        )


if __name__ == "__main__":
    main()
