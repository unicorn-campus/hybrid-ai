import pytest

from app.bootstrap import create_language_model
from app.infrastructure.groq_gateway import GroqGateway
from app.infrastructure.ollama_gateway import OllamaGateway
from app.infrastructure.settings import Settings
from app.infrastructure.vllm_gateway import VllmGateway


def settings(provider="groq"):
    return Settings(
        "host=localhost dbname=test",
        "password",
        "groq-key",
        llm_provider=provider,
        gemma_model="gemma4:test",
        ollama_base_url="http://localhost:11434",
        vllm_base_url="http://localhost:8000/v1",
        vllm_model="gemma-vllm:test",
        vllm_api_key="vllm-key",
        vllm_max_tokens=1024,
    )


def test_language_model_uses_configured_provider():
    assert isinstance(create_language_model(settings("groq")), GroqGateway)
    local = create_language_model(settings("google_local"))
    assert isinstance(local, OllamaGateway)
    assert local.model == "gemma4:test"
    assert local.endpoint == "http://localhost:11434"
    assert local.structured_methods[0] == "function_calling"

def test_explicit_provider_overrides_settings():
    assert isinstance(create_language_model(settings("groq"), "google_local"), OllamaGateway)


def test_google_local_model_can_use_vllm_runtime():
    local = create_language_model(settings("google_local"), runtime="vllm")
    assert isinstance(local, VllmGateway)
    assert local.model == "gemma-vllm:test"
    assert local.endpoint == "http://localhost:8000/v1"


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="groq 또는 google_local"):
        create_language_model(settings(), "unknown")
