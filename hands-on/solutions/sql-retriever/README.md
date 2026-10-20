# 정형 데이터 검색기

고객 상담 중 상담사가 이탈 위험 신호를 포착하면, 상담 오케스트레이터는 필요한 고객 현황을 요청합니다.  
이 프로그램은 PostgreSQL의 카드·승인 사용액·연체 자료를 검색해 다음 단계에 전달합니다.  
[유저스토리](../../specs/userstory.md)의 **S-03 / UFR-EVID-010 고객 현황 확보**를 구현합니다.

오케스트레이터는 정형 검색이 필요한지를 결정합니다. 검색기는 고정 조회 목록과 허용 스키마를 소유하고,  
자연어 질문에 맞는 고정 조회를 선택하거나 SQL을 생성합니다. 고정 조회 목록을 오케스트레이터에 복제할 필요가 없습니다.

## 검색 방식과 LLM 호출

| 요청 | 검색 계획과 실행 | 정상 처리 시 LLM 호출 |
|---|---|---|
| `auto` + 질문 | 한 번의 모델 응답에서 고정 `query_id` 또는 SQL 선택·생성 후 실행 | 1회 |
| `fixed` | 지정한 고정 조회 실행; 미지정 시 `customer_snapshot` | 0회 |
| `nl2sql` + 질문 | SQL 생성 → 검증 → 실행 | 1회 |
| 위 요청 + `explain=true` | 검색 후 확인용 결과 설명 생성 | 추가 1회 |

기본 모드는 `auto`이며, **검색 후 설명 생성은 기본 OFF**입니다.  
실제 시스템은 `data`에 들어 있는 검색 결과를 사용합니다. `explanation`은 개발자가 확인할 때만 사용합니다.  
전송 실패에는 SDK 재시도가 최대 1회 있어 네트워크 전송 횟수는 위 논리 호출 횟수보다 늘어날 수 있습니다.  
SQL 검증 실패를 자동 재작성하는 반복 루프는 없습니다.

LLM은 실행 옵션에 따라 Groq의 `openai/gpt-oss-120b` 또는 로컬 Gemma 4 12B를 사용합니다.  
Gemma는 Ollama와 vLLM 런타임을 지원하며, 두 모델 경로 모두 같은 `QueryPlan` 계약을 반환합니다.  
정형 검색기로는 이탈 확률을 예측하거나 최종 상담 제안을 작성하지 않습니다.  
문서·과거 상담 근거 조회와 채택 기록도 별도 유저스토리의 책임입니다.

## 계층 구조

```text
run_sql.py / serve_sql.py
  └─ presentation: CLI 인자·HTTP 요청 수신, 결과·오류 출력
       └─ application: 공통 요청 계약과 검색 흐름
            ├─ domain: 고정 조회 목록, 날짜 규칙, 식별자 제거
            └─ ports ← infrastructure: PostgreSQL, SQL 검증, Groq·Ollama, 환경 설정

app/bootstrap.py: 인터페이스와 실제 어댑터 조립
```

CLI와 API는 같은 `SearchService.execute()`를 호출합니다.  
응용 계층은 메서드를 순서대로 호출하여 `검색 계획 → 조회 → 선택적 설명`을 실행합니다.  
인프라 구현은 직접 생성하지 않고 주입받으며, LLM 호출은 각 어댑터 안에서 LCEL 체인으로 구성합니다.  
검색 계획은 Structured Output으로 `QueryPlan` 형식에 맞춰 받습니다.  
조회 계획과 실행 SQL의 검증은 구분합니다. 모델이 선택한 계획이더라도 허용 규칙을 통과해야 DB에서 실행합니다.

## 설치와 설정

Python 3.12 이상에서 다음 명령을 실행합니다. 경로는 저장소 루트 기준입니다.

```powershell
cd hybrid-ai-lab/retriever/sql-retriever
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

키는 작업 디렉터리와 관계없이 **`secrets/.env`**에서 읽습니다.  
서비스 폴더에 키를 복사할 필요는 없습니다. 실제 값은 코드·예제·로그에 포함하지 않습니다.  
같은 이름의 프로세스 환경변수가 있으면 그 값을 우선합니다.

```dotenv
GROQ_API_KEY=발급받은_키
SQL_RETRIEVER_LLM_PROVIDER=groq
SQL_RETRIEVER_LLM_RUNTIME=ollama
SQL_RETRIEVER_GROQ_MODEL=openai/gpt-oss-120b
SQL_RETRIEVER_GEMMA_MODEL=hf.co/unsloth/gemma-4-12B-it-qat-GGUF:UD-Q4_K_XL
SQL_RETRIEVER_OLLAMA_BASE_URL=http://127.0.0.1:11434
# DSN은 선택, 비밀번호는 필수입니다.
SQL_RETRIEVER_DB_DSN=host=localhost port=5432 dbname=cardlab user=sql_retriever_user
SQL_RETRIEVER_DB_PASSWORD=실습_DB_비밀번호
```

DSN이 없으면 공통 RDB의 `localhost:5432/cardlab`과 검색기 전용 `sql_retriever_user`를 사용합니다.  
DB 비밀번호는 `secrets/.env`의 `SQL_RETRIEVER_DB_PASSWORD`에서만 읽습니다. 값이 없으면 DB 연결이 실패합니다.  
기존 `S22_DB_DSN`, `S22_DB_PASSWORD`도 인식합니다. 예전 SQLite용 `S22_DB_PATH`는 사용하지 않습니다.  
RDB가 꺼져 있다면 [공통 RDB 안내](../../rdb/README.md)에 따라 시작합니다.

선택 설정은 `.env.example`에서 확인할 수 있습니다. DB 쿼리 제한은 기본 5초, 모델 요청 제한은 기본 30초입니다.
`fixed` 검색과 스키마 명세 조회에는 API 키가 필요하지 않습니다.

## CLI

고객 현황 전체를 LLM 없이 조회합니다.

```powershell
.\.venv\Scripts\python.exe run_sql.py --query-mode fixed --member-id M-1042 --base-date 2026-08-31
```

자연어 질문으로 고정 조회 선택 또는 SQL 생성을 맡깁니다.

```powershell
.\.venv\Scripts\python.exe run_sql.py --member-id M-1042 --base-date 2026-08-31 --question "보유 카드 목록을 보여 주세요"
.\.venv\Scripts\python.exe run_sql.py --member-id M-1042 --base-date 2026-08-31 --question "월별 총 승인 사용액을 합산해 주세요"
```

호출할 LLM은 Groq `openai/gpt-oss-120b` 또는 로컬 `Gemma 4 12B QAT UD-Q4_K_XL` 중에서 선택합니다.  
로컬 모델을 사용하려면 Ollama가 실행 중이고 모델이 설치되어 있어야 합니다.

```powershell
ollama pull hf.co/unsloth/gemma-4-12B-it-qat-GGUF:UD-Q4_K_XL
.\.venv\Scripts\python.exe run_sql.py --llm-provider google_local `
  --member-id M-1042 --base-date 2026-08-31 --question "보유 카드 목록을 보여 주세요"
```

공식 원본은 `google/gemma-4-12B-it-qat-q4_0-unquantized`이고, Ollama용 GGUF는 `unsloth`가 배포한  
UD-Q4_K_XL 변환본입니다. 이 환경에 설치된 Ollama 0.40.0-rc0에서 동작을 확인했습니다.

조회 방식을 강제로 지정하거나 확인용 설명을 추가할 수도 있습니다.

```powershell
.\.venv\Scripts\python.exe run_sql.py --query-mode fixed --query-id delinquency `
  --member-id M-1042 --base-date 2026-08-15
.\.venv\Scripts\python.exe run_sql.py --query-mode nl2sql --member-id M-1042 `
  --base-date 2026-08-31 --question "월별 승인 총액은?"
.\.venv\Scripts\python.exe run_sql.py --query-mode fixed --member-id M-1042 --base-date 2026-08-31 --explain
.\.venv\Scripts\python.exe run_sql.py --schema
```

JSON 결과는 stdout으로, 오류는 stderr로 출력합니다. 스키마 명세는 키·DB 접속 없이 확인할 수 있습니다.  
PowerShell에서 결과를 다른 프로그램으로 전달할 때는 UTF-8 인코딩을 사용합니다.

### M-5029 auto 모드 테스트

DB와 `.env`를 준비한 뒤, 표의 질문을 `$question`에 하나씩 넣어 실행합니다.
기준일을 고정하면 상대적인 날짜 표현을 같은 조건에서 비교할 수 있습니다.

```powershell
$question = "발급받은 카드의 상품명, 브랜드, 발급일, 현재 상태를 카드별로 알려 주세요."
.\.venv\Scripts\python.exe run_sql.py --query-mode auto --member-id M-5029 --base-date 2026-08-31 --question $question
```

결과의 `requested_query_mode`는 `auto`이고, 실제 선택된 `query_mode`를 아래 예상 값과 비교합니다.

| 번호 | 질문 | 예상 query mode |
| ---: | --- | --- |
| 1 | 발급받은 카드의 상품명, 브랜드, 발급일, 현재 상태를 카드별로 알려 주세요. | fixed |
| 2 | 상담에 필요한 카드 보유 현황과 최근 이용 내역, 최신 연체 현황을 한꺼번에 확인해 주세요. | fixed |
| 3 | 각 카드가 최근 6개월 동안 월마다 승인 사용한 금액과 승인 건수를 보여 주세요. | fixed |
| 4 | 최근 완료 월의 연체 금액, 연체 일수, 최근 12개월 연체 월 수를 알려 주세요. | fixed |
| 5 | 현재 보유 중인 카드별 상품과 연회비 목록을 확인하고 싶어요. | fixed |
| 6 | 최근 2개월 전체 카드의 승인 사용액을 월별로 합산해 보여 주세요. | nl2sql |
| 7 | 지난달 전체 카드의 승인 건수 합계를 알려 주세요. | nl2sql |
| 8 | 이번 달 카드별 승인 사용액을 큰 금액부터 정렬해 주세요. | nl2sql |
| 9 | 브랜드별 보유 카드 수와 연회비 합계를 보여 주세요. | nl2sql |
| 10 | 현재 카드 상태별 카드 수를 많은 순서대로 보여 주세요. | nl2sql |
| 11 | 보유 카드 전체의 평균 연회비를 계산해 주세요. | nl2sql |
| 12 | ACTIVE 카드 중 연회비가 낮은 두 장의 카드 참조값, 상품명, 연회비를 보여 주세요. | nl2sql |
| 13 | 이 회원의 가입일과 연령대만 보여 주세요. | nl2sql |
| 14 | 최근 4개월 중 전체 카드 승인 사용액이 가장 컸던 월과 금액을 알려 주세요. | nl2sql |
| 15 | 최근 2개월 전체 카드의 승인 거래 1건당 평균 승인 금액을 계산해 주세요. | nl2sql |
| 16 | 이 회원이 최근 3개월동안 가장 많이 소비한 업종은 무엇인가요? | nl2sql |
| 17 | 최근 3개월 동안 가장 많이 소비한 가맹점 이름, 업종, 승인 금액을 알려 주세요. | nl2sql |
| 18 | 최근 7일 동안 하루별 승인 사용액과 승인 건수를 날짜순으로 보여 주세요. | nl2sql |
| 19 | 최근 6개 완료 월의 연체 금액과 연체 일수를 월별로 보여 주세요. | nl2sql |

## HTTP API

```powershell
.\.venv\Scripts\python.exe serve_sql.py --port 8012
.\.venv\Scripts\python.exe serve_sql.py --port 8012 --llm-provider google_local
```

기본 바인딩은 `127.0.0.1`, 로컬 기본 포트는 `8012`입니다. `/docs`에서 요청 계약을 확인할 수 있습니다.

| 메서드·경로 | 용도 |
|---|---|
| `POST /search` | CLI와 동일한 검색 서비스 호출 |
| `GET /schema` | 고정 조회 목록과 허용 논리 테이블·컬럼 명세 |
| `GET /health` | 프로세스 생존 확인; DB·LLM 연결 검증 결과가 아님 |

`auto` 요청 예시입니다.

```json
{
  "query_mode": "auto",
  "member_id": "M-1042",
  "base_date": "2026-08-31",
  "question": "월별 총 승인 사용액을 합산해 주세요",
  "explain": false
}
```

`fixed` 요청은 `question`을 생략할 수 있습니다. `query_id`는 `fixed`에서만 직접 지정합니다.

```json
{
  "query_mode": "fixed",
  "query_id": "customer_snapshot",
  "member_id": "M-1042",
  "base_date": "2026-08-31"
}
```

응답의 `requested_query_mode`는 요청 방식이고 `query_mode`는 실제 선택한 `fixed` 또는 `nl2sql`입니다.
`query_id`, `routing_reason`, `data`, `warnings`, `explanation_status`로 선택 이유와 결과를 확인합니다.  
설명을 요청하지 않으면 `explanation=null`, `explanation_status=not_requested`입니다.  
설명 생성에 실패해도 성공한 검색 결과는 유지하고 `explanation_status=failed`로 반환합니다.

입력 오류와 거부된 SQL은 실행하지 않습니다. DB 또는 LLM 실패 시 SQL·접속 문자열·키를 오류 본문에 노출하지 않습니다.  
이 API는 신뢰된 내부 호출용이며, 상담사 인증과 해당 회원 조회 권한 확인은 호출 측에서 수행해야 합니다.  
현재 실습 서비스에는 사내 인증·권한 시스템 연동이 없습니다.

## 고정 조회와 논리 스키마

| query_id | 반환할 내용 |
|---|---|
| `customer_snapshot` | S-03용 고객 현황 전체, 원본 카드ID·상품ID, 승인 사용액, 연체액, 출처·기준시점 |
| `cards` | 보유 카드·상품·브랜드·발급일·현재 상태·상품 시행일·연회비 |
| `monthly_usage` | 최근 6개월 카드별 월 승인액·승인 건수·조회 기간 |
| `delinquency` | 기준일 이전 완료된 월 중 최신 연체 지표 |

NL2SQL은 원본 테이블을 직접 검색하지 않습니다. 요청 회원·기준일로 제한한 논리 테이블만 봅니다.  
논리 테이블은 DB의 `app` 스키마 뷰이며, 정의는 `rdb/init/04_views_rls.sql`,  
`rdb/init/05_merchant_usage.sql`, `rdb/init/06_history_daily_usage.sql`에 있습니다.  
기존 DB에는 새로 추가된 05·06 파일을 순서대로 적용해야 합니다.

| 논리 테이블 | 내용 |
|---|---|
| `customer_profile` | 해당 회원의 가입일·연령대 |
| `customer_cards` | 해당 회원의 기준일 이전 발급 카드와 연결 상품 |
| `monthly_usage` | 해당 회원 카드의 최근 6개월 월별 승인 거래 집계 |
| `merchant_usage` | 해당 회원의 최근 6개월 카드·월·가맹점별 승인액·건수, 가맹점명·업종·실제 첫/마지막 승인일 |
| `customer_daily_usage` | 기준일 포함 최근 90일의 회원별 일 승인액·건수, 무거래일은 0원·0건 |
| `customer_delinquency` | 기준일 이전 완료된 월의 최신 회원 단위 연체 지표 |
| `customer_delinquency_history` | 기준일 이전 완료된 최근 12개월의 월별 연체 이력 |

전체 컬럼은 `--schema` 또는 `/schema`에서 확인합니다. 명세의 원본은 코드 한곳에 있습니다.  
카드 연결에는 요청 내 대체 식별자 `card_ref`를 사용합니다.  
검색 결과에 원본 카드ID가 필요한 S-03 호출은 `customer_snapshot`을 사용합니다.  
원본 카드ID는 `app` 스키마에 없고, NL2SQL에 열지 않은 `app_internal` 스키마에만 둡니다.

### 회원 격리를 지키는 방법

격리 책임을 한 곳에만 두어 같은 조건이 두 군데로 갈라지지 않게 합니다.

| 층 | 담당 | 무엇을 막나 |
|---|---|---|
| 읽기 전용 계정 | `sql_retriever_user` | 원본 테이블 권한이 없어 `public.card` 조회 자체가 거부됨 |
| 행 수준 보안(RLS) | `public`의 회원 관련 4개 테이블 | 세션에 지정한 회원 외의 **행**을 DB가 돌려주지 않음 |
| 논리 뷰 | `app` / `app_internal` | 기준일·최근 6개월 창·컬럼 선택·`card_ref` 생성 |
| SQL 검증기 | `app/infrastructure/sql_guard.py` | 모델이 만든 SQL의 구문·테이블·컬럼·행수 |

조회 전에 읽기 전용 트랜잭션 안에서 세션 변수 세 개를 지정합니다.  
`app.member_id` · `app.base_date` · `app.coverage_start`이며, `set_config(..., true)`로 넣어  
트랜잭션이 끝나면 자동으로 풀립니다. 지정하지 않으면 모든 논리 뷰가 0행을 반환합니다.

DB에 로그인할 수 있는 실습 계정은 `sql_retriever_user` 하나뿐이며, 전체 허용 정책을 가진 계정은 없습니다.  
원본 테이블 전체를 읽어야 하는 오프라인 도구(스키마 추출 등)는 관리 계정 `cardlab`을 씁니다.

## 데이터 해석과 검증 경계

- 공통 RDB는 교육용 합성 데이터입니다. 요청 기준일과 `lab_metadata`의 데이터 기준일을 구분합니다.
- 데이터 기준일 이후 또는 회원 가입 전을 조회하면 거부합니다. 예제 기준일은 `2026-08-31`입니다.
- 거래 제공 기간은 메타데이터 `txn_period`에서 확인합니다. 현재 실습 데이터는 `2025-08`부터 있습니다.
- 제공 기간 이전 요청은 거부하며, 초기 월 조회에서는 가용 월만 반환하고 없는 과거 월을 0원으로 채우지 않습니다.
- 승인 사용액은 `APPROVED` 거래만 합산합니다. 취소 거래·기준일 이후 거래를 포함하지 않습니다.
- 연체 자료는 월말을 실제 기준시점으로 사용합니다. `2026-08-15` 요청에 8월 말 자료를 사용하지 않습니다.
- 카드 상태 이력이 없어 `current_status`는 현재 스냅샷으로 표시합니다.
- 기준일 이전 발급 카드를 현재 상태와 함께 반환합니다. 현재 `ACTIVE` 상태로 과거 거래를 일괄 제외하지 않습니다.
- 상품 시행일이 미래이면 조회 당시 유효한 연회비로 단정하지 않도록 경고합니다.
- 월 집계는 건별 거래가 아닙니다. 건수는 `SUM(transaction_count)`이며 `COUNT(*)`는 집계 행 수입니다.
- `merchant_usage`는 승인 거래가 있는 조합만 반환합니다. 업종별 합계에는 이 뷰의 금액을 합산하며,  
  `monthly_usage`와 두 뷰를 JOIN해서 합산하면 금액이 중복될 수 있습니다.
- `customer_daily_usage`는 기준일을 포함한 최근 90일 중 데이터 제공 시작일·가입일 이후 날짜를 반환합니다.  
  승인 거래가 없는 날도 0원·0건으로 보여 주며, 건별 거래는 노출하지 않습니다.
- `customer_delinquency_history`는 완료된 월만 반환합니다. 월중 기준일이면 이번 달 말 자료는 제외하며,  
  `overdue_count_12m`은 각 월의 지표이므로 여러 월 값을 더하지 않습니다.
- 데이터가 없는 연체 상태와 실제 연체액 0을 구분합니다.
- 정수 금액·합계는 JSON 숫자로, 소수 결과는 정밀도를 보존하는 문자열로 반환합니다.

SQL 검증기는 허용 논리 테이블과 컬럼을 대상으로 한 SELECT 한 개만 허용합니다.  
쓰기, 원본·private 스키마 접근, 서브쿼리, WITH, UNION, 잠금, 임의 함수 등은 실행 전에 차단합니다.  
일부 JOIN·GROUP BY·정렬·집계는 지원하며 최대 100행과 DB 실행시간 제한을 적용합니다.  
입력 회원·기준일은 세션 변수로 지정하고 PostgreSQL 읽기 전용 트랜잭션에서 실행합니다.  
모델이 만든 SQL에는 회원 조건이 들어가지 않습니다. 넣을 수도 없고, 넣지 않아도 범위가 좁혀집니다.

모델의 검색 계획 입력에는 질문·요청 기준일(`base_date`)·조회 모드·허용 스키마·고정 조회 설명을 보냅니다.  
실제 고객 행은 보내지 않습니다. 최근 N개월은 기준일이 속한 달을 포함하고, 지난달은 그 직전 달입니다.  
월중 기준일이면 해당 월은 기준일까지의 부분 집계입니다. 모델은 월 범위를 `YYYY-MM` 조건으로 작성합니다.  
확인용 설명을 켜면 조회 결과에서 원본 식별자 필드를 제거하고 대체 카드 참조를 사용합니다.  
질문에도 식별자·연락처·이메일 등 알려진 패턴을 제거합니다. 자유문장의 모든 개인정보를 판별하는 기능은 아닙니다.  
호출 측에서도 질문의 민감정보를 제거해야 합니다. 실행 중 LangSmith 외부 tracing은 비활성화합니다.

## 모델과 런타임 벤치마크 테스트 결과

아래 표는 새로 테스트하지 않고 이전에 저장한 `benchmark-*.json` 결과를 취합한 것입니다.  
`benchmark_llm.py`가 DB 조회와 결과 설명을 제외하고 LLM의 검색 계획 생성만 측정했습니다. 고정 조회 4개,  
NL2SQL 5개, 미지원 질문 3개를 각각 5회 실행했으므로 모델 또는 런타임마다 총 60개 결과가 있습니다.

### 테스트 PC와 실행 조건

| 항목 | 테스트 조건 |
|---|---|
| 운영체제 | Windows 11, 빌드 26200 |
| CPU | Intel Core i9-14900HX |
| 메모리 | 31.7GB(표기상 32GB) |
| GPU | NVIDIA GeForce RTX 4090 Laptop GPU, VRAM 16,376MiB |
| Python | 3.12.12 |
| Ollama | 0.40.0-rc0, 컨텍스트 4,096 |
| 로컬 모델 형식 | GGUF Q4 계열, 단일 요청 순차 실행 |
| vLLM 주요 설정 | `max-num-seqs=1`, `--enforce-eager`, GPU 메모리 사용률 설정 0.85 |

`warm` 측정은 모델을 처음 적재하는 첫 호출을 제외합니다. Ollama의 Gemma 모델은 측정 후 GPU 메모리를  
약 9,243MiB 사용했고, vLLM은 약 14,677MiB를 사용했습니다.

### 각 항목을 읽는 방법

| 항목 | 의미 |
|---|---|
| 전체 계획 | 경로 선택, 고정 조회 ID, SQL 안전성, 질문 의미를 모두 만족한 건수 |
| 고정 조회 | 질문과 일치하는 사전 정의 조회를 정확히 선택한 건수 |
| NL2SQL | NL2SQL 경로를 선택하고 안전성과 의미 검사를 통과한 SQL을 만든 건수 |
| 미지원 판정 | 제공 데이터로 답할 수 없는 질문을 실행하지 않고 거절한 건수 |
| warm P95 | 첫 적재를 제외한 호출 중 95%가 완료된 시간. 작을수록 응답이 빠름 |

### 모델별 비교

| 모델·실행 방식 | 전체 계획 | 고정 조회 | NL2SQL | 미지원 판정 | warm P95 |
|---|---:|---:|---:|---:|---:|
| Groq `openai/gpt-oss-120b` | **60/60** | 20/20 | **25/25** | 15/15 | **1.040초** |
| Gemma 4 12B + Ollama | **60/60** | 20/20 | **25/25** | 15/15 | 3.022초 |
| Qwen3.5 9B + Ollama | 45/60 | 20/20 | 10/25 | 15/15 | 2.240초 |

이 표는 각 모델의 마지막 저장 결과를 모은 것입니다. Groq는 평균 계산식을 보완한 현재 프롬프트, Gemma는  
그 직전 프롬프트, Qwen3.5는 튜닝 전 프롬프트로 측정했습니다. 따라서 운영 후보를 고르는 참고 자료로는 쓸 수  
있지만, 같은 프롬프트를 사용한 엄밀한 모델 비교는 아닙니다. Qwen3.5는 60회 중 55회만 호출에 성공했으며,  
호출 실패도 전체 계획 실패에 포함했습니다.

### Ollama와 vLLM 비교

다음 표는 같은 Gemma 4 12B 모델과 같은 프롬프트 SHA를 사용한 저장 결과입니다.

| Gemma 4 12B 런타임 | 전체 계획 | 고정 조회 | NL2SQL | 미지원 판정 | warm P95 |
|---|---:|---:|---:|---:|---:|
| Ollama | **60/60** | 20/20 | 25/25 | **15/15** | **3.022초** |
| vLLM | 55/60 | 20/20 | 25/25 | 10/15 | 9.882초 |

Ollama는 `function_calling`, vLLM은 `json_schema` 방식으로 구조화 결과를 받았습니다. 모델과 프롬프트는  
같지만 출력 제약 방식이 달라서 런타임 엔진만 완전히 분리한 비교는 아닙니다.

### Local LLM이 Groq보다 느린 이유

Groq 호출에는 네트워크 시간이 포함되지만, 원격 서비스는 모델 추론에 맞춘 데이터센터 가속기와 최적화된  
서빙 환경을 사용합니다. 로컬 모델은 노트북 GPU 한 장의 연산 성능, 메모리 대역폭, 전력과 발열 한도 안에서  
프롬프트 처리와 토큰 생성을 모두 수행합니다. 120B 모델인 Groq가 9B·12B 로컬 모델보다 빠른 이유는 모델  
크기보다 실행 하드웨어와 서빙 최적화가 응답 시간에 더 큰 영향을 주기 때문입니다.

PC 자원은 특히 vLLM 결과에 큰 영향을 준 것으로 보입니다. vLLM이 16,376MiB 중 약 14,677MiB를 사용해  
VRAM 여유가 약 1.7GB뿐이었습니다. 다만 Ollama의 Gemma는 약 9.2GB를 사용했고 모델 전체가 GPU에 적재됐기  
때문에, 모든 로컬 지연을 시스템 메모리 부족만으로 설명하기는 어렵습니다. 단일 노트북 GPU의 처리량과  
메모리 대역폭, 런타임별 최적화 차이도 함께 작용했습니다.

Qwen3.5는 Gemma보다 작아 더 빨랐지만 NL2SQL 정확도가 낮았습니다. 이 결과는 작은 모델이 지연시간에는  
유리할 수 있어도 복잡한 SQL 계획 품질까지 보장하지는 않는다는 점을 보여 줍니다.

### 이 PC에서 vLLM이 Ollama보다 느린 이유

vLLM은 여러 요청을 묶어 GPU 처리량을 높이는 서버 환경에 강점이 있습니다. 이번 시험은 요청을 하나씩 보내고  
`max-num-seqs=1`로 실행했기 때문에 배치 처리의 장점을 사용하지 못했습니다. `--enforce-eager` 설정으로 CUDA  
Graph 최적화도 사용하지 않았습니다.

같은 GGUF 모델을 실행할 때 Ollama의 llama.cpp 경로는 단일 요청에 비교적 가볍게 동작했습니다. 반면 vLLM은  
OpenAI 호환 서버와 JSON Schema 제약 처리 비용이 추가됐고 GPU 메모리도 약 5.4GB 더 사용했습니다. 이 PC에서는  
VRAM 여유 부족, 단일 요청 방식, vLLM 설정이 함께 영향을 준 것으로 판단합니다. 따라서 이 결과를 vLLM이 항상  
Ollama보다 느리다는 의미로 해석하면 안 됩니다. 동시 요청과 배치가 늘어나면 처리량 결과가 달라질 수 있습니다.

원본 결과는 `benchmark-results.json`, `benchmark-groq-prompt-results.json`, `benchmark-ollama-results.json`,  
`benchmark-vllm-groq-results.json`에서 확인할 수 있습니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

단위 검증은 모델·저장소를 대역으로 바꿔 외부 호출 없이 수행합니다.  
실제 PostgreSQL 통합 테스트는 `SQL_RETRIEVER_TEST_DSN`을 지정한 경우에만 실행합니다.  
실제 모델 검증은 CLI의 `--llm-provider`, `auto`·`nl2sql`·`--explain` 요청으로 구분해서 확인할 수 있습니다.  
모델은 지원하지 않는 질문을 거절하도록 요청받지만, 자연어의 의미를 항상 정확히 해석한다고 보장하지는 않습니다.  
반환 SQL과 검색 결과를 확인할 수 있도록 유지하고, 데이터 접근 경계는 모델 판단과 별도로 코드가 강제합니다.

2026-09-27 구현 시점의 실제 확인 결과입니다.

| 검증 | 결과 |
|---|---|
| 단위·프레젠테이션 시험 | 111개 통과, 실제 PostgreSQL 통합 시험 4개 건너뜀 |
| Groq 계획 재측정 | 60/60 호출 성공, 계획 60/60 일치, warm P50 720ms |
| API 키를 비운 고정 검색 | 카드 2개와 고객 현황 조회 성공, 설명 미호출 |
| Groq 자동 고정 조회 선택 | 보유 카드 질문을 `cards`로 선택하고 2행 반환 |
| Groq 자동 NL2SQL | 고객 전체 월별 승인 총액 질문에 집계 SQL을 생성하고 6개월 반환 |
| 강제 NL2SQL | 승인 총액 상위 2개월 조회 성공 |
| 선택적 Groq 설명 | 연체 조회 결과의 확인용 설명 생성 성공 |
| 실제 HTTP | `/health`·`/schema`·고정/자동 `/search` 200, 잘못된 입력 422 |

검증용 API 서버는 테스트 후 종료했습니다. 프로그램을 사용하려면 위 실행 명령으로 시작합니다.

참고한 공식 문서:  
[LangChain ChatGroq](https://docs.langchain.com/oss/python/integrations/chat/groq),  
[Groq GPT-OSS 120B](https://console.groq.com/docs/model/openai/gpt-oss-120b),  
[Ollama Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs),  
[Qwen3.5-9B 공식 모델](https://huggingface.co/Qwen/Qwen3.5-9B),  
[Qwen3.5-9B GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF),  
[Gemma 4 12B QAT 공식 모델](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-unquantized),  
[Gemma 4 12B QAT GGUF](https://huggingface.co/unsloth/gemma-4-12B-it-qat-GGUF).
