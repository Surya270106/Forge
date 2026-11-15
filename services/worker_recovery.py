"""Mark interrupted worker jobs failed without replaying filesystem side effects."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.execution import ExecutionJobModel, ExecutionStatus, MutationModel
from packages.database.models.import_job import ImportJobModel, ImportJobStatus
from packages.database.models.planning import PlanModel, PlanStatus
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.models.verification import (
    RepairAttemptModel,
    RepairAttemptStatus,
    VerificationJobModel,
    VerificationStatus,
)
from services.execution.events import ExecutionEventPublisher, create_execution_requested_event
from services.execution.flight_recorder import record_event


async def fail_stale_jobs(session: AsyncSession, organization_id: UUID, *, execution_timeout_seconds: int = 600) -> dict[str, int]:
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=max(execution_timeout_seconds, 600) + 120)
    counts = {"execution": 0, "verification": 0, "import": 0, "repair": 0}

    executions = (
        (
            await session.execute(
                select(ExecutionJobModel)
                .where(
                    ExecutionJobModel.status == ExecutionStatus.RUNNING,
                    ExecutionJobModel.organization_id == organization_id,
                    or_(
                        ExecutionJobModel.lease_expires_at < now,
                        and_(ExecutionJobModel.lease_expires_at.is_(None), ExecutionJobModel.started_at < cutoff),
                    ),
                )
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for job in executions:
        expired_owner = getattr(job, "lease_owner", None)
        if not getattr(job, "cancellation_requested_at", None) and getattr(job, "lease_owner", None) and getattr(job, "lease_generation", 0) < 3:
            await session.execute(
                update(MutationModel).where(
                    MutationModel.execution_job_id == job.id,
                    MutationModel.organization_id == organization_id,
                ).values(is_reverted=True)
            )
            job.status = ExecutionStatus.PENDING
            job.lease_owner = None
            job.lease_expires_at = None
            await record_event(session, organization_id, job.id, "worker.lease_expired", "system", "worker.recovery",
                               actor_id=expired_owner, data={"generation": job.lease_generation}, idempotency_key=f"lease-expired-{job.lease_generation}")
            await record_event(session, organization_id, job.id, "execution.recovered", "system", "worker.recovery",
                               data={"generation": job.lease_generation}, idempotency_key=f"recovered-{job.lease_generation}")
            await ExecutionEventPublisher(session).publish(
                create_execution_requested_event(organization_id, job.repository_id, job.id, job.plan_id)
            )
            counts["execution"] += 1
            continue
        job.status = ExecutionStatus.FAILED
        job.finished_at = now
        job.error_message = ("Cancellation was interrupted; inspect the sandbox before retrying"
                             if getattr(job, "cancellation_requested_at", None) else
                             "Worker interrupted or execution timed out; inspect the workspace before retrying")
        await record_event(session, organization_id, job.id, "worker.lease_expired", "system", "worker.recovery",
                           actor_id=expired_owner, data={"generation": job.lease_generation}, idempotency_key=f"lease-expired-{job.lease_generation}")
        await record_event(session, organization_id, job.id,
                           "execution.cancellation_failed" if getattr(job, "cancellation_requested_at", None) else "execution.failed",
                           "system", "worker.recovery", data={"reason_code": "LEASE_EXPIRED"},
                           idempotency_key=f"lease-failed-{job.lease_generation}")
        plan = await session.get(PlanModel, job.plan_id)
        if plan and plan.organization_id == job.organization_id and plan.status == PlanStatus.EXECUTING:
            plan.status = PlanStatus.FAILED
        repair = (
            await session.execute(
                select(RepairAttemptModel).where(
                    RepairAttemptModel.repair_execution_id == job.id,
                    RepairAttemptModel.organization_id == job.organization_id,
                    RepairAttemptModel.status == RepairAttemptStatus.EXECUTING,
                )
            )
        ).scalar_one_or_none()
        if repair:
            repair.status = RepairAttemptStatus.FAILED
            repair.error_message = "Repair execution was interrupted"
        counts["execution"] += 1

    verifications = (
        (
            await session.execute(
                select(VerificationJobModel)
                .where(
                    VerificationJobModel.status == VerificationStatus.RUNNING,
                    VerificationJobModel.organization_id == organization_id,
                    VerificationJobModel.started_at < cutoff,
                )
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for job in verifications:
        job.status = VerificationStatus.FAILED
        job.finished_at = now
        repair = (
            await session.execute(
                select(RepairAttemptModel).where(
                    RepairAttemptModel.repair_execution_id == job.execution_job_id,
                    RepairAttemptModel.organization_id == job.organization_id,
                    RepairAttemptModel.status == RepairAttemptStatus.REVERIFYING,
                )
            )
        ).scalar_one_or_none()
        if repair:
            repair.status = RepairAttemptStatus.FAILED
            repair.error_message = "Repair verification was interrupted"
        counts["verification"] += 1

    imports = (
        (
            await session.execute(
                select(ImportJobModel)
                .where(
                    ImportJobModel.status.in_(
                        [
                            ImportJobStatus.AUTHENTICATING,
                            ImportJobStatus.CLONING,
                            ImportJobStatus.SCANNING,
                            ImportJobStatus.DETECTING,
                            ImportJobStatus.BUILDING_MANIFEST,
                            ImportJobStatus.PERSISTING,
                        ]
                    ),
                    ImportJobModel.organization_id == organization_id,
                    ImportJobModel.updated_at < cutoff,
                )
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for job in imports:
        job.status = ImportJobStatus.FAILED
        job.finished_at = now
        job.error_message = "Import worker was interrupted; inspect any existing workspace before retrying"
        repo = await session.get(RepositoryModel, job.repository_id)
        if repo and repo.organization_id == job.organization_id and repo.status == RepositoryStatus.IMPORTING:
            repo.status = RepositoryStatus.FAILED
        counts["import"] += 1

    repairs = (
        (
            await session.execute(
                select(RepairAttemptModel)
                .where(
                    RepairAttemptModel.status == RepairAttemptStatus.PLANNING,
                    RepairAttemptModel.organization_id == organization_id,
                    RepairAttemptModel.updated_at < cutoff,
                )
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for repair in repairs:
        repair.status = RepairAttemptStatus.FAILED
        repair.error_message = "Repair planning worker was interrupted; request a new proposal"
        counts["repair"] += 1

    if any(counts.values()):
        await session.commit()
    return counts
