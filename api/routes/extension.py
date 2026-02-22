"""Chrome extension API routes — /api/v1/extension/*.

Dual semaphore isolation:
- KB_ONLY_SEMAPHORE (10): JSON lookups, <50ms, never blocked by LLM
- LLM_SEMAPHORE (3): Anthropic API calls, 1-5s, shared with chatbot
"""
import asyncio
import logging
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/extension", tags=["extension"])

# ── Dual semaphores ──
KB_ONLY_SEMAPHORE = asyncio.Semaphore(10)
LLM_SEMAPHORE = asyncio.Semaphore(3)


# ── Request/Response models ──

class PredictRequest(BaseModel):
    ship_type: str = ""
    inspection_area: str = ""
    inspection_type: str = ""
    ship_name: str = ""
    form_context: dict = Field(default_factory=dict)


class Suggestion(BaseModel):
    id: str = ""
    text_en: str
    text_zh: str = ""
    regulation_ref: str = ""
    category: str = ""
    confidence: float = 0.0
    detention_risk: str = ""
    frequency_rank: int = 999


class PredictResponse(BaseModel):
    suggestions: list[Suggestion]
    source: str = "knowledge_base"
    response_time_ms: int = 0


class CompleteRequest(BaseModel):
    partial_input: str
    field_label: str = ""
    ship_type: str = ""
    inspection_area: str = ""
    form_context: dict = Field(default_factory=dict)


class CompleteResponse(BaseModel):
    suggestions: list[Suggestion]
    source: str = "knowledge_base"
    response_time_ms: int = 0


class FillRequest(BaseModel):
    selected_text: str
    target_lang: str = "en"
    field_label: str = ""
    form_context: dict = Field(default_factory=dict)


class FillResponse(BaseModel):
    filled_text: str
    regulation_ref: str = ""
    confidence: str = "medium"
    model_used: str = ""


class ExplainRequest(BaseModel):
    selected_text: str
    page_context: str = ""


class ExplainResponse(BaseModel):
    explanation: str
    model_used: str = ""


class ChatRequest(BaseModel):
    text: str
    session_id: str | None = None


class FeedbackRequest(BaseModel):
    original_input: str
    generated_text: str
    is_accurate: bool
    corrected_text: str = ""
    field_label: str = ""
    form_context: dict = Field(default_factory=dict)
    defect_id: str = ""


# ── Helpers ──

def _kb_suggestion_to_model(item: dict) -> Suggestion:
    """Convert a DefectKnowledgeBase result dict to a Suggestion model."""
    refs = item.get("regulation_refs", [])
    ref_str = ""
    if refs:
        first = refs[0]
        ref_str = f"{first.get('convention', '')} {first.get('ref', '')}".strip()

    return Suggestion(
        id=item.get("id", ""),
        text_en=item.get("standard_text_en", ""),
        text_zh=item.get("standard_text_zh", ""),
        regulation_ref=ref_str,
        category=item.get("category", ""),
        confidence=0.8,
        detention_risk=item.get("detention_risk", ""),
        frequency_rank=item.get("frequency_rank", 999),
    )


def _llm_suggestion_to_model(item: dict) -> Suggestion:
    """Convert an LLM-generated suggestion dict to a Suggestion model."""
    return Suggestion(
        text_en=item.get("text_en", ""),
        text_zh=item.get("text_zh", ""),
        regulation_ref=item.get("regulation_ref", ""),
        category=item.get("category", ""),
        confidence=item.get("confidence", 0.5),
    )


# ── Endpoints ──

@router.get("/kb-version")
async def kb_version(request: Request):
    """Return current defect knowledge base version (no semaphore needed)."""
    kb = request.app.state.defect_kb
    return kb.get_version()


@router.get("/kb-update")
async def kb_update(request: Request, since_version: str = ""):
    """Return defects added/modified since a given version."""
    async with KB_ONLY_SEMAPHORE:
        kb = request.app.state.defect_kb
        updates = kb.get_updates_since(since_version)
    return {"updates": updates, "current_version": kb.get_version()["version"]}


@router.post("/predict", response_model=PredictResponse)
async def predict_defects(request: Request, body: PredictRequest):
    """L1 prediction: context-aware defect suggestions.

    Fast path: KB lookup (<50ms, KB_ONLY_SEMAPHORE).
    Slow fallback: LLM generation (<1.5s, LLM_SEMAPHORE) when KB results < 3.
    """
    start = time.time()
    kb = request.app.state.defect_kb

    # 1. Fast KB lookup
    async with KB_ONLY_SEMAPHORE:
        candidates = kb.query(
            ship_type=body.ship_type,
            area=body.inspection_area,
            inspection_type=body.inspection_type,
            top_k=8,
        )

    suggestions = [_kb_suggestion_to_model(c) for c in candidates]
    source = "knowledge_base"

    # 2. LLM fallback if KB results insufficient
    if len(suggestions) < 3 and body.inspection_area:
        try:
            async with LLM_SEMAPHORE:
                rag_query = (
                    f"Common defects in {body.inspection_area} "
                    f"of {body.ship_type} during {body.inspection_type} inspection"
                )
                retriever = request.app.state.retriever
                chunks = retriever.retrieve(query=rag_query, top_k=5)

                generator = request.app.state.generator
                extra = generator.generate_predict_suggestions(
                    chunks=chunks,
                    ship_type=body.ship_type,
                    area=body.inspection_area,
                    inspection_type=body.inspection_type,
                    form_context=body.form_context,
                )
                suggestions.extend(_llm_suggestion_to_model(e) for e in extra)
                source = "mixed"
        except Exception as exc:
            logger.warning("[Extension] predict LLM fallback failed: %s", exc)

    elapsed = int((time.time() - start) * 1000)
    return PredictResponse(
        suggestions=suggestions[:8],
        source=source,
        response_time_ms=elapsed,
    )


@router.post("/complete", response_model=CompleteResponse)
async def complete_defect(request: Request, body: CompleteRequest):
    """L2 autocomplete: keyword search + LLM fallback.

    Fast path: KB keyword search (<50ms).
    Slow fallback: LLM generation when local matches < 3.
    """
    start = time.time()
    kb = request.app.state.defect_kb

    # 1. Local keyword search
    async with KB_ONLY_SEMAPHORE:
        local_matches = kb.search_by_keyword(body.partial_input, top_k=5)

    suggestions = [_kb_suggestion_to_model(m) for m in local_matches]
    source = "knowledge_base"

    # 2. LLM fallback if local matches insufficient
    if len(suggestions) < 3:
        try:
            async with LLM_SEMAPHORE:
                retriever = request.app.state.retriever
                chunks = retriever.retrieve(query=body.partial_input, top_k=5)

                generator = request.app.state.generator
                completions = generator.generate_completions(
                    partial_input=body.partial_input,
                    chunks=chunks,
                    field_label=body.field_label,
                    ship_type=body.ship_type,
                    area=body.inspection_area,
                    form_context=body.form_context,
                )
                suggestions.extend(_llm_suggestion_to_model(c) for c in completions)
                source = "mixed"
        except Exception as exc:
            logger.warning("[Extension] complete LLM fallback failed: %s", exc)

    # Deduplicate by text_en prefix
    seen: set[str] = set()
    unique: list[Suggestion] = []
    for s in suggestions:
        key = s.text_en[:50]
        if key not in seen:
            seen.add(key)
            unique.append(s)

    elapsed = int((time.time() - start) * 1000)
    return CompleteResponse(
        suggestions=unique[:5],
        source=source,
        response_time_ms=elapsed,
    )


@router.post("/fill", response_model=FillResponse)
async def fill_text(request: Request, body: FillRequest):
    """L3 standardization: convert informal text to professional defect description.

    Always uses LLM (via LLM_SEMAPHORE). Tries KB exact match first for speed.
    """
    kb = request.app.state.defect_kb

    # Quick KB keyword check — if input matches a known defect exactly
    local = kb.search_by_keyword(body.selected_text, top_k=1)
    if local:
        best = local[0]
        refs = best.get("regulation_refs", [])
        ref_str = ""
        if refs:
            ref_str = f"{refs[0].get('convention', '')} {refs[0].get('ref', '')}".strip()
        text_key = "standard_text_en" if body.target_lang == "en" else "standard_text_zh"
        filled = best.get(text_key, best.get("standard_text_en", ""))
        if ref_str:
            filled = f"{filled} (Ref: {ref_str})"
        return FillResponse(
            filled_text=filled,
            regulation_ref=ref_str,
            confidence="high",
            model_used="knowledge_base",
        )

    # LLM path
    async with LLM_SEMAPHORE:
        retriever = request.app.state.retriever
        chunks = retriever.retrieve(query=body.selected_text, top_k=5)

        generator = request.app.state.generator
        result = generator.generate_fill_text(
            user_input=body.selected_text,
            target_lang=body.target_lang,
            chunks=chunks,
            field_label=body.field_label,
            form_context=body.form_context,
        )

    return FillResponse(**result)


@router.post("/explain", response_model=ExplainResponse)
async def explain_text(request: Request, body: ExplainRequest):
    """Explain selected regulation text in Chinese."""
    async with LLM_SEMAPHORE:
        retriever = request.app.state.retriever
        chunks = retriever.retrieve(query=body.selected_text, top_k=5)

        generator = request.app.state.generator
        result = generator.generate_explanation(
            selected_text=body.selected_text,
            chunks=chunks,
            page_context=body.page_context,
        )

    return ExplainResponse(**result)


@router.post("/chat")
async def chat(request: Request, body: ChatRequest):
    """Sidebar chatbot — proxies to existing pipeline."""
    async with LLM_SEMAPHORE:
        pipeline = request.app.state.pipeline
        result = await pipeline.process_text_query(
            text=body.text,
            session_id=body.session_id,
            generate_audio=False,
        )
    return result


@router.post("/feedback")
async def submit_feedback(request: Request, body: FeedbackRequest):
    """Collect user feedback on generated suggestions (KB_ONLY path)."""
    async with KB_ONLY_SEMAPHORE:
        logger.info(
            "[Extension] Feedback: accurate=%s defect_id=%s input=%s",
            body.is_accurate,
            body.defect_id,
            body.original_input[:50],
        )
        # For now, log feedback. DB persistence will be added when
        # extension_feedback table is created.
    return {"status": "ok"}
