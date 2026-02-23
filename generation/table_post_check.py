"""Post-check module for table lookup validation in LLM answers.

Catches two classes of errors:
  1. Ship-type / table mismatch (e.g., tanker answer citing Table 9.5)
  2. Known-value mismatch (e.g., answering A-60 when the cell is A-0)

Designed to be called after LLM generation, before returning the answer
to the user.  When errors are found, returns correction context that can
be injected into a regeneration prompt.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known correct values for high-frequency table lookups
# Key format: "Table X.Y|(row)|(col)" → expected fire rating
# ---------------------------------------------------------------------------
KNOWN_TABLE_VALUES: dict[str, str] = {
    # Table 9.5 — Cargo ships other than tankers (bulkheads)
    "Table 9.5|(1)|(1)": "A-0",
    "Table 9.5|(1)|(2)": "A-0",
    "Table 9.5|(1)|(3)": "A-60",
    "Table 9.5|(1)|(4)": "A-0",
    "Table 9.5|(1)|(5)": "A-15",
    "Table 9.5|(1)|(6)": "A-60",
    "Table 9.5|(1)|(7)": "A-15",
    "Table 9.5|(1)|(8)": "A-60",
    "Table 9.5|(1)|(9)": "A-60",
    "Table 9.5|(2)|(2)": "C",
    "Table 9.5|(2)|(3)": "B-0",
    "Table 9.5|(2)|(4)": "B-0",
    "Table 9.5|(2)|(5)": "B-0",
    "Table 9.5|(2)|(6)": "A-60",
    "Table 9.5|(2)|(7)": "A-0",
    "Table 9.5|(2)|(8)": "A-60",
    "Table 9.5|(2)|(9)": "A-0",
    "Table 9.5|(3)|(3)": "C",
    "Table 9.5|(3)|(6)": "A-60",
    "Table 9.5|(3)|(7)": "A-0",
    "Table 9.5|(3)|(8)": "A-60",
    "Table 9.5|(3)|(9)": "A-0",
    "Table 9.5|(6)|(6)": "A-0",
    "Table 9.5|(6)|(9)": "A-60",
    # Table 9.7 — Tankers (bulkheads)
    "Table 9.7|(1)|(1)": "A-0",
    "Table 9.7|(1)|(2)": "A-0",
    "Table 9.7|(1)|(3)": "A-60",
    "Table 9.7|(1)|(4)": "A-0",
    "Table 9.7|(1)|(5)": "A-15",
    "Table 9.7|(1)|(6)": "A-60",
    "Table 9.7|(1)|(7)": "A-15",
    "Table 9.7|(1)|(8)": "A-60",
    "Table 9.7|(1)|(9)": "A-60",
    "Table 9.7|(2)|(2)": "C",
    "Table 9.7|(2)|(3)": "B-0",
    "Table 9.7|(2)|(4)": "B-0",
    "Table 9.7|(2)|(5)": "B-0",
    "Table 9.7|(2)|(6)": "A-60",
    "Table 9.7|(2)|(7)": "A-0",
    "Table 9.7|(2)|(8)": "A-60",
    "Table 9.7|(2)|(9)": "A-0",
    "Table 9.7|(3)|(3)": "C",
    "Table 9.7|(3)|(6)": "A-60",
    "Table 9.7|(3)|(7)": "A-0",
    "Table 9.7|(3)|(8)": "A-60",
    "Table 9.7|(3)|(9)": "A-0",
    "Table 9.7|(6)|(6)": "A-0",
    "Table 9.7|(6)|(9)": "A-60",
    # Table 9.1 — Passenger ships >36 pax (bulkheads) — key lookups
    "Table 9.1|(1)|(1)": "A-0",
    "Table 9.1|(1)|(2)": "A-0",
    "Table 9.1|(1)|(3)": "A-60",
    "Table 9.1|(1)|(6)": "A-60",
    "Table 9.1|(2)|(2)": "B-0",
    "Table 9.1|(2)|(3)": "B-0",
    "Table 9.1|(2)|(9)": "B-15",
    "Table 9.1|(3)|(6)": "A-60",
    "Table 9.1|(6)|(6)": "A-0",
    "Table 9.1|(6)|(9)": "A-60",
    # Table 9.3 — Passenger ships ≤36 pax (bulkheads) — same as 9.5
    "Table 9.3|(1)|(1)": "A-0",
    "Table 9.3|(1)|(2)": "A-0",
    "Table 9.3|(1)|(3)": "A-60",
    "Table 9.3|(1)|(6)": "A-60",
    "Table 9.3|(2)|(2)": "C",
    "Table 9.3|(2)|(3)": "B-0",
    "Table 9.3|(2)|(9)": "A-0",
    "Table 9.3|(3)|(6)": "A-60",
    "Table 9.3|(6)|(6)": "A-0",
    "Table 9.3|(6)|(9)": "A-60",
}

# ---------------------------------------------------------------------------
# Ship-type → valid table mapping
# ---------------------------------------------------------------------------
SHIP_TYPE_VALID_TABLES: dict[str, list[str]] = {
    "tanker": ["9.7", "9.8"],
    "cargo_ship_non_tanker": ["9.5", "9.6"],
    "passenger_ship": ["9.1", "9.2", "9.3", "9.4"],
    "passenger_ship_gt36": ["9.1", "9.2"],
    "passenger_ship_le36": ["9.3", "9.4"],
}

# Reverse: table → expected ship types
TABLE_TO_SHIP_TYPES: dict[str, list[str]] = {
    "9.1": ["passenger_ship", "passenger_ship_gt36"],
    "9.2": ["passenger_ship", "passenger_ship_gt36"],
    "9.3": ["passenger_ship", "passenger_ship_le36"],
    "9.4": ["passenger_ship", "passenger_ship_le36"],
    "9.5": ["cargo_ship_non_tanker"],
    "9.6": ["cargo_ship_non_tanker"],
    "9.7": ["tanker"],
    "9.8": ["tanker"],
}

# ---------------------------------------------------------------------------
# Regex patterns for extracting info from answers
# ---------------------------------------------------------------------------
_TABLE_REF_RE = re.compile(r"Table\s*9\.(\d)", re.IGNORECASE)
_FIRE_RATING_RE = re.compile(r"\b(A-60|A-30|A-15|A-0|B-15|B-0|C)\b")
_CATEGORY_RE = re.compile(
    r"[Cc]ategory\s*\(?(\d{1,2})\)?\s*.*?[Cc]ategory\s*\(?(\d{1,2})\)?",
)
_CATEGORY_CN_RE = re.compile(
    r"[（(](\d{1,2})[)）]\s*[×xX×]\s*[（(](\d{1,2})[)）]",
)


def extract_ship_type_from_text(text: str) -> str | None:
    """Detect ship type from combined query + answer text."""
    lower = text.lower()

    tanker_kw = [
        "tanker", "油轮", "化学品船", "成品油轮", "可燃液体",
        "flammable liquid", "inflammable",
    ]
    if any(kw in lower for kw in tanker_kw):
        return "tanker"

    passenger_kw = ["passenger", "客船", "客轮", "邮轮"]
    if any(kw in lower for kw in passenger_kw):
        return "passenger_ship"

    cargo_kw = [
        "bulk carrier", "散货船", "集装箱船", "container ship",
        "杂货船", "general cargo", "货船", "cargo ship",
    ]
    if any(kw in lower for kw in cargo_kw):
        return "cargo_ship_non_tanker"

    return None


def extract_table_references(text: str) -> list[str]:
    """Extract all SOLAS Table 9.X references from text."""
    return sorted({m.group(1) for m in _TABLE_REF_RE.finditer(text)})


def extract_categories_from_answer(text: str) -> tuple[int, int] | None:
    """Extract category pair (row, col) from answer text.

    Looks for patterns like "Category (1) × Category (2)" or "(1)×(2)".
    """
    m = _CATEGORY_CN_RE.search(text)
    if m:
        return (int(m.group(1)), int(m.group(2)))

    m = _CATEGORY_RE.search(text)
    if m:
        return (int(m.group(1)), int(m.group(2)))

    return None


def extract_fire_rating_from_answer(text: str) -> str | None:
    """Extract the primary fire rating conclusion from the answer.

    Looks for bold-formatted ratings first (likely the main conclusion),
    then falls back to the first rating found.
    """
    # Bold patterns: **A-0**, **A-60** etc.
    bold = re.search(r"\*\*(A-60|A-30|A-15|A-0|B-15|B-0|C)\*\*", text)
    if bold:
        return bold.group(1)

    all_ratings = _FIRE_RATING_RE.findall(text)
    return all_ratings[0] if all_ratings else None


# ---------------------------------------------------------------------------
# Main post-check function
# ---------------------------------------------------------------------------

def post_check_table_lookup(
    answer: str,
    query: str,
    chunks: list[dict] | None = None,
) -> dict:
    """Validate table references and values in an LLM answer.

    Returns:
        {
            "has_table_lookup": bool,
            "ship_type_detected": str | None,
            "tables_cited": list[str],
            "warnings": list[dict],
            "should_regenerate": bool,
            "correction_context": str,  # inject into regeneration prompt
        }
    """
    combined_text = f"{query} {answer}"
    warnings: list[dict] = []

    # 1. Detect ship type
    ship_type = extract_ship_type_from_text(combined_text)

    # 2. Detect table references
    tables_cited = extract_table_references(answer)

    if not tables_cited:
        return {
            "has_table_lookup": False,
            "ship_type_detected": ship_type,
            "tables_cited": [],
            "warnings": [],
            "should_regenerate": False,
            "correction_context": "",
        }

    # 3. Ship-type / table consistency check
    # tables_cited contains just the digit (e.g., "7" for Table 9.7)
    # SHIP_TYPE_VALID_TABLES values are like "9.7" — strip the "9." prefix for comparison
    if ship_type:
        valid_table_digits = [
            v.replace("9.", "") for v in SHIP_TYPE_VALID_TABLES.get(ship_type, [])
        ]
        if valid_table_digits:
            for t in tables_cited:
                if t not in valid_table_digits:
                    correct_tables = ", ".join(
                        f"Table 9.{d}" for d in valid_table_digits
                    )
                    warnings.append({
                        "level": "ERROR",
                        "type": "table_ship_type_mismatch",
                        "message": (
                            f"{ship_type} 应使用 {correct_tables}，"
                            f"但回答引用了 Table 9.{t}"
                        ),
                        "fix_suggestion": (
                            f"请使用 SOLAS II-2/Reg 9 中适用于 {ship_type} 的 "
                            f"{correct_tables}"
                        ),
                    })

    # 4. Known-value verification
    categories = extract_categories_from_answer(answer)
    if categories:
        row, col = categories
        # Normalize: always use smaller index first (table is symmetric)
        cat_lo, cat_hi = min(row, col), max(row, col)
        actual_rating = extract_fire_rating_from_answer(answer)

        for t in tables_cited:
            key = f"Table 9.{t}|({cat_lo})|({cat_hi})"
            expected = KNOWN_TABLE_VALUES.get(key)
            if expected and actual_rating and actual_rating != expected:
                warnings.append({
                    "level": "ERROR",
                    "type": "table_value_mismatch",
                    "message": (
                        f"查 {key} 应为 {expected}，但回答给出 {actual_rating}"
                    ),
                    "fix_suggestion": f"正确值为 {expected}",
                })

    # 5. Build correction context for regeneration
    should_regenerate = any(w["level"] == "ERROR" for w in warnings)
    correction_lines = []
    for w in warnings:
        if w["level"] == "ERROR":
            correction_lines.append(
                f"CORRECTION: {w['message']}. {w.get('fix_suggestion', '')}"
            )

    correction_context = "\n".join(correction_lines) if correction_lines else ""

    if warnings:
        for w in warnings:
            logger.warning(
                f"[TABLE_POST_CHECK] [{w['level']}] {w['type']}: {w['message']}"
            )

    return {
        "has_table_lookup": True,
        "ship_type_detected": ship_type,
        "tables_cited": [f"9.{t}" for t in tables_cited],
        "warnings": warnings,
        "should_regenerate": should_regenerate,
        "correction_context": correction_context,
    }
