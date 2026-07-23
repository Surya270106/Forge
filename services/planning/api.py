from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.planning import TaskEdgeModel
from packages.shared.identifiers import OrganizationId

from .schemas import CreatePlanRequest, PlanResponse
from .service import PlanningService

router = APIRouter(tags=["planning"])


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


@router.post("/api/v1/repositories/{repository_id}/plans", response_model=PlanResponse)
async def create_plan(
    repository_id: UUID,
    request: CreatePlanRequest,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_db_session),
):
    service = PlanningService(session, organization_id)
    plan = await service.create_plan(repository_id, intent=request.intent, memory_version_id=request.memory_version_id)

    # Fetch edges separately to attach to response schema easily since we didn't setup the reverse relation backref
    stmt = select(TaskEdgeModel).where(TaskEdgeModel.plan_id == plan.id)
    edges = (await session.execute(stmt)).scalars().all()

    plan_dict = plan.__dict__.copy()
    plan_dict["edges"] = edges
    return plan_dict


@router.get("/api/v1/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: UUID,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_db_session),
):
    service = PlanningService(session, organization_id)
    plan = await service.get_plan(plan_id)

    stmt = select(TaskEdgeModel).where(TaskEdgeModel.plan_id == plan.id)
    edges = (await session.execute(stmt)).scalars().all()

    plan_dict = plan.__dict__.copy()
    plan_dict["edges"] = edges
    return plan_dict


@router.post("/api/v1/plans/{plan_id}/approve", response_model=PlanResponse)
async def approve_plan(
    plan_id: UUID,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_db_session),
):
    service = PlanningService(session, organization_id)
    plan = await service.approve_plan(plan_id)

    stmt = select(TaskEdgeModel).where(TaskEdgeModel.plan_id == plan.id)
    edges = (await session.execute(stmt)).scalars().all()

    plan_dict = plan.__dict__.copy()
    plan_dict["edges"] = edges
    return plan_dict
