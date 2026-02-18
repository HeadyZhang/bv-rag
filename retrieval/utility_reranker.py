"""MemRL-inspired Utility-Aware Reranker for maritime regulation RAG.

Maintains per-chunk utility scores based on historical usage effectiveness.
Chunks that are frequently cited in high-confidence answers get higher scores.
Chunks that are retrieved but never cited get demoted over time.

Two-Phase Retrieval (adapted from MemRL):
  Phase A: Existing Vector + BM25 + Graph -> RRF fusion (semantic recall)
  Phase B: This module - utility-aware reranking (value selection)

Runtime Learning:
  After each answer, update utility scores using EMA (Exponential Moving Average).
"""
import logging

logger = logging.getLogger(__name__)


class UtilityReranker:
    """Rerank chunks based on historical utility scores."""

    def __init__(self, pg_conn, alpha: float = 0.3, learning_rate: float = 0.1):
        """Initialize the utility reranker.

        Args:
            pg_conn: PostgreSQL connection with execute/fetchall methods.
            alpha: Weight of utility in final score (0.3 = 70% RRF + 30% utility).
                   Start low when utility data is sparse, increase as data accumulates.
            learning_rate: EMA update rate for utility scores.
        """
        self.pg_conn = pg_conn
        self.alpha = alpha
        self.lr = learning_rate

    def rerank(
        self,
        chunks: list[dict],
        query_category: str = "general",
    ) -> list[dict]:
        """Phase B: Utility-Aware Selection.

        Args:
            chunks: RRF-fused candidates (each has rrf_score).
            query_category: Regulatory domain (fire_safety, pollution, etc.).

        Returns:
            Reranked chunks with final_score and utility_score fields.
        """
        if not chunks:
            return chunks

        chunk_ids = [c.get("chunk_id", c.get("doc_id", "")) for c in chunks]
        utilities = self._batch_get_utilities(chunk_ids, query_category)

        # Compute max RRF for normalization
        max_rrf = max(
            (c.get("rrf_score", c.get("score", 0.0)) for c in chunks),
            default=0.1,
        )
        if max_rrf == 0:
            max_rrf = 0.1

        reranked = []
        for chunk in chunks:
            updated = {**chunk}
            cid = chunk.get("chunk_id", chunk.get("doc_id", ""))
            utility = utilities.get(cid, 0.5)
            rrf = chunk.get("rrf_score", chunk.get("score", 0.0))

            rrf_norm = min(rrf / max_rrf, 1.0)
            final_score = (1 - self.alpha) * rrf_norm + self.alpha * utility

            updated["utility_score"] = utility
            updated["final_score"] = final_score
            reranked.append(updated)

        reranked.sort(key=lambda x: x["final_score"], reverse=True)

        top_info = [(round(r["final_score"], 3), round(r["utility_score"], 2)) for r in reranked[:3]]
        logger.info(
            f"[UtilityReranker] category={query_category}, "
            f"top scores: {top_info}"
        )
        return reranked

    def update_utilities(
        self,
        retrieved_chunks: list[dict],
        cited_chunk_ids: set[str],
        confidence: str,
        query_category: str = "general",
    ) -> None:
        """Update utility scores after answering (Runtime Learning).

        Reward/penalty rules:
        - Cited + high confidence: reward = +1.0
        - Cited + medium confidence: reward = +0.5
        - Retrieved but not cited + high confidence: reward = -0.1
        - Retrieved but not cited + low confidence: reward = -0.3
        - All chunks when answer is "unable to answer": reward = -0.5
        """
        for chunk in retrieved_chunks:
            cid = chunk.get("chunk_id", chunk.get("doc_id", ""))
            if not cid:
                continue

            is_cited = cid in cited_chunk_ids

            if confidence == "high":
                reward = 1.0 if is_cited else -0.1
            elif confidence == "medium":
                reward = 0.5 if is_cited else 0.0
            else:
                reward = 0.0 if is_cited else -0.3

            self._update_utility(cid, query_category, reward)

    def _update_utility(self, chunk_id: str, category: str, reward: float) -> None:
        """EMA update: utility = (1 - lr) * old + lr * reward."""
        success = 1 if reward > 0 else 0
        initial_utility = max(0.0, min(1.0, 0.5 + reward * self.lr))

        sql = """
        INSERT INTO chunk_utilities (chunk_id, query_category, utility_score, use_count, success_count, last_used)
        VALUES (%s, %s, %s, 1, %s, NOW())
        ON CONFLICT (chunk_id, query_category)
        DO UPDATE SET
            utility_score = GREATEST(0.0, LEAST(1.0,
                (1 - %s) * chunk_utilities.utility_score + %s * %s
            )),
            use_count = chunk_utilities.use_count + 1,
            success_count = chunk_utilities.success_count + %s,
            last_used = NOW()
        """
        try:
            self.pg_conn.execute(sql, (
                chunk_id, category, initial_utility, success,
                self.lr, self.lr, reward, success,
            ))
        except Exception as exc:
            logger.error(f"[UtilityReranker] Failed to update utility for {chunk_id}: {exc}")

    def _batch_get_utilities(self, chunk_ids: list[str], category: str) -> dict[str, float]:
        """Batch-fetch utility scores from PostgreSQL."""
        if not chunk_ids:
            return {}

        placeholders = ",".join(["%s"] * len(chunk_ids))
        sql = f"""
        SELECT chunk_id, utility_score
        FROM chunk_utilities
        WHERE chunk_id IN ({placeholders}) AND query_category = %s
        """
        try:
            results = self.pg_conn.fetchall(sql, (*chunk_ids, category))
            return {r[0]: r[1] for r in results}
        except Exception as exc:
            logger.error(f"[UtilityReranker] Failed to fetch utilities: {exc}")
            return {}

    def get_stats(self) -> list[dict]:
        """Get utility learning statistics per category."""
        sql = """
        SELECT query_category,
               COUNT(*) as total_chunks,
               AVG(utility_score) as avg_utility,
               AVG(use_count) as avg_uses,
               COUNT(CASE WHEN utility_score > 0.7 THEN 1 END) as high_utility,
               COUNT(CASE WHEN utility_score < 0.3 THEN 1 END) as low_utility
        FROM chunk_utilities
        GROUP BY query_category
        ORDER BY total_chunks DESC
        """
        try:
            results = self.pg_conn.fetchall(sql)
            return [
                {
                    "category": r[0],
                    "total_chunks": r[1],
                    "avg_utility": round(r[2], 3) if r[2] else 0,
                    "avg_uses": round(r[3], 1) if r[3] else 0,
                    "high_utility": r[4],
                    "low_utility": r[5],
                }
                for r in results
            ]
        except Exception as exc:
            logger.error(f"[UtilityReranker] Failed to get stats: {exc}")
            return []
