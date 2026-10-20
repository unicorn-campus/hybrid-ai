"""정형 데이터 검색을 HTTP로 여는 얇은 FastAPI 표현 계층입니다."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.application.models import SearchError, SearchRequest, SearchResponse


def create_app(service=None) -> FastAPI:
    app = FastAPI(title="SQL Retriever", version="1.0.0")
    cached_service = service

    def get_service():
        nonlocal cached_service
        if cached_service is None:
            from app.bootstrap import create_service

            cached_service = create_service()
        return cached_service

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        details = [
            {key: value for key, value in item.items() if key in {"type", "loc", "msg"}}
            for item in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_request", "message": "요청 형식을 확인해 주세요."},
                     "details": details},
        )

    @app.exception_handler(SearchError)
    async def search_error_handler(_request: Request, error: SearchError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, _error: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid_request", "message": "검색 조건을 확인해 주세요."}},
        )

    @app.exception_handler(RuntimeError)
    async def runtime_error_handler(_request: Request, _error: RuntimeError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "service_unavailable",
                               "message": "정형 데이터 검색 서비스를 사용할 수 없습니다."}},
        )

    @app.get("/health")
    def health() -> dict:
        return {"status": "live", "database": "not_checked", "llm": "not_checked"}

    @app.get("/schema")
    def schema() -> dict:
        return get_service().schema()

    @app.post("/search", response_model=SearchResponse)
    def search(request: SearchRequest) -> SearchResponse:
        return get_service().execute(request)

    return app


app = create_app()
