from datetime import date

import pytest
from pydantic import ValidationError

from app.application.models import QueryPlan, SearchError, SearchRequest
from app.application.search_service import SearchService
from app.domain.privacy import redact_text, safe_context


class Repository:
    def __init__(self):
        self.calls = []

    def retrieve_customer_snapshot(self, member_id, base_date):
        self.calls.append(("retrieve", member_id, base_date))
        return {"member_id": member_id, "cards": [{"card_id": "C-001", "card_ref": "CARD_001"}],
                "warnings": ["현재 상태 스냅샷입니다."]}

    def search(self, member_id, base_date, validated_sql):
        self.calls.append(("search", member_id, base_date, validated_sql))
        return {"rows": [], "row_count": 0, "warnings": []}


class Model:
    def __init__(self, plan=None, fail_explain=False):
        self.result = plan
        self.fail_explain = fail_explain
        self.plan_calls, self.explain_calls = [], []
        self.plan_dates = []

    def plan(self, *args, base_date):
        self.plan_calls.append(args)
        self.plan_dates.append(base_date)
        return self.result

    def explain(self, *args):
        self.explain_calls.append(args)
        if self.fail_explain:
            raise RuntimeError("should never appear: credentials")
        return "조회 결과 확인용 설명입니다."


def request(**overrides):
    return SearchRequest(**{"member_id": "M-1042", "base_date": "2026-08-31",
                            "query_mode": "fixed", **overrides})


def service(model=None, validator=lambda value: value):
    repository = Repository()
    model = model or Model()
    return SearchService(repository, model, validator, {"customer_cards": ["card_ref"]}), repository, model


def test_fixed_default_never_calls_llm():
    engine, repository, model = service()
    result = engine.execute(request())
    assert result.query_id == "customer_snapshot"
    assert result.explanation_status == "not_requested"
    assert result.explanation is None
    assert repository.calls == [("retrieve", "M-1042", date(2026, 8, 31))]
    assert model.plan_calls == model.explain_calls == []


def test_fixed_catalog_uses_registered_query():
    engine, repository, model = service()
    result = engine.execute(request(query_id="cards"))
    assert result.query_id == "cards"
    assert "FROM customer_cards" in repository.calls[0][-1]
    assert not model.plan_calls


def test_auto_selects_fixed_in_one_plan_call():
    plan = QueryPlan(query_mode="fixed", query_id="cards", sql=None, reason="카드 목록 조회")
    engine, repository, model = service(Model(plan))
    result = engine.execute(request(query_mode="auto", question="M-1042의 보유 카드를 알려 주세요"))
    assert result.query_mode == "fixed" and result.requested_query_mode == "auto"
    assert len(model.plan_calls) == 1 and not model.explain_calls
    assert "M-1042" not in model.plan_calls[0][0]
    assert repository.calls[0][0] == "search"


def test_auto_sql_is_generated_and_executed_without_second_plan_call():
    plan = QueryPlan(query_mode="nl2sql", query_id=None,
                     sql="SELECT month, SUM(approved_amount) FROM monthly_usage GROUP BY month", reason="합계")
    engine, repository, model = service(Model(plan), validator=lambda value: value + " LIMIT 100")
    result = engine.execute(request(query_mode="auto", question="월별 총액을 합산해 주세요"))
    assert result.query_mode == "nl2sql"
    assert len(model.plan_calls) == 1 and not model.explain_calls
    assert repository.calls[0][-1].endswith("LIMIT 100")


def test_forced_nl2sql_rejects_wrong_mode():
    plan = QueryPlan(query_mode="fixed", query_id="cards", sql=None, reason="카드 조회")
    engine, repository, _ = service(Model(plan))
    with pytest.raises(SearchError, match="검색 방식"):
        engine.execute(request(query_mode="nl2sql", question="카드 조회"))
    assert repository.calls == []


@pytest.mark.parametrize("mode", ["auto", "nl2sql"])
@pytest.mark.parametrize("base_date", [date(2026, 8, 31), date(2026, 8, 15), date(2026, 1, 5)])
def test_planner_and_repository_receive_same_requested_date(mode, base_date):
    plan = QueryPlan(query_mode="nl2sql", query_id=None,
                     sql="SELECT month, SUM(approved_amount) FROM monthly_usage GROUP BY month",
                     reason="monthly total")
    engine, repository, model = service(Model(plan))
    engine.execute(request(query_mode=mode, base_date=base_date, question="monthly total"))
    assert model.plan_dates == [base_date]
    assert repository.calls[0][2] == base_date


def test_unsafe_sql_does_not_reach_database():
    def reject(sql):
        raise ValueError("DROP TABLE secrets")
    plan = QueryPlan(query_mode="nl2sql", query_id=None, sql="DROP TABLE member", reason="malicious")
    engine, repository, _ = service(Model(plan), reject)
    with pytest.raises(SearchError) as failure:
        engine.execute(request(query_mode="auto", question="테이블 조회"))
    assert failure.value.code == "unsafe_sql"
    assert "DROP" not in failure.value.message
    assert not repository.calls


def test_unsupported_question_does_not_query_database():
    plan = QueryPlan(query_mode="unsupported", query_id=None, sql=None, reason="이탈 확률이 없습니다")
    engine, repository, _ = service(Model(plan))
    with pytest.raises(SearchError) as failure:
        engine.execute(request(query_mode="auto", question="이탈 확률은?"))
    assert failure.value.code == "unsupported_question" and not repository.calls


def test_explanation_is_optional_and_redacted():
    engine, _, model = service()
    result = engine.execute(request(explain=True, question="M-1042 C-001 정보를 설명해 주세요"))
    assert result.explanation_status == "completed"
    assert not model.plan_calls
    assert len(model.explain_calls) == 1
    assert "M-1042" not in str(model.explain_calls)
    assert "C-001" not in str(model.explain_calls)
    assert "CARD_001" in str(model.explain_calls)
    assert result.data["member_id"] == "M-1042"  # 내부 결과의 식별자는 보존


def test_explanation_failure_preserves_search():
    engine, _, _ = service(Model(fail_explain=True))
    result = engine.execute(request(explain=True))
    assert result.data["cards"]
    assert result.explanation_status == "failed" and result.explanation is None
    assert "credentials" not in result.model_dump_json()


@pytest.mark.parametrize("overrides", [
    {"query_mode": "auto"}, {"query_mode": "nl2sql", "question": " "},
    {"query_mode": "auto", "question": "카드", "query_id": "cards"},
    {"base_date": 1798761600}, {"base_date": "2026-02-30"},
    {"sql": "SELECT 1"}, {"member_id": "M-1042' OR TRUE--"},
])
def test_invalid_requests_rejected(overrides):
    with pytest.raises(ValidationError):
        request(**overrides)


def test_sensitive_identifiers_removed_recursively():
    data = {"member_id": "custom-member", "nested": {"card_id": "original-card"},
            "source": "custom-member / original-card", "amount": 12345}
    clean = safe_context(data)
    assert "custom-member" not in str(clean) and "original-card" not in str(clean)
    assert clean["amount"] == 12345
    assert "010-1234-5678" not in redact_text("연락처 010-1234-5678")


def test_schema_does_not_call_llm_or_repository():
    engine, repository, model = service()
    schema = engine.schema()
    assert len(schema["fixed_queries"]) == 4
    assert repository.calls == model.plan_calls == []
