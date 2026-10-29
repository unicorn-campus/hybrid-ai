# GraphRAG 인덱싱 실습 예제

하이브리드 AI 교육 W5 「그래프DB 인덱싱」(교재 『W05 ~ W07』 30 ~ 62쪽) 실습용 예제임.  
RAG 실습(W3)이 만든 청크를 입력으로 받아 **지식 그래프(Neo4j)와 검색엔진 인덱스(OpenSearch)를 한 세대로 함께 만들고,  
검증을 통과하면 활성 세대 파일을 바꿔 게시**함. 레이어드 아키텍처 없이 **main 1개 + 핵심 모듈 1개**로 짰고,  
교육생은 핵심 모듈의 실습 함수 16개를 클론 코딩한 뒤 본인 코드로 바꿔 끼움.

## 수업용 명령 2개

가상환경은 상위 폴더 `hands-on/solutions/graphrag`에서 만들고 활성화함([상위 README 3절](../README.md#3-가상환경-설정과-패키지-설치)).  
활성화한 터미널에서 이 폴더(`indexer`)로 들어와 실행함. `{별명}`은 본인 별명(영문)으로 바꿈. 예) `hong-s1`

```bash
python index_graph.py --run {별명}-s1 --sample
```

```bash
python check_graph.py --qid Q09
```

첫 명령은 표본 10청크로 ① ~ ⑤를 끝까지 돌려 활성 세대를 만듦(약 1분, LLM 약 30번).  
둘째 명령은 질문 하나로 「검색엔진 → 청크 → 그래프 엔티티 → 커뮤니티 보고서」를 눈으로 확인함.  
프롬프트 앞에 `(.venv)`가 없으면 먼저 활성화함(3.2). 나머지 옵션은 8장에 있음.

## 1. 목표와 주요 기능

| 목표 | 내용 |
|---|---|
| 개념을 코드로 | 교재 30쪽 워크플로우(① 세대 ID → ② 청크 고정 → ③ KG 구축 K1 ~ K6, K8과 검색엔진 S1 ~ S3 → ④ 검증 → ⑤ 게시)를 함수 하나씩으로 봄 |
| 클론 코딩 | 단계마다 실습 함수 1개 이상, 모두 16개(직접 6개, 빈칸 10개). `my_graph.py`에 채우고 `--mine` 옵션으로 바꿔 끼움 |
| 눈으로 확인 | 단계마다 수(추출 단위, 노드와 관계, 병합 묶음, 임베딩, 커뮤니티, 적재 건수)와 예시를 출력하고, 확인 도구로 질문을 던져 봄 |

주요 기능

- 전체 재색인(full)만 함. 증분 색인과 K7 청크 정리는 교재(30, 45쪽)로만 다룸
- K2 추출 결과와 K8 보고서를 **재사용**함(본문 해시, 스키마 지문, 머리줄이 같으면 LLM을 부르지 않음). 강사 배포본으로 LLM 0번 실행 가능
- 시작 검사가 키, Neo4j(APOC, GDS), OpenSearch, 벡터 인덱스 차원을 확인하고 모자라면 할 일을 알려 줌
- 중단 뒤 같은 `--run`으로 다시 돌리면 그 세대의 흔적을 지우고 처음부터 만듦. ④ 검증에 실패하면 게시하지 않음

## 2. 디렉토리 구조

```text
hands-on/solutions/graphrag/
├─ README.md                   가상환경 설정과 실행 순서(공통)
├─ requirements.txt            GraphRAG 실습 공통 패키지 목록(이 파일로 설치. 서브 폴더에는 두지 않음)
├─ .venv/                      GraphRAG 실습 공용 가상환경(상위 폴더에서 만듦)
└─ indexer/
   ├─ README.md                이 문서
   ├─ index_graph.py           main: 설정 상수, 시작 검사, ① ~ ⑤ 순서, K2 병렬 호출, S1 임베딩(96건씩), K8 보고서 LLM 호출, 단계별 출력
   ├─ core_graph.py            핵심(클론 코딩 대상): 실습 함수 16개 + 제공 함수 5개
   ├─ my_graph.template.py     교육생 작업 파일의 뼈대(강사 템플릿). --mine 실행 때 my_graph.py로 복사됨. 맨 아래 USE_TEACHER_CODE 목록으로 안 채운 함수는 강사 코드가 대신 돎
   ├─ kr_tokenizer.py          제공(읽지 않아도 됨): RAG 실습 W3에서 작성한 Kiwi 토크나이저와 카드 별칭 규칙
   ├─ check_graph.py           결과 확인 도구(읽기만): 질문 → 검색엔진 → 청크 → 엔티티 → 커뮤니티 → 리랭크 → 적중 판정. --drop으로 세대 지우기
   └─ data/                    실행 결과(Git에 올리지 않음)
      ├─ active_generation.json              활성 세대 파일(⑤ 게시가 바꾸는 유일한 파일)
      ├─ generations/{세대 ID}/              prepared-chunks.json, kg_prepared.json, community_reports.json, build_report.json
      └─ teacher/                            강사 배포본(선택). --reuse data/teacher 로 LLM 없이 전체 그래프를 만듦
```

읽기만 하는 입력(저장소 안)

| 입력 | 경로 | 만든 곳 |
|---|---|---|
| 청크 260개(본문, 메타데이터) | `hands-on/solutions/rag/indexing/data/chroma` (collection `card_docs`) | RAG 실습 W3 `index_docs.py` |
| 그래프 스키마 3종 | `hands-on/solutions/graphrag/schema/doc/{regulation,benefit_guide,consult_log}/graph_schema.json`, `approval.json`, `schema_spec.json` | 스키마 설계 실습 |
| 승인 별칭 | `hands-on/solutions/rag/indexing/aliases_approved.json` | RAG 실습(강사 제공) |
| 평가셋(확인 도구) | `hands-on/solutions/eval-set.json` | RAG 실습 |

## 3. 준비물과 가상환경 설정

| 항목 | 값 |
|---|---|
| Python | 3.13 |
| LLM | Groq `openai/gpt-oss-120b` (K2 추출, K8 보고서). JSON 모드, temperature 0 |
| 임베딩 | Cohere `embed-v5.0-fast` (API, 2048차원). S1 청크, K6 엔티티 설명, K8 보고서, 확인 도구의 질문 |
| 리랭커 | Cohere `rerank-v4.0-fast`. 확인 도구 `--rerank`에서만 씀(인덱싱에는 없음) |
| 그래프 DB | Neo4j 2026.09.0 Community + APOC + GDS(`backing-services/neo4j/`) |
| 검색엔진 | OpenSearch 2.19.1(`backing-services/opensearch/`) |
| API 키 | 저장소 루트 `secrets/.env`에 `GROQ_API_KEY=...`, `COHERE_API_KEY=...`. RAG 실습과 같은 파일 |
| Neo4j 비밀번호 | 환경변수 `NEO4J_PASSWORD` 또는 `backing-services/neo4j/.env` |
| 로컬 모델 | 없음(GPU, torch 불필요) |

### 3.1 Neo4j와 OpenSearch 실행, 중지, 삭제

저장소 루트의 `backing-services` 폴더에서 실행함. 비밀번호 설정은 `backing-services/neo4j/README.md`를 따름.  
전체 명령 표(상태, 다시 켜기, 로그, rdb 포함)는 [상위 README 2.1](../README.md#21-백킹-서비스-실행-중지-삭제)에 있음.

```bash
docker compose -f neo4j/compose.yml up -d          # 실행
docker compose -f opensearch/compose.yml up -d
docker compose -f neo4j/compose.yml ps             # 상태 확인(healthy가 되면 준비 끝, 30초쯤)
docker compose -f opensearch/compose.yml ps
```

```bash
docker compose -f neo4j/compose.yml stop           # 중지(데이터 남음). 다시 켤 때는 start
docker compose -f opensearch/compose.yml stop
docker compose -f neo4j/compose.yml down           # 삭제: 컨테이너만(데이터 남음)
docker compose -f opensearch/compose.yml down
```

```bash
docker compose -f neo4j/compose.yml down -v        # 삭제: 데이터까지(그래프 세대와 검색 인덱스가 모두 사라짐)
docker compose -f opensearch/compose.yml down -v
```

`down -v` 뒤에는 그래프와 인덱스가 비어 있으므로 indexer를 다시 돌림(`--reuse data/teacher`면 LLM 없이 몇 분).

### 3.2 가상환경(상위 폴더에서 만들고 활성화)

가상환경과 패키지 설치는 이 폴더가 아니라 **상위 폴더 `hands-on/solutions/graphrag`**에서 함.  
만들기, 설치, PowerShell에서 활성화가 막힐 때 할 일은 [상위 README 3절](../README.md#3-가상환경-설정과-패키지-설치)을 따름.  
한 번 설치한 뒤에는 터미널 창마다 활성화만 하고 이 폴더로 들어옴.

| 터미널 | 활성화하고 이 폴더로 들어오기 |
|---|---|
| Windows PowerShell | `cd hands-on\solutions\graphrag` → `.venv\Scripts\Activate.ps1` → `cd indexer` |
| Windows Git Bash | `cd hands-on/solutions/graphrag` → `source .venv/Scripts/activate` → `cd indexer` |
| macOS, Linux | `cd hands-on/solutions/graphrag` → `source .venv/bin/activate` → `cd indexer` |

PowerShell에서 「이 시스템에서 스크립트를 실행할 수 없으므로 ...」로 막히면 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`를  
먼저 실행하고 다시 활성화함(지금 창에서만 허용. 상위 README 3.3).

- 저장소를 통째로 clone해서 씀. `indexer/` 폴더만 복사하면 Chroma, 스키마, `secrets/`를 찾지 못함
- RAG 실습 인덱싱 결과(`rag/indexing/data/chroma`)가 없으면 RAG 실습 `index_docs.py`를 먼저 돌리거나 강사 배포본을 복사함

## 4. 실행 방법

### 4.1 표본 실행(수업용)

```bash
python index_graph.py --run {별명}-s1 --sample
```

표본은 청크 10개(약관 2, 혜택 안내 4 「한빛 가족돌봄」, 상담 4)임. 상담 4개에는 앞 상담을 가리키는 쌍이 들어 있어 K5 병합을 볼 수 있음.

### 4.2 전체 실행(강사, 또는 강사 배포본 재사용)

```bash
python index_graph.py --run {별명}-f1
```

```bash
python index_graph.py --run {별명}-f1 --reuse data/teacher
```

전체 260청크는 K2 LLM 약 300번, K8 약 100번이 들어 10분 안팎임. 강사 배포본(`data/teacher/`)을 `--reuse`로 주면  
추출 결과와 보고서를 재사용해 LLM을 부르지 않고 임베딩만 새로 함.

### 4.3 결과 확인

```bash
python check_graph.py --qid Q09 --rerank
```

```bash
python check_graph.py "할부로 산 상품의 철회는 며칠 안에 요청해야 하나요?"
```

평가셋 번호(`--qid`)로 실행하면 마지막에 「적중 판정」이 붙음(정답 근거 문구가 상위 청크 본문이나 엔티티 설명에 있는지).  
표본 세대에서는 Q09(가족돌봄 바우처)와 상담 질문만 맞고, 약관 질문(Q01, Q02)은 전체 세대에서 확인함.

### 4.4 같은 입력으로 다시 돌리면

① 사전 검사가 「입력과 설정이 활성 세대와 같아 할 일 없음」으로 끝남. 그래도 새로 만들려면 `--full-reindex`를 붙이고  
**새 실행 이름**을 줌(활성 세대와 같은 이름은 거부함).

## 5. 단계별 출력 읽는 법

| 출력 머리 | 단계 | 봐야 할 것 | 표본 실행 값(2026-10-24, 강사 PC) |
|---|---|---|---|
| `시작 검사` | - | 키 2개, Neo4j와 APOC, GDS, OpenSearch 판 | APOC 2026.09.0, GDS 2026.09.0, OpenSearch 2.19.1 |
| `② 공통 단계` | ② | 문서 유형별 청크 수, 문서 수, chunk_id 예 | 10개(약관 2, 혜택 4, 상담 4), 문서 6개 |
| `① 세대 ID` | ① | `gen-lab-{별명}-{해시 8자리}`. 흔적 정리 줄이 있으면 중단 뒤 재실행임 | `gen-lab-hong-s1-…` |
| `[K1]` | K1 | 청크 → 단위 수, 청크 2개 이상에 걸친 단위 수, 단위가 없는 청크 | 10 → 18(약관 10, 혜택 4, 상담 4), 겹침 0, 없는 청크 0 |
| `[K2]` | K2 | LLM 추출 수와 재사용 수 | 처음 18번, 두 번째부터 0번(재사용 18) |
| `[K3]` | K3 | 가지치기 전 → 후 노드 수, 실패 단위, 머리줄 채움률, 단위 하나의 노드와 관계 | 94 → 94, 실패 0, 채움률 약관 100 혜택 40 상담 80 |
| `[K4]` | K4 | 노드 수(청크 노드 포함), 관계 수(FROM_CHUNK와 추출 관계) | 노드 약 100(청크 노드 10), 관계 약 150 |
| `[K5]` | K5 | 검사한 값 수, 합친 묶음 수, 값 예 | 값 6개 중 4묶음(상담 3, 상품 안내 1) |
| `[K6]` | K6 | 임베딩한 엔티티 수와 차원, 설명 글 예 3개 | 약 80개, 2048차원 |
| `[K8]` | K8 | 묶음 수, 3개 이상 묶음 수, LLM과 재사용 수, 보고서 제목 3개 | 묶음 16개 중 13개 요약 |
| `[S1]` | S1 | 새로 임베딩 수와 재사용 수, 벡터 앞 3개 | 처음 10개, 두 번째부터 재사용 10 |
| `[S2]` | S2 | 카드명 사전과 별칭 수, 첫 청크의 낱말 | 카드명 1개, 별칭 18개 |
| `[S3]` | S3 | 인덱스 이름, 문서 수, 지운 수, 넣은 수 | 문서 6개, 0건 지우고 10건 넣음 |
| `④ 검증` | ④ | 검색엔진 n/n, 청크 노드 = 고유 n/n, 중복 0. K8 줄은 커뮤니티 수와 빠짐 0 | 10/10, 10 = 10/10, 커뮤니티 13개 |
| `⑤ 게시` | ⑤ | 활성 세대 파일이 바뀐 세대 | 완료 약 60 ~ 70초 |

- LLM 추출은 실행마다 노드 수가 조금 다름(같은 입력이라도 86 ~ 94개). 수가 「약」인 이유임
- `[K3]` 뒤 「단위 … 의 노드 […]」 한 줄은 추출 단위 하나에서 나온 라벨과 관계 이름임. 교재 36쪽 「LLM이 돌려준 그래프」와 대조함

## 6. 교육생 교체 방법

1. `index_graph.py`는 고치지 않고 실행 명령에 `--mine`을 붙임. 처음 한 번 뼈대 `my_graph.template.py`가 `my_graph.py`로 복사됨  
   (`my_graph.py`는 Git이 무시하므로 강사 저장소를 pull해도 충돌이 나지 않음. 자세한 내용은 `../README.md` 5장)

   ```bash
   python index_graph.py (기존 옵션)          # 강사 코드(core_graph.py)로 실행
   python index_graph.py --mine (기존 옵션)   # 본인 코드(my_graph.py)로 실행
   ```

2. `my_graph.py` 맨 아래 `USE_TEACHER_CODE` 목록에서 **지금 채울 함수 이름을 지움**. 목록에 남은 함수는 강사 코드가 대신 돎
3. 그 함수를 채우고(직접 작성은 `NotImplementedError` 자리, 빈칸은 `"빈칸 N을 채울 것"` 자리) 같은 명령으로 다시 실행해  
   5장 출력을 강사 결과와 비교함
4. 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감(실습이 멈추지 않음)

실습 함수와 단계(채우는 순서. 교시 배치는 실습 가이드 참고)

| 순서 | 함수 | 방식 | 단계 | 교재 |
|---|---|---|---|---|
| 1 | `issue_generation` | 직접 | ① 세대 ID 규칙과 사전 검사 | 31 |
| 2 | `prepare_chunks` | 빈칸 2 | ② doc_id, chunk_id 규칙 | 31 |
| 3 | `split_by_heading` | 직접 | K1 조항 제목 줄로 자르기 | 34 |
| 4 | `k1_split_units` | 빈칸 2 | K1 단위 ID, 겹친 조항 합치기 | 34 |
| 5 | `extract_one` | 빈칸 2 | K2 추출기 호출, K3 가지치기 | 36 |
| 6 | `build_graph_rows` | 빈칸 2 | K4 청크 노드, FROM_CHUNK | 38 |
| 7 | `k5_merge` | 빈칸 2 | K5 같은 값 노드 모으기, mergeNodes | 41 |
| 8 | `entity_description` | 직접 | K6 「라벨: 속성=값」 | 43 |
| 9 | `k6_embed_descriptions` | 빈칸 2 | K6 벡터 저장, 벡터 인덱스 | 44 |
| 10 | `detect_communities` | 빈칸 2 | K8 GDS 투영, Leiden | 48 |
| 11 | `build_community_rows` | 빈칸 2 | K8 3개 이상 묶음, 구성원 ID | 49 |
| 12 | `embed_with_reuse` | 직접 | S1 본문 해시로 벡터 재사용 | 55 |
| 13 | `build_search_docs` | 빈칸 2 | S2 토큰화, 엔진 문서 한 건 | 53, 58 |
| 14 | `apply_search` | 빈칸 3 | S3 문서 단위 지우기, bulk, refresh | 59 |
| 15 | `verify_chunk_ids` | 직접 | ④ 세 목록 비교 | 61 |
| 16 | `publish_active` | 직접 | ⑤ 활성 세대 파일 교체 | 30, 62 |

교재 코드와 이름이 다른 곳: 교재 61쪽 `step4_verify`는 main에 있고 집합 비교 부분만 `verify_chunk_ids`로 뺌.  
교재 38쪽 `apply()`의 K4 부분은 `build_graph_rows`(행 만들기)와 main의 `k4_write`(쓰기)로 나눔.

## 7. 실측값(강사 PC, 2026-10-24)

### 7.1 전체 실행(260청크, `--run full-001`)

| 항목 | 값 |
|---|---|
| 걸린 시간 | 907초(약 15분). K2 추출 10분, K8 보고서 4분 20초, 나머지 1분 |
| ② 청크 | 260개(약관 15, 혜택 안내 197, 상담 48), 문서 50개 |
| K1 | 추출 단위 297개(약관 조항 52, 혜택 197, 상담 48). 두 청크에 걸친 단위 0개. 단위가 없는 청크 5개(약관 표지, 메타데이터, 차례, 각주 쪽) |
| K2, K3 | LLM 279번(표본 실행 결과 18개 재사용), 토큰 973,126. 가지치기 뒤 노드 1,955개. 실패 단위 1개(혜택 안내 청크 1개, Groq JSON 모드 400이 3번 연속) |
| K4 | 노드 2,215개(청크 노드 260개 포함), 관계 3,541개(FROM_CHUNK 1,955, 추출 관계 1,586) |
| K5 | 검사한 값 113개 중 100묶음 합침(상담 48, 상품 안내 52), FROM_CHUNK 중복 0 |
| K6 | 엔티티 설명 임베딩 1,669개(2048차원) |
| K8 | 묶음 92개 중 엔티티 3개 이상 78개 요약(LLM 78번). 가장 큰 묶음은 약관 162개 엔티티 |
| S1 ~ S3 | 임베딩 250개 새로(표본 10개 재사용), 카드명 사전 64개, 별칭 390개, 문서 50개에 260건 적재 |
| ④, ⑤ | 통과(검색엔진 260/260, 청크 노드 260 = 고유 260/260, 커뮤니티 78개), 활성 세대 `gen-lab-full-001-807ef9e6` |
| 엔티티 라벨 | BenefitCondition 390, BenefitLimit 310, Benefit 267, BenefitExclusion 257, Proposal 101, Handling 81, ProductGuide 64, Clause 52, Complaint 51, Consultation 48, ReconsiderCondition 19, Deadline 16, Requirement 12, TermsDocument 1 |
| 강사 배포본 재사용 | 57초(7.3) |

### 7.2 결과 확인 도구(전체 세대, 상위 청크 4개, 엔티티 5개)

| 질문 | 검색엔진 1위 | 적중 판정 | 읽는 법 |
|---|---|---|---|
| Q01 연회비 면제 기준 | D1-0007(제10조) | 적중(청크, 엔티티) | BM25 1위가 바로 약관 조항. 엔티티 설명에도 같은 문장이 있음 |
| Q02 할부 철회 기한 | D1-0008(제13조 쪽) | 적중(엔티티) | 상위 청크 4개에는 제16조의2 쪽이 없지만 엔티티 직접 검색이 「7일 이내」 기한 엔티티를 찾음(교재 42쪽 「서로 메운 예」) |
| Q14 M-1042 회원 상담 이력 | D3-0035(최근 상담) | 근거 4개 중 2개 적중 | 첫 상담 문장은 적중, 최근 상담의 두 문장은 상위 4개 밖. 회원 필터와 FOLLOWS 추적은 다음 실습(검색기)에서 함 |
| Q24 받아들인 제안의 공통점 | D3-0011 | 근거 5개 중 1개 적중 | 거시 질문이라 청크 몇 개로는 못 답함. [4] 커뮤니티 보고서 3개(민원 처리 지연, 반복 신청 불만, 연회비 대비 가치)가 답의 재료임 |

- 적중 판정은 「정답 근거 문구가 상위 청크 본문이나 엔티티 설명에 그대로 있는가」만 봄. 답을 만드는 LLM은 부르지 않음
- 표본 세대(10청크)에서는 Q09(가족돌봄 바우처)가 청크와 엔티티 둘 다 적중, 리랭크 1위 0.885

### 7.3 강사 배포본 재사용(`--run full-002 --reuse data/teacher --full-reindex`)

| 항목 | 값 |
|---|---|
| 걸린 시간 | 57초(전체 실행 907초의 약 1/16) |
| K2 | LLM 1번(full-001에서 실패한 단위 1개만 다시 물어 성공), 재사용 296개. 실패 단위 0 |
| K8 | 보고서 LLM 1번, 재사용 77개 |
| S1 | 임베딩 0개 새로, 260개 재사용(활성 세대 인덱스의 본문 해시가 같음). K6 엔티티 설명 1,673개는 새로 임베딩 |
| ④, ⑤ | 통과, 활성 세대 `gen-lab-full-002-14209840` |

- `data/teacher/`는 이 `full-002` 결과(실패 단위 0)로 바꿔 둠. 교육생 PC에서는 활성 세대가 없어 S1 임베딩 260개도 새로 하므로 1 ~ 2분 더 걸림
- 교육생 Chroma가 강사 것과 같은 코드와 문서로 만든 것이면 본문 해시가 같아 그대로 재사용됨. 다르면 그 단위만 LLM을 부름

### 7.2 교재 그림과 이 실습 데이터가 다른 곳

| 항목 | 교재 | 이 실습 | 이유 |
|---|---|---|---|
| 약관 추출 단위 | 청크 10 → 단위 51, 겹친 조항 있음(32, 34쪽) | 청크 15 → 단위 52, 겹친 조항 0 | RAG 실습 Chroma는 쪽 단위 청킹이라 조항이 두 청크에 걸치지 않음. 합치기 코드는 그대로 있지만 이 데이터에서는 돌지 않음 |
| K5 병합 예 | TermsDocument 16 → 1(40쪽) | 상담 Consultation(record_id), 상품 안내 ProductGuide(product_id) | 약관 문서 노드가 2개뿐임. 상담은 앞 상담 참조(FOLLOWS)로 생긴 노드와 본문 노드가 합쳐짐 |
| 임베딩 | KURE-v2 768차원(43쪽) | Cohere embed-v5.0-fast 2048차원 | 설치가 가볍고 RAG 실습과 같은 키 |
| 별칭 수 | 189개(57쪽) | 390개(승인 별칭 포함) | RAG 실습과 같은 규칙과 승인 파일 |
| 머리줄 칸 | 모두 채움(35쪽) | 약관은 문서 프로필 상수로 채움(100%), 혜택 40%, 상담 80% | Chroma 메타데이터에 benefit_id, section_label, topic이 없음 |
| 게시 | 검색엔진 별칭 전환(62쪽) | 활성 세대 파일 하나 교체 | 세대마다 인덱스 하나를 두고 검색기가 활성 세대 파일로 고름(교재 30쪽 ②) |

## 8. 옵션(부록)

| 옵션 | 뜻 | 언제 |
|---|---|---|
| `--run {이름}` | 실행 이름(필수). 같은 이름이면 같은 세대 ID. 별명을 넣어 여럿이 한 DB를 써도 섞이지 않게 함 | 항상 |
| `--sample` | 표본 10청크만 | 수업 중 |
| `--full-reindex` | 사전 검사를 건너뛰고 새 세대를 만듦 | 같은 입력으로 다시 만들 때(새 이름과 함께) |
| `--skip-communities` | K8 커뮤니티 요약을 건너뜀 | K1 ~ K6, S1 ~ S3만 빨리 볼 때. GDS가 없으면 자동 |
| `--reuse {폴더}` | 앞 결과 폴더(kg_prepared.json, community_reports.json) | 강사 배포본으로 LLM 없이 돌릴 때. 없으면 활성 세대 폴더를 씀 |
| `--chunks {파일}` | Chroma 대신 쓸 청크 파일(prepared-chunks.json) | 강사 배포 청크로 맞출 때 |
| `check_graph.py --drop {세대}` | 그 세대의 노드와 검색엔진 인덱스를 지움(활성 세대는 거부) | 실패한 세대 정리 |

환경변수: `NEO4J_URI`(기본 bolt://localhost:7687), `NEO4J_USER`, `NEO4J_PASSWORD`, `OPENSEARCH_URL`(기본 http://127.0.0.1:9200).  
다른 PC의 저장소를 쓰면 이 값만 바꾸고, 세대 ID(별명)로 서로 구분함.

## 9. 막혔을 때

| 증상 | 할 일 |
|---|---|
| `secrets/.env에 … 줄이 필요함` | 강사에게 받은 키 두 줄을 `secrets/.env`에 넣음 |
| `Neo4j 접속 또는 APOC 확인 실패` | `backing-services`에서 `docker compose -f neo4j/compose.yml up -d`, `ps`로 healthy 확인 |
| `GDS가 없어 K8을 건너뜀` | `neo4j/README.md` 문제 해결의 `gds.version` 항목. 수업은 K8 없이 진행 가능 |
| `… 인덱스가 768차원으로 이미 있음` | 다른 실습 데이터가 있는 DB임. 안내대로 `DROP INDEX` 하거나 실습용 Neo4j를 따로 띄움 |
| 429(호출 제한)로 K2가 느림 | 기다렸다 다시 부름(최대 6번). 계속 막히면 `--reuse data/teacher` |
| 중단된 뒤 다시 돌림 | 같은 `--run`으로 다시 실행하면 ① 에서 흔적을 지우고 처음부터 만듦 |
| `④ 검증 실패` | `data/generations/{세대}/build_report.json`의 missing, extra, duplicate 목록을 봄. 활성 세대는 그대로임 |
| 본인 코드로 바꿨더니 수가 다름 | `--mine`을 빼고 실행해 강사 결과와 비교. 함수 하나씩 USE_TEACHER_CODE에서 빼며 확인 |

## 10. 한계

- 약관 그래프 스키마는 채움 시험 합격 기준 미달 상태로 확정된 것임(`schema/doc/regulation/approval.json`의 `below_criteria`)
- 증분 색인이 없으므로 문서가 바뀌면 새 실행 이름으로 전체 재색인함. 옛 세대는 `check_graph.py --drop`으로 지움
- K5 병합은 속성이 다르면 목록 첫 노드 값을 남김(`properties: 'discard'`). 어느 값이 남을지는 정해져 있지 않음
- K8은 문서 종류를 건너는 관계가 없어 상담과 약관을 한 묶음으로 엮지 못함
- LLM 추출은 실행마다 조금 다름. 같은 입력의 재실행은 재사용으로 같지만, 처음부터 다시 뽑으면 노드 수가 달라짐
- Groq JSON 모드가 가끔 「Failed to generate JSON」 400을 냄. 같은 입력으로 최대 4번 묻고(`LLM_RETRIES` 3) 그래도 실패하면  
  그 단위만 기록하고 계속함. 실패한 청크도 청크 노드는 있어 ④는 통과하고, 그 청크의 엔티티만 없음(전체 실행에서 297개 중 1개)
- 혜택 안내와 상담의 머리줄 칸 일부(benefit_id, section_label, topic)는 Chroma 메타데이터에 없어 비워 보냄.  
  약관은 `DOC_PROFILES` 상수(버전 1.2, 시행일, 이전 판)로 채움
- 실행 중 `LLMInterface is deprecated` 경고를 숨겼음(neo4j-graphrag 1.22.0). 동작에는 영향 없음
