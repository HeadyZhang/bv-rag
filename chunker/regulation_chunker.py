"""Maritime regulation chunker with tiktoken-based token counting."""
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field

import tiktoken
from rich.console import Console
from rich.progress import track

console = Console()


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    url: str
    text: str
    text_for_embedding: str
    metadata: dict = field(default_factory=dict)
    token_count: int = 0


class RegulationChunker:
    def __init__(
        self,
        target_tokens: int = 512,
        max_tokens: int = 1024,
        overlap_tokens: int = 64,
    ):
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))

    def chunk_document(self, parsed_doc: dict) -> list[Chunk]:
        page_type = parsed_doc.get("page_type", "")
        if page_type in ("index", "collection"):
            return []

        doc_id = parsed_doc["doc_id"]
        url = parsed_doc["url"]
        body_text = parsed_doc.get("body_text", "")
        body_structured = parsed_doc.get("body_structured", [])
        title = parsed_doc.get("title", "")
        breadcrumb = parsed_doc.get("breadcrumb", "")

        if not body_text or not body_text.strip():
            return []

        metadata = self._build_metadata(parsed_doc)
        breadcrumb_short = self._shorten_breadcrumb(breadcrumb, parsed_doc.get("document", ""))

        if page_type == "footnote":
            chunks = self._chunk_as_single(doc_id, url, body_text, title, breadcrumb_short, metadata)
        elif body_structured:
            chunks = self._chunk_structured(doc_id, url, body_structured, title, breadcrumb_short, metadata)
        else:
            chunks = self._chunk_by_sentences(doc_id, url, body_text, title, breadcrumb_short, metadata)

        chunks = self._force_split_oversized(chunks)
        return chunks

    def _build_metadata(self, doc: dict) -> dict:
        regulation_number = self._standardize_regulation_number(
            doc.get("document", ""),
            doc.get("chapter", ""),
            doc.get("regulation", ""),
        )
        return {
            "collection": doc.get("collection", ""),
            "document": doc.get("document", ""),
            "chapter": doc.get("chapter", ""),
            "part": doc.get("part", ""),
            "regulation": doc.get("regulation", ""),
            "title": doc.get("title", ""),
            "breadcrumb": doc.get("breadcrumb", ""),
            "page_type": doc.get("page_type", ""),
            "regulation_number": regulation_number,
            "url": doc.get("url", ""),
            "has_table": any(
                item.get("type") == "table"
                for item in doc.get("body_structured", [])
            ),
        }

    def _standardize_regulation_number(self, document: str, chapter: str, regulation: str) -> str:
        if not document:
            return ""

        parts = []
        if chapter:
            ch_match = re.search(r"(Chapter|Annex)\s+([\w\-]+)", chapter, re.IGNORECASE)
            if ch_match:
                parts.append(ch_match.group(2))

        if regulation:
            reg_match = re.search(r"(?:Regulation|Rule|Section)\s+([\w\-/.]+)", regulation, re.IGNORECASE)
            if reg_match:
                parts.append(reg_match.group(1))

        if parts:
            return f"{document} {'/'.join(parts)}"
        return document

    def _shorten_breadcrumb(self, breadcrumb: str, document: str) -> str:
        if "---" in breadcrumb:
            content = breadcrumb.split("---")[-1].strip()
        else:
            content = breadcrumb
        segments = [s.strip() for s in content.split("-") if s.strip()]
        relevant = []
        found_doc = False
        for seg in segments:
            if document and document.upper() in seg.upper():
                found_doc = True
            if found_doc:
                relevant.append(seg)
        if relevant:
            return " > ".join(relevant)
        return " > ".join(segments[-4:]) if len(segments) > 4 else " > ".join(segments)

    def _make_embedding_text(self, breadcrumb_short: str, title: str, text: str) -> str:
        prefix = f"[{breadcrumb_short}]" if breadcrumb_short else ""
        if title:
            prefix = f"{prefix} {title}" if prefix else title
        if prefix:
            return f"{prefix}\n\n{text}"
        return text

    def _chunk_as_single(self, doc_id, url, body_text, title, breadcrumb_short, metadata):
        text = body_text.strip()
        token_count = self.count_tokens(text)
        if token_count > self.max_tokens:
            return self._chunk_by_sentences(doc_id, url, text, title, breadcrumb_short, metadata)

        embedding_text = self._make_embedding_text(breadcrumb_short, title, text)
        return [Chunk(
            chunk_id=f"{doc_id}__chunk_0",
            doc_id=doc_id,
            url=url,
            text=text,
            text_for_embedding=embedding_text,
            metadata=metadata,
            token_count=token_count,
        )]

    def _chunk_structured(self, doc_id, url, body_structured, title, breadcrumb_short, metadata):
        chunks = []
        current_texts = []
        current_tokens = 0
        chunk_index = 0
        overlap_text = ""

        for item in body_structured:
            item_text = item.get("text", "").strip()
            if not item_text:
                continue

            item_tokens = self.count_tokens(item_text)

            if current_tokens + item_tokens > self.target_tokens and current_texts:
                chunk_text = "\n".join(current_texts)
                embedding_text = self._make_embedding_text(breadcrumb_short, title, chunk_text)
                chunks.append(Chunk(
                    chunk_id=f"{doc_id}__chunk_{chunk_index}",
                    doc_id=doc_id,
                    url=url,
                    text=chunk_text,
                    text_for_embedding=embedding_text,
                    metadata=metadata,
                    token_count=self.count_tokens(chunk_text),
                ))
                chunk_index += 1

                last_text = current_texts[-1]
                overlap_text = last_text[:200] if len(last_text) > 200 else last_text
                current_texts = [overlap_text] if overlap_text else []
                current_tokens = self.count_tokens(overlap_text) if overlap_text else 0

            current_texts.append(item_text)
            current_tokens += item_tokens

        if current_texts:
            chunk_text = "\n".join(current_texts)
            embedding_text = self._make_embedding_text(breadcrumb_short, title, chunk_text)
            chunks.append(Chunk(
                chunk_id=f"{doc_id}__chunk_{chunk_index}",
                doc_id=doc_id,
                url=url,
                text=chunk_text,
                text_for_embedding=embedding_text,
                metadata=metadata,
                token_count=self.count_tokens(chunk_text),
            ))

        return chunks

    def _chunk_by_sentences(self, doc_id, url, body_text, title, breadcrumb_short, metadata):
        sentences = re.split(r"(?<=[.!?])\s+", body_text)
        chunks = []
        current_sentences = []
        current_tokens = 0
        chunk_index = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sent_tokens = self.count_tokens(sentence)

            if current_tokens + sent_tokens > self.target_tokens and current_sentences:
                chunk_text = " ".join(current_sentences)
                embedding_text = self._make_embedding_text(breadcrumb_short, title, chunk_text)
                chunks.append(Chunk(
                    chunk_id=f"{doc_id}__chunk_{chunk_index}",
                    doc_id=doc_id,
                    url=url,
                    text=chunk_text,
                    text_for_embedding=embedding_text,
                    metadata=metadata,
                    token_count=self.count_tokens(chunk_text),
                ))
                chunk_index += 1

                overlap_sent = current_sentences[-1] if current_sentences else ""
                current_sentences = [overlap_sent] if overlap_sent else []
                current_tokens = self.count_tokens(overlap_sent) if overlap_sent else 0

            current_sentences.append(sentence)
            current_tokens += sent_tokens

        if current_sentences:
            chunk_text = " ".join(current_sentences)
            embedding_text = self._make_embedding_text(breadcrumb_short, title, chunk_text)
            chunks.append(Chunk(
                chunk_id=f"{doc_id}__chunk_{chunk_index}",
                doc_id=doc_id,
                url=url,
                text=chunk_text,
                text_for_embedding=embedding_text,
                metadata=metadata,
                token_count=self.count_tokens(chunk_text),
            ))

        return chunks

    def _force_split_oversized(self, chunks: list[Chunk]) -> list[Chunk]:
        """Split any chunk exceeding max_tokens at sentence/line boundaries."""
        result = []
        for chunk in chunks:
            if chunk.token_count <= self.max_tokens:
                result.append(chunk)
                continue

            # Split by newlines first (preserves table rows), then by sentences
            lines = chunk.text.split("\n")
            segments = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if self.count_tokens(line) <= self.max_tokens:
                    segments.append(line)
                else:
                    # Line itself is too long — break by sentences
                    sentences = re.split(r"(?<=[.!?;])\s+", line)
                    for sent in sentences:
                        sent = sent.strip()
                        if not sent:
                            continue
                        if self.count_tokens(sent) <= self.max_tokens:
                            segments.append(sent)
                        else:
                            # Last resort: hard split by token count
                            tokens = self.encoder.encode(sent)
                            for i in range(0, len(tokens), self.target_tokens):
                                part = self.encoder.decode(tokens[i:i + self.target_tokens])
                                segments.append(part)

            # Reassemble segments into chunks under max_tokens
            current_segs = []
            current_tokens = 0
            sub_index = 0

            for seg in segments:
                seg_tokens = self.count_tokens(seg)
                if current_tokens + seg_tokens > self.target_tokens and current_segs:
                    sub_text = "\n".join(current_segs)
                    sub_emb = self._make_embedding_text(
                        chunk.metadata.get("breadcrumb", ""),
                        chunk.metadata.get("title", ""),
                        sub_text,
                    )
                    result.append(Chunk(
                        chunk_id=f"{chunk.chunk_id}_s{sub_index}",
                        doc_id=chunk.doc_id,
                        url=chunk.url,
                        text=sub_text,
                        text_for_embedding=sub_emb,
                        metadata=chunk.metadata,
                        token_count=self.count_tokens(sub_text),
                    ))
                    sub_index += 1
                    current_segs = []
                    current_tokens = 0

                current_segs.append(seg)
                current_tokens += seg_tokens

            if current_segs:
                sub_text = "\n".join(current_segs)
                sub_emb = self._make_embedding_text(
                    chunk.metadata.get("breadcrumb", ""),
                    chunk.metadata.get("title", ""),
                    sub_text,
                )
                result.append(Chunk(
                    chunk_id=f"{chunk.chunk_id}_s{sub_index}",
                    doc_id=chunk.doc_id,
                    url=chunk.url,
                    text=sub_text,
                    text_for_embedding=sub_emb,
                    metadata=chunk.metadata,
                    token_count=self.count_tokens(sub_text),
                ))

        return result


def main():
    input_path = "data/parsed/regulations.jsonl"
    output_path = "data/chunks/chunks.jsonl"

    if not os.path.exists(input_path):
        console.print(f"[red]Input file not found: {input_path}[/red]")
        sys.exit(1)

    os.makedirs("data/chunks", exist_ok=True)

    chunker = RegulationChunker()
    total = sum(1 for _ in open(input_path, encoding="utf-8"))
    total_chunks = 0
    skipped_empty = 0
    skipped_dup = 0
    seen_ids = set()

    console.print(f"[bold blue]Chunking {total} documents...[/bold blue]")

    with open(input_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:
        for line in track(fin, total=total, description="Chunking"):
            doc = json.loads(line)
            chunks = chunker.chunk_document(doc)
            for chunk in chunks:
                if len(chunk.text.strip()) < 20:
                    skipped_empty += 1
                    continue
                if chunk.chunk_id in seen_ids:
                    skipped_dup += 1
                    continue
                seen_ids.add(chunk.chunk_id)
                fout.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
                total_chunks += 1

    console.print(f"[green]Done! {total_chunks} chunks saved to {output_path}[/green]")
    if skipped_empty:
        console.print(f"  Skipped {skipped_empty} empty chunks (text < 20 chars)")
    if skipped_dup:
        console.print(f"  Skipped {skipped_dup} duplicate chunk IDs")


if __name__ == "__main__":
    main()
