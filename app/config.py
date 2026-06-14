from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    cookie_secure: bool = False  # set True in production (requires HTTPS)

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_must_be_strong(cls, v: str) -> str:
        if v == "change-me-in-production" or len(v) < 32:
            raise ValueError(
                "JWT_SECRET must be set to a strong random value (≥32 chars). "
                "Generate one with: openssl rand -hex 32"
            )
        return v

    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    minio_root_user: str
    minio_root_password: str
    minio_bucket: str
    minio_internal_url: str
    minio_public_url: str

    llm_provider: Literal["ollama", "openai"] = "ollama"
    # 300s — Ollama cold-load (model pull + first inference) can exceed 180s on CPU
    llm_timeout_seconds: int = 300

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_embed_model: str = "nomic-embed-text"

    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    max_upload_bytes: int = 10 * 1024 * 1024
    max_video_upload_bytes: int = 150 * 1024 * 1024
    presigned_url_ttl_seconds: int = 300

    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False

    # Email (SMTP) — leave smtp_host empty to use log-only stub in development
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@example.com"
    smtp_use_tls: bool = True  # set False for Mailpit / local dev
    app_base_url: str = "http://localhost:3000"

    invite_token_expire_hours: int = 72

    # Azure AD OIDC SSO (F2) — all optional; SSO routes are disabled when unset
    azure_tenant_id: str | None = None
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_redirect_uri: str | None = None

    audit_retention_months: int = 12

    # Slack / MS Teams webhook — leave empty to disable notifications
    slack_webhook_url: str = ""
    teams_webhook_url: str = ""

    # Comma-separated list of trusted reverse-proxy IPs that may set X-Forwarded-For.
    # Leave empty (default) to trust the direct peer IP only.
    trusted_proxies: list[str] = []

    # Elasticsearch (F4) — leave empty to disable ES and fall back to Postgres search
    elasticsearch_url: str = ""
    elasticsearch_username: str = ""
    elasticsearch_password: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()  # type: ignore[call-arg]
