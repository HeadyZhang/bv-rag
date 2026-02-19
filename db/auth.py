"""User authentication database operations."""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import bcrypt
import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

_PASSWORD_PATTERN = re.compile(r"^(?=.*[a-zA-Z])(?=.*\d).{8,}$")


def validate_password(password: str) -> tuple[bool, str]:
    """Validate password meets requirements: >=8 chars, letters + digits."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not _PASSWORD_PATTERN.match(password):
        return False, "Password must contain at least one letter and one digit"
    return True, ""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


class AuthDB:
    """User authentication database operations."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._conn = None

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.database_url)
            self._conn.autocommit = True
        return self._conn

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    def create_user(self, email: str, password: str) -> dict:
        """Create a new user. Raises ValueError on validation failure."""
        ok, msg = validate_password(password)
        if not ok:
            raise ValueError(msg)

        pw_hash = hash_password(password)
        sql = """
            INSERT INTO users (email, password_hash)
            VALUES (%s, %s)
            RETURNING id, email, display_name, created_at
        """
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (email.lower().strip(), pw_hash))
                return dict(cur.fetchone())
        except psycopg2.errors.UniqueViolation:
            raise ValueError("Email already registered")

    def authenticate(self, email: str, password: str) -> Optional[dict]:
        """Authenticate user. Returns user dict or None."""
        sql = """
            SELECT id, email, password_hash, display_name, is_active
            FROM users WHERE email = %s
        """
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (email.lower().strip(),))
            row = cur.fetchone()

        if not row:
            return None
        if not row["is_active"]:
            return None
        if not verify_password(password, row["password_hash"]):
            return None

        # Update last_login
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET last_login = %s WHERE id = %s",
                (datetime.now(timezone.utc), row["id"]),
            )

        return {
            "id": str(row["id"]),
            "email": row["email"],
            "display_name": row["display_name"],
        }

    def get_user_by_id(self, user_id: str) -> Optional[dict]:
        sql = "SELECT id, email, display_name FROM users WHERE id = %s AND is_active = TRUE"
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (user_id,))
            row = cur.fetchone()
            if row:
                return {"id": str(row["id"]), "email": row["email"], "display_name": row["display_name"]}
            return None

    # --- Chat sessions ---

    def create_chat_session(self, user_id: str, title: str = "") -> dict:
        sql = """
            INSERT INTO chat_sessions (user_id, title)
            VALUES (%s, %s)
            RETURNING id, user_id, title, created_at, updated_at
        """
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (user_id, title))
            row = cur.fetchone()
            return {k: str(v) if k in ("id", "user_id") else v for k, v in dict(row).items()}

    def get_user_sessions(self, user_id: str, limit: int = 50) -> list[dict]:
        sql = """
            SELECT id, title, created_at, updated_at
            FROM chat_sessions
            WHERE user_id = %s
            ORDER BY updated_at DESC
            LIMIT %s
        """
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (user_id, limit))
            rows = cur.fetchall()
            return [{"id": str(r["id"]), **{k: v for k, v in dict(r).items() if k != "id"}} for r in rows]

    def add_chat_message(
        self, session_id: str, role: str, content: str, metadata: dict | None = None,
    ) -> dict:
        import json
        sql = """
            INSERT INTO chat_messages (session_id, role, content, metadata)
            VALUES (%s, %s, %s, %s)
            RETURNING id, session_id, role, content, created_at
        """
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (
                session_id, role, content,
                json.dumps(metadata) if metadata else None,
            ))
            row = cur.fetchone()

        # Update session timestamp and title (from first user message)
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE chat_sessions SET updated_at = NOW() WHERE id = %s",
                (session_id,),
            )
            if role == "user":
                cur.execute(
                    "UPDATE chat_sessions SET title = %s WHERE id = %s AND (title IS NULL OR title = '')",
                    (content[:100], session_id),
                )

        return {"id": str(row["id"]), **{k: v for k, v in dict(row).items() if k != "id"}}

    def get_session_messages(self, session_id: str) -> list[dict]:
        sql = """
            SELECT id, role, content, metadata, created_at
            FROM chat_messages
            WHERE session_id = %s
            ORDER BY created_at ASC
        """
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (session_id,))
            return [dict(r) for r in cur.fetchall()]
