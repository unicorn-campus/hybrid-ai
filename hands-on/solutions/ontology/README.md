# 온톨로지 실습 예제 — Turtle 원본으로 하는 스키마 설계, 인덱싱, 검색

하이브리드 AI 교육 「관계로 찾기(GraphRAG)」 예제에 온톨로지를 결합한 폴더임.  
Class, 관계, 검사 규칙, 맞추기 표를 표준 형식(Turtle) 파일로 적어 두고, 스키마 설계와 인덱싱과 검색이 그 파일을 읽음.  
가상환경과 패키지 설치는 **이 폴더(`hands-on/solutions/ontology`)에서만** 하고, 서브 폴더는 같은 가상환경을 활성화한 채 실행함.


## 0. 이 폴더는 무엇인가(Turtle 원본판)

`hands-on/solutions/graphrag`를 복사하고, 옛 `graphrag-ontology` 폴더에서 사람이 승인한 설계 결과(2026-11-18)를 얹은 뒤,  
온톨로지를 적는 곳을 JSON에서 Turtle로 바꾼 폴더임(2026-11-22).  
`graphrag-ontology` 폴더는 이 폴더로 바뀌면서 2026-11-22에 저장소에서 지웠고, Git 기록(커밋 c4fbcd7까지)에 남아 있음.  
전제: 정형 데이터(회원, 카드, 거래)의 행은 PostgreSQL에 그대로 두고, 문서 노드에는 키 속성(상품 ID, 회원 가명 ID)만 둠.

### 0.1 무엇이 원본이고 무엇이 생성물인가

| 구분 | 파일 | 담는 것 | 쓰는 표준 |
|------|------|---------|-----------|
| 원본(승인본) | `ttl/card.ttl` | Class 9개와 문서 전용 노드 타입 3개의 이름, 뜻, 같은 말, 키, 허용 값 목록. 관계 6개와 반대 이름. 건너가는 경로 P1 ~ P6 | OWL, RDFS, SKOS |
| 원본(승인본) | `ttl/shapes/{regulation,benefit_guide,consult_log}.ttl` | 문서 종류마다 노드 타입의 속성, 허용 패턴, 고유 키, 채우는 방법 | SHACL |
| 원본(승인본) | `ttl/shapes/checks.ttl` | 검사 규칙 K01 ~ K09 | SHACL |
| 원본(승인본) | `ttl/maps/topic.ttl`, `ttl/maps/category.ttl` | 주제 맞추기 표, 업종 맞추기 표(확정한 것과 아직 확정하지 않은 것) | SKOS |
| 초안 | `schema/doc-ontology/draft-ttl/` | 스키마 설계 중에만 생김. 승인본을 복사해 고치는 곳. 승인받으면 승인본으로 올리고 지움 | 승인본과 같음 |
| 생성물 | `schema/doc-ontology/{문서 종류}/graph_schema.json`, `output/schema_draft.json`, 검토 표, 그림 | Turtle에서 도구가 만들어 냄. 손으로 고치지 않음 | - |
| 설정(JSON 그대로) | `unit_text_rules.json`, `approval.json`, `schema/rdb/app_views.json` | 추출 단위 글 규칙, 승인 기록, 정형 조회용 뷰 설명. 뜻이 아니라 실행 설정이라 옮기지 않음 | - |

- 뜻은 Turtle에, 실행 설정은 JSON에 둠. neo4j-graphrag는 Turtle을 읽지 못해 `graph_schema.json`을 만들어 줌  
- 표준에 없어 우리가 지은 낱말(`card:kind`, `card:order`, `card:fill` 등)은 `indexer/core_turtle.py`의 `CUSTOM_TERMS`에 뜻과 함께 적어 둠  
- 낱말 주소 `card:`는 `https://hanbit-card.example/ontology#`임(가상 회사 주소)  
- 옛 JSON 기록(`common/concepts.json`, `common/*_map_approved.json`)과 옛 도구(`tools/build_schema.py`,  
  `common/tools/check_concepts.py`)는 이 폴더에서 지웠음. 내용은 모두 Turtle로 옮기고 대조했으며, 옛 파일은 Git 기록의 `graphrag-ontology` 폴더에 남아 있음

### 0.2 어느 단계가 Turtle을 어떻게 읽고 쓰는가

| 단계 | 하는 일 | 파일과 함수 |
|------|---------|-------------|
| 스키마 설계: 초안 | 승인본을 초안 폴더로 복사, 승인본과의 차이, 승인본으로 올리기, 버리기 | `ttl/tools/draft.py`(start, diff, promote, discard) |
| 스키마 설계: 기계 검사 | 문법, SHACL 규격, 허용 값, 키 속성, 채우는 방법, 그래프 스키마 꼴, 생성물과의 일치, 설계 입력과의 대조, 맞추기 표 | `ttl/tools/check_ttl.py`(`--draft`를 붙이면 초안) |
| 스키마 설계: 생성물 | 그래프 스키마 JSON과 Mermaid 그림, 사람이 볼 검토 표 | `ttl/tools/build_from_ttl.py`, `ttl/tools/render_review.py` |
| 스키마 설계: 채우기 시험 | 초안에서 만든 스키마로 추출하고, 검사 규칙은 인덱서와 같은 파일(`shapes/checks.ttl`)로 검사 | `schema/doc-ontology/tools/fill_test.py` |
| 스키마 설계: 맞추기 표 | LLM이 후보를 내고 사람이 확정한 것을 `maps/*.ttl`에 씀 | `schema/doc-ontology/common/tools/draft_topic_map.py`, `draft_category_map.py`, `ttl/tools/ttl_write.py` |
| 스키마 설계: 확정 | 초안을 올리고 승인 기록을 남김 | `schema/doc-ontology/tools/finalize.py` |
| 인덱서 | 공통 개념 층 싣기, 주제 이름 맞추기, 업종 잇기, SHACL 검사(K01 ~ K09), 재사용 판단(내용 지문) | `indexer/core_turtle.py`의 `load_concepts`, `load_topic_map`, `load_category_map`, `run_checks`, `signature` |
| 검색기 | 엔티티 찾기의 키 표를 `owl:hasKey`에서 읽음. 그 밖은 그래프에 실린 공통 개념 층을 읽음 | `core_turtle.entity_keys` → `retriever/search_graph.py`의 `find_entities` |

- 스키마 설계 절차는 `prompts/design-kg-schema-ontology.md`를 따름(JSON에 적던 옛 온톨로지 프롬프트를 대신함)  
- 인덱서와 검색기는 Turtle을 읽기만 하고, 쓰는 것은 스키마 설계 도구뿐임  
- 지문은 글자가 아니라 내용으로 만듦. 주석이나 줄 순서만 바뀌면 지문이 같아 다시 인덱싱하지 않음

### 0.3 실행 순서

```powershell
# 0) 가상환경(이 폴더에서 한 번). rdflib, pyshacl이 더 들어 있음
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
# 1) 온톨로지 원본 검사 → 그래프 스키마 확인
cd ttl
..\.venv\Scripts\python.exe tools\check_ttl.py
..\.venv\Scripts\python.exe tools\build_from_ttl.py --check
# 2) 인덱싱(전체 260청크). LLM 추출이 돌아감
cd ..\indexer
..\.venv\Scripts\python.exe index_graph.py --run {별명}-f1
# 3) 검색
cd ..\retriever
..\.venv\Scripts\python.exe check_paths.py --member-id M-1042
..\.venv\Scripts\python.exe search_graph.py --qid Q01
```

온톨로지를 고칠 때(승인본을 바로 고치지 않음)

```powershell
cd ttl
..\.venv\Scripts\python.exe tools\draft.py start            # 승인본 → 초안 폴더
# 초안 폴더(schema\doc-ontology\draft-ttl)의 Turtle을 고침
..\.venv\Scripts\python.exe tools\build_from_ttl.py --draft # 스키마 초안과 그림
..\.venv\Scripts\python.exe tools\check_ttl.py --draft      # 기계 검사
..\.venv\Scripts\python.exe tools\draft.py diff             # 승인본과 달라진 곳
..\.venv\Scripts\python.exe tools\render_review.py          # 사람이 볼 검토 표(review\step5-ttl.md)
# 채우기 시험과 사람 승인 뒤
cd ..\schema\doc-ontology
..\..\.venv\Scripts\python.exe tools\finalize.py regulation # 초안을 승인본으로 올리고 승인 기록을 씀
```

- 인덱싱을 LLM 추출 없이 다시 하려면 `--reuse {앞 결과 폴더}`를 붙임. 화면의 「LLM 추출 0개」를 먼저 확인함  
- 인덱싱 뒤 늘어난 맞추기 항목은 `draft_category_map.py draft --from {세대 폴더}\new_map_items.json`처럼 후보를 만들고,  
  사람이 정한 결정 파일로 `approve`를 돌리면 `maps/*.ttl`에 적힘

### 0.4 확인한 것(2026-11-22)

| 번호 | 확인한 것 | 결과 |
|------|-----------|------|
| A1 | Turtle에서 만든 `graph_schema.json` 3개가 승인본과 같은가 | 같음(칸의 값과 순서까지) |
| A2 | Turtle 내용이 승인된 JSON 기록과 같은가 | 같음. 채우는 방법 13행과 건너가는 경로 6개까지 옮기고 대조한 뒤 JSON 기록을 지움 |
| A3 | SHACL 검사 결과가 Cypher 검사와 같은가 | 같음(K06 14건, 나머지 0건) |
| A4 | 인덱싱 결과가 기준 세대(`gen-lab-doconto-f1`)와 같은가 | 12개 항목 중 11개 같음. 다른 1개는 주제 「해외」(의도한 차이) |
| A5 | 검색기가 기준과 같게 동작하는가 | 경로 점검 같음. Q01과 Q07 답변 완료, Q25는 기준과 같이 「확인할 수 없음」 |
| B1 | 설계 도구를 Turtle로 바꾼 뒤 채우기 시험 채점이 앞과 같은가(LLM 호출 없이 다시 채점) | 질문별 지표, 경로, 키, 규칙 위반 수 모두 같음 |
| B2 | LLM이 프롬프트를 따라 Turtle 초안을 쓸 수 있는가(시험 폴더, 가상 요구) | 첫 기계 검사에서 통과(고친 횟수 0). Sonnet이 씀 |
| B3 | 초안 → 검사 → 올리기 → 확정이 끝까지 도는가(시험 폴더) | 통과. 손으로 고친 생성물과 올리지 않은 판 번호를 도구가 막음 |
| B4 | LLM 후보 → 사람 확정 → Turtle 초안 → 승인본 올리기를 실제 항목으로 돌렸는가(업종 맞추기 표) | 돌림. 새 혜택 185건 중 133건 확정, 업종에 이어진 혜택 22 → 138개 |

- 자세한 실행 기록은 `ttl/RUN_LOG.md`, 검색기의 기준 기록은 `retriever/RUN_LOG-doconto.md`

### 0.5 아직 하지 않은 것

- Class, 관계, 셰이프를 바꾸는 실제 설계 한 바퀴는 돌리지 않음(B2와 B3은 시험 폴더에서 지어낸 요구로 한 것). 실제로 돌린 것은 맞추기 표(B4)임  
- 업종 맞추기 표의 확정 전 52건과 주제 맞추기 표의 확정 전 48건, 새 주제 이름 172개는 사람 확정을 기다림  
- 새 스키마로 LLM 추출을 다시 돌리는 채우기 시험(`fill_test.py extract`)은 Turtle 방식에서 돌려 보지 않음(채점만 다시 함)  
- 프롬프트의 1 ~ 4단계와 7단계(입력 받기, 역량 질문, 표본, 후보 뽑기, 기대 답)는 JSON 방식과 같아 다시 돌리지 않음  
- 건너가는 경로는 Turtle에 글로 적었고, 검색기가 따라가는 실제 질의는 아직 코드(`retriever/search_graph.py`)에 있음  
- 교육생 뼈대 `indexer/my_graph.template.py`(`--mine`)는 옛 추출 단위 규칙을 씀  
- 아래 1절부터는 원래 `graphrag` 폴더의 안내를 이 폴더 경로로 바꾼 것임. `schema/doc`은 `schema/doc-ontology`로 읽음

## 1. 폴더 구성

```text
hands-on/solutions/ontology/
├─ README.md            이 문서(가상환경 설정과 실행 순서)
├─ requirements.txt     GraphRAG 실습 공통 패키지 목록(서브 폴더에는 두지 않음)
├─ .venv/               공용 가상환경(이 폴더에서 만듦. Git에 올리지 않음)
├─ ttl/                 온톨로지 원본(Turtle)과 도구. card.ttl, shapes/, maps/, tools/. 0절 참조
├─ schema/              그래프 스키마 설계 결과와 도구(doc-ontology: 문서 그래프와 공통 개념 층, rdb: 정형 데이터 그래프). indexer가 schema/doc-ontology를 읽음
├─ indexer/             그래프 인덱싱 실습(교재 31 ~ 67쪽). 사용법은 indexer/README.md
└─ retriever/           그래프 검색 실습(교재 70 ~ 99쪽). 사용법은 retriever/README.md
```

| 폴더 | main | 교육생 작업 파일 | 만드는 것 |
|---|---|---|---|
| `indexer/` | `index_graph.py`, 확인 도구 `check_graph.py` | `my_graph.py`(`--mine`이 템플릿에서 만듦) | Neo4j 그래프 세대, OpenSearch 인덱스, 활성 세대 파일 |
| `retriever/` | `search_graph.py` | `my_search.py`(`--mine`이 템플릿에서 만듦) | 단계별 검색 화면, 실행 기록 |
| `schema/doc-ontology`, `schema/rdb` | `tools/*.py`, `common/tools/*.py`(강사용 스키마 설계 도구) | - | `graph_schema.json`, `unit_text_rules.json`, `approval.json`, `common/concepts.json` 등 |

## 2. 준비물

| 항목 | 값 |
|---|---|
| Python | 3.13 |
| 백킹 서비스 | Neo4j(APOC, GDS), OpenSearch. 저장소 루트 `backing-services/`의 compose로 띄움(2.1) |
| API 키 | 저장소 루트 `secrets/.env`: `GROQ_API_KEY`, `COHERE_API_KEY`(indexer, retriever), `JEV_API_KEY`(retriever) |
| 선행 실습 | RAG 인덱싱 결과 `hands-on/solutions/rag/indexing/data/chroma`(없으면 RAG 실습을 먼저 돌리거나 강사 배포본 복사) |

### 2.1 백킹 서비스 실행, 중지, 삭제

Neo4j(그래프 DB)와 OpenSearch(검색엔진)는 indexer와 retriever가 쓰고, PostgreSQL(rdb)은 `schema/rdb` 도구만 씀.  
명령은 모두 **저장소 루트의 `backing-services` 폴더**에서 실행함(가상환경과 상관없음). Docker Desktop이 켜져 있어야 함.

처음 한 번: Neo4j 비밀번호 파일을 만듦(`backing-services/neo4j/.env.example`을 복사해 `.env`로 저장하고 `NEO4J_PASSWORD`를 적음.  
비밀번호는 8자리 이상이어야 합니다.      
자세한 것은 [neo4j/README.md](../../../backing-services/neo4j/README.md))

```bash
cd backing-services
```

| 하는 일 | Neo4j | OpenSearch | 데이터 |
|---|---|---|---|
| 실행(만들고 켬) | `docker compose -f neo4j/compose.yml up -d` | `docker compose -f opensearch/compose.yml up -d` | 남음 |
| 상태 확인 | `docker compose -f neo4j/compose.yml ps` | `docker compose -f opensearch/compose.yml ps` | - |
| 중지(잠시 멈춤) | `docker compose -f neo4j/compose.yml stop` | `docker compose -f opensearch/compose.yml stop` | 남음 |
| 멈춘 것 다시 켬 | `docker compose -f neo4j/compose.yml start` | `docker compose -f opensearch/compose.yml start` | 남음 |
| 삭제(컨테이너만) | `docker compose -f neo4j/compose.yml down` | `docker compose -f opensearch/compose.yml down` | 남음(볼륨 유지) |
| 삭제(데이터까지) | `docker compose -f neo4j/compose.yml down -v` | `docker compose -f opensearch/compose.yml down -v` | **지워짐** |
| 로그 보기 | `docker compose -f neo4j/compose.yml logs --tail 50` | `docker compose -f opensearch/compose.yml logs --tail 50` | - |

- 실행 뒤 상태가 `healthy`가 되면(30초쯤) 준비 끝. Neo4j는 처음 실행 때 APOC, GDS 플러그인을 받느라 1 ~ 2분 걸릴 수 있음
- 둘을 한꺼번에: `docker compose -f neo4j/compose.yml up -d; docker compose -f opensearch/compose.yml up -d`(중지, 삭제도 같은 꼴)
- `restart: unless-stopped`라서 Docker Desktop을 다시 켜면 실행 중이던 컨테이너도 따라 켜짐. `stop`으로 멈춘 것은 켜지지 않음
- Neo4j는 `stop` 뒤 상태가 `Exited (137)`로 보일 수 있음(종료 대기 시간 10초를 넘겨 강제 종료된 표시). 데이터는 남음(2026-10-26 실측)
- **`down -v`는 볼륨(Neo4j `hybrid-ai-neo4j-data` 등, OpenSearch `hybrid-ai-opensearch-data`)까지 지움.**  
  그래프 세대와 검색 인덱스가 모두 사라지므로 indexer를 다시 돌려야 하고, `indexer/data/active_generation.json`도 맞지 않게 됨.  
  Neo4j 비밀번호를 바꿀 때처럼 처음부터 다시 만들 때만 씀
- PostgreSQL(rdb, `schema/rdb` 도구용)도 같은 꼴:  
  `docker compose -f rdb/compose.yml up -d`, `stop`, `start`, `down`, `down -v`.  
  rdb는 `down -v` 뒤 다시 `up -d` 하면 `rdb/init`의 SQL로 데이터를 다시 채움([rdb/README.md](../../../backing-services/rdb/README.md))

## 3. 가상환경 설정과 패키지 설치

가상환경은 이 폴더의 `.venv` **하나**를 `indexer/`, `retriever/`, `schema/` 도구가 함께 씀.  
가상환경을 **활성화(activate)**하면 프롬프트 앞에 `(.venv)`가 붙고, 그 터미널의 `python`, `pip`이 가상환경의 것으로 바뀜.  
활성화는 터미널 창마다 한 번 함. 활성화한 뒤 서브 폴더로 `cd` 해도 활성화는 그대로 유지됨.

### 3.1 처음 한 번: 만들기, 활성화, 설치

Windows PowerShell

```powershell
cd hands-on\solutions\graphrag
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Windows Git Bash

```bash
cd hands-on/solutions/ontology
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

macOS, Linux (zsh, bash)

```bash
cd hands-on/solutions/ontology
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

설치 확인(활성화한 터미널에서)

```bash
python -c "import langchain_groq, langchain_cohere, langgraph, neo4j_graphrag, opensearchpy, chromadb, kiwipiepy, typesafe_sdk; print('ok')"
```

예전처럼 `indexer/requirements.txt`, `retriever/requirements.txt`로 설치한 `.venv`가 있으면 활성화한 뒤  
`pip install -r requirements.txt`를 한 번 더 실행해 빠진 패키지를 채움.

### 3.2 다음부터: 활성화만

| 터미널 | 활성화(`hands-on/solutions/ontology` 폴더에서) | 끄기 |
|---|---|---|
| Windows PowerShell | `.venv\Scripts\Activate.ps1` | `deactivate` |
| Windows Git Bash | `source .venv/Scripts/activate` | `deactivate` |
| macOS, Linux | `source .venv/bin/activate` | `deactivate` |

### 3.3 PowerShell에서 활성화가 막힐 때

`.venv\Scripts\Activate.ps1`을 실행했을 때 아래처럼 나오면 PowerShell 실행 정책이 스크립트 실행을 막은 것임.

```text
.venv\Scripts\Activate.ps1 : 이 시스템에서 스크립트를 실행할 수 없으므로 ... 파일을 로드할 수 없습니다.
(영문: ... cannot be loaded because running scripts is disabled on this system.)
```

방법 1(권장): 지금 연 PowerShell 창에서만 허용함. 창을 닫으면 원래대로 돌아가 다른 설정에 영향이 없음

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

방법 2: 내 계정에서 계속 허용함(한 번만 하면 이후 창에서도 됨. 인터넷에서 받은 서명 없는 스크립트는 여전히 막힘)

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

- 지금 설정 보기: `Get-ExecutionPolicy -List`. 방법 2를 되돌리려면 `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy Undefined`
- 회사 PC처럼 관리자가 정책을 막아 두어 위 명령도 안 되면, 활성화 없이 가상환경의 파이썬을 직접 지정해 실행함  
  (예: `.venv\Scripts\python.exe -m pip install -r requirements.txt`,  
  `..\.venv\Scripts\python.exe search_graph.py --qid Q01`)
- 저장소를 통째로 clone해서 씀. 이 폴더만 복사하면 RAG 청크, `docs/`, `secrets/`, `backing-services/`를 찾지 못함

### 3.4 VS Code에서 import 경고 없애기(선택)

`retriever/search_graph.py`의 `import kr_tokenizer` 줄에 「Import "kr_tokenizer" could not be resolved」 경고가 보일 수 있음.  
실행할 때는 코드가 `indexer` 폴더를 검색 경로에 넣어 정상 동작함. 편집기(Pylance)는 코드를 실행하지 않아 그 경로를 모르기 때문에 생기는 경고임.  
VS Code에 경로를 알려 주면 경고가 사라지고, 함수 이름 자동 완성과 정의로 이동(F12)도 됨.

저장소 루트(`hybrid-ai`)를 VS Code로 열었다면 루트에 `.vscode/settings.json`을 만들고 아래처럼 적음(RAG 실습 경로도 함께 넣어 둠)

```json
{
  "python.analysis.extraPaths": [
    "hands-on/solutions/rag/indexing",
    "hands-on/solutions/ontology/indexer"
  ]
}
```

- `hands-on/solutions/ontology` 폴더만 열었다면 그 폴더에 `.vscode/settings.json`을 만들고  
  `"python.analysis.extraPaths": ["indexer"]`로 적음
- 이미 `settings.json`이 있으면 파일을 새로 만들지 말고 `"python.analysis.extraPaths"` 항목만 더함
- 파이썬 인터프리터도 가상환경으로 맞춤: `Ctrl+Shift+P` → `Python: Select Interpreter` → `hands-on/solutions/ontology/.venv`.  
  그래야 neo4j_graphrag, opensearchpy 같은 패키지 import 경고도 사라짐
- `.vscode/` 폴더는 Git에 올리지 않음(저장소 `.gitignore`에 있음). 각자 PC에서 만듦
- 확인(2026-10-26): 같은 엔진인 pyright로 검사하면 설정 전에는 `kr_tokenizer` 경고가 나고, `extraPaths`를 넣은 뒤에는 사라짐

## 4. 실행 순서

가상환경을 활성화한 터미널에서 실행함. 아래는 Git Bash, macOS, Linux 기준이며 PowerShell은 `cd` 경로의 `/`를 `\`로 씀.  
`{별명}`은 본인 별명(영문)으로 바꿈. 예) `hong-f1`

```bash
# 0) 가상환경 활성화(hands-on/solutions/ontology 폴더에서). macOS, Linux는 source .venv/bin/activate,
#    PowerShell은 .venv\Scripts\Activate.ps1
source .venv/Scripts/activate

# 1) 그래프 인덱싱(indexer 폴더에서)
cd indexer

# 1-1) 단계별로 멈춰 결과 보기 — 그 단계까지만 수행하고, 한 일과 실제 결과와 직접 확인할 명령을 보여 줌(게시하지 않음)
#      KG 구축은 k1, k3, k5, k6, k8, 검색엔진 인덱싱은 s1, s2, s3. 값만 바꿔 차례로 돌림
#      K4 이후(k5, k6, k8)는 화면의 「이어서 보기」 명령처럼 --reuse를 붙여 기존 KG 추출 결과를 다시 씀
python index_graph.py --run {별명}-u1 --until k3

# 1-2) 전체 인덱싱(청크 260개)으로 ① ~ ⑤ 끝까지. 게시까지 해서 활성 세대가 됨 — 강사 배포본을 재사용해 LLM 호출을 줄임(몇 분)
python index_graph.py --run {별명}-f1 --reuse data/teacher
python check_graph.py --qid Q01

# 2) 그래프 검색 — 질문 하나를 ① ~ ⑩ 단계별 출력으로 확인
cd ../retriever
python search_graph.py --qid Q01
```

인덱싱은 1-1, 1-2 중 필요한 것을 고름(1-2로 게시한 세대가 활성 세대가 되고, 검색은 활성 세대를 읽음).  

| 단계 | 언제 | 비고 |
|---|---|---|
| 1-1 단계별 확인 | 각 단계가 무엇을 하고 결과가 어떤지 보고 싶을 때 | 게시하지 않아 활성 세대는 그대로. 실행 이름은 1-2와 다르게 줌 |
| 1-2 전체 인덱싱 | 260청크 전체로 검색 결과를 볼 때 | 강사 배포본(`data/teacher`)이 없으면 `--reuse`를 빼고 돌림(LLM 약 300번, 10분 안팎) |

- 1-2는 2026-11-11 실측으로 186초가 걸렸고, 강사 배포본에 없는 부분만 LLM을 불렀음(추출 48번, 커뮤니티 요약 12번)  
- 같은 입력과 설정으로 다시 돌리면 「할 일 없음」으로 끝남. 그래도 새로 만들려면 `--full-reindex`와 **새 실행 이름**을 줌  
- `--until`로 단계를 보는 중에는 활성 세대가 바뀌지 않으므로 검색과 `check_graph.py`는 이전과 똑같이 동작함  

각 단계의 옵션과 출력 읽는 법은 [indexer/README.md](indexer/README.md)(전체 실행은 4절, 단계별 확인은 5.1절),  
[retriever/README.md](retriever/README.md)에 있음.  
`schema/` 도구는 강사용이며, 같은 가상환경을 활성화한 채 `schema/doc` 또는 `schema/rdb` 폴더에서 `python tools/{도구}.py`로 실행함  
(실행 예는 각 도구 파일 맨 위 설명에 있음).

## 5. 교육생 작업 파일과 pull

### 작업 파일과 pull 충돌

- Git에는 강사 뼈대 `my_*.template.py`만 올라가고, 교육생 파일 `my_*.py`는 Git이 무시함(저장소 루트 `.gitignore`)  
- 강사가 뼈대를 고쳐도 교육생 파일과 겹치지 않으므로 `git pull` 충돌이 나지 않음  
- main 파일(`index_graph.py`, `search_graph.py`)은 고치지 않음. 바꿔 끼우기는 `--mine` 옵션으로만 함  
- 강사가 뼈대를 고친 내용(새 함수, 빈칸 안내)은 `my_*.template.py`와 본인 `my_*.py`를 나란히 열어 비교해 옮김
