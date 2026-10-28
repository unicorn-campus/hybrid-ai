# GraphRAG 실습 예제 — 스키마, 인덱싱, 검색

하이브리드 AI 교육 W5 ~ W7 「관계로 찾기(GraphRAG)」 실습용 예제임(교재 『신한카드 하이브리드AI_W05 ~ W07』).  
RAG 실습(W3)이 만든 청크를 입력으로 지식 그래프(Neo4j)와 검색엔진 인덱스(OpenSearch)를 만들고, 그 위에서 에이전트 검색을 돌림.  
가상환경과 패키지 설치는 **이 폴더(`hands-on/solutions/graphrag`)에서만** 하고, 서브 폴더는 같은 가상환경을 활성화한 채 실행함.

## 1. 폴더 구성

```text
hands-on/solutions/graphrag/
├─ README.md            이 문서(가상환경 설정과 실행 순서)
├─ requirements.txt     GraphRAG 실습 공통 패키지 목록(서브 폴더에는 두지 않음)
├─ .venv/               공용 가상환경(이 폴더에서 만듦. Git에 올리지 않음)
├─ schema/              그래프 스키마 설계 결과와 도구(doc: 문서 그래프, rdb: 정형 데이터 그래프). indexer가 schema/doc의 결과를 읽음
├─ indexer/             그래프 인덱싱 실습(교재 30 ~ 62쪽). 사용법은 indexer/README.md
└─ retriever/           그래프 검색 실습(교재 64 ~ 79쪽). 사용법은 retriever/README.md
```

| 폴더 | main | 교육생 작업 파일 | 만드는 것 |
|---|---|---|---|
| `indexer/` | `index_graph.py`, 확인 도구 `check_graph.py` | `my_graph.py` | Neo4j 그래프 세대, OpenSearch 인덱스, 활성 세대 파일 |
| `retriever/` | `search_graph.py` | `my_search.py` | 단계별 검색 화면, 실행 기록 |
| `schema/doc`, `schema/rdb` | `tools/*.py`(강사용 스키마 설계 도구) | - | `graph_schema.json`, `approval.json` 등 |

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
cd hands-on/solutions/graphrag
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

macOS, Linux (zsh, bash)

```bash
cd hands-on/solutions/graphrag
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

| 터미널 | 활성화(`hands-on/solutions/graphrag` 폴더에서) | 끄기 |
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
    "hands-on/solutions/graphrag/indexer"
  ]
}
```

- `hands-on/solutions/graphrag` 폴더만 열었다면 그 폴더에 `.vscode/settings.json`을 만들고  
  `"python.analysis.extraPaths": ["indexer"]`로 적음
- 이미 `settings.json`이 있으면 파일을 새로 만들지 말고 `"python.analysis.extraPaths"` 항목만 더함
- 파이썬 인터프리터도 가상환경으로 맞춤: `Ctrl+Shift+P` → `Python: Select Interpreter` → `hands-on/solutions/graphrag/.venv`.  
  그래야 neo4j_graphrag, opensearchpy 같은 패키지 import 경고도 사라짐
- `.vscode/` 폴더는 Git에 올리지 않음(저장소 `.gitignore`에 있음). 각자 PC에서 만듦
- 확인(2026-10-26): 같은 엔진인 pyright로 검사하면 설정 전에는 `kr_tokenizer` 경고가 나고, `extraPaths`를 넣은 뒤에는 사라짐

## 4. 실행 순서

가상환경을 활성화한 터미널에서 실행함. 아래는 Git Bash, macOS, Linux 기준이며 PowerShell은 `cd` 경로의 `/`를 `\`로 씀.  
`{별명}`은 본인 별명(영문)으로 바꿈. 예) `hong-s1`

```bash
# 0) 가상환경 활성화(hands-on/solutions/graphrag 폴더에서). macOS, Linux는 source .venv/bin/activate,
#    PowerShell은 .venv\Scripts\Activate.ps1
source .venv/Scripts/activate

# 1) 그래프 인덱싱 — 표본 10청크로 ① ~ ⑤ 끝까지(약 1분), 결과를 질문 하나로 확인
cd indexer
python index_graph.py --run {별명}-s1 --sample
python check_graph.py --qid Q09

# 2) 그래프 검색 — 질문 하나를 ① ~ ⑩ 단계별 출력으로 확인
cd ../retriever
python search_graph.py --qid Q01
```

각 단계의 옵션과 출력 읽는 법은 [indexer/README.md](indexer/README.md), [retriever/README.md](retriever/README.md)에 있음.  
`schema/` 도구는 강사용이며, 같은 가상환경을 활성화한 채 `schema/doc` 또는 `schema/rdb` 폴더에서 `python tools/{도구}.py`로 실행함  
(실행 예는 각 도구 파일 맨 위 설명에 있음).
