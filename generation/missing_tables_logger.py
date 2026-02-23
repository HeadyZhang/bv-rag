"""Log queries where the LLM answer indicates missing table data.

Detects phrases like "未检索到" / "未找到" / "基于模型知识" in LLM answers
and writes a JSONL record for later review.  High-frequency missing references
indicate tables that should be prioritised for structured ingestion.

Usage (called from generator.py after answer generation):
    from generation.missing_tables_logger import log_if_missing_table
    log_if_missing_table(query=query, answer=answer)
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_FILE = Path(__file__).resolve().parent.parent / "data" / "missing_tables_log.jsonl"

_MISSING_PATTERNS = re.compile(
    r"未检索到|未找到|没有找到|基于模型知识|无法检索|未能找到"
    r"|not found in.*database|no relevant.*retrieved"
    r"|based on model knowledge|unable to retrieve",
    re.IGNORECASE,
)

_TABLE_REF_PATTERN = re.compile(
    r"Table\s*\d+[\.\-]\d+|Reg(?:ulation)?\s*[\dIVX]+[\-/\.\d]*",
    re.IGNORECASE,
)


def _extract_possible_table_refs(text: str) -> list[str]:
    """Extract table/regulation references mentioned in query or answer."""
    return sorted({m.group(0) for m in _TABLE_REF_PATTERN.finditer(text)})


def log_if_missing_table(
    query: str,
    answer: str,
    session_id: str = "",
) -> bool:
    """Check whether the answer signals missing data and log if so.

    Returns True if a missing-data pattern was detected.
    """
    if not _MISSING_PATTERNS.search(answer):
        return False

    refs = _extract_possible_table_refs(f"{query} {answer}")

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query[:500],
        "missing_reference": refs[0] if refs else "unknown",
        "all_references": refs,
        "confidence_level": "high" if refs else "medium",
        "session_id": session_id,
    }

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info(
            "[MISSING_TABLE] Logged: query='%s', ref=%s",
            query[:60],
            record["missing_reference"],
        )
    except OSError as exc:
        logger.warning("[MISSING_TABLE] Failed to write log: %s", exc)

    return True
