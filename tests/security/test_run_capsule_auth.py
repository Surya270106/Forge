from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.main import app
from packages.database.engine import get_session


def test_capsule_routes_require_authentication():
    async def unused_session():
        yield object()

    app.dependency_overrides[get_session] = unused_session
    execution, capsule, artifact = (uuid4() for _ in range(3))
    base = f"/api/v1/executions/{execution}/capsules"
    try:
        with TestClient(app) as client:
            for path in (base, f"{base}/{capsule}", f"{base}/{capsule}/export",
                         f"{base}/{capsule}/artifacts/{artifact}"):
                assert client.get(path).status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)
