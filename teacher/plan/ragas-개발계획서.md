# RAGAS 평가 예제 프로그램 개발계획서

| 항목 | 내용 |
|---|---|
| 작성 | 클로니(오케스트레이터), 2026-10-31 |
| 검토 | 지식니(지표와 평가 설계, 「수정 후 사용」), 에듀니(교육, 「조건부 통과」). 15장 「검토 이력」 |
| 대상 교재 | 『신한카드 하이브리드AI_W01 ~ W04』 「품질 평가 및 튜닝 이해」 176 ~ 193쪽, 실습 코드 장표 195 ~ 207쪽(2026-10-31 반영, 16.4) |
| 평가 대상 | RAG 검색기 `hands-on/solutions/rag/retriever/`(교재 150쪽 ① ~ ⑥ 워크플로우. import해서 그대로 부름) |
| 입력(읽기만) | 평가셋 `hands-on/solutions/eval-set.json`(10문항: 답 있음 8, 답 없음 2(Q20, Q21)),  
RAG 인덱싱 결과 `rag/indexing/data/`(260청크) |
| 산출 위치 | `hands-on/solutions/ragas/`(소스, requirements.txt, README.md), 결과 `ragas/results/{하이퍼 파라미터명}/` |
| 상태 | **v0.2 승인(2026-10-31, `top_k` 3, 5, 10) 뒤 개발 완료, 교재 반영 완료(195 ~ 207쪽). 실행 결과는 16장** |

## 1. 목표

- 교육생이 교재 177쪽 「버전 비교 평가」를 **파이썬 코드로 직접 만들며** 이해함:  
  하이퍼 파라미터 하나를 바꾼 버전들을 **같은 평가셋, 같은 지표**로 채점하고 기준선과 비교함
- 한 번 실행으로 교재의 두 채점을 모두 냄(179쪽 평가 수행 Role의 ①, ②)
  - 코드 평가 4지표(하, 빠, 빨, 앞): Hit@k, Recall@k, MRR, nDCG@k(180, 181쪽). LLM 없이 정답 단서로 계산
  - LLM 평가 5지표(위, 정, 출, 관, 답): ContextPrecision, ContextRecall, Faithfulness, AnswerRelevancy,  
    FactualCorrectness(182 ~ 185, 188쪽). ragas 0.4.3의 `@experiment`, `arun`, `ascore()`
- 강사는 전체 예제를 보여 주고, 교육생은 **단계마다 1개 이상, 실습 함수 9개**를 클론 코딩한 뒤 본인 코드로 바꿔 끼워 실행함
- 단계마다 결과를 화면과 결과 파일에 남김: 버전 목록과 기준선, 문항별 결과 정보 4칸, 순위별 적중 청크와 찾은 정답 근거,  
  문항별 9지표, 버전별 평균과 기준선 대비 변화(▲, ▼, 변화 없음), 지표 조합으로 본 원인 후보(187쪽)
- 한계를 숨기지 않음: 답 있는 8문항 중 6문항이 정답 근거 1개라 Recall@k가 0 또는 1임. 한 문항이 바뀌면 평균이 0.125 움직이므로  
  **최소 식별 변화 0.125, 통계적 유의성은 주장하지 않음**을 README와 결과 파일에 적음(지식니)

## 2. 교재와 다른 점(교육용으로 단순화)

| 항목 | 교재 | 실습 예제 | 이유 |
|---|---|---|---|
| 평가 대상 검색기 | 178쪽 `retriever.search`, `generator.answer`(가상의 객체) | 실제 RAG 검색기의 `run_workflow`를 버전마다 문항마다 부름 | W4에서 만든 검색기를 그대로 채점해야 실습이 이어짐 |
| 실행과 채점의 분리 | 178쪽은 실험 함수 안에서 검색과 채점을 함께 함 | 검색기 실행(단계 ②)을 먼저 끝내고, 그 결과 정보로 채점(③, ④) | 검색기는 화면 출력이 많은 동기 함수임. 채점만 비동기로 돌려 시간과 호출 제한을 다루기 쉬움(188쪽 「결과 정보를 만들고 지표가 읽어 판정」과 같은 구조) |
| ragas에 넘기는 질문과 답변 | 184쪽 질문 칸은 원 질문(M-3001 포함), 답변은 인용 표시 없는 글 | 질문 = **회원번호를 지운 질문**(검색기가 ⑤ 답변 생성에 넘긴 문장), 답변 = **인용 표시(`[D3-0019]`)를 뺀 글** | 평가자가 회원번호와 인용 표시까지 「주장」으로 쪼개, 근거에 없다며 Faithfulness를 0으로 매김(9.1 실측). 모든 버전에 같게 적용하므로 비교는 공정함. 원 질문과 원 답변은 결과 파일에 함께 남김 |
| 결과 저장 | 178쪽 `experiments/top_k/A.csv`(ragas local/csv) | 강사 지시 형식의 마크다운 `results/{하이퍼 파라미터명}/evaluate_{YYMMDDHHMM}_{vNN}.md`. ragas 데이터셋은 메모리(inmemory) | 강사 지시. 마크다운은 사람이 바로 읽음 |
| 비교표 | 178쪽 pandas `groupby` 평균 | 순수 파이썬으로 버전별 평균과 기준선 대비 변화(실습 함수) | 교재 「비교표는 직접 작성」. pandas 문법을 몰라도 읽힘 |
| 코드 평가 적중 판정 | 옛 189쪽(지움) 코드는 청크 ID 비교 | 정답 단서(clues)가 청크 본문에 있으면 적중(180쪽 「적중 청크 판정」). 공백과 줄바꿈을 지우고 비교 | 청크 크기를 바꿔 재색인해도 같은 평가셋으로 채점 가능(180쪽 노트) |
| 판정 이유(reason) | 176, 188쪽 「점수와 판정 이유」 | 결과 파일과 화면에 점수만 씀 | ragas 0.4.3 collections 지표는 reason이 빈 값임(9.1 실측) |
| 사람 평가 | 186쪽 검토표와 kappa | 없음(결과 파일의 문항별 표를 사람이 읽는 데까지) | 범위를 코드와 LLM 채점으로 한정(10장 후속 과제) |

### 2.1 교재에서 바로잡을 곳(개발 뒤 강사 확인)

| 쪽 | 교재 | 실습 코드와 실측 | 제안 |
|---|---|---|---|
| 180, 181 노트 | 「정답 근거 3개 → IDCG 2.13 → nDCG 0.50」 | 본문(관련 청크 4 → 2.56 → 0.41)과 185쪽(0.97)은 관련 청크 수 기준. 코드도 이 기준 | 노트의 0.50 문장을 0.41로. 관련 청크 기준이면 「nDCG가 1을 넘는」 경우가 구조적으로 없음을 덧붙임 |
| 옛 189 | `retrieval_metrics`가 Recall을 적중 청크 수로, IDCG를 정답 근거 수로 셈 | 실습 코드는 180쪽 정의(찾은 정답 근거 수, 관련 청크 수 기준 IDCG) | 해소: 장표를 지우고 실습 코드 장표(199 ~ 200쪽)로 대체함(16.4) |
| 176, 188 | MetricResult의 reason으로 「왜 낮은지 읽을 수 있음」 | 0.4.3 collections 지표는 reason이 빈 값 | 「0.4.3은 점수만 채움(실측)」으로 |
| 182 / 183, 185 | 제목은 「답」, 카드와 185쪽은 「사」 | 실습은 182쪽 제목대로 「답」 | 한쪽으로 통일 |
| 193 / 194 | 「평가셋 20문항」인데 Q25까지 있음 | 실습 평가셋은 10문항(`eval-set.json`), 전체는 `eval-set-full.json` | 문항 수 표기 정리 |
| 181 노트 | 답 없는 문항 「Q18 ~ Q22」 | 실습 10문항의 답 없는 문항은 Q20, Q21 | README에 실습 기준을 적음(장표는 전체 평가셋 기준이라 그대로 둠) |
| 옛 190 | 평가자 `gpt-4o-mini`, `text-embedding-3-small` | 실습은 Groq Qwen, Cohere | 해소: 장표를 지우고 실습 코드 장표(201쪽)로 대체함(16.4) |

## 3. 디렉토리 구성

```text
hands-on/solutions/ragas/
├─ .venv/                    이 실습 전용 가상환경(RAG 검색기 패키지 + ragas). 9장
├─ requirements.txt          패키지 판 고정(RAG 공용 판 + ragas 0.4.3 등. 9.1 실측 판)
├─ README.md                 목표와 기능, 구조, 가상환경(PowerShell, Git Bash, macOS와 Linux), 실행 방법(하이퍼 파라미터 5개별 명령), 결과 읽는 법, 용어 풀이
├─ evaluate_rag.py           main: 설정 상수(모델, 경로, 지원 하이퍼 파라미터), 시작 검사, 버전 만들기, 검색기 실행,
│                            코드 평가, LLM 평가(ragas), 비교, 결과 파일 쓰기, 자체 점검(--selftest), 명령행
├─ core_eval.py              핵심(클론 코딩 대상): 실습 함수 9개 + 제공 함수
├─ my_eval.template.py       교육생 뼈대(강사가 고침). --mine 실행 때 my_eval.py로 복사됨(Git 무시)
└─ results/                  평가 결과 마크다운. results/{하이퍼 파라미터명}/evaluate_{YYMMDDHHMM}_{vNN}.md
```

- 교육생이 여는 파일: `evaluate_rag.py`(읽기)와 `my_eval.py`(쓰기). 설정 파일은 두지 않음(상수는 main 맨 위)
- 검색기는 복사하지 않고 `../rag/retriever/search_docs.py`를 import함. 검색기 화면 출력은 문항별로 모아 결과 파일 상세에 붙이고  
  화면에는 한 줄 요약만 찍음
- 비밀값: 저장소 루트 `secrets/.env`를 `dotenv_values()`로 읽어 클라이언트마다 인자로 넘김(화면과 파일에 찍지 않음)

## 4. 워크플로우와 실습 함수 선별

방식 선택 기준(RAG 검색 실습과 같음)

- **직접 작성**: 개념이 순수 파이썬 계산(비교, 합, 나눗셈)에 있어 손으로 써야 남는 함수. 코드 평가 지표와 비교표가 여기에 속함
- **빈칸 채우기**: 개념이 라이브러리 호출의 「무엇에 어떤 칸을 넘기나」에 있거나, 공식이 길어 처음부터 쓰면 시간이 넘치는 함수.  
  ragas 지표 생성과 `ascore()` 인자, nDCG, 지표 조합 진단이 여기에 속함
- `@experiment` 실험 함수와 `arun` 호출은 main에 있는 **읽기 구간**임(178쪽과 거의 같은 모양, 교재 204쪽). 강사가 5분 해설함

결과 정보 = 한 문항을 한 버전으로 실행한 결과의 4칸(188쪽): 질문(user_input), 모범 답안(reference), 검색 결과(retrieved_contexts),  
답변(response). 코드 평가를 위해 검색 결과의 청크ID, 평가셋의 정답 근거 목록(relevance), 종료 상태도 함께 담음.

| 단계 | 하는 일(main이 부르는 흐름) | 교재 | 실습 함수 | 방식 | 실습 개념 |
|---|---|---|---|---|---|
| ① 버전 만들기 | 명령행의 하이퍼 파라미터명, 값 목록, 기준선 값(생략하면 4.1 표의 현재 값) → 이름 검사 → 버전 목록 | 177, 195, 196 | `build_versions` | 직접 | 버전 = 하이퍼 파라미터 값 한 묶음. **한 번에 하나만 바꿈**(나머지는 기준선 고정). 이름 v01, v02, …, 기준선 ★ |
| ② 검색기 실행 → 결과 정보 | 버전마다 검색기 설정 바꾸기(main `apply_version`, 4.1) → 문항마다 `run_workflow` → ragas용 정리(main `clean_for_ragas`) → 결과 정보 행 | 177, 188, 192 | `make_result_row` | 빈칸 2곳 | 평가셋이 채우는 칸(user_input, reference)과 검색기가 채우는 칸(retrieved_contexts = ⑤에 넘긴 근거 본문 목록, 리랭크 순서. response = 답변) |
| ③ 코드 평가 | 문항마다 적중 판정 → 4지표. 관련 청크 수는 색인 260청크에서 셈(제공, 시작 검사 때 한 번) | 179 ~ 181, 189 | `find_hits` | 직접 | 적중 청크 = 정답 단서를 하나라도 담은 검색 결과 청크(공백 지우고 글자 대조). 찾은 정답 근거는 한 번만 셈 |
| | | | `retrieval_metrics` | 직접 | 하(Hit@k: 적중 청크 있으면 1), 빠(Recall@k: 찾은 정답 근거 수 ÷ 전체 정답 근거 수), 빨(MRR: 1 ÷ 첫 적중 순위). 답 없는 문항은 None |
| | | | `ndcg_at_k` | 빈칸 2곳 | 앞(nDCG@k). 빈칸 = DCG(적중 칸 순위 가중치의 합)와 IDCG(관련 청크를 1위부터 min(관련 청크 수, k)개 채운 합). 순위 가중치 `rank_weight`는 제공 |
| ⑤ 버전 비교 | 버전별 평균(매크로 평균) → 기준선 대비 변화 → 원인 후보 | 177, 178, 181, 187 | `summarize_versions` | 직접 | 지표마다 문항 점수의 평균(None, nan은 뺌), 기준선과의 차이, 흔들림 폭보다 작으면 「변화 없음」 |
| | | | `diagnose` | 빈칸 3곳 | 187쪽 표를 `if`로: Context Recall ↓ → 청킹, 임베딩, Top-k / Context Precision ↓ → 리랭커, 하이브리드 비중 / Faithfulness ↓ → 프롬프트 / Answer Relevancy ↓ → 질문 변환, 프롬프트 / Factual Correctness ↓ → Recall 정상이면 답변 프롬프트, 낮으면 검색 |
| ④ LLM 평가(RAGAS) | 평가자 LLM과 임베딩 준비(main) → 지표 5개 → `@experiment` 실험 함수(main 읽기 구간)가 문항마다 `score_row` → `arun`이 문항 × 지표 표 | 182 ~ 185, 188, 190, 191 | `build_metrics` | 빈칸 2곳 | 빈칸 = 모범 답안이 있을 때 쓰는 `ContextPrecisionWithReference`, 임베딩이 필요한 `AnswerRelevancy(llm, embeddings)`. 나머지 3개는 채워 둠 |
| | | | `score_row` | 빈칸 5곳 | 지표마다 **읽는 칸이 다름**(188쪽 표): Precision(질문, 모범 답안, 검색 결과), Recall(질문, 검색 결과, 모범 답안), Faithfulness(질문, 답변, 검색 결과), AnswerRelevancy(질문, 답변), FactualCorrectness(답변, 모범 답안). 점수는 `MetricResult.value` |

- 합계 9개: 직접 4개(`build_versions`, `find_hits`, `retrieval_metrics`, `summarize_versions`),  
  빈칸 5개(`make_result_row`, `ndcg_at_k`, `diagnose`, `build_metrics`, `score_row`)
- 다섯 단계 모두 실습 함수가 있음: ① 1개, ② 1개, ③ 3개, ⑤ 2개, ④ 2개. ⑤를 ④보다 먼저 실습함(코드 지표만으로 비교표가 나옴, 에듀니)
- 제공 함수(읽고 이해, 클론 대상 아님): `compact_text`(공백 지우기), `rank_weight`(1 ÷ log₂(순위 + 1)),  
  `count_relevant_chunks`(색인에서 관련 청크 수), `mean_of`(None, nan 뺀 평균), `format_delta`(▲, ▼ 표시)
- main 제공(읽기): 시작 검사, `apply_version`, 검색기 실행, `clean_for_ragas`, ragas 평가자 준비,  
  `@experiment` 실험 함수와 `arun`, 결과 파일 쓰기, `--selftest`, 명령행

### 4.1 함수 인자와 반환값(실습 함수 사이의 약속)

| 함수 | 인자 | 반환값 |
|---|---|---|
| `build_versions` | param(이름), values(값 목록), baseline(기준선 값), supported(지원 이름과 현재 값 dict) | 버전 dict 목록. 키 name(v01 …), param, value, is_baseline |
| `make_result_row` | item(평가셋 문항), result(검색기 결과), question_for_ragas, answer_for_ragas | dict. 키 id, answerable, status, user_input, reference, retrieved_contexts, response, chunk_ids, relevance |
| `find_hits` | chunk_texts(검색 결과 본문 목록, 순위 순), relevance(정답 근거 목록) | dict. 키 hit_ranks(적중 순위 목록, 1부터), found_evidence(찾은 정답 근거 번호 집합), evidence_count |
| `retrieval_metrics` | hits(`find_hits` 반환), k | dict. 키 hit, recall, mrr. 정답 근거 0개면 모두 None |
| `ndcg_at_k` | hit_ranks, relevant_chunk_count, k | 0 ~ 1 실수. 관련 청크 0개면 None |
| `summarize_versions` | rows_by_version(버전 이름 → 문항 점수 dict 목록), metric_names, baseline_name, noise | dict. 버전마다 mean(지표별 평균), delta(기준선과의 차이), change(▲, ▼, 변화 없음, -) |
| `diagnose` | change(지표별 변화) | 원인 후보 문장 목록(187쪽 표) |
| `build_metrics` | llm, embeddings | dict. 지표 이름 → 지표 객체 5개 |
| `score_row` | row(결과 정보 행), metrics | dict. 지표 이름 → 점수(0 ~ 1). 실패한 지표는 nan |

### 4.2 하이퍼 파라미터와 검색기 설정 바꾸기(`apply_version`)

| 이름(명령행) | 바꾸는 방법 | 현재 값(기준선 기본) | 값 예 | 193쪽 순위 |
|---|---|---|---|---|
| `top_k` | `run_workflow` 인자. 후보 수(×4, ×2)도 함께 늘어남 | 5 | 3, 5, 10 | 5 |
| `fusion` | `run_workflow` 인자 | weighted | weighted, rrf | 15 |
| `vector_weight` | 검색기 모듈 상수 **두 개를 함께** 바꿈: `VECTOR_WEIGHT` = 값, `BM25_WEIGHT` = 1 - 값(따로 선언된 상수라 하나만 바꾸면 합이 1이 아님, 지식니) | 0.6 | 0.3, 0.6, 0.8 | 9 |
| `rerank_model` | 검색기 모듈 상수 `RERANK_MODEL`(호출 때 읽음) | rerank-v4.0-fast | rerank-v4.0-fast, rerank-v4.0-pro | 6 |
| `llm_model` | 검색기 모듈 상수 `LLM_MODEL`을 바꾸고 **자원을 다시 만듦**(LLM 객체는 `load_resources` 때 만들어짐) | openai/gpt-oss-120b | openai/gpt-oss-120b, openai/gpt-oss-20b | 1 |

- 버전이 끝나면 상수를 원래 값으로 돌려놓음(다음 버전이 기준선에서 출발하게)
- 청크 크기, 오버랩, 임베딩 모델(193쪽 2 ~ 4위)은 재색인이 필요해 이번 범위에서 뺌(10장 후속 과제)
- **팀 추천: `top_k` 3, 5, 10(기준선 5)**. 재색인 없이 바로 바뀌고, 177, 178쪽 예시가 모두 top_k라 설명이 끊기지 않음.  
  k가 커지면 Hit와 Recall은 기계적으로 오르므로 결과 파일 원인 후보에 「ContextPrecision과 짝지어 읽음」을 적음.  
  `vector_weight`는 리랭커가 다시 줄 세워 10문항으로는 차이가 묻힐 위험이 큼(지식니 의견). **최종 선택은 강사(14장 D1)**

### 4.3 문항 처리 규칙

| 경우 | 코드 평가 | LLM 평가 | 따로 보는 것 |
|---|---|---|---|
| 답 있는 문항, 근거 있음(답변 완료, 검증 실패) | 4지표 | 5지표 | - |
| 답 있는 문항, **근거 0개**(근거 부족, 되묻기, 잡담. 검색기가 `evidence`를 비운 채 끝남) | Hit, Recall, MRR, nDCG 모두 0 | 채점하지 않음(빈 검색 결과면 ragas가 예외). 「채점 안 함: 근거 0개」 | 리랭크 상위 청크ID와 적중 여부만 참고로 남김 |
| 답 없는 문항(Q20, Q21) | 계산하지 않음(정답 근거 0개라 분모 0, 181쪽) | 채점하지 않음 | **「확인 필요」 판정**: 종료 상태가 근거 부족 또는 검증 실패이거나 답이 「확인 필요」로 시작하면 맞음, 되묻기와 답변 완료는 틀림 |
| 검색기 예외 | 「오류」로 남기고 다음 문항 | 채점하지 않음 | 오류 문구 |

- 근거 0개 문항의 코드 평가를 0점으로 하는 이유: ⑤에 넘기지 않은 근거는 답변에 쓰이지 않아 LLM 지표와 분모가 어긋나고,  
  검색기 결과 요약에는 청크ID만 있어 정답 단서를 대조할 수 없음(지식니). 13장 D3에서 팀 합의
- 복합 질문은 하위 질의마다 근거를 골라 RRF로 합친 뒤 자름. 결과 파일 문항별 상세에 질의 수를 적음
- 평균은 매크로 평균(질문별 점수의 평균, 181쪽). 결과 파일에 질문별 표를 함께 남겨 0점 질문이 평균에 가려지지 않게 함

### 4.4 시작 검사

| 검사 | 실패하면 |
|---|---|
| 색인 파일(`rag/indexing/data/`)과 `secrets/.env`의 키 2개 | 빠진 것과 할 일을 출력하고 중단 |
| 정답 단서마다 색인 260청크 중 1개 이상에 들어 있는지 | 청크 경계에 걸려 어느 청크에도 없으면 관련 청크 0 → nDCG와 Hit가 영원히 0이 됨. 그 단서와 문항을 출력하고 중단(지식니) |
| 지원하지 않는 하이퍼 파라미터명, 값 형식 | 지원 목록(4.2)을 출력하고 중단 |

### 4.5 외부 API 제한 시간과 실패 처리

| 자리 | 제한 시간, 재시도 | 실패 뒤 |
|---|---|---|
| 검색기(Groq, Cohere) | 검색기 설정 그대로(60초, 30초) | 검색기의 실패 대체 그대로. 그래도 예외면 그 문항을 「오류」로 남기고 다음 문항 |
| 평가자 LLM(Groq Qwen) | 60초, 재시도 3번 | 그 지표를 nan으로 두고 결과 파일에 「채점 실패」. 평균에서 뺌 |
| 동시 채점 | 동시에 2행 | 429(호출 제한)를 피하려고 작게 둠. 상수로 조정 |

## 5. 실행 옵션(핵심 단계까지만 실행)

| 옵션 | 하는 일 | API 호출 |
|---|---|---|
| `--selftest` | 181쪽 가상 예(관련 청크 4, 정답 근거 3, k 5)로 코드 평가 함수만 점검. 기대값 Hit 1, MRR 0.50, Recall 0.67, nDCG 0.41과 비교해 맞음/틀림 | **없음** |
| `--param top_k --values 3 5 10` | 실험할 하이퍼 파라미터와 값 범위(필수) | - |
| `--baseline 5` | 기준선 값(생략하면 4.2 표의 현재 값) | - |
| `--until versions` | ①까지: 버전 목록만 | 없음 |
| `--until run` | ②까지: 검색기 실행과 결과 정보(문항별 근거 순위, 답변 앞부분) | Groq, Cohere |
| `--until code` | ③과 ⑤까지: 코드 4지표, 비교표, 결과 파일(LLM 칸은 「실행 안 함」) | Groq, Cohere |
| `--until all`(기본) | 전부: 코드 4지표 + LLM 5지표, 비교표, 결과 파일 | + 평가자 LLM, 임베딩 |
| `--qid Q01 Q17 Q20` | 일부 문항만(수업 중 빠른 확인) | 줄어듦 |
| `--repeat 3` | 기준선만 N번 채점해 지표별 흔들림 폭을 실측하고 결과 파일에 적음(177쪽) | 기준선 LLM 평가 × N |
| `--mine` | 평가 실습 함수를 교육생 코드(`my_eval.py`)로 | - |

- `--mine`은 직전 실습들과 같은 뜻(「이 프로그램의 실습 함수를 내 코드로」)으로 둠
- **평가 대상 검색기는 언제나 강사 코드 `core_search.py`**(강사 지시 2026-10-31). 검색기는 명령행에 `--mine`이 있으면 교육생 검색기로  
  바뀌므로, main이 검색기를 import하는 동안 명령행에서 `--mine`을 잠시 뺌. 시작 화면에 「검색기: core_search(강사 코드)」를 찍음
- 흔들림 폭(「변화 없음」 기준)은 상수 `NOISE`(초깃값 0.03, 177쪽 그림 예시값). 개발 때 `--repeat 3`으로 실측해 고치고 README에 근거를 적음
- 수업용 문항: Q01(약관, 정답 근거 1개), Q17(상담, 정답 근거 3개. 184, 185쪽 실제 예), Q20(답 없음)

## 6. 결과 파일 형식

`results/{하이퍼 파라미터명}/evaluate_{YYMMDDHHMM}_{vNN}.md` — 실행 1번에 버전 수만큼 파일을 만듦(vNN = 버전 번호, 같은 실행은 같은 시각).  
제목에 버전을 넣음(예: 「top_k 평가 — v02 top_k=5 ★기준선」).

| 절 | 내용 |
|---|---|
| 읽는 순서 | 3줄: ① 요약에서 기준선 대비 ▲, ▼ ② 원인 후보 ③ 0점 문항은 문항별 상세. 범례(▲, ▼, 변화 없음, 채점 안 함, 종료 상태) |
| 머리 | 실행 시각, 하이퍼 파라미터명과 이 버전의 값, 고정한 나머지 설정, 평가셋(문항 수), 평가자 LLM과 임베딩, 흔들림 폭, 실행 옵션 |
| 요약 | 코드 4지표 평균, LLM 5지표 평균, 기준선 대비 변화, 답 없는 문항의 「확인 필요」 맞음 수, 최소 식별 변화 0.125 안내 |
| 버전 비교표 | 같은 실행의 모든 버전 평균을 한 표로(기준선 ★). 모든 버전 파일에 같은 표를 넣어 파일 하나만 열어도 비교됨 |
| 원인 후보 | `diagnose` 결과(187쪽 표). 기준선 파일에는 「기준선」 |
| 문항별 검색 표 | 문항, 종료 상태, 관련 청크 수, 적중 순위, 찾은 정답 근거 수, 하(Hit), 빠(Recall), 빨(MRR), 앞(nDCG), 위(Precision), 정(Recall) |
| 문항별 답변 표 | 문항, 종료 상태, 출(Faithfulness), 관(AnswerRelevancy), 답(FactualCorrectness), 「확인 필요」 판정(답 없는 문항) |
| 문항별 상세 | 원 질문과 ragas에 넘긴 질문, 모범 답안, 원 답변과 ragas에 넘긴 답변, 검색 결과(순위, 청크ID, 적중 여부, 본문 앞부분), 질의 수 |

## 7. 실습 순서와 교시 배치(안)

| 교시 | 내용(분) | 함수(순서대로, 예상 줄 수) | 직접 : 빈칸 | 교시 끝에 확인할 것 |
|---|---|---|---|---|
| 1 | 교재 176 ~ 193쪽 이론(30), 강사 화면으로 결과 파일 읽기(10), 교체 방법과 `--selftest` 시연(10) | - | - | 기준선과 버전의 차이, 지표 조합으로 원인 찾기 |
| 2 | 환경 점검(5) → ①, ②(15) → ③(30) | `build_versions`(21) → `make_result_row`(빈칸 2) → `find_hits`(21) → `retrieval_metrics`(17) → `ndcg_at_k`(빈칸 2) | 3 : 2 | `--selftest` 맞음 12/12, `--until code --qid Q01 Q17 Q20`이 강사와 같음 |
| 3 | ⑤(20) → `@experiment` 읽기 구간 해설(5) → ④(25) | `summarize_versions`(31) → `diagnose`(빈칸 3) → `build_metrics`(빈칸 2) → `score_row`(빈칸 5) | 1 : 4 | `--qid Q01 Q17 Q20`의 비교표와 5지표 |

- 넘치면 `diagnose`를 숙제로 돌림(교시 3의 다른 함수와 독립)
- 함수 하나를 채울 때마다 그 단계까지만(`--until`) 돌려 확인함. LLM 평가 전체 실행(10문항 × 3버전, 약 10분)은 조별 1대만 함

### 7.1 교육생 확인표

명령은 `hands-on/solutions/ragas` 폴더에서 가상환경을 켠 뒤 실행함. 기대값의 「(실측)」은 개발 뒤 강사 화면 값으로 채움.

| 실습 함수 | 확인 명령 | 화면에서 볼 것 | 정상 기준 |
|---|---|---|---|
| `find_hits`, `retrieval_metrics`, `ndcg_at_k` | `python evaluate_rag.py --mine --selftest` | 4지표 기대값과 내 값 | 맞음 12/12(4지표 Hit 1, MRR 0.50, Recall 0.67, nDCG 0.41 포함). 4위 청크의 정답 근거 ①을 두 번 세면 Recall 1.00으로 틀림 |
| `build_versions` | `python evaluate_rag.py --mine --param top_k --values 3 5 10 --until versions` | 버전 목록 | v01 top_k=3, v02 top_k=5 ★기준선, v03 top_k=10. `--param chunk_size`면 지원 목록 오류 |
| `make_result_row` | `python evaluate_rag.py --mine --param top_k --values 5 --until run --qid Q17` | 결과 정보 4칸 | user_input = 회원번호를 지운 질문(「회원과 상담할 때 …」), reference = 모범 답안, 검색 결과 = 본문 4 ~ 5개, response = 인용 표시 없는 답변 |
| `find_hits` 등(실데이터) | `python evaluate_rag.py --mine --param top_k --values 5 --until code --qid Q01 Q17 Q20` | 순위별 적중, 4지표 | Q01 (실측), Q17 정답 근거 3개 모두 찾음, Q20 「계산 안 함」과 「확인 필요」 맞음 |
| `summarize_versions`, `diagnose` | `python evaluate_rag.py --mine --param top_k --values 3 5 10 --until code --qid Q01 Q17 Q20` | 비교표, 원인 후보 | 기준선 행 변화 「-」, 다른 행 ▲, ▼ 또는 변화 없음. 원인 후보 문장 |
| `build_metrics`, `score_row` | `python evaluate_rag.py --mine --param top_k --values 5 --qid Q17` | 5지표 | 오류 없이 5개 점수. 칸을 바꿔 넣으면 `TypeError`(인자 이름 오류)가 남. 184쪽(원 질문, Claude 평가자)과 값을 직접 비교하지 않음 |

## 8. 교체 방법

1. `python evaluate_rag.py --mine ...`처럼 `--mine`을 붙여 실행함. `my_eval.py`가 없으면 `my_eval.template.py`를 복사해 만듦
2. 채울 함수 이름을 `my_eval.py` 맨 아래 `USE_TEACHER_CODE` 목록에서 지움(남은 함수는 강사 코드가 대신 돎)
3. 함수를 채우고 7.1 표의 명령으로 실행해 강사 결과와 비교함. 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감

## 9. 모델과 패키지

| 항목 | 값 |
|---|---|
| ragas | **0.4.3**(PyPI 최신, 2026-01-13 배포. 2026-10-31 확인) |
| 평가자 LLM | **Groq `qwen/qwen3.8-27b`**(강사 지정). `llm_factory("qwen/qwen3.8-27b", client=AsyncOpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1"))`. 답변 LLM(`openai/gpt-oss-120b`)과 다른 모델이라 자기 채점이 아님 |
| 임베딩(AnswerRelevancy) | Cohere `embed-v5.0-fast`. Cohere의 OpenAI 호환 주소로 ragas `OpenAIEmbeddings` 사용 |
| 평가 대상 검색기 | RAG 검색기 그대로(Groq `openai/gpt-oss-120b`, Cohere `embed-v5.0-fast`, `rerank-v4.0-fast`) |
| 가상환경 | `hands-on/solutions/ragas/.venv`(Python 3.13). RAG 공용 판(langchain-community만 0.3.31) + `ragas==0.4.3` + `pandas` |
| LangChain | 검색기는 LangChain 그대로. 평가자는 ragas 0.4 방식(`llm_factory`, `OpenAIEmbeddings`). 0.4에서 LangChain 래퍼가 deprecated라 native 사용(교재 201쪽) |

- 의존성(이전 예제 실측): ragas 0.4.3은 import 때 `langchain_community.chat_models.vertexai`를 부르는데 langchain-community 0.4에는  
  이 모듈이 없음 → `langchain-community==0.3.31`. 0.3.31은 `langchain<2`, `langchain-core<2`를 허용해 검색기의 langchain 1.x와 함께 설치됨(9.1)
- context7 MCP는 월 한도 초과라 REST API(`secrets/.env`의 `CONTEXT7_API_KEY`)로 확인함:  
  `@experiment` + `arun(dataset, name=...)`, `llm_factory(model, client=...)`, collections 지표의 `ascore()`와 `MetricResult`

### 9.1 한 가상환경 설치와 채점 실측(2026-10-31, 스크래치 가상환경)

| 확인 | 결과 |
|---|---|
| 설치 | RAG 공용 판 13개(단 `langchain-community==0.3.31`) + `ragas==0.4.3` + `pandas` → `pip check` 문제 없음.  
pip이 고른 판: `openai 1.109.1`, `instructor 1.3.2`, `langchain-openai 1.1.9`, `pandas 3.1.0`(requirements.txt에 고정) |
| import | `import ragas`, `ragas.metrics.collections` 5개, `search_docs`(RAG 검색기) 모두 성공. 검색기 Q17 「답변 완료」(근거 4개) |
| 평가자와 임베딩 | Groq `qwen/qwen3.8-27b`(Groq 모델 목록에서 ID 확인), Cohere OpenAI 호환 임베딩 모두 동작 |
| Q17 5지표 | `@experiment` + `arun` 한 행 28.8초. Precision 1.00, Recall 1.00, Faithfulness 0.00, AnswerRelevancy 0.62, FactualCorrectness 0.40 |
| Faithfulness 0.00 원인 | 평가자 출력을 가로채 봄: 답변 주장 2개 = 「M-3001 회원 상담 때 …」(회원번호는 근거에 없음 → 0), 「D3-0019 코드로 식별됨」(인용 표시 → 0).  
인용 표시만 빼면 0.00, **인용 표시와 회원번호를 모두 빼면 1.00**(184쪽과 같음) → 2장의 정리 규칙 |
| 판정 이유(reason) | collections 지표 5개 모두 `reason`이 빈 값 |
| 시도했다 버린 것 | Claude Haiku 5.5 평가자: ragas가 `temperature`, `top_p`를 넘겨 실패(2026-10-21부터 Claude API가 거절), 빼도 생각 블록을 instructor 1.3.2가 읽지 못함. 강사 지시로 Groq Qwen으로 바꿈 |

## 10. 사전 과제와 환경 점검(교육생), 후속 과제

| 번호 | 과제 | 확인 방법 |
|---|---|---|
| 1 | W3 인덱싱, W4 검색 실습 완료(또는 강사 배포 `rag/indexing/data/`) | `rag/indexing/data/bm25/manifest.json` 있음, `chunk_count` 260 |
| 2 | 이 실습 가상환경 `ragas/.venv`(README 3장) | 설치 확인 명령이 `ok` |
| 3 | `secrets/.env`에 키 2개(`GROQ_API_KEY`: 검색기와 평가자, `COHERE_API_KEY`: 검색기와 임베딩) | `python evaluate_rag.py --param top_k --values 5 --until run --qid Q01`이 끝남 |

- `evaluate_rag.py`의 시작 검사(4.4)가 1과 3을 확인하고 빠진 것과 할 일을 출력함
- 후속 과제(이번 범위 밖): 재색인이 필요한 하이퍼 파라미터(청크 크기, 오버랩, 임베딩 모델), 186쪽 사람 평가와 kappa

## 11. 용어 풀이(README와 실습 가이드에 넣음)

버전, 기준선, 하이퍼 파라미터, 정답 근거, 정답 단서, 모범 답안, 적중 청크, 관련 청크, 결과 정보, 매크로 평균, 순위 가중치,  
DCG와 IDCG, 평가자 LLM, 코사인 유사도(AnswerRelevancy), 흔들림 폭, 비동기(`async`, `await`), 데코레이터(`@experiment`),  
`None`과 `nan`(값 없음과 계산 실패), 429(호출 제한).  
「관련」의 두 뜻을 따로 풂: 코드 평가의 **관련 청크**(정답 단서를 담은 청크, 글자 대조)와 LLM 평가 ContextPrecision의 **관련 1 / 무관 0**  
(평가자가 뜻으로 판정). 184쪽 Q17 3위 청크(코드는 적중 아님, LLM은 관련)를 예로 씀.

## 12. 검증 계획(정직한 보고 기준)

| 검증 | 완료 기준 |
|---|---|
| 코드 평가 계산 | `--selftest`가 181쪽 가상 예에서 Hit 1, MRR 0.50, Recall 0.67, nDCG 0.41 |
| 교재 실제 예 | Q17 기준선 실행. 검색 결과가 185쪽과 같으면 코드 4지표가 같음(Hit 1, MRR 1.00, Recall 1.00, nDCG 0.97). LLM 지표는 방향이 같은지 |
| 강사 지정 하이퍼 파라미터 | 10문항 × 버전 수로 실행해 결과 파일 생성. 9지표가 채워짐(채점 안 함, 채점 실패는 사유와 함께 표시) |
| 흔들림 폭 | `--repeat 3`으로 기준선 지표별 폭을 실측해 `NOISE`와 README에 반영 |
| 문항 처리 규칙 | 근거 0개 문항, 답 없는 문항의 「확인 필요」 판정이 4.3 표대로인지 실제 문항으로 확인 |
| 단계 옵션 | `--selftest`, `--until versions`, `run`, `code`가 그 단계에서 멈추고 API를 더 부르지 않음 |
| 뼈대 교체 | 정답으로 채운 사본이 같은 지표. 빈 뼈대는 목록 덕분에 완주, 목록에서 지운 함수만 `NotImplementedError` |
| 설치 | 새 가상환경에 README 절차대로 설치 → `pip check` 문제 없음, 설치 확인 명령 `ok` |
| 코드 형식 | `references/dev-comment-guide.md` 10장 체크리스트, 핵심 파일은 줄 단위 주석, 줄 길이 120자, pyflakes 통과, 한 줄 축약(컴프리헨션, 삼항 연산) 대신 `for`와 `if`로 풀어 씀 |

## 13. 작업 순서

1. 개발계획서 초안 → 팀원 리뷰(완료) → 최종안(이 문서) → 강사 승인과 하이퍼 파라미터 받기(14장)
2. `core_eval.py` → `evaluate_rag.py` → `--selftest`와 단계별 실행 → 강사 지정 하이퍼 파라미터로 전체 실행, `--repeat 3` → 결과 파일
3. `my_eval.template.py` → 교체 경로 확인 → `requirements.txt`, README
4. 교육생 실습 가이드(마크다운) → 핵심 슬라이드(상세는 원격 Git 링크) → 렌더링 검증

## 14. 결정 사항과 승인 요청

| 번호 | 항목 | 제안 | 대안 |
|---|---|---|---|
| D1 | 실험할 하이퍼 파라미터와 값 범위 | **결정됨: `top_k` 3, 5, 10(기준선 5)**(강사 승인 2026-10-31) | - |
| D2 | 평가자 LLM | **결정됨: Groq `qwen/qwen3.8-27b`**(강사 지시 2026-10-31) | - |
| D3 | 근거 0개 문항의 코드 평가 | **승인:** 0점(팀 합의, 4.3) | 리랭크 상위로 계산(청크ID만 있어 단서 대조 불가) |
| D4 | 결과 파일 수 | **승인:** 버전마다 1개(vNN = 버전 번호), 파일마다 같은 비교표 | 실행마다 1개(vNN = 같은 날 실행 순번), 버전을 한 파일에 |
| D5 | API 비용 | Groq와 Cohere만 씀. 10문항 × 3버전 × 2 ~ 3회 + `--repeat 3`. 비용은 실측해 README에 적음 | - |

## 15. 검토 이력

| 단계 | 내용 |
|---|---|
| 초안 v0.1 | 클로니 작성(2026-10-31). 교재 176 ~ 196쪽, RAG 검색기, 이전 RAGAS 예제(`teacher/rag/ragas/`)를 대조 |
| 설치와 채점 실측 | 한 가상환경 설치, Q17 5지표 채점, Faithfulness 0.00 원인 분석(9.1). 강사 지시로 평가자를 Groq `qwen/qwen3.8-27b`로 |
| 지식니 검토 | 수정 후 사용. 반영 11건: `vector_weight`는 상수 두 개를 함께 바꿈, 설정 바꾸는 방법 셋(인자, 상수, 자원 재생성) 표, 되묻기와 잡담도 근거 0개로 묶어 LLM 평가 제외, 최소 식별 변화 0.125 명시, D3 0점 지지와 이유, 복합 질문 질의 수 표시, 정답 단서 색인 포함 시작 검사, 관련 청크 수 열, 질문 정리 규칙을 2장에(184쪽과 직접 비교 금지), 「확인 필요」 판정 규칙, 흔들림 폭 실측(`--repeat`). 추천 하이퍼 파라미터 `top_k` 3, 5, 10 |
| 에듀니 검토 | 조건부 통과. 반영 12건: `--selftest`(API 없이 181쪽 예), 판정 이유 항목 정리(`--show-reason` 삭제), 질문 정리 규칙 2장 행 추가, 교시별 분과 `ndcg_at_k` 빈칸 분리, 함수 인자와 반환 표(4.1), 확인 명령 전체 표기, `diagnose` 빈칸 실습으로 올리고 `build_metrics` 빈칸 2곳으로 줄임, `--baseline` 생략 가능과 `--until all`, ⑤ 비교표를 ④보다 먼저, 결과 파일 표 나눔과 교재 약칭과 범례, 용어 풀이 장, 교재 불일치 항목 추가. 반영하지 않은 것: `--mine-eval` 이름(직전 실습들과 같은 뜻의 `--mine` 유지) |
| 강사 승인 | 2026-10-31 「첫번째(`top_k` 3, 5, 10)로 하고 README.md에 각 하이퍼 파라미터별로 실행 옵션 주는 명령을 추가」, 「`--mine-retriever` 제거, 무조건 core_search.py를 이용」 |

## 16. 개발 결과(2026-10-31)

| 산출물 | 경로 | 상태 |
|---|---|---|
| 예제 프로그램 | `hands-on/solutions/ragas/`(evaluate_rag.py, core_eval.py, my_eval.template.py, requirements.txt, README.md) | 완료 |
| 결과 파일 | `hands-on/solutions/ragas/results/top_k/evaluate_2610311725_v01 ~ v03.md`(1회차), 2회차는 16.3 | 완료 |
| 교육생 실습 가이드 | `teacher/plan/ragas-실습가이드.md`(에듀니 작성, 클로니 검수) | 완료 |
| 핵심 슬라이드 | `teacher/plan/ragas-실습가이드.pptx`(6장, 스크립트 `…-slides.md`, 빌드 `build/build-ragas-guide-slides.js`, 미리보기 `…-preview/`) | 완료. LibreOffice 렌더링 6장 확인(넘침 없음) |

### 16.1 검증 결과(12장 기준)

| 검증 | 결과 |
|---|---|
| 코드 평가 계산 | `--selftest` 12/12 맞음(181쪽 예 Hit 1, MRR 0.50, Recall 0.67, nDCG 0.41 + 버전, 비교, 원인 6개) |
| 교재 실제 예 | Q17 기준선(top_k 5) 코드 4지표 Hit 1, Recall 1.00, MRR 1.00, nDCG 0.97 = 185쪽. LLM 지표는 Precision, Recall 1.00으로 방향 같음, Faithfulness는 답변 문장 꼴에 따라 0 또는 1(README 7.3) |
| 강사 지정 하이퍼 파라미터 | `top_k` 3, 5, 10 × 10문항, 기준선 3회 반복. 913초. 9지표 모두 채워짐(채점 실패 0건). README 7장 |
| 흔들림 폭 | 기준선 3회 채점에서 LLM 5지표 평균 차이 0.000(평가자 temperature 0.01). 흔들림은 검색기 쪽(Q17이 기준선 실행에서만 되묻기) |
| 문항 처리 규칙 | 근거 0개(Q17 되묻기, Q20, Q21 근거 부족)는 LLM 채점 안 함. 답 없는 문항 「확인 필요」 2/2 맞음 |
| 단계 옵션 | `--selftest`, `--until versions`(API 없음), `--until run`, `--until code`가 그 단계에서 멈춤 |
| 뼈대 교체 | `--mine --selftest`: 뼈대 복사 뒤 강사 코드 대체로 12/12. 목록에서 `find_hits`를 지우면 `NotImplementedError`. `my_eval.py`는 Git 무시 확인 |
| 설치 | 새 가상환경에 `pip install -r requirements.txt` → `pip check` 문제 없음 |
| 코드 형식 | pyflakes 통과(뼈대의 빈칸 변수와 제공 import는 의도된 경고), 줄 120자 이내, 핵심 파일 줄 단위 주석 |

### 16.2 개발 중 바꾼 것

- 평가자를 Claude Haiku 5.5에서 **Groq `qwen/qwen3.8-27b`**로(강사 지시. ragas가 넘기는 temperature를 Claude API가 거절)
- `--mine-retriever` 제거, 검색기는 언제나 `core_search.py`(강사 지시). main이 검색기를 import하는 동안 `--mine`을 잠시 뺌
- 실습 함수 7개 → 9개(에듀니 리뷰: `ndcg_at_k`, `diagnose`를 빈칸 실습으로 분리)
- `diagnose` 인자를 `(change)`로 단순화(평균은 쓰지 않음)
- LLM 평가는 버전 전체를 이벤트 루프 하나(`asyncio.run` 1번)에서 돌림. 버전마다 루프를 새로 만들면 같은 API 클라이언트가 닫힌 루프를 쓰다 오류가 남
- 평가자 판정의 한계 3건(Q02 FactualCorrectness 0, Q14 ContextPrecision 0, Q17 Faithfulness 흔들림)을 원시 출력으로 확인해 README 7.4에 적음

### 16.3 2회차 실행

같은 명령을 한 번 더 돌림(733초, `results/top_k/evaluate_2610311741_v01 ~ v03.md`). 1회차와 다른 점과 해석은 README 7.5에 적음.  
요지: 1회차의 코드 지표 ▲ +0.125는 기준선 Q17이 되묻기로 끝난 검색기 흔들림이었고, 2회차에서 보이는 top_k 효과는 Q17 Recall(top_k 3에서 2/3)과  
Q07 nDCG(k가 커질수록 내려감)뿐임. LLM 지표의 방향은 두 회차에서 달라 10문항으로는 생성 지표에 미치는 top_k 효과를 가릴 수 없음.  
흔들림 폭 실측은 1회차 모두 0.000, 2회차 Faithfulness 0.125(한 문항이 3회 중 1회 다름).

### 16.4 교재 반영(2026-10-31 강사 지시)

- 강사 지시: 「150페이지처럼 워크플로우 그리고 단계 일련번호와 각 단계별 수행 설명」, 「189, 190, 191페이지 삭제」,  
  「현재 교재 기준으로 198페이지부터 코드 설명 추가. 코드에 일련번호 붙이고 우측에서 설명」
- 반영: 백업 `backup/신한카드 하이브리드AI_W01~W04.backup-20261031-ragas-code.pptx` 뒤 `merge-ragas-code.py`로  
  「코드로 보기」 3장(옛 189 ~ 191쪽)을 지우고, 간지 「품질 평가 및 튜닝 실습」(194쪽) 뒤에 13장을 넣음(교재 총 208장)

| 새 쪽 | 장표 | 내용 |
|---|---|---|
| 195 | 평가 워크플로우: 버전 비교 평가 구성안 | 150쪽 모양. 입력 → ① ~ ⑤ → 결과 파일, 분기 카드 3개, 단계 표(하는 일, 판단 방식, 핵심 코드) |
| 196 | ① 버전 만들기 | `build_versions` |
| 197 | ② 검색기 실행 – 결과 정보 | `make_result_row`, `clean_for_ragas` |
| 198 | ③ 적중 청크 판정 | `find_hits` |
| 199 | ③ 하, 빠, 빨 | `retrieval_metrics` |
| 200 | ③ 앞(nDCG) | `ndcg_at_k` |
| 201 | ④ 평가자와 지표 | `build_judge`, `build_metrics` |
| 202 | ④ 한 행 채점(위, 정) | `score_row` 앞부분 |
| 203 | ④ 한 행 채점(출, 관, 답) | `score_row` 뒷부분 |
| 204 | ④ 실험 실행 | `run_llm_evaluation`(`@experiment`, `arun`) |
| 205 | ⑤ 버전별 평균 | `summarize_versions` 앞부분 |
| 206 | ⑤ 기준선 대비 변화 | `summarize_versions` 뒷부분 |
| 207 | ⑤ 원인 찾기 | `diagnose` |

- 쪽 번호 이동: 옛 192 ~ 197쪽 → 189 ~ 194쪽, Q&A 198 → 208. 소스 주석, README, 실습 가이드, 가이드 슬라이드, 계획서의 쪽 번호를 맞춤  
  (옛 190쪽 「점 격자」는 188쪽 표로, 옛 191쪽 실험 코드는 178쪽과 새 204쪽으로)
- 도구: 스크립트 `teacher/plan/ragas-code-slides.md`, 발췌 `build/extract-ragas-code.py`(구성안 장은 kind=overview),  
  빌드 `build/build-ragas-code.js`(코드 장표 + 150쪽 모양 구성안), 넣기 `build/merge-ragas-code.py`(다시 돌리면 같은 제목을 바꿈).  
  `code_excerpt.py`가 `async def`도 찾게 고침. `score_row`의 호출 5곳은 닫는 괄호를 마지막 인자 줄로 올려 발췌가 깔끔하게 줄어들게 함(동작 같음)
- 확인: 장표 덱 13장 LibreOffice 렌더링(넘침 없음), 붙여넣기 점검 OK, 교재 zip 이름 중복 0, 186 ~ 208쪽 제목 순서 확인
