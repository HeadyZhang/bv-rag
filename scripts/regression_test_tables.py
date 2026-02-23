"""End-to-end regression test queries for structured table ingestion.

Sends predefined queries to the local API and checks that the answers
contain expected keywords/values.  Run after each batch ingestion.

Usage:
    python -m scripts.regression_test_tables
    python -m scripts.regression_test_tables --batch 1
    python -m scripts.regression_test_tables --base-url http://localhost:8000

Requires a running BV-RAG server.
"""

import argparse
import logging
import sys

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REGRESSION_CASES: list[dict] = [
    # ----- Batch 1: SOLAS II-2 fire protection tables -----
    {
        "batch": 1,
        "query": "油轮走廊和控制站之间的舱壁防火等级",
        "expected_keywords": ["A-0", "9.7"],
        "reject_keywords": ["未找到", "未检索到"],
        "description": "Tanker corridor vs control station → A-0, Table 9.7",
    },
    {
        "batch": 1,
        "query": "散货船走廊和控制站之间的舱壁防火等级",
        "expected_keywords": ["9.5"],
        "reject_keywords": ["未找到", "未检索到"],
        "description": "Cargo ship corridor vs control station → Table 9.5",
    },
    {
        "batch": 1,
        "query": "客船超过36人走廊和机舱之间舱壁防火等级",
        "expected_keywords": ["9.1"],
        "reject_keywords": ["未找到"],
        "description": "Passenger >36 corridor vs machinery → Table 9.1",
    },
    {
        "batch": 1,
        "query": "油轮居住区和机舱之间的舱壁防火等级",
        "expected_keywords": ["A-60", "9.7"],
        "reject_keywords": ["未找到"],
        "description": "Tanker accommodation vs machinery → A-60, Table 9.7",
    },
    {
        "batch": 1,
        "query": "SOLAS II-2 Regulation 3 处所分类有哪些类别",
        "expected_keywords": ["控制站", "走廊"],
        "reject_keywords": ["未找到"],
        "description": "Reg 3 category definitions",
    },
    {
        "batch": 1,
        "query": "货船需要什么灭火系统",
        "expected_keywords": ["CO2", "灭火"],
        "reject_keywords": ["未找到"],
        "description": "Cargo ship firefighting systems → Reg 10",
    },
    # ----- Batch 2: MARPOL emission limits -----
    {
        "batch": 2,
        "query": "2021年建造的船NOx排放限值是多少",
        "expected_keywords": ["Tier"],
        "reject_keywords": ["未找到", "未检索到"],
        "description": "2021 ship NOx → Tier III in ECA",
    },
    {
        "batch": 2,
        "query": "2025年ECA内燃油硫含量限值",
        "expected_keywords": ["0.10"],
        "reject_keywords": ["未找到"],
        "description": "2025 ECA sulphur → 0.10%",
    },
    {
        "batch": 2,
        "query": "机舱含油污水排放标准",
        "expected_keywords": ["15"],
        "reject_keywords": ["未找到"],
        "description": "Oily water discharge → 15 ppm",
    },
    {
        "batch": 2,
        "query": "油轮在特殊区域内可以排放货舱洗舱水吗",
        "expected_keywords": ["禁止"],
        "reject_keywords": ["未找到"],
        "description": "Tanker special area cargo tank washwater → prohibited",
    },
    # ----- Batch 3: SOLAS III/IV/V + STCW -----
    {
        "batch": 3,
        "query": "散货船需要多少救生筏",
        "expected_keywords": ["200"],
        "reject_keywords": ["未找到"],
        "description": "Cargo ship liferaft → 200% capacity",
    },
    {
        "batch": 3,
        "query": "A3航区需要什么通信设备",
        "expected_keywords": ["GMDSS"],
        "reject_keywords": ["未找到"],
        "description": "A3 sea area → GMDSS equipment list",
    },
    {
        "batch": 3,
        "query": "船员最低休息时间是多少",
        "expected_keywords": ["10", "77"],
        "reject_keywords": ["未找到"],
        "description": "Crew rest hours → 10h/24h, 77h/7days",
    },
]


def run_regression(
    base_url: str,
    batch_filter: int | None = None,
) -> bool:
    """Run regression queries and return True if all pass."""
    cases = REGRESSION_CASES
    if batch_filter is not None:
        cases = [c for c in cases if c["batch"] == batch_filter]

    if not cases:
        logger.error("No cases for batch %s", batch_filter)
        return False

    client = httpx.Client(base_url=base_url, timeout=120.0)
    total_pass = 0
    total_fail = 0
    results: list[dict] = []

    for case in cases:
        query = case["query"]
        try:
            resp = client.post(
                "/api/v1/voice/text-query",
                data={
                    "text": query,
                    "session_id": "regression-test",
                    "generate_audio": "false",
                    "input_mode": "text",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data.get("answer_text", "") or data.get("answer", "")
        except Exception as exc:
            logger.error("  ERROR: %s — %s", query[:40], exc)
            results.append({"case": case["description"], "status": "ERROR", "detail": str(exc)})
            total_fail += 1
            continue

        # Check expected keywords
        missing_expected = [
            kw for kw in case["expected_keywords"] if kw not in answer
        ]
        # Check reject keywords
        found_rejected = [
            kw for kw in case.get("reject_keywords", []) if kw in answer
        ]

        passed = not missing_expected and not found_rejected
        status = "PASS" if passed else "FAIL"

        if passed:
            total_pass += 1
            logger.info("  PASS: %s", case["description"])
        else:
            total_fail += 1
            detail_parts = []
            if missing_expected:
                detail_parts.append(f"missing: {missing_expected}")
            if found_rejected:
                detail_parts.append(f"rejected found: {found_rejected}")
            detail = "; ".join(detail_parts)
            logger.warning("  FAIL: %s — %s", case["description"], detail)

        results.append({
            "case": case["description"],
            "status": status,
            "answer_preview": answer[:200],
        })

    logger.info("\n" + "=" * 60)
    logger.info("REGRESSION SUMMARY")
    logger.info("=" * 60)
    for r in results:
        logger.info("  %s  %s", r["status"], r["case"])
    logger.info("-" * 60)
    logger.info("  TOTAL: %d PASS, %d FAIL out of %d cases", total_pass, total_fail, len(cases))

    return total_fail == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run table regression tests")
    parser.add_argument("--batch", type=int, default=None, help="Filter by batch number")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()

    ok = run_regression(args.base_url, batch_filter=args.batch)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
