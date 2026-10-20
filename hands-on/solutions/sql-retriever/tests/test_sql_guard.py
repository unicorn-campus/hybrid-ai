import pytest

from app.domain.catalog import FIXED_QUERIES
from app.infrastructure.sql_guard import LOGICAL_SCHEMA, SqlValidationError, validate_sql


@pytest.mark.parametrize("query_id", ["cards", "monthly_usage", "delinquency"])
def test_fixed_catalog_queries_are_allowed(query_id):
    result = validate_sql(FIXED_QUERIES[query_id]["sql"])
    assert result.endswith("LIMIT 100")


def test_schema_contract_contains_only_logical_read_models():
    assert set(LOGICAL_SCHEMA) == {
        "customer_profile", "customer_cards", "monthly_usage", "merchant_usage",
        "customer_daily_usage", "customer_delinquency", "customer_delinquency_history"
    }
    assert "member_id" not in {column for columns in LOGICAL_SCHEMA.values() for column in columns}


def test_aggregate_query_is_normalized_and_limited():
    result = validate_sql(
        "SELECT month, SUM(approved_amount) AS amount "
        "FROM monthly_usage GROUP BY month ORDER BY amount"
    )
    assert "SUM(approved_amount) AS amount" in result
    assert result.endswith("LIMIT 100")


def test_merchant_category_aggregate_is_allowed_without_transaction_details():
    sql = (
        "SELECT category, SUM(approved_amount) AS amount, "
        "SUM(transaction_count) AS approved_count FROM merchant_usage "
        "WHERE month BETWEEN '2026-06' AND '2026-08' "
        "GROUP BY category ORDER BY amount DESC LIMIT 100"
    )
    assert validate_sql(sql) == sql
    for hidden in ("member_id", "card_id", "merchant_id", "txn_id", "txn_date"):
        assert hidden not in LOGICAL_SCHEMA["merchant_usage"]


def test_date_bounds_with_boolean_operators_are_allowed():
    sql = (
        "SELECT category, SUM(approved_amount) AS amount FROM merchant_usage "
        "WHERE month >= '2026-06' AND month <= '2026-08' "
        "GROUP BY category ORDER BY amount DESC LIMIT 1"
    )
    assert validate_sql(sql) == sql
    alternatives = (
        "SELECT merchant_name FROM merchant_usage "
        "WHERE category = '교통' OR category = '교육' LIMIT 100"
    )
    assert validate_sql(alternatives) == alternatives


def test_daily_usage_and_delinquency_history_support_bounded_selects():
    daily = (
        "SELECT usage_date, approved_amount, transaction_count FROM customer_daily_usage "
        "WHERE usage_date BETWEEN '2026-08-25' AND '2026-08-31' ORDER BY usage_date LIMIT 100"
    )
    history = (
        "SELECT base_month, overdue_amount, overdue_days FROM customer_delinquency_history "
        "ORDER BY base_month LIMIT 100"
    )
    assert validate_sql(daily) == daily
    assert validate_sql(history) == history


def test_existing_limit_is_preserved_or_capped():
    assert validate_sql("SELECT card_ref FROM customer_cards LIMIT 7").endswith("LIMIT 7")
    assert validate_sql("SELECT card_ref FROM customer_cards LIMIT 500").endswith("LIMIT 100")


def test_allowed_join_requires_unambiguous_columns():
    result = validate_sql(
        "SELECT c.card_ref, SUM(u.approved_amount) AS amount "
        "FROM customer_cards AS c JOIN monthly_usage AS u ON c.card_ref = u.card_ref "
        "GROUP BY c.card_ref"
    )
    assert "JOIN monthly_usage AS u ON c.card_ref = u.card_ref" in result


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) FROM customer_cards",
        "SELECT COUNT(DISTINCT card_ref) AS card_count FROM customer_cards",
        "SELECT COALESCE(annual_fee, 0) AS annual_fee FROM customer_cards",
        "SELECT card_ref FROM customer_cards WHERE current_status = 'ACTIVE'",
        "SELECT month, AVG(approved_amount) FROM monthly_usage GROUP BY month",
    ],
)
def test_supported_select_forms(sql):
    assert validate_sql(sql).endswith("LIMIT 100")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM customer_cards",
        "UPDATE customer_cards SET current_status = 'CLOSED'",
        "DROP TABLE customer_cards",
        "SELECT card_ref FROM customer_cards; DELETE FROM customer_cards",
        "SELECT card_ref INTO copied_cards FROM customer_cards",
        "SELECT card_ref FROM customer_cards FOR UPDATE",
        "WITH cards AS (SELECT card_ref FROM customer_cards) SELECT card_ref FROM cards",
        "SELECT card_ref FROM customer_cards UNION SELECT card_ref FROM monthly_usage",
        "SELECT card_ref FROM customer_cards WHERE card_ref IN (SELECT card_ref FROM monthly_usage)",
    ],
)
def test_writes_multiple_statements_and_query_composition_are_rejected(sql):
    with pytest.raises(SqlValidationError):
        validate_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT card_id FROM cards",
        "SELECT card_ref FROM public.customer_cards",
        "SELECT card_ref FROM pg_catalog.pg_tables",
        "SELECT customer_cards.unknown_column FROM customer_cards",
        "SELECT member_id FROM customer_cards",
        "SELECT c.card_ref FROM customer_cards AS cards",
        "SELECT card_ref FROM customer_cards JOIN monthly_usage ON true",
    ],
)
def test_external_tables_schema_access_and_unknown_columns_are_rejected(sql):
    with pytest.raises(SqlValidationError):
        validate_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM customer_cards",
        "SELECT COUNT(customer_cards.*) FROM customer_cards",
        "SELECT pg_sleep(1) FROM customer_cards",
        "SELECT current_setting('application_name') FROM customer_cards",
        "SELECT card_ref::text FROM customer_cards",
        "SELECT card_ref FROM customer_cards OFFSET 1",
        "SELECT card_ref FROM customer_cards LIMIT -1",
        "SELECT card_ref FROM customer_cards LIMIT $1",
        "SELECT card_ref FROM customer_cards JOIN monthly_usage USING (card_ref)",
    ],
)
def test_wildcards_functions_cast_parameters_and_dynamic_limits_are_rejected(sql):
    with pytest.raises(SqlValidationError):
        validate_sql(sql)


def test_string_literals_are_safely_serialized():
    result = validate_sql("SELECT card_ref FROM customer_cards WHERE product_name = 'Kim''s Card'")
    assert "'Kim''s Card'" in result
    assert result.endswith("LIMIT 100")


def test_untrusted_comments_are_removed_from_executable_sql():
    result = validate_sql("SELECT card_ref /* model note */ FROM customer_cards -- trailing note")
    assert "note" not in result
    assert result.endswith("LIMIT 100")


def test_parse_error_does_not_echo_sql_or_identifier():
    secret = "SENSITIVE_MEMBER_1024"
    with pytest.raises(SqlValidationError) as failure:
        validate_sql(f"SELECT {secret} FROM")
    assert secret not in str(failure.value)
