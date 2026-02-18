"""Practical knowledge base for senior surveyor experience."""
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class PracticalKnowledgeBase:
    """Surveyor practical knowledge that bridges regulation text and real-world practice.

    Loads YAML entries from ``knowledge/practical/*.yaml`` and exposes a
    keyword/regulation-based lookup so the pipeline can inject relevant
    practical context alongside retrieved regulation chunks.
    """

    def __init__(self, knowledge_dir: str = "knowledge/practical"):
        self.knowledge_dir = Path(knowledge_dir)
        self._by_id: dict[str, dict] = {}
        self._keyword_index: dict[str, list[str]] = {}
        self._reg_index: dict[str, list[str]] = {}
        self._load_all()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_all(self) -> None:
        if not self.knowledge_dir.exists():
            logger.warning(f"[PracticalKB] Dir not found: {self.knowledge_dir}")
            return

        for yaml_file in sorted(self.knowledge_dir.glob("*.yaml")):
            try:
                with open(yaml_file, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if not data or not isinstance(data, list):
                    continue
                for entry in data:
                    eid = entry.get("id", yaml_file.stem)
                    self._by_id[eid] = entry
                    for kw in entry.get("keywords", []):
                        self._keyword_index.setdefault(kw.lower(), []).append(eid)
                    for reg in entry.get("regulations", []):
                        self._reg_index.setdefault(reg.lower(), []).append(eid)
            except Exception as exc:
                logger.error(f"[PracticalKB] Failed to load {yaml_file}: {exc}")

        logger.info(f"[PracticalKB] Loaded {len(self._by_id)} entries")

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def query(
        self,
        user_query: str,
        matched_terms: set[str] | None = None,
        relevant_regs: set[str] | None = None,
    ) -> list[dict]:
        """Return up to 3 practical knowledge entries ranked by relevance.

        Entries with a ``scope_required`` field are only included when at
        least one scope keyword matches in the query.  This prevents broad
        ship-type matches from injecting topic-specific knowledge into
        unrelated queries (e.g. liferaft knowledge into ventilation queries).
        """
        scores: dict[str, int] = {}
        query_lower = user_query.lower()

        # keyword hits
        for kw, eids in self._keyword_index.items():
            if kw in query_lower:
                for eid in eids:
                    scores[eid] = scores.get(eid, 0) + 2

        # regulation hits
        if relevant_regs:
            for reg in relevant_regs:
                for eid in self._reg_index.get(reg.lower(), []):
                    scores[eid] = scores.get(eid, 0) + 3
        for reg, eids in self._reg_index.items():
            if reg in query_lower:
                for eid in eids:
                    scores[eid] = scores.get(eid, 0) + 2

        # matched_terms hits
        if matched_terms:
            for eid, entry in self._by_id.items():
                for term in entry.get("terms", []):
                    if term.lower() in matched_terms:
                        scores[eid] = scores.get(eid, 0) + 1

        # ship_type hits (only +1 to prevent ship-type-only matches
        # from dominating the ranking)
        for eid, entry in self._by_id.items():
            for st in entry.get("ship_types", []):
                if st.lower() in query_lower:
                    scores[eid] = scores.get(eid, 0) + 1

        # Scope gate: entries with scope_required must match at least one
        # scope keyword, otherwise they are excluded regardless of score.
        for eid, entry in list(self._by_id.items()):
            scope_words = entry.get("scope_required")
            if not scope_words:
                continue
            if eid not in scores:
                continue
            has_scope = any(sw.lower() in query_lower for sw in scope_words)
            if not has_scope:
                del scores[eid]

        # Minimum relevance threshold: require at least one keyword/reg
        # match (score >= 2) to prevent ship-type-only injections
        _MIN_SCORE = 2
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        results = []
        for eid, score in ranked[:3]:
            if score >= _MIN_SCORE:
                results.append(self._by_id[eid])
        return results

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def format_for_llm(entries: list[dict]) -> str:
        """Format entries into a markdown block for LLM context injection."""
        if not entries:
            return ""

        parts = ["## 验船实务参考（来自资深验船师经验）\n"]
        for entry in entries:
            parts.append(f"### {entry.get('title', 'N/A')}")
            parts.append(f"**适用法规**: {', '.join(entry.get('regulations', []))}")

            if entry.get("correct_interpretation"):
                parts.append(f"**正确理解**: {entry['correct_interpretation']}")
            if entry.get("common_mistake"):
                parts.append(f"**常见误解**: {entry['common_mistake']}")

            if entry.get("typical_configurations"):
                parts.append("**典型配置**:")
                for cfg in entry["typical_configurations"]:
                    parts.append(f"- {cfg}")

            if entry.get("decision_tree"):
                parts.append("**判断逻辑**:")
                for step in entry["decision_tree"]:
                    parts.append(f"- {step}")

            parts.append("")

        return "\n".join(parts)
