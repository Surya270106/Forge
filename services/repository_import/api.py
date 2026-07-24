from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.repository import RepositoryModel
from packages.shared.errors import ConflictError

from .schemas import ImportRepositoryRequest, ImportRepositoryResponse
from .service import RepositoryService

router = APIRouter(prefix="/api/v1/repositories", tags=["Repositories"])
logger = structlog.get_logger(__name__)

from services.auth.dependencies import get_current_user, require_permission


@router.post("/import", response_model=ImportRepositoryResponse, status_code=status.HTTP_202_ACCEPTED)
async def import_repository(
    request: ImportRepositoryRequest,
    organization_id: UUID = Depends(require_permission("repo:import")),
    session: AsyncSession = Depends(get_session),
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


@router.get("/imported")
async def list_imported_repositories(organization_id: UUID = Depends(require_permission("repo:read")), session: AsyncSession = Depends(get_session)):
    stmt = select(RepositoryModel).where(RepositoryModel.organization_id == organization_id)
    result = await session.execute(stmt)
    repos = result.scalars().all()

    return {
        "repositories": [
            {
                "id": str(repo.id),
                "name": repo.name,
                "owner": repo.owner,
                "clone_url": repo.clone_url,
                "status": repo.status.value,
                "default_branch": repo.default_branch,
                "created_at": repo.created_at.isoformat() if repo.created_at else None,
            }
            for repo in repos
        ]
    }


@router.get("/github-repos")
async def list_github_repositories(user: dict = Depends(get_current_user)):
    token = user.get("github_token")
    if not token:
        raise HTTPException(status_code=400, detail="GitHub token not found. Please log in with GitHub again.")

    async with httpx.AsyncClient() as client:
        res = await client.get(
            "https://api.github.com/user/repos?per_page=100&sort=updated",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
        )
        if res.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch repositories from GitHub")

        repos = res.json()
        return {
            "repositories": [
                {
                    "name": repo["name"],
                    "owner": repo["owner"]["login"],
                    "clone_url": repo["clone_url"],
                    "is_private": repo["private"],
                    "description": repo["description"],
                    "default_branch": repo["default_branch"],
                }
                for repo in repos
            ]
        }
