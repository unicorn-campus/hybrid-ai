# 스키마 후보 요약: consult_log

- 모델: openai/gpt-oss-120b, 추출기: neo4j-graphrag `SchemaFromTextExtractor`, examples = 역량 질문만
- 호출 30건(성공 30, 실패 0), 노드 타입 이름 50개, 관계 이름 117개

## 묶음별 멈춤

| 묶음 | 본 건수 | 멈춘 이유 |
|---|---:|---|
| D3_S01_신규가입_상담이력_합성.txt | 5 | 모두 봄 |
| D3_S02_장기보유_상담이력_합성.txt | 5 | 모두 봄 |
| D3_S03_VIP_상담이력_합성.txt | 5 | 모두 봄 |
| D3_S04_휴면직전_상담이력_합성.txt | 5 | 모두 봄 |
| D3_S05_다중카드_상담이력_합성.txt | 5 | 모두 봄 |
| D3_S06_연회비부담_상담이력_합성.txt | 5 | 모두 봄 |

## 역량 질문별로 답할 수 있어 보이는 이름(LLM 분류, 드문 이름 포함)

| 질문 | 이름 |
|---|---|
| C1 | Issue, Request, Message, Conversation, Record |
| C2 | Proposal, Guidance, Message, Consultation |
| C3 | Message, Call, Interaction |
| C4 | Condition, Message, Request |
| C5 | Consultation, ConsultationRecord, Record, Conversation, Interaction |

## 노드 타입 이름별 나온 청크 수와 자주 나온 속성

| 노드 타입 | 청크 수 | 속성(나온 수) |
|---|---:|---|
| Customer | 23 | email(8), name(8), age_group(4), preferred_contact_method(4), preferred_contact_time(3), virtual_card_last4(3), contact(3), age_range(3) |
| Request | 18 | description(7), request_id(4), request_type(4), content(3), type(2), date(2), summary_method(1), complaint(1) |
| Transaction | 16 | total_amount(14), count(13), date(8), month(6), approval_month(1), approval_count(1), type(1), period(1) |
| TransactionSummary | 11 | total_amount(11), month(10), transaction_count(6), approved_count(3), count(1), date(1), approval_count(1) |
| Record | 8 | record_id(6), date(6), topic(2), id(1), title(1) |
| Issue | 5 | description(5) |
| Agent | 5 | name(4), role(1) |
| Consultation | 4 | date(4), id(2), topic(2), record_id(1), consultation_id(1), transaction_count(1), transaction_total(1), preferred_contact(1) |
| Conversation | 4 | date(4), id(3), record_id(1), topic(1), virtual_card_masked(1) |
| Card | 3 | status(2), masked_number(1), last_four(1), purpose(1) |
| Message | 2 | channel(1), content(1) |
| Statement | 2 | name(1), period(1), storage_path(1) |
| CommunicationMethod | 2 | method(2) |
| CommunicationPreference | 2 | method(2) |
| Notification | 2 | preference(1), frequency(1) |
| Channel | 2 | channel_type(1), name(1) |
| Address | 2 | type(1), address(1), full_address(1), address_type(1) |
| Interaction | 2 | record_id(1), date(1), interaction_id(1) |
| TransactionBatch | 2 | month(2), approved_count(2), total_amount(2) |
| CommunicationChannel | 2 | channel_type(1), channel(1) |
| Category | 2 | name(2) |
| Menu | 1 | name(1) |
| Device | 1 | device_type(1) |
| Cancellation | 1 | is_partial(1) |
| Topic | 1 | name(1) |
| Inquiry | 1 | topic(1) |
| Condition | 1 | description(1) |
| Call | 1 | outcome(1) |
| CancellationRequest | 1 | scope(1), method(1) |
| MessageChannel | 1 | type(1) |
| Communication | 1 | communication_id(1), date(1) |
| Proof | 1 | proof_type(1) |
| Product | 1 | category(1), model_name(1) |
| Company | 1 | name(1) |
| Benefit | 1 | name(1), automatic(1) |
| ComparisonTable | 1 | format(1) |
| ComparisonRequest | 1 | type(1) |
| Procedure | 1 | description(1) |
| Preference | 1 | method(1) |
| ContactMethod | 1 | method(1) |
| Guidance | 1 | content(1) |
| Branch | 1 | guidance_method(1) |
| Counselor | 1 | employee_id(1) |
| Proposal | 1 | suggestion(1) |
| ConsultationRecord | 1 | record_id(1), date(1), summary(1) |
| Person | 1 | contact(1) |
| Receipt | 1 | collected(1) |
| FollowUp | 1 | method(1) |
| OrderMethod | 1 | method(1) |
| ExpenseRequest | 1 | description(1), type(1), is_one_time(1) |

## 관계 이름별 나온 청크 수

| 관계 | 청크 수 |
|---|---:|
| MAKES_REQUEST | 8 |
| INTERACTS_WITH | 7 |
| HAS_TRANSACTION | 6 |
| PARTICIPATES_IN | 5 |
| HANDLES | 5 |
| HAS_PREFERENCE | 5 |
| MAKES | 5 |
| INITIATES | 4 |
| INCLUDES | 4 |
| RESPONDS_TO | 4 |
| OWNS | 3 |
| FOLLOWS | 3 |
| HAS_RECORD | 3 |
| REFERS_TO | 3 |
| RESPONDS | 3 |
| INCLUDES_TRANSACTION | 3 |
| MADE | 2 |
| USES | 2 |
| RECORDED_IN | 2 |
| MENTIONS | 2 |
| CONTAINS | 2 |
| INVOLVES_TRANSACTION | 2 |
| REFERENCES | 2 |
| REQUESTS | 2 |
| HANDLED_BY | 2 |
| HAS_ISSUE | 2 |
| HAS_REQUEST | 2 |
| ASSOCIATED_WITH | 2 |
| CONSULTS | 2 |
| HAS_SUMMARY | 2 |
| SUGGESTS | 2 |
| PROVIDES | 2 |
| RECORDS | 2 |
| ADDRESSED_BY | 1 |
| RECORDED_BY | 1 |
| EXPERIENCES | 1 |
| CONSULTATION_FOLLOWS | 1 |
| CONSULTATION_REFERS_TO_TRANSACTION | 1 |
| CUSTOMER_PARTICIPATES_IN | 1 |
| COUNSELOR_PARTICIPATES_IN | 1 |
| CONSULTATION_HAS_REQUEST | 1 |
| CONSULTATION_HAS_ISSUE | 1 |
| RECOMMENDS | 1 |
| HAS_CANCELLATION | 1 |
| SENT_BY | 1 |
| CONTAINS_REQUEST | 1 |
| REFERS_TO_STATEMENT | 1 |
| PROVIDES_RESPONSE | 1 |
| ABOUT_TOPIC | 1 |
| PREFERS_METHOD | 1 |
| HANDLES_INQUIRY | 1 |
| SUGGESTS_METHOD | 1 |
| MAKES_INQUIRY | 1 |
| HAS_CONDITION | 1 |
| CONDUCTS | 1 |
| TRIGGERS | 1 |
| HANDLES_CALL | 1 |
| REFERENCES_TRANSACTION | 1 |
| PREVIOUS_RECORD | 1 |
| CONNECTS_TO_DEPARTMENT | 1 |
| MAKES_CALL | 1 |
| ADDRESSES_ISSUE | 1 |
| REFERS_TO_TRANSACTION | 1 |
| FOLLOW_UP_OF | 1 |
| REFERS_TO_CARD | 1 |
| HANDLES_REQUEST | 1 |
| INCLUDES_TRANSACTION_QUERY | 1 |
| PROOF_FROM | 1 |
| OCCURRED_AT | 1 |
| VIA | 1 |
| SEEK_PROOF | 1 |
| ABOUT_TRANSACTION | 1 |
| PROOF_FOR | 1 |
| REQUESTED | 1 |
| REQUESTED_BY | 1 |
| PREFERRED_COMM_METHOD | 1 |
| INVOLVES_WARRANTY | 1 |
| HAS_NOTIFICATION | 1 |
| PROVIDES_TABLE | 1 |
| RECEIVES_TABLE | 1 |
| ASSOCIATED_WITH_COMPANY | 1 |
| REQUIRES_PROCEDURE | 1 |
| RECORDS_REQUEST | 1 |
| CREATED_RECORD | 1 |
| HAS_ADDRESS | 1 |
| INCLUDES_MAIL | 1 |
| USES_METHOD | 1 |
| HAS_APPLICATION | 1 |
| USES_ADDRESS | 1 |
| TARGETS_ADDRESS | 1 |
| HANDLED_VIA | 1 |
| RESPONDS_IN | 1 |
| USES_CHANNEL | 1 |
| INCLUDES_GUIDANCE | 1 |
| SENT | 1 |
| ASKS_ABOUT | 1 |
| OPERATES_AT | 1 |
| RELATES_TO_CARD | 1 |
| HAS_TRANSACTION_SUMMARY | 1 |
| HANDLED_AT | 1 |
| ABOUT_REQUEST | 1 |
| TARGETS_CARD | 1 |
| CREATES_RECORD | 1 |
| HAS_CARD | 1 |
| TARGETS | 1 |
| HAS_PROPOSAL | 1 |
| HAS_STATEMENT | 1 |
| CLASSIFIED_AS | 1 |
| COUNSELOR_IN | 1 |
| CUSTOMER_IN | 1 |
| INTERESTS_IN | 1 |
| ADVISES_ON | 1 |
| PREFERS | 1 |
| SELECTS | 1 |
| CONTAINS_TRANSACTION | 1 |
| CONDUCTED_BY | 1 |
| HAS_CONVERSATION | 1 |

## 자주 나온 패턴(2건 이상)

| 패턴 | 청크 수 |
|---|---:|
| (Customer)-[MAKES]->(Request) | 5 |
| (Customer)-[MAKES_REQUEST]->(Request) | 5 |
| (Customer)-[INITIATES]->(Conversation) | 2 |
| (Request)-[INVOLVES_TRANSACTION]->(Transaction) | 2 |
| (Customer)-[INTERACTS_WITH]->(Agent) | 2 |
| (Customer)-[HAS_TRANSACTION]->(Transaction) | 2 |
| (Request)-[INCLUDES_TRANSACTION]->(TransactionSummary) | 2 |
