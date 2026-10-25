# RAG 검색 실습 가이드(교육생용)

| 항목 | 내용 |
|---|---|
| 대상 | 하이브리드 AI 교육 「문서 검색」. 엔지니어, 데이터 모델러, 기획자 혼합(파이썬 초보 포함) |
| 교재 | 『신한카드 하이브리드AI_W01 ~ W04』 144 ~ 174쪽(검색 워크플로우는 150 ~ 174쪽) |
| 예제 | [hands-on/solutions/rag/retriever](https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/rag/retriever/README.md) |
| 시간 | 이론 1교시 + 클론 코딩 3교시(교시 2, 3, 4) = 4교시 |
| 완료 | 본인 코드(`my_search.py`)로 Q01은 「답변 완료」, Q18(답이 없는 질문)은 되묻기 또는 「확인 필요」로 끝남 |

## 0. 이 실습에서 만드는 것

인덱싱 실습이 만든 색인(Chroma 벡터, bm25s 점수표)을 읽어 **질문에 근거를 붙여 답하는 검색기**를 만듦.  
교재 150쪽 고정 워크플로우 6단계가 그대로 코드가 됨: **LLM은 제안만 하고, 받아들일지는 코드 규칙이 정함**.

```text
① 권한 필터(코드)  → 볼 수 있는 청크만 남김
② Adaptive 분류    → LLM이 질문 유형을 제안, 코드 규칙이 확정(잡담, 단순, 복합)
③ 검색             → 벡터 + BM25 → 융합(6 : 4) → 리랭크 → 근거 5개
④ CRAG 채점        → 신호로 정확, 불확실, 부정확 판정. 불확실이면 질문 변환 → 재검색(최대 1회)
⑤ 답변 생성(Groq)  → 근거만으로, 문장마다 청크ID와 인용문
⑥ Self-RAG 검증    → 인용문이 근거 본문에 글자 그대로 있는지 대조. 실패면 ⑤ 재작성(최대 2회)
```

분기는 모두 미리 그린 `if`이고, 반복은 고정 상한임. 그래서 같은 입력이면 흐름을 예측할 수 있음.  
레이어드 구조 없이 main 1개(`search_docs.py`)와 핵심 모듈 1개(`core_search.py`)로 짰고, 교육생은 핵심 모듈의 함수 10개를  
`my_search.py`에 따라 쓴 뒤 import 한 줄로 바꿔 끼움.

## 1. 사전 준비(수업 전까지)

| 번호 | 할 일 | 확인 |
|---|---|---|
| 1 | 인덱싱 실습 완료. 없으면 강사 배포 `data/`를 복사 | `indexing/data/`에 `chroma/`와 `bm25/` 폴더가 있음 |
| 2 | 저장소를 통째로 clone(`secrets/`, `eval-set.json`, `indexing/`를 상대 경로로 찾음) | `hands-on/solutions/eval-set.json`이 있음 |
| 3 | 공용 가상환경 `rag/.venv` 준비(없으면 `retriever/README.md` 3장대로 만들고 활성화한 뒤 패키지 설치) | 설치 확인 명령이 `ok` |
| 4 | `secrets/.env`에 키 2줄: `GROQ_API_KEY`, `COHERE_API_KEY`(강사 배포) | 아래 명령이 「답변 완료」까지 끝남 |

가상환경 활성화(`hands-on/solutions/rag` 폴더에서, 터미널 창마다 한 번). 프롬프트 앞에 `(.venv)`가 붙으면 됨

| 터미널 | 활성화 명령 |
|---|---|
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows Git Bash | `source .venv/Scripts/activate` |
| macOS, Linux | `source .venv/bin/activate` |

PowerShell에서 「이 시스템에서 스크립트를 실행할 수 없으므로 ...」로 막히면 아래 한 줄을 먼저 실행하고 다시 활성화함  
(지금 창에서만 허용. 계속 허용하려면 `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`)

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

설치 확인과 수업용 명령(활성화한 터미널에서)

```bash
python -c "import langchain, langchain_groq, chromadb, kiwipiepy, cohere, bm25s; print('ok')"
cd retriever
python search_docs.py --qid Q01
```

로컬 모델은 없음(임베딩, 리랭크, LLM 모두 API 호출). 인덱싱이 도는 동안에는 검색을 실행하지 않음(같은 Chroma 폴더를 함께 열면 결과가 흔들림).  
Cohere 체험 키는 리랭크가 분당 10회이고 복합 질문 한 번에 리랭크가 최대 6번 일어남. 수업 중에는 조별 1대로 실행함.

## 2. 수업 흐름

| 교시 | 내용 | 실습 함수(채우는 순서) |
|---|---|---|
| 1 이론 | 교재 144 ~ 174쪽. 강사 화면으로 ① ~ ⑥ 출력 읽기, 교체 방법 시연 | - |
| 2 | ① 권한 필터, ② 분류, ③ 벡터 검색 | `build_chroma_filter`, `apply_plan_rules`, `search_vector` |
| 3 | ③ BM25, 융합, 리랭크 | `search_bm25`, `fuse_weighted`, `rerank` |
| 4 | ④ 채점과 질문 변환, ⑤ 답변, ⑥ 검증 | `grade`, `apply_transform_rules`, `generate_answer`, `verify_answer` |

방식 두 가지(모두 10개: 직접 4, 빈칸 6)

- **직접 작성**(4개): 함수 몸통이 `raise NotImplementedError("여기에 본인 코드를 작성함")` 한 줄임. docstring의 「할 일」을 보고 씀
- **빈칸 채우기**(6개): 거의 완성된 코드 중간에 `raise NotImplementedError("빈칸 N을 채울 것")`이 있음.  
  바로 위 주석이 무엇을 채울지 알려 줌. 채운 뒤 그 `raise` 줄은 지움

## 3. 따라하기

### Step 1. 강사 코드로 실행하고 출력 읽기(교시 1)

```bash
python search_docs.py --qid Q01
```

```bash
python search_docs.py --qid Q18
```

Q01은 약관 질문을 ① ~ ⑥ 끝까지 돌려 「답변 완료」를 봄(약 4초, LLM 2번, 임베딩 1번, 리랭크 1번).  
Q18은 근거에 답이 없는 질문(연회비를 포인트로 내기)이 지어내지 않고 되묻기 또는 「확인 필요」로 끝나는 것을 봄.

| 줄 | 볼 것 | Q01(강사 PC) |
|---|---|---|
| `[① 권한 필터]` | 역할, Chroma 필터, BM25 대상 청크 수 | agent(public만), 212개(전체 260개 중) |
| `[② Adaptive 분류]` | LLM 제안 → 코드 확정 | 유형 simple, 검색할 질의 1개 |
| `[③ 검색]` | 벡터, BM25, 융합, 리랭크 순위와 점수 | 정답 청크 D1-0007이 1위(리랭크 0.908) |
| `[④ CRAG 채점]` | 신호와 기준값, 판정 | 판정 정확 |
| `[⑤ 답변 생성]` | 문장, 청크ID, 인용문 | 문장 1개, 인용 [D1-0007] |
| `[⑥ Self-RAG 근거 검증]`, `[종료]` | 검증 결과, 종료 상태 | 검증 통과, 답변 완료 |

같은 질문도 LLM이 낸 값(분류, 질문 변환 기법, 답 문장)은 실행마다 조금씩 다를 수 있음.  
강사와 같은 문장이 아니어도, 교시 표의 정상 기준(대상 청크 수, 판정, 종료 상태)으로 자기 함수를 확인함.

### Step 2. 본인 코드로 바꿀 준비

1. `search_docs.py` 위쪽 import 한 줄을 바꿈

   ```python
   import core_search as core   # 강사 코드로 실행
   import my_search as core     # 본인 코드로 실행 (이 줄만 바꿈)
   ```

2. `my_search.py` 맨 아래 `USE_TEACHER_CODE` 목록을 봄. 여기 있는 함수는 **강사 코드가 대신 돎**
3. 지금 채울 함수 이름을 목록에서 지움 → 그 함수를 채움 → 아래 표의 확인 명령으로 다시 실행 → 결과를 비교함
4. 막히면 함수 이름을 목록에 다시 넣고 다음 함수로 넘어감. 본인 함수에서 예외가 나면 감추지 않고 그대로 보임
5. W3 인덱싱을 `my_indexing.py`로 했다면 `search_docs.py`의 `import core_indexing as indexing`도 `my_indexing`으로 바꿈

### Step 3. 교시 2 함수 3개(모두 빈칸)

| 순서 | 함수 | 단계 | 방식 | 무엇을 쓰는지(빈칸 주석) | 예상 줄 수 |
|---|---|---|---|---|---|
| 1 | `build_chroma_filter` | ① 권한 필터 | 빈칸 2곳 | 빈칸 1: `access_level`이 `"public"`과 같은(`$eq`) 청크만 남기는 필터 dict. 빈칸 2: `"$and"` 목록에 조건 두 개(`restricted`, 그 회원의 `member_pseudo_id`)를 넣은 dict | 15 |
| 2 | `apply_plan_rules` | ② Adaptive 분류 | 빈칸 3곳 | 빈칸 1: 업무 낱말이 하나라도 있으면 `fallback_simple(...)`을 return. 빈칸 2: `texts`를 앞 `max_sub_questions`개로 자름. 빈칸 3: `lost`와 `invented`를 집합 빼기(`-`)로 구함 | 35 |
| 3 | `search_vector` | ③ 검색: 벡터 | 빈칸 2곳 | 빈칸 1: `store.similarity_search_with_score(...)`에 질의, `k=top_n`, `filter=chroma_filter`. 빈칸 2: 거리를 「클수록 좋은」 점수로 바꿔 `score`에 받음(`float`) | 20 |

| 함수 | 확인 명령 | 정상 기준(이 데이터) |
|---|---|---|
| `build_chroma_filter` | `--qid Q14`, 같은 질문을 `--role agent`로 | BM25 대상 청크: agent 212개, auditor + M-1042는 4개(그 회원 상담만) |
| `apply_plan_rules` | `"안녕하세요"`, `--qid Q01` | 「안녕하세요」는 잡담으로 검색 0회, Q01은 유형 simple |
| `search_vector` | `--qid Q01 --no-answer` | 정답 청크 0.45 ~ 0.6, 관련 없는 청크 0.2 ~ 0.4. 절댓값보다 순위를 봄 |

```bash
python search_docs.py --qid Q14
python search_docs.py --qid Q14 --role agent
python search_docs.py "안녕하세요"
python search_docs.py --qid Q01 --no-answer
```

### Step 4. 교시 3 함수 3개(직접 2 + 빈칸 1)

| 순서 | 함수 | 단계 | 방식 | 무엇을 쓰는지(할 일과 빈칸 주석) | 예상 줄 수 |
|---|---|---|---|---|---|
| 4 | `search_bm25` | ③ 검색: BM25 | 직접 | `bm25.get_scores(query_tokens, weight_mask=weight_mask)`로 청크마다 점수. (점수, 순번) 쌍을 모으되 점수 0은 버림. 내림차순 정렬. 앞 `top_n`개를 `chunk_id`, `text`, `metadata`, `score`, `rank` dict로 만듦 | 20 |
| 5 | `fuse_weighted` | ③ 검색: 융합 | 직접 | `_normalize_scores`로 두 결과를 0 ~ 1로 맞춤. `_merge_lists`로 `chunk_id` 묶음 표. 청크마다 0.6 × 벡터 + 0.4 × BM25(없는 쪽은 0점). `_build_fused_list`를 return | 20 |
| 6 | `rerank` | ③ 검색: 리랭크 | 빈칸 2곳 | 빈칸 1: `cohere_client.rerank(...)`에 `model`, `query`, `documents`, `top_n`. 빈칸 2: `result.index`로 후보를 찾아 `dict(...)`로 복사 | 25 |

| 함수 | 확인 명령 | 정상 기준(이 데이터) |
|---|---|---|
| `search_bm25` | `--qid Q07 --no-answer` | 카드명이 한 토큰(`한빛모아생활`). 점수는 상한이 없음(0 ~ 수십) |
| `fuse_weighted` | 같은 명령 | 두 검색에 모두 나온 청크가 위로(`[vector, bm25]`). 양쪽 1위면 1.0 |
| `rerank` | 같은 명령 | 정답 청크 0.7 이상, 관련 없는 청크 0.3 이하로 벌어짐 |

```bash
python search_docs.py --qid Q07 --no-answer
```

### Step 5. 교시 4 함수 4개(직접 2 + 빈칸 2)

| 순서 | 함수 | 단계 | 방식 | 무엇을 쓰는지(할 일과 빈칸 주석) | 예상 줄 수 |
|---|---|---|---|---|---|
| 7 | `grade` | ④ CRAG 채점 | 직접 | 부정확(하나라도): 결과 0건, 1위 점수 < 하한. 정확(모두): 리랭크 성공, 1위 ≥ 상한, 핵심어 포함, 대상 일치, 격차, 겹침. 나머지는 불확실 | 20 |
| 8 | `apply_transform_rules` | ④ 질문 변환 | 빈칸 3곳 | 빈칸 1: `technique`을 `CLARIFY`로, `clarify_question`을 `forced_clarify`로 바꾸고 return. 빈칸 2: 이미 본 질의면 경고를 더하고 `continue`. 빈칸 3: `ORIGINAL_REQUIRED`에 있으면 `include_original`에 True | 35 |
| 9 | `generate_answer` | ⑤ 답변 생성 | 빈칸 2곳 | 빈칸 1: `llm.with_structured_output(GroundedAnswer, method="json_schema", strict=True)`. 빈칸 2: `prompt`와 `structured_llm`을 `\|`로 이어 `chain` | 20 |
| 10 | `verify_answer` | ⑥ 근거 검증 | 직접 | 문장마다(번호는 1부터) 검사 1: 청크ID가 비었는가. 검사 2: 청크ID가 근거 묶음에 있는가. 검사 3: 인용문이 본문 안에 있는가(`compact_text`로 비교) | 25 |

| 함수 | 확인 명령 | 정상 기준(이 데이터) |
|---|---|---|
| `grade` | `--qid Q01`, `--qid Q18` | 같은 결과면 언제나 같은 판정. 불확실이면 「④ 질문 변환」이 이어짐 |
| `apply_transform_rules` | `"모아생활 연회비 안 내려면 어케 해?"` | clarify면 되묻고 끝, keep이면 재검색 없음, 그 밖은 재검색 1/1 |
| `generate_answer` | `--qid Q01`, `--qid Q18` | 문장, 청크ID, 인용문이 나옴. 답 없는 질문은 「확인 필요:」만 나오고 ⑥을 건너뜀 |
| `verify_answer` | `--qid Q01` | 「검증 통과」 또는 실패 사유와 「재작성 n/2」 |

```bash
python search_docs.py --qid Q01
python search_docs.py --qid Q18
python search_docs.py "모아생활 연회비 안 내려면 어케 해?"
```

교시 4 끝: `USE_TEACHER_CODE` 목록이 비고 Q01과 Q18이 아래 완료 기준대로 끝나면 완료임.  
교시 4가 넘치면 `apply_transform_rules`는 숙제로 돌려도 됨(목록에 이름을 남기면 강사 코드가 대신 돎).

## 4. 완료 기준

| 항목 | 기준 |
|---|---|
| 교체 실행 | `USE_TEACHER_CODE`가 빈 `my_search.py`로 Q01이 「답변 완료」, ⑥ 검증 통과 |
| 답 없는 질문 | Q18이 지어내지 않고 되묻기 또는 「확인 필요」로 끝남(어느 단계에서 막혔는지 설명할 수 있음) |
| 회원 권한 | `--qid Q14`의 BM25 대상 청크가 4개(M-1042의 상담만), 같은 질문을 `--role agent`로 돌리면 212개 |
| 제출 | `my_search.py`와 Q01, Q18 실행 화면 캡처 |

## 5. 막혔을 때

| 증상 | 할 일 |
|---|---|
| `오류: 인덱싱 결과가 없음` | `../indexing`에서 `index_docs.py`를 `--limit` 없이 전체 실행하거나 강사 배포 `data/`를 복사 |
| `오류: ... 에 GROQ_API_KEY 가 없음` | 저장소 루트 `secrets/.env`에 키 2줄을 넣음 |
| `NotImplementedError: 빈칸 N을 채울 것` | 그 함수의 빈칸을 아직 안 채움. 채웠으면 `raise` 줄을 지웠는지 확인. 또는 이름을 `USE_TEACHER_CODE` 목록에 다시 넣음 |
| `429`, `rate limit` | 조별 한 대만 실행, 1 ~ 2분 뒤 다시. 수정을 반복할 때는 `--no-answer` |
| 경고: 색인과 검색기의 토큰화 모듈이 다름 | `search_docs.py`의 `import core_indexing as indexing`을 색인을 만든 모듈로 맞춤 |
| 본인 함수에서 예외(Traceback) | 실습 함수의 오류는 감추지 않고 그대로 보임. 맨 아래 줄의 파일과 함수가 본인 코드임 |
| 강사와 답 문장이 다름 | 정상임. 대상 청크 수, 판정, 종료 상태를 비교함 |

## 6. 용어 풀이

| 용어 | 뜻 |
|---|---|
| 청크(chunk) | 문서를 검색하기 좋게 잘라 둔 한 토막. 이 실습 색인에는 260개가 있음 |
| Adaptive RAG | 질문 유형에 따라 길을 가름(잡담은 검색 없이, 단순은 1번, 복합은 나눠서) |
| CRAG | 검색 결과를 채점하고, 믿기 어려우면 질문을 바꿔 다시 검색함 |
| Self-RAG | 답을 낸 뒤 근거와 맞는지 스스로 검증함 |
| 메타데이터 필터 | 청크에 붙은 꼬리표(등급, 회원)로 검색 대상을 거름. `$eq`는 같음, `$and`는 모두 만족 |
| 가명 ID | 회원번호를 해시로 바꾼 값(`m_` + 16자). 색인에는 회원번호 대신 이 값만 있음 |
| 벡터 검색(HNSW) | 질문과 청크를 숫자 목록(벡터)으로 바꿔 가까운 것을 빠르게 찾는 근사 검색 |
| 코사인 거리 | 두 벡터의 방향이 얼마나 다른가. 작을수록 가깝고, 1 - 거리를 점수로 써 「클수록 좋게」 맞춤 |
| BM25 | 질문 낱말이 청크에 얼마나 나오는가로 매기는 글자 기반 점수. 상한이 없음 |
| 최소-최대 정규화 | 점수를 (점수 - 최소) / (최대 - 최소)로 0 ~ 1에 펴서 범위가 다른 두 점수를 같은 눈금으로 맞춤 |
| RRF | 점수는 버리고 순위만으로 합치는 방식. 점수 = Σ 1 / (60 + 순위). `--fusion rrf`로 씀 |
| 리랭크 | 질문과 청크를 한 쌍으로 읽어 다시 채점함(Cohere `rerank-v4.0-fast`) |
| 주 점수, 격차, 검색기 합의 | 채점 신호. 1위 리랭크 점수, 1위와 다른 대상 최고 점수의 차, 벡터와 BM25 상위의 겹침 수 |
| 질문 변환 | 불확실할 때 질문을 바꿔 재검색함. rewrite(또렷하게), multi(여러 표현), hyde(가상 답변), stepback(넓혀서) |
| keep, clarify | 바꾸지 않음, 사용자에게 되물음 |
| LCEL 체인 | `프롬프트 \| 모델`처럼 `\|`로 단계를 이어 붙이는 LangChain 문법 |
| 구조화 출력 | LLM이 정해진 칸(Pydantic 스키마)을 채운 객체로 답하게 함(`with_structured_output`) |
| 인용문 | 답 문장마다 붙는, 근거 청크 본문에서 글자 그대로 옮긴 문장. ⑥이 이것을 본문과 대조함 |
| 확인 필요 | 근거에 답이 없을 때 지어내지 않고 내는 끝맺음. 정상 종료임 |

## 7. 더 해 보기(선택)

- 154쪽 복합 질문 「다음 연도 기본 연회비 면제 기준과 한빛 모아생활 생활 포인트 적립을 위한 전월 최소 이용액」을 돌려  
  하위 질문 2개로 나뉘는지 봄
- `--fusion rrf`로 Q07을 돌려 `weighted`와 융합 순위가 어떻게 다른지 봄
- `--top-k 5` 값을 바꿔 질의당 근거 수에 따른 답 변화를 봄
- `--role auditor --member-id M-1042`로 같은 상담 질문을 돌려 볼 수 있는 청크 수를 비교함

## 8. 참고 링크

- 예제 README: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/rag/retriever/README.md
- 핵심 모듈(정답): https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/rag/retriever/core_search.py
- 교육생 뼈대: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/rag/retriever/my_search.py
- main: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/rag/retriever/search_docs.py
- 개발계획서(강사용): https://github.com/unicorn-campus/hybrid-ai/blob/main/teacher/plan/rag-search-개발계획서.md
