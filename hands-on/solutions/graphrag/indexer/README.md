# GraphRAG 인덱싱 실습

이 예제는 RAG 실습에서 만든 청크로 Neo4j 지식 그래프와 OpenSearch 인덱스를 함께 만듭니다.  
처음 실행한다면 아래 순서대로 환경을 준비한 뒤 표본 10청크로 동작을 확인합니다.

## 1. 실행 전 확인

다음 항목이 준비되어 있어야 합니다.

- Python 3.13과 Docker Desktop
- 저장소 루트 `secrets/.env`의 `GROQ_API_KEY`, `COHERE_API_KEY`
- `backing-services/neo4j/.env`의 `NEO4J_PASSWORD`
- RAG 실습 결과 `hands-on/solutions/rag/indexing/data/chroma`

Neo4j 비밀번호 설정과 백킹 서비스의 자세한 사용법은  
[GraphRAG 공통 안내](../README.md)와  
[Neo4j 안내](../../../../backing-services/neo4j/README.md)를 참고합니다.

## 2. 가상환경 설정

가상환경과 패키지는 `indexer`가 아니라 상위 `graphrag` 폴더에 설치합니다.  
이곳의 `.venv` 하나를 GraphRAG 실습 전체가 함께 사용합니다.

### 2.1 처음 한 번

Windows PowerShell에서는 저장소 루트에서 다음 명령을 실행합니다.

```powershell
cd hands-on\solutions\graphrag
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Windows Git Bash에서는 다음 명령을 실행합니다.

```bash
cd hands-on/solutions/graphrag
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
```

macOS와 Linux에서는 다음 명령을 실행합니다.

```bash
cd hands-on/solutions/graphrag
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

프롬프트 앞에 `(.venv)`가 보이면 활성화된 상태입니다.

PowerShell에서 스크립트 실행이 차단되면 현재 터미널에서만 실행을 허용한 뒤 다시 활성화합니다.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

### 2.2 다음 실행부터

패키지를 다시 설치할 필요는 없습니다. 터미널을 열 때마다 상위 `graphrag` 폴더에서 가상환경만 활성화합니다.

| 터미널 | 활성화 명령 |
|---|---|
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows Git Bash | `source .venv/Scripts/activate` |
| macOS, Linux | `source .venv/bin/activate` |

## 3. 백킹 서비스 실행

새 터미널을 열고 저장소 루트에서 Neo4j와 OpenSearch를 실행합니다.

```powershell
cd backing-services
docker compose -f neo4j/compose.yml up -d
docker compose -f opensearch/compose.yml up -d
docker compose -f neo4j/compose.yml ps
docker compose -f opensearch/compose.yml ps
```

두 서비스의 상태가 `healthy`가 되면 준비가 끝납니다. 처음 실행할 때는 플러그인 설치로 시간이 더 걸릴 수 있습니다.

## 4. 표본으로 빠르게 실행

가상환경을 활성화한 터미널에서 `indexer` 폴더로 이동합니다.  
`{별명}`은 본인의 영문 별명으로 바꿉니다. 예를 들어 `hong-s1`처럼 사용합니다.

```bash
cd indexer
python index_graph.py --run {별명}-s1 --sample
python check_graph.py --qid Q09
```

첫 명령은 표본 10청크를 인덱싱하고 검증을 통과한 세대를 게시합니다.  
두 번째 명령은 질문 하나로 검색엔진, 청크, 그래프 엔티티, 커뮤니티 보고서가 연결되는지 보여 줍니다.

`--run` 값은 세대를 구분하는 실행 이름입니다. 활성 세대와 같은 이름은 사용할 수 없으므로 새 이름을 지정합니다.

## 5. 필요한 방식으로 실행

### 5.1 전체 청크 인덱싱

`--sample`을 빼면 전체 청크를 처리합니다.

```bash
python index_graph.py --run {별명}-f1
```

강사 배포 결과가 있다면 호환되는 LLM 결과를 재사용해 호출을 줄일 수 있습니다.

```bash
python index_graph.py --run {별명}-f1 --reuse data/teacher
```

`--reuse`는 입력 본문, 스키마, 머리줄이 일치하는 결과만 재사용합니다.  
빠진 결과나 일치하지 않는 결과는 새로 만들기 때문에 LLM 호출이 전혀 없음을 보장하지 않습니다.

전체 세대는 다음 질문으로 확인합니다.

```bash
python check_graph.py --qid Q01 --rerank
```

### 5.2 단계별 결과 확인

`--until`을 사용하면 지정한 단계까지만 실행하고 결과와 확인 명령을 보여 줍니다.

```bash
python index_graph.py --run {별명}-u1 --sample --until k3
```

| 트랙 | 지정 가능한 단계 |
|---|---|
| 지식 그래프 | `k1`, `k3`, `k5`, `k6`, `k8` |
| 검색엔진 | `s1`, `s2`, `s3` |

`--until` 실행은 검증과 게시를 하지 않습니다. 현재 활성 세대와 검색 결과는 바뀌지 않습니다.  
단계를 바꾸어 다시 실행할 때 LLM 호출을 줄이려면 `--reuse`에 앞선 결과 폴더를 지정합니다.  
K2 또는 K3 코드를 수정해 비교할 때는 `--reuse`를 빼야 수정 결과가 반영됩니다.

### 5.3 내 코드로 실행

처음 `--mine`을 붙이면 `my_graph.template.py`를 복사해 `my_graph.py`를 만듭니다.

```bash
python index_graph.py --run {별명}-m1 --sample --mine
```

`my_graph.py` 맨 아래 `USE_TEACHER_CODE`에서 구현할 함수 이름을 뺍니다.  
목록에 남아 있는 함수는 계속 강사 코드가 대신 실행합니다. 한 번에 한 함수씩 바꾸면 결과를 비교하기 쉽습니다.

### 5.4 옵션 확인

전체 옵션과 기본값은 실행 파일의 도움말이 가장 정확합니다.

```bash
python index_graph.py --help
python check_graph.py --help
```

## 6. 처리 흐름과 파일

인덱서는 청크를 고정한 뒤 지식 그래프와 검색 인덱스를 만듭니다.  
마지막에 두 결과를 검증하고, 통과한 세대만 `active_generation.json`에 게시합니다.

| 파일 | 역할 |
|---|---|
| `index_graph.py` | 환경 검사와 전체 인덱싱 순서를 실행함 |
| `core_graph.py` | 교육생이 학습할 핵심 인덱싱 함수를 제공함 |
| `my_graph.template.py` | 교육생 코드인 `my_graph.py`의 뼈대를 제공함 |
| `check_graph.py` | 활성 세대에 질문하고 검색 연결 결과를 보여 줌 |
| `stage_view.py` | `--until` 실행의 단계별 결과와 확인 명령을 보여 줌 |
| `data/generations/` | 세대별 중간 결과와 보고서를 저장함 |
| `data/active_generation.json` | 현재 검색에서 사용할 활성 세대를 가리킴 |

## 7. 자주 막히는 상황

| 증상 | 확인할 내용 |
|---|---|
| API 키가 필요하다는 메시지 | 저장소 루트 `secrets/.env`에 키 두 개가 있는지 확인함 |
| Neo4j 또는 OpenSearch 연결 실패 | `backing-services`에서 `docker compose ... ps`로 `healthy`인지 확인함 |
| GDS가 없어 K8을 건너뜀 | Neo4j 안내의 `gds.version` 문제 해결을 확인함. K8 없이도 나머지 실습은 가능함 |
| RAG 청크를 찾지 못함 | RAG 인덱싱을 먼저 실행하거나 강사 배포 결과를 복사함 |
| 중단 뒤 다시 실행함 | 같은 `--run`으로 실행하면 해당 세대의 흔적을 정리하고 처음부터 다시 만듦 |
| 같은 입력이라 할 일이 없다고 나옴 | 새 `--run` 이름과 `--full-reindex`를 함께 사용함 |
| 내 코드의 결과가 다름 | `--mine`을 빼서 강사 결과와 비교하고 함수 하나씩 교체함 |

검증을 통과하지 못한 세대는 게시되지 않습니다.  
자세한 환경 설정과 서비스 중지 방법은 [GraphRAG 공통 안내](../README.md)를 참고합니다.
