import pytest
from pydantic import SecretStr, ValidationError

from packages.shared.config import ForgeSettings


def test_production_settings_reject_missing_github_client_secret():
    with pytest.raises(ValidationError, match="GitHub OAuth config required"):
        ForgeSettings(
            environment="production",
            secret_key=SecretStr("s" * 32),
            encryption_key=SecretStr("e" * 32),
            database_url="postgresql+asyncpg://forge:password@db.internal:5432/forge",
            redis_url="redis://cache.internal:6379/0",
            frontend_url="https://forge-ui.example.test",
            github_client_id="client-id",
            github_client_secret=None,
        )
