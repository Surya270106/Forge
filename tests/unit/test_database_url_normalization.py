import pytest
from pydantic import SecretStr

from packages.shared.config import ForgeSettings, normalize_async_database_url


def test_postgres_scheme_is_normalized_for_asyncpg():
    assert (
        normalize_async_database_url("postgres://forge:password@db.internal:5432/forge")
        == "postgresql+asyncpg://forge:password@db.internal:5432/forge"
    )


def test_postgresql_sslmode_is_translated_and_other_query_params_remain():
    assert normalize_async_database_url(
        "postgresql://forge:p%40ss@db.external:5432/forge?sslmode=require&application_name=forge"
    ) == (
        "postgresql+asyncpg://forge:p%40ss@db.external:5432/forge"
        "?ssl=require&application_name=forge"
    )


def test_neon_channel_binding_parameter_is_removed_for_asyncpg_but_tls_remains():
    assert normalize_async_database_url(
        "postgresql://forge:password@db.neon.tech/forge?sslmode=require&channel_binding=require"
    ) == "postgresql+asyncpg://forge:password@db.neon.tech/forge?ssl=require"


def test_existing_asyncpg_url_is_preserved():
    value = "postgresql+asyncpg://forge:password@db.internal:5432/forge"
    assert normalize_async_database_url(value) == value


def test_empty_url_is_preserved():
    assert normalize_async_database_url(None) is None
    assert normalize_async_database_url("") == ""


def test_production_rejects_rls_exempt_database_role():
    with pytest.raises(ValueError, match="must not be forge_admin"):
        ForgeSettings(
            environment="production",
            database_url="postgresql+asyncpg://forge_admin:test@db.example.invalid/forge?ssl=require",
            redis_url="rediss://default:test@redis.example.invalid:6379",
            secret_key=SecretStr("test-only-secret"),
            encryption_key=SecretStr("test-only-encryption"),
            github_client_id="test-client",
            github_client_secret=SecretStr("test-secret"),
            frontend_url="https://forge.example.invalid",
        )
