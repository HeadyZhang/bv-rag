"""Defect Knowledge Base for PSC inspection deficiency predictions.

Provides fast (<50ms) lookups by area, ship_type, category, and chinese
keyword matching.  Used by the extension /predict and /complete endpoints
to return instant suggestions without calling the LLM.

Data lives in ``data/defect_kb.json`` (built by scripts/build_defect_kb.py).
"""
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class DefectKnowledgeBase:
    """In-memory defect knowledge base backed by a JSON file.

    Indexes are pre-built in the JSON and loaded at startup for O(1) lookups.
    All public methods are synchronous and allocation-light so they can be
    called under ``KB_ONLY_SEMAPHORE`` without blocking the event loop.
    """

    def __init__(self, data_path: str = "data/defect_kb.json") -> None:
        self._path = Path(data_path)
        self._version: str = ""
        self._updated_at: str = ""
        self._defects_by_id: dict[str, dict] = {}
        self._defects_list: list[dict] = []
        self._by_area: dict[str, list[str]] = {}
        self._by_ship_type: dict[str, list[str]] = {}
        self._by_category: dict[str, list[str]] = {}
        self._chinese_keyword_map: dict[str, list[str]] = {}
        self._all_chinese_triggers: list[tuple[str, str]] = []
        self._load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            logger.warning("[DefectKB] File not found: %s", self._path)
            return

        try:
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("[DefectKB] Failed to load %s: %s", self._path, exc)
            return

        self._version = data.get("version", "0.0.0")
        self._updated_at = data.get("updated_at", "")

        for defect in data.get("defects", []):
            did = defect["id"]
            self._defects_by_id[did] = defect
            self._defects_list.append(defect)

        idx = data.get("index", {})
        self._by_area = idx.get("by_area", {})
        self._by_ship_type = idx.get("by_ship_type", {})
        self._by_category = idx.get("by_category", {})
        self._chinese_keyword_map = idx.get("chinese_keyword_map", {})

        # Pre-sort triggers by length (longest first) for greedy matching
        for trigger, ids in self._chinese_keyword_map.items():
            for did in ids:
                self._all_chinese_triggers.append((trigger, did))
        self._all_chinese_triggers.sort(key=lambda t: len(t[0]), reverse=True)

        logger.info(
            "[DefectKB] Loaded %d defects (v%s), %d chinese triggers",
            len(self._defects_by_id),
            self._version,
            len(self._chinese_keyword_map),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_version(self) -> dict:
        """Return current KB version metadata."""
        return {
            "version": self._version,
            "updated_at": self._updated_at,
            "defect_count": len(self._defects_by_id),
        }

    def query(
        self,
        *,
        ship_type: str = "",
        area: str = "",
        inspection_type: str = "",
        input_text: str = "",
        top_k: int = 8,
    ) -> list[dict]:
        """Context-aware defect prediction.

        Scores each defect by how well it matches the given context
        (ship_type, area, inspection_type) and any chinese keyword hits
        from ``input_text``.  Returns up to ``top_k`` results sorted by
        relevance then frequency_rank.

        This is the primary method for the /predict endpoint.
        """
        scores: dict[str, float] = {}
        ship_type_lower = _normalize(ship_type)
        area_lower = _normalize(area)
        inspection_lower = _normalize(inspection_type)
        input_lower = input_text.lower()

        # 1. Area match (+3 per hit)
        if area_lower:
            for did in self._by_area.get(area_lower, []):
                scores[did] = scores.get(did, 0) + 3

        # 2. Ship type match (+2 per hit)
        if ship_type_lower:
            for did in self._by_ship_type.get(ship_type_lower, []):
                scores[did] = scores.get(did, 0) + 2
            # "all" ship type entries get a smaller boost
            for did in self._by_ship_type.get("all", []):
                scores[did] = scores.get(did, 0) + 1

        # 3. Chinese keyword match from input text (+5 per hit — highest signal)
        if input_lower:
            matched_ids = self._match_chinese_triggers(input_lower)
            for did in matched_ids:
                scores[did] = scores.get(did, 0) + 5

        # 4. Inspection type match (+1)
        if inspection_lower:
            for defect in self._defects_list:
                for insp in defect.get("applicable_inspections", []):
                    if inspection_lower in insp.lower():
                        scores[defect["id"]] = scores.get(defect["id"], 0) + 1
                        break

        # If no context at all, return top by frequency_rank
        if not scores:
            sorted_all = sorted(
                self._defects_list,
                key=lambda d: d.get("frequency_rank", 999),
            )
            return [self._format_result(d) for d in sorted_all[:top_k]]

        # Sort by score desc, then frequency_rank asc
        ranked = sorted(
            scores.items(),
            key=lambda item: (-item[1], self._defects_by_id[item[0]].get("frequency_rank", 999)),
        )
        results = []
        for did, _score in ranked[:top_k]:
            results.append(self._format_result(self._defects_by_id[did]))
        return results

    def search_by_keyword(self, keyword: str, top_k: int = 10) -> list[dict]:
        """Search defects by chinese or english keyword.

        Used by the /complete endpoint for partial text matching.
        """
        keyword_lower = keyword.lower().strip()
        if not keyword_lower:
            return []

        scores: dict[str, float] = {}

        # Chinese trigger match
        matched_ids = self._match_chinese_triggers(keyword_lower)
        for did in matched_ids:
            scores[did] = scores.get(did, 0) + 5

        # English text match (standard_text_en, subcategory)
        for defect in self._defects_list:
            did = defect["id"]
            en_text = defect.get("standard_text_en", "").lower()
            subcat = defect.get("subcategory", "").lower()
            cat = defect.get("category", "").lower()

            if keyword_lower in en_text:
                scores[did] = scores.get(did, 0) + 3
            if keyword_lower in subcat:
                scores[did] = scores.get(did, 0) + 2
            if keyword_lower in cat:
                scores[did] = scores.get(did, 0) + 1

        ranked = sorted(
            scores.items(),
            key=lambda item: (-item[1], self._defects_by_id[item[0]].get("frequency_rank", 999)),
        )
        return [self._format_result(self._defects_by_id[did]) for did, _ in ranked[:top_k]]

    def exact_match(self, defect_id: str) -> dict | None:
        """Return a single defect by ID, or None."""
        defect = self._defects_by_id.get(defect_id)
        if defect is None:
            return None
        return self._format_result(defect, include_variants=True)

    def get_updates_since(self, since_version: str) -> list[dict]:
        """Return defects added/modified after ``since_version``.

        For now, since we only have v1.0.0, this returns all defects when
        the client's version doesn't match.  As we add version tracking,
        this will return only the delta.
        """
        if since_version == self._version:
            return []
        return [self._format_result(d) for d in self._defects_list]

    def get_by_category(self, category: str, top_k: int = 20) -> list[dict]:
        """Return defects for a given category, sorted by frequency."""
        ids = self._by_category.get(category, [])
        defects = [self._defects_by_id[did] for did in ids if did in self._defects_by_id]
        defects.sort(key=lambda d: d.get("frequency_rank", 999))
        return [self._format_result(d) for d in defects[:top_k]]

    def format_for_llm(self, defect_results: list[dict]) -> str:
        """Format defect results as context for LLM prompt injection."""
        if not defect_results:
            return ""

        parts = ["## Relevant PSC Defect References\n"]
        for item in defect_results[:5]:
            parts.append(f"- **{item['id']}**: {item['standard_text_en']}")
            refs = item.get("regulation_refs", [])
            if refs:
                ref_strs = [f"{r['convention']} {r['ref']}" for r in refs]
                parts.append(f"  Refs: {', '.join(ref_strs)}")
            if item.get("detention_risk") == "high":
                parts.append("  **Detention risk: HIGH**")
            parts.append("")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _match_chinese_triggers(self, text: str) -> list[str]:
        """Return defect IDs matching chinese triggers in text.

        Uses longest-match-first to prefer more specific triggers.
        """
        matched: list[str] = []
        seen: set[str] = set()
        for trigger, did in self._all_chinese_triggers:
            if trigger in text and did not in seen:
                matched.append(did)
                seen.add(did)
        return matched

    def _format_result(self, defect: dict, *, include_variants: bool = False) -> dict:
        """Create a clean result dict from a raw defect entry."""
        result = {
            "id": defect["id"],
            "category": defect["category"],
            "subcategory": defect.get("subcategory", ""),
            "standard_text_en": defect["standard_text_en"],
            "standard_text_zh": defect.get("standard_text_zh", ""),
            "regulation_refs": defect.get("regulation_refs", []),
            "detention_risk": defect.get("detention_risk", "medium"),
            "frequency_rank": defect.get("frequency_rank", 999),
        }
        if defect.get("paris_mou_code"):
            result["paris_mou_code"] = defect["paris_mou_code"]
        if include_variants and defect.get("variants"):
            result["variants"] = defect["variants"]
        return result


def _normalize(value: str) -> str:
    """Normalize a context value for index lookup.

    Maps common English forms to the snake_case keys used in the JSON
    index (e.g. "Engine Room" -> "engine_room", "Bulk Carrier" -> "bulk_carrier").
    """
    if not value:
        return ""
    v = value.strip().lower()
    v = re.sub(r"[\s\-/]+", "_", v)
    return v
