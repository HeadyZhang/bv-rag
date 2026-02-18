"""Regression test: 5 surveyor questions against ground truth.

Tests the full pipeline offline (QueryEnhancer + QueryClassifier +
ClarificationChecker) and optionally the live API endpoint.

Usage:
    # Offline component tests (no API needed):
    python -m scripts.regression_test_5questions

    # Full API tests (requires running server):
    python -m scripts.regression_test_5questions --api http://localhost:8000
"""
import argparse
import json
import logging
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GROUND_TRUTH = {
    "T101": {
        "question": (
            "货船上相邻的两个房间，一个是厨房，另一个是走廊，"
            "请问它们之间的舱壁应该是什么等级的防火分隔？"
        ),
        "correct_answer": "A-0",
        "correct_table": "Table 9.5",
        "correct_categories": {"厨房": "Category (9)", "走廊": "Category (2)"},
        "must_contain": ["A-0", "Table 9.5", "Category"],
        "must_not_contain": ["B-15"],
        "should_clarify": False,
        "expected_intent": "specification",
        "expected_topic": "fire_division",
        "expected_ship_type": "cargo ship",
    },
    "T102": {
        "question": (
            "上层是驾驶室，正下层是船员住舱，"
            "它们之间分割的甲板应该是什么样的防火等级？"
        ),
        "correct_answer": "A-60",
        "universal": True,
        "must_contain": ["A-60"],
        "should_clarify": False,
        "expected_intent": "specification",
        "expected_topic": "fire_division",
    },
    "T103": {
        "question": (
            "一艘90米的货船有free-fall lifeboat，"
            "两舷的救生筏是不是都不需要davit了？"
        ),
        "correct_answer": "不是，至少一舷仍需要 davit",
        "must_contain": ["davit"],
        "should_clarify": False,
        "expected_intent": "applicability",
        "expected_topic": "lifesaving",
        "expected_ship_type": "cargo ship",
    },
    "T104": {
        "question": (
            "一艘10万载重吨的油轮，其排油监控系统（ODME）"
            "向舷外排油时，总排油量不能超过多少？"
        ),
        "correct_answer": "总装载容积的 1/30,000",
        "must_contain": ["1/30", "MARPOL"],
        "should_clarify": False,
        "expected_intent": "specification",
        "expected_topic": "oil_discharge",
        "expected_ship_type": "oil tanker",
    },
    "T105": {
        "question": (
            "在干舷甲板上有3层上层建筑，每层高度3米。"
            "请问在第3层上层建筑上方的透气管（Air pipe），"
            "其离甲板的开口高度有什么要求？"
        ),
        "correct_answer": "760mm or 450mm depending on position",
        "must_contain": ["760", "450"],
        "should_clarify": False,
        "expected_intent": "specification",
        "expected_topic": "air_pipe",
    },
}


def test_query_enhancer():
    """Test that QueryEnhancer correctly matches Chinese terms."""
    from retrieval.query_enhancer import QueryEnhancer

    enhancer = QueryEnhancer()
    results = {}

    for tid, truth in GROUND_TRUTH.items():
        enhanced = enhancer.enhance(truth["question"])
        matched = enhancer._last_matched_terms
        regs = enhancer._last_relevant_regs

        issues = []

        # Check that matched_terms is not empty
        if not matched:
            issues.append("matched_terms is EMPTY")

        # Check expected terms based on test
        if tid == "T101":
            for term in ["galley", "corridor", "fire division", "cargo ship"]:
                if not any(term.lower() in t.lower() for t in matched):
                    issues.append(f"missing term: {term}")
            if "SOLAS II-2/9" not in regs:
                issues.append("missing reg: SOLAS II-2/9")

        elif tid == "T103":
            for term in ["free-fall", "davit", "liferaft"]:
                if not any(term.lower() in t.lower() for t in matched):
                    issues.append(f"missing term: {term}")

        elif tid == "T104":
            for term in ["ODME", "oil discharge"]:
                if not any(term.lower() in t.lower() for t in matched):
                    issues.append(f"missing term: {term}")

        elif tid == "T105":
            for term in ["air pipe", "superstructure"]:
                if not any(term.lower() in t.lower() for t in matched):
                    issues.append(f"missing term: {term}")

        status = "PASS" if not issues else "FAIL"
        results[tid] = {"status": status, "issues": issues, "matched": len(matched)}
        logger.info(
            f"  {tid} QueryEnhancer: {status} "
            f"(matched={len(matched)}, regs={len(regs)})"
        )
        for issue in issues:
            logger.warning(f"    {issue}")

    return results


def test_query_classifier():
    """Test that QueryClassifier correctly identifies intent/topic/ship_type."""
    from retrieval.query_classifier import QueryClassifier

    classifier = QueryClassifier()
    results = {}

    for tid, truth in GROUND_TRUTH.items():
        classification = classifier.classify(truth["question"])
        issues = []

        if "expected_intent" in truth:
            if classification["intent"] != truth["expected_intent"]:
                issues.append(
                    f"intent: expected={truth['expected_intent']}, "
                    f"got={classification['intent']}"
                )

        if "expected_topic" in truth:
            if classification["topic"] != truth["expected_topic"]:
                issues.append(
                    f"topic: expected={truth['expected_topic']}, "
                    f"got={classification['topic']}"
                )

        if "expected_ship_type" in truth:
            ship_type = classification["ship_info"].get("type")
            if ship_type != truth["expected_ship_type"]:
                issues.append(
                    f"ship_type: expected={truth['expected_ship_type']}, "
                    f"got={ship_type}"
                )

        status = "PASS" if not issues else "FAIL"
        results[tid] = {"status": status, "issues": issues, "classification": classification}
        logger.info(
            f"  {tid} Classifier: {status} "
            f"(intent={classification['intent']}, topic={classification['topic']})"
        )
        for issue in issues:
            logger.warning(f"    {issue}")

    return results


def test_clarification_checker():
    """Test that ClarificationChecker does NOT trigger for these 5 questions."""
    from retrieval.clarification_checker import ClarificationChecker
    from retrieval.query_classifier import QueryClassifier

    classifier = QueryClassifier()
    checker = ClarificationChecker()
    results = {}

    for tid, truth in GROUND_TRUTH.items():
        classification = classifier.classify(truth["question"])
        topic = classification.get("topic") or checker.detect_topic(truth["question"])
        needs_clarification, questions = checker.check(
            intent=classification["intent"],
            ship_info=classification.get("ship_info", {}),
            query=truth["question"],
            topic=topic,
        )

        issues = []
        if truth["should_clarify"] != needs_clarification:
            if needs_clarification:
                slots = [q["slot"] for q in questions]
                issues.append(f"should NOT clarify but triggered: {slots}")
            else:
                issues.append("should clarify but didn't")

        status = "PASS" if not issues else "FAIL"
        results[tid] = {
            "status": status,
            "issues": issues,
            "needs_clarification": needs_clarification,
        }
        logger.info(
            f"  {tid} Clarification: {status} "
            f"(needs_clarification={needs_clarification})"
        )
        for issue in issues:
            logger.warning(f"    {issue}")

    return results


def test_api(api_url: str):
    """Test full API responses against ground truth (requires running server)."""
    import httpx

    results = {}

    for tid, truth in GROUND_TRUTH.items():
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing {tid}: {truth['question'][:50]}...")

        try:
            resp = httpx.post(
                f"{api_url}/api/v1/voice/text-query",
                json={"text": truth["question"]},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            results[tid] = {"status": "ERROR", "issues": [str(e)]}
            logger.error(f"  {tid}: API error: {e}")
            continue

        answer = data.get("answer_text", "")
        did_clarify = data.get("action") == "clarify"

        score = 0
        max_score = 0
        issues = []

        # Check: no unnecessary clarification
        max_score += 2
        if not truth["should_clarify"] and did_clarify:
            issues.append("should NOT clarify but triggered clarification")
        elif not truth["should_clarify"] and not did_clarify:
            score += 2

        # Check: must_contain keywords
        for kw in truth.get("must_contain", []):
            max_score += 1
            if kw.lower() in answer.lower():
                score += 1
            else:
                issues.append(f"missing keyword: {kw}")

        # Check: must_not_contain
        for kw in truth.get("must_not_contain", []):
            max_score += 1
            if kw.lower() not in answer.lower():
                score += 1
            else:
                issues.append(f"contains wrong content: {kw}")

        pct = score / max_score * 100 if max_score > 0 else 0
        if pct >= 80:
            status = "PASS"
        elif pct >= 50:
            status = "PARTIAL"
        else:
            status = "FAIL"

        results[tid] = {
            "status": status,
            "score": f"{score}/{max_score} ({pct:.0f}%)",
            "issues": issues,
            "answer_preview": answer[:200],
        }
        logger.info(f"  {tid}: {status} {score}/{max_score}")
        for issue in issues:
            logger.warning(f"    {issue}")

    return results


def print_summary(title: str, results: dict):
    """Print a summary table."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

    pass_count = sum(1 for r in results.values() if r["status"] == "PASS")
    total = len(results)

    for tid, r in sorted(results.items()):
        status_icon = {"PASS": "OK", "FAIL": "XX", "PARTIAL": "!!", "ERROR": "??"}.get(
            r["status"], "??"
        )
        extra = ""
        if r.get("score"):
            extra = f" {r['score']}"
        print(f"  [{status_icon}] {tid}: {r['status']}{extra}")
        for issue in r.get("issues", []):
            print(f"       -> {issue}")

    print(f"\n  Result: {pass_count}/{total} passed")
    return pass_count == total


def main():
    parser = argparse.ArgumentParser(description="BV-RAG 5-question regression test")
    parser.add_argument("--api", help="API base URL for full integration test")
    args = parser.parse_args()

    all_pass = True

    # Offline component tests
    print("\n[1/3] QueryEnhancer tests...")
    enhancer_results = test_query_enhancer()
    if not print_summary("QueryEnhancer Results", enhancer_results):
        all_pass = False

    print("\n[2/3] QueryClassifier tests...")
    classifier_results = test_query_classifier()
    if not print_summary("QueryClassifier Results", classifier_results):
        all_pass = False

    print("\n[3/3] ClarificationChecker tests...")
    clarification_results = test_clarification_checker()
    if not print_summary("ClarificationChecker Results", clarification_results):
        all_pass = False

    # Optional API test
    if args.api:
        print(f"\n[4/4] Full API tests against {args.api}...")
        api_results = test_api(args.api)
        if not print_summary("API Integration Results", api_results):
            all_pass = False

    print(f"\n{'='*60}")
    if all_pass:
        print("  ALL TESTS PASSED")
    else:
        print("  SOME TESTS FAILED - see details above")
    print(f"{'='*60}\n")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
