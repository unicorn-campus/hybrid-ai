# RAG 실습 예제 — 인덱싱, 검색, RAGAS 평가

하이브리드 AI 교육 3 ~ 4주차 「문서 인덱싱」, 「문서 검색」, 「품질 평가」 실습용 예제임.  
레이어드 아키텍처 없이 **main 1개 + 핵심 모듈 1개**로 짰고, 교육생은 핵심 모듈만 클론 코딩한 뒤 본인 코드로 바꿔 끼움.  
실습 진행 순서와 시간 배분은 [실습계획서](../../plan/rag-실습계획서.md)에 있음.

## 1. 세 프로그램의 관계

```mermaid
flowchart LR
    DOCS[docs/<br/>약관 pdf, 혜택 pdf, 상담 txt] --> IDX[indexing/index_docs.py<br/>로드, 정제, 가명처리, 청킹, 임베딩, 적재]
    IDX --> DATA[(indexing/data/<br/>chroma/, chunks.json)]
    DATA --> RET[retriever/search_docs.py<br/>벡터 + BM25, 융합, 리랭크, 답변]
    EVAL[ragas/eval-set.json<br/>22문항] --> RUN[retriever/run_eval.py]
    DATA --> RUN
    RUN --> LOG[(retriever/logs/results.json)]
    LOG --> RAG[ragas/evaluate_ragas.py<br/>4지표 채점]
```

| 폴더 | main | 핵심 모듈(클론 코딩 대상) | 교육생 작업 파일 | 만드는 것 |
|---|---|---|---|---|
| `indexing/` | `index_docs.py` | `core_chunking.py` | `my_chunking.py` | `data/chroma/`, `data/chunks.json` |
| `retriever/` | `search_docs.py`, `run_eval.py` | `core_hybrid.py` | `my_hybrid.py` | 검색 결과 화면, `logs/results.json` |
| `ragas/` | `evaluate_ragas.py` | `core_scoring.py` | `my_scoring.py` | 채점 표, `logs/ragas-*.json` |

## 2. 준비물

| 항목 | 값 |
|---|---|
| Python | 3.13 |
| 임베딩 모델 | Cohere `embed-v5.0-fast` (API, 2048차원) |
| LLM | Groq `openai/gpt-oss-120b` (답변 생성, RAGAS 채점) |
| 리랭커 | Cohere `rerank-v4.0-fast` (API) |
| 형태소 분석 | Kiwi(`kiwipiepy`, 로컬. BM25 토큰화) |
| API 키 | 저장소 루트 `secrets/.env` 에 `GROQ_API_KEY=...`, `COHERE_API_KEY=...` 두 줄. 다른 곳에 적지 않음 |
| 로컬 모델 | 없음. 임베딩과 리랭크가 모두 API라 GPU, torch, 모델 다운로드가 필요 없음 |

## 3. 가상환경 설정과 패키지 설치

가상환경은 **두 개**임. `indexing/`과 `retriever/`는 이 폴더의 `.venv`를 함께 쓰고, `ragas/`는 자기 폴더의 `.venv`를 씀.  
이유: `ragas 0.4.3`이 `langchain 1.x`와 같이 깔리면 import가 실패함(`ragas/requirements.txt` 주석 참고).  
둘 다 가벼움(각각 수백 MB). GPU와 로컬 모델은 필요 없음.

### Windows PowerShell

```powershell
cd hands-on\solutions\rag
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ragas
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Windows Git Bash

```bash
cd hands-on/solutions/rag
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
cd ragas
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

### macOS, Linux (zsh, bash)

```bash
cd hands-on/solutions/rag
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd ragas
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

설치 확인

```bash
.venv/Scripts/python.exe -c "import langchain, chromadb, kiwipiepy, cohere; print('ok')"
ragas/.venv/Scripts/python.exe -c "import ragas; print(ragas.__version__)"
```

- macOS와 Linux는 `.venv/Scripts/python.exe` 대신 `.venv/bin/python`을 씀. 아래 실행 명령도 같음
- 가상환경을 "활성화(activate)"하지 않고 venv 안의 파이썬을 직접 지정하는 방식임.  
  PowerShell의 `Activate.ps1`은 실행 정책에 막힐 수 있고, 두 가상환경을 오갈 때 어느 쪽이 켜졌는지 헷갈리기 때문임
- 저장소를 통째로 clone해서 씀. `rag/` 폴더만 복사하면 `docs/`와 `secrets/`를 찾지 못함

## 4. 실행 순서

```bash
# 1) 인덱싱 — 처음엔 --limit 8 로 빨리 확인(결과는 data-limit/). 검색 전에는 전체 실행(data/, 약 1분)
cd indexing
../.venv/Scripts/python.exe index_docs.py --limit 8
../.venv/Scripts/python.exe index_docs.py

# 2) 검색 — 질문 하나로 단계별 출력 확인
cd ../retriever
../.venv/Scripts/python.exe search_docs.py "직전 12개월 동안 카드를 얼마나 쓰면 다음 해 기본 연회비가 면제되나요?"

# 3) 평가셋 22문항 실행 → logs/results.json
../.venv/Scripts/python.exe run_eval.py

# 4) RAGAS 채점(전용 가상환경)
cd ../ragas
.venv/Scripts/python.exe evaluate_ragas.py --limit 3
.venv/Scripts/python.exe evaluate_ragas.py
```

인덱싱이 도는 동안에는 검색 프로그램을 실행하지 않음(같은 Chroma 폴더를 두 프로그램이 열면 결과가 흔들림).  
인덱싱이 안 되는 PC는 강사가 배포하는 `indexing/data/`(chromadb 1.5.9 기준)를 복사해 검색부터 시작해도 됨.

각 단계의 자세한 옵션과 출력 읽는 법은 폴더별 README에 있음:
[indexing](indexing/README.md), [retriever](retriever/README.md), [ragas](ragas/README.md).

## 5. 화면 출력에 쓰인 형식 기호

세 프로그램의 `print`에 공통으로 나오는 f-string 형식 기호임. 처음 보면 어렵게 느껴지지만 뜻은 다섯 가지뿐임.

| 기호 | 뜻 | 예 |
|---|---|---|
| `{값:.3f}` | 소수점 아래 3자리 | `0.836` |
| `{값:,}` | 천 단위 쉼표 | `166,893` |
| `{값:04d}` | 4자리 숫자, 빈자리는 0 | `0007` |
| `{값:>2}` | 2칸 오른쪽 정렬 | `' 7'` |
| `{값:<44}` | 44칸 왼쪽 정렬(표 칸 맞춤) | `D1_개인회원표준약관_합성.pdf      ` |

## 6. 교육생 교체 방법(공통)

1. `my_*.py` 뼈대 파일에 강사 시연을 보며 같은 이름, 같은 인자의 함수를 채움
2. main 파일의 import 한 줄을 바꿈. 예: `import core_chunking as chunking` → `import my_chunking as chunking`
3. 같은 명령으로 다시 실행해 단계별 출력을 강사 결과와 비교함
4. 막히면 import를 되돌려 강사 코드로 뒤 단계를 계속 진행함

## 7. 실측값(강사 PC, 2026-10-21, Cohere 임베딩 기준)

| 항목 | 값 |
|---|---|
| 청크 수 | 260개 (약관 15, 혜택 197, 상담 48). 800토큰(Cohere 토크나이저) 초과 0개 |
| 인덱싱 시간 | 전체 12초(임베딩 API 호출 3회, 6초) |
| 개인정보 잔존 | 고객명, 전화, 이메일, 카드번호 문자열 0건 |
| 검색 평가(run_eval) | 답 있는 17문항 Hit@5 17/17, 답 없는 5문항 `확인 필요:` 5/5, 22문항 75초 |
| RAGAS(17행) | 평균 ContextPrecision 0.924, ContextRecall 1.000, Faithfulness 0.833, AnswerRelevancy 0.603. 3분 29초 |
| RAGAS 참고 | AnswerRelevancy는 임베딩 모델에 따라 분포가 달라짐(KURE-v2 때 0.742). 절댓값보다 기준선 대비 변화를 봄 |
| RAGAS 흔들림 | 같은 로그를 두 번 채점하면 문항별 값이 바뀜(Faithfulness 1.0 ↔ 0.0). 평균 비교 때는 `--repeat` 사용 |

## 8. Cohere 비용과 무료(체험) 키

출처(2026-10-21 확인): [요금 페이지](https://cohere.com/pricing),  
[호출 제한 문서](https://docs.cohere.com/docs/rate-limits).  
요금은 바뀔 수 있으므로 교육 전날 다시 확인함.

### 8.1 요금표(종량제, Production 키)

| 모델 | 쓰는 곳 | 단가 | 과금 단위 |
|---|---|---|---|
| Embed 5 Fast (`embed-v5.0-fast`) | 인덱싱 문서 임베딩, 검색 질문 임베딩, RAGAS AnswerRelevancy | $0.08 / 1M 토큰 | 입력 토큰 |
| Embed 5 Pro (`embed-v5.0-pro`) | 쓰지 않음(품질 우선 대안. Fast와 같은 벡터 공간) | $0.12 / 1M 토큰 | 입력 토큰 |
| Rerank 4 Fast (`rerank-v4.0-fast`) | 검색 리랭크 | $2.00 / 1K 검색 | 검색 단위 |
| Rerank 4 Pro (`rerank-v4.0-pro`) | 쓰지 않음(품질 우선 대안) | $2.50 / 1K 검색 | 검색 단위 |

검색 단위(search unit) = 질문 1개 + 문서 최대 100개. 문서가 500토큰을 넘으면 여러 조각으로 나뉘어 조각마다 문서 1개로 셈.  
이 예제는 리랭크 후보가 10개(top_k 5 × 2)이고 청크가 최대 780토큰이라 조각이 늘어도 100개를 넘지 않음 → 검색 1회 = 1단위(실측).

### 8.2 무료(체험, Trial) 키

| 항목 | 내용 |
|---|---|
| 요금 | 무료. 상업용과 운영 목적에는 쓸 수 없음 |
| 월 상한 | 키 하나당 월 1,000회 API 호출 |
| 분당 상한 | Embed 2,000건(input) / 분, Rerank 10회 / 분, Tokenize 100회 / 분 |
| Production 키 | 종량제(위 요금표). Embed 2,000건 / 분, Rerank 1,000회 / 분 |

체험 키로 `run_eval.py`(22문항)를 돌리면 리랭크가 분당 10회를 넘어 429가 날 수 있음.  
그때는 `run_eval.py`의 `SLEEP_BETWEEN_QUESTIONS`를 6초 이상으로 올리거나 `--mode hybrid`(리랭크 없음)로 돌림.

### 8.3 이 예제의 실제 비용(강사 PC 실측, API 응답의 billed_units 기준)

| 작업 | 호출 | 과금량 | 비용(USD) |
|---|---|---|---|
| 전체 인덱싱 1회(청크 260개) | Embed 3회 | 입력 124,325 토큰 | $0.0099 (약 1센트) |
| 검색 1회(질문 임베딩 + 리랭크) | Embed 1회 + Rerank 1회 | 25 토큰 + 검색 1단위 | $0.0020 |
| `run_eval.py` 22문항 | Embed 22회 + Rerank 22회 | 약 550 토큰 + 검색 22단위 | $0.044 |
| RAGAS 17행(AnswerRelevancy 임베딩) | Embed 약 17 ~ 34회 | 약 2,000 토큰 | $0.0002 |
| 교육생 1명 한 주차(인덱싱 3회, 검색 50회, run_eval과 RAGAS 1회씩) | 약 190회 | 위 합계 | 약 $0.18 |
| 교육생 25명 두 주차 | 약 9,500회 | — | 약 $9 |

- 비용의 대부분은 리랭크(검색 1회당 $0.002)이고 임베딩은 거의 공짜임(인덱싱 100번 해야 $1)
- 체험 키는 비용이 0이지만 월 1,000회 상한이 있어 교육생 1명이 두 주차를 쓰면 약 380회, 조별 공용 키라면 상한에 걸릴 수 있음
- 토큰 수는 `index_docs.py`가 쓰는 Cohere 오프라인 토크나이저 계산값(124,351)과 과금값(124,325)이 거의 같음
