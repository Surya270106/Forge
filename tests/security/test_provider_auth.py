from fastapi.testclient import TestClient

from apps.api.main import app
from packages.database.engine import get_session


def test_provider_settings_reject_anonymous_requests():
    async def unused_session():
        yield object()

    app.dependency_overrides[get_session] = unused_session
    try:
        with TestClient(app) as client:
            for method, path in (
                ("get", "/api/v1/auth/workspaces/current/provider"),
                ("put", "/api/v1/auth/workspaces/current/provider"),
                ("post", "/api/v1/auth/workspaces/current/provider/test"),
            ):
                response = client.request(method, path, json={} if method != "get" else None)
                assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)
