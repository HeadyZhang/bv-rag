"""BV-RAG regression test suite.

Usage:
    python tests/regression_test.py [BASE_URL]

Default BASE_URL: https://bv-rag-production.up.railway.app
"""
import json
import sys
import time

import requests

BASE_URL = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "https://bv-rag-production.up.railway.app"
)

TEST_CASES = [
    {
        "id": "T001",
        "query": "SOLAS II-1/3-6的最小开口尺寸?",
        "expect_contains": ["600", "mm", "SOLAS II-1/3-6"],
        "expect_not_contains": ["无法回答", "无法直接"],
        "expect_model": "haiku",
        "max_time_ms": 15000,
    },
    {
        "id": "T002",
        "query": "我是一个100米长的国际航行船舶，请问两边的救生筏都需要起降落设备吗？",
        "expect_contains_any": [
            ["单边", "一舷", "throw-overboard", "抛投"],
        ],
        "expect_not_contains": ["无法回答", "无法直接"],
        "expect_model": "sonnet",
        "max_time_ms": 25000,
        "note": "Conclusion should be 'only one side needs davit'",
    },
    {
        "id": "T003_context",
        "setup_query": "What are the requirements of SOLAS Regulation II-1/3-6?",
        "query": "这个规定适用于FPSO吗？",
        "expect_contains": ["SOLAS II-1/3-6"],
        "expect_not_contains": ["没有明确指向", "不确定您指的"],
        "note": "Coreference resolution — must resolve '这个规定' to SOLAS II-1/3-6",
    },
    {
        "id": "T004",
        "query": "What is the minimum metacentric height (GM) for a cargo ship?",
        "expect_contains": ["0.15"],
        "expect_not_contains": ["无法回答"],
    },
    {
        "id": "T005",
        "query": "散货船货舱进入通道的要求是什么？",
        "expect_contains": ["access"],
        "expect_not_contains": ["无法回答"],
    },
    {
        "id": "T006",
        "query": "MARPOL Annex I对油水分离器的排放标准是多少？",
        "expect_contains": ["15", "ppm"],
        "expect_not_contains": ["无法回答"],
    },
    {
        "id": "T007",
        "query": "客船和货船的救生设备要求有什么区别？",
        "expect_contains": ["SOLAS III"],
        "expect_not_contains": ["无法回答"],
        "expect_model": "sonnet",
        "note": "Comparison query must use Sonnet",
    },
    {
        "id": "T008",
        "query": "防火门A-60和A-0的区别是什么？",
        "expect_contains": ["60"],
        "expect_not_contains": ["无法回答"],
    },
]


def _send_query(text: str, session_id: str = "") -> dict:
    resp = requests.post(
        f"{BASE_URL}/api/v1/voice/text-query",
        data={
            "text": text,
            "generate_audio": "false",
            "session_id": session_id,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def run_test(tc: dict) -> dict:
    result = {"id": tc["id"], "passed": True, "errors": []}
    session_id = ""

    # Setup query (for coreference tests)
    if tc.get("setup_query"):
        data = _send_query(tc["setup_query"])
        session_id = data.get("session_id", "")
        time.sleep(1)

    start = time.time()
    try:
        data = _send_query(tc["query"], session_id)
    except Exception as exc:
        result["passed"] = False
        result["errors"].append(f"REQUEST FAILED: {exc}")
        result["answer_preview"] = ""
        result["model"] = "?"
        result["elapsed_ms"] = int((time.time() - start) * 1000)
        return result

    elapsed_ms = int((time.time() - start) * 1000)
    answer = data.get("answer_text", "")
    model = data.get("model_used", "")
    answer_lower = answer.lower()

    # Check: expected keywords present
    for kw in tc.get("expect_contains", []):
        if kw.lower() not in answer_lower:
            result["errors"].append(f"MISSING: '{kw}' not found in answer")
            result["passed"] = False

    # Check: at least one keyword from any group present
    for group in tc.get("expect_contains_any", []):
        if not any(kw.lower() in answer_lower for kw in group):
            result["errors"].append(
                f"MISSING_ANY: none of {group} found in answer"
            )
            result["passed"] = False

    # Check: unwanted keywords absent
    for kw in tc.get("expect_not_contains", []):
        if kw.lower() in answer_lower:
            result["errors"].append(f"UNWANTED: '{kw}' found in answer")
            result["passed"] = False

    # Check: model
    if tc.get("expect_model") and tc["expect_model"] not in model.lower():
        result["errors"].append(
            f"WRONG MODEL: expected {tc['expect_model']}, got {model}"
        )
        result["passed"] = False

    # Check: response time
    if tc.get("max_time_ms") and elapsed_ms > tc["max_time_ms"]:
        result["errors"].append(
            f"SLOW: {elapsed_ms}ms > {tc['max_time_ms']}ms limit"
        )
        result["passed"] = False

    result["answer_preview"] = answer[:200]
    result["model"] = model
    result["elapsed_ms"] = elapsed_ms
    return result


def main() -> None:
    print(f"Running {len(TEST_CASES)} regression tests against {BASE_URL}\n")

    passed = 0
    failed = 0

    for tc in TEST_CASES:
        r = run_test(tc)
        status = "PASS" if r["passed"] else "FAIL"
        print(f"[{status}] {r['id']} ({r.get('elapsed_ms', '?')}ms, {r.get('model', '?')})")

        if not r["passed"]:
            for err in r["errors"]:
                print(f"    -> {err}")
            failed += 1
        else:
            passed += 1

        if r.get("answer_preview"):
            print(f"    Answer: {r['answer_preview']}...")
        if tc.get("note"):
            print(f"    Note: {tc['note']}")
        print()

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed, {len(TEST_CASES)} total")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
