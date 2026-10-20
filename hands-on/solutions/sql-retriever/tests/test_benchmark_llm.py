from types import SimpleNamespace

import pytest

# benchmark_llm.py는 실습 배포본에 포함되지 않을 수 있으므로, 없으면 이 파일의 테스트를 건너뜀.
benchmark_llm = pytest.importorskip("benchmark_llm")
from benchmark_llm import CASES, _assess, _latency_summary, _rate, _select_gateway, _semantic_match  # noqa: E402
from app.application.models import QueryPlan  # noqa: E402


def case(case_id):
    return next(item for item in CASES if item.case_id == case_id)


def test_semantic_check_distinguishes_sum_from_counting_rows():
    correct = "SELECT month, SUM(transaction_count) FROM monthly_usage GROUP BY month LIMIT 100"
    wrong = "SELECT month, COUNT(*) FROM monthly_usage GROUP BY month LIMIT 100"
    assert _semantic_match("N2", correct)
    assert not _semantic_match("N2", wrong)


def test_plan_match_requires_route_guard_and_meaning():
    plan = QueryPlan(
        query_mode="nl2sql",
        query_id=None,
        sql="SELECT month, SUM(approved_amount) FROM monthly_usage GROUP BY month LIMIT 100",
        reason="월별 고객 전체 합계",
    )
    result = _assess(case("N1"), plan)
    assert result == {
        "route_match": True,
        "fixed_id_match": True,
        "sql_guard_pass": True,
        "semantic_match": True,
        "plan_match": True,
    }


def test_unsupported_plan_must_not_contain_executable_target():
    plan = QueryPlan(query_mode="unsupported", query_id=None, sql=None, reason="지원 데이터 없음")
    result = _assess(case("U3"), plan)
    assert result["semantic_match"] and result["plan_match"]


def test_failed_calls_count_as_quality_failures_and_latency_samples():
    records = [
        {"status": "ok", "plan_match": True, "latency_ms": 100.0},
        {"status": "error", "latency_ms": 300.0},
    ]

    assert _rate(records, "plan_match", failures_as_false=True) == 0.5
    assert _latency_summary(records) == {"samples": 2, "p50_ms": 200.0, "p95_ms": 290.0}


def test_vllm_benchmark_selects_the_served_model(monkeypatch):
    sentinel = object()
    settings = SimpleNamespace(vllm_model="gemma-vllm:test")
    monkeypatch.setattr(
        benchmark_llm,
        "create_language_model",
        lambda actual, provider, runtime: sentinel,
    )

    model_name, gateway = _select_gateway("google_local-vllm", settings)

    assert model_name == "gemma-vllm:test"
    assert gateway is sentinel
