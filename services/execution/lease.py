"""PostgreSQL owns execution state; a generation fences expired workers."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.execution import ExecutionJobModel, ExecutionStatus


async def claim_execution(
    session: AsyncSession, job_id: UUID, organization_id: UUID, owner: str, lease_seconds: int,
    *, commit: bool = True,
) -> int | None:
    job = (
        await session.execute(
            select(ExecutionJobModel).where(
                ExecutionJobModel.id == job_id, ExecutionJobModel.organization_id == organization_id
            ).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not job or job.status != ExecutionStatus.PENDING:
        return None
    job.lease_generation += 1
    job.lease_owner = owner
    job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
    job.status = ExecutionStatus.RUNNING
    job.started_at = datetime.now(UTC)
    if commit:
        await session.commit()
    return job.lease_generation


async def renew_execution(
    session: AsyncSession, job_id: UUID, organization_id: UUID, owner: str, generation: int, lease_seconds: int
) -> bool:
    now = datetime.now(UTC)
    result = await session.execute(
        update(ExecutionJobModel).where(
            ExecutionJobModel.id == job_id,
            ExecutionJobModel.organization_id == organization_id,
            ExecutionJobModel.status == ExecutionStatus.RUNNING,
            ExecutionJobModel.lease_owner == owner,
            ExecutionJobModel.lease_generation == generation,
            ExecutionJobModel.lease_expires_at > now,
        ).values(lease_expires_at=now + timedelta(seconds=lease_seconds))
    )
    await session.commit()
    return getattr(result, "rowcount", 0) == 1


def owns_execution(job: ExecutionJobModel, owner: str, generation: int) -> bool:
    return (
        job.status == ExecutionStatus.RUNNING
        and job.lease_owner == owner
        and job.lease_generation == generation
        and job.lease_expires_at is not None
        and job.lease_expires_at > datetime.now(UTC)
    )
