from typing import Literal
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


def normalize_async_database_url(value: str | None) -> str | None:
    """Normalize PostgreSQL URLs for SQLAlchemy's asyncpg driver."""
    if not value:
        return value
    parsed = urlsplit(value)
    scheme = {
        "postgres": "postgresql+asyncpg",
        "postgresql": "postgresql+asyncpg",
    }.get(parsed.scheme, parsed.scheme)
    query = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        # asyncpg does not implement libpq's channel_binding URL parameter.
        # Keep sslmode=require (translated to ssl=require) so TLS remains enabled.
        if key == "channel_binding":
            continue
        query.append(("ssl" if key == "sslmode" else key, item))
    return urlunsplit((scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


class ForgeSettings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://forge:forge@localhost:5432/forge"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Workspace
    workspace_root: str = "/tmp/forge-workspaces"

    # GitHub
    github_client_id: str | None = Field(default=None)
    github_client_secret: SecretStr | None = Field(default=None)
    github_webhook_secret: str | None = Field(default=None)

    # Security
    secret_key: SecretStr = SecretStr("change-me-in-production")
    encryption_key: SecretStr = SecretStr("")

    # Application
    environment: Literal["development", "staging", "production", "test"] = "development"
    log_level: str = "INFO"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]
    frontend_url: str = "http://localhost:3000"

    # Execution
    sandbox_images: list[str] = ["python:3.12-slim", "node:20-slim"]

    # Limits
    max_repository_size_mb: int = 500
    import_timeout_seconds: int = 300
    execution_timeout_seconds: int = 600
    worker_concurrency: int = 4

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    from pydantic import model_validator

    @model_validator(mode='after')
    def check_production_secret(self) -> "ForgeSettings":
        if self.environment == "production":
            if self.secret_key.get_secret_value() == "change-me-in-production":
                raise ValueError("SECRET_KEY must be changed in production")
            if not self.encryption_key.get_secret_value():
                raise ValueError("encryption_key must be set in production")
            if not self.database_url or "forge:forge@localhost" in self.database_url:
                raise ValueError("Valid production database_url required")
            if unquote(urlsplit(self.database_url).username or "") == "forge_admin":
                raise ValueError("Production API database role must not be forge_admin because RLS policies exempt it")
            if not self.redis_url:
                raise ValueError("redis_url required in production")
            if not self.github_client_id or not self.github_client_secret or not self.github_client_secret.get_secret_value():
                raise ValueError("GitHub OAuth config required in production")
            if self.frontend_url == "http://localhost:3000":
                raise ValueError("frontend_url must be updated in production")
            if not self.sandbox_images:
                raise ValueError("sandbox_images required")
        return self

def get_settings() -> ForgeSettings:
    return ForgeSettings()
