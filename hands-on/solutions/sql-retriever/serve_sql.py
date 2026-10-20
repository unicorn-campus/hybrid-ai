"""로컬 FastAPI 서버 진입점."""

from __future__ import annotations

import argparse
import os

import uvicorn
from dotenv import dotenv_values

from app.infrastructure.settings import LLM_PROVIDERS, LLM_RUNTIMES, SECRETS_ENV


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SQL Retriever API 서버")
    values = dotenv_values(SECRETS_ENV, interpolate=False)
    default_port = os.getenv("SQL_RETRIEVER_PORT") or values.get("SQL_RETRIEVER_PORT") or "8012"
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument(
        "--llm-provider",
        choices=LLM_PROVIDERS,
        help="LLM 실행 위치(.env의 SQL_RETRIEVER_LLM_PROVIDER보다 우선)",
    )
    parser.add_argument(
        "--llm-runtime",
        choices=LLM_RUNTIMES,
        help="로컬 Gemma 실행 런타임(.env의 SQL_RETRIEVER_LLM_RUNTIME보다 우선)",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("포트는 1~65535 범위여야 합니다.")
    if args.llm_provider:
        os.environ["SQL_RETRIEVER_LLM_PROVIDER"] = args.llm_provider
    if args.llm_runtime:
        os.environ["SQL_RETRIEVER_LLM_RUNTIME"] = args.llm_runtime
    uvicorn.run("app.presentation.api:app", host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
