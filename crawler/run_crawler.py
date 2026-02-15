"""Run the IMO Rules spider."""
import os
import sys

from rich.console import Console
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

console = Console()


def main():
    os.makedirs("data/raw", exist_ok=True)
    os.makedirs("data/cache", exist_ok=True)

    console.print("[bold blue]BV-RAG Crawler[/bold blue]")
    console.print("Target: https://www.imorules.com/")
    console.print("Output: data/raw/pages.jsonl\n")

    process = CrawlerProcess()

    from crawler.spider import IMORulesSpider
    process.crawl(IMORulesSpider)

    console.print("[yellow]Starting crawl...[/yellow]")
    process.start()
    console.print("[green]Crawl complete![/green]")

    output_path = "data/raw/pages.jsonl"
    if os.path.exists(output_path):
        line_count = sum(1 for _ in open(output_path, encoding="utf-8"))
        console.print(f"Total pages saved: [bold]{line_count}[/bold]")


if __name__ == "__main__":
    main()
