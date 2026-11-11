# GraphRAG 실습 코드 KG 최소 속성 점검과 수정계획

- 작성: 클로니(Agentic AI 아키텍트), 2026-11-11
- 기준: 교재 6쪽 「지식 그래프(KG)에는 ID와 최소 속성만 넣음」(`.temp/w06-w08-slides.txt` SLIDE 6)
- 대상: `hands-on/solutions/graphrag` (indexer, retriever, schema/doc)
- 상태: 개선 1 적용, 3절은 A안(교재 수정)으로 적용(2026-11-11). 개선 2와 보류 항목은 미적용

### 적용 결과(2026-11-11)

| 항목 | 결과 |
|---|---|
| 코드 | `core_graph.py` 청크 노드에서 `text` 삭제(주석은 `text` 줄이 있던 자리), `my_graph.template.py`와 `my_graph.py` 빈칸 1 힌트 수정 |
| 다시 색인 | `--run v3 --sample --full-reindex --reuse`(v2 결과) → 세대 `gen-lab-v3-e0d2747b` 게시, LLM 추출 0건, 검증 통과 |
| 그래프 확인 | 청크 노드 10개 중 `text` 있는 것: v2 10개 → v3 0개 |
| `check_graph.py --qid Q09` | 검색 결과와 적중 판정(단서 2개 적중)이 수정 전과 같음. 엔티티 표시 순서만 다름(조회에 ORDER BY 없음) |
| `search_graph.py --qid Q09` | 원문 근거 D2-0067을 검색엔진에서 붙여 답변, 근거 검증 통과. `--eval` 전체는 돌리지 않음 |
| 교재 | 6쪽 혜택 행과 노트, 34쪽 청크 노드 설명과 노트, 41쪽 K4 코드와 ❹ 설명과 노트 수정. 백업 `.temp/backup/하이브리드AI_W06~W08.before-kgmin-20261111.pptx` |

주의: 코드 변경은 설정 지문에 들어가지 않아, 입력이 같으면 사전 검사가 「할 일 없음」으로 건너뜀. 이미 색인한 교육생은 `--full-reindex`로 다시 색인해야 반영됨

## 1. 판정 기준(교재 6쪽 질문 3가지)

| 질문 | 그렇다면 |
|---|---|
| ① 노드 탐색에 쓰나? | 그래프에 넣음 |
| ② 탐색된 노드의 제목인가? | 그래프에 넣음 |
| ③ 자주 바뀌거나 크거나 민감한가? | 빼고 ID만 넣음(값은 원래 저장소에서 ID로 가져옴) |

## 2. 점검 결과

실측 근거: 활성 세대 `gen-lab-v2-fb04dcb6`의 `kg_prepared.json`, `prepared-chunks.json`(실습 표본 청크 10개).

### 2.1 라벨별 판정

| 라벨 | 그래프에 든 속성(평균 길이) | 판정 | 조치 |
|---|---|---|---|
| **Chunk** | chunk_id, doc_id, doc_type, **text(평균 771자)** | text는 ③ 해당(크고, 상담 원문은 민감) | **text 제거(개선 1)** |
| ProductGuide | product_id, card_name | ①, ② 해당 | 유지 |
| Benefit | benefit_id, name, amount(17자), product_id | amount는 교재 표와 다름(교재: 혜택률은 벡터 DB) | **결정 필요(3절)** |
| BenefitCondition, BenefitLimit, BenefitExclusion | description(33 ~ 87자, 최대 124자) | 이름이 없는 노드라 문구 한 줄이 곧 제목(②) | 유지. 길이 점검 추가(개선 2) |
| Consultation | record_id, consult_date, topic, channel, member_pseudo_id | 교재 표의 상담 ID, 상담일, 불만 주제와 일치 | 유지 |
| Complaint, Proposal, ReconsiderCondition | cause, content, reason, condition(31 ~ 37자) | 발언 요지 한 줄이 제목(②) | 유지. 길이 점검 추가(개선 2) |
| TermsDocument, Clause, Requirement, Deadline, Handling | version, clause_no, title, description 등(3 ~ 46자) | ①, ② 해당 | 유지 |
| Community | title, summary, findings, embedding | 그래프에서 만든 값이라 「원래 자리」가 그래프 자체 | 유지 |
| __Entity__ 공통 | embedding | 교재 SLIDE 33 노트가 「따로 정할 일」로 남김 | 유지 |

### 2.2 가장 큰 문제: 청크 원문이 그래프에 사본으로 들어감

- `indexer/core_graph.py:333-340`의 K4가 청크 노드에 `"text": chunk["text"]`를 넣음  
  같은 본문이 OpenSearch 인덱스에도 들어 있음(`core_graph.py:632`)
- 검색 쪽은 그래프의 `c.text`를 **한 번도 읽지 않음**  
  근거 원문은 OpenSearch에서 읽은 `chunk_meta`를 씀(`retriever/search_graph.py:314`, `1224`, `1285`).  
  그래프에서는 `c.chunk_id`만 돌려받음(`search_graph.py:692-693`). `check_graph.py`도 엔티티 속성만 읽음
- 결과: 쓰지 않는 사본이 두 곳에 생김. 청크가 바뀌면 맞춰 둘 대상이 늘고,  
  상담 기록 청크(접근 수준 restricted)의 발언 원문이 Neo4j에도 남아 노출 범위가 넓어짐
- 교재 6쪽 표의 「상담: 발언 원문은 벡터 DB」와 정면으로 어긋남

## 3. 결정이 필요한 것: 혜택 행이 교재 표와 다름

교재 6쪽 표는 「혜택: 그래프에는 혜택 ID, 혜택명 / 혜택률, 한도, 조건 문구는 벡터 DB」라고 적음.  
실습 스키마(`schema/doc/benefit_guide/graph_schema.json`)는 혜택 크기(amount)를 혜택 노드에 넣고,  
조건, 한도, 제외를 문구 한 줄짜리 별도 노드로 둠.

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| **A안(권장)** | 코드는 그대로 두고, 교재 6쪽 혜택 행과 노트를 실습 스키마에 맞춤 | 재추출 없음. 엔티티 직접 검색(K6)과 커뮤니티 보고서(K8)가 그대로 동작 | 교재 표 1행과 노트 수정 필요 |
| B안 | 교재대로 amount를 스키마에서 뺌 | 교재 원칙과 글자 그대로 일치 | 역량 질문 B1(혜택은 얼마인가) 채우기 시험을 다시 판정해야 함(`decisions.json:671`). benefit_guide 전체 재추출(LLM 비용, 결과 흔들림) |

A안 권장 이유

- amount는 평균 17자로 작고, 상품 개정 때만 바뀌며(개정이면 새 세대로 다시 색인), 민감하지 않음 → ③에 걸리지 않음
- 조건, 한도, 제외 노드는 이름이 없어 문구 한 줄이 곧 제목임 → ② 해당. 문구를 빼면 노드가 빈 껍데기가 됨
- 답의 근거는 이미 OpenSearch 청크 원문에서만 가져옴(엔티티 속성은 탐색과 화면 표시에만 씀)

A안의 교재 수정 문구(초안)

- 표 혜택 행: 그래프 「혜택 ID, 혜택명, 혜택 크기 한 줄」 / 원래 자리 「혜택 문단 전체(벡터 DB)」
- 노트 한 문장 추가: 「조건, 한도, 제외처럼 이름이 없는 노드는 원문 한 줄을 제목으로 씀. 문단 전체는 넣지 않음」

## 4. 수정 항목

### 개선 1. 청크 노드에서 text 제거(필수)

| 파일 | 수정 내용 |
|---|---|
| `indexer/core_graph.py:333-340` | Chunk 노드 properties에서 `"text"` 삭제. docstring에 「원문은 검색엔진에만 둠」 한 줄 추가 |
| `indexer/my_graph.template.py:269-270` | 빈칸 1 힌트에서 `text` 삭제, 「원문은 넣지 않음(교재 6쪽)」 추가 |
| `indexer/my_graph.py` | 템플릿과 같은 내용이면 같이 고침(강사용 정답 사본) |
| 교재 SLIDE 34 노트 | 「원문 본문도 함께 들어 있어 답의 근거를 보여 줄 때 씁니다」 → 「원문은 넣지 않고 chunk_id만 둡니다. 근거 원문은 검색엔진에서 chunk_id로 가져옵니다」 |
| 교재 SLIDE 37(K4) 그림 | 청크 노드 속성 예시에 text가 있으면 삭제 |

### 개선 2. 그래프 속성 길이 점검 추가(권장)

- `indexer/check_graph.py`에 「속성 크기」 출력 추가: 라벨별 속성의 최대 길이, 80자를 넘는 속성 수
- 경고만 내고 실패로 처리하지 않음. 교재 6쪽 질문 ③(「크면 뺌」)을 숫자로 확인하는 용도
- 현재 표본에서 80자 초과: BenefitLimit.description(최대 124자), BenefitCondition.description(최대 89자),  
  Requirement.description(80자)

### 보류. Benefit.product_id 중복

- OFFERS_BENEFIT 관계와 benefit_id 앞부분(`D2-C055-B07`)에 이미 상품 ID가 있어 중복임
- 스키마를 바꾸면 benefit_guide 전체를 다시 추출해야 하므로, 효과(7자짜리 속성 1개) 대비 비용이 커서 보류

## 5. 작업 순서와 검증

| 순서 | 작업 | 완료 기준(증거) |
|---|---|---|
| 1 | 개선 1 코드 수정(core_graph, 템플릿, my_graph) | `grep -n '"text"' indexer/core_graph.py`에 Chunk 노드 줄이 없음 |
| 2 | 표본 다시 색인 `python index_graph.py --run {별명}-s2 --sample` | K2 추출이 캐시 재사용으로 끝남(LLM 호출 0건 로그) |
| 3 | 그래프 확인 Cypher `MATCH (c:Chunk {generation: $g}) WHERE c.text IS NOT NULL RETURN count(c)` | 0건 |
| 4 | `python check_graph.py --qid Q09` | 적중 판정이 수정 전과 같음 |
| 5 | `python search_graph.py --eval` | 통과 문항 수가 수정 전 기록(`retriever/data/logs/eval-*.jsonl`)과 같음 |
| 6 | 개선 2 구현 후 `python check_graph.py --qid Q09` | 속성 크기 표가 출력됨 |
| 7 | 3절 결정에 따라 교재 6쪽, SLIDE 34, 37 수정 | `python scripts/render-pptx.py`로 미리보기 확인 |

되돌리기: 코드는 git으로 되돌린 뒤 다시 색인함. 이전 세대가 남아 있으면 `indexer/data/active_generation.json`을 이전 세대로 바꿔 바로 복구함.

## 6. 바꾸지 않는 것과 이유

- 엔티티 임베딩(Neo4j): 엔티티 직접 검색(K6)의 재료. 검색엔진으로 옮길지는 교재가 별도 과제로 남김
- Community 보고서(summary, findings): 그래프에서 만든 값이라 다른 원래 자리가 없음
- Consultation의 member_pseudo_id: 가명 ID이며 「이 회원의 상담」 탐색(①)에 씀(`search_graph.py:575`)
