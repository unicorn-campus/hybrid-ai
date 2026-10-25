# GraphRAG 검색 실습 가이드(교육생용)

| 항목 | 내용 |
|---|---|
| 대상 | 하이브리드 AI 교육 「그래프 검색」. 엔지니어, 데이터 모델러, 기획자 혼합(파이썬 초보 포함) |
| 교재 | 『신한카드 하이브리드AI_W05 ~ W07』 64 ~ 79쪽 |
| 예제 | [hands-on/solutions/graphrag/retriever](https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/README.md) |
| 시간 | 이론 1교시 + 클론 코딩 3교시(교시 2, 3, 4) = 4H |
| 완료 | 본인 코드(`my_search.py`)로 Q01은 「답변 완료」, Q19(함정)는 「확인할 수 없음」으로 끝남 |

## 0. 이 실습에서 만드는 것

인덱싱 실습이 만든 그래프(Neo4j)와 검색엔진(OpenSearch)에서 **근거를 모아 답하는 검색기**를 만듦.  
교재 64쪽 카드 4장이 그대로 코드가 됨: **툴 고르기는 Opus, 판단은 Jev(확률만), 막는 일은 코드, 툴 안은 고정 순서**.

```text
① 요청 접수(코드) → ② 질문 분석(코드 + Jev)
   → ③ 검색 에이전트(Opus) ⇄ ④ 툴 실행(래퍼 + 서브 워크플로우) ⇄ ⑤ 채점과 상한(코드 + Jev)   … 반복 1, 최대 6회차
      ③ ~ ⑤는 LangChain create_agent + 미들웨어 2개(GuardMiddleware, ToolWrapperMiddleware)
   → ⑥ 리랭킹(Cohere) → ⑦ 수집 종료 판정(코드 재확인 → Jev)
   → ⑧ 답변 생성(Groq, LCEL 체인 + 구조화 출력) ⇄ ⑨ 근거 검증(코드)                       … 반복 2, 재작성 최대 2회
   → ⑩ 종료 상태(답변 완료, 확인할 수 없음 등 7가지)
```

툴 6개: `search_vector-bm25`(O: 벡터 + BM25 → RRF → 리랭크), `local_search`(L: 청크 → 엔티티 16 → 이웃 → 보고서),  
`global_search`(G: 보고서 고르기 → 주제와 Follow-up → 주제별 Local), `find_entities`(E), `get_source_chunks`(R), `finish`.  
툴 입력에는 필터 칸이 없음. 세대, 역할, 회원, 카드 필터는 래퍼가 강제로 붙임.

## 1. 사전 준비(수업 전까지)

| 번호 | 할 일 | 확인 |
|---|---|---|
| 1 | 인덱싱 실습 완료(활성 세대). 없으면 `../indexer`에서 `index_graph.py --run {별명}-f1 --reuse data/teacher` | `indexer/data/active_generation.json`의 `chunk_count` 260 |
| 2 | Neo4j와 OpenSearch 기동 | `docker compose -f neo4j/compose.yml ps`가 `healthy` |
| 3 | 공용 가상환경에 패키지 2개 추가(README 3장: `pip install -r retriever/requirements.txt`) | 설치 확인 명령이 `ok` |
| 4 | `secrets/.env`에 키 4줄: `CLAUDE_API_KEY`, `JEV_API_KEY`, `GROQ_API_KEY`, `COHERE_API_KEY`(강사 배포) | 아래 명령이 ⑩까지 끝남 |

```bash
cd hands-on/solutions/graphrag/retriever
../.venv/Scripts/python.exe search_graph.py --qid Q01
```

macOS와 Linux는 `../.venv/Scripts/python.exe` 대신 `../.venv/bin/python`.  
실행마다 Opus 실제 비용이 찍힘(질문 하나 약 $0.02 ~ 0.05). 함수 하나를 고칠 때마다 질문 한두 개만 돌려 확인함.

## 2. 수업 흐름

| 교시 | 내용 | 실습 함수(채우는 순서) |
|---|---|---|
| 1 이론 | 교재 64 ~ 79쪽. 강사 화면으로 ① ~ ⑩ 출력 읽기, 교체 방법 시연 | - |
| 2 | ① ~ ④ 래퍼 | `check_ready`, `decide_question_route`, `build_agent`, `run_tool` |
| 3 | ④ O, L과 ⑤ | `rrf_merge`, `narrow_entities`, `diagnose_signals`, `force_stop_reason`(남으면 선택 `normalize_entity_key`) |
| 4 | ⑥ ~ ⑩ | `select_final_chunks`, `recheck_question`, `generate_answer`, `verify_answer`, `make_end_state` |

방식 두 가지

- **직접 작성**(7개): 함수 몸통이 `raise NotImplementedError("여기에 본인 코드를 작성함")` 한 줄임. docstring의 「방법」을 보고 씀
- **빈칸 채우기**(6개): 거의 완성된 코드 중간에 `raise NotImplementedError("빈칸 N을 채울 것")`이 있음.  
  바로 위 주석이 무엇을 채울지 알려 줌. 채운 뒤 그 `raise` 줄은 지움

## 3. 따라하기

### Step 1. 강사 코드로 실행하고 출력 읽기(교시 1)

```bash
../.venv/Scripts/python.exe search_graph.py --qid Q01
```

```bash
../.venv/Scripts/python.exe search_graph.py --qid Q19
```

| 줄 | 볼 것 | Q01(강사 PC) | Q19(강사 PC) |
|---|---|---|---|
| `② Jev` / `② 코드의 결정` | 잡담, 모호 확률과 첫 툴 후보 | 모호 0.21, 첫 툴 `local_search` | 첫 툴 `local_search` |
| `③ →` | Opus가 고른 툴과 질의 | `local_search` 1회 | 여러 툴(실행마다 다름) |
| `⑤ 신호` | 진단 신호, 포함률, 공존 문장 | 공존 3문장 | `NO_COOCCUR` 등 |
| `⑦ 코드 재확인` | 조건 ①, ② | 조건 ① 통과 | 불통과(「가족돌봄」과 「해외」를 잇는 근거 없음) |
| `⑩ 종료 상태` | 이름과 이유, Opus 비용 | 답변 완료, 약 $0.02 ~ 0.03 | 확인할 수 없음 |

Opus는 temperature를 줄 수 없어 **실행마다 고르는 툴이 다를 수 있음**. 강사와 비교할 때는 툴 경로보다 신호, 판정, 종료 상태를 봄.

### Step 2. 본인 코드로 바꿀 준비

1. `search_graph.py` 위쪽 import 한 줄을 `import my_search as core`로 바꿈
2. `my_search.py` 맨 아래 `USE_TEACHER_CODE` 목록을 봄. 여기 있는 함수는 **강사 코드가 대신 돎**
3. 지금 채울 함수 이름을 목록에서 지움 → 그 함수를 채움 → 아래 표의 확인 명령으로 다시 실행 → 결과를 비교함
4. 막히면 함수 이름을 목록에 다시 넣고 다음 함수로 넘어감. 본인 함수에서 예외가 나면 `[실습 함수 오류]`와 Traceback이 그대로 보임

### Step 3. 교시 2 함수 4개

| 순서 | 함수 | 방식 | 채울 것 | 확인 명령 | 정상 기준 |
|---|---|---|---|---|---|
| 1 | `check_ready` | 직접 | 역할 확인, 활성 세대와 인덱스와 그래프 청크 수 비교, 보고서 유무 | `--qid Q01`, `"질문" --role guest` | Q01 「준비 완료」, 없는 역할은 ⑩ 오류 |
| 2 | `decide_question_route` | 직접 | Noul 0.7 이상이면 끝냄, Choice는 두 번 답이 같고 확신 0.5 이상일 때만 후보 | `--qid Q01`, `"안녕하세요"` | 잡담은 「검색 불필요」로 검색 0회, Q01은 첫 툴 후보가 찍힘 |
| 3 | `build_agent` | 빈칸 2 | `create_agent(model, tools, system_prompt, middleware)`, `agent.invoke(입력, context, config)` | `--qid Q01` | `③ 회차` 줄이 나오고 ⑩까지 끝남 |
| 4 | `run_tool` | 빈칸 2 | 질의 속 식별자 지우기(`strip_identifiers`), 필터를 붙여 서브 워크플로우 부르기 | `--qid Q14` | 질의에 회원번호가 없음, 다른 회원 원문 0건 |

### Step 4. 교시 3 함수 4개(+ 선택 1개)

| 순서 | 함수 | 방식 | 채울 것 | 확인 명령 | 정상 기준 |
|---|---|---|---|---|---|
| 5 | `rrf_merge` | 직접 | 청크마다 Σ 1 / (60 + 순위), 점수 내림차순 상위 25 | `--qid Q05` | ⑩까지 끝나고 답이 강사와 같은 조항(제21조) |
| 6 | `narrow_entities` | 직접 | 고정 → 청크마다 1개 → 유사도 순, 합계 16 | `--qid Q09` | `local_search` 관찰의 엔티티 수가 16 이하 |
| 7 | `diagnose_signals` | 빈칸 3 | NO_SEED, NO_COOCCUR, PASS 규칙 | `--qid Q01`, `--qid Q18` | Q18은 `NO_COOCCUR`가 한 번 이상 |
| 8 | `force_stop_reason` | 직접 | 회차 6, NO_NEW 2회 연속, 같은 호출 2회 연속, 전량 실패 2회 | `--qid Q22` | 강제 종료가 나면 「⑤ 강제 종료: 이유」 한 줄 |
| 선택 | `normalize_entity_key` | 직접 | 레이블마다 키를 같은 꼴로(카드 접미어, 조항 번호) | `--qid Q14` | `find_entities` 결과가 강사와 같음 |

### Step 5. 교시 4 함수 5개

| 순서 | 함수 | 방식 | 채울 것 | 확인 명령 | 정상 기준 |
|---|---|---|---|---|---|
| 9 | `select_final_chunks` | 직접 | 주제마다 1자리 먼저, 남은 자리는 점수 순, 8자리 | `--qid Q24` | `⑥ 리랭킹` 8자리에 주제 id가 고루 있음 |
| 10 | `recheck_question` | 빈칸 2 | 조건 ① 공존 문장 수, 조건 ② 두 엔티티가 관계 하나로 이어짐 | `--qid Q01`, `--qid Q18` | Q01 「조건 ①」 통과, Q18 불통과 |
| 11 | `generate_answer` | 빈칸 2 | `llm.with_structured_output(GroundedAnswer, ...)`, `prompt \| structured` | `--qid Q01` | 문장마다 `[c1]` 같은 인용 |
| 12 | `verify_answer` | 직접 | 인용 id 존재, 숫자와 조항 번호, 보고서 인용은 경향 문장에만 | `--qid Q01`, `--qid Q25` | Q01 「검증 통과」, Q25는 실패 사유와 「재작성 1/2」가 나올 수 있음 |
| 13 | `make_end_state` | 빈칸 1 | `END_STATES`에서 이름과 뜻 꺼내기 | 위 명령 모두 | 교재 79쪽 표의 이름과 같음 |

교시 4 끝: `USE_TEACHER_CODE` 목록이 비고 Q01과 Q19가 아래 완료 기준대로 끝나면 완료임.

## 4. 완료 기준

| 항목 | 기준 |
|---|---|
| 교체 실행 | `USE_TEACHER_CODE`가 빈 `my_search.py`로 Q01이 「답변 완료」, ⑨ 검증 통과 |
| 함정 질문 | Q19가 「확인할 수 없음」(어느 단계에서 막혔는지 설명할 수 있음) |
| 회원 권한 | `--qid Q14`에서 다른 회원 원문이 0건이고, 같은 질문을 `--role agent`로 돌리면 상담 원문이 0건 |
| 제출 | `my_search.py`와 Q01, Q19 실행 화면 캡처(Opus 비용 줄 포함) |

## 5. 막혔을 때

| 증상 | 할 일 |
|---|---|
| 시작 검사에서 멈춤 | 출력의 「→」 줄이 할 일임(키 넣기, compose 띄우기 등) |
| `NotImplementedError: 빈칸 1을 채울 것` | 그 함수의 빈칸을 아직 안 채움. 채웠으면 `raise` 줄을 지웠는지 확인 |
| `[실습 함수 오류]`와 Traceback | 맨 아래 줄의 파일과 함수가 본인 코드임. 고치거나 이름을 목록에 다시 넣음 |
| 강사와 툴 경로가 다름 | 정상임. 신호, ⑦ 판정, 종료 상태를 비교함 |
| 429(호출 제한) | 잠시 뒤 다시 실행 |
| Q14가 「확인할 수 없음」 | 강사 코드도 같음(한계). 질문은 「해지」, 원문은 「정리」라고 적어 ⑦ 코드 재확인이 낱말로 이어 주지 못함 |

## 6. 용어 풀이

| 용어 | 뜻 |
|---|---|
| ReAct | 생각하고, 툴을 부르고, 결과를 보고 다시 생각하는 방식. 한 바퀴가 한 회차 |
| create_agent | LangChain이 ReAct 고리를 만들어 주는 함수. 미들웨어로 고리 중간에 코드를 끼움 |
| 미들웨어(middleware) | 모델 호출 전후나 툴 호출을 감싸 끼우는 코드. 여기서는 상한, 강제 종료, 필터, 채점을 맡음 |
| 래퍼(wrapper) | 툴 호출을 감싸 필터를 강제로 붙이는 함수(`run_tool`) |
| RRF | 여러 검색의 순위를 합치는 방식. 점수 = Σ 1 / (60 + 순위) |
| 진단 신호 | PASS(충분), NO_COOCCUR(핵심 낱말이 한 문장에 함께 없음), NO_SEED(결과 없음), LOW_COVERAGE(낱말 일부만), SCATTERED(여러 문서에 흩어짐), NO_REPORTS(관련 보고서 없음), NO_NEW(새 원문 없음) |
| Jev Noul, Choice | 참일 확률(0 ~ 1), 보기 고르기와 확신(confidence). Jev는 확률만 내고 결정은 코드 기준값이 함 |
| LCEL 체인 | `프롬프트 \| 모델`처럼 `\|`로 단계를 이어 붙이는 LangChain 문법 |
| 구조화 출력 | LLM이 정해진 칸(Pydantic 스키마)을 채운 객체로 답하게 함(`with_structured_output`) |
| 함정 질문 | 문서에 없는 사실을 있는 것처럼 묻는 질문. 지어내지 않고 「확인할 수 없음」으로 멈춰야 함 |
| 생각 토큰 | Opus가 답 전에 쓰는 생각. 끌 수 없고 출력 요금으로 셈 |

## 7. 더 해 보기(선택)

- `search_graph.py` 맨 위 `PASSAGE_THRESHOLDS`의 `relevant_min`(0.45)을 0.3으로 내리고 Q18이 여전히 막히는지 봄
- `MAX_ROUNDS`를 2로 줄이고 Q25(혼합 질문)의 종료 상태와 Opus 비용이 어떻게 바뀌는지 봄
- `--no-answer`로 Q09를 돌려 ⑩ 「검색 결과」(근거 목록만)를 봄
- `--role agent`와 `--role auditor --member-id M-1042`로 같은 상담 질문을 돌려 볼 수 있는 청크 수를 비교함

## 8. 참고 링크

- 예제 README: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/README.md
- 핵심 모듈(정답): https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/core_search.py
- 교육생 뼈대: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/my_search.py
- main: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/search_graph.py
- 개발계획서(강사용): https://github.com/unicorn-campus/hybrid-ai/blob/main/teacher/plan/graphrag-search-개발계획서.md
- 인덱싱 실습 가이드: https://github.com/unicorn-campus/hybrid-ai/blob/main/teacher/plan/graphrag-indexing-실습가이드.md
