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

# Source-type weight multipliers for reranking (Workflow 3: P3 fix)
# Convention/Code text is the primary source; Circulars are supplementary.
SOURCE_WEIGHT: dict[str, float] = {
    "curated": 1.30,       # curated chunks — highest priority
    "convention": 1.15,     # SOLAS/MARPOL/ICLL convention text
    "code": 1.10,           # IBC/IGC/FSS/LSA/ISM Code
    "resolution": 0.95,     # MSC/MEPC resolutions
    "circular": 0.85,       # MSC/MEPC circulars — supplementary, downweighted
    "bv_rules": 1.05,       # BV classification rules
    "iacs": 1.00,           # IACS unified requirements
    "default": 1.00,
}

# Query category classification for utility reranking
_QUERY_CATEGORIES: dict[str, list[str]] = {
    "fire_safety": ["防火", "fire", "A-0", "A-60", "B-15", "防火分隔", "灭火"],
    "lifesaving": ["救生", "liferaft", "davit", "lifeboat", "救生筏", "救生艇"],
    "pollution": ["排放", "MARPOL", "排油", "ODME", "OWS", "污水", "压载水"],
    "stability": ["稳性", "stability", "freeboard", "载重线", "干舷"],
    "structure": ["结构", "强度", "strength", "scantling", "板厚"],
    "machinery": ["机械", "machinery", "engine", "boiler", "锅炉"],
    "navigation": ["航行", "navigation", "ECDIS", "AIS", "雷达"],
    "survey": ["检验", "survey", "PSC", "certificate", "证书"],
}


def normalize_ship_type_for_regulation(ship_type: str) -> str:
    """Normalize a user-provided ship type string into a regulation category.

    Categories:
      - "tanker" — oil tankers, chemical tankers, product tankers
      - "passenger_ship_gt36" — passenger ships carrying >36 passengers
      - "passenger_ship_le36" — passenger ships carrying ≤36 passengers
      - "passenger_ship" — passenger ship (unspecified count)
      - "cargo_ship_non_tanker" — bulk carriers, container ships, general cargo, etc.
    """
    lower = ship_type.lower()

    tanker_keywords = [
        "tanker", "oil tanker", "chemical tanker", "product tanker",
        "油轮", "化学品船", "成品油轮", "原油轮",
        "可燃液体", "flammable liquid", "inflammable",
    ]
    if any(kw in lower for kw in tanker_keywords):
        return "tanker"

    passenger_keywords = ["passenger", "客船", "客轮", "cruise", "邮轮"]
    if any(kw in lower for kw in passenger_keywords):
        if "36" in lower:
            # Check ≤36 FIRST (because "不超过36" contains "超过36")
            le36_markers = ["≤36", "<=36", "不超过36", "不多于36", "le36", "36人以下"]
            if any(marker in lower for marker in le36_markers):
                return "passenger_ship_le36"
            gt36_markers = [">36", "超过36", "多于36", "gt36", "36人以上"]
            if any(marker in lower for marker in gt36_markers):
                return "passenger_ship_gt36"
        return "passenger_ship"

    return "cargo_ship_non_tanker"


class HybridRetriever:
    def __init__(
        self,
        vector_store: VectorStore,
        bm25_search: BM25Search,
        graph_queries: GraphQueries,
        cohere_reranker=None,
        utility_reranker=None,
    ):
        self.vector_store = vector_store
        self.bm25 = bm25_search
        self.graph = graph_queries
        self.router = QueryRouter()
        self.query_enhancer = QueryEnhancer()
        self.cohere_reranker = cohere_reranker
        self.utility_reranker = utility_reranker

    def retrieve_with_applicability(
        self,
        query: str,
        ship_type: str | None = None,
        top_k: int = 10,
        strategy: str = "auto",
        query_intent: str | None = None,
    ) -> list[dict]:
        """Retrieve chunks with applicability-aware filtering.

        If a ship_type is provided (or can be extracted from the query),
        prioritize chunks whose metadata.applicability matches the ship type
        and deprioritize chunks that explicitly exclude it.
        """
        # Auto-detect ship type from query if not provided
        if not ship_type:
            ship_type = self.query_enhancer.extract_ship_type_from_query(query)

        # Fetch extra candidates for filtering headroom
        raw_chunks = self.retrieve(
            query=query,
            top_k=top_k * 2 if ship_type else top_k,
            strategy=strategy,
            query_intent=query_intent,
        )

        if not ship_type:
            return raw_chunks[:top_k]

        normalized = normalize_ship_type_for_regulation(ship_type)
        logger.info(f"[APPLICABILITY] ship_type='{ship_type}' → normalized='{normalized}'")

        matched: list[dict] = []
        neutral: list[dict] = []
        conflicting: list[dict] = []

        for chunk in raw_chunks:
            app = chunk.get("metadata", {}).get("applicability", {})

            if not app or not app.get("ship_types"):
                neutral.append(chunk)
                continue

            exclusions = app.get("ship_type_exclusions", [])
            if any(normalized in exc or exc in normalized for exc in exclusions):
                conflicting.append(chunk)
                continue

            types = app.get("ship_types", [])
            if any(normalized in t or t in normalized for t in types):
                matched.append(chunk)
            else:
                neutral.append(chunk)

        result = matched + neutral
        if len(result) < top_k:
            for c in conflicting:
                ship_types_label = c.get("metadata", {}).get("applicability", {}).get("ship_types", [])
                c["_applicability_warning"] = (
                    f"This chunk is for {ship_types_label}, not for {ship_type}"
                )
            result.extend(conflicting)

        logger.info(
            f"[APPLICABILITY] matched={len(matched)} neutral={len(neutral)} "
            f"conflicting={len(conflicting)} → returning {min(len(result), top_k)}"
        )

        return result[:top_k]

    def retrieve(self, query: str, top_k: int = 10, strategy: str = "auto", query_intent: str | None = None) -> list[dict]:
        # Enhance query with maritime terminology
        enhanced_query = self.query_enhancer.enhance(query)

        logger.info(f"[RETRIEVAL] 原始查询: {query[:100]}")
        logger.info(f"[RETRIEVAL] 增强查询: {enhanced_query[:200]}")

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

        # Determine which Qdrant collections to search
        search_collections = self._determine_search_collections(enhanced_query)
        logger.info(f"[RETRIEVAL] Collections: {search_collections}")

        if strategy in ("hybrid", "semantic"):
            vector_results = self.vector_store.search(
                query_text=enhanced_query,
                top_k=effective_top_k * 2,
                document_filter=doc_filter,
                collections=search_collections,
            )
            logger.info(f"[RETRIEVAL] 向量检索返回 {len(vector_results)} 条")
            for i, r in enumerate(vector_results[:5]):
                logger.info(
                    f"[RETRIEVAL]   Vec {i+1}: score={r.get('score', 0):.4f} "
                    f"title={r.get('metadata', {}).get('title', '?')[:80]}"
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
            logger.info(f"[RETRIEVAL] BM25 检索返回 {len(bm25_results)} 条")
            for i, r in enumerate(bm25_results[:5]):
                logger.info(
                    f"[RETRIEVAL]   BM25 {i+1}: "
                    f"title={r.get('title', '?')[:80]}"
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

        logger.info(f"[RETRIEVAL] RRF 融合后: {len(sorted_results)} 条")

        # Phase B-1: Cohere cross-encoder reranking
        if self.cohere_reranker:
            try:
                sorted_results = self.cohere_reranker.rerank(
                    query=query,
                    chunks=sorted_results,
                    top_n=effective_top_k,
                    query_intent=query_intent,
                )
            except Exception as exc:
                logger.error(f"[RETRIEVAL] Cohere rerank failed: {exc}")

        # Phase B-2: Utility-aware reranking (MemRL)
        if self.utility_reranker:
            try:
                query_category = self._classify_query_category(enhanced_query)
                sorted_results = self.utility_reranker.rerank(
                    sorted_results, query_category,
                )
            except Exception as exc:
                logger.error(f"[RETRIEVAL] Utility rerank failed: {exc}")

        # Source weight adjustment: boost conventions, downweight circulars
        sorted_results = self._apply_source_weights(sorted_results)

        # Graph expansion: follow cross-references from top results
        before_graph = len(sorted_results)
        sorted_results = self._graph_expand(sorted_results, effective_top_k)
        graph_added = len(sorted_results) - before_graph
        if graph_added > 0:
            logger.info(f"[RETRIEVAL] 图扩展新增 {graph_added} 条:")
            for r in sorted_results[before_graph:]:
                logger.info(
                    f"[RETRIEVAL]   Graph: "
                    f"title={r.get('metadata', {}).get('title', '?')[:80]}"
                )
        else:
            logger.info("[RETRIEVAL] 图扩展: 无新增")

        for result in sorted_results:
            result["fused_score"] = result["rrf_score"]
            result["graph_context"] = self._get_graph_context(result)

        return sorted_results

    def _graph_expand(
        self, results: list[dict], max_total: int,
    ) -> list[dict]:
        """Follow cross-references from top results to pull in related chunks."""
        if not results:
            return results

        # Collect doc_ids from initial results
        source_doc_ids = set()
        existing_cids = {r.get("chunk_id", "") for r in results}
        for r in results[:5]:
            doc_id = r.get("metadata", {}).get("doc_id", "")
            if doc_id:
                cleaned = doc_id.replace("bm25__", "").replace("graph__", "")
                if cleaned:
                    source_doc_ids.add(cleaned)

        if not source_doc_ids:
            return results

        # Look up cross-references for each source doc
        related_titles: dict[str, str] = {}
        for doc_id in source_doc_ids:
            try:
                xrefs = self.graph.get_cross_document_regulations(doc_id)
                for ref in xrefs.get("references", [])[:5]:
                    target_id = ref.get("target_doc_id", "")
                    title = ref.get("title", "")
                    if target_id and target_id not in source_doc_ids:
                        related_titles[target_id] = title
            except Exception:
                continue

        if not related_titles:
            return results

        logger.info(
            f"[GraphExpand] Found {len(related_titles)} related docs: "
            f"{list(related_titles.keys())[:5]}"
        )

        # Fetch related chunks via BM25 using regulation title
        added = 0
        for target_doc_id, title in list(related_titles.items())[:5]:
            if added >= 3:
                break
            try:
                extra = self.bm25.search(query=title[:80], top_k=1)
                for r in extra:
                    pseudo_cid = f"graph_expand__{r['doc_id']}"
                    if pseudo_cid not in existing_cids:
                        results.append({
                            "chunk_id": pseudo_cid,
                            "text": (r.get("body_text") or "")[:2000],
                            "score": r.get("score", 0),
                            "metadata": {
                                "doc_id": r["doc_id"],
                                "title": r.get("title", ""),
                                "breadcrumb": r.get("breadcrumb", ""),
                                "url": r.get("url", ""),
                            },
                            "sources": ["graph_expand"],
                            "rrf_score": 0.005,
                            "_graph_expanded": True,
                        })
                        existing_cids.add(pseudo_cid)
                        added += 1
            except Exception:
                continue

        return results[:max_total]

    @staticmethod
    def _determine_search_collections(enhanced_query: str) -> list[str]:
        """Determine which Qdrant collections to search based on query content.

        Always searches imo_regulations. Adds bv_rules and/or iacs_resolutions
        when query content indicates relevance. For generic technical queries,
        searches all collections.
        """
        collections = ["imo_regulations"]
        query_lower = enhanced_query.lower()

        bv_keywords = [
            "bv", "bureau veritas", "nr467", "nr216", "nr445", "nr483",
            "nr217", "nr526", "nr544", "nr580", "入级", "附加标志",
            "classification rule", "erules",
        ]
        iacs_keywords = [
            "iacs", "ur ", "ur-", "统一要求", "统一解释", "csr",
            "共同结构", "unified requirement", "unified interpretation",
        ]

        has_bv = any(kw in query_lower for kw in bv_keywords)
        has_iacs = any(kw in query_lower for kw in iacs_keywords)

        if has_bv:
            collections.append("bv_rules")
        if has_iacs:
            collections.append("iacs_resolutions")

        # Generic technical queries -> search all collections for broader coverage
        if not has_bv and not has_iacs:
            collections.extend(["bv_rules", "iacs_resolutions"])

        return collections

    @staticmethod
    def _classify_query_category(query: str) -> str:
        """Classify query into a regulatory domain for utility bucketing."""
        query_lower = query.lower()
        for category, keywords in _QUERY_CATEGORIES.items():
            if any(kw.lower() in query_lower for kw in keywords):
                return category
        return "general"

    @staticmethod
    def _apply_source_weights(results: list[dict]) -> list[dict]:
        """Apply source-type weight multipliers to reranked results.

        Boosts convention/code chunks and downweights circulars so that
        primary regulatory text outranks supplementary material.
        """
        if not results:
            return results

        for chunk in results:
            payload = chunk.get("metadata", {})
            collection = payload.get("collection", "")
            is_curated = payload.get("curated", False)

            # Determine source type from collection/breadcrumb
            if is_curated:
                weight = SOURCE_WEIGHT["curated"]
            elif "circular" in collection.lower():
                weight = SOURCE_WEIGHT["circular"]
            elif "resolution" in collection.lower():
                weight = SOURCE_WEIGHT["resolution"]
            elif collection in ("bv_rules",):
                weight = SOURCE_WEIGHT["bv_rules"]
            elif collection in ("iacs_resolutions",):
                weight = SOURCE_WEIGHT["iacs"]
            else:
                # Infer from breadcrumb for imo_regulations collection
                breadcrumb = payload.get("breadcrumb", "").lower()
                title = payload.get("title", "").lower()
                combined = f"{breadcrumb} {title}"

                if "circular" in combined or "circ." in combined:
                    weight = SOURCE_WEIGHT["circular"]
                elif "resolution" in combined:
                    weight = SOURCE_WEIGHT["resolution"]
                elif any(kw in combined for kw in [
                    "ibc code", "igc code", "fss code", "lsa code",
                    "ism code", "isps code",
                ]):
                    weight = SOURCE_WEIGHT["code"]
                elif any(kw in combined for kw in [
                    "solas", "marpol", "icll", "load line", "colreg", "stcw",
                ]):
                    weight = SOURCE_WEIGHT["convention"]
                else:
                    weight = SOURCE_WEIGHT["default"]

            original_score = chunk.get("rrf_score", 0)
            weighted_score = original_score * weight
            chunk["rrf_score"] = weighted_score

            if weight != 1.0:
                chunk_id = chunk.get("chunk_id", "?")
                logger.debug(
                    f"[SourceWeight] {chunk_id}: "
                    f"original={original_score:.4f} weight={weight:.2f} "
                    f"adjusted={weighted_score:.4f}"
                )

        results.sort(key=lambda x: x.get("rrf_score", 0), reverse=True)
        return results

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
