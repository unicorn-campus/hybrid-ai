"""PostgreSQL 고객 현황 조회 어댑터."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
import re
from typing import Any, Generator

import psycopg
from psycopg.rows import dict_row
from sqlglot import exp, parse_one

from app.domain.customer import (
    snapshot_warnings,
    usage_window,
    validate_member_id,
    validate_requested_date,
)
from .queries import (
    BASE_DATE_SETTING,
    CARDS_SELECT,
    COVERAGE_START_SETTING,
    DELINQUENCY_SELECT,
    LOGICAL_SCHEMA_NAME,
    LOGICAL_VIEW_SOURCES,
    LOGICAL_VIEWS,
    MEMBER_SELECT,
    MEMBER_SETTING,
    METADATA_SELECT,
    PROFILE_SELECT,
    SCHEMA_COLUMNS_SELECT,
    SEARCH_METADATA_SELECT,
    USAGE_SELECT,
    guarded_query,
)


def _normalize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else str(value)
    return value


class PostgresRepository:
    """읽기 전용·반복 읽기 트랜잭션에서만 정형 데이터를 조회함."""

    def __init__(self, dsn: str, password: str = "", statement_timeout_ms: int = 5000) -> None:
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("PostgreSQL 연결 설정이 필요합니다.")
        if not 100 <= statement_timeout_ms <= 60000:
            raise ValueError("SQL 제한 시간은 100~60000ms 범위여야 합니다.")
        self._dsn = dsn
        self._password = password
        self._statement_timeout_ms = statement_timeout_ms

    @contextmanager
    def _transaction(self) -> Generator[Any, None, None]:
        kwargs: dict[str, Any] = {"row_factory": dict_row, "connect_timeout": 5}
        if self._password:
            kwargs["password"] = self._password
        try:
            with psycopg.connect(self._dsn, **kwargs) as connection:
                with connection.transaction():
                    connection.execute(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                    )
                    # 모델이 만든 SQL은 스키마 없이 논리 테이블 이름만 씀. app만 두어
                    # 원본 테이블 이름이 우연히 풀리지 않게 함.
                    connection.execute("SET LOCAL search_path TO pg_catalog, app")
                    connection.execute(
                        "SELECT set_config('statement_timeout', %s, true)",
                        (str(self._statement_timeout_ms),),
                    )
                    yield connection
        except psycopg.Error as error:
            raise RuntimeError(
                "PostgreSQL 읽기 전용 조회에 실패했습니다. 연결·권한·컨테이너 상태를 확인해 주세요."
            ) from error

    @staticmethod
    def _rows(connection: Any, sql: str, parameters: dict | None = None) -> list[dict]:
        # 빈 dict를 넘기면 psycopg가 SQL 안의 %를 자리표시자로 해석함. None을 그대로 전달함.
        rows = connection.execute(sql, parameters).fetchall()
        return [_normalize(dict(row)) for row in rows]

    @staticmethod
    def _set_scope(connection: Any, name: str, value: str) -> None:
        """이 트랜잭션에만 유효한 세션 변수를 지정함. 커밋·롤백 시 자동으로 풀림."""

        connection.execute("SELECT set_config(%s, %s, true)", (name, value))

    @staticmethod
    def _sources(
        models: set[str],
        data_base_date: date,
        base_date: date,
        coverage_start: date,
        delinquency_basis: str | None,
    ) -> list[dict]:
        """외부 설정의 원본 테이블과 요청별 기준 정보를 결합함."""

        details = {
            "customer_profile": {
                "actual_basis_date": data_base_date.isoformat(),
            },
            "customer_cards": {
                "actual_basis_date": data_base_date.isoformat(),
            },
            "monthly_usage": {
                "actual_basis_date": base_date.isoformat(),
                "coverage_start": coverage_start.isoformat(),
                "filter": "approval_code=APPROVED, 최근 6개월, txn_date<=requested_base_date",
            },
            "merchant_usage": {
                "actual_basis_date": base_date.isoformat(),
                "coverage_start": coverage_start.isoformat(),
                "filter": "approval_code=APPROVED, 최근 6개월, txn_date<=requested_base_date",
            },
            "customer_daily_usage": {
                "actual_basis_date": base_date.isoformat(),
                "coverage_start": coverage_start.isoformat(),
                "filter": "approval_code=APPROVED, 최근 90일, txn_date<=requested_base_date",
            },
            "customer_delinquency": {
                "actual_basis_date": delinquency_basis,
                "status": "available" if delinquency_basis else "unknown",
            },
            "customer_delinquency_history": {
                "actual_basis_date": delinquency_basis,
                "status": "available" if delinquency_basis else "unknown",
                "window": "최근 12개 완료 월",
            },
        }
        missing = models.difference(LOGICAL_VIEW_SOURCES) | models.difference(details)
        if missing:
            raise RuntimeError(f"논리 뷰의 출처 설정을 확인해 주세요: {sorted(missing)}")
        return [
            {
                "name": name,
                "tables": list(LOGICAL_VIEW_SOURCES[name]),
                **details[name],
            }
            for name in LOGICAL_VIEWS
            if name in models
        ]

    @classmethod
    def _request_context(
        cls,
        connection: Any,
        member_id: str,
        base_date: date,
    ) -> tuple[dict, date, date]:
        validate_member_id(member_id)
        if type(base_date) is not date:
            raise ValueError("기준일은 날짜여야 합니다.")
        # 회원 범위를 먼저 열어야 RLS가 아래 회원 조회에 행을 내어 줌.
        cls._set_scope(connection, MEMBER_SETTING, member_id)
        metadata_rows = connection.execute(METADATA_SELECT).fetchall()
        metadata = {row["key"]: row["value"] for row in metadata_rows}
        if "base_date" not in metadata or "txn_period" not in metadata:
            raise RuntimeError("정형 데이터의 기준일 메타데이터를 확인할 수 없습니다.")
        try:
            data_base_date = date.fromisoformat(metadata["base_date"])
            period_match = re.fullmatch(
                r"\s*(\d{4}-\d{2})\s*~\s*(\d{4}-\d{2})\s*",
                metadata["txn_period"],
            )
            if period_match is None:
                raise ValueError
            coverage_start = date.fromisoformat(f"{period_match.group(1)}-01")
        except (TypeError, ValueError) as error:
            raise RuntimeError("정형 데이터의 기준일 메타데이터 형식이 올바르지 않습니다.") from error
        # 회원 조건을 SQL에 넣지 않음. RLS가 세션 범위의 한 회원만 보여 줌.
        member = connection.execute(MEMBER_SELECT).fetchone()
        if member is None:
            raise ValueError("존재하지 않는 회원ID입니다.")
        validate_requested_date(base_date, data_base_date, member["join_date"], coverage_start)
        # 날짜 범위는 검증을 통과한 뒤에 연다. 이 값이 없으면 논리 뷰는 0행을 반환함.
        cls._set_scope(connection, BASE_DATE_SETTING, base_date.isoformat())
        cls._set_scope(connection, COVERAGE_START_SETTING, coverage_start.isoformat())
        return dict(member), data_base_date, coverage_start

    def retrieve_customer_snapshot(self, member_id: str, base_date: date) -> dict:
        """고객 현황 전체 묶음을 조회함.

        목적: 한 회원의 프로필·카드·최근 이용실적·연체 현황을 근거와 함께 제공함.
        방법: 읽기 전용 트랜잭션에서 회원과 기준일 범위를 설정한 뒤 논리 뷰를 각각 조회함.
        반환값: 조회 데이터, 출처, 기준일, 경고와 고객 현황 확보 이벤트를 담은 dict임.
        """

        with self._transaction() as connection:
            member, data_base_date, coverage_start = self._request_context(
                connection, member_id, base_date
            )
            profile_rows = self._rows(connection, PROFILE_SELECT)
            cards = self._rows(connection, CARDS_SELECT)
            usage = self._rows(connection, USAGE_SELECT)
            delinquency_rows = self._rows(connection, DELINQUENCY_SELECT)

        delinquency = delinquency_rows[0] if delinquency_rows else None
        product_future = any(not row["is_product_effective_on_base_date"] for row in cards)
        warnings = snapshot_warnings(base_date, product_future)
        requested_window_start, _ = usage_window(base_date)
        if coverage_start > requested_window_start:
            warnings.append(
                "최근 6개월 전체를 채울 거래 자료가 없어 데이터 제공 시작월부터만 반환합니다."
            )
        if delinquency is None:
            warnings.append("기준일까지 이용 가능한 연체 자료가 없어 연체액은 확인 필요 상태입니다.")

        approved_amount = sum(row["approved_amount"] for row in usage)
        overdue_amount = delinquency["overdue_amount"] if delinquency else None
        delinquency_basis = delinquency["as_of_date"] if delinquency else None
        sources = self._sources(
            {"customer_profile", "customer_cards", "monthly_usage", "customer_delinquency"},
            data_base_date,
            base_date,
            coverage_start,
            delinquency_basis,
        )
        event = {
            "event_id": "E-3",
            "event_name": "고객 현황 확보됨",
            "card_ids": [row["card_id"] for row in cards],
            "product_ids": list(dict.fromkeys(row["product_id"] for row in cards)),
            "approved_amount": approved_amount,
            "approved_amount_period": {
                "start": min((row["period_start"] for row in usage), default=None),
                "end": base_date.isoformat(),
            },
            "overdue_amount": overdue_amount,
            "basis_date": base_date.isoformat(),
            "delinquency_basis_date": delinquency_basis,
            "sources": sources,
        }
        return {
            "member_id": member_id,
            "requested_base_date": base_date.isoformat(),
            "data_base_date": data_base_date.isoformat(),
            "customer_profile": profile_rows[0] if profile_rows else _normalize(member),
            "cards": cards,
            "monthly_usage": usage,
            "delinquency": delinquency,
            "sources": sources,
            "warnings": warnings,
            "event": event,
        }

    def search(self, member_id: str, base_date: date, validated_sql: str) -> dict:
        """검증된 논리 SQL을 회원·기준일 세션 범위 안에서 다시 검사해 실행함."""

        if not isinstance(validated_sql, str) or not validated_sql.strip():
            raise ValueError("실행할 SQL이 필요합니다.")
        # 서비스 계층을 우회한 직접 호출에서도 같은 검사 적용
        from .sql_guard import validate_sql

        checked_sql = validate_sql(validated_sql)
        with self._transaction() as connection:
            _, data_base_date, coverage_start = self._request_context(
                connection, member_id, base_date
            )
            rows = self._rows(connection, guarded_query(checked_sql))
            metadata = self._rows(connection, SEARCH_METADATA_SELECT)[0]
        if len(rows) > 100:
            raise ValueError("조회 결과가 최대 100행을 초과했습니다.")
        referenced_models = {
            table.name.lower()
            for table in parse_one(checked_sql, read="postgres").find_all(exp.Table)
        }
        sources = self._sources(
            referenced_models,
            data_base_date,
            base_date,
            coverage_start,
            metadata["delinquency_as_of_date"],
        )
        warnings = snapshot_warnings(
            base_date,
            "customer_cards" in referenced_models and metadata["has_future_product"],
        )
        if referenced_models.intersection({"monthly_usage", "merchant_usage"}) and coverage_start > usage_window(base_date)[0]:
            warnings.append(
                "최근 6개월 전체를 채울 거래 자료가 없어 데이터 제공 시작월부터만 반환합니다."
            )
        if "customer_daily_usage" in referenced_models and coverage_start > base_date - timedelta(days=89):
            warnings.append("최근 90일 전체를 채울 거래 자료가 없어 데이터 제공 시작일부터만 반환합니다.")
        if (
            referenced_models.intersection({"customer_delinquency", "customer_delinquency_history"})
            and metadata["delinquency_as_of_date"] is None
        ):
            warnings.append("기준일까지 이용 가능한 연체 자료가 없어 연체액은 확인 필요 상태입니다.")
        return {
            "rows": rows,
            "row_count": len(rows),
            "sql": checked_sql,
            "member_id": member_id,
            "requested_base_date": base_date.isoformat(),
            "data_base_date": data_base_date.isoformat(),
            "sources": sources,
            "warnings": warnings,
        }

    def schema(self) -> list[dict]:
        """NL2SQL에 열려 있는 app 스키마 논리 뷰의 컬럼만 반환함."""

        with self._transaction() as connection:
            result = []
            for view in LOGICAL_VIEWS:
                columns = self._rows(
                    connection,
                    SCHEMA_COLUMNS_SELECT,
                    {"schema": LOGICAL_SCHEMA_NAME, "view": view},
                )
                # 행 수는 세지 않음. 논리 뷰는 요청 회원·기준일 범위 안에서만 행이 있어
                # 범위를 열지 않고 센 값은 언제나 0이며 뜻이 없음.
                result.append({"table": view, "columns": columns})
        return result
