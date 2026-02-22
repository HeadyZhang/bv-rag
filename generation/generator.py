"""Claude LLM answer generation with smart model routing."""
import json
import logging
import re
import threading

import anthropic
import httpx
import tiktoken

from config.bv_rules_urls import generate_reference_url
from config.solas_regulation_mapping import annotate_obsolete_refs
from generation.extension_prompts import (
    COMPLETE_SYSTEM_PROMPT,
    EXPLAIN_SYSTEM_PROMPT,
    FILL_SYSTEM_PROMPT,
    PREDICT_SYSTEM_PROMPT,
)
from generation.prompts import LANGUAGE_INSTRUCTIONS, SYSTEM_PROMPT
from generation.table_post_check import post_check_table_lookup

logger = logging.getLogger(__name__)

# === Usage tracking (process-level, thread-safe) ===
_usage_lock = threading.Lock()
_usage_stats: dict = {
    "total_requests": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "by_model": {},
    "by_service": {},
}

MODEL_PRICES: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-haiku-4-5-20251001": {"input": 0.80 / 1_000_000, "output": 4.0 / 1_000_000},
}
_DEFAULT_PRICE: dict[str, float] = {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000}


def record_llm_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    session_id: str = "",
    query_preview: str = "",
) -> None:
    """Record a single LLM call's token usage."""
    with _usage_lock:
        _usage_stats["total_requests"] += 1
        _usage_stats["total_input_tokens"] += input_tokens
        _usage_stats["total_output_tokens"] += output_tokens

        if model not in _usage_stats["by_model"]:
            _usage_stats["by_model"][model] = {
                "requests": 0, "input_tokens": 0, "output_tokens": 0,
            }
        _usage_stats["by_model"][model]["requests"] += 1
        _usage_stats["by_model"][model]["input_tokens"] += input_tokens
        _usage_stats["by_model"][model]["output_tokens"] += output_tokens

    logger.info(
        f"[USAGE] model={model} "
        f"input_tokens={input_tokens} "
        f"output_tokens={output_tokens} "
        f"total_tokens={input_tokens + output_tokens} "
        f"session={session_id} "
        f"query={query_preview[:50]}"
    )


def record_service_call(service: str, extra: str = "") -> None:
    """Record an external service call (embedding, reranker, etc.)."""
    with _usage_lock:
        if service not in _usage_stats["by_service"]:
            _usage_stats["by_service"][service] = 0
        _usage_stats["by_service"][service] += 1

    logger.info(f"[USAGE] service={service} calls=1 {extra}".strip())


def get_usage_stats() -> dict:
    """Return cumulative usage statistics with cost estimation."""
    with _usage_lock:
        stats = {
            "total_requests": _usage_stats["total_requests"],
            "total_input_tokens": _usage_stats["total_input_tokens"],
            "total_output_tokens": _usage_stats["total_output_tokens"],
            "by_model": {k: dict(v) for k, v in _usage_stats["by_model"].items()},
            "by_service": dict(_usage_stats["by_service"]),
        }

    total_cost = 0.0
    for model, usage in stats["by_model"].items():
        prices = MODEL_PRICES.get(model, _DEFAULT_PRICE)
        total_cost += (
            usage["input_tokens"] * prices["input"]
            + usage["output_tokens"] * prices["output"]
        )
    stats["estimated_cost_usd"] = round(total_cost, 4)
    return stats

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

# Safety-critical answer patterns: catch dangerous LLM outputs
SAFETY_RULES = [
    {
        "id": "liferaft_davit",
        "trigger_query": re.compile(
            r"(free.?fall|自由抛落|自由降落).*(davit|降落|救生筏)", re.IGNORECASE,
        ),
        "dangerous_answer": re.compile(
            r"(都不需要|都无需|均不需要|不需要.{0,5}davit|无需.{0,10}davit"
            r"|两舷.{0,10}不需要|两舷.{0,10}无需|都可以.{0,5}throw)",
            re.IGNORECASE,
        ),
        "correction": (
            "⚠️ **安全修正**：即使配备了 free-fall lifeboat，根据 SOLAS III/31.1.2.2，"
            "≥85m 货船仍须在**至少一舷**配备 davit-launched 救生筏。"
            "Free-fall lifeboat 不免除 davit 要求。\n\n---\n\n"
        ),
        "action": "prepend",
    },
    {
        "id": "odme_no_limit",
        "trigger_query": re.compile(
            r"(ODME|排油|oil discharge|总排油量|排放.*油轮)", re.IGNORECASE,
        ),
        "dangerous_answer": re.compile(
            r"(没有.{0,10}(总量|排油量|排油).{0,10}(限制|限值|要求)"
            r"|无.{0,5}(总量|排油).{0,5}限"
            r"|不存在.{0,10}排油.{0,5}限)",
            re.IGNORECASE,
        ),
        "correction": (
            "\n\n⚠️ **重要补充**：MARPOL Annex I Regulation 34 明确规定了货舱区排油限制——"
            "每航次总排油量不得超过该批货油总量的 **1/30,000**（新船）或 1/15,000（旧船），"
            "且瞬时排放率 ≤30 升/海里。"
        ),
        "action": "append",
    },
]

RELATION_KEYWORDS = [
    "所有", "哪些", "all", "which", "compare", "区别", "关系", "relationship",
]


class AnswerGenerator:
    def __init__(self, anthropic_api_key: str, primary_model: str, fast_model: str):
        self.client = anthropic.Anthropic(
            api_key=anthropic_api_key,
            max_retries=3,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        self.primary_model = primary_model
        self.fast_model = fast_model
        logger.info("Anthropic client initialized: max_retries=3, timeout=120s")

    def generate(
        self,
        query: str,
        retrieved_chunks: list[dict],
        conversation_history: list[dict] | None = None,
        user_context: str | None = None,
        practical_context: str | None = None,
        query_classification: dict | None = None,
    ) -> dict:
        classification = query_classification or {}

        # Model selection: classifier hint > fallback routing
        if classification.get("model") == "primary":
            model = self.primary_model
        elif classification.get("model") == "fast":
            model = self.fast_model
        else:
            model = self._select_model(query, retrieved_chunks)

        is_fast = model == self.fast_model
        max_tokens = 1024 if is_fast else 2048
        max_context_tokens = 3000 if is_fast else 5000

        context_text = self._build_context(retrieved_chunks, max_context_tokens)

        system = SYSTEM_PROMPT

        # Dynamic language instruction based on detected language
        language = classification.get("language", "zh")
        system += LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS["zh"])

        if is_fast:
            system += (
                "\n\n重要：请简洁回答，直接给出关键数值和法规引用，"
                "控制在300字以内。不需要列出完整的适用性分析和替代方案。"
            )
        else:
            system += "\n\n请提供完整但不冗余的回答，控制在600字以内。"

        if user_context:
            system = f"{system}\n\n## 用户偏好\n{user_context}"

        # Applicability: inject extracted ship info
        ship_info = classification.get("ship_info", {})
        if classification.get("intent") == "applicability" and ship_info:
            extra = "\n\n## 用户船舶信息"
            if ship_info.get("type"):
                extra += f"\n- 船型: {ship_info['type']}"
            if ship_info.get("length"):
                extra += f"\n- 船长: {ship_info['length']}米"
            if ship_info.get("tonnage"):
                extra += f"\n- 总吨: {ship_info['tonnage']}GT"
            extra += "\n请根据这些参数给出明确的适用性判断。"
            system += extra

        messages = []
        if conversation_history:
            messages.extend(conversation_history[-6:])

        user_parts = [f"## 检索到的法规内容\n\n{context_text}"]
        if practical_context:
            user_parts.append(practical_context)
        user_parts.append(f"## 用户问题\n\n{query}")
        user_message = "\n\n".join(user_parts)
        messages.append({"role": "user", "content": user_message})

        # === Diagnostic logging: record full retrieval + context details ===
        logger.info("=" * 80)
        logger.info("[DIAG] ========== 查询诊断开始 ==========")
        logger.info(f"[DIAG] 用户查询: {query}")

        if classification:
            logger.info(f"[DIAG] 意图分类: {classification.get('intent', '?')}")
            logger.info(f"[DIAG] 船舶信息: {classification.get('ship_info', {})}")

        logger.info(f"[DIAG] 检索到 {len(retrieved_chunks)} 个 chunks:")
        for i, chunk in enumerate(retrieved_chunks):
            meta = chunk.get("metadata", {})
            score = chunk.get("score") or chunk.get("fused_score", 0)
            text_preview = chunk.get("text", "")[:200].replace("\n", " ")
            graph_flag = " [GRAPH-EXPANDED]" if chunk.get("_graph_expanded") else ""
            logger.info(f"[DIAG]   Chunk {i+1}{graph_flag}:")
            logger.info(f"[DIAG]     Score: {score:.4f}")
            logger.info(f"[DIAG]     Source: {meta.get('breadcrumb', 'N/A')}")
            logger.info(f"[DIAG]     RegNum: {meta.get('regulation_number', 'N/A')}")
            logger.info(f"[DIAG]     Title: {meta.get('title', 'N/A')}")
            logger.info(f"[DIAG]     Collection: {meta.get('collection', 'N/A')}")
            logger.info(f"[DIAG]     URL: {meta.get('url', 'N/A')}")
            logger.info(f"[DIAG]     Text: {text_preview}...")

        if practical_context:
            logger.info("[DIAG] 实务知识库匹配:")
            for line in practical_context[:500].split("\n"):
                if line.strip():
                    logger.info(f"[DIAG]   {line.strip()}")
        else:
            logger.info("[DIAG] 实务知识库: 无匹配")

        try:
            enc = tiktoken.encoding_for_model("gpt-4")
            token_count = len(enc.encode(user_message))
        except Exception:
            token_count = len(user_message) // 4

        logger.info(f"[DIAG] 发给LLM的上下文: {token_count} tokens ({len(user_message)} chars)")
        logger.info(f"[DIAG] 模型选择: {model}")

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            answer = response.content[0].text

            record_llm_usage(
                model=model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                query_preview=query,
            )
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            raise

        logger.info(f"[DIAG] LLM 回答前200字: {answer[:200].replace(chr(10), ' ')}")

        # Safety post-check: catch dangerous patterns in LLM output
        answer = self._safety_post_check(answer, query)

        # Table lookup post-check: catch table/ship-type mismatches and wrong values
        table_check = post_check_table_lookup(answer, query, retrieved_chunks)
        if table_check["should_regenerate"]:
            logger.warning(
                f"[TABLE_CHECK] Regenerating — "
                f"{len(table_check['warnings'])} error(s): "
                f"{table_check['correction_context'][:200]}"
            )
            corrected_user_message = (
                user_message
                + "\n\nIMPORTANT CORRECTIONS:\n"
                + table_check["correction_context"]
                + "\n\nPlease regenerate your answer with these corrections applied."
            )
            corrected_messages = messages[:-1] + [
                {"role": "user", "content": corrected_user_message}
            ]
            try:
                corrected_response = self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=corrected_messages,
                )
                answer = corrected_response.content[0].text
                record_llm_usage(
                    model=model,
                    input_tokens=corrected_response.usage.input_tokens,
                    output_tokens=corrected_response.usage.output_tokens,
                    query_preview=f"table_correction:{query[:30]}",
                )
                logger.info(
                    f"[TABLE_CHECK] Corrected answer: "
                    f"{answer[:200].replace(chr(10), ' ')}"
                )
            except Exception as exc:
                logger.error(f"[TABLE_CHECK] Regeneration failed: {exc}")

        logger.info("[DIAG] ========== 查询诊断结束 ==========")
        logger.info("=" * 80)

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

    @staticmethod
    def _safety_post_check(answer: str, query: str) -> str:
        """Post-check LLM output for safety-critical errors.

        If the query matches a safety rule's trigger and the answer contains
        a dangerous pattern, prepend or append a correction.
        """
        for rule in SAFETY_RULES:
            if not rule["trigger_query"].search(query):
                continue
            if rule["dangerous_answer"].search(answer):
                logger.warning(
                    f"[SAFETY] Rule '{rule['id']}' triggered — "
                    f"dangerous pattern found in LLM answer"
                )
                if rule["action"] == "prepend":
                    answer = rule["correction"] + answer
                elif rule["action"] == "append":
                    answer = answer + rule["correction"]
        return answer

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
            # Annotate chunks that reference obsolete SOLAS II-2 numbers
            text = annotate_obsolete_refs(text)
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
            url = meta.get("url", "")
            breadcrumb = meta.get("breadcrumb", "")

            # If no URL from crawled data, try to generate one from the reference
            if not url and breadcrumb:
                url = generate_reference_url(breadcrumb)

            sources.append({
                "chunk_id": cid,
                "url": url,
                "breadcrumb": breadcrumb,
                "score": chunk.get("score") or chunk.get("fused_score", 0),
            })
        return sources

    # ------------------------------------------------------------------
    # Extension endpoint methods (L1/L2/L3)
    # ------------------------------------------------------------------

    def generate_predict_suggestions(
        self,
        *,
        chunks: list[dict],
        ship_type: str = "",
        area: str = "",
        inspection_type: str = "",
        form_context: dict | None = None,
        existing_ids: list[str] | None = None,
    ) -> list[dict]:
        """Generate LLM-based defect predictions (L1 fallback).

        Returns a list of suggestion dicts with text_en, text_zh,
        regulation_ref, category, confidence.
        """
        context_text = self._build_context(chunks, max_context_tokens=2000)
        prompt = PREDICT_SYSTEM_PROMPT.format(
            ship_type=ship_type or "unknown",
            inspection_area=area or "general",
            inspection_type=inspection_type or "PSC",
            form_context=json.dumps(form_context or {}, ensure_ascii=False),
            context_chunks=context_text,
        )

        return self._call_llm_json_array(
            prompt=prompt,
            model=self.fast_model,
            max_tokens=800,
            query_preview=f"predict:{ship_type}/{area}",
        )

    def generate_completions(
        self,
        *,
        partial_input: str,
        chunks: list[dict],
        field_label: str = "",
        ship_type: str = "",
        area: str = "",
        form_context: dict | None = None,
    ) -> list[dict]:
        """Generate LLM-based autocomplete suggestions (L2 fallback).

        Returns a list of suggestion dicts.
        """
        context_text = self._build_context(chunks, max_context_tokens=2000)
        prompt = COMPLETE_SYSTEM_PROMPT.format(
            partial_input=partial_input,
            field_label=field_label or "Defect Description",
            ship_type=ship_type or "unknown",
            inspection_area=area or "general",
            form_context=json.dumps(form_context or {}, ensure_ascii=False),
            context_chunks=context_text,
        )

        return self._call_llm_json_array(
            prompt=prompt,
            model=self.fast_model,
            max_tokens=800,
            query_preview=f"complete:{partial_input[:30]}",
        )

    def generate_fill_text(
        self,
        *,
        user_input: str,
        target_lang: str,
        chunks: list[dict],
        field_label: str = "",
        form_context: dict | None = None,
    ) -> dict:
        """Generate standardized fill text from informal input (L3).

        Returns a dict with filled_text, regulation_ref, confidence.
        """
        context_text = self._build_context(chunks, max_context_tokens=3000)
        prompt = FILL_SYSTEM_PROMPT.format(
            selected_text=user_input,
            target_lang=target_lang,
            field_label=field_label or "Defect Description",
            form_context=json.dumps(form_context or {}, ensure_ascii=False),
            context_chunks=context_text,
        )

        try:
            response = self.client.messages.create(
                model=self.fast_model,
                max_tokens=512,
                system=prompt,
                messages=[{"role": "user", "content": user_input}],
            )
            filled_text = response.content[0].text.strip()
            record_llm_usage(
                model=self.fast_model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                query_preview=f"fill:{user_input[:30]}",
            )
        except Exception as exc:
            logger.error("[Extension] fill generation failed: %s", exc)
            raise

        # Extract regulation ref from the filled text
        ref_match = re.search(r"\(Ref:\s*([^)]+)\)", filled_text)
        regulation_ref = ref_match.group(1) if ref_match else ""

        return {
            "filled_text": filled_text,
            "regulation_ref": regulation_ref,
            "confidence": "high" if regulation_ref else "medium",
            "model_used": self.fast_model,
        }

    def generate_explanation(
        self,
        *,
        selected_text: str,
        chunks: list[dict],
        page_context: str = "",
    ) -> dict:
        """Generate chinese explanation of selected regulation text.

        Returns a dict with explanation, regulation_refs.
        """
        context_text = self._build_context(chunks, max_context_tokens=2000)
        prompt = EXPLAIN_SYSTEM_PROMPT.format(
            selected_text=selected_text,
            page_context=page_context or "N/A",
            context_chunks=context_text,
        )

        try:
            response = self.client.messages.create(
                model=self.fast_model,
                max_tokens=512,
                system=prompt,
                messages=[{"role": "user", "content": selected_text}],
            )
            explanation = response.content[0].text.strip()
            record_llm_usage(
                model=self.fast_model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                query_preview=f"explain:{selected_text[:30]}",
            )
        except Exception as exc:
            logger.error("[Extension] explain generation failed: %s", exc)
            raise

        return {
            "explanation": explanation,
            "model_used": self.fast_model,
        }

    def _call_llm_json_array(
        self,
        *,
        prompt: str,
        model: str,
        max_tokens: int,
        query_preview: str,
    ) -> list[dict]:
        """Call LLM expecting a JSON array response; parse with fallback."""
        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=prompt,
                messages=[{"role": "user", "content": "Generate suggestions."}],
            )
            raw = response.content[0].text.strip()
            record_llm_usage(
                model=model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                query_preview=query_preview,
            )
        except Exception as exc:
            logger.error("[Extension] LLM call failed: %s", exc)
            return []

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
            logger.warning("[Extension] LLM returned non-array JSON: %s", type(parsed))
            return []
        except json.JSONDecodeError as exc:
            logger.warning("[Extension] Failed to parse LLM JSON: %s | raw=%s", exc, raw[:200])
            return []
