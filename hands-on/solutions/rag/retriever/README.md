# RAG 검색 실습 예제 — 검색 워크플로우 6단계

하이브리드 AI 교육 「문서 검색」(교재 『W01 ~ W04』 150 ~ 174쪽) 실습용 예제임.  
W3 인덱싱 실습(`../indexing`)이 만든 색인(Chroma 벡터, bm25s 점수표)을 읽어, 교재 150쪽 **고정 워크플로우 6단계**  
(① 권한 필터 → ② Adaptive 분류 → ③ 검색 → ④ CRAG 채점 → ⑤ 답변 생성 → ⑥ Self-RAG 근거 검증)를 돌림.  
레이어드 아키텍처 없이 **main 1개 + 핵심 모듈 1개**로 짰고, 교육생은 핵심 모듈의 실습 함수 10개를 클론 코딩한 뒤 본인 코드로 바꿔 끼움.  
개발 계획과 결정 사항은 [개발계획서](../../../../teacher/plan/rag-search-개발계획서.md)에 있음.

## 수업용 명령 2개

이 폴더(`hands-on/solutions/rag/retriever`)에서 실행함.

```bash
../.venv/Scripts/python.exe search_docs.py --qid Q01
```

```bash
../.venv/Scripts/python.exe search_docs.py --qid Q18
```

첫 명령은 약관 질문을 ① ~ ⑥ 끝까지 돌려 「답변 완료」를 봄(약 4초, LLM 2번, 임베딩 1번, 리랭크 1번).  
둘째 명령은 근거에 답이 없는 질문(연회비를 포인트로 내기)이 지어내지 않고 되묻기 또는 「확인 필요」로 끝나는 것을 봄.  
macOS와 Linux는 `../.venv/Scripts/python.exe` 대신 `../.venv/bin/python`을 씀. 나머지 옵션은 4장에 있음.

## 1. 목표와 주요 기능

| 목표 | 내용 |
|---|---|
| 개념을 코드로 | 교재 147쪽 「Self-RAG + Adaptive RAG + CRAG 결합」 워크플로우를 단계 함수 하나씩으로 봄. 분기는 모두 미리 그린 `if`, 반복은 고정 상한 |
| 클론 코딩 | 단계마다 실습 함수 1개 이상, 모두 10개(직접 4개, 빈칸 6개). `my_search.py`에 채우고 import 한 줄로 바꿔 끼움 |
| 눈으로 확인 | 권한 대상 청크 수, LLM 제안과 코드 확정, 벡터와 BM25와 융합 순위, 리랭크 전후 순위, 채점 신호 6개와 판정, 질문 변환 기법, 재검색 전후 근거, 문장별 인용, 검증 결과, 종료 상태를 화면에 찍음 |

주요 기능

- **LLM은 제안만, 결정은 코드**: ② 질문 유형과 ④ 질문 변환은 LLM이 제안하고, 받아들일지는 코드 규칙(`apply_plan_rules`,  
  `apply_transform_rules`)이 정함. ④ 채점(`grade`)과 ⑥ 검증(`verify_answer`)은 LLM 없이 규칙으로만 함
- **권한은 검색 전에**: 역할(agent, auditor)과 회원번호로 벡터 검색은 Chroma 필터, BM25는 0과 1 마스크로 거름
- **하이브리드 검색**: 벡터(Cohere `embed-v5.0-fast` + Chroma HNSW)와 BM25(Kiwi + bm25s)를 가중합(6 : 4)으로 합친 뒤  
  Cohere `rerank-v4.0-fast`로 다시 채점해 근거 5개를 고름
- **LCEL 체인과 구조화 출력**: LLM 호출 3곳(② 분류, ④ 질문 변환, ⑤ 답변)은 모두 `프롬프트 | 모델.with_structured_output(스키마)`로 짬.  
  ⑤는 문장마다 청크ID와 인용문을 따로 받아 ⑥이 글자 대조를 할 수 있음
- **지어내지 않음**: 근거가 없거나(부정확), 핵심어가 근거에 없거나, 인용 검증을 끝내 통과하지 못하면 「확인 필요」로 끝냄

## 2. 디렉토리 구조

```text
hands-on/solutions/rag/
├─ .venv/                      인덱싱과 검색 공용 가상환경
├─ indexing/                   (읽기만) data/chroma(본문, 메타데이터, 벡터), data/bm25(점수표, 사전), core_indexing.py(토큰화)
└─ retriever/
   ├─ README.md                이 문서
   ├─ requirements.txt         rag/requirements.txt와 같은 판
   ├─ search_docs.py           main: 설정 상수(기준값, 상한), 프롬프트와 스키마(분류, 질문 변환), 시작 검사, 색인 열기,
   │                           LLM 호출 2종, 단계 함수 ① ~ ⑥, run_workflow(분기와 반복 상한), 화면 출력, 명령행
   ├─ core_search.py           핵심(클론 코딩 대상): 실습 함수 10개 + 제공 함수
   └─ my_search.py             교육생 작업 파일(뼈대). 맨 아래 USE_TEACHER_CODE 목록의 함수는 강사 코드가 대신 돎
```

| 단계 | 교재 | 실습 함수(`core_search.py`) | 방식 | main이 하는 일(`search_docs.py`) |
|---|---|---|---|---|
| ① 권한 필터 | 151 | `build_chroma_filter` | 빈칸 2곳 | 회원번호 → 가명 ID, BM25 마스크(제공 `build_weight_mask`) |
| ② Adaptive 분류 | 152 ~ 155 | `apply_plan_rules` | 빈칸 3곳 | 분류 LLM 호출(`classify_question`) |
| ③ 검색: 벡터 | 159, 160 | `search_vector` | 빈칸 2곳 | 후보 수 top_k × 4 |
| ③ 검색: BM25 | 157, 158 | `search_bm25` | 직접 | 질의 토큰화(인덱서 `tokenize_korean`) |
| ③ 검색: 융합 | 161, 162 | `fuse_weighted` | 직접 | 상위 top_k × 2를 리랭크로. 복합 질문은 하위 질문 근거를 RRF로(제공 `fuse_rrf`) |
| ③ 검색: 리랭크 | 163 ~ 166 | `rerank` | 빈칸 2곳 | 원 질의 기준으로 다시 채점 |
| ④ CRAG 채점 | 149, 171 | `grade` | 직접 | 신호 6개 계산(제공 `build_signals`) |
| ④ 질문 변환 | 167 ~ 170, 172 | `apply_transform_rules` | 빈칸 3곳 | 변환 LLM 호출(`transform_query`), 재검색, 재채점 |
| ⑤ 답변 생성 | 173 | `generate_answer` | 빈칸 2곳 | 근거 고르기(제공 `select_evidence`) |
| ⑥ 근거 검증 | 174 | `verify_answer` | 직접 | 실패면 ⑤ 재작성(최대 2회) |

읽기만 하는 입력

- 색인: `../indexing/data/chroma`(collection `card_docs`, 260청크),  
  `../indexing/data/bm25`(점수표, `chunk_ids.json`, `dictionary.json`, `manifest.json`)
- 평가셋: `hands-on/solutions/eval-set.json`(25문항. `--qid`로 한 문항씩 씀)
- 비밀값: 저장소 루트 `secrets/.env`의 `GROQ_API_KEY`, `COHERE_API_KEY`.  
  `dotenv_values()`로 읽어 클라이언트에 인자로만 넘김(환경변수에 올리지 않음, 화면에 찍지 않음)

## 3. 준비물과 가상환경 설정

| 항목 | 값 |
|---|---|
| Python | 3.13 |
| LLM | Groq `openai/gpt-oss-120b`(② 분류, ④ 질문 변환, ⑤ 답변). 구조화 출력은 `method="json_schema", strict=True` |
| 임베딩 | Cohere `embed-v5.0-fast`(2048차원, 인덱서와 같은 모델) |
| 리랭커 | Cohere `rerank-v4.0-fast`(SDK `cohere.ClientV2.rerank`. 점수가 `relevance_score`로 바로 보임) |
| BM25 | `bm25s` 저장 색인 + `kiwipiepy`(인덱서 토크나이저 재사용) |
| 로컬 모델 | 없음(임베딩, 리랭크, LLM 모두 API) |

### 3.1 사전 조건

- W3 인덱싱 실습을 전체 실행해 `../indexing/data/`에 `chroma/`와 `bm25/`가 있어야 함(없으면 강사 배포본을 복사)
- 저장소를 통째로 clone해서 씀(`secrets/`, `hands-on/solutions/eval-set.json`, `indexing/`을 상대 경로로 찾음)

### 3.2 가상환경(Windows PowerShell)

W3에서 만든 `rag/.venv`를 그대로 씀. 없으면 아래로 만듦.

```powershell
cd hands-on\solutions\rag
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r retriever\requirements.txt
```

### 3.3 가상환경(Windows Git Bash)

```bash
cd hands-on/solutions/rag
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r retriever/requirements.txt
```

### 3.4 가상환경(macOS, Linux)

```bash
cd hands-on/solutions/rag
python3.13 -m venv .venv
.venv/bin/python -m pip install -r retriever/requirements.txt
```

설치 확인(Windows는 `.venv/Scripts/python.exe`, macOS와 Linux는 `.venv/bin/python`)

```bash
.venv/Scripts/python.exe -c "import langchain, langchain_groq, chromadb, kiwipiepy, cohere, bm25s; print('ok')"
```

- 가상환경을 활성화(activate)하지 않고 venv 안의 파이썬을 직접 지정함. PowerShell의 `Activate.ps1`이 실행 정책에 막히는 일을 피함

## 4. 실행 방법

모두 `retriever` 폴더에서 실행함. 인덱싱이 도는 동안에는 실행하지 않음(같은 Chroma 폴더를 두 프로그램이 열면 결과가 흔들림).

| 쓰임 | 명령(예) | 설명 |
|---|---|---|
| 평가셋 질문 | `../.venv/Scripts/python.exe search_docs.py --qid Q01` | 역할은 평가셋 `filters`대로 자동(회원 문항은 auditor + 그 회원, 나머지는 agent) |
| 자유 질문 | `../.venv/Scripts/python.exe search_docs.py "한빛 모아생활 카드의 생활 포인트 적립률은?"` | 기본 역할 agent |
| 회원 상담 | `../.venv/Scripts/python.exe search_docs.py "첫 상담에서 무엇을 요청했나요?" --role auditor --member-id M-1042` | 그 회원의 상담 이력만 봄 |
| 근거만 보기 | 위 명령 + `--no-answer` | ⑤, ⑥ 건너뜀(Groq 호출은 ②, ④만) |
| 기타 | `--top-k 5`, `--fusion weighted` 또는 `--fusion rrf` | 질의당 근거 수, 벡터와 BM25 융합 방식 |

수업 중에는 조별 1대로 실행함. Cohere 체험 키는 리랭크가 분당 10회이고 복합 질문 한 번에 리랭크가 최대 6번 일어남.

## 5. 단계별 출력 읽는 법

`--qid Q01` 실제 화면(일부 줄임)

```text
[① 권한 필터] 볼 수 있는 청크만 남김
  역할: agent (볼 수 있는 등급 ['public'])
  Chroma 필터: {'access_level': {'$eq': 'public'}}
  BM25 대상 청크: 212개 (전체 260개 중 권한 마스크 통과)
[② Adaptive 분류] LLM이 제안하고 코드 규칙이 확정함
  LLM 제안: 유형 simple, 하위 질문 []
  코드 확정: 유형 simple, 검색할 질의 1개
[③ 검색] 질의 q1/1: 직전 12개월 동안 카드를 얼마나 쓰면 다음 해 기본 연회비가 면제되나요?
   벡터 검색(embed-v5.0-fast, 점수 = 1 - 코사인 거리) 후보 20개 중 상위 5
     1  0.482  D1-0007    D1_개인회원표준약관_합성.pdf p.7    제10조(연회비 면제 및 계약 해지에 따른 반환) ...
   BM25 검색 토큰 ['직전', '12', '동안', '카드', '쓰', '다음', '해', '기본', '연회비', '면제'] 후보 20개 중 상위 5
     1  7.427  D1-0007    D1_개인회원표준약관_합성.pdf p.7    제10조(연회비 면제 및 계약 해지에 따른 반환) ...
   융합(가중합: 벡터 0.6 + BM25 0.4) 상위 10 → 리랭크로 넘김
     1  1.000  D1-0007    [vector, bm25]  D1_개인회원표준약관_합성.pdf p.7 ...
   리랭크(Cohere rerank-v4.0-fast, 원 질의 기준) 상위 5
     1  0.908  D1-0007    (융합  1위 → 1위)  D1_개인회원표준약관_합성.pdf p.7 ...
     2  0.689  D1-0006    (융합  9위 → 2위)  D1_개인회원표준약관_합성.pdf p.6 ...
[④ CRAG 채점] 질의 q1: 신호 6개 → 판정
    - 주 점수(1위 리랭크) 0.908 (하한 0.3, 상한 0.7)
    - 격차(1위 - 다른 대상 최고) 0.219 (최소 0.05)
    - 핵심어 ['12'] → 근거에 없는 것 []
  판정: 정확
[⑤ 답변 생성] 근거만으로, 문장마다 청크ID와 인용문
  1. 직전 12개월 이용금액이 3,000,000원 이상이고 연체가 없으면 다음 연도의 기본 연회비가 전액 면제됩니다.
     인용 [D1-0007] "본인회원의 직전 12개월 이용금액이 3,000,000원 이상이고 다음 연회비 청구일까지 연"
[⑥ Self-RAG 근거 검증] 인용 청크ID와 인용문을 근거 본문과 대조
  검증 통과 (문장 1개 모두 인용이 본문과 맞음)
[종료] 답변 완료
```

| 자리 | 볼 것 | 정상 기준(이 데이터) |
|---|---|---|
| ① | Chroma 필터, BM25 대상 청크 수 | agent 212개(public), auditor 260개, auditor + M-1042는 4개(그 회원 상담만) |
| ② | LLM 제안 → 코드 확정, 규칙이 바꾼 이유 | 「안녕하세요」는 잡담으로 검색 0회. 154쪽 복합 질문은 하위 질문 2개 |
| ③ 벡터 | 점수(1 - 코사인 거리) | 정답 청크 0.45 ~ 0.6, 관련 없는 청크 0.2 ~ 0.4. 절댓값보다 순위를 봄 |
| ③ BM25 | 질문 토큰, 점수 | 카드명이 한 토큰(`한빛모아생활`). 점수는 상한이 없음(0 ~ 수십) |
| ③ 융합 | [vector, bm25] 표시 | 두 검색에 모두 나온 청크가 위로. 양쪽 1위면 1.0 |
| ③ 리랭크 | 융합 n위 → m위, 점수 | 정답 청크 0.7 이상, 관련 없는 청크 0.3 이하로 벌어짐 |
| ④ 채점 | 신호 6개와 기준값, 판정 | 같은 결과면 언제나 같은 판정. 불확실이면 「④ 질문 변환」이 이어짐 |
| ④ 질문 변환 | LLM 제안 → 금지 규칙 → 코드 결정, 재검색 전후 근거 | clarify면 되묻고 끝, keep이면 재검색 없음, 그 밖은 재검색 1/1 |
| ⑤ | 문장, 청크ID, 인용문 | 답 없는 질문은 「확인 필요:」만 나오고 ⑥을 건너뜀 |
| ⑥ | 검증 통과 또는 실패 사유, 재작성 n/2 | 실패 사유를 받아 다시 쓴 답이 통과하는지 봄 |

종료 상태: 답변 완료, 잡담, 되묻기, 근거 부족, 검증 실패, 검색만(`--no-answer`), 오류. 「확인 필요」도 정상 종료임.

### 5.1 분기와 반복 상한(main `run_workflow`)

| 자리 | 조건 | 다음 |
|---|---|---|
| ② 뒤 | 잡담 / 단순 / 복합 | 인사 답으로 끝 / 질의 1개 / 하위 질문 2 ~ 3개(`MAX_SUB_QUESTIONS` 3) |
| ④ 뒤 | 불확실 질의 | 질문 변환 → 재검색 → 재채점(`MAX_RESEARCH` 1회). 리랭크가 실패한 질의는 재검색하지 않음 |
| ④ 변환 뒤 | clarify | 되물음으로 끝. 복합 질문의 하위 질문이면 keep으로 바꿈(다른 하위 질문 답까지 버리지 않게) |
| 근거 고르기 | 부정확 질의, 핵심어가 근거에 없는 불확실 질의 | 근거에서 뺌. 남은 근거 0건이면 「근거 부족」으로 끝(LLM 호출 없음) |
| 근거 고르기 | 정확, 불확실 질의 | 리랭크 0.3 이상 청크만 ⑤로. 불확실이 섞이면 「불확실 근거 포함」 표시 |
| ⑥ 뒤 | 인용 검증 실패 | 실패 사유를 넣어 ⑤ 재작성(`MAX_REWRITES` 2회). 다 쓰면 「검증 실패」 |

외부 API가 실패하면(429, 시간 초과, 모델명 오류) ② 분류는 단순 질문으로, 임베딩은 BM25만으로, 리랭크는 융합 순위로,  
④ 변환은 keep으로, ⑤ 답변은 「확인 필요: 답변 생성 실패」로 넘어감. 교육생 실습 함수의 오류는 감추지 않고 그대로 띄움.

## 6. 교육생 교체 방법

1. `my_search.py`에 같은 이름, 같은 인자의 함수를 채움. 직접 작성 4개는 `NotImplementedError("여기에 본인 코드를 작성함")` 자리,  
   빈칸 6개는 `NotImplementedError("빈칸 N을 채울 것")` 자리
2. `search_docs.py`의 import 한 줄을 바꿈

   ```python
   import core_search as core   # 강사 코드로 실행
   import my_search as core     # 본인 코드로 실행 (이 줄만 바꿈)
   ```

3. `my_search.py` 맨 아래 `USE_TEACHER_CODE` 목록에서 지금 채운 함수 이름을 지움(남은 함수는 강사 코드가 대신 돎)
4. 같은 명령으로 다시 실행해 5장 표대로 강사 결과와 비교함. 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감
5. W3 인덱싱을 `my_indexing.py`로 했다면 `search_docs.py`의 `import core_indexing as indexing`도 `my_indexing`으로 바꿈

| 교시 | 채우는 함수(순서대로) | 확인 명령 |
|---|---|---|
| 2 | `build_chroma_filter` → `apply_plan_rules` → `search_vector` | `--qid Q14`, 같은 질문 `--role agent`, `"안녕하세요"`, `--qid Q01 --no-answer` |
| 3 | `search_bm25` → `fuse_weighted` → `rerank` | `--qid Q07 --no-answer` |
| 4 | `grade` → `apply_transform_rules` → `generate_answer` → `verify_answer` | `--qid Q01`, `--qid Q18`, `"모아생활 연회비 안 내려면 어케 해?"` |

## 7. 실측값(강사 PC, 2026-10-26)

### 7.1 평가셋 25문항(`--qid Q01` ~ `Q25`를 차례로 실행, 마지막 실행)

| 항목 | 값 |
|---|---|
| 답 있는 20문항 | 답변 완료 18, 근거 적중 18/20(정답 근거 문장이 ⑤에 넘긴 근거 안에 있음). 약관, 혜택, 상담 17문항(Q01 ~ Q17)은 모두 답변 완료와 적중 |
| 답 없는 5문항(Q18 ~ Q22) | 5/5 답변 완료가 아님(근거 부족 4, 되묻기 1). 지어낸 답 0건 |
| 답하지 못한 문항 | Q23, Q24(고객군별 불만, 받아들인 제안의 공통점). 여러 상담을 모아 경향을 묻는 질문이라 청크 5개 검색으로는 답이 없음 → GraphRAG 실습(W5 ~ W7)에서 다룸 |
| 질문 변환이 일어난 문항 | 10문항(rewrite, multi, hyde, stepback, clarify, keep 모두 나옴) |
| 종료 상태 | 답변 완료 18, 근거 부족 6, 되묻기 1 |
| 호출(25문항 합계) | LLM 59번, 임베딩 46번, 리랭크 41번. 문항당 시간 중앙값 3.6초, 최대 11.6초 |
| 비용(추정) | 리랭크 41회 × $0.002 ≈ $0.08 + 임베딩과 Groq 수 센트 미만. 25문항 1회 약 $0.1 |

이전 예제(`teacher/rag/retriever`, ①③⑤만)의 결과(답 있는 17문항 적중 17/17, 답 없는 5문항 확인 필요 5/5)보다 나빠지지 않음.

### 7.2 경로별 실제 실행

| 경로 | 질문(예) | 결과 |
|---|---|---|
| 잡담 | 「안녕하세요, 수고 많으세요」 | 검색 0회, LLM 1번으로 끝 |
| 복합(분해) | 154쪽 「다음 연도 기본 연회비 면제 기준과 한빛 모아생활 생활 포인트 적립을 위한 전월 최소 이용액」 | 하위 질문 2개 모두 정확, 근거 RRF 합치기, 두 문장 답 |
| 불확실 → 재검색 | 「모아생활 연회비 안 내려면 어케 해?」, Q16, Q17 | rewrite 또는 hyde 뒤 재검색, 답변 완료 |
| 대상 섞임 → 되묻기 | Q18 「연회비를 적립 포인트로 낼 수 있나요?」 | 코드 규칙(대상명 없음 + 카드 3종 섞임)이 clarify |
| 부정확 | 「비트코인 오늘 시세가 얼마인가요?」 | 1위 리랭크 < 0.3 → 근거 부족(LLM 답변 호출 없음) |
| 핵심어 없음 → 근거 부족 | Q20 「이전 버전(1.1) 약관」 | 근거에 1.1이 없어 근거에서 뺌, 현재 약관으로 답하지 않음 |
| 검증 실패 → 재작성 | Q17(개발 중 실행) | 3번 문장 인용문이 본문과 달라 재작성 1/2 → 검증 통과 |
| 권한 | Q14를 `--role agent`로 | 상담 청크 0건(약관만 검색) |
| API 실패 | 리랭크 모델명, LLM 모델명을 일부러 틀림 | 융합 순위로 답변 완료 / 분류는 단순 처리, 답변은 「확인 필요: 답변 생성 실패」 |

### 7.3 개발 중 평가셋으로 바꾼 것

| 문제(실측) | 바꾼 것 |
|---|---|
| 혜택 청크의 카드 코드(D2-C001-B02)를 청크ID로 인용해 검증이 늘 실패(5문항) | 근거를 `<청크 id="D2-0007">` 태그로 감싸고 프롬프트에 「본문 속 코드는 청크ID가 아님」 |
| 상담 질문의 회원번호(M-1042)가 핵심어로 잡혀 늘 「근거에 없음」, 답변 LLM은 「그 회원 것인지 확인 불가」 | ① 필터를 만든 뒤 ② ~ ⑤의 질문에서 회원번호를 지움 |
| 「이전 버전(1.1)」 질문에 현재 약관으로 답함 | 불확실 질의는 핵심어가 근거에 없으면 근거에서 뺌(교재 149쪽 「핵심어 일치: 없으면 부정확」) |
| 복합 질문의 짧은 하위 질문에 LLM이 되묻기를 골라 답 전체를 버림(3문항) | 복합 질문의 하위 질문은 clarify를 keep으로 바꿈, 분류 프롬프트에 「뒤 질문에도 대상을 다시 적음」 예시 |
| 내용어가 없는 질문(기호뿐, 영어만 등)에서 bm25s `get_scores([])`가 IndexError(context7 문서 대조 뒤 실측) | 질문 토큰이 0개면 BM25를 건너뛰고 벡터 결과만으로 융합 |

같은 질문도 LLM 답(분류, 변환 기법, 답 문장)은 실행마다 조금씩 다를 수 있음. 교육생은 강사와 같은 문장이 아니어도 5장 표의  
정상 기준(대상 청크 수, 판정, 종료 상태)으로 자기 함수를 확인함.

## 8. 막혔을 때

| 증상 | 할 일 |
|---|---|
| `오류: 인덱싱 결과가 없음` | `../indexing`에서 `index_docs.py`를 `--limit` 없이 전체 실행하거나 강사 배포 `data/`를 복사 |
| `오류: ... 에 GROQ_API_KEY 가 없음` | 저장소 루트 `secrets/.env`에 키 2줄을 넣음 |
| `NotImplementedError: 빈칸 N을 채울 것` | 그 함수의 빈칸을 채우거나 이름을 `USE_TEACHER_CODE` 목록에 다시 넣음 |
| `429`, `rate limit` | 조별 한 대만 실행, 1 ~ 2분 뒤 다시. 수정 반복 때는 `--no-answer` |
| 경고: 색인과 검색기의 토큰화 모듈이 다름 | `search_docs.py`의 `import core_indexing as indexing`을 색인을 만든 모듈로 맞춤 |

## 9. 한계

- 경향 질문(여러 상담을 모아 공통점을 묻는 Q23 ~ Q25)은 청크 5개 검색으로는 답하기 어려움. 그래프 검색(W5 ~ W7)의 몫임
- 채점 기준값(상한 0.7, 하한 0.3, 격차 0.05, 겹침 1)은 이 평가셋 25문항으로 정한 출발값임. 문서가 바뀌면 다시 맞춤
- ⑥ 검증은 「인용문이 본문에 글자 그대로 있는가」만 봄. 인용은 맞는데 해석이 틀린 답은 걸러내지 못함
- 근거 적중은 평가셋 정답 문장이 근거에 글자 그대로(공백 무시) 있는지로만 셈
