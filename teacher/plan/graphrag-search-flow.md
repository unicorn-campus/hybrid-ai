# GraphRAG 검색 워크플로우 구성안 (OpenSearch + Neo4j)

| 항목 | 내용 |
|------|------|
| 상태 | **최종안 v1.1** (2026-10-24, 토론형 리뷰 반영. 특정 구현 코드 언급을 지움) |
| 작성 | 클로니(초안, 수렴). 조사 보조(Sonnet), 리뷰 지식니, 플로니, 스택니, 에듀니 |
| 저장소 | OpenSearch `card_chunks-{세대}`(BM25 + kNN), Neo4j 엔티티 그래프 + Chunk 노드 + Community 보고서 |
| 인덱스 | 벡터 `kg_entity_embedding`, `kg_community_embedding`(KURE-v2 768차원). 커뮤니티는 GDS Leiden 한 단계(계층 없음) |
| 슬라이드 | `teacher/plan/graphrag-search-flow.pptx`(스크립트 `graphrag-search-flow-slides.md`) |
| 후속 문서 | `teacher/plan/graphrag-agentic-search.md`(이 구성안을 벡터 검색 Agentic 워크플로우 뼈대로 다시 짠 설계) |

## 1. 왜 세 가지 검색인가 (WHY)

상담 지원 질문은 답이 나오는 자리에 따라 나뉨(평가셋 `hands-on/solutions/eval-set.json` 25문항 기준).

| 질문 유형 | 예시 | 답이 있는 자리 | 검색 방식 |
|-----------|------|---------------|-----------|
| 특정 대상의 사실(Q01 ~ Q17) | 「연회비 면제 조건은?」(Q01), 「M-1042 회원이 처음 요청한 것은?」(Q14) | 청크 몇 개와 그 안의 엔티티 | **Local Search** |
| 여러 문서를 모은 경향(Q23, Q24) | 「고객군별 불만을 주제별로」(Q23), 「받아들인 제안의 공통점」(Q24) | 커뮤니티 보고서 여러 개 | **Global Search** |
| 경향 + 그 경향의 근거 사실(Q25) | 「불만 주제별로 관련 약관 조항과 카드 혜택」(Q25) | 보고서로 주제를 잡고, 주제마다 원문 | **Hybrid Search** |
| 답할 수 없음(Q18 ~ Q22) | 대상은 있지만 문서에 사실이 없음(함정 질문) | 없음 | Local로 찾고 「근거에 없음」으로 답함 |

### 용어 약속 (리뷰 반영)

| 이름 | 뜻 |
|------|-----|
| Local Search | 청크와 엔티티에서 출발해 이웃, 원문, 보고서를 모아 사실을 답함 |
| Global Search | 커뮤니티 보고서들로 여러 문서의 경향을 답함 |
| Hybrid Search(주제 후 근거 검색) | Global로 주제를 잡고 주제마다 Local로 근거를 찾음(Microsoft DRIFT의 축소판) |
| 키워드와 벡터 순위 융합(RRF) | BM25 순위와 kNN 순위를 합쳐 한 줄로 세움. 「하이브리드」라고 부르지 않음 |

- 「Hybrid Search」는 요청 받은 이름을 그대로 쓰되, 슬라이드에서는 항상 「주제 후 근거 검색」을 함께 적음  
  (에듀니와 지식니는 개명을 제안했으나, 사용자 요구 용어와 Microsoft 문서의 Local, Global 대비를 살리는 쪽으로 클로니가 정함)
- 후속 설계(`graphrag-agentic-search.md`)에서는 모드를 local과 global 둘로 줄이고, Hybrid의 방향은 두 모드 안으로 넣음

## 2. 실무 Best Practice 조사 요약

| # | Best Practice | 근거 |
|---|---------------|------|
| 1 | 질문 유형별로 경로를 나눔. 단순 사실은 rerank RAG가 GraphRAG보다 정확(60.9 대 49.3), 요약과 추론은 GraphRAG가 앞섬 | GraphRAG-Bench https://arxiv.org/html/2506.05690v3 |
| 2 | 청크 검색은 BM25와 벡터를 RRF(k 60)로 합침. 점수 분포가 달라도 한쪽이 지배하지 않음 | https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/ |
| 3 | kNN 후보 수는 최종 개수의 3배 이상. 필터는 BM25와 벡터 갈래에 똑같이 적용 | https://docs.digitalocean.com/products/vector-databases/opensearch/concepts/hybrid-search/ |
| 4 | Local은 엔티티를 진입점으로 관계, 원문, 커뮤니티 보고서를 한 컨텍스트에 섞고 몫을 나눔(원문 0.5, 커뮤니티 0.15, 12000 토큰) | Microsoft GraphRAG `docs/query/local_search.md`, `config/defaults.py` |
| 5 | 엔티티 찾기도 벡터에 키워드를 섞음. 이름이 중요한 질문을 놓치지 않음 | https://neo4j.com/blog/developer/microsoft-graphrag-neo4j/ |
| 6 | 그래프 탐색은 홉 수와 후보 수를 제한함(결과 폭증 방지) | https://graphrag.com/reference/graphrag/graph-enhanced-vector-search/ |
| 7 | Global은 관련 보고서만 골라 map-reduce. 동적 선택으로 토큰 77% 절감, 품질 차이 유의하지 않음 | https://www.microsoft.com/en-us/research/blog/graphrag-improving-global-search-via-dynamic-community-selection/ |
| 8 | 넓은 질문을 사실까지 내리려면 DRIFT: 보고서로 초안과 후속 질문 → 후속 질문마다 Local | Microsoft GraphRAG `docs/query/drift_search.md` |
| 9 | 라우터로 그래프 호출을 줄임. 불확실하면 질문 다시 쓰기 | https://arxiv.org/abs/2609.02894 |
| 10 | 평가는 근거 일치율(faithfulness)과 검색 재현율(Context Recall)을 나눠 봄 | https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/ |

- 비용 감각(외부 벤치마크, 우리 측정값 아님): 질의당 평균 토큰 벡터 RAG 879, GraphRAG Local 38707,  
  Global 331375(GraphRAG-Bench, GPT-4o-mini, Novel 데이터셋)
- Neo4j `HybridRetriever`, `HybridCypherRetriever`는 filters를 지원하지 않음 → 세대 필터가 필요한 우리 구성은 Cypher에서 직접 거름
- 미확인: 라우터 실패 시 기본값, 질의 캐시, 세대 필터를 다룬 1차 자료는 찾지 못함(아래 해당 설계는 팀 판단)

## 3. 전체 흐름

```
질문 → ⓪ 앞단 → ① 라우터 → Local | Global | Hybrid → ⑤ 뒷단(근거 묶기, 답 스트리밍, 인용 검사)
       (세대 고정, 마감 시각, 질문 정리, 임베딩 1회)
```

| 단계 | 하는 일 |
|------|---------|
| ⓪-1 세대 고정 | 첫 노드에서 `active_generation.json`을 한 번 읽어 generation과 인덱스 이름을 고정. 질의 끝까지 바꾸지 않음 |
| ⓪-2 마감 시각 | `deadline_at` = 시작 + 경로 예산(Local 45초, Global 90초, Hybrid 150초). 모든 노드가 들어갈 때 확인 |
| ⓪-3 질문 정리 | 카드명 별칭 사전으로 정식 이름, 회원번호(M-0000)를 가명 규칙으로 `member_pseudo_id`로 바꿈 |
| ⓪-4 질문 임베딩 | KURE-v2로 한 번만 계산해 모든 갈래가 같이 씀 |
| ① 라우터 | 규칙 먼저(회원번호, 카드명 → Local) → LLM 3분류(local, global, hybrid). 꼴 오류 2번이면 Local |
| ⑤ 뒷단 | 사실은 원문 우선, 보고서는 맥락. 답은 평문으로 흘려 보내고, 끝난 뒤 인용 id가 근거 묶음에 있는지 검사 |

## 4. Local Search

1. 범위 좁히기: ⓪-3의 `member_pseudo_id`, `product_id`를 **필터**로 씀(OpenSearch term 필터, Cypher 조건).  
   상담 청크 본문에 회원번호가 없어서(260청크 중 0건) 정확 일치 시작점으로는 못 찾음(지식니 확인)
2. 시작점 찾기(병렬)
   - 청크 갈래: BM25 25개 + kNN 25개 → RRF(k 60) → 리랭커(선택) → 청크 4 ~ 6개 → Neo4j Chunk → 엔티티
   - 엔티티 갈래: `kg_entity_embedding` 벡터 8개(세대 필터)
   - 이름 갈래: 정식 카드명, 조항 번호로 엔티티 정확 일치(Cypher, 세대 조건 직접)
3. 그래프 넓히기: 1-hop 상한. 이웃 엔티티(질문과 비슷한 순 6개), 원문 청크(FROM_CHUNK), 커뮤니티 보고서(IN_COMMUNITY).  
   상담 질문은 「첫 상담」과 「가장 최근 상담」을 `consult_date`로 먼저 고정 슬롯에 넣음(Q14, Q16)
4. 고르고 자르기: 갈래별 최소 쿼터(청크 갈래 원문 3, 엔티티 갈래 원문 2 이상) 뒤 토큰 예산으로 자름.  
   몫은 원문 0.5, 엔티티와 관계 0.35, 보고서 0.15에서 출발. 원문 상한 1600자(청크 260개 중 131개가 700자를 넘음)
5. 0건 처리: 세 갈래 모두 0건이면 BM25만 한 번 더. 그래도 0건이면 LLM을 부르지 않고 「근거에 없음」
6. 답: 원문 id 인용, 근거에 없으면 「근거에 없음」

## 5. Global Search

1. 보고서 고르기: 보고서가 50개 이하면 **전부** 묶음으로 나눠 map(재현율 우선). 50개를 넘으면 벡터 후보 + LLM 관련도 점수로 거름
2. Map: 보고서 묶음마다 LLM이 「중간 답 + 중요도 점수(0 ~ 100)」. 묶음당 45초
3. Reduce: 점수 0 버림, 점수 높은 순으로 예산까지 모아 최종 답. 보고서 제목 인용
4. 선행 과제(인덱싱): 고객군(신규가입, 장기보유, VIP 등)이 그래프에 없음 → 색인 때 파일명의 segment를 Consultation 속성으로 넣고  
   보고서 입력에 segment 분포를 넘김. 그 전까지 Q23은 「고객군별」 요구를 맞추지 못함(지식니 확인)

## 6. Hybrid Search (주제 후 근거 검색)

1. Primer: Global 보고서로 주제 목록과 1차 답, 주제당 후속 질문 1개(상한 5개). MS 기본 20개, 깊이 3 → 교육용으로 줄임
2. Follow-up: 후속 질문마다 Local Search의 **검색까지만** 함(주제별 답은 만들지 않음, 주제당 원문 3개). 라운드 1회 고정  
   종료 조건: 라운드 소진 또는 새 근거 0건. 컨텍스트 몫은 원문 0.9, 보고서 0.1(MS DRIFT 기본값)
3. 합치기: 주제(보고서) 아래에 근거 사실(원문)을 붙여 LLM 한 번으로 최종 답. 근거마다 topic_id
- LLM 호출: 라우터 1 + Primer 1 + 합치기 1 = 3회(MS DRIFT는 후속 질문마다 중간 답을 만들지만, 비용을 묶으려고 뺌)

## 7. 실행 규칙과 실패 대체 (플로니 리뷰)

| 규칙 | 값 | 이유 |
|------|----|------|
| 전체 시간 예산 | Local 45초, Global 90초, Hybrid 150초. 넘으면 `degrade` | 늦은 답보다 부분 답이 나음 |
| 재시도 곱 상한 | 질의 경로는 LLM 내부 재시도 2회, 대기 10초 상한, 노드 재시도 1회 | 색인용 LLM 호출 설정(429에 6회, 최대 90초 대기)을 질의에 그대로 쓰면 라우터 하나에서 수 분 멈출 수 있음 |
| 동시성 | LLM 전역 세마포어 4, Neo4j 세션 8 | Hybrid가 스스로 429를 만들지 않게 함 |
| 병렬 상태 | 목록 필드(seeds, chunks, entities, reports)에 합치기 리듀서 | 병렬 노드 갱신 충돌 방지 |

| 상황 | 대체 | 바깥 알림(code) |
|------|------|----------------|
| 라우터 답 꼴 오류 | 2번 더 묻고 끝내 틀리면 Local(보고서 포함) | `ROUTER_BAD_FORM` |
| 커뮤니티 보고서 없음 | Global, Hybrid를 Local로 내림 | `NO_REPORTS` |
| OpenSearch 장애 | 엔티티 갈래와 이름 갈래만으로 Local | `SEARCH_ENGINE_DOWN` |
| Neo4j 장애 | 2초 뒤 1번 다시 연결. 실패하면 OpenSearch 원문만으로 답 | `GRAPH_DOWN` |
| 임베딩 실패 | BM25 단독 Local | `EMBED_FAILED` |
| LLM 429 계속 | Global은 받은 map만 Reduce, Local은 근거만 보이고 답 생략 | `LLM_RATE_LIMIT` |
| Map 일부 시간 초과 | 받은 중간 답만으로 Reduce, 빠진 보고서 수 표시 | `MAP_PARTIAL` |
| 질의 중 세대 교체 | 고정 세대로 끝까지. 인덱스 없음 오류면 세대 1번 다시 읽음 | `GENERATION_CHANGED` |

## 8. 바깥 계약 (스택니 리뷰)

- 요청: `question`, `mode`(auto, local, global, hybrid). 비교용 스위치는 디버그 옵션으로만
- 응답: `request_id`, `generation`, `answer`, `route`(requested, decided, executed, reason), `fallback`(from, to, code),  
  `citations`(id, kind, title, snippet, verified), `warnings`(code, detail), `usage`(llm_calls, tokens, elapsed_ms, 요청별)
- SSE 순서: `route` → (`fallback`) → `stage` 반복 → `evidence`(Hybrid는 topic_id) → `answer.delta` → `citations` → `done` 또는 `error`.  
  `warning`은 아무 때나, 15초마다 heartbeat
- 안쪽 흐름은 단계 이벤트를 내는 생성기로 만들고, 경로 함수는 받아서 전달만 함. 프롬프트 원문과 회원번호는 응답에 넣지 않고 서버 로그에만

## 9. 평가 기준

| 지표 | 정의 | 측정 전 준비 |
|------|------|-------------|
| 라우팅 정확도 | 정답 경로와 라우터 판단 일치율 | 평가셋에 `route` 라벨 추가(지금은 측정 불가) |
| 검색 적중률(Context Recall) | relevance `clues`(정답 단서)가 근거 묶음에 있는 비율 | 원문 상한 1600자로 둔 뒤 측정 |
| 근거 일치율(faithfulness) | 답의 주장 중 근거가 뒷받침하는 비율 | Ragas 또는 LLM 판정 |
| 올바른 거절률, 잘못된 거절률 | Q18 ~ Q22에서 「근거에 없음」 비율, 답할 수 있는 문항에서 거절한 비율 | 목표는 실측 전까지 가정값 |
| 지연, 토큰 | 경로별 p50, p95. 노드별 `stage_ms`, `tokens`, 찾은 id | 상태에 기록 |

## 10. 실행 순서 (로드맵)

1. 측정 먼저: 평가셋 `route` 라벨, 원문 상한 1600자, 거절 지표 → 기준선 측정
2. Local 보강: 식별자 필터, 갈래별 쿼터, 풀 25 + 리랭커, 0건 처리
3. 실행 규칙: 세대 고정을 첫 노드로, 마감 시각, 재시도 곱 상한, 전역 세마포어
4. Global map-reduce(보고서 50개 이하 전수)와 인덱싱 segment 보강
5. Hybrid Search(Primer → Follow-up → 합치기), SSE 계약

## 11. 리뷰 기록

| 리뷰어 | 판정 | 핵심 지적 | 반영 |
|--------|------|-----------|------|
| 지식니(검색 품질) | 수정 후 사용 | 회원번호가 청크에 없음 → 필터로. 원문 700자 절단. 고객군이 그래프에 없음. 거절 지표와 경로 라벨 | 모두 반영(4, 5, 9절) |
| 플로니(실행 흐름) | 수정 후 사용 | 재시도 중첩, 전체 시간 예산, 전역 세마포어, 세대 고정 위치, 장애 표 보강 | 모두 반영(3, 7절) |
| 스택니(API 계약) | 수정 후 사용 | 단계 이벤트 생성기, fallback과 warnings 코드, 스트리밍과 인용 검사 순서, 원문 비노출 | 모두 반영(8절) |
| 에듀니(교육) | 수정 후 사용 | 「하이브리드」 세 뜻 혼동, 벤치마크 수치 출처 표시 | 용어 약속표로 반영. 개명은 하지 않음(1절) |

- 엇갈린 의견과 결정
  - Global 보고서 선택: 초안(벡터 후보 + LLM 관련도) 대 지식니(보고서 전수) → 50개 이하면 전수, 넘으면 동적 선택
  - Hybrid 후속 질문 수: 초안 3개 대 지식니 「주제당 1개, 상한 6」 대 플로니 「3개, 동시성 부담」 →  
    주제당 1개, 상한 5, LLM 세마포어 4로 차례 실행
  - 이름: 에듀니 「주제 후 근거 검색」, 지식니 `drift` 제안 → 사용자 요구 이름 Hybrid Search 유지, 풀이 이름을 함께 표기
- 사용자 결정(2026-10-24): 특정 구현 코드 언급과 「구현됨 대 확장」 표시를 문서와 슬라이드에서 모두 지움
