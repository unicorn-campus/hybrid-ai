from datetime import date

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.application.models import QueryPlan, SearchError
from app.infrastructure.vllm_gateway import VllmGateway


class FakeVllmModel:
    def __init__(self, response, structured_options):
        self.response = response
        self.structured_options = structured_options

    def with_structured_output(self, schema, **kwargs):
        self.structured_options.update({"schema": schema, **kwargs})
        return RunnableLambda(lambda prompt: self.response)


def test_vllm_plan_uses_openai_compatible_json_schema():
    plan = QueryPlan(query_mode="fixed", query_id="cards", sql=None, reason="카드 조회")
    model_options = {}
    structured_options = {}

    def factory(**kwargs):
        model_options.update(kwargs)
        return FakeVllmModel(
            {
                "parsed": plan,
                "parsing_error": None,
                "raw": AIMessage(content="{}", response_metadata={"finish_reason": "stop"}),
            },
            structured_options,
        )

    gateway = VllmGateway(
        "http://localhost:8000/v1/", "gemma:test", "token", 30.0, 512, factory,
    )

    assert gateway.plan("카드를 보여 주세요", {}, [], "auto", base_date=date(2026, 8, 31)) == plan
    assert model_options == {
        "model": "gemma:test",
        "base_url": "http://localhost:8000/v1",
        "api_key": "token",
        "temperature": 0,
        "timeout": 30.0,
        "max_completion_tokens": 512,
        "max_retries": 0,
    }
    assert structured_options == {
        "schema": QueryPlan,
        "method": "json_schema",
        "include_raw": True,
        "strict": True,
    }


def test_vllm_requires_key_without_exposing_it():
    gateway = VllmGateway("http://localhost:8000/v1", "gemma:test", "", 30.0, 512)

    with pytest.raises(SearchError) as failure:
        gateway.plan("질문", {}, [], "auto", base_date=date(2026, 8, 31))

    assert failure.value.code == "missing_vllm_key"


def test_vllm_rejects_incomplete_structured_response():
    plan = QueryPlan(query_mode="fixed", query_id="cards", sql=None, reason="카드 조회")
    gateway = VllmGateway(
        "http://localhost:8000/v1",
        "gemma:test",
        "token",
        30.0,
        512,
        lambda **kwargs: FakeVllmModel(
            {
                "parsed": plan,
                "parsing_error": None,
                "raw": AIMessage(content="{}", response_metadata={"finish_reason": "length"}),
            },
            {},
        ),
    )

    with pytest.raises(SearchError) as failure:
        gateway.plan("질문", {}, [], "auto", base_date=date(2026, 8, 31))

    assert failure.value.code == "planning_failed"


def test_vllm_explanation_uses_plain_chat_completion():
    gateway = VllmGateway(
        "http://localhost:8000/v1",
        "gemma:test",
        "token",
        30.0,
        512,
        lambda **kwargs: RunnableLambda(
            lambda prompt: AIMessage(
                content="  조회 결과 설명  ", response_metadata={"finish_reason": "stop"},
            )
        ),
    )

    assert gateway.explain("설명해 주세요", {"rows": []}) == "조회 결과 설명"
