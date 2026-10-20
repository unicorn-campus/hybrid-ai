-- 최신 연체 1행과 월별 사용액을 유지하면서 연체 이력과 일별 승인 사용액을 별도 제공함.
-- 신규 DB 초기화 때 05_merchant_usage.sql 다음에 실행하며, 기존 DB에도 재실행 가능함.

CREATE OR REPLACE VIEW app.customer_delinquency_history WITH (security_barrier = true) AS
SELECT
    d.base_month,
    (
        to_date(d.base_month || '-01', 'YYYY-MM-DD')
        + INTERVAL '1 month - 1 day'
    )::date AS as_of_date,
    d.overdue_amount,
    d.overdue_days,
    d.overdue_count_12m
FROM public.delinquency AS d
CROSS JOIN app_internal.request_scope AS scope
CROSS JOIN LATERAL (
    SELECT CASE
        WHEN scope.base_date = (
            date_trunc('month', scope.base_date) + INTERVAL '1 month - 1 day'
        )::date
        THEN date_trunc('month', scope.base_date)::date
        ELSE (date_trunc('month', scope.base_date) - INTERVAL '1 month')::date
    END AS latest_completed_month
) AS boundary
WHERE to_date(d.base_month || '-01', 'YYYY-MM-DD')
      BETWEEN boundary.latest_completed_month - INTERVAL '11 months'
          AND boundary.latest_completed_month;

ALTER VIEW app.customer_delinquency_history OWNER TO app_reader;
GRANT SELECT ON app.customer_delinquency_history TO sql_retriever_user;

CREATE OR REPLACE VIEW app.customer_daily_usage WITH (security_barrier = true) AS
SELECT
    days.usage_date::date AS usage_date,
    coalesce(sum(txn.amount), 0)::bigint AS approved_amount,
    count(txn.txn_id)::integer AS transaction_count
FROM app_internal.request_scope AS scope
JOIN app_internal.member_basic AS member_scope
  ON member_scope.join_date <= scope.base_date
CROSS JOIN LATERAL generate_series(
    greatest(
        scope.base_date - INTERVAL '89 days',
        scope.coverage_start,
        member_scope.join_date
    ),
    scope.base_date,
    INTERVAL '1 day'
) AS days(usage_date)
LEFT JOIN public.card_txn AS txn
  ON txn.txn_date = days.usage_date::date
 AND txn.approval_code = 'APPROVED'
GROUP BY days.usage_date;

ALTER VIEW app.customer_daily_usage OWNER TO app_reader;
GRANT SELECT ON app.customer_daily_usage TO sql_retriever_user;
