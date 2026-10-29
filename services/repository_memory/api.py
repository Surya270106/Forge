from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.memory import (
    SymbolModel,
)
from packages.shared.identifiers import OrganizationId
from packages.shared.pagination import PaginatedResponse
from services.auth.dependencies import require_permission

from .schemas import (
    IndexingJobResponse,
    IndexRepositoryRequest,
    SymbolResponse,
)
from .service import MemoryService

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


@router.post("/repositories/{repository_id}/index", response_model=IndexingJobResponse)
async def start_indexing(
    repository_id: UUID,
    request: IndexRepositoryRequest,
    organization_id: OrganizationId = Depends(require_permission("repo:import")),
    session: AsyncSession = Depends(get_session),
):
    service = MemoryService(session, organization_id)
    job = await service.start_indexing(repository_id, branch=request.branch, force_reindex=request.force_reindex)
    return job


@router.get("/jobs/{job_id}", response_model=IndexingJobResponse)
async def get_indexing_status(
    job_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("repo:read")),
    session: AsyncSession = Depends(get_session),
):
    service = MemoryService(session, organization_id)
    return await service.get_job_status(job_id)


@router.get("/repositories/{repository_id}/symbols", response_model=PaginatedResponse[SymbolResponse])
async def list_symbols(
    repository_id: UUID,
    query: str | None = Query(None, description="Search by symbol name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    organization_id: OrganizationId = Depends(require_permission("repo:read")),
    session: AsyncSession = Depends(get_session),
):
    filters = (SymbolModel.repository_id == repository_id, SymbolModel.organization_id == organization_id)
    stmt = select(SymbolModel).where(*filters)
    count_stmt = select(func.count()).select_from(SymbolModel).where(*filters)
    if query:
        search_filter = SymbolModel.name.ilike(f"%{query}%")
        stmt = stmt.where(search_filter)
        count_stmt = count_stmt.where(search_filter)

    # Pagination
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    total = (await session.execute(count_stmt)).scalar_one()
    result = await session.execute(stmt)
    symbols = result.scalars().all()

    return PaginatedResponse(
        items=symbols,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
        has_next=page * page_size < total,
        has_previous=page > 1,
    )
