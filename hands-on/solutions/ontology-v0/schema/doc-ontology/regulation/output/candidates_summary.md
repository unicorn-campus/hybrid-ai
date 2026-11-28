# 스키마 후보 요약: regulation

- 호출 25건(성공 25, 실패 0), 토큰 82,906, 걸린 시간 94초  
- 노드 타입 이름 43개(두 번 이상 나온 것 11개), 관계 이름 79개(두 번 이상 나온 것 8개)  
- 이름은 대소문자, 띄어쓰기, 밑줄 차이를 없애고 셈. 한 번만 나온 이름도 빼지 않고 적음  

## 묶음별 멈춘 곳

| 묶음 | 본 건수 | 멈춘 까닭 |
|---|---|---|
| 조항 | 25 | 25건 모두 봄(상한) |

## 노드 타입 후보(나온 건수 순)

| 이름 | 나온 건수 | 속성(나온 건수) |
|---|---|---|
| Clause | 7 | title(7), number(4), clause_number(3), due_date(1), unpaid_amount(1), occurrence_date(1), virtual_cost(1), remediation_method(1), is_delinquent(1) |
| Member | 4 | member_id(2), payment_date(1), member_type(1) |
| CardCompany | 3 | name(3) |
| Transaction | 3 | amount(2), identifier(1), approval_date(1), purchase_date(1), merchant_category(1), fee(1), benefit(1), cancellation_status(1), transaction_id(1), payment_date(1), installment_number(1) |
| Statement | 3 | card_identifier_partial(1), received_date(1), statement_id(1), period(1), order_details(1) |
| CardIssuer | 3 | name(3) |
| Merchant | 2 | name(2) |
| Cancellation | 2 | timestamp(1), cancellation_id(1), received_before_payment(1), overseas(1) |
| Payment | 2 | amount(2), partial(1) |
| Record | 2 | record_type(2), record_id(1), before_value(1), after_value(1) |
| Account | 2 | balance(1), bank_status(1), account_number(1) |
| Approval | 1 | timestamp(1), amount(1) |
| InstallmentTransaction | 1 | monthCount(1), installmentAmount(1), feeRate(1) |
| Product | 1 | name(1) |
| ContractDocument | 1 | date(1) |
| PersonalInformation | 1 | category(1) |
| Purpose | 1 | name(1) |
| RetentionPeriod | 1 | description(1) |
| Work | 1 | category(1) |
| Consignee | 1 | role(1) |
| Procedure | 1 | name(1) |
| Person | 1 | person_id(1), name(1) |
| System | 1 | system_id(1), name(1) |
| Objection | 1 | deadline_days(1), receipt_number(1), review_due_days(1), request_items(1), reply_due_date(1) |
| RevaluationRequest | 1 | reason(1), acceptance(1), effectiveDate(1), appealPath(1) |
| Amount | 1 | category(1) |
| PartialPayment | 1 | minimum_amount(1), next_month_carryover(1), estimated_cost(1) |
| Screen | 1 | name(1) |
| PartialPaymentRolloverAgreement | 1 | minimum_payment_ratio(1), virtual_fee_rate(1), expected_repayment_period(1), total_cost(1) |
| LoanApplication | 1 | available_amount(1), virtual_fee_rate(1), usage_period(1), payment_date(1), expected_repayment(1), verification_status(1), result_status(1), reason_category(1) |
| CardLoan | 1 | requested_amount(1), term(1), repayment_method(1), virtual_interest_rate(1), early_repayment_condition(1), consent_required(1) |
| RepaymentSchedule | 1 | effective_date(1) |
| Installment | 1 | installment_number(1), principal_amount(1), fee_amount(1) |
| Applicant | 1 | name(1), contactMethod(1), paymentAccount(1) |
| FamilyCard | 1 | annualFee(1), maxIssuableCount(1), paymentResponsibility(1), usageScope(1) |
| Issue | 1 | type(1) |
| SupportChannel | 1 | type(1) |
| FeeComponent | 1 | name(1), amount(1), billing_cycle(1) |
| Card | 1 | card_type(1) |
| ExternalSystem | 1 | name(1) |
| Refund | 1 | amount(1) |
| ConversionStandard | 1 | reference_clause(1) |
| Debt | 1 | cost_amount(1), late_amount(1), principal_amount(1), transaction_time(1) |

## 관계 후보(나온 건수 순)

| 이름 | 나온 건수 |
|---|---|
| APPLIES_TO | 4 |
| REPORTS_TO | 2 |
| DESCRIBES | 2 |
| ASSOCIATED_WITH | 2 |
| PROCESSES | 2 |
| APPLIES | 2 |
| APPLIES_FOR | 2 |
| ISSUES | 2 |
| APPROVES | 1 |
| APPROVAL_AT | 1 |
| SUBMITS_CANCELLATION | 1 |
| DISPLAYED_IN | 1 |
| TRIGGERS | 1 |
| REQUEST_WITHDRAWAL | 1 |
| PROCESS_WITHDRAWAL | 1 |
| HANDLES | 1 |
| INVOLVES | 1 |
| REQUEST_HOLD | 1 |
| BASED_ON | 1 |
| PROVIDED_BY | 1 |
| INFORMS | 1 |
| REVIEWED | 1 |
| PROCESS_FOR | 1 |
| SUBJECT_TO | 1 |
| OUTSOURCES | 1 |
| PERFORMS | 1 |
| VIEW_RECORD | 1 |
| REQUEST_CORRECTION | 1 |
| CORRECTED_BY | 1 |
| TRANSMITTED_TO | 1 |
| FILED_OBJECTION | 1 |
| ABOUT | 1 |
| HANDLED_BY | 1 |
| REQUESTS_MATERIALS | 1 |
| SUBMITS | 1 |
| HAS_INVESTIGATION | 1 |
| SEPARATES | 1 |
| UPDATES | 1 |
| RECEIVES | 1 |
| INCLUDES | 1 |
| HAS_ACCOUNT | 1 |
| WITHDRAWAL | 1 |
| WITHDRAWAL_FAILED | 1 |
| SELECTS | 1 |
| VIEWED_ON | 1 |
| PROVIDES | 1 |
| TERMINATES | 1 |
| MODIFIES | 1 |
| HAS_SCHEDULE | 1 |
| CONTAINS_INSTALLMENT | 1 |
| SUBMITS_APPLICATION | 1 |
| REQUEST_ISSUANCE | 1 |
| HAS_FAMILY_MEMBER | 1 |
| NOTIFIES_RESULT | 1 |
| REQUEST_LIMIT_REDUCTION | 1 |
| REQUEST_SUSPENSION | 1 |
| REQUEST_TERMINATION | 1 |
| SUSPENDS | 1 |
| DELIVERED_TO | 1 |
| PROXY_RECEIPT | 1 |
| APPLIED_FOR | 1 |
| HAS_ISSUE | 1 |
| REPORTED_TO | 1 |
| MADE | 1 |
| HAS_APPROVAL | 1 |
| HAS_DELIVERY | 1 |
| DEFINES_FEE | 1 |
| HAS_FEE | 1 |
| BILLED_FOR | 1 |
| NOTIFY_MEMBER | 1 |
| REFUND_TO | 1 |
| HOLD_FUNDS | 1 |
| DEFINES | 1 |
| ISSUED_BY | 1 |
| RECORDED_IN | 1 |
| RESULTS_IN | 1 |
| USES_STANDARD | 1 |
| MAKES_PAYMENT | 1 |
| GENERATES | 1 |

## 패턴 후보(두 번 이상 나온 것)

| 출발 | 관계 | 도착 | 나온 건수 |
|---|---|---|---|

## 역량 질문마다 답할 수 있어 보이는 이름

- AI가 후보 이름과 속성을 읽고 짝지은 것임. 드물게 나온 이름도 빼지 않음. 괄호는 나온 건수  

| 역량 질문 | 질문 | 후보 이름 |
|---|---|---|
| R1 | 이 조항은 어떤 경우에 무엇을 하도록 정하는가? | Clause(7, title와 number), Procedure(1), Issue(1) |
| R2 | 이 조항이 정한 기한이나 기준 금액은 얼마인가? | Clause.due_date(1), Objection.deadline_days(1), Payment.amount(2), FeeComponent.amount(1), RetentionPeriod(1) |
| R3 | 이 조항의 절차는 어떻게 진행되고 결과는 언제 알리는가? | Procedure(1), Objection.review_due_days와 reply_due_date(1), INFORMS(1), NOTIFIES_RESULT(1) |
| R4 | 이 조항은 다른 어느 조항을 따르라고 하는가? | ConversionStandard.reference_clause(1), BASED_ON(1), SUBJECT_TO(1) |
| M1 | 고객이 말한 불만 주제마다 관련된 약관 조항은 무엇인가? | 없음(여러 문서를 잇는 개념이 후보에 나오지 않음) |
