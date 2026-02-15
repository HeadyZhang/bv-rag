"""Search API routes."""
import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["search"])


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    document_filter: str | None = None


@router.post("/search")
async def search(request: Request, body: SearchRequest):
    retriever = request.app.state.retriever
    results = retriever.retrieve(
        query=body.query,
        top_k=body.top_k,
    )
    return {
        "query": body.query,
        "results": [
            {
                "chunk_id": r.get("chunk_id"),
                "text": r.get("text", "")[:500],
                "score": r.get("score") or r.get("fused_score", 0),
                "metadata": r.get("metadata", {}),
            }
            for r in results
        ],
    }


@router.get("/regulation/{doc_id}")
async def get_regulation(request: Request, doc_id: str):
    from db.postgres import PostgresDB
    from config.settings import settings

    db = PostgresDB(settings.database_url)
    try:
        reg = db.get_regulation(doc_id)
        if not reg:
            return {"error": "Not found"}

        graph = request.app.state.graph
        children = graph.get_children(doc_id)
        cross_refs = graph.get_cross_document_regulations(doc_id)

        reg.pop("search_vector", None)

        return {
            "regulation": reg,
            "children": children,
            "cross_references": cross_refs,
        }
    finally:
        db.close()
