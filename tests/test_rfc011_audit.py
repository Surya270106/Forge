import pytest

pytestmark = pytest.mark.asyncio

async def test_audit_api_stub():
    # Verify the router is connected
    from apps.api.main import app
    paths = app.openapi()["paths"]
    assert "/api/v1/organizations/{organization_id}/audit-logs" in paths
    assert "/api/v1/repositories/{repository_id}/audit-logs" in paths
