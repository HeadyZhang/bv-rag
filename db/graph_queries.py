"""Graph-style queries using PostgreSQL recursive CTEs (replaces Neo4j)."""
import logging

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


class GraphQueries:
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

    def get_children(self, doc_id: str) -> list[dict]:
        sql = """
            SELECT doc_id, title, breadcrumb, url, page_type
            FROM regulations
            WHERE parent_doc_id = %s
            ORDER BY doc_id
        """
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (doc_id,))
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"get_children error: {e}")
            return []

    def get_parent_chain(self, doc_id: str) -> list[dict]:
        sql = """
            WITH RECURSIVE ancestors AS (
                SELECT doc_id, parent_doc_id, title, breadcrumb, 0 as depth
                FROM regulations WHERE doc_id = %s
                UNION ALL
                SELECT r.doc_id, r.parent_doc_id, r.title, r.breadcrumb, a.depth + 1
                FROM regulations r JOIN ancestors a ON r.doc_id = a.parent_doc_id
                WHERE a.depth < 20
            )
            SELECT * FROM ancestors ORDER BY depth DESC
        """
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (doc_id,))
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"get_parent_chain error: {e}")
            return []

    def get_interpretations(self, doc_id: str) -> list[dict]:
        sql = """
            SELECT cr.*, r.title as source_title, r.url as source_url
            FROM cross_references cr
            LEFT JOIN regulations r ON cr.source_doc_id = r.doc_id
            WHERE cr.target_doc_id = %s AND cr.relation_type = 'INTERPRETS'
        """
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (doc_id,))
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"get_interpretations error: {e}")
            return []

    def get_amendments(self, doc_id: str) -> list[dict]:
        sql = """
            SELECT cr.*, r.title as source_title, r.url as source_url
            FROM cross_references cr
            LEFT JOIN regulations r ON cr.source_doc_id = r.doc_id
            WHERE cr.target_doc_id = %s AND cr.relation_type = 'AMENDS'
        """
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (doc_id,))
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"get_amendments error: {e}")
            return []

    def get_related_by_concept(self, concept_name: str) -> list[dict]:
        sql = """
            SELECT r.doc_id, r.title, r.breadcrumb, r.url, r.document, r.regulation
            FROM regulations r
            JOIN regulation_concepts rc ON r.doc_id = rc.doc_id
            JOIN concepts c ON rc.concept_id = c.concept_id
            WHERE LOWER(c.name) = LOWER(%s)
            LIMIT 20
        """
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (concept_name,))
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"get_related_by_concept error: {e}")
            return []

    def get_cross_document_regulations(self, doc_id: str) -> dict:
        referenced_by_sql = """
            SELECT cr.source_doc_id, cr.anchor_text, cr.relation_type,
                   r.title, r.url
            FROM cross_references cr
            LEFT JOIN regulations r ON cr.source_doc_id = r.doc_id
            WHERE cr.target_doc_id = %s
            LIMIT 20
        """
        references_sql = """
            SELECT cr.target_doc_id, cr.anchor_text, cr.relation_type,
                   r.title, r.url
            FROM cross_references cr
            LEFT JOIN regulations r ON cr.target_doc_id = r.doc_id
            WHERE cr.source_doc_id = %s
            LIMIT 20
        """
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(referenced_by_sql, (doc_id,))
                referenced_by = [dict(r) for r in cur.fetchall()]
                cur.execute(references_sql, (doc_id,))
                references = [dict(r) for r in cur.fetchall()]
                return {"referenced_by": referenced_by, "references": references}
        except Exception as e:
            logger.error(f"get_cross_document_regulations error: {e}")
            return {"referenced_by": [], "references": []}
