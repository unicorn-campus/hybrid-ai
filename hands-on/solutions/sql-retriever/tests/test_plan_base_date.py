"""요청 기준일이 실제 모델 메시지까지 전달되는지 확인합니다."""

import json
from datetime import date

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.application.models import QueryPlan
from app.infrastructure.groq_gateway import GroqGateway
from app.infrastructure.ollama_gateway import OllamaGateway
from app.infrastructure.settings import Settings
from app.infrastructure.vllm_gateway import VllmGateway


@pytest.mark.parametrize("provider", ["groq", "ollama", "vllm"])
@pytest.mark.parametrize("base_date", [date(2026, 8, 31), date(2026, 8, 15), date(2026, 1, 5)])
def test_plan_message_contains_requested_date(provider, base_date):
    messages = []
    plan = QueryPlan(query_mode="fixed", query_id="cards", sql=None, reason="cards")

    class Model:
        def with_structured_output(self, *args, **kwargs):
            def invoke(prompt):
                messages.extend(prompt.to_messages())
                return {
                    "parsed": plan,
                    "parsing_error": None,
                    "raw": AIMessage(content="{}", response_metadata={"finish_reason": "stop"}),
                }
            return RunnableLambda(invoke)

    factory = lambda **kwargs: Model()
    if provider == "groq":
        gateway = GroqGateway(Settings("dsn", "password", "test-key"), factory)
    elif provider == "ollama":
        gateway = OllamaGateway("http://localhost", "test-model", 30, 1024, factory)
    else:
        gateway = VllmGateway("http://localhost/v1", "test-model", "test-key", 30, 1024, factory)

    assert gateway.plan("cards", {}, [], "auto", base_date=base_date) == plan
    payload = json.loads(messages[-1].content.removeprefix("<request>").removesuffix("</request>"))
    assert payload["base_date"] == base_date.isoformat()
    assert payload["question"] == "cards"
    assert payload["mode"] == "auto"
