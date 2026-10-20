"""CLI 입력을 응용 계층의 검색 계약으로 변환합니다."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from pydantic import ValidationError

from app.application.models import SearchError, SearchRequest
from app.infrastructure.settings import LLM_PROVIDERS, LLM_RUNTIMES


class _ParserExit(Exception):
    def __init__(self, status: int, message: str | None = None):
        self.status = status
        self.message = message


class _ArgumentParser(argparse.ArgumentParser):
    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise _ParserExit(status, message)

    def error(self, message: str) -> None:
        raise _ParserExit(2, message)


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(description="고객 정형 데이터 검색 CLI")
    parser.add_argument("--schema", action="store_true", help="지원 스키마와 고정 조회 목록 출력")
    parser.add_argument(
        "--llm-provider",
        choices=LLM_PROVIDERS,
        help="LLM 제공자(기본값: groq, .env의 SQL_RETRIEVER_LLM_PROVIDER보다 우선)",
    )
    parser.add_argument(
        "--llm-runtime",
        choices=LLM_RUNTIMES,
        help="로컬 Gemma 실행 런타임(기본값: ollama, .env 설정보다 우선)",
    )
    parser.add_argument(
        "--query-mode",
        choices=("auto", "fixed", "nl2sql"),
        default="auto",
        help="검색 방식(기본값: auto)",
    )
    parser.add_argument(
        "--query-id",
        choices=("customer_snapshot", "cards", "monthly_usage", "delinquency"),
        help="fixed 모드에서 실행할 고정 조회",
    )
    parser.add_argument("--member-id", help="조회할 회원ID(M-숫자)")
    parser.add_argument("--base-date", help="조회 기준일(YYYY-MM-DD)")
    parser.add_argument("--question", help="auto 또는 nl2sql 검색 질문")
    parser.add_argument("--explain", action="store_true", help="검색 결과에 확인용 LLM 설명 추가")
    return parser


def _write_json(stream: TextIO, value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str), file=stream)


def _safe_error(stream: TextIO, code: str, message: str) -> None:
    _write_json(stream, {"error": {"code": code, "message": message}})


def _resolve_service(service, provider: str | None = None, runtime: str | None = None):
    if service is not None:
        return service
    from app.bootstrap import create_service

    return create_service(provider, runtime)


def main(
    argv: Sequence[str] | None = None,
    service=None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """CLI를 실행하고 프로세스 종료 코드를 반환합니다."""
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except _ParserExit as error:
        if error.message:
            _safe_error(errors, "invalid_arguments", "명령행 인자를 확인해 주세요.")
        return error.status

    try:
        application = _resolve_service(service, args.llm_provider, args.llm_runtime)
        if args.schema:
            _write_json(output, application.schema())
            return 0
        if not args.member_id or not args.base_date:
            _safe_error(errors, "invalid_arguments", "--member-id와 --base-date가 필요합니다.")
            return 2
        request = SearchRequest(
            query_mode=args.query_mode,
            query_id=args.query_id,
            member_id=args.member_id,
            base_date=args.base_date,
            question=args.question,
            explain=args.explain,
        )
        response = application.execute(request)
        payload = response.model_dump(mode="json") if hasattr(response, "model_dump") else response
        _write_json(output, payload)
        return 0
    except ValidationError:
        _safe_error(errors, "invalid_request", "검색 조건의 형식과 필수 항목을 확인해 주세요.")
        return 2
    except SearchError as error:
        _safe_error(errors, error.code, error.message)
        return 1
    except (ValueError, RuntimeError, OSError, ImportError):
        _safe_error(errors, "search_unavailable", "정형 데이터 검색을 실행할 수 없습니다.")
        return 1

