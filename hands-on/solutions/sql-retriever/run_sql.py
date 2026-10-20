"""정형 데이터 검색 CLI 진입점."""

import sys

from app.presentation.cli import main


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
