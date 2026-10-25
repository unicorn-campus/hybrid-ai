# RAG 검색 예제 프로그램 개발계획서

| 항목 | 내용 |
|---|---|
| 작성 | 클로니(오케스트레이터), 2026-10-26 |
| 검토 | 에듀니(교육, 「수정 후 사용」), 플로니(실행 흐름과 장애, 「조건부 통과」). 14장 「검토 이력」 |
| 대상 교재 | 『신한카드 하이브리드AI_W01 ~ W04』 「검색 워크플로우」 150 ~ 173쪽(앞선 이론 144 ~ 149쪽) |
| 설계 근거 | 교재 147쪽 「Self-RAG + Adaptive RAG + CRAG 결합」 고정 워크플로우, 149쪽 「검색 결과 판정」,  
상세 예제 `design-agentic-ai/hybrid-ai-lab/retriever/vector-retriever/app/domain/`(plan_rules, grading, transform_rules, verification) |
| 참조 코드 | `teacher/rag/retriever/`(이전 실습 예제. ① 권한, ③ 검색, ⑤ 답변만 있음) |
| 입력(읽기만) | RAG 인덱싱 결과 `hands-on/solutions/rag/indexing/data/`(Chroma `card_docs` 260청크, bm25s 색인과 사전),  
인덱서 `indexing/core_indexing.py`(질문 토큰화), 평가셋 `hands-on/solutions/eval-set.json`(25문항. `--qid`로 한 문항씩 씀) |
| 산출 위치 | `hands-on/solutions/rag/retriever/`(이전 실습 예제를 대체함) |
| 상태 | **v0.4 승인(2026-10-26) 뒤 개발 완료, 교재 반영 완료(150 ~ 174쪽, 새 장표 172쪽). 실행 결과는 15장** |

## 1. 목표

- 교육생이 교재 150쪽 검색 워크플로우 **6단계 전부**(① 권한 필터 → ② Adaptive 분류 → ③ 검색 → ④ CRAG 채점 →  
  ⑤ 답변 생성 → ⑥ Self-RAG 근거 검증)를 **파이썬 코드로 직접 만들며** 이해함.  
  이전 예제는 ①, ③, ⑤만 있었고 ②, ④, ⑥은 상세 예제 발췌로 설명했음. 이번 예제는 6단계를 한 프로그램에 모두 구현함
- 핵심은 교재 147쪽 한 줄임: **분기는 모두 개발자가 미리 그린 조건, 반복은 고정 상한, 끝내 부족하면 「확인 필요」로 종료**.  
  LLM은 제안(②의 유형, ④의 질문 변환)과 작성(⑤의 답)만 하고, 받아들일지와 다음 길은 코드 규칙이 정함
- 강사는 전체 예제를 보여 주고, 교육생은 **단계마다 1개 이상, 실습 함수 10개(직접 4개, 빈칸 6개)**를 클론 코딩한 뒤  
  본인 코드로 바꿔 끼워 실행함. ③ 검색은 벡터, BM25, 융합, 리랭크 네 부품을 모두 실습함
- 단계마다 판단 결과를 화면에 남김: 권한 대상 청크 수, LLM이 제안한 유형과 코드의 확정, 질의별 벡터와 BM25 순위, 융합 순위,  
  리랭크 전후 순위, 채점 신호 6개와 판정, 질문 변환 기법과 변환 질의, 재검색 전후 순위, 문장별 인용, 검증 실패 사유,  
  상한 소비량(「재검색 1/1」, 「재작성 1/2」), 종료 상태

## 2. 교재와 다른 점(교육용으로 단순화)

| 항목 | 교재(147 ~ 173쪽, 상세 예제) | 실습 예제 | 이유 |
|---|---|---|---|
| 흐름 구현 | 「조건부 엣지」(147쪽), 상세 예제는 LangGraph 노드 9개 | main의 `run_workflow` 한 함수가 파이썬 `if`와 `for`로 ① ~ ⑥을 부름. 호출마다 교재 단계 번호 주석 | 에이전트가 고르는 길이 없는 고정 분기라 if로 충분하고 흐름이 한 화면에 보임(D1) |
| ③ 검색 모드 | Vector, Hybrid, Rerank 선택지(146쪽) | Vector + BM25 → 가중합 융합 → 리랭크 고정. `--fusion rrf`만 선택 | ④의 주 점수가 리랭크 점수임(149쪽 「Hybrid + Rerank: Rerank 점수」) |
| ④ 부정확 | web_search(선택) 또는 확인 필요 | 확인 필요로 종료(웹 검색 없음) | 147쪽 「일부 = 웹 검색 경로는 없음」과 같음 |
| ④ 재검색 뒤에도 불확실 | LLM 평가자(선택, 149쪽) | 리랭크 0.3 이상 근거만 ⑤로 넘겨 답변 LLM이 판단(근거에 답이 없으면 「확인 필요」)하고 ⑥이 인용 검증. 화면에 「불확실 근거 포함」 표시(D2) | LLM 평가자를 따로 두지 않고 ⑤가 겸함. 호출 수를 늘리지 않음 |
| ④ 채점 신호 | 7개(149쪽), 상세 예제는 역문서 빈도(IDF)로 핵심어 선별 | 6개(하위 질문 충족은 질의별 채점으로 대신). 핵심어 = 질문 토큰 중 카드명, 숫자, 조항 번호(4.3) | 규칙을 초보자가 읽을 수 있게 줄임 |
| ⑤ 답변 형식 | 상세 예제: 문장, 조각ID, 인용문 구조화 출력 | 같음. 화면에는 이전 예제처럼 「문장 [D1-0007]」 문자열로 이어 붙임 | ⑥이 인용문을 본문과 글자 대조하려면 인용문이 따로 있어야 함 |
| 평가와 RAGAS | 이전 예제: `run_eval.py`(일괄 실행) → `logs/results.json` → RAGAS 채점 | 없음. 질문 하나를 단계별로 보는 프로그램만 둠(평가셋 문항은 `--qid`로 하나씩) | 강사 지시(2026-10-26): RAGAS 실행 제거, 일괄 실행 옵션 제거 |

### 2.1 LCEL 체인과 구조화 출력

LLM 호출은 모두 **LCEL 체인**(LangChain Expression Language: `프롬프트 | 모델`처럼 `|`로 단계를 이어 붙이는 문법)과  
**구조화 출력**(`with_structured_output`: LLM이 Pydantic 스키마의 칸을 채운 객체로 답하게 함)으로 짬(GraphRAG 검색 실습과 같은 방식).

| 자리 | 체인 | 스키마(Pydantic) | 담는 칸 |
|---|---|---|---|
| ② 분류(main `classify_question`) | `PLAN_PROMPT \| groq.with_structured_output(QuestionPlan, method="json_schema", strict=True)` | `QuestionPlan` | `question_type`(chitchat, simple, complex), `sub_questions`(복합일 때 2 ~ 3개), `chitchat_reply` |
| ④ 질문 변환(main `transform_query`) | `TRANSFORM_PROMPT \| groq.with_structured_output(QueryTransform, ...)` | `QueryTransform` | `technique`(rewrite, multi, hyde, stepback, keep, clarify), `queries`(1 ~ 3개), `clarify_question`, `reason` |
| ⑤ 답변(실습 `generate_answer`) | `ANSWER_PROMPT \| groq.with_structured_output(GroundedAnswer, ...)` | `GroundedAnswer`, `AnswerSentence` | 문장마다 `text`, `chunk_id`, `quote`(근거 본문에서 그대로 옮긴 인용문). 답이 없는 부분은 `missing`(확인 필요 사유) |

- 프롬프트는 `ChatPromptTemplate.from_messages([("system", ...), ("human", ...)])`. 분류와 변환 프롬프트는 main 맨 위,  
  답변 프롬프트는 실습 함수 옆(`core_search.py`)에 둠. 근거와 검색 결과는 `<근거>`, `<검색결과>` 태그로 감쌈(지시와 데이터 구분)
- 스키마 칸마다 `Field(description=...)`를 붙여 LLM이 칸의 뜻을 읽게 함
- `method="json_schema", strict=True`: 실측(2026-10-25)에서 strict를 빼면 gpt-oss-120b가 스키마를 되돌려 파싱이 실패함.  
  `strict=True`면 분류 2건(잡담, 복합) 모두 정상, 0.8 ~ 1.0초
- 실습 함수 `generate_answer`의 빈칸 2곳이 바로 이 두 줄임: ① `llm.with_structured_output(GroundedAnswer, ...)` ② `prompt | 구조화 모델`

## 3. 디렉토리 구성

```text
hands-on/solutions/rag/
├─ .venv/                      인덱싱과 검색 공용 가상환경(이미 있음. 새 패키지 없음)
├─ indexing/                   (기존, 읽기만) data/(chroma, bm25), core_indexing.py(질문 토큰화. 색인과 같은 규칙)
└─ retriever/
   ├─ README.md                맨 위에 수업용 명령 2개, 목표와 기능, 구조, 가상환경 설정(PowerShell, Git Bash, macOS와 Linux),
   │                           실행 방법, 출력 읽는 법, 용어 풀이, 실측값
   ├─ search_docs.py           main: 설정 상수(기준값, 상한), 프롬프트(분류, 질문 변환), 스키마, 시작 검사, 색인 열기,
   │                           LLM 호출 2종, 단계 함수 ① ~ ⑥, run_workflow(분기와 반복 상한), 화면 출력, 명령행
   ├─ core_search.py           핵심(클론 코딩 대상): 실습 함수 10개 + 제공 함수
   └─ my_search.py             교육생 작업 파일(뼈대). 맨 아래 USE_TEACHER_CODE 목록의 함수는 강사 코드가 대신 돎
```

- 교육생이 여는 파일: `search_docs.py`(읽기)와 `my_search.py`(쓰기). 설정 파일은 두지 않음
- `core_indexing.py`는 복사하지 않고 import함(색인과 같은 토큰화여야 BM25가 맞음. W3에서 직접 작성한 함수임)
- 결과 파일을 남기지 않음(화면 출력만). 그래서 `logs/` 폴더와 `.gitignore`가 없음
- 비밀값: 저장소 루트 `secrets/.env`를 `dotenv_values()`로 읽어 **클라이언트마다 인자로 넘김**(환경변수에 올리지 않음, 화면에 찍지 않음)

  | 키(`secrets/.env`) | 넘기는 곳 |
  |---|---|
  | `GROQ_API_KEY` | `ChatGroq(api_key=...)` |
  | `COHERE_API_KEY` | `CohereEmbeddings(cohere_api_key=...)`, `cohere.ClientV2(api_key=...)` |

## 4. 워크플로우와 실습 함수 선별

방식 선택 기준(인덱싱, GraphRAG 실습과 같음)

- **직접 작성**: 개념이 순수 파이썬 논리(비교, 정렬, 조건)에 있어 손으로 써야 남는 함수.  
  뼈대는 `raise NotImplementedError("여기에 본인 코드를 작성함")`
- **빈칸 채우기**: 개념이 라이브러리 호출의 「무엇을 어떤 순서로 부르나」에 있거나, 규칙이 많아 처음부터 쓰면 시간이 넘치는 함수.  
  뼈대는 거의 완성된 코드에 `raise NotImplementedError("빈칸 N을 채울 것")`

실습 함수는 모두 `core_search.py`(정답)와 `my_search.py`(뼈대)에 같은 이름으로 있음. 「하는 일」의 나머지는 main과 제공 함수가 맡음.  
질의는 검색에 쓰는 문장임. 단순 질문이면 원 질문 1개, 복합 질문이면 하위 질문 2 ~ 3개임.

| 단계 | 하는 일(main이 부르는 흐름) | 교재 | 실습 함수 | 방식 | 실습 개념 |
|---|---|---|---|---|---|
| ① 권한 필터 | 회원번호를 가명 ID로 바꿈(제공 `member_pseudonym`) → 벡터용 Chroma 필터 → BM25용 0과 1 마스크(제공 `build_weight_mask`, 같은 규칙 `is_chunk_allowed`) | 151 | `build_chroma_filter` | 빈칸 2곳 | agent는 public만, auditor + 회원은 그 회원의 restricted만, auditor만이면 조건 없음. 메타데이터 필터 `$eq`(같음)와 `$and`(모두 만족). 권한은 LLM이 아니라 코드가 검색 전에 정함 |
| ② Adaptive 분류 | 분류 LLM 호출(main, 2.1) → 규칙 확정 → 잡담이면 인사 답을 내고 끝(검색 0회), 단순이면 질의 1개, 복합이면 하위 질문 2 ~ 3개 | 152 ~ 155 | `apply_plan_rules` | 빈칸 3곳 | 규칙 5개: 모르는 유형 → 단순, 업무 낱말이 있는 잡담 → 단순, 하위 질문 1개 이하 → 단순, 최대 3개, 조건 낱말(카드명, 숫자)이 빠지거나 새로 생기면 → 단순. 조건 낱말과 업무 낱말 뽑기는 제공(`condition_terms`, `domain_terms`) |
| ③ 검색: 벡터 | 질의를 Cohere로 임베딩하고 Chroma HNSW로 후보 top_k × 4개 | 159, 160 | `search_vector` | 빈칸 2곳 | `similarity_search_with_score(질의, k, filter)` 한 번으로 임베딩과 근사 검색, ①의 필터를 그대로 넘김. 점수 = 1 - 코사인 거리(클수록 좋게 방향 통일), chunk_id = Chroma id |
| ③ 검색: BM25 | 질의를 색인과 같은 규칙으로 토큰화(`core_indexing.tokenize_korean`) → 저장된 점수표에서 후보 top_k × 4개 | 157, 158 | `search_bm25` | 직접 | bm25s 점수 × 권한 마스크, 0점 제외, (점수, 순번) 내림차순, 벡터 결과와 같은 꼴(chunk_id, text, metadata, score, rank) |
| ③ 검색: 융합 | 벡터와 BM25 후보를 합쳐 상위 top_k × 2개. 복합 질문은 하위 질문별 근거를 RRF로 합침(제공 `fuse_rrf`) | 161, 162, 154 | `fuse_weighted` | 직접 | 최소-최대 정규화(보조 함수 제공) 뒤 벡터 0.6 + BM25 0.4. 한쪽에만 있으면 없는 쪽 0점. 어느 검색에서 왔는지(found_in) 남김 |
| ③ 검색: 리랭크 | 융합 후보 10개를 원 질의 기준으로 다시 채점해 근거 5개 | 163 ~ 166 | `rerank` | 빈칸 2곳 | 본문 목록을 Cohere `rerank(model, query, documents, top_n)`에 한 번 보냄. 응답 `index`(보낸 순번)로 원래 후보를 찾고 `relevance_score`(0 ~ 1)와 리랭크 전 순위(fused_rank)를 남김 |
| ④ CRAG 채점 | 질의마다 신호 계산(제공 `build_signals`) → 판정 → 화면에 신호 6개와 기준값 | 149, 171 | `grade` | 직접 | 부정확(하나라도: 0건, 1위 < 하한) → 정확(모두: 1위 ≥ 상한, 핵심어 포함, 대상 일치, 격차, 겹침) → 나머지 불확실. 같은 결과면 언제나 같은 판정 |
| ④ 질문 변환 | 불확실 질의만 변환 LLM 호출(main, 2.1: 원 질문, 검색 결과, 판정 근거, 이전 시도, 기법 가이드) → 금지 규칙 → 재검색(③) → 재채점. 근거 고르기(제공 `select_evidence`) | 167 ~ 170 | `apply_transform_rules` | 빈칸 3곳 | 금지 규칙 4개(169쪽): 대상명 없음 + 대상 섞임 → clarify, 허용 선택지 밖 → keep, 같은 질의 반복은 버리고 남은 게 없으면 keep, HyDE와 Step-Back은 원 질의 함께 검색. 섞임 판정과 질의 비교 보조 함수는 제공 |
| ⑤ 답변 생성 | 근거를 `<근거>` 태그로 묶어 Groq 호출 → 문장별 청크ID와 인용문. 근거 0건이면 LLM 없이 「확인 필요」 | 172 | `generate_answer` | 빈칸 2곳 | LCEL 체인 `prompt \| llm.with_structured_output(GroundedAnswer)`(2.1). 재작성 때 ⑥의 실패 사유를 프롬프트에 함께 넣음 |
| ⑥ Self-RAG 근거 검증 | 검사 → 실패면 사유를 붙여 ⑤ 재작성(최대 2회, main) → 다 쓰면 「확인 필요」 | 173 | `verify_answer` | 직접 | 실패 3종: 청크ID 없는 문장, 근거 묶음에 없는 청크ID, 인용문이 그 청크 본문에 없음. 공백을 지우고 비교(PDF 줄바꿈 차이). 빈 목록이면 통과 |

- 합계 10개: 직접 4개(`search_bm25`, `fuse_weighted`, `grade`, `verify_answer`),  
  빈칸 6개(`build_chroma_filter`, `apply_plan_rules`, `search_vector`, `rerank`, `apply_transform_rules`, `generate_answer`)
- 6단계 모두 실습 함수가 있음: ① 1개, ② 1개, ③ 4개(벡터, BM25, 융합, 리랭크), ④ 2개(채점, 질문 변환), ⑤ 1개, ⑥ 1개
- 제공 함수(읽고 이해, 클론 대상 아님): `member_pseudonym`, `is_chunk_allowed`, `build_weight_mask`, `condition_terms`, `domain_terms`,  
  `_normalize_scores`와 묶기 보조 함수, `fuse_rrf`, `merge_query_results`(재검색 질의 합치기), `build_signals`, `select_evidence`,  
  `mixed_target_clarify`(대상 섞임 판정), `format_evidence`
- main 제공(읽기): 시작 검사, 색인 열기, `classify_question`, `transform_query`, `run_workflow`, 화면 출력

### 4.1 분기와 반복 규칙(run_workflow)

| 자리 | 조건 | 다음 | 상한 |
|---|---|---|---|
| ② 뒤 | 잡담 | 인사 답을 내고 끝(종료 상태 「잡담」) | - |
| ② 뒤 | 단순 / 복합 | 질의 1개 / 2 ~ 3개로 ③ | `MAX_SUB_QUESTIONS` 3 |
| ④ 뒤 | 불확실 질의 없음 | 정확 질의 근거로 ⑤. 부정확 질의는 근거에서 뺌 | - |
| ④ 뒤 | 불확실 질의 있음 | 그 질의만 질문 변환 → 금지 규칙 → 재검색 → 재채점 | `MAX_RESEARCH` 1회 |
| 변환 뒤 | 기법 clarify | 질의 개수와 상관없이 되묻는 문장을 내고 끝(종료 상태 「되묻기」) | - |
| 변환 뒤 | 기법 keep(바꿀 것 없음, 규칙 위반, 변환 실패) | 재검색 없이 원 결과 유지 | 재검색 횟수를 쓰지 않음 |
| 재검색 뒤 | 판정 | 정확 질의 근거 + 불확실 질의 근거 중 리랭크 0.3 이상만 ⑤로(D2). 화면에 「불확실 근거 포함」 | - |
| ④ 뒤 | 모든 질의 부정확, 또는 남은 근거 0건 | LLM 없이 「확인 필요: 근거 부족」(종료 상태 「근거 부족」) | - |
| ⑤ 뒤 | 인용 문장 0개(「확인 필요」만) | ⑥ 건너뛰고 끝. 인용 문장이 있으면 그 문장만 ⑥ | - |
| ⑥ 뒤 | 실패 | 실패 사유를 넣어 ⑤ 다시 | `MAX_REWRITES` 2회(⑤ 최대 3번) |
| ⑥ 뒤 | 재작성을 다 씀 | 「확인 필요: 인용 검증을 통과하지 못함」 + 마지막 실패 사유(종료 상태 「검증 실패」) | - |

- 재검색 질의 합치기(154쪽, 제공 `merge_query_results`): Multi-Query는 같은 답을 찾는 다른 표현이라 질의별 융합 점수를 평균(가중합).  
  HyDE와 Step-Back은 원 질의도 함께 검색해 같은 방식으로 합침(167쪽 「원 질문 검색: HyDE, Step-Back은 필수」)
- 리랭크는 변환 질의가 아니라 **원 질의(하위 질문)** 기준으로 매김. HyDE 가상 답변처럼 검색 문장이 바뀌어도 관련성은 원래 물음으로 잼
- 호출 수 상한: 질문 하나당 LLM 최대 7번(분류 1 + 변환 3 + 답변 3), Cohere 최대 18번(복합 3질의 × (임베딩 1 + 리랭크 1) +  
  재검색 3질의 × (임베딩 3 + 리랭크 1)). 반복이 모두 고정 상한이라 따로 호출 상한 상수는 두지 않고 소비량만 찍음
- 종료 상태 6가지: 답변 완료, 잡담, 되묻기, 근거 부족, 검증 실패, 오류. 「확인 필요」도 정상 종료임
- 교육생 함수 예외: 감추지 않고 화면에 띄운 뒤 그 질문을 「오류」로 끝냄(어디가 틀렸는지 보이는 쪽이 학습에 유리)

### 4.2 외부 API 제한 시간과 실패 대체

| 자리 | 제한 시간, 재시도 | 실패 뒤 대체 |
|---|---|---|
| ② 분류 Groq | 60초, 재시도 2번 | 단순 질문으로 처리(원 질의 1개), 경고 |
| ③ 임베딩 Cohere | 30초 | 그 질의는 BM25 결과만으로 융합, 경고 |
| ③ 리랭크 Cohere | 30초, 재시도 1번 | 융합 순위 그대로, 주 점수 없음 → 판정은 최대 불확실이지만 **재검색 대상에서 뺌**(호출 폭증 연쇄 방지). 근거는 융합 상위 5개 |
| ④ 변환 Groq | 60초, 재시도 2번 | keep(원 결과 유지) |
| ⑤ 답변 Groq | 60초, 재시도 2번 | 「확인 필요: 답변 생성 실패(사유)」, 근거 목록만 |
| 공통 429 | - | 오류 문구에 「조별 한 대만 실행, 1 ~ 2분 뒤 다시」 안내 |

- 외부 API 예외만 이 표대로 처리하고, 교육생 실습 함수의 예외는 그대로 띄움(4.1). 값은 출발값이며 실측 뒤 README에 고침

### 4.3 채점 신호와 기준값(교재 149쪽)

| 신호 | 계산(제공 `build_signals`) | 판정 역할 | 기준값(초깃값) |
|---|---|---|---|
| 결과 수 | 최종 근거 개수 | 0건이면 부정확 | - |
| 주 점수 | 1위 리랭크 점수 | 하한 미만 부정확, 상한 이상이 정확 조건 | 상한 0.7, 하한 0.3 |
| 격차 | 1위와 「다른 대상」 중 최고 점수의 차. 대상 = 카드 코드(`card_id`). 카드가 없는 청크(약관, 상담)는 청크 자신 | 미달이면 불확실 | 0.05 |
| 핵심어 포함 | 질문 토큰 중 카드명, 숫자, 조항 번호(제N조)가 결과 본문 토큰에 모두 있는지 | 없으면 불확실 | - |
| 대상 일치 | 질문의 카드와 1위 청크의 카드가 같은지(카드명 사전으로 통일) | 다르면 불확실 | - |
| 검색기 합의 | 벡터, BM25 상위 top_k 겹침 수. 1위 0.9 이상이면 면제 | 미달이면 불확실 | 1개, 면제 0.9 |

- 핵심어가 0개인 질문은 핵심어 신호를 통과로 보고 화면에 「핵심어 없음」을 찍음. 나머지 신호가 판정을 맡음.  
  평가셋에서 헐거우면 「핵심어 0개면 정확 금지」로 바꿈(11장)
- 약관 청크를 원천 파일 단위로 묶지 않는 이유: 약관 안의 다른 조항끼리 경쟁자가 사라져 격차가 늘 통과하기 때문임(플로니)
- 기준값은 평가셋 25문항을 `--qid`로 돌린 실측으로 조정하고 README에 근거를 적음(149쪽 「기준값은 평가셋으로 결정」)

### 4.4 권한 필터

| 역할 | 볼 수 있는 청크 | Chroma 필터 | BM25 마스크 |
|---|---|---|---|
| `agent`(상담사) | public(약관, 혜택) | `{"access_level": {"$eq": "public"}}` | public 청크만 1 |
| `auditor`(감사자) | 전부 | 없음(None) | 전부 1 |
| `auditor` + 회원 | 그 회원의 상담 이력(restricted)만 | `$and`(restricted, 그 회원 가명 ID) | 그 회원 청크만 1 |

- agent에 `--member-id`를 주면 무시하고 안내함(agent는 상담 이력을 볼 수 없음)
- auditor + 회원이 public을 빼는 이유: 약관이 섞이면 회원 질문 근거 5개 중 절반이 약관으로 채워짐(이전 예제 실측)
- `--qid`는 평가셋 `filters`에 회원이 있으면 auditor + 그 회원, 나머지는 agent로 자동 실행(이전 예제와 같은 규칙)

## 5. 실습 순서와 교시 배치(안)

`teacher/plan/rag-실습계획서.md` 7장의 W4 배치 중 검색 실습을 이 배치로 대체함.  
함수는 워크플로우 순서대로 채움. 뼈대 맨 아래 `USE_TEACHER_CODE` 목록 덕분에 앞 교시에서 막혀도 전체가 완주됨.

| 교시 | 내용 | 함수(순서대로, 예상 줄 수) | 직접 : 빈칸 | 교시 끝에 확인할 것 |
|---|---|---|---|---|
| 1 | 교재 144 ~ 173쪽 이론, 강사 화면으로 ① ~ ⑥ 출력 읽기, 교체 방법 시연 | - | - | 복합 질문이 하위 질문 2개로 나뉘고, 불확실 → 재검색 → 답변까지 가는 화면 |
| 2 | ①, ②, ③ 벡터 | `build_chroma_filter`(15) → `apply_plan_rules`(35) → `search_vector`(20) | 0 : 3 | 5.1 표의 ①, ②, ③ 벡터 |
| 3 | ③ BM25, 융합, 리랭크 | `search_bm25`(20) → `fuse_weighted`(20) → `rerank`(25) | 2 : 1 | 5.1 표의 ③ BM25, 융합, 리랭크 |
| 4 | ④, ⑤, ⑥ | `grade`(20) → `apply_transform_rules`(35) → `generate_answer`(20) → `verify_answer`(25) | 2 : 2 | 5.1 표의 ④ ~ ⑥ |

- 교시 4는 네 개이나 `generate_answer`(빈칸 2곳)는 짧음. 넘치면 `apply_transform_rules`를 숙제로 돌림
- 수업 중 실행은 조별 1대를 기본으로 함(Cohere 체험 키 리랭크 분당 10회, 복합 질문 1번에 최대 6회)
- 함수 하나를 고칠 때마다 수업용 질문 1개만 돌려 확인함. API를 아끼는 옵션: `--no-answer`(⑤, ⑥ 건너뜀)
- 수업용 질문: Q01(약관, 단순), Q07(카드 혜택, 대상 일치), Q14(회원 상담, auditor), Q18(답 없음, 확인 필요).  
  강사 시연: 「안녕하세요」(잡담), 154쪽 복합 질문(분해), 「연회비 면제 조건이 뭐예요?」(대상 섞임 → 되묻기 또는 재검색)

### 5.1 교육생 확인표(화면 출력 항목과 정상 기준)

| 실습 함수 | 확인 명령(예) | 화면에서 볼 것 | 정상 기준(실측 뒤 README에 숫자 확정) |
|---|---|---|---|
| `build_chroma_filter` | `--qid Q14`, 같은 질문을 `--role agent`로 | Chroma 필터, BM25 대상 청크 수 | agent 212개(public), auditor + M-1042는 그 회원 청크만, agent는 상담 근거 0건 |
| `apply_plan_rules` | `"안녕하세요"`, `--qid Q01`, 154쪽 복합 질문 | LLM 제안 → 규칙 판정, 바뀐 이유(경고) | 잡담은 검색 0회, Q01은 단순, 복합은 하위 질문 2개 |
| `search_vector` | `--qid Q01 --no-answer` | 벡터 상위 순위와 점수 | 점수 0 ~ 1, 내림차순, 정답 청크(제10조)가 위. agent면 상담 청크 0건 |
| `search_bm25` | `--qid Q07 --no-answer` | 질문 토큰, BM25 상위 순위 | `한빛모아생활`이 한 토큰, 점수 내림차순, D2-C001 청크가 위 |
| `fuse_weighted` | 같은 명령 | 융합 점수와 [vector, bm25] 표시 | 두 검색에 모두 나온 청크가 위로, 양쪽 1위면 1.0 |
| `rerank` | 같은 명령 | 융합 n위 → 리랭크 m위, 리랭크 점수 | 점수 0 ~ 1, 정답 청크는 0.7 이상으로 올라옴 |
| `grade` | `--qid Q01`, `--qid Q18` | 신호 6개 값과 기준값, 판정 | 같은 질문이면 같은 판정. Q18은 정확이 아님 |
| `apply_transform_rules` | `"연회비 면제 조건이 뭐예요?"` | LLM이 고른 기법과 질의 → 규칙 뒤 결정, 바뀐 이유 | 대상 섞임이면 clarify, HyDE와 Step-Back이면 원 질의 포함, 재검색 전후 순위 |
| `generate_answer` | `--qid Q01`, `--qid Q18` | 문장별 청크ID와 인용문 | Q18은 「확인 필요:」로 끝남 |
| `verify_answer` | `--qid Q01` | 검사 결과, 실패 사유, 재작성 횟수 | 「검증 통과」 또는 사유와 「재작성 1/2」 |

## 6. 교체 방법

1. `my_search.py`에 같은 이름, 같은 인자의 함수를 채움
2. `search_docs.py`의 import 한 줄을 바꿈: `import core_search as core` → `import my_search as core`
3. `my_search.py` 맨 아래 `USE_TEACHER_CODE` 목록에서 지금 채운 함수 이름을 지움(남은 함수는 강사 코드가 대신 돎)
4. 같은 명령으로 다시 실행해 5.1 표대로 강사 결과와 비교함. 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감
5. W3 인덱싱을 `my_indexing.py`로 했다면 `search_docs.py`의 `import core_indexing as indexing`도 바꿈(질문 토큰화를 색인과 맞춤)

## 7. 실행 방법과 비용

| 쓰임 | 명령(예) | 용도 |
|---|---|---|
| 평가셋 질문 | `search_docs.py --qid Q01` | 수업 중 함수 확인. 역할은 평가셋 `filters`대로 자동 |
| 자유 질문 | `search_docs.py "질문" --role agent` | 강사 시연, 교육생 실험. `--role auditor --member-id M-1042`로 회원 지정 |
| 답변 끔 | 위 명령 + `--no-answer` | ⑤, ⑥ 건너뜀(Groq 호출은 ②, ④만) |
| 기타 | `--top-k 5`, `--fusion weighted 또는 rrf` | 근거 수, 융합 방식 |

- 비용(이전 예제 실측 기준 추정): 질문 1개에 Cohere 약 $0.002 ~ 0.01(리랭크 1 ~ 4회), Groq 약 $0.001 미만. 실측은 README에 적음
- 화면에는 회원번호 대신 가명 ID를 씀

## 8. 모델과 패키지

| 항목 | 값 |
|---|---|
| LLM(②, ④, ⑤) | Groq `openai/gpt-oss-120b`(`ChatGroq`, temperature 0.2, max_retries 2, timeout 60초). LCEL 체인 + `with_structured_output(..., method="json_schema", strict=True)` |
| 임베딩 | Cohere `embed-v5.0-fast` 2048차원(인덱서와 같은 모델). `langchain-cohere 0.6.0` `CohereEmbeddings` + `langchain-chroma 1.1.0` |
| 리랭커 | Cohere `rerank-v4.0-fast`. `cohere.ClientV2.rerank`(LangChain `CohereRerank`는 점수를 메타데이터에 숨겨 SDK 직접 사용, 이전 예제와 같은 결정) |
| BM25 | `bm25s 0.3.14` 저장 색인 읽기 + `kiwipiepy 0.23.2`(인덱서 `core_indexing.tokenize_korean`) |
| Python | 3.13, 공용 가상환경 `hands-on/solutions/rag/.venv`(새 패키지 없음) |

- context7은 월 한도 초과로 응답하지 않음(2026-10-25 확인). 설치된 패키지 소스에서 확인함  
  (`ChatGroq.with_structured_output`의 `method`: `function_calling`, `json_mode`, `json_schema`, 인자 `strict`).  
  개발 중 문서가 더 필요하면 GraphRAG 검색 때처럼 `secrets/.env`의 `CONTEXT7_API_KEY`로 REST API를 부름

## 9. 사전 과제와 환경 점검(교육생)

| 번호 | 과제 | 확인 방법 |
|---|---|---|
| 1 | W3 인덱싱 실습 완료(또는 강사 배포 `indexing/data/` 복사. `chroma/`와 `bm25/` 둘 다) | `indexing/data/bm25/manifest.json` 있음, `chunk_count` 260 |
| 2 | 공용 가상환경 `rag/.venv`(W3에서 설치) | 설치 확인 명령이 `ok` |
| 3 | `secrets/.env`에 키 2개(`GROQ_API_KEY`, `COHERE_API_KEY`) | `search_docs.py --qid Q01`이 ⑥까지 끝나고 종료 상태 「답변 완료」 |

`search_docs.py`의 시작 검사가 1과 3을 확인하고 빠진 것과 할 일을 출력함.

## 10. 용어 풀이(README와 실습 가이드에 넣음)

Adaptive RAG(질문 유형에 따라 길을 가름), CRAG(검색 결과를 채점하고 고침), Self-RAG(검색할지 묻고 답을 스스로 검증함),  
Decomposition(질문을 하위 질문으로 나눔), Query Rewriting(흐린 질문을 또렷하게), Multi-Query(같은 질문을 여러 표현으로),  
HyDE(가상 답변으로 검색), Step-Back(상위 개념으로 넓혀 검색), keep(바꾸지 않음), clarify(사용자에게 되물음),  
HNSW(가까운 벡터를 빠르게 찾는 근사 검색 색인), 코사인 거리, RRF(순위로만 합치는 방식), 최소-최대 정규화,  
리랭크(질문과 청크를 한 쌍으로 다시 채점), 주 점수, 격차, 검색기 합의, 구조화 출력, LCEL, `$eq`와 `$and`(메타데이터 필터), 가명 ID

## 11. 검증 계획(정직한 보고 기준)

| 검증 | 완료 기준 |
|---|---|
| 경로별 실행 | 잡담, 단순 정확, 복합(분해), 불확실 → 재검색, clarify, 부정확 → 근거 부족, 「확인 필요」 답(⑥ 건너뜀), 검증 실패 → 재작성을 각각 실제 질문으로 한 번 이상 실행해 화면 기록 |
| 평가셋 25문항 | 강사 검증용으로 `--qid Q01` ~ `Q25`를 차례로 실행(예제에는 일괄 실행 옵션을 두지 않으므로 셸 반복문 또는 스크래치 스크립트). 답 있는 20문항은 평가셋 `relevance.any_of` 문장이 최종 근거 5개 안에 있으면 적중(공백 무시), 답 없는 5문항(Q18 ~ Q22)은 모두 「확인 필요」. 이전 예제(17문항 17/17, 5문항 5/5)보다 나빠지지 않게 기준값 조정. 결과는 README 실측값에만 적음 |
| 권한 | 같은 상담 질문을 agent(상담 근거 0건)와 auditor + 회원(그 회원 청크만)으로 실행 |
| 실패 대체 | 리랭크와 답변 LLM 예외를 일부러 일으켜(잘못된 모델명) 4.2 표대로 도는지 확인 |
| 뼈대 교체 | `my_search.py`를 정답으로 채운 사본이 같은 결과. 빈 뼈대는 목록 덕분에 완주, 목록에서 지운 함수만 `NotImplementedError` → 「오류」 |
| 주석 | `references/dev-comment-guide.md` 10장 체크리스트, 핵심 파일은 줄 단위 주석, 줄 길이 120자, pyflakes 통과 |

## 12. 작업 순서

1. 개발계획서 초안 → 팀원 리뷰(완료) → 최종안(이 문서) → 강사 승인(13장)
2. `core_search.py` → `search_docs.py` → 경로별 실행 → 평가셋 25문항 → 기준값 조정
3. `my_search.py` 뼈대 → 교체 경로 확인 → README
4. 교육생 실습 가이드(마크다운) → 핵심 슬라이드(상세는 원격 Git 링크) → 렌더링 검증
5. 교재 코드 장표(12.1): 장표 스크립트 → 발췌, 빌드 → 렌더링 확인 → 교재 백업 → 교체

### 12.1 교재 코드 장표 교체(D4)

| 항목 | 내용 |
|---|---|
| 바꿀 자리 | 150쪽(구성안: 범례 「상세 예제에 구현」 삭제, 6단계 모두 실습 예제, 핵심 코드 열을 실제 함수명으로, 출처), 코드 장표 9장: 151(①), 155(②), 158(③ BM25), 160(③ 벡터), 162(③ 융합), 166(③ 리랭크), 171(④ 채점과 질문 변환), 172(⑤), 173(⑥) |
| 장 구성 | GraphRAG 검색 코드 장표와 같은 모양: 왼쪽 실제 소스 발췌, 중요한 줄에 일련번호(단계 번호 ① ~ ⑥과 헷갈리지 않게 ❶, ❷, ❸ …), 오른쪽 번호별 설명, 아래 출처 파일과 함수 이름, 상세 보기 링크(원격 Git) |
| 발췌 규칙 | 실제 소스에서 발췌기가 자동으로 꺼냄(`build/code_excerpt.py` 재사용). docstring과 주석은 빼고 나머지 글자는 소스 그대로. 생략은 `...` 한 줄. 코드를 고치면 발췌와 빌드, 교체를 다시 돌림 |
| 문구 정리 | 173쪽 「실습 예제(hands-on)에는 이 단계가 없음」, 각 장 「상세 예제 발췌」 출처, 이전 줄 번호 ①②(단계 번호와 겹침)를 모두 없앰. 개념 장표(153, 154, 156, 157, 159, 161, 163 ~ 165, 167 ~ 170쪽)는 그대로 둠 |
| 171쪽 | ④에 실습 함수가 둘(`grade`, `apply_transform_rules`)이라 한 장에 두 함수를 발췌함. 넘치면 `apply_transform_rules`는 핵심 줄만 남기고 `...`로 줄임(쪽 수 유지) |
| 형식 | `references/pptx-guide.md` 준수, 글꼴 Pretendard, 링크는 눌리게. 미리보기는 `scripts/render-pptx.py`(LibreOffice) |
| 교재 반영 | 교재 파일을 닫은 상태에서 백업(`backup/…backup-YYYYMMDD-rag-search-code.pptx`) 뒤 교체. 쪽 수(150 ~ 173)는 바꾸지 않음 |

## 13. 결정 사항과 승인 요청

| 번호 | 항목 | 제안 | 대안 | 팀 의견 |
|---|---|---|---|---|
| D1 | 흐름 구현 | main `run_workflow` 한 함수의 파이썬 `if`와 `for`, 상한 상수 3개(`MAX_SUB_QUESTIONS`, `MAX_RESEARCH`, `MAX_REWRITES`)를 맨 위에 | LangGraph `StateGraph`(조건부 엣지) | 둘 다 찬성. GraphRAG 검색은 에이전트 고리라 `create_agent`를 썼지만 여기는 고르는 주체가 없는 고정 분기임 |
| D2 | 재검색 뒤에도 불확실 | 리랭크 0.3 이상 근거만 ⑤로 넘겨 답변 LLM이 판단, ⑥이 인용 검증, 화면에 「불확실 근거 포함」 | 바로 「확인 필요」로 끝(상세 예제 방식) | 둘 다 조건부 찬성(점수 하한과 화면 표시가 조건. 반영함) |
| D3 | 실습 함수 수와 교시 | **강사 지시 반영: 10개**(직접 4, 빈칸 6). 벡터 검색, 리랭크, 질문 변환을 실습에 넣음. 이론 1교시 + 클론 코딩 3교시 | - | 에듀니는 처음 초안(7개)에서도 초보자 시간을 우려했음. 빈칸 비중을 늘려(6개) 교시당 3 ~ 4개로 맞춤 |
| D4 | 교재 코드 장표 | 150쪽과 코드 장표 9장을 새 예제 발췌로 교체(12.1) | 상세 예제 발췌 유지 | 둘 다 찬성(에듀니: 150, 172쪽 포함 필수) |
| D5 | API 비용 | 개발과 검증에 약 $2 이내(평가셋 25문항 3 ~ 4회, 경로별 단건) | - | - |

## 14. 검토 이력

| 단계 | 내용 |
|---|---|
| 초안 v0.1 | 클로니 작성(2026-10-25). 교재 144 ~ 173쪽, 이전 예제, 상세 예제의 규칙 코드를 대조 |
| 구조화 출력 실측 | Groq `json_schema`는 `strict=True` 필수 확인(2.1) |
| 플로니 검토 | 조건부 통과. 반영 10건: 「확인 필요」 답은 ⑥ 건너뜀, 정확과 부정확 혼재 경로, 불확실 근거 점수 하한(`select_evidence`), 외부 API 실패 대체 표(4.2), 상한 소비량 화면 표시, clarify와 keep 분리, 격차 대상 정의(약관은 청크 단위), 핵심어 0개 처리, 리랭크 실패 질의는 재검색 제외, 조별 1대 |
| 에듀니 검토 | 수정 후 사용. 반영 9건: 기존 W4 배치 대체 명기, Multi-Query 합치기를 154쪽대로 가중합으로, D4 범위에 150, 172쪽 추가, 핵심어에 조항 번호 추가와 용어 정정(역문서 빈도), 교육생 확인표(5.1), 사전 과제 확인을 검색 경로로, 조별 1대와 수업용 질문, 용어 풀이(10장) |
| 재작성 v0.3 | 강사 지시(2026-10-26): `graphrag-search-개발계획서.md` 형식으로 다시 쓰고 150쪽 ① ~ ⑥을 모두 포함 |
| 강사 지시 v0.4 | 2026-10-26 지시 5건 반영: ① RAGAS 실행 제거(results.json, RAGAS 호환 검증 삭제) ② 벡터 검색 실습 추가(`search_vector`, 빈칸 2곳) ③ 리랭크 필수 실습(`rerank`, 빈칸 2곳. 선택 과제 `fuse_rrf`는 제공 함수로) ④ 질문 변환 실습 추가(`apply_transform_rules`, 빈칸 3곳) ⑤ `--eval`, `--plan` 옵션 제거(평가셋 25문항은 강사 검증 때 `--qid`로 차례로 실행). 교시 배치를 이론 1 + 클론 코딩 3으로 바꿈 |
| 강사 승인 | 2026-10-26 「v0.4 계획서대로 승인해요. 개발을 시작해요」 |

## 15. 개발 결과(2026-10-26)

| 산출물 | 경로 | 상태 |
|---|---|---|
| 예제 프로그램 | `hands-on/solutions/rag/retriever/`(search_docs.py, core_search.py, my_search.py, README.md. 패키지는 상위 `rag/requirements.txt`) | 완료 |
| 공통 README | `hands-on/solutions/rag/README.md`(RAGAS, run_eval 언급을 빼고 새 검색기로 고침) | 완료 |
| 교육생 실습 가이드 | `teacher/plan/rag-search-실습가이드.md`(에듀니 작성, 클로니 검수) | 완료 |
| 핵심 슬라이드 | `teacher/plan/rag-search-실습가이드.pptx`(6장, 스크립트 `…-slides.md`, 빌드 `build/build-rag-search-guide-slides.js`) | 완료. 붙여넣기 점검 OK, LibreOffice 미리보기 6장 확인 |
| 교재 코드 장표 | `teacher/plan/rag-search-code.pptx`(10장, 스크립트 `rag-search-code-slides.md`, 발췌 `build/extract-rag-search-code.py`, 빌드 `build/build-rag-search-code.js`, 넣기 `build/merge-rag-search-code.py`) | 빌드와 교재 사본 교체 시험 완료. 원본 반영은 15.3 |

### 15.1 검증 결과(11장 기준)

| 검증 | 결과 |
|---|---|
| 평가셋 25문항(`--qid` 차례 실행, 4회차) | 답 있는 20문항: 답변 완료 18, 근거 적중 18/20. 답 없는 5문항: 5/5 답변 완료 아님(근거 부족 4, 되묻기 1). 못 답한 Q23, Q24는 여러 상담을 모아 묻는 경향 질문(GraphRAG 몫) |
| 경로별 실행 | 잡담, 단순 정확, 복합(154쪽 질문, 하위 질문 2개 모두 정확), 불확실 → rewrite, multi, hyde, stepback 재검색, 대상 섞임 → 되묻기(Q18), 부정확(비트코인 시세), 핵심어 없음 → 근거 부족(Q20), 「확인 필요」 답(⑥ 건너뜀), 검증 실패 → 재작성 1/2 → 통과(Q17, 개발 중 실행) |
| 권한 | agent 212청크, auditor + M-1042는 4청크. Q14를 agent로 돌리면 상담 청크 0건 |
| 실패 대체 | 리랭크 모델명 오류 → 융합 순위로 답변 완료, 재검색 제외. LLM 모델명 오류 → ② 단순 처리, ⑤ 「확인 필요: 답변 생성 실패」 |
| 뼈대 교체 | 빈칸을 정답으로 채운 사본, 목록 그대로인 뼈대, 강사 코드가 같은 근거를 냄(3문항). 목록에서 `search_bm25`를 지우면 `NotImplementedError`. 채운 사본으로 되묻기, 부정확, 정확, 재검색 경로 실행. 실습 함수 10개 시그니처가 정답과 같음 |
| 주석, 형식 | 핵심 파일 줄 단위 주석, 줄 길이 120자 이내, pyflakes 통과(뼈대의 빈칸 변수와 제공 import는 의도된 경고) |
| 호출과 비용 | 25문항 합계 LLM 59번, 임베딩 46번, 리랭크 41번(약 $0.1). 문항당 중앙값 3.6초 |

### 15.2 개발 중 바꾼 것(README 7.3에 상세)

- 근거를 `<청크 id="...">` 태그로 감쌈: 혜택 청크 본문의 카드 코드(D2-C001-B02)를 청크ID로 인용해 검증이 늘 실패했음(5문항)
- 회원번호(M-1042 꼴)를 ① 뒤 ② ~ ⑤의 질문에서 지움: 핵심어로 잡혀 늘 「근거에 없음」이 되고, 답변 LLM은 「그 회원 것인지 확인 불가」로 답했음
- 불확실 질의는 핵심어가 근거에 없으면 근거에서 뺌(`select_evidence`): Q20 「이전 버전(1.1)」에 현재 약관으로 답했음. 교재 149쪽 신호표 「핵심어 일치: 없으면 부정확」
- 복합 질문의 하위 질문에서 LLM이 clarify를 고르면 keep으로 바꿈(main): 짧은 하위 질문 때문에 답 전체를 버렸음(3문항). 분류 프롬프트에 「뒤 질문에도 대상을 다시 적음」 예시 추가
- 답변 프롬프트에 「근거 문장이 질문에 직접 답할 때만 씀」 추가: 경향 질문에 관련 먼 약관 문장으로 답했음
- 교재 코드 장표 발췌를 위해 소스 3곳을 줄 단위로 손봄(동작 같음): 여러 줄 호출 2곳을 한 줄로, 열린 괄호 줄의 줄 끝 주석을 윗줄로
- context7 MCP는 월 한도 초과라, 개발 중에는 설치된 패키지 소스로 확인하고 개발 뒤 REST API로 다시 검증함(15.4)

### 15.3 교재 반영(2026-10-26)

- 교재 사본에 `merge-rag-search-code.py`를 돌려 확인함: 150쪽 표 3칸 고침(③, ④ 핵심 코드, ⑤ 하는 일), 코드 장표 9장 바꿈, 새 장표 1장
- **새 장표 1장**: ④는 실습 함수가 둘(`grade` 18줄, `apply_transform_rules`)이라 14pt로 한 장에 들어가지 않음.  
  그래서 「④ CRAG 채점 – 채점 실제 코드」(171쪽) 뒤에 「④ CRAG 채점 – 질문 변환 실제 코드」(172쪽)를 넣음. 이후 쪽이 하나씩 밀림(⑤ 173쪽, ⑥ 174쪽, 교재 총 212장).  
  12.1의 「쪽 수 유지」와 달라 강사 확인을 받음(2026-10-26 「새 장 넣고 반영」)
- 반영: 백업 `backup/신한카드 하이브리드AI_W01~W04.backup-20261026-rag-search-code.pptx` → `merge-rag-search-code.py` →  
  LibreOffice로 212장 렌더링, 150 ~ 175쪽 확인(코드 넘침 없음, 150쪽 표 3칸, 175쪽 다음 장 간지 그대로)
- 쪽 번호가 바뀐 곳(⑤ 173쪽, ⑥ 174쪽)을 소스 주석, README, 실습 가이드, 가이드 슬라이드에 맞추고 가이드 덱을 다시 빌드함

### 15.4 context7 REST API로 코드 검증(2026-10-26, 강사 지시)

`secrets/.env`의 `CONTEXT7_API_KEY`로 `GET https://context7.com/api/v2/context?libraryId=...&query=...&type=txt`를 불러 대조함.  
Git Bash에서는 `/websites/langchain` 같은 인자가 Windows 경로로 바뀌어 404가 나므로 `MSYS_NO_PATHCONV=1`을 붙임(실측).

| 대상(라이브러리 ID) | 확인한 것 | 결과 |
|---|---|---|
| LangChain(`/websites/langchain`) | `with_structured_output(schema, method="json_schema", strict=True)` | 코드와 같음(strict는 json_schema, function_calling에서만) |
| LangChain | `Chroma.similarity_search_with_score(query, k, filter)`가 (Document, 점수) 쌍을 돌려줌 | 코드와 같음 |
| LangChain | `CohereEmbeddings(model=...)`, `embed_query` | 코드와 같음(키는 인자 `cohere_api_key`로 넘김, 설치 소스로 확인) |
| LangChain | `ChatPromptTemplate.from_messages`, `prompt \| model` LCEL | 코드와 같음 |
| Chroma(`/chroma-core/chroma`) | `$eq`, `$and` 필터. 필터 객체 하나에 필드 하나 또는 논리 연산자 하나 | 코드와 같음(`$and` 목록 안 조건마다 필드 하나) |
| Cohere SDK(`/cohere-ai/cohere-python`) | `ClientV2.rerank(model, query, documents, top_n)`, 응답 `results[].index`, `relevance_score` | 코드와 같음 |
| bm25s(`/xhluca/bm25s`) | `BM25.get_scores(query_tokens, weight_mask=None)`가 문서마다 점수 배열 | 코드와 같음. **빈 토큰 목록은 IndexError(실측)** → main이 질문 토큰 0개면 BM25를 부르지 않게 고침 |


### 15.5 교재 실습 가이드 장표(176쪽, 2026-10-26 강사 지시)

- 강사 지시: 「교재 176 페이지에 실습 가이드 슬라이드를 작성해줘요. 워크플로우 도식화, 실습 방법」
- 자리: 간지 「문서 검색 실습」(175쪽) 바로 뒤 176쪽. 다음 간지 「품질 평가 및 튜닝 이해」는 177쪽으로 밀림(교재 총 210장)
- 내용: 위는 워크플로우 도식(① ~ ⑥ 단계 상자, 상자 아래 단계별 실습 함수 10개, 굵게 = 직접 작성, 분기 메모 3개),  
  아래는 실습 방법(절차 5개, 교시별 실습 함수와 확인 명령 표). 「상세 보기」는 실습 가이드(원격 Git)로 연결
- 파일: 스크립트 `teacher/plan/rag-search-practice-slide.md`, 빌드 `build/build-rag-search-practice.js`,  
  넣기 `build/merge-rag-search-practice.py`(다시 돌리면 같은 제목 장표를 바꿈), 덱 `teacher/plan/rag-search-practice-slide.pptx`
- 확인: 백업 `backup/신한카드 하이브리드AI_W01~W04.backup-20261026-rag-search-practice.pptx` 뒤 넣음. 붙여넣기 점검 OK,  
  zip 이름 중복 0, LibreOffice로 210장 렌더링해 175 ~ 177쪽 확인

### 15.6 가상환경 정리(2026-10-26 강사 지시)

- 강사 지시: 「가상환경 설정을 hands-on/solutions/rag에서 하도록, retriever/requirements.txt는 상위 requirements.txt에 병합, README 수정」
- 두 파일의 패키지와 판이 같아(13개) 상위 `rag/requirements.txt`에 설명 주석만 옮기고 `retriever/requirements.txt`는 지움
- `retriever/README.md` 2장 구조와 3장 가상환경 절을 `hands-on/solutions/rag`에서 `pip install -r requirements.txt` 하도록 고침

- 검증: 임시 폴더에 새 가상환경을 만들어 README 절차대로 `pip install -r requirements.txt`(rag 폴더) → `pip check` 문제 없음,  
  설치 확인 명령 `ok`, `indexing/index_docs.py --limit 8` 완료(청크 64개), `retriever/search_docs.py --qid Q01` 답변 완료,  
  `--qid Q14` 답변 완료(BM25 대상 4청크). 확인 뒤 임시 가상환경은 지움
