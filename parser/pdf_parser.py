"""PDF regulation document parser with table-aware extraction using Docling."""
import hashlib
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

BV_HIERARCHY_PATTERN = re.compile(
    r"(?:Part|Pt)\.?\s*([A-Z])\s+"
    r"(?:Chapter|Ch)\.?\s*(\d+)\s+"
    r"(?:Section|Sec)\.?\s*(\d+)\s*"
    r"([\d.]+)?",
    re.IGNORECASE,
)

CLAUSE_NUMBER_PATTERN = re.compile(r"^(\d+(?:\.\d+)*)")

NR_CODE_PATTERN = re.compile(r"NR\s*(\d+)", re.IGNORECASE)

EDITION_PATTERN = re.compile(
    r"(?:Edition|Ed\.?)\s*([\w\s]+\d{4})", re.IGNORECASE,
)

AUTHORITY_MAP = {
    "bv_rules": "classification_rule",
    "iacs": "industry_standard",
    "imo": "international_convention",
}


@dataclass
class ParsedPDFRegulation:
    """A single regulation entry extracted from a PDF."""

    doc_id: str
    title: str
    document: str
    regulation_number: str
    breadcrumb: str
    body_text: str
    page_type: str = "regulation"
    url: str = ""
    source_type: str = "bv_rules"
    parent_doc_id: str = ""
    tables: list = field(default_factory=list)
    cross_references: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class PDFParser:
    """PDF regulation document parser with table-aware extraction.

    Uses Docling (IBM) as primary parser with pdfplumber fallback.
    Handles BV classification rules and general maritime PDFs.
    """

    def __init__(self):
        self._converter = None
        self._pdfplumber_available = None

    @property
    def converter(self):
        """Lazy-load Docling converter to avoid import cost when not needed."""
        if self._converter is None:
            try:
                from docling.document_converter import DocumentConverter

                self._converter = DocumentConverter()
            except ImportError:
                logger.warning(
                    "Docling not installed. Install with: pip install docling"
                )
                self._converter = False
        return self._converter

    @property
    def pdfplumber_available(self):
        """Check pdfplumber availability once."""
        if self._pdfplumber_available is None:
            try:
                import pdfplumber  # noqa: F401

                self._pdfplumber_available = True
            except ImportError:
                self._pdfplumber_available = False
        return self._pdfplumber_available

    def parse_pdf(self, pdf_path: str, source: str = "BV") -> list[ParsedPDFRegulation]:
        """Parse a single PDF, return structured regulation entries.

        Args:
            pdf_path: Path to the PDF file.
            source: Source identifier ("BV", "IACS", etc.).

        Returns:
            List of ParsedPDFRegulation entries extracted from the document.

        Raises:
            FileNotFoundError: If pdf_path does not exist.
            RuntimeError: If neither Docling nor pdfplumber can parse the file.
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        source_type = self._source_to_type(source)
        nr_code = self._extract_nr_code(path.stem)

        docling_result = self._parse_with_docling(path)
        if docling_result is not None:
            return self._process_docling_result(
                docling_result, path, source, source_type, nr_code,
            )

        logger.warning(
            "Docling failed for %s, falling back to pdfplumber", pdf_path,
        )
        return self._parse_with_pdfplumber_fallback(
            path, source, source_type, nr_code,
        )

    def _parse_with_docling(self, path: Path):
        """Attempt to parse PDF with Docling. Returns None on failure."""
        if not self.converter:
            return None
        try:
            result = self.converter.convert(str(path))
            return result
        except Exception as exc:
            logger.error("Docling conversion failed for %s: %s", path, exc)
            return None

    def _process_docling_result(
        self, result, path, source, source_type, nr_code,
    ) -> list[ParsedPDFRegulation]:
        """Convert Docling result into structured regulation entries."""
        doc = result.document
        document_name = self._build_document_name(source, nr_code, path.stem)
        edition = self._extract_edition_from_text(
            doc.export_to_markdown()[:2000],
        )

        tables = self._parse_tables(result)

        sections = self._split_into_sections(doc.export_to_markdown(), source)

        if not sections:
            sections = [{"title": document_name, "body": doc.export_to_markdown(), "hierarchy": {}}]

        entries = []
        for idx, section in enumerate(sections):
            hierarchy = section.get("hierarchy", {})
            reg_number = self._build_regulation_number(hierarchy, source)
            breadcrumb = self._build_breadcrumb(nr_code, hierarchy, source)
            doc_id = self._generate_doc_id(source, nr_code, reg_number, idx)
            parent_doc_id = self._derive_parent_doc_id(doc_id)

            section_tables = self._match_tables_to_section(
                tables, section.get("body", ""),
            )

            cross_refs = self._extract_cross_references(section.get("body", ""))

            entry = ParsedPDFRegulation(
                doc_id=doc_id,
                title=section.get("title", ""),
                document=document_name,
                regulation_number=reg_number,
                breadcrumb=breadcrumb,
                body_text=section.get("body", ""),
                page_type="regulation",
                url="",
                source_type=source_type,
                parent_doc_id=parent_doc_id,
                tables=section_tables,
                cross_references=cross_refs,
                metadata={
                    "nr_code": nr_code,
                    "edition": edition,
                    "authority_level": AUTHORITY_MAP.get(
                        source_type, "classification_rule",
                    ),
                    "pdf_filename": path.name,
                    "source": source,
                },
            )
            entries.append(entry)

        return entries

    def _parse_tables(self, docling_result) -> list[dict]:
        """Extract tables and convert to multiple formats.

        Produces:
        1. Markdown table (for LLM context)
        2. Structured JSON with headers/rows (for precise queries)
        3. Natural language descriptions (for vector search)

        Critical: Fire division tables need each row/column expanded into
        individual searchable entries.
        """
        tables = []
        try:
            doc = docling_result.document
            for table_idx, table_item in enumerate(
                getattr(doc, "tables", []),
            ):
                table_data = self._extract_table_data(table_item)
                if not table_data.get("rows"):
                    continue

                markdown = self._table_to_markdown(table_data)
                descriptions = self._generate_table_descriptions(table_data)

                tables.append({
                    "table_index": table_idx,
                    "caption": table_data.get("caption", ""),
                    "headers": table_data.get("headers", []),
                    "rows": table_data.get("rows", []),
                    "markdown": markdown,
                    "descriptions": descriptions,
                    "row_count": len(table_data.get("rows", [])),
                    "col_count": len(table_data.get("headers", [])),
                })
        except Exception as exc:
            logger.error("Table extraction failed: %s", exc)

        return tables

    def _extract_table_data(self, table_item) -> dict:
        """Extract structured data from a Docling table element."""
        try:
            if hasattr(table_item, "export_to_dataframe"):
                df = table_item.export_to_dataframe()
                headers = list(df.columns)
                rows = df.values.tolist()
                caption = getattr(table_item, "caption", "") or ""
                return {
                    "caption": caption,
                    "headers": headers,
                    "rows": [list(row) for row in rows],
                }

            if hasattr(table_item, "data"):
                data = table_item.data
                if isinstance(data, list) and data:
                    headers = (
                        [str(cell) for cell in data[0]]
                        if data
                        else []
                    )
                    rows = [
                        [str(cell) for cell in row]
                        for row in data[1:]
                    ]
                    return {
                        "caption": "",
                        "headers": headers,
                        "rows": rows,
                    }
        except Exception as exc:
            logger.debug("Table data extraction error: %s", exc)

        return {"caption": "", "headers": [], "rows": []}

    def _table_to_markdown(self, table_data: dict) -> str:
        """Convert structured table data to Markdown format."""
        headers = table_data.get("headers", [])
        rows = table_data.get("rows", [])

        if not headers and not rows:
            return ""

        lines = []
        if headers:
            lines.append("| " + " | ".join(str(h) for h in headers) + " |")
            lines.append(
                "| " + " | ".join("---" for _ in headers) + " |",
            )

        for row in rows:
            cells = [str(cell) for cell in row]
            while len(cells) < len(headers):
                cells.append("")
            lines.append("| " + " | ".join(cells) + " |")

        return "\n".join(lines)

    def _generate_table_descriptions(self, table_data: dict) -> list[str]:
        """Convert table cells to natural language descriptions for embedding.

        This is critical for fire division tables where each cell combination
        must be individually searchable, e.g.:
        "According to BV NR467, the fire integrity between a galley and
        corridor is A-0"
        """
        headers = table_data.get("headers", [])
        rows = table_data.get("rows", [])
        caption = table_data.get("caption", "")
        descriptions = []

        if len(headers) < 2 or not rows:
            if rows:
                for row in rows:
                    row_text = ", ".join(str(cell) for cell in row if cell)
                    if row_text:
                        descriptions.append(row_text)
            return descriptions

        row_header_idx = 0
        col_start_idx = 1

        is_matrix = self._is_matrix_table(headers, rows)

        if is_matrix:
            for row in rows:
                row_label = str(row[row_header_idx]) if row else ""
                for col_idx in range(col_start_idx, min(len(row), len(headers))):
                    col_label = str(headers[col_idx])
                    cell_value = str(row[col_idx]) if col_idx < len(row) else ""

                    if not cell_value or cell_value.strip() in ("-", "N/A", ""):
                        continue

                    prefix = f"From {caption}: " if caption else ""
                    desc = (
                        f"{prefix}The value for {row_label} and "
                        f"{col_label} is {cell_value}"
                    )
                    descriptions.append(desc)
        else:
            for row in rows:
                parts = []
                for col_idx, header in enumerate(headers):
                    if col_idx < len(row):
                        cell_val = str(row[col_idx])
                        if cell_val and cell_val.strip() not in ("-", "N/A", ""):
                            parts.append(f"{header}: {cell_val}")
                if parts:
                    prefix = f"From {caption}: " if caption else ""
                    descriptions.append(prefix + "; ".join(parts))

        return descriptions

    def _is_matrix_table(self, headers: list, rows: list) -> bool:
        """Detect if a table is a matrix/cross-reference style table.

        Matrix tables typically have the same labels in both row headers
        and column headers (like fire division tables).
        """
        if len(headers) < 3:
            return False

        row_labels = {str(row[0]).strip().lower() for row in rows if row}
        col_labels = {str(h).strip().lower() for h in headers[1:]}

        overlap = row_labels & col_labels
        if len(overlap) > min(len(row_labels), len(col_labels)) * 0.3:
            return True

        fire_keywords = {"a-60", "a-15", "a-0", "b-15", "b-0", "c", "f"}
        all_values = set()
        for row in rows:
            for cell in row[1:]:
                all_values.add(str(cell).strip().lower())
        if all_values & fire_keywords:
            return True

        return False

    def _extract_hierarchy(self, text: str, source: str) -> dict:
        """Extract regulation hierarchy from text content.

        BV format: Part > Chapter > Section > 1.2.3
        IACS format: Section > 1.2.3
        """
        hierarchy = {
            "part": "",
            "chapter": "",
            "section": "",
            "clause": "",
        }

        if source.upper() == "BV":
            match = BV_HIERARCHY_PATTERN.search(text)
            if match:
                hierarchy = {
                    **hierarchy,
                    "part": match.group(1) or "",
                    "chapter": match.group(2) or "",
                    "section": match.group(3) or "",
                    "clause": match.group(4) or "",
                }
                return hierarchy

            part_match = re.search(
                r"(?:Part|Pt)\.?\s*([A-Z])", text, re.IGNORECASE,
            )
            if part_match:
                hierarchy = {**hierarchy, "part": part_match.group(1)}

            ch_match = re.search(
                r"(?:Chapter|Ch)\.?\s*(\d+)", text, re.IGNORECASE,
            )
            if ch_match:
                hierarchy = {**hierarchy, "chapter": ch_match.group(1)}

            sec_match = re.search(
                r"(?:Section|Sec)\.?\s*(\d+)", text, re.IGNORECASE,
            )
            if sec_match:
                hierarchy = {**hierarchy, "section": sec_match.group(1)}
        else:
            sec_match = re.search(
                r"(?:Section|Sec)\.?\s*(\d+)", text, re.IGNORECASE,
            )
            if sec_match:
                hierarchy = {**hierarchy, "section": sec_match.group(1)}

        clause_match = CLAUSE_NUMBER_PATTERN.search(text.split("\n")[0])
        if clause_match:
            hierarchy = {**hierarchy, "clause": clause_match.group(1)}

        return hierarchy

    def _split_into_sections(
        self, markdown_text: str, source: str,
    ) -> list[dict]:
        """Split Markdown text into regulation sections at heading boundaries.

        Splits on lines starting with # or ## that look like regulation
        headings (Part, Chapter, Section, numbered clauses).
        """
        heading_pattern = re.compile(
            r"^(#{1,4})\s+(.+)$", re.MULTILINE,
        )
        matches = list(heading_pattern.finditer(markdown_text))

        if not matches:
            return self._split_by_clause_numbers(markdown_text, source)

        sections = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
            heading_text = match.group(2).strip()
            body = markdown_text[start:end].strip()

            hierarchy = self._extract_hierarchy(heading_text, source)

            sections.append({
                "title": heading_text,
                "body": body,
                "hierarchy": hierarchy,
            })

        return sections

    def _split_by_clause_numbers(
        self, text: str, source: str,
    ) -> list[dict]:
        """Split text by numbered clause patterns (1.1, 1.2, etc.)."""
        clause_pattern = re.compile(
            r"^(\d+\.\d+(?:\.\d+)*)\s+", re.MULTILINE,
        )
        matches = list(clause_pattern.finditer(text))

        if not matches:
            return []

        sections = []
        for i, match in enumerate(matches):
            start = match.start()
            end = (
                matches[i + 1].start()
                if i + 1 < len(matches)
                else len(text)
            )
            clause_num = match.group(1)
            body = text[start:end].strip()
            first_line = body.split("\n")[0]
            title_text = first_line[:120].strip()

            hierarchy = self._extract_hierarchy(body[:500], source)
            hierarchy = {**hierarchy, "clause": clause_num}

            sections.append({
                "title": title_text,
                "body": body,
                "hierarchy": hierarchy,
            })

        return sections

    def _parse_with_pdfplumber_fallback(
        self, path: Path, source: str, source_type: str, nr_code: str,
    ) -> list[ParsedPDFRegulation]:
        """Fallback parser using pdfplumber when Docling fails."""
        if not self.pdfplumber_available:
            raise RuntimeError(
                f"Cannot parse {path}: Neither Docling nor pdfplumber available. "
                "Install one: pip install docling OR pip install pdfplumber"
            )

        import pdfplumber

        document_name = self._build_document_name(source, nr_code, path.stem)
        entries = []
        page_batch_size = 50

        with pdfplumber.open(str(path)) as pdf:
            total_pages = len(pdf.pages)
            logger.info(
                "Parsing %s with pdfplumber (%d pages)", path.name, total_pages,
            )

            for batch_start in range(0, total_pages, page_batch_size):
                batch_end = min(batch_start + page_batch_size, total_pages)
                batch_text_parts = []
                batch_tables = []

                for page_num in range(batch_start, batch_end):
                    page = pdf.pages[page_num]

                    text = page.extract_text() or ""
                    batch_text_parts.append(text)

                    for raw_table in (page.extract_tables() or []):
                        table_data = self._normalize_pdfplumber_table(
                            raw_table,
                        )
                        if table_data.get("rows"):
                            markdown = self._table_to_markdown(table_data)
                            descriptions = self._generate_table_descriptions(
                                table_data,
                            )
                            batch_tables.append({
                                "table_index": len(batch_tables),
                                "caption": "",
                                "headers": table_data.get("headers", []),
                                "rows": table_data.get("rows", []),
                                "markdown": markdown,
                                "descriptions": descriptions,
                                "row_count": len(table_data.get("rows", [])),
                                "col_count": len(
                                    table_data.get("headers", []),
                                ),
                                "page": page_num + 1,
                            })

                batch_text = "\n".join(batch_text_parts)
                sections = self._split_into_sections(batch_text, source)

                if not sections:
                    sections = [{
                        "title": f"{document_name} pages {batch_start + 1}-{batch_end}",
                        "body": batch_text,
                        "hierarchy": {},
                    }]

                for idx, section in enumerate(sections):
                    hierarchy = section.get("hierarchy", {})
                    reg_number = self._build_regulation_number(
                        hierarchy, source,
                    )
                    breadcrumb = self._build_breadcrumb(
                        nr_code, hierarchy, source,
                    )
                    global_idx = batch_start + idx
                    doc_id = self._generate_doc_id(
                        source, nr_code, reg_number, global_idx,
                    )
                    cross_refs = self._extract_cross_references(
                        section.get("body", ""),
                    )

                    entry = ParsedPDFRegulation(
                        doc_id=doc_id,
                        title=section.get("title", ""),
                        document=document_name,
                        regulation_number=reg_number,
                        breadcrumb=breadcrumb,
                        body_text=section.get("body", ""),
                        page_type="regulation",
                        url="",
                        source_type=source_type,
                        parent_doc_id=self._derive_parent_doc_id(doc_id),
                        tables=batch_tables if idx == 0 else [],
                        cross_references=cross_refs,
                        metadata={
                            "nr_code": nr_code,
                            "edition": "",
                            "authority_level": AUTHORITY_MAP.get(
                                source_type, "classification_rule",
                            ),
                            "pdf_filename": path.name,
                            "source": source,
                            "pages": f"{batch_start + 1}-{batch_end}",
                        },
                    )
                    entries.append(entry)

        return entries

    def _normalize_pdfplumber_table(self, raw_table: list) -> dict:
        """Convert pdfplumber raw table to standardized format."""
        if not raw_table or len(raw_table) < 2:
            return {"caption": "", "headers": [], "rows": []}

        headers = [str(cell or "") for cell in raw_table[0]]
        rows = [
            [str(cell or "") for cell in row]
            for row in raw_table[1:]
        ]
        return {"caption": "", "headers": headers, "rows": rows}

    def _match_tables_to_section(
        self, all_tables: list[dict], section_body: str,
    ) -> list[dict]:
        """Match tables to a section based on content overlap."""
        if not all_tables:
            return []

        matched = []
        section_lower = section_body.lower()
        for table in all_tables:
            caption = table.get("caption", "").lower()
            if caption and caption in section_lower:
                matched.append(table)
                continue

            headers = table.get("headers", [])
            header_text = " ".join(str(h).lower() for h in headers)
            if any(word in section_lower for word in header_text.split() if len(word) > 3):
                matched.append(table)

        return matched

    def _extract_cross_references(self, text: str) -> list[dict]:
        """Extract cross-references to other regulations from text."""
        refs = []
        patterns = [
            re.compile(
                r"(?:see|refer(?:ence)?\s+to|in\s+accordance\s+with|as\s+required\s+by)\s+"
                r"((?:Part|Pt|Chapter|Ch|Section|Sec|Regulation|Reg|Rule)\s*\.?\s*[\w\d./-]+)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(SOLAS\s+(?:Chapter|Ch\.?)\s*[\w\d./-]+)", re.IGNORECASE,
            ),
            re.compile(
                r"(MARPOL\s+Annex\s+[\w\d./-]+)", re.IGNORECASE,
            ),
            re.compile(
                r"((?:NR|UR)\s*\d+[A-Z]?\s*(?:,\s*(?:Part|Pt|Ch|Sec)[\s.]*[\w\d./-]+)?)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(IACS\s+(?:UR|UI|PR|Rec)\s*\d+[A-Z]?)", re.IGNORECASE,
            ),
        ]

        seen = set()
        for pattern in patterns:
            for match in pattern.finditer(text):
                ref_text = match.group(1).strip()
                if ref_text not in seen:
                    seen.add(ref_text)

                    context_start = max(0, match.start() - 50)
                    context_end = min(len(text), match.end() + 50)
                    context = text[context_start:context_end].strip()

                    refs.append({
                        "target_text": ref_text,
                        "target_url": "",
                        "context": context,
                    })

        return refs

    def _source_to_type(self, source: str) -> str:
        """Map source identifier to source_type."""
        source_map = {
            "BV": "bv_rules",
            "IACS": "iacs",
            "IMO": "imo",
        }
        return source_map.get(source.upper(), "bv_rules")

    def _extract_nr_code(self, stem: str) -> str:
        """Extract NR code from filename stem."""
        match = NR_CODE_PATTERN.search(stem)
        return f"NR{match.group(1)}" if match else stem.upper()

    def _extract_edition_from_text(self, text: str) -> str:
        """Extract edition info from document text."""
        match = EDITION_PATTERN.search(text)
        return match.group(1).strip() if match else ""

    def _build_document_name(
        self, source: str, nr_code: str, filename_stem: str,
    ) -> str:
        """Build a human-readable document name."""
        if source.upper() == "BV":
            return f"BV {nr_code}"
        if source.upper() == "IACS":
            return f"IACS {nr_code}"
        return filename_stem

    def _build_regulation_number(
        self, hierarchy: dict, source: str,
    ) -> str:
        """Build a standardized regulation number from hierarchy."""
        parts = []
        if source.upper() == "BV":
            if hierarchy.get("part"):
                parts.append(f"Pt.{hierarchy['part']}")
            if hierarchy.get("chapter"):
                parts.append(f"Ch.{hierarchy['chapter']}")
            if hierarchy.get("section"):
                parts.append(f"Sec.{hierarchy['section']}")
            if hierarchy.get("clause"):
                parts.append(hierarchy["clause"])
        else:
            if hierarchy.get("section"):
                parts.append(f"Sec.{hierarchy['section']}")
            if hierarchy.get("clause"):
                parts.append(hierarchy["clause"])

        return " ".join(parts)

    def _build_breadcrumb(
        self, nr_code: str, hierarchy: dict, source: str,
    ) -> str:
        """Build breadcrumb trail from hierarchy."""
        crumbs = [nr_code]

        if source.upper() == "BV":
            if hierarchy.get("part"):
                crumbs.append(f"Part {hierarchy['part']}")
            if hierarchy.get("chapter"):
                crumbs.append(f"Chapter {hierarchy['chapter']}")
            if hierarchy.get("section"):
                crumbs.append(f"Section {hierarchy['section']}")
        else:
            if hierarchy.get("section"):
                crumbs.append(f"Section {hierarchy['section']}")

        if hierarchy.get("clause"):
            crumbs.append(hierarchy["clause"])

        return " > ".join(crumbs)

    def _generate_doc_id(
        self, source: str, nr_code: str, reg_number: str, idx: int,
    ) -> str:
        """Generate a unique document ID."""
        source_prefix = source.upper()
        reg_clean = re.sub(r"[\s.]+", "_", reg_number) if reg_number else ""

        if reg_clean:
            doc_id = f"{source_prefix}_{nr_code}_{reg_clean}"
        else:
            hash_suffix = hashlib.md5(
                f"{nr_code}_{idx}".encode(),
            ).hexdigest()[:8]
            doc_id = f"{source_prefix}_{nr_code}_{hash_suffix}"

        return doc_id

    def _derive_parent_doc_id(self, doc_id: str) -> str:
        """Derive parent doc_id by removing the last hierarchy segment."""
        parts = doc_id.rsplit("_", 1)
        if len(parts) > 1:
            return parts[0]
        return ""

    def to_dict(self, entry: ParsedPDFRegulation) -> dict:
        """Convert a ParsedPDFRegulation to a dict for JSONL output."""
        return asdict(entry)
