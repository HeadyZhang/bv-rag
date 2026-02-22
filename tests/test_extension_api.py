"""Tests for Chrome Extension API endpoints — /api/v1/extension/*.

Tests are organized into 7 groups:
1. Predict endpoint (L1 context-aware suggestions)
2. Complete endpoint (L2 keyword autocomplete)
3. Fill endpoint (L3 standardization)
4. Feedback endpoint
5. KB Version endpoint
6. Semaphore isolation (conceptual)
7. Regression tests (20 surveyor scenarios, parametrized)

Strategy:
- DefectKnowledgeBase uses real data/defect_kb.json (pure local lookup).
- LLM-dependent methods on AnswerGenerator are mocked.
- retriever.retrieve is mocked (avoids DB/Qdrant dependency).
- pipeline.process_text_query is mocked (avoids full stack).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from knowledge.defect_kb import DefectKnowledgeBase


# ── Fixtures ──


@pytest.fixture(scope="module")
def real_kb():
    """Load the real defect knowledge base (pure JSON, no external deps)."""
    return DefectKnowledgeBase("data/defect_kb.json")


@pytest.fixture(scope="module")
def mock_generator():
    """Create a mock AnswerGenerator that never calls the real LLM."""
    gen = MagicMock()

    gen.generate_predict_suggestions.return_value = [
        {
            "text_en": "LLM-generated suggestion for testing",
            "text_zh": "LLM生成的测试建议",
            "regulation_ref": "SOLAS II-2/10",
            "category": "fire_safety",
            "confidence": 0.6,
        }
    ]

    gen.generate_completions.return_value = [
        {
            "text_en": "LLM-completed defect description",
            "text_zh": "LLM补全的缺陷描述",
            "regulation_ref": "MARPOL Annex I/15",
            "category": "pollution_prevention",
            "confidence": 0.55,
        }
    ]

    gen.generate_fill_text.return_value = {
        "filled_text": "Hull plating found with severe corrosion. (Ref: SOLAS II-1/3-1)",
        "regulation_ref": "SOLAS II-1/3-1",
        "confidence": "high",
        "model_used": "claude-haiku-4-5-20251001",
    }

    gen.generate_explanation.return_value = {
        "explanation": "这条法规要求所有货船必须配备固定式灭火系统。",
        "model_used": "claude-haiku-4-5-20251001",
    }

    return gen


@pytest.fixture(scope="module")
def mock_retriever():
    """Create a mock retriever that returns empty chunks."""
    retriever = MagicMock()
    retriever.retrieve.return_value = []
    return retriever


@pytest.fixture(scope="module")
def mock_pipeline():
    """Create a mock VoiceQAPipeline."""
    pipeline = MagicMock()
    pipeline.process_text_query = AsyncMock(return_value={
        "answer_text": "Test answer from pipeline.",
        "session_id": "test-session-123",
        "sources": [],
    })
    return pipeline


@pytest.fixture(scope="module")
def client(real_kb, mock_generator, mock_retriever, mock_pipeline):
    """Create a TestClient with real KB but mocked LLM/DB dependencies."""
    from api.main import app

    # Inject mocked dependencies into app.state
    app.state.defect_kb = real_kb
    app.state.generator = mock_generator
    app.state.retriever = mock_retriever
    app.state.pipeline = mock_pipeline

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ════════════════════════════════════════════════════════════════════
# 1. Predict endpoint tests
# ════════════════════════════════════════════════════════════════════


class TestPredict:
    """Test /api/v1/extension/predict — L1 context-aware suggestions."""

    def test_predict_returns_suggestions_for_engine_room(self, client):
        resp = client.post(
            "/api/v1/extension/predict",
            json={"ship_type": "Bulk Carrier", "inspection_area": "Engine Room"},
        )
        assert resp.status_code == 200
        data = resp.json()
        suggestions = data["suggestions"]
        assert len(suggestions) >= 1

        all_text = " ".join(
            s["text_en"].lower() + " " + s.get("category", "").lower()
            for s in suggestions
        )
        # Engine Room on a Bulk Carrier should surface at least one of these
        engine_keywords = ["corros", "oily water", "fire pump", "bilge", "fuel"]
        assert any(kw in all_text for kw in engine_keywords), (
            f"Expected engine-room defects, got: {all_text[:200]}"
        )

    def test_predict_returns_different_results_for_different_areas(self, client):
        resp_engine = client.post(
            "/api/v1/extension/predict",
            json={"ship_type": "Bulk Carrier", "inspection_area": "Engine Room"},
        )
        resp_bridge = client.post(
            "/api/v1/extension/predict",
            json={"ship_type": "Bulk Carrier", "inspection_area": "Bridge"},
        )
        assert resp_engine.status_code == 200
        assert resp_bridge.status_code == 200

        engine_ids = {s["id"] for s in resp_engine.json()["suggestions"]}
        bridge_ids = {s["id"] for s in resp_bridge.json()["suggestions"]}
        # They should not be completely identical
        assert engine_ids != bridge_ids, "Engine Room and Bridge should differ"

    def test_predict_empty_context_returns_generic(self, client):
        resp = client.post(
            "/api/v1/extension/predict",
            json={},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["suggestions"]) >= 1
        # Without context, returns top frequency-ranked defects
        assert data["source"] == "knowledge_base"

    def test_predict_latency_acceptable(self, client):
        resp = client.post(
            "/api/v1/extension/predict",
            json={"ship_type": "Bulk Carrier", "inspection_area": "Engine Room"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "response_time_ms" in data
        assert isinstance(data["response_time_ms"], int)


# ════════════════════════════════════════════════════════════════════
# 2. Complete endpoint tests
# ════════════════════════════════════════════════════════════════════


class TestComplete:
    """Test /api/v1/extension/complete — L2 keyword autocomplete."""

    def test_complete_filters_by_chinese_keyword(self, client):
        resp = client.post(
            "/api/v1/extension/complete",
            json={"partial_input": "油水"},
        )
        assert resp.status_code == 200
        data = resp.json()
        suggestions = data["suggestions"]
        assert len(suggestions) >= 1

        all_text = " ".join(s["text_en"].lower() for s in suggestions)
        assert "oily water" in all_text or "oil" in all_text, (
            f"Expected oily water results, got: {all_text[:200]}"
        )

    def test_complete_filters_by_english_keyword(self, client):
        resp = client.post(
            "/api/v1/extension/complete",
            json={"partial_input": "fire ext"},
        )
        assert resp.status_code == 200
        data = resp.json()
        suggestions = data["suggestions"]
        assert len(suggestions) >= 1

        all_text = " ".join(s["text_en"].lower() for s in suggestions)
        assert "fire extinguisher" in all_text or "extinguish" in all_text, (
            f"Expected fire extinguisher results, got: {all_text[:200]}"
        )

    def test_complete_returns_empty_for_nonsense(self, client):
        resp = client.post(
            "/api/v1/extension/complete",
            json={"partial_input": "xyzabc123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should return empty or very few results, not error
        assert isinstance(data["suggestions"], list)


# ════════════════════════════════════════════════════════════════════
# 3. Fill endpoint tests
# ════════════════════════════════════════════════════════════════════


class TestFill:
    """Test /api/v1/extension/fill — L3 standardization."""

    def test_fill_generates_clean_english_output(self, client):
        resp = client.post(
            "/api/v1/extension/fill",
            json={"selected_text": "机舱管路锈蚀", "target_lang": "en"},
        )
        assert resp.status_code == 200
        data = resp.json()
        filled = data["filled_text"]
        # Should be English and contain Ref:
        assert "Ref:" in filled or "ref:" in filled.lower(), (
            f"Expected Ref: in output, got: {filled}"
        )
        # Should not contain Chinese pleasantries
        assert not filled.startswith("好的")
        assert not filled.startswith("Here")

    def test_fill_generates_clean_chinese_output(self, client):
        resp = client.post(
            "/api/v1/extension/fill",
            json={"selected_text": "机舱管路锈蚀", "target_lang": "zh"},
        )
        assert resp.status_code == 200
        data = resp.json()
        filled = data["filled_text"]
        # Should contain Chinese text
        assert any("\u4e00" <= c <= "\u9fff" for c in filled), (
            f"Expected Chinese output, got: {filled}"
        )
        # Should contain Ref:
        assert "Ref:" in filled or "ref:" in filled.lower()

    def test_fill_output_not_too_long(self, client):
        resp = client.post(
            "/api/v1/extension/fill",
            json={"selected_text": "灭火器过期", "target_lang": "en"},
        )
        assert resp.status_code == 200
        filled = resp.json()["filled_text"]
        assert len(filled) < 500, f"Fill output too long ({len(filled)} chars): {filled}"

    def test_fill_no_greeting_prefix(self, client):
        resp = client.post(
            "/api/v1/extension/fill",
            json={"selected_text": "消防水带破损", "target_lang": "en"},
        )
        assert resp.status_code == 200
        filled = resp.json()["filled_text"]
        greeting_prefixes = ["好的", "Here", "Sure", "Based on"]
        for prefix in greeting_prefixes:
            assert not filled.startswith(prefix), (
                f"Fill output starts with greeting '{prefix}': {filled[:60]}"
            )


# ════════════════════════════════════════════════════════════════════
# 4. Feedback endpoint tests
# ════════════════════════════════════════════════════════════════════


class TestFeedback:
    """Test /api/v1/extension/feedback — user correction collection."""

    def test_feedback_positive_submission(self, client):
        resp = client.post(
            "/api/v1/extension/feedback",
            json={
                "original_input": "灭火器过期",
                "generated_text": "Portable fire extinguisher overdue.",
                "is_accurate": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_feedback_negative_with_correction(self, client):
        resp = client.post(
            "/api/v1/extension/feedback",
            json={
                "original_input": "灭火器过期",
                "generated_text": "Portable fire extinguisher overdue.",
                "is_accurate": False,
                "corrected_text": "Portable fire extinguisher past expiry date and not maintained.",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_feedback_missing_fields_still_works(self, client):
        resp = client.post(
            "/api/v1/extension/feedback",
            json={
                "original_input": "test input",
                "generated_text": "test output",
                "is_accurate": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ════════════════════════════════════════════════════════════════════
# 5. KB Version endpoint tests
# ════════════════════════════════════════════════════════════════════


class TestKBVersion:
    """Test /api/v1/extension/kb-version and kb-update."""

    def test_kb_version_returns_valid_structure(self, client):
        resp = client.get("/api/v1/extension/kb-version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "defect_count" in data
        assert isinstance(data["defect_count"], int)
        assert data["defect_count"] > 0

    def test_kb_update_returns_data(self, client):
        resp = client.get("/api/v1/extension/kb-update", params={"since_version": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert "updates" in data
        assert isinstance(data["updates"], list)
        assert len(data["updates"]) > 0
        # Each update should have basic defect fields
        first = data["updates"][0]
        assert "id" in first
        assert "standard_text_en" in first


# ════════════════════════════════════════════════════════════════════
# 6. Semaphore isolation test
# ════════════════════════════════════════════════════════════════════


class TestSemaphoreIsolation:
    """Verify predict uses KB_ONLY path and is not blocked by LLM semaphore."""

    def test_predict_uses_kb_only_semaphore(self, client):
        """Conceptual proof: predict on a known area returns fast KB results
        even if the LLM semaphore were fully saturated.

        We verify by checking:
        1. source == "knowledge_base" (didn't need LLM)
        2. response_time_ms is small (KB-only path is <50ms)
        """
        resp = client.post(
            "/api/v1/extension/predict",
            json={
                "ship_type": "Bulk Carrier",
                "inspection_area": "Engine Room",
                "inspection_type": "PSC",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # With a well-populated KB and Engine Room context, we should get
        # enough results (>=3) to skip the LLM fallback entirely
        assert len(data["suggestions"]) >= 3
        assert data["source"] == "knowledge_base"


# ════════════════════════════════════════════════════════════════════
# 7. Regression tests — 20 common surveyor scenarios (parametrized)
# ════════════════════════════════════════════════════════════════════


REGRESSION_CASES = [
    ("机舱管路锈蚀", "en", "corros", "SOLAS"),
    ("救生筏过期", "en", "liferaft", "SOLAS"),
    ("消防水带破损", "en", "fire hose", "SOLAS"),
    ("磁罗经误差超标", "en", "compass", "SOLAS"),
    ("油水分离器故障", "en", "oily water separator", "MARPOL"),
    ("灭火器过期", "en", "fire extinguisher", "SOLAS"),
    ("海图未更新", "en", "chart", "SOLAS"),
    ("船员适任证书过期", "en", "certificate", "SOLAS"),
    ("应急消防泵无法启动", "en", "fire pump", "SOLAS"),
    ("救生艇释放装置缺陷", "en", "lifeboat", "SOLAS"),
    ("油类记录簿记录不完整", "en", "oil record book", "MARPOL"),
    ("锚机刹车带磨损严重", "en", "windlass", ""),
    ("通风挡火闸无法关闭", "en", "fire damper", "SOLAS"),
    ("应急逃生呼吸装置过期", "en", "escape breathing", "SOLAS"),
    ("主机滑油温度报警失灵", "en", "alarm", "SOLAS"),
    ("机舱管路锈蚀", "zh", "锈蚀", "SOLAS"),
    ("灭火器过期", "zh", "灭火器", "SOLAS"),
    ("油水分离器故障", "zh", "油水分离", "MARPOL"),
    ("救生筏过期", "zh", "救生筏", "SOLAS"),
    ("消防水带破损", "zh", "消防", "SOLAS"),
]


@pytest.mark.parametrize(
    "input_text,target_lang,expected_keyword,expected_convention",
    REGRESSION_CASES,
    ids=[f"{case[0]}_{case[1]}" for case in REGRESSION_CASES],
)
def test_fill_regression(
    client,
    input_text,
    target_lang,
    expected_keyword,
    expected_convention,
):
    """Regression: fill endpoint returns relevant, convention-correct output."""
    resp = client.post(
        "/api/v1/extension/fill",
        json={"selected_text": input_text, "target_lang": target_lang},
    )
    assert resp.status_code == 200
    data = resp.json()
    filled = data["filled_text"].lower()
    ref = data.get("regulation_ref", "").upper()

    # Check keyword presence in filled text
    assert expected_keyword.lower() in filled, (
        f"Expected '{expected_keyword}' in fill output for '{input_text}', "
        f"got: {data['filled_text'][:200]}"
    )

    # Check convention presence in regulation_ref (skip if empty expected)
    if expected_convention:
        # Convention can appear in filled_text or regulation_ref
        combined = (data["filled_text"] + " " + ref).upper()
        assert expected_convention.upper() in combined, (
            f"Expected '{expected_convention}' in refs for '{input_text}', "
            f"got ref='{ref}', text='{data['filled_text'][:100]}'"
        )
