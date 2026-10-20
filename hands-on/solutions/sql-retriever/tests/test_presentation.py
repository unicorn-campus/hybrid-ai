"""CLI와 API가 동일한 검색 계약을 노출하는지 검증합니다."""

from __future__ import annotations

import io
import json
from datetime import date

from fastapi.testclient import TestClient

from app.application.models import SearchError, SearchResponse
from app.presentation.api import create_app
from app.presentation.cli import main


class FakeService:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.requests = []

    def schema(self):
        return {"query_modes": ["auto", "fixed", "nl2sql"],
                "fixed_queries": [{"query_id": "customer_snapshot"}], "tables": {}}

    def execute(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        actual_mode = "fixed" if request.query_mode in ("auto", "fixed") else "nl2sql"
        return SearchResponse(
            query_mode=actual_mode,
            requested_query_mode=request.query_mode,
            query_id="customer_snapshot" if actual_mode == "fixed" else None,
            routing_reason="고정 조회로 충분합니다.",
            member_id=request.member_id,
            base_date=request.base_date,
            data={"customer": {"member_ref": "member-1"}},
        )


def valid_body(**overrides):
    body = {
        "query_mode": "auto",
        "member_id": "M-1042",
        "base_date": "2026-08-31",
        "question": "고객 현황을 조회해 주세요.",
    }
    body.update(overrides)
    return body


def test_api_health_does_not_create_service_or_check_dependencies():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "live", "database": "not_checked", "llm": "not_checked"}


def test_api_schema_uses_injected_service():
    client = TestClient(create_app(FakeService()))
    response = client.get("/schema")
    assert response.status_code == 200
    assert response.json()["query_modes"] == ["auto", "fixed", "nl2sql"]


def test_api_search_passes_validated_contract_to_service():
    service = FakeService()
    response = TestClient(create_app(service)).post("/search", json=valid_body())
    assert response.status_code == 200
    assert response.json()["requested_query_mode"] == "auto"
    assert service.requests[0].base_date == date(2026, 8, 31)


def test_api_validation_does_not_reflect_question_input():
    secret_question = "노출되면 안 되는 상담 질문"
    response = TestClient(create_app(FakeService())).post(
        "/search", json=valid_body(member_id="invalid", question=secret_question)
    )
    assert response.status_code == 422
    assert secret_question not in response.text
    assert "input" not in response.text


def test_api_maps_search_error_status_and_hides_runtime_details():
    expected = TestClient(create_app(FakeService(SearchError("unsafe_sql", "조회 규칙 위반", 422))))
    response = expected.post("/search", json=valid_body())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsafe_sql"

    runtime = TestClient(create_app(FakeService(RuntimeError("password=do-not-leak"))),
                         raise_server_exceptions=False)
    response = runtime.post("/search", json=valid_body())
    assert response.status_code == 503
    assert "do-not-leak" not in response.text


def test_cli_schema_does_not_require_search_arguments():
    stdout, stderr = io.StringIO(), io.StringIO()
    code = main(["--schema"], FakeService(), stdout=stdout, stderr=stderr)
    assert code == 0
    assert json.loads(stdout.getvalue())["fixed_queries"]
    assert stderr.getvalue() == ""


def test_cli_and_api_use_same_auto_request_contract():
    service = FakeService()
    stdout, stderr = io.StringIO(), io.StringIO()
    code = main(
        ["--query-mode", "auto", "--member-id", "M-1042", "--base-date", "2026-08-31",
         "--question", "고객 현황을 조회해 주세요."],
        service,
        stdout=stdout,
        stderr=stderr,
    )
    assert code == 0
    assert json.loads(stdout.getvalue())["query_mode"] == "fixed"
    assert service.requests[0].query_mode == "auto"
    assert stderr.getvalue() == ""


def test_cli_reports_sanitized_usage_and_service_errors():
    stdout, stderr = io.StringIO(), io.StringIO()
    assert main(["--query-mode", "nl2sql"], FakeService(), stdout=stdout, stderr=stderr) == 2
    assert "--member-id" in stderr.getvalue()

    stdout, stderr = io.StringIO(), io.StringIO()
    service = FakeService(RuntimeError("postgresql://user:secret@host/db"))
    code = main(
        ["--query-mode", "fixed", "--member-id", "M-1042", "--base-date", "2026-08-31"],
        service,
        stdout=stdout,
        stderr=stderr,
    )
    assert code == 1
    assert "secret" not in stderr.getvalue()


def test_cli_llm_provider_is_forwarded_to_bootstrap(monkeypatch):
    selected = []

    def create_service(provider=None, runtime=None):
        selected.append((provider, runtime))
        return FakeService()

    monkeypatch.setattr("app.bootstrap.create_service", create_service)
    stdout, stderr = io.StringIO(), io.StringIO()
    code = main(
        ["--llm-provider", "google_local", "--llm-runtime", "vllm", "--query-mode", "fixed",
         "--member-id", "M-1042", "--base-date", "2026-08-31"],
        stdout=stdout,
        stderr=stderr,
    )
    assert code == 0
    assert selected == [("google_local", "vllm")]
    assert stderr.getvalue() == ""

