"""Centralized application settings via pydantic-settings."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    env: str = Field("local")
    log_level: str = Field("INFO")
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # === LLM ===
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None
    litellm_base_url: str | None = None
    litellm_api_key: str | None = None

    # === ByteDance ===
    volcengine_ak: str | None = None
    volcengine_sk: str | None = None

    # === Cloudflare ===
    cf_account_id: str | None = None
    cf_ai_gateway_url: str | None = None
    cf_ai_gateway_token: str | None = None

    # === Patent OPS ===
    epo_ops_key: str | None = None
    epo_ops_secret: str | None = None

    # === DB ===
    database_url: str | None = None

    # === Observability ===
    langfuse_host: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


@lru_cache(maxsize=1)
def _get_settings() -> Settings:
    return Settings()


settings = _get_settings()
