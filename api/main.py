import logging
import os
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config.settings import settings
from db.bm25_search import BM25Search
from db.graph_queries import GraphQueries
from generation.generator import AnswerGenerator
from memory.conversation_memory import ConversationMemory
from pipeline.voice_qa_pipeline import VoiceQAPipeline
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.vector_store import VectorStore
from voice.stt_service import STTService
from voice.tts_service import TTSService

logger = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, settings.log_level))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("BV-RAG starting up...")

    app.state.stt = STTService(settings.openai_api_key, settings.stt_model)
    app.state.tts = TTSService(settings.openai_api_key, settings.tts_model, settings.tts_voice)
    app.state.memory = ConversationMemory(
        settings.redis_url, settings.anthropic_api_key,
        settings.max_conversation_turns, settings.session_ttl_hours,
    )
    app.state.vector_store = VectorStore(
        settings.qdrant_url, settings.qdrant_api_key, settings.openai_api_key,
    )
    app.state.bm25 = BM25Search(settings.database_url)
    app.state.graph = GraphQueries(settings.database_url)
    # Initialize rerankers (optional, graceful degradation)
    cohere_reranker = None
    if settings.reranker_enabled and settings.cohere_api_key:
        try:
            from retrieval.reranker import CohereReranker
            cohere_reranker = CohereReranker(settings.cohere_api_key, settings.reranker_model)
            logger.info("Cohere reranker initialized")
        except Exception as exc:
            logger.warning(f"Cohere reranker unavailable: {exc}")

    utility_reranker = None
    if settings.utility_reranker_enabled:
        try:
            from retrieval.utility_reranker import UtilityReranker
            utility_reranker = UtilityReranker(
                database_url=settings.database_url,
                alpha=settings.utility_reranker_alpha,
            )
            logger.info("Utility reranker initialized (alpha=%.2f)", settings.utility_reranker_alpha)
        except Exception as exc:
            logger.warning(f"Utility reranker unavailable: {exc}")

    app.state.utility_reranker = utility_reranker
    app.state.retriever = HybridRetriever(
        app.state.vector_store, app.state.bm25, app.state.graph,
        cohere_reranker=cohere_reranker,
        utility_reranker=utility_reranker,
    )
    app.state.generator = AnswerGenerator(
        settings.anthropic_api_key, settings.llm_model_primary, settings.llm_model_fast,
    )
    app.state.pipeline = VoiceQAPipeline(
        app.state.stt, app.state.tts, app.state.memory,
        app.state.retriever, app.state.generator,
    )

    logger.info(
        "All services initialized | cohere_reranker=%s | utility_reranker=%s",
        "active" if cohere_reranker else "disabled",
        "active" if utility_reranker else "disabled",
    )
    yield

    logger.info("BV-RAG shutting down...")
    app.state.bm25.close()
    app.state.graph.close()
    if utility_reranker:
        utility_reranker.close()


app = FastAPI(title="BV-RAG Maritime Regulations", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "bv-rag"}


@app.get("/api/v1/status")
async def system_status():
    from api.routes.voice import MAX_CONCURRENT_REQUESTS, _active_requests, _start_time
    from generation.generator import get_usage_stats

    return {
        "current_requests": _active_requests,
        "max_concurrent": MAX_CONCURRENT_REQUESTS,
        "uptime_seconds": round(time.time() - _start_time),
        "usage": get_usage_stats(),
        "status": "healthy",
    }


# Register API routes
from api.routes.voice import router as voice_router
from api.routes.search import router as search_router
from api.routes.admin import router as admin_router

app.include_router(voice_router)
app.include_router(search_router)
app.include_router(admin_router)

# Serve frontend (must be after API routes)
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
