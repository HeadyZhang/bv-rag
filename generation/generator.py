"""Claude LLM answer generation."""
import logging
import re
from collections import defaultdict

import anthropic

from generation.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

CITATION_PATTERN = re.compile(
    r"\[(SOLAS|MARPOL|MSC|MEPC|ISM|ISPS|Resolution|LSA|FSS|FTP|STCW|COLREG)[^\]]*\]"
)


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
        context_text = self._build_context(retrieved_chunks)
        system = SYSTEM_PROMPT
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
                max_tokens=4096,
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
        has_exact_ref = bool(re.search(
            r"(SOLAS|MARPOL|STCW|ISM|ISPS)\s*(regulation|chapter|annex|rule)",
            query,
            re.IGNORECASE,
        ))
        top_score = max(
            (c.get("score") or c.get("fused_score", 0) for c in chunks),
            default=0,
        )
        if has_exact_ref and top_score > 0.8:
            return self.fast_model
        return self.primary_model

    def _build_context(self, chunks: list[dict]) -> str:
        by_document = defaultdict(list)
        for chunk in chunks:
            doc = chunk.get("metadata", {}).get("document", "Other")
            by_document[doc].append(chunk)

        sections = []
        for doc, doc_chunks in by_document.items():
            section_parts = [f"### {doc}\n"]
            for chunk in doc_chunks:
                meta = chunk.get("metadata", {})
                breadcrumb = meta.get("breadcrumb", "")
                url = meta.get("url", "")
                text = chunk.get("text", "")
                section_parts.append(
                    f"**[{breadcrumb}]** (Source: {url})\n{text}\n"
                )

                graph_ctx = chunk.get("graph_context", {})
                if graph_ctx.get("has_interpretations"):
                    count = graph_ctx.get("interpretation_count", 0)
                    section_parts.append(
                        f"*Note: {count} unified interpretation(s) available for this regulation.*\n"
                    )
            sections.append("\n".join(section_parts))

        return "\n---\n".join(sections)

    def _extract_citations(self, answer: str) -> list[dict]:
        matches = CITATION_PATTERN.findall(answer)
        full_matches = CITATION_PATTERN.finditer(answer)
        citations = []
        seen = set()
        for match in full_matches:
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
