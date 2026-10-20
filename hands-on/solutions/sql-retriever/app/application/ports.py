"""응용 계층이 사용하는 저장소·모델·SQL 검사 계약."""
from datetime import date
from typing import Protocol

from .models import QueryPlan


class RepositoryPort(Protocol):
    def retrieve_customer_snapshot(self, member_id: str, base_date: date) -> dict: ...
    def search(self, member_id: str, base_date: date, validated_sql: str) -> dict: ...


class LanguageModelPort(Protocol):
    def plan(self, question: str, schema: dict, catalog: list[dict], mode: str,
             *, base_date: date) -> QueryPlan: ...
    def explain(self, question: str, context: dict) -> str: ...
