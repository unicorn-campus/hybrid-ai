# RAGAS 평가 실습 가이드(교육생용)

| 항목 | 내용 |
|---|---|
| 대상 | 하이브리드 AI 교육 「품질 평가 및 튜닝 이해」. 엔지니어, 데이터 모델러, 기획자 혼합(파이썬 초보 포함) |
| 교재 | 『신한카드 하이브리드AI_W01 ~ W04』 176 ~ 193쪽, 실습 코드 장표 195 ~ 207쪽 |
| 예제 | [hands-on/solutions/ragas](https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/README.md) |
| 시간 | 이론 1교시 + 클론 코딩 2교시(교시 2, 3) = 3교시 |
| 완료 | 본인 코드(`my_eval.py`)로 `--selftest`가 12/12 맞음, Q17 기준선의 코드 4지표가 강사와 같고, Q17의 LLM 5지표 점수가 나옴 |

## 0. 이 실습에서 만드는 것

W4에서 만든 RAG 검색기를 **설정값만 다르게 여러 번 돌려서, 어느 설정이 나은지 점수로 비교하는 평가기**를 만듦.  
시험에 비유하면 같은 시험지(평가셋)와 같은 채점표(지표)로 여러 답안을 채점해 비교하는 일임.  
다만 실제로는 검색기 코드가 하나이고, 실행할 때 설정값(예: 근거를 몇 개 가져올지)만 바꿔 끼움.

설정값 중 하나(예: `top_k`)의 값 목록을 **버전**으로 만들고, 그중 하나를 **기준선(★)**으로 정해 나머지를 기준선과 비교함.  
**한 번에 하나만 바꿈**. 그래야 점수가 달라졌을 때 그 값 탓이라고 말할 수 있음(교재 177쪽).

```text
① 버전 만들기  값 목록(예: top_k 3, 5, 10) → 버전 v01, v02, v03. 기준선에 ★ 표시
② 검색기 실행  버전마다, 문항마다 검색기를 돌려 「결과 정보」 한 행(칸 4개)을 만듦
③ 코드 평가    정답 단서를 글자로 대조해 Hit, Recall, MRR, nDCG 계산(LLM 없음, 같은 입력이면 같은 값)
④ LLM 평가     평가자 LLM(Groq qwen)이 지표 5개로 채점(ragas 0.4.3). 같은 입력도 점수가 조금씩 흔들림
⑤ 버전 비교    버전별 평균, 기준선 대비 ▲ ▼ 변화 없음, 지표 조합으로 본 원인 후보
```

화면에는 ① ② ③ ④ ⑤ 순서로 나오지만, **교시 3에서는 ⑤를 먼저 실습**함. 코드 평가 지표만으로도 비교표가 나오기 때문임.  
평가 대상 검색기는 **언제나 강사 코드**(`core_search.py`)로 돎. `--mine`은 평가 함수만 내 코드로 바꿈.

두 가지 채점(교재 179쪽)

| 구분 | 지표 | 한 줄 뜻 |
|---|---|---|
| 코드 평가 4개 | 하 Hit@k | 정답 재료를 하나라도 건졌나(1 또는 0) |
| | 빠 Recall@k | 찾아야 할 정답 근거를 몇 개나 찾았나 |
| | 빨 MRR | 첫 적중 청크가 몇 위인가(1 ÷ 순위) |
| | 앞 nDCG@k | 필요한 청크가 앞쪽에 모여 있나 |
| LLM 평가 5개 | 위 ContextPrecision | 검색 결과 위쪽에 쓸모 있는 청크가 있나 |
| | 정 ContextRecall | 모범 답안의 내용이 검색 결과에 들어 있나 |
| | 출 Faithfulness | 답변이 검색 결과에 있는 말만 했나(지어내지 않았나) |
| | 관 AnswerRelevancy | 답변이 질문에 맞는가 |
| | 답 FactualCorrectness | 답변이 모범 답안과 맞는가 |

한계도 알고 시작함: 평가셋 10문항 중 답이 있는 문항은 8개이고, 그중 6개가 정답 근거 1개라 Recall이 0 또는 1임.  
한 문항이 바뀌면 평균이 0.125 움직이므로 **이보다 작은 차이는 의미를 두지 않고**, 통계적으로 유의하다고도 말하지 않음.

## 1. 사전 준비(수업 전까지)

| 번호 | 할 일 | 확인 |
|---|---|---|
| 1 | 인덱싱 실습 완료. 없으면 강사 배포 `rag/indexing/data/`를 복사(`chroma/`와 `bm25/` 둘 다) | `rag/indexing/data/bm25/manifest.json`의 `chunk_count`가 260 |
| 2 | 저장소를 통째로 clone(`secrets/`, `eval-set.json`, `rag/`를 상대 경로로 찾음) | `hands-on/solutions/eval-set.json`이 있음(10문항) |
| 3 | **이 폴더 전용** 가상환경 `ragas/.venv` 준비(`README.md` 3장대로 만들고 활성화한 뒤 패키지 설치) | 설치 확인 명령이 `ok 0.4.3` |
| 4 | `secrets/.env`에 키 2줄: `GROQ_API_KEY`, `COHERE_API_KEY`(RAG 실습과 같은 키. 평가자 LLM도 Groq) | 아래 명령이 끝까지 돎 |

`rag/.venv`를 그대로 쓰지 않는 이유: ragas 0.4.3과 RAG 실습이 서로 다른 판의 `langchain-community`를 요구해 한 환경에 두면 한쪽이 깨짐.

가상환경 활성화(`hands-on/solutions/ragas` 폴더에서, 터미널 창마다 한 번). 프롬프트 앞에 `(.venv)`가 붙으면 됨

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

설치 확인과 준비 점검 명령(활성화한 터미널에서. 처음 import는 ragas가 무거워 10초쯤 걸림)

```bash
python -c "import ragas, langchain_chroma, kiwipiepy, cohere, bm25s; print('ok', ragas.__version__)"
python evaluate_rag.py --param top_k --values 5 --until run --qid Q01
```

두 번째 명령은 검색기만 1문항 돌려 색인, 키, 정답 단서 검사를 한꺼번에 확인함. 빠진 것이 있으면 할 일을 알려 줌.  
API 호출은 Groq, Cohere, 평가자 LLM(Groq) 모두 외부 호출임. 인덱싱이 도는 동안에는 실행하지 않음(같은 Chroma 폴더를 함께 열면 결과가 흔들림).  
전체 실행(10문항 × 3버전)은 시간이 길고 호출 제한(429)에 걸리기 쉬워 **수업 중에는 조별 1대만** 함. 함수를 채울 때는 `--qid`와 `--until`로 줄여 확인함.

## 2. 수업 흐름

| 교시 | 내용(분) | 실습 함수(채우는 순서) |
|---|---|---|
| 1 이론 | 교재 176 ~ 193쪽(30), 강사 화면으로 결과 파일 읽기(10), `--mine` 교체와 `--selftest` 시연(10) | - |
| 2 | 환경 점검(5), ① ②(15), ③(30) | `build_versions`, `make_result_row`, `find_hits`, `retrieval_metrics`, `ndcg_at_k` |
| 3 | ⑤(20), `@experiment` 읽기 구간 해설(5), ④(25) | `summarize_versions`, `diagnose`, `build_metrics`, `score_row` |

방식 두 가지(모두 9개: 직접 4, 빈칸 5)

- **직접 작성**(4개): 함수 몸통이 `raise NotImplementedError("여기에 본인 코드를 작성함")` 한 줄임.  
  함수 설명(docstring)의 「순서」를 보고 씀
- **빈칸 채우기**(5개): 거의 완성된 코드 중간에 `raise NotImplementedError("빈칸 N을 채울 것")`이 있음.  
  바로 위 주석 「# 빈칸 N: ...」이 무엇을 채울지 알려 줌. 채운 뒤 그 `raise` 줄은 지움

교시 3이 넘치면 `diagnose`는 숙제로 돌려도 됨(다른 함수와 독립).

## 3. 따라하기

### Step 1. 강사 코드로 실행하고 출력 읽기(교시 1)

아래 두 명령은 `hands-on/solutions/ragas` 폴더에서 가상환경을 켠 뒤 실행함.

```bash
python evaluate_rag.py --selftest
```

API 없이 교재 181쪽 가상 예(관련 청크 4개, 정답 근거 3개, k 5)로 계산 함수를 점검함. 마지막 줄이 `맞음 12/12`이면 정상임.

```bash
python evaluate_rag.py --param top_k --values 3 5 10 --until code --qid Q01 Q17 Q20
```

`top_k`를 3, 5, 10으로 바꾼 버전 3개를 문항 3개(Q01 약관, Q17 상담, Q20 답이 없는 질문)로 돌림.  
`--until code`는 ③과 ⑤까지만 실행하고 LLM 평가는 건너뜀. 검색기만 부르므로 비교적 빠름.

| 화면 줄 | 볼 것 |
|---|---|
| `[① 버전 만들기]` | `v01 top_k = 3`, `v02 top_k = 5 ★기준선`, `v03 top_k = 10` |
| `[준비]` | 평가셋 문항 수(`--qid`로 3개를 고르면 3문항)와 「정답 단서 검사」 통과 |
| `[② 검색기 실행]` | 문항마다 종료 상태, 근거 개수와 청크ID, 걸린 시간. 마지막에 호출 합계 |
| `[③ 코드 평가]` | 문항마다 정답 근거를 몇 개 찾았는지, 순위별 적중, 4지표 |
| `[⑤ 버전 비교]` | 버전별 평균과 기준선 대비 변화, 「원인 후보」 문장 |
| `[결과 파일]` | `results/top_k/evaluate_...md` 파일 경로(버전마다 1개) |

③의 한 줄 읽는 법(Q17 기준선 `top_k=5`. 강사 화면과 같은 값이 나옴)

```text
[③ 코드 평가] v02 top_k=5 — 적중 청크와 4지표(교재 180쪽)
  Q17 관련 청크 3개, 정답 근거 3/3 | 1위 3 2위 2 3위 - 4위 1
      Hit 1  Recall 1.00  MRR 1.00  nDCG 0.97
```

- 「1위 3」은 1위 청크에 정답 근거 ③의 정답 단서가 있다는 뜻(적중 청크). 「3위 -」는 적중이 아님
- 「정답 근거 3/3」은 전체 정답 근거 3개 중 3개를 찾았다는 뜻. 같은 근거가 여러 청크에 있어도 한 번만 셈
- 답이 없는 문항(Q20, Q21)은 지표를 계산하지 않고, 「확인 필요」로 끝났는지만 맞음 또는 틀림으로 봄
- Q01의 숫자는 강사 화면과 비교함. 전체 실행 실측값은 README 7장에 정리됨

같은 문항도 LLM이 낸 값(검색기의 분류, 답 문장, ④의 평가 점수)은 실행마다 조금씩 다를 수 있음.  
**코드 4지표는 검색 결과가 같으면 언제나 같은 값**이므로, 강사와 값이 다르면 먼저 의심할 곳은 내 함수임.

### Step 2. 본인 코드로 바꿀 준비

1. `--mine`을 붙여 실행함. `my_eval.py`가 없으면 `my_eval.template.py`를 복사해 만들고 안내가 나옴

   ```bash
   python evaluate_rag.py --mine --selftest
   ```

   처음에는 `[--mine] my_eval.py 이 없어 my_eval.template.py 를 복사해 만듦`이 나오고, 이어서 `[실습 함수] my_eval`이 나오면  
   내 파일로 돌고 있다는 뜻임(강사 코드는 `[실습 함수] core_eval`). 검색기는 `core_search(강사 코드)`로 그대로임.
2. `my_eval.py` 맨 아래 `USE_TEACHER_CODE` 목록을 봄. **여기 있는 함수는 강사 코드가 대신 돎**(처음에는 9개 모두 있음)

   ```python
   USE_TEACHER_CODE = [
       "build_versions", "make_result_row", "find_hits", "retrieval_metrics", "ndcg_at_k",
       "summarize_versions", "diagnose", "build_metrics", "score_row",
   ]
   ```

3. 지금 채울 함수 이름을 목록에서 지움 → 그 함수를 채움 → 아래 표의 확인 명령으로 실행 → 결과를 비교함
4. 막히면 함수 이름을 목록에 다시 넣고 다음 함수로 넘어감. 본인 함수에서 예외가 나면 감추지 않고 그대로 보임
5. `my_eval.py`는 Git이 무시하므로, 강사가 뼈대(`my_eval.template.py`)를 고쳐 올려도 pull 충돌이 없음.  
   `my_eval.template.py`는 직접 고치지 않고 복사본 `my_eval.py`만 고침

함수 위쪽의 `compact_text`, `rank_weight`, `count_relevant_chunks`, `mean_of`, `format_delta`, `ascore_or_nan`은 **제공 함수**임.  
미리 완성돼 있으니 읽고 가져다 쓰기만 하면 됨(`my_eval.py` 위쪽 `from core_eval import` 목록에 있음).

### Step 3. 교시 2: 함수 5개(직접 3 + 빈칸 2)

| 순서 | 함수 | 단계 | 방식 | 채울 양 |
|---|---|---|---|---|
| 1 | `build_versions` | ① 버전 만들기 | 직접 | 약 20줄 |
| 2 | `make_result_row` | ② 결과 정보 | 빈칸 2곳 | 1줄, 4줄 |
| 3 | `find_hits` | ③ 적중 청크 판정 | 직접 | 약 20줄 |
| 4 | `retrieval_metrics` | ③ Hit, Recall, MRR | 직접 | 약 17줄 |
| 5 | `ndcg_at_k` | ③ nDCG | 빈칸 2곳 | 1줄씩 |

(직접 함수의 줄 수는 완성본에서 주석과 빈 줄을 뺀 값에 가깝고, 사람마다 다름)

#### 3.1 `build_versions`: 값 목록을 버전 목록으로(직접)

- **무엇을**: `param`(이름), `values`(값 목록), `baseline`(기준선 값), `supported`(지원 이름과 현재 값)를 받아  
  버전 목록을 돌려줌. 버전 하나는 `name`(v01, v02, ...), `param`, `value`, `is_baseline`(기준선이면 True) 네 칸임
- **왜**: 한 번에 하나만 바꾸고 나머지는 기준선 값으로 고정해야 점수 변화를 그 값 탓으로 볼 수 있음.  
  기준선을 돌리지 않으면 비교할 잣대가 없으므로 오류로 막음
- **순서(docstring의 「순서」를 요약)**: ① `param`이 `supported`에 없으면 `ValueError` ② `baseline`이 `None`이면 `supported[param]`을 기준선으로  
  ③ `baseline`이 `values`에 없으면 `ValueError` ④ `values`를 돌며(같은 값은 한 번만) 번호를 1부터 매겨 버전을 목록에 더함
- **알아둘 것**: `f"v{번호:02d}"`에서 `02d`는 두 자리로 맞추라는 뜻(1이면 `01`)
- **확인**: `python evaluate_rag.py --mine --selftest`의 `버전 목록` 줄이 `맞음`.  
  그리고 아래 두 명령(API 호출 없음)

```bash
python evaluate_rag.py --mine --param top_k --values 3 5 10 --until versions
python evaluate_rag.py --mine --param top_k --values 3 10 --until versions
```

첫 명령은 `v01 top_k = 3`, `v02 top_k = 5 ★기준선`, `v03 top_k = 10`이 나와야 함.  
둘째 명령은 값 목록에 기준선(5)이 없으므로 `오류: 기준선 값 5 이(가) 값 목록 [3, 10] 에 없음`이 나와야 함.

#### 3.2 `make_result_row`: 문항 하나를 결과 정보 한 행으로(빈칸 2곳)

- **무엇을**: 평가셋 문항 하나(`item`)와 검색기 결과 하나(`result`)를 모아 **결과 정보 한 행**을 만듦.  
  ragas가 읽는 칸 4개는 `user_input`(질문), `reference`(모범 답안), `retrieved_contexts`(검색 결과), `response`(답변)임(교재 188쪽)
- **왜**: 질문과 모범 답안은 평가셋이, 검색 결과와 답변은 검색기가 채움. 한 행에 모아 두어야 지표들이 필요한 칸만 골라 읽음
- **알아둘 것**: `question_for_ragas`(회원번호를 지운 질문)와 `answer_for_ragas`(인용 표시를 뺀 답변)는 main이 정리해서 넘김.  
  이유는 README 5.3장에 있음. 평가자가 회원번호와 인용 표시까지 「근거에 없는 주장」으로 세어 점수를 0으로 매기기 때문임
- **빈칸 안내(원문)**

```text
# 빈칸 1: 청크 본문(hit["text"])을 retrieved_contexts에 더함
# 빈칸 2: ragas 4칸을 row에 넣음(교재 188쪽). 질문과 모범 답안은 평가셋이, 검색 결과와 답변은 검색기가 채움
#         row["user_input"] = 회원번호를 지운 질문, row["reference"] = 모범 답안(item["ground_truth"]),
#         row["retrieved_contexts"] = 검색 결과 본문 목록, row["response"] = 인용 표시를 뺀 답변
```

- **확인**: 검색기를 1문항 돌림(Groq, Cohere 호출)

```bash
python evaluate_rag.py --mine --param top_k --values 5 --until run --qid Q17
```

`user_input`이 「회원과 상담할 때 ...」로 시작해 회원번호가 없고, `reference`는 모범 답안이며, 검색 결과가 4개, `response`에 `[D3-0019]` 같은 인용 표시가 없으면 정상임.

#### 3.3 `find_hits`: 어느 청크가 정답을 담았나(직접)

- **무엇을**: 검색 결과 청크를 1위부터 차례로 보며, 청크마다 정답 단서가 들어 있는지 글자로 대조함.  
  돌려주는 값은 `hit_ranks`(적중한 순위 목록), `found_evidence`(찾은 정답 근거 번호 집합),  
  `evidence_by_rank`(순위마다 담긴 근거 번호), `evidence_count`(전체 정답 근거 수)
- **왜**: 코드 평가 4지표가 모두 이 판정을 씀. 정답 단서를 하나라도 담은 청크가 **적중 청크**임
- **알아둘 것**: 줄바꿈과 띄어쓰기가 달라도 같은 문장을 찾도록 `compact_text`로 공백을 모두 지우고 비교함.  
  같은 정답 근거가 여러 청크에 나와도 **찾은 근거는 한 번만** 셈(집합 `set`은 같은 값을 두 번 넣어도 하나만 남음)
- **확인**: `python evaluate_rag.py --mine --selftest`의 `적중 순위` 줄이 `내 값 [2, 4], 기대값 [2, 4]`로 `맞음`

#### 3.4 `retrieval_metrics`: Hit, Recall, MRR 계산(직접)

- **무엇을**: `find_hits`가 돌려준 값과 `k`로 문항 하나의 Hit@k, Recall@k, MRR을 계산해 `{"hit", "recall", "mrr"}`로 돌려줌
- **왜**: 같은 검색 결과를 세 가지 질문으로 읽음. Hit는 답할 재료를 건졌나, Recall은 정답 근거를 빠짐없이 찾았나,  
  MRR은 첫 적중 청크를 얼마나 앞에 보여 줬나(교재 180쪽)
- **순서(docstring의 「순서」를 요약)**: ① `evidence_count`가 0이면 모두 `None`(답이 없는 문항은 분모가 0) ② 적중 순위 중 `k` 이하만 `ranks_in_k`에 모음  
  ③ Hit = `ranks_in_k`가 있으면 1, 없으면 0 ④ Recall = 찾은 정답 근거 수 ÷ 전체 정답 근거 수 ⑤ MRR = 첫 적중 순위의 역수, 없으면 0.0
- **알아둘 것**: Recall은 **청크 수가 아니라 정답 근거 수**로 셈. 4위 청크가 이미 찾은 근거 ①을 또 담았다고 한 번 더 세면 Recall이 1.00으로 틀려짐
- **확인**: `--selftest`에서 `하 Hit@5` 1, `빠 Recall@5` 0.667, `빨 MRR` 0.5, `답 없는 문항 Recall` None이 모두 `맞음`

#### 3.5 `ndcg_at_k`: 앞쪽에 모여 있나(빈칸 2곳)

- **무엇을**: nDCG@k = DCG ÷ IDCG를 계산함. DCG는 적중 청크 칸의 순위 가중치 합, IDCG는 관련 청크를 1위부터 이상적으로 채웠을 때의 합임
- **왜**: 필요한 청크가 앞쪽에 있을수록 점수가 큼. 순위 가중치는 제공 함수 `rank_weight`가 계산함(1 ÷ log₂(순위 + 1)):  
  1위 1.00, 2위 0.63, 3위 0.50, 4위 0.43, 5위 0.39
- **계산 예**(교재 181쪽): 적중 2위, 4위, 관련 청크 4개, k 5이면 (0.63 + 0.43) ÷ (1.00 + 0.63 + 0.50 + 0.43) = 0.41
- **빈칸 안내(원문)**

```text
# 빈칸 1: dcg에 그 순위의 가중치 rank_weight(rank)를 더함
# 빈칸 2: idcg에 그 순위의 가중치를 더함
```

- **확인**: `--selftest`의 `앞 nDCG@5`가 `내 값 0.4144..., 기대값 0.4144`로 `맞음`

교시 2 끝 확인(선택. 검색기를 부르므로 문항을 줄임)

```bash
python evaluate_rag.py --mine --param top_k --values 3 5 10 --until code --qid Q01 Q17 Q20
```

| 함수 | 정상 기준(이 데이터) |
|---|---|
| `find_hits`, `retrieval_metrics`, `ndcg_at_k` | `--selftest` 맞음. Q17 기준선(`v02`)은 정답 근거 3/3, Hit 1, Recall 1.00, MRR 1.00, nDCG 0.97 |
| 답이 없는 문항 | Q20이 `코드 지표 계산 안 함`이고 「확인 필요」 판정이 `맞음` |

### Step 4. 교시 3: 함수 4개(직접 1 + 빈칸 3)

| 순서 | 함수 | 단계 | 방식 | 채울 양 |
|---|---|---|---|---|
| 6 | `summarize_versions` | ⑤ 버전 비교 | 직접 | 약 30줄 |
| 7 | `diagnose` | ⑤ 원인 후보 | 빈칸 3곳 | 1줄, 1줄, 4줄 |
| 8 | `build_metrics` | ④ 지표 만들기 | 빈칸 2곳 | 1줄씩 |
| 9 | `score_row` | ④ 한 행 채점 | 빈칸 5곳 | 빈칸마다 1 ~ 4줄 |

#### 3.6 `summarize_versions`: 버전별 평균과 기준선 대비 변화(직접)

- **무엇을**: 버전마다 지표별 평균을 내고, 기준선 대비 차이(`delta`)와 변화 표시(`change`)를 돌려줌.  
  변화 표시는 `▲`(나아짐), `▼`(나빠짐), `변화 없음`, `-`(기준선 자신), `비교 불가` 중 하나임
- **왜**: 「0.8점이면 합격」 같은 고정 기준보다 **기준선보다 얼마나 달라졌나**로 채택 여부를 정함(교재 187쪽)
- **알아둘 것**: 문항마다 점수를 먼저 내고 그 평균을 냄(매크로 평균). 평균에서 `None`(계산 안 함)과 `nan`(채점 실패)을 빼는 일은  
  제공 함수 `mean_of`가 함. 차이가 흔들림 폭(`noise`, 초깃값 0.03)보다 작으면 `변화 없음`임
- **순서(docstring의 「순서」를 요약)**: ① 버전마다, 지표마다 문항 점수를 모아 `mean_of`로 평균 ② 기준선 평균을 꺼냄  
  ③ 기준선 자신이면 `delta` None, `change` `"-"` / 평균이나 기준선 평균이 None이면 `"비교 불가"` /  
  아니면 `delta` = 평균 - 기준선 평균, `delta > noise`이면 `"▲"`, `delta < -noise`이면 `"▼"`, 그 사이면 `"변화 없음"`
- **확인**: `python evaluate_rag.py --mine --selftest`에서 `v01 Recall 평균` 0.5, `v01 ContextRecall 평균(None 뺌)` 0.6,  
  `v01 Recall 변화` ▼, `기준선 변화` -가 모두 `맞음`

#### 3.7 `diagnose`: 떨어진 지표 조합으로 원인 후보 고르기(빈칸 3곳)

- **무엇을**: `summarize_versions`가 만든 한 버전의 변화(`change`)를 보고, 기준선보다 떨어진(`▼`) 지표의 조합으로 고칠 곳 후보 문장을 만듦
- **왜**: 지표 하나만 보면 놓침. 검색 지표와 답변 지표를 함께 봐야 검색, 순위, 생성 중 어디서 새는지 보임(교재 187쪽 표)
- **알아둘 것**: `change.get("이름")`은 그 지표가 없으면 `None`이라 `== "▼"` 조건이 거짓이 됨. 그래서 `--until code`처럼 LLM 평가를 안 돌려도 오류가 나지 않음
- **빈칸 안내(원문)**

```text
# 빈칸 1: change.get("context_recall")이 "▼"와 같은지(True/False)를 context_recall_dropped에 받음
# 빈칸 2: 같은 방법으로 Context Precision이 떨어졌는지를 context_precision_dropped에 받음
# 빈칸 3: Context Recall도 떨어졌으면(context_recall_dropped) 검색이 근거를 못 가져온 것,
#         아니면 검색은 됐는데 답변이 근거 일부만 담은 것(교재 185쪽 Q17). 조건에 맞는 문장 하나를 reasons에 더함
```

- **확인**: `--selftest`의 `원인 후보 수`가 `내 값 2, 기대값 2`로 `맞음`(Recall과 Context Recall이 함께 떨어진 예)

교시 3 끝 확인(1): 비교표와 원인 후보

```bash
python evaluate_rag.py --mine --param top_k --values 3 5 10 --until code --qid Q01 Q17 Q20
```

기준선 행은 변화가 `-`이고, 다른 행은 `▲`, `▼` 또는 `변화 없음`이 나옴. `원인 후보 v01: ...` 문장이 이어짐.  
이 명령은 LLM 평가를 하지 않으므로 코드 지표(Recall, nDCG)가 떨어진 경우의 원인 후보만 나옴.

#### 3.8 `build_metrics`: ragas 지표 객체 5개 만들기(빈칸 2곳)

- **무엇을**: 평가자 LLM(`llm`)과 임베딩(`embeddings`)으로 ragas 지표 객체 5개를 만들어 `{지표 이름: 지표 객체}`로 돌려줌
- **왜**: 지표마다 평가자 LLM이 하는 일이 다름(교재 188쪽). 모두 LLM이 필요하고, **AnswerRelevancy만 임베딩도 필요**함.  
  답변으로 만든 역질문과 원래 질문이 얼마나 비슷한지(코사인 유사도)를 재기 때문임
- **알아둘 것**: 지표 3개(`context_recall`, `faithfulness`, `factual_correctness`)는 이미 채워져 있음. 빈칸은 나머지 2개임
- **빈칸 안내(원문)**

```text
# 빈칸 1: metrics["context_precision"]에 위(ContextPrecision) 지표를 넣음.
#         평가셋에 모범 답안이 있으므로 모범 답안과 비교하는 WithReference 클래스를 llm=llm으로 만듦
# 빈칸 2: metrics["answer_relevancy"]에 관(AnswerRelevancy) 지표를 넣음.
#         역질문과 원래 질문을 임베딩으로 비교하므로 llm과 embeddings를 둘 다 넘김
```

- **확인**: 아래 `score_row`와 함께 실행해 확인함(지표 객체는 채점할 때 처음 쓰임)

#### 3.9 `score_row`: 한 행을 지표 5개로 채점(빈칸 5곳)

- **무엇을**: 결과 정보 한 행을 5지표로 채점해 `{지표 이름: 점수(0 ~ 1)}`와 `"errors"`(실패 사유)를 돌려줌
- **왜**: **지표마다 읽는 칸이 다름**(교재 188쪽). 맞는 칸을 맞는 이름으로 넘겨야 채점됨
- **알아둘 것**: `async def`, `await`는 평가자 LLM처럼 **기다리는 일**을 다른 행의 채점과 겹쳐 돌리려는 문법임.  
  `await ascore_or_nan(지표, "지표 이름", errors, 칸=값, ...)`를 지표마다 차례로 부름.  
  칸 이름(`user_input`, `reference` 등)은 ragas가 정한 영어 이름을 그대로 써야 함. 실패한 지표는 점수가 `nan`이 되고 사유가 `errors`에 남음  
  `score_row`는 ragas가 행마다 부르는 함수라, 안에서 난 오류는 Traceback이 아니라 `Warning: Task failed with error: ...` 한 줄로 나옴

| 지표 | 읽는 칸(빈칸 안내 그대로) |
|---|---|
| 빈칸 1 위 `context_precision` | `user_input`=질문, `reference`=모범 답안, `retrieved_contexts`=검색 결과 |
| 빈칸 2 정 `context_recall` | `user_input`=질문, `retrieved_contexts`=검색 결과, `reference`=모범 답안 |
| 빈칸 3 출 `faithfulness` | `user_input`=질문, `response`=답변, `retrieved_contexts`=검색 결과(모범 답안은 안 읽음) |
| 빈칸 4 관 `answer_relevancy` | `user_input`=질문, `response`=답변만 읽음 |
| 빈칸 5 답 `factual_correctness` | `response`=답변, `reference`=모범 답안만 읽음(검색 결과는 안 읽음) |

- **확인**: 평가자 LLM을 부름(Groq, Cohere 호출. 한 행에 20 ~ 30초쯤 걸리므로 1문항만)

```bash
python evaluate_rag.py --mine --param top_k --values 5 --qid Q17
```

LLM 5지표 점수(0 ~ 1)가 오류 없이 나오면 정상임. 칸 이름을 틀리면 `TypeError`가 나고 그 지표가 「채점 실패」로 표시됨.  
교재 184쪽 값과 직접 비교하지 않음(평가자 LLM이 다르고, 184쪽은 회원번호를 지우지 않은 질문을 씀).

교시 3 끝 확인(2): LLM 평가 포함 비교(조별 1대만. 답 있는 문항 × 3버전을 채점하므로 시간이 걸림)

```bash
python evaluate_rag.py --mine --param top_k --values 3 5 10 --qid Q01 Q17 Q20
```

Q20(답 없음)은 LLM 채점에서 빠지고 「확인 필요」 판정만 봄. 근거가 0개로 끝난 문항도 채점하지 않음(`채점 안 함: 근거 0개`).

### Step 5. 결과 파일 읽기(전체 실행 뒤, 교시 1 시연과 교시 3)

전체 실행은 조별 1대만 함. 명령은 README 4.2장에 하이퍼 파라미터별로 있음(수업용은 `top_k`).

```bash
python evaluate_rag.py --param top_k --values 3 5 10 --repeat 3
```

결과는 버전마다 `results/top_k/evaluate_{YYMMDDHHMM}_{vNN}.md` 한 개씩 생기고, 파일마다 같은 비교표가 들어 있어 하나만 열어도 비교됨.

| 읽는 순서 | 볼 것 |
|---|---|
| 1 | 요약에서 기준선 대비 ▲, ▼ |
| 2 | 원인 후보(교재 187쪽 표). 기준선 파일에는 「기준선」이라고만 나옴 |
| 3 | 0점 문항은 문항별 표와 상세로 내려가 원인을 찾음. 평균만 보면 0점 문항이 가려짐 |

- `top_k`가 커지면 Hit와 Recall은 기계적으로 오름. 위 ContextPrecision과 짝지어 읽음
- `--repeat 3`은 기준선만 세 번 채점해 지표별 흔들림 폭을 재고, 그 폭보다 작은 차이를 「변화 없음」으로 봄(교재 177쪽)
- 평균 차이가 0.125보다 작으면 의미를 두지 않음(0장 한계)
- 전체 실행의 실측값은 `README.md` 7장을 봄. 이 가이드에는 숫자를 적지 않음

## 4. 완료 기준

| 항목 | 기준 |
|---|---|
| 교체 실행 | `USE_TEACHER_CODE`가 빈 `my_eval.py`로 `python evaluate_rag.py --mine --selftest`가 `맞음 12/12` |
| 코드 평가(실데이터) | `--mine ... --until code --qid Q01 Q17 Q20`에서 Q17 기준선이 정답 근거 3/3, Hit 1, Recall 1.00, MRR 1.00, nDCG 0.97 |
| 답 없는 질문 | Q20이 계산 안 함이고 「확인 필요」 판정이 맞음 |
| 버전 비교 | 기준선 행의 변화가 `-`이고, 다른 행에 ▲, ▼ 또는 변화 없음이 나오며 원인 후보 문장이 나옴 |
| LLM 평가 | `--mine ... --qid Q17`로 5지표 점수가 오류 없이 나옴 |
| 제출 | `my_eval.py`와 위 실행 화면 캡처 |

## 5. 막혔을 때

| 증상 | 할 일 |
|---|---|
| `ModuleNotFoundError: No module named 'ragas'`, 프롬프트에 `(.venv)`가 없음 | `hands-on/solutions/ragas` 폴더에서 활성화함. `rag/.venv`가 아니라 **이 폴더의** `.venv`임 |
| `오류: ... secrets/.env 에 GROQ_API_KEY 가 없거나 비어 있음` | 저장소 루트 `secrets/.env`에 키 2줄을 넣음(강사 배포) |
| `오류: 인덱싱 결과가 없음` | 인덱싱을 전체 실행하거나 강사 배포 `rag/indexing/data/`를 복사 |
| `오류: 색인 어느 청크에도 없는 정답 단서가 있음` | 평가셋이나 색인이 어긋난 것. 직접 고치지 말고 강사에게 알림 |
| `오류: 기준선 값 5 이(가) 값 목록 ... 에 없음` | `--values`에 기준선 값(5)을 넣음. 다른 값을 기준선으로 쓰려면 `--baseline 값` |
| `error: argument --param: invalid choice: ...` | 지원하는 이름(`top_k`, `fusion`, `vector_weight`, `rerank_model`, `llm_model`)만 씀. 청크 크기는 재색인이 필요해 지원하지 않음 |
| `NotImplementedError: 빈칸 N을 채울 것` | 그 함수의 빈칸을 아직 안 채움. 채웠으면 `raise` 줄을 지웠는지 확인. 또는 이름을 `USE_TEACHER_CODE` 목록에 다시 넣음 |
| `NotImplementedError: 여기에 본인 코드를 작성함` | 직접 작성 함수를 아직 안 씀. docstring의 「순서」를 보고 씀 |
| `--selftest`에서 `틀림  라벨: 내 값 ..., 기대값 ...` | 틀린 줄의 라벨이 틀린 함수를 알려 줌. 예: `빠 Recall@5`가 1.00이면 같은 근거를 두 번 센 것 |
| `429`, `rate limit`, 채점 실패(`nan`) | 조별 한 대만 실행하고 1 ~ 2분 뒤 다시. 줄여서 `--qid`, `--until code`로 확인. 사유는 결과 파일의 채점 실패 표시에 있음 |
| `TypeError`가 「채점 실패」로 표시됨 | `score_row`의 칸 이름(`user_input` 등)이 틀린 것. 3.9장 표와 맞춰 봄 |
| 본인 함수에서 예외(Traceback) | 실습 함수의 오류는 감추지 않고 그대로 보임. 맨 아래 줄의 파일과 함수가 본인 코드임. 단 `score_row`는 아래 줄 |
| `Warning: Task failed with error: ...`, `채점 0/n행`, `채점 실패 행 전체: arun에서 행 채점 실패(경고 참고)` | `score_row` 안에서 예외가 난 것. ragas가 Traceback 대신 경고 한 줄로 알리고 그 행을 건너뜀. 경고 문구가 예외 메시지(예: `빈칸 1을 채울 것`)임 |
| 강사와 LLM 점수가 다름 | 정상임. LLM 지표는 같은 입력도 흔들림. 코드 4지표와 선택 로직은 같아야 함 |

## 6. 용어 풀이

전체 용어는 [README 8장](https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/README.md)에 있음.  
여기에는 실습에서 꼭 필요한 것만 둠.

| 용어 | 뜻 |
|---|---|
| 하이퍼 파라미터 | 사람이 정해서 바꿀 수 있는 설정값(근거 수 `top_k`, 모델 등). 학습으로 정해지는 모델 가중치와 구분함 |
| 버전, 기준선(★) | 버전은 하이퍼 파라미터 값 한 묶음. 기준선은 비교의 잣대가 되는 버전(검색기의 현재 값) |
| 평가셋 | 질문, 모범 답안, 정답 근거를 담은 문항 모음(`eval-set.json`, 10문항) |
| 모범 답안(`reference`) | 평가셋에 사람이 미리 정해 둔 답 |
| 정답 근거, 정답 단서 | 정답 근거는 질문마다 꼭 찾아야 할 근거. 정답 단서는 그 근거가 되는 원문 문장으로, 청크 본문과 글자로 대조함 |
| 적중 청크 | 검색 결과 중 정답 단서를 하나라도 담은 청크 |
| 관련 청크 | 색인된 전체 청크 중 정답 단서를 하나라도 담은 청크. nDCG의 이상적 순서(IDCG)를 셀 때 씀 |
| 결과 정보 | 문항 1건을 실행한 결과 칸 4개: 질문, 모범 답안, 검색 결과, 답변 |
| 매크로 평균 | 문항마다 점수를 먼저 내고 그 평균을 냄. 정답 근거가 많은 문항에 무게가 쏠리지 않음 |
| 순위 가중치 | 1 ÷ log₂(순위 + 1). 앞 순위일수록 큼(1위 1.00, 2위 0.63, 3위 0.50) |
| DCG, IDCG | 적중 칸의 순위 가중치 합, 관련 청크를 1위부터 채웠을 때의 합. nDCG = DCG ÷ IDCG |
| 평가자 LLM | 채점하는 LLM(Groq `qwen/qwen3.8-27b`). 답변을 만드는 LLM과 다른 모델이라 자기 답을 자기가 채점하지 않음 |
| 코사인 유사도 | 두 벡터(숫자 목록)의 방향이 얼마나 비슷한지. AnswerRelevancy가 역질문과 원래 질문을 비교할 때 씀 |
| 흔들림 폭 | 같은 입력을 다시 채점만 해도 생기는 점수 차이. 이보다 작은 차이는 「변화 없음」 |
| 비동기(`async`, `await`) | 기다리는 일을 여러 개 겹쳐 돌리는 방식. `await`는 「끝날 때까지 기다림」 |
| 데코레이터(`@experiment`) | 함수 위에 붙여 기능을 덧입히는 문법. ragas가 행마다 함수를 돌리고 표로 모아 줌(`arun`). main의 읽기 구간에 있음 |
| `None`, `nan` | `None`은 계산하지 않음(답 없는 문항), `nan`은 계산 실패(채점 실패). 둘 다 평균에서 뺌 |
| 429 | API 호출 제한에 걸렸다는 응답. 조별 한 대만 실행하고 1 ~ 2분 뒤 다시 함 |

「관련」의 두 뜻을 구분함: 코드 평가의 **관련 청크**는 정답 단서를 담았는지 글자로 판정하고,  
LLM 평가 ContextPrecision의 **관련 1 / 무관 0**은 평가자가 뜻으로 판정함.  
교재 184쪽 Q17의 3위 청크는 코드로는 적중이 아니지만 LLM은 관련 있다고 봄.

## 7. 더 해 보기(선택)

- `--repeat 3`으로 기준선을 세 번 채점해 지표별 흔들림 폭을 보고, 어떤 지표가 더 흔들리는지 비교함
- 다른 하이퍼 파라미터로 바꿔 봄(하나만 바꿈). 명령은 README 4.2장

  ```bash
  python evaluate_rag.py --param vector_weight --values 0.3 0.6 0.8
  python evaluate_rag.py --param fusion --values weighted rrf
  ```

- `--baseline`으로 기준선을 바꿔 봄(예: `--param top_k --values 5 10 20 --baseline 10`)
- 결과 파일의 문항별 표에서 0점 문항을 찾아, 검색 문제인지 답변 문제인지 지표 조합으로 설명해 봄(교재 187쪽)

## 8. 참고 링크

- 예제 README: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/README.md
- 핵심 모듈(정답): https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/core_eval.py
- 교육생 뼈대: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/my_eval.template.py
- main: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/evaluate_rag.py
- 개발계획서(강사용): https://github.com/unicorn-campus/hybrid-ai/blob/main/teacher/plan/ragas-개발계획서.md
