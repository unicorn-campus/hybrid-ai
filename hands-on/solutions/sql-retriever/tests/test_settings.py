from pathlib import Path

import pytest

from app.infrastructure.settings import SECRETS_ENV, load_settings


def test_common_env_path_is_independent_of_working_directory():
    assert SECRETS_ENV.is_absolute()
    assert SECRETS_ENV.parts[-2:] == ("secrets", ".env")


def test_db_password_is_read_only_from_env_file(tmp_path, monkeypatch):
    for key in ("SQL_RETRIEVER_DB_DSN", "S22_DB_DSN", "SQL_RETRIEVER_DB_PASSWORD", "S22_DB_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text("SQL_RETRIEVER_DB_PASSWORD=db-secret\n", encoding="utf-8")
    assert load_settings(env).db_password == "db-secret"
    # 비밀번호가 .env에 없으면 다른 파일에서 찾지 않고 빈 값으로 둠.
    assert load_settings(tmp_path / "missing.env").db_password == ""


def test_settings_does_not_expose_secrets_and_env_has_precedence(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("GROQ_API_KEY=file-secret\nSQL_RETRIEVER_DB_PASSWORD=db-secret\n", encoding="utf-8")
    monkeypatch.setenv("GROQ_API_KEY", "runtime-secret")
    monkeypatch.delenv("SQL_RETRIEVER_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SQL_RETRIEVER_LLM_RUNTIME", raising=False)
    settings = load_settings(env)
    assert settings.api_key == "runtime-secret"
    assert "secret" not in repr(settings)
    assert settings.model == "openai/gpt-oss-120b"
    assert settings.llm_provider == "groq"
    assert settings.gemma_model == "hf.co/unsloth/gemma-4-12B-it-qat-GGUF:UD-Q4_K_XL"
    assert settings.llm_runtime == "ollama"
    assert settings.vllm_model == "gemma-4-12b-it"
    assert settings.vllm_api_key == ""
    assert settings.vllm_max_tokens == 1024


def test_missing_key_does_not_block_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    settings = load_settings(tmp_path / "missing.env")
    assert settings.api_key == ""


def test_llm_provider_and_gemma_settings_can_be_selected(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "SQL_RETRIEVER_LLM_PROVIDER=google_local\n"
        "SQL_RETRIEVER_GEMMA_MODEL=gemma4:custom\n"
        "SQL_RETRIEVER_OLLAMA_BASE_URL=http://localhost:11434\n"
        "SQL_RETRIEVER_LLM_RUNTIME=vllm\n"
        "SQL_RETRIEVER_VLLM_BASE_URL=http://localhost:8000/v1\n"
        "SQL_RETRIEVER_VLLM_MODEL=gemma-vllm:test\n"
        "SQL_RETRIEVER_VLLM_API_KEY=local-secret\n"
        "SQL_RETRIEVER_VLLM_MAX_TOKENS=768\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SQL_RETRIEVER_LLM_PROVIDER", raising=False)
    settings = load_settings(env)
    assert settings.llm_provider == "google_local"
    assert settings.gemma_model == "gemma4:custom"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.llm_runtime == "vllm"
    assert settings.vllm_base_url == "http://localhost:8000/v1"
    assert settings.vllm_model == "gemma-vllm:test"
    assert settings.vllm_api_key == "local-secret"
    assert settings.vllm_max_tokens == 768
    assert "local-secret" not in repr(settings)


def test_unknown_llm_provider_is_rejected(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SQL_RETRIEVER_LLM_PROVIDER=unknown\n", encoding="utf-8")
    monkeypatch.delenv("SQL_RETRIEVER_LLM_PROVIDER", raising=False)
    with pytest.raises(ValueError, match="groq 또는 google_local"):
        load_settings(env)


def test_unknown_llm_runtime_is_rejected(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SQL_RETRIEVER_LLM_RUNTIME=unknown\n", encoding="utf-8")
    monkeypatch.delenv("SQL_RETRIEVER_LLM_RUNTIME", raising=False)
    with pytest.raises(ValueError, match="ollama 또는 vllm"):
        load_settings(env)
