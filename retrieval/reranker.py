"""Cross-encoder reranking for improved retrieval precision.

Uses Cohere's multilingual reranker to re-score retrieved chunks
based on cross-attention relevance rather than cosine similarity.
"""
import logging
import re

logger = logging.getLogger(__name__)

# Signals that a chunk contains configuration/carriage requirements
_CONFIG_REQUIREMENT_SIGNALS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"shall carry",
        r"shall be provided with",
        r"shall be equipped",
        r"shall comply with",
        r"are required to",
        r"in addition to complying",
        r"cargo ships of .{0,20} metres",
        r"passenger ships .{0,20} shall",
        r"every ship .{0,20} shall",
        r"shall not exceed",
        r"total quantity .{0,20} discharged",
    ]
]

# Signals that a chunk contains equipment technical specifications
_EQUIPMENT_SPEC_SIGNALS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"shall be capable of",
        r"shall withstand",
        r"shall be of sufficient strength",
        r"when suspended from",
        r"proof load test",
        r"breaking strength",
        r"buoyancy .{0,20} shall be",
        r"shall be so designed",
        r"nominal length .{0,20} shall",
    ]
]

# Query patterns that indicate the user wants applicability/requirement info
_APPLICABILITY_QUERY_RE = re.compile(
    r"(是否|需不需要|是否需要|必须|要不要|需要.*吗|是不是.*需要|不需要.*了"
    r"|do .{0,5} need|is .{0,5} required|must .{0,5} have|shall .{0,5} carry"
    r"|不能超过|限制|限值|limit|exceed)",
    re.IGNORECASE,
)


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
        query_intent: str | None = None,
    ) -> list[dict]:
        """Rerank chunks by cross-encoder relevance score.

        Args:
            query: The user's original query text.
            chunks: Retrieved chunks from hybrid search.
            top_n: Number of top results to return.
            query_intent: Optional intent from classifier (e.g. "applicability").

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

        # Apply config-vs-spec boost for applicability queries
        is_applicability = (
            query_intent == "applicability"
            or bool(_APPLICABILITY_QUERY_RE.search(query))
        )
        if is_applicability:
            reranked = _apply_config_boost(reranked)

        top_scores = [round(r["rerank_score"], 3) for r in reranked[:3]]
        logger.info(
            f"[Reranker] Reranked {len(chunks)} -> top {len(reranked)}, "
            f"scores: {top_scores}, config_boost={is_applicability}"
        )
        return reranked


def _apply_config_boost(chunks: list[dict]) -> list[dict]:
    """Boost configuration-requirement chunks, penalize equipment-spec chunks.

    For applicability queries, users need to know "what must I carry/do",
    not "what are the technical specifications of the equipment".
    """
    boosted = []
    for chunk in chunks:
        text = chunk.get("text", "")
        score = chunk.get("rerank_score", 0.0)

        has_config = any(pat.search(text) for pat in _CONFIG_REQUIREMENT_SIGNALS)
        has_spec = any(pat.search(text) for pat in _EQUIPMENT_SPEC_SIGNALS)

        if has_config and not has_spec:
            score *= 1.25
        elif has_spec and not has_config:
            score *= 0.75

        boosted.append({**chunk, "rerank_score": score})

    boosted.sort(key=lambda x: x["rerank_score"], reverse=True)
    return boosted
