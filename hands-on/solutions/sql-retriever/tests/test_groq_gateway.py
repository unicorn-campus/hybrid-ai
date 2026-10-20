from datetime import date

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.application.models import QueryPlan, SearchError
from app.infrastructure.groq_gateway import GroqGateway
from app.infrastructure.settings import MODEL, Settings


class FakeModel:
    def __init__(self, response):
        self.response = response

    def with_structured_output(self, *args, **kwargs):
        return RunnableLambda(lambda prompt: self.response)


def gateway(response):
    recorded = {}

    def factory(**kwargs):
        recorded.update(kwargs)
        return FakeModel(response)

    return GroqGateway(Settings("dsn", "password", "fake-test-key"), factory), recorded


def test_structured_groq_plan_and_requested_model():
    plan = QueryPlan(query_mode="fixed", query_id="cards", sql=None, reason="카드 조회")
    model, options = gateway({"parsed": plan, "parsing_error": None,
                              "raw": AIMessage(content="", response_metadata={"finish_reason": "stop"})})
    result = model.plan("카드를 보여 주세요", {}, [], "auto", base_date=date(2026, 8, 31))
    assert result == plan
    assert options["model"] == MODEL == "openai/gpt-oss-120b"
    assert options["model_kwargs"]["include_reasoning"] is False


@pytest.mark.parametrize("response", [
    {"parsed": None, "parsing_error": ValueError("raw credentials")},
    {"parsed": QueryPlan(query_mode="fixed", query_id="cards", sql=None, reason="카드"),
     "raw": AIMessage(content="", response_metadata={"finish_reason": "length"})},
])
def test_invalid_or_truncated_plan_is_not_executed(response):
    model, _ = gateway(response)
    with pytest.raises(SearchError) as failure:
        model.plan("질문", {}, [], "auto", base_date=date(2026, 8, 31))
    assert failure.value.code == "planning_failed"
    assert "credentials" not in failure.value.message


def test_no_api_key_fails_only_when_model_is_used():
    model = GroqGateway(Settings("dsn", "password", ""))
    with pytest.raises(SearchError) as failure:
        model.plan("질문", {}, [], "auto", base_date=date(2026, 8, 31))
    assert failure.value.code == "missing_groq_key"


def test_empty_or_truncated_explanation_is_not_completed():
    settings = Settings("dsn", "password", "fake-test-key")
    model = GroqGateway(settings, lambda **kwargs: RunnableLambda(
        lambda value: AIMessage(content="부분 응답", response_metadata={"finish_reason": "length"})))
    with pytest.raises(ValueError):
        model.explain("설명해 주세요", {})
