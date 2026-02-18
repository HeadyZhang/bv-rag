"""BM25-style full-text search using PostgreSQL tsvector."""
import logging
import re

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\u2000-\u206f？！。，、；：""'']+")
_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9./-]{1,}")
_MAX_TERMS_PER_SECTION = 4


class BM25Search:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self._conn = None

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.database_url)
        return self._conn

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    @staticmethod
    def _prepare_query(query: str) -> str:
        """Convert enhanced query to websearch_to_tsquery format.

        Enhanced queries use '|' as section separator:
          "原始查询 | synonym_group | regulation_refs"
        Strategy: AND within sections (capped), OR between sections.
        Chinese characters are stripped since English tsvector can't index them.
        """
        sections = query.split("|")
        tsquery_parts: list[str] = []

        for section in sections:
            text = _CJK_RE.sub(" ", section).strip()
            if not text:
                continue
            tokens = _TOKEN_RE.findall(text)
            seen: set[str] = set()
            unique: list[str] = []
            for t in tokens:
                tl = t.lower()
                if tl not in seen and len(tl) > 1:
                    seen.add(tl)
                    unique.append(t)
            unique = unique[:_MAX_TERMS_PER_SECTION]
            if unique:
                tsquery_parts.append(" ".join(unique))

        if not tsquery_parts:
            text = _CJK_RE.sub(" ", query)
            tokens = _TOKEN_RE.findall(text)[:10]
            return " OR ".join(tokens) if tokens else query

        return " OR ".join(f"({p})" for p in tsquery_parts)

    def search(self, query: str, top_k: int = 10, document_filter: str | None = None) -> list[dict]:
        prepared = self._prepare_query(query)
        if not prepared or not prepared.strip():
            logger.warning("[BM25] Empty prepared query after CJK stripping")
            return []

        sql = """
            SELECT doc_id, title, breadcrumb, url, body_text,
                   ts_rank_cd(search_vector, websearch_to_tsquery('english', %s), 32) as score
            FROM regulations
            WHERE search_vector @@ websearch_to_tsquery('english', %s)
              AND (%s::text IS NULL OR document = %s)
            ORDER BY score DESC
            LIMIT %s
        """
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (prepared, prepared, document_filter, document_filter, top_k))
                results = cur.fetchall()
                results = [dict(r) for r in results]

                # Fallback: if tsvector search returned nothing, try ILIKE on
                # body_text for key English terms extracted from the query.
                # This catches curated chunks with rich English text.
                if not results:
                    fallback_terms = self._extract_fallback_terms(query)
                    if fallback_terms:
                        like_clauses = " OR ".join(
                            "body_text ILIKE %s" for _ in fallback_terms
                        )
                        fallback_sql = f"""
                            SELECT doc_id, title, breadcrumb, url, body_text,
                                   0.01 as score
                            FROM regulations
                            WHERE ({like_clauses})
                              AND (%s::text IS NULL OR document = %s)
                            LIMIT %s
                        """
                        params = [f"%{t}%" for t in fallback_terms]
                        params.extend([document_filter, document_filter, top_k])
                        cur.execute(fallback_sql, params)
                        results = [dict(r) for r in cur.fetchall()]
                        if results:
                            logger.info(f"[BM25] Fallback ILIKE found {len(results)} results")

                return results
        except Exception as e:
            logger.error(f"BM25 search error: {e}")
            try:
                self._conn = None
            except Exception:
                pass
            return []

    @staticmethod
    def _extract_fallback_terms(query: str) -> list[str]:
        """Extract key English phrases from the enhanced query for ILIKE fallback."""
        # Look for important fire/safety terms that should exist in body_text
        important_phrases = [
            "Table 9.1", "Table 9.2", "Table 9.3", "Table 9.4",
            "Table 9.5", "Table 9.6",
            "fire integrity", "fire division",
            "galley", "corridor", "control station",
            "Category 9", "Category 1", "Category 6",
            "ODME", "Regulation 34", "1/30000",
            "air pipe", "Regulation 20",
            "superstructure", "superstructure deck", "deckhouse",
            "freeboard deck", "first tier", "760 mm", "450 mm",
            "Regulation 3", "enclosed superstructure",
            "load lines", "ICLL",
        ]
        found = []
        query_lower = query.lower()
        for phrase in important_phrases:
            if phrase.lower() in query_lower:
                found.append(phrase)
        return found[:3]  # limit to avoid slow queries

    def search_by_regulation_number(self, reg_number: str, top_k: int = 10) -> list[dict]:
        sql = """
            SELECT doc_id, title, breadcrumb, url, body_text
            FROM regulations
            WHERE regulation ILIKE %s
               OR breadcrumb ILIKE %s
            LIMIT %s
        """
        pattern = f"%{reg_number}%"
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (pattern, pattern, top_k))
                results = cur.fetchall()
                return [dict(r) for r in results]
        except Exception as e:
            logger.error(f"Regulation number search error: {e}")
            return []
