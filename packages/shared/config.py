from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class ForgeSettings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://forge:forge@localhost:5432/forge"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Workspace
    workspace_root: str = "/tmp/forge-workspaces"

    # GitHub
    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")

    # Security
    secret_key: SecretStr = SecretStr("change-me-in-production")

    # Application
    environment: Literal["development", "staging", "production", "test"] = "development"
    log_level: str = "INFO"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]

    # Limits
    max_repository_size_mb: int = 500
    import_timeout_seconds: int = 300
    execution_timeout_seconds: int = 600
    worker_concurrency: int = 4

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    from pydantic import model_validator

    @model_validator(mode='after')
    def check_production_secret(self) -> "ForgeSettings":
        if self.environment == "production" and self.secret_key.get_secret_value() == "change-me-in-production":
            raise ValueError("SECRET_KEY must be changed in production")
        return self

def get_settings() -> ForgeSettings:
    return ForgeSettings()
