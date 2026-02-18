"""Qdrant Cloud vector search with multi-collection support."""
import logging

import openai
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from generation.generator import record_service_call

logger = logging.getLogger(__name__)

COLLECTION_NAME = "imo_regulations"

# Multi-collection config with authority-level weights
COLLECTIONS = {
    "imo_regulations": {"authority_weight": 1.0},
    "bv_rules": {"authority_weight": 0.7},
    "iacs_resolutions": {"authority_weight": 0.85},
}


class VectorStore:
    def __init__(self, qdrant_url: str, qdrant_api_key: str, openai_api_key: str):
        self.client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        self.oai = openai.OpenAI(api_key=openai_api_key, max_retries=3, timeout=30.0)
        self.model = "text-embedding-3-large"
        self.dimensions = 1024
        logger.info("OpenAI embedding client: max_retries=3, timeout=30s")

    def search(
        self,
        query_text: str,
        top_k: int = 10,
        document_filter: str | None = None,
        collection_filter: str | None = None,
        collections: list[str] | None = None,
    ) -> list[dict]:
        try:
            response = self.oai.embeddings.create(
                model=self.model,
                input=[query_text],
                dimensions=self.dimensions,
            )
            query_vector = response.data[0].embedding
            record_service_call("openai_embedding")
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return []

        conditions = []
        if document_filter:
            conditions.append(
                FieldCondition(key="document", match=MatchValue(value=document_filter))
            )
        if collection_filter:
            conditions.append(
                FieldCondition(key="collection", match=MatchValue(value=collection_filter))
            )

        query_filter = Filter(must=conditions) if conditions else None

        # Determine which collections to search
        target_collections = collections or [COLLECTION_NAME]

        all_results = []
        for coll_name in target_collections:
            try:
                if not self.client.collection_exists(coll_name):
                    continue
                authority_weight = COLLECTIONS.get(coll_name, {}).get("authority_weight", 1.0)

                results = self.client.query_points(
                    collection_name=coll_name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                    with_payload=True,
                )

                for point in results.points:
                    all_results.append({
                        "chunk_id": point.payload.get("chunk_id", ""),
                        "text": point.payload.get("text", ""),
                        "score": point.score * authority_weight,
                        "metadata": {
                            k: v for k, v in point.payload.items()
                            if k not in ("text", "text_for_embedding")
                        },
                    })
            except Exception as e:
                logger.error(f"Qdrant search error ({coll_name}): {e}")

        all_results.sort(key=lambda x: x["score"], reverse=True)
        return all_results[:top_k]

    def get_collection_info(self) -> dict:
        try:
            info = self.client.get_collection(COLLECTION_NAME)
            return {
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "status": info.status.value,
            }
        except Exception as e:
            logger.error(f"Collection info error: {e}")
            return {}
