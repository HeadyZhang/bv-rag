"""Claude LLM answer generation with smart model routing."""
import logging
import re
from collections import defaultdict

import anthropic

from generation.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

CITATION_PATTERN = re.compile(
    r"\[(SOLAS|MARPOL|MSC|MEPC|ISM|ISPS|Resolution|LSA|FSS|FTP|STCW|COLREG)[^\]]*\]"
)

REG_PATTERN = re.compile(
    r"(SOLAS|MARPOL|STCW|COLREG|ISM|ISPS|LSA|FSS|IBC|IGC)\s*[\w\-\/\.]+",
    re.IGNORECASE,
)

COMPLEX_KEYWORDS = [
    "compare", "比较", "区别", "difference", "vs",
    "所有相关", "修改", "amend", "解释", "interpret",
    "适用", "apply", "applicable", "豁免", "exempt",
]

RELATION_KEYWORDS = [
    "所有", "哪些", "all", "which", "compare", "区别", "关系", "relationship",
]


class AnswerGenerator:
    def __init__(self, anthropic_api_key: str, primary_model: str, fast_model: str):
        self.client = anthropic.Anthropic(api_key=anthropic_api_key)
        self.primary_model = primary_model
        self.fast_model = fast_model

    def generate(
        self,
        query: str,
        retrieved_chunks: list[dict],
        conversation_history: list[dict] | None = None,
        user_context: str | None = None,
    ) -> dict:
        model = self._select_model(query, retrieved_chunks)
        is_fast = model == self.fast_model
        max_tokens = 1024 if is_fast else 2048
        max_context_tokens = 3000 if is_fast else 5000

        context_text = self._build_context(retrieved_chunks, max_context_tokens)

        system = SYSTEM_PROMPT
        if is_fast:
            system += (
                "\n\n重要：请简洁回答，直接给出关键数值和法规引用，"
                "控制在300字以内。不需要列出完整的适用性分析和替代方案。"
            )
        else:
            system += "\n\n请提供完整但不冗余的回答，控制在600字以内。"

        if user_context:
            system = f"{system}\n\n## 用户偏好\n{user_context}"

        messages = []
        if conversation_history:
            messages.extend(conversation_history[-6:])

        user_message = f"## 检索到的法规内容\n\n{context_text}\n\n## 用户问题\n\n{query}"
        messages.append({"role": "user", "content": user_message})

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            answer = response.content[0].text
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            raise

        citations = self._extract_citations(answer)
        confidence = self._assess_confidence(retrieved_chunks)
        sources = self._build_sources(retrieved_chunks)

        return {
            "answer": answer,
            "citations": citations,
            "confidence": confidence,
            "model_used": model,
            "sources": sources,
        }

    def _select_model(self, query: str, chunks: list[dict]) -> str:
        """Smart model routing: Haiku for simple, Sonnet for complex."""
        use_fast = False

        # Haiku conditions (any one triggers fast)
        if REG_PATTERN.search(query):
            use_fast = True

        top_score = max(
            (c.get("score") or c.get("fused_score", 0) for c in chunks),
            default=0,
        )
        if chunks and top_score > 0.75:
            use_fast = True

        word_count = len(query.split())
        if word_count < 15 and not any(kw in query.lower() for kw in RELATION_KEYWORDS):
            use_fast = True

        # --- Sonnet overrides (complex queries force Sonnet) ---
        query_lower = query.lower()

        if any(kw in query_lower for kw in COMPLEX_KEYWORDS):
            use_fast = False

        # Ship parameters or ship type → applicability analysis needs Sonnet
        has_ship_params = bool(re.search(
            r"\d+\s*(米|m|吨|GT|DWT|总吨|载重)", query, re.IGNORECASE,
        ))
        has_ship_type = any(kw in query_lower for kw in [
            "货船", "客船", "油轮", "散货", "集装箱", "滚装", "国际航行",
            "cargo ship", "passenger", "tanker", "bulk carrier",
        ])
        if has_ship_params or has_ship_type:
            use_fast = False

        # Yes/no applicability questions need reasoning
        if any(kw in query for kw in [
            "是否", "需不需要", "是否需要", "必须", "要不要",
            "do I need", "is it required", "must",
        ]):
            use_fast = False

        # Long queries (>60 chars for Chinese) are usually complex scenarios
        if len(query) > 60:
            use_fast = False

        model = self.fast_model if use_fast else self.primary_model
        logger.info(f"[ModelRouter] use_fast={use_fast}, model={model}, len={len(query)}")
        return model

    def _build_context(self, chunks: list[dict], max_context_tokens: int = 5000) -> str:
        """Build context with per-chunk and total token limits."""
        context_parts = []
        total_tokens = 0

        for chunk in chunks:
            text = chunk.get("text", "")
            if len(text) > 1600:
                text = text[:1600] + "..."
            chunk_tokens = len(text) // 4
            if total_tokens + chunk_tokens > max_context_tokens:
                break

            meta = chunk.get("metadata", {})
            breadcrumb = meta.get("breadcrumb", "")
            url = meta.get("url", "")
            context_parts.append(f"**[{breadcrumb}]** (Source: {url})\n{text}")
            total_tokens += chunk_tokens

            graph_ctx = chunk.get("graph_context", {})
            if graph_ctx.get("has_interpretations"):
                count = graph_ctx.get("interpretation_count", 0)
                context_parts.append(
                    f"*Note: {count} unified interpretation(s) available for this regulation.*"
                )

        return "\n\n---\n\n".join(context_parts)

    def _extract_citations(self, answer: str) -> list[dict]:
        citations = []
        seen = set()
        for match in CITATION_PATTERN.finditer(answer):
            citation = match.group(0)
            if citation not in seen:
                seen.add(citation)
                citations.append({"citation": citation, "verified": True})
        return citations

    def _assess_confidence(self, chunks: list[dict]) -> str:
        if not chunks:
            return "low"
        top_score = max(
            (c.get("score") or c.get("fused_score", 0) for c in chunks),
            default=0,
        )
        if top_score > 0.85:
            return "high"
        if top_score > 0.6:
            return "medium"
        return "low"

    def _build_sources(self, chunks: list[dict]) -> list[dict]:
        sources = []
        seen = set()
        for chunk in chunks:
            cid = chunk.get("chunk_id", "")
            if cid in seen:
                continue
            seen.add(cid)
            meta = chunk.get("metadata", {})
            sources.append({
                "chunk_id": cid,
                "url": meta.get("url", ""),
                "breadcrumb": meta.get("breadcrumb", ""),
                "score": chunk.get("score") or chunk.get("fused_score", 0),
            })
        return sources
