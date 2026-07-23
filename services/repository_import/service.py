from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.import_job import ImportJobModel, ImportJobStatus
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.shared.errors import ConflictError, ErrorCategory
from packages.shared.identifiers import generate_id

from .schemas import ImportRepositoryRequest

logger = structlog.get_logger(__name__)


class RepositoryService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_repository_by_name(self, organization_id: UUID, owner: str, name: str) -> RepositoryModel | None:
        stmt = select(RepositoryModel).where(
            RepositoryModel.organization_id == organization_id,
            RepositoryModel.owner == owner,
            RepositoryModel.name == name,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def register_repository_for_import(self, organization_id: UUID, req: ImportRepositoryRequest) -> tuple[RepositoryModel, ImportJobModel]:
        # Check if repository already exists for this org
        repo = await self.get_repository_by_name(organization_id, req.owner, req.name)

        if not repo:
            # Create new repository
            repo = RepositoryModel(
                id=generate_id(),
                organization_id=organization_id,
                owner=req.owner,
                name=req.name,
                full_name=f"{req.owner}/{req.name}",
                clone_url=req.clone_url,
                default_branch=req.branch,
                is_private=req.is_private,
                status=RepositoryStatus.PENDING,
            )
            self.session.add(repo)
            await self.session.flush()
        else:
            if repo.status in [RepositoryStatus.IMPORTING]:
                raise ConflictError(
                    code="REPO_IMPORT_IN_PROGRESS",
                    message="Repository import is already in progress.",
                    category=ErrorCategory.CONFLICT,
                )

            repo.status = RepositoryStatus.PENDING
            repo.clone_url = req.clone_url

        # Create import job
        job = ImportJobModel(
            id=generate_id(),
            organization_id=organization_id,
            repository_id=repo.id,
            status=ImportJobStatus.PENDING,
            branch=req.branch,
        )
        self.session.add(job)

        try:
            await self.session.commit()
            await self.session.refresh(repo)
            await self.session.refresh(job)
        except IntegrityError as e:
            await self.session.rollback()
            logger.error("integrity_error_during_import_registration", error=str(e))
            raise ConflictError(
                code="REPO_REGISTRATION_CONFLICT",
                message="A conflict occurred while registering the repository.",
                category=ErrorCategory.CONFLICT,
            )

        return repo, job
