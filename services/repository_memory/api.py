from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.memory import (
    SymbolModel,
)
from packages.shared.identifiers import OrganizationId
from packages.shared.pagination import PaginatedResponse

from .schemas import (
    IndexingJobResponse,
    IndexRepositoryRequest,
    SymbolResponse,
)
from .service import MemoryService

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


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


@router.post("/repositories/{repository_id}/index", response_model=IndexingJobResponse)
async def start_indexing(
    repository_id: UUID,
    request: IndexRepositoryRequest,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_db_session),
):
    service = MemoryService(session, organization_id)
    job = await service.start_indexing(repository_id, branch=request.branch, force_reindex=request.force_reindex)
    return job


@router.get("/jobs/{job_id}", response_model=IndexingJobResponse)
async def get_indexing_status(
    job_id: UUID,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_db_session),
):
    service = MemoryService(session, organization_id)
    return await service.get_job_status(job_id)


@router.get("/repositories/{repository_id}/symbols", response_model=PaginatedResponse[SymbolResponse])
async def list_symbols(
    repository_id: UUID,
    query: str | None = Query(None, description="Search by symbol name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_db_session),
):
    # Enforce tenant isolation via query
    stmt = select(SymbolModel).where(SymbolModel.repository_id == repository_id, SymbolModel.organization_id == organization_id)
    if query:
        stmt = stmt.where(SymbolModel.name.ilike(f"%{query}%"))

    # Pagination
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    result = await session.execute(stmt)
    symbols = result.scalars().all()

    # In a real app we'd also count total for correct pagination metadata
    return PaginatedResponse(
        items=symbols,
        total=len(symbols),  # mock
        page=page,
        page_size=page_size,
        total_pages=1,
        has_next=False,
        has_previous=False,
    )
