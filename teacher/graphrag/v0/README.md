# GraphRAG 인덱싱 v0 (교육용)

「인덱싱 워크플로우 구성안」 장표를 그대로 옮긴 교육용 코드.  
계층 구조(Layered Architecture) 없이 파일 하나가 워크플로우 하나를 맡는 단순한 파이썬 함수로 작성함.

- 오케스트레이터 워크플로우: `orchestrator.py` (① 세대 ID 발급 → ② 공통 단계 → ③ 인덱스 구축 → ④ 검증 → ⑤ 게시)
- KG 구축 서브 워크플로우: `kg_build.py` (준비 K1 ~ K3, 반영 K4 ~ K6, 정리 K7), `community.py` (K8 커뮤니티 요약, 선택)
- 검색엔진 인덱싱 서브 워크플로우: `search_index.py` (준비 S1 ~ S2, 반영 S3)
- 그래프 검색(질의): `graph_search.py` (질문 판단 → 거시 검색 또는 하이브리드 검색 → 답)

## 파일 구성

| 파일 | 하는 일 |
|------|--------|
| `config.py` | 경로, 접속 주소, 모델 이름, BM25 조절값 |
| `common.py` | JSON 읽고 쓰기, 해시, 문서 키, KURE-v2 임베딩, Groq LLM |
| `orchestrator.py` | ① ~ ⑤, 전체 재색인(full)과 증분 색인(incremental) |
| `kg_build.py` | `prepare()` K1 ~ K3, `apply()` K4 ~ K6, `cleanup()` K7 |
| `search_index.py` | `prepare()` S1 ~ S2, `apply()` S3 |
| `lexical.py` | S2 토크나이저와 카드 별칭 규칙(`hands-on/solutions/rag/indexing/core_indexing.py`에서 옮김) |
| `community.py` | `k8_summarize()` K8 커뮤니티 요약(GDS Leiden 묶기, LLM 보고서, 임베딩, 적재), `verify()` ④ 추가 검사 |
| `tests/test_community.py` | K8 단위 시험(묶음 결정성은 실제 GDS로, 보고서 재사용, 옵션을 껐을 때 무변화) |
| `graph_search.py` | 질문 판단(`classify`), 거시 검색(`global_search`), 하이브리드 검색(`chunk_search`, `chunk_graph`, `hybrid_search`), 답하기 |
| `tests/test_graph_search.py` | 그래프 검색 시험(질문 판단 해석, 근거 정리, 순위 융합. 실제 Neo4j와 OpenSearch에서 활성 세대만 찾는지) |
| `tools/export_chroma_chunks.py` | 이 저장소 Chroma(`card_docs`) 청크를 v0 입력 꼴로 바꿔 `data/chroma-chunks.json`에 저장 |
| `tools/make_sample.py` | 시험용 표본 청킹 결과 두 개(전체용, 증분용) |
| `tools/inspect_generation.py` | 활성 세대의 그래프와 인덱스 요약(읽기만 함) |
| `tools/reset.py` | 이 저장소 v0가 만든 세대(`gen-hai-`로 시작)만 지움. 그냥 돌리면 대상만 세고 `--yes`일 때 지움.  
활성 세대는 `--all`을 줄 때만 지움. Neo4j 노드(Community 포함)와 검색엔진 인덱스는 지우고, data 폴더 기록은 `data/_old/`로 옮김 |
| `tools/snapshot_stores.py` | Neo4j 세대별 노드 수와 Community 수, `card_chunks-*` 인덱스와 별칭을 JSON으로 남김(읽기만 함) |
| `tools/search_check.py` | 평가 질문으로 BM25, 벡터, 엔티티 벡터, 커뮤니티 벡터 상위 결과를 보여 줌(읽기만 함) |

## 단계와 코드

| 단계 | 함수 | 하는 일 |
|------|------|--------|
| ① 세대 ID 발급 | `step1_issue_generation` | `gen-hai-{실행 이름}-{해시 8자리}`. 입력 파일 지문과 설정 지문이 활성 세대와 같으면 할 일 없음(사전 검사) |
| ② 공통 단계 | `step2_common` | 청킹 결과 파일(prepared-chunks.json 꼴, 기본은 `data/chroma-chunks.json`)을 세대 폴더에 고정 |
| ③ 인덱스 구축 | `step3_build_full` | 전체 재색인: KG 구축과 검색엔진 인덱싱을 처음부터 끝까지 병렬 |
| K1 추출 단위 나누기 | `kg_build.k1_split_units` | 약관은 조항 제목 줄로 나눔(승인 기록의 규칙), 나머지는 청크 그대로.  
추출 단위는 LLM 입력에만 쓰고 그래프 노드가 되지 않음 |
| K2 추출, K3 가지치기 | `kg_build._k2_k3_one` | 머리줄 + 단위 본문을 LLM에 넣고, 스키마 밖 노드와 관계는 지움 |
| K4 적재 | `kg_build.apply` | 청크 노드(라벨 Chunk, 검색엔진 청크와 1대1, `chunk_id` 같음)와 엔티티를 Neo4j에 씀.  
엔티티는 자기 추출 단위가 나온 청크마다 FROM_CHUNK로 이음(겹친 조항은 두 청크). 모든 노드에 generation |
| K5 병합 | `kg_build.k5_merge` | 스키마 고유 속성(UNIQUENESS) 값이 같은 노드를 합침. 이번에 들어온 값만.  
합친 뒤 같은 엔티티와 청크 사이 FROM_CHUNK 중복을 하나로 줄임(`dedup_from_chunk`) |
| K6 노드 설명 임베딩 | `kg_build.k6_embed_descriptions` | 「라벨: 속성=값」을 KURE-v2로 임베딩, 벡터 인덱스 `kg_entity_embedding` |
| K7 청크 정리 | `kg_build.cleanup` | 바뀐 문서의 옛 청크 노드와 고아 엔티티를 지움(증분 색인에서만) |
| K8 커뮤니티 요약(선택) | `community.k8_summarize` | `--communities`로 켬. 엔티티 그래프만(청크 노드, FROM_CHUNK 제외) GDS Leiden으로 묶고,  
엔티티 3개 이상 묶음마다 LLM 보고서(title, summary, findings와 근거 엔티티) → KURE-v2 임베딩 →  
`(:Community)`와 `(엔티티)-[:IN_COMMUNITY]->(:Community)` 적재, 벡터 인덱스 `kg_community_embedding`.  
전체 재색인은 K6 뒤, 증분 색인은 K7 뒤. 구성원 지문(member_hash)이 같은 보고서는 다시 씀 |
| S1 임베딩 | `search_index.prepare` | 본문 해시가 앞 세대에 있으면 벡터 재사용, 바뀐 청크만 임베딩 |
| S2 키워드 분석 | `search_index.prepare` | RAG 인덱싱 예제와 같은 Kiwi 토크나이저 + 카드명 사전과 별칭(`lexical.py`) |
| S3 적재 | `search_index.apply` | 문서(doc_id)마다 지우고 넣기. 인덱스 이름 `card_chunks-{세대 ID}`, BM25 k1 1.5 |
| ④ 검증 | `step4_verify` | 검색엔진 chunk_id 집합 = 전체 청크 = KG 청크 노드 chunk_id 집합, 청크 하나에 노드 하나인지 비교.  
K8을 켰을 때만 「모든 Community에 summary와 embedding, 빈 묶음 없음, 구성원이 모두 현재 세대 엔티티」도 봄 |
| ⑤ 게시 | `step5_publish` | `data/active_generation.json` 하나만 교체 |

- 증분 색인(`run_incremental`): 바뀐 문서만 골라 준비(K1 ~ K3, S1 ~ S2)는 병렬로 하고,  
  반영은 K4 ~ K6 → S3 → K7 → 기록 갱신 순서로 함. 그래프는 먼저 넣고 나중에 지워서 바뀌는 동안에도 검색이 찾은 chunk_id가 그래프에 있음
- 준비 결과는 `data/generations/{세대}/kg_prepared.json`에 보관함. 본문 해시와 스키마가 같은 단위는 LLM을 다시 부르지 않음.  
  추출 단위와 그 단위가 나온 청크 ID 목록(`chunk_ids`)은 이 파일에만 있고 그래프에는 없음
- 서브 워크플로우는 활성 세대 파일을 바꾸지 않음. 게시는 오케스트레이터만 함
- 되돌리기와 옛 세대 정리는 이 흐름 밖에서 함(v0에는 없음)

## 준비

필요한 것: 실행 중인 Neo4j(APOC 포함, K8을 쓰면 GDS도), OpenSearch, `secrets/.env`의 `GROQ_API_KEY`,  
이 저장소 RAG 인덱싱 예제가 만든 Chroma(`hands-on/solutions/rag/indexing/data/chroma`), Hugging Face 캐시의 KURE-v2.  
다른 저장소(hybrid-ai-lab)의 코드나 가상환경은 쓰지 않음.

| 자원 | 위치(`config.py`) |
|------|------------------|
| 그래프 스키마 | `hands-on/solutions/graphrag/schema/doc/{regulation,benefit_guide,consult_log}/` (읽기만 함) |
| 입력 청크 | Chroma collection `card_docs` 260개 → `tools/export_chroma_chunks.py` → `data/chroma-chunks.json` |
| 승인 별칭 | `hands-on/solutions/rag/indexing/aliases_approved.json` (읽기만 함) |
| 비밀값 | `secrets/.env`의 `GROQ_API_KEY`, `backing-services/neo4j/.env`의 `NEO4J_PASSWORD` |
| 임베딩 모델 | `nlpai-lab/KURE-v2` revision `3431f86…`, `~/.cache/huggingface/hub`에 있는 것만 씀 |

가상환경은 이 폴더 안 `.venv`에 만듦. torch는 CPU 판을 먼저 설치함(PyTorch 전용 저장소, 휠 약 124MB).

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python.exe -m pip install -r requirements-torch-cpu.txt
```

```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

KURE-v2가 캐시에 없으면 한 번 받음(약 300MB). 코드는 캐시에서만 읽고 스스로 내려받지 않음.

```bash
.venv/Scripts/hf.exe download nlpai-lab/KURE-v2 --revision 3431f86d399d666083890dbb882aced6708873bc
```

- 설치 뒤 `.venv/Lib/site-packages`는 약 1.3GB(torch 539MB, transformers 115MB, scipy 115MB, kiwipiepy_model 105MB 등)
- 판은 hybrid-ai-lab 1-a 인덱서와 같게 맞춤. 같은 청크의 벡터가 옛 세대(1-a 임베더로 만든 것)와 같음을 확인함(코사인 1.0)
- Chroma 청크의 벡터는 쓰지 않음(Cohere 2048차원이라 KURE-v2 768차원과 다름). 본문과 메타데이터만 읽어  
  S1, K6, K8에서 KURE-v2로 다시 임베딩함
- S2 토큰화 규칙은 이 저장소 RAG 검색기와 같음. hybrid-ai-lab 1-a 토크나이저와 규칙이 달라  
  `gen-hai-sample-003` 이전 세대의 사전 기록으로는 증분 색인을 할 수 없음(새 실행 이름으로 `full`을 다시 돌림)

Neo4j와 OpenSearch는 이 저장소의 compose 파일로 띄움(저장소 루트에서 실행).

```bash
docker compose -f backing-services/neo4j/compose.yml up -d
```

```bash
docker compose -f backing-services/opensearch/compose.yml up -d
```

- Neo4j: 컨테이너 `hybrid-ai-neo4j`(볼륨 `hybrid-ai-neo4j-data`, `-logs`, `-plugins`), `bolt://localhost:7687`,  
  Neo4j 2026.09.0 Community + APOC + GDS.  
  비밀번호는 코드에 두지 않음. 환경변수 `NEO4J_PASSWORD`가 있으면 그것을, 없으면 `backing-services/neo4j/.env`의 값을 읽음
- OpenSearch: 컨테이너 `hybrid-ai-opensearch`(볼륨 `hybrid-ai-opensearch-data`), `http://127.0.0.1:9200`(보안 플러그인 꺼짐, 2.19.1)
- `config.py`의 기본 접속 주소는 이 두 컨테이너임. 다른 곳에 띄웠으면 환경변수 `NEO4J_URI`, `OPENSEARCH_URL`로 넘김
- 두 컨테이너의 볼륨은 이 저장소 전용임(2026-10-24에 hybrid-ai-lab과 함께 쓰던 볼륨에서 분리함).  
  분리 전 습관을 그대로 두어 이 저장소가 만드는 세대는 모두 `gen-hai-`로 시작하고, 증분 색인은 활성 세대가 `gen-hai-`가 아니면 멈추며,  
  `tools/reset.py`는 `gen-hai-` 세대만 지움. 같은 DB에 다른 실험 데이터가 섞여도 v0 세대만 다루게 하려는 것임.  
  예전 세대 기록(hybrid-ai-lab에서 옮겨 온 것, 분리 전 볼륨의 `gen-hai-*`)은 `data/_old/`에 있음

## 실행

```bash
.venv/Scripts/python.exe tools/export_chroma_chunks.py
```

```bash
.venv/Scripts/python.exe tools/make_sample.py
```

```bash
.venv/Scripts/python.exe orchestrator.py full --run sample-001 --chunks data/sample-chunks.json
```

```bash
.venv/Scripts/python.exe orchestrator.py incremental --run sample-002 --chunks data/sample-chunks-v2.json
```

```bash
.venv/Scripts/python.exe tools/inspect_generation.py
```

K8 커뮤니티 요약을 켜려면 `--communities`를 붙임(전체 재색인과 증분 색인 모두).

```bash
.venv/Scripts/python.exe orchestrator.py full --run sample-003 --chunks data/sample-chunks.json --full-reindex --communities
```

```bash
.venv/Scripts/python.exe -m pytest tests -q
```

그래프 검색: 질문을 주면 질문 판단 후 알맞은 검색으로 답함(`--mode global|hybrid|local`로 고정 가능, `--show-context`로 근거 글 출력).

```bash
.venv/Scripts/python.exe graph_search.py --qid Q01 Q09 Q23 Q24 Q25
```

```bash
.venv/Scripts/python.exe graph_search.py "할부로 산 물건은 며칠 안에 철회하나요?" --show-context
```

- `--chunks`를 빼면 Chroma 청크 전체(`data/chroma-chunks.json`, 260개)를 씀.  
  실측(2026-10-24): K2 LLM 297번, K8을 켜면 105번 더, 약 13분
- 같은 입력으로 `full`을 다시 돌리면 사전 검사가 「할 일 없음」으로 끝남. 그래도 새로 만들려면 `--full-reindex`
- 전체 재색인은 활성 세대와 다른 실행 이름으로 해야 함. 같은 이름이면 활성 세대에 덮어쓰게 되어 멈춤
- 실행 이름이 같으면 세대 ID가 같음. 이 저장소에서 처음 쓰는 이름이면 hybrid-ai-lab에서 쓴 이름이어도 앞머리가 달라 겹치지 않음

## 그래프 검색 검증 (2026-10-24, 활성 세대 `gen-hai-full-002-14209840`)

흐름: ① 질문 판단(LLM이 global 또는 hybrid 고름) → ② global이면 커뮤니티 보고서 벡터 검색(`kg_community_embedding`, 상위 5개) →
③ hybrid이면 시작점을 두 갈래로 찾고 둘 다 커뮤니티 보고서까지 따라감 → ④ LLM이 근거만으로 답함  
- 청크 갈래: OpenSearch BM25와 kNN을 순위 융합(RRF)한 청크 4개 → Neo4j에서 그 청크의 엔티티(`FROM_CHUNK`) → 보고서(`IN_COMMUNITY`)  
- 엔티티 갈래: `VectorCypherRetriever`로 `kg_entity_embedding` 상위 8개 → 이웃, 원문, 보고서를 같은 Cypher로 가져옴.  
  이웃은 1-hop 이웃 중 질문 벡터와 코사인 유사도가 높은 6개(정렬 없이 자르면 아무 6개가 남아 2026-10-24에 고침)  

| 질문 | 판단 | 결과 |
|---|---|---|
| Q01 연회비 면제 기준 | hybrid | 「직전 12개월 3,000,000원 이상이면 기본 연회비 전액 면제」(제10조 원문 근거). 정답의 「연체 없음」 조건은 빠짐 |
| Q09 가족돌봄 돌봄 바우처 | hybrid | 「연 1회 90,000원, 발급일부터 180일 분할 사용」으로 정답과 같음. 해당 카드 보고서가 1순위로 붙음 |
| Q23 고객군별 불만 주제 | global | 상담 보고서 5개로 주제별 정리. 실제 고객군(신규가입, VIP 등)이 아니라 불만 주제로 무리를 지음(그래프에 고객군 정보 없음) |
| Q24 받아들인 제안의 공통점 | global | 「정보 제공, 간단한 기능 안내, 선택적 설정 변경」과 예시. 「소비를 늘리는 제안은 거절」은 다루지 않음 |
| Q25 불만별 약관 조항과 혜택 | global | 주제는 나누나 약관 조항은 모두 「근거에 없음」 |

- 처음 구현(엔티티 갈래만)에서는 Q01, Q09가 둘 다 「근거에 없음」이었음. 엔티티 벡터가 다른 카드의 혜택 엔티티만 찾아서,
  청크 갈래(BM25 + kNN)를 더해 해결함  
- Q25를 hybrid로 고정해도 상담 청크만 찾음. 이때 답이 혜택 조건(BenefitCondition)을 「약관 조항」이라 부르고 관련 없는 카드를 붙여,
  global보다 나쁨. 상담과 약관을 잇는 관계가 그래프에 없고 질문 한 번으로는 주제마다 약관을 찾지 못함(주제별 2단계 검색이 필요함)  
- 보고서를 뺀 local과 견줌: Q09는 local도 정답(원문으로 충분). 보고서가 답을 바꾼 사례는 이번 질문들에서 확인하지 못함  
- 시험: `pytest tests` 17개 통과(그래프 검색 9개, 실제 Neo4j와 OpenSearch 연결 시험 포함)  
- LLM(Groq `openai/gpt-oss-120b`): 24번. 자동 판단 실행 두 번(고치기 전과 뒤, 각 10번, 각 약 3만 토큰), 비교 실행(hybrid, local) 4번  
- 실행 기록: 저장소 루트 `.temp/v0-graph-search/`(`auto2.log`, `compare.log`와 JSON)

## 전체 실행 결과 (2026-10-24, 청크 260개, hybrid-ai 전용 볼륨)

Neo4j와 OpenSearch를 hybrid-ai 전용 볼륨(`hybrid-ai-neo4j-data`, `hybrid-ai-opensearch-data`)으로 옮긴 뒤 빈 DB에 다시 색인함.  
앞 세대 `gen-hai-full-001`의 준비 결과(`kg_prepared.json`)와 K8 보고서 기록(`community_reports.json`)을 재사용해 LLM을 부르지 않음.  
재사용은 본문 해시와 스키마 지문(K2), 구성원 지문(K8)이 같을 때만 일어나고, 그래프와 인덱스는 처음부터 새로 씀.

```bash
.venv/Scripts/python.exe orchestrator.py full --run full-002 --chunks data/chroma-chunks.json --full-reindex --communities
```

| 항목 | `full-002` (전용 볼륨) | `full-001` (분리 전 볼륨) |
|------|----------------------|--------------------------|
| 걸린 시간 | 8분 18초 | 13분 22초 |
| LLM 호출(K2 + K8) | 0 + 0번(297개, 105개 재사용) | 297 + 105번, 토큰 1,027,273 + 257,828 |
| S1 임베딩 | 260개(새 DB라 앞 세대 벡터 없음) | 260개 |
| 엔티티(혜택 안내, 상담, 약관) | 1,673(1,317, 199, 157) | 1,673(1,317, 199, 157) |
| 관계 | 5,084 | 5,084 |
| 청크 노드, Community | 260, 105 | 260, 105 |
| 임베딩 없는 엔티티 | 0 | 0 |
| 검색엔진 문서, 별칭 | 260, 없음 | 260, 없음 |
| ④ 검증, ⑤ 게시 | 통과, `gen-hai-full-002-14209840` | 통과, `gen-hai-full-001-807ef9e6` |
| 같은 입력으로 다시 `full` | 「할 일 없음」 | 「할 일 없음」 |

- 검색 확인(Q01, Q09, Q24)은 BM25, 엔티티 벡터, 커뮤니티 벡터 결과와 kNN 1위가 `full-001`과 같음.  
  kNN 2 ~ 3위만 달라짐. 점수가 거의 같은 「이용 기준」 청크끼리(0.912, 0.862 등) 순서가 바뀐 것으로, 근사 검색(HNSW)을 새로 만들어서임
- 빈 DB에서 K6를 처음 돌릴 때 Neo4j가 「`embedding` 속성이 아직 없음」 알림을 한 번 냄. 동작에는 영향 없음

### 분리 전 볼륨 실행 기록 (full-001)



입력: Chroma `card_docs` 260개(약관 15, 혜택 안내 197, 상담 기록 48, 문서 50개).  
모델 Groq `openai/gpt-oss-120b`, 임베딩 KURE-v2(CPU), Neo4j 2026.09.0 Community, OpenSearch 2.19.1.  
그 전에 이 저장소 세대 기록(`data/generations`, 활성 세대 파일)은 `data/_old/`로 옮겨 앞 세대 결과를 재사용하지 않음.

```bash
.venv/Scripts/python.exe orchestrator.py full --run full-001 --chunks data/chroma-chunks.json --full-reindex --communities
```

| 항목 | 결과 |
|------|------|
| 걸린 시간 | 13분 22초(K2와 S1 ~ S3 병렬 5분, K6 임베딩 3분 36초, K8 4분 26초) |
| K1 추출 단위 | 297개(약관 조항 단위 52개, 혜택 안내 197개와 상담 기록 48개는 청크 그대로), 단위가 없는 청크 5개(약관 표지, 메타데이터, 차례, 각주 쪽) |
| K2, K3 | LLM 297번, 토큰 1,027,273(입력 550,713, 출력 476,560), 추출 실패 0개, 가지치기 뒤 노드 1,910개.  
가지치기로 노드가 하나도 안 남은 단위 4개(약관 제8조, 혜택 안내 청크 3개) |
| K4, K5 | 노드 2,170개(청크 노드 260개 포함), 관계 3,451개, 병합 100묶음, FROM_CHUNK 중복 0개 |
| K6 | 노드 설명 임베딩 1,673개, 임베딩 없는 엔티티 0개 |
| K8 | 묶음 135개 중 엔티티 3개 이상 105개 요약, LLM 105번, 토큰 257,828 |
| S1 ~ S3 | 임베딩 260개, 카드명 사전 64개, 별칭 390개, 문서 50개, 260건 적재 |
| ④ 검증, ⑤ 게시 | 통과(검색엔진 260/260, 청크 노드 260개 = 고유 260/260, 커뮤니티 105개), 활성 세대 `gen-hai-full-001-807ef9e6` |
| 같은 입력으로 다시 `full` | ① 사전 검사에서 「할 일 없음」으로 끝남 |

그래프(엔티티 1,673개, 근거 청크의 문서 종류별): 혜택 안내 1,317, 상담 기록 199, 약관 157.  
라벨: BenefitCondition 397, BenefitLimit 324, Benefit 268, BenefitExclusion 264, Proposal 84, Handling 70, ProductGuide 64,  
Clause 51, Complaint 50, Consultation 48, Deadline 23, ReconsiderCondition 17, Requirement 11, TermsDocument 2.  
관계 5,084개(FROM_CHUNK 1,906, IN_COMMUNITY 1,637, 추출 관계 1,541).

검색 확인(`tools/search_check.py Q01 Q09 Q24`, 상위 3개):

| 질문 | BM25 | 벡터(kNN) | 엔티티 벡터 | 커뮤니티 벡터 |
|------|------|-----------|-------------|---------------|
| Q01 연회비 면제 기준(약관 제10조①) | 1위 제10조 | 1위 제10조 | 혜택 한도 노드만 나옴(빗나감) | 카드 혜택 요약만 나옴(빗나감) |
| Q09 가족돌봄 돌봄 바우처(D2-C021-B01) | 1위 `D2-0067`(90,000원, 180일 포함) | 다른 카드 이용 기준 청크(빗나감) | 혜택 한도 노드(빗나감) | 다른 카드 요약(빗나감) |
| Q24 받아들인 제안의 공통점(거시) | 상담 청크 3개(기대 근거 상담은 3위 안에 없음) | 상담 청크 3개 | `decision: 수용` 제안 노드 2개 | 상담 제안 요약 커뮤니티 3개 |

- 사실 질문은 BM25가 가장 잘 찾음. 엔티티 벡터는 「라벨: 속성=값」 설명이 비슷한 혜택 한도 노드가 많아 사실 질문에서 빗나감
- 거시 질문(Q24)은 엔티티 벡터와 커뮤니티 벡터가 「수용한 제안」을 모아 줌. 답을 만드는 검색기는 v0에 없어 답의 정확도는 재지 않음

## 이 저장소 표본 실행 결과 (2026-10-24)

입력: Chroma `card_docs` 260개 → `data/chroma-chunks.json`(문서 50개) → 표본 10개(약관 2, 혜택 안내 4 한빛 가족돌봄, 상담 4).  
모델 Groq `openai/gpt-oss-120b`, 임베딩 KURE-v2, Neo4j 2026.09.0 Community, OpenSearch 2.19.1.

| 실행 | 결과 |
|------|------|
| 단위 시험 | 8개 통과(GDS 실제 실행 포함) |
| 전체 재색인 `sample-003` (`--communities`) | K1 단위 18개, K2 LLM 0번(18개 재사용), K4 노드 95개(청크 노드 10개 포함), 관계 152개, K5 5묶음,  
K6 77개, K8 묶음 16개 중 12개 요약(LLM 3번, 재사용 9개), S3 10건, ④ 통과(10/10, 커뮤니티 12개), ⑤ 게시 |
| 같은 입력으로 다시 `full` | ① 사전 검사에서 「할 일 없음」으로 끝남 |
| 증분 색인 `sample-004` (`--communities`) | 바뀐 문서 2개, K2 LLM 1번(3개 재사용), S1 임베딩 1개(3개 재사용), S3 옛 청크 5건 지우고 4건 넣음,  
K7 옛 청크 노드 5개와 고아 엔티티 31개 지움, K8 LLM 3번, ④ 통과(9/9, 커뮤니티 10개) |
| 같은 입력으로 다시 증분 | 바뀐 문서가 없어 「할 일 없음」 |
| `tools/inspect_generation.py` | 활성 세대 `gen-hai-sample-003-06e0ccea`, 청크 노드 9개, 임베딩 없는 엔티티 0개, 검색엔진 청크 9개 |

- 처음 세대 `sample-001`(K2 LLM 16번, K8 LLM 11번)을 증분한 뒤 같은 실행 이름으로 `full`을 다시 돌리자,  
  같은 세대 ID라 활성 세대에 그대로 덮어써 ④ 검증이 실패함(청크 노드 19개). 그래서 활성 세대와 같은 세대 ID면  
  전체 재색인을 멈추게 고쳤고, 망가진 그 세대는 지움
- 이 표본의 약관 청크 두 개(`D1-0005`, `D1-0006`)는 두 청크에 걸친 조항이 없음(`두 청크에 이어진 조항: []`).  
  Chroma 청킹이 hybrid-ai-lab 1-a 청킹과 달라 표본 성격이 바뀐 것임

## hybrid-ai-lab 의존 제거 뒤 결과 (2026-10-24)

환경변수 `HYBRID_AI_LAB` 없음, `sys.path`에 hybrid-ai-lab 경로 없음, `.venv`에 hybrid-ai-lab을 가리키는 `.pth` 없음.

| 실행 | 결과 |
|------|------|
| `pytest tests/` | 8개 통과(GDS 실제 실행 포함) |
| 전체 재색인 `sample-006` (`--communities`) | K2 LLM 2번(16개 재사용), K4 노드 95개, 관계 152개, K6 77개, S1 임베딩 2개(8개 재사용),  
S2 카드명 사전 1개와 별칭 18개(승인 별칭 포함), K8 12개 요약(LLM 4번), ④ 통과(10/10, 커뮤니티 12개), ⑤ 게시 |
| 증분 색인 `sample-007` | 기록된 사전으로 토크나이저를 다시 만들어 씀. K2 LLM 1번, K7 옛 청크 노드 5개와 고아 엔티티 31개 지움, ④ 통과(9/9) |

## 표본 실행 결과 (2026-10-23, hybrid-ai-lab에서 실행, 청크 노드 1대1 구조)

표본: 약관 청크 2개(조항이 겹치는 이웃 청크), 혜택 안내 청크 4개(한빛 가족돌봄), 상담 기록 청크 4개.  
모델 Groq `openai/gpt-oss-120b`, Neo4j 2026.09.0 Community, OpenSearch 2.19.1.  
앞 세대(sample-001) 준비 결과를 재사용해 LLM은 바뀐 단위만 부름.

| 실행 | 결과 |
|------|------|
| 전체 재색인 `sample-003` (`--full-reindex`) | K1 단위 24개(겹친 조항 2개는 청크 2개에서 나옴), K2 LLM 2번(22개 재사용, 토큰 9,088), K4 노드 122개(청크 노드 10개 포함), 관계 216개, K5 병합 3묶음, FROM_CHUNK 중복 0개, K6 임베딩 93개, S3 10건, ④ 통과(검색엔진 10/10, 청크 노드 10개 = 고유 10/10), ⑤ 게시 |
| 같은 입력으로 다시 `full` | ① 사전 검사에서 「할 일 없음」으로 끝남 |
| 증분 색인 `sample-004` (상담 1건 본문 수정, 혜택 청크 1개 뺌) | 바뀐 문서 2개. K2 LLM 1번(3개는 재사용), S1 임베딩 1개(3개 재사용), 반영 순서 K4 ~ K6 → S3(옛 청크 5건 지우고 4건 넣음) → K7(옛 청크 노드 5개, 고아 엔티티 35개 지움), ④ 통과(검색엔진 9/9, 청크 노드 9개 = 고유 9/9) |
| 같은 입력으로 다시 증분 | 바뀐 문서가 없어 「할 일 없음」 |
| 전체 재색인 `sample-005` (필드 이름 `chunk_ids`로 바꾼 뒤) | K1 단위 24개, K2 LLM 2번(22개 재사용, 토큰 8,886), K3 엔티티 110개, K4 노드 120개(청크 노드 10개 포함), 관계 212개(FROM_CHUNK 120, 추출 관계 92), K5 병합 3묶음(엔티티 110 → 91), K6 임베딩 91개, ④ 통과(10/10) |
| 증분 색인 `sample-006` | K4 노드 35개(청크 노드 4개 포함), 관계 64개, K5 병합 3묶음(새 엔티티 31개 중 5개가 기존 노드와 합쳐짐), K7 옛 청크 노드 5개와 고아 엔티티 33개 지움, ④ 통과(9/9) |

- 두 청크에 걸친 조항 제16조와 제16조의2는 엔티티가 두 청크 노드에 모두 이어짐(`tools/inspect_generation.py`로 확인)
- K5 병합 예: 조항 16개에서 각각 뽑힌 약관 문서 노드(TermsDocument)가 1개로 합쳐지고 두 약관 청크에 하나씩 이어짐.  
  앞 상담을 가리키며 생긴 상담 노드가 실제 상담 노드와 1개로 합쳐짐(FOLLOWS 관계 1개 유지)
- 그래프의 청크 노드에는 옛 구조의 `parent_chunk_ids` 속성이 없음(0개 확인). 추출 단위 기록은 `kg_prepared.json`에만 있음

## K8 커뮤니티 요약 결과 (2026-10-23, hybrid-ai-lab에서 실행)

GDS Leiden(randomSeed 42, concurrency 1, 한 단계), 엔티티 3개 이상 묶음만 요약, 보고서 판 v2.  
기록: `hybrid-ai-lab/verify/k8-community/`(실행 로그 run-a ~ run-d, `result.json`, `README.md`).

| 실행 | 결과 |
|------|------|
| a. 전체 재색인 `sample-014` (옵션 없음) | K4 노드 123개, 관계 218개, K5 3묶음, K6 94개, ④ 통과(10/10). 보고서와 검증 결과에 K8 칸 없음 |
| b. 전체 재색인 `sample-015` (`--communities`) | a와 K4 ~ K6이 같음. K8 묶음 16개(엔티티 94개, 관계 95개) 중 15개 요약, LLM 15번, ④ 통과(커뮤니티 15개) |
| c. 같은 입력으로 `sample-016` | 묶음과 지문 15개가 b와 같음, LLM 0번(15개 재사용) |
| d. 증분 색인 `sample-017` (`--communities`) | K7 뒤 K8: 묶음 14개 중 13개 요약, LLM 4번, 재사용 9개, ④ 통과(커뮤니티 13개, 9/9) |
| 단위 시험 | 8개 통과(GDS 실제 실행으로 묶음 결정성 확인 포함) |

- a와 b의 준비 결과와 K4 ~ K6 결과가 같아, 옵션을 켜고 끄는 것은 K8 말고 바꾸지 않음
- 묶음은 모두 한 문서 종류 안에서만 생김(약관 8, 혜택 안내 3, 상담 2, 섞인 묶음 0). 엔티티 사이 관계가 문서 안에서만 있어서임
- 처음에는 igraph와 leidenalg로 묶었으나 GDS Leiden으로 바꿈. 그래프가 이미 Neo4j에 있고 Neo4j GraphRAG에서 더 일반적이기 때문임.  
  그래서 두 라이브러리는 requirements에 넣지 않았고 가상환경에서도 지움

## 한계 (v0)

- 약관 그래프 스키마는 채움 시험 합격 기준 미달 상태로 확정된 것임(`schema/doc/regulation/approval.json`의 `below_criteria`)
- 혜택 안내와 상담 기록 스키마는 자동 승인 상태임. 인덱싱 운영 전에 사람 승인이 필요함
- ② 공통 단계는 청킹 결과 파일을 받기만 함(로드, 정제와 가명처리, 청킹은 RAG 인덱싱 예제가 함)
- 증분 색인의 카드명 사전은 활성 세대 것을 그대로 씀. 새 카드명이 생기면 전체 재색인이 필요함
- K5 병합은 `apoc.refactor.mergeNodes`의 `properties: 'discard'`라 값이 다르면 목록 첫 노드의 값을 남김.  
  목록 순서를 정하지 않아(`collect`에 정렬 없음) 증분 색인에서 옛 노드와 새 노드가 합쳐질 때 어느 값이 남을지 정해져 있지 않음
- K6은 임베딩이 없는 엔티티만 임베딩함. 증분 색인에서 새 노드가 K5로 기존 노드와 합쳐지면 기존 임베딩이 남아,  
  합치며 바뀐 속성이 설명 임베딩에 반영되지 않음(표본 증분: 새 엔티티 29개 중 합쳐진 5개는 다시 임베딩하지 않음)
- S1의 벡터 재사용은 앞 세대 인덱스를 통째로 읽음. 청크가 많으면 바뀐 청크만 골라 읽도록 바꿔야 함
- 증분 색인의 반영은 두 저장소에 걸쳐 한 번에 일어나지 않음(KG 먼저, 검색엔진 나중으로 어긋남을 줄임)
- 그래프 검색(`graph_search.py`)은 교육용 명령행 도구임. API로 열지 않았고, 질문마다 활성 세대 파일을 읽어 `card_chunks-{세대}`와 Neo4j `generation`으로 조회함
- 그래프 검색은 neo4j-graphrag 1.22.0 `VectorCypherRetriever`의 결함(세대 필터를 줄 때 임베딩 속성 이름을 잘못 봄)을 `_retriever()`에서 우회함
- 실행 중 `LLMInterface is deprecated` 경고가 나옴(neo4j-graphrag 1.22.0). 동작에는 영향 없음
- K8은 문서를 건너는 관계가 없어 상담과 약관을 한 묶음으로 엮지 못함. 거시 질문 중 문서 건너기(Q25)는 커뮤니티 보고서만으로 답할 수 없음
- K8은 매 실행 세대의 Community를 모두 다시 씀. 묶음 경계가 조금만 바뀌어도 그 묶음 보고서는 LLM으로 다시 만듦
- K8 보고서 판(`community.REPORT_VERSION`)을 올리면 모든 보고서를 다시 만듦. 프롬프트를 바꿀 때 올려야 옛 보고서가 섞이지 않음
