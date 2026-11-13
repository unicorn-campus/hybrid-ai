# 테이블 판정표

- FK 제약 수: 열 수가 아니라 FK 규칙(제약) 수. 열 2개로 된 FK 1개는 1개로 셈  
- 업무 열 수: PK에도 FK에도 들어가지 않는 열의 수  
- 판정은 위에서부터 먼저 맞는 규칙을 적용함(다른 테이블이 가리킴 → FK 0개 또는 1개 → FK 3개 이상 → FK 2개)

| 테이블 | FK 제약 수 | 업무 열 수 | 판정 | 적용 규칙 |
|--------|-----------|-----------|------|-----------|
| card | 2 | 2 | 노드 타입 | 다른 테이블이 가리킴 |
| card_txn | 2 | 3 | 규칙 ① 후보 → 사용자가 노드 타입으로 정함 | 규칙 ① (FK 2개, 업무 열 있음) |
| delinquency | 1 | 3 | 노드 타입 | FK 0개 또는 1개 |
| lab_metadata | 0 | 1 | 노드 타입 → 사용자가 그래프에서 뺌 | FK 0개 또는 1개 |
| member | 0 | 3 | 노드 타입 | 다른 테이블이 가리킴 |
| merchant | 0 | 2 | 노드 타입 | 다른 테이블이 가리킴 |
| product | 0 | 4 | 노드 타입 | 다른 테이블이 가리킴 |
| product_annual_fee | 1 | 3 | 노드 타입 | 다른 테이블이 가리킴 |

## FK 제약 목록

| 제약 이름 | 테이블 | 가리키는 테이블 | 열 짝 |
|---|---|---|---|
| card_member_id_fkey | card | member | card.member_id → member.member_id |
| card_product_id_brand_fkey | card | product_annual_fee | card.product_id → product_annual_fee.product_id, card.brand → product_annual_fee.brand |
| card_txn_card_id_fkey | card_txn | card | card_txn.card_id → card.card_id |
| card_txn_merchant_id_fkey | card_txn | merchant | card_txn.merchant_id → merchant.merchant_id |
| delinquency_member_id_fkey | delinquency | member | delinquency.member_id → member.member_id |
| product_annual_fee_product_id_fkey | product_annual_fee | product | product_annual_fee.product_id → product.product_id |
