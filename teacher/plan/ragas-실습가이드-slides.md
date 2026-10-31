# RAGAS 평가 실습 가이드 슬라이드 스크립트

- 덱 파일: `teacher/plan/ragas-실습가이드.pptx`
- 빌드: `NODE_PATH="C:\Users\hiond\.npm-global\node_modules" node teacher/plan/build/build-ragas-guide-slides.js`
- 레이아웃: 본 덱 `내용_단쪽`(references/pptx-guide.md 붙여넣기 호환 규칙 7가지)
- 원칙: 슬라이드는 핵심만 적고 상세는 「상세 보기」 링크(원격 Git 주소)로 연결함
- 상세 문서 기준 주소: https://github.com/unicorn-campus/hybrid-ai/blob/main/

<!-- 간지: RAGAS 평가 실습 -->

## 슬라이드 1. 실습 개요
- 제목: RAGAS 평가 실습: 무엇을 만들고 어떻게 진행하나
- 리드문: 설정 하나만 바꾼 버전들을 같은 평가셋과 지표로 채점해 기준선과 비교하고 원인을 찾음
- 좌 배지: 만드는 것(교재 177쪽 버전 비교 평가)
- 흐름 단계
  - ① 버전 만들기: 값 목록(top_k 3, 5, 10)을 버전 v01, v02, v03으로 만들고 기준선에 ★
  - ② 검색기 실행: 버전마다 문항마다 강사 검색기를 돌려 결과 정보 4칸을 만듦
  - ③ 코드 평가: 정답 단서를 글자로 대조해 Hit, Recall, MRR, nDCG 계산(LLM 없음)
  - ④ LLM 평가: 평가자 LLM이 위, 정, 출, 관, 답 5지표를 채점(ragas 0.4.3)
  - ⑤ 버전 비교: 버전별 평균과 기준선 대비 ▲, ▼, 변화 없음, 원인 후보
- 우상 배지: 수업 흐름(3교시)
- 표 열 너비: [1.0, 3.75, 2.3]

| 교시 | 내용 | 실습 함수 |
|---|---|---|
| 1 이론 | 교재 176 ~ 193쪽, 결과 읽기 | - |
| 2 | ① ② ③ 버전, 결과 정보, 코드 평가 | 5개(직접 3, 빈칸 2) |
| 3 | ⑤ 비교, ④ LLM 평가 | 4개(직접 1, 빈칸 3) |

- 우하 배지: 실습 방식
- 우하 카드
  - 9개 함수(직접 4, 빈칸 5)를 my_eval.py에 채움
  - 안 채운 함수는 강사 코드가 대신 돌아 늘 끝까지 완주
  - 검색기는 언제나 강사 코드(--mine은 평가 함수만 바꿈)
- 콜아웃: 한 번에 하나만 바꿔 같은 평가셋과 지표로 기준선과 비교함(교재 177쪽)
- 화면 출처: 『신한카드 하이브리드AI_W01 ~ W04』 176 ~ 193쪽, teacher/plan/ragas-개발계획서.md 1장, 4장
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/teacher/plan/ragas-실습가이드.md
- 발표자 노트
  - 평가 단위는 버전임. 버전은 하이퍼 파라미터 값 한 묶음이고, 한 번에 하나만 바꾸고 나머지는 기준선 값으로 고정함
  - 화면에는 ① ~ ⑤ 순서로 나오지만 교시 3에서는 ⑤ 비교를 ④ LLM 평가보다 먼저 실습함. 코드 지표만으로 비교표가 나오기 때문임
  - 레이어드 구조 없이 main 1개(evaluate_rag.py)와 핵심 모듈 1개(core_eval.py)로 짬. 교육생은 핵심 모듈의 함수 9개를 클론 코딩함
  - 한계도 함께 말함: 답 있는 8문항 중 6문항이 정답 근거 1개라 한 문항이 바뀌면 평균이 0.125 움직임. 이보다 작은 차이는 의미를 두지 않음

## 슬라이드 2. 사전 준비와 수업용 명령
- 제목: 사전 준비 4가지와 수업에서 쓰는 명령 2개
- 리드문: 이 폴더 전용 가상환경을 쓰고, 시작 검사가 색인, 키, 정답 단서를 확인해 빠진 것을 알려 줌
- 좌 배지: 사전 준비(수업 전)
- 준비 항목
  - 인덱싱 실습 완료(chroma, bm25 폴더). 없으면 강사 배포본 복사
  - 저장소를 통째로 clone(secrets, eval-set.json 상대 경로)
  - ragas 폴더의 .venv 활성화(rag/.venv가 아님, README 3장)
  - secrets/.env에 키 2줄: GROQ, COHERE(평가자도 Groq)
- 우 배지: 수업용 명령 2개(활성화 뒤 ragas 폴더에서)
- 명령 카드
  - python evaluate_rag.py --selftest
  - API 없이 교재 181쪽 예로 계산 함수를 점검함. 끝에 「맞음 12/12」를 봄
  - python evaluate_rag.py --param top_k --values 3 5 10 --until code --qid Q01 Q17 Q20
  - 버전 3개를 문항 3개로 돌려 코드 4지표와 비교표를 봄(LLM 평가는 건너뜀)
- 표 열 너비: [1.9, 3.3, 4.25]

| 출력 줄 | 봐야 할 것 | 정상 기준 |
|---|---|---|
| ① 버전 | v01, v02 ★, v03 | 기준선은 v02(5) |
| ③ Q17 | 정답 근거 3/3 | Hit 1, Recall 1.00, MRR 1.00, nDCG 0.97 |
| Q20 | 「확인 필요」 판정 | 맞음(지표는 계산 안 함) |

- 콜아웃: PowerShell에서 활성화가 막히면 먼저 Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
- 화면 출처: hands-on/solutions/ragas/README.md 3 ~ 5장, 2026-10-31 --selftest 실행과 README 5.1장 Q17 값
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/README.md
- 발표자 노트
  - ragas 0.4.3은 langchain-community 0.3 계열을 요구하고 RAG 실습은 0.4 계열을 써서 가상환경을 따로 둠. rag/.venv로 실행하면 import가 깨짐
  - 사전 준비가 끝났는지는 python evaluate_rag.py --param top_k --values 5 --until run --qid Q01 한 번으로 확인함. 시작 검사가 빠진 것과 할 일을 출력함
  - 키는 dotenv_values()로 읽어 클라이언트에 인자로만 넘김. 화면과 결과 파일에 찍지 않음
  - 가상환경 활성화는 터미널 창마다 한 번 함. Git Bash는 source .venv/Scripts/activate, macOS와 Linux는 source .venv/bin/activate
  - 전체 실행(10문항 × 3버전)은 시간이 길고 호출 제한(429)에 걸리기 쉬워 조별 1대만 함. 실측값은 README 7장

## 슬라이드 3. 결과 화면 읽기
- 제목: 교시 1: 결과 읽기, 점수보다 기준선 대비 변화를 봄
- 리드문: 고정 합격선 대신 기준선보다 얼마나 달라졌나를 보고, 떨어진 지표 조합으로 고칠 곳을 고름
- 표 열 너비: [1.7, 2.9, 5.6]

| 변화 표시 | 뜻 | 정해지는 방식 |
|---|---|---|
| ▲ | 기준선보다 나아짐 | 평균 차이가 흔들림 폭보다 큼 |
| ▼ | 기준선보다 나빠짐 | 평균 차이가 흔들림 폭의 음수보다 작음 |
| 변화 없음 | 차이가 흔들림 폭 안 | 초깃값 0.03(--repeat 3이면 LLM 지표는 실측) |
| - | 기준선 자신 | 자기 자신과는 비교하지 않음 |
| 비교 불가 | 평균을 낼 점수가 없음 | 모두 None(계산 안 함) 또는 nan(채점 실패) |

- 우상 배지: 결과 파일 읽는 순서
- 우상 카드
  - 요약에서 기준선 대비 ▲, ▼ 찾기
  - 원인 후보 문장 읽기(교재 187쪽 표)
  - 0점 문항은 문항별 표와 상세로 내려감
- 우하 배지: 조심할 점
- 우하 카드
  - 평균 차이 0.125 미만은 의미를 두지 않음
  - top_k가 크면 Hit, Recall이 기계적으로 오름
  - 통계적 유의성은 주장하지 않음
- 콜아웃: 0.8점 같은 고정 합격선보다 기준선 대비 변화로 채택 여부를 정함(교재 187쪽)
- 화면 출처: hands-on/solutions/ragas/README.md 5장, core_eval.py summarize_versions, 교재 177, 187쪽
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/README.md
- 발표자 노트
  - 결과 파일은 results/top_k/evaluate_{YYMMDDHHMM}_{vNN}.md이고 버전마다 1개임. 파일마다 같은 비교표가 있어 하나만 열어도 비교됨
  - 평균은 문항마다 점수를 먼저 내고 그 평균을 냄(매크로 평균). None과 nan은 평균에서 뺌. 평균만 보면 0점 문항이 가려지므로 문항별 표를 함께 봄
  - 한 문항이 바뀌면 Recall 평균이 1 ÷ 8 = 0.125 움직임. 그래서 최소 식별 변화를 0.125로 안내함
  - 강사 화면으로 결과 파일을 읽는 시연이 10분임. 전체 실행의 실측값은 README 7장에 정리됨

## 슬라이드 4. 교시 2 실습 함수
- 제목: 교시 2: ① 버전, ② 결과 정보, ③ 코드 평가(실습 함수 5개)
- 리드문: 버전 만들기와 적중 판정, 지표 계산은 직접 쓰고, 결과 정보 칸 채우기와 nDCG는 빈칸을 채움
- 표 열 너비: [1.2, 2.4, 0.9, 4.9, 0.8]

| 단계 | 함수 | 방식 | 채울 것(실습 개념) | 줄 수 |
|---|---|---|---|---|
| ① | build_versions | 직접 | 값 목록을 버전 v01, v02로, 기준선 표시. 기준선이 목록에 없으면 오류 | 21 |
| ② | make_result_row | 빈칸 2 | 검색 결과 본문 목록과 결과 정보 4칸(질문, 모범 답안, 검색 결과, 답변) | 19 |
| ③ 적중 | find_hits | 직접 | 단서를 글자 대조해 적중 순위와 찾은 정답 근거(한 번만 셈) | 21 |
| ③ 지표 | retrieval_metrics | 직접 | Hit(하나라도 1), Recall(찾은 근거 ÷ 전체), MRR(1 ÷ 첫 적중 순위) | 17 |
| ③ nDCG | ndcg_at_k | 빈칸 2 | DCG와 IDCG에 순위 가중치를 더함. nDCG = DCG ÷ IDCG | 11 |

- 우상 배지: 교시 끝에 확인할 출력
- 우상 카드
  - --selftest: 맞음 12/12
  - 버전 v01=3, v02=5 ★, v03=10
  - Q17 기준선: 3/3, nDCG 0.97
- 우하 배지: 보는 포인트
- 우하 카드
  - 한 번에 하나만 바꿈. 기준선도 함께 돌림
  - 같은 정답 근거는 한 번만 셈
  - Recall은 청크 수가 아니라 정답 근거 수
- 콜아웃: 코드 4지표는 LLM 없이 글자 대조로 계산해 같은 입력이면 같은 값(교재 180쪽)
- 화면 출처: hands-on/solutions/ragas/core_eval.py, README.md 6장, 교재 177, 180, 181, 188쪽
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/core_eval.py
- 발표자 노트
  - 줄 수는 정답 코드 전체의 줄 수(주석과 빈 줄 제외). 직접 작성 함수는 이만큼 쓰고, 빈칸 함수는 빈칸 몇 줄만 채움
  - build_versions는 같은 값을 한 번만 버전으로 만들고, 기준선이 값 목록에 없으면 ValueError를 냄. 기준선을 돌려야 비교할 잣대가 생기기 때문임
  - make_result_row의 질문은 main이 회원번호를 지운 것이고 답변은 인용 표시를 뺀 것임. 평가자가 이를 근거에 없는 주장으로 세어 Faithfulness가 0이 되는 일을 막음(README 5.3장)
  - find_hits는 compact_text로 공백을 모두 지우고 대조함. 4위 청크의 정답 근거 ①을 두 번 세면 Recall이 1.00으로 틀려지고 --selftest가 잡아 줌

## 슬라이드 5. 교시 3 실습 함수
- 제목: 교시 3: ⑤ 버전 비교와 ④ LLM 평가(실습 함수 4개)
- 리드문: 비교 함수는 직접 쓰고, 원인 고르기와 ragas 지표 만들기와 채점은 빈칸을 채움
- 표 열 너비: [1.2, 2.4, 0.9, 4.9, 0.8]

| 단계 | 함수 | 방식 | 채울 것(실습 개념) | 줄 수 |
|---|---|---|---|---|
| ⑤ 비교 | summarize_versions | 직접 | 문항 점수의 평균, 기준선 대비 차이, ▲ ▼ 판정 | 31 |
| ⑤ 원인 | diagnose | 빈칸 3 | 떨어진(▼) 지표 조합으로 고칠 곳 후보(교재 187쪽 표) | 23 |
| ④ 지표 | build_metrics | 빈칸 2 | ContextPrecisionWithReference, AnswerRelevancy(llm, embeddings) | 8 |
| ④ 채점 | score_row | 빈칸 5 | 지표마다 읽는 칸이 다름. await로 차례로 채점 | 28 |

- 우상 배지: 교시 끝에 확인할 출력
- 우상 카드
  - --selftest: 맞음 12/12
  - 비교표: 기준선 행은 「-」
  - Q17: 5지표 점수 5개
- 우하 배지: 보는 포인트
- 우하 카드
  - 지표 하나만 보면 놓침: 검색과 답변 지표를 함께 봄
  - 지표마다 읽는 칸이 다름(위, 정, 출, 관, 답)
  - 칸 이름이 틀리면 TypeError, 「채점 실패」
- 콜아웃: LLM 점수는 흔들리므로 흔들림 폭보다 큰 차이만 개선으로 봄(교재 177쪽)
- 화면 출처: hands-on/solutions/ragas/core_eval.py, README.md 6장, 교재 177, 187, 188, 201 ~ 204쪽
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/core_eval.py
- 발표자 노트
  - 줄 수는 정답 코드 전체의 줄 수(주석과 빈 줄 제외)임
  - ④ 읽기 구간 5분 해설: main의 @experiment 실험 함수가 행마다 score_row를 부르고 arun이 문항 × 지표 표로 모음. 동시에 2행만 채점해 429를 피함
  - AnswerRelevancy만 임베딩(Cohere embed-v5.0-fast)을 함께 씀. 평가자 LLM은 Groq qwen/qwen3.8-27b로 답변 LLM과 다른 모델이라 자기 채점이 아님
  - score_row 안의 예외는 Traceback이 아니라 Warning: Task failed with error 한 줄로 나오고 그 행이 채점 실패로 남음
  - 교시 3이 넘치면 diagnose를 숙제로 돌림. 다른 함수와 독립임

## 슬라이드 6. 교체 방법과 완료 기준
- 제목: 본인 코드로 바꿔 끼우기: --mine 옵션과 USE_TEACHER_CODE 목록
- 리드문: 안 채운 함수는 강사 코드가 대신 돌므로 한 함수씩 채우며 끝까지 돌려 볼 수 있음
- 좌 배지: 교체 절차
- 절차
  - 명령에 --mine을 붙여 실행. my_eval.py가 없으면 템플릿을 복사해 만듦
  - my_eval.py 맨 아래 USE_TEACHER_CODE 목록에서 채울 함수 이름을 지움
  - 그 함수를 채우고(raise 줄은 지움) 확인 명령으로 실행함
  - 정상 기준(--selftest 맞음, Q17 값)을 강사 결과와 비교함
  - 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감
- 우상 배지: 완료 기준
- 완료 카드
  - --mine --selftest가 「맞음 12/12」
  - Q17 기준선: Hit 1, Recall 1.00, MRR 1.00, nDCG 0.97
  - Q20 「확인 필요」 판정 맞음, Q17의 LLM 5지표 점수
  - 제출: my_eval.py와 실행 화면 캡처
- 우하 배지: 막혔을 때
- 막힘 카드
  - NotImplementedError 빈칸 N: 아직 안 채움 또는 raise 줄을 안 지움
  - 429(호출 제한): 1 ~ 2분 뒤 다시, --qid와 --until로 줄임
  - 강사와 LLM 점수가 다름: 정상(코드 4지표는 같아야 함)
- 콜아웃: 본인 함수의 예외는 Traceback 맨 아래 줄에 보임(score_row만 경고 한 줄)
- 화면 출처: hands-on/solutions/ragas/my_eval.template.py, README.md 4장과 6장
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/my_eval.template.py
- 발표자 노트
  - 앞선 실습들과 같은 뜻의 --mine임(이 프로그램의 실습 함수를 내 코드로). 이번에는 import 줄을 고치지 않고 옵션만 붙임. 처음 한 번 my_eval.template.py를 my_eval.py로 복사하고 my_eval.py는 Git이 무시해 pull 충돌이 없음
  - 시작 화면의 [실습 함수] my_eval이 내 파일로 돌고 있다는 표시임. 검색기는 언제나 core_search(강사 코드)임
  - 실습 중에는 함수 하나를 고칠 때마다 --qid와 --until로 줄여 API 호출을 아낌. 전체 실행(10문항 × 3버전)은 조별 1대만 함
  - 예외 하나 주의: score_row 안의 예외만 Traceback이 아니라 경고 한 줄로 나오고 그 행이 채점 실패로 표시됨
