"""Authenticated organization Safety Gate controls."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.execution import ExecutionJobModel, ExecutionStatus
from packages.database.models.safety import SafetyPolicyModel
from packages.shared.identifiers import OrganizationId
from services.auth.dependencies import get_current_user, require_permission
from services.execution.flight_recorder import record_event

from .service import as_document, current_policy, revise_policy

router = APIRouter(prefix="/api/v1/safety", tags=["safety"])


class RestrictionRequest(BaseModel):
    denied: list[str]
    repository_denies: dict[str, list[str]] = {}


async def _record_policy_change(session: AsyncSession, organization_id: UUID, actor_id: UUID,
                                version: int, event_type: str) -> None:
    jobs = (await session.execute(select(ExecutionJobModel.id).where(
        ExecutionJobModel.organization_id == organization_id,
        ExecutionJobModel.status.in_([ExecutionStatus.PENDING, ExecutionStatus.RUNNING]),
    ))).scalars().all()
    for job_id in jobs:
        await record_event(session, organization_id, job_id, event_type, "user", "safety.api",
                           actor_id=str(actor_id), data={"policy_version": version},
                           idempotency_key=f"safety-policy-{event_type}-{version}")


@router.get("/policy")
async def get_policy(organization_id: OrganizationId = Depends(require_permission("workspace:settings:read")),
                     session: AsyncSession = Depends(get_session)):
    return as_document(await current_policy(session, organization_id))


@router.get("/history")
async def policy_history(organization_id: OrganizationId = Depends(require_permission("workspace:settings:read")),
                         session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(SafetyPolicyModel).where(
        SafetyPolicyModel.organization_id == organization_id,
    ).order_by(SafetyPolicyModel.version.desc()).limit(50))).scalars().all()
    return {"revisions": [{"version": row.version, "denied": row.denied,
                            "repository_denies": row.repository_denies, "stopped": row.stopped,
                            "created_by": str(row.created_by), "created_at": row.created_at.isoformat()} for row in rows]}


@router.put("/policy")
async def update_policy(request: RestrictionRequest,
                        organization_id: OrganizationId = Depends(require_permission("workspace:settings:write", rate_category="execution")),
                        user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    try:
        state = await revise_policy(session, organization_id, UUID(user["id"]),
                                    denied=request.denied, repository_denies=request.repository_denies)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    await _record_policy_change(session, organization_id, UUID(user["id"]), state.version, "safety.policy_changed")
    await session.commit()
    return as_document(state)


@router.post("/emergency-stop")
async def emergency_stop(organization_id: OrganizationId = Depends(require_permission("workspace:settings:write", rate_category="execution")),
                         user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    state = await revise_policy(session, organization_id, UUID(user["id"]), stopped=True)
    await _record_policy_change(session, organization_id, UUID(user["id"]), state.version, "safety.emergency_stop")
    await session.commit()
    return as_document(state)


@router.post("/resume")
async def resume(organization_id: OrganizationId = Depends(require_permission("workspace:settings:write", rate_category="execution")),
                 user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    state = await revise_policy(session, organization_id, UUID(user["id"]), stopped=False)
    await _record_policy_change(session, organization_id, UUID(user["id"]), state.version, "safety.policy_changed")
    await session.commit()
    return as_document(state)
