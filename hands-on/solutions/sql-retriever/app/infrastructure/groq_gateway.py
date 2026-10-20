"""Groq의 계획 생성과 선택적 설명을 LangChain으로 호출합니다."""
import json
from datetime import date

from langchain_groq import ChatGroq
from langsmith import tracing_context

from app.application.models import QueryPlan, SearchError
from .prompt_loader import explain_prompt, plan_prompt
from .settings import Settings


class GroqGateway:
    def __init__(self, settings: Settings, model_factory=ChatGroq):
        self.settings, self.model_factory = settings, model_factory

    def _model(self):
        if not self.settings.api_key:
            raise SearchError("missing_groq_key", "secrets/.env의 GROQ_API_KEY를 설정해 주세요.", 503)
        return self.model_factory(
            model=self.settings.model, api_key=self.settings.api_key,
            temperature=0, reasoning_effort="low", model_kwargs={"include_reasoning": False},
            timeout=self.settings.llm_timeout_seconds, max_tokens=self.settings.max_tokens,
            max_retries=1,
        )

    def plan(self, question: str, schema: dict, catalog: list[dict], mode: str,
             *, base_date: date) -> QueryPlan:
        prompt = plan_prompt()
        payload = json.dumps({"question": question, "mode": mode, "schema": schema,
                              "fixed_queries": catalog,
                              "base_date": base_date.isoformat()}, ensure_ascii=False)
        try:
            model = self._model().with_structured_output(
                QueryPlan, method="json_schema", include_raw=True, strict=True)
            
            # LCEL 체인 수행. prompt 객체의 human 메시지 변수인 'request' 치환 
            with tracing_context(enabled=False):
                result = (prompt | model).invoke({"request": payload})
                
            if result.get("parsing_error") is not None or result.get("parsed") is None:
                raise ValueError("Invalid structured output")
            raw = result.get("raw")
            if raw is not None and raw.response_metadata.get("finish_reason") not in (None, "stop"):
                raise ValueError("Incomplete model response")
            return QueryPlan.model_validate(result["parsed"])
        except SearchError:
            raise
        except Exception as error:
            raise SearchError("planning_failed", "Groq 검색 계획 생성에 실패했습니다. 연결·모델 응답을 확인해 주세요.", 502) from error

    def explain(self, question: str, context: dict) -> str:
        prompt = explain_prompt()
        payload = json.dumps({"question": question, "context": context}, ensure_ascii=False, default=str)
        if len(payload) > 50000:
            raise SearchError("explanation_too_large", "확인용 설명의 입력 크기를 초과했습니다.", 422)
        with tracing_context(enabled=False):
            result = (prompt | self._model()).invoke({"payload": payload})
        if not isinstance(result.content, str) or not result.content.strip():
            raise ValueError("Empty explanation")
        if result.response_metadata.get("finish_reason") not in (None, "stop"):
            raise ValueError("Incomplete explanation")
        return result.content.strip()
