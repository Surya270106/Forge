from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.execution import ExecutionJobModel, ExecutionLogModel, ExecutionStatus
from packages.database.models.planning import PlanModel, PlanStatus
from packages.shared.errors import ConflictError, ErrorCategory, NotFoundError
from packages.shared.identifiers import OrganizationId, generate_id

from .schemas import ExecutionJobResponse, ExecutionLogResponse, StartExecutionRequest

router = APIRouter(prefix="/api/v1/executions", tags=["execution"])


from fastapi import Header


async def get_tenant_organization_id(
    x_organization_id: str | None = Header("00000000-0000-0000-0000-000000000000", alias="X-Organization-Id"),
) -> OrganizationId:
    from packages.database.tenant import set_tenant

    org_id = OrganizationId(UUID(x_organization_id))
    set_tenant(org_id)
    return org_id


async def get_db_session(org_id: OrganizationId = Depends(get_tenant_organization_id)):
    async for session in get_session():
        yield session


@router.post("/plans/{plan_id}", response_model=ExecutionJobResponse)
async def start_execution(
    plan_id: UUID,
    request: StartExecutionRequest,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_db_session),
):
    plan = await session.get(PlanModel, plan_id)
    if not plan or plan.organization_id != organization_id:
        raise NotFoundError(code="plan_not_found", message="Plan not found", category=ErrorCategory.NOT_FOUND)  # type: ignore

    if plan.status != PlanStatus.APPROVED:
        raise ConflictError(
            code="plan_not_approved",
            message="Plan must be APPROVED to execute",
            category=ErrorCategory.CONFLICT,
        )

    job = ExecutionJobModel(
        id=generate_id(),
        organization_id=organization_id,
        repository_id=plan.repository_id,
        plan_id=plan_id,
        status=ExecutionStatus.PENDING,
        commit_sha_before="HEAD",
    )
    session.add(job)

    from .events import ExecutionEventPublisher, create_execution_started_event

    publisher = ExecutionEventPublisher(session)
    event = create_execution_started_event(organization_id, plan.repository_id, job.id, plan_id)
    await publisher.publish(event)

    await session.commit()
    return job


@router.get("/{job_id}", response_model=ExecutionJobResponse)
async def get_execution_status(
    job_id: UUID,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_db_session),
):
    job = await session.get(ExecutionJobModel, job_id)
    if not job or job.organization_id != organization_id:
        raise NotFoundError(code="job_not_found", message="Job not found", category=ErrorCategory.NOT_FOUND)  # type: ignore
    return job


@router.get("/{job_id}/logs", response_model=list[ExecutionLogResponse])
async def get_execution_logs(
    job_id: UUID,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(ExecutionLogModel)
        .where(
            ExecutionLogModel.execution_job_id == job_id,
            ExecutionLogModel.organization_id == organization_id,
        )
        .order_by(ExecutionLogModel.created_at.asc())
    )

    logs = (await session.execute(stmt)).scalars().all()
    return logs
