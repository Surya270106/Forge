import json
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.auth import OrganizationModel
from packages.database.models.execution import ExecutionJobModel, ExecutionStatus
from packages.database.models.planning import PlanModel, PlanStatus
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.models.run_capsule import RunCapsuleModel
from packages.database.models.verification import VerificationJobModel, VerificationResultModel, VerificationStatus
from packages.database.tenant import set_system_context
from packages.shared.identifiers import OrganizationId
from services.execution.flight_recorder import record_event
from services.execution.run_capsules_api import export_run_capsule, get_run_capsule, get_run_capsule_artifact, list_run_capsules


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["PASSED", "FAILED", "CANCELLED"])
async def test_capsule_records_partial_then_terminal_without_rewriting_history(terminal, monkeypatch):
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable migrated PostgreSQL required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, repo, plan, execution, verification = (uuid4() for _ in range(5))
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=org, name=f"capsule-{org}"))
            await session.flush()
            session.add(RepositoryModel(id=repo, organization_id=org, owner="fixture", name="capsule",
                                        full_name=f"fixture/{repo}", clone_url="https://example.invalid/capsule.git",
                                        status=RepositoryStatus.READY, commit_sha="a" * 40))
            await session.flush()
            session.add(PlanModel(id=plan, organization_id=org, repository_id=repo,
                                  status=PlanStatus.APPROVED, intent="Capsule test", context_snapshot={}))
            await session.flush()
            session.add(ExecutionJobModel(id=execution, organization_id=org, repository_id=repo, plan_id=plan,
                                          status=ExecutionStatus.RUNNING, commit_sha_before="a" * 40,
                                          started_at=datetime.now(UTC), lease_generation=1))
            await session.flush()
            started = await record_event(session, org, execution, "execution.started", "worker", "test.capsule",
                                         idempotency_key="capsule-start")
            await session.commit()
        async with sessions() as session:
            job = await session.get(ExecutionJobModel, execution)
            job.status = ExecutionStatus.COMPLETED
            job.finished_at = datetime.now(UTC)
            await record_event(session, org, execution, "execution.completed", "worker", "test.capsule",
                               idempotency_key="capsule-execution-complete")
            session.add(VerificationJobModel(id=verification, organization_id=org, repository_id=repo,
                                             execution_job_id=execution, status=VerificationStatus(terminal),
                                             finished_at=datetime.now(UTC)))
            await session.flush()
            if terminal != "CANCELLED":
                session.add(VerificationResultModel(organization_id=org, verification_job_id=verification,
                                                    execution_id=execution, verifier="safe-check",
                                                    status=VerificationStatus(terminal), exit_code=0 if terminal == "PASSED" else 1,
                                                    finished_at=datetime.now(UTC), diagnostics=[], attempt=1))
                await session.flush()
            if terminal == "FAILED":
                monkeypatch.setattr("services.execution.run_capsules.get_settings", lambda: SimpleNamespace(
                    capsule_artifact_max_bytes=1, capsule_artifact_max_count=2))
            if terminal == "CANCELLED":
                monkeypatch.setattr("services.execution.run_capsules.get_settings", lambda: SimpleNamespace(
                    capsule_artifact_max_bytes=16384, capsule_artifact_max_count=1))
            finished = await record_event(session, org, execution,
                                          "verification.cancelled" if terminal == "CANCELLED" else "verification.completed",
                                          "worker", "test.capsule", data={"verification_id": verification},
                                          idempotency_key="capsule-verification-complete")
            assert (await record_event(session, org, execution,
                                       "verification.cancelled" if terminal == "CANCELLED" else "verification.completed",
                                       "worker", "test.capsule", data={"verification_id": verification},
                                       idempotency_key="capsule-verification-complete")).id == finished.id
            await session.commit()
        async with sessions() as session:
            listing = await list_run_capsules(execution, OrganizationId(org), session)
            assert len(listing["capsules"]) == 3
            assert listing["capsules"][0]["state"] == "FINAL"
            first = (await session.execute(select(RunCapsuleModel).where(RunCapsuleModel.event_id == started.id))).scalar_one()
            assert first.state == "PARTIAL" and first.manifest["verification_status"] is None
            final = await get_run_capsule(execution, listing["capsules"][0]["id"], OrganizationId(org), session)
            assert final["manifest"]["verification_status"] == terminal
            assert final["manifest"]["base_commit_sha"] == "a" * 40
            assert len(final["manifest"]["verification_results"]) == (0 if terminal == "CANCELLED" else 1)
            assert final["manifest"]["missing_evidence"]
            export = await export_run_capsule(execution, final["id"], OrganizationId(org), session)
            assert export.body == json.dumps(final["manifest"], sort_keys=True,
                                             separators=(",", ":"), ensure_ascii=False).encode()
            if terminal == "FAILED":
                assert final["manifest"]["artifacts"] == []
                assert "execution-summary_size_limit" in final["manifest"]["missing_evidence"]
            else:
                artifact_id = final["manifest"]["artifacts"][0]["id"]
                response = await get_run_capsule_artifact(execution, final["id"], artifact_id, OrganizationId(org), session)
                assert response.status_code == 200 and b"execution_status" in response.body
                if terminal == "CANCELLED":
                    assert len(final["manifest"]["artifacts"]) == 1
                    assert "verification-results_count_limit" in final["manifest"]["missing_evidence"]
            with pytest.raises(HTTPException) as hidden:
                await get_run_capsule(execution, final["id"], OrganizationId(uuid4()), session)
            assert hidden.value.status_code == 404
            if terminal != "FAILED":
                with pytest.raises(HTTPException) as hidden_artifact:
                    await get_run_capsule_artifact(execution, final["id"], artifact_id, OrganizationId(uuid4()), session)
                assert hidden_artifact.value.status_code == 404
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="append-only"):
                await connection.execute(text("UPDATE run_capsules SET state = 'PARTIAL' WHERE event_id = :id"),
                                         {"id": finished.id})
            await connection.rollback()
            with pytest.raises(Exception, match="append-only"):
                await connection.execute(text("DELETE FROM run_capsule_artifacts WHERE capsule_id = :id"),
                                         {"id": first.id})
            await connection.rollback()
        async with engine.begin() as connection:
            await connection.execute(text("GRANT SELECT ON run_capsules, run_capsule_artifacts TO forge_rls_test"))
        async with engine.connect() as connection:
            await connection.execute(text("SET ROLE forge_rls_test"))
            await connection.execute(text("SELECT set_config('forge.organization_id', :org, false)"), {"org": str(uuid4())})
            assert (await connection.execute(text("SELECT count(*) FROM run_capsules WHERE execution_job_id = :id"),
                                             {"id": execution})).scalar_one() == 0
            await connection.rollback()
    finally:
        await engine.dispose()
