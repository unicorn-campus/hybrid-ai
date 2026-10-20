"""vLLM의 OpenAI 호환 API로 검색 계획과 선택적 설명을 생성합니다."""

import json
from datetime import date
from typing import Any, Callable

from langchain_openai import ChatOpenAI
from langsmith import tracing_context

from app.application.models import QueryPlan, SearchError
from .prompt_loader import explain_prompt, plan_prompt


class VllmGateway:
    """기존 언어 모델 포트 계약을 vLLM Chat Completions API에 연결합니다."""

    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: str,
        timeout_seconds: float,
        max_tokens: int,
        model_factory: Callable[..., Any] = ChatOpenAI,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.model_factory = model_factory
        self.runtime = "vllm"
        self._structured_method = "json_schema"

    def _model(self):
        if not self.api_key:
            raise SearchError(
                "missing_vllm_key",
                "secrets/.env의 SQL_RETRIEVER_VLLM_API_KEY를 설정해 주세요.",
                503,
            )
        return self.model_factory(
            model=self.model,
            base_url=self.endpoint,
            api_key=self.api_key,
            temperature=0,
            timeout=self.timeout_seconds,
            max_completion_tokens=self.max_tokens,
            max_retries=0,
        )

    @staticmethod
    def _validate_complete_response(raw: Any) -> None:
        if raw is None:
            raise ValueError("Missing model response")
        metadata = getattr(raw, "response_metadata", {}) or {}
        if metadata.get("finish_reason") not in (None, "stop"):
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
            model = self._model().with_structured_output(
                QueryPlan,
                method="json_schema",
                include_raw=True,
                strict=True,
            )
            with tracing_context(enabled=False):
                result = (prompt | model).invoke({"request": payload})
            if result.get("parsing_error") is not None or result.get("parsed") is None:
                raise ValueError("Invalid structured output")
            self._validate_complete_response(result.get("raw"))
            return QueryPlan.model_validate(result["parsed"])
        except SearchError:
            raise
        except Exception as error:
            raise SearchError(
                "planning_failed",
                "vLLM 검색 계획 생성에 실패했습니다. 연결·인증·모델 응답을 확인해 주세요.",
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
            if not isinstance(result.content, str) or not result.content.strip():
                raise ValueError("Empty model response")
            return result.content.strip()
        except SearchError:
            raise
        except Exception as error:
            raise SearchError(
                "explanation_failed",
                "vLLM 결과 설명 생성에 실패했습니다. 연결·인증·모델 응답을 확인해 주세요.",
                502,
            ) from error
