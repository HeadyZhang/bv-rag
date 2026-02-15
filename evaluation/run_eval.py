"""Evaluation script for BV-RAG system."""
import asyncio
import json
import os
import sys
import time
from collections import defaultdict

from rich.console import Console
from rich.table import Table

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

console = Console()


def build_pipeline() -> VoiceQAPipeline:
    stt = STTService(settings.openai_api_key, settings.stt_model)
    tts = TTSService(settings.openai_api_key, settings.tts_model, settings.tts_voice)
    memory = ConversationMemory(
        settings.redis_url, settings.anthropic_api_key,
        settings.max_conversation_turns, settings.session_ttl_hours,
    )
    vector_store = VectorStore(
        settings.qdrant_url, settings.qdrant_api_key, settings.openai_api_key,
    )
    bm25 = BM25Search(settings.database_url)
    graph = GraphQueries(settings.database_url)
    retriever = HybridRetriever(vector_store, bm25, graph)
    generator = AnswerGenerator(
        settings.anthropic_api_key, settings.llm_model_primary, settings.llm_model_fast,
    )
    return VoiceQAPipeline(stt, tts, memory, retriever, generator)


async def run_single_test(pipeline, test_case: dict) -> dict:
    query = test_case.get("query", "")
    query_sequence = test_case.get("query_sequence")
    session_id = None

    results = []
    if query_sequence:
        for q in query_sequence:
            start = time.time()
            result = await pipeline.process_text_query(
                text=q, session_id=session_id, generate_audio=False,
            )
            elapsed = time.time() - start
            session_id = result["session_id"]
            results.append({**result, "query": q, "elapsed": elapsed})
        final = results[-1]
    else:
        start = time.time()
        result = await pipeline.process_text_query(
            text=query, session_id=session_id, generate_audio=False,
        )
        elapsed = time.time() - start
        final = {**result, "query": query, "elapsed": elapsed}

    passed = True
    failures = []

    expected_doc = test_case.get("expected_document")
    if expected_doc:
        sources = final.get("sources", [])
        found_doc = any(
            expected_doc.lower() in (s.get("breadcrumb", "") + s.get("url", "")).lower()
            for s in sources
        )
        if not found_doc:
            passed = False
            failures.append(f"Expected document '{expected_doc}' not in sources")

    expected_contains = test_case.get("expected_answer_contains")
    if expected_contains:
        if expected_contains.lower() not in final.get("answer_text", "").lower():
            passed = False
            failures.append(f"Answer does not contain '{expected_contains}'")

    if not final.get("citations"):
        passed = False
        failures.append("No citations")

    if final.get("elapsed", 0) > 15:
        failures.append(f"Slow: {final['elapsed']:.1f}s")

    return {
        "id": test_case["id"],
        "category": test_case["category"],
        "difficulty": test_case.get("difficulty", "unknown"),
        "passed": passed,
        "failures": failures,
        "confidence": final.get("confidence", "unknown"),
        "model_used": final.get("model_used", ""),
        "elapsed": final.get("elapsed", 0),
        "num_citations": len(final.get("citations", [])),
        "num_sources": len(final.get("sources", [])),
        "answer_preview": final.get("answer_text", "")[:200],
    }


async def main():
    test_file = os.path.join(os.path.dirname(__file__), "test_queries.json")
    with open(test_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    test_cases = data["test_cases"]
    console.print(f"\n[bold blue]BV-RAG Evaluation: {len(test_cases)} test cases[/bold blue]\n")

    pipeline = build_pipeline()
    results = []

    for tc in test_cases:
        console.print(f"  Running: {tc['id']} - {tc.get('query', tc.get('query_sequence', [''])[0])[:60]}...")
        try:
            result = await run_single_test(pipeline, tc)
            results.append(result)
            status = "[green]PASS[/green]" if result["passed"] else "[red]FAIL[/red]"
            console.print(f"    {status} ({result['elapsed']:.1f}s, {result['confidence']})")
            if result["failures"]:
                for f in result["failures"]:
                    console.print(f"      - {f}")
        except Exception as e:
            console.print(f"    [red]ERROR: {e}[/red]")
            results.append({
                "id": tc["id"], "category": tc["category"],
                "difficulty": tc.get("difficulty"), "passed": False,
                "failures": [str(e)], "elapsed": 0,
            })

    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    console.print(f"\n[bold]Overall: {passed}/{total} passed ({passed*100//total}%)[/bold]\n")

    by_category = defaultdict(list)
    for r in results:
        by_category[r["category"]].append(r)

    table = Table(title="Results by Category")
    table.add_column("Category", style="cyan")
    table.add_column("Passed", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Rate", justify="right")
    table.add_column("Avg Time", justify="right")

    for cat, cat_results in sorted(by_category.items()):
        cat_passed = sum(1 for r in cat_results if r.get("passed"))
        cat_total = len(cat_results)
        avg_time = sum(r.get("elapsed", 0) for r in cat_results) / cat_total
        rate = f"{cat_passed*100//cat_total}%"
        table.add_row(cat, str(cat_passed), str(cat_total), rate, f"{avg_time:.1f}s")
    console.print(table)

    times = [r.get("elapsed", 0) for r in results if r.get("elapsed")]
    if times:
        console.print(f"\n  Avg latency: {sum(times)/len(times):.1f}s")
        console.print(f"  Min: {min(times):.1f}s, Max: {max(times):.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
