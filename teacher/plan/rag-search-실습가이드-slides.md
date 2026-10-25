# RAG 검색 실습 가이드 슬라이드 스크립트

- 덱 파일: `teacher/plan/rag-search-실습가이드.pptx`
- 빌드: `NODE_PATH="C:\Users\hiond\.npm-global\node_modules" node teacher/plan/build/build-rag-search-guide-slides.js`
- 레이아웃: 본 덱 `내용_단쪽`(references/pptx-guide.md 붙여넣기 호환 규칙 7가지)
- 원칙: 슬라이드는 핵심만 적고 상세는 「상세 보기」 링크(원격 Git 주소)로 연결함
- 상세 문서 기준 주소: https://github.com/unicorn-campus/hybrid-ai/blob/main/

<!-- 간지: RAG 검색 실습 -->

## 슬라이드 1. 실습 개요
- 제목: RAG 검색 실습: 무엇을 만들고 어떻게 진행하나
- 리드문: 인덱싱 실습이 만든 색인을 읽어 교재 150쪽 워크플로우 6단계를 돌리고, LLM은 제안만 하고 결정은 코드 규칙이 맡음
- 좌 배지: 만드는 것(교재 150쪽 워크플로우)
- 흐름 단계
  - ① 권한 필터: 역할과 회원으로 볼 수 있는 청크만 남김(벡터는 Chroma 필터, BM25는 마스크)
  - ② Adaptive 분류: LLM이 유형을 제안하고 코드 규칙이 잡담, 단순, 복합으로 확정함
  - ③ 검색: 벡터 + BM25를 6 : 4로 융합한 뒤 Cohere 리랭크로 근거 5개를 고름
  - ④ CRAG 채점: 신호로 정확, 불확실, 부정확을 판정, 불확실이면 질문 변환 후 재검색
  - ⑤ 답변 생성: 근거만으로 문장마다 청크ID와 인용문을 달아 씀(Groq)
  - ⑥ Self-RAG 검증: 인용문을 근거 본문과 글자 대조, 실패면 ⑤ 재작성 최대 2회
- 우상 배지: 수업 흐름(4교시)
- 표 열 너비: [1.0, 3.75, 2.3]

| 교시 | 내용 | 실습 함수 |
|---|---|---|
| 1 이론 | 교재 144 ~ 174쪽 | - |
| 2 | ① ② ③ 벡터 | 3개(빈칸 3) |
| 3 | ③ BM25, 융합, 리랭크 | 3개(직접 2, 빈칸 1) |
| 4 | ④ ⑤ ⑥ | 4개(직접 2, 빈칸 2) |

- 우하 배지: 실습 방식
- 우하 카드
  - 10개 함수(직접 4, 빈칸 6)를 my_search.py에 채움
  - 안 채운 함수는 강사 코드가 대신 돌아 늘 끝까지 완주
  - 한 함수를 고칠 때마다 질문 한두 개만 실행
- 콜아웃: LLM은 제안만 하고, 받아들일지는 코드 규칙이 정함. 채점과 검증은 LLM 없이 규칙으로만 함(교재 152쪽)
- 화면 출처: 『신한카드 하이브리드AI_W01 ~ W04』 144 ~ 174쪽, teacher/plan/rag-search-개발계획서.md 4장
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/teacher/plan/rag-search-실습가이드.md
- 발표자 노트
  - 교재 150쪽 고정 워크플로우 6단계가 그대로 코드가 됨. 분기는 모두 미리 그린 if이고 반복은 고정 상한임
  - 레이어드 구조 없이 main 1개(search_docs.py)와 핵심 모듈 1개(core_search.py)로 짬. 교육생은 핵심 모듈의 함수 10개를 클론 코딩함
  - 외부 API가 실패하면 대체 경로로 넘어가지만, 교육생 실습 함수의 오류는 감추지 않고 그대로 화면에 띄움

## 슬라이드 2. 사전 준비와 수업용 명령
- 제목: 사전 준비 4가지와 수업에서 쓰는 명령 2개
- 리드문: 시작 검사가 색인 폴더와 키를 확인하고 모자란 것을 알려 주며, 로컬 모델 없이 임베딩, 리랭크, LLM 모두 API로 호출함
- 좌 배지: 사전 준비(수업 전)
- 준비 항목
  - 인덱싱 실습 완료(chroma, bm25 폴더). 없으면 강사 배포본 복사
  - 저장소를 통째로 clone(secrets, eval-set.json 상대 경로)
  - 공용 가상환경 rag/.venv 준비(README 3장)
  - secrets/.env에 키 2줄: GROQ, COHERE
- 우 배지: 수업용 명령 2개(retriever 폴더에서)
- 명령 카드
  - ../.venv/Scripts/python.exe search_docs.py --qid Q01
  - 약관 질문을 ① ~ ⑥ 끝까지(약 4초). 「답변 완료」를 봄
  - ../.venv/Scripts/python.exe search_docs.py --qid Q18
  - 답 없는 질문이 지어내지 않고 되묻기 또는 「확인 필요」로 끝남(macOS는 ../.venv/bin/python)
- 표 열 너비: [1.9, 3.3, 4.25]

| 출력 줄 | 봐야 할 것 | Q01(강사 PC) |
|---|---|---|
| ① 권한 필터 | 역할, BM25 대상 청크 수 | agent, 212개(전체 260개 중) |
| ③ 리랭크 | 융합 n위 → 리랭크 m위, 점수 | D1-0007이 1위, 0.908 |
| ④ CRAG 채점 | 신호와 기준값, 판정 | 판정 정확 |
| ⑥ 검증, 종료 | 검증 결과, 종료 상태 | 검증 통과, 답변 완료 |

- 콜아웃: 같은 질문도 LLM 값은 실행마다 조금 다를 수 있음. 강사와는 대상 청크 수, 판정, 종료 상태로 비교함
- 화면 출처: hands-on/solutions/rag/retriever/README.md 3 ~ 5장, 2026-10-26 강사 PC 실측
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/rag/retriever/README.md
- 발표자 노트
  - 사전 준비가 끝났는지는 Q01 실행 한 번으로 확인함. 시작 검사가 빠진 것과 할 일을 출력함
  - 키는 dotenv_values()로 읽어 클라이언트에 인자로만 넘김. 환경변수에 올리지 않고 화면에 찍지 않음
  - Cohere 체험 키는 리랭크가 분당 10회이고 복합 질문 한 번에 리랭크가 최대 6번이라 수업 중에는 조별 1대로 실행함

## 슬라이드 3. 교시 2 실습 함수
- 제목: 교시 2: ① 권한 필터, ② 분류, ③ 벡터(실습 함수 3개)
- 리드문: 세 함수 모두 빈칸 채우기이고, 권한 필터와 분류 규칙, 벡터 검색 호출의 「무엇을 어떤 순서로 쓰나」가 개념임
- 표 열 너비: [1.2, 2.4, 0.9, 4.9, 0.8]

| 단계 | 함수 | 방식 | 채울 것(실습 개념) | 줄 수 |
|---|---|---|---|---|
| ① | build_chroma_filter | 빈칸 2 | agent는 public만($eq), auditor + 회원은 그 회원의 restricted만($and) | 15 |
| ② | apply_plan_rules | 빈칸 3 | 업무 낱말 있는 잡담은 단순, 하위 질문 앞 3개, 조건 낱말 집합 빼기 | 35 |
| ③ 벡터 | search_vector | 빈칸 2 | similarity_search_with_score(질의, k, filter), 거리를 점수로 바꿈 | 20 |

- 우상 배지: 교시 끝에 확인할 출력
- 우상 카드
  - ① Q14: BM25 대상 4개, agent는 212개
  - ② 「안녕하세요」: 잡담, 검색 0회
  - ③ Q01: 정답 청크 점수 0.45 ~ 0.6
- 우하 배지: 보는 포인트
- 우하 카드
  - 권한은 LLM이 아니라 코드가 검색 전에 정함
  - LLM은 제안만, 받아들일지는 규칙이 정함
  - 점수는 절댓값보다 순위를 봄
- 콜아웃: 권한 필터는 검색 전에 코드가 만들고, 벡터는 Chroma 필터, BM25는 0과 1 마스크로 거름(교재 151쪽)
- 화면 출처: hands-on/solutions/rag/retriever/core_search.py, README.md 5, 6장, 교재 151 ~ 160쪽
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/rag/retriever/core_search.py
- 발표자 노트
  - ①은 회원번호를 가명 ID로 바꾼 뒤(제공 member_pseudonym) 필터를 만듦. 색인에는 회원번호 없이 가명 ID만 있음
  - apply_plan_rules는 규칙 5개 중 3곳이 빈칸임. 조건 낱말과 업무 낱말 뽑기는 제공 함수(condition_terms, domain_terms)가 함
  - search_vector 한 번 호출이 질의 임베딩(Cohere 1번)과 필터를 건 근사 검색을 함께 함

## 슬라이드 4. 교시 3 실습 함수
- 제목: 교시 3: ③ BM25, 융합, 리랭크(실습 함수 3개)
- 리드문: BM25 정렬과 가중합 융합은 순수 파이썬 논리라 직접 작성이고, 리랭크 API 호출만 빈칸 채우기임
- 표 열 너비: [1.2, 2.4, 0.9, 4.9, 0.8]

| 단계 | 함수 | 방식 | 채울 것(실습 개념) | 줄 수 |
|---|---|---|---|---|
| ③ BM25 | search_bm25 | 직접 | 청크별 점수, 0점은 버림, 내림차순 정렬, 앞 top_n개를 dict로 | 20 |
| ③ 융합 | fuse_weighted | 직접 | 0 ~ 1로 정규화 뒤 벡터 0.6 + BM25 0.4, 없는 쪽은 0점 | 20 |
| ③ 리랭크 | rerank | 빈칸 2 | cohere_client.rerank(model, query, documents, top_n), index로 후보 찾기 | 25 |

- 우상 배지: 교시 끝에 확인할 출력
- 우상 카드
  - BM25: 카드명이 한 토큰(한빛모아생활)
  - 융합: 양쪽 1위면 1.0
  - 리랭크: 정답 0.7 이상, 무관 0.3 이하
- 우하 배지: 보는 포인트
- 우하 카드
  - BM25 점수는 상한이 없음(0 ~ 수십)
  - 두 점수를 0 ~ 1로 맞춘 뒤 합침
  - 리랭크는 질문과 청크를 한 쌍으로 채점
- 콜아웃: BM25 점수는 0 ~ 수십이라 그대로 더하면 BM25가 결과를 좌우함. 그래서 정규화 뒤 6 : 4로 합침(교재 161쪽)
- 화면 출처: hands-on/solutions/rag/retriever/core_search.py, README.md 5, 6장, 교재 157 ~ 166쪽
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/rag/retriever/core_search.py
- 발표자 노트
  - search_bm25는 점수 배열 순서가 chunks와 같음. weight_mask를 넘기면 권한 밖 청크는 0점이 되어 0점을 버리는 것만으로 걸러짐
  - fuse_weighted의 정규화(_normalize_scores)와 묶기(_merge_lists, _build_fused_list)는 제공 함수임. 어느 검색에서 왔는지(found_in)가 남음
  - rerank는 원 질의 기준임. 질문 변환으로 검색 문장이 바뀌어도 관련성은 원래 물음으로 잼. Cohere 리랭크 API를 1번 부름

## 슬라이드 5. 교시 4 실습 함수
- 제목: 교시 4: ④ 채점과 질문 변환, ⑤ 답변, ⑥ 검증(함수 4개)
- 리드문: 채점과 근거 검증은 직접 작성, 질문 변환 금지 규칙과 LCEL 체인은 빈칸 채우기임
- 표 열 너비: [1.2, 2.4, 0.9, 4.9, 0.8]

| 단계 | 함수 | 방식 | 채울 것(실습 개념) | 줄 수 |
|---|---|---|---|---|
| ④ 채점 | grade | 직접 | 부정확(하나라도), 정확(모두), 나머지는 불확실 | 20 |
| ④ 질문 변환 | apply_transform_rules | 빈칸 3 | 대상 섞임이면 clarify, 같은 질의 제외, HyDE와 Step-Back은 원 질의 포함 | 35 |
| ⑤ | generate_answer | 빈칸 2 | with_structured_output(GroundedAnswer), LCEL 체인으로 프롬프트와 모델 잇기 | 20 |
| ⑥ | verify_answer | 직접 | 청크ID 있음, 근거에 있음, 인용문이 본문에 글자 그대로 있음 | 25 |

- 우상 배지: 교시 끝에 확인할 출력
- 우상 카드
  - Q01: 검증 통과
  - Q18: 「확인 필요:」만 나오고 ⑥ 건너뜀
  - 불확실이면 질문 변환, 재검색 1/1
- 우하 배지: 보는 포인트
- 우하 카드
  - 같은 결과면 언제나 같은 판정
  - 금지 규칙은 LLM 답과 상관없이 적용
  - 「확인 필요」도 정상 종료
- 콜아웃: ⑥ 검증은 인용문이 본문에 글자 그대로 있는지만 봄. 인용은 맞는데 해석이 틀린 답은 못 거름(README 9장)
- 화면 출처: hands-on/solutions/rag/retriever/core_search.py, README.md 5, 6, 9장, 교재 149, 167 ~ 174쪽
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/rag/retriever/core_search.py
- 발표자 노트
  - grade는 LLM 없이 규칙만 씀. 신호 계산(build_signals)은 제공 함수임. 기준값은 상한 0.7, 하한 0.3, 격차 0.05, 겹침 1임
  - apply_transform_rules는 LLM이 고른 기법에 금지 규칙을 씌움. 교시 4가 넘치면 이 함수를 숙제로 돌림
  - verify_answer의 실패 사유는 문장 번호를 1부터 적어 ⑤ 재작성 프롬프트로 그대로 넘어감. 재작성은 최대 2회임

## 슬라이드 6. 교체 방법과 완료 기준
- 제목: 본인 코드로 바꿔 끼우기: import 한 줄과 USE_TEACHER_CODE 목록
- 리드문: 안 채운 함수는 강사 코드가 대신 돌므로 한 함수씩 채우며 전체를 끝까지 돌려 볼 수 있음
- 좌 배지: 교체 절차
- 절차
  - search_docs.py의 import 한 줄을 import my_search as core 로 바꿈
  - my_search.py 맨 아래 USE_TEACHER_CODE 목록에서 채울 함수 이름을 지움
  - 그 함수를 채우고(raise 줄은 지움) 확인 명령으로 실행함
  - 정상 기준(대상 청크 수, 판정, 종료 상태)을 강사 결과와 비교함
  - 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감
- 우상 배지: 완료 기준
- 완료 카드
  - USE_TEACHER_CODE가 빈 my_search.py로 Q01이 「답변 완료」, ⑥ 검증 통과
  - Q18이 되묻기 또는 「확인 필요」로 끝남
  - Q14의 BM25 대상 4개, --role agent는 212개
  - 제출: my_search.py와 Q01, Q18 실행 화면 캡처
- 우하 배지: 막혔을 때
- 막힘 카드
  - NotImplementedError 빈칸 N: 아직 안 채움 또는 raise 줄을 안 지움
  - 429(호출 제한): 1 ~ 2분 뒤 다시, 수정 반복은 --no-answer
  - 강사와 답 문장이 다름: 정상(판정으로 비교)
- 콜아웃: 본인 함수에서 예외가 나면 감추지 않고 Traceback을 그대로 보여 주고 그 질문만 「오류」로 끝남
- 화면 출처: hands-on/solutions/rag/retriever/my_search.py, README.md 6장과 8장
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/rag/retriever/my_search.py
- 발표자 노트
  - W3 인덱싱 실습과 같은 방식임(import 한 줄 + 함수 단위로 강사 코드 대체). 인덱싱을 my_indexing.py로 했다면 core_indexing import도 바꿈
  - 실습 중에는 함수 하나를 고칠 때마다 질문 한두 개만 돌려 API 호출을 아낌. 수정 반복에는 --no-answer를 씀
  - 제출 화면에는 ① ~ ⑥ 출력과 마지막 호출 횟수 줄이 보이게 캡처함
