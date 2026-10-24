# OpenSearch 실습 컨테이너

GraphRAG 실습(`indexer/graphrag/v0` 등)에서 BM25와 벡터 검색을 맡는 검색 엔진을 docker compose로 띄움.  
그래프 DB는 `../neo4j`에서 따로 띄움.

## 구성

| 항목 | 값 |
|------|------|
| 컨테이너 이름 | `hybrid-ai-opensearch` (Compose 프로젝트 `hybrid-ai-opensearch`) |
| 이미지 | `opensearchproject/opensearch:2.19.1` |
| 포트 | 9200(REST API). 이 PC(127.0.0.1)에서만 접속됨 |
| 볼륨 | `hybrid-ai-opensearch-data` |
| 보안 | 보안 플러그인 꺼짐(실습 전용). 그래서 외부에 열지 않음 |

- 한국어 분석기 nori는 넣지 않음. v0는 Kiwi로 미리 나눈 낱말을 공백 분석기(`whitespace`)로 넣기 때문임
- 벡터 검색(kNN)은 기본 이미지에 들어 있어 따로 설치하지 않음

## 실행

`backing-services` 폴더에서 실행함. 비밀번호가 없어 `.env`는 없어도 됨.

```bash
docker compose -f opensearch/compose.yml up -d
```

상태가 `healthy`가 되면 쓸 수 있음(20초쯤).

```bash
docker compose -f opensearch/compose.yml ps
curl http://localhost:9200
```

`curl` 결과에 `"number" : "2.19.1"`이 보이면 정상임.

## 설정 바꾸기

포트나 메모리를 바꿀 때만 `.env.example`을 `.env`로 복사해 고침.

```bash
cp opensearch/.env.example opensearch/.env
```

| 값 | 기본 | 뜻 |
|------|------|------|
| `OPENSEARCH_PORT` | 9200 | PC에서 접속할 포트 |
| `OPENSEARCH_HEAP` | 1g | 자바 힙 크기 |

## 중지와 다시 시작

| 하고 싶은 일 | 명령 | 데이터 |
|------|------|------|
| 잠시 멈춤 | `docker compose -f opensearch/compose.yml stop` | 남음 |
| 멈춘 것 다시 켬 | `docker compose -f opensearch/compose.yml start` | 남음 |
| 컨테이너만 지움 | `docker compose -f opensearch/compose.yml down` | 남음(볼륨 유지) |
| 다시 만들어 켬 | `docker compose -f opensearch/compose.yml up -d` | 남음 |

`restart: unless-stopped`라서 Docker Desktop을 다시 켜면 컨테이너도 따라 켜짐. `stop`으로 멈춘 것은 켜지지 않음.

## 삭제

색인까지 모두 지우려면 볼륨도 함께 지움. **되돌릴 수 없음.**

```bash
docker compose -f opensearch/compose.yml down -v
```

다음 `up -d` 때 빈 검색 엔진으로 새로 시작함. v0 색인은 전체 재색인으로 다시 만들어야 함.

## 문제 해결

| 증상 | 확인할 것 |
|------|------|
| `port is already allocated` | 9200을 다른 프로그램이 씀. `.env`에서 `OPENSEARCH_PORT`를 바꿈 |
| 상태가 계속 `starting` | `docker logs hybrid-ai-opensearch`로 오류 확인. 메모리가 모자라면 `OPENSEARCH_HEAP`을 줄임 |
| `max virtual memory areas` 오류 | WSL에서 `sysctl -w vm.max_map_count=262144`가 필요할 수 있음 |

## 확인 기록 (2026-10-23)

- `up -d` 뒤 `healthy`, `curl http://localhost:9200`에서 판 2.19.1 확인
