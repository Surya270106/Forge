import re
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

from services.auth.dependencies import get_current_user, require_github_token, require_permission


@router.post("/import", response_model=ImportRepositoryResponse, status_code=status.HTTP_202_ACCEPTED)
async def import_repository(
    request: ImportRepositoryRequest,
    organization_id: UUID = Depends(require_permission("repo:import")),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    token = await require_github_token(user, session)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", request.owner) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", request.name):
        raise HTTPException(status_code=400, detail="Invalid GitHub repository identity")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            remote = await client.get(
                f"https://api.github.com/repos/{request.owner}/{request.name}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="GitHub is unavailable; retry the import") from None
    if remote.status_code in (401, 403, 404):
        raise HTTPException(status_code=403, detail="GitHub access is unavailable; reconnect or check repository access")
    if remote.status_code != 200:
        raise HTTPException(status_code=503, detail="GitHub could not confirm repository access")
    metadata = remote.json()
    owner = metadata.get("owner", {}).get("login")
    name = metadata.get("name")
    permissions = metadata.get("permissions") or {}
    if not isinstance(owner, str) or not isinstance(name, str) or not permissions.get("pull"):
        raise HTTPException(status_code=403, detail="GitHub did not confirm repository read access")
    if f"{owner}/{name}".casefold() != f"{request.owner}/{request.name}".casefold():
        raise HTTPException(status_code=400, detail="Repository identity changed; select it again")
    branch = metadata.get("default_branch")
    if not isinstance(branch, str) or not branch or request.branch != branch:
        raise HTTPException(status_code=400, detail="Select the repository's current default branch")
    canonical = f"https://github.com/{owner}/{name}.git"
    verified_request = request.model_copy(update={
        "owner": owner, "name": name, "clone_url": canonical,
        "branch": branch, "is_private": bool(metadata.get("private")),
    })
    service = RepositoryService(session)
    try:
        repo, job = await service.register_repository_for_import(organization_id, verified_request, requested_by=UUID(user["id"]))
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

    # Fetch latest indexing jobs for these repos
    from packages.database.models.memory import IndexingJobModel
    from sqlalchemy import desc

    jobs_stmt = select(IndexingJobModel).where(IndexingJobModel.organization_id == organization_id).order_by(desc(IndexingJobModel.created_at))
    jobs = (await session.execute(jobs_stmt)).scalars().all()
    
    latest_jobs = {}
    for job in jobs:
        if job.repository_id not in latest_jobs:
            progress = 0
            if getattr(job, 'total_files', 0) > 0:
                progress = int((job.files_processed / job.total_files) * 100)
            latest_jobs[job.repository_id] = {
                "status": job.status.value,
                "progress": progress
            }

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
                "indexing_status": latest_jobs.get(repo.id, {}).get("status", "NEEDS_INDEXING"),
                "indexing_progress": latest_jobs.get(repo.id, {}).get("progress", 0),
            }
            for repo in repos
        ]
    }


@router.get("/github-repos")
async def list_github_repositories(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    token = await require_github_token(user, session)

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
