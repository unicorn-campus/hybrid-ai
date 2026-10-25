# GraphRAG 검색 예제 프로그램 개발계획서

| 항목 | 내용 |
|---|---|
| 작성 | 클로니(오케스트레이터), 2026-10-25 |
| 검토 | 에듀니(교육), 플로니(실행 흐름과 장애), 지식니(검색 품질, 그래프 실측), 커넥니(외부 연동과 키). 14장 「검토 이력」 |
| 대상 교재 | 『신한카드 하이브리드AI_W05 ~ W07』 「3. 검색」 64 ~ 79쪽 |
| 설계 근거 | `teacher/plan/graphrag-react-search.md` v1.4(ReAct 권고안), `teacher/plan/graphrag-agentic-search.md` v2.2(서브 워크플로우 O, L, G와 진단 신호) |
| 입력(읽기만) | GraphRAG 인덱싱 결과. 활성 세대 `hands-on/solutions/graphrag/indexer/data/active_generation.json`(현재 `gen-lab-full-002-14209840`),  
Neo4j 그래프(엔티티 1,673개, 청크 노드 260개, 커뮤니티 보고서 78개), OpenSearch 인덱스 `card_chunks-{세대}`(260청크) |
| 산출 위치 | `hands-on/solutions/graphrag/retriever/` |
| 상태 | **v1.3(2026-10-25). ③ 에이전트를 Opus 5.5에서 Groq gpt-oss-120b로 바꿈(강사 결정, 16장). 개발 완료, 교재 반영 완료.  
아래 본문의 Opus 관련 서술 중 16장에 적은 항목은 바뀐 값이 현재 설정임** |

## 1. 목표

- 교육생이 교재 64쪽 검색 워크플로우 10단계(① 요청 접수 → ② 질문 분석 → ③ 검색 에이전트 ⇄ ④ 툴 실행 → ⑤ 채점과 상한 판정 →  
  ⑥ 리랭킹 → ⑦ 수집 종료 판정 → ⑧ 답변 생성 ⇄ ⑨ 근거 검증 → ⑩ 종료 상태)를 **파이썬 코드로 직접 만들며** 이해함  
- 핵심은 교재 64쪽 카드 4장임: **툴 고르기는 에이전트(Groq), 판단은 Jev(확률만), 막는 일은 코드, 툴 안은 고정 순서**.  
  교육생이 「LLM이 고르게 두되, 지켜야 할 것은 코드가 지킨다」를 손으로 써 보게 함  
- 강사는 전체 예제를 보여 주고, 교육생은 **단계마다 1개 이상, 실습 함수 13개(직접 7개, 빈칸 6개)**를 클론 코딩한 뒤  
  본인 코드로 바꿔 끼워 실행함(13장 D2)  
- 단계마다 판단 결과를 화면에 남김: Jev 확률과 코드의 결정, 회차마다 에이전트가 고른 툴과 질의, 진단 신호, 남은 회차,  
  강제 종료 이유, 리랭킹 뒤 8자리, 코드 재확인 결과, 인용 검증 실패 사유, 종료 상태

## 2. 교재 설계와 다른 점(교육용으로 단순화)

| 항목 | 교재(설계 문서) | 실습 예제 | 이유 |
|---|---|---|---|
| 흐름 구현 | LangGraph 노드(`agent`, `tools`, `s5_guard`) | ③ ~ ⑤는 LangChain `create_agent` + 미들웨어 2개, ①②와 ⑥ ~ ⑩은 main의 `run_workflow`가 파이썬 순서로 부름(2.1, D1) | 「막는 일은 코드」가 미들웨어 훅으로 보이고, 회차 상한과 고리 종료를 프레임워크가 보장함 |
| L2 ~ L4 Neo4j 호출 | Cypher 1번(71쪽) | Cypher 2번(후보 엔티티와 유사도 → 파이썬 축소 → 이웃과 보고서) | L2 축소 규칙을 실습 함수로 꺼냄. 2번째 쿼리에도 세대와 권한 조건을 다시 걺(4.4) |
| 그래프 쪽 권한 | 그래프 필터 | ①에서 OpenSearch 청크 메타데이터(260건)를 한 번 읽어 「볼 수 있는 청크 표」를 만들고, 엔티티와 보고서도 이 표로 거름(4.4) | 그래프의 Chunk 노드에는 `access_level`, `member_pseudo_id`가 없음(실측) |
| 진단 신호 | 설계 문서 8개(`OFF_TOPIC_REPORTS` 포함) | 교재 74쪽 7개. NO_REPORTS를 「관련도 0.25 이상인 보고서 0건」으로 정의해 OFF_TOPIC을 흡수 | 교재와 맞추되 상담 질문에서 혜택 보고서만 걸리는 경우를 잡음(지식니) |
| ⑦ 전제 충돌 | 설계 문서 7-4: 확인할 수 없음 | 교재 77쪽대로 **통과 + 「전제가 원문과 다름」 표시** | 교재가 나중 결정(교재 검토 35번) |
| 임베딩 | 설계 문서 v2.2: KURE-v2 | Cohere `embed-v5.0-fast`(인덱싱 실습과 같음) | 색인과 같은 모델이어야 함 |

툴 이름과 입력은 교재 69쪽대로 씀(`search_vector-bm25`, `find_entities(entity_key)`). 설계 문서의 `search_chunks`, `text`는 쓰지 않음.

### 2.1 LangChain `create_agent` 검토(강사 요청, 2026-10-25)

설치된 `langchain 1.4.6` 소스(`langchain/agents/factory.py`, `agents/middleware/`)에서 확인함(context7 월 한도 초과).  
`create_agent(model, tools, system_prompt=, middleware=[...], context_schema=, state_schema=)`는 「모델 → 툴 → 모델」 고리를  
LangGraph 그래프로 만들어 주고, 미들웨어 훅으로 고리 중간에 코드를 끼움.

| 교재 요구 | `create_agent`로 하는 법 | 판정 |
|---|---|---|
| ③ Opus가 툴을 고르고 되풀이(ReAct) | 기본 동작(model 노드 ⇄ tools 노드) | 그대로 됨 |
| ④ 툴 입력에 필터 칸 없음, 래퍼가 필터 강제 | 툴 함수가 `ToolRuntime`으로 요청 정보(세대, 식별자)를 받음. 모델이 보는 툴 스키마에는 나오지 않음. 또는 `wrap_tool_call` 훅 | 됨 |
| ④ 근거를 상태에 구조화해 기록 | 툴이 `Command(update=...)`를 돌려주고, 미들웨어 `state_schema`에 칸을 더함 | 됨 |
| ⑤ 관찰에 신호와 Jev 판정 붙이기 | `wrap_tool_call` 훅에서 툴 결과 메시지에 덧붙임 | 됨 |
| ⑤ 병렬 5, global_search 1회, 질의 8개 | `wrap_tool_call`에서 실행 전에 막고 오류 표시 ToolMessage를 돌려줌. 내장 `ToolCallLimitMiddleware(tool_name=..., run_limit=1)`도 있으나 영어 문구라 직접 짬 | 됨 |
| ⑤ 회차 6 | 내장 `ModelCallLimitMiddleware(run_limit=6, exit_behavior="end")` | 됨 |
| ⑤ 강제 종료(NO_NEW 2회 등), 모델을 다시 부르지 않음 | `before_model` 훅이 `{"jump_to": "end"}`를 돌려줌. 모델 호출 전에 끝남 | 됨 |
| finish | 툴로 두고 `before_model`이 finish 기록을 보면 끝냄. `return_direct`는 같은 회차에 다른 툴이 섞이면 끝나지 않아 쓰지 않음 | 됨(직접 처리) |
| 메시지 덧붙이기만(append-only) | 기본이 `add_messages`로 덧붙임. 요약 미들웨어를 넣지 않음 | 됨 |
| ①②, ⑥ ~ ⑩ | 에이전트 바깥 파이썬 순서로 둠(`create_agent`는 반복 1만 맡음) | 해당 없음 |
| Opus 실제 비용 | 결과 메시지의 `usage_metadata`(입력, 캐시, 출력 토큰)를 더함 | 됨 |
| 요청 180초 하드 상한 | `before_model`에서 시각을 보고 끝냄. 툴 실행 중에는 못 끊으므로 툴마다 제한 시간(4.5)이 필요 | 됨(보완 필요) |

| 관점 | 좋은 점 | 걸리는 점 |
|---|---|---|
| 교육 | 「막는 일은 코드」(교재 64쪽 카드 3)가 미들웨어 훅 하나하나로 보임: `before_model` = 상한과 강제 종료, `wrap_tool_call` = 래퍼와 채점. LangChain 1.x의 표준 에이전트 작성법을 익힘 | 새 개념이 늘어남(미들웨어, 훅, `ToolRuntime`, `Command`, `jump_to`). 고리가 프레임워크 안에 있어 ③ → ④ → ⑤ 순서를 코드 한 화면에서 따라가지 못함 |
| 안정성 | 회차 상한과 고리 종료를 프레임워크가 보장함(플로니 지적 「교육생 함수가 틀려도 고리가 끝남」을 내장 미들웨어가 맡음) | 미들웨어 API는 1.x에서 자주 바뀜(판 고정 필요). Opus 5.5의 생각 블록이 고리 안에서 그대로 오가는지는 실측해야 함 |
| 실습 함수 | 13개의 핵심 함수는 그대로 일반 함수로 둠. main의 미들웨어가 이 함수들을 불러 씀(`run_tool`, `diagnose_signals`, `force_stop_reason`) | `agent_step`(bind_tools와 tool_calls 빈칸)은 뜻이 없어짐 → `build_agent`(빈칸: `create_agent`에 모델, 툴, 시스템 프롬프트, 미들웨어 넘기기)로 바꿈 |

**클로니 권고: 조건부 채택.** ③ ~ ⑤(반복 1)만 `create_agent` + 미들웨어 2개(`GuardMiddleware`: `before_model`에서 상한과 강제 종료,  
`ToolWrapperMiddleware`: `wrap_tool_call`에서 래퍼와 채점)로 짜고, ①②와 ⑥ ~ ⑩은 파이썬 순서 그대로 둠. 미들웨어 클래스는  
main에 두고 교육생은 읽기만 함. 조건은 두 가지: ① 개발 첫 단계에서 Opus 5.5 + `ChatAnthropic` + `create_agent`로 툴 2회차  
고리와 `jump_to` 종료를 실측해 통과할 것(실패하면 파이썬 `while`로 돌아감) ② `langchain` 판을 1.4.6으로 고정할 것

### 2.2 LCEL 체인과 구조화 출력(강사 지시, 2026-10-25)

글을 만드는 LLM 호출은 모두 **LCEL 체인**(LangChain Expression Language: `프롬프트 | 모델`처럼 `|`로 단계를 이어 붙이는 문법)과  
**구조화 출력**(`with_structured_output`: LLM이 Pydantic 스키마의 칸을 채운 객체로 답하게 함)으로 짬.  
문자열을 받아 직접 파싱하지 않으므로 「LLM이 형식을 어겨 파싱이 깨지는」 실패가 줄고, 칸 이름이 곧 다음 단계의 입력이 됨.

| 자리 | 체인 | 스키마(Pydantic) | 담는 칸 |
|---|---|---|---|
| G1 보고서 고르기 | `G1_PROMPT \| groq.with_structured_output(PickedReports, method="json_schema", strict=True)` | `PickedReports` | `report_ids`(고른 보고서 id 목록, 최대 12), `reason` |
| G2 주제와 Follow-up 질문 | `G2_PROMPT \| groq.with_structured_output(TopicPlan, ...)` | `TopicPlan`, `Topic` | 주제 1 ~ 5개마다 `title`, `report_ids`, `follow_up`(사실 확인 질문 1개) |
| ⑧ 답변 생성(실습 `generate_answer`) | `ANSWER_PROMPT \| groq.with_structured_output(GroundedAnswer, ...)` | `GroundedAnswer`, `AnswerSentence` | 문장마다 `text`, `citation_ids`(근거 id 목록). 근거가 없으면 문장 0개 |

- 프롬프트는 `ChatPromptTemplate.from_messages([("system", ...), ("human", ...)])`로 main 맨 위에 상수로 둠
- 스키마 칸마다 `Field(description=...)`를 붙여 LLM이 칸의 뜻을 읽게 함(주석 가이드 4.4)
- `method="json_schema", strict=True`: RAG 검색 실습 실측(2026-10-25)에서 strict를 빼면 gpt-oss-120b가 스키마를 되돌려 파싱이 실패함
- ③ 검색 에이전트(Opus)는 체인이 아니라 `create_agent`(2.1)이고, 끝내는 방법은 `finish` 툴(교재 69쪽)임.  
  `create_agent`의 `response_format`(구조화 최종 답)은 쓰지 않음. 답은 ⑧이 만들고 ③은 근거만 모으기 때문임  
- Jev는 LangChain 통합이 없어 SDK를 직접 부르지만, 질문 유형(`Noul`, `Choice`)이 곧 「타입이 정해진 답」이라 구조화 출력과 같은 생각임
- 실습 함수 `generate_answer`의 빈칸 2곳이 바로 이 두 줄임: ① `llm.with_structured_output(GroundedAnswer, ...)` ② `prompt | 구조화 모델`

## 3. 디렉토리 구성

```text
hands-on/solutions/graphrag/
├─ .venv/                      GraphRAG 실습 공용 가상환경(인덱싱과 같음. 패키지 2개 추가)
├─ indexer/                    (기존, 읽기만) 활성 세대 파일, kr_tokenizer.py(질의 토큰화)
└─ retriever/
   ├─ README.md                맨 위에 수업용 명령 2개, 목표와 기능, 구조, 가상환경 설정(PowerShell, Git Bash, macOS와 Linux),
   │                           실행 방법, 출력 읽는 법, 용어 풀이, 실측값
   ├─ .gitignore               data/logs/ 제외(질문별 실행 기록)
   ├─ search_graph.py          main: 설정 상수(기준값, 상한, 제한 시간), 프롬프트(에이전트 시스템, G1, G2, 답변), 툴 6개 명세,
   │                           시작 검사, 저장소 연결, 외부 호출, Opus 비용 계산, 서브 워크플로우 O, L, G, E, R,
   │                           run_workflow(① ~ ⑩과 반복 2개, 하드 상한), 화면 출력, 명령행(--eval 포함)
   ├─ core_search.py           핵심(클론 코딩 대상): 실습 함수 13개 + 선택 1개 + 제공 함수
   ├─ my_search.py             교육생 작업 파일(뼈대). 맨 아래 USE_TEACHER_CODE 목록의 함수는 강사 코드가 대신 돎
   └─ data/
      └─ logs/                 실행 기록(Git 제외). --eval 결과
```

- 교육생이 여는 파일: `search_graph.py`(읽기)와 `my_search.py`(쓰기). 설정 파일은 두지 않고 main 맨 위 상수로 둠
- `kr_tokenizer.py`는 복사하지 않고 import함(색인과 같은 토큰화여야 BM25가 맞음. 읽지 않아도 됨)
- 비밀값: `secrets/.env`를 `dotenv_values()`로 읽어 **네 클라이언트 모두 인자로 넘김**(환경변수에 올리지 않음, 화면에 찍지 않음).  
  키 이름이 SDK 기본값과 달라 인자를 빠뜨리면 다른 키를 집으므로 주의함

  | 키(`secrets/.env`) | 넘기는 곳 | SDK 기본 환경변수(쓰지 않음) |
  |---|---|---|
  | `JEV_API_KEY` | `TypeSafeClient(api_key=...)` | `TYPESAFE_API_KEY` |
  | `GROQ_API_KEY` | `ChatGroq(api_key=...)` | `GROQ_API_KEY` |
  | `COHERE_API_KEY` | `CohereEmbeddings`, `cohere.ClientV2` | `COHERE_API_KEY` |

- Neo4j 비밀번호는 인덱싱과 같음(`NEO4J_PASSWORD` 또는 `backing-services/neo4j/.env`)

## 4. 워크플로우와 실습 함수 선별

방식 선택 기준(인덱싱, RAG 검색 실습과 같음)

- **직접 작성**: 개념이 순수 파이썬 논리(비교, 세기, 정렬, 조건)에 있어 손으로 써야 남는 함수.  
  뼈대는 `raise NotImplementedError("여기에 본인 코드를 작성함")`  
- **빈칸 채우기**: 개념이 라이브러리 호출의 「무엇을 어떤 순서로 부르나」에 있거나, 규칙이 많아 처음부터 쓰면 시간이 넘치는 함수.  
  뼈대는 거의 완성된 코드에 `raise NotImplementedError("빈칸 N을 채울 것")`

실습 함수는 모두 `core_search.py`(정답)와 `my_search.py`(뼈대)에 같은 이름으로 있음. 「하는 일」의 나머지는 main이 제공함.  
래퍼는 「툴 호출을 감싸 필터를 강제로 붙이는 함수」를 뜻함.

| 단계 | 하는 일(main이 부르는 흐름) | 교재 | 실습 함수 | 방식 | 실습 개념 |
|---|---|---|---|---|---|
| ① 요청 접수 | 활성 세대 파일, 검색엔진 인덱스, 그래프 세대, 보고서 수를 읽음(main) → 준비 판정. 「볼 수 있는 청크 표」를 만듦(제공) | 65 | `check_ready` | 직접 | 세 조건(권한, 같은 세대, 보고서 유무). 권한이나 세대가 틀리면 ⑩ 오류, 보고서가 없으면 global_search만 막음. 요청 끝까지 처음 읽은 세대를 씀 |
| ② 질문 분석 | 회원번호를 가명 id로, 카드명과 별칭을 card_id로 바꾸고 질의에서 지움(제공 `replace_identifiers`). Jev 한 요청(Noul 2개 + Choice 1개)과 보기 순서를 바꾼 Choice 1번(main) → 결정 | 65, 66 | `decide_question_route` | 직접 | Jev는 확률만 내고 결정은 코드 기준값: 잡담 0.7 이상 → 검색 불필요, 모호 0.7 이상 → 확인 필요, Choice는 confidence 0.5 이상이고 두 번 답이 같을 때만 첫 툴 후보. 0.3 ~ 0.7이면 검색으로 감 |
| ③ 검색 에이전트 | 시스템 프롬프트, 툴 6개, 미들웨어 2개, 첫 메시지(②의 결과)를 준비하고(main) 에이전트를 만들어 돌림 → 툴 호출 고리 → finish 또는 강제 종료 | 68 | `build_agent` | 빈칸 2곳 | `create_agent(모델, 툴, system_prompt, middleware, context_schema)`로 ReAct 고리를 만듦. 미들웨어가 「막는 일은 코드」를 맡음(`before_model` = 상한과 강제 종료, `wrap_tool_call` = 래퍼와 채점). 메시지는 덧붙이기만 함 |
| ④ 툴 실행(래퍼) | 입력 검사와 막힌 호출 거르기(제공), 래퍼 실행, 결과를 ToolMessage로 덧붙임(main) | 69 | `run_tool` | 빈칸 2곳 | 툴 입력에 필터 칸이 없고 래퍼가 세대와 식별자 필터를 강제로 붙임. 질의 속 회원번호를 지움. 결과를 `<chunk id=...>` 태그로 감쌈(프롬프트 인젝션 방지). 원문은 상태에, 메시지에는 요약 |
| ④ O 검색엔진 검색 | O1 벡터와 O2 BM25를 같은 필터로 OpenSearch에 2번(main) → O3 → O4 리랭크(6개 이하면 건너뜀) | 70 | `rrf_merge` | 직접 | RRF(여러 검색 순위를 합치는 방식) 점수 = Σ 1 / (60 + 순위). 한쪽에만 있어도 합치고 중복을 지운 뒤 상위 25개 |
| ④ L Local 검색 | L1(O 부름) → 청크 엔티티 후보와 질문 유사도(Cypher, main) → 축소 → L3 이웃, L4 보고서(Cypher, main) | 71 | `narrow_entities` | 직접 | 청크마다 가장 가까운 엔티티 1개를 먼저 남기고 나머지를 유사도 순으로 채워 16개. 상담 질문은 첫 상담과 최근 상담을 먼저 고정. 엔티티 0개인 청크(8개)는 건너뜀 |
| ④ G, E, R | G1 보고서 제목 78개 → Groq 고르기, G2 주제와 Follow-up 질문(Groq 구조화 출력), G3 주제별 Local. E1 ~ E4 엔티티 찾기, R1 ~ R2 원문 붙이기(모두 main) | 72, 73 | 선택 과제 `normalize_entity_key`(E1) | 직접 | 레이블마다 키가 다름(카드 「카드」 접미어 빼기, 조항 「제10조①」과 「10조 1항」을 같은 꼴로). G, R은 읽기. 교시 3 끝에 강사가 Q14, Q24로 시연 |
| ⑤ 채점 | 새 원문마다 Jev Noul 4개(main, 캐시) → 판정 표시(제공) → 진단 신호 | 74 | `diagnose_signals` | 빈칸 3곳 | 신호 7개 중 NO_SEED, NO_COOCCUR, PASS의 규칙을 채움(나머지 4개는 완성). 포함률과 공존 문장 수는 제공 함수로 셈. 세는 일은 코드가 함 |
| ⑤ 상한 판정 | 회차, 병렬 5개, global_search 1회, 질의 8개로 호출을 막음(제공) → 강제 종료 판정 → 「남은 회차 N」을 관찰에 덧붙임(main) | 75 | `force_stop_reason` | 직접 | 강제 종료 4조건(회차 6 소진, NO_NEW 2회 연속, 같은 툴과 인자 2회 연속, 툴 전량 실패 2회). 걸리면 모델을 다시 부르지 않고 코드가 종료 상태를 정함 |
| ⑥ 리랭킹 | 모든 회차 원문을 원 질문 기준으로 리랭크(main) → 8자리 → 이어진 엔티티만 남기고 보고서는 걸린 횟수 순(제공) | 76 | `select_final_chunks` | 직접 | 주제(topic_id)마다 1자리를 먼저 맡기고 남은 자리를 점수 순으로 채움. 회차 1회이고 원문 8개 이하면 건너뜀 |
| ⑦ 수집 종료 판정 | 원 질문 핵심 낱말 2개(제공), 근거 엔티티 사이 관계(Cypher, main) → 코드 재확인 → Jev 종합(제공 `decide_collection`) → 통과, 불통과 | 77 | `recheck_question` | 빈칸 2곳 | 조건 ① 핵심 낱말 2개가 한 문장에 함께, ② 두 낱말이 **서로 다른 엔티티의 원문**에 각각 있고 두 엔티티가 관계 하나로 이어짐(IN_COMMUNITY 제외). 둘 다 아니면 불통과(함정 질문을 막음) |
| ⑧ 답변 생성 | 근거를 `<근거>` 태그로 묶어 Groq 호출(main) | 78 | `generate_answer` | 빈칸 2곳 | LCEL 체인 `prompt \| llm.with_structured_output(GroundedAnswer)`(2.2). 문장마다 인용 id. 재작성 피드백과 전제 충돌 표시를 프롬프트에 함께 넣음 |
| ⑨ 근거 검증 | 검사 → 실패면 피드백을 붙여 ⑧ 재작성(최대 2회, main) | 78 | `verify_answer` | 직접 | 검사 3개: 인용 id가 근거 목록에 있음, 답의 숫자와 조항 번호가 인용 원문에 그대로 있음, 보고서 인용은 경향 문장에만(경향 낱말 목록 제공) |
| ⑩ 종료 상태 | 끝난 자리와 이유를 응답으로 묶고 화면과 로그에 남김(main) | 79 | `make_end_state` | 빈칸 1곳 | 종료 상태 7가지(교재 79쪽 표)와 돌려줄 것(답, 근거 목록, 경고). 「확인할 수 없음」도 정상 종료 |

- 합계 13개: 직접 7개(`check_ready`, `decide_question_route`, `rrf_merge`, `narrow_entities`, `force_stop_reason`,  
  `select_final_chunks`, `verify_answer`), 빈칸 6개(`build_agent`, `run_tool`, `diagnose_signals`, `recheck_question`,  
  `generate_answer`, `make_end_state`). 선택 과제 1개(`normalize_entity_key`)  
- 제공 함수(읽고 이해, 클론 대상 아님): `replace_identifiers`, `strip_identifiers`, `allowed_chunk_ids`, `wrap_chunks`,  
  `core_terms`(핵심 낱말), `coverage`(포함률), `count_cooccur`(공존 문장 수), `apply_passage_judgments`(Jev 확률 → 표시),  
  `block_calls`(병렬, global 1회, 질의 8개), `decide_collection`(⑦ Jev 종합), `keep_linked_entities`  
- main 제공(읽기): 시작 검사, 저장소와 외부 API 호출, Opus 비용 계산, O1, O2, Cypher, G1, G2, E, R, run_workflow, 화면 출력
- 핵심 낱말(`core_terms`)은 숫자와 버전(예: 1.1), 카드명, 조항 번호를 먼저 고름. Q20(「이전 버전(1.1)」)이 ⑦ 조건 ②로  
  통과하지 않게 하기 위함임(지식니 실측: 약관 문서 노드 1개가 조항 52개와 HAS_CLAUSE로 이어져 있어 ②가 헐거워지기 쉬움)

### 4.1 반복 구간과 상한(run_workflow)

| 반복 | 단계 | 상한 | 착지 |
|---|---|---|---|
| 반복 1 | ③ → ④ → ⑤ → ③ | 툴 호출 회차 6(= Opus 호출 6번), 한 회차 병렬 5, global_search 1회, 서로 다른 질의 8개(find_entities의 entity_key는 세지 않음) | finish, 툴 호출 없는 응답, 강제 종료 → ⑥ |
| 반복 2 | ⑧ → ⑨ → ⑧ | 재작성 2회(⑧ 최대 3번) | ⑩ 확인 필요(답과 경고) |

- 회차 6의 뜻: 6회차의 툴 결과를 받은 뒤에는 Opus를 다시 부르지 않고 코드가 끝냄(숨은 7회차 없음).  
  교재 75쪽의 「더 부를 수 없음. 지금 근거로 finish할 것」(`is_error`)은 회차 안의 개별 상한(병렬 6번째, global_search 2번째,  
  질의 9번째)에 걸린 호출과 입력 오류에만 돌려줌  
- finish도 툴 호출도 없는 응답(`end_turn`)은 강제 종료와 같이 처리함: 코드가 ⑦ 기준으로 sufficient 또는 unverifiable을 정함
- **하드 상한(main)**: 교육생의 `force_stop_reason`과 상관없이 main이 Opus 호출 6번, 요청 전체 180초에서 고리를 끊음.  
  함수를 잘못 채워도 고리가 끝남(플로니). 「Opus 6번」은 응답을 받은 호출 수이며 429와 529 재시도는 세지 않음.  
  `--eval`(평가셋 일괄)에서는 정상 문항이 잘리지 않게 요청 제한 시간을 600초로 둠(Advisor)  
- **교육생 함수 예외**: 감추지 않고 화면에 띄운 뒤 그 요청을 ⑩ 오류로 끝냄. Opus를 다시 부르지 않으므로 툴 호출과 결과의 짝이  
  깨진 대화가 API로 가지 않음(커넥니)  
- 화면에 상한 소비량을 찍음: 「회차 2/6」, 「질의 3/8」, 「global_search 0/1」, 「재작성 1/2」, 「Opus 3번, Jev 5번, Groq 2번」

### 4.2 툴 명세(교재 69쪽, 래퍼가 검사)

Anthropic 툴 정의에는 서버 쪽 검사 옵션이 따로 없다고 보고 래퍼가 입력을 다시 검사함. 모르는 키(필터 칸 흉내 포함)는 입력 오류.

| 툴 | 입력과 제약 | 결과(메시지에 보내는 것) |
|---|---|---|
| `search_vector-bm25` | `query` 문자열(빈 문자열 금지) | 청크 최대 6개(태그로 감싼 앞부분), 신호 |
| `local_search` | `query` 문자열, `topic_id` 문자열 또는 null(global_search가 매긴 번호만) | 청크 6, 엔티티 16, 이웃, 보고서 3의 요약, 신호 |
| `global_search` | `query` 문자열. 요청당 1회, 보고서 없는 세대면 입력 오류 | 주제(topic_id, Follow-up 질문)와 주제별 원문 요약, 미확인 주제, 신호 |
| `find_entities` | `entity_key` 문자열. 질의 수에 세지 않음 | 엔티티와 1-hop 이웃(원문 없음). 0건이면 가까운 후보 3개(오류 아님) |
| `get_source_chunks` | `entity_ids` 문자열 배열 1 ~ 16개, `with_reports` 불리언 | 원문 청크(권한 표로 다시 거름), 보고서 |
| `finish` | `status`는 sufficient, unverifiable, need_clarification 중 하나, `reason` 문자열 | - |

### 4.3 에이전트 실제 비용 표시(강사 결정. v1.3부터 Groq 에이전트 비용)

| 항목 | 규칙 |
|---|---|
| 계산 | ③ 에이전트 응답마다 API가 돌려준 사용량(입력, 캐시된 입력, 출력 토큰. 추론 토큰은 출력에 들어 있음) × main 맨 위 단가 상수(100만 토큰당. Groq 공식 모델 문서: 입력 $0.15, 캐시된 입력 $0.075, 출력 $0.60) |
| 표시 | 질문마다 ⑩ 아래 「에이전트(Groq) 비용 $0.00000(호출 N번, 입력 N, 캐시 읽기 N, 출력 N 토큰)」 한 줄. `--eval`은 문항별 값과 합계를 로그와 화면에 남김 |
| 표시하지 않음 | Jev, G1, G2, ⑧의 Groq, Cohere 비용(강사 결정: 에이전트 실제 비용만). 추정값은 쓰지 않음 |
| 재시도 | 실패한 호출은 사용량이 없으면 0으로 셈. 그래서 화면 값은 「응답을 받은 호출의 실제 사용량」임 |

- `--eval`은 문항마다 바로 로그에 쓰고 `--start Q10`으로 중간부터 이어 함(플로니)
- 에이전트 응답은 대화 이력에 그대로 덧붙임(이전 턴을 고치지 않음. 앞부분이 같으면 Groq가 자동으로 캐시함)
- 같은 질문이라도 에이전트 결과가 실행마다 다를 수 있음(temperature 0이어도). 교육생은 강사와 같은 툴 경로가 아니어도  
  5.1 표의 정상 기준(신호, 판정, 종료 상태)으로 자기 함수를 확인함

### 4.4 권한 필터(지식니 실측 반영)

| 대상 | 규칙 |
|---|---|
| 청크 | 「볼 수 있는 청크 표」: agent는 public만, auditor는 전부, auditor + 회원은 public과 그 회원의 restricted. O1, O2 필터와 R2가 이 표를 씀 |
| 엔티티 | 엔티티가 나온 청크(FROM_CHUNK)가 **모두** 표에 있을 때만 씀. L2, L3, E2 ~ E4의 Cypher에 같은 조건을 걺(2번째 쿼리 포함) |
| 커뮤니티 보고서 | 구성 엔티티가 모두 볼 수 있을 때만 씀. 상담 커뮤니티 13개는 모두 회원 한 명의 것이라(실측), agent에게는 보이지 않음. G1, L4, R1에 적용 |

- 경향 질문(Q23 ~ Q25)은 평가셋 기록대로 auditor(회원 지정 없음)로 실행함. agent로 물으면 상담 보고서 없이 답함

### 4.5 외부 API 제한 시간과 실패 대체

| 자리 | 제한 시간, 재시도 | 실패 뒤 대체 |
|---|---|---|
| ② Jev | 20초, SDK 재시도(retry-after) | 잡담과 모호 종료 없이, 첫 툴 후보 없이 ③으로. 경고(Jev를 끄는 옵션은 두지 않음. 장애 때만 이 경로) |
| ③ 에이전트(Groq) | 90초, 429와 5xx는 백오프 재시도 4번 | 모은 근거로 ⑥에 감(코드가 종료 상태를 정함). 첫 회차면 ⑩ 오류 |
| ④ OpenSearch, Neo4j | 10초, 재시도 없음 | 한쪽만 죽으면 남은 쪽 결과와 경고(부분결과). Neo4j가 죽으면 원문만 |
| ④ O4, ⑥ 리랭크 | 30초, 재시도 1번 | RRF 순위 그대로 |
| ④ G1, G2 Groq | 60초, 재시도 2번(인덱싱과 같은 `max_retries`) | 보고서 벡터 상위 5개, 질문은 제목 + 요약 첫 문장 |
| ⑤, ⑦ Jev | 20초 | ⑤는 원문을 모두 관련으로 셈, ⑦은 코드 재확인 결과만 씀 |
| ⑧ Groq | 60초, 재시도 2번 | ⑩ 생성 실패(근거 목록만) |
| 요청 전체 | 180초(하드 상한) | 그때까지 모은 근거로 ⑥ |

- 값은 출발값이며 실측 뒤 README에 고침

## 5. 실습 순서와 교시 배치(안)

함수는 워크플로우 순서대로 채움. 뼈대 맨 아래 `USE_TEACHER_CODE` 목록 덕분에 앞 교시에서 막혀도 전체가 완주됨.

| 교시 | 내용 | 함수(순서대로, 예상 줄 수) | 직접 : 빈칸 | 교시 끝에 확인할 것 |
|---|---|---|---|---|
| 1 | 교재 64 ~ 79쪽 이론, 강사 화면으로 ① ~ ⑩ 출력 읽기, 교체 방법 시연 | - | - | 함정 질문(Q19)이 ⑦ 불통과로 끝나는 화면 |
| 2 | ① ~ ④ 래퍼 | `check_ready`(15) → `decide_question_route`(25) → `build_agent`(20) → `run_tool`(30) | 2 : 2 | 5.1 표의 ① ~ ④ |
| 3 | ④ O, L과 ⑤ | `rrf_merge`(20) → `narrow_entities`(30) → `diagnose_signals`(40) → `force_stop_reason`(20). 남으면 `normalize_entity_key`(20) | 3 : 1 | 5.1 표의 ④ O, L, ⑤ |
| 4 | ⑥ ~ ⑩ | `select_final_chunks`(25) → `recheck_question`(30) → `generate_answer`(20) → `verify_answer`(35) → `make_end_state`(15) | 2 : 3 | 5.1 표의 ⑥ ~ ⑩ |

- 교시 4는 다섯 개이나 `make_end_state`(빈칸 1곳, 15줄)와 `generate_answer`(빈칸 2곳)는 짧음. 넘치면 `make_end_state`를 숙제로 돌림
- 수업 중 실행은 모두 실제 호출이며 교육생도 키 3개(Jev, Groq, Cohere)가 필요함. 에이전트 비용은 실행마다 화면에 찍힘(질문당 1센트 미만).  
  함수 하나를 고칠 때마다 Q01 한 번만 돌려 확인하고, 여러 질문은 교시 끝에 한 번 돌림  
- 수업용 질문: Q01(약관 사실), Q02(상위 청크에 없고 엔티티가 메우는 예), Q14(회원 상담, find_entities), Q19(함정).  
  강사 시연: Q24(경향, global_search, auditor)

### 5.1 교육생 확인표(화면 출력 항목과 정상 기준)

| 실습 함수 | 확인 명령(예) | 화면에서 볼 것 | 정상 기준(실측 뒤 README에 숫자 확정) |
|---|---|---|---|
| `check_ready` | `--qid Q01`, `--role guest`(없는 역할) | 세대, 보고서 수, 볼 수 있는 청크 수 | Q01은 「준비 완료」, 없는 역할은 ⑩ 오류 |
| `decide_question_route` | `--qid Q01`, `"안녕하세요"` | Jev 확률 3개와 순서 바꾼 Choice, 코드의 결정 | 잡담은 검색 0회로 끝, Q01은 첫 툴 후보가 찍힘 |
| `build_agent` | `--qid Q01` | 회차마다 툴 이름과 인자, 미들웨어가 붙인 「남은 회차」 | 툴 이름이 6개 중 하나, 인자가 명세와 맞음(Opus는 실행마다 고르는 툴이 다를 수 있음) |
| `run_tool` | `--qid Q14 --role auditor --member-id M-1042` | 래퍼가 붙인 필터, 지운 식별자, 태그로 감싼 관찰 | 질의에 M-1042가 없음, 다른 회원 청크 0건 |
| `rrf_merge` | `--qid Q01` | 벡터 순위, BM25 순위, RRF 점수 | 두 검색에 모두 나온 청크가 위로, 점수 내림차순 |
| `narrow_entities` | `--qid Q01` | 후보 엔티티 수 → 16개, 청크별 보장 1개 | 청크마다 1개 이상, 합계 16 이하 |
| `diagnose_signals` | `--qid Q01`, `--qid Q19` | 포함률, 공존 문장 수, 신호와 권장 행동 | Q01은 PASS, Q19는 NO_COOCCUR |
| `force_stop_reason` | `--qid Q19` | 회차별 남은 회차, 강제 종료 이유 | 같은 질문이면 같은 이유 |
| `select_final_chunks` | `--qid Q24 --role auditor` | 주제별 맡긴 자리와 점수 순 자리 | 모든 주제가 1자리 이상 |
| `recheck_question` | `--qid Q01`, `--qid Q19` | 핵심 낱말 2개, 조건 ①, ② 결과 | Q01 통과, Q19 불통과 |
| `generate_answer` | `--qid Q01` | 문장별 인용 id | 인용 없는 문장 0개 |
| `verify_answer` | `--qid Q01` | 검사 3개 결과, 실패 사유, 재작성 횟수 | 「검증 통과」 또는 사유와 「재작성 1/2」 |
| `make_end_state` | 위 명령 모두 | 종료 상태 이름과 이유 | 교재 79쪽 표의 이름과 같음 |

## 6. 교체 방법

1. `my_search.py`에 같은 이름, 같은 인자의 함수를 채움
2. `search_graph.py`의 import 한 줄을 바꿈: `import core_search as core` → `import my_search as core`
3. `my_search.py` 맨 아래 `USE_TEACHER_CODE` 목록에서 지금 채운 함수 이름을 지움(남은 함수는 강사 코드가 대신 돎)
4. 같은 명령으로 다시 실행해 5.1 표대로 강사 결과와 비교함. 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감

## 7. 실행 모드와 비용

| 모드 | 명령(예) | 용도 |
|---|---|---|
| 평가셋 질문 | `search_graph.py --qid Q01` | 수업 중 함수 확인. 역할은 평가셋 `filters`대로 자동 |
| 자유 질문 | `search_graph.py "질문" --role agent` | 강사 시연, 교육생 실험 |
| 평가셋 일괄 | `search_graph.py --eval`(`--start Q10`으로 이어 하기) | 강사 사전 실행 25문항. 근거 적중, 함정 거절, Opus 비용 합계 |
| 답변 끔 | 위 명령 + `--no-answer` | ⑧ Groq 0번. ⑩ 「검색 결과」(근거 목록만) |

- 비용: 화면과 로그에는 Opus 실제 비용만 찍음(4.3). 계획 단계 추정은 질문당 약 $0.1 ~ 0.2, 25문항 1회 약 $5 ~ 10이며  
  강사 승인 예산은 25문항 1회 + 함정 5문항 3회 반복. 실측 합계는 README에 적음  
- 역할: `--role agent`(public만), `--role auditor`(전부), `--role auditor --member-id M-1042`(public과 그 회원 상담).  
  `--eval`은 평가셋 `filters`에 회원이 있으면 auditor + 그 회원, 경향 문항은 auditor, 나머지는 agent(RAG 실습과 같은 규칙)  
- 로그 파일 이름에는 문항 번호와 시각만 씀(회원번호를 쓰지 않음)

## 8. 모델과 패키지

| 항목 | 값 |
|---|---|
| 검색 에이전트(③) | **v1.3: Groq `openai/gpt-oss-120b`**(`ChatGroq`, temperature 0, reasoning_effort medium). v1.2까지는 Anthropic Claude Opus 5.5(`ChatAnthropic`, effort medium) |
| 판단(②, ⑤, ⑦) | TypeSafe Jev `jev-1.14.0` 고정. `typesafe-sdk 0.7.5`(LangChain 통합이 없어 SDK 직접 사용). 질문 문장은 영어, 자료(state)는 한국어 그대로 |
| 보조와 답변(G1, G2, ⑧) | Groq `openai/gpt-oss-120b`. `langchain-groq 1.1.3`. LCEL 체인 + `with_structured_output(Pydantic 스키마, method="json_schema", strict=True)`(2.2) |
| 임베딩 | Cohere `embed-v5.0-fast` 2048차원, 질문은 `embed_query`(search_query). `langchain-cohere 0.6.0` |
| 리랭커(O4, ⑥) | Cohere `rerank-v4.0-fast`. `cohere.ClientV2.rerank`(LangChain `CohereRerank`는 점수를 메타데이터에 숨겨 SDK 직접 사용, RAG 검색과 같은 결정) |
| 저장소 | `neo4j 6.4.1`(Cypher, `vector.similarity.cosine`), `opensearch-py 3.0.0`(kNN과 BM25 질의 2번) |
| 토큰화 | 인덱싱 실습 `kr_tokenizer.py`(Kiwi, 카드 별칭) |
| Python | 3.13, 공용 가상환경 `hands-on/solutions/graphrag/.venv`(D5) |

- 새 패키지 2개는 설치 뒤 기존 판(langchain-core 1.6.12)과 충돌이 없는 판으로 고정함
- context7은 월 한도 초과로 응답하지 않음(2026-10-25 확인). 설치된 패키지 소스와 공식 문서 사본(`.temp/jev/`)으로  
  시그니처(`ChatAnthropic`의 effort와 툴 호출, `TypeSafeClient.system_one`)를 확인함

## 9. 사전 과제와 환경 점검(교육생)

| 번호 | 과제 | 확인 방법 |
|---|---|---|
| 1 | GraphRAG 인덱싱 실습 완료(전체 세대. 또는 `--reuse data/teacher`로 강사 배포본 재색인) | `indexer/data/active_generation.json`이 있고 `chunk_count` 260 |
| 2 | Neo4j와 OpenSearch 기동 | `docker compose ... ps`가 둘 다 `healthy` |
| 3 | 공용 가상환경에 새 패키지 2개 설치(README 3장) | 설치 확인 명령이 `ok` |
| 4 | `secrets/.env`에 키 3개(`JEV_API_KEY`, `GROQ_API_KEY`, `COHERE_API_KEY`) | `search_graph.py --qid Q01`이 ⑩까지 끝나고 에이전트 비용이 찍힘 |

`search_graph.py`의 시작 검사가 1 ~ 4를 한 번에 확인하고 빠진 것과 할 일을 출력함.  
교육생 세대를 `--reuse data/teacher`로 만들면 청크와 엔티티가 강사와 같아 5.1 표의 숫자를 그대로 비교할 수 있음.

## 10. 용어 풀이(README와 실습 가이드에 넣음)

ReAct(생각하고 툴을 부르고 결과를 보고 다시 생각하는 방식), RRF, 래퍼, 진단 신호 7개(PASS 충분함, NO_COOCCUR 함께 나옴 없음,  
NO_SEED 검색 결과 없음, LOW_COVERAGE 질문 일부만 근거 있음, SCATTERED 근거가 여러 문서에 흩어짐, NO_REPORTS 관련 보고서 없음,  
NO_NEW 새 원문 없음), Noul(참일 확률), Choice(보기 고르기), confidence(확신), 함정 질문, 생각 토큰(Opus가 답 전에 쓰는 생각.  
출력 요금으로 셈)

## 11. 검증 계획(정직한 보고 기준)

| 검증 | 완료 기준 |
|---|---|
| 경로별 실행 | 잡담(검색 불필요), 모호(확인 필요), 약관 사실, 회원 상담(find_entities → get_source_chunks), 함정(⑦ 불통과 → 확인할 수 없음), 경향(global_search), 강제 종료, 인용 검증 실패 → 재작성을 각각 실제 질문으로 한 번 이상 실행해 화면 기록 |
| 함정 질문 차단 검사 | 함정 Q18 ~ Q22 다섯 문항이 모두 「확인할 수 없음」을 **3회 반복 모두**에서 지킴(5/5 × 3) |
| 근거 적중 | 답 있는 20문항: 평가셋 `relevance.any_of` 문구가 ⑥ 뒤 원문이나 엔티티 설명에 그대로 있으면 적중. 목표 16/20 이상(가정값, 실측 뒤 README에 기록) |
| 권한 | 같은 상담 질문을 agent(상담 원문과 상담 보고서 0건)와 auditor + 회원(그 회원 것만)으로 실행. 다른 회원 청크와 보고서가 0건 |
| 실패 대체 | Jev, 리랭크, Groq 예외를 일부러 일으켜(잘못된 모델명) 4.5 표대로 도는지 확인. 하드 상한(180초, Opus 6번) 동작 확인 |
| Opus 비용 표시 | 화면 값이 응답 사용량 × 단가와 맞음(한 문항 손계산 대조). `--eval` 합계를 README에 기록. 로그에 회원번호 원문과 키가 없음(grep) |
| 뼈대 교체 | `my_search.py`를 정답으로 채운 사본이 같은 결과. 빈 뼈대는 목록 덕분에 완주, 목록에서 지운 함수만 `NotImplementedError` |
| 주석 | `references/dev-comment-guide.md` 10장 체크리스트, 핵심 파일은 줄 단위 주석 |

## 12. 작업 순서

1. 개발계획서 초안 → 팀원 리뷰(완료) → 최종안(이 문서) → 강사 승인(13장)
2. 패키지 설치와 시그니처 확인 → `core_search.py` → `search_graph.py`
3. 경로별 실행 → 기준값 확인 → `--eval`(25문항) → 함정 3회 반복 → Opus 비용 대조
4. `my_search.py` 뼈대 → 교체 경로 확인 → README
5. 교육생 실습 가이드(마크다운) → 핵심 슬라이드(상세는 원격 Git 링크) → 렌더링 검증
6. 교재 코드 예시 장표(D7): 단계별 설명 장 뒤에 코드 장을 하나씩 넣음. 장표 스크립트 → 빌드 → 렌더링 확인 → 교재 백업 → 삽입

### 12.1 교재 코드 예시 장표(D7, 강사 결정)

| 항목 | 내용 |
|---|---|
| 넣는 자리 | 64 ~ 79쪽의 단계별 설명 장 바로 뒤(①②, ③, ④ 래퍼, ④ O, ④ L, ④ G, ④ E와 R, ⑤ 채점, ⑤ 상한, ⑥, ⑦, ⑧⑨, ⑩). 설명 장 하나에 코드 장 하나가 원칙이며 짧은 단계는 한 장에 묶음(장 수는 스크립트 작성 때 확정해 보고) |
| 장 구성 | 왼쪽: 실제 소스(`core_search.py`, `search_graph.py`)에서 발췌한 코드. 중요한 줄에 일련번호 표시(단계 번호 ① ~ ⑩과 헷갈리지 않게 ❶, ❷, ❸ …). 오른쪽: 일련번호별 설명(무엇을 왜 하는지). 아래: 출처 파일과 함수 이름 |
| 발췌 규칙 | 실제 소스에서 발췌기가 자동으로 꺼냄. docstring, 줄 전체 주석, 줄 끝 주석은 빼고(설명은 오른쪽 칸) 나머지 글자는 소스 그대로. 생략은 `...` 한 줄로만 표시. 코드를 고치면 발췌와 빌드, 넣기를 다시 돌림 |
| 형식 | `references/pptx-guide.md` 준수, 글꼴 Pretendard, 링크는 눌리게(교훈 목록). 미리보기는 `scripts/render-pptx.py`(LibreOffice) |
| 교재 반영 | 백업(`backup/…backup-YYYYMMDD-graph-search-code.pptx`) 뒤 삽입. 79쪽 「검색 단계의 실제 코드는 구현 뒤 이 자리에 덧붙입니다」 노트 문구는 지움. 71쪽 「L2 ~ L4는 Cypher 한 번」은 코드 장에서 「실습 예제는 2번」으로 밝힘 |

## 13. 결정 사항과 승인 요청

| 번호 | 항목 | 제안 | 대안 | 팀 의견 |
|---|---|---|---|---|
| D1 | 흐름 구현 | **강사 승인(2026-10-25).** ③ ~ ⑤는 LangChain `create_agent` + 미들웨어 2개, 나머지는 파이썬 순서. 실측 실패 시 `while`로 | 처음 안: 파이썬 `while`과 `if`(`run_workflow` 한 함수) / LangGraph `StateGraph` 직접 | 플로니는 처음 안(`while`)에 찬성했음. `create_agent`는 플로니 지적(고리 종료 보장)을 내장 미들웨어가 맡아 더 안전함 |
| D2 | 실습 함수 수와 교시 | **강사 승인: 13개**(직접 7, 빈칸 6, `agent_step`은 `build_agent`로) + 선택 1개, 이론 1교시 + 클론 코딩 3교시 | 에듀니 11개 / Advisor 8개 안팎 | 에듀니는 `make_end_state` 제외 11개를 권함. 그러면 ⑩에 실습이 없어 강사 요구(단계마다 1개)와 어긋나 13개 유지. `judge_collection`은 권고대로 코드 재확인만 남김 |
| D3 | 녹화 재생, Jev 끔 옵션 | **강사 결정(2026-10-25): 두지 않음.** 모든 실행이 실제 호출. 교육생도 키 4개 필요 | - | Advisor가 지적한 「교육생마다 결과가 갈림」은 5.1 정상 기준을 툴 경로가 아니라 신호, 판정, 종료 상태로 잡아 대응 |
| D4 | 에이전트 모델 | **강사 결정 변경(2026-10-25): Groq gpt-oss-120b로 바꿈**(15.2 비교 실험 뒤, 16장) | 처음 결정: Opus만, 대체 모델 없음 | 처음에는 Advisor, 커넥니가 Groq 툴 호출 불안정을 우려했으나, 실험에서 품질이 거의 같았음 |
| D5 | 가상환경 | 인덱싱 공용 `graphrag/.venv`에 2개 추가 | `retriever/.venv` 따로 | - |
| D6 | API 비용 | **강사 결정: 승인**(25문항 1회 + 함정 5문항 3회). **결과에는 Opus 실제 비용만 표시**(4.3) | - | - |
| D7 | 교재 장표 | **강사 결정: 단계별 설명 장 뒤에 코드 예시 장을 추가.** 중요 코드에 일련번호, 오른쪽에 번호별 설명(12.1) | - | 에듀니 제안을 강사가 넓힘 |

## 14. 검토 이력

| 단계 | 내용 |
|---|---|
| Advisor 사전 자문(Opus) | 「함수 16개, 외부 서비스 5종은 초보에게 많음. ③, ⑤, ⑦ 중심으로 줄이고, 키 누락과 한도 초과로 교육생마다 결과가 갈리지 않게 녹화 응답 재생 모드를 둘 것」. 반영: 16 → 13개(G, E, R은 읽기), 녹화 재생(D3). 8개 축소는 D2로 넘김 |
| 초안 v0.1 | 클로니 작성. 교재 64 ~ 79쪽, 설계 문서 v1.4와 v2.2, 인덱싱 예제 구조, 그래프 실측(Chunk 노드에 권한 속성 없음) 대조 |
| 에듀니 검토 | 수정 후 사용. 반영 7건: 교육생 확인표(5.1), 예상 줄 수, `judge_collection`을 `recheck_question`(코드 재확인)으로 줄이고 Jev 종합은 제공, 교재 장표 갱신(D7), 용어 풀이(10장), `normalize_entity_key`를 교시 3에 배치, 용어 다듬기(하드 게이트 → 함정 질문 차단 검사, 래퍼 풀이). 받지 않음 2건: `diagnose_signals` 직접 전환(신호 7개를 처음부터 쓰면 교시 3이 넘침. 3개만 빈칸), `make_end_state` 제외(D2) |
| 플로니 검토 | 수정 후 통과. 반영 8건: main 하드 상한(Opus 6번, 180초), 회차 6의 뜻(숨은 7회차 없음), 호출별 제한 시간과 재시도(4.5), Opus 429와 529 재시도, 녹화 키 산식(생각 블록 제외, 호출 순서), 녹화 미스 동작, 생각 블록을 서명째 저장, `end_turn` 처리와 녹화 이어하기 |
| 지식니 검토 | 조건부 승인(그래프 실측). 반영 8건: 보고서 권한 필터(상담 커뮤니티 13개가 모두 회원 1명), 엔티티 수 1,673으로 정정, find_entities 키에 `member_pseudo_id` 포함(교재 73쪽 표대로. 키 속성이 있는 엔티티는 432/1,673이라 나머지는 E3 후보로 닿음), ⑦ 조건 ②를 「서로 다른 엔티티의 원문」으로 한정하고 핵심 낱말에 숫자와 버전 우선, L3 이웃의 권한 조건, 엔티티 0개 청크, NO_REPORTS 정의로 OFF_TOPIC 흡수, 적중 판정과 합격선 수치. 수업용 질문을 Q01, Q02, Q14, Q19로(Q20은 위험 문항이라 검증에서만 봄) |
| Advisor 마무리 점검(Opus) | 「승인 요청 가능, 반드시 고칠 결함 없음」. 권고 2건 반영: 하드 상한에 재시도를 세지 않음, 일괄 실행의 제한 시간을 따로 둠(4.1) |
| 강사 결정(2026-10-25) | 녹화, 재생, Jev 끔 옵션 제거(D3). API 비용 승인, 결과에는 Opus 실제 비용만 표시(D6, 4.3). 교재 단계별 설명 뒤 코드 예시 장 추가(D7, 12.1). 개발 시작과 D2(함수 수)는 확인 요청 중 |
| 강사 지시(2026-10-25) | LCEL 체인과 구조화 출력 사용을 명시(2.2) |
| 강사 승인(2026-10-25) | 「③ ~ ⑤는 create_agent + 미들웨어 2개로, 실습 함수 13개(agent_step은 build_agent로)로 개발 시작. Opus 실측이 실패하면 while로」 |
| 커넥니 검토 | 수정 후 승인. 반영 7건: 툴 명세와 래퍼 입력 검사(4.2), 교육생 함수 예외 때 Opus를 다시 부르지 않음, `dotenv_values()`로 네 키 모두 인자 전달, 키 이름과 SDK 기본값 표, 녹화 키는 식별자를 지운 질문, 응답 본문만 저장, `.gitignore`와 로그 이름 규칙. 받지 않음 1건: `find_entities` 입력을 `text`로 통일(현재 교재 69쪽은 `entity_key`. 커넥니가 본 슬라이드 스크립트는 교재 직접 수정 전 판) |

## 15. 개발 결과(2026-10-25)

| 산출물 | 경로 | 상태 |
|---|---|---|
| 예제 프로그램 | `hands-on/solutions/graphrag/retriever/`(search_graph.py, core_search.py, my_search.py, README.md, .gitignore) | 완료 |
| 교육생 실습 가이드 | `teacher/plan/graphrag-search-실습가이드.md` | 완료 |
| 핵심 슬라이드 | `teacher/plan/graphrag-search-실습가이드.pptx`(6장, 스크립트 `…-slides.md`, 빌드 `build/build-search-guide-slides.js`) | 완료. 붙여넣기 호환 점검 OK, LibreOffice 미리보기 6장 확인 |
| 교재 코드 예시 장표(D7) | 교재 『W05 ~ W07』 66, 70, 72, 74, 76, 78, 80, 82, 84, 86, 88, 90, 91, 93쪽(14장, 교재 80 → 94쪽) | 완료. 스크립트 `teacher/plan/graph-search-code-slides.md`, 발췌 `build/extract-graph-search-code.py`(실제 소스에서 자동 발췌), 빌드 `build/build-graph-search-code.js`, 넣기 `build/merge-graph-search-code.py`. 백업 `backup/…backup-20261025-graph-search-code.pptx`. 하이퍼링크 8개 그대로, LibreOffice로 94쪽 렌더링 확인 |

검증(11장 기준) 결과

| 검증 | 결과 |
|---|---|
| Opus + create_agent 실측(D1 조건) | 통과. 3회차 고리, before_model의 jump_to 강제 종료, wrap_tool_call 덧붙임, ToolRuntime context, 생각 블록 보존(400 없음) |
| 경로별 실행 | 약관 사실(Q01), 회원 상담(Q14 ~ Q17), 함정(Q18 ~ Q22), 경향(Q23 ~ Q25), 인용 검증 실패 → 재작성(Q25), 답변 끔(--no-answer), 실습 함수 예외 → ⑩ 오류 확인. 잡담과 모호는 Jev 판정까지 확인 |
| 함정 질문 차단 검사 | 15/15(5문항 × 3회). ⑦이 14번, 에이전트가 1번 먼저 멈춤. 마지막 25문항 실행에서는 5/5 모두 ⑦이 막음 |
| 근거 적중 | 18/20(목표 16/20 이상 달성). 빗나간 Q02, Q05도 답은 정답과 같음(평가셋 문구와 원문 글자 차이) |
| 답변 완료 | 답 있는 20문항 중 18개. 오거절 Q14(「해지」와 「정리」 낱말 차이), Q16(Jev 답 근거 확률 낮음) |
| 권한 | 회원 질문은 그 회원 청크와 public만 보임(볼 수 있는 청크 216개), agent는 212개(public만). 상담 커뮤니티 보고서는 agent에게 0개(65개만 보임) |
| Opus 비용 표시 | 25문항 합계 $0.75, 응답 usage(입력, 캐시 읽기, 캐시 쓰기, 출력) × 단가로 계산 |
| 뼈대 교체 | 강사 코드 목록 그대로 Q05 완주, 목록에서 rrf_merge를 지우면 「실습 함수 오류」와 NotImplementedError로 ⑩ 오류 |
| 주석 | 줄 길이 120자 이내, pyflakes 통과(뼈대의 빈칸 변수는 의도된 미정의) |

개발 중 바꾼 것(README 7.4에 상세)

- ② 「모호함」 Jev 질문 문장, 핵심 낱말 순서, ⑦ 조건 ② 후보 쌍(속성 기준 추가), ⑦ 답 근거에 관련 확률 0.7 이상,  
  ⑦에서 ⑤ 판정 재사용, 카드 필터 이름 키 버그 수정, 회원 상담 원문은 관련 확률로 빼지 않음  
- context7 MCP가 월 한도 초과라 `secrets/.env`의 `CONTEXT7_API_KEY`로 REST API를 불러 LangChain 문서를 확인함(교훈 목록에 추가)
- 실제 API 비용(Opus): 개발과 검증 전체 약 $5(평가셋 25문항 4회, 함정 3회 반복 2번, 단건 실행 포함). 승인 예산 안

### 15.1 교재 코드 예시 장표(D7) 반영 기록(2026-10-25)

- 넣은 자리: ② 질문 분석(66쪽), ③(70), ④ 래퍼(72), O(74), L(76), G(78), R(80), ⑤ 채점(82), ⑤ 상한(84), ⑥(86), ⑦(88), ⑧(90), ⑨(91), ⑩(93).  
  ①은 단계가 짧아 ② 장에 묶고, ⑧과 ⑨는 코드가 길어 한 장씩 둠
- 모양: 교재 48, 61쪽 코드 장표와 같게 왼쪽 실제 코드(Pretendard 14pt), 오른쪽 번호별 설명. 번호는 ❶ ❷ …(단계 번호와 구분)
- 코드 상자는 교재 다른 장(본문 끝 7.9in)보다 조금 아래(8.1in)까지 씀. 긴 함수(⑨ 22줄)가 들어가게 하려는 것임
- 92쪽(⑩ 설명 장) 발표자 노트의 「검색 단계의 실제 코드는 구현 뒤 이 자리에 덧붙입니다」를 「실제 코드는 다음 장에 있습니다」로 바꿈
- 그래프 검색 장표 교체 스크립트(`merge-graph-search-textbook.py`)는 코드 예시 장표가 있으면 멈추게 고침(지워지지 않게)

### 15.2 비교 실험: ③ 에이전트를 Groq로 바꾸면(2026-10-25, 강사 요청)

③ 검색 에이전트 모델만 Opus 5.5에서 Groq `openai/gpt-oss-120b`로 바꾸고 나머지(②, ⑤, ⑦ Jev, G1, G2, ⑧, 기준값, 미들웨어)는 그대로 둠.  
제품 코드는 바꾸지 않고 스크래치 스크립트로 모델만 끼워 돌림(D4 결정 유지). Opus 쪽은 15장의 마지막 25문항 실행과 함정 3회 반복 값임.

| 항목 | Opus 5.5 | Groq gpt-oss-120b |
|---|---|---|
| 답 있는 20문항 답변 완료 | 18 | 17(Q17이 ⑦ 코드 재확인에서 더 막힘) |
| 근거 적중 | 18/20 | 18/20 |
| 함정 5문항 × 3회 | 15/15(⑦ 14, 에이전트 1) | 15/15(모두 ⑦) |
| 회차 평균(25문항) | 2.16 | 2.92. 6회차 상한에 닿은 문항 2개(Q08, 함정 Q20 1회) |
| 툴 고르는 경향 | 약관은 local_search나 search_vector-bm25 1 ~ 2회 | search_vector-bm25를 3번 이어 부르는 일이 잦음. 함정 Q20에 global_search를 부르기도 함 |
| 시간 중앙값 | 10.5초 | 7.1초 |
| 에이전트 토큰(25문항) | 입력 347,708(캐시 읽기 244,607), 출력 9,358 | 입력 204,215, 출력 14,786(한 문항은 사용량이 기록되지 않음) |
| 에이전트 비용 | $0.75(실측) | 단가를 확인하지 않아 계산하지 않음 |

- 결과의 품질(답변 완료, 적중, 함정)은 거의 같음. 함정은 두 경우 모두 ⑦(코드 재확인과 Jev)이 막아, 「막는 일은 코드」 설계가 모델과 상관없이 지켜짐
- 차이는 툴 고르기에서 남. Groq는 같은 툴을 표현만 바꿔 되풀이하는 편이라 회차가 늘고, 상한(6회차)에 두 번 닿음
- 한 번 실행한 결과라 실행마다 달라질 수 있음(25문항 1회, 함정 3회)

## 16. 에이전트 모델 변경: Opus 5.5 → Groq gpt-oss-120b(2026-10-25, 강사 결정)

강사 지시: 「groq으로 변경해요. 교재와 예제 모두 변경해요」(15.2 비교 실험 뒤)

| 대상 | 바꾼 것 |
|---|---|
| 예제 코드 | `search_graph.py`: 에이전트를 `ChatGroq(openai/gpt-oss-120b, temperature 0, reasoning_effort medium, 재시도 4)`로, Anthropic 프롬프트 캐시 미들웨어 뺌(Groq는 앞부분이 같은 입력을 자동으로 캐시함), 비용 단가를 Groq 공식 값(입력 $0.15, 캐시된 입력 $0.075, 출력 $0.60, 100만 토큰당)으로, 키는 3개(Claude 키 불필요). 에이전트 프롬프트에 「같은 툴을 표현만 바꿔 되풀이하지 않음, PASS면 finish」 한 줄 추가. `core_search.py`는 주석만 바꿈(실습 함수와 빈칸은 그대로) |
| 패키지 | `langchain-anthropic`, `anthropic` 뺌 |
| 문서 | README(7장 실측과 7.4 모델 비교, 10장 한계), 실습 가이드, 가이드 슬라이드, 이 계획서(상태, 4.3, 4.5, 8, 9, D4) |
| 교재 | 64쪽(리드문, ③ 상자, 카드 1, 노트), 69쪽(리드문, 생각 단계, 콜아웃, 노트)을 직접 고침(사용자가 손으로 고친 장표가 있어 다시 만들지 않음). 코드 예시 장표는 다시 발췌, 빌드해 넣음. 백업 `backup/…backup-20261025-groq-agent.pptx` |
| 설계 문서 | `graphrag-react-search.md` 상태 표에 실습 예제 변경 한 줄(5장 Opus 배치는 당시 기록으로 둠) |

변경 뒤 실측(에이전트 Groq)

| 항목 | 값 |
|---|---|
| 답 있는 20문항 | 답변 완료 16(오거절 Q14, Q16, Q17, Q24), 근거 적중 17/20 |
| 함정 | 25문항 실행에서 5/5(⑦ 4, ⑧ 1), 3회 반복에서 15/15(모두 ⑦) |
| 회차 | 평균 3.16, 최대 6 |
| 에이전트 비용 | 25문항 $0.0415, 함정 15회 $0.0227 |
| 시간 중앙값 | 8.0초 |

- 에이전트 프롬프트에 넣은 「되풀이하지 않음」 한 줄은 효과가 뚜렷하지 않았음(회차 평균 2.92 → 3.16, 한 번 실행 값)
- Q19는 이번 25문항 실행에서 ⑦을 통과하고 ⑧이 답을 내지 않아 멈춤. 3회 반복에서는 3번 모두 ⑦이 막음

## 부록. 가상환경 정리(2026-10-26 강사 지시)

- 강사 지시: 「graphrag도 hands-on/solutions/graphrag에서 가상환경 설정. 서브 폴더에는 README.md만 두고 가상환경 설정과 실행은 상위 폴더에서 하도록 안내.  
  requirements.txt는 graphrag 폴더에만. 가상환경을 활성화하고 수행하도록 안내」
- `indexer/`, `retriever/`, `schema/doc/`, `schema/rdb/`의 requirements.txt 4개를 `graphrag/requirements.txt` 하나로 합치고 지움  
  (psycopg[binary]와 langgraph, typesafe-sdk 포함). 상위 안내서 `graphrag/README.md`를 새로 둠(구성, 만들기와 활성화, PowerShell이 막을 때, 실행 순서)
- `indexer/README.md`, `retriever/README.md`는 상위 README 3절로 안내하고 실행 명령을 활성화 뒤 `python ...`으로 바꿈. 실습 가이드와 가이드 슬라이드도 같게 고치고 덱을 다시 빌드함
- 검증: 새 가상환경에 `pip install -r requirements.txt` 성공, `pip check` 문제 없음. 활성화 뒤 `check_graph.py --qid Q09` 적중,  
  `search_graph.py --qid Q01` 답변 완료. 기존 `.venv`를 PowerShell에서 활성화해 설치 보충(psycopg) 뒤 `--qid Q19` 확인할 수 없음(함정 차단).  
  활성 세대를 바꾸는 `index_graph.py --sample`은 검색 실습 그래프를 바꾸므로 돌리지 않고 `--help`로만 확인함
