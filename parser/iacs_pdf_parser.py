"""IACS-specific PDF parser for Unified Requirements and Interpretations."""
import logging
import re
from pathlib import Path

from parser.pdf_parser import AUTHORITY_MAP, PDFParser, ParsedPDFRegulation

logger = logging.getLogger(__name__)

UR_CODE_PATTERN = re.compile(
    r"((?:UR|UI|PR|Rec)\s*[A-Z]?\d+[A-Z]?)", re.IGNORECASE,
)

APPLICABLE_DATE_PATTERN = re.compile(
    r"(?:applicable|effective|entry\s+into\s+force|valid\s+from)\s*[:;]?\s*"
    r"(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2}|\w+\s+\d{4})",
    re.IGNORECASE,
)

IMO_CONVENTION_PATTERN = re.compile(
    r"(SOLAS|MARPOL|STCW|COLREG|Load\s*Lines?|LL|Tonnage|BWM|"
    r"ISM|ISPS|LSA|FSS|FTP|IBC|IGC|IGF|IMDG|Polar\s*Code)",
    re.IGNORECASE,
)

IACS_SCOPE_PATTERN = re.compile(
    r"(?:^|\n)(?:1\.?\s*)?(?:Scope|Application|Applicability)\s*\n",
    re.IGNORECASE,
)

IACS_CLAUSE_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)*)\s+(.+)",
    re.MULTILINE,
)


class IACSPDFParser(PDFParser):
    """Parser for IACS Unified Requirements, Interpretations, and Procedures.

    IACS documents are shorter (typically 5-30 pages) and follow a standard
    format: title + scope + numbered clauses, often referencing specific
    IMO conventions.
    """

    def parse_pdf(
        self, pdf_path: str, source: str = "IACS",
    ) -> list[ParsedPDFRegulation]:
        """Parse an IACS PDF document.

        Args:
            pdf_path: Path to the IACS PDF file.
            source: Source identifier (defaults to "IACS").

        Returns:
            List of ParsedPDFRegulation entries.
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        source_type = "iacs"
        ur_code = self._extract_ur_code(path.stem)

        docling_result = self._parse_with_docling(path)
        if docling_result is not None:
            return self._process_iacs_docling(
                docling_result, path, ur_code, source_type,
            )

        logger.warning(
            "Docling failed for %s, falling back to pdfplumber",
            pdf_path,
        )
        return self._parse_iacs_pdfplumber(path, ur_code, source_type)

    def _process_iacs_docling(
        self, result, path: Path, ur_code: str, source_type: str,
    ) -> list[ParsedPDFRegulation]:
        """Process Docling result with IACS-specific extraction."""
        doc = result.document
        full_text = doc.export_to_markdown()

        document_name = f"IACS {ur_code}"
        applicable_date = self._extract_applicable_date(full_text)
        related_conventions = self._extract_related_conventions(full_text)
        scope_text = self._extract_scope(full_text)
        tables = self._parse_tables(result)

        sections = self._split_iacs_sections(full_text, ur_code)

        if not sections:
            sections = [{
                "title": document_name,
                "body": full_text,
                "clause_number": "",
            }]

        entries = []

        if scope_text:
            scope_entry = self._build_iacs_entry(
                doc_id=f"IACS_{ur_code}_scope",
                title=f"{ur_code} - Scope",
                document_name=document_name,
                regulation_number=f"{ur_code} Scope",
                breadcrumb=f"IACS > {ur_code} > Scope",
                body_text=scope_text,
                source_type=source_type,
                path=path,
                ur_code=ur_code,
                applicable_date=applicable_date,
                related_conventions=related_conventions,
                tables=[],
            )
            entries.append(scope_entry)

        for idx, section in enumerate(sections):
            clause_num = section.get("clause_number", "")
            reg_number = f"{ur_code} {clause_num}" if clause_num else ur_code
            breadcrumb = f"IACS > {ur_code}"
            if clause_num:
                breadcrumb = f"{breadcrumb} > {clause_num}"

            doc_id = (
                f"IACS_{ur_code}_{clause_num.replace('.', '_')}"
                if clause_num
                else f"IACS_{ur_code}_{idx}"
            )

            section_tables = self._match_tables_to_section(
                tables, section.get("body", ""),
            )

            entry = self._build_iacs_entry(
                doc_id=doc_id,
                title=section.get("title", ""),
                document_name=document_name,
                regulation_number=reg_number,
                breadcrumb=breadcrumb,
                body_text=section.get("body", ""),
                source_type=source_type,
                path=path,
                ur_code=ur_code,
                applicable_date=applicable_date,
                related_conventions=related_conventions,
                tables=section_tables,
            )
            entries.append(entry)

        return entries

    def _parse_iacs_pdfplumber(
        self, path: Path, ur_code: str, source_type: str,
    ) -> list[ParsedPDFRegulation]:
        """Fallback IACS parsing with pdfplumber."""
        if not self.pdfplumber_available:
            raise RuntimeError(
                f"Cannot parse {path}: Neither Docling nor pdfplumber available."
            )

        import pdfplumber

        document_name = f"IACS {ur_code}"
        full_text_parts = []
        all_tables = []

        with pdfplumber.open(str(path)) as pdf:
            logger.info(
                "Parsing IACS %s with pdfplumber (%d pages)",
                path.name, len(pdf.pages),
            )
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                full_text_parts.append(text)

                for raw_table in (page.extract_tables() or []):
                    table_data = self._normalize_pdfplumber_table(raw_table)
                    if table_data.get("rows"):
                        markdown = self._table_to_markdown(table_data)
                        descriptions = self._generate_table_descriptions(
                            table_data,
                        )
                        all_tables.append({
                            "table_index": len(all_tables),
                            "caption": "",
                            "headers": table_data.get("headers", []),
                            "rows": table_data.get("rows", []),
                            "markdown": markdown,
                            "descriptions": descriptions,
                            "row_count": len(table_data.get("rows", [])),
                            "col_count": len(table_data.get("headers", [])),
                            "page": page_num + 1,
                        })

        full_text = "\n".join(full_text_parts)
        applicable_date = self._extract_applicable_date(full_text)
        related_conventions = self._extract_related_conventions(full_text)

        sections = self._split_iacs_sections(full_text, ur_code)
        if not sections:
            sections = [{
                "title": document_name,
                "body": full_text,
                "clause_number": "",
            }]

        entries = []
        for idx, section in enumerate(sections):
            clause_num = section.get("clause_number", "")
            reg_number = f"{ur_code} {clause_num}" if clause_num else ur_code
            breadcrumb = f"IACS > {ur_code}"
            if clause_num:
                breadcrumb = f"{breadcrumb} > {clause_num}"

            doc_id = (
                f"IACS_{ur_code}_{clause_num.replace('.', '_')}"
                if clause_num
                else f"IACS_{ur_code}_{idx}"
            )

            section_tables = self._match_tables_to_section(
                all_tables, section.get("body", ""),
            )

            entry = self._build_iacs_entry(
                doc_id=doc_id,
                title=section.get("title", ""),
                document_name=document_name,
                regulation_number=reg_number,
                breadcrumb=breadcrumb,
                body_text=section.get("body", ""),
                source_type=source_type,
                path=path,
                ur_code=ur_code,
                applicable_date=applicable_date,
                related_conventions=related_conventions,
                tables=section_tables,
            )
            entries.append(entry)

        return entries

    def _build_iacs_entry(
        self,
        doc_id: str,
        title: str,
        document_name: str,
        regulation_number: str,
        breadcrumb: str,
        body_text: str,
        source_type: str,
        path: Path,
        ur_code: str,
        applicable_date: str,
        related_conventions: list[str],
        tables: list[dict],
    ) -> ParsedPDFRegulation:
        """Build a ParsedPDFRegulation for an IACS section."""
        cross_refs = self._extract_cross_references(body_text)

        return ParsedPDFRegulation(
            doc_id=doc_id,
            title=title,
            document=document_name,
            regulation_number=regulation_number,
            breadcrumb=breadcrumb,
            body_text=body_text,
            page_type="regulation",
            url="",
            source_type=source_type,
            parent_doc_id=f"IACS_{ur_code}",
            tables=tables,
            cross_references=cross_refs,
            metadata={
                "nr_code": "",
                "ur_code": ur_code,
                "edition": "",
                "authority_level": AUTHORITY_MAP.get(
                    source_type, "industry_standard",
                ),
                "applicable_date": applicable_date,
                "related_conventions": related_conventions,
                "pdf_filename": path.name,
                "source": "IACS",
            },
        )

    def _extract_ur_code(self, filename_stem: str) -> str:
        """Extract UR code from filename (e.g., 'UR_S11A' -> 'UR S11A')."""
        match = UR_CODE_PATTERN.search(filename_stem)
        if match:
            code = match.group(1)
            return re.sub(r"\s+", " ", code).strip().upper()

        clean = filename_stem.replace("_", " ").replace("-", " ").upper()
        return clean

    def _extract_applicable_date(self, text: str) -> str:
        """Extract the applicable/effective date from document text."""
        match = APPLICABLE_DATE_PATTERN.search(text[:3000])
        return match.group(1).strip() if match else ""

    def _extract_related_conventions(self, text: str) -> list[str]:
        """Extract IMO conventions referenced in the document."""
        conventions = set()
        for match in IMO_CONVENTION_PATTERN.finditer(text):
            convention = match.group(1).strip()
            normalized = convention.upper().replace(" ", "")
            if normalized == "LL":
                conventions.add("Load Lines")
            elif normalized == "POLARCODE":
                conventions.add("Polar Code")
            else:
                conventions.add(convention.upper())
        return sorted(conventions)

    def _extract_scope(self, text: str) -> str:
        """Extract the scope section from IACS document text."""
        match = IACS_SCOPE_PATTERN.search(text)
        if not match:
            return ""

        scope_start = match.end()

        next_heading = re.search(
            r"\n(?:\d+\.?\s+)?(?:Requirements?|Definitions?|General)\s*\n",
            text[scope_start:],
            re.IGNORECASE,
        )
        scope_end = (
            scope_start + next_heading.start()
            if next_heading
            else min(scope_start + 2000, len(text))
        )

        return text[scope_start:scope_end].strip()

    def _split_iacs_sections(
        self, text: str, ur_code: str,
    ) -> list[dict]:
        """Split IACS document into numbered clause sections.

        IACS documents typically use simple numbered clauses:
        1. Scope
        2. Requirements
        2.1 General
        2.2 Specific requirements
        etc.
        """
        matches = list(IACS_CLAUSE_PATTERN.finditer(text))
        if not matches:
            return self._split_into_sections(text, "IACS")

        sections = []
        for i, match in enumerate(matches):
            clause_num = match.group(1)
            clause_title = match.group(2).strip()
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()

            sections.append({
                "title": f"{clause_num} {clause_title}",
                "body": body,
                "clause_number": clause_num,
            })

        return sections
