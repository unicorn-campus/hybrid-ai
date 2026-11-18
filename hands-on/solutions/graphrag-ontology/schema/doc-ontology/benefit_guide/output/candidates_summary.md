# 스키마 후보 요약: benefit_guide

- 호출 67건(성공 67, 실패 0), 토큰 245,269, 걸린 시간 279초  
- 노드 타입 이름 29개(두 번 이상 나온 것 17개), 관계 이름 59개(두 번 이상 나온 것 18개)  
- 이름은 대소문자, 띄어쓰기, 밑줄 차이를 없애고 셈. 한 번만 나온 이름도 빼지 않고 적음  

## 묶음별 멈춘 곳

| 묶음 | 본 건수 | 멈춘 까닭 |
|---|---|---|
| 적립 | 15 | 15건에서 멈춤(새 타입이 3건 연속 없음) |
| 할인 | 16 | 16건에서 멈춤(새 타입이 3건 연속 없음) |
| 그 밖 | 10 | 10건에서 멈춤(새 타입이 3건 연속 없음) |
| 이용 기준 | 15 | 15건에서 멈춤(새 타입이 3건 연속 없음) |
| 캐시백 | 11 | 11건에서 멈춤(새 타입이 3건 연속 없음) |
| 항목 아님 | 0 | 0건 모두 봄(상한) |

## 노드 타입 후보(나온 건수 순)

| 이름 | 나온 건수 | 속성(나온 건수) |
|---|---|---|
| Card | 67 | card_id(67), name(62), card_name(5), virtual_effective_date(1), has_family_card(1) |
| Benefit | 67 | benefit_id(67), name(50), effective_date(43), exclusions(16), discount_rate(14), payment_timing(11), payout_day(9), payment_day(7), target_channel(6), virtual_implementation_date(6), accrual_rate(5), limit_monthly_amount(5) |
| Condition | 20 | description(17), currency(2), condition_type(2), excluded_from_spend(2), amount_threshold(2), threshold_amount(2), min_monthly_spending(1), min_spend(1), excludes(1), required_transactions(1), minimum_spend(1), required_amount(1) |
| Limit | 18 | amount(12), period(9), unit(3), currency(2), monthly_amount(2), total_monthly_amount(1), item_monthly_amount(1), total_monthly_limit(1), specific_monthly_limit(1), per_benefit_amount(1), per_transaction_amount(1), type(1) |
| Channel | 15 | name(13), description(2), channel_name(1) |
| Exclusion | 11 | description(7), name(2), transaction_type(1), items(1) |
| TransactionType | 6 | name(5), type_name(1) |
| Account | 5 | type(3), account_type(2), account_name(1), linked_to_virtual_guardian(1) |
| Guardian | 4 | guardian_type(1), is_virtual(1), role(1), type(1) |
| Payout | 3 | day_of_month(3), method(2) |
| MerchantCategory | 2 | category_name(1), name(1) |
| TransactionCategory | 2 | name(1), category_name(1) |
| Merchant | 2 | name(2) |
| Restriction | 2 | category(1), restriction_type(1), description(1) |
| Industry | 2 | name(2) |
| Voucher | 2 | quantity_per_month(1), amount_per_month(1), expiration_date(1) |
| Settlement | 2 | day_of_month(1), basis(1), description(1), payment_day(1) |
| Service | 1 | name(1), service_type(1) |
| Charity | 1 | name(1) |
| Category | 1 | name(1) |
| PaymentTiming | 1 | description(1) |
| Notification | 1 | method(1) |
| Store | 1 | name(1) |
| FinancialInstitution | 1 | name(1) |
| BusinessProfile | 1 | profile_type(1), account_connected(1) |
| ExcludedTransaction | 1 | name(1) |
| DiscountCategory | 1 | name(1) |
| ExclusionCategory | 1 | name(1) |
| Bonus | 1 | amount(1) |

## 관계 후보(나온 건수 순)

| 이름 | 나온 건수 |
|---|---|
| HAS_BENEFIT | 51 |
| CARD_HAS_BENEFIT | 12 |
| HAS_CONDITION | 11 |
| HAS_LIMIT | 11 |
| EXCLUDES | 8 |
| APPLIES_TO_CHANNEL | 7 |
| BENEFIT_HAS_LIMIT | 7 |
| BENEFIT_HAS_CONDITION | 7 |
| BENEFIT_APPLIES_TO_CHANNEL | 5 |
| HAS_EXCLUSION | 3 |
| EXCLUDES_TRANSACTION | 3 |
| BENEFIT_HAS_EXCLUSION | 3 |
| OFFERS | 2 |
| APPLIES_TO_CATEGORY | 2 |
| LINKED_TO_GUARDIAN | 2 |
| BENEFIT_HAS_SETTLEMENT | 2 |
| BENEFIT_EXCLUDES | 2 |
| HAS_PAYOUT | 2 |
| APPLIES_TO_SERVICE | 1 |
| DELIVERED_TO | 1 |
| APPLIES_TO | 1 |
| ACCRUES_TO_ACCOUNT | 1 |
| CONDITION_ON | 1 |
| TARGETS | 1 |
| TARGETS_MERCHANT | 1 |
| BENEFIT_TARGETS_CATEGORY | 1 |
| BENEFIT_EXCLUDES_TYPE | 1 |
| APPLICABLE_VIA | 1 |
| PAYMENT_AT | 1 |
| EXCLUDED_FROM | 1 |
| HAS_ISSUANCE_CONDITION | 1 |
| HAS_USAGE_CONDITION | 1 |
| APPLIES_TO_ACCOUNT | 1 |
| HAS_RESTRICTION | 1 |
| HAS_NOTIFICATION | 1 |
| ALLOWS_INDUSTRY | 1 |
| RESTRICTS_INDUSTRY | 1 |
| REQUIRES_ACCOUNT | 1 |
| PROVIDES_VOUCHER | 1 |
| BENEFIT_APPLIES_TO_STORE | 1 |
| HAS_ACCOUNT | 1 |
| MANAGED_BY | 1 |
| ISSUES_VOUCHER | 1 |
| PROVIDED_BY | 1 |
| APPLICABLE_TO | 1 |
| CONNECTED_TO | 1 |
| CONDITION_APPLIES_TO_ACCOUNT | 1 |
| ACCOUNT_LINKED_TO_GUARDIAN | 1 |
| BENEFIT_RESTRICTS_INDUSTRY | 1 |
| BENEFIT_EXCLUDES_TRANSACTION | 1 |
| CARD_OFFERED_BENEFIT | 1 |
| HAS_CATEGORY | 1 |
| CARD_OFFER_BENEFIT | 1 |
| BENEFIT_HAS_PAYOUT | 1 |
| BENEFIT_HAS_BONUS | 1 |
| BENEFIT_HAS_RESTRICTION | 1 |
| TARGETS_CHANNEL | 1 |
| HAS_CHANNEL | 1 |
| REQUIRES_CONDITION | 1 |

## 패턴 후보(두 번 이상 나온 것)

| 출발 | 관계 | 도착 | 나온 건수 |
|---|---|---|---|
| Card | HAS_BENEFIT | Benefit | 51 |
| Card | CARD_HAS_BENEFIT | Benefit | 12 |
| Benefit | HAS_CONDITION | Condition | 11 |
| Benefit | HAS_LIMIT | Limit | 11 |
| Benefit | APPLIES_TO_CHANNEL | Channel | 7 |
| Benefit | BENEFIT_HAS_LIMIT | Limit | 7 |
| Benefit | BENEFIT_HAS_CONDITION | Condition | 7 |
| Benefit | BENEFIT_APPLIES_TO_CHANNEL | Channel | 5 |
| Benefit | EXCLUDES | Exclusion | 4 |
| Benefit | BENEFIT_HAS_EXCLUSION | Exclusion | 3 |
| Card | OFFERS | Benefit | 2 |
| Benefit | HAS_EXCLUSION | Exclusion | 2 |
| Benefit | EXCLUDES | TransactionCategory | 2 |
| Benefit | EXCLUDES_TRANSACTION | TransactionType | 2 |
| Account | LINKED_TO_GUARDIAN | Guardian | 2 |
| Benefit | BENEFIT_HAS_SETTLEMENT | Settlement | 2 |
| Benefit | HAS_PAYOUT | Payout | 2 |

## 역량 질문마다 답할 수 있어 보이는 이름

- AI가 후보 이름과 속성을 읽고 짝지은 것임. 드물게 나온 이름도 빼지 않음. 괄호는 나온 건수  

| 역량 질문 | 질문 | 후보 이름 |
|---|---|---|
| B1 | 이 카드에는 어떤 혜택이 있고 혜택마다 얼마(비율, 금액, 횟수)를 주는가? | Benefit(67, name), Benefit.discount_rate, accrual_rate, cashback_rate, percentage, amount, Voucher(2), Bonus(1) |
| B2 | 이 혜택을 받으려면 어떤 조건(전월 실적, 대상 가맹점이나 결제 방식, 등록)을 채워야 하는가? | Condition(20), Channel(15), Merchant(2), Store(1), Benefit.performance_condition, target_channel |
| B3 | 이 혜택의 한도와 사용 기한, 지급 시점은 언제 얼마인가? | Limit(18), Payout(3), PaymentTiming(1), Benefit.payment_timing, payout_day, monthly_limit |
| B4 | 이 혜택에서 빠지는 거래는 무엇인가? | Exclusion(11), ExcludedTransaction(1), TransactionType(6), Benefit.exclusions |
| B5 | 이 카드에 걸린 이용 제한(결제 한도 등)은 무엇인가? | Limit(18), Restriction(2), Guardian(4) |
| M2 | 고객이 말한 불만 주제마다 관련된 카드 혜택은 무엇인가? 없으면 없다고 답하는가? | 없음(여러 문서를 잇는 개념이 후보에 나오지 않음) |
| M3 | 상담에서 말한 카드에는 어떤 혜택이 있는가? | Card(67, card_id와 name) |
| X1 | 회원이 많이 쓰는 업종에 혜택을 주는 카드는 무엇인가? | MerchantCategory(2), TransactionCategory(2), Industry(2), Category(1), DiscountCategory(1) |
| X3 | 회원이 가진 카드에는 어떤 혜택이 있는가? | Card(67, card_id) |
