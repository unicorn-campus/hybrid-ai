# RAGAS 평가 실습 예제 — 하이퍼 파라미터 버전 비교

하이브리드 AI 교육 4주차 「품질 평가 및 튜닝 이해」(교재 176 ~ 193쪽, 코드 장표 195 ~ 207쪽) 실습용 예제임.  
W4에서 만든 RAG 검색기(`../rag/retriever/`)를 **하이퍼 파라미터 값마다(버전마다) 같은 평가셋으로 돌려** 코드 평가 4지표와  
RAGAS(LLM 평가) 5지표로 채점하고, 기준선과 비교해 어디서 새는지 찾음.  
레이어드 아키텍처 없이 **main 1개 + 핵심 모듈 1개**로 짰고, 교육생은 핵심 모듈만 클론 코딩한 뒤 본인 코드로 바꿔 끼움.  
실습 함수 선별과 교시 배치는 [개발계획서](../../../teacher/plan/ragas-개발계획서.md)에 있음.

수업용 명령 2개(가상환경을 켠 뒤 이 폴더에서)

```bash
python evaluate_rag.py --selftest
```

```bash
python evaluate_rag.py --param top_k --values 3 5 10 --until code --qid Q01 Q17 Q20
```

## 1. 목표와 주요 기능

| 기능 | 하는 일 | 교재 |
|---|---|---|
| ① 버전 만들기 | 하이퍼 파라미터 **하나**의 값 목록으로 버전 v01, v02, …를 만듦. 나머지 설정은 기준선 값으로 고정 | 177, 195 |
| ② 검색기 실행 | 버전마다 문항마다 검색기 `run_workflow`를 불러 결과 정보 4칸(질문, 모범 답안, 검색 결과, 답변)을 만듦 | 188 |
| ③ 코드 평가 | 정답 단서를 청크 본문과 글자 대조해 적중 청크를 판정하고 하(Hit@k), 빠(Recall@k), 빨(MRR), 앞(nDCG@k)을 계산. LLM 없음 | 180, 181 |
| ④ LLM 평가 | ragas 0.4.3으로 위(ContextPrecision), 정(ContextRecall), 출(Faithfulness), 관(AnswerRelevancy), 답(FactualCorrectness) | 182 ~ 191 |
| ⑤ 버전 비교 | 버전별 평균(매크로 평균)과 기준선 대비 변화(▲, ▼, 변화 없음), 지표 조합으로 원인 후보 | 178, 187 |
| 결과 파일 | `results/{하이퍼 파라미터명}/evaluate_{YYMMDDHHMM}_{vNN}.md`. 버전마다 1개, 파일마다 같은 비교표 | - |

- 평가 대상 검색기는 **언제나 강사 코드** `../rag/retriever/core_search.py`로 돎(`--mine`은 이 폴더의 평가 함수만 바꿈)
- 실행 옵션 `--until`로 핵심 단계까지만 돌릴 수 있고, `--selftest`는 API 없이 교재 181쪽 예로 계산 함수를 점검함

## 2. 디렉토리 구조

```text
hands-on/solutions/ragas/
├─ .venv/                    이 실습 전용 가상환경(3장). RAG 검색기 패키지 + ragas
├─ requirements.txt          패키지 판 고정
├─ README.md                 이 문서
├─ evaluate_rag.py           main: 설정 상수, 시작 검사, ① ~ ⑤, 결과 파일, --selftest, 명령행(읽기)
├─ core_eval.py              핵심 모듈(클론 코딩 대상): 실습 함수 9개 + 제공 함수
├─ my_eval.template.py       교육생 뼈대(강사가 고침). --mine이 처음 한 번 my_eval.py로 복사함(my_eval.py는 Git이 무시)
└─ results/                  결과 파일. results/top_k/evaluate_2610311725_v01.md 같은 꼴
```

읽기만 하는 입력: 검색기 `../rag/retriever/search_docs.py`, `core_search.py`, 색인 `../rag/indexing/data/`,  
평가셋 `../eval-set.json`(10문항: 답 있음 8, 답 없음 Q20, Q21), 비밀값 `secrets/.env`(저장소 루트).

## 3. 가상환경 설정과 패키지 설치

RAG 실습의 `rag/.venv`를 쓰지 않고 **이 폴더에 `.venv`를 따로** 만듦.  
이유: ragas 0.4.3은 `langchain-community` 0.3 계열을 요구하는데 RAG 실습은 0.4 계열을 씀. 같은 가상환경에 두면 한쪽이 깨짐.  
가상환경을 **활성화(activate)**한 뒤에는 `python`, `pip`이 이 가상환경의 것으로 바뀜. 프롬프트 앞에 `(.venv)`가 보이면 활성화된 것임.  
활성화는 터미널 창마다 한 번 함. 새 터미널을 열면 다시 활성화함.

### 처음 한 번: 만들기, 활성화, 설치

Windows PowerShell

```powershell
cd hands-on\solutions\ragas
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Windows Git Bash

```bash
cd hands-on/solutions/ragas
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

macOS, Linux (zsh, bash)

```bash
cd hands-on/solutions/ragas
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

설치 확인(활성화한 터미널에서. 처음 import는 ragas가 무거워 10초쯤 걸림)

```bash
python -c "import ragas, langchain_chroma, kiwipiepy, cohere, bm25s; print('ok', ragas.__version__)"
```

### 다음부터: 활성화만

| 터미널 | 활성화(`hands-on/solutions/ragas` 폴더에서) | 끄기 |
|---|---|---|
| Windows PowerShell | `.venv\Scripts\Activate.ps1` | `deactivate` |
| Windows Git Bash | `source .venv/Scripts/activate` | `deactivate` |
| macOS, Linux | `source .venv/bin/activate` | `deactivate` |

PowerShell에서 「스크립트를 실행할 수 없으므로」가 나오면 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`를 먼저 실행함  
(지금 창에서만 허용. 자세한 설명은 [RAG README 3장](../rag/README.md#powershell에서-활성화가-막힐-때)).

### 사전 과제와 환경 점검

| 번호 | 과제 | 확인 방법 |
|---|---|---|
| 1 | W3 인덱싱 실습 완료(또는 강사 배포 `rag/indexing/data/` 복사. `chroma/`와 `bm25/` 둘 다) | `rag/indexing/data/bm25/manifest.json`의 `chunk_count`가 260 |
| 2 | 이 폴더의 `.venv`(위 절차) | 설치 확인 명령이 `ok 0.4.3` |
| 3 | 저장소 루트 `secrets/.env`에 `GROQ_API_KEY`, `COHERE_API_KEY`(RAG 실습과 같은 키 2개. 평가자 LLM도 Groq) | `python evaluate_rag.py --param top_k --values 5 --until run --qid Q01`이 끝남 |

`evaluate_rag.py`가 시작할 때 색인 파일, 키, 그리고 **정답 단서가 색인 청크에 실제로 있는지**를 검사하고 빠진 것과 할 일을 출력함.

## 4. 실행 방법

### 4.1 옵션

| 옵션 | 하는 일 | API 호출 |
|---|---|---|
| `--selftest` | 교재 181쪽 가상 예(관련 청크 4, 정답 근거 3, k 5)로 계산 함수를 점검. 기대값 Hit 1, MRR 0.50, Recall 0.67, nDCG 0.41 | 없음 |
| `--param 이름 --values 값 값 …` | 실험할 하이퍼 파라미터와 값 범위(필수) | - |
| `--baseline 값` | 기준선 값. 생략하면 검색기의 현재 값(4.2 표). 기준선 값은 `--values`에 들어 있어야 함 | - |
| `--until versions` | ①까지: 버전 목록만 | 없음 |
| `--until run` | ②까지: 검색기 실행과 결과 정보 4칸 | 검색기(Groq, Cohere) |
| `--until code` | ③과 ⑤까지: 코드 4지표, 비교표, 결과 파일(LLM 칸은 비움) | 검색기 |
| `--until all`(기본) | 전부: 코드 4지표 + LLM 5지표, 비교표, 결과 파일 | 검색기 + 평가자 LLM(Groq), 임베딩(Cohere) |
| `--qid Q01 Q17 Q20` | 일부 문항만(수업 중 빠른 확인) | 줄어듦 |
| `--repeat 3` | 기준선만 3번 채점해 지표별 흔들림 폭을 실측하고 「변화 없음」 기준으로 씀(교재 177쪽) | 기준선 LLM 평가 × 3 |
| `--mine` | 평가 실습 함수를 교육생 코드(`my_eval.py`)로. 검색기는 그대로 강사 코드 | - |

### 4.2 하이퍼 파라미터별 실행 명령

재색인 없이 바꿀 수 있는 5개를 지원함. 기준선은 검색기의 현재 값이며 `--baseline`을 생략하면 그 값을 씀.  
한 번에 하나만 바꿈(교재 177쪽). 수업에서는 `top_k`를 씀(실측값은 7장).

| 이름 | 뜻 | 기준선 | 교재 193쪽 순위 | 명령 |
|---|---|---|---|---|
| `top_k` | 리랭크 뒤 근거 수(⑤에 넘기는 청크 수). 후보 수(×4, ×2)도 함께 늘어남 | 5 | 5 | 아래 ① |
| `vector_weight` | 가중합 융합에서 벡터 점수 비중(BM25 비중은 1 - 값) | 0.6 | 9 | 아래 ② |
| `fusion` | 벡터와 BM25 융합 방식(가중합 또는 RRF) | weighted | 15 | 아래 ③ |
| `rerank_model` | Cohere 리랭커 모델 | rerank-v4.0-fast | 6 | 아래 ④ |
| `llm_model` | Groq 생성 LLM(검색기의 질문 분류, 질문 변환, 답변 생성) | openai/gpt-oss-120b | 1 | 아래 ⑤ |

① Top-k(수업용)

```bash
python evaluate_rag.py --param top_k --values 3 5 10 --repeat 3
```

② 하이브리드 비중(벡터 0.3이면 BM25 0.7)

```bash
python evaluate_rag.py --param vector_weight --values 0.3 0.6 0.8
```

③ 융합 방식

```bash
python evaluate_rag.py --param fusion --values weighted rrf
```

④ 리랭커 모델

```bash
python evaluate_rag.py --param rerank_model --values rerank-v4.0-fast rerank-v4.0-pro
```

⑤ 생성 LLM(Groq 모델 ID. 답변이 바뀌므로 생성 지표(출, 관, 답)가 주로 움직임)

```bash
python evaluate_rag.py --param llm_model --values openai/gpt-oss-120b openai/gpt-oss-20b
```

- 청크 크기, 오버랩, 임베딩 모델(193쪽 2 ~ 4위)은 바꾸면 다시 색인해야 하므로 이 예제가 지원하지 않음
- `--baseline`을 주면 그 값이 ★기준선이 됨(예: `--param top_k --values 5 10 20 --baseline 10`)

### 4.3 실행 시간과 호출(강사 PC 실측, 7장)

문항 1개당 검색기 약 3 ~ 7초, LLM 평가(지표 5개) 약 20 ~ 30초. 10문항 × 3버전 + 기준선 반복 3회는 약 (7장 참고)분.  
수업 중 전체 실행은 조별 1대만 하고, 함수를 채울 때는 `--qid`와 `--until`로 줄여 확인함.

## 5. 화면과 결과 파일 읽는 법

### 5.1 화면

```text
[③ 코드 평가] v02 top_k=5 — 적중 청크와 4지표(교재 180쪽)
  Q17 관련 청크 3개, 정답 근거 3/3 | 1위 3 2위 2 3위 - 4위 1
      Hit 1  Recall 1.00  MRR 1.00  nDCG 0.97
```

- 「1위 3」 = 1위 청크에 정답 근거 ③의 정답 단서가 있음(적중 청크). 「3위 -」 = 적중 아님
- 「정답 근거 3/3」 = 전체 정답 근거 3개 중 3개를 찾음(같은 근거가 여러 청크에 있어도 한 번만 셈)
- 답 없는 문항(Q20, Q21)은 지표를 계산하지 않고 「확인 필요」로 끝났는지만 맞음/틀림으로 봄

### 5.2 결과 파일(`results/top_k/evaluate_…_vNN.md`)

| 절 | 보는 것 |
|---|---|
| 읽는 순서, 범례 | ▲ ▼ 변화 없음, 「-」(기준선 자신 또는 계산 안 함), 「실패」(채점 실패), 「채점 안 함」의 뜻 |
| 실행 정보 | 이 버전의 값과 ★기준선 여부, 고정한 나머지 설정, 평가자 LLM, 흔들림 폭, 실행 명령 |
| 요약 | 9지표 평균과 기준선 대비 변화. 답 없는 문항의 「확인 필요」 맞음 수 |
| 버전 비교표 | 같은 실행의 모든 버전을 한 표로(모든 파일에 같은 표가 있어 하나만 열어도 됨) |
| 원인 후보 | 떨어진 지표 조합으로 본 고칠 곳(교재 187쪽) |
| 문항별 검색 표, 답변 표 | 문항마다 종료 상태, 관련 청크 수, 적중 순위, 9지표 |
| 문항별 상세 | 원 질문과 ragas에 넘긴 질문, 모범 답안, 원 답변과 ragas에 넘긴 답변, 순위별 청크와 담긴 정답 근거, 검색기 실행 기록 |

평균만 보면 0점 문항이 가려지므로 문항별 표를 함께 봄(교재 181쪽 노트).  
답 있는 8문항 중 6문항이 정답 근거 1개라 Recall은 0 또는 1임. 한 문항이 바뀌면 평균이 0.125 움직이므로  
이보다 작은 차이는 의미를 두지 않고, 통계적 유의성도 주장하지 않음.

### 5.3 ragas에 넘기는 질문과 답변을 정리하는 이유

평가자 LLM은 답변을 「주장」으로 쪼개 근거와 대조함(Faithfulness). 이때 질문의 회원번호(M-3001)와 답변 끝의 인용 표시(`[D3-0019]`)까지  
주장에 넣는데, 색인 본문에는 둘 다 없어(회원번호는 가명 처리, 인용 표시는 검색기가 붙인 것) 「근거에 없음」으로 판정됨(2026-10-31 실측 0.00).  
그래서 질문은 검색기가 답변 생성에 넘긴 것과 같게 **회원번호를 지우고**, 답변은 **인용 표시를 빼고** 넘김. 모든 버전에 같게 적용함.  
결과 파일 상세에는 원 질문과 원 답변도 함께 적음. 교재 184쪽은 원 질문을 질문 칸에 보여 주며 평가자도 다르므로 값을 직접 비교하지 않음.

## 6. 교육생 교체 방법과 확인표

1. `python evaluate_rag.py --mine --selftest`처럼 `--mine`을 붙여 실행함. `my_eval.py`가 없으면 `my_eval.template.py`를 복사해 만듦
2. 채울 함수 이름을 `my_eval.py` 맨 아래 `USE_TEACHER_CODE` 목록에서 지움(남은 함수는 강사 코드가 대신 돎)
3. 함수를 채우고 아래 표의 명령으로 실행해 강사 결과와 비교함. 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감
4. `my_eval.py`는 Git이 무시하므로 강사가 뼈대를 고쳐 push해도 pull 충돌이 없음

| 실습 함수 | 확인 명령(이 폴더에서) | 정상 기준 |
|---|---|---|
| `find_hits`, `retrieval_metrics`, `ndcg_at_k` | `python evaluate_rag.py --mine --selftest` | 맞음 12/12. 4위 청크의 정답 근거 ①을 두 번 세면 Recall이 1.00으로 틀림 |
| `build_versions`, `summarize_versions`, `diagnose` | 같은 명령 | 버전 목록 v01=3, v02=5★, v03=10. v01 Recall 변화 ▼, 기준선 「-」 |
| `build_versions`(오류 안내) | `python evaluate_rag.py --mine --param top_k --values 3 10 --until versions` | 「기준선 값 5 이(가) 값 목록에 없음」 오류 |
| `make_result_row` | `python evaluate_rag.py --mine --param top_k --values 5 --until run --qid Q17` | user_input = 「회원과 상담할 때 …」(회원번호 없음), reference = 모범 답안, 검색 결과 4개, response = 인용 표시 없는 답변 |
| 코드 평가 전체(실데이터) | `python evaluate_rag.py --mine --param top_k --values 3 5 --until code --qid Q01 Q17 Q20` | Q17 기준선: 정답 근거 3/3, Hit 1, Recall 1.00, MRR 1.00, nDCG 0.97(185쪽과 같음). Q20 「확인 필요」 맞음. 비교표에 ▼ |
| `build_metrics`, `score_row` | `python evaluate_rag.py --mine --param top_k --values 5 --qid Q17` | 5지표 점수가 나옴. 칸 이름을 틀리면 그 지표가 「채점 실패 TypeError」로 표시됨. 함수 자체의 오류(이름 오타 등)는 Traceback 대신 `Warning: Task failed with error: …` 한 줄로 나오고 그 문항이 「행 전체 채점 실패」가 됨(ragas arun이 행 오류를 경고로만 남김) |

## 7. 실측값(강사 PC, 2026-10-31)

명령 `python evaluate_rag.py --param top_k --values 3 5 10 --repeat 3`(10문항 × 3버전, 기준선 LLM 평가 3회 반복).  
결과 파일 `results/top_k/evaluate_2610311725_v01.md` ~ `_v03.md`.

### 7.1 실행 시간과 호출

| 항목 | 값 |
|---|---|
| 전체 | 913초(약 15분) |
| 검색기 | 문항당 2 ~ 15초. 3버전 합계 LLM 68회, 임베딩 62회, 리랭크 54회 |
| LLM 평가 | 8행(답 있는 문항) 한 회차 100 ~ 206초(문항당 지표 5개, 동시 2행). 기준선 3회 반복 포함 5회차 |
| 비용 | Groq와 Cohere 모두 종량제 기준 수십 원 수준(Groq Qwen 27B 입력 백만 토큰당 약 $0.3, 출력 약 $0.6, 호출당 수천 토큰) |

### 7.2 버전 비교표(1회차)

| 버전 | 하 Hit@k | 빠 Recall@k | 빨 MRR | 앞 nDCG@k | 위 Precision | 정 Recall | 출 Faithfulness | 관 Relevancy | 답 Factual |
|---|---|---|---|---|---|---|---|---|---|
| v01 top_k=3 | 1.00 (▲ +0.125) | 0.96 (▲ +0.083) | 1.00 (▲ +0.125) | 0.90 (▲ +0.105) | 0.85 (변화 없음) | 1.00 (변화 없음) | 0.69 (▼ -0.312) | 0.69 (▼ -0.024) | 0.38 (▼ -0.103) |
| v02 top_k=5 ★ | 0.88 | 0.88 | 0.88 | 0.80 | 0.86 | 1.00 | 1.00 | 0.71 | 0.48 |
| v03 top_k=10 | 1.00 (▲ +0.125) | 1.00 (▲ +0.125) | 1.00 (▲ +0.125) | 0.92 (▲ +0.117) | 0.85 (변화 없음) | 1.00 (변화 없음) | 0.90 (▼ -0.104) | 0.70 (변화 없음) | 0.51 (▲ +0.029) |

답 없는 문항(Q20, Q21)은 3버전 모두 「확인 필요」 판정 2/2 맞음.

### 7.3 읽는 법(이 실행에서 배울 것)

- **기준선이 가장 낮게 나온 이유는 Top-k가 아님.** 기준선(v02)에서만 Q17이 「되묻기」로 끝나 근거 0개 → 코드 4지표 0점.  
  같은 설정으로 다시 돌리면 Q17은 보통 「답변 완료」임(개발 중 2번 실행 모두 답변 완료, 185쪽 값과 같음).  
  검색기의 질문 변환 LLM(temperature 0.2)이 실행마다 다른 기법을 고르기 때문임. v01, v03의 코드 지표 ▲ +0.125는 정확히  
  **한 문항(1 ÷ 8)** 만큼이며 이것이 5.2에서 말한 최소 식별 변화임. 하이퍼 파라미터 효과로 읽으면 안 됨
- **코드 지표에서 실제 top_k 효과는 nDCG와 Q17에서 보임.** Q17(정답 근거 3개)은 top_k 3이면 3위 안에 근거 2개만 들어와 Recall 0.67,  
  top_k 5 이상이면 3/3. Q07처럼 관련 청크가 많은 문항(38개)은 k가 커질수록 nDCG가 내려감(0.70 → 0.58): 적중 청크가 뒤쪽에도 흩어져  
  이상적 순서(IDCG)와 멀어짐
- **흔들림 폭 실측 0.000**: 기준선을 3번 채점해 LLM 5지표 평균이 모두 같았음. 평가자를 temperature 0.01로 부르므로 같은 입력에는  
  같은 판정을 냄. 따라서 LLM 지표의 흔들림은 평가자가 아니라 **검색기 쪽**(답변 문장이 실행마다 달라짐)에서 옴.  
  코드는 실측 폭이 0이면 0.01을 「변화 없음」 기준으로 씀
- **Faithfulness ▼는 답변 문장 꼴 때문일 수 있음.** v01의 Q01, Q17이 0.00인데 평가자 판정 이유를 열어 보면 같은 뜻이라도  
  「~해야 합니다」(1)와 「~하지 않으셔야 합니다」(0)처럼 문장 꼴에 따라 갈림. 원인 후보 「답변 프롬프트를 고침」은 맞는 방향임

### 7.4 평가자(Groq Qwen 3.8 27B) 판정의 한계(실측)

| 문항, 지표 | 값 | 평가자 판정 이유(원문 요약) | 해석 |
|---|---|---|---|
| Q02 답 FactualCorrectness | 0.00(3버전 모두) | 답변 주장 「**할부 거래의** 철회는 … 7일 이내」가 모범 답안(「상품을 받은 날 … 7일 이내」)에 「할부」가 없어 틀림(정밀도 0) → F1 0 | 「할부」는 질문에 있던 말임. 주장이 1개뿐이라 단어 하나로 0점이 됨. 교재 183쪽 「Faithfulness와 함께 봄」대로 Faithfulness 1.00과 같이 읽음 |
| Q14 위 ContextPrecision | 0.00(3버전 모두) | 질문이 두 상담(첫 상담, 최근 상담)을 묻는데 청크 하나는 상담 한 건이라 「모범 답안 전체를 뒷받침하지 못함」으로 청크마다 0 | 여러 근거를 합쳐야 답이 되는 문항은 이 평가자가 청크 단위 관련을 0으로 매김. 코드 평가(nDCG 1.00)와 ContextRecall 1.00이 검색이 맞았음을 보여 줌 |
| Q17 출 Faithfulness | 0.00 ~ 1.00 | 「M-3001 회원」을 남기면 「근거에 회원번호가 없음」, 인용 표시를 남기면 「코드 D3-0019는 근거에 없음」으로 0 | 5.3의 정리 규칙으로 해결. 정리한 뒤에도 문장 꼴에 따라 갈림(7.3) |

평가자 LLM을 바꾸면 이 표도 달라짐. 교재 184 ~ 185쪽(Claude Haiku 5.5)과 값을 직접 비교하지 않는 이유임.

### 7.5 2회차 실행(검색기 흔들림 확인)

같은 명령을 한 번 더 돌림(733초). 결과 파일 `results/top_k/evaluate_2610311741_v01.md` ~ `_v03.md`.

| 버전 | 하 Hit@k | 빠 Recall@k | 빨 MRR | 앞 nDCG@k | 위 Precision | 정 Recall | 출 Faithfulness | 관 Relevancy | 답 Factual |
|---|---|---|---|---|---|---|---|---|---|
| v01 top_k=3 | 1.00 (변화 없음) | 0.96 (▼ -0.042) | 1.00 (변화 없음) | 0.91 (변화 없음) | 0.87 (변화 없음) | 1.00 (변화 없음) | 0.94 (▲ +0.146) | 0.73 (▲ +0.021) | 0.44 (변화 없음) |
| v02 top_k=5 ★ | 1.00 | 1.00 | 1.00 | 0.92 | 0.87 | 1.00 | 0.79 | 0.71 | 0.44 |
| v03 top_k=10 | 1.00 (변화 없음) | 1.00 (변화 없음) | 1.00 (변화 없음) | 0.92 (변화 없음) | 0.85 (▼ -0.024) | 1.00 (변화 없음) | 0.75 (변화 없음) | 0.69 (▼ -0.026) | 0.61 (▲ +0.172) |

- 2회차는 기준선의 Q17이 「답변 완료」로 끝나 코드 지표가 1회차보다 높고(Hit 1.00, nDCG 0.92), top_k 3에서만 Q17의 정답 근거 1개를  
  놓쳐 Recall ▼ -0.042(= 1/3 ÷ 8). **코드 지표에서 보이는 top_k 효과는 이것뿐이며, 1회차의 ▲ +0.125는 검색기 흔들림이었음**
- 흔들림 폭 실측: Faithfulness 0.125, AnswerRelevancy 0.001, 나머지 0.000. 1회차(모두 0.000)와 달리 Faithfulness가 한 문항에서  
  3회 중 1회 다르게 판정됨(temperature 0.01이어도 완전히 같지는 않음). 그래서 2회차의 Faithfulness ▲ +0.146은 폭 0.125를 겨우 넘김
- LLM 지표의 ▲, ▼는 두 회차에서 방향이 다름(1회차 v01 Faithfulness ▼ -0.312, 2회차 ▲ +0.146). 답변 LLM이 실행마다 다른 문장을  
  쓰기 때문이며, 평가셋 10문항으로는 top_k가 생성 지표에 미치는 효과를 가릴 수 없음. 교재 177쪽 「그 폭보다 큰 차이만 개선」을  
  적용하려면 **검색기 실행까지 포함해 여러 번 돌린 폭**을 써야 함(이 예제의 `--repeat`는 채점만 반복함)
- 수업에서는 1회차와 2회차 결과 파일을 나란히 열어 「같은 설정인데 왜 다른가」를 먼저 묻고, 그다음 top_k 효과(Q17 Recall, Q07 nDCG)를 찾게 함

## 8. 용어 풀이

| 용어 | 뜻 |
|---|---|
| 하이퍼 파라미터 | 사람이 정해서 바꿀 수 있는 설정값(Top-k, 청크 크기, 모델 등). 학습으로 정해지는 모델 가중치(파라미터)와 구분 |
| 버전 | 하이퍼 파라미터 값 한 묶음. 이 예제는 하나만 바꾸고 나머지를 고정함 |
| 기준선(★) | 비교의 잣대가 되는 버전. 검색기의 현재 값 |
| 평가셋 | 질문, 모범 답안, 정답 근거를 담은 문항 모음(`eval-set.json`) |
| 모범 답안(reference) | 평가셋에 사람이 미리 정해 둔 답(`ground_truth`) |
| 정답 근거 | 질문마다 꼭 찾아야 할 근거. 원본 문서, 위치, 정답 단서로 구성(`relevance`의 원소) |
| 정답 단서(clues) | 정답 근거가 되는 원문 문장. 코드 평가가 청크 본문과 글자로 대조함 |
| 적중 청크 | 검색 결과 중 정답 단서를 하나라도 담은 청크 |
| 관련 청크 | 색인된 전체 청크 중 정답 단서를 하나라도 담은 청크. nDCG의 이상적 순서(IDCG)를 계산할 때 씀 |
| 결과 정보 | 문항 1건을 실행한 결과 4칸: 질문(user_input), 모범 답안(reference), 검색 결과(retrieved_contexts), 답변(response) |
| 매크로 평균 | 문항마다 점수를 먼저 내고 그 평균을 냄. 정답 근거가 많은 문항에 무게가 쏠리지 않음 |
| 순위 가중치 | 1 ÷ log₂(순위 + 1). 1위 1.00, 2위 0.63, 3위 0.50, 4위 0.43, 5위 0.39 |
| DCG, IDCG | 적중 칸의 순위 가중치 합, 관련 청크를 1위부터 채웠을 때의 합. nDCG = DCG ÷ IDCG |
| 평가자 LLM | 채점하는 LLM(Groq `qwen/qwen3.8-27b`). 답변을 만드는 LLM과 다른 모델 |
| 코사인 유사도 | 두 벡터의 방향이 얼마나 비슷한지(1에 가까울수록 비슷). AnswerRelevancy가 역질문과 원래 질문을 비교할 때 씀 |
| 흔들림 폭 | 같은 입력을 다시 채점만 해도 생기는 점수 차이. 이보다 작은 차이는 「변화 없음」 |
| 비동기(`async`, `await`) | 평가자 호출처럼 기다리는 일을 여러 개 겹쳐 돌리는 방식. `await`는 「끝날 때까지 기다림」 |
| 데코레이터(`@experiment`) | 함수 위에 붙여 기능을 덧입히는 문법. ragas가 행마다 함수를 돌리고 표로 모으는 `arun`을 붙여 줌 |
| `None`과 `nan` | `None` = 계산하지 않음(답 없는 문항), `nan` = 계산 실패(채점 실패). 둘 다 평균에서 뺌 |
| 429 | API 호출 제한에 걸렸다는 응답. 조별로 한 대만 실행하고 1 ~ 2분 뒤 다시 함 |

「관련」의 두 뜻: 코드 평가의 **관련 청크**는 정답 단서를 담았는지 글자로 판정하고, LLM 평가 ContextPrecision의 **관련 1 / 무관 0**은  
평가자가 뜻으로 판정함. 교재 184쪽 Q17의 3위 청크(즐겨찾기 거절)는 코드로는 적중이 아니지만 LLM은 관련 있다고 봄.

## 9. 교재와 다른 점

| 항목 | 교재 | 이 예제 |
|---|---|---|
| 평가자 모델 | 184쪽 실제 예는 Claude Haiku 5.5 | Groq `qwen/qwen3.8-27b`, Cohere `embed-v5.0-fast`(OpenAI 호환 주소). 평가자가 다르면 점수도 달라 184쪽 값과 직접 비교하지 않음 |
| 판정 이유(reason) | 176, 188쪽 「점수 + 판정 이유」 | ragas 0.4.3 collections 지표는 reason을 채우지 않음(실측). 점수만 씀 |
| 결과 저장 | 178쪽 `experiments/top_k/A.csv` | 마크다운 결과 파일. ragas Dataset은 메모리(inmemory)에만 둠 |
| 비교표 | 178쪽 pandas `groupby` | 순수 파이썬(`summarize_versions`) |
| nDCG의 IDCG | 180쪽 본문(관련 청크 기준)과 노트(정답 근거 기준)가 다름 | 관련 청크 기준(181쪽 본문, 185쪽 0.97과 같음) |
| 답 없는 문항 | 181쪽 「Q18 ~ Q22」(전체 평가셋) | 실습 평가셋 10문항에서는 Q20, Q21 |
