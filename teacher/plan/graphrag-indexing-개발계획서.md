# GraphRAG 인덱싱 예제 프로그램 개발계획서

| 항목 | 내용 |
|---|---|
| 작성 | 클로니(오케스트레이터), 2026-10-24 |
| 검토 | 에듀니(교육 관점), 플로니(운영과 장애 관점), 지식니(지식 그래프와 검색 품질 관점). 14장 「검토 이력」 |
| 대상 교재 | 『신한카드 하이브리드AI_W05 ~ W07』 「2. 인덱싱」 30 ~ 62쪽 |
| 대상 커리큘럼 | M4 「관계로 찾기」 W5 ~ W6(8H) 중 그래프 적재 실습 2H(배치는 13장 Q3로 강사 확인) |
| 참조 코드 | `teacher/graphrag/v0/` (강사용 원본. 교재 장표의 코드 발췌가 이 코드에서 나옴) |
| 산출 위치 | `hands-on/solutions/graphrag/indexer/` |
| 상태 | 승인(13.2) 뒤 개발 완료(2026-10-24). 실행 결과는 15장과 예제 README 7장 |

## 1. 목표

- 교육생이 GraphRAG 인덱싱의 뼈대(① 세대 ID → ② 청크 고정 → ③ KG 구축과 검색엔진 인덱싱 → ④ 검증 → ⑤ 게시)를  
  **파이썬 코드로 직접 만들며** 이해함
- 강사는 전체 예제를 보여 주고, 교육생은 **워크플로우 단계마다 1개 이상, 핵심 함수 16개(직접 6개, 빈칸 10개)를 클론 코딩**한 뒤  
  본인 코드로 바꿔 끼워 실행함
- 단계마다 눈으로 확인할 출력(추출 단위 수, 노드와 관계 수, 병합 묶음, 커뮤니티 수, 검증 통과 여부)을 남김

## 2. v0와 다른 점(교육용으로 단순화)

| 항목 | v0(강사용) | 실습 예제 | 이유 |
|---|---|---|---|
| 파일 | 7개 모듈 + tools 6개 | main 1개 + 핵심 1개 + 뼈대 1개 + 제공 1개 + 확인 도구 1개 | 교육생은 핵심 파일 하나만 봄 |
| 설정 | `config.py` 분리 | main 맨 위 상수 | 프롬프트 요구(설정 파일 분리 금지) |
| 임베딩 | KURE-v2(로컬, torch 1.3GB, 768차원) | Cohere `embed-v5.0-fast`(API, 2048차원) | 설치가 가볍고 RAG 실습과 같은 모델과 키 |
| LLM 호출 | 표준 라이브러리 urllib로 직접 | LangChain `ChatGroq`를 neo4j-graphrag `LLMInterface`로 감쌈 | LangChain 기본 사용 요구. 추출 프롬프트는 교재대로 neo4j-graphrag 것 |
| 입력 | `tools/export_chroma_chunks.py`로 변환한 JSON | main의 ② 공통 단계가 RAG 실습 Chroma를 직접 읽음(또는 `--chunks`로 강사 배포 파일) | 도구 한 단계를 없앰. 로드, 정제, 가명처리, 청킹은 RAG 실습이 한 것이고 ②는 chunk_id 부여와 파일 고정만 함 |
| 증분 색인, K7 | 있음 | 없음(전체 재색인만) | 운영 주제. RAG 실습과 같은 결정(D1) |
| K8 커뮤니티 요약 | `--communities` 옵션(끄면 안 돎) | 기본 실행(`--skip-communities`로 끔), 핵심 파일에 빈칸 채우기 2개 | 강사 결정(D2). 교재 46 ~ 49쪽을 코드로 익힘 |
| 병렬 실행 | KG 구축과 검색엔진 인덱싱을 스레드로 병렬 | 순서대로 실행(KG 먼저, 검색엔진 다음) | 초보자가 로그를 순서대로 읽게 함. 교재 30쪽 「전체 재색인은 순서 불필요」를 주석으로 설명 |
| 비동기 | asyncio.gather + Semaphore | K2만 ThreadPoolExecutor(기본 2개)로 병렬, 나머지는 동기 | async 문법을 핵심 코드에서 뺌. 조별 키 하나를 여럿이 쓰므로 동시 수를 낮춤(플로니) |
| 벡터 인덱스 이름 | `kg_entity_embedding`, `kg_community_embedding` | 교재와 같은 이름. 시작 때 차원이 다른 같은 이름 인덱스가 있으면 멈추고 안내 | 강사 PC처럼 v0(768차원)가 있는 DB에서는 2048차원 저장이 색인되지 않음(플로니, 지식니 실측). 대응은 13장 Q2 |

## 3. 파일 구성

```text
hands-on/solutions/graphrag/
├─ .venv/                      GraphRAG 실습 공용 가상환경(검색 예제가 생기면 함께 씀)
└─ indexer/
   ├─ README.md                맨 위에 수업용 명령 2개, 목표, 구조, 가상환경 설정(OS, 셸별), 실행 옵션(부록), 출력 읽는 법, 실측값
   ├─ requirements.txt         RAG 실습과 같은 판(langchain 1.4.6 등) + neo4j-graphrag, neo4j, opensearch-py
   ├─ index_graph.py           main: 설정 상수, 시작 검사, ① ~ ⑤, K2 병렬 호출, S1 임베딩(96건씩), S2 토큰화 호출, K8 보고서 LLM 호출, 단계별 출력
   ├─ core_graph.py            핵심(클론 코딩 대상): ① ~ ⑤, K1 ~ K8, S1 ~ S3의 실습 함수 16개 + 제공 함수(머리줄, K8 쓰기)
   ├─ my_graph.py              교육생 작업 파일(직접 6개는 NotImplementedError, 빈칸 10개는 "빈칸 N을 채울 것" 표시.
   │                           아직 안 채운 함수는 강사 코드로 대신 돌게 하는 한 줄이 맨 아래에 있음)
   ├─ kr_tokenizer.py          제공(읽지 않아도 됨): RAG 실습 W3에서 이미 작성한 Kiwi 토크나이저와 카드 별칭 규칙(작성 완료)
   ├─ check_graph.py           결과 확인 도구(읽기만): 질문 → 검색엔진(BM25 + 벡터) → 청크 → 엔티티 → 커뮤니티 보고서 → 리랭크, 적중 판정.
   │                           `--drop {세대}`로 실패한 세대의 노드와 인덱스만 지움
   └─ data/                    실행 결과: active_generation.json, generations/{세대}/(prepared-chunks, kg_prepared, community_reports, build_report)
      └─ teacher/              강사 배포본(선택): 강사 PC의 prepared-chunks.json, kg_prepared.json, community_reports.json. `--reuse`가 읽음
```

- 입력(읽기만): RAG 실습 Chroma `hands-on/solutions/rag/indexing/data/chroma`(collection `card_docs`, 260청크),  
  그래프 스키마 `hands-on/solutions/graphrag/schema/doc/{regulation,benefit_guide,consult_log}/`,  
  승인 별칭 `hands-on/solutions/rag/indexing/aliases_approved.json`
- 저장소(쓰기): Neo4j `bolt://localhost:7687`(APOC, GDS), OpenSearch `http://127.0.0.1:9200`. 둘 다 `backing-services/`의 compose로 띄움.  
  다른 곳이면 환경변수 `NEO4J_URI`, `OPENSEARCH_URL`
- 비밀값: `secrets/.env`의 `GROQ_API_KEY`, `COHERE_API_KEY`. Neo4j 비밀번호는 환경변수 `NEO4J_PASSWORD` 또는 `backing-services/neo4j/.env`

## 4. 워크플로우와 실습 함수 선별

워크플로우 단계(① ~ ⑤, K1 ~ K8, S1 ~ S3)마다 실습 함수를 최소 1개 둠(강사 지시 2026-10-24).  
방식은 단계마다 둘 중 학습 효과가 큰 쪽을 고름.

- **직접 작성**: 개념이 순수 파이썬 논리(규칙, 비교, 조립)에 있어 손으로 써야 남는 단계. 뼈대에는 `raise NotImplementedError("여기에 본인 코드를 작성함")`
- **빈칸 채우기**: 개념이 라이브러리나 DB 호출의 「무엇을 어떤 순서로 부르나」에 있어, 호출 한두 줄을 채우면 흐름이 보이는 단계.  
  뼈대는 거의 완성된 코드에 `raise NotImplementedError("빈칸 N을 채울 것")`를 둠(RAG 뼈대와 같은 표시, `____` 금지)

실습 함수는 모두 `core_graph.py`(정답)와 `my_graph.py`(뼈대)에 같은 이름으로 있음. 「하는 일」의 나머지 부분은 main이 제공함.

| 단계 | 하는 일(main이 부르는 흐름) | 교재 | 실습 함수 | 방식 | 실습 개념 |
|---|---|---|---|---|---|
| 시작 검사 | Neo4j 접속, APOC과 GDS 버전, 같은 이름 벡터 인덱스의 차원, OpenSearch 접속, 키 2개. GDS가 없으면 K8을 건너뛰고 안내 | - | 없음(환경 검사) | - | - |
| ① 세대 ID 발급 | `gen-lab-{실행 이름}-{해시 8자리}`를 만들고, 입력 지문과 설정 지문이 활성 세대와 같으면 「할 일 없음」. 같은 세대의 흔적(중단 뒤 재실행)은 main이 지움 | 31 | `issue_generation` | 직접 | 같은 실행 이름이면 같은 세대 ID가 나오는 규칙(해시), 사전 검사 조건 3개(활성 세대 있음, 입력 지문 같음, 설정 지문 같음)를 and로 묶음 |
| ② 공통 단계 | Chroma에서 본문과 메타데이터를 읽어(main) 청크 한 건으로 만들고 `prepared-chunks.json`으로 고정(main). `chroma_id` 보존 | 31 | `prepare_chunks` | 빈칸 2곳 | doc_id 규칙(약관과 혜택은 원천 파일, 상담은 상담 건)과 chunk_id 규칙(문서 키 + 본문 해시 16 + 반복 번호). S3 문서 단위 교체와 ④ 검증의 열쇠가 여기서 정해짐 |
| K1 추출 단위 나누기 | 약관은 조항 제목 줄로 나누고 겹친 조항은 합침. 혜택과 상담은 청크 그대로. 정규식 상수와 「다음 빈 줄 아닌 줄」 보조 함수는 제공 | 32, 34 | `split_by_heading` | 직접 | 제목 줄 다음 줄이 ①로 시작할 때만 시작점(차례 제외), 다음 제목 전까지가 한 단위 |
| | | | `k1_split_units` | 빈칸 2곳 | 단위 ID = 문서 ID + 조항 번호, 겹친 조항은 긴 글을 남기고 청크 ID를 모두 모음(이 실습 데이터는 겹침 0건, README에 이유) |
| K2 추출, K3 가지치기 | 머리줄(값이 있는 칸만) + 단위 본문을 추출기에 넣고 스키마 밖은 지움. 재사용 판정, 병렬 호출, 실패 기록은 main | 35, 36 | `extract_one` | 빈칸 2곳 | 추출기에 넣는 것 세 가지(단위 ID를 uid로 준 TextChunk, 문서 유형의 GraphSchema)와 추출 직후 가지치기 순서 |
| K4 적재 | 청크 노드(검색 청크와 1대1) + 엔티티 + FROM_CHUNK를 행으로 만들고 `Neo4jWriter`로 씀(main). 세대 표시와 병합 키 모으기는 제공 | 37, 38 | `build_graph_rows` | 빈칸 2곳 | 청크마다 Chunk 노드 하나(chunk_id가 검색엔진과 같음), 엔티티는 나온 청크마다 FROM_CHUNK(겹친 조항이면 청크 2개) |
| K5 병합 | 스키마 고유 속성 값이 같은 노드를 하나로 합침. 50건마다 진행 출력 | 39 ~ 41 | `k5_merge` | 빈칸 2곳 | 같은 세대에서 라벨과 속성 값이 같은 노드 모으기(Cypher), 2개 이상일 때만 `apoc.refactor.mergeNodes` |
| K6 엔티티 설명 임베딩 | 「라벨: 속성=값」 설명 글을 만들어 main의 `embed_texts`(96건씩)로 임베딩하고 벡터 인덱스를 만듦 | 42 ~ 44 | `entity_description` | 직접 | 관리용 속성(generation, run_id, embedding)을 빼고 이름순으로 「라벨: k=v, …」. 설명 글이 곧 검색 대상임 |
| | | | `k6_embed_descriptions` | 빈칸 2곳 | 임베딩 없는 엔티티만 읽기, `setNodeVectorProperty`로 저장, 차원과 코사인을 적은 벡터 인덱스 |
| K8 커뮤니티 요약 | 엔티티 그래프를 읽고(main) Leiden으로 묶고, 엔티티 3개 이상 묶음마다 LLM 보고서(main) → 임베딩(main) → Community 노드(제공 함수 `k8_write_communities`) | 46 ~ 49 | `detect_communities` | 빈칸 2곳 | 엔티티와 관계만 무방향으로 투영(`gds.graph.project`), 씨앗과 병렬 1로 Leiden(`gds.leiden.stream`)을 불러 같은 그래프에서 같은 묶음 |
| | | | `build_community_rows` | 빈칸 2곳 | 엔티티 3개 이상 묶음만 보고서 대상, 묶음 안 번호를 엔티티 ID로 바꿔 IN_COMMUNITY 대상 만들기 |
| S1 임베딩 | 색인용 본문의 해시로 활성 세대 벡터를 찾아 재사용하고 새 본문만 Cohere로 임베딩(96건씩은 main의 `embed_texts`) | 54, 55 | `embed_with_reuse` | 직접 | 본문 해시가 같으면 벡터 재사용, 다르면 새로 임베딩. 재사용과 새 임베딩을 합쳐 청크 순서대로 돌려줌 |
| S2 키워드 분석 | 카드명 사전과 별칭으로 Kiwi 토큰화(W3에서 만든 `kr_tokenizer` 제공)하여 엔진 문서 한 건을 만듦 | 53, 56 ~ 58 | `build_search_docs` | 빈칸 2곳 | 엔진 문서 한 건 = chunk_id(_id), doc_id, text_hash, text, text_tokens(낱말을 공백으로 이음), embedding, 메타데이터 |
| S3 적재 | 문서(doc_id)마다 옛 청크를 지우고 새 청크를 한꺼번에 넣은 뒤 바로 보이게 함 | 58, 59 | `apply_search` | 빈칸 3곳 | `delete_by_query`(term doc_id), `bulk`(_id = chunk_id), `refresh`. 청크 단위가 아니라 문서 단위로 바꿔야 고아 청크가 없음 |
| ④ 검증 | 입력 = 검색엔진 = 그래프 청크 노드, 중복 노드 없음. K8 검사(요약과 임베딩 빠짐 0, 빈 묶음 0, 세대 밖 구성원 0)는 main | 60, 61 | `verify_chunk_ids` | 직접 | 집합 비교(==, 차집합)로 빠짐과 남음을 적고, 목록 그대로 세어 중복 노드를 잡음. 셋 다 맞아야 통과 |
| ⑤ 게시 | 활성 세대 파일 하나만 바꿈 | 30, 62 | `publish_active` | 직접 | 임시 파일에 다 쓴 뒤 `os.replace`로 바꿔 끼움(반쯤 쓴 파일이 보이지 않음). 검증 통과 뒤에만 부름 |

- 합계 16개: 직접 6개(①, K1 분할, K6 설명 글, S1, ④, ⑤), 빈칸 10개(②, K1 합치기, K2, K4, K5, K6 임베딩, K8 2개, S2, S3)
- 실습에서 뺀 것(읽기만): 시작 검사, Chroma 읽기, K2 재사용 판정과 병렬 호출, K8 엔티티 그래프 읽기와 지문(member_hash)과 보고서 LLM 호출과 쓰기,  
  `embed_texts`(96건 분할), 토크나이저, 결과 확인 도구
- 교재 그림과 이 실습 데이터(RAG 실습 Chroma, 쪽 단위 청킹)가 다른 곳은 README 「실측값」에 적음  
  (약관 단위 10 → 51과 겹침 있음 대 15 → 52와 겹침 0, TermsDocument 16 → 1 대 2개, 768차원 대 2048차원, 별칭 189 대 390)

## 5. 실습 순서와 교시 배치(안)

함수는 워크플로우 순서대로 채움. 앞 함수가 비어 있으면 그 자리에서 `NotImplementedError`가 나므로 순서를 바꾸지 못함.  
한 교시에 5 ~ 6개가 들어가 세 교시로 나눔(두 교시면 K2, S2, ⑤를 읽기로 돌림. 13장 Q3).

| 교시 | 함수(순서대로) | 직접 : 빈칸 | 줄 수(예상) | 교시 끝에 확인할 것 |
|---|---|---|---|---|
| A | `issue_generation` → `prepare_chunks` → `split_by_heading` → `k1_split_units` → `extract_one` | 2 : 3 | 15, 20, 20, 30, 20 | 표본 10청크 → 단위 18개, LLM 호출 수, 단위 1개의 노드와 관계 |
| B | `build_graph_rows` → `k5_merge` → `entity_description` → `k6_embed_descriptions` → `detect_communities` → `build_community_rows` | 1 : 5 | 35, 20, 10, 25, 30, 20 | 노드와 관계 수, 병합 묶음 수, 설명 글 예, 커뮤니티 수와 보고서 제목 |
| C | `embed_with_reuse` → `build_search_docs` → `apply_search` → `verify_chunk_ids` → `publish_active` | 3 : 2 | 15, 20, 25, 20, 10 | 재사용 수, 적재 건수, ④ 통과, 활성 세대 파일, 결과 확인 도구로 질문 1개 |

- 교시 A가 끝나면 뒤 단계는 강사 코드로 돌아 전체가 한 번 완주됨(import를 `my_graph`로 두되 빈 함수는 `core_graph`의 것을 쓰게  
  뼈대 맨 아래에 「아직 안 채운 함수는 강사 코드로」 한 줄을 둠). 그래서 앞 교시에서 막혀도 다음 교시 실습이 가능함

## 6. 교체 방법

1. `my_graph.py`에 같은 이름, 같은 인자의 함수를 채움(직접 6개는 `NotImplementedError` 자리, 빈칸 10개는 "빈칸 N을 채울 것" 자리)
2. `index_graph.py`의 import 한 줄을 바꿈: `import core_graph as core` → `import my_graph as core`
3. 같은 명령으로 다시 실행해 단계별 출력을 강사 결과와 비교함
4. 막히면 두 가지 중 하나: ① 그 함수만 뼈대의 「강사 코드로 대신」 목록에 넣어 뒤 단계를 계속함  
   ② import를 되돌려 강사 코드 전체로 돌림

## 7. 실행 모드와 비용

| 모드 | 명령 | 입력 | LLM 호출 | 시간 | 용도 |
|---|---|---|---|---|---|
| 표본(수업용) | `index_graph.py --run {별명}-s1 --sample` | 10청크(약관 2, 혜택 4 한빛 가족돌봄, 상담 4) | K2 약 18번 + K8 약 12번 | 미측정(목표 2분 안) | 수업 중 클론 코딩 확인 |
| 전체 | `index_graph.py --run {별명}-f1` | 260청크 | K2 297번(약 100만 토큰) + K8 약 105번 | 미측정(v0 13분) | 강사 사전 실행 |
| 전체(재사용) | `index_graph.py --run {별명}-f1 --reuse data/teacher` | 강사 배포 청크 파일 | 0번(K2 추출 결과와 K8 보고서 재사용) | 미측정(v0 LLM 0번 실행 8분) | 교육생 PC에서 전체 그래프를 만들 때 |
| K8 끔 | 위 명령 + `--skip-communities` | 같음 | K8 0번 | K8 시간만큼 줄어듦 | K1 ~ K6, S1 ~ S3만 빨리 볼 때. GDS가 없으면 자동으로 이 모드 |

- README 맨 위에는 수업용 명령 2개(표본 실행, 결과 확인)만 두고 나머지 옵션은 부록으로 내림(에듀니)
- 세대 ID에 교육생 별명을 넣게 하여(`--run`), Neo4j와 OpenSearch를 여럿이 함께 써도 세대가 섞이지 않게 함
- `--reuse`는 강사 PC의 청크 파일과 추출 결과를 함께 배포받아 쓰므로 교육생 Chroma와 본문 해시가 달라도 재사용이 맞음(지식니)
- Groq 호출 제한: `ChatGroq(max_retries=6, request_timeout=90)`과 `extract_one`의 재시도 2번. 재시도마다 로그 한 줄. 그래도 막히면 `--reuse`
- Cohere: 전체 인덱싱 임베딩 약 2,000건(청크 260 + 엔티티 약 1,700 + 보고서 약 100) = 호출 약 22번, 비용 1센트 미만.  
  인덱싱은 모두 `embed_documents`(search_document), 확인 도구의 질문은 `embed_query`(search_query)로 구분함(지식니)

## 8. 모델과 패키지

| 항목 | 값 |
|---|---|
| LLM | Groq `openai/gpt-oss-120b`, JSON 모드, temperature 0, reasoning_effort medium. LangChain `langchain-groq 1.1.3` |
| 임베딩 | Cohere `embed-v5.0-fast` 2048차원. LangChain `langchain-cohere 0.6.0` + `cohere 5.21.1`(RAG 실습과 같은 판). 96건씩 나눠 부름 |
| 리랭커 | Cohere `rerank-v4.0-fast`. 인덱싱에는 쓰지 않고 결과 확인 도구(`check_graph.py`)의 마지막 단계에서만 씀 |
| KG 구축 | `neo4j-graphrag 1.22.0`(추출기, 가지치기, Neo4jWriter, GraphSchema), `neo4j 6.4.1`(접속 제한 시간 상수) |
| 검색엔진 | `opensearch-py 3.0.0`(LangChain OpenSearch 저장소는 문서 단위 교체와 사용자 매핑을 지원하지 않아 native 사용). 2048차원 lucene kNN 매핑과 질의를 2026-10-24에 확인함 |
| 형태소 분석 | `kiwipiepy 0.23.2` |
| Python | 3.13, 가상환경 `hands-on/solutions/graphrag/.venv`(설치 확인 완료 2026-10-24) |

- context7은 월 한도 초과로 응답하지 않아(2026-10-24), 설치된 패키지의 소스에서 시그니처를 직접 확인함  
  (`ChatGroq`: `model_kwargs`, `reasoning_effort`, `max_retries`, `request_timeout` 필드. `CohereEmbeddings.embed_documents`는 한 요청에 모두 보내므로 96건씩 직접 나눔.  
  `LLMInterface.invoke(input, message_history, system_instruction)`, `LLMEntityRelationExtractor.run(chunks, schema)`)

## 9. 사전 과제와 환경 점검(교육생, W5 전주)

| 번호 | 과제 | 확인 방법 |
|---|---|---|
| 1 | RAG 실습(W3) 인덱싱 결과 `rag/indexing/data/chroma`가 있음(없으면 강사 배포본 복사) | 폴더 안 `chroma.sqlite3` 존재 |
| 2 | Docker Desktop 설치, `backing-services/neo4j/.env` 비밀번호 설정, Neo4j와 OpenSearch 기동 | `docker compose ... ps`가 둘 다 `healthy` |
| 3 | APOC과 GDS 확인 | `RETURN apoc.version(), gds.version()`이 둘 다 `2026.09.0` |
| 4 | 가상환경 설치(README 3절) | 설치 확인 명령이 `ok` 출력 |
| 5 | `secrets/.env`에 키 2개 | `index_graph.py --run {별명}-s1 --sample`의 시작 검사 통과 |

실습 예제의 시작 검사가 2 ~ 5를 한 번에 확인하고 실패한 항목과 할 일을 출력함(플로니, 에듀니).

## 10. 운영 위험과 코드 대응(플로니 검토 반영)

| 위험 | 코드 대응 |
|---|---|
| 같은 이름 벡터 인덱스가 다른 차원으로 이미 있음(강사 PC의 v0 768차원) | 시작 검사에서 `SHOW VECTOR INDEXES`로 차원을 보고 다르면 멈추고 안내. 대응 방식은 13장 Q2 |
| 중단 뒤 같은 `--run`으로 재실행하면 청크 노드가 두 벌 | ①에서 그 세대의 Chunk 노드와 `card_chunks-{세대}` 인덱스를 찾아 지우고 다시 만듦. 활성 세대와 같으면 멈춤 |
| K6, K8 임베딩이 한 요청에 1,700건 | 핵심 함수가 main의 `embed_texts`(96건씩)를 인자로 받아 씀 |
| GDS가 안 붙은 PC에서 기본 실행이 멈춤 | 시작 검사에서 `gds.version()` 실패면 K8을 건너뛰고 안내 |
| 조별 키 하나에 동시 호출이 겹침 | `LLM_CONCURRENCY` 상수 기본 2, `request_timeout=90`, 재시도 로그 |
| K2 한 건 실패가 전체를 멈춤 | `extract_one`이 예외를 잡아 `{"error": ...}`로 돌려주고 단계 끝에 실패 수 출력 |
| Neo4j 긴 쿼리 무한 대기 | 드라이버 접속 제한 시간 상수, K5 루프 50건마다 진행 출력 |
| 실패한 세대가 DB에 쌓임 | `check_graph.py --drop {세대}`로 그 세대의 노드, Community, 인덱스만 지움 |

## 11. 검증 계획(정직한 보고 기준)

| 검증 | 완료 기준 |
|---|---|
| 표본 전체 재색인 | ④ 통과(10/10), ⑤ 게시. K1 단위 수, K4 노드와 관계 수, K5 묶음 수, K8 커뮤니티 수를 README 실측값에 기록 |
| 같은 입력 재실행 | ① 사전 검사 「할 일 없음」. 새 실행 이름으로 다시 돌리면 K2와 K8이 재사용으로 LLM 0번 |
| 중단 뒤 재실행 | 표본 실행을 K4 뒤 강제 중단한 다음 같은 `--run`으로 재실행 → ①이 흔적을 지우고 ④ 통과 |
| 뼈대 교체 경로 | `my_graph.py`를 `core_graph.py` 내용으로 채운 사본으로 같은 결과. 빈 뼈대는 첫 핵심 함수에서 `NotImplementedError` |
| 전체 재색인 | 260청크 ④ 통과, 시간과 LLM 토큰 기록. `--reuse`로 다시 돌려 LLM 0번 확인 |
| 그래프 품질 실측표 | 라벨별 엔티티 수, 임베딩 없는 엔티티 0, FROM_CHUNK 중복 0, 단위 없는 청크 5개(D1 표지, 메타데이터, 차례, 각주 쪽) |
| 결과 확인 도구 | Q01(약관), Q09(혜택), Q14(상담, 회원 필터와 FOLLOWS), Q24(거시)로 실행. 적중 = 평가셋 `relevance.any_of` 문자열이 상위 청크 본문이나 엔티티 속성에 있음 |
| 주석 | `references/dev-comment-guide.md` 10장 체크리스트, 핵심 파일은 줄 단위 주석 |

## 12. 작업 순서

1. 개발계획서 초안 → 강사 결정(D1 ~ D4, 완료) → 팀원 리뷰(완료) → 최종안(이 문서) → 강사 승인(13장)
2. `kr_tokenizer.py`(완료) → `core_graph.py` → `index_graph.py` → 표본 실행
3. `my_graph.py` 뼈대 → 교체 경로 확인 → 중단 뒤 재실행 확인
4. `check_graph.py` → 전체 재색인(백그라운드) → `data/teacher/` 배포본 → README
5. 교육생용 실습 가이드(마크다운) → 핵심 슬라이드(상세는 원격 Git 링크) → 렌더링 검증

## 13. 결정 사항과 승인 요청

### 13.1 확정된 결정(2026-10-24 강사)

| 번호 | 항목 | 확정안 | 대안(채택 안 함) |
|---|---|---|---|
| D1 | 실습 범위 | 전체 재색인만(증분 색인과 K7 제외). 교재 45쪽 K7과 30쪽 증분 순서는 이론으로 설명 | 증분 색인 포함 |
| D2 | K8 커뮤니티 요약 | 핵심 파일에 포함하고 빈칸 채우기로 실습함(5장 6, 7번). 기본으로 실행하고 `--skip-communities`로 끔 | 선택 옵션 제공 파일 / 제외 |
| D3 | 교육생 실행 환경 | 교육생 PC마다 Docker로 Neo4j와 OpenSearch(`backing-services/`). 안 되는 PC는 강사 PC 주소를 환경변수로 받고 세대 ID(별명)로 분리 | 강사 PC 한 대만 공유 |
| D4 | 입력 청크 | RAG 실습 Chroma(교육생이 W3에서 만든 것)를 ②에서 직접 읽음. 강사 배포 파일은 `--chunks`와 `--reuse`로 선택 | 강사가 `prepared-chunks.json`만 배포 |
| D5 | 가상환경 위치 | `hands-on/solutions/graphrag/.venv`(검색 예제와 공용) | `indexer/.venv` |
| D6 | 세대 ID 접두어 | `gen-lab-`(v0의 `gen-hai-`와 같은 DB에서 구분) | 다른 접두어 |
| D7 | 리랭커 | 결과 확인 도구에서만 사용 | 쓰지 않음 |

### 13.2 승인(2026-10-24 강사)

| 번호 | 질문 | 강사 답 | 반영 |
|---|---|---|---|
| Q1 | 이 최종안으로 개발을 시작해도 되는지 | **승인** | 개발 시작 |
| Q2 | 강사 PC의 Neo4j에 v0 768차원 인덱스(`kg_entity_embedding`)가 있어 실습 코드와 충돌함 | **v0 인덱스를 지움**(강사 PC의 v0 벡터 인덱스와 세대를 지우고 같은 DB를 씀) | v0 `tools/reset.py --yes --all`로 `gen-hai-` 세대와 검색엔진 인덱스를 지운 뒤 벡터 인덱스 2개를 `DROP INDEX`. v0 그래프 검색 도구는 v0를 재색인하기 전까지 동작하지 않음(v0 README에 기록). 코드는 교재 이름을 유지하고 시작 검사의 차원 확인은 그대로 둠 |
| Q3 | 클론 코딩 3교시(5장 A, B, C) | **세 교시** | 이론 1교시 + 클론 코딩 3교시(4H)로 실습 가이드 작성 |

## 14. 검토 이력

| 단계 | 내용 |
|---|---|
| 초안 v0.1 | 클로니 작성. 교재 30 ~ 62쪽과 v0 코드 분석, Advisor 자문(클론 직접 작성 3개로 축소, 세대 ID에 별명, 재사용 파일 배포) |
| 강사 결정 | D1 전체 재색인만, D2 K8 핵심 포함(빈칸), D3 교육생 PC마다 Docker, D4 RAG Chroma 직접 읽기 |
| 에듀니 검토 | 판정 「수정 후 사용」. 반영: 두 교시 분할, 첫 과제(`split_by_heading`)에 정규식 상수와 보조 함수 제공, `build_graph_rows`를 빈칸으로 내리고 `k1_split_units`를 직접으로 올림, K8 빈칸을 교재에 코드가 있는 자리(48쪽 투영과 Leiden, 49쪽 묶음 고르기)로 옮김, 빈칸 표시를 RAG 선례와 통일, K2 실패 단위 출력, README 수업용 명령 2개 고정, 사전 과제 장 신설, 「교재 값 : 실습 값」 칸 추가 |
| 플로니 검토 | 판정 「조건부 통과」. 반영: 벡터 인덱스 차원 충돌 검사와 대응(Q2), 중단 뒤 재실행 시 세대 흔적 정리, K6과 K8 임베딩 96건 분할, GDS 없으면 K8 자동 생략, 동시 호출 2와 제한 시간과 재시도 로그, `extract_one` 예외 기록, 재사용 모드 시간 「미측정」, Neo4j 접속 제한 시간과 K5 진행 출력, `--drop` 도구 |
| 지식니 검토 | 판정 「수정 후 사용」. 반영: 인덱스 차원 충돌(플로니와 같음), K1 겹친 조항 0건인 이유와 출력, K5 예시를 ProductGuide와 Consultation으로, 강사 배포 입력(`--chunks`, `--reuse`), `embed_documents`와 `embed_query` 구분, 머리줄 빈 칸 제외와 채움률 출력, OpenSearch 2048차원 매핑 사전 확인(통과), ② 범위 한정과 `chroma_id` 보존, 검색 품질 적중 기준과 실측표 항목 |
| 사전 확인 | 2026-10-24 OpenSearch 2.19.1에서 2048차원 lucene kNN 인덱스 생성과 질의 통과. Neo4j에 v0 벡터 인덱스 2개(768차원, `gen-hai-full-002` 노드 2,038개) 존재 확인 |
| 강사 지시(실습 범위) | 워크플로우 단계마다 실습 함수 최소 1개. 4장을 「워크플로우와 실습 함수 선별」로 바꾸고 단계마다 직접 작성과 빈칸 채우기 중 학습 효과가 큰 쪽을 고름(16개: 직접 6, 빈칸 10). 5장은 세 교시 배치안으로 바꿈 |
| 강사 승인 | Q1 승인, Q2 v0 인덱스 삭제, Q3 세 교시 |

## 15. 개발 결과(2026-10-24)

| 산출물 | 경로 | 상태 |
|---|---|---|
| 예제 프로그램 | `hands-on/solutions/graphrag/indexer/`(index_graph.py, core_graph.py, my_graph.py, kr_tokenizer.py, check_graph.py, requirements.txt, README.md) | 완료 |
| 강사 배포본 | `hands-on/solutions/graphrag/indexer/data/teacher/`(prepared-chunks, kg_prepared, community_reports, 5.2MB) | 생성(`.gitignore` 예외로 Git에 포함). `--reuse data/teacher` 실행 57초, LLM 2번 |
| 교육생 실습 가이드 | `teacher/plan/graphrag-indexing-실습가이드.md` | 완료 |
| 핵심 슬라이드 | `teacher/plan/graphrag-indexing-실습가이드.pptx`(6장, 스크립트 `…-slides.md`, 빌드 `build/build-guide-slides.js`) | 완료. 붙여넣기 호환 점검 OK, LibreOffice 미리보기 확인 |

검증(11장 기준) 결과

| 검증 | 결과 |
|---|---|
| 표본 전체 재색인 | 통과. 71초, 단위 18, 노드 96, 병합 4묶음, 임베딩 77, 커뮤니티 13, ④ 10/10 |
| 같은 입력 재실행 | 「할 일 없음」. 새 이름 재실행은 K2 0번, K8 0번, 임베딩 0개 재사용으로 7초 |
| 중단 뒤 재실행 | 같은 세대의 흔적(노드 1, 인덱스 1)을 ①에서 지우고 ④ 통과 |
| 뼈대 교체 경로 | 목록에서 지운 함수만 NotImplementedError, 나머지는 강사 코드로 완주(6초) |
| 전체 재색인 | 통과. 907초, 단위 297, LLM 279번(토큰 973,126), 노드 2,215, 병합 100묶음, 임베딩 1,669, 커뮤니티 78, 실패 단위 1(Groq JSON 400). README 7.1 |
| 전체 재색인(재사용) | 통과. 57초, K2 LLM 1번(실패했던 단위 성공), K8 LLM 1번, 임베딩 재사용 260. 활성 세대 `gen-lab-full-002`. README 7.3 |
| 결과 확인 도구 | Q01 적중(청크, 엔티티), Q02 적중(엔티티 직접 검색이 메움), Q14 근거 4개 중 2개, Q24 거시 질문은 커뮤니티 보고서가 재료. README 7.2 |
| 주석 점검 | Haiku 점검 뒤 docstring 누락 13개와 120자 초과 4줄 수정. 가운뎃점과 행 번호 참조 없음 |
| 문서 프로필 | 약관 머리줄에 version 등이 없어 LLM이 파일 이름을 version에 넣는 것을 확인하고 `DOC_PROFILES` 상수로 고침 |

Advisor(Opus) 사전 자문 1회, 팀원 리뷰 3회(기본 모델), 형식 점검 1회(Haiku) 수행. context7은 월 한도 초과로 쓰지 못해  
설치된 패키지 소스로 시그니처를 확인함.
