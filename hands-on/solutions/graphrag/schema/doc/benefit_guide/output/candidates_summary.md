# 스키마 후보 요약: benefit_guide

- 모델: openai/gpt-oss-120b, 추출기: neo4j-graphrag `SchemaFromTextExtractor`, examples = 역량 질문만
- 호출 47건(성공 44, 실패 3), 노드 타입 이름 31개, 관계 이름 43개

## 묶음별 멈춤

| 묶음 | 본 건수 | 멈춘 이유 |
|---|---:|---|
| 공통 안내 | 3 | 모두 봄 |
| 참고 카드 | 5 | 모두 봄 |
| 카드 개요 | 29 | 시작 수 뒤 연속 3건 새 타입 없음 |
| 혜택 상세 | 10 | 시작 수 뒤 연속 3건 새 타입 없음 |

## 역량 질문별로 답할 수 있어 보이는 이름(LLM 분류, 드문 이름 포함)

| 질문 | 이름 |
|---|---|
| B1 | Card, Benefit, BenefitProgram, BenefitTier |
| B2 | Condition |
| B3 | Limit |
| B4 | Exclusion |
| B5 | Card, Fee |

## 노드 타입 이름별 나온 청크 수와 자주 나온 속성

| 노드 타입 | 청크 수 | 속성(나온 수) |
|---|---:|---|
| Card | 43 | name(40), code(30), effective_date(10), virtualEffectiveDate(10), public_grade(6), annual_fee_domestic(6), annual_fee_overseas(6), virtual_effective_date(6) |
| Benefit | 34 | name(30), exclusions(14), code(9), description(9), discount_rate(8), payment_timing(5), payout_day(5), limit_monthly_amount(4) |
| Condition | 23 | description(15), excluded_items(3), min_spending(3), type(3), threshold_amount(2), amount(2), prior_month_spending_min(1), monthly_spend_min(1) |
| Limit | 22 | period(17), amount(17), description(6), unit(3), currency(2), max_amount(1), monthly_amount(1), monthly_cap(1) |
| Channel | 17 | name(10), description(6), type(2) |
| Fee | 10 | total(5), amount(4), basic(4), service(4), category(3), fee_type(2), currency(2), component(1) |
| Exclusion | 10 | description(9), excluded_items(1), name(1) |
| FeeComponent | 6 | amount(5), component(2), type(2), brand_method(1), basic_fee(1), service_fee(1), total_fee(1), category(1) |
| Issuer | 4 | name(4) |
| TransactionType | 3 | name(3), automatic(1) |
| Provider | 2 | name(2) |
| Document | 1 | format(1) |
| Brand | 1 | name(1) |
| Usage | 1 | description(1) |
| AnnualFee | 1 | category(1), basic_amount(1), service_amount(1), total_amount(1), currency(1) |
| TimeWindow | 1 | start_hour(1), end_hour(1) |
| MerchantCategory | 1 | name(1) |
| Category | 1 | name(1) |
| Company | 1 | name(1) |
| BenefitProgram | 1 | code(1), name(1), benefitDescription(1) |
| BenefitTier | 1 | minAmount(1), maxAmount(1), rate(1) |
| PaymentTiming | 1 | description(1) |
| Implementation | 1 | effective_date(1), is_virtual(1) |
| Offer | 1 | code(1), name(1), description(1), effective_date(1) |
| Restriction | 1 | description(1) |
| Target | 1 | name(1) |
| TransactionCategory | 1 | name(1) |
| SettlementRule | 1 | settlementDay(1), basis(1), period(1) |
| Account | 1 | type(1) |
| Transaction | 1 | type(1) |
| Bonus | 1 | name(1), amount(1), currency(1), type(1), achievement_condition(1), payment_timing(1), exclusions(1), duplicate_restriction(1) |

## 관계 이름별 나온 청크 수

| 관계 | 청크 수 |
|---|---:|
| HAS_BENEFIT | 23 |
| HAS_CONDITION | 17 |
| HAS_LIMIT | 16 |
| HAS_FEE | 11 |
| APPLIES_TO_CHANNEL | 9 |
| ISSUED_BY | 7 |
| HAS_EXCLUSION | 6 |
| BENEFIT_HAS_CONDITION | 5 |
| BENEFIT_HAS_LIMIT | 5 |
| OFFERS | 4 |
| CARD_HAS_BENEFIT | 4 |
| APPLIES_TO | 3 |
| BENEFIT_HAS_EXCLUSION | 3 |
| TARGETS_CHANNEL | 3 |
| EXCLUDES | 3 |
| HAS_FEE_COMPONENT | 2 |
| CARD_HAS_FEE | 2 |
| TARGETS | 2 |
| CARD_HAS_FEE_COMPONENT | 2 |
| CARD_OFFER_BENEFIT | 2 |
| BENEFIT_HAS_CHANNEL | 2 |
| EXCLUDES_TRANSACTION | 2 |
| REFERENCED_IN | 1 |
| MENTIONED_IN | 1 |
| BENEFIT_HAS_USAGE | 1 |
| BENEFIT_HAS_FEE | 1 |
| APPLIES_DURING | 1 |
| BENEFIT_EXCLUDES | 1 |
| BENEFIT_ALLOCATES_PERCENTAGE | 1 |
| REQUIRES_CONDITION | 1 |
| HAS_TIER | 1 |
| HAS_FAMILY_CARD | 1 |
| HAS_TIMING | 1 |
| OFFERS_BENEFIT | 1 |
| HAS_EFFECTIVE_DATE | 1 |
| APPLICABLE_VIA | 1 |
| HAS_RESTRICTION | 1 |
| PROVIDED_BY | 1 |
| SETTLES_ON | 1 |
| APPLIES_TO_ACCOUNT | 1 |
| BONUS_HAS_LIMIT | 1 |
| CARD_OFFER_BONUS | 1 |
| CARD_HAS_LIMIT | 1 |

## 자주 나온 패턴(2건 이상)

| 패턴 | 청크 수 |
|---|---:|
| (Card)-[HAS_BENEFIT]->(Benefit) | 23 |
| (Benefit)-[HAS_LIMIT]->(Limit) | 15 |
| (Benefit)-[HAS_CONDITION]->(Condition) | 15 |
| (Benefit)-[APPLIES_TO_CHANNEL]->(Channel) | 9 |
| (Card)-[HAS_FEE]->(Fee) | 8 |
| (Benefit)-[HAS_EXCLUSION]->(Exclusion) | 6 |
| (Benefit)-[BENEFIT_HAS_LIMIT]->(Limit) | 5 |
| (Benefit)-[BENEFIT_HAS_CONDITION]->(Condition) | 5 |
| (Card)-[ISSUED_BY]->(Issuer) | 4 |
| (Card)-[CARD_HAS_BENEFIT]->(Benefit) | 4 |
| (Benefit)-[BENEFIT_HAS_EXCLUSION]->(Exclusion) | 3 |
| (Benefit)-[TARGETS_CHANNEL]->(Channel) | 3 |
| (Card)-[OFFERS]->(Benefit) | 3 |
| (Card)-[HAS_FEE_COMPONENT]->(FeeComponent) | 2 |
| (Card)-[CARD_HAS_FEE]->(Fee) | 2 |
| (Card)-[CARD_HAS_FEE_COMPONENT]->(FeeComponent) | 2 |
| (Card)-[HAS_FEE]->(FeeComponent) | 2 |
| (Card)-[CARD_OFFER_BENEFIT]->(Benefit) | 2 |
| (Benefit)-[BENEFIT_HAS_CHANNEL]->(Channel) | 2 |

## 실패한 호출

- 공통 안내 1번 `D2_5a3c0df949be0524_04326c8435fbadcf_0000`: SchemaValidationError: UNIQUENESS and KEY constraints cannot apply to the same node type and properties ('Card', ('card_id',)).
- 카드 개요 16번 `D2_5a3c0df949be0524_0930063f60846ef1_0000`: SchemaValidationError: EXISTENCE and KEY constraints cannot apply to the same node type and property ('Card', 'code').
- 혜택 상세 9번 `D2_5a3c0df949be0524_b548f0141f4c348e_0000`: SchemaValidationError: EXISTENCE and KEY constraints cannot apply to the same node type and property ('BenefitProgram', 'code').
