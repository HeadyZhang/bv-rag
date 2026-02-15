"""Initialize database schema."""
from config.settings import settings
from db.postgres import PostgresDB
from rich.console import Console

console = Console()


def main():
    console.print("[bold blue]Initializing BV-RAG database schema...[/bold blue]")
    db = PostgresDB(settings.database_url)
    try:
        db.init_schema()
        console.print("[green]Schema initialized successfully![/green]")
        stats = db.get_stats()
        console.print(f"  Regulations: {stats['total_regulations']}")
        console.print(f"  Chunks: {stats['total_chunks']}")
        console.print(f"  Cross-references: {stats['total_cross_references']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
