SELECT
    card_id,
    card_ref,
    product_id,
    product_name,
    brand,
    issue_date,
    current_status,
    product_effective_date,
    is_product_effective_on_base_date,
    annual_fee
FROM app_internal.customer_cards_full
ORDER BY card_ref
