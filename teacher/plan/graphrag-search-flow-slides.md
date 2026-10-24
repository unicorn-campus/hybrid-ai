# GraphRAG 검색 워크플로우 슬라이드 스크립트

- 덱 파일: `teacher/plan/graphrag-search-flow.pptx`  
- 빌드: `NODE_PATH="C:\Users\hiond\.npm-global\node_modules" node teacher/plan/build/build-search-flow.js`  
- 후처리: `python teacher/plan/build/fix_ph.py` → `check_paste.py` → `python scripts/render-pptx.py`(미리보기)  
- 상세 문서: `teacher/plan/graphrag-search-flow.md`(최종안 v1.0). 링크 기준 URL:  
  `https://github.com/unicorn-campus/hybrid-ai/blob/main/teacher/plan/graphrag-search-flow.md`  
- 레이아웃: 본 덱 `내용_단쪽`(references/pptx-guide.md 붙여넣기 호환 규칙 7가지), 16″ × 9″, Pretendard, 최소 14pt  
- 총 12장. 표지와 간지는 만들지 않음  
- 아래 「화면 본문」만 슬라이드에 넣고, 「발표자 노트」는 노트에 넣음

<!-- 간지: GraphRAG 검색 워크플로우 -->

## 슬라이드 1. 왜 세 가지 검색인가
- 제목: 검색 워크플로우: 질문의 답이 있는 자리에 따라 길을 나눔
- 리드문: 사실은 청크와 엔티티에, 경향은 커뮤니티 보고서에 있으므로 Local, Global, Hybrid로 검색 길을 나눔
- 표 열 너비: [2.6, 5.6, 3.9, 2.8]

| 질문 유형 | 예시(평가셋) | 답이 있는 자리 | 검색 방식 |
|---|---|---|---|
| 특정 대상의 사실 | Q01 연회비 면제 조건은? / Q14 M-1042 회원의 첫 요청은? | 청크 몇 개와 엔티티 | Local Search |
| 여러 문서의 경향 | Q23 고객군별 불만 주제 / Q24 받아들인 제안의 공통점 | 커뮤니티 보고서 여러 개 | Global Search |
| 경향 + 근거 사실 | Q25 불만 주제별 관련 약관 조항과 카드 혜택 | 보고서로 주제, 주제마다 원문 | Hybrid Search |
| 답할 수 없음 | Q18 ~ Q22 대상은 있지만 문서에 사실이 없음 | 없음 | Local 후 「근거에 없음」 |

- 용어 약속 배지: 용어 약속
- 용어 카드:
  - Hybrid Search = 주제 후 근거 검색: Global로 주제를 잡고 주제마다 Local로 원문 근거를 찾음
  - 키워드와 벡터 순위 융합(RRF): BM25 순위와 벡터 순위를 합쳐 한 줄로 세움. 「하이브리드」라 부르지 않음
  - Local과 Global의 출발점: Local은 청크와 엔티티에서, Global은 커뮤니티 보고서에서 출발함
- 화면 출처: hands-on/solutions/eval-set.json 25문항, teacher/plan/graphrag-search-flow.md 1절
- 상세 보기 링크: #1-왜-세-가지-검색인가-why
- 발표자 노트:
  - 평가셋 25문항 중 Q01 ~ Q17은 사실, Q23과 Q24는 경향, Q25는 경향과 사실을 함께 묻습니다.
  - Q18 ~ Q22 다섯 문항은 answerable이 false인 함정 질문입니다. 검색 방식이 아니라 결과로 다룹니다.
  - 「하이브리드」라는 말이 세 가지 뜻으로 쓰여 혼동이 생기므로 이 장에서 약속을 먼저 정합니다.

## 슬라이드 2. 실무 Best Practice 조사
- 제목: 실무 Best Practice: 질문 유형별로 길을 나누고, 후보와 홉 수를 묶음
- 리드문: 단순 사실은 원문 중심 검색이 더 정확하고, 요약과 추론은 그래프가 앞선다는 결과가 공통으로 나옴
- 화면 본문:
  1. 질문 유형별로 경로를 나눔: 단순 사실은 rerank RAG 60.9 대 GraphRAG 49.3, 요약은 GraphRAG 우세
  2. 청크는 BM25와 벡터를 RRF(k 60)로 합침. 벡터 후보는 최종 개수의 3배 이상
  3. Local은 엔티티에서 출발해 관계, 원문, 보고서를 한 컨텍스트로. 몫은 원문 0.5, 보고서 0.15
  4. 엔티티 찾기에도 키워드를 섞고, 그래프 탐색은 홉 수와 후보 수를 제한함
  5. Global은 관련 보고서만 골라 map-reduce. 동적 선택으로 토큰 77% 절감
  6. 넓은 질문을 사실까지 내리려면 DRIFT: 보고서로 초안과 후속 질문, 후속 질문마다 Local
- 비용 카드 제목: 질의당 평균 토큰
- 비용 카드 값:
  - 벡터 RAG: 879
  - GraphRAG Local: 38,707
  - GraphRAG Global: 331,375
- 비용 카드 주석: GraphRAG-Bench(GPT-4o-mini) 외부 벤치마크. 우리 시스템 측정값 아님
- 화면 출처: GraphRAG-Bench(arXiv 2506.05690), Microsoft GraphRAG 문서와 블로그, OpenSearch RRF 블로그, Neo4j 블로그
- 상세 보기 링크: #2-실무-best-practice-조사-요약
- 발표자 노트:
  - https://arxiv.org/html/2506.05690v3 (단순 사실과 요약에서 RAG와 GraphRAG 비교, 토큰 수치)
  - https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/ (OpenSearch 2.19 RRF, 기본 k 60)
  - https://docs.digitalocean.com/products/vector-databases/opensearch/concepts/hybrid-search/ (k는 최종의 3배 이상, 필터는 두 갈래에 똑같이)
  - https://raw.githubusercontent.com/microsoft/graphrag/main/docs/query/local_search.md (Local 컨텍스트 구성)
  - https://www.microsoft.com/en-us/research/blog/graphrag-improving-global-search-via-dynamic-community-selection/ (77% 절감, 데이터셋 1개와 질문 50개 기준)
  - https://raw.githubusercontent.com/microsoft/graphrag/main/docs/query/drift_search.md (Primer, Follow-up, Output)
  - https://neo4j.com/blog/developer/microsoft-graphrag-neo4j/ (엔티티 검색에 키워드 병행 권고)
  - Microsoft GraphRAG 저장소는 유지보수 모드로 표시되어 있습니다. 개념은 참고하되 구현은 Neo4j와 OpenSearch로 직접 합니다.

## 슬라이드 3. 전체 흐름
- 제목: 전체 흐름: 앞단에서 조건을 고정하고, 라우터가 세 길 중 하나로 보냄
- 리드문: 세대, 마감 시각, 질문 벡터를 처음에 한 번 정해 모든 갈래가 같은 조건으로 찾게 함
- 흐름 질문: 질문
- 흐름 앞단: ⓪ 앞단 | 세대 고정, 마감 시각, 질문 정리, 임베딩 1회
- 흐름 라우터: ① 라우터 | 규칙 → LLM 3분류
- 흐름 갈래 Local: Local Search | 사실 질문
- 흐름 갈래 Global: Global Search | 경향 질문
- 흐름 갈래 Hybrid: Hybrid Search | 경향 + 근거
- 흐름 뒷단: ⑤ 뒷단 | 근거 묶기, 답 스트리밍, 인용 검사
- 표 열 너비: [2.6, 12.3]

| 단계 | 하는 일 |
|---|---|
| ⓪-1 세대 고정 | 첫 노드에서 활성 세대와 인덱스 이름을 한 번 읽고 질의 끝까지 바꾸지 않음 |
| ⓪-2 마감 시각 | Local 45초, Global 90초, Hybrid 150초. 넘으면 모은 근거로 부분 답 |
| ⓪-3 질문 정리 | 카드명 별칭을 정식 이름으로, 회원번호를 가명 id로 바꿔 필터로 씀 |
| ① 라우터 | 규칙 먼저 보고 LLM이 3분류(local, global, hybrid), 꼴 오류면 Local |
| ⑤ 뒷단 | 사실은 원문 우선, 보고서는 맥락. 답이 끝나면 인용 id 검사 |

- 화면 출처: teacher/plan/graphrag-search-flow.md 3절
- 상세 보기 링크: #3-전체-흐름
- 발표자 노트:
  - 세대 고정은 라우터보다 먼저, 첫 노드에서 합니다(플로니 리뷰). 라우터가 도는 사이에 세대가 바뀌어도 질의 전체가 같은 세대를 봅니다.
  - 질문 벡터는 한 번만 계산해 청크 갈래, 엔티티 갈래, 보고서 검색이 같이 씁니다.
  - 라우터가 답 꼴을 지키지 못하면 Local로 보냅니다. Local도 보고서를 함께 넣으므로 거시 질문을 잘못 보내도 맥락이 남습니다.

## 슬라이드 4. Local Search 흐름
- 제목: Local Search: 세 갈래로 시작점을 찾고, 1-hop으로 넓혀 원문 위주로 답함
- 리드문: 회원번호와 카드는 필터로 범위를 먼저 좁히고, 청크와 엔티티와 이름 갈래가 함께 시작점을 찾음
- 범위 띠: 범위 좁히기(필터) | 회원번호 M-1042 → 가명 id, 카드명 → product_id. 상담 청크 본문에는 회원번호가 없음
- 갈래 1: 청크 갈래 | OpenSearch BM25 25 + 벡터 25 | RRF(k 60) + 리랭커 | 청크 4 ~ 6개의 엔티티(FROM_CHUNK)
- 갈래 2: 엔티티 갈래 | Neo4j 벡터 인덱스 kg_entity_embedding | 엔티티 8개(세대 필터) | 1-hop 이웃 6, 원문, 보고서
- 갈래 3: 이름 갈래 | 정식 카드명, 조항 번호 | Cypher 정확 일치 | 엔티티 → 원문, 보고서
- 합류 1: 고르고 자르기 | 갈래별 쿼터, 몫 원문 0.5, 관계 0.35, 보고서 0.15
- 합류 2: 답 | 원문 id 인용, 없으면 「근거에 없음」
- 콜아웃: 세 갈래가 모두 0건이면 BM25만 한 번 더 찾고, 그래도 없으면 LLM을 부르지 않고 「근거에 없음」으로 답함
- 화면 출처: teacher/plan/graphrag-search-flow.md 4절, Microsoft GraphRAG local_search.md, Neo4j 블로그(키워드 병행)
- 상세 보기 링크: #4-local-search
- 발표자 노트:
  - 청크 갈래는 BM25와 벡터에서 25개씩 뽑아 RRF로 합칩니다. 리랭커가 고를 후보가 충분해야 하므로 최종 개수(4 ~ 6개)보다 넉넉히 뽑습니다.
  - 엔티티 벡터만으로는 「한빛 가족돌봄 카드」, 「연회비 면제」처럼 낱말이 중요한 질문(Q01, Q09)의 시작점을 놓쳐 청크 갈래를 더했습니다.
  - 지식니 확인: 상담 청크 260개 본문에 M-1042가 한 번도 나오지 않습니다. 회원번호는 가명 id로 바꿔 메타데이터 필터로 써야 합니다.
  - 이름 갈래는 정식 카드명과 조항 번호처럼 정확히 같은 값이 있는 것만 맡습니다.

## 슬라이드 5. Local Search 상세
- 제목: Local Search 상세: 한 번의 Cypher로 이웃, 원문, 보고서를 함께 가져옴
- 리드문: 그래프는 1-hop까지만 넓히고, 컨텍스트 칸은 원문에 가장 많이 나눠 줌
- 코드 제목: 엔티티 갈래 Cypher 예시
- 코드:
  - WITH node AS e, score
  - ① OPTIONAL MATCH (e)-[r]-(n:__Entity__ {generation: e.generation})
  -    WITH e, score, r, n, coalesce(vector.similarity.cosine(n.embedding, $query_vector), -1.0) AS sim
  -    ORDER BY sim DESC   // 질문과 비슷한 이웃부터
  -    WITH e, score, collect(DISTINCT {...})[..$max_neighbors] AS neighbors
  - ② OPTIONAL MATCH (e)-[:FROM_CHUNK]->(k:Chunk)
  -    WITH e, score, neighbors, collect(DISTINCT {...}) AS chunks
  - ③ OPTIONAL MATCH (e)-[:IN_COMMUNITY]->(c:Community)
  -    RETURN ..., neighbors, chunks, ... {title: c.title, summary: c.summary, ...} ...
- 풀이:
  - ① 이웃: 관계 1개로 이어진 엔티티 중 질문과 가장 비슷한 6개. 사실 근거
  - ② 원문: 엔티티가 나온 청크. 사실 근거이며 가장 우선함
  - ③ 보고서: 엔티티가 속한 묶음의 요약. 맥락 근거
- 몫 제목: 컨텍스트 몫(출발값)
- 몫: 원문 50 | 엔티티와 관계 35 | 보고서 15
- 바꿀 점 제목: 설계 기준
- 바꿀 점:
  - 원문 상한 1600자(청크 260개 중 131개가 700자를 넘음)
  - 원문 칸 쿼터: 청크 갈래 3, 엔티티 갈래 2 이상
  - 상담 질문은 첫 상담과 가장 최근 상담을 먼저 고정 칸에 넣음
- 화면 출처: teacher/plan/graphrag-search-flow.md 4절, Microsoft GraphRAG config defaults.py(text_unit_prop 0.5, community_prop 0.15)
- 상세 보기 링크: #4-local-search
- 발표자 노트:
  - 긴 맵 리터럴은 {...}로 줄였습니다. ①②③ 번호와 「질문과 비슷한 이웃부터」 주석은 설명용입니다.
  - neo4j-graphrag의 VectorCypherRetriever가 벡터로 엔티티를 찾은 뒤 이 Cypher를 이어서 실행합니다. filters로 활성 세대만 봅니다.
  - Microsoft 기본값은 원문 0.5, 커뮤니티 0.15이고 나머지 0.35를 엔티티와 관계 몫으로 해석했습니다. 원문에 명시된 해석은 아닙니다.
  - 원문 칸은 갈래별 최소 쿼터를 둡니다. 쿼터가 없으면 청크 갈래가 원문 칸을 먼저 다 차지해 엔티티 갈래의 원문이 빠집니다.

## 슬라이드 6. Global Search 흐름
- 제목: Global Search: 관련 보고서를 묶음마다 요약하고, 점수 높은 것만 합쳐 답함
- 리드문: 경향 질문은 한 곳에 답이 없어서 보고서 여러 개를 나눠 읽고(Map) 중요한 것만 모음(Reduce)
- 단계 1: 보고서 고르기 | 50개 이하면 전부 | 넘으면 벡터 후보 + 관련도 점수
- 단계 2: Map | 보고서 묶음마다 중간 답 + 점수(0 ~ 100) | 동시 4, 묶음당 45초
- 단계 3: Reduce | 0점 버림, 점수 높은 순으로 예산까지 | 보고서 제목 인용
- 카드 1 제목: 선행 과제(인덱싱)
- 카드 1:
  - 고객군(신규가입, 장기보유, VIP 등)이 그래프에 없음
  - 상담 파일명의 고객군을 Consultation 속성으로 넣고 보고서 입력에 분포를 넘김
  - 그 전까지 Q23의 「고객군별」 요구는 맞추지 못함
- 카드 2 제목: 비용 감각
- 카드 2:
  - LLM 호출 = 라우터 1 + 묶음 수 + Reduce 1
  - 보고서를 다 넣는 기본형은 비용이 크고 무관한 보고서가 섞임
  - 동적 선택: 토큰 77% 절감, 품질 차이 유의하지 않음(MS, 질문 50개)
- 화면 출처: Microsoft GraphRAG global_search.md, MS Research 블로그(dynamic community selection), graphrag.com 패턴
- 상세 보기 링크: #5-global-search
- 발표자 노트:
  - 지식니 의견: 청크 260개, 묶음 최소 크기 3이면 보고서 수가 많지 않을 것으로 보여 전부 읽는 편이 단순하고 재현율이 높습니다. 실제 보고서 수는 재색인 뒤 확인합니다.
  - Map은 보고서 묶음마다 LLM을 한 번씩 부르므로 묶음 수가 곧 비용입니다. 동시 호출은 전역 4개로 묶습니다.
  - 지식니 확인: 상담 그래프 스키마의 노드는 Consultation, Complaint, Proposal, ReconsiderCondition 4종이고 고객군은 없습니다.

## 슬라이드 7. Hybrid Search 흐름
- 제목: Hybrid Search: 보고서로 주제를 먼저 잡고, 주제마다 Local로 근거를 붙임
- 리드문: 「주제 후 근거 검색」으로 경향과 사실을 함께 묻는 질문(Q25)에 답함. Microsoft DRIFT를 교육용으로 줄인 형태
- 단계 1: Primer | Global 보고서로 주제 목록과 1차 답 | 주제당 후속 질문 1개(상한 5)
- 단계 2: Follow-up | 후속 질문마다 Local 검색만(답 생성 없음) | 주제당 원문 3개, topic_id
- 단계 3: 합치기 | 주제 아래 근거 원문을 붙임 | LLM 한 번으로 최종 답
- 예시 제목: 예시 흐름(Q25, 설명용 가정)
- 예시:
  - 주제: 연회비 부담 불만 → 후속 질문: 연회비 면제 조건 약관 조항은?
  - Local 검색: 약관 제10조① 원문
  - 답: 「연회비 부담」 주제 아래에 제10조① 근거를 붙임
- 규칙 제목: 멈춤 규칙
- 규칙:
  - 라운드 1회, 후속 질문 상한 5
  - 종료: 라운드 소진 또는 새 근거 0건
  - 시간 예산 150초, 넘으면 모은 근거로 답
  - LLM 호출 3회(라우터, Primer, 합치기)
- 화면 출처: Microsoft GraphRAG drift_search.md, config defaults.py(drift_k_followups 20, n_depth 3)
- 상세 보기 링크: #6-hybrid-search-주제-후-근거-검색
- 발표자 노트:
  - Microsoft DRIFT 기본값은 후속 질문 20개, 깊이 3입니다. 교육용으로 라운드 1회, 후속 질문 5개로 줄였습니다.
  - DRIFT는 후속 질문마다 중간 답을 만들지만, 이 구성은 검색만 하고 마지막에 한 번 답해 LLM 호출을 3회로 묶습니다.
  - 후속 질문 수는 지식니(주제당 1개, 상한 6)와 플로니(3개, 동시성 부담) 의견을 합쳐 주제당 1개, 상한 5로 정했습니다.
  - 예시 흐름은 설명용 가정입니다. 실제 주제와 조항은 실행 결과로 확인합니다.

## 슬라이드 8. 세 방식 비교
- 제목: 세 방식 비교: 무엇에서 출발하고 얼마나 드는가
- 리드문: 사실은 Local이 싸고 정확하며, Global과 Hybrid는 경향 질문에만 비용을 들임
- 표 열 너비: [2.6, 4.1, 4.1, 4.1]

| 비교 축 | Local Search | Global Search | Hybrid Search |
|---|---|---|---|
| 예시 질문 | Q01 연회비 면제 조건 | Q23 고객군별 불만 주제 | Q25 주제별 약관과 혜택 |
| 시작점 | 청크, 엔티티, 이름 | 커뮤니티 보고서 | 보고서 → 후속 질문 |
| 근거 | 원문, 엔티티, 보고서 | 보고서 | 보고서와 원문 |
| LLM 호출(라우터 포함) | 2회 | 2 + 묶음 수 | 3회 |
| 시간 예산 | 45초 | 90초 | 150초 |

- 화면 출처: teacher/plan/graphrag-search-flow.md 4 ~ 7절. LLM 호출 수는 설계 기준 계산값
- 상세 보기 링크: #3-전체-흐름
- 발표자 노트:
  - LLM 호출 수는 설계로 계산한 값입니다. 형식 오류 재시도는 넣지 않았습니다.
  - 토큰과 지연은 아직 측정하지 않았습니다. 10장의 실행 순서 1번이 기준선 측정입니다.

## 슬라이드 9. 실행 규칙과 실패 대체
- 제목: 실행 규칙과 실패 대체: 막히면 한 단계 낮춰서라도 답함
- 리드문: 시간 예산과 재시도 상한으로 멈춤을 막고, 장애마다 대체 경로와 알림 코드를 정함
- 표 열 너비: [2.6, 4.3, 3.3]

| 상황 | 대체 경로 | 알림 코드 |
|---|---|---|
| 라우터 답 꼴 오류 | 2번 더 묻고, 끝내 틀리면 Local | ROUTER_BAD_FORM |
| 보고서 없음 | Global, Hybrid를 Local로 내림 | NO_REPORTS |
| OpenSearch 장애 | 엔티티 갈래와 이름 갈래만 | SEARCH_ENGINE_DOWN |
| Neo4j 장애 | 1번 다시 연결, 실패 시 원문만 | GRAPH_DOWN |
| LLM 429 계속 | 받은 Map만 Reduce, Local은 근거만 | LLM_RATE_LIMIT |
| Map 일부 시간 초과 | 받은 중간 답으로 Reduce | MAP_PARTIAL |
| 질의 중 세대 교체 | 고정 세대로 끝까지 | GENERATION_CHANGED |

- 규칙 제목: 실행 규칙
- 규칙:
  - 시간 예산(초): Local 45, Global 90, Hybrid 150
  - 재시도 곱 상한: LLM 2회 × 노드 1회, 대기는 10초까지
  - 동시성(전역): LLM 4개, Neo4j 세션 8개
  - 병렬 결과는 합치기 리듀서로 모음
- 화면 출처: 플로니 리뷰(2026-10-24), teacher/plan/graphrag-search-flow.md 7절
- 상세 보기 링크: #7-실행-규칙과-실패-대체-플로니-리뷰
- 발표자 노트:
  - 색인용 LLM 호출 설정(429와 5xx에서 6번까지, 한 번에 최대 90초 대기)을 질의에 그대로 쓰면 라우터 하나가 몇 분 멈출 수 있습니다.
  - 그래서 질의 경로는 재시도 횟수와 대기 상한을 따로 둡니다.
  - Hybrid는 후속 질문 검색이 동시에 여러 개 돌므로 LLM과 Neo4j 세션의 전역 상한이 필요합니다.
  - LangGraph API 이름(Send, RetryPolicy 등)은 구현 전에 공식 문서로 다시 확인합니다.

## 슬라이드 10. 바깥 계약
- 제목: 바깥 계약: 오래 걸리는 검색은 단계 이벤트로 흘려 보냄
- 리드문: 안쪽 흐름이 단계마다 이벤트를 내고, API는 받아서 전달만 해 경계를 얇게 유지함
- 이벤트: route | fallback | stage(반복) | evidence | answer.delta | citations | done 또는 error
- 이벤트 주석: fallback은 대체할 때만 보냄. warning은 아무 때나, 15초마다 heartbeat
- 표 열 너비: [3.0, 11.9]

| 응답 필드 | 내용 |
|---|---|
| route | 요청 mode, 라우터 판단, 실제 실행 경로와 이유 |
| fallback | 대체했을 때만: 원래 경로, 바뀐 경로, 알림 코드 |
| citations | 인용 id, 종류(원문 또는 보고서), 제목, 짧은 발췌, 검증 여부 |
| warnings | MAP_PARTIAL 같은 부분 실패 코드와 설명 |
| usage | 요청별 LLM 호출 수, 토큰, 걸린 시간 |

- 콜아웃: 답 토큰은 검증 전 초안이며, 인용 검증은 citations 이벤트에서 확정함. 프롬프트 원문과 회원번호는 응답에 넣지 않음
- 화면 출처: 스택니 리뷰(2026-10-24), teacher/plan/graphrag-search-flow.md 8절
- 상세 보기 링크: #8-바깥-계약-스택니-리뷰
- 발표자 노트:
  - 검색 함수가 마지막에 결과 하나만 돌려주면 진행 표시를 할 수 없습니다. 단계 이벤트를 내는 생성기로 만듭니다.
  - 답을 JSON 모드로 받으면 토큰을 흘려 보낼 수 없습니다. 답은 평문으로 흘리고 인용 검사는 끝난 뒤에 합니다.
  - 공개 mode 이름은 local, global, hybrid로 정리하고, 보고서를 뺀 비교용은 디버그 옵션으로 뺍니다.
  - 연결이 끊기면 진행 중인 LLM 호출을 취소합니다.

## 슬라이드 11. 팀원 리뷰 결과
- 제목: 팀원 리뷰: 네 명 모두 「수정 후 사용」, 지적 사항은 모두 반영함
- 리드문: 같은 초안을 검색 품질, 실행 흐름, API 계약, 교육 관점에서 따로 보고 클로니가 엇갈린 의견을 정리함
- 표 열 너비: [2.4, 9.6, 2.9]

| 리뷰어 | 핵심 지적 | 반영 |
|---|---|---|
| 지식니(검색 품질) | 회원번호는 청크 본문에 없으니 필터로. 원문 700자 절단. 고객군이 그래프에 없음. 거절 지표 | 4, 5, 6, 11장 |
| 플로니(실행 흐름) | 재시도 중첩, 전체 시간 예산, 전역 동시성 상한, 세대 고정 위치, 장애 표 보강 | 3, 9장 |
| 스택니(API 계약) | 단계 이벤트 생성기, 대체 알림 코드, 스트리밍과 인용 검사 순서, 원문 비노출 | 10장 |
| 에듀니(교육) | 「하이브리드」 세 뜻 혼동, 외부 수치 출처 표시 | 1, 2장 |

- 결정 제목: 엇갈린 의견과 결정
- 결정:
  - Global 보고서 선택: LLM 관련도 평가 대 전부 읽기 → 50개 이하면 전부, 넘으면 동적 선택
  - Hybrid 후속 질문 수: 3개 대 주제당 1개(상한 6) → 주제당 1개, 상한 5, 검색만 하고 답은 한 번
  - 이름: 「주제 후 근거 검색」 또는 drift로 개명 제안 → 요청 이름 Hybrid Search를 쓰고 풀이 이름을 함께 표기
- 화면 출처: 팀원 리뷰 기록(2026-10-24), teacher/plan/graphrag-search-flow.md 11절
- 상세 보기 링크: #11-리뷰-기록
- 발표자 노트:
  - 리뷰는 토론형으로 진행했습니다. 네 명이 같은 초안을 서로의 의견을 보지 않고 따로 읽었습니다.
  - 리뷰에서 나온 사실 주장 세 가지(회원번호 0건, 700자 넘는 청크 131개, 429 재시도 6회와 최대 90초 대기)는 클로니가 다시 확인했습니다.

## 슬라이드 12. 최종안과 실행 순서
- 제목: 최종안: 측정부터 하고, Local을 다지고, Global과 Hybrid를 차례로 넓힘
- 리드문: 평가셋에 경로 라벨과 거절 지표를 먼저 넣어 기준선을 잰 뒤 단계마다 같은 지표로 비교함
- 표 열 너비: [2.9, 4.7]

| 지표 | 정의 |
|---|---|
| 라우팅 정확도 | 정답 경로와 판단 일치율 |
| 검색 적중률 | 정답 문장이 근거에 든 비율 |
| 근거 일치율 | 답의 주장 중 근거가 받치는 비율 |
| 거절률 | 올바른 거절과 잘못된 거절 |
| 지연과 토큰 | 경로별 p50, p95 |

- 순서:
  1. 측정: 평가셋 경로 라벨, 원문 1600자, 거절 지표로 기준선
  2. Local 보강: 식별자 필터, 갈래별 쿼터, 후보 25 + 리랭커, 0건 처리
  3. 실행 규칙: 세대 고정, 마감 시각, 재시도 곱 상한, 전역 동시성
  4. Global: 보고서 map-reduce, 인덱싱에 고객군 추가
  5. Hybrid: Primer → Follow-up → 합치기, 단계 이벤트 API
- 화면 출처: teacher/plan/graphrag-search-flow.md 9 ~ 10절, Ragas faithfulness 정의
- 상세 보기 링크: #10-실행-순서-로드맵
- 발표자 노트:
  - 평가셋에는 지금 정답 경로 필드가 없어 라우팅 정확도를 잴 수 없습니다. 라벨부터 붙입니다.
  - 원문을 700자에서 자르면 검색이 맞아도 정답 문장이 잘려 적중률이 낮게 나옵니다. 상한을 올린 뒤 기준선을 잽니다.
  - 거절률 목표값은 실측 전까지 가정값으로 둡니다.
  - https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
