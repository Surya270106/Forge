from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.main import app
from packages.database.engine import get_session
from services.auth.permissions import has_permission


def test_bench_routes_require_authenticated_workspace():
    async def unused_session():
        yield object()

    app.dependency_overrides[get_session] = unused_session
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/bench/suites").status_code == 401
            assert client.get("/api/v1/bench/runs").status_code == 401
            assert client.get(f"/api/v1/bench/runs/{uuid4()}").status_code == 401
            assert client.post("/api/v1/bench/runs", json={}).status_code == 401
            assert client.post(f"/api/v1/bench/runs/{uuid4()}/cancel").status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_only_owners_and_admins_can_start_or_cancel_runs():
    for role in ("OWNER", "ADMIN"):
        assert has_permission(role, "bench:read")
        assert has_permission(role, "bench:create")
        assert has_permission(role, "bench:cancel")
    for role in ("MEMBER", "VIEWER"):
        assert has_permission(role, "bench:read")
        assert not has_permission(role, "bench:create")
        assert not has_permission(role, "bench:cancel")
