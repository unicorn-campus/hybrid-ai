# GraphRAG 검색 실습 예제

하이브리드 AI 교육 「그래프 검색」(교재 『W05 ~ W07』 64 ~ 79쪽) 실습용 예제임.  
인덱싱 실습(`../indexer`)이 게시한 활성 세대(Neo4j 그래프 + OpenSearch 검색엔진)를 읽어,  
**Groq 에이전트(gpt-oss-120b)가 툴을 골라 근거를 모으고(ReAct), 판단은 의사결정AI Jev가 확률로, 막는 일은 코드가 맡는** 검색 워크플로우 10단계를 돌림.  
레이어드 아키텍처 없이 **main 1개 + 핵심 모듈 1개**로 짰고, 교육생은 핵심 모듈의 실습 함수 13개를 클론 코딩한 뒤 본인 코드로 바꿔 끼움.

## 수업용 명령 2개

이 폴더(`hands-on/solutions/graphrag/retriever`)에서 실행함.

```bash
../.venv/Scripts/python.exe search_graph.py --qid Q01
```

```bash
../.venv/Scripts/python.exe search_graph.py --qid Q19
```

첫 명령은 약관 사실 질문을 ① ~ ⑩ 끝까지 돌려 「답변 완료」를 봄(약 7 ~ 10초, 에이전트 비용 약 $0.001).  
둘째 명령은 함정 질문(가족돌봄 카드에 없는 해외 수수료 할인)이 지어내지 않고 「확인할 수 없음」으로 멈추는 것을 봄.  
macOS와 Linux는 `../.venv/Scripts/python.exe` 대신 `../.venv/bin/python`을 씀. 나머지 옵션은 8장에 있음.

## 1. 목표와 주요 기능

| 목표 | 내용 |
|---|---|
| 개념을 코드로 | 교재 64쪽 워크플로우(① 요청 접수 → ② 질문 분석 → ③ 검색 에이전트 ⇄ ④ 툴 실행 → ⑤ 채점과 상한 판정 → ⑥ 리랭킹 → ⑦ 수집 종료 판정 → ⑧ 답변 생성 ⇄ ⑨ 근거 검증 → ⑩ 종료 상태)를 함수 하나씩으로 봄 |
| 클론 코딩 | 단계마다 실습 함수 1개 이상, 모두 13개(직접 7개, 빈칸 6개) + 선택 1개. `my_search.py`에 채우고 import 한 줄로 바꿔 끼움 |
| 눈으로 확인 | Jev 확률과 코드의 결정, 회차마다 에이전트가 고른 툴과 질의, 진단 신호, 강제 종료 이유, 8자리, 코드 재확인, 인용 검증, 종료 상태, 에이전트 실제 비용을 화면에 찍음 |

주요 기능

- ③ ~ ⑤(반복 1)는 LangChain `create_agent` + 미들웨어 2개로 돎. `GuardMiddleware`(모델 호출 전 강제 종료, 모델이 고른 호출의 상한)와  
  `ToolWrapperMiddleware`(막힌 호출은 오류 표시, 실행한 결과에는 Jev 판정과 진단 신호)가 「막는 일은 코드」를 맡음  
- 툴 6개(`search_vector-bm25`, `local_search`, `global_search`, `find_entities`, `get_source_chunks`, `finish`)는  
  입력에 필터 칸이 없음.  
  세대, 역할, 회원, 카드 필터는 래퍼가 강제로 붙임  
- 글을 만드는 LLM 호출(G1, G2, ⑧)은 모두 LCEL 체인(`프롬프트 | 모델`)과 구조화 출력(`with_structured_output`, Pydantic 스키마)으로 짬
- 결과 끝에 ③ 에이전트의 실제 비용(응답의 토큰 사용량 × Groq 단가)을 찍음. Groq가 앞부분이 같은 입력을 자동으로 캐시해  
  회차가 늘어도 입력 비용이 작음
- `--eval`로 평가셋 25문항을 돌려 근거 적중, 함정 거절, 툴 경로, 비용 합계를 봄(강사용)

## 2. 디렉토리 구조

```text
hands-on/solutions/graphrag/
├─ .venv/                      GraphRAG 실습 공용 가상환경(인덱싱과 같음. 3장에서 패키지 1개 추가)
├─ indexer/                    (읽기만) 활성 세대 파일(data/active_generation.json), kr_tokenizer.py(질의 토큰화)
└─ retriever/
   ├─ README.md                이 문서
   ├─ requirements.txt         인덱싱과 같은 판 + typesafe-sdk
   ├─ search_graph.py          main: 설정 상수, 프롬프트와 스키마, 시작 검사, 저장소 접속, 외부 호출, 서브 워크플로우 O, L, G, E, R,
   │                           툴 6개, 미들웨어 2개, run_workflow(① ~ ⑩), 화면 출력, 평가셋 일괄 실행
   ├─ core_search.py           핵심(클론 코딩 대상): 실습 함수 13개 + 선택 1개 + 제공 함수
   ├─ my_search.py             교육생 작업 파일(뼈대). 맨 아래 USE_TEACHER_CODE 목록의 함수는 강사 코드가 대신 돎
   └─ data/logs/               실행 기록(Git에 올리지 않음). 질문마다 JSON, --eval은 문항마다 한 줄(jsonl)
```

읽기만 하는 입력

| 입력 | 경로 | 만든 곳 |
|---|---|---|
| 활성 세대 | `../indexer/data/active_generation.json` | 인덱싱 실습 ⑤ 게시 |
| 그래프(엔티티 1,673개, 커뮤니티 보고서 78개) | Neo4j `bolt://localhost:7687` | 인덱싱 실습 K1 ~ K8 |
| 검색엔진 인덱스(260청크) | OpenSearch `card_chunks-{세대}` | 인덱싱 실습 S1 ~ S3 |
| 평가셋 25문항 | `hands-on/solutions/eval-set.json` | RAG 실습 |

## 3. 준비물과 가상환경 설정

| 항목 | 값 |
|---|---|
| Python | 3.13 |
| ③ 검색 에이전트 | Groq `openai/gpt-oss-120b`(G1, G2, ⑧과 같은 모델), reasoning_effort medium. 단가는 100만 토큰당 입력 $0.15, 캐시된 입력 $0.075, 출력 $0.60(Groq 공식 모델 문서, 2026-10-25 확인) |
| ②, ⑤, ⑦ 판단 | TypeSafe Jev(`jev-1.14.0` 고정). 확률만 내고 결정은 코드의 기준값이 함 |
| G1, G2, ⑧ | Groq `openai/gpt-oss-120b`(LCEL 체인 + 구조화 출력) |
| 임베딩, 리랭커 | Cohere `embed-v5.0-fast`(2048차원, 색인과 같음), `rerank-v4.0-fast` |
| 저장소 | Neo4j 2026.09.0 + APOC, OpenSearch 2.19.1(`backing-services/`) |
| API 키 | 저장소 루트 `secrets/.env`에 3줄: `JEV_API_KEY`, `GROQ_API_KEY`, `COHERE_API_KEY` |
| Neo4j 비밀번호 | 환경변수 `NEO4J_PASSWORD` 또는 `backing-services/neo4j/.env`(인덱싱과 같음) |

- 키는 환경변수에 올리지 않고 클라이언트마다 인자로 넘김. Jev는 SDK 기본 이름(`TYPESAFE_API_KEY`)과 달라 직접 넘김

### 3.1 사전 조건

1. 인덱싱 실습을 끝내 활성 세대가 있음(`../indexer/data/active_generation.json`). 없으면 인덱싱 README의 `--reuse data/teacher` 실행
2. Neo4j와 OpenSearch가 떠 있음(`docker compose -f neo4j/compose.yml ps`가 `healthy`)

### 3.2 가상환경(Windows PowerShell)

```powershell
cd hands-on\solutions\graphrag
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r retriever\requirements.txt
```

### 3.3 가상환경(Windows Git Bash)

```bash
cd hands-on/solutions/graphrag
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r retriever/requirements.txt
```

### 3.4 가상환경(macOS, Linux)

```bash
cd hands-on/solutions/graphrag
python3.13 -m venv .venv
.venv/bin/python -m pip install -r retriever/requirements.txt
```

인덱싱 실습에서 `.venv`를 이미 만들었으면 `python -m venv` 줄은 건너뛰고 설치 줄만 실행함(typesafe-sdk가 더해짐).

설치 확인

```bash
.venv/Scripts/python.exe -c "import typesafe_sdk, langchain_groq, langchain_cohere, neo4j, opensearchpy; print('ok')"
```

## 4. 실행 방법

### 4.1 평가셋 질문(수업용)

```bash
../.venv/Scripts/python.exe search_graph.py --qid Q14
```

역할과 회원은 평가셋 `filters`대로 정해짐(회원 질문은 감사자 + 그 회원, 경향 질문은 감사자, 나머지는 상담원).

### 4.2 자유 질문

```bash
../.venv/Scripts/python.exe search_graph.py "할부로 산 상품의 철회는 며칠 안에 요청해야 하나요?" --role agent
```

```bash
../.venv/Scripts/python.exe search_graph.py "이 회원이 가장 최근 상담에서 요청한 것은?" --role auditor --member-id M-1042
```

### 4.3 근거만 보기(⑧ 끔)

```bash
../.venv/Scripts/python.exe search_graph.py --qid Q01 --no-answer
```

### 4.4 평가셋 일괄(강사용, API 비용 듦)

```bash
../.venv/Scripts/python.exe search_graph.py --eval
```

```bash
../.venv/Scripts/python.exe search_graph.py --eval --only Q18,Q19,Q20,Q21,Q22 --repeat 3
```

## 5. 단계별 출력 읽는 법

| 출력 머리 | 단계 | 봐야 할 것 |
|---|---|---|
| `── ① 요청 접수` | ① | 준비 판정, 활성 세대, 보고서 수 |
| `── ② 질문 분석(코드)` | ② | 회원번호를 지운 질문, 회원과 카드 필터, 볼 수 있는 청크 수, 핵심 낱말 |
| `② Jev` / `② 코드의 결정` | ② | 잡담, 모호 확률과 첫 툴(보기 순서를 바꾼 답 포함) → 코드가 내린 결정 |
| `── ③ 회차 N/6` / `③ →` | ③ | 에이전트가 고른 툴과 질의. 한 회차에 여러 개일 수 있음. 「막힘」은 상한에 걸린 호출 |
| `④ 툴 이름 … → 원문 N개` | ④ | 새 원문 수, 근거에서 뺀 수(관련 없음, 지시 끼워 넣기) |
| `⑤ Jev` / `⑤ 신호` | ⑤ | 원문마다 관련, 답 근거, 전제 충돌 확률. 진단 신호와 포함률, 공존 문장 수 |
| `⑤ 강제 종료` | ⑤ | 강제 종료 이유(모델을 다시 부르지 않음) |
| `── ⑥ 리랭킹` | ⑥ | 8자리와 점수, 주제 id |
| `── ⑦ 코드 재확인` / `⑦ 판정` | ⑦ | 조건 ①(한 문장 공존), ②(관계 하나로 이어짐) 결과와 통과, 불통과 |
| `── ⑧ 답변` / `── ⑨ 근거 검증` | ⑧ ⑨ | 문장마다 인용 id, 검증 실패 사유, 재작성 횟수 |
| `── ⑩ 종료 상태` | ⑩ | 종료 상태 이름과 뜻, 에이전트(Groq) 비용(호출, 입력, 캐시, 출력 토큰), 호출 수, 툴 경로, 시간 |

## 6. 교육생 교체 방법

1. `search_graph.py`의 import 한 줄을 바꿈

   ```python
   import core_search as core  # 강사 코드로 실행
   import my_search as core    # 본인 코드로 실행(이 줄만 바꿈)
   ```

2. `my_search.py` 맨 아래 `USE_TEACHER_CODE` 목록에서 **지금 채울 함수 이름을 지움**. 목록에 남은 함수는 강사 코드가 대신 돎
3. 그 함수를 채우고(직접 작성은 `NotImplementedError` 자리, 빈칸은 `"빈칸 N을 채울 것"` 자리) 같은 명령으로 다시 실행해  
   5장 출력을 강사 결과와 비교함. LLM은 실행마다 고르는 툴이 다를 수 있으므로 툴 경로보다 신호, 판정, 종료 상태를 비교함  
4. 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감(실습이 멈추지 않음)

실습 함수와 단계(채우는 순서)

| 순서 | 함수 | 방식 | 단계 | 교재 |
|---|---|---|---|---|
| 1 | `check_ready` | 직접 | ① 권한, 같은 세대, 보고서 유무 | 65 |
| 2 | `decide_question_route` | 직접 | ② Jev 확률 → 코드의 결정 | 65, 66 |
| 3 | `build_agent` | 빈칸 2 | ③ create_agent로 ReAct 고리 | 68 |
| 4 | `run_tool` | 빈칸 2 | ④ 래퍼: 식별자 지우기, 필터 강제 | 69 |
| 5 | `rrf_merge` | 직접 | ④ O3 RRF | 70 |
| 6 | `narrow_entities` | 직접 | ④ L2 엔티티 16개 | 71 |
| 7 | `diagnose_signals` | 빈칸 3 | ⑤ 진단 신호 | 74 |
| 8 | `force_stop_reason` | 직접 | ⑤ 강제 종료 | 75 |
| 선택 | `normalize_entity_key` | 직접 | ④ E1 키 정규화 | 73 |
| 9 | `select_final_chunks` | 직접 | ⑥ 주제마다 1자리, 8자리 | 76 |
| 10 | `recheck_question` | 빈칸 2 | ⑦ 코드 재확인 조건 ①, ② | 77 |
| 11 | `generate_answer` | 빈칸 2 | ⑧ LCEL 체인 + 구조화 출력 | 78 |
| 12 | `verify_answer` | 직접 | ⑨ 인용, 숫자, 보고서 인용 검사 | 78 |
| 13 | `make_end_state` | 빈칸 1 | ⑩ 종료 상태 | 79 |

## 7. 실측값(강사 PC, 2026-10-25)

### 7.1 평가셋 25문항(`--eval`, 에이전트 Groq, 마지막 실행)

| 항목 | 값 |
|---|---|
| 답이 있는 20문항 | 답변 완료 16개. 확인할 수 없음 4개(Q14, Q16, Q17, Q24, 아래 10장) |
| 근거 적중 | 17/20(평가셋 `relevance.any_of` 문구가 ⑥ 뒤 원문에 그대로 있음). Q02, Q05는 답이 정답과 같지만 평가셋 문구와 원문의 글자가 달라 적중으로 세지 않음 |
| 함정 5문항(Q18 ~ Q22) | 5/5 「확인할 수 없음」. 4개는 ⑦에서 막힘(코드 재확인 2, 약관 버전 1, Jev 답 근거 없음 1). Q19는 ⑦을 통과했지만 ⑧ 답변 LLM이 「근거로 답할 수 없음」(문장 0개)을 돌려 멈춤 |
| 회차 | 1 ~ 6회차(평균 3.16, 중앙값 3). 같은 툴을 표현만 바꿔 되풀이하는 경우가 잦음 |
| 에이전트 비용 | 25문항 합계 $0.0415(문항당 $0.0006 ~ 0.0062). 입력의 상당 부분이 Groq 자동 캐시로 처리됨 |
| 시간 | 문항당 4.3 ~ 26.5초(중앙값 8.0초) |
| 다른 호출 | 문항당 Jev 약 8 ~ 30번, Groq(G1, G2, ⑧) 1 ~ 4번, Cohere 4 ~ 12번(화면 맨 끝 「호출 수」 줄) |

### 7.2 함정 질문 3회 반복(`--eval --only Q18,Q19,Q20,Q21,Q22 --repeat 3`, 에이전트 Groq)

| 항목 | 값 |
|---|---|
| 결과 | 15/15 「확인할 수 없음」 |
| 막은 곳 | 15번 모두 ⑦(코드 재확인과 Jev) |
| 비용 | 15회 합계 $0.0227 |

### 7.3 질문 유형별 경로(예)

| 유형 | 문항 | 에이전트가 고른 툴(예) |
|---|---|---|
| 약관 사실 | Q01 ~ Q06 | `search_vector-bm25` 1 ~ 3회 → finish |
| 카드 혜택 | Q07 ~ Q13 | `local_search` → 엔티티 id로 `get_source_chunks` |
| 회원 상담 | Q14 ~ Q17 | `find_entities("회원")` → `get_source_chunks` |
| 함정 | Q18 ~ Q22 | 2 ~ 5회 찾아본 뒤 ⑦ 불통과 |
| 경향, 혼합 | Q23 ~ Q25 | `global_search` → (Q25) 미확인 주제만 `local_search` |

### 7.4 에이전트 모델 비교(Opus 5.5 → Groq, 강사 결정 2026-10-25)

처음에는 ③ 에이전트를 Claude Opus 5.5로 만들었고, 비교 실험 뒤 Groq `openai/gpt-oss-120b`로 바꿈(G1, G2, ⑧과 같은 모델).

| 항목 | Opus 5.5(마지막 실행) | Groq(마지막 실행) |
|---|---|---|
| 답변 완료(20문항) | 18 | 16 |
| 근거 적중 | 18/20 | 17/20 |
| 함정 5문항, 3회 반복 | 5/5, 15/15 | 5/5, 15/15 |
| 회차 평균 | 2.16 | 3.16 |
| 25문항 에이전트 비용 | $0.75 | $0.0415(약 1/18) |
| 시간 중앙값 | 10.5초 | 8.0초 |

- 두 모델 모두 같은 25문항으로 한두 번 돌린 값이라 1 ~ 2문항 차이는 실행마다 바뀔 수 있음(Opus도 Q16, Q24가 실행에 따라 바뀌었음)

### 7.5 조정 이력(평가셋으로 바꾼 것)

| 무엇을 | 처음 | 바꾼 값 | 까닭(실측) |
|---|---|---|---|
| ② 「모호함」 질문 문장 | 「어느 카드, 조항, 회원인지 말하지 않음」 | 「무엇을 묻는지 알 수 없음」 | 처음 문장은 일반 약관 질문 Q01까지 0.90으로 막음 |
| 핵심 낱말 순서 | 덜 흔한 낱말 먼저 | 버전, 카드명, 조항, 명사(질문 순서), 숫자 | 「동안」, 「직전」 같은 말이 앞에 와 공존 판정이 틀림 |
| ⑦ 조건 ② 후보 | 서로 다른 두 원문만 | + 같은 원문이라도 낱말을 속성에 가진 두 엔티티 | 카드명과 혜택이 한 청크의 다른 문장에 있으면 Q07 ~ Q12가 모두 불통과였음 |
| ⑦ 답 근거 | Jev 「바로 답이 됨」 0.55 초과 | + 「주제를 다룸」 0.7 이상(회원 상담 원문은 예외) | 함정 Q18에서 관련 0.5 ~ 0.6인 원문을 답 근거로 봄 |
| ⑦ Jev 판정 | 원 질문으로 다시 물음 | ⑤ 판정 재사용(Global 원문은 주제 Follow-up 판정) | 교재 77쪽 규칙. 경향 질문 Q23, Q25가 원 질문 판정으로 막혔음 |
| 카드 필터 | 별칭표 이름으로 card_id 찾기 | 띄어쓰기 없는 꼴도 키로 둠 | 「한빛가족돌봄」과 「한빛 가족돌봄」이 달라 필터가 걸리지 않았음(Q19가 다른 카드 원문을 근거로 씀) |

## 8. 옵션(부록)

| 옵션 | 뜻 |
|---|---|
| `--qid Q01` | 평가셋 질문으로 실행(역할과 회원은 평가셋대로) |
| `--role agent` / `auditor` | 상담원(공개 문서만) / 감사자(상담 기록까지) |
| `--member-id M-1042` | 감사자일 때 그 회원의 상담만 봄 |
| `--no-answer` | ⑧ 답변 생성을 끄고 근거 목록만(⑩ 「검색 결과」) |
| `--eval` | 평가셋 25문항 일괄. `--start Q10`(이어 하기), `--only Q18,Q19`(골라 하기), `--repeat 3`(반복), `--sleep 2` |

환경변수: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `OPENSEARCH_URL`(인덱싱과 같음).

## 9. 막혔을 때

| 증상 | 할 일 |
|---|---|
| `secrets/.env에 … 줄이 필요함` | 강사에게 받은 키 3줄을 `secrets/.env`에 넣음 |
| `활성 세대 파일이 없음` | 인덱싱 실습을 먼저 게시함(`../indexer`에서 `index_graph.py --run {별명}-f1 --reuse data/teacher`) |
| `Neo4j 접속 실패`, `OpenSearch 접속 실패` | `backing-services`에서 `docker compose ... up -d`, `ps`로 healthy 확인 |
| `[실습 함수 오류]`와 Traceback | 본인 함수의 예외임. 고치거나 이름을 `USE_TEACHER_CODE`에 다시 넣음 |
| 429(호출 제한) | 잠시 뒤 다시 실행. `--eval`은 `--sleep 2`와 `--start`로 이어 함 |
| 강사와 툴 경로가 다름 | 정상임(temperature 0이어도 LLM은 실행마다 고르는 툴이 다를 수 있음). 신호, 판정, 종료 상태를 비교함 |

## 10. 한계

- **실행마다 결과가 다름**: 에이전트와 Global 검색의 주제, Follow-up 질문을 LLM(Groq)이 만들어 temperature 0이어도 달라질 수 있음.  
  같은 질문도 툴 경로, 회차, 종료 상태가 달라질 수 있음(실측: Q16, Q24는 실행에 따라 답변 완료와 확인할 수 없음이 바뀜)  
- **⑦ 코드 재확인은 낱말 기준**: 질문과 원문의 낱말이 다르면 이어 주지 못함. Q14는 질문의 「해지」가 원문에서 「정리」라 불통과(오거절).  
  설계 문서가 예고한 부작용(두 사실을 묻는 질문의 오거절)임  
- **Jev 한국어 정확도**: 공식 문서상 영어보다 낮음. 회원 상담 원문은 관련 확률이 낮게 나오는 편이라 ⑤, ⑦에서 관련 확률 기준을 걸지 않음.  
  Q16처럼 답 근거 확률이 0.55 아래로 나오면 확인할 수 없음이 됨  
- **기준값은 평가셋 25문항으로 맞춘 가정값**: 7.5의 조정은 이 평가셋에 맞춘 것이라 7.1의 점수(16/20, 5/5)도 같은 25문항의 점수임.  
  새 문항으로는 검증하지 않았음(과적합 위험). 문서나 질문이 바뀌면 다시 맞춰야 함
- **함정 차단과 오거절은 한 묶음**: 함정은 주로 ⑦ 코드 재확인과 Jev가 막고, 그 대가로 Q14, Q16, Q17 같은 오거절이 생김.  
  ⑦을 통과한 함정이 ⑧에서 멈춘 경우도 있음(Q19, 7.1)
- **Groq 에이전트는 회차가 많음**: 같은 툴을 표현만 바꿔 되풀이하는 편이라 Opus보다 회차가 1회쯤 많음. 상한(6회차)이 막음
- **⑤ 신호 PASS의 「원문 2개 이상」**: 답이 원문 하나에 다 있는 질문(Q01)은 PASS 없이 끝남. 에이전트가 신호 없이도 finish하므로 결과에는 영향 없음
- **비용**: 수업 중 질문 하나에 에이전트 약 $0.0006 ~ 0.006. Jev, G1, G2, ⑧(Groq), Cohere 비용은 화면에 찍지 않음(강사 결정)
- **L2 ~ L4는 Cypher 2번**: 교재 71쪽은 1번. L2 축소를 파이썬 실습 함수로 꺼내려고 나눔
- 그래프의 Chunk 노드에 권한 속성이 없어 검색엔진 메타데이터로 「볼 수 있는 청크 표」를 만들어 거름. 인덱싱 세대가 바뀌면 다시 읽음(실행할 때마다 읽음)
