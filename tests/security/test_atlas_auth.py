from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.main import app
from packages.database.engine import get_session


def test_all_atlas_routes_require_authentication():
    async def unused_session():
        yield object()

    repo, snapshot, job, node = (uuid4() for _ in range(4))
    prefix = f"/api/v1/repositories/{repo}/atlas"
    paths = [f"{prefix}/jobs/{job}", f"{prefix}/snapshots", f"{prefix}/snapshots/{snapshot}",
             f"{prefix}/graph?snapshot_id={snapshot}", f"{prefix}/symbols?snapshot_id={snapshot}",
             f"{prefix}/impact?snapshot_id={snapshot}&node_key=file:a.py",
             f"{prefix}/tests?snapshot_id={snapshot}&node_key=file:a.py",
             f"{prefix}/diff?left={snapshot}&right={snapshot}", f"{prefix}/nodes/{node}"]
    app.dependency_overrides[get_session] = unused_session
    try:
        with TestClient(app) as client:
            for path in paths:
                assert client.get(path).status_code == 401, path
            assert client.post(f"{prefix}/index", json={"idempotency_key": str(uuid4())}).status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)
