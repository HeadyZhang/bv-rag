"""Cross-encoder reranking for improved retrieval precision.

Uses Cohere's multilingual reranker to re-score retrieved chunks
based on cross-attention relevance rather than cosine similarity.
"""
import logging

logger = logging.getLogger(__name__)


class CohereReranker:
    """Rerank retrieved chunks using Cohere's cross-encoder model."""

    def __init__(self, api_key: str, model: str = "rerank-multilingual-v3.0"):
        import cohere

        self.client = cohere.ClientV2(api_key=api_key)
        self.model = model

    def rerank(
        self,
        query: str,
        chunks: list[dict],
        top_n: int = 5,
    ) -> list[dict]:
        """Rerank chunks by cross-encoder relevance score.

        Args:
            query: The user's original query text.
            chunks: Retrieved chunks from hybrid search.
            top_n: Number of top results to return.

        Returns:
            Reranked list of chunks with added rerank_score field.
        """
        if not chunks:
            return chunks

        doc_texts = []
        for c in chunks:
            meta = c.get("metadata", {})
            prefix = f"{meta.get('breadcrumb', '')} - {meta.get('title', '')}"
            text = c.get("text", "")[:1000]
            doc_texts.append(f"{prefix}\n{text}" if prefix.strip(" -") else text)

        try:
            response = self.client.rerank(
                model=self.model,
                query=query,
                documents=doc_texts,
                top_n=min(top_n, len(chunks)),
            )
        except Exception as exc:
            logger.error(f"[Reranker] API error, returning original order: {exc}")
            return chunks[:top_n]

        reranked = []
        for result in response.results:
            original = {**chunks[result.index]}
            original["rerank_score"] = result.relevance_score
            original["original_rrf_rank"] = result.index
            reranked.append(original)

        top_scores = [round(r["rerank_score"], 3) for r in reranked[:3]]
        logger.info(
            f"[Reranker] Reranked {len(chunks)} -> top {len(reranked)}, "
            f"scores: {top_scores}"
        )
        return reranked
