"""Qdrant Cloud vector search."""
import logging

import openai
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

logger = logging.getLogger(__name__)

COLLECTION_NAME = "imo_regulations"


class VectorStore:
    def __init__(self, qdrant_url: str, qdrant_api_key: str, openai_api_key: str):
        self.client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        self.oai = openai.OpenAI(api_key=openai_api_key)
        self.model = "text-embedding-3-large"
        self.dimensions = 1024

    def search(
        self,
        query_text: str,
        top_k: int = 10,
        document_filter: str | None = None,
        collection_filter: str | None = None,
    ) -> list[dict]:
        try:
            response = self.oai.embeddings.create(
                model=self.model,
                input=[query_text],
                dimensions=self.dimensions,
            )
            query_vector = response.data[0].embedding
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

        try:
            results = self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )

            return [
                {
                    "chunk_id": point.payload.get("chunk_id", ""),
                    "text": point.payload.get("text", ""),
                    "score": point.score,
                    "metadata": {
                        k: v for k, v in point.payload.items()
                        if k not in ("text", "text_for_embedding")
                    },
                }
                for point in results.points
            ]
        except Exception as e:
            logger.error(f"Qdrant search error: {e}")
            return []

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
