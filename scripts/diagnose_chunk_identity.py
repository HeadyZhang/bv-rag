"""Diagnose chunk identity: how many chunks lack regulation path identifiers.

Samples chunks from PostgreSQL and checks whether each chunk's text
contains an explicit regulation path (e.g. "SOLAS II-2/9") in either
English or Chinese.

Usage:
    python -m scripts.diagnose_chunk_identity
"""
import logging
import re
from collections import defaultdict

from config.settings import settings
from db.postgres import PostgresDB

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# === English regulation path patterns ===
EN_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("SOLAS", re.compile(
        r"SOLAS\s+(I+[-\s]?\d|Chapter\s+\w|Regulation\s+\d)", re.IGNORECASE,
    )),
    ("MARPOL", re.compile(
        r"MARPOL\s+Annex\s+[IVX]+", re.IGNORECASE,
    )),
    ("IBC", re.compile(
        r"IBC\s+Code\s+(Chapter\s+\d+|Ch\.\s*\d+|\d+\.\d+)", re.IGNORECASE,
    )),
    ("IGC", re.compile(r"IGC\s+Code", re.IGNORECASE)),
    ("ICLL", re.compile(
        r"(ICLL|Load\s+Line).*(Reg|Regulation)\s*\.?\s*\d+", re.IGNORECASE,
    )),
    ("FSS", re.compile(r"FSS\s+Code\s+(Chapter|Ch)", re.IGNORECASE)),
    ("LSA", re.compile(r"LSA\s+Code", re.IGNORECASE)),
    ("COLREG", re.compile(r"COLREG\s+(Rule|Regulation)\s+\d+", re.IGNORECASE)),
    ("NR467", re.compile(
        r"NR\s*467.*(Part\s+[A-F]|Section|Chapter)", re.IGNORECASE,
    )),
    ("generic", re.compile(r"Regulation\s+\d+(\.\d+)*", re.IGNORECASE)),
]

# === Chinese regulation path patterns ===
ZH_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("SOLAS_zh", re.compile(
        r"(SOLAS|国际海上人命安全公约).*(第.+章|第.+条|规则\s*\d+)",
    )),
    ("MARPOL_zh", re.compile(
        r"(MARPOL|防污公约).*(附则\s*[IVXⅠⅡⅢⅣⅤⅥ一二三四五六])",
    )),
    ("IBC_zh", re.compile(
        r"(IBC|国际散装运输危险化学品船舶构造和设备规则).*(第.+章|\d+\.\d+)",
    )),
    ("ICLL_zh", re.compile(
        r"(ICLL|国际载重线公约|载重线).*(规则\s*\d+|第.+条)",
    )),
    ("generic_zh", re.compile(r"(第\s*\d+\s*章|第\s*\d+\s*条|规则\s*\d+)")),
]


def _has_pattern(text: str, patterns: list[tuple[str, re.Pattern]]) -> bool:
    """Return True if any pattern matches in text."""
    return any(pat.search(text) for _, pat in patterns)


def main():
    logger.info("=== Chunk Identity Diagnostic ===\n")

    db = PostgresDB(settings.database_url)
    cur = db.conn.cursor()

    # Sample non-curated chunks (random 2000 or all if fewer)
    cur.execute("""
        SELECT c.chunk_id, c.doc_id, c.text,
               c.metadata,
               r.document, r.chapter, r.regulation
        FROM chunks c
        LEFT JOIN regulations r ON c.doc_id = r.doc_id
        WHERE (c.metadata->>'curated')::boolean IS NOT TRUE
        ORDER BY random()
        LIMIT 2000
    """)
    rows = cur.fetchall()
    logger.info(f"Sampled {len(rows)} non-curated chunks\n")

    # Counters per document
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {
        "total": 0,
        "has_en_path": 0,
        "has_zh_path": 0,
        "has_metadata_doc": 0,
        "no_identity": 0,
    })

    for chunk_id, doc_id, text, metadata, doc_name, chapter, regulation in rows:
        doc_key = doc_name or metadata.get("document", "Unknown") if metadata else "Unknown"
        s = stats[doc_key]
        s["total"] += 1

        has_en = _has_pattern(text or "", EN_PATTERNS)
        has_zh = _has_pattern(text or "", ZH_PATTERNS)
        has_meta = bool(doc_name or (metadata and metadata.get("document")))

        if has_en:
            s["has_en_path"] += 1
        if has_zh:
            s["has_zh_path"] += 1
        if has_meta:
            s["has_metadata_doc"] += 1
        if not has_en and not has_zh and not has_meta:
            s["no_identity"] += 1

    # Print report
    logger.info(
        f"{'Document':<20} {'Total':>6} {'EN Path':>10} {'ZH Path':>10} "
        f"{'Metadata':>10} {'No ID':>10}"
    )
    logger.info("-" * 76)

    totals = {"total": 0, "has_en_path": 0, "has_zh_path": 0,
              "has_metadata_doc": 0, "no_identity": 0}

    for doc_key in sorted(stats.keys()):
        s = stats[doc_key]
        t = s["total"]

        def pct(v: int) -> str:
            return f"{v} ({v*100//t}%)" if t > 0 else "0"

        logger.info(
            f"{doc_key:<20} {t:>6} {pct(s['has_en_path']):>10} "
            f"{pct(s['has_zh_path']):>10} {pct(s['has_metadata_doc']):>10} "
            f"{pct(s['no_identity']):>10}"
        )
        for k in totals:
            totals[k] += s[k]

    logger.info("-" * 76)
    t = totals["total"]

    def pct(v: int) -> str:
        return f"{v} ({v*100//t}%)" if t > 0 else "0"

    logger.info(
        f"{'TOTAL':<20} {t:>6} {pct(totals['has_en_path']):>10} "
        f"{pct(totals['has_zh_path']):>10} {pct(totals['has_metadata_doc']):>10} "
        f"{pct(totals['no_identity']):>10}"
    )

    # Summary
    en_pct = totals["has_en_path"] * 100 // t if t else 0
    meta_pct = totals["has_metadata_doc"] * 100 // t if t else 0
    logger.info(
        f"\nConclusion: {100 - en_pct}% of chunks lack a regulation path in text, "
        f"but {meta_pct}% have metadata.document set."
    )

    db.close()


if __name__ == "__main__":
    main()
