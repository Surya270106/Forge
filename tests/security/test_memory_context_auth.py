from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from apps.api.main import app
from packages.database.engine import get_session


@pytest.fixture
def client():
    async def unused_session():
        yield object()

    app.dependency_overrides[get_session] = unused_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/memory/repositories/{id}/index"),
        ("get", "/api/v1/memory/jobs/{id}"),
        ("get", "/api/v1/memory/repositories/{id}/symbols"),
        ("get", "/api/v1/context/snapshots/{id}"),
        ("get", "/api/v1/context/interactions/{id}"),
        ("post", "/api/v1/verifications/executions/{id}"),
        ("get", "/api/v1/verifications/{id}"),
    ],
)
def test_memory_and_context_routes_reject_anonymous_requests(client, method, path):
    url = path.format(id=uuid4())
    response = client.post(url, json={}) if method == "post" else client.get(url)
    assert response.status_code == 401


def test_execution_websocket_rejects_missing_credentials(client):
    with pytest.raises(WebSocketDisconnect) as error, client.websocket_connect(f"/api/v1/executions/{uuid4()}/ws"):
        pass
    assert error.value.code == 1008


def test_execution_websocket_rejects_bearer_token_in_subprotocol(client):
    with (
        pytest.raises(WebSocketDisconnect) as error,
        client.websocket_connect(
            f"/api/v1/executions/{uuid4()}/ws",
            subprotocols=["forge.v1", "forge.jwt.an-application-token"],
            headers={"Origin": "http://localhost:3000"},
        ),
    ):
        pass
    assert error.value.code == 1008
