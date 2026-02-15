"""BM25-style full-text search using PostgreSQL tsvector."""
import logging

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


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

    def search(self, query: str, top_k: int = 10, document_filter: str | None = None) -> list[dict]:
        sql = """
            SELECT doc_id, title, breadcrumb, url, body_text,
                   ts_rank_cd(search_vector, plainto_tsquery('english', %s), 32) as score
            FROM regulations
            WHERE search_vector @@ plainto_tsquery('english', %s)
              AND (%s::text IS NULL OR document = %s)
            ORDER BY score DESC
            LIMIT %s
        """
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (query, query, document_filter, document_filter, top_k))
                results = cur.fetchall()
                return [dict(r) for r in results]
        except Exception as e:
            logger.error(f"BM25 search error: {e}")
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
