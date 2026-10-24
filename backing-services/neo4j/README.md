# Neo4j 실습 컨테이너 (APOC, GDS 포함)

GraphRAG 실습(`indexer/graphrag/v0` 등)에서 쓰는 그래프 DB를 docker compose로 띄움.  
검색 엔진은 `../opensearch`에서 따로 띄움.

## 구성

| 항목 | 값 |
|------|------|
| 컨테이너 이름 | `hybrid-ai-neo4j` (Compose 프로젝트 `hybrid-ai-neo4j`) |
| 이미지 | `neo4j:2026.09.0-community` |
| 플러그인 | APOC(core) 2026.09.0, Graph Data Science(GDS) Community Edition 2026.09.0 |
| 포트 | 7474(Neo4j Browser), 7687(bolt 접속) |
| 볼륨 | `hybrid-ai-neo4j-data`(데이터), `hybrid-ai-neo4j-logs`(로그), `hybrid-ai-neo4j-plugins`(플러그인) |
| 비밀번호 | 이 폴더의 `.env`에서 읽음. compose 파일과 git에는 넣지 않음 |

- GDS Community Edition은 무료이고 모든 알고리즘(Leiden 포함)을 씀. 병렬 처리는 4코어까지임
- APOC Extended는 넣지 않음. core APOC와 함께 두면 core 프로시저가 깨지는 일이 있었음

## 처음 한 번: 비밀번호 정하기

`backing-services/neo4j` 폴더의 `.env.example`을 `.env`로 복사하고 `NEO4J_PASSWORD`를 채움(8자 이상).  
아래 명령은 `backing-services` 폴더에서 실행함.

```bash
cp neo4j/.env.example neo4j/.env
```

`.env`는 git에 올라가지 않음(저장소 `.gitignore`에 `.env`가 있음).  
`NEO4J_PASSWORD`가 비어 있으면 기동하지 않고 안내 문구를 냄.

## 실행

`backing-services` 폴더에서 실행함.

```bash
docker compose -f neo4j/compose.yml up -d
```

- 첫 기동은 플러그인 설치 때문에 30초쯤 걸림
- 상태가 `healthy`가 되면 쓸 수 있음

```bash
docker compose -f neo4j/compose.yml ps
```

## 접속

| 방법 | 주소 |
|------|------|
| Neo4j Browser | http://localhost:7474 (사용자 `neo4j`, 비밀번호는 `.env`) |
| 드라이버(Python 등) | `bolt://localhost:7687` |
| 컨테이너 안 cypher-shell | 아래 명령 |

```bash
docker exec -it hybrid-ai-neo4j sh -c 'cypher-shell -u neo4j -p "${NEO4J_AUTH#neo4j/}"'
```

플러그인이 붙었는지는 아래 질의로 확인함. 두 값 모두 `2026.09.0`이 나오면 정상임.

```bash
docker exec hybrid-ai-neo4j sh -c 'cypher-shell -u neo4j -p "${NEO4J_AUTH#neo4j/}" "RETURN apoc.version() AS apoc, gds.version() AS gds;"'
```

GraphRAG v0는 비밀번호를 환경변수 `NEO4J_PASSWORD`로 받음. 접속 주소가 다르면 `NEO4J_URI`로 넘김.

## 중지와 다시 시작

| 하고 싶은 일 | 명령 | 데이터 |
|------|------|------|
| 잠시 멈춤 | `docker compose -f neo4j/compose.yml stop` | 남음 |
| 멈춘 것 다시 켬 | `docker compose -f neo4j/compose.yml start` | 남음 |
| 컨테이너만 지움 | `docker compose -f neo4j/compose.yml down` | 남음(볼륨 유지) |
| 다시 만들어 켬 | `docker compose -f neo4j/compose.yml up -d` | 남음 |

`restart: unless-stopped`라서 Docker Desktop을 다시 켜면 컨테이너도 따라 켜짐. `stop`으로 멈춘 것은 켜지지 않음.

## 삭제

데이터까지 모두 지우려면 볼륨도 함께 지움. **되돌릴 수 없음.**

```bash
docker compose -f neo4j/compose.yml down -v
```

- 데이터, 로그, 플러그인 볼륨이 모두 지워짐
- 다음 `up -d` 때 빈 DB로 새로 시작하고 플러그인을 다시 설치함
- 비밀번호를 바꾸려면 `down -v`로 지운 뒤 `.env`를 고치고 다시 띄움. Neo4j는 처음 만들 때의 비밀번호를 데이터에 저장하기 때문임

## 문제 해결

| 증상 | 확인할 것 |
|------|------|
| `port is already allocated` | 7474나 7687을 다른 프로그램이 씀. `.env`에서 `NEO4J_HTTP_PORT`, `NEO4J_BOLT_PORT`를 바꿈 |
| 상태가 계속 `starting` | `docker logs hybrid-ai-neo4j`로 오류 확인. 메모리가 모자라면 `.env`의 `NEO4J_HEAP`을 줄임 |
| 로그인 실패 | 볼륨을 만든 뒤 `.env` 비밀번호를 바꾸면 맞지 않음. 처음 비밀번호를 쓰거나 `down -v` 후 다시 띄움 |
| `gds.version`을 찾지 못함 | `docker logs hybrid-ai-neo4j`에서 `Installing Plugin 'graph-data-science'` 줄을 확인. 없으면 `down` 후 `up -d` |

## 확인 기록 (2026-10-23)

- `up -d` 뒤 `healthy`, `apoc.version()`와 `gds.version()` 모두 `2026.09.0`
- GDS Leiden 동작 확인: 삼각형 두 개를 이은 작은 그래프를 `gds.leiden.stream`(randomSeed 42)으로 돌려 두 묶음으로 나뉨
- `down` 후 `up -d`에서 시험 노드가 남아 있음을 확인(볼륨 유지)
