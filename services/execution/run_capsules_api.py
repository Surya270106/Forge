"""Authorized inspection and deterministic export of immutable run capsules."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.execution import ExecutionJobModel
from packages.database.models.repository import RepositoryModel
from packages.database.models.run_capsule import RunCapsuleArtifactModel, RunCapsuleModel
from packages.shared.identifiers import OrganizationId
from services.auth.dependencies import require_permission

from .run_capsules import canonical_bytes, content_sha256, verified_artifact

router = APIRouter(prefix="/api/v1/executions/{execution_id}/capsules", tags=["run-capsules"])


async def _execution(session: AsyncSession, organization_id: UUID, execution_id: UUID) -> ExecutionJobModel:
    job = (await session.execute(select(ExecutionJobModel).where(
        ExecutionJobModel.id == execution_id, ExecutionJobModel.organization_id == organization_id,
    ))).scalar_one_or_none()
    if job is None or not (await session.execute(select(RepositoryModel.id).where(
        RepositoryModel.id == job.repository_id, RepositoryModel.organization_id == organization_id,
    ))).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Execution unavailable")
    return job


async def _capsule(session: AsyncSession, organization_id: UUID, execution_id: UUID,
                   repository_id: UUID, capsule_id: UUID) -> RunCapsuleModel:
    capsule = (await session.execute(select(RunCapsuleModel).where(
        RunCapsuleModel.id == capsule_id, RunCapsuleModel.organization_id == organization_id,
        RunCapsuleModel.repository_id == repository_id, RunCapsuleModel.execution_job_id == execution_id,
    ))).scalar_one_or_none()
    if capsule is None:
        raise HTTPException(status_code=404, detail="Capsule unavailable")
    if content_sha256(canonical_bytes(capsule.manifest)) != capsule.manifest_sha256:
        raise HTTPException(status_code=409, detail="Capsule manifest integrity check failed")
    return capsule


@router.get("")
async def list_run_capsules(
    execution_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    job = await _execution(session, organization_id, execution_id)
    rows = (await session.execute(select(RunCapsuleModel).where(
        RunCapsuleModel.organization_id == organization_id, RunCapsuleModel.repository_id == job.repository_id,
        RunCapsuleModel.execution_job_id == execution_id,
    ).order_by(RunCapsuleModel.created_at.desc(), RunCapsuleModel.id.desc()).limit(21))).scalars().all()
    return {"capsules": [{"id": str(row.id), "state": row.state, "attempt": row.attempt,
                           "event_id": str(row.event_id), "created_at": row.created_at,
                           "manifest_sha256": row.manifest_sha256} for row in rows[:20]],
            "truncated": len(rows) > 20}


@router.get("/{capsule_id}/export")
async def export_run_capsule(
    execution_id: UUID, capsule_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    job = await _execution(session, organization_id, execution_id)
    capsule = await _capsule(session, organization_id, execution_id, job.repository_id, capsule_id)
    return Response(canonical_bytes(capsule.manifest), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="forge-capsule-{capsule.id}.json"'})


@router.get("/{capsule_id}/artifacts/{artifact_id}")
async def get_run_capsule_artifact(
    execution_id: UUID, capsule_id: UUID, artifact_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    job = await _execution(session, organization_id, execution_id)
    capsule = await _capsule(session, organization_id, execution_id, job.repository_id, capsule_id)
    artifact = (await session.execute(select(RunCapsuleArtifactModel).where(
        RunCapsuleArtifactModel.id == artifact_id, RunCapsuleArtifactModel.capsule_id == capsule.id,
        RunCapsuleArtifactModel.organization_id == organization_id,
    ))).scalar_one_or_none()
    if artifact is None or not any(item["id"] == str(artifact.id) and item["sha256"] == artifact.sha256
                               and item["size_bytes"] == artifact.size_bytes for item in capsule.manifest["artifacts"]):
        raise HTTPException(status_code=404, detail="Artifact unavailable")
    try:
        content = verified_artifact(artifact)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(content, media_type="application/json")


@router.get("/{capsule_id}")
async def get_run_capsule(
    execution_id: UUID, capsule_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    job = await _execution(session, organization_id, execution_id)
    capsule = await _capsule(session, organization_id, execution_id, job.repository_id, capsule_id)
    return {"id": str(capsule.id), "state": capsule.state, "manifest_sha256": capsule.manifest_sha256,
            "manifest": capsule.manifest}
