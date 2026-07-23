from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.execution import ExecutionJobModel, ExecutionLogModel, ExecutionStatus, MutationModel
from packages.database.models.planning import PlanModel, PlanStatus
from packages.shared.errors import ConflictError, ErrorCategory, NotFoundError
from packages.shared.identifiers import OrganizationId, generate_id

from .schemas import ExecutionJobResponse, ExecutionLogResponse, StartExecutionRequest

router = APIRouter(prefix="/api/v1/executions", tags=["execution"])


from services.auth.dependencies import get_tenant_context as get_tenant_organization_id


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

@router.get("/{job_id}/mutations")
async def get_execution_mutations(
    job_id: UUID,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(MutationModel)
        .where(
            MutationModel.execution_job_id == job_id,
            MutationModel.organization_id == organization_id,
        )
    )
    mutations = (await session.execute(stmt)).scalars().all()

    return {
        "mutations": [
            {
                "id": str(m.id),
                "file_path": m.file_path,
                "mutation_type": m.mutation_type,
                "diff_hunk": m.diff_hunk
            }
            for m in mutations
        ]
    }
