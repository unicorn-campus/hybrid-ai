SELECT card_ref, month, period_start, period_end, approved_amount, transaction_count
FROM app.monthly_usage
ORDER BY month, card_ref
