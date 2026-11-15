from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.planning import PlanModel, PlanStatus
from packages.database.models.verification import (
    RepairAttemptModel,
    RepairAttemptStatus,
    VerificationJobModel,
    VerificationResultModel,
    VerificationStatus,
)
from packages.shared.errors import ErrorCategory, NotFoundError
from packages.shared.events import EventEnvelope
from packages.shared.identifiers import OrganizationId

from .schemas import TriggerVerificationRequest, VerificationJobResponse
from .service import VerificationDispatcher

router = APIRouter(prefix="/api/v1/verifications", tags=["verification"])


from services.auth.dependencies import get_current_user, require_permission
from services.repository_memory.events import OutboxEventPublisher


@router.post("/executions/{execution_job_id}", response_model=VerificationJobResponse)
async def trigger_verification(
    execution_job_id: UUID,
    request: TriggerVerificationRequest,
    organization_id: OrganizationId = Depends(require_permission("plan:approve")),
    session: AsyncSession = Depends(get_session),
):
    dispatcher = VerificationDispatcher(session, organization_id)
    job = await dispatcher.trigger_verification(execution_job_id)

    return job


@router.get("/{job_id}", response_model=VerificationJobResponse)
async def get_verification(
    job_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    job = await session.get(VerificationJobModel, job_id)
    if not job or job.organization_id != organization_id:
        raise NotFoundError(
            code="verification_not_found",
            message="Verification job not found",
            category=ErrorCategory.NOT_FOUND,
        )

    stmt = select(VerificationResultModel).where(
        VerificationResultModel.verification_job_id == job_id,
        VerificationResultModel.organization_id == organization_id,
    )
    results = (await session.execute(stmt)).scalars().all()

    job_dict = job.__dict__.copy()
    job_dict["results"] = results
    return job_dict


@router.get("/executions/{execution_job_id}/latest", response_model=VerificationJobResponse)
async def get_latest_verification(
    execution_job_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    job = (
        await session.execute(
            select(VerificationJobModel)
            .where(
                VerificationJobModel.execution_job_id == execution_job_id,
                VerificationJobModel.organization_id == organization_id,
            )
            .order_by(VerificationJobModel.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not job:
        raise NotFoundError(code="verification_not_found", message="Verification not found", category=ErrorCategory.NOT_FOUND)
    return await get_verification(job.id, organization_id, session)


@router.get("/{job_id}/repair")
async def get_repair_for_verification(
    job_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    verification = await session.get(VerificationJobModel, job_id)
    if not verification or verification.organization_id != organization_id:
        raise NotFoundError("verification_not_found", "Verification not found", ErrorCategory.NOT_FOUND)
    repair = (
        await session.execute(
            select(RepairAttemptModel)
            .where(
                RepairAttemptModel.verification_job_id == job_id,
                RepairAttemptModel.organization_id == organization_id,
            )
            .order_by(RepairAttemptModel.attempt_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not repair:
        raise NotFoundError("repair_not_found", "No repair proposal is available", ErrorCategory.NOT_FOUND)
    return {
        "id": str(repair.id),
        "status": repair.status.value,
        "attempt_number": repair.attempt_number,
        "repair_plan_id": str(repair.repair_plan_id) if repair.repair_plan_id else None,
        "error_message": repair.error_message,
        "feedback": repair.prompt_used[:12000] if repair.prompt_used else None,
    }


@router.post("/repairs/{repair_id}/plan")
async def request_repair_plan(
    repair_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("plan:create")),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repair = (
        await session.execute(
            select(RepairAttemptModel).where(RepairAttemptModel.id == repair_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not repair or repair.organization_id != organization_id:
        raise NotFoundError("repair_not_found", "Repair proposal not found", ErrorCategory.NOT_FOUND)
    verification = await session.get(VerificationJobModel, repair.verification_job_id)
    if not verification or verification.organization_id != organization_id or verification.status != VerificationStatus.FAILED:
        raise HTTPException(status_code=409, detail="Repair source verification is no longer failed")
    if repair.status != RepairAttemptStatus.ELIGIBLE or repair.attempt_number > 3 or repair.repair_plan_id:
        raise HTTPException(status_code=409, detail="Repair proposal is not eligible for planning")
    repair.status = RepairAttemptStatus.PLANNING
    repair.requested_by = UUID(user["id"])
    await OutboxEventPublisher(session).publish(
        EventEnvelope(
            event_type="repair.plan_requested",
            aggregate_type="repair",
            aggregate_id=str(repair.id),
            organization_id=str(organization_id),
            payload={"repair_id": str(repair.id)},
        )
    )
    await session.commit()
    return {"id": str(repair.id), "status": repair.status.value}


@router.post("/repairs/{repair_id}/cancel")
async def cancel_repair_proposal(
    repair_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("plan:create")),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repair = (
        await session.execute(
            select(RepairAttemptModel).where(RepairAttemptModel.id == repair_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not repair or repair.organization_id != organization_id:
        raise NotFoundError("repair_not_found", "Repair proposal not found", ErrorCategory.NOT_FOUND)
    if repair.requested_by != UUID(user["id"]) or repair.status not in {RepairAttemptStatus.PLANNING, RepairAttemptStatus.AWAITING_APPROVAL}:
        raise HTTPException(status_code=409, detail="Only the requester can cancel an unexecuted repair proposal")
    if repair.repair_plan_id:
        plan = await session.get(PlanModel, repair.repair_plan_id)
        if plan and plan.status == PlanStatus.PENDING_APPROVAL:
            plan.status = PlanStatus.REJECTED
    repair.status = RepairAttemptStatus.CANCELLED
    await session.commit()
    return {"id": str(repair.id), "status": repair.status.value}
