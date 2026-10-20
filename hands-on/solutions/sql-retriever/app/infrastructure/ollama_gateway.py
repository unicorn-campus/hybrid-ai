"""Ollama의 로컬 모델로 검색 계획과 선택적 설명을 생성합니다."""

import json
from datetime import date
from typing import Any, Callable

from langchain_ollama import ChatOllama
from langsmith import tracing_context

from app.application.models import QueryPlan, SearchError
from .prompt_loader import explain_prompt, plan_prompt


class OllamaGateway:
    """기존 언어 모델 포트 계약을 Ollama의 Chat API에 연결합니다."""

    def __init__(
        self,
        endpoint: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        model_factory: Callable[..., Any] = ChatOllama,
        structured_methods: tuple[str, ...] = ("json_schema", "function_calling", "json_mode"),
    ):
        self.endpoint = endpoint
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.model_factory = model_factory
        self.structured_methods = structured_methods
        self._structured_method: str | None = None
        self.structured_output_attempts = 0
        self.structured_output_fallback_calls = 0

    def _model(self):
        return self.model_factory(
            model=self.model,
            base_url=self.endpoint,
            temperature=0,
            reasoning=False,
            num_ctx=4096,
            num_predict=self.max_tokens,
            client_kwargs={"timeout": self.timeout_seconds},
        )

    @staticmethod
    def _validate_complete_response(raw: Any) -> None:
        if raw is None:
            raise ValueError("Missing model response")

        content = getattr(raw, "content", None)
        tool_calls = getattr(raw, "tool_calls", None)
        if isinstance(content, str):
            if not content.strip() and not tool_calls:
                raise ValueError("Empty model response")
        elif not content and not tool_calls:
            raise ValueError("Empty model response")

        metadata = getattr(raw, "response_metadata", {}) or {}
        finish_reason = metadata.get("done_reason", metadata.get("finish_reason"))
        if finish_reason not in (None, "stop") or metadata.get("done") is False:
            raise ValueError("Incomplete model response")

    def plan(self, question: str, schema: dict, catalog: list[dict], mode: str,
             *, base_date: date) -> QueryPlan:
        prompt = plan_prompt()
        payload = json.dumps(
            {
                "question": question,
                "mode": mode,
                "base_date": base_date.isoformat(),
                "schema": schema,
                "fixed_queries": catalog,
            },
            ensure_ascii=False,
        )

        try:
            methods = list(self.structured_methods)
            if self._structured_method:
                methods = [self._structured_method] + [
                    method for method in methods if method != self._structured_method
                ]
            last_error: Exception | None = None
            attempts = 0
            for method in methods:
                try:
                    attempts += 1
                    self.structured_output_attempts += 1
                    model = self._model().with_structured_output(
                        QueryPlan,
                        method=method,
                        include_raw=True,
                    )
                    with tracing_context(enabled=False):
                        result = (prompt | model).invoke({"request": payload})
                    if result.get("parsing_error") is not None or result.get("parsed") is None:
                        raise ValueError("Invalid structured output")
                    self._validate_complete_response(result.get("raw"))
                    plan = QueryPlan.model_validate(result["parsed"])
                    self._structured_method = method
                    if attempts > 1:
                        self.structured_output_fallback_calls += 1
                    return plan
                except Exception as error:
                    last_error = error
            raise ValueError("No supported structured output method") from last_error
        except SearchError:
            raise
        except Exception as error:
            raise SearchError(
                "planning_failed",
                "로컬 모델의 검색 계획 생성에 실패했습니다. Ollama 연결과 모델 응답을 확인해 주세요.",
                502,
            ) from error

    def explain(self, question: str, context: dict) -> str:
        prompt = explain_prompt()
        payload = json.dumps(
            {"question": question, "context": context},
            ensure_ascii=False,
            default=str,
        )
        if len(payload) > 50000:
            raise SearchError(
                "explanation_too_large",
                "확인용 설명의 입력 크기를 초과했습니다.",
                422,
            )

        try:
            with tracing_context(enabled=False):
                result = (prompt | self._model()).invoke({"payload": payload})
            self._validate_complete_response(result)
            return result.content.strip()
        except SearchError:
            raise
        except Exception as error:
            raise SearchError(
                "explanation_failed",
                "로컬 모델의 결과 설명 생성에 실패했습니다. Ollama 연결과 모델 응답을 확인해 주세요.",
                502,
            ) from error
