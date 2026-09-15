"""Central application configuration.

All secrets and environment-specific values arrive via environment variables
(see .env.example). Nothing secret is ever hard-coded or shipped to the
frontend (§42).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR.parent / ".env", BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Serah"
    app_env: str = "development"
    secret_key: str = "dev-only-insecure-secret-change-me"
    access_token_expire_minutes: int = 60 * 12

    database_url: str = f"sqlite:///{BASE_DIR / 'dev.db'}"

    # Vector store
    vector_store: str = "memory"  # memory | qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "career_evidence"

    # Object store
    object_store: str = "local"  # local | minio
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "applicant-companion"
    minio_secure: bool = False
    local_storage_path: str = str(BASE_DIR / "storage")

    # LLM providers (OpenRouter is the primary gateway; others remain optional)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = "http://localhost:5173"
    openrouter_app_title: str = "Serah"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Task -> "provider:model" routing (§45 cost management)
    # Defaults use OpenRouter model IDs; without OPENROUTER_API_KEY the router
    # falls back to the deterministic mock provider.
    llm_model_extraction: str = "openrouter:openai/gpt-4o-mini"
    llm_model_classification: str = "openrouter:openai/gpt-4o-mini"
    llm_model_research: str = "openrouter:openai/gpt-4o-mini"
    llm_model_scoring: str = "openrouter:openai/gpt-4o-mini"
    llm_model_matching: str = "openrouter:openai/gpt-4o-mini"
    llm_model_strategy: str = "openrouter:openai/gpt-4o"
    llm_model_cv_generation: str = "openrouter:openai/gpt-4o"
    llm_model_cover_letter: str = "openrouter:openai/gpt-4o"
    llm_model_ats: str = "openrouter:openai/gpt-4o-mini"
    llm_model_coach: str = "openrouter:openai/gpt-4o-mini"
    llm_timeout_seconds: float = 120.0
    llm_transport_retries: int = 2

    # Embeddings
    embedding_provider: str = "hash"  # hash | openrouter | openai
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dim: int = 384
    embedding_timeout_seconds: float = 60.0
    qdrant_timeout_seconds: float = 15.0

    # Background workflow lease/deadline. A lease permits stale-run recovery
    # after a process restart; bounded providers ensure the deadline is observed.
    analysis_timeout_seconds: int = 15 * 60
    workflow_lease_seconds: int = 20 * 60

    # Scoring
    score_threshold: float = 0.80

    # Research
    research_enabled: bool = True
    research_max_pages: int = 6
    research_timeout_seconds: int = 15

    # Uploads
    max_upload_mb: int = 15
    allowed_upload_extensions: str = ".pdf,.docx,.txt,.md"

    # Rate limiting
    rate_limit_per_minute: int = 120
    coach_rate_limit_per_minute: int = 20

    frontend_origin: str = "http://localhost:5173"

    # Google Sign-In (GIS ID-token). Empty disables the button and /api/auth/google.
    google_client_id: str = ""

    @property
    def allowed_extensions(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_upload_extensions.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
