"""Industrial-grade backfill: inject bilingual regulation path prefixes into chunks.

Scans 5,874+ chunks that lack regulation path identifiers, infers the correct
path from 4 signal sources, and prepends a bilingual prefix like:
  [SOLAS Chapter II-2, Regulation 9 | 国际海上人命安全公约 第II-2章 第9条]

Safety: backup → plan → validate → execute (batched) → verify → rollback

Modes:
    --mode plan      Generate enrichment_plan.jsonl (read-only)
    --mode validate  Stratified sample of 50 for human spot-check
    --mode execute   Apply changes (batched, checkpoint, backup first)
    --mode verify    Post-execution quality check
    --mode rollback  Restore PG data from backup file

Usage:
    python -m scripts.backfill_regulation_paths --mode plan
    python -m scripts.backfill_regulation_paths --mode validate
    python -m scripts.backfill_regulation_paths --mode execute --batch imo --dry-run
    python -m scripts.backfill_regulation_paths --mode execute --batch imo
    python -m scripts.backfill_regulation_paths --mode verify
    python -m scripts.backfill_regulation_paths --mode rollback --rollback-file backups/chunks_backup_XXX.jsonl
"""
import argparse
import hashlib
import json
import logging
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import openai
import psycopg2
import psycopg2.extras
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)

from config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLAN_FILE = Path("backups/enrichment_plan.jsonl")
BACKUP_DIR = Path("backups")

# Reuse regulation-path detection patterns from diagnose_chunk_identity.py
_EN_PATH_PATTERNS: list[re.Pattern] = [
    re.compile(r"SOLAS\s+(I+[-\s]?\d|Chapter\s+\w|Regulation\s+\d)", re.I),
    re.compile(r"MARPOL\s+Annex\s+[IVX]+", re.I),
    re.compile(r"IBC\s+Code\s+(Chapter\s+\d+|Ch\.\s*\d+|\d+\.\d+)", re.I),
    re.compile(r"IGC\s+Code", re.I),
    re.compile(r"(ICLL|Load\s+Line).*(Reg|Regulation)\s*\.?\s*\d+", re.I),
    re.compile(r"FSS\s+Code\s+(Chapter|Ch)", re.I),
    re.compile(r"LSA\s+Code", re.I),
    re.compile(r"COLREG\s+(Rule|Regulation)\s+\d+", re.I),
    re.compile(r"NR\s*467.*(Part\s+[A-F]|Section|Chapter)", re.I),
    re.compile(r"^\[.*Chapter.*Regulation.*\]", re.I | re.M),
]

_ZH_PATH_PATTERNS: list[re.Pattern] = [
    re.compile(r"(SOLAS|国际海上人命安全公约).*(第.+章|第.+条|规则\s*\d+)"),
    re.compile(r"(MARPOL|防污公约).*(附则\s*[IVXⅠⅡⅢⅣⅤⅥ一二三四五六])"),
    re.compile(r"(IBC|国际散装运输危险化学品船舶构造和设备规则).*(第.+章|\d+\.\d+)"),
    re.compile(r"(ICLL|国际载重线公约|载重线).*(规则\s*\d+|第.+条)"),
    re.compile(r"(第\s*\d+\s*章|第\s*\d+\s*条|规则\s*\d+)"),
]

# Bilingual document name mapping
DOCUMENT_ZH_MAP: dict[str, str] = {
    "SOLAS": "国际海上人命安全公约",
    "MARPOL": "国际防止船舶造成污染公约",
    "IBC": "国际散化规则",
    "IGC": "国际液化气体船规则",
    "ICLL": "国际载重线公约",
    "Load Lines": "国际载重线公约",
    "FSS": "消防安全系统规则",
    "LSA": "救生设备规则",
    "ISM": "国际安全管理规则",
    "ISPS": "国际船舶和港口设施保安规则",
    "STCW": "船员培训发证值班标准公约",
    "COLREG": "国际海上避碰规则",
    "BWM": "压载水管理公约",
    "Polar": "极地规则",
    "IGF": "国际气体燃料船规则",
    "MLC": "海事劳工公约",
    "Tonnage": "国际船舶吨位丈量公约",
    "MODU": "移动式海上钻井装置规则",
    "HSC": "高速船安全规则",
    "NOx": "氮氧化物技术规则",
    "MSC Circular": "海安会通函",
    "MSC Resolution": "海安会决议",
    "MEPC Resolution": "海环会决议",
    "MEPC Circular": "海环会通函",
    "IMO Resolution": "IMO决议",
    "BV NR467": "BV船级社规范NR467",
    "BV NR216": "BV船级社规范NR216",
    "BV NR670": "BV船级社规范NR670",
}

# Chapter-level Chinese mapping
CHAPTER_ZH_MAP: dict[str, str] = {
    # SOLAS chapters
    "I": "第I章 总则",
    "II-1": "第II-1章 构造—结构分舱稳性",
    "II-2": "第II-2章 构造—防火探火灭火",
    "III": "第III章 救生设备和装置",
    "IV": "第IV章 无线电通信",
    "V": "第V章 航行安全",
    "VI": "第VI章 货物运输",
    "VII": "第VII章 危险货物运输",
    "IX": "第IX章 船舶安全营运管理",
    "X": "第X章 高速船安全措施",
    "XI-1": "第XI-1章 加强海上安全的特别措施",
    "XI-2": "第XI-2章 加强海上保安的特别措施",
    "XII": "第XII章 散货船附加安全措施",
    "XIV": "第XIV章 极地水域船舶营运安全措施",
    # MARPOL annexes
    "Annex I": "附则I 油类",
    "Annex II": "附则II 散装有毒液体物质",
    "Annex III": "附则III 包装形式有害物质",
    "Annex IV": "附则IV 船舶生活污水",
    "Annex V": "附则V 船舶垃圾",
    "Annex VI": "附则VI 船舶造成大气污染",
    # BV NR467 parts
    "Part A": "A篇 船舶检验分级",
    "Part B": "B篇 船体与稳性",
    "Part C": "C篇 机械电气与自动化",
    "Part D": "D篇 服务附加标志",
    "Part E": "E篇 附加入级符号",
    "Part F": "F篇 附加服务特征",
}

# Batch filter categorization
BATCH_FILTERS: dict[str, object] = {
    "imo": lambda e: e.get("collection", "") in (
        "convention", "code", "imo_regulations", ""
    ) and not e.get("document", "").startswith("BV")
    and "IACS" not in e.get("document", ""),
    "bv": lambda e: e.get("document", "").startswith("BV")
    or e.get("collection", "") == "bv_rules",
    "circular": lambda e: any(
        kw in e.get("collection", "").lower()
        for kw in ("circular", "resolution", "specification", "guideline")
    ) or any(
        kw in e.get("document", "")
        for kw in ("MSC", "MEPC", "Resolution", "Circular")
    ),
    "iacs": lambda e: "IACS" in e.get("document", "")
    or e.get("collection", "") == "iacs_resolutions",
    "all": lambda _: True,
}

# Confidence level ordering
CONFIDENCE_LEVELS = {"high": 3, "medium": 2, "low": 1, "none": 0}

# Maximum prefix length to avoid diluting embeddings
MAX_PREFIX_LEN = 200

# Regex to extract condensed reference from verbose BV erules breadcrumbs
_BREADCRUMB_CONDENSERS: list[tuple[str, re.Pattern]] = [
    # MSC/Circular.1175, MSC.1/Circ.1604, MEPC/Circular.414
    ("MSC Circular", re.compile(
        r"MSC[\./](?:1/)?Circ(?:ular)?[\./](\d+)", re.I,
    )),
    ("MEPC Circular", re.compile(
        r"MEPC[\./](?:1/)?Circ(?:ular)?[\./](\d+)", re.I,
    )),
    # Resolution MSC.252(83), MEPC.259(68)
    ("MSC Resolution", re.compile(
        r"Resolution\s+MSC[\./](\d+\(\d+\))", re.I,
    )),
    ("MEPC Resolution", re.compile(
        r"Resolution\s+MEPC[\./](\d+\(\d+\))", re.I,
    )),
    # IMO Resolution A.985(24)
    ("IMO Resolution", re.compile(
        r"(?:IMO\s+)?Resolution\s+A[\./](\d+\(\d+\))", re.I,
    )),
    # SN.1/Circ.288 (Safety of Navigation circulars)
    ("SN Circular", re.compile(
        r"SN[\./](?:1/)?Circ[\./](\d+)", re.I,
    )),
    # International Codes: SCV Code, DSC Code, etc.
    ("Code", re.compile(
        r"International Codes\s*-\s*(\w+\s+Code)", re.I,
    )),
]


def condense_breadcrumb(breadcrumb: str) -> tuple[str, str] | None:
    """Extract a short regulation reference from verbose BV erules breadcrumbs.

    Returns (path_en, document_type) or None.
    """
    if not breadcrumb:
        return None
    for doc_type, pat in _BREADCRUMB_CONDENSERS:
        m = pat.search(breadcrumb)
        if m:
            ref = m.group(1)
            path_en = f"[{doc_type} {ref}]"
            return path_en, doc_type
    # Fallback: extract after last " - " segment if breadcrumb is very long
    if len(breadcrumb) > 150 and " - " in breadcrumb:
        # Try to find the document title segment
        segments = breadcrumb.split(" - ")
        # Look for meaningful segments (skip "Clasification Society...", "Statutory Documents...")
        for seg in segments:
            seg = seg.strip()
            if any(kw in seg for kw in [
                "SOLAS", "MARPOL", "IBC", "IGC", "FSS", "LSA",
                "COLREG", "ICLL", "Load Line", "STCW",
            ]):
                return f"[{seg[:100]}]", "convention"
        # If no match, skip (don't inject a mega breadcrumb)
        return None
    return None


# ---------------------------------------------------------------------------
# Path Detection (reused from diagnose_chunk_identity)
# ---------------------------------------------------------------------------

def has_regulation_path(text: str) -> bool:
    """Return True if chunk text already contains a regulation path."""
    if not text:
        return False
    for pat in _EN_PATH_PATTERNS:
        if pat.search(text):
            return True
    for pat in _ZH_PATH_PATTERNS:
        if pat.search(text):
            return True
    return False


# ---------------------------------------------------------------------------
# Signal Source 1: regulations table fields
# ---------------------------------------------------------------------------

def _truncate_chapter(chapter: str, max_len: int = 60) -> str:
    """Truncate a chapter name if it's too long (e.g. 'Annex – Unified...')."""
    if not chapter or len(chapter) <= max_len:
        return chapter
    # Try to cut at a natural boundary
    for delim in [" – ", " - ", ", "]:
        idx = chapter.find(delim)
        if 0 < idx < max_len:
            return chapter[:idx]
    return chapter[:max_len]


def build_english_path(document: str, chapter: str, regulation: str) -> str:
    """Build standardized English regulation path."""
    parts = [document]

    if chapter:
        ch = _truncate_chapter(chapter)
        if document == "SOLAS" and not ch.startswith("Chapter"):
            parts.append(f"Chapter {ch}")
        elif document == "MARPOL" and not ch.startswith("Annex"):
            parts.append(f"Annex {ch}")
        elif document.startswith("BV") and not ch.startswith("Part"):
            parts.append(f"Part {ch}")
        else:
            parts.append(ch)

    if regulation:
        parts.append(regulation)

    return f"[{', '.join(parts)}]"


def build_chinese_path(document: str, chapter: str, regulation: str) -> str:
    """Build Chinese regulation path (document-context-aware)."""
    doc_zh = DOCUMENT_ZH_MAP.get(document, document)

    # Only use CHAPTER_ZH_MAP when the chapter key matches the document context
    # to avoid "Tonnage Annex III" → "附则III 包装形式有害物质" (which is MARPOL)
    ch_zh = ""
    if chapter:
        ch_key = _truncate_chapter(chapter)
        if document == "MARPOL" and ch_key.startswith("Annex"):
            ch_zh = CHAPTER_ZH_MAP.get(ch_key, ch_key)
        elif document == "SOLAS" and ch_key in CHAPTER_ZH_MAP:
            ch_zh = CHAPTER_ZH_MAP.get(ch_key, ch_key)
        elif document.startswith("BV") and ch_key.startswith("Part"):
            ch_zh = CHAPTER_ZH_MAP.get(ch_key, ch_key)
        else:
            # For other documents, use the chapter name as-is (no cross-mapping)
            ch_zh = ch_key

    reg_num = ""
    if regulation:
        num_match = re.search(r"(\d+[\.\d]*)", regulation)
        if num_match:
            reg_num = f"第{num_match.group(1)}条"

    parts = [doc_zh]
    if ch_zh and ch_zh != document:
        parts.append(ch_zh)
    if reg_num:
        parts.append(reg_num)

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Signal Source 3: regex extraction from text
# ---------------------------------------------------------------------------

_TEXT_PATH_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("SOLAS", re.compile(
        r"SOLAS\s+(?:Chapter\s+)?(I+[-]?\d?)\s*(?:,\s*)?(?:Reg(?:ulation)?\.?\s*(\d+[\.\d]*))?",
        re.I,
    )),
    ("MARPOL", re.compile(
        r"MARPOL\s+(?:Annex\s+)?([IVX]+)\s*(?:,\s*)?(?:Reg(?:ulation)?\.?\s*(\d+[\.\d]*))?",
        re.I,
    )),
    ("IBC", re.compile(r"IBC\s+Code\s+(?:Chapter\s+)?(\d+)", re.I)),
    ("IGC", re.compile(r"IGC\s+Code\s+(?:Chapter\s+)?(\d+)", re.I)),
    ("FSS", re.compile(r"FSS\s+Code\s+(?:Chapter\s+)?(\d+)", re.I)),
    ("LSA", re.compile(r"LSA\s+Code\s+(?:Chapter\s+)?(\d+)", re.I)),
    ("COLREG", re.compile(r"COLREG\s+Rule\s+(\d+)", re.I)),
    ("ICLL", re.compile(r"(?:ICLL|Load\s+Line).*Reg(?:ulation)?\.?\s*(\d+)", re.I)),
]


def extract_path_from_text(text: str) -> str | None:
    """Signal source 3: extract regulation path from chunk text content."""
    if not text:
        return None
    # Only check first 500 chars to avoid false matches in body
    head = text[:500]
    for doc_name, pat in _TEXT_PATH_PATTERNS:
        m = pat.search(head)
        if m:
            groups = [g for g in m.groups() if g]
            if groups:
                return f"[{doc_name} {' '.join(groups)}]"
    return None


# ---------------------------------------------------------------------------
# Signal Source 4: doc_id pattern parsing
# ---------------------------------------------------------------------------

_DOCID_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("SOLAS", re.compile(r"solas[_-]+([\w-]+)", re.I)),
    ("MARPOL", re.compile(r"marpol[_-]+([\w-]+)", re.I)),
    ("IBC", re.compile(r"ibc[_-]+([\w-]+)", re.I)),
    ("IGC", re.compile(r"igc[_-]+([\w-]+)", re.I)),
    ("FSS", re.compile(r"fss[_-]+([\w-]+)", re.I)),
    ("LSA", re.compile(r"lsa[_-]+([\w-]+)", re.I)),
    ("COLREG", re.compile(r"colreg[_-]+([\w-]+)", re.I)),
    ("ICLL", re.compile(r"(?:icll|load[_-]?line)[_-]+([\w-]+)", re.I)),
    ("MSC", re.compile(r"msc[_.-]+([\w.-]+)", re.I)),
    ("MEPC", re.compile(r"mepc[_.-]+([\w.-]+)", re.I)),
    ("BV NR467", re.compile(r"nr[_-]?467[_-]+([\w-]+)", re.I)),
]


def parse_doc_id_pattern(doc_id: str) -> str | None:
    """Signal source 4: infer regulation path from doc_id naming convention."""
    if not doc_id:
        return None
    for doc_name, pat in _DOCID_PATTERNS:
        m = pat.search(doc_id)
        if m:
            suffix = m.group(1).replace("_", " ").replace("-", " ").strip()
            if suffix:
                return f"[{doc_name} {suffix}]"
    return None


def translate_path(path_en: str) -> str:
    """Translate an English path bracket to Chinese equivalent."""
    if not path_en:
        return ""
    # Extract document name from path like "[SOLAS Chapter II-2]"
    inner = path_en.strip("[]")
    for en_name, zh_name in DOCUMENT_ZH_MAP.items():
        if inner.startswith(en_name):
            return inner.replace(en_name, zh_name, 1)
    return inner


# ---------------------------------------------------------------------------
# Core inference logic
# ---------------------------------------------------------------------------

def infer_regulation_path(
    chunk_id: str,
    doc_id: str,
    text: str,
    metadata: dict,
    reg_row: dict,
) -> tuple[str | None, str | None, str]:
    """
    Infer regulation path from 4 signal sources.

    Returns (path_en, path_zh, confidence) where confidence is
    "high", "medium", "low", or "none".
    """
    # Signal 1 (most reliable): regulations table fields
    document = reg_row.get("document", "") or ""
    chapter = reg_row.get("chapter", "") or ""
    regulation = reg_row.get("regulation", "") or ""

    if document and chapter:
        path_en = build_english_path(document, chapter, regulation)
        path_zh = build_chinese_path(document, chapter, regulation)
        return path_en, path_zh, "high"
    if document:
        path_en = f"[{document}]"
        path_zh = DOCUMENT_ZH_MAP.get(document, document)
        return path_en, path_zh, "medium"

    # Signal 2: metadata JSONB
    if metadata:
        meta_breadcrumb = metadata.get("breadcrumb", "") or ""
        meta_doc = metadata.get("document", "") or ""

        if meta_breadcrumb and len(meta_breadcrumb) > 5:
            # Skip BV erules platform headers (not useful regulation paths)
            is_platform_header = meta_breadcrumb.startswith(
                "Clasification Society"
            ) or meta_breadcrumb.startswith("Classification Society")
            if is_platform_header or len(meta_breadcrumb) > 150:
                condensed = condense_breadcrumb(meta_breadcrumb)
                if condensed:
                    path_en, doc_type = condensed
                    path_zh = DOCUMENT_ZH_MAP.get(doc_type, doc_type)
                    return path_en, path_zh, "medium"
                # If condensing fails, skip this breadcrumb (too noisy)
            else:
                path_en = f"[{meta_breadcrumb}]"
                path_zh = translate_path(path_en)
                return path_en, path_zh, "medium"

        if meta_doc:
            path_en = f"[{meta_doc}]"
            path_zh = DOCUMENT_ZH_MAP.get(meta_doc, meta_doc)
            return path_en, path_zh, "medium"

    # Signal 3: text regex
    path_from_text = extract_path_from_text(text)
    if path_from_text:
        return path_from_text, translate_path(path_from_text), "medium"

    # Signal 4: doc_id pattern
    path_from_docid = parse_doc_id_pattern(doc_id)
    if path_from_docid:
        return path_from_docid, translate_path(path_from_docid), "low"

    return None, None, "none"


def build_bilingual_prefix(path_en: str, path_zh: str) -> str:
    """Build the bilingual prefix to prepend to chunk text.

    Enforces MAX_PREFIX_LEN to avoid diluting embeddings.
    """
    if path_zh and path_zh != path_en and path_zh != path_en.strip("[]"):
        prefix = f"{path_en} | {path_zh}"
    else:
        prefix = path_en

    # Truncate if too long
    if len(prefix) > MAX_PREFIX_LEN:
        prefix = prefix[:MAX_PREFIX_LEN]

    return f"{prefix}\n\n"


# ---------------------------------------------------------------------------
# Phase 0: Backup
# ---------------------------------------------------------------------------

def backup_chunks(
    chunk_ids: list[str], conn, timestamp: str,
) -> tuple[Path, int]:
    """Backup chunks that will be modified to a JSONL file."""
    BACKUP_DIR.mkdir(exist_ok=True)
    backup_file = BACKUP_DIR / f"chunks_backup_{timestamp}.jsonl"

    cur = conn.cursor()
    count = 0
    with open(backup_file, "w", encoding="utf-8") as f:
        for chunk_id in chunk_ids:
            cur.execute(
                "SELECT chunk_id, text, text_for_embedding, metadata "
                "FROM chunks WHERE chunk_id = %s",
                (chunk_id,),
            )
            row = cur.fetchone()
            if row:
                cid, text, tfe, meta = row
                meta_dict = meta if isinstance(meta, dict) else json.loads(meta or "{}")
                json.dump(
                    {
                        "chunk_id": cid,
                        "original_text": text,
                        "original_text_for_embedding": tfe,
                        "original_metadata": meta_dict,
                    },
                    f,
                    ensure_ascii=False,
                )
                f.write("\n")
                count += 1
    cur.close()

    logger.info(f"Backup saved: {backup_file} ({count} chunks)")
    return backup_file, count


def backup_qdrant_payloads(
    chunk_ids: list[str], qdrant_client: QdrantClient, timestamp: str,
) -> Path:
    """Backup Qdrant payloads for chunks that will be modified."""
    backup_file = BACKUP_DIR / f"qdrant_backup_{timestamp}.jsonl"

    count = 0
    with open(backup_file, "w", encoding="utf-8") as f:
        for chunk_id in chunk_ids:
            try:
                results, _ = qdrant_client.scroll(
                    collection_name="imo_regulations",
                    scroll_filter=Filter(must=[
                        FieldCondition(
                            key="chunk_id",
                            match=MatchValue(value=chunk_id),
                        )
                    ]),
                    limit=1,
                    with_payload=True,
                    with_vectors=False,
                )
                if results:
                    point = results[0]
                    json.dump(
                        {
                            "chunk_id": chunk_id,
                            "point_id": point.id,
                            "payload": point.payload,
                        },
                        f,
                        ensure_ascii=False,
                    )
                    f.write("\n")
                    count += 1
            except Exception as exc:
                logger.warning(f"Qdrant backup skip {chunk_id}: {exc}")

    logger.info(f"Qdrant payload backup: {backup_file} ({count} payloads)")
    return backup_file


# ---------------------------------------------------------------------------
# Phase 1: Plan generation
# ---------------------------------------------------------------------------

def generate_plan(conn) -> tuple[Path, dict]:
    """Scan all chunks and generate enrichment_plan.jsonl."""
    BACKUP_DIR.mkdir(exist_ok=True)
    cur = conn.cursor()

    cur.execute("""
        SELECT c.chunk_id, c.doc_id, c.text, c.metadata,
               r.document, r.chapter, r.regulation, r.collection, r.page_type
        FROM chunks c
        LEFT JOIN regulations r ON c.doc_id = r.doc_id
        WHERE (c.metadata->>'curated')::boolean IS NOT TRUE
           OR c.metadata->>'curated' IS NULL
        ORDER BY c.chunk_id
    """)

    stats = {
        "total": 0,
        "needs_enrichment": 0,
        "already_has_path": 0,
        "confidence_high": 0,
        "confidence_medium": 0,
        "confidence_low": 0,
        "confidence_none": 0,
        "by_document": {},
    }

    with open(PLAN_FILE, "w", encoding="utf-8") as f:
        for row in cur:
            (chunk_id, doc_id, text, metadata,
             doc, chapter, reg, collection, page_type) = row
            stats["total"] += 1

            metadata = (
                metadata if isinstance(metadata, dict)
                else json.loads(metadata or "{}")
            )

            if has_regulation_path(text):
                stats["already_has_path"] += 1
                continue

            reg_row = {
                "document": doc or "",
                "chapter": chapter or "",
                "regulation": reg or "",
                "collection": collection or "",
            }
            path_en, path_zh, confidence = infer_regulation_path(
                chunk_id, doc_id, text or "", metadata, reg_row,
            )

            stats[f"confidence_{confidence}"] += 1

            if confidence == "none":
                continue

            stats["needs_enrichment"] += 1

            doc_key = doc or metadata.get("document", "UNKNOWN")
            stats["by_document"][doc_key] = (
                stats["by_document"].get(doc_key, 0) + 1
            )

            prefix = build_bilingual_prefix(path_en, path_zh)
            new_text = prefix + (text or "")

            plan_entry = {
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "confidence": confidence,
                "path_en": path_en,
                "path_zh": path_zh,
                "prefix": prefix.strip(),
                "original_text_preview": (text or "")[:100],
                "new_text_preview": new_text[:150],
                "document": doc_key,
                "collection": collection or "",
            }
            json.dump(plan_entry, f, ensure_ascii=False)
            f.write("\n")

    cur.close()

    # Print statistics
    logger.info("\n=== Enrichment Plan Summary ===")
    logger.info(f"Total chunks scanned: {stats['total']}")
    logger.info(f"Already has path: {stats['already_has_path']}")
    logger.info(f"Needs enrichment: {stats['needs_enrichment']}")
    logger.info(f"  High confidence: {stats['confidence_high']}")
    logger.info(f"  Medium confidence: {stats['confidence_medium']}")
    logger.info(f"  Low confidence: {stats['confidence_low']}")
    logger.info(f"  Cannot infer: {stats['confidence_none']}")
    logger.info("\nBy document:")
    for doc, cnt in sorted(
        stats["by_document"].items(), key=lambda x: -x[1],
    )[:20]:
        logger.info(f"  {cnt:5d} | {doc}")
    logger.info(f"\nPlan saved to: {PLAN_FILE}")

    return PLAN_FILE, stats


# ---------------------------------------------------------------------------
# Phase 2: Validate
# ---------------------------------------------------------------------------

def validate_plan(plan_file: Path, sample_size: int = 50):
    """Stratified sample from plan for human inspection."""
    lines = plan_file.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        logger.error("Plan file is empty!")
        return

    entries = [json.loads(line) for line in lines]
    total = len(entries)

    high = [e for e in entries if e["confidence"] == "high"]
    medium = [e for e in entries if e["confidence"] == "medium"]
    low = [e for e in entries if e["confidence"] == "low"]

    sample: list[tuple[str, dict]] = []
    for group, name in [(high, "HIGH"), (medium, "MEDIUM"), (low, "LOW")]:
        if not group:
            continue
        n = min(max(int(sample_size * len(group) / total), 3), len(group))
        sample.extend([(name, e) for e in random.sample(group, n)])

    print(f"\n{'=' * 80}")
    print(f"VALIDATION SAMPLE ({len(sample)} items from {total} total)")
    print(f"{'=' * 80}\n")

    for i, (conf, entry) in enumerate(sample, 1):
        print(f"--- [{i}/{len(sample)}] Confidence: {conf} ---")
        print(f"  chunk_id: {entry['chunk_id']}")
        print(f"  document: {entry['document']}")
        print(f"  path_en:  {entry['path_en']}")
        print(f"  path_zh:  {entry['path_zh']}")
        print(f"  prefix:   {entry['prefix']}")
        print(f"  original: {entry['original_text_preview']}...")
        print(f"  new:      {entry['new_text_preview']}...")
        print()

    print(f"\nConfidence distribution:")
    print(f"  HIGH:   {len(high):5d} ({100 * len(high) / total:.1f}%)")
    print(f"  MEDIUM: {len(medium):5d} ({100 * len(medium) / total:.1f}%)")
    print(f"  LOW:    {len(low):5d} ({100 * len(low) / total:.1f}%)")


# ---------------------------------------------------------------------------
# Phase 3: Execute
# ---------------------------------------------------------------------------

def generate_embeddings_batch(
    oai_client: openai.OpenAI,
    texts: list[str],
) -> list[list[float]]:
    """Generate embeddings in one API call."""
    response = oai_client.embeddings.create(
        input=texts,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    return [item.embedding for item in response.data]


def execute_enrichment(
    conn,
    qdrant_client: QdrantClient,
    plan_file: Path,
    batch_filter: str = "all",
    batch_size: int = 50,
    start_from: int = 0,
    dry_run: bool = False,
    confidence_min: str = "low",
    pg_only: bool = False,
):
    """Phase 3: apply enrichment changes in batches with checkpointing."""
    # Read plan
    entries = []
    with open(plan_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    # Filter by batch
    filter_fn = BATCH_FILTERS.get(batch_filter, BATCH_FILTERS["all"])
    filtered = [e for e in entries if filter_fn(e)]

    # Filter by confidence
    min_level = CONFIDENCE_LEVELS.get(confidence_min, 1)
    filtered = [
        e for e in filtered
        if CONFIDENCE_LEVELS.get(e["confidence"], 0) >= min_level
    ]

    logger.info(
        f"Batch '{batch_filter}' (confidence >= {confidence_min}): "
        f"{len(filtered)} chunks to process"
    )

    if start_from > 0:
        filtered = filtered[start_from:]
        logger.info(f"Resuming from #{start_from}, {len(filtered)} remaining")

    if not filtered:
        logger.info("Nothing to process.")
        return

    if dry_run:
        logger.info("DRY RUN — no data will be modified")
        for e in filtered[:10]:
            logger.info(f"  Would update: {e['chunk_id']} → {e['prefix']}")
        logger.info(f"  ... ({len(filtered)} total)")
        return

    # === Backup ===
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    chunk_ids = [e["chunk_id"] for e in filtered]

    logger.info(f"\n=== Backing up {len(chunk_ids)} chunks ===")
    backup_file, backup_count = backup_chunks(chunk_ids, conn, timestamp)
    if backup_count != len(chunk_ids):
        logger.error(
            f"Backup count mismatch: {backup_count} vs {len(chunk_ids)}. "
            f"Some chunks may not exist in PG. Continuing with found chunks."
        )

    # Also backup Qdrant payloads (sampled for large sets)
    qdrant_backup_ids = chunk_ids[:200] if len(chunk_ids) > 200 else chunk_ids
    backup_qdrant_payloads(qdrant_backup_ids, qdrant_client, timestamp)

    # === Initialize embedding client ===
    oai_client = openai.OpenAI(api_key=settings.openai_api_key)

    # Checkpoint
    checkpoint_file = BACKUP_DIR / f"checkpoint_{batch_filter}_{timestamp}.txt"
    processed_count = 0
    error_count = 0
    cur = conn.cursor()

    # Process in batches
    total_batches = (len(filtered) + batch_size - 1) // batch_size

    for batch_start in range(0, len(filtered), batch_size):
        batch = filtered[batch_start : batch_start + batch_size]
        batch_num = batch_start // batch_size + 1

        logger.info(
            f"\n--- Batch {batch_num}/{total_batches} "
            f"({len(batch)} chunks) ---"
        )

        chunk_updates: list[dict] = []

        for entry in batch:
            chunk_id = entry["chunk_id"]
            prefix = entry["prefix"] + "\n\n"

            cur.execute(
                "SELECT text, text_for_embedding, metadata "
                "FROM chunks WHERE chunk_id = %s",
                (chunk_id,),
            )
            row = cur.fetchone()
            if not row:
                logger.warning(f"Chunk not found in PG: {chunk_id}")
                error_count += 1
                continue

            original_text, original_tfe, original_metadata = row
            original_metadata = (
                original_metadata
                if isinstance(original_metadata, dict)
                else json.loads(original_metadata or "{}")
            )

            # Skip already enriched
            if original_metadata.get("enriched"):
                logger.debug(f"Already enriched: {chunk_id}")
                continue

            new_text = prefix + original_text
            new_tfe = prefix + (original_tfe or original_text)

            new_metadata = {
                **original_metadata,
                "enriched": True,
                "enriched_at": timestamp,
                "path_en": entry["path_en"],
                "path_zh": entry["path_zh"],
                "enrichment_confidence": entry["confidence"],
            }
            if "original_text_hash" not in original_metadata:
                new_metadata["original_text_hash"] = hashlib.md5(
                    original_text.encode()
                ).hexdigest()[:12]

            chunk_updates.append({
                "chunk_id": chunk_id,
                "new_text": new_text,
                "new_tfe": new_tfe,
                "new_metadata": new_metadata,
                "path_en": entry["path_en"],
                "path_zh": entry["path_zh"],
            })

        if not chunk_updates:
            logger.info("No updates in this batch (all already enriched).")
            continue

        # === Generate embeddings (skip if pg_only) ===
        embeddings = None
        if not pg_only:
            embed_texts = [u["new_tfe"][:8000] for u in chunk_updates]
            try:
                embeddings = generate_embeddings_batch(oai_client, embed_texts)
            except Exception as exc:
                logger.error(f"Embedding API error at batch {batch_num}: {exc}")
                logger.info("Waiting 60s before retry...")
                time.sleep(60)
                try:
                    embeddings = generate_embeddings_batch(
                        oai_client, embed_texts,
                    )
                except Exception as exc2:
                    logger.error(f"Retry failed: {exc2}. Saving checkpoint.")
                    checkpoint_file.write_text(
                        str(batch_start + start_from), encoding="utf-8",
                    )
                    cur.close()
                    raise

        # === Update PostgreSQL ===
        for update in chunk_updates:
            cur.execute(
                "UPDATE chunks SET text = %s, text_for_embedding = %s, "
                "metadata = %s WHERE chunk_id = %s",
                (
                    update["new_text"],
                    update["new_tfe"],
                    json.dumps(update["new_metadata"], ensure_ascii=False),
                    update["chunk_id"],
                ),
            )
        conn.commit()

        # === Update Qdrant ===
        points_to_upsert: list[PointStruct] = []
        for i, update in enumerate(chunk_updates):
            try:
                results, _ = qdrant_client.scroll(
                    collection_name="imo_regulations",
                    scroll_filter=Filter(must=[
                        FieldCondition(
                            key="chunk_id",
                            match=MatchValue(value=update["chunk_id"]),
                        )
                    ]),
                    limit=1,
                    with_payload=True,
                    with_vectors=False,
                )

                if results:
                    point = results[0]
                    updated_payload = {
                        **point.payload,
                        "text": update["new_text"],
                        "text_for_embedding": update["new_tfe"][:8000],
                        "enriched": True,
                        "path_en": update["path_en"],
                        "path_zh": update["path_zh"],
                    }
                    if pg_only:
                        # Payload-only update: keep existing vector
                        qdrant_client.set_payload(
                            collection_name="imo_regulations",
                            payload=updated_payload,
                            points=[point.id],
                        )
                    else:
                        points_to_upsert.append(PointStruct(
                            id=point.id,
                            vector=embeddings[i],
                            payload=updated_payload,
                        ))
                else:
                    logger.warning(
                        f"Qdrant point not found: {update['chunk_id']}"
                    )
                    error_count += 1
            except Exception as exc:
                logger.warning(
                    f"Qdrant scroll error for {update['chunk_id']}: {exc}"
                )
                error_count += 1

        if points_to_upsert:
            qdrant_client.upsert(
                collection_name="imo_regulations",
                points=points_to_upsert,
            )

        processed_count += len(chunk_updates)

        # Save checkpoint
        checkpoint_file.write_text(
            str(batch_start + batch_size + start_from), encoding="utf-8",
        )

        logger.info(
            f"Batch {batch_num} done: {len(chunk_updates)} updated, "
            f"{len(points_to_upsert)} Qdrant points, "
            f"{error_count} errors, "
            f"processed: {processed_count}/{len(filtered)}"
        )

        # Rate limiting between batches
        time.sleep(1)

    cur.close()
    logger.info(f"\n=== Enrichment Complete ===")
    logger.info(f"Total processed: {processed_count}")
    logger.info(f"Total errors: {error_count}")
    logger.info(f"Checkpoint: {checkpoint_file}")


# ---------------------------------------------------------------------------
# Phase 4: Verify
# ---------------------------------------------------------------------------

def verify_enrichment(conn):
    """Post-execution quality check."""
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM chunks")
    total = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM chunks
        WHERE (metadata->>'enriched')::boolean = true
    """)
    enriched = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM chunks
        WHERE (metadata->>'curated')::boolean = true
    """)
    curated = cur.fetchone()[0]

    # Sample enriched chunks for format check
    cur.execute("""
        SELECT c.chunk_id, c.doc_id, LEFT(c.text, 300),
               c.metadata->>'path_en', c.metadata->>'path_zh',
               c.metadata->>'enrichment_confidence'
        FROM chunks c
        WHERE (c.metadata->>'enriched')::boolean = true
        ORDER BY RANDOM()
        LIMIT 20
    """)
    samples = cur.fetchall()

    # Count remaining chunks without paths (re-run diagnostic logic)
    cur.execute("""
        SELECT c.chunk_id, c.text
        FROM chunks c
        WHERE (c.metadata->>'curated')::boolean IS NOT TRUE
           OR c.metadata->>'curated' IS NULL
        ORDER BY RANDOM()
        LIMIT 2000
    """)
    sample_rows = cur.fetchall()
    still_missing = sum(
        1 for _, text in sample_rows if not has_regulation_path(text or "")
    )

    cur.close()

    logger.info("\n=== Verification Results ===")
    logger.info(f"Total chunks: {total}")
    logger.info(f"Enriched (metadata flag): {enriched}")
    logger.info(f"Curated: {curated}")
    logger.info(
        f"Enrichment rate: {100 * enriched / total:.1f}%"
        if total > 0 else "N/A"
    )

    sampled = len(sample_rows)
    if sampled > 0:
        missing_pct = 100 * still_missing / sampled
        logger.info(
            f"\nDiagnostic sample ({sampled} chunks): "
            f"{still_missing} still missing path ({missing_pct:.1f}%)"
        )
        if missing_pct < 5:
            logger.info("TARGET MET: missing rate < 5%")
        else:
            logger.warning(
                f"TARGET NOT MET: missing rate {missing_pct:.1f}% (goal: <5%)"
            )

    if samples:
        print("\n--- Sample enriched chunks (20) ---")
        for cid, did, text_preview, pen, pzh, conf in samples:
            print(f"  {cid} [{conf}]")
            print(f"    EN: {pen}")
            print(f"    ZH: {pzh}")
            print(f"    Text: {text_preview[:120]}...")
            print()


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

def rollback(conn, backup_file: str):
    """Restore PG data from backup file."""
    logger.warning(f"ROLLBACK from {backup_file}")

    cur = conn.cursor()
    restored = 0

    with open(backup_file, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            chunk_id = entry["chunk_id"]
            original_text = entry["original_text"]
            original_tfe = entry.get(
                "original_text_for_embedding", original_text,
            )
            original_metadata = entry["original_metadata"]

            cur.execute(
                "UPDATE chunks SET text = %s, text_for_embedding = %s, "
                "metadata = %s WHERE chunk_id = %s",
                (
                    original_text,
                    original_tfe,
                    json.dumps(original_metadata, ensure_ascii=False),
                    chunk_id,
                ),
            )
            restored += 1

    conn.commit()
    cur.close()
    logger.info(f"PostgreSQL: {restored} chunks restored")
    logger.warning(
        "Qdrant vectors NOT restored (would need re-embedding). "
        "Run full re-ingest if needed."
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Backfill regulation paths for BV-RAG chunks",
    )
    parser.add_argument(
        "--mode",
        choices=["plan", "validate", "execute", "verify", "rollback"],
        default="plan",
    )
    parser.add_argument(
        "--batch",
        choices=["all", "imo", "bv", "circular", "iacs"],
        default="all",
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--start-from", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--pg-only", action="store_true",
        help="Update PG text + Qdrant payload only, skip re-embedding vectors",
    )
    parser.add_argument("--rollback-file", type=str)
    parser.add_argument(
        "--confidence-min",
        choices=["high", "medium", "low"],
        default="low",
    )
    args = parser.parse_args()

    logger.info(f"=== Backfill Regulation Paths (mode={args.mode}) ===\n")

    # Initialize connections
    conn = psycopg2.connect(settings.database_url)
    conn.autocommit = False

    try:
        if args.mode == "plan":
            generate_plan(conn)

        elif args.mode == "validate":
            if not PLAN_FILE.exists():
                logger.error(f"Plan file not found: {PLAN_FILE}")
                logger.error("Run --mode plan first.")
                sys.exit(1)
            validate_plan(PLAN_FILE)

        elif args.mode == "execute":
            if not PLAN_FILE.exists():
                logger.error(f"Plan file not found: {PLAN_FILE}")
                sys.exit(1)
            qdrant = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                timeout=60,
            )
            execute_enrichment(
                conn,
                qdrant,
                plan_file=PLAN_FILE,
                batch_filter=args.batch,
                batch_size=args.batch_size,
                start_from=args.start_from,
                dry_run=args.dry_run,
                confidence_min=args.confidence_min,
                pg_only=args.pg_only,
            )

        elif args.mode == "verify":
            verify_enrichment(conn)

        elif args.mode == "rollback":
            if not args.rollback_file:
                logger.error("--rollback-file required for rollback mode")
                sys.exit(1)
            rollback(conn, args.rollback_file)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
