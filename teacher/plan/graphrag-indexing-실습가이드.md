# GraphRAG 인덱싱 실습 가이드(교육생용)

| 항목 | 내용 |
|---|---|
| 대상 | 하이브리드 AI 교육 W5 「그래프DB 인덱싱」. 엔지니어, 데이터 모델러, 기획자 혼합(파이썬 초보 포함) |
| 교재 | 『신한카드 하이브리드AI_W05 ~ W07』 30 ~ 62쪽 |
| 예제 | [hands-on/solutions/graphrag/indexer](https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/README.md) |
| 시간 | 이론 1교시 + 클론 코딩 3교시(교시 A, B, C) = 4H |
| 완료 | 본인 코드(`my_graph.py`)로 표본 10청크를 ① ~ ⑤ 끝까지 돌려 ④ 검증을 통과하고, 질문 하나로 결과를 확인함 |

## 0. 이 실습에서 만드는 것

RAG 실습(W3)에서 만든 청크 260개를 입력으로, **그래프(Neo4j)와 검색엔진 인덱스(OpenSearch)를 한 세대로 함께 만듦**.  
검색엔진이 찾은 청크의 `chunk_id`와 같은 청크 노드가 그래프에 있어, 검색 결과에서 그래프로 건너갈 수 있음(교재 29쪽).

```text
RAG 실습 Chroma(청크 260개)
   │ ② 공통 단계: chunk_id 부여, 파일로 고정
   ├────────────────────────────┐
   ▼ KG 구축                     ▼ 검색엔진 인덱싱
 K1 추출 단위 나누기            S1 임베딩(Cohere)
 K2 LLM 추출 → K3 가지치기      S2 키워드 분석(Kiwi)
 K4 Neo4j 적재(청크 노드 + FROM_CHUNK)   S3 OpenSearch에 문서 단위로 쓰기
 K5 병합 → K6 설명 임베딩 → K8 커뮤니티 요약
   └────────────┬───────────────┘
                ▼
        ④ 검증(chunk_id 목록 비교) → ⑤ 게시(활성 세대 파일 교체)
```

수업에서는 **표본 10청크**(약관 2, 혜택 안내 4, 상담 4)로 돌림. 1분 안에 끝나고 LLM을 약 30번 부름.  
전체 260청크는 강사가 돌린 결과를 배포하며, 받은 폴더를 `--reuse`로 주면 LLM 없이 2 ~ 3분에 전체 그래프를 만들 수 있음.

## 1. 사전 준비(수업 전주까지)

| 번호 | 할 일 | 확인 |
|---|---|---|
| 1 | 저장소 최신 `pull`, Python 3.13 | `python --version` |
| 2 | RAG 실습 인덱싱 결과가 있음: `hands-on/solutions/rag/indexing/data/chroma/chroma.sqlite3` | 없으면 RAG 실습 `index_docs.py`를 돌리거나 강사 배포본 복사 |
| 3 | Docker Desktop 설치, Neo4j와 OpenSearch 기동([backing-services/neo4j](https://github.com/unicorn-campus/hybrid-ai/blob/main/backing-services/neo4j/README.md), [opensearch](https://github.com/unicorn-campus/hybrid-ai/blob/main/backing-services/opensearch/README.md)) | `docker compose -f neo4j/compose.yml ps`가 `healthy` |
| 4 | 가상환경 설치(README 3장. PowerShell, Git Bash, macOS와 Linux 명령이 따로 있음) | 설치 확인 명령이 `ok` |
| 5 | `secrets/.env`에 `GROQ_API_KEY`, `COHERE_API_KEY`(강사 배포) | 아래 표본 실행의 시작 검사 통과 |

사전 준비가 끝났는지는 표본 실행 한 번으로 확인함(시작 검사가 2 ~ 5를 모두 검사해 모자란 것을 알려 줌).

```bash
cd hands-on/solutions/graphrag/indexer
../.venv/Scripts/python.exe index_graph.py --run {별명}-s1 --sample
```

`{별명}`은 본인 영문 별명(예: `hong-s1`). 세대 ID에 들어가므로 여럿이 한 DB를 써도 섞이지 않음.  
macOS와 Linux는 `../.venv/Scripts/python.exe` 대신 `../.venv/bin/python`.

## 2. 수업 흐름

| 교시 | 내용 | 실습 함수(채우는 순서) |
|---|---|---|
| 이론 | 교재 28 ~ 62쪽. 저장소 구성안, 워크플로우, K1 ~ K8, S1 ~ S3, 검증과 게시 | - |
| A | 강사 코드로 표본 실행과 출력 읽기 → 교체 설정 → 세대와 청크, 추출 단위, 추출 | `issue_generation`, `prepare_chunks`, `split_by_heading`, `k1_split_units`, `extract_one` |
| B | 그래프 적재, 병합, 설명 임베딩, 커뮤니티 | `build_graph_rows`, `k5_merge`, `entity_description`, `k6_embed_descriptions`, `detect_communities`, `build_community_rows` |
| C | 검색엔진 인덱싱, 검증, 게시 → 결과 확인 도구로 질문 → 조 간 코드 리뷰 | `embed_with_reuse`, `build_search_docs`, `apply_search`, `verify_chunk_ids`, `publish_active` |

방식 두 가지(교재의 코드가 어떤 모양인지에 따라 정함)

- **직접 작성**(6개): 함수 몸통이 `raise NotImplementedError("여기에 본인 코드를 작성함")` 한 줄임. docstring의 「방법」과 「힌트」를 보고 씀
- **빈칸 채우기**(10개): 거의 완성된 코드 중간에 `raise NotImplementedError("빈칸 N을 채울 것")`이 있음.  
  바로 위 주석이 무엇을 채울지 알려 줌. 채운 뒤 그 `raise` 줄은 지움

## 3. 따라하기

### Step 1. 강사 코드로 표본 실행(교시 A 시작)

```bash
../.venv/Scripts/python.exe index_graph.py --run {별명}-s1 --sample
```

출력에서 아래 줄을 찾아 수를 적어 둠(본인 코드로 바꾼 뒤 같은 수가 나와야 함). 값은 강사 PC 실측이며 LLM 추출은 실행마다 조금 다름.

| 줄 | 적어 둘 것 | 강사 PC 값 |
|---|---|---|
| `[K1]` | 청크 → 단위 수 | 10 → 18(약관 10, 혜택 4, 상담 4) |
| `[K3]` | 남은 노드 수, 실패 단위 | 약 90, 실패 0 |
| `[K4]` | 노드 수, 관계 수 | 약 100(청크 노드 10 포함), 약 150 |
| `[K5]` | 합친 묶음 수 | 4(상담 3, 상품 안내 1) |
| `[K6]` | 임베딩한 엔티티 수, 차원 | 약 80, 2048 |
| `[K8]` | 묶음 수, 요약한 묶음 수 | 16, 13 |
| `[S1]` `[S2]` `[S3]` | 임베딩 수, 별칭 수, 넣은 건수 | 10, 18, 10 |
| `④ 검증` | 검색엔진 n/n, 청크 노드, 커뮤니티 | 10/10, 10 = 10/10, 13개 |
| `⑤ 게시` | 활성 세대 | `gen-lab-{별명}-s1-…` |

같은 명령을 한 번 더 돌리면 ① 에서 「할 일 없음」으로 끝남(교재 31쪽 사전 검사).

### Step 2. 결과 확인 도구로 질문 던지기

```bash
../.venv/Scripts/python.exe check_graph.py --qid Q09 --rerank
```

[1] 검색엔진(BM25와 벡터를 RRF로 합침) → [2] 청크의 엔티티(FROM_CHUNK) → [3] 엔티티 직접 검색(K6 벡터) →  
[4] 커뮤니티 보고서 → [5] 리랭크 → [6] 적중 판정 순서로 나옴. Q09(가족돌봄 바우처)는 청크와 엔티티 둘 다 적중이어야 함.

### Step 3. 본인 코드로 바꿀 준비

1. `index_graph.py` 위쪽 import 한 줄을 `import my_graph as core`로 바꿈
2. `my_graph.py` 맨 아래 `USE_TEACHER_CODE` 목록을 봄. 여기 있는 함수는 **강사 코드가 대신 돎**
3. 지금 채울 함수 이름을 목록에서 지움 → 그 함수를 채움 → Step 1 명령으로 다시 실행 → 수를 비교함
4. 새 실행 이름은 필요 없음. 같은 `--run {별명}-s1`로 돌리면 ① 사전 검사가 「할 일 없음」이라고 하므로 `--full-reindex`를 붙이고  
   이름을 `{별명}-s2`처럼 바꿈(활성 세대와 같은 이름은 거부함)

```bash
../.venv/Scripts/python.exe index_graph.py --run {별명}-s2 --sample --full-reindex
```

LLM 추출(K2)과 보고서(K8)는 앞 실행 결과를 재사용하므로 두 번째부터는 LLM을 부르지 않고 10초 안에 끝남.  
막히면 함수 이름을 목록에 다시 넣고 다음 함수로 넘어감.

### Step 4. 교시 A 함수 5개

| 순서 | 함수 | 방식 | 채울 것 | 확인할 출력 |
|---|---|---|---|---|
| 1 | `issue_generation` | 직접 | 세대 ID `gen-lab-{이름}-{해시 8자리}`, 사전 검사 조건 3개를 and로 | `① 세대 ID gen-lab-…` 가 강사 코드 때와 같은 ID |
| 2 | `prepare_chunks` | 빈칸 2 | doc_id 규칙(상담은 record_id, 나머지는 파일 이름 해시 16자리), chunk_id 규칙 | `② 공통 단계` 의 chunk_id 예가 같음, 문서 6개 |
| 3 | `split_by_heading` | 직접 | 제목 줄 + 다음 줄 ① 조건으로 시작점, 다음 시작점 전까지 한 조각, 장 제목 줄 버림 | `[K1]` 약관 단위 10개 |
| 4 | `k1_split_units` | 빈칸 2 | 단위 ID = 문서 ID + `#` + 조항 번호, 겹친 조항 합치기 | `[K1]` 단위 18개, 겹침 0(이 데이터는 쪽 단위 청킹이라 겹치는 조항이 없음) |
| 5 | `extract_one` | 빈칸 2 | `TextChunk(uid=단위 ID)`를 추출기에, 결과를 바로 가지치기 | `[K2]` 0번(재사용) 또는 18번, `[K3]` 실패 0 |

### Step 5. 교시 B 함수 6개

| 순서 | 함수 | 방식 | 채울 것 | 확인할 출력 |
|---|---|---|---|---|
| 6 | `build_graph_rows` | 빈칸 2 | 청크마다 `Chunk` 노드, 엔티티마다 나온 청크로 `FROM_CHUNK` | `[K4]` 청크 노드 10, FROM_CHUNK 수 = 엔티티 수 |
| 7 | `k5_merge` | 빈칸 2 | 같은 세대에서 값이 같은 노드 모으기, `apoc.refactor.mergeNodes` | `[K5]` 4묶음 |
| 8 | `entity_description` | 직접 | 관리용 속성 빼고 이름순 「라벨: k=v, …」 | `[K6]` 설명 글 예가 강사 것과 같은 꼴 |
| 9 | `k6_embed_descriptions` | 빈칸 2 | `setNodeVectorProperty`로 저장, 벡터 인덱스 생성 | `[K6]` 임베딩 약 80개, 2048차원 |
| 10 | `detect_communities` | 빈칸 2 | `gds.graph.project`(무방향), `gds.leiden.stream`(씨앗 42, 병렬 1) | `[K8]` 묶음 16개 |
| 11 | `build_community_rows` | 빈칸 2 | 3개 이상 묶음만, 구성원 번호 → 엔티티 ID | `[K8]` 13개 요약, `④ 검증(K8)` 통과 |

### Step 6. 교시 C 함수 5개

| 순서 | 함수 | 방식 | 채울 것 | 확인할 출력 |
|---|---|---|---|---|
| 12 | `embed_with_reuse` | 직접 | 해시가 옛 벡터에 없는 글만 임베딩, 원래 순서로 합침 | `[S1]` 두 번째 실행부터 재사용 10 |
| 13 | `build_search_docs` | 빈칸 2 | `lexicon.tokenize`, 엔진 문서 한 건(text_tokens는 공백으로 이음) | `[S2]` 첫 청크의 낱말이 같음 |
| 14 | `apply_search` | 빈칸 3 | `delete_by_query`(doc_id), `bulk`(_id = chunk_id), `refresh` | `[S3]` 10건 넣음 |
| 15 | `verify_chunk_ids` | 직접 | 집합 비교 2개 + 중복 노드 검사 | `④ 검증: 통과` |
| 16 | `publish_active` | 직접 | 임시 파일에 쓴 뒤 `os.replace` | `⑤ 게시`, `data/active_generation.json`이 새 세대 |

교시 C 끝: `USE_TEACHER_CODE` 목록이 비어 있고 Step 1 명령이 끝까지 돌면 완료임. Step 2로 본인 세대에서 질문을 확인함.

## 4. 완료 기준

| 항목 | 기준 |
|---|---|
| 교체 실행 | `USE_TEACHER_CODE`가 빈 `my_graph.py`로 표본 실행이 ④ 통과, ⑤ 게시 |
| 수 비교 | `[K1]` 단위 18개, `[K5]` 4묶음, `④` 10/10과 커뮤니티 13개가 강사 결과와 같음(노드 수는 ±10 허용) |
| 확인 도구 | Q09가 청크와 엔티티 둘 다 적중. 자유 질문 1개의 [2] 엔티티와 [4] 보고서를 조에서 설명할 수 있음 |
| 제출 | `my_graph.py`와 마지막 실행 화면 캡처 |

## 5. 막혔을 때

| 증상 | 할 일 |
|---|---|
| 시작 검사에서 멈춤 | 출력의 「→」 줄이 할 일임(키 넣기, compose 띄우기 등) |
| `NotImplementedError: 빈칸 1을 채울 것` | 그 함수의 빈칸을 아직 안 채움. 채웠으면 `raise` 줄을 지웠는지 확인 |
| 본인 코드로 바꿨더니 수가 다름 | 함수 이름을 목록에 다시 넣고 실행해 어느 함수에서 달라지는지 하나씩 좁힘 |
| `세대 …는 지금 활성 세대임` | `--run` 이름을 바꿈(`{별명}-s3`) |
| 429(호출 제한)로 K2가 느림 | 기다렸다 다시 부름. 계속 막히면 강사 배포본 `--reuse data/teacher` |
| 중단된 뒤 다시 돌림 | 같은 `--run`으로 다시 실행하면 ① 에서 흔적을 지우고 처음부터 만듦 |
| 실패한 세대가 쌓임 | `check_graph.py --drop gen-lab-…`(활성 세대는 거부) |

## 6. 더 해 보기(선택)

- 표본 목록 `SAMPLE_CHROMA_IDS`(main 상수)에 상담 청크를 더 넣고 K5 병합 수가 어떻게 바뀌는지 봄
- `COMMUNITY_MIN_SIZE`를 2로 바꾸면 커뮤니티가 몇 개 늘고 보고서가 어떻게 달라지는지 봄
- 강사 배포본으로 전체 260청크를 만든 뒤 Q01(연회비 면제), Q02(철회 기한), Q14(상담 이력)로 확인 도구를 돌리고 적중 여부를 적음
- 교재 62쪽 별칭 전환을 직접 구현해 봄(`update_aliases` 한 요청으로 remove와 add)

## 7. 참고 링크

- 예제 README: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/README.md
- 핵심 모듈(정답): https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/core_graph.py
- 교육생 뼈대: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/my_graph.py
- 결과 확인 도구: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/check_graph.py
- 개발계획서(강사용): https://github.com/unicorn-campus/hybrid-ai/blob/main/teacher/plan/graphrag-indexing-개발계획서.md
- Neo4j 컨테이너: https://github.com/unicorn-campus/hybrid-ai/blob/main/backing-services/neo4j/README.md
- OpenSearch 컨테이너: https://github.com/unicorn-campus/hybrid-ai/blob/main/backing-services/opensearch/README.md
