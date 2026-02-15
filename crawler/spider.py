import hashlib
import json
import os
from urllib.parse import urljoin

import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule


class IMORulesSpider(CrawlSpider):
    name = "imorules"
    allowed_domains = ["imorules.com", "www.imorules.com"]

    start_urls = [
        "https://www.imorules.com/",
        "https://www.imorules.com/COLLECTION-_-_9.html",
        "https://www.imorules.com/COLLECTION-_-_10.html",
        "https://www.imorules.com/COLLECTION-_-_11.html",
        "https://www.imorules.com/COLLECTION-_-_15.html",
        "https://www.imorules.com/COLLECTION-_-_30.html",
        "https://www.imorules.com/COLLECTION-_-_31.html",
        "https://www.imorules.com/COLLECTION-_-_32.html",
    ]

    rules = (
        Rule(
            LinkExtractor(allow=r".*\.html$", allow_domains=["imorules.com", "www.imorules.com"]),
            callback="parse_page",
            follow=True,
        ),
    )

    custom_settings = {
        "DEPTH_LIMIT": 15,
        "DOWNLOAD_DELAY": 1.0,
        "CONCURRENT_REQUESTS": 3,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 3,
        "HTTPCACHE_ENABLED": True,
        "HTTPCACHE_DIR": "data/cache",
        "HTTPCACHE_EXPIRATION_SECS": 86400 * 30,
        "ROBOTSTXT_OBEY": True,
        "USER_AGENT": "BV-RAG-Bot/1.0 (+https://github.com/bv-rag; maritime regulation research)",
        "LOG_LEVEL": "INFO",
        "FEEDS": {
            "data/raw/pages.jsonl": {
                "format": "jsonlines",
                "encoding": "utf-8",
                "overwrite": True,
            }
        },
        "RETRY_TIMES": 3,
        "DOWNLOAD_TIMEOUT": 30,
        "CLOSESPIDER_ERRORCOUNT": 50,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page_count = 0
        self.error_count = 0

    def parse_page(self, response):
        self.page_count += 1
        if self.page_count % 100 == 0:
            self.logger.info(f"Crawled {self.page_count} pages so far...")

        raw_html = response.text
        page_hash = hashlib.md5(raw_html.encode("utf-8")).hexdigest()

        title = self._extract_title(response)
        breadcrumb = self._extract_breadcrumb(response)
        internal_links = self._extract_internal_links(response)
        child_links = self._extract_child_links(response)
        parent_topic = self._extract_parent_topic(response)

        yield {
            "url": response.url,
            "title": title,
            "breadcrumb": breadcrumb,
            "raw_html": raw_html,
            "internal_links": internal_links,
            "child_links": child_links,
            "parent_topic": parent_topic,
            "page_hash": page_hash,
        }

    def _extract_title(self, response):
        for selector in ["h1::text", "h2::text", "h3::text"]:
            title = response.css(selector).get()
            if title and title.strip():
                return title.strip()

        title_tag = response.css("title::text").get()
        if title_tag:
            return title_tag.strip()
        return ""

    def _extract_breadcrumb(self, response):
        tds = response.css("td")
        for td in tds:
            text = td.css("::text").getall()
            joined = " ".join(t.strip() for t in text if t.strip())
            if "---" in joined and ("Clasification" in joined or "Classification" in joined):
                return joined
        return ""

    def _extract_internal_links(self, response):
        links = []
        for a in response.css("a[href$='.html']"):
            href = a.attrib.get("href", "")
            anchor_text = a.css("::text").get() or ""
            full_url = urljoin(response.url, href)
            if "imorules.com" in full_url:
                links.append({
                    "url": full_url,
                    "anchor_text": anchor_text.strip(),
                    "href": href,
                })
        return links

    def _extract_child_links(self, response):
        children = []
        for li in response.css("li"):
            a = li.css("a[href$='.html']")
            if a:
                href = a.attrib.get("href", "")
                title = a.css("::text").get() or ""
                full_url = urljoin(response.url, href)
                children.append({
                    "url": full_url,
                    "title": title.strip(),
                    "href": href,
                })
        return children

    def parse_start_url(self, response):
        """Also parse the start URLs themselves (CrawlSpider skips them by default)."""
        return self.parse_page(response)

    def _extract_parent_topic(self, response):
        body_text = response.text
        if "Parent topic:" in body_text:
            parent_links = response.xpath(
                "//*[contains(text(), 'Parent topic:')]/following::a[1]"
            )
            if parent_links:
                first = parent_links[0]
                href = first.attrib.get("href", "")
                full_url = urljoin(response.url, href)
                return {"url": full_url, "href": href}
        return None

    def closed(self, reason):
        self.logger.info(
            f"Crawl finished: {self.page_count} pages crawled, "
            f"{self.error_count} errors, reason: {reason}"
        )
