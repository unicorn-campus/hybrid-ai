# DBeaver 25.0.5 분석 기록

- 분석 대상: 이 PC에 설치된 DBeaver Community 25.0.5(`%LOCALAPPDATA%\DBeaver`)  
- 분석 도구: REA 6.8.0(설치 폴더와 jar 구성 조사), Vineflower 1.12.0(jar 11개 역컴파일, Java 파일 2,417개)  
- 근거 경로는 역컴파일 출력 폴더 기준이며, 이 저장소에는 역컴파일 코드를 넣지 않음  
- 「관찰」은 코드에서 확인한 것, 「추론」은 코드 흐름에서 판단한 것, 「모름」은 확인하지 못한 것

## DBeaver 25.0.5 SQL 편집기 분석 (sqlkiwi 설계용)

- 근거 기준 `.temp/dbeaver-src/`. MS=`model.sql/.../model/sql`, M=`model/.../dbeaver`,  
  UI=`ui.editors.sql/.../ui/editors/sql`
- 역컴파일 한계: `MS/parser/SQLScriptParser.extractNextQueryImpl` 복원 실패, `parseQueryImpl`의 `prevNotEmptyTokenType` 갱신 누락 추정

### 1. 스크립트 분할 (`SQLScriptParser.parseQueryImpl`, `extractScriptQueries`)
- 토큰 스캐너로 읽다가 구분자 토큰에서 문장 확정. 구분자 기본 `;` + 방언 `getScriptDelimiters()` (`M/model/sql/SQLSyntaxManager.init`)
- 영문 구분자(GO)는 뒤 글자가 식별자 문자가 아닐 때만. `DELIMITER //`는 줄 맨 앞에서만 인식 (`SQLDelimiterSetRule.evaluate`)
- 빈 줄 구분 모드 `BLANK_LINE_AND_SEPARATOR`(기본), `ONLY_SEPARATOR`, `SMART`. 빈 줄은 줄바꿈 2개 이상
- 블록 스택 `ScriptBlockInfo`: 괄호 깊이, BEGIN/END, 달러 따옴표 토글. 블록 안 구분자는 무시
- 규칙 순서 (`SQLRuleManager.loadRules`): 방언 확장, 제어 명령, 매개변수, 식별자 따옴표, 문자열, 한 줄 주석, 여러 줄 주석, 공백, 숫자, 구분자, 단어
- 주석만 있는 조각은 방언이 허용할 때만 문장
- SMART: 첫 토큰이 문장 시작 키워드가 아니면 앞 문장에 붙임 (`ScriptElementContinuationDetector.elementStartsProperly`)

### 2. 커서 문장 실행 (`SQLScriptParser.extractQueryAtPosImpl`, `UI/SQLEditor.processQueries`)
- 선택 영역이 있으면 그 전체가 한 문장
- 줄 끝 주석 안 커서는 주석 앞 글자로 당김. 빈 줄 위 커서는 윗줄도 비면 없음, 아니면 윗 문장
- 커서 바로 앞이 구분자이고 뒤에 글자가 없으면 방금 끝낸 문장 선택
- 위로 올라가며 빈 줄을 시작으로, 커서 이후 첫 구분자를 끝으로 잡음
- 스크립트 실행(Alt+X)은 선택 범위 또는 문서 전체를 분할해 순서대로 실행

### 3. 자동완성
- 구 엔진 `MS/completion/SQLCompletionAnalyzer`, 신 엔진 `MS/semantics/completion/SQLQueryCompletionAnalyzer`(기본 NEW)
- 주석 안 제안 없음. 자동 활성화 문자: 영문자, `_`, `$`, `.` (`SQLCompletionProcessor.computeCompletionProposals`)
- 직전 키워드로 문맥 판정: 테이블 키워드 `FROM INSERT UPDATE DELETE INTO TABLE VIEW JOIN TRUNCATE MERGE`,
  컬럼 키워드 `SELECT WHERE SET ON AND OR BY HAVING` (`M/model/sql/SQLConstants`)
- 별칭 해석: `MS/analyzer/TableReferencesAnalyzerImpl`가 `FROM t a`에서 별칭 맵을 만듦
- 정렬: 종류 순서(조인 조건, 컬럼, 테이블, 스키마, 프로시저, 키워드) 후 퍼지 점수, 알파벳순 (`UI/syntax/SQLCompletionSorter`)

### 4. 구문 강조
- 토큰 종류 `SQLTokenType` (KEYWORD, STRING, QUOTED, TYPE, NUMBER, COMMENT, DELIMITER, PARAMETER 등)
- 강조와 분할이 같은 `SQLRuleManager` 규칙을 공유
- 키워드는 SQL2003 기본 + 드라이버 메타데이터 + 방언별 하드코딩 (`BasicSQLDialect.loadStandardKeywords`, `JDBCSQLDialect.loadDriverKeywords`)

### 5. 실행 (`UI/SQLQueryJob.run`, `executeSingleQuery`, `executeStatement`)
- 사전 검사: 읽기 전용 연결에서 변경 문장 차단, WHERE 없는 DELETE와 UPDATE, DROP TABLE 확인 대화상자 (`isDeleteUpdateDangerous`)
- 문장 순회, 오류 정책(무시, 중지, 재시도), 끝나면 통계(실행 시간, 영향 행 수)
- 결과 셋 여러 개는 `nextResults()`로 새 탭. 결과 없으면 `getUpdateRowCount()`
- 취소: 작업 취소 + JDBC `Statement.cancel()` (`JDBCDataSource.cancelStatementExecute`)
- 매개변수 `:name` 기본 켬, 값은 텍스트 치환(`SQLUtils.fillQueryParameters`)

### 6. 방언 차이
| 항목 | PostgreSQL | MySQL | SQLite |
|---|---|---|---|
| 식별자 따옴표 | `"` | `` ` ``, `"` | `"`, `[ ]`, `` ` `` |
| 문자열 이스케이프 | 서버 지원 시 `\`, `E'...'` | `\` | 없음 |
| 한 줄 주석 | `--` | `-- `, `#` | `--` |
| BEGIN/END 블록 | 없음 | 없음 | 있음 |
| 달러 따옴표 | `$$`, `$tag$` | 없음 | 없음 |
| 구분자 재정의 | 없음 | `DELIMITER` | 없음 |
| 중첩 주석 | 예 | 아니오 | 아니오 |
- 근거: `ext.postgresql/.../PostgreDialect`, `ext.mysql/.../MySQLDialect`, `ext.sqlite/.../SQLiteSQLDialect`,  
  `MS/parser/rules/SQLDollarQuoteRule`

### 7. sqlkiwi에 옮길 요점
1. 방언을 데이터로 정의하고 분할기가 그것만 읽음
2. 토크나이저는 따옴표, 주석, 구분자, 단어 순서로 판정
3. 분할은 블록 스택 + 구분자 + 빈 줄(기본 켬)
4. 커서 문장 선택은 순수 함수 `statementAt`
5. 스크립트는 문장마다 시간, 영향 행 수, 오류 기록, 오류 시 중지
6. 취소는 드라이버별(`pg_cancel_backend`, `KILL QUERY`, SQLite는 작업 중단)
7. 위험 문장(WHERE 없는 DELETE, UPDATE) 확인

## DBeaver 25.0.5 스키마 탐색 트리 분석 (sqlkiwi 설계용)

- 분석 대상: Vineflower 1.12.0으로 역컴파일한 `.temp/dbeaver-src/` (ext.postgresql, ext.mysql, ext.sqlite, ext.generic,  
  model, model.jdbc)
- 분석: Sonnet 분석가, 저장과 검수: 클로니
- 근거 표기: `상대경로:클래스.메서드`

### 1. 공통 구조
#### 관찰
- 트리 모양은 각 `plugin.xml`의 `<tree>` 선언(folder, items property)에서 옴. 펼칠 때 getter를 불러 자식을 얻음  
  (`ext.postgresql/plugin.xml` 92행, `model/.../navigator/DBNDatabaseNode.java:loadTreeItems`)
- 자식은 처음 펼칠 때만 읽고 보관함 (`DBNDatabaseNode.getChildren`)
- 목록 캐시 `JDBCObjectCache.loadObjects`: 메타 전용 세션, `setFetchSize(1000)`, 행마다 `fetchObject`
- 테이블과 컬럼은 `JDBCStructCache`, 인덱스와 제약은 스키마 전체를 한 질의로 읽어 부모별로 나누는 `JDBCCompositeCache`
- 새로고침은 선택 노드 아래 캐시만 지우고 다시 읽음 (`DBNDatabaseNode.refreshNode`, `PostgreSchema.refreshObject`)
- 시스템 객체는 질의가 아니라 트리 생성 때 숨김. 자식이 스키마나 카탈로그 하나뿐이면 보여 줌 (`DBNDatabaseNode.loadTreeItems`)
#### 모름
- 펼침 작업 스레드 세부, `tryExecuteRecover` 재시도 횟수

### 2. PostgreSQL
- DB 목록: `pg_database` 에서 `datallowconn AND NOT datistemplate`. 기본은 연결 DB 하나만 보임  
  (`PostgreDataSource.isReadDatabaseList`, `prepareReadDatabaseListStatement`). DB마다 연결이 따로임  
  (`PostgreDatabase.openIsolatedContext`)
- 스키마: `pg_namespace` 전체를 읽고 앱에서 숨김. 시스템은 `pg_catalog`, `information_schema`, `pg_` 접두 (`PostgreSchema.isSystem`),
  유틸리티는 `pg_toast`, `pg_temp_` (`PostgreSchema.isUtilitySchema`)
- 테이블류: `pg_class WHERE relnamespace=? AND relkind NOT IN ('i','I','c')`, `relkind` r, p 테이블, v 뷰, m 구체화 뷰, f 외부 테이블  
  (`PostgreSchema.TableCache.prepareLookupStatement`)
- 컬럼: `pg_attribute` + `pg_attrdef`(기본값 `pg_get_expr`) + `pg_description`, `NOT attisdropped`, `ORDER BY  
  attnum`, 음수 attnum 숨김  
  (`TableCache.prepareChildrenStatement`, `PostgreAttribute.isHidden`)
- 인덱스: `pg_index` + `pg_class`, `indkey`를 attnum으로 풀고 식 인덱스는 `pg_get_indexdef` (`PostgreSchema.IndexCache`)
- 제약: `pg_constraint`, `contype` p, u, c, f, 컬럼은 `conkey`, 참조 컬럼은 `confkey` (`PostgreSchema.ConstraintCache`)

### 3. MySQL
- 카탈로그가 곧 DB, 스키마 층 없음. `show databases` (`MySQLDataSource.CatalogCache`)
- 시스템 DB: `information_schema`, `performance_schema`, `mysql` (`MySQLDataSource.isSystemCatalog`)
- 테이블, 뷰: `SHOW FULL TABLES FROM db`, `Table_type`에 VIEW면 뷰 (`MySQLCatalog.TableCache`)
- 컬럼: `information_schema.COLUMNS ... ORDER BY ORDINAL_POSITION`
- 인덱스: `information_schema.STATISTICS ... ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX`
- 기본 키, 유니크: `KEY_COLUMN_USAGE` (REFERENCED_TABLE_NAME IS NULL), 이름 `PRIMARY`면 기본 키
- 외래 키: JDBC `getImportedKeys` (`MySQLTable.loadForeignKeys`). 내부 SQL은 모름
- 연결 때 `lower_case_table_names` 확인

### 4. SQLite
- `generic` 확장 위에 얹힘. 메타데이터는 JDBC `DatabaseMetaData` 호출(getTables, getColumns, getPrimaryKeys, getIndexInfo,  
  getImportedKeys)
- DBeaver 코드에 `PRAGMA` 문자열 0건. 직접 SQL은 트리거와 DDL(`sqlite_master`), `sqlite_sequence` 정도  
  (`SQLiteUtils.readMasterDefinition`)
- 숨김: `sqlite_` 접두 시스템, `sqlite_autoindex_` 유틸리티 (`SQLiteMetaModel.isSystemTable`, `isUtilityTable`)
- 추론: sqlkiwi는 `sqlite_master` + `PRAGMA table_xinfo`, `index_list`, `index_info`, `foreign_key_list`로 같은 정보를  
  얻음(sqlkiwi의 선택)

### 5. 드라이버 기본값 (plugin.xml)
| 항목 | PostgreSQL | MySQL 8 | SQLite |
|------|-----------|---------|--------|
| 기본 포트 | 5432 | 3306 | 없음 |
| 기본 DB | postgres | 없음 | 파일 경로 |
| 기본 사용자 | postgres | root | 없음 |
| 연결 타임아웃 | 20초 | 20000ms | 해당 없음 |

- SQLite 읽기 전용이면 `open_mode=1` (`SQLiteDataSource.getInternalConnectionProperties`)

### 6. 테이블 데이터 열기
- `SELECT <컬럼 또는 *> FROM <정규화 이름> [WHERE] [ORDER BY]` (`JDBCTable.readData`)
- 기본 최대 행 수 `resultset.maxrows` = 200 (`ModelPreferences.java` 166행)
- MySQL과 MariaDB는 SQL 끝에 `LIMIT offset, n`을 붙이고, PostgreSQL과 SQLite는 JDBC `setMaxRows`, `setFetchSize`로 제한
- 이미 LIMIT, OFFSET, INTO, UPDATE, PROCEDURE, FETCH가 있으면 덧붙이지 않음 (`NON_LIMIT_QUERY_PATTERN`)
- 전체 행 수는 `SELECT COUNT(*)` 별도 실행

### 7. sqlkiwi에 옮길 설계 요점
1. 펼칠 때 한 층만 읽고 캐시, 새로고침은 그 노드 아래만 무효화
2. 시스템 객체 숨김은 앱에서 처리, 기본은 숨김
3. PostgreSQL은 연결 DB 하나만 표시, 스키마 > 테이블과 뷰 > 컬럼, 인덱스, 외래 키
4. PostgreSQL 테이블류는 `pg_class`의 `relkind`로 분류
5. MySQL은 DB(카탈로그) > 테이블과 뷰, `information_schema` 기반
6. SQLite는 `sqlite_master`와 PRAGMA 기반, `sqlite_` 접두 숨김
7. 결과는 200행씩 가져옴(Node 드라이버는 커서나 스트림으로 구현)

## DBeaver 25.0.5 결과 그리드와 연결 관리 분석 (sqlkiwi 설계용)

- 근거 기준 `.temp/dbeaver-src/`. UEDATA=`ui.editors.data/.../ui/controls/resultset`, REG=`registry/.../registry`
- 실제 DBeaver 작업 공간과 비밀번호 파일은 열지 않음. 암호화 키 값은 옮기지 않음

### (가) 결과 그리드
1. 한 묶음 200행 (`resultset.maxrows`, `model/ModelPreferences.java`, `UEDATA/ResultSetViewer.getSegmentMaxRows`)
2. 스크롤 끝에서 자동으로 다음 묶음 (`resultset.autofetch.next.segment` 기본 true, `ResultSetViewer.readNextSegment`).
   DBeaver는 offset을 바꿔 같은 질의를 다시 실행함
3. 더 있음 판정은 받은 행 수가 최대 이상 (`UEDATA/ResultSetDataReceiver`), 행 수 표시는 `200+` (`ResultSetViewer.updateStatusInfo`)
4. 전체 행 수는 수동, `SELECT COUNT(*) FROM (원질의) dbvrcnt` (`model.sql/.../SQLQueryTransformerCount`)
5. NULL 화면 표시 `[NULL]`, 복사는 빈 문자열 (`model/DBValueFormatting.getDefaultValueDisplayString`)
6. 시각 형식 `yyyy-MM-dd HH:mm:ss.SSS`, 날짜 `yyyy-MM-dd`, 시간 `HH:mm:ss` (`model/DBConstants`)
7. 바이너리 앞 32자 미리보기 + `...`, BLOB은 `[BLOB]` (`DBValueFormatting.formatBinaryString`)
8. 숫자와 날짜 열은 오른쪽 정렬 기본
9. 정렬 SMART: 다 받았으면 메모리 정렬, 남았으면 서버 ORDER BY 재질의 (`ResultSetViewer.toggleSortOrder`).
   순환은 없음, 오름차순, 내림차순, 해제
10. 필터는 서버 재질의, 감싸기 `SELECT * FROM (원질의) z_q WHERE ...`
11. 셀 복사는 탭 구분, 값에 구분자가 있을 때만 따옴표 (`SpreadsheetPresentation.copySelection`)
12. 레코드 모드(행을 세로로) 있음 (`SpreadsheetPresentation.changeMode`)

### (나) 연결 관리
1. 설정 파일 `.dbeaver/data-sources.json` (`model/app/DBPDataSourceRegistry`), 최상위 `folders`, `connections`
2. 연결 ID `<드라이버>-<시각16진>-<난수16진>` (`DataSourceDescriptor.generateNewId`)
3. 쓰기는 백업 후 덮어쓰기 (`DataSourceConfigurationManagerNIO.writeConfiguration`)
4. 비밀번호는 `credentials-config.json`에 파일 통째로 `AES/CBC/PKCS5Padding`, 키는 앱 코드에 고정된 값 (`model/impl/app/BaseProjectImpl`),
   무결성 검사 없음. 같은 코드로 누구나 풀 수 있는 난독화 수준(추론)
5. 연결 테스트는 접속 후 DB 제품과 버전 조회 (`ConnectionTestJob.run`)
6. keep-alive 기본 꺼짐, 켜면 테스트 SQL로 확인하고 재연결 (`DataSourceMonitorJob`, `KeepAlivePingJob`)
7. 질의 중 연결 끊김 오류는 1회 재시도 (`DBExecUtils.tryExecuteRecover`)
8. 자동 커밋 기본은 연결 유형이 정함: dev와 test는 켬, prod는 끔 + 실행 전 확인 (`DBPConnectionType`)
9. 읽기 전용은 JDBC `setReadOnly(true)` + 앱의 편집 차단 (`JDBCDataSource`, `DataSourceDescriptor.hasModifyPermission`)

### sqlkiwi에 옮길 요점
1. 200행 묶음 + 스크롤 끝 자동 로딩. offset 재질의 대신 서버 커서를 유지해 행 겹침과 누락을 피함(sqlkiwi의 선택)
2. 행 수는 `200+`로 시작
3. 값은 화면용 문자열로 바꿔 넘기고, 큰 정수와 10진수와 날짜는 문자열로 받음(JS 숫자 정밀도 한계)
4. NULL `[NULL]`, 바이너리 16진 미리보기
5. 정렬은 SMART 규칙
6. 설정은 단일 JSON, 비밀번호는 Electron `safeStorage`로 OS 계정에 묶어 별도 파일에 저장
7. 읽기 전용은 드라이버 수준 읽기 전용 + 앱 수준 차단

