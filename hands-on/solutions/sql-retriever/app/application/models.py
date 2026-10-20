"""CLI와 API가 공유하는 요청·응답 및 검색 계획 계약."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

QueryMode = Literal["auto", "fixed", "nl2sql"]
QueryId = Literal["customer_snapshot", "cards", "monthly_usage", "delinquency"]


class SearchError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query_mode: QueryMode = "auto"
    member_id: str = Field(pattern=r"^M-[0-9]{1,20}$", max_length=22)
    base_date: date
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    query_id: QueryId | None = None
    explain: bool = False

    @field_validator("base_date", mode="before")
    @classmethod
    def iso_date_only(cls, value):
        if isinstance(value, str):
            if len(value) != 10:
                raise ValueError("기준일은 YYYY-MM-DD 형식이어야 합니다.")
            try:
                return date.fromisoformat(value)
            except ValueError as error:
                raise ValueError("유효한 YYYY-MM-DD 날짜가 필요합니다.") from error
        if type(value) is not date:
            raise ValueError("기준일은 날짜여야 합니다.")
        return value

    @model_validator(mode="after")
    def consistent_mode(self):
        if self.query_mode != "fixed" and not self.question:
            raise ValueError("auto와 nl2sql 모드에는 question이 필요합니다.")
        if self.query_mode != "fixed" and self.query_id is not None:
            raise ValueError("query_id는 fixed 모드에서만 지정합니다.")
        return self


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query_mode: Literal["fixed", "nl2sql", "unsupported"] = Field(
        description=("질문 전체를 고정 조회가 그대로 충족하면 fixed, 추가 필터·집계·정렬이 필요하면 "
                     "nl2sql, 제공 데이터로 알 수 없으면 unsupported"),
    )
    query_id: QueryId | None = Field(
        description="fixed에서만 사용할 고정 조회 ID. nl2sql과 unsupported에서는 null",
    )
    sql: str | None = Field(
        max_length=10000,
        description=("nl2sql에서만 사용할 SELECT. 개별 customer_cards 행을 반환하면 card_ref를 포함하고, "
                     "집계 결과에는 불필요한 card_ref를 포함하지 않음"),
    )
    reason: str = Field(min_length=1, max_length=1000, description="계획을 선택한 이유를 설명하는 짧은 한국어")

    # QueryPlan 모델 검사 수행 데코레이트: mode가 'after'이므로 QueryPlan 객체 생성 후 valid_plan 수행 
    # 상위 클래스인 BaseModel에 의해 프라퍼티의 자료형 검사(51~63라인)이 자동 수행 -> 
    # QueryPlan 생성 -> valid_plan함수 수행 
    @model_validator(mode="after")
    def valid_plan(self):
        if self.query_mode == "fixed" and (self.query_id is None or self.sql is not None):
            raise ValueError("고정 계획에는 query_id만 있어야 합니다.")
        if self.query_mode == "nl2sql" and (not self.sql or self.query_id is not None):
            raise ValueError("NL2SQL 계획에는 sql만 있어야 합니다.")
        if self.query_mode == "unsupported" and (self.sql is not None or self.query_id is not None):
            raise ValueError("미지원 계획에는 실행할 조회가 없어야 합니다.")
        return self


class SearchResponse(BaseModel):
    query_mode: Literal["fixed", "nl2sql"]
    requested_query_mode: QueryMode = "auto"
    query_id: QueryId | None = None
    routing_reason: str = ""
    member_id: str
    base_date: date
    data: dict
    explanation: str | None = None
    explanation_status: Literal["not_requested", "completed", "failed"] = "not_requested"
    warnings: list[str] = Field(default_factory=list)
