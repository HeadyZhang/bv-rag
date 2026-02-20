"""Batch inject regulation path prefixes into chunk text.

Reads metadata.document + regulations table to build a bilingual prefix
like "[SOLAS Chapter II-2, Regulation 9 | SOLAS 第II-2章 第9条 防火围蔽]"
and prepends it to chunk.text for chunks that lack an explicit path.

Modes:
    MODE=dry_run (default): prints statistics + sample before/after, no DB changes
    MODE=execute: updates PostgreSQL + re-embeds + upserts to Qdrant

Usage:
    python -m scripts.enrich_chunk_identity              # dry_run
    MODE=execute python -m scripts.enrich_chunk_identity  # actual execution
"""
import logging
import os
import re

from config.settings import settings
from db.postgres import PostgresDB

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Bilingual prefix mapping: document → chapter_key → (en_label, zh_label)
BILINGUAL_PREFIX: dict[str, dict[str, tuple[str, str]]] = {
    "SOLAS": {
        "I": ("Chapter I", "第I章 总则"),
        "II-1": ("Chapter II-1", "第II-1章 构造/分舱/稳性"),
        "II-2": ("Chapter II-2", "第II-2章 防火/探火/灭火"),
        "III": ("Chapter III", "第III章 救生设备"),
        "IV": ("Chapter IV", "第IV章 无线电通信"),
        "V": ("Chapter V", "第V章 航行安全"),
        "VI": ("Chapter VI", "第VI章 货物运输"),
        "VII": ("Chapter VII", "第VII章 危险货物运输"),
        "IX": ("Chapter IX", "第IX章 安全管理/ISM"),
        "X": ("Chapter X", "第X章 高速船"),
        "XI-1": ("Chapter XI-1", "第XI-1章 特殊安全措施"),
        "XI-2": ("Chapter XI-2", "第XI-2章 安保/ISPS"),
        "XII": ("Chapter XII", "第XII章 散货船"),
        "XIV": ("Chapter XIV", "第XIV章 极地规则"),
    },
    "MARPOL": {
        "Annex I": ("Annex I", "附则I 油污染"),
        "Annex II": ("Annex II", "附则II 有害液体物质"),
        "Annex III": ("Annex III", "附则III 包装有害物质"),
        "Annex IV": ("Annex IV", "附则IV 生活污水"),
        "Annex V": ("Annex V", "附则V 垃圾"),
        "Annex VI": ("Annex VI", "附则VI 大气污染"),
    },
    "BV NR467": {
        "Part A": ("Part A", "A篇 船舶检验分级"),
        "Part B": ("Part B", "B篇 船体结构"),
        "Part C": ("Part C", "C篇 机械电气自动化"),
        "Part D": ("Part D", "D篇 服务附加标志"),
        "Part E": ("Part E", "E篇 附加入级标志"),
        "Part F": ("Part F", "F篇 附加服务特征"),
    },
}

# Regex patterns to check if text already has a regulation path
_HAS_PATH_RE = re.compile(
    r"(SOLAS\s+(I+[-\s]?\d|Chapter|Regulation)"
    r"|MARPOL\s+Annex"
    r"|IBC\s+Code\s+(Chapter|Ch\.|\d+\.\d+)"
    r"|IGC\s+Code"
    r"|ICLL.*(Reg|Regulation)"
    r"|FSS\s+Code"
    r"|LSA\s+Code"
    r"|NR\s*467.*(Part|Section|Chapter)"
    r"|^\[.*Chapter.*Regulation.*\])",
    re.IGNORECASE | re.MULTILINE,
)


def _build_prefix(document: str, chapter: str, regulation: str) -> str | None:
    """Build a bilingual prefix string from regulation metadata."""
    doc_map = BILINGUAL_PREFIX.get(document)
    if not doc_map:
        # For unmapped documents, build a simple prefix
        if document and chapter:
            return f"[{document} {chapter}]"
        return None

    # Try to match chapter key
    ch_info = doc_map.get(chapter)
    if not ch_info:
        # Try partial match
        for key, val in doc_map.items():
            if key in (chapter or ""):
                ch_info = val
                break

    if not ch_info:
        if chapter:
            return f"[{document} {chapter}]"
        return None

    en_label, zh_label = ch_info

    # Extract regulation number if available
    reg_num = ""
    if regulation:
        # Extract just the regulation number part
        reg_match = re.search(r'(?:Reg(?:ulation)?\.?\s*)(\d+(?:\.\d+)*)', regulation)
        if reg_match:
            reg_num = f", Regulation {reg_match.group(1)}"
            zh_reg = f" 第{reg_match.group(1)}条"
        else:
            zh_reg = ""
    else:
        zh_reg = ""

    return f"[{document} {en_label}{reg_num} | {document} {zh_label}{zh_reg}]"


def main():
    mode = os.environ.get("MODE", "dry_run")
    logger.info(f"=== Chunk Identity Enrichment (mode={mode}) ===\n")

    db = PostgresDB(settings.database_url)
    cur = db.conn.cursor()

    # Fetch all non-curated chunks with their regulation metadata
    cur.execute("""
        SELECT c.chunk_id, c.doc_id, c.text,
               r.document, r.chapter, r.regulation
        FROM chunks c
        LEFT JOIN regulations r ON c.doc_id = r.doc_id
        WHERE (c.metadata->>'curated')::boolean IS NOT TRUE
    """)
    rows = cur.fetchall()
    logger.info(f"Total non-curated chunks: {len(rows)}")

    would_update = 0
    already_has_path = 0
    no_metadata = 0
    samples = []

    for chunk_id, doc_id, text, document, chapter, regulation in rows:
        if not text:
            continue

        # Check if text already has a regulation path
        if _HAS_PATH_RE.search(text):
            already_has_path += 1
            continue

        # Try to build prefix from metadata
        if not document:
            no_metadata += 1
            continue

        prefix = _build_prefix(document, chapter or "", regulation or "")
        if not prefix:
            no_metadata += 1
            continue

        # Check if prefix already present
        if prefix in text:
            already_has_path += 1
            continue

        would_update += 1

        if len(samples) < 10:
            new_text = f"{prefix} {text}"
            samples.append({
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "prefix": prefix,
                "before": text[:100],
                "after": new_text[:150],
            })

    logger.info(f"\n=== Results ===")
    logger.info(f"Already has path in text: {already_has_path}")
    logger.info(f"Would update (prefix needed): {would_update}")
    logger.info(f"No metadata available: {no_metadata}")
    logger.info(f"Total: {already_has_path + would_update + no_metadata}")

    if samples:
        logger.info(f"\n=== Sample Before/After (first {len(samples)}) ===")
        for s in samples:
            logger.info(f"\n  chunk_id: {s['chunk_id']}")
            logger.info(f"  prefix:   {s['prefix']}")
            logger.info(f"  before:   {s['before']}...")
            logger.info(f"  after:    {s['after']}...")

    if mode == "execute":
        logger.info("\n⚠ Execute mode is not yet implemented.")
        logger.info("This script currently supports dry_run mode only.")
        logger.info("To implement execute mode: update PG text, re-embed, upsert Qdrant.")
    else:
        logger.info(f"\nDry run complete. Use MODE=execute to apply changes.")

    db.close()


if __name__ == "__main__":
    main()
