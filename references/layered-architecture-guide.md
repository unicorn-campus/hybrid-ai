# 파이썬 Layered Architecture 개발 가이드 (DIP 적용)

## 0. 적용 범위
- 적용 대상: 파이썬으로 작성하는 모든 앱·서비스·에이전트 코드(API 서버, CLI, 인덱서, 리트리버, LangGraph 워크플로우 등)
- 제외 대상: 1회성 스크립트, 노트북 실습, 50줄 이하 단일 파일 예제
- 근거 자료: 「신한카드 하이브리드AI_W01 ~ W04」 94 ~ 98쪽 '파이썬 적용 가이드'
- 참고 구현: `hybrid-ai-lab/retriever/sql-retriever`(덕 타이핑 방식), `hybrid-ai-lab/retriever/vector-retriever`(명시적 상속 방식)

## 1. 한 줄 원칙
**업무 규칙(비즈니스 계층)이 인터페이스를 정하고, 기술(DB·LLM·API)은 그 인터페이스를 따라 만듦**

### 1.1 왜 필요한가
- 기존 Layered: 비즈니스 계층이 DB·LLM 라이브러리를 직접 import함  
  → LLM을 Groq에서 Ollama로 바꾸거나 테스트하려면 비즈니스 코드까지 고쳐야 함
- DIP 적용 Layered: 비즈니스 계층이 "이런 기능이 필요함"이라는 약속(포트)을 먼저 정의함  
  → 인프라 계층이 그 약속을 구현하므로 의존 방향이 뒤집힘  
  → 기술 교체는 조립 지점 한 곳만, 테스트는 가짜 구현체로 DB·LLM 없이 가능

### 1.2 용어 풀이
| 용어 | 쉬운 뜻 |
|------|---------|
| DIP(의존성 역전 원칙) | 윗단(업무 규칙)이 아랫단(기술)에 끌려가지 않고, 둘 다 가운데 약속(인터페이스)을 바라보게 하는 원칙 |
| 포트(Port) | 비즈니스 계층이 "이런 입력을 주면 이런 결과를 돌려 달라"고 정한 약속. 파이썬에서는 `Protocol` 클래스 |
| 어댑터(Adapter)·구현체 | 포트 약속을 실제 기술(psycopg, ChatOllama 등)로 지키는 클래스. Repository·Gateway 등 |
| DTO | 계층 사이를 오가는 요청·응답 데이터 묶음(pydantic 모델 등) |
| 조립 지점(bootstrap) | 어떤 구현체를 만들어 어디에 끼울지 결정하는 유일한 파일 |
| 주입(Injection) | 서비스가 구현체를 직접 만들지 않고, 생성자 인자로 받아 쓰는 방식 |

## 2. 반드시 지킬 규칙 3가지
1. **인터페이스는 쓰는 쪽이 소유함**: 포트는 `application/ports.py`에 둠. `infrastructure/`에 두지 않음
2. **구현체 생성·주입은 한 곳에서만 함**: `app/bootstrap.py`만 구현체를 생성함. 서비스·API 안에서 직접 생성 금지
3. **import는 바깥에서 안쪽 방향으로만 함**: presentation·infrastructure → application → domain

- 허용 예외: 공용 데이터 모델(예: LangChain `Document`)은 domain·application에서도 import 허용  
  단, 데이터 모델만 허용이며 체인·모델·클라이언트 같은 실행 객체는 허용하지 않음

## 3. 표준 패키지 구조
```
app/
├─ domain/            순수 업무 규칙, 외부 의존 없음
├─ application/
│  ├─ models.py       요청 · 응답 · 오류 모델(DTO)
│  ├─ ports.py        인터페이스(Protocol)
│  └─ services.py     비즈니스 흐름 (예: search_service.py)
├─ infrastructure/    포트 구현(DB·LLM·API·벡터DB·LangGraph 실행기·설정 로딩)
├─ presentation/      FastAPI·CLI 진입점
└─ bootstrap.py       조립 지점
tests/                가짜 구현체로 검증
```
- 파일이 커지면 계층 폴더 안에서 파일을 나눔(예: `application/state.py`, `application/errors.py`)  
  계층 폴더 자체를 새로 만들지는 않음
- 실행 진입 스크립트(`run_*.py`, `serve_*.py`)는 프로젝트 루트에 두고 presentation 또는 bootstrap만 호출함

## 4. 계층별 역할과 import 규칙
| 계층 | 두는 것 | import 가능 | import 금지 |
|------|---------|-------------|-------------|
| Domain | 도메인 모델(엔티티, VO), 도메인 규칙(순수 함수) | 표준 라이브러리, 공용 데이터 모델(Document) | app 내부 모든 계층, 외부 기술 |
| Application | DTO · 포트 · 서비스 | domain | infrastructure, presentation, 외부 기술(최소화) |
| Infrastructure | Repository · Gateway 구현체, 설정 로딩 | application(DTO·포트), domain, 외부 라이브러리 | presentation |
| Presentation | API·CLI, 요청 변환, 오류 응답 | application(DTO·서비스) | infrastructure 구현체 |
| bootstrap.py | 구현체 생성과 주입 | 모든 계층 | - |

- Application의 "외부 기술 최소화" 기준: pydantic 등 데이터 검증 라이브러리는 허용  
  psycopg·langchain_*·langgraph·httpx·chromadb 등 실행 기술은 금지

## 5. 계층별 작성 방법

### 5.1 Domain — 순수 규칙
- 업무 규칙은 순수 함수 또는 불변 값 객체로 작성함
- 입출력·네트워크·파일 접근을 하지 않음. 같은 입력이면 항상 같은 결과를 냄
```python
# domain/customer.py
from datetime import date, timedelta
import re                                   # ◀ 표준 라이브러리만

MEMBER_ID_PATTERN = re.compile(r"^M-[0-9]{1,20}$")

def validate_member_id(member_id: str) -> str:
    if not isinstance(member_id, str) or not MEMBER_ID_PATTERN.fullmatch(member_id):
        raise ValueError("회원ID 형식이 올바르지 않습니다.")
    return member_id
```

### 5.2 Application — DTO(models.py)
- 계층 사이를 오가는 요청 · 응답 · 오류 구조는 application 계층에서 정의함
- 계층 공통 오류 클래스를 하나 두고, 오류 코드·메시지·HTTP 상태를 함께 담음
```python
# application/models.py
from pydantic import BaseModel, Field

class SearchError(Exception):                 # ◀ 계층 공통 오류
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code

class SearchRequest(BaseModel):               # ◀ 입력 계약
    member_id: str = Field(pattern=r"^M-[0-9]{1,20}$", max_length=22)
```

### 5.3 Application — 포트(ports.py)
- 포트는 `typing.Protocol`로 정의하고 모든 메서드에 `@abstractmethod`를 붙임
- 메서드 인자·반환 타입은 DTO·domain 타입 또는 표준 타입만 사용함(외부 SDK 타입 금지)
- 포트 이름은 `{역할}Port` 형식(예: `RepositoryPort`, `LanguageModelPort`, `BM25Port`)
```python
# application/ports.py
from abc import abstractmethod
from typing import Protocol

class BM25Port(Protocol):
    @abstractmethod                                  # ◀ 추상 메서드 표시
    def keyword_search(self, query: str, *,
                       allowed_access_levels: frozenset[str] | None = None,
                       k: int) -> dict[str, float]: ...
```

### 5.4 Application — 서비스(services.py)
- 생성자는 구현체가 아닌 **포트 타입**을 인자로 받음
- 서비스 안에서 구현체를 생성하지 않음. 외부 기술 import도 하지 않음
```python
# application/search_service.py
from app.domain.privacy import redact_text, safe_context
from .ports import LanguageModelPort, RepositoryPort     # ◀ 포트만

class SearchService:
    def __init__(self, repository: RepositoryPort, llm: LanguageModelPort,
                 sql_validator: Callable[[str], str], logical_schema: dict):
        self.repository, self.llm = repository, llm

    def _retrieve(self, state):
        data = self.repository.search(          # ◀ 포트 메서드 호출
            request.member_id, request.base_date, validated_sql)
```

### 5.5 Infrastructure — 어댑터
- 외부 라이브러리 import는 **이 계층에만** 둠
- 실제 어댑터는 포트를 명시적으로 상속함(§6 권장 조합)
- SDK 생성 함수(`model_factory`)도 생성자 인자로 받아, 가짜 모델로 단위 테스트 가능하게 함
- 같은 포트를 여러 기술로 구현 가능(예: `GroqGateway`, `OllamaGateway`, `VllmGateway` → `LanguageModelPort`)
```python
# infrastructure/groq_gateway.py
from langchain_groq import ChatGroq                  # ◀ SDK는 여기서만
from ..application.ports import LanguageModelPort

class GroqGateway(LanguageModelPort):                # ◀ 명시적 상속
    def __init__(self, settings: Settings, model_factory=ChatGroq):
        self.settings, self.model_factory = settings, model_factory

    def plan(self, question: str, schema: dict, catalog: list[dict], mode: str,
             *, base_date: date) -> QueryPlan:
        model = self._model().with_structured_output(
            QueryPlan, method="json_schema", include_raw=True, strict=True)
        result = (prompt | model).invoke({"request": payload})
```
- LangGraph 워크플로우도 기술이므로 infrastructure에 둠  
  application에 실행 포트(예: `RetrieverGraphPort`)를 정의하고, `infrastructure/graph.py`가 `StateGraph`로 구현함  
  (참고: `vector-retriever/app/infrastructure/graph.py`)
- 환경변수·`.env`를 읽는 설정 로더(`settings.py`)도 infrastructure에 둠. 비밀값은 코드에 박지 않음

### 5.6 Presentation — 진입점
- 서비스를 인자로 받을 수 있게 열어 둠. 값이 없을 때만 bootstrap으로 조립함
- 경로 함수 안에는 요청 변환·서비스 호출·오류 응답만 둠. 업무 판단을 넣지 않음
```python
# presentation/api.py
def create_app(service=None) -> FastAPI:
    app = FastAPI(title="SQL Retriever", version="1.0.0")
    cached_service = service                        # ◀ 주입된 서비스 우선

    def get_service():
        nonlocal cached_service
        if cached_service is None:
            from app.bootstrap import create_service  # ◀ 없을 때만 조립(지연 import)
            cached_service = create_service()
        return cached_service

    @app.post("/search", response_model=SearchResponse)
    def search(request: SearchRequest) -> SearchResponse:
        return get_service().execute(request)
```

### 5.7 bootstrap.py — 조립 지점
- 구현체 선택·생성은 이곳에만 둠. 기술을 바꿀 때 이 파일만 수정함
- 설정값(provider 등)으로 구현체를 고름
- 순서: 설정 로딩 → 구현체 생성 → 서비스 조립
```python
# app/bootstrap.py
def create_language_model(settings: Settings, provider: str | None = None):
    if selected_provider == "groq":
        return GroqGateway(settings)                    # ◀ 설정으로 구현체 선택
    return OllamaGateway(settings.ollama_base_url, settings.gemma_model, ...)

def create_service(provider: str | None = None) -> SearchService:
    settings = load_settings()
    repository = PostgresRepository(settings.db_dsn, settings.db_password, ...)
    return SearchService(repository, create_language_model(settings, provider),
                         validate_sql, LOGICAL_SCHEMA)
```

### 5.8 tests — 가짜 주입 검증
- 서비스 테스트: 포트 모양의 가짜를 주입해 업무 규칙만 검증함
- 표현 계층 테스트: 가짜 서비스를 `create_app(service)`에 주입해 DB·LLM 없이 검증함
- 가짜는 호출 기록(`calls`)을 남겨 "LLM을 부르지 않았는지" 같은 행위까지 확인함
```python
# tests/test_search_service.py
class Repository:                                  # ◀ RepositoryPort 모양의 가짜
    def __init__(self):
        self.calls = []
    def search(self, member_id, base_date, validated_sql):
        self.calls.append(("search", member_id, base_date, validated_sql))

def test_fixed_default_never_calls_llm():
    engine, repository, model = service()
    engine.execute(request())
    assert model.plan_calls == model.explain_calls == []

# tests/test_presentation.py
def test_api_search_passes_validated_contract_to_service():
    service = FakeService()
    response = TestClient(create_app(service)).post("/search", json=valid_body())
    assert response.status_code == 200
```

## 6. 포트 구현 방식: 덕 타이핑 vs 명시적 상속
| 항목 | 덕 타이핑 | 명시적 상속 (Protocol + @abstractmethod) |
|------|-----------|------------------------------------------|
| 구현 선언 | 선언 없음. 메서드 모양이 같으면 포트로 봄 | 구현체가 포트를 상속해서 구현한다고 선언 |
| 장점 | 구현체가 포트를 import하지 않아 느슨한 결합 | 포트와 구현체 관계가 코드에 드러남 |
| 구현 관계 파악 | 코드에 드러나지 않음 | 클래스 선언만 보면 바로 알 수 있음 |
| 빠진 메서드 발견 | 타입 검사기가 미리 발견 | 객체를 만드는 순간 TypeError |
| 외부 클래스 활용 | 수정 없이 끼워 넣기 가능 | 포트를 상속한 어댑터 클래스 필요 |

### 6.1 권장 조합 (본 팀 표준)
- 포트: `Protocol` + `@abstractmethod`
- 실제 어댑터: 포트를 명시적 상속
- 테스트 가짜: 상속 없이 모양만 맞춤(덕 타이핑)
- CI: mypy 또는 pyright로 정적 타입 검사

### 6.2 주의
- `@abstractmethod` 없이 Protocol을 상속하면, 구현을 빠뜨린 메서드가 **오류 없이 `None`을 반환함**  
  (Python 3.13.13에서 실행 확인, 2026-09-30)
- 따라서 포트를 상속하는 경우 `@abstractmethod`를 반드시 함께 붙임

## 7. DIP 위반 신호 (코드 리뷰 체크리스트)
아래 중 하나라도 보이면 DIP 위반이므로 수정 후 완료 처리함
- [ ] 서비스(application) 파일에 psycopg · langchain_* · langgraph 같은 외부 기술 import가 있음
- [ ] 서비스 안에서 `PostgresRepository()`처럼 구현체를 직접 생성함
- [ ] 포트(인터페이스)가 `infrastructure/` 폴더에 있음
- [ ] presentation이 infrastructure 구현체를 직접 import함(bootstrap 경유가 아님)
- [ ] domain이 app 내부 다른 계층이나 외부 기술을 import함
- [ ] 포트 메서드에 `@abstractmethod`가 빠져 있음
- [ ] 서비스를 테스트하려면 실제 DB·API가 필요함

### 7.1 자동 점검 명령 (선택)
application·domain의 금지 import를 빠르게 찾는 명령
```bash
grep -rnE "^(from|import) (psycopg|langchain|langgraph|httpx|requests|chromadb|openai|groq)" app/application app/domain
```
```bash
grep -rn "infrastructure" app/presentation app/application app/domain
```
- 두 명령 모두 결과가 없어야 통과. 계층 규칙을 강제하려면 `import-linter` 도입을 검토함

## 8. 개발 절차 요약
1. domain: 업무 규칙을 순수 함수로 작성하고 단위 테스트함
2. application: DTO → 포트 → 서비스 순으로 작성하고, 가짜 포트로 서비스 테스트함
3. infrastructure: 포트를 상속한 어댑터를 작성하고, SDK 생성 함수를 주입해 가짜 모델로 테스트함
4. presentation: `create_app(service=None)` 형태로 작성하고, 가짜 서비스로 테스트함
5. bootstrap: 설정으로 구현체를 골라 조립함
6. 점검: §7 체크리스트와 자동 점검 명령, mypy·pyright 실행
