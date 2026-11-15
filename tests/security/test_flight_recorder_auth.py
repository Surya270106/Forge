from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.main import app
from packages.database.engine import get_session
from services.auth.permissions import has_permission


def test_flight_recorder_routes_require_authentication():
    async def unused_session():
        yield object()

    app.dependency_overrides[get_session] = unused_session
    job_id, event_id = uuid4(), uuid4()
    try:
        with TestClient(app) as client:
            for path in (f"/api/v1/executions/{job_id}/timeline",
                         f"/api/v1/executions/{job_id}/timeline/{event_id}",
                         f"/api/v1/executions/{job_id}/timeline/export"):
                assert client.get(path).status_code == 401
            assert client.post(f"/api/v1/executions/{job_id}/cancel").status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_cancel_permission_is_limited_to_workspace_owners_and_admins():
    assert has_permission("OWNER", "exec:cancel")
    assert has_permission("ADMIN", "exec:cancel")
    assert not has_permission("MEMBER", "exec:cancel")
    assert not has_permission("VIEWER", "exec:cancel")
