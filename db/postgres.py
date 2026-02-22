"""PostgreSQL connection and data operations."""
import json
import logging
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


class PostgresDB:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self._conn = None

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.database_url)
            self._conn.autocommit = False
        return self._conn

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    def init_schema(self):
        schema_path = Path(__file__).parent / "schema.sql"
        sql = schema_path.read_text(encoding="utf-8")
        with self.conn.cursor() as cur:
            cur.execute(sql)
        self.conn.commit()
        logger.info("Schema initialized")

    def insert_regulation(self, doc: dict):
        parent_doc_id = ""
        parent_url = doc.get("parent_url", "")
        if parent_url:
            path = urlparse(parent_url).path
            filename = path.rstrip("/").split("/")[-1]
            if filename.endswith(".html"):
                filename = filename[:-5]
            parent_doc_id = filename

        sql = """
            INSERT INTO regulations (
                doc_id, url, title, breadcrumb, collection, document,
                chapter, part, regulation, paragraph, body_text,
                page_type, version, parent_doc_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (doc_id) DO UPDATE SET
                title = EXCLUDED.title,
                body_text = EXCLUDED.body_text,
                breadcrumb = EXCLUDED.breadcrumb
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (
                doc["doc_id"], doc["url"], doc.get("title", ""),
                doc.get("breadcrumb", ""), doc.get("collection", ""),
                doc.get("document", ""), doc.get("chapter", ""),
                doc.get("part", ""), doc.get("regulation", ""),
                doc.get("paragraph", ""), doc.get("body_text", ""),
                doc.get("page_type", ""), doc.get("version", ""),
                parent_doc_id,
            ))

    def insert_chunk(self, chunk: dict):
        sql = """
            INSERT INTO chunks (chunk_id, doc_id, url, text, text_for_embedding, metadata, token_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (chunk_id) DO NOTHING
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (
                chunk["chunk_id"], chunk["doc_id"], chunk.get("url", ""),
                chunk["text"], chunk["text_for_embedding"],
                json.dumps(chunk.get("metadata", {})),
                chunk.get("token_count", 0),
            ))

    def insert_cross_references(self, doc_id: str, refs: list):
        if not refs:
            return
        sql = """
            INSERT INTO cross_references (source_doc_id, target_doc_id, target_url, anchor_text, context, relation_type)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        with self.conn.cursor() as cur:
            for ref in refs:
                target_url = ref.get("target_url", "")
                target_doc_id = ""
                if target_url:
                    path = urlparse(target_url).path
                    filename = path.rstrip("/").split("/")[-1]
                    if filename.endswith(".html"):
                        filename = filename[:-5]
                    target_doc_id = filename

                relation_type = self._classify_relation(ref.get("target_text", ""), ref.get("context", ""))
                cur.execute(sql, (
                    doc_id, target_doc_id, target_url,
                    ref.get("target_text", ""), ref.get("context", "")[:200],
                    relation_type,
                ))

    def batch_insert_cross_references(self, all_docs: list, batch_size: int = 2000):
        """Batch insert cross-references using execute_values for speed."""
        rows = []
        for doc in all_docs:
            doc_id = doc.get("doc_id", "")
            for ref in doc.get("cross_references", []):
                target_url = ref.get("target_url", "")
                target_doc_id = ""
                if target_url:
                    path = urlparse(target_url).path
                    filename = path.rstrip("/").split("/")[-1]
                    if filename.endswith(".html"):
                        filename = filename[:-5]
                    target_doc_id = filename
                relation_type = self._classify_relation(ref.get("target_text", ""), ref.get("context", ""))
                rows.append((
                    doc_id, target_doc_id, target_url,
                    ref.get("target_text", ""), ref.get("context", "")[:200],
                    relation_type,
                ))

        sql = "INSERT INTO cross_references (source_doc_id, target_doc_id, target_url, anchor_text, context, relation_type) VALUES %s"
        with self.conn.cursor() as cur:
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                psycopg2.extras.execute_values(cur, sql, batch, page_size=batch_size)
                self.conn.commit()
                logger.info(f"Inserted cross-references {i} to {i + len(batch)} of {len(rows)}")

    def _classify_relation(self, anchor_text: str, context: str) -> str:
        combined = f"{anchor_text} {context}".lower()
        if any(w in combined for w in ["interpret", "unified interpretation", "clarif"]):
            return "INTERPRETS"
        if any(w in combined for w in ["amend", "revise", "supersed"]):
            return "AMENDS"
        return "REFERENCES"

    def link_concepts(self, doc_id: str, body_text: str):
        if not body_text:
            return
        body_lower = body_text.lower()
        with self.conn.cursor() as cur:
            cur.execute("SELECT concept_id, name FROM concepts")
            concepts = cur.fetchall()

            for concept_id, name in concepts:
                if name.lower() in body_lower:
                    cur.execute(
                        "INSERT INTO regulation_concepts (doc_id, concept_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (doc_id, concept_id),
                    )

    def batch_link_concepts(self, all_docs: list, batch_size: int = 2000):
        """Batch link concepts using execute_values for speed."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT concept_id, name FROM concepts")
            concepts = cur.fetchall()

        rows = []
        for doc in all_docs:
            doc_id = doc.get("doc_id", "")
            body_text = doc.get("body_text", "")
            if not body_text:
                continue
            body_lower = body_text.lower()
            for concept_id, name in concepts:
                if name.lower() in body_lower:
                    rows.append((doc_id, concept_id))

        sql = "INSERT INTO regulation_concepts (doc_id, concept_id) VALUES %s ON CONFLICT DO NOTHING"
        with self.conn.cursor() as cur:
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                psycopg2.extras.execute_values(cur, sql, batch, page_size=batch_size)
                self.conn.commit()
                logger.info(f"Linked concepts {i} to {i + len(batch)} of {len(rows)}")

    def batch_insert_regulations(self, docs: list, batch_size: int = 500):
        for i in range(0, len(docs), batch_size):
            batch = docs[i:i + batch_size]
            for doc in batch:
                try:
                    self.insert_regulation(doc)
                except Exception as e:
                    logger.error(f"Error inserting regulation {doc.get('doc_id')}: {e}")
            self.conn.commit()
            logger.info(f"Inserted regulations {i} to {i + len(batch)}")

    def batch_insert_chunks(self, chunks: list, batch_size: int = 500):
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            for chunk in batch:
                try:
                    self.insert_chunk(chunk)
                except Exception as e:
                    logger.error(f"Error inserting chunk {chunk.get('chunk_id')}: {e}")
            self.conn.commit()
            logger.info(f"Inserted chunks {i} to {i + len(batch)}")

    def get_regulation(self, doc_id: str) -> dict | None:
        sql = "SELECT * FROM regulations WHERE doc_id = %s"
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (doc_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_stats(self) -> dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM regulations")
            reg_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM chunks")
            chunk_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM cross_references")
            xref_count = cur.fetchone()[0]
            return {
                "total_regulations": reg_count,
                "total_chunks": chunk_count,
                "total_cross_references": xref_count,
            }
