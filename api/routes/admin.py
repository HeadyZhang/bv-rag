"""Admin API routes."""
import logging

from fastapi import APIRouter, Request

from config.settings import settings
from db.postgres import PostgresDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/stats")
async def stats(request: Request):
    db = PostgresDB(settings.database_url)
    try:
        pg_stats = db.get_stats()
    finally:
        db.close()

    qdrant_info = request.app.state.vector_store.get_collection_info()

    try:
        redis_client = request.app.state.memory.redis_client
        session_keys = redis_client.keys("session:*")
        redis_sessions = len(session_keys)
    except Exception:
        redis_sessions = -1

    return {
        **pg_stats,
        "qdrant_points": qdrant_info.get("points_count", 0),
        "qdrant_status": qdrant_info.get("status", "unknown"),
        "redis_sessions": redis_sessions,
    }


@router.post("/reindex")
async def reindex(request: Request):
    return {
        "status": "not_implemented",
        "message": "Run `python -m pipeline.ingest` locally to reindex.",
    }
