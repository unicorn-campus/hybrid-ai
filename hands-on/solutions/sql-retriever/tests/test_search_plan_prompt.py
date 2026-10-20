from pathlib import Path

from app.infrastructure.sql_guard import validate_sql


PROMPT = Path(__file__).resolve().parents[1] / "app" / "prompts" / "search_plan.md"
AVERAGE_EXPRESSION = (
    "ROUND(SUM(approved_amount) * 1.0 / NULLIF(SUM(transaction_count), 0), 2)"
)
THREE_MONTH_YEAR_BOUNDARY_SQL = (
    "SELECT month, SUM(approved_amount) AS amount FROM monthly_usage "
    "WHERE month BETWEEN '2025-11' AND '2026-01' "
    "GROUP BY month ORDER BY month LIMIT 100"
)


def test_transaction_average_prompt_uses_guard_compatible_decimal_division():
    prompt = PROMPT.read_text(encoding="utf-8")
    sql = f"SELECT {AVERAGE_EXPRESSION} AS average_approved_amount FROM monthly_usage LIMIT 1"

    assert AVERAGE_EXPRESSION in prompt
    assert "형변환을 추가하지 않음" in prompt
    assert validate_sql(sql) == sql


def test_relative_month_prompt_defines_base_date_and_calendar_month_rules():
    prompt = PROMPT.read_text(encoding="utf-8")

    assert "기준일(base_date, YYYY-MM-DD)" in prompt
    assert "상대 기간은 시스템 시각이 아니라 base_date를 기준으로 계산함" in prompt
    assert "최근 N개월은 base_date가 속한 달을 포함" in prompt
    assert "지난달은 base_date가 속한 달의 바로 이전 달" in prompt
    assert "month는 YYYY-MM 문자열" in prompt
    assert "base_date가 월중이면 이번 달 자료" in prompt
    assert "NL2SQL에서 상대 기간을 지정할 때 LIMIT으로 기간을 선택하지 않음" in prompt
    assert "상대 기간은 반드시 WHERE로 제한함" in prompt


def test_three_month_range_across_year_boundary_is_guard_compatible():
    assert validate_sql(THREE_MONTH_YEAR_BOUNDARY_SQL) == THREE_MONTH_YEAR_BOUNDARY_SQL
