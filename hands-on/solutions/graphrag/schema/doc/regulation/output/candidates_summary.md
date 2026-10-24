# 스키마 후보 요약: regulation

- 모델: openai/gpt-oss-120b, 추출기: neo4j-graphrag `SchemaFromTextExtractor`, examples = 역량 질문만
- 호출 17건(성공 17, 실패 0), 노드 타입 이름 42개, 관계 이름 63개

## 묶음별 멈춤

| 묶음 | 본 건수 | 멈춘 이유 |
|---|---:|---|
| 약관 조항 전체 | 17 | 모두 봄 |

## 역량 질문별로 답할 수 있어 보이는 이름(LLM 분류, 드문 이름 포함)

| 질문 | 이름 |
|---|---|
| R1 | Clause, Article |
| R2 | Requirement |
| R3 | Clause, ChangeEvent |
| R4 | TransactionSituation, Procedure, IncidentResponseProcedure |
| R5 | Document, ChangeEvent |

## 노드 타입 이름별 나온 청크 수와 자주 나온 속성

| 노드 타입 | 청크 수 | 속성(나온 수) |
|---|---:|---|
| Clause | 14 | title(14), number(13), termination_conditions(1), notice_period_days(1), appeal_method(1), effective_date(1), summary(1) |
| Transaction | 4 | transaction_type(1), exchange_rate_basis(1), includes_virtual_brand_cost(1), currency(1), calculation_formula(1), purchase_date(1), approval_cancellation_date(1), initial_purchase_date(1) |
| CardCompany | 4 | name(4) |
| Document | 2 | name(1), doc_id(1), version(1), access_date(1) |
| Article | 2 | number(2), title(2) |
| Purpose | 2 | name(1), description(1) |
| Merchant | 2 | name(2) |
| Member | 2 | member_id(1), name(1) |
| Person | 2 | role(2) |
| Account | 1 | account_id(1), balance(1) |
| Contract | 1 | identifier(1) |
| RetentionPolicy | 1 | name(1), description(1) |
| PersonalInformation | 1 | category(1) |
| SafetyMeasure | 1 | implemented(1) |
| TransactionSituation | 1 | description(1) |
| Responsibility | 1 | type(1) |
| Role | 1 | title(1) |
| Principle | 1 | name(1) |
| Procedure | 1 | name(1) |
| IncidentResponseProcedure | 1 | description(1) |
| Task | 1 | name(1) |
| RetentionPeriod | 1 | duration(1) |
| AccessPermission | 1 | type(1) |
| ProcessingItem | 1 | description(1) |
| RecordInspection | 1 | method(1) |
| Contractor | 1 | name(1) |
| Currency | 1 | code(1), name(1) |
| Refund | 1 | amount(1), date(1) |
| ExchangeRate | 1 | rate(1), date(1) |
| Cancellation | 1 | date(1), conversion_difference(1) |
| Fee | 1 | name(1), amount(1), calculation_basis(1) |
| Company | 1 | name(1) |
| Footnote | 1 | content(1) |
| Investigation | 1 | report_time(1), approval_location(1), auth_record(1), device_info(1), delivery_record(1), disputed_amount(1), normal_amount(1) |
| Reason | 1 | description(1) |
| Action | 1 | description(1) |
| Service | 1 | name(1) |
| Record | 1 | usage_date(1), virtual_cost(1) |
| Requirement | 1 | amount(1), count(1), monthly_limit(1) |
| Credential | 1 | type(1) |
| Term | 1 | name(1) |
| ChangeEvent | 1 | effective_date(1), reason(1), notice_period_days(1), full_text_url(1) |

## 관계 이름별 나온 청크 수

| 관계 | 청크 수 |
|---|---:|
| REGULATES | 3 |
| DEFINES | 2 |
| PROCESSES | 2 |
| HAS_PURPOSE | 2 |
| APPLIES_TO | 2 |
| DESCRIBES | 2 |
| DISPLAYED_IN | 1 |
| AFFECTS | 1 |
| REFERS_TO | 1 |
| MAKES | 1 |
| PAYMENT_COVERS_DEBT | 1 |
| MEMBER_MAKES_PAYMENT | 1 |
| CLAUSE_DEFINES_PAYMENT_ORDER | 1 |
| PAYMENT_RECORDED_IN_STATEMENT | 1 |
| GOVERNED_BY | 1 |
| REQUESTS_HOLD | 1 |
| NOTIFIES | 1 |
| INITIATED_BY | 1 |
| HAS_RESPONSIBILITY | 1 |
| DETERMINED_BY_SAFETY | 1 |
| OCCURS_AT | 1 |
| DETERMINED_BY_SITUATION | 1 |
| PROHIBITS_INPUT | 1 |
| HAS_CLAUSE | 1 |
| SET_BY | 1 |
| INTERPRETED_BY | 1 |
| RESOLUTION_PROCEDURE | 1 |
| HAS_INCIDENT_RESPONSE_PROCEDURE | 1 |
| HAS_PROCESSING_ITEM | 1 |
| HAS_CONTRACTOR | 1 |
| HAS_RETENTION_PERIOD | 1 |
| GRANTED_PERMISSION | 1 |
| PERFORMS_RECORD_INSPECTION | 1 |
| MERCHANT_ACCEPTS_CURRENCY | 1 |
| CLAUSE_INCLUDES_MERCHANT | 1 |
| CLAUSE_RECORDS_TRANSACTION | 1 |
| CLAUSE_SPECIFIES_EXCHANGE_RATE | 1 |
| CLAUSE_INCLUDES_MEMBER | 1 |
| TRANSACTION_USES_CURRENCY | 1 |
| TRANSACTION_HAS_CANCELLATION | 1 |
| CLAUSE_HAS_FEE | 1 |
| CLAUSE_USES_CURRENCY | 1 |
| CANCELLATION_RESULTS_IN_REFUND | 1 |
| CONTAINS | 1 |
| PUBLISHED_BY | 1 |
| HAS_FOOTNOTE | 1 |
| PRODUCES | 1 |
| INVESTIGATES | 1 |
| REPORTS | 1 |
| CAN_REVIEW | 1 |
| HAS_TRIGGER | 1 |
| RESULTS_IN | 1 |
| REQUIRES | 1 |
| USED_IN | 1 |
| CREATES | 1 |
| RECORDS_FOR | 1 |
| OFFERS | 1 |
| HAS_CARD | 1 |
| MENTIONS | 1 |
| HAS_CREDENTIAL | 1 |
| PROHIBITS_SHARING | 1 |
| NOTIFY | 1 |
| ALTERS | 1 |

## 자주 나온 패턴(2건 이상)

| 패턴 | 청크 수 |
|---|---:|
