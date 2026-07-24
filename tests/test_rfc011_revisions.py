import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_revise_plan_stub():
    # Since we can't easily mock the whole DB here without full setup,
    # we just import and ensure it compiles and routers are valid.
    from apps.api.main import app
    assert any(route.path == "/api/v1/plans/{plan_id}/revise" for route in app.routes)

async def test_revise_patch_stub():
    from apps.api.main import app
    assert any(route.path == "/api/v1/patches/{patch_id}/revise" for route in app.routes)
