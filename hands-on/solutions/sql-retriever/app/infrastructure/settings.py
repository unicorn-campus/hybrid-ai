"""작업 디렉터리에 의존하지 않고 공통 .env를 읽습니다."""
from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
LAB_ROOT = ROOT.parents[1]
SECRETS_ENV = LAB_ROOT.parent / "secrets" / ".env"
MODEL = "openai/gpt-oss-120b"
GEMMA_MODEL = "hf.co/unsloth/gemma-4-12B-it-qat-GGUF:UD-Q4_K_XL"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
VLLM_BASE_URL = "http://127.0.0.1:8000/v1"
VLLM_MODEL = "gemma-4-12b-it"
VLLM_MAX_TOKENS = 1024
LLM_PROVIDERS = ("groq", "google_local")
LLM_RUNTIMES = ("ollama", "vllm")


@dataclass(frozen=True)
class Settings:
    db_dsn: str = field(repr=False)
    db_password: str = field(repr=False)
    api_key: str = field(repr=False)
    model: str = MODEL
    statement_timeout_ms: int = 5000
    llm_timeout_seconds: float = 30.0
    max_tokens: int = 2500
    llm_provider: str = "groq"
    gemma_model: str = GEMMA_MODEL
    ollama_base_url: str = OLLAMA_BASE_URL
    llm_runtime: str = "ollama"
    vllm_base_url: str = VLLM_BASE_URL
    vllm_model: str = VLLM_MODEL
    vllm_api_key: str = field(default="", repr=False)
    vllm_max_tokens: int = VLLM_MAX_TOKENS


def load_settings(env_path: Path | None = None) -> Settings:
    values = dotenv_values(env_path or SECRETS_ENV, interpolate=False)

    def get(key, default=""):
        return os.environ.get(key, values.get(key) or default)

    # DB 비밀번호는 secrets/.env(또는 같은 이름의 환경변수)에서만 읽음.
    dsn = (get("SQL_RETRIEVER_DB_DSN") or get("S22_DB_DSN")
           or "host=localhost port=5432 dbname=cardlab user=sql_retriever_user")
    password = get("SQL_RETRIEVER_DB_PASSWORD") or get("S22_DB_PASSWORD")
    try:
        timeout = int(get("SQL_RETRIEVER_STATEMENT_TIMEOUT_MS", "5000"))
        llm_timeout = float(get("SQL_RETRIEVER_LLM_TIMEOUT_SECONDS", "30"))
        tokens = int(get("SQL_RETRIEVER_MAX_TOKENS", "2500"))
        vllm_tokens = int(get("SQL_RETRIEVER_VLLM_MAX_TOKENS", str(VLLM_MAX_TOKENS)))
        if (not 100 <= timeout <= 60000 or not 1 <= llm_timeout <= 120
                or not 128 <= tokens <= 8192 or not 128 <= vllm_tokens <= 4096):
            raise ValueError()
    except ValueError as error:
        raise ValueError("SQL 검색기의 시간·토큰 제한 설정을 확인해 주세요.") from error
    provider = get("SQL_RETRIEVER_LLM_PROVIDER", "groq").lower()
    if provider not in LLM_PROVIDERS:
        raise ValueError("SQL_RETRIEVER_LLM_PROVIDER는 groq 또는 google_local이어야 합니다.")
    runtime = get("SQL_RETRIEVER_LLM_RUNTIME", "ollama").lower()
    if runtime not in LLM_RUNTIMES:
        raise ValueError("SQL_RETRIEVER_LLM_RUNTIME은 ollama 또는 vllm이어야 합니다.")
    return Settings(
        db_dsn=dsn,
        db_password=password,
        api_key=get("GROQ_API_KEY"),
        model=get("SQL_RETRIEVER_GROQ_MODEL", MODEL),
        statement_timeout_ms=timeout,
        llm_timeout_seconds=llm_timeout,
        max_tokens=tokens,
        llm_provider=provider,
        gemma_model=get("SQL_RETRIEVER_GEMMA_MODEL", GEMMA_MODEL),
        ollama_base_url=get("SQL_RETRIEVER_OLLAMA_BASE_URL", OLLAMA_BASE_URL),
        llm_runtime=runtime,
        vllm_base_url=get("SQL_RETRIEVER_VLLM_BASE_URL", VLLM_BASE_URL),
        vllm_model=get("SQL_RETRIEVER_VLLM_MODEL", VLLM_MODEL),
        vllm_api_key=get("SQL_RETRIEVER_VLLM_API_KEY"),
        vllm_max_tokens=vllm_tokens,
    )
