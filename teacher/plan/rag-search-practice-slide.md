# RAG 검색 실습 가이드 장표 스크립트(W01 ~ W04 176쪽)

- 넣을 자리: 『신한카드 하이브리드AI_W01 ~ W04』 175쪽 간지 「문서 검색 실습」 바로 뒤(176쪽). 다음 간지 「품질 평가 및 튜닝 이해」는 177쪽으로 밀림
- 덱 파일: `teacher/plan/rag-search-practice-slide.pptx`(1장)
- 빌드: `NODE_PATH="C:\Users\hiond\.npm-global\node_modules" node teacher/plan/build/build-rag-search-practice.js`
- 교재 넣기: `python teacher/plan/build/fix_ph.py teacher/plan/rag-search-practice-slide.pptx` →  
  `python teacher/plan/build/merge-rag-search-practice.py {교재}.pptx`(같은 제목 장표가 있으면 바꾸고, 없으면 간지 뒤에 넣음)
- 레이아웃: 본 덱 `내용_단쪽`. 위는 워크플로우 도식(단계 상자 6개 + 단계별 실습 함수 + 분기 메모 3개), 아래는 실습 방법(절차 카드 + 교시 표)
- 원칙: 핵심만 적고 상세는 「상세 보기」 링크(실습 가이드, 원격 Git 주소)로 연결함

## 슬라이드 1. 문서 검색 실습 가이드
- 제목: 문서 검색 실습: 검색 워크플로우 6단계를 코드로 만들기
- 리드문: 교재 150쪽 ① ~ ⑥을 search_docs.py 한 프로그램으로 돌리고, 단계마다 실습 함수를 my_search.py에 채워 바꿔 끼움
- 도식 배지: 질문 + 역할 → ① ~ ⑥ → 최종 답변 또는 「확인 필요」   |   상자 아래 = 실습 함수(굵게 = 직접 작성)
- 단계:
  - ① 권한 필터 | 검색 전에 코드가 거름 | build_chroma_filter
  - ② Adaptive 분류 | LLM 제안 + 규칙 확정 | apply_plan_rules
  - ③ 검색 | 하이브리드 + 리랭크 | search_vector, *search_bm25, *fuse_weighted, rerank
  - ④ CRAG 채점 | 신호 6개로 판정 | *grade, apply_transform_rules
  - ⑤ 답변 생성 | 근거만, 청크ID와 인용문 | generate_answer
  - ⑥ Self-RAG 검증 | 인용문을 본문과 대조 | *verify_answer
- 분기:
  - ② | 잡담이면 검색 없이 답변, 복합이면 하위 질문 2 ~ 3개로 나눠 각각 검색
  - ④ | 불확실이면 질문 변환 후 재검색(1회), 부정확이면 「확인 필요」로 끝
  - ⑥ | 인용 검증 실패면 사유를 주고 ⑤ 재작성(최대 2회)
- 좌 배지: 실습 방법(retriever 폴더에서)
- 절차:
  - 강사 코드로 ① ~ ⑥ 출력 읽기: search_docs.py --qid Q01
  - search_docs.py의 import를 my_search로 바꿈
  - USE_TEACHER_CODE에서 이름을 지우고 그 함수를 채움
  - 다시 실행해 청크 수, 판정, 종료 상태를 강사와 비교
  - 막히면 이름을 목록에 되돌림(강사 코드가 대신 돎)
- 우 배지: 교시별 실습 함수와 확인 명령
- 표 열 너비: [0.7, 4.35, 2.3]

| 교시 | 채우는 함수(순서대로) | 확인 명령 |
|---|---|---|
| 2 | build_chroma_filter, apply_plan_rules, search_vector | --qid Q14, "안녕하세요" |
| 3 | search_bm25, fuse_weighted, rerank | --qid Q07 --no-answer |
| 4 | grade, apply_transform_rules, generate_answer, verify_answer | --qid Q01, --qid Q18 |

- 화면 출처: 교재 150 ~ 174쪽, hands-on/solutions/rag/retriever(README.md, my_search.py), teacher/plan/rag-search-실습가이드.md
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/teacher/plan/rag-search-실습가이드.md
- 발표자 노트:
  - 이론 장(144 ~ 174쪽)에서 본 고정 워크플로우를 이제 코드로 만듭니다. 도식의 상자 아래 이름이 그 단계에서 교육생이 채울 함수입니다
  - 굵은 글씨 4개는 처음부터 직접 쓰고, 나머지 6개는 거의 완성된 코드의 빈칸만 채웁니다. 모두 my_search.py에 있습니다
  - 수업 흐름은 이론 1교시, 클론 코딩 3교시입니다. 교시 2는 ①, ②, ③ 벡터, 교시 3은 ③ BM25, 융합, 리랭크, 교시 4는 ④, ⑤, ⑥입니다
  - 실행은 조별 1대로 합니다. Cohere 체험 키는 리랭크가 분당 10회이고 복합 질문 한 번에 리랭크가 최대 6번 일어납니다
  - 같은 질문도 LLM 문장은 실행마다 다를 수 있습니다. 강사 결과와는 대상 청크 수, 판정, 종료 상태로 비교합니다
  - 상세 절차, 빈칸 설명, 막혔을 때 대처는 「상세 보기」의 실습 가이드에 있습니다
