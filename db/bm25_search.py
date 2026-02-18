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
                return [dict(r) for r in results]
        except Exception as e:
            logger.error(f"BM25 search error: {e}")
            try:
                self._conn = None
            except Exception:
                pass
            return []

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
