"""고정 조회의 목적과 SQL을 한곳에서 관리합니다."""

FIXED_QUERIES = {
    "customer_snapshot": {
        "description": "보유 카드, 최근 6개월 카드별 월 승인액, 최신 이용 가능한 연체 현황을 모두 확보합니다.",
        "result_grain": "고객 현황 전체 묶음. 질문별 집계·계산·정렬·필터를 추가하지 않습니다.",
        "sql": None,
    },
    "cards": {
        "description": "보유 카드 목록과 상품·브랜드·발급일·현재 상태·상품 시행일·연회비를 조회합니다.",
        "result_grain": "기준일 이전 발급 카드마다 1행. 현재 상태를 포함하며 ACTIVE로 필터하지 않습니다.",
        "sql": "SELECT card_ref, product_id, product_name, brand, issue_date, current_status, "
               "product_effective_date, is_product_effective_on_base_date, annual_fee "
               "FROM customer_cards ORDER BY card_ref",
    },
    "monthly_usage": {
        "description": "최근 6개월의 카드별 월 승인 금액과 승인 건수, 조회 기간을 모두 조회합니다.",
        "result_grain": "카드 × 월마다 1행. 여러 카드의 금액을 합친 고객 전체 월별 총액은 아닙니다.",
        "sql": "SELECT card_ref, month, period_start, period_end, approved_amount, transaction_count "
               "FROM monthly_usage ORDER BY month, card_ref",
    },
    "delinquency": {
        "description": "기준일 이전 완료된 월 중 최신 연체액·연체 일수·최근 12개월 연체 월 수를 조회합니다.",
        "result_grain": "고객의 최신 완료 월 0~1행. 카드별 연체와 연체 월별 추이를 지원하지 않습니다.",
        "sql": "SELECT base_month, as_of_date, overdue_amount, overdue_days, overdue_count_12m "
               "FROM customer_delinquency",
    },
}


def query_catalog() -> list[dict]:
    return [{"query_id": key, 
             "description": value["description"], 
             "result_grain": value["result_grain"],
             "sql": value["sql"]}
            for key, value in FIXED_QUERIES.items()]
