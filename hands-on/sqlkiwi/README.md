# sqlkiwi

SQLite, PostgreSQL, MySQL에 연결해 SQL을 실행하는 데스크톱 SQL 클라이언트.  
DBeaver 25.0.5를 REA와 역컴파일로 분석한 동작 방식을 참고해 Electron + React로 새로 만듦(코드 복사 아님).

## 1. 기능

| 영역 | 내용 |
|------|------|
| 연결 관리 | SQLite(파일 열기, 새로 만들기), PostgreSQL, MySQL 연결 만들기, 고치기, 지우기, 연결 시험 |
| 비밀번호 | 저장을 고르면 OS 보안 저장소(Electron `safeStorage`, Windows는 DPAPI)로 암호화. 저장하지 않으면 연결할 때 물음 |
| 읽기 전용 연결 | DB 쪽 읽기 전용 설정과, 앱의 쓰기 문장 차단을 함께 적용 |
| 탐색 트리 | 스키마(MySQL은 DB) > 테이블과 뷰 > 컬럼, 인덱스, 외래 키. 펼칠 때 한 층씩 읽음. 테이블을 두 번 누르면 데이터 보기 |
| SQL 편집기 | DB별 구문 강조, 키워드와 테이블과 컬럼 자동완성(Ctrl+Space), 편집기 탭 여러 개 |
| 실행 | Ctrl+Enter 커서 문장 실행, Alt+X 스크립트 실행(문장별 통계), 실행 취소, WHERE 없는 DELETE와 UPDATE 확인 |
| 결과 그리드 | 200행씩 가져오고 스크롤 끝에서 자동으로 더 가져옴, 모두 가져오기, 정렬, NULL 표시, 셀 복사(탭 구분) |

### 단축키

| 키 | 동작 |
|----|------|
| Ctrl+Enter | 커서가 있는 문장 실행. 선택 영역이 있으면 선택한 글 전체 실행 |
| Alt+X | 스크립트 실행(선택 영역 또는 전체를 문장으로 나눠 차례로 실행, 오류가 나면 멈춤) |
| Ctrl+Space | 자동완성 |
| Ctrl+C / Ctrl+Shift+C | 결과 셀 복사 / 머리글 포함 복사 |
| Ctrl+A | 결과 전체 선택(받은 행까지) |

문장은 `;` 또는 빈 줄로 나뉨(DBeaver 기본값과 같음).  
따옴표, 주석, 괄호, PostgreSQL `$$` 본문, SQLite 트리거의 `BEGIN ... END` 안의 `;`는 문장 경계로 보지 않음.  
MySQL은 `DELIMITER //` 명령으로 구분자를 바꿀 수 있음.

## 2. 실행 방법

준비물: Node.js 22.12 이상과 npm. Windows에서는 Visual Studio Build Tools(C++)가 있으면 better-sqlite3 빌드가 확실함.

```bash
cd hands-on/sqlkiwi
npm install
npm run dev
```

- `npm install`이 끝나면 better-sqlite3를 Electron용으로 다시 빌드함(`postinstall`)
- `npm run build` 후 `npm start`로 빌드 결과를 실행 가능

## 3. 시험

| 명령 | 내용 | 필요한 것 |
|------|------|-----------|
| `npm test` | SQL 문장 분리기 단위 시험(32건) | 없음 |
| `npm run test:db` | DB 드라이버 시험(24건): 200행 나눠 받기, 중간 닫기, 취소, 읽기 전용, 탐색 트리 | 시험 DB |
| `npm run test:e2e` | 실제 앱을 띄워 화면 조작(19단계), 화면은 `test-results/`에 저장 | 시험 DB |
| `npm run typecheck` | 타입 검사 | 없음 |

시험 DB는 Docker로 띄움. 공용 실습 DB(5432)와 겹치지 않게 PostgreSQL은 55432, MySQL은 53306 포트를 씀.

```bash
docker compose -f test-db/compose.yml up -d --wait
```

```bash
docker compose -f test-db/compose.yml down -v
```

## 4. 구조

```
src/
  shared/          main과 화면이 함께 쓰는 코드
    types.ts         자료형, 한 번에 가져오는 행 수(FETCH_SIZE = 200)
    sql-split.ts     SQL 문장 분리기, 커서 문장 고르기, 위험 문장 판정
  main/            Electron 메인 프로세스
    index.ts         창 만들기, IPC 처리기
    session.ts       연결 세션, 실행 잠금, 결과 커서 보관
    store/connections.ts  연결 설정(connections.json)과 비밀번호(credentials.json) 저장
    db/
      driver.ts        DB 공통 틀(Driver, RowCursor)
      meta-tree.ts     탐색 트리 모양(DB와 상관없이 같음)
      postgres.ts      pg + pg-cursor
      mysql.ts         mysql2 스트리밍 질의
      sqlite.ts        SQLite 드라이버(실행은 별도 프로세스, 탐색은 읽기 전용 연결)
      sqlite-worker.ts SQLite 실행 프로세스(Electron utilityProcess)
      sqlite-engine.ts better-sqlite3 실행과 메타데이터
      cell.ts          DB 값을 화면 값으로 바꿈
  preload/         화면에 열어 주는 API(window.kiwi)
  renderer/src/    React 화면
    App.tsx          전체 배치, 탭, 실행, 정렬
    components/      Navigator, SqlEditor(CodeMirror 6), ResultGrid, ConnectionDialog
test/              단위, DB, 화면 시험
test-db/           시험용 PostgreSQL, MySQL(compose와 시드)
docs/              DBeaver 분석 기록
```

## 5. DBeaver에서 가져온 것과 다르게 고른 것

분석 근거는 [docs/dbeaver-analysis.md](docs/dbeaver-analysis.md)에 있음.

### 5.1 DBeaver 동작을 따른 것

| 항목 | DBeaver 근거 | sqlkiwi |
|------|-------------|---------|
| 한 번에 가져오는 행 수 | `resultset.maxrows` 기본 200 (`ModelPreferences`) | `FETCH_SIZE = 200` |
| 스크롤 끝 자동 로딩 | `resultset.autofetch.next.segment` 기본 켬 | 마지막 행이 보이면 다음 200행 |
| 행 수 표시 | 남은 행이 있으면 `200+` | 같음 |
| 문장 나누기 | `;`와 빈 줄(`BLANK_LINE_AND_SEPARATOR` 기본) | 같음 |
| 커서 문장 고르기 | `SQLScriptParser.extractQueryAtPosImpl` | `statementAt()` 순수 함수 |
| 정렬 | SMART: 다 받았으면 메모리, 남았으면 서버 ORDER BY | 같음(`SELECT * FROM (...) z_q ORDER BY n`) |
| NULL 표시 | 화면 `[NULL]`, 복사 빈 문자열 | 같음 |
| 위험 문장 확인 | WHERE 없는 DELETE, UPDATE, DROP TABLE | 같음 + TRUNCATE |
| 메타데이터 전용 연결 | 탐색용 실행 컨텍스트를 따로 씀 | 실행용과 탐색용 연결을 따로 엶 |
| 시스템 객체 숨김 | `pg_catalog`, `information_schema`, `pg_` 접두, MySQL `mysql` 등 | 같음 |
| 연결 기본값 | PostgreSQL 5432/postgres/postgres, MySQL 3306/root, 연결 제한 20초 | 같음 |
| 끊긴 연결 | 연결 끊김 오류는 1회 재연결 후 실행 | 다음 실행 때 같은 설정으로 다시 연결 |

### 5.2 다르게 고른 것

| 항목 | DBeaver | sqlkiwi | 이유 |
|------|---------|---------|------|
| 더 가져오기 방식 | offset을 바꿔 같은 질의를 다시 실행 | 서버 커서를 열어 둔 채 이어 읽음 | 정렬 없는 질의에서 행이 겹치거나 빠지는 문제를 피함 |
| 비밀번호 암호화 | 앱 코드에 고정된 AES 키로 파일 전체 암호화 | OS 보안 저장소(`safeStorage`) | 키가 앱에 들어 있으면 같은 코드로 누구나 풀 수 있음 |
| SQLite 메타데이터 | JDBC 메타데이터 호출(PRAGMA 직접 사용 없음) | `sqlite_master`와 `PRAGMA` 직접 질의 | Node 드라이버에는 JDBC 메타데이터 API가 없음 |
| SQLite 취소 | JDBC `Statement.cancel()` | 실행 프로세스를 끝냄 | better-sqlite3에 실행 중단 API가 없음 |
| 큰 정수, 10진수, 날짜 | Java 형으로 받아 형식 지정 | DB 문자열 그대로 | JS 숫자 정밀도(2^53) 한계 |
| 자동완성 | 자체 분석기(별칭, 조인 조건 추천) | `@codemirror/lang-sql`의 스키마 자동완성 | 첫 버전 범위. 조인 조건 추천은 없음 |

## 6. 알려진 한계

- SQLite 실행을 취소하면 실행 프로세스를 새로 띄우므로 임시 테이블 같은 세션 상태가 사라짐
- 스크립트 실행(Alt+X)의 결과는 문장마다 처음 200행만 보여 줌
- PostgreSQL은 연결한 DB 하나의 스키마만 보여 줌(DBeaver 기본값과 같음)
- 질의 매개변수(`:name`), 결과 편집, 결과 내보내기, 쿼리 기록, SSH 터널, SSL 설정은 아직 없음
- 결과 그리드는 열이 수백 개인 결과에서 가로 방향 가상 스크롤을 하지 않음
- 화면 시험은 Windows에서만 돌려 봄(`test/e2e.mjs`가 `electron.exe` 경로를 씀)
