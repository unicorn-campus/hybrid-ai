import os

import serve_sql


def test_server_accepts_provider_and_runtime_and_sets_environment(monkeypatch):
    calls = []
    monkeypatch.delenv("SQL_RETRIEVER_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SQL_RETRIEVER_LLM_RUNTIME", raising=False)
    monkeypatch.setattr(serve_sql.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    result = serve_sql.main([
        "--port", "8013", "--llm-provider", "google_local", "--llm-runtime", "vllm",
    ])

    assert result == 0
    assert os.environ["SQL_RETRIEVER_LLM_PROVIDER"] == "google_local"
    assert os.environ["SQL_RETRIEVER_LLM_RUNTIME"] == "vllm"
    assert calls == [(('app.presentation.api:app',), {"host": "127.0.0.1", "port": 8013})]
