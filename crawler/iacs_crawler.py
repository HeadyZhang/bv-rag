"""
IACS (International Association of Classification Societies) catalog crawler.

Uses Playwright (headless Chromium) to bypass Cloudflare protection.
Crawls UR/UI/PR/Rec index pages and extracts document metadata
including PDF links, version info, and CLN/UL status.

Output: data/catalog/iacs_catalog.json

Usage:
    python -m crawler.iacs_crawler
"""
import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

logger = logging.getLogger(__name__)
console = Console()

IACS_BASE_URL = "https://iacs.org.uk"

INDEX_PAGES = {
    "UR": {
        "base": f"{IACS_BASE_URL}/resolutions/unified-requirements",
        "sub_categories": [
            "a", "c", "d", "e", "f", "g", "h", "i",
            "k", "l", "m", "n", "p", "s", "w", "z",
        ],
    },
    "UI": {
        "base": f"{IACS_BASE_URL}/resolutions/unified-interpretations",
        "sub_categories": [],
    },
    "PR": {
        "base": f"{IACS_BASE_URL}/resolutions/procedural-requirements",
        "sub_categories": [],
    },
    "Rec": {
        "base": f"{IACS_BASE_URL}/resolutions/recommendations",
        "sub_categories": [],
    },
}

PAGE_LOAD_TIMEOUT_MS = 60_000
CLOUDFLARE_RETRY_WAIT_S = 10
CLOUDFLARE_MAX_RETRIES = 3
INTER_PAGE_DELAY_MIN_S = 3
INTER_PAGE_DELAY_MAX_S = 5


@dataclass(frozen=True)
class IACSDocument:
    """Immutable representation of a single IACS document entry."""

    title: str
    code: str
    category: str
    sub_category: str
    pdf_url: str
    version: str
    is_clean: bool
    is_underlined: bool
    detail_url: str
    crawled_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _build_index_urls() -> list[dict]:
    """Build list of all index URLs to crawl with their metadata."""
    urls = []
    for category, config in INDEX_PAGES.items():
        base = config["base"]
        subs = config["sub_categories"]
        if subs:
            for sub in subs:
                urls.append({
                    "url": f"{base}/ur-{sub}",
                    "category": category,
                    "sub_category": sub.upper(),
                })
        else:
            urls.append({
                "url": base,
                "category": category,
                "sub_category": "",
            })
    return urls


def _parse_code_from_text(text: str) -> str:
    """Extract document code like 'UR S1 Rev7' from link text."""
    text = text.strip()
    pattern = r"((?:UR|UI|PR|Rec)\s*[A-Z]?\d*(?:\s*Rev\.?\s*\d+)?)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def _parse_version(text: str) -> str:
    """Extract version string (e.g. 'Rev7', 'Rev.12') from text."""
    pattern = r"(Rev\.?\s*\d+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _is_clean_version(text: str) -> bool:
    """Check if the document text indicates a CLN (clean) version."""
    return bool(re.search(r"\bCLN\b", text, re.IGNORECASE))


def _is_underlined_version(text: str) -> bool:
    """Check if the document text indicates a UL (underlined) version."""
    return bool(re.search(r"\bUL\b", text, re.IGNORECASE))


def _select_latest_clean(documents: list[IACSDocument]) -> list[IACSDocument]:
    """
    Filter to keep only the latest CLN version per unique code base.

    Groups by base code (without Rev suffix), prefers CLN over UL,
    and picks the highest revision number.
    """
    grouped: dict[str, list[IACSDocument]] = {}
    for doc in documents:
        base_code = re.sub(r"\s*Rev\.?\s*\d+", "", doc.code).strip()
        key = f"{doc.category}_{doc.sub_category}_{base_code}"
        grouped.setdefault(key, []).append(doc)

    selected = []
    for key, group in grouped.items():
        clean_docs = [d for d in group if d.is_clean]
        candidates = clean_docs if clean_docs else group

        def _rev_number(doc: IACSDocument) -> int:
            match = re.search(r"Rev\.?\s*(\d+)", doc.version, re.IGNORECASE)
            return int(match.group(1)) if match else 0

        best = max(candidates, key=_rev_number)
        selected.append(best)

    return sorted(selected, key=lambda d: (d.category, d.sub_category, d.code))


async def _wait_for_cloudflare(page, url: str) -> bool:
    """
    Detect and wait through Cloudflare challenge pages.

    Returns True if page loaded successfully, False if still blocked.
    """
    for attempt in range(CLOUDFLARE_MAX_RETRIES):
        content = await page.content()
        title = await page.title()

        is_challenge = (
            "Just a moment" in title
            or "Checking your browser" in content
            or "cf-challenge" in content
            or "cloudflare" in content.lower() and "challenge" in content.lower()
        )

        if not is_challenge:
            return True

        logger.info(
            "Cloudflare challenge detected for %s (attempt %d/%d), waiting %ds...",
            url, attempt + 1, CLOUDFLARE_MAX_RETRIES, CLOUDFLARE_RETRY_WAIT_S,
        )
        await asyncio.sleep(CLOUDFLARE_RETRY_WAIT_S)
        await page.reload(wait_until="networkidle")

    logger.warning("Failed to bypass Cloudflare for %s after %d retries", url, CLOUDFLARE_MAX_RETRIES)
    return False


async def _extract_documents_from_index(page, index_info: dict) -> list[IACSDocument]:
    """Extract document entries from a single IACS index page."""
    url = index_info["url"]
    category = index_info["category"]
    sub_category = index_info["sub_category"]

    documents = []

    try:
        await page.goto(url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
    except Exception as err:
        logger.error("Failed to navigate to %s: %s", url, err)
        return documents

    passed = await _wait_for_cloudflare(page, url)
    if not passed:
        return documents

    try:
        await page.wait_for_selector("a[href]", timeout=15_000)
    except Exception:
        logger.warning("No links found on %s, page may not have loaded", url)
        return documents

    links = await page.query_selector_all("a[href]")

    for link in links:
        try:
            href = await link.get_attribute("href") or ""
            text = (await link.inner_text()).strip()

            if not href or not text:
                continue

            is_pdf = href.lower().endswith(".pdf")
            is_detail = (
                "/resolutions/" in href.lower()
                and href != url
                and not href.endswith("#")
            )

            if not is_pdf and not is_detail:
                continue

            has_relevant_code = bool(
                re.search(r"(UR|UI|PR|Rec)\s*[A-Z]?\d", text, re.IGNORECASE)
            )
            if not has_relevant_code and not is_pdf:
                continue

            full_url = href if href.startswith("http") else f"{IACS_BASE_URL}{href}"
            code = _parse_code_from_text(text)
            version = _parse_version(text)
            is_clean = _is_clean_version(text)
            is_underlined = _is_underlined_version(text)

            doc = IACSDocument(
                title=text,
                code=code,
                category=category,
                sub_category=sub_category,
                pdf_url=full_url if is_pdf else "",
                version=version,
                is_clean=is_clean,
                is_underlined=is_underlined,
                detail_url=full_url if not is_pdf else url,
            )
            documents.append(doc)

        except Exception as err:
            logger.debug("Error extracting link on %s: %s", url, err)
            continue

    logger.info("Extracted %d entries from %s", len(documents), url)
    return documents


async def _scrape_detail_page(page, doc: IACSDocument) -> IACSDocument:
    """
    Visit a detail page to find the PDF download link if not already present.

    Returns a new IACSDocument with the pdf_url populated.
    """
    if doc.pdf_url:
        return doc

    try:
        await page.goto(doc.detail_url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
        passed = await _wait_for_cloudflare(page, doc.detail_url)
        if not passed:
            return doc

        pdf_links = await page.query_selector_all("a[href$='.pdf']")
        for link in pdf_links:
            href = await link.get_attribute("href") or ""
            link_text = (await link.inner_text()).strip()

            if "CLN" in link_text.upper() or "clean" in link_text.lower() or not doc.pdf_url:
                full_url = href if href.startswith("http") else f"{IACS_BASE_URL}{href}"
                return IACSDocument(
                    title=doc.title,
                    code=doc.code,
                    category=doc.category,
                    sub_category=doc.sub_category,
                    pdf_url=full_url,
                    version=doc.version,
                    is_clean=doc.is_clean or "CLN" in link_text.upper(),
                    is_underlined=doc.is_underlined,
                    detail_url=doc.detail_url,
                    crawled_at=doc.crawled_at,
                )
    except Exception as err:
        logger.warning("Failed to scrape detail page %s: %s", doc.detail_url, err)

    return doc


async def crawl_iacs_catalog() -> list[dict]:
    """
    Main crawl routine: visit all IACS index pages, extract document metadata,
    visit detail pages for missing PDFs, filter to latest CLN versions.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        console.print(
            "[red]Playwright is required. Install with:[/red]\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )
        sys.exit(1)

    index_urls = _build_index_urls()
    all_documents: list[IACSDocument] = []

    console.print("[bold blue]IACS Catalog Crawler[/bold blue]")
    console.print(f"Index pages to crawl: {len(index_urls)}")
    console.print()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            java_script_enabled=True,
        )
        page = await context.new_page()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Crawling index pages...", total=len(index_urls))

            for idx, index_info in enumerate(index_urls):
                progress.update(
                    task,
                    description=f"[{idx + 1}/{len(index_urls)}] {index_info['category']}-{index_info['sub_category'] or 'all'}: {index_info['url']}",
                )

                docs = await _extract_documents_from_index(page, index_info)
                all_documents.extend(docs)
                progress.advance(task)

                delay = INTER_PAGE_DELAY_MIN_S + (
                    (INTER_PAGE_DELAY_MAX_S - INTER_PAGE_DELAY_MIN_S)
                    * (idx % 3) / 2
                )
                await asyncio.sleep(delay)

        console.print(f"\n[yellow]Total raw entries extracted: {len(all_documents)}[/yellow]")

        docs_without_pdf = [d for d in all_documents if not d.pdf_url]
        if docs_without_pdf:
            console.print(f"[yellow]Visiting {len(docs_without_pdf)} detail pages for PDF links...[/yellow]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                detail_task = progress.add_task("Scraping detail pages...", total=len(docs_without_pdf))

                enriched = []
                for idx, doc in enumerate(docs_without_pdf):
                    progress.update(
                        detail_task,
                        description=f"[{idx + 1}/{len(docs_without_pdf)}] {doc.code}",
                    )
                    updated = await _scrape_detail_page(page, doc)
                    enriched.append(updated)
                    progress.advance(detail_task)

                    delay = INTER_PAGE_DELAY_MIN_S + (
                        (INTER_PAGE_DELAY_MAX_S - INTER_PAGE_DELAY_MIN_S)
                        * (idx % 3) / 2
                    )
                    await asyncio.sleep(delay)

                docs_with_pdf = [d for d in all_documents if d.pdf_url]
                all_documents = [*docs_with_pdf, *enriched]

        await browser.close()

    filtered = _select_latest_clean(all_documents)
    console.print(f"[green]After CLN filtering: {len(filtered)} documents[/green]")

    return [asdict(d) for d in filtered]


def _print_summary(catalog: list[dict]) -> None:
    """Print a summary table of the crawled catalog."""
    table = Table(title="IACS Catalog Summary")
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right", style="green")

    counts: dict[str, int] = {}
    for doc in catalog:
        key = doc["category"]
        if doc["sub_category"]:
            key = f"{key}-{doc['sub_category']}"
        counts[key] = counts.get(key, 0) + 1

    for key in sorted(counts.keys()):
        table.add_row(key, str(counts[key]))

    table.add_row("TOTAL", str(len(catalog)), style="bold")
    console.print(table)


async def _async_main() -> None:
    """Async entry point."""
    output_dir = "data/catalog"
    output_path = os.path.join(output_dir, "iacs_catalog.json")

    os.makedirs(output_dir, exist_ok=True)

    catalog = await crawl_iacs_catalog()

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "crawled_at": datetime.now(timezone.utc).isoformat(),
                "total_documents": len(catalog),
                "documents": catalog,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    console.print(f"\n[green]Catalog saved to {output_path}[/green]")
    _print_summary(catalog)


def main() -> None:
    """Synchronous entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
