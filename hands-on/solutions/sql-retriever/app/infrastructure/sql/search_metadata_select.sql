SELECT
    EXISTS (
        SELECT 1
        FROM app.customer_cards
        WHERE is_product_effective_on_base_date = false
    ) AS has_future_product,
    (SELECT max(as_of_date) FROM app.customer_delinquency) AS delinquency_as_of_date
