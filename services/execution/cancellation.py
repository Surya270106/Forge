"""Durable, tenant-scoped execution cancellation requests."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.execution import ExecutionJobModel, ExecutionStatus
from packages.database.models.planning import PlanModel, PlanStatus
from packages.database.models.verification import (
    RepairAttemptModel,
    RepairAttemptStatus,
    VerificationJobModel,
    VerificationStatus,
)
from services.verification.events import VerificationEventPublisher, create_verification_cancelled_event

from .events import ExecutionEventPublisher, create_execution_cancel_requested_event, create_execution_cancelled_event
from .flight_recorder import record_event


async def request_execution_cancellation(
    session: AsyncSession, organization_id: UUID, execution_id: UUID, requested_by: UUID,
) -> ExecutionJobModel:
    job = (await session.execute(select(ExecutionJobModel).where(
        ExecutionJobModel.id == execution_id, ExecutionJobModel.organization_id == organization_id,
    ).with_for_update(key_share=True).execution_options(populate_existing=True))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    verification = None
    if job.status == ExecutionStatus.COMPLETED:
        verification = (await session.execute(select(VerificationJobModel).where(
            VerificationJobModel.execution_job_id == job.id,
            VerificationJobModel.organization_id == organization_id,
            VerificationJobModel.status.in_([VerificationStatus.PENDING, VerificationStatus.RUNNING]),
        ).order_by(VerificationJobModel.created_at.desc()).limit(1)
        .with_for_update(key_share=True))).scalar_one_or_none()
    if (job.status in {ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}
        or (job.status == ExecutionStatus.COMPLETED and verification is None)
        or job.cancellation_requested_at):
        return job

    job.cancellation_requested_at = datetime.now(UTC)
    job.cancellation_requested_by = requested_by
    await record_event(session, organization_id, job.id, "execution.cancel_requested", "user", "execution.api",
                       actor_id=str(requested_by), idempotency_key="cancel-requested")
    await ExecutionEventPublisher(session).publish(
        create_execution_cancel_requested_event(organization_id, job.repository_id, job.id, job.plan_id)
    )
    if verification and verification.status == VerificationStatus.PENDING:
        verification.status = VerificationStatus.CANCELLED
        verification.finished_at = datetime.now(UTC)
        repair = (await session.execute(select(RepairAttemptModel).where(
            RepairAttemptModel.repair_execution_id == job.id,
            RepairAttemptModel.organization_id == organization_id,
            RepairAttemptModel.status == RepairAttemptStatus.REVERIFYING,
        ))).scalar_one_or_none()
        if repair:
            repair.status = RepairAttemptStatus.CANCELLED
        await VerificationEventPublisher(session).publish(create_verification_cancelled_event(
            organization_id, verification.repository_id, verification.id, job.id,
        ))
        await record_event(session, organization_id, job.id, "verification.cancelled", "system", "execution.api",
                           data={"verification_id": verification.id}, idempotency_key=f"verification-cancelled-{verification.id}")
    if job.status == ExecutionStatus.PENDING:
        job.status = ExecutionStatus.CANCELLED
        job.finished_at = datetime.now(UTC)
        plan = await session.get(PlanModel, job.plan_id)
        if plan and plan.organization_id == organization_id and plan.status == PlanStatus.APPROVED:
            plan.status = PlanStatus.CANCELLED
        repair = (await session.execute(select(RepairAttemptModel).where(
            RepairAttemptModel.repair_execution_id == job.id,
            RepairAttemptModel.organization_id == organization_id,
            RepairAttemptModel.status == RepairAttemptStatus.EXECUTING,
        ))).scalar_one_or_none()
        if repair:
            repair.status = RepairAttemptStatus.CANCELLED
        await ExecutionEventPublisher(session).publish(
            create_execution_cancelled_event(organization_id, job.repository_id, job.id, job.plan_id)
        )
        await record_event(session, organization_id, job.id, "execution.cancelled", "system", "execution.api",
                           data={"status": "CANCELLED"}, idempotency_key="cancelled")
    await session.commit()
    return job
