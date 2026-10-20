"""계층별 어댑터를 조립하는 유일한 구성 지점."""
from app.application.search_service import SearchService
from app.infrastructure.groq_gateway import GroqGateway
from app.infrastructure.ollama_gateway import OllamaGateway
from app.infrastructure.postgres_repository import PostgresRepository
from app.infrastructure.settings import Settings, load_settings
from app.infrastructure.sql_guard import LOGICAL_SCHEMA, validate_sql
from app.infrastructure.vllm_gateway import VllmGateway


def create_language_model(
    settings: Settings,
    provider: str | None = None,
    runtime: str | None = None,
):
    selected_provider = (provider or settings.llm_provider).lower()
    selected_runtime = (runtime or settings.llm_runtime).lower()
    if selected_provider == "groq":
        return GroqGateway(settings)
    if selected_provider == "google_local":
        if selected_runtime == "vllm":
            return VllmGateway(
                settings.vllm_base_url,
                settings.vllm_model,
                settings.vllm_api_key,
                settings.llm_timeout_seconds,
                settings.vllm_max_tokens,
            )
        if selected_runtime != "ollama":
            raise ValueError("LLM runtime은 ollama 또는 vllm이어야 합니다.")
        return OllamaGateway(
            settings.ollama_base_url,
            settings.gemma_model,
            settings.llm_timeout_seconds,
            settings.max_tokens,
            structured_methods=("function_calling", "json_schema", "json_mode"),
        )
    raise ValueError("LLM provider는 groq 또는 google_local이어야 합니다.")


def create_service(provider: str | None = None, runtime: str | None = None) -> SearchService:
    settings = load_settings()
    repository = PostgresRepository(settings.db_dsn, settings.db_password,
                                    statement_timeout_ms=settings.statement_timeout_ms)
    return SearchService(
        repository,
        create_language_model(settings, provider, runtime),
        validate_sql,
        LOGICAL_SCHEMA,
    )
