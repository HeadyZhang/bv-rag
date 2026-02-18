"""Run external data ingestion (BV Rules + IACS) into RAG system.

Usage:
    python scripts/run_external_ingest.py [--bv-only | --iacs-only]
"""
import sys

from pipeline.ingest_external import main

if __name__ == "__main__":
    main()
