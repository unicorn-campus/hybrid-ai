# 스키마 후보 요약: consult_log

- 호출 22건(성공 21, 실패 1), 토큰 93,619, 걸린 시간 102초  
- 노드 타입 이름 23개(두 번 이상 나온 것 9개), 관계 이름 50개(두 번 이상 나온 것 21개)  
- 이름은 대소문자, 띄어쓰기, 밑줄 차이를 없애고 셈. 한 번만 나온 이름도 빼지 않고 적음  

## 묶음별 멈춘 곳

| 묶음 | 본 건수 | 멈춘 까닭 |
|---|---|---|
| S01 신규가입 | 4 | 4건 모두 봄(상한) |
| S03 VIP | 4 | 4건 모두 봄(상한) |
| S06 연회비부담 | 3 | 3건 모두 봄(상한) |
| S02 장기보유 | 4 | 4건 모두 봄(상한) |
| S05 다중카드 | 4 | 4건 모두 봄(상한) |
| S04 휴면직전 | 3 | 3건 모두 봄(상한) |

## 노드 타입 후보(나온 건수 순)

| 이름 | 나온 건수 | 속성(나온 건수) |
|---|---|---|
| Consultation | 21 | date(21), topic(16), channel(14), id(11), consultation_id(10), follow_up_method(5), customer_group(4), transaction_count(3), followup_method(2), contact_phone(2), approved_transaction_count(2), transaction_month(2) |
| Card | 18 | name(9), masked_number(7), last_four(4), last4(2), number(1), card_type(1), card_name(1) |
| Customer | 12 | pseudonym_id(10), customer_group(7), group(3), name(3), member_id(2), phone(1), birthdate(1), email(1), contact_phone(1) |
| Member | 9 | pseudonym_id(7), customer_group(7), member_id(2), phone(2), contact_phone(2), group(1) |
| Agent | 9 | role(7), name(2) |
| TransactionSummary | 8 | total_amount(7), month(7), approved_count(4), transaction_count(3), count(1), approved_total(1) |
| Channel | 7 | name(7) |
| Transaction | 4 | count(3), total_amount(3), transaction_date(2), month(1), amount(1), approval_count(1), period(1) |
| Request | 4 | description(2), type(1), request_type(1) |
| Merchant | 1 | name(1), region_displayed(1) |
| Product | 1 | category(1) |
| Store | 1 | name(1) |
| Company | 1 | name(1) |
| PaymentMethod | 1 | method_name(1) |
| IssueTopic | 1 | topic(1) |
| OrderMethod | 1 | method(1) |
| Issue | 1 | description(1) |
| Proposal | 1 | description(1) |
| Complaint | 1 | topic(1) |
| TransactionRecord | 1 | month(1), count(1), total_amount(1) |
| Guideline | 1 | description(1) |
| ContactMethod | 1 | method(1) |
| Address | 1 | address_type(1) |

## 관계 후보(나온 건수 순)

| 이름 | 나온 건수 |
|---|---|
| FOLLOWS | 12 |
| HANDLED_BY | 8 |
| HANDLES | 8 |
| PARTICIPATES_IN | 7 |
| HAS_CONSULTATION | 5 |
| REFERENCES_CARD | 4 |
| HAS_CUSTOMER | 4 |
| USES_CARD | 4 |
| HAS_TRANSACTION | 3 |
| REFERS_TO_CARD | 3 |
| PARTICIPATED_IN | 3 |
| HAS_REQUEST | 3 |
| USES_CHANNEL | 2 |
| HAS_TRANSACTION_SUMMARY | 2 |
| VIA_CHANNEL | 2 |
| REFERS_TO_TRANSACTION | 2 |
| HAS_SUMMARY | 2 |
| INVOLVES_CARD | 2 |
| HANDLED | 2 |
| INVOLVES | 2 |
| HAS_ISSUE | 2 |
| INVOLVES_CUSTOMER | 1 |
| PRECEDES | 1 |
| MENTIONS_TRANSACTION | 1 |
| MENTIONS_MERCHANT | 1 |
| REFERS_TO | 1 |
| OCCURRED_ON | 1 |
| INVOLVES_PRODUCT | 1 |
| AT_STORE | 1 |
| COMPARES_WITH | 1 |
| PREVIOUS_CONSULTATION | 1 |
| DISCUSSES | 1 |
| INCLUDES | 1 |
| MENTIONS_METHOD | 1 |
| OCCURS_VIA | 1 |
| HAS_PROPOSAL | 1 |
| HAS_COMPLAINT | 1 |
| REFERENCES_TRANSACTION | 1 |
| ABOUT_CARD | 1 |
| MENTIONS_CARD | 1 |
| MADE_REQUEST | 1 |
| REQUEST_FOR | 1 |
| HAS_MEMBER | 1 |
| VIA | 1 |
| TARGETS | 1 |
| INCLUDES_TRANSACTION | 1 |
| PROVIDES_GUIDELINE | 1 |
| INCLUDES_CARD | 1 |
| PREFERS_CONTACT_METHOD | 1 |
| REFERS_TO_ADDRESS | 1 |

## 패턴 후보(두 번 이상 나온 것)

| 출발 | 관계 | 도착 | 나온 건수 |
|---|---|---|---|
| Consultation | FOLLOWS | Consultation | 12 |
| Agent | HANDLES | Consultation | 6 |
| Consultation | REFERENCES_CARD | Card | 4 |
| Consultation | HAS_CUSTOMER | Customer | 4 |
| Member | PARTICIPATES_IN | Consultation | 4 |
| Customer | PARTICIPATES_IN | Consultation | 3 |
| Customer | HAS_CONSULTATION | Consultation | 3 |
| Consultation | REFERS_TO_CARD | Card | 3 |
| Consultation | HANDLED_BY | Agent | 3 |
| Consultation | HAS_REQUEST | Request | 3 |
| Member | HAS_CONSULTATION | Consultation | 2 |
| Consultation | USES_CHANNEL | Channel | 2 |
| Consultation | HAS_TRANSACTION_SUMMARY | TransactionSummary | 2 |
| Consultation | VIA_CHANNEL | Channel | 2 |
| Transaction | USES_CARD | Card | 2 |
| Consultation | USES_CARD | Card | 2 |
| Consultation | HAS_SUMMARY | TransactionSummary | 2 |
| Consultation | INVOLVES_CARD | Card | 2 |
| Member | PARTICIPATED_IN | Consultation | 2 |
| Consultation | HAS_TRANSACTION | TransactionSummary | 2 |

## 실패한 호출

| 단위 | 사유 |
|---|---|
| D3-0012 | SchemaValidationError: EXISTENCE and KEY constraints cannot apply to the same node type and property ('Member', 'member_id'). |

## 역량 질문마다 답할 수 있어 보이는 이름

- AI가 후보 이름과 속성을 읽고 짝지은 것임. 드물게 나온 이름도 빼지 않음. 괄호는 나온 건수  

| 역량 질문 | 질문 | 후보 이름 |
|---|---|---|
| C1 | 이 상담에서 고객이 말한 불만이나 불편은 무엇인가? | Complaint(1), Issue(1), IssueTopic(1), Consultation.topic(16) |
| C2 | 이 상담에서 고객이 요청한 것(비교 기준, 원하는 조건)은 무엇인가? | Request(4) |
| C3 | 상담사가 어떤 제안을 했고 고객은 받아들였는가? 거절했다면 까닭은 무엇인가? | Proposal(1), Guideline(1) |
| C4 | 이 상담에서 일(해지, 전환, 신고 등)은 어디까지 진행되었는가? | 없음(진행 상태를 담는 이름이 후보에 나오지 않음) |
| C5 | 이 상담은 앞선 어느 상담과 이어지는가? | FOLLOWS(12), PRECEDES(1), PREVIOUS_CONSULTATION(1) |
| C6 | 고객이 원한 후속 안내 방식은 무엇인가? | Consultation.follow_up_method(5), followup_method(2), ContactMethod(1), PREFERS_CONTACT_METHOD(1) |
| A1 | 고객군마다 어떤 주제의 불만이 나왔는가? | Consultation.customer_group(4), Customer.customer_group(7), group(3) |
| A2 | 고객이 받아들인 제안들에는 어떤 공통점이 있는가? | Proposal(1) |
| M1 | 고객이 말한 불만 주제마다 관련된 약관 조항은 무엇인가? | Complaint(1), Issue(1) |
| M2 | 고객이 말한 불만 주제마다 관련된 카드 혜택은 무엇인가? 없으면 없다고 답하는가? | Complaint(1), Issue(1) |
| M3 | 상담에서 말한 카드에는 어떤 혜택이 있는가? | Card(18, name) |
| X2 | 회원 번호로 지정한 회원의 상담 기록은 무엇이고, 첫 상담과 가장 최근 상담은 어느 것인가? | Customer.pseudonym_id(10), Member.pseudonym_id(7) |
