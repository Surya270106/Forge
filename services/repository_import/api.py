from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.shared.errors import ConflictError

from .schemas import ImportRepositoryRequest, ImportRepositoryResponse
from .service import RepositoryService

router = APIRouter(prefix="/api/v1/repositories", tags=["Repositories"])
logger = structlog.get_logger(__name__)


async def get_tenant_context(
    x_organization_id: str = Header(..., description="Organization ID"),
    # other tenant contexts can be injected here
) -> UUID:
    from packages.database.tenant import set_tenant

    try:
        org_id = UUID(x_organization_id)
        set_tenant(org_id)
        return org_id
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format")


async def get_db_session(org_id: UUID = Depends(get_tenant_context)):
    async for session in get_session():
        yield session


@router.post("/import", response_model=ImportRepositoryResponse, status_code=status.HTTP_202_ACCEPTED)
async def import_repository(
    request: ImportRepositoryRequest,
    organization_id: UUID = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
):
    service = RepositoryService(session)
    try:
        repo, job = await service.register_repository_for_import(organization_id, request)
    except ConflictError as e:
        logger.warning("import_repository_conflict", error=str(e), org_id=str(organization_id))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    except Exception as e:
        logger.error("import_repository_failed", error=str(e), org_id=str(organization_id))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

    return ImportRepositoryResponse(
        repository_id=repo.id,
        import_job_id=job.id,
        status=job.status.value,
        message="Repository import scheduled successfully.",
    )
