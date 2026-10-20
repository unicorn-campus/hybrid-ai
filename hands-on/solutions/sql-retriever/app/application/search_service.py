"""검색 계획 → 검증된 조회 → 선택적 설명을 연결합니다."""
from collections.abc import Callable

from langsmith import tracing_context

from app.domain.catalog import FIXED_QUERIES, query_catalog
from app.domain.privacy import redact_text, safe_context
from .models import QueryPlan, SearchError, SearchRequest, SearchResponse
from .ports import LanguageModelPort, RepositoryPort


class SearchService:
    def __init__(self, repository: RepositoryPort, llm: LanguageModelPort,
                 sql_validator: Callable[[str], str], logical_schema: dict):
        self.repository, self.llm = repository, llm
        self.sql_validator, self.logical_schema = sql_validator, logical_schema

    def schema(self) -> dict:
        return {
            "query_modes": ["auto", "fixed", "nl2sql"],
            "default_query_mode": "auto",
            "fixed_queries": query_catalog(),
            "tables": self.logical_schema,
            "rules": [
                "테이블은 요청 회원과 기준일로 제한된 논리 읽기 모델입니다.",
                "승인 금액은 원 단위이며 취소 거래를 제외합니다. monthly_usage는 최근 6개월 카드별 월 집계입니다.",
                "merchant_usage는 최근 6개월 카드·월·가맹점별 승인 거래 집계이며 가맹점명과 업종을 제공합니다.",
                "customer_daily_usage는 최근 90일의 회원별 일 승인액·건수이며 무거래일도 0으로 표시합니다.",
                "customer_delinquency_history는 기준일 이전 완료된 최근 12개월의 월별 연체 이력입니다.",
                "회원ID와 원본 카드ID는 SQL 조건에 넣지 않습니다. card_ref는 요청 내 대체 식별자입니다.",
                "월별 연체는 기준일 이전 완료된 월만 조회합니다. 현재 카드 상태의 과거 이력은 없습니다.",
                "SELECT 한 개, 허용 컬럼, 최대 100행만 지원합니다. 세부 거래·문서·상담 이력·이탈 확률은 없습니다.",
            ],
        }

    def execute(self, request: SearchRequest) -> SearchResponse:
        if not isinstance(request, SearchRequest):
            request = SearchRequest.model_validate(request)
            
        # 목적: 실습의 원본 식별자와 검색 결과가 외부 tracing으로 전송되는 것을 방지합니다.
        # 방법: 이 검색 흐름에서는 환경 설정과 관계없이 LangSmith tracing을 비활성화합니다.
        # tracing_context는 아래 langsmith에서 import한 함수로서 'enabled=False'로 하면 추적이 비활성화됨 
        # from langsmith import tracing_context
        with tracing_context(enabled=False):
            try:
                planned = self._plan(request)
                retrieved = self._retrieve(planned)
                return self._explain(retrieved)
            except SearchError:
                raise
            except ValueError as error:
                raise SearchError("invalid_search", "회원·기준일 또는 조회 조건을 확인해 주세요.", 422) from error
            except Exception as error:
                raise SearchError("search_unavailable", "정형 데이터 검색에 실패했습니다. DB 연결과 설정을 확인해 주세요.", 503) from error

    def _plan(self, request: SearchRequest) -> tuple[SearchRequest, QueryPlan]:
        if request.query_mode == "fixed":
            # QueryPlan 객체 plan 생성. 아직 query_id에 해당하는 sql이 셋팅되지는 않음 
            plan = QueryPlan(query_mode="fixed", query_id=request.query_id or "customer_snapshot",
                             sql=None, reason="호출자가 지정한 고정 조회를 실행합니다.")
        else:

            # question에서 member_id, 다른 ID 식별자, 대체 카드번호, 이메일, 주민번호 앞7자리, 전화번호, 카드번호 제거  
            question = redact_text(request.question or "", (request.member_id,))
            
            # LLM에 QueryPlan 스키마에 맞춰 결과 리턴 요청 
            # query_mode(fixed 또는 nl2sql), query_id(nl2sql일땐 null), sql(fixed일땐 null), reason(판단 이유)을 
            plan = self.llm.plan(
                question, self.logical_schema, query_catalog(), request.query_mode,
                base_date=request.base_date)
            
            if plan.query_mode == "unsupported":
                raise SearchError("unsupported_question", "질문에 필요한 데이터나 조회 형태를 지원하지 않습니다.", 422)
            if request.query_mode == "nl2sql" and plan.query_mode != "nl2sql":
                raise SearchError("invalid_plan", "모델이 요청한 검색 방식에 맞는 계획을 반환하지 않았습니다.", 502)
        return request, plan

    def _retrieve(self, state: tuple[SearchRequest, QueryPlan]) -> tuple[SearchRequest, SearchResponse]:
        """검색 계획에 따라 고객의 정형 데이터를 조회합니다.

        목적: 확정된 고정 조회 또는 NL2SQL 계획으로 요청 회원의 데이터를 안전하게 확보합니다.
        처리 방법: 고객 현황은 전용 저장소 함수로 조회하고, 나머지 계획은 SQL을 검증한 뒤 실행합니다.
        결과값: 원본 요청과 조회 데이터·검색 방식·경고를 담은 SearchResponse의 튜플을 반환합니다.
        """

        request, plan = state
        
        if plan.query_mode == "fixed" and plan.query_id == "customer_snapshot":
            data = self.repository.retrieve_customer_snapshot(
                request.member_id, request.base_date
            )
        else:
            sql = FIXED_QUERIES[plan.query_id]["sql"] if plan.query_mode == "fixed" else plan.sql
            try:
                validated_sql = self.sql_validator(sql or "")
            except ValueError as error:
                raise SearchError("unsafe_sql", "생성된 SQL이 허용된 조회 규칙을 충족하지 않아 실행하지 않았습니다.", 422) from error
            data = self.repository.search(request.member_id, request.base_date, validated_sql)
        response = SearchResponse(
            query_mode=plan.query_mode, requested_query_mode=request.query_mode,
            query_id=plan.query_id, routing_reason=redact_text(plan.reason, (request.member_id,)),
            member_id=request.member_id, base_date=request.base_date, data=data,
            warnings=list(data.get("warnings", [])),
        )
        return request, response

    def _explain(self, state: tuple[SearchRequest, SearchResponse]) -> SearchResponse:
        request, response = state
        if request.explain:
            try:
                context = safe_context(response.data, (request.member_id,))
                question = redact_text(request.question or "조회된 고객 현황과 데이터의 한계를 설명해 주세요.",
                                       (request.member_id,))
                response.explanation = self.llm.explain(question, context)
                response.explanation_status = "completed"
            except Exception:
                response.explanation_status = "failed"
                response.warnings.append("검색은 완료했으나 확인용 LLM 설명 생성에 실패했습니다.")
        return response
