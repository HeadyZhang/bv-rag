"""
Scrapy spider for crawling Bureau Veritas marine rules publication catalog.

Crawls the BV rules index page, extracts publication metadata (NR/NI codes,
titles, PDF links, edition dates), and outputs a structured catalog JSON.

Usage:
    python -m crawler.bv_rules_crawler

NOTE: The BV website may render content dynamically via JavaScript. If the
Scrapy spider yields empty results, a Playwright-based fallback is included
(requires `playwright install chromium`). Set BV_USE_PLAYWRIGHT=1 to enable.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.http import Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = (
    "https://marine-offshore.bureauveritas.com"
    "/rules-classification-rule-notes-and-guidance-notes"
)

ERULES_PDF_PATTERN = re.compile(
    r"https?://erules\.veristar\.com/dy/data/bv/pdf/[^\s\"'<>]+\.pdf",
    re.IGNORECASE,
)

NR_CODE_PATTERN = re.compile(r"\b(NR\d{3}|NI\d{3})\b", re.IGNORECASE)

EDITION_DATE_PATTERN = re.compile(
    r"(January|February|March|April|May|June|July|August|September"
    r"|October|November|December)\s+\d{4}",
    re.IGNORECASE,
)

CATEGORY_KEYWORDS = {
    "Rules": ["classification rules", "rules for"],
    "Rule Notes": ["rule note", "rule notes"],
    "Guidance Notes": ["guidance note", "guidance notes"],
}

OUTPUT_PATH = Path("data/catalog/bv_catalog.json")


# ---------------------------------------------------------------------------
# Spider
# ---------------------------------------------------------------------------


class BVRulesSpider(scrapy.Spider):
    """Crawl the BV marine rules publication index and detail pages."""

    name = "bv_rules"
    allowed_domains = [
        "marine-offshore.bureauveritas.com",
        "erules.veristar.com",
    ]
    start_urls = [BASE_URL]

    custom_settings = {
        "DOWNLOAD_DELAY": 2.5,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS": 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "HTTPCACHE_ENABLED": True,
        "HTTPCACHE_DIR": "data/cache/bv_rules",
        "HTTPCACHE_EXPIRATION_SECS": 86400 * 7,
        "ROBOTSTXT_OBEY": True,
        "USER_AGENT": (
            "BV-RAG-Bot/1.0 "
            "(+https://github.com/bv-rag; maritime regulation research)"
        ),
        "LOG_LEVEL": "INFO",
        "RETRY_TIMES": 3,
        "DOWNLOAD_TIMEOUT": 30,
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.catalog: list[dict[str, Any]] = []

    # -- Index page ----------------------------------------------------------

    def parse(self, response: Response, **kwargs: Any):
        """Parse the main index page and follow links to publication pages."""
        links = response.css("a[href]")
        followed = set()

        for link in links:
            href = link.attrib.get("href", "")
            full_url = urljoin(response.url, href)
            text = (link.css("::text").get() or "").strip()

            if self._is_publication_link(full_url, text) and full_url not in followed:
                followed.add(full_url)
                yield scrapy.Request(
                    full_url,
                    callback=self.parse_publication,
                    meta={"link_text": text},
                )

        # Also extract publications embedded directly in the index page
        inline_items = self._extract_inline_publications(response)
        for item in inline_items:
            self.catalog.append(item)

        self.logger.info(
            "Index page parsed: %d publication links discovered", len(followed)
        )

    # -- Publication detail page ---------------------------------------------

    def parse_publication(self, response: Response, **kwargs: Any):
        """Extract metadata from a single publication detail page."""
        link_text = response.meta.get("link_text", "")
        page_text = " ".join(response.css("::text").getall())

        title = self._extract_title(response, link_text)
        nr_code = self._extract_nr_code(title, page_text, response.url)
        description = self._extract_description(response)
        pdf_urls = self._extract_pdf_urls(response)
        category = self._classify_category(title, page_text)
        edition_date = self._extract_edition_date(page_text)
        related = self._extract_related_publications(response, page_text)

        item = {
            "title": title,
            "nr_code": nr_code,
            "description": description,
            "pdf_urls": pdf_urls,
            "category": category,
            "edition_date": edition_date,
            "related_publications": related,
            "source_url": response.url,
        }

        self.catalog.append(item)
        self.logger.info("Extracted publication: %s - %s", nr_code, title)

        yield item

    # -- Extraction helpers --------------------------------------------------

    def _is_publication_link(self, url: str, text: str) -> bool:
        """Determine whether a link likely points to a publication detail page."""
        combined = f"{url} {text}".lower()
        indicators = ["nr", "ni", "rule", "guidance", "note", "classification"]
        return any(indicator in combined for indicator in indicators)

    def _extract_title(self, response: Response, fallback: str) -> str:
        """Extract the publication title from the detail page."""
        for selector in [
            "h1::text",
            "h1 *::text",
            ".page-title::text",
            ".field--name-title::text",
            "article h2::text",
        ]:
            title = response.css(selector).get()
            if title and title.strip():
                return title.strip()

        og_title = response.css('meta[property="og:title"]::attr(content)').get()
        if og_title:
            return og_title.strip()

        return fallback or response.css("title::text").get("").strip()

    def _extract_nr_code(self, title: str, page_text: str, url: str) -> str:
        """Extract NR/NI code from title, page text, or URL."""
        for source in [title, url, page_text[:2000]]:
            match = NR_CODE_PATTERN.search(source)
            if match:
                return match.group(1).upper()
        return ""

    def _extract_description(self, response: Response) -> str:
        """Extract publication description from meta tags or body."""
        meta_desc = response.css(
            'meta[name="description"]::attr(content)'
        ).get()
        if meta_desc and len(meta_desc.strip()) > 20:
            return meta_desc.strip()

        og_desc = response.css(
            'meta[property="og:description"]::attr(content)'
        ).get()
        if og_desc and len(og_desc.strip()) > 20:
            return og_desc.strip()

        # Fallback: first substantial paragraph
        for para in response.css("p::text").getall():
            cleaned = para.strip()
            if len(cleaned) > 50:
                return cleaned[:500]

        return ""

    def _extract_pdf_urls(self, response: Response) -> list[str]:
        """Extract PDF download URLs, prioritizing consolidated versions."""
        pdf_urls: list[str] = []
        seen: set[str] = set()

        # Strategy 1: href attributes ending in .pdf
        for href in response.css("a[href$='.pdf']::attr(href)").getall():
            full_url = urljoin(response.url, href)
            if full_url not in seen:
                seen.add(full_url)
                pdf_urls.append(full_url)

        # Strategy 2: erules.veristar.com pattern anywhere in page source
        for match in ERULES_PDF_PATTERN.findall(response.text):
            if match not in seen:
                seen.add(match)
                pdf_urls.append(match)

        # Prioritize consolidated PDFs (sort: consolidated first, amendments last)
        return sorted(
            pdf_urls,
            key=lambda u: (
                0 if "consol" in u.lower() else 1,
                0 if "amend" not in u.lower() else 1,
            ),
        )

    def _classify_category(self, title: str, page_text: str) -> str:
        """Classify publication as Rules, Rule Notes, or Guidance Notes."""
        combined = f"{title} {page_text[:1000]}".lower()

        for category, keywords in CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in combined:
                    return category

        return "Rules"

    def _extract_edition_date(self, page_text: str) -> str:
        """Extract the most recent edition date from the page text."""
        matches = EDITION_DATE_PATTERN.findall(page_text)
        if matches:
            # Return the last occurrence (typically the latest edition)
            return matches[-1] if isinstance(matches[-1], str) else matches[-1]
        return ""

    def _extract_related_publications(
        self, response: Response, page_text: str
    ) -> list[str]:
        """Extract references to related NR/NI publications."""
        all_codes = set(NR_CODE_PATTERN.findall(page_text))
        # Normalize to uppercase
        return sorted(code.upper() for code in all_codes)

    def _extract_inline_publications(
        self, response: Response
    ) -> list[dict[str, Any]]:
        """Extract publication items listed directly on the index page."""
        items: list[dict[str, Any]] = []
        page_text = " ".join(response.css("::text").getall())

        # Look for list items or table rows containing NR/NI codes
        for row in response.css("tr, li, .views-row, .item-list li"):
            row_text = " ".join(row.css("::text").getall()).strip()
            code_match = NR_CODE_PATTERN.search(row_text)
            if not code_match:
                continue

            nr_code = code_match.group(1).upper()
            link = row.css("a[href]")
            title = row_text[:200]
            pdf_urls = [
                urljoin(response.url, h)
                for h in row.css("a[href$='.pdf']::attr(href)").getall()
            ]

            items.append({
                "title": title,
                "nr_code": nr_code,
                "description": "",
                "pdf_urls": pdf_urls,
                "category": self._classify_category(title, row_text),
                "edition_date": self._extract_edition_date(row_text),
                "related_publications": [],
                "source_url": response.url,
            })

        return items

    # -- Lifecycle -----------------------------------------------------------

    def closed(self, reason: str) -> None:
        """Write the consolidated catalog to JSON on spider close."""
        # Deduplicate by nr_code (keep entry with most PDF URLs)
        deduped: dict[str, dict[str, Any]] = {}
        for entry in self.catalog:
            key = entry.get("nr_code") or entry.get("title", "")
            if not key:
                continue
            existing = deduped.get(key)
            if existing is None or len(entry.get("pdf_urls", [])) > len(
                existing.get("pdf_urls", [])
            ):
                deduped[key] = entry

        catalog_list = list(deduped.values())

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(catalog_list, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        self.logger.info(
            "Catalog saved: %d publications -> %s",
            len(catalog_list),
            OUTPUT_PATH,
        )


# ---------------------------------------------------------------------------
# Playwright fallback (for JS-rendered content)
# ---------------------------------------------------------------------------


async def _playwright_fallback() -> list[dict[str, Any]]:
    """
    Fallback crawler using Playwright for pages that require JS rendering.

    Activate by setting BV_USE_PLAYWRIGHT=1 environment variable.
    Requires: playwright install chromium
    """
    from playwright.async_api import async_playwright

    catalog: list[dict[str, Any]] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        page.set_default_timeout(30000)

        logger.info("Playwright: loading index page %s", BASE_URL)
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.wait_for_timeout(3000)

        links = await page.eval_on_selector_all(
            "a[href]",
            """elements => elements.map(el => ({
                href: el.href,
                text: el.textContent.trim()
            }))""",
        )

        publication_links = [
            link
            for link in links
            if any(
                kw in (link.get("text", "") + link.get("href", "")).lower()
                for kw in ["nr", "ni", "rule", "guidance", "note"]
            )
        ]

        logger.info(
            "Playwright: found %d publication links", len(publication_links)
        )

        for link_info in publication_links:
            href = link_info.get("href", "")
            if not href:
                continue

            try:
                await page.goto(href, wait_until="networkidle")
                await page.wait_for_timeout(2500)

                title = await page.title()
                content = await page.content()

                nr_match = NR_CODE_PATTERN.search(f"{title} {content[:3000]}")
                nr_code = nr_match.group(1).upper() if nr_match else ""

                pdf_links = await page.eval_on_selector_all(
                    "a[href$='.pdf']",
                    "elements => elements.map(el => el.href)",
                )
                erules_matches = ERULES_PDF_PATTERN.findall(content)
                all_pdfs = list(dict.fromkeys(pdf_links + erules_matches))

                edition_match = EDITION_DATE_PATTERN.search(content[:5000])
                edition_date = edition_match.group(0) if edition_match else ""

                catalog.append({
                    "title": title,
                    "nr_code": nr_code,
                    "description": "",
                    "pdf_urls": all_pdfs,
                    "category": "Rules",
                    "edition_date": edition_date,
                    "related_publications": sorted(
                        set(
                            m.upper()
                            for m in NR_CODE_PATTERN.findall(content[:5000])
                        )
                    ),
                    "source_url": href,
                })

                logger.info("Playwright: extracted %s - %s", nr_code, title)

            except Exception as exc:
                logger.warning("Playwright: failed to load %s: %s", href, exc)

        await browser.close()

    return catalog


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the BV Rules crawler (Scrapy or Playwright fallback)."""
    from rich.console import Console

    console = Console()

    console.print("[bold blue]BV Rules Catalog Crawler[/bold blue]")
    console.print(f"Target: {BASE_URL}")
    console.print(f"Output: {OUTPUT_PATH}\n")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    use_playwright = os.environ.get("BV_USE_PLAYWRIGHT", "0") == "1"

    if use_playwright:
        import asyncio

        console.print("[yellow]Using Playwright fallback (JS rendering)...[/yellow]")
        catalog = asyncio.run(_playwright_fallback())

        OUTPUT_PATH.write_text(
            json.dumps(catalog, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        console.print(
            f"[green]Catalog saved: {len(catalog)} publications -> {OUTPUT_PATH}[/green]"
        )
    else:
        console.print("[yellow]Starting Scrapy crawl...[/yellow]")

        process = CrawlerProcess()
        process.crawl(BVRulesSpider)
        process.start()

        if OUTPUT_PATH.exists():
            catalog = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            console.print(
                f"[green]Catalog saved: {len(catalog)} publications -> {OUTPUT_PATH}[/green]"
            )
        else:
            console.print(
                "[red]No catalog output found. The site may require JS rendering.[/red]"
            )
            console.print(
                "[yellow]Try: BV_USE_PLAYWRIGHT=1 python -m crawler.bv_rules_crawler[/yellow]"
            )


if __name__ == "__main__":
    main()
