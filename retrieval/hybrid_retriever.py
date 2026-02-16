"""Hybrid retrieval: vector + BM25 + graph with RRF fusion."""
import logging
import re
from collections import defaultdict

from db.bm25_search import BM25Search
from db.graph_queries import GraphQueries
from retrieval.query_enhancer import QueryEnhancer
from retrieval.query_router import QueryRouter
from retrieval.vector_store import VectorStore

logger = logging.getLogger(__name__)

_COMPLEX_QUERY_RE = re.compile(r"(\d+)\s*(米|m|吨|GT|DWT)", re.IGNORECASE)
_APPLICABILITY_KW = ["是否", "需不需要", "是否需要", "do I need", "要不要"]


class HybridRetriever:
    def __init__(
        self,
        vector_store: VectorStore,
        bm25_search: BM25Search,
        graph_queries: GraphQueries,
    ):
        self.vector_store = vector_store
        self.bm25 = bm25_search
        self.graph = graph_queries
        self.router = QueryRouter()
        self.query_enhancer = QueryEnhancer()

    def retrieve(self, query: str, top_k: int = 10, strategy: str = "auto") -> list[dict]:
        # Enhance query with maritime terminology
        enhanced_query = self.query_enhancer.enhance(query)

        # Dynamic top_k based on regulation count in enhanced query
        reg_count = len(re.findall(
            r"SOLAS|LSA|MARPOL|FSS|MSC|STCW|COLREG", enhanced_query,
        ))
        if reg_count >= 3:
            effective_top_k = min(top_k + 5, 15)
        elif reg_count >= 2:
            effective_top_k = min(top_k + 3, 12)
        elif bool(_COMPLEX_QUERY_RE.search(query)) or any(
            kw in query for kw in _APPLICABILITY_KW
        ):
            effective_top_k = min(top_k * 2, 15)
        else:
            effective_top_k = top_k
        logger.info(
            f"[Retriever] reg_count={reg_count}, "
            f"effective_top_k={effective_top_k}"
        )

        route_result = self.router.route(query)
        if strategy == "auto":
            strategy = route_result["strategy"]

        entities = route_result["entities"]
        doc_filter = entities.get("document_filter")
        concept = entities.get("concept")

        all_results = {}

        if strategy in ("hybrid", "semantic"):
            vector_results = self.vector_store.search(
                query_text=enhanced_query,
                top_k=effective_top_k * 2,
                document_filter=doc_filter,
            )
            for rank, r in enumerate(vector_results):
                cid = r["chunk_id"]
                if cid not in all_results:
                    all_results[cid] = {**r, "sources": [], "rrf_score": 0.0}
                all_results[cid]["sources"].append("vector")
                all_results[cid]["rrf_score"] += 1.0 / (60 + rank)

        if strategy in ("hybrid", "keyword"):
            bm25_results = self.bm25.search(
                query=enhanced_query,
                top_k=effective_top_k * 2,
                document_filter=doc_filter,
            )
            for rank, r in enumerate(bm25_results):
                doc_id = r["doc_id"]
                pseudo_cid = f"bm25__{doc_id}"
                if pseudo_cid not in all_results:
                    all_results[pseudo_cid] = {
                        "chunk_id": pseudo_cid,
                        "text": (r.get("body_text") or "")[:2000],
                        "score": r.get("score", 0),
                        "metadata": {
                            "doc_id": doc_id,
                            "title": r.get("title", ""),
                            "breadcrumb": r.get("breadcrumb", ""),
                            "url": r.get("url", ""),
                        },
                        "sources": [],
                        "rrf_score": 0.0,
                    }
                all_results[pseudo_cid]["sources"].append("bm25")
                all_results[pseudo_cid]["rrf_score"] += 1.0 / (60 + rank)

        if strategy == "hybrid":
            graph_results = []
            if concept:
                graph_results = self.graph.get_related_by_concept(concept)
            elif entities.get("regulation_ref"):
                ref_results = self.bm25.search_by_regulation_number(
                    entities["regulation_ref"], top_k=1
                )
                if ref_results:
                    target_doc_id = ref_results[0]["doc_id"]
                    interps = self.graph.get_interpretations(target_doc_id)
                    amends = self.graph.get_amendments(target_doc_id)
                    graph_results = interps + amends

            for rank, r in enumerate(graph_results):
                doc_id = r.get("doc_id") or r.get("source_doc_id", "")
                pseudo_cid = f"graph__{doc_id}"
                if pseudo_cid not in all_results:
                    all_results[pseudo_cid] = {
                        "chunk_id": pseudo_cid,
                        "text": r.get("anchor_text", "") or r.get("title", ""),
                        "score": 0,
                        "metadata": {
                            "doc_id": doc_id,
                            "title": r.get("title", r.get("source_title", "")),
                            "url": r.get("url", r.get("source_url", "")),
                            "breadcrumb": r.get("breadcrumb", ""),
                        },
                        "sources": [],
                        "rrf_score": 0.0,
                    }
                all_results[pseudo_cid]["sources"].append("graph")
                all_results[pseudo_cid]["rrf_score"] += 1.0 / (60 + rank)

        sorted_results = sorted(
            all_results.values(),
            key=lambda x: x["rrf_score"],
            reverse=True,
        )[:effective_top_k]

        for result in sorted_results:
            result["fused_score"] = result["rrf_score"]
            result["graph_context"] = self._get_graph_context(result)

        return sorted_results

    def _get_graph_context(self, result: dict) -> dict:
        doc_id = result.get("metadata", {}).get("doc_id", "")
        if not doc_id or doc_id.startswith("bm25__") or doc_id.startswith("graph__"):
            doc_id = doc_id.replace("bm25__", "").replace("graph__", "")
        if not doc_id:
            return {}

        try:
            parent_chain = self.graph.get_parent_chain(doc_id)
            breadcrumb_path = " > ".join(
                p.get("title", "") for p in parent_chain if p.get("title")
            )
            interps = self.graph.get_interpretations(doc_id)
            return {
                "breadcrumb_path": breadcrumb_path,
                "has_interpretations": len(interps) > 0,
                "interpretation_count": len(interps),
            }
        except Exception:
            return {}
