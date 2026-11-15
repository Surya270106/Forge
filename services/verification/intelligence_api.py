"""Tenant-scoped reads of suggested tests and persisted verifier decisions."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.context_lens import ContextChangeSetModel
from packages.database.models.execution import ExecutionEventModel, ExecutionJobModel
from packages.database.models.patch import PatchModel
from packages.database.models.repository import RepositoryModel
from packages.database.models.verification import VerificationJobModel, VerificationResultModel
from packages.database.models.verification_intelligence import VerificationPlanModel
from packages.shared.errors import ConflictError
from packages.shared.identifiers import OrganizationId
from services.auth.dependencies import require_permission
from services.patch.service import PatchService

from .intelligence import build_decision, verifier_ref

router = APIRouter(prefix="/api/v1/verifications/executions", tags=["verification-intelligence"])


async def _scope(session: AsyncSession, organization_id: UUID, execution_id: UUID) -> ExecutionJobModel:
    execution = (await session.execute(select(ExecutionJobModel).where(
        ExecutionJobModel.id == execution_id, ExecutionJobModel.organization_id == organization_id,
    ))).scalar_one_or_none()
    if execution is None or not (await session.execute(select(RepositoryModel.id).where(
        RepositoryModel.id == execution.repository_id, RepositoryModel.organization_id == organization_id,
    ))).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Execution unavailable")
    return execution


async def _current_digest(session: AsyncSession, organization_id: UUID, patch: PatchModel | None,
                          captured_digest: str) -> bool:
    if patch is None or patch.review_digest != captured_digest:
        return False
    try:
        mutations = await PatchService(session, organization_id)._mutations(patch)
        return PatchService._review_digest(patch.base_commit_sha or "", mutations) == captured_digest
    except (ConflictError, ValueError):
        return False


@router.get("/{execution_id}/intelligence/preview")
async def preview_verification_intelligence(
    execution_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    execution = await _scope(session, organization_id, execution_id)
    patch = (await session.execute(select(PatchModel).where(
        PatchModel.execution_job_id == execution_id, PatchModel.organization_id == organization_id,
        PatchModel.repository_id == execution.repository_id,
    ).order_by(PatchModel.created_at.desc()).limit(1))).scalar_one_or_none()
    change = (await session.execute(select(ContextChangeSetModel).where(
        ContextChangeSetModel.patch_id == patch.id,
        ContextChangeSetModel.execution_job_id == execution_id,
        ContextChangeSetModel.organization_id == organization_id,
        ContextChangeSetModel.repository_id == execution.repository_id,
    ))).scalar_one_or_none() if patch else None
    if not change:
        raise HTTPException(status_code=404, detail="Prepared change evidence unavailable")
    decision = await build_decision(session, organization_id, execution.repository_id, change, [])
    return {"execution_id": str(execution_id), "change_set_id": str(change.id),
            "patch_digest": change.review_digest,
            "current": await _current_digest(session, organization_id, patch, change.review_digest),
            "configuration_checked": False, "snapshot_id": decision["snapshot_id"],
            "changed_paths": decision["changed_paths"], "suggested_tests": decision["suggested_tests"],
            "fallback_reasons": [reason for reason in decision["fallback_reasons"]
                                 if reason != "NO_CONFIGURED_TEST_VERIFIER"],
            "coverage_claimed": False}


@router.get("/{execution_id}/intelligence")
async def get_verification_intelligence(
    execution_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    execution = await _scope(session, organization_id, execution_id)
    job = (await session.execute(select(VerificationJobModel).where(
        VerificationJobModel.execution_job_id == execution_id,
        VerificationJobModel.organization_id == organization_id,
        VerificationJobModel.repository_id == execution.repository_id,
    ).order_by(VerificationJobModel.created_at.desc()).limit(1))).scalar_one_or_none()
    if not job:
        return {"execution_id": str(execution_id), "job": None, "plan": None, "results": [],
                "results_truncated": False, "coverage_claimed": False}
    plan = (await session.execute(select(VerificationPlanModel).where(
        VerificationPlanModel.verification_job_id == job.id,
        VerificationPlanModel.execution_job_id == execution_id,
        VerificationPlanModel.organization_id == organization_id,
        VerificationPlanModel.repository_id == execution.repository_id,
    ))).scalar_one_or_none()
    decision = None
    if plan:
        change = (await session.execute(select(ContextChangeSetModel).where(
            ContextChangeSetModel.id == plan.change_set_id,
            ContextChangeSetModel.execution_job_id == execution_id,
            ContextChangeSetModel.organization_id == organization_id,
            ContextChangeSetModel.repository_id == execution.repository_id,
            ContextChangeSetModel.review_digest == plan.patch_digest,
        ))).scalar_one_or_none()
        patch = (await session.execute(select(PatchModel).where(
            PatchModel.id == change.patch_id, PatchModel.organization_id == organization_id,
            PatchModel.repository_id == execution.repository_id,
            PatchModel.execution_job_id == execution_id,
        ))).scalar_one_or_none() if change else None
        event = (await session.execute(select(ExecutionEventModel.id).where(
            ExecutionEventModel.execution_job_id == execution_id,
            ExecutionEventModel.organization_id == organization_id,
            ExecutionEventModel.idempotency_key == f"verification-selection-{job.id}",
        ))).scalar_one_or_none()
        decision = {"id": str(plan.id), "change_set_id": str(plan.change_set_id),
                    "base_commit_sha": plan.base_commit_sha, "patch_digest": plan.patch_digest,
                    "created_at": plan.created_at, "current": bool(change) and await _current_digest(
                        session, organization_id, patch, plan.patch_digest),
                    "flight_recorder_event_id": str(event) if event else None, **plan.decision}
    rows = (await session.execute(select(VerificationResultModel).where(
        VerificationResultModel.verification_job_id == job.id,
        VerificationResultModel.execution_id == execution_id,
        VerificationResultModel.organization_id == organization_id,
    ).order_by(VerificationResultModel.created_at).limit(101))).scalars().all()
    results = [{"id": str(row.id), "verifier": verifier_ref(row.verifier), "status": row.status.value,
                "exit_code": row.exit_code, "duration_ms": row.duration_ms, "started_at": row.started_at,
                "finished_at": row.finished_at, "attempt": row.attempt} for row in rows[:100]]
    return {"execution_id": str(execution_id),
            "job": {"id": str(job.id), "status": job.status.value,
                    "started_at": job.started_at, "finished_at": job.finished_at},
            "plan": decision, "results": results, "results_truncated": len(rows) > 100,
            "coverage_claimed": False}
