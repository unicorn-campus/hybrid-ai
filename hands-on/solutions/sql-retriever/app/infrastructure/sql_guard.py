"""NL2SQL 결과를 제한된 논리 읽기 모델에만 허용합니다."""

from __future__ import annotations

from collections.abc import Mapping

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from .queries import LOGICAL_SCHEMA

_MAX_ROWS = 100
_MAX_SQL_LENGTH = 20_000
_ALLOWED_FUNCTIONS = {"SUM", "COUNT", "AVG", "MIN", "MAX", "ROUND", "COALESCE", "NULLIF", "ABS"}

# 허용할 문법을 나열함. 목록에 없는 PostgreSQL 확장 구문은 기본 거부됨.
_ALLOWED_NODE_TYPES = (
    exp.Select,
    exp.From,
    exp.Join,
    exp.Table,
    exp.TableAlias,
    exp.Column,
    exp.Identifier,
    exp.Alias,
    exp.Distinct,
    exp.Where,
    exp.Group,
    exp.Having,
    exp.Order,
    exp.Ordered,
    exp.Limit,
    exp.Literal,
    exp.Null,
    exp.Boolean,
    exp.Paren,
    exp.And,
    exp.Or,
    exp.Not,
    exp.EQ,
    exp.NEQ,
    exp.GT,
    exp.GTE,
    exp.LT,
    exp.LTE,
    exp.Is,
    exp.NullSafeEQ,
    exp.Between,
    exp.In,
    exp.Like,
    exp.ILike,
    exp.Add,
    exp.Sub,
    exp.Mul,
    exp.Div,
    exp.Mod,
    exp.Neg,
    exp.Func,
    exp.Star,
)


class SqlValidationError(ValueError):
    """실행 가능한 범위를 벗어난 SQL을 나타냅니다."""


def _fail(message: str) -> None:
    # 파싱 대상 SQL과 DB 식별자는 오류 메시지에 포함하지 않음.
    raise SqlValidationError(message)


def _normalize(value: str) -> str:
    return value.lower()


def _has_ancestor(node: exp.Expression, *types: type[exp.Expression]) -> bool:
    parent = node.parent
    while parent is not None:
        if isinstance(parent, types):
            return True
        parent = parent.parent
    return False


def _validate_tables(statement: exp.Select) -> tuple[dict[str, str], tuple[str, ...]]:
    references: dict[str, str] = {}
    selected_tables: list[str] = []

    for table in statement.find_all(exp.Table):
        if table.args.get("db") is not None or table.args.get("catalog") is not None:
            _fail("스키마 또는 카탈로그를 지정한 테이블은 조회할 수 없습니다.")
        if not isinstance(table.this, exp.Identifier):
            _fail("테이블 함수와 동적 테이블은 조회할 수 없습니다.")

        table_name = _normalize(table.name)
        if table_name not in LOGICAL_SCHEMA:
            _fail("허용되지 않은 테이블입니다.")

        alias_expression = table.args.get("alias")
        if alias_expression is not None and alias_expression.args.get("columns"):
            _fail("테이블 컬럼 별칭 목록은 사용할 수 없습니다.")
        reference = _normalize(table.alias_or_name)
        previous = references.get(reference)
        if previous is not None and previous != table_name:
            _fail("중복된 테이블 별칭은 사용할 수 없습니다.")

        references[reference] = table_name
        if not table.alias:
            references[table_name] = table_name
        selected_tables.append(table_name)

    if not selected_tables:
        _fail("논리 테이블을 하나 이상 조회해야 합니다.")
    return references, tuple(selected_tables)


def _validate_columns(
    statement: exp.Select,
    references: Mapping[str, str],
    selected_tables: tuple[str, ...],
) -> None:
    output_aliases = {
        _normalize(projection.alias)
        for projection in statement.expressions
        if isinstance(projection, exp.Alias) and projection.alias
    }

    for column in statement.find_all(exp.Column):
        if column.args.get("db") is not None or column.args.get("catalog") is not None:
            _fail("스키마 또는 카탈로그를 지정한 컬럼은 조회할 수 없습니다.")

        column_name = _normalize(column.name)
        qualifier = _normalize(column.table) if column.table else ""
        if qualifier:
            table_name = references.get(qualifier)
            if table_name is None or column_name not in LOGICAL_SCHEMA[table_name]:
                _fail("허용되지 않은 컬럼입니다.")
            continue

        if column_name in output_aliases and _has_ancestor(column, exp.Order, exp.Group):
            continue

        matching_tables = {
            table_name for table_name in selected_tables if column_name in LOGICAL_SCHEMA[table_name]
        }
        if not matching_tables:
            _fail("허용되지 않은 컬럼입니다.")
        if len(matching_tables) > 1:
            _fail("여러 테이블에 있는 컬럼은 테이블 별칭으로 구분해야 합니다.")


def _validate_functions(statement: exp.Select) -> None:
    for function in statement.find_all(exp.Func):
        # sqlglot은 AND/OR 연산자도 Func 하위 타입으로 표현합니다.
        # 구문 허용 목록에서 별도로 검사하므로 함수 이름 검사는 건너뜁니다.
        if isinstance(function, (exp.And, exp.Or)):
            continue
        if function.sql_name().upper() not in _ALLOWED_FUNCTIONS:
            _fail("허용되지 않은 함수입니다.")


def _validate_stars(statement: exp.Select) -> None:
    for star in statement.find_all(exp.Star):
        if not isinstance(star.parent, exp.Count) or star.parent.this is not star:
            _fail("별표 조회는 COUNT(*)에서만 사용할 수 있습니다.")


def _validate_syntax(statement: exp.Select) -> None:
    if statement.args.get("with_") is not None:
        _fail("WITH 절은 사용할 수 없습니다.")
    if statement.args.get("into") is not None:
        _fail("SELECT INTO는 사용할 수 없습니다.")
    if statement.args.get("locks"):
        _fail("행 잠금 조회는 사용할 수 없습니다.")
    if statement.args.get("offset") is not None:
        _fail("OFFSET은 사용할 수 없습니다.")

    for join in statement.find_all(exp.Join):
        if join.args.get("using"):
            _fail("JOIN은 허용 컬럼을 명시한 ON 조건으로 작성해야 합니다.")
        if str(join.args.get("method") or "").upper() == "NATURAL":
            _fail("NATURAL JOIN은 사용할 수 없습니다.")

    for node in statement.walk():
        if not isinstance(node, _ALLOWED_NODE_TYPES):
            _fail("지원하지 않는 SQL 구문입니다.")


def _apply_limit(statement: exp.Select) -> exp.Select:
    limit = statement.args.get("limit")
    if limit is not None:
        expression = limit.expression
        if not isinstance(expression, exp.Literal) or expression.is_string:
            _fail("LIMIT은 0부터 100 사이의 정수여야 합니다.")
        try:
            value = int(expression.this)
        except (TypeError, ValueError):
            _fail("LIMIT은 0부터 100 사이의 정수여야 합니다.")
        if value < 0:
            _fail("LIMIT은 0부터 100 사이의 정수여야 합니다.")
        if value > _MAX_ROWS:
            statement.set("limit", exp.Limit(expression=exp.Literal.number(_MAX_ROWS)))
    else:
        statement.set("limit", exp.Limit(expression=exp.Literal.number(_MAX_ROWS)))
    return statement


def validate_sql(sql: str) -> str:
    """한 개의 안전한 PostgreSQL SELECT를 정규화하고 최대 100행으로 제한합니다."""
    if not isinstance(sql, str) or not sql.strip():
        _fail("SQL이 비어 있습니다.")
    if len(sql) > _MAX_SQL_LENGTH:
        _fail("SQL이 허용된 길이를 초과했습니다.")

    try:
        statements = [statement for statement in sqlglot.parse(sql, read="postgres") if statement is not None]
    except (ParseError, ValueError, RecursionError):
        _fail("SQL을 해석할 수 없습니다.")

    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        _fail("한 개의 SELECT 문만 사용할 수 있습니다.")

    statement = statements[0]
    if statement.find(exp.Subquery) is not None or statement.find(exp.With) is not None:
        _fail("WITH 절과 하위 SELECT는 사용할 수 없습니다.")
    if any(select is not statement for select in statement.find_all(exp.Select)):
        _fail("하위 SELECT는 사용할 수 없습니다.")

    _validate_syntax(statement)
    references, selected_tables = _validate_tables(statement)
    _validate_columns(statement, references, selected_tables)
    _validate_functions(statement)
    _validate_stars(statement)
    statement = _apply_limit(statement)
    for node in statement.walk():
        node.comments = None
    return statement.sql(dialect="postgres")
