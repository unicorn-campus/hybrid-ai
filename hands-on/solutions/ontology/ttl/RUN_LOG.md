# Turtle 원본 방식 실행 기록

작성일 2026-11-22. `hands-on/solutions/ontology` 폴더를 만들고 확인한 과정을 적음.  
설계서와 앞선 시험 기록은 `.temp/ontology-turtle-trial/`의 `DESIGN.md`, `RESULT.md`에 있음(Git에 올리지 않는 폴더).

## 1. 만든 순서

| 순서 | 한 일 | 결과 |
|------|-------|------|
| 1 | `graphrag`를 복사하고 `graphrag-ontology`의 승인된 설계 결과와 코드를 얹음. `rdflib 7.6.0`, `pyshacl 0.40.2` 추가 | 이 시점에 `graphrag-ontology`와 파일 차이 0 |
| 2 | 승인된 JSON(`concepts.json`, 맞추기 표 2개, `graph_schema.json` 3개)을 Turtle 7개로 옮김 | `card.ttl`(문장 319개), 셰이프 4개, 맞추기 표 2개 |
| 3 | 읽기 라이브러리 `indexer/core_turtle.py` 작성 | 개념 층, 그래프 스키마, 맞추기 표, SHACL 검사, 지문, 엔티티 키 표 |
| 4 | 도구 `ttl/tools/build_from_ttl.py`, `ttl/tools/check_ttl.py` 작성 | 아래 2절 |
| 5 | 인덱서가 JSON 대신 Turtle을 읽게 고침. 검사 규칙 K01 ~ K09를 Cypher에서 SHACL로 바꿈 | 아래 3절 |
| 6 | 검색기의 엔티티 찾기가 키 표를 Turtle에서 읽게 고침 | 아래 4절 |

- 옮길 때 쓴 일회용 스크립트는 `.temp/ontology-turtle-trial/migrate.py`임. 이 폴더에는 넣지 않음(다시 쓸 일이 없음)

## 2. 원본 검사와 스키마 만들기

- `check_ttl.py`: 통과. Turtle 파일 7개, Class 9개, 관계 6개, 검사 규칙 9개, 주제 확정 이름 95개와 미확정 48개,  
  업종 확정 22행(전체 32행). 결과 파일 `ttl/output/check_ttl.json`  
- `build_from_ttl.py --check`: 문서 3종 모두 「지금 파일과 같음」(약관 노드 타입 2, 혜택 안내 3, 상담 기록 6)  
- 일부러 고쳐 본 4곳(Class 뜻, 허용 값, 키 속성, 맞추기 표 한 행)을 `check_ttl.py`가 모두 잡았음  
- 주제 확정 이름이 JSON의 92행보다 3개 많은 까닭: 대표 이름 칸에만 있던 이름 3개(예: 해외)가 Turtle에서는  
  대표 이름(`skos:prefLabel`)으로 적혀 확정한 이름에 들어감

## 3. 인덱싱

| 실행 | 명령 | 결과 |
|------|------|------|
| `ttl-f1` | `index_graph.py --run ttl-f1 --reuse {기준 결과}` | **의도와 달리 LLM 추출이 다시 돌았음.** 추출 단위 368개, 토큰 1,396,487, 보고서 54번, 757초 |
| `ttl-f2` | `index_graph.py --run ttl-f2 --reuse data/reuse-doconto-f1 --full-reindex` | LLM 추출 0개, 재사용 368개, 보고서 재사용 61개, 임베딩 재사용 260개, 45초 |

- `ttl-f1`에서 재사용이 안 된 까닭: 재사용 여부를 `graph_schema.json`의 파일 지문으로 판단하는데, 기준 추출(2026-11-18)은  
  파일 저장 형식을 바꾼 커밋 67bf960보다 앞서 만들어져 지문이 달랐음. Turtle과는 관계없고 `graphrag-ontology`에서도 똑같이 일어남  
- `ttl-f2`를 위해 기준 결과의 지문 칸만 지금 값으로 바꾼 사본(`indexer/data/reuse-doconto-f1`)을 만들었고,  
  돌리기 전에 368개가 모두 재사용되는지 먼저 확인함  
- 활성 세대: `gen-lab-ttl-f2-b1182ed8`

기준 세대 `gen-lab-doconto-f1-0c0b0e64`와 대조(`build_report.json`끼리)

| 항목 | 결과 |
|------|------|
| 라벨별 엔티티 수(843개), 노드 1,432개와 관계 1,933개, 합친 묶음 123개, 임베딩 843개 | 같음 |
| 공통 개념 층(Class 9, 관계 8), 뷰 설명(뷰 2, 컬럼 19), 업종 잇기(8, 22, 22) | 같음 |
| 검사 규칙 K01 ~ K09 위반 수(K06 14건, 나머지 0건), K06 대상 304개와 비율 0.046 | 같음. 어긴 개체도 같음 |
| 건너가는 지점 P1 ~ P6, 여러 문서에 걸친 주제 10개 | 같음 |
| 맞추기 표에 없는 새 항목 | 혜택 185개 같음. 주제 173개에서 172개로 **다름** |

- 다른 1개는 주제 「해외」임. 옛 JSON 표에서는 이름 칸만 보아 대표 이름 「해외」를 새 이름으로 잡았고,  
  Turtle에서는 대표 이름도 확정한 이름이라 빠짐. 사람이 이미 승인한 이름이므로 새 쪽을 그대로 둠  
- 검사 보고의 어긴 개체 표기가 키 값에서 「라벨 키 값」으로 바뀜(예: `D2-C002-B02` → `Benefit D2-C002-B02`)

## 4. 검색

| 확인 | 결과 | 기록 |
|------|------|------|
| 경로 점검 M-1042(`check_paths.py`) | 기준과 같음. P5 상담 4건, P3 4경로, P1 9경로 중 5개가 「연회비」로 조항과 이어짐, P2 0개, P6 2행, P4 교육 1, 쇼핑 4, 주유 1 | `retriever/data/logs/ttl-f2/check_paths-M-1042.log` |
| Q01 | 답변 완료. 「3,000,000원 이상이고 연체가 없으면 다음 연도 기본 연회비 전액 면제」 | `Q01.log` |
| Q07 | 답변 완료. 「1.2% 적립, 월 한도 8,000원 상당」 | `Q07.log`, 고친 뒤 `Q07-keys.log` |
| Q25 | 확인할 수 없음(기준과 같음). ⑥에 남긴 쌍도 기준과 같은 D3-0017, D1-0007 | `Q25.log` |
| 엔티티 찾기 앞뒤 대조 | 키 40개와 권한 3가지로 120건, 모두 같음(엔티티를 찾은 것 86건) | 화면 출력만 |

- 「연회비」 주제와 이어진 조항 8개는 두 세대가 같음(화면에는 4개까지만 찍혀 순서가 달라 보임)  
- 실행 중 외부 호출 오류가 있었음: Cohere 리랭크 연결 끊김(RRF 순위로 대신함), Q01에서 Groq 툴 호출 검증 오류 1번,  
  Q25에서 Jev 연결 끊김 1번. 기준 기록에도 있던 종류이며 종료 상태는 바뀌지 않았음  
- Q14는 돌리지 않음

## 5. 남긴 것과 알아 둘 점

- Neo4j에 세대 2개가 더 생김: `gen-lab-ttl-f1-ac785868`(다시 추출한 것), `gen-lab-ttl-f2-b1182ed8`(활성).  
  OpenSearch에도 같은 이름의 인덱스 2개가 생김. `ttl-f1`은 쓰지 않으므로 지워도 됨(지우지 않았음)  
- 공통 개념 층 노드(OntoConcept 등)는 세대와 관계없이 한 벌이라, 이 폴더의 인덱싱이 Turtle에서 읽은 내용으로 다시 실었음.  
  내용은 같고 `doc_labels`에서 설계 과정 메모 칸(`fill`, `detail`)만 빠짐. 검색기는 라벨과 역할만 씀  
- `graphrag`, `graphrag-ontology` 폴더의 파일은 고치지 않았음  
- 아직 하지 않은 것은 `../README.md` 0.5절에 적음

## 6. 스키마 설계 도구와 프롬프트를 Turtle 방식으로 바꿈(2026-11-22)

### 6.1 바꾼 것

| 구분 | 바꾼 것 |
|------|---------|
| 승인본 Turtle | JSON 기록에만 있던 채우는 방법 13행(`card:fill`, `card:fillNote`)과 건너가는 경로 6개(`card:CrossingPath`)를 옮기고 대조함. 맞추기 표는 이름 없는 노드를 이름 있는 주소로 바꿔 다시 저장해도 같은 글이 나오게 함 |
| 읽기 라이브러리 | `core_turtle.py`에 `fill_of`, `crossing_paths`를 더하고, 지문(`signature`)을 글자 기준에서 내용 기준으로 바꿈 |
| 새 도구 | `ttl/tools/ttl_write.py`(Turtle 쓰기와 맞추기 표 행), `draft.py`(초안 시작, 차이, 올리기, 버리기), `render_review.py`(검토 표) |
| 고친 도구 | `check_ttl.py`(초안도 검사, 설계 입력 대조 추가), `build_from_ttl.py`(초안에서 스키마 초안과 그림), `fill_test.py`(Turtle 읽기, 규칙 검사를 SHACL로), `draft_topic_map.py`와 `draft_category_map.py`(확정을 `maps/*.ttl`에 씀), `finalize.py`(초안 올리기와 승인 기록) |
| 지운 것 | `common/concepts.json`, `common/topic_map_approved.json`, `common/category_map_approved.json`, `tools/build_schema.py`, `common/tools/check_concepts.py`. `check_ttl.py`의 옛 검사 ⑤(JSON 기록과 대조)도 없앰 |
| 프롬프트 | `prompts/design-kg-schema-doc-turtle.md`를 새로 만듦(611줄). 기존 `design-kg-schema-doc-ontology.md`(521줄)는 고치지 않았고, 만드는 스크립트는 `.temp/ontology-turtle-trial/make_turtle_prompt.py`임 |

### 6.2 확인한 것

| 확인 | 결과 |
|------|------|
| 옮긴 뒤 대조 | 채우는 방법, 건너가는 경로가 JSON 기록과 같음. 맞추기 표와 그래프 스키마 3개는 옮기기 앞과 같음 |
| 채우기 시험 다시 채점(`fill_test.py score`, LLM 호출 없음) | 질문별 지표, 경로, 키, 허브, 규칙 위반 수(K06 1건, 나머지 0건)가 앞과 모두 같음. 규칙 표의 대상 칸과 예 표기만 바뀜 |
| 초안 도구(본 폴더에서 시작했다가 버림) | 시작, 차이(달라진 문장 없음), 초안 검사 통과. 스키마 초안은 옛 초안을 검증해 낸 꼴과 같고 그림 2장은 글자까지 같음 |
| 재인덱싱 `ttl-f3`(재사용) | LLM 추출 0개, 재사용 368개, 36초. 기준 세대와 라벨 수, 노드와 관계 수, 개념 층, 업종 잇기, 규칙 위반, 경로가 같음. 활성 세대 `gen-lab-ttl-f3-e0dd0609` |
| 경로 점검 M-1042(`ttl-f3`) | 앞과 같음(조항을 4개까지만 찍는 줄의 순서만 다름) |

- `fill_test.py score`를 다시 돌려 `output/fill_scores.json`과 문서 종류별 `output/fill_report.md`가 새로 쓰였음(숫자는 같고 규칙 표 표기만 다름)

### 6.3 LLM이 Turtle 초안을 쓰는 시험(시험 폴더 `.temp/turtle-flow-trial/`)

- 방법: 이 폴더의 사본을 만들고, 팀원 지식니(Sonnet)에게 새 프롬프트의 5 ~ 6단계와 지어낸 요구만 줌.  
  요구는 약관에 시행일 속성(`effective_date`), 대체 관계(`REPLACES`, 반대 이름 `REPLACED_BY`), 검사 규칙 K10(참조 무결성)을 보태는 것임  
- 결과: 첫 `check_ttl.py --draft --schema none`에서 통과(고친 횟수 0). 도구 호출 15번, 76초, 약 12만 9천 토큰  
- 달라진 곳: `card.ttl` 더한 문장 9개와 뺀 문장 1개(판 번호 1 → 2), `shapes/regulation.ttl` 더한 문장 13개, `shapes/checks.ttl` 더한 문장 7개. 의도한 대상뿐임  
- 따로 검증한 것: K10이 없는 조항을 가리킬 때만 위반을 냄. 스키마 초안에 속성과 패턴이 들어감.  
  생성물을 손으로 고치면 검사 ④가 잡음. 판 번호를 되돌리면 올리기가 막힘.  
  `finalize.py regulation`으로 초안이 승인본으로 올라가고 승인 기록에 판 번호 2와 지문이 적힘  
- 검토 표 예: `ttl/output/trial-review-step5.md`(시험 폴더에서 만든 것을 복사해 둠. 실제 승인 대상이 아님)  
- 지식니가 짚은 프롬프트의 모자란 곳 4가지(참조 무결성의 도착 대상 이름, 순서 번호 매기는 법, 반대 이름 선언, `--schema none`은 통과 판정이 아님)를 프롬프트에 보탬  
- 한계: 지어낸 요구 하나, 문서 종류 하나로 한 시험임. 실패 사례를 만나지 못해 LLM이 틀린 초안을 고쳐 가는 과정은 보지 못함.  
  사람 승인과 LLM 추출을 다시 돌리는 채우기 시험은 하지 않음

### 6.4 알아 둘 점

- 시험 중 지식니가 세션 넘기기 도구를 잘못 불러 「dummy」 세션이 하나 생겼다가 바로 멈춤  
- `ttl/tools/draft.py`의 차이 계산은 그 「dummy」 세션이 고친 것임(이름 없는 노드를 내용 기준 번호로 바꿔 견줌).  
  시험 폴더에서 돌려 보니 「(이름 없는 노드)」 대신 딸린 셰이프 이름이 나와 그대로 둠  
- 같은 세션이 인덱싱을 한 번 더 돌려 `indexer/data/ttl-f3.log`가 「할 일 없음」으로 끝난 빈 실행의 로그로 덮어써짐.  
  그래프와 인덱스는 바뀌지 않았고, 원래 실행의 숫자는 세대 폴더의 `build_report.json`과 이 문서 6.2절에 남아 있음  
- 그 세션이 남긴 프롬프트 지적 4가지(관계의 목록 밖 속성 허용 값은 true, 속성은 card.ttl에 따로 선언하지 않음,  
  역량 질문 번호는 2단계에서 확정한 것만, 파일 머리 주석의 범위도 함께 고침)를 프롬프트에 보탬(614줄)  
- Neo4j와 OpenSearch에 세대 `gen-lab-ttl-f3-e0dd0609`가 더 생김. `ttl-f1`, `ttl-f2`는 지우지 않았음

## 7. 업종 맞추기 표를 새 흐름으로 실제 확정함(2026-11-22)

LLM이 후보를 내고, 사람이 확정하고, Turtle 초안에 적어 승인본으로 올리는 한 바퀴를 실제 항목으로 돌림.

| 순서 | 한 일 | 결과 |
|------|-------|------|
| 1 | `draft.py start` | 승인본 7개 파일을 초안 폴더로 복사 |
| 2 | `draft_category_map.py draft --from {세대}/new_map_items.json` | 새 혜택 185건 가운데 LLM에 물은 것 160건(7건은 후보가 이미 있음, 18건은 대상 문장이 없어 묻지 않음). 오류 0. 로그 `schema/doc-ontology/output/category_draft_20261122.log` |
| 3 | `review_category_map.py`(새 도구) | 검토 파일 `review/step8-category.md`. 후보가 분명한 것 116건, 미정 51건, 대상 문장 없음 18건 |
| 4 | 제안 만들기 | 앞서 사람이 정한 혜택과 대상 문장이 같으면 그 결정을 따름(64건), 그 밖에 LLM 후보가 분명하고 갈리지 않으면 LLM 후보(69건), 나머지 52건은 정하지 않음 |
| 5 | 사용자 확정 | 답 원문 「제안대로 확정」. `decisions.json`에 검토 파일 경로와 SHA-256 값과 함께 기록. 결정 파일 `output/category_decision_20261122.json` |
| 6 | `draft_category_map.py approve` → `check_ttl.py --draft` → `draft.py diff` | 초안 검사 통과. 달라진 파일은 `maps/category.ttl` 하나(더한 문장 1,086개, 뺀 문장 1개) |
| 7 | `draft.py promote` | 승인본으로 올림. 맞추기 표만 바뀌어 판 번호는 1 그대로. 승인본 검사 통과 |
| 8 | 재인덱싱 `ttl-f4`(재사용) | 내용 지문이 바뀌어 `--full-reindex` 없이 새 세대를 만듦. LLM 추출 0개, 24초. 활성 세대 `gen-lab-ttl-f4-ddf8bca3` |

확정 뒤 숫자

| 항목 | 앞 | 뒤 |
|------|----|----|
| 업종 맞추기 표 행 | 32(확정 22, 잇지 않음 10) | 217(확정 138, 잇지 않음 27, 확정 전 52) |
| 업종에 이어진 혜택(IN_CATEGORY) | 22 / 217 | 138 / 217 |
| 맞추기 표에 없는 새 혜택 | 185 | 0 |
| 검사 규칙 | K06 14건, 나머지 0건 | 같음(K02 허용 값 위반 0건) |
| 경로 점검 M-1042의 업종 → 혜택 | 교육 1, 쇼핑 4, 주유 1 | 교육 6, 쇼핑 21, 주유 6 |

- LLM 후보를 그대로 쓰지 않은 까닭: 같은 대상 문장인데 앞선 사람 결정과 다른 후보가 24건 있었음  
  (예: 「국내외 일반 가맹점의 일시불 결제」는 앞서 「잇지 않음」인데 LLM은 14건을 미정으로 냄)  
- 「생활」이 51건으로 가장 넓게 쓰임(편의점, 마트, 커피점을 함께 적은 문장과 정기결제, 통신요금). 앞선 결정을 따른 결과임  
- 확정 전 52건: 대상 문장 없음 18건, 여러 업종을 나열한 문장, 주말 한정 일반 가맹점, 후보가 갈린 「편의점 하루상점」 3건 등  
- 평가 질문 가운데 업종을 묻는 문항이 없어 답변까지의 확인은 하지 않음. 경로 점검으로만 확인함  
- Neo4j와 OpenSearch에 세대 `gen-lab-ttl-f4-ddf8bca3`가 더 생김. 앞선 `ttl-f1` ~ `ttl-f3`은 지우지 않았음

## 8. 이름과 폴더 정리(2026-11-22, 사용자가 직접 함)

- 프롬프트 이름을 `prompts/design-kg-schema-ontology.md`로 바꿈. 이 문서의 앞 절에 나오는 `design-kg-schema-doc-turtle.md`가 이 파일임(내용 같음)  
- 옛 프롬프트 `prompts/design-kg-schema-doc-ontology.md`와 옛 폴더 `hands-on/solutions/graphrag-ontology`를 지움.  
  둘 다 Git 기록(커밋 c4fbcd7까지)에 남아 있음. 이 문서의 앞 절에서 「비교 기준」으로 부른 것이 그 폴더임  
- 비교 기준으로 쓰던 세대 결과는 이 폴더의 `indexer/data/generations/gen-lab-doconto-f1-0c0b0e64`와 `indexer/data/reuse-doconto-f1`에 사본이 있음(Git 밖)  
- 이에 맞춰 코드 주석과 도구의 경로를 고침: `indexer/core_ontology.py`, `indexer/index_graph.py`, `schema/doc-ontology/tools/common.py`,  
  `prepare.py`(정형 DB 구조 명세 경로를 이 폴더의 `schema/rdb`로), `render_step2.py`  
- 그대로 둔 것: `sources.json`, `decisions.json`, `approval.json`, `review/step1.md`, `step2.md`, `schema/doc-ontology/RUN_LOG.md`에 적힌 옛 경로.  
  2026-11-18 설계 당시의 기록이라 고치지 않음  
- 프롬프트를 만들던 스크립트(`.temp/ontology-turtle-trial/make_turtle_prompt.py`)는 옛 프롬프트를 읽어 만들던 것이라 더 쓰지 않음.  
  앞으로는 `prompts/design-kg-schema-ontology.md`를 직접 고침  
- Neo4j와 OpenSearch에는 옛 폴더가 만든 세대 `gen-lab-doconto-f1-0c0b0e64`가 남아 있음(지우지 않았음)

## 9. card:kind를 없애고 공통 개념 표시로 바꿈(2026-11-22, 사용자 결정 「수정안대로」)

- 까닭: `card:kind "개체"`가 「종류」로 읽혀 `a owl:Class`와 같은 질문에 두 번 답하는 것처럼 보였음.  
  코드를 보니 이 줄은 값이 아니라 「있는지」로 공통 개념 9개를 골라내는 숨은 표시였고, 「분류」 값은 `card:valueList`와 정확히 겹쳤음  
- 바꾼 것: `card:kind` 9줄을 지우고 공통 개념 9개에 `rdfs:subClassOf card:CommonConcept`를 붙임. `card:CommonConcept` 정의를 더함. 판 1 → 2  
- 개체와 분류는 따로 적지 않고 값 목록(`card:valueList`)이 있으면 분류로 계산함(`core_turtle.load_concepts`). 그래프의 OntoConcept 노드 값은 그대로임  
- 고친 코드: `indexer/core_turtle.py`(`common_concepts` 추가, `CUSTOM_TERMS`), `ttl/tools/check_ttl.py`, `ttl/tools/draft.py`(판 번호만 따로 읽게 고침.  
  처음 올리기는 옛 승인본을 새 규칙으로 읽다가 멈췄음), 프롬프트 `prompts/design-kg-schema-ontology.md`의 낱말 표와 예시  
- 확인: 공통 개념 층(판 번호 빼고), 엔티티 키 표, 그래프 스키마 3개가 바꾸기 전과 같음. 초안 검사와 승인본 검사 통과.  
  재인덱싱 `ttl-f5`(재사용, LLM 추출 0, 29초)가 `ttl-f4`와 라벨 수, 노드와 관계, 업종 잇기, 규칙 위반, 경로 모두 같음. 활성 세대 `gen-lab-ttl-f5-a6e78683`  
- 교재 덱: 11쪽(Class 정의 코드와 풀이표에서 card:kind 줄을 빼고 「문장 6개」로)과 15쪽(업종 코드에서 card:kind 줄을 빼고 ④ 설명에 「이 줄이 있으면 분류 Class로 봄」)을 고침.  
  사용자가 그 사이 덱에서 용어를 「주어, 속성, 값」으로 고친 판 위에 얹었음(`.temp/ttl-slides/edit_kind_on_user_deck.py`)

## 10. 역관 이유의 번호 정리와 17쪽 설명 보강(2026-11-22, 사용자 결정)

- `card:FOLLOWS`의 이유 「C5, Q14는 …」에서 평가셋 사용자 질문 번호(Q14)를 빼고 역량 질문 번호(C5)만 남김. Q14는 C5의 근거가 된 질문임  
- card.ttl이 바뀌어 올리기 도구의 규칙대로 판을 2 → 3으로 올림. 재인덱싱 `ttl-f6`(재사용, LLM 추출 0, 28초), 규칙 위반과 업종 잇기는 앞과 같음. 활성 세대 `gen-lab-ttl-f6-fcd0aad2`  
- 교재 17쪽(Turtle로 적기: 개념, 역관)의 ⑤ 설명에 「M1, M2, A1은 스키마 설계 단계 ①에서 정한 역량 질문 번호」와 M1 질문 예를 넣고, 발표자 노트에 세 질문의 문장을 적음  
  (`.temp/ttl-slides/edit_p17_cq.py`, 사용자가 그 사이 저장한 판 위에 얹음)

## 11. 주제 같은 개체 규칙의 옛 파일 경로를 고침(2026-11-22, 사용자 지시)

- `card:Topic`의 `card:identityRule` 설명에 지운 파일 `common/topic_map_approved.json`이 남아 있었음.  
  지금 쓰는 주제 맞추기 표 `maps/topic.ttl`로 고침. 이 글은 OntoConcept 노드의 identity 속성으로 그래프에 실려 검색기가 읽음  
- 초안 폴더에서 고치고(`draft.py start`, 판 3 → 4) 기계 검사 통과 뒤 승인본으로 올림. 그래프 스키마 3개는 바뀌지 않음  
- 재인덱싱 `ttl-f7`(재사용, LLM 추출 0): 공통 개념 층 판 4, 업종 잇기 138, 규칙 위반과 경로가 앞과 같음. 활성 세대 `gen-lab-ttl-f7-d4bd772c`  
- 그대로 둔 것: `decisions.json`, `approval.json`, `output/round*/concepts_draft.json`, `schema/doc-ontology/RUN_LOG.md`의 옛 경로(설계 당시 기록)
- 이어서 온톨로지 앞머리 설명(`dcterms:description`)의 지운 도구 이름 `build_schema.py`를 `build_from_ttl.py`로 고침.  
  「graph_schema.json의 노드 타입 설명(description) 첫머리는 build_from_ttl.py가 여기서 가져옴」. 판 4 → 5, 그래프 스키마 3개는 그대로  
- 재인덱싱 `ttl-f8`(재사용, LLM 추출 0): 공통 개념 층 판 5, 업종 잇기 138, 규칙 위반과 경로가 앞과 같음. 활성 세대 `gen-lab-ttl-f8-44b34a7f`

## 12. Class 노드 사이 관계를 관계 이름 그대로 실음(2026-11-22, 사용자 결정 「네, 바꿔요」)

- 바꾸기 전: OntoConcept 사이를 모두 `CONCEPT_REL` 한 가지로 잇고 관계 이름을 속성 `label`에 둠  
- 바꾼 뒤: card.ttl의 관계 이름 그대로 이음(예: `(혜택)-[:IN_CATEGORY {inverse: "CATEGORY_OF"}]->(업종)`). 반대 이름은 그대로 속성  
- 고친 코드: `indexer/core_ontology.py`의 `load_concept_layer`(`MERGE (a)-[x:$(r.label)]->(b)`, Cypher 동적 관계 이름. context7로 문법 확인)와 개수 세는 쿼리  
- 확인: 관계 이름으로 거는 쿼리(검색기 경로, K8 투영, 검사 내보내기)는 모두 라벨이나 세대로 범위를 좁혀 개념 노드 사이 선이 섞이지 않음. 검색기는 이 관계를 읽지 않음  
- 재인덱싱 `ttl-f9`(재사용, 사전 검사 무시 `--full-reindex`, LLM 추출 0): 개념 사이 관계 6종 8개(ABOUT 3, FOLLOWS, HAS_COMPLAINT, IN_CATEGORY,
  IN_SEGMENT, REFERS_TO), `CONCEPT_REL` 0개, 세대의 IN_CATEGORY 138개, 규칙 위반과 경로가 앞과 같음. 활성 세대 `gen-lab-ttl-f9-60f089e3`  
- 교재 「공통 개념 층을 OntoConcept 노드로 싣기」 장표의 코드 발췌, 설명 ④, 아래 띠, 노트를 고침(`.temp/rel/fix_rel_names.py`)

## 13. 정형 조회용 뷰 설명을 app 스키마의 논리 뷰 7개로 늘림(2026-11-22, 사용자 결정 「app 7개만」)

- 까닭: sql-retriever는 app 스키마의 논리 뷰 7개를 쓰는데, 뷰 설명(`schema/rdb/app_views.json`)에는 2개(customer_cards, merchant_usage)만 있었음.  
  검색기는 그래프에 실린 뷰로만 SQL을 허용하므로 연체, 일별 사용액, 가입 정보 질문을 SQL로 풀지 못했음.  
  인덱서의 카탈로그 대조도 「파일에 적은 뷰」만 봐서 빠진 뷰를 알리지 않았음  
- 바꾼 것: `app_views.json` 판 2. 뷰 7개(customer_profile, customer_cards, monthly_usage, merchant_usage, customer_daily_usage,
  customer_delinquency, customer_delinquency_history), 컬럼 40개, 예시 SQL 5개(월별 총액, 연체 추이 추가). 뜻은 `backing-services/rdb/init`의
  뷰 정의와 sql-retriever의 `query_config.json`, `search_plan.md`에서 가져옴. 건너가는 키 컬럼은 그대로 2개(product_id, category)  
- app_internal 스키마(customer_cards_full, member_basic. 원본 카드 ID와 회원 ID가 있음)는 DB 주석과 sql-retriever README대로 NL2SQL에 열지 않는
  서비스 코드 전용이라 적지 않음  
- 고친 코드: `indexer/core_ontology.py`의 `check_view_catalog`가 DB의 app 스키마에 있는데 파일에 없는 뷰도 어긋남으로 잡음(옛 파일로 대조하면 5개가 걸림)  
- 재인덱싱 `ttl-f10`(재사용, `--full-reindex`, LLM 추출 0): 뷰 7개, 컬럼 40개, 키 컬럼 2/2, 예시 SQL 5개. 규칙 위반과 경로가 앞과 같음. 활성 세대 `gen-lab-ttl-f10-0a7adf08`  
- 검색기 확인: 「이 회원의 최근 12개월 연체 추이」(M-1042)에서 정형 조회가 `customer_delinquency_history`로 SQL을 만들어 12행을 받음(앞에서는 허용하지 않은 뷰라 실행 못 함).
  다만 최종 답은 「확인할 수 없음」. 검색기의 ⑦ 판정이 문서 원문 근거를 요구하는 설계라, 정형 조회만으로 끝나는 질문은 답하지 않음(이번 수정과 별개).  
  `check_paths.py`의 P4, P6 정형 조회도 앞과 같이 동작함  
- 교재: 「정형 조회용 뷰 설명 싣기」 장표(아래 띠 숫자, 키 컬럼 없는 뷰 5개 글, 설명 ③, 노트)와 「검색기 ① 요청 접수」 장표의 「뷰 2개」를 고침(`.temp/views7/fix_views7.py`)
