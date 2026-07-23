import httpx
import pytest

# The test requires a running API server, which run_integration.py will spin up.
BASE_URL = "http://127.0.0.1:8000"


@pytest.mark.asyncio
async def test_e2e_alpha_workflow():
    headers = {"X-Organization-Id": "00000000-0000-0000-0000-000000000000"}
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers) as client:
        # Step 1: Check readiness
        resp = await client.get("/ready")
        assert resp.status_code == 200, f"Readiness failed: {resp.text}"
        assert resp.json()["status"] == "ready"

        # Step 2: Trigger repository import (RFC-001)
        req_data = {"clone_url": "file:///tmp/dummy", "owner": "dummy-owner", "name": "dummy-repo"}
        resp = await client.post("/api/v1/repositories/import", json=req_data)
        assert resp.status_code == 202, f"Import failed: {resp.text}"
        import_id = resp.json()["import_job_id"]
        repo_id = resp.json()["repository_id"]

        # Step 3: Trigger memory indexing (RFC-002)
        resp = await client.post(f"/api/v1/memory/repositories/{repo_id}/index", json={"branch": "main"})
        assert resp.status_code == 200, f"Memory index failed: {resp.text}"

        # Step 4: Create a plan (RFC-003)
        plan_req = {"intent": "Fix the bug"}
        resp = await client.post(f"/api/v1/repositories/{repo_id}/plans", json=plan_req)
        assert resp.status_code == 200, f"Plan creation failed: {resp.text}"
        plan_id = resp.json()["id"]

        # Step 5: Approve the plan
        resp = await client.post(f"/api/v1/plans/{plan_id}/approve")
        assert resp.status_code == 200, f"Plan approval failed: {resp.text}"

        # Step 6: Start execution (RFC-004)
        exec_req = {}
        resp = await client.post(f"/api/v1/executions/plans/{plan_id}", json=exec_req)
        assert resp.status_code == 200, f"Execution failed: {resp.text}"

        print("E2E Alpha Workflow executed successfully via HTTPX!")
