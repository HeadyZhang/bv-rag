"""Parse raw crawled HTML pages into structured regulation documents."""
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Comment, NavigableString
from rich.console import Console
from rich.progress import track

console = Console()

CONVENTIONS = [
    "SOLAS", "MARPOL", "STCW", "COLREG", "Load Lines", "Tonnage",
    "CLC", "OPRC", "AFS", "BWM", "SAR", "SUA",
]
CODES = [
    "ISM", "ISPS", "LSA", "FSS", "FTP", "IBC", "IGC", "IGF",
    "IMDG", "CSS", "CTU", "HSC", "MODU", "ESP", "Grain", "NOx",
    "OSV", "Polar", "SPS", "IMSBC",
]

COLLECTION_KEYWORDS = {
    "International Conventions": "convention",
    "International Codes": "code",
    "Resolutions": "resolution",
    "Circulars": "circular",
    "Guidelines": "guideline",
    "Specifications and Manuals": "specification",
    "International Conferences": "conference",
}

COPYRIGHT_PATTERNS = [
    re.compile(r"Copyright\s+\d{4}\s+Clas[si]ification", re.IGNORECASE),
    re.compile(r"All rights reserved", re.IGNORECASE),
]


@dataclass
class ParsedRegulation:
    doc_id: str
    url: str
    breadcrumb: str = ""
    collection: str = ""
    document: str = ""
    chapter: str = ""
    part: str = ""
    regulation: str = ""
    paragraph: str = ""
    title: str = ""
    body_text: str = ""
    body_structured: list = field(default_factory=list)
    parent_url: str = ""
    child_urls: list = field(default_factory=list)
    cross_references: list = field(default_factory=list)
    page_type: str = ""
    version: str = ""


class IMOHTMLParser:
    def parse_page(self, raw_data: dict) -> ParsedRegulation:
        url = raw_data.get("url", "")
        doc_id = self._url_to_doc_id(url)
        raw_html = raw_data.get("raw_html", "")
        child_links = raw_data.get("child_links", [])
        parent_topic = raw_data.get("parent_topic")

        soup = BeautifulSoup(raw_html, "lxml")

        breadcrumb = raw_data.get("breadcrumb", "") or self._extract_breadcrumb(soup)
        title = raw_data.get("title", "") or self._extract_title(soup)
        version = self._extract_version(breadcrumb)
        collection = self._identify_collection(breadcrumb, url)
        document = self._identify_document(url, breadcrumb)
        chapter, part, regulation, paragraph = self._parse_breadcrumb(breadcrumb)
        body_text, body_structured = self._extract_body(soup)
        cross_references = self._extract_cross_references(soup, url)
        page_type = self._classify_page_type(url, child_links, body_text)
        child_urls = [c.get("url", "") for c in child_links]
        parent_url = parent_topic.get("url", "") if parent_topic else ""

        return ParsedRegulation(
            doc_id=doc_id,
            url=url,
            breadcrumb=breadcrumb,
            collection=collection,
            document=document,
            chapter=chapter,
            part=part,
            regulation=regulation,
            paragraph=paragraph,
            title=title,
            body_text=body_text,
            body_structured=body_structured,
            parent_url=parent_url,
            child_urls=child_urls,
            cross_references=cross_references,
            page_type=page_type,
            version=version,
        )

    def _url_to_doc_id(self, url: str) -> str:
        path = urlparse(url).path
        filename = path.rstrip("/").split("/")[-1]
        if filename.endswith(".html"):
            filename = filename[:-5]
        return filename or "index"

    def _extract_breadcrumb(self, soup: BeautifulSoup) -> str:
        """Extract breadcrumb from the DITA layout header td (bgcolor=#091C45)."""
        bc_td = soup.find("td", bgcolor="#091C45")
        if bc_td:
            text = bc_td.get_text(separator=" --- ", strip=True)
            # Normalize whitespace
            text = re.sub(r"\s+", " ", text).strip()
            return text
        return ""

    def _extract_title(self, soup: BeautifulSoup) -> str:
        for tag in ["h1", "h2", "h3"]:
            el = soup.find(tag)
            if el:
                text = el.get_text(strip=True)
                if text:
                    return text
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text(strip=True)
        return ""

    def _extract_version(self, breadcrumb: str) -> str:
        match = re.search(r"Version\s+([\d.]+)", breadcrumb)
        if match:
            return match.group(1)
        return ""

    def _identify_collection(self, breadcrumb: str, url: str) -> str:
        bc_lower = breadcrumb.lower()
        for keyword, coll_type in COLLECTION_KEYWORDS.items():
            if keyword.lower() in bc_lower:
                return coll_type

        if "COLLECTION" in url:
            return "collection"

        url_upper = url.upper()
        if any(f"/{c}" in url_upper or f"/{c}_" in url_upper for c in CONVENTIONS):
            return "convention"
        if any(f"/{c}" in url_upper or f"/{c}_" in url_upper for c in CODES):
            return "code"
        if "RES" in url_upper:
            return "resolution"
        if "CIRC" in url_upper:
            return "circular"

        return ""

    def _identify_document(self, url: str, breadcrumb: str) -> str:
        filename = urlparse(url).path.split("/")[-1].replace(".html", "")

        for conv in CONVENTIONS:
            if filename.upper().startswith(conv.upper().replace(" ", "")):
                return conv
            if conv.upper() in filename.upper().split("_")[0:1]:
                return conv

        for code in CODES:
            if filename.upper().startswith(code.upper()):
                return code

        prefix_map = {
            "MSCRES": "MSC Resolution",
            "MEPCRES": "MEPC Resolution",
            "IMORES": "IMO Resolution",
            "MSCCIRC": "MSC Circular",
            "MEPCCIRC": "MEPC Circular",
        }
        for prefix, doc_name in prefix_map.items():
            if filename.upper().startswith(prefix):
                return doc_name

        bc_parts = breadcrumb.split("---")[-1] if "---" in breadcrumb else breadcrumb
        for conv in CONVENTIONS:
            if f" {conv} " in f" {bc_parts} " or f"- {conv} -" in bc_parts:
                return conv
        for code in CODES:
            if f" {code} " in f" {bc_parts} " or f"- {code} -" in bc_parts:
                return code

        return ""

    def _parse_breadcrumb(self, breadcrumb: str) -> tuple:
        chapter = ""
        part = ""
        regulation = ""
        paragraph = ""

        content = breadcrumb.split("---")[-1] if "---" in breadcrumb else breadcrumb
        segments = [s.strip() for s in content.split("-") if s.strip()]

        for seg in segments:
            seg_lower = seg.lower().strip()
            if seg_lower.startswith("chapter") or seg_lower.startswith("annex"):
                chapter = seg.strip()
            elif seg_lower.startswith("part"):
                part = seg.strip()
            elif any(seg_lower.startswith(kw) for kw in ["regulation", "rule", "section"]):
                regulation = seg.strip()
            elif re.match(r"^\d+(\.\d+)*$", seg.strip()):
                paragraph = seg.strip()

        return chapter, part, regulation, paragraph

    def _extract_body(self, soup: BeautifulSoup) -> tuple:
        content_root = self._find_content_root(soup)
        body_structured = []
        self._walk_content(content_root, body_structured)

        body_text = self._clean_text(
            "\n".join(item["text"] for item in body_structured)
        )
        return body_text, body_structured

    def _find_content_root(self, soup: BeautifulSoup):
        """Locate the main content element in the page.

        DITA pages use a layout table with two rows:
          row 0 <td>: breadcrumb header (dark background)
          row 1 <td>: content area containing div.body.conbody etc.
        Non-DITA pages (home, some collections) have no layout table.
        """
        # Try DITA layout: find layout table (top-level, width=100%)
        layout_table = soup.find(
            "table", attrs={"width": "100%", "border": "0"},
        )
        if layout_table:
            rows = layout_table.find_all("tr", recursive=False)
            if len(rows) >= 2:
                content_td = rows[1].find("td", recursive=False)
                if content_td:
                    # Prefer div.body.conbody (actual regulation content)
                    conbody = content_td.find(
                        "div",
                        class_=lambda c: c and "conbody" in c.split(),
                    )
                    if conbody:
                        return conbody
                    # Fallback: use the content td itself
                    return content_td

        # Fallback for non-DITA pages
        return soup.find("body") or soup

    def _walk_content(self, root, body_structured: list):
        """Recursively extract structured content from an element.

        Skips navigation, scripts, copyright, related-links, and ads.
        """
        SKIP_TAGS = {"script", "style", "form", "nav", "header", "footer", "img", "noscript"}
        SKIP_CLASSES = {"related-links", "familylinks", "parentlink", "ullinks"}

        for child in root.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                text = child.strip()
                if text and not self._is_copyright(text):
                    self._append_text_item(text, body_structured)
                continue

            if not hasattr(child, "name") or child.name is None:
                continue

            # Skip non-content elements
            if child.name in SKIP_TAGS:
                continue
            child_classes = set(child.get("class", []))
            if child_classes & SKIP_CLASSES:
                continue
            # Skip banner images / ads
            if child.name == "a" and child.find("img"):
                continue

            if child.name == "table":
                table_text = self._table_to_text(child)
                if table_text and not self._is_copyright(table_text):
                    body_structured.append({
                        "type": "table",
                        "number": "",
                        "text": table_text,
                    })
            elif child.name in ("ul", "ol"):
                for li in child.find_all("li", recursive=False):
                    li_text = li.get_text(strip=True)
                    if li_text and not self._is_copyright(li_text):
                        body_structured.append({
                            "type": "list_item",
                            "number": "",
                            "text": li_text,
                        })
            elif child.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                text = child.get_text(strip=True)
                if text:
                    body_structured.append({
                        "type": "heading",
                        "number": "",
                        "text": text,
                    })
            elif child.name == "p":
                text = child.get_text(strip=True)
                if text and not self._is_copyright(text):
                    self._append_text_item(text, body_structured)
            elif child.name in ("div", "section", "article", "span", "blockquote"):
                # Recurse into container elements
                self._walk_content(child, body_structured)
            elif child.name == "br":
                continue
            elif child.name == "hr":
                continue
            else:
                text = child.get_text(strip=True)
                if text and not self._is_copyright(text):
                    self._append_text_item(text, body_structured)

    def _append_text_item(self, text: str, body_structured: list):
        """Append a text item, detecting numbered paragraphs."""
        numbered = re.match(r"^(\d+(?:\.\d+)*\.?\s*|\.\d+\s*)", text)
        if numbered:
            body_structured.append({
                "type": "paragraph",
                "number": numbered.group(1).strip(),
                "text": text,
            })
        else:
            body_structured.append({
                "type": "text",
                "number": "",
                "text": text,
            })

    def _table_to_text(self, table) -> str:
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            rows.append(" | ".join(cells))
        return "\n".join(rows)

    def _extract_cross_references(self, soup: BeautifulSoup, base_url: str) -> list:
        refs = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.endswith(".html"):
                continue
            anchor_text = a.get_text(strip=True)
            if not anchor_text:
                continue

            is_reg_ref = bool(re.search(
                r"(regulation|rule|chapter|annex|resolution|circular|section)",
                anchor_text,
                re.IGNORECASE,
            ))
            is_guid = "GUID-" in href

            if is_reg_ref or is_guid:
                parent = a.parent
                context = parent.get_text(strip=True)[:200] if parent else ""
                from urllib.parse import urljoin
                target_url = urljoin(base_url, href)
                refs.append({
                    "target_url": target_url,
                    "target_text": anchor_text,
                    "context": context,
                })
        return refs

    def _classify_page_type(self, url: str, child_links: list, body_text: str) -> str:
        filename = urlparse(url).path.split("/")[-1]
        if filename.startswith("COLLECTION"):
            return "collection"
        if filename.startswith("Chunk"):
            return "footnote"
        if len(child_links) > 2:
            return "index"
        if body_text and len(body_text) > 50:
            return "content"
        if child_links:
            return "index"
        return "content"

    def _is_copyright(self, text: str) -> bool:
        return any(p.search(text) for p in COPYRIGHT_PATTERNS)

    def _clean_text(self, text: str) -> str:
        for pattern in COPYRIGHT_PATTERNS:
            text = pattern.sub("", text)
        text = re.sub(r"Parent topic:.*", "", text)
        # Collapse multi-space runs from DITA whitespace formatting
        text = re.sub(r"[ \t]+", " ", text)
        # Clean up space before/after newlines
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def main():
    input_path = "data/raw/pages.jsonl"
    output_path = "data/parsed/regulations.jsonl"

    if not os.path.exists(input_path):
        console.print(f"[red]Input file not found: {input_path}[/red]")
        sys.exit(1)

    os.makedirs("data/parsed", exist_ok=True)

    parser = IMOHTMLParser()
    total = sum(1 for _ in open(input_path, encoding="utf-8"))

    console.print(f"[bold blue]Parsing {total} pages...[/bold blue]")

    with open(input_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:
        for line in track(fin, total=total, description="Parsing"):
            raw_data = json.loads(line)
            try:
                parsed = parser.parse_page(raw_data)
                fout.write(json.dumps(asdict(parsed), ensure_ascii=False) + "\n")
            except Exception as e:
                console.print(f"[red]Error parsing {raw_data.get('url', '?')}: {e}[/red]")

    output_count = sum(1 for _ in open(output_path, encoding="utf-8"))
    console.print(f"[green]Done! {output_count} regulations saved to {output_path}[/green]")


if __name__ == "__main__":
    main()
