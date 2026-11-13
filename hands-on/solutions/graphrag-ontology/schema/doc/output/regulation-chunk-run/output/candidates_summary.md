# 스키마 후보 요약: regulation

- 모델: openai/gpt-oss-120b, 추출기: neo4j-graphrag `SchemaFromTextExtractor`, examples = 역량 질문만
- 호출 5건(성공 4, 실패 1), 노드 타입 이름 21개, 관계 이름 27개

## 묶음별 멈춤

| 묶음 | 본 건수 | 멈춘 이유 |
|---|---:|---|
| 약관 전체 | 5 | 모두 봄 |

## 역량 질문별로 답할 수 있어 보이는 이름(LLM 분류, 드문 이름 포함)

| 질문 | 이름 |
|---|---|
| R1 | Clause |
| R2 | Condition |
| R3 | Notification |
| R4 | Action, Reason |
| R5 | Document |

## 노드 타입 이름별 나온 청크 수와 자주 나온 속성

| 노드 타입 | 청크 수 | 속성(나온 수) |
|---|---:|---|
| Clause | 3 | number(3), title(3), effective_date(1) |
| Condition | 2 | description(2) |
| CardIssuer | 2 | name(2) |
| Notification | 2 | method(1), date(1), type(1), sent_date(1), channel(1) |
| Transaction | 2 | amount(2), date(2), transaction_id(1), type(1), approved(1) |
| Card | 2 | card_id(1), expiration_date(1), status(1), card_number(1), annual_fee(1), credit_limit(1) |
| Document | 1 | identifier(1), version(1), publication_date(1) |
| Party | 1 | name(1), role(1) |
| Action | 1 | description(1) |
| Limit | 1 | amount(1), type(1), effective_date(1) |
| Report | 1 | report_number(1), date(1) |
| Fee | 1 | amount(1), due_date(1) |
| Approval | 1 | datetime(1), amount(1) |
| Member | 1 | member_id(1) |
| Reason | 1 | category(1) |
| Cancellation | 1 | datetime(1) |
| PrimaryMember | 1 | member_id(1), name(1) |
| CardApplication | 1 | application_date(1), status(1) |
| ElectronicDocument | 1 | format(1) |
| FamilyMember | 1 | member_id(1), name(1) |
| Request | 1 | type(1) |

## 관계 이름별 나온 청크 수

| 관계 | 청크 수 |
|---|---:|
| ISSUES | 2 |
| SUBMITS | 2 |
| REFERS_TO | 2 |
| HAS_ACTION | 1 |
| REFERS_TO_DOCUMENT | 1 |
| INVOLVES_PARTY | 1 |
| HAS_CONDITION | 1 |
| ON | 1 |
| NOTIFIES | 1 |
| HAS_FEE | 1 |
| ABOUT | 1 |
| DEFINES | 1 |
| RECEIVES | 1 |
| HAS_LIMIT | 1 |
| OWNED_BY | 1 |
| FOR | 1 |
| HAS_REASON | 1 |
| SUBMITTED_BY | 1 |
| MAKES | 1 |
| HAS_FAMILY_MEMBER | 1 |
| RESULTED_IN | 1 |
| SENDS | 1 |
| REVIEWED_BY | 1 |
| OWNS | 1 |
| ASSOCIATED_WITH | 1 |
| RELATES_TO | 1 |
| RESPONDS | 1 |

## 자주 나온 패턴(2건 이상)

| 패턴 | 청크 수 |
|---|---:|
| (CardIssuer)-[ISSUES]->(Card) | 2 |

## 실패한 호출

- 약관 전체 5번 `D1_27223010abe31291_44afb5c64dae945d_0000`: SchemaExtractionError: LLM response does not conform to GraphSchema: 5 validation errors for GraphSchema
relationship_types
  Input should be a valid tuple [typ
