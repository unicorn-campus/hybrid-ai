-- 기존 카드×월 집계를 바꾸지 않고 가맹점·업종별 승인 사용액을 제공함.
-- 신규 DB 초기화 때 04_views_rls.sql 다음에 실행하며, 기존 DB에도 재실행 가능함.
GRANT SELECT ON public.merchant TO app_reader;

CREATE OR REPLACE VIEW app.merchant_usage WITH (security_barrier = true) AS
SELECT
    cards.card_ref,
    to_char(date_trunc('month', txn.txn_date), 'YYYY-MM') AS month,
    greatest(date_trunc('month', txn.txn_date)::date, cards.issue_date) AS period_start,
    least(
        (date_trunc('month', txn.txn_date) + INTERVAL '1 month - 1 day')::date,
        scope.base_date
    ) AS period_end,
    merchant.merchant_name,
    merchant.category,
    min(txn.txn_date) AS first_approved_date,
    max(txn.txn_date) AS last_approved_date,
    sum(txn.amount)::bigint AS approved_amount,
    count(*)::integer AS transaction_count
FROM app_internal.customer_cards_full AS cards
CROSS JOIN app_internal.request_scope AS scope
JOIN public.card_txn AS txn
  ON txn.card_id = cards.card_id
 AND txn.approval_code = 'APPROVED'
 AND txn.txn_date >= greatest(
     date_trunc('month', scope.base_date)::date - INTERVAL '5 months',
     scope.coverage_start,
     cards.issue_date
 )
 AND txn.txn_date <= scope.base_date
JOIN public.merchant AS merchant
  ON merchant.merchant_id = txn.merchant_id
GROUP BY
    cards.card_ref,
    date_trunc('month', txn.txn_date),
    cards.issue_date,
    scope.base_date,
    merchant.merchant_id,
    merchant.merchant_name,
    merchant.category;

ALTER VIEW app.merchant_usage OWNER TO app_reader;
GRANT SELECT ON app.merchant_usage TO sql_retriever_user;
