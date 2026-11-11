# DBeaver에서 확인한 작업 흐름과 sqlkiwi의 설계

SQL 클라이언트에서는 연결을 고르고, 테이블 구조를 살펴보고, SQL을 실행한 뒤 결과를 확인하는 일이 이어집니다.
이 흐름을 한 화면에서 사용할 수 있도록 설치된 DBeaver의 배포 파일을 분석했습니다.
분석 결과는 기능의 근거로 사용하고, 구현 코드는 이 프로젝트에서 새로 작성합니다.

## 분석 대상과 근거

이 PC의 `%LOCALAPPDATA%/DBeaver`에 설치된 Community 25.0.5를 대상으로 했습니다.
2026-11-07에 REA MCP 플러그인 6.8.0으로 JAR을 열고 컨테이너 구성과 해시를 확인했습니다.
분석이 끝난 세션은 `close_binary`로 닫았습니다.

| 대상 | SHA-256 | REA 정적 조사 결과 |
| --- | --- | --- |
| SQL 편집기 1.0.155 | `c7bea38a21688d8043096eb5b5bde91f9a0fd5a51c252b1b3358e51332d5c862` | 557개 파일, 42개 디렉터리 |
| SQL 모델 1.0.145 | `8c473835851ec9759bf5211696cdd15619be75f78868c22a5d0a9589dd2f9548` | 407개 파일, 40개 디렉터리 |

원본 REA Evidence는 다음 파일에 보존했습니다.

- [SQL 편집기 Evidence](evidence/rea-dbeaver.json)
- [SQL 모델 Evidence](evidence/rea-dbeaver-sql-model.json)
- [설치 파일 메타데이터와 명령 연결](evidence/installed-artifacts.json)

편집기의 부모 Evidence ID는
`ev_cf3e187c7b2951f2d8866b63ef5f7f3e204b33a718acecb7e3f8666f26517b16`입니다.
모델의 부모 Evidence ID는
`ev_78542c1790fb6ad7652f41f7166afc40d56b9891ae30f37aa65b9e6f157c03e5`입니다.

REA의 컨테이너 조사는 파일 목록과 바이트 식별을 확인합니다. 실행 동작까지 입증하지는 않습니다.
따라서 기능의 의미는 설치 JAR의 `plugin.xml`과 별도의 역컴파일 결과를 함께 읽어 판단했습니다.
메타데이터 조사는 `python scripts/inspect-dbeaver.py`로 다시 수행할 수 있습니다.

## 관찰한 사실

`ui.editors.sql/plugin.xml`에는 현재 문장 실행과 스크립트 실행이 서로 다른 명령으로 등록되어 있습니다.
Windows의 현재 문장 실행은 `Ctrl+Enter`, 스크립트 실행은 `Alt+X`에 연결됩니다.
두 명령은 `SQLEditorHandlerExecute`로 연결되며, 취소는 별도 핸들러에 연결됩니다.
이 내용은 `installed-artifacts.json`의 `keyBindings`와 `handlers`에서 확인할 수 있습니다.

Vineflower 1.12.0으로 설치 JAR에서 직접 꺼낸 세 클래스를 추가로 역컴파일했습니다.
이 작업은 REA의 Java 역컴파일 기능을 실행한 것으로 표현하지 않습니다.
복원 파일은 저장소 밖의 작업용 `.temp/sqlkiwi-openai-dbeaver/decompiled`에 두었습니다.

| 복원 클래스 | 확인한 지점 | 관찰 내용 |
| --- | --- | --- |
| `ModelPreferences` | `initializeDefaultPreferences`, 복원본 145 ~ 167행 | 기본 구분자는 `;`, 기본 결과 묶음은 200행입니다. |
| `SQLScriptParser` | `parseQueryImpl`, `extractScriptQueries` | 토큰을 읽어 실행할 문장 범위를 구성합니다. |
| `SQLQueryJob` | `run`, 복원본 216 ~ 279행 | 문장을 순서대로 실행하고, 오류 처리와 취소 상태를 확인합니다. |
| `SQLQueryJob` | `executeStatement`, 복원본 595 ~ 680행 | 실행 시간과 결과 집합, 영향 행 수를 각각 다룹니다. |

위 행 번호는 원본 소스 행 번호가 아니라 이번 역컴파일 결과의 위치입니다.
`SQLQueryJob`의 일부 제어 흐름에는 복원기 경고가 있습니다.
`SQLScriptParser.extractNextQueryImpl`과 `skipCommentsBackTillLetter`는 복원에 실패했습니다.
이 메서드의 내부 동작을 확인했다고 주장하지 않습니다.

## sqlkiwi에 적용하는 방식

탐색기는 왼쪽에, SQL은 가운데에, 결과는 아래에 놓습니다.
테이블을 열면 해당 테이블을 조회하는 새 SQL 탭을 만들고, 컬럼의 자료형과 기본 키를 확인하게 합니다.
현재 문장과 스크립트 실행을 구분하고, 실행 이력에서 SQL을 다시 사용할 수 있게 합니다.

결과는 기본 200행으로 제한하고 사용자가 500행 또는 1,000행을 선택하게 합니다.
가져온 범위를 넘는 행이 있으면 화면에서 잘림을 알립니다.
이 프로젝트의 행 수 제한은 전체 데이터를 계속 읽어오는 DBeaver의 페이지 탐색과 같은 기능이 아닙니다.

구현은 Electron, React, CodeMirror와 Node 데이터베이스 드라이버를 사용합니다.
DBeaver의 Eclipse, SWT, JDBC 구조를 그대로 옮기지 않습니다.
비밀번호는 Electron `safeStorage`를 통해 운영체제 계정에 연결된 방식으로 저장합니다.
기존 DBeaver 연결 설정이나 자격 증명은 읽지 않습니다.

## 분석 범위 밖의 내용

이번 조사에서는 DBeaver를 실행해 실제 사용자 조작을 녹화하거나 전체 기능을 비교하지 않았습니다.
ER 다이어그램, SSH 터널, JDBC 드라이버 관리자, 플러그인 생태계와 모든 SQL 방언의 동등성은 범위 밖입니다.
sqlkiwi의 동작 검증은 별도 테스트로 수행하고 [검증 기록](verification.md)에 구분해 기록합니다.
