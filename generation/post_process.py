"""Post-processing for LLM answers.

Fixes generic regulation URLs by replacing them with specific page URLs
from the retrieved source metadata, or removes them entirely.
"""
import re


# Pattern: [Some Ref] → generic-imorules-link (with optional trailing text)
_GENERIC_LINK_PATTERN = re.compile(
    r"\[([^\]]+)\]"                     # [regulation ref]
    r"\s*→\s*"                          # → arrow
    r"(https?://)?(www\.)?imorules\.com"  # generic imorules domain
    r"[^\n]*"                           # rest of the line
)

# Pattern: bare generic URLs not in [ref] → url format
_BARE_GENERIC_URL = re.compile(
    r"(?<!\[URL: )"              # not a source metadata tag
    r"(https?://)?(www\.)?"      # optional protocol/www
    r"imorules\.com/?(?!\S*GUID)"  # generic, not specific
    r"(?!\S)"                    # end of URL
)


def fix_source_links(answer: str, sources: list[dict] | None = None) -> str:
    """Replace generic imorules.com links with specific URLs from sources.

    If a specific URL for the cited regulation is found in ``sources``,
    substitute it. Otherwise, remove the generic link entirely (a missing
    link is better than a fake one).
    """
    source_url_map = _build_source_url_map(sources or [])

    def _replace_ref_link(match: re.Match) -> str:
        ref = match.group(1)
        url = _find_url_for_ref(ref, source_url_map)
        if url:
            return f"[{ref}] → {url}"
        # No specific URL — keep the ref but drop the generic link
        return f"[{ref}]"

    result = _GENERIC_LINK_PATTERN.sub(_replace_ref_link, answer)

    # Also strip any remaining bare generic URLs
    result = _BARE_GENERIC_URL.sub("", result)

    return result


def _build_source_url_map(sources: list[dict]) -> dict[str, str]:
    """Build a mapping from breadcrumb/regulation keywords to specific URLs."""
    url_map: dict[str, str] = {}
    for src in sources:
        url = src.get("url", "")
        breadcrumb = src.get("breadcrumb", "")
        is_generic = (
            "imorules.com" in url
            and "/" not in url.split("imorules.com")[-1]
        )
        if not url or is_generic:
            continue  # skip generic URLs
        # Index by breadcrumb segments for fuzzy matching
        key = breadcrumb.lower().strip()
        if key:
            url_map[key] = url
        # Also index by common regulation patterns found in breadcrumb
        for token in _extract_reg_tokens(breadcrumb):
            url_map[token] = url
    return url_map


def _extract_reg_tokens(breadcrumb: str) -> list[str]:
    """Extract regulation identifiers from a breadcrumb string."""
    tokens: list[str] = []
    # Match patterns like "SOLAS II-2/9", "MARPOL Annex I/15", "Reg 9"
    for m in re.finditer(
        r"(SOLAS|MARPOL|STCW|COLREG|LSA|FSS|IBC|IGC|ICLL)"
        r"[\s\-]*(?:Annex\s*)?[IVX\d\-/\.]+",
        breadcrumb,
        re.IGNORECASE,
    ):
        tokens.append(m.group(0).lower().strip())
    # Also match "Reg X" or "Regulation X"
    for m in re.finditer(r"Reg(?:ulation)?\s*[\d\.\-/]+", breadcrumb, re.IGNORECASE):
        tokens.append(m.group(0).lower().strip())
    # Match "Table X.Y"
    for m in re.finditer(r"Table\s*[\d\.]+", breadcrumb, re.IGNORECASE):
        tokens.append(m.group(0).lower().strip())
    return tokens


def _find_url_for_ref(ref: str, url_map: dict[str, str]) -> str:
    """Find the best matching URL for a regulation reference."""
    ref_lower = ref.lower().strip()

    # Direct match
    if ref_lower in url_map:
        return url_map[ref_lower]

    # Partial match: check if any key is contained in the ref or vice versa
    best_url = ""
    best_overlap = 0
    for key, url in url_map.items():
        if key in ref_lower or ref_lower in key:
            overlap = min(len(key), len(ref_lower))
            if overlap > best_overlap:
                best_overlap = overlap
                best_url = url

    # Extract regulation tokens from ref and match against map
    if not best_url:
        for token in _extract_reg_tokens(ref):
            if token in url_map:
                return url_map[token]

    return best_url
