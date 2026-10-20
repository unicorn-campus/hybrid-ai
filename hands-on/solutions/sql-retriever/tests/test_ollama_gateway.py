from datetime import date

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.application.models import QueryPlan, SearchError
from app.infrastructure.ollama_gateway import OllamaGateway


GEMMA_MODEL = "hf.co/unsloth/gemma-4-12B-it-qat-GGUF:UD-Q4_K_XL"


class FakePlanningModel:
    def __init__(self, response, structured_options):
        self.response = response
        self.structured_options = structured_options

    def with_structured_output(self, schema, **kwargs):
        self.structured_options.update({"schema": schema, **kwargs})
        return RunnableLambda(lambda prompt: self.response)


def planning_gateway(response):
    model_options = {}
    structured_options = {}

    def factory(**kwargs):
        model_options.update(kwargs)
        return FakePlanningModel(response, structured_options)

    gateway = OllamaGateway(
        "http://127.0.0.1:11434",
        GEMMA_MODEL,
        45.0,
        2048,
        factory,
    )
    return gateway, model_options, structured_options


def test_structured_ollama_plan_and_model_options():
    plan = QueryPlan(query_mode="fixed", query_id="cards", sql=None, reason="카드 조회")
    response = {
        "parsed": plan,
        "parsing_error": None,
        "raw": AIMessage(
            content="",
            tool_calls=[{"name": "QueryPlan", "args": plan.model_dump(), "id": "call-1"}],
            response_metadata={"done": True, "done_reason": "stop"},
        ),
    }
    gateway, model_options, structured_options = planning_gateway(response)

    result = gateway.plan("카드를 보여 주세요", {}, [], "auto", base_date=date(2026, 8, 31))

    assert result == plan
    assert model_options == {
        "model": GEMMA_MODEL,
        "base_url": "http://127.0.0.1:11434",
        "temperature": 0,
        "reasoning": False,
        "num_ctx": 4096,
        "num_predict": 2048,
        "client_kwargs": {"timeout": 45.0},
    }
    assert structured_options == {
        "schema": QueryPlan,
        "method": "json_schema",
        "include_raw": True,
    }


def test_plan_falls_back_and_caches_supported_structured_output_method():
    plan = QueryPlan(query_mode="fixed", query_id="cards", sql=None, reason="카드 조회")
    calls = []

    class NegotiatingModel:
        def with_structured_output(self, schema, **kwargs):
            method = kwargs["method"]
            calls.append(method)
            if method == "json_schema":
                return RunnableLambda(lambda prompt: (_ for _ in ()).throw(ValueError("unsupported")))
            return RunnableLambda(
                lambda prompt: {
                    "parsed": plan,
                    "parsing_error": None,
                    "raw": AIMessage(
                        content="",
                        tool_calls=[{
                            "name": "QueryPlan",
                            "args": plan.model_dump(),
                            "id": "call-1",
                        }],
                        response_metadata={"done": True, "done_reason": "stop"},
                    ),
                }
            )

    gateway = OllamaGateway(
        "http://127.0.0.1:11434",
        GEMMA_MODEL,
        45.0,
        2048,
        lambda **kwargs: NegotiatingModel(),
    )

    assert gateway.plan("카드를 보여 주세요", {}, [], "auto", base_date=date(2026, 8, 31)) == plan
    assert gateway.plan("카드를 다시 보여 주세요", {}, [], "auto", base_date=date(2026, 8, 31)) == plan
    assert calls == ["json_schema", "function_calling", "function_calling"]
    assert gateway.structured_output_attempts == 3
    assert gateway.structured_output_fallback_calls == 1


def test_cached_method_failure_tries_remaining_methods():
    plan = QueryPlan(query_mode="fixed", query_id="cards", sql=None, reason="카드 조회")
    calls = []
    json_invocations = 0

    class RecoveringModel:
        def with_structured_output(self, schema, **kwargs):
            method = kwargs["method"]
            calls.append(method)

            def invoke(prompt):
                nonlocal json_invocations
                if method == "json_schema":
                    json_invocations += 1
                    if json_invocations == 2:
                        raise ValueError("response-specific schema failure")
                return {
                    "parsed": plan,
                    "parsing_error": None,
                    "raw": AIMessage(
                        content="{}",
                        response_metadata={"done": True, "done_reason": "stop"},
                    ),
                }

            return RunnableLambda(invoke)

    gateway = OllamaGateway(
        "http://127.0.0.1:11434",
        GEMMA_MODEL,
        45.0,
        2048,
        lambda **kwargs: RecoveringModel(),
    )

    assert gateway.plan("카드를 보여 주세요", {}, [], "auto", base_date=date(2026, 8, 31)) == plan
    assert gateway.plan("카드를 다시 보여 주세요", {}, [], "auto", base_date=date(2026, 8, 31)) == plan
    assert calls == ["json_schema", "json_schema", "function_calling"]
    assert gateway._structured_method == "function_calling"
    assert gateway.structured_output_attempts == 3
    assert gateway.structured_output_fallback_calls == 1


@pytest.mark.parametrize(
    "response",
    [
        {"parsed": None, "parsing_error": ValueError("raw credentials"), "raw": None},
        {
            "parsed": QueryPlan(query_mode="fixed", query_id="cards", sql=None, reason="카드"),
            "parsing_error": None,
            "raw": AIMessage(content="", response_metadata={"done": True, "done_reason": "stop"}),
        },
        {
            "parsed": QueryPlan(query_mode="fixed", query_id="cards", sql=None, reason="카드"),
            "parsing_error": None,
            "raw": AIMessage(content="{}", response_metadata={"done": True, "done_reason": "length"}),
        },
    ],
)
def test_invalid_empty_or_truncated_plan_is_not_executed(response):
    gateway, _, _ = planning_gateway(response)

    with pytest.raises(SearchError) as failure:
        gateway.plan("질문", {}, [], "auto", base_date=date(2026, 8, 31))

    assert failure.value.code == "planning_failed"
    assert "credentials" not in failure.value.message


def test_explanation_uses_same_model_and_returns_trimmed_text():
    recorded = {}

    def factory(**kwargs):
        recorded.update(kwargs)
        return RunnableLambda(
            lambda value: AIMessage(
                content="  조회 결과 설명  ",
                response_metadata={"done": True, "done_reason": "stop"},
            )
        )

    gateway = OllamaGateway("http://localhost:11434", GEMMA_MODEL, 10.0, 512, factory)

    assert gateway.explain("설명해 주세요", {}) == "조회 결과 설명"
    assert recorded["num_predict"] == 512


@pytest.mark.parametrize(
    "message",
    [
        AIMessage(content="", response_metadata={"done": True, "done_reason": "stop"}),
        AIMessage(content="일부 응답", response_metadata={"done": False}),
    ],
)
def test_empty_or_incomplete_explanation_returns_safe_error(message):
    gateway = OllamaGateway(
        "http://localhost:11434",
        GEMMA_MODEL,
        10.0,
        512,
        lambda **kwargs: RunnableLambda(lambda value: message),
    )

    with pytest.raises(SearchError) as failure:
        gateway.explain("설명해 주세요", {})

    assert failure.value.code == "explanation_failed"
    assert "일부 응답" not in failure.value.message
