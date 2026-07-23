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


from services.auth.dependencies import get_tenant_context as get_tenant_organization_id


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

from packages.database.models.planning import PlanModel


@router.get("/api/v1/plans")
async def list_plans(
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = select(PlanModel).where(PlanModel.organization_id == organization_id).order_by(PlanModel.created_at.desc())
    result = await session.execute(stmt)
    plans = result.scalars().all()

    return {
        "plans": [
            {
                "id": str(p.id),
                "intent": p.intent,
                "status": p.status.value,
                "repository_id": str(p.repository_id),
                "created_at": p.created_at.isoformat() if p.created_at else None
            }
            for p in plans
        ]
    }
