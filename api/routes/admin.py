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


@router.get("/session/{session_id}")
async def debug_session(session_id: str, request: Request):
    """Debug endpoint to inspect session contents."""
    memory = request.app.state.pipeline.memory
    session = memory.get_session(session_id)
    if not session:
        return {"error": "session not found", "session_id": session_id}
    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "turns_count": len(session.turns),
        "active_regulations": session.active_regulations,
        "active_topics": session.active_topics,
        "active_ship_type": session.active_ship_type,
        "turns": [
            {
                "role": t.role,
                "content": t.content[:100],
                "metadata": t.metadata,
            }
            for t in session.turns[-4:]
        ],
    }


@router.get("/utility-stats")
async def utility_stats(request: Request):
    """Show chunk utility learning statistics (MemRL)."""
    reranker = getattr(request.app.state, "utility_reranker", None)
    if not reranker:
        return {"status": "disabled", "message": "Utility reranker not enabled"}

    try:
        stats = reranker.get_stats()
        return {"status": "ok", "utility_stats": stats}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.post("/reindex")
async def reindex(request: Request):
    return {
        "status": "not_implemented",
        "message": "Run `python -m pipeline.ingest` locally to reindex.",
    }
