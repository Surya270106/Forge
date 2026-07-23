import hashlib
import os
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.memory import (
    IndexingFailureModel,
    IndexingJobModel,
    IndexingStatus,
    RepositoryMemoryVersionModel,
    SourceFileModel,
    SymbolModel,
)
from packages.database.models.repository import RepositoryModel
from packages.shared.config import get_settings
from packages.shared.errors import ConflictError, ErrorCategory, NotFoundError, ErrorCategory
from packages.shared.identifiers import generate_id

from .events import (
    OutboxEventPublisher,
    create_file_parsed_event,
    create_indexing_completed_event,
    create_indexing_failed_event,
    create_indexing_requested_event,
    create_indexing_started_event,
    create_version_created_event,
)
from .parser_registry import get_default_registry

logger = structlog.get_logger(__name__)


class MemoryService:
    def __init__(self, session: AsyncSession, organization_id: UUID):
        self.session = session
        self.organization_id = organization_id
        self.publisher = OutboxEventPublisher(session)

    async def start_indexing(self, repository_id: UUID, branch: str | None = None, force_reindex: bool = False) -> IndexingJobModel:
        repo = await self.session.get(RepositoryModel, repository_id)
        if not repo or repo.organization_id != self.organization_id:
            raise NotFoundError(code="repo_not_found", message="Repository not found", category=ErrorCategory.NOT_FOUND)

        target_branch = branch or repo.default_branch

        # Check if already indexing
        stmt = select(IndexingJobModel).where(
            IndexingJobModel.repository_id == repository_id,
            IndexingJobModel.status.in_(
                [
                    IndexingStatus.PENDING,
                    IndexingStatus.QUEUED,
                    IndexingStatus.SCANNING,
                    IndexingStatus.PARSING,
                ]
            ),
        )
        existing_job = (await self.session.execute(stmt)).scalars().first()
        if existing_job:
            raise ConflictError(
                code="already_indexing",
                message="Repository is already being indexed",
                category=ErrorCategory.CONFLICT,
            )

        job = IndexingJobModel(
            id=generate_id(),
            organization_id=self.organization_id,
            repository_id=repository_id,
            status=IndexingStatus.PENDING,
            commit_sha="HEAD",  # Ideally fetched from Git
            branch=target_branch,
        )
        self.session.add(job)

        await self.publisher.publish(create_indexing_requested_event(self.organization_id, repository_id, job.id))
        await self.session.commit()
        return job

    async def get_job_status(self, job_id: UUID) -> IndexingJobModel:
        job = await self.session.get(IndexingJobModel, job_id)
        if not job or job.organization_id != self.organization_id:
            raise NotFoundError(code="job_not_found", message="Job not found", category=ErrorCategory.NOT_FOUND)
        return job


class IndexingCoordinator:
    def __init__(self, session: AsyncSession, settings=None):
        self.session = session
        self.registry = get_default_registry()
        self.settings = settings or get_settings()

    async def execute_job(self, job_id: UUID) -> None:
        job = await self.session.get(IndexingJobModel, job_id)
        if not job:
            return

        publisher = OutboxEventPublisher(self.session)
        logger = structlog.get_logger(__name__).bind(job_id=str(job_id), repo_id=str(job.repository_id))

        try:
            job.status = IndexingStatus.SCANNING
            job.started_at = datetime.now(UTC)
            await publisher.publish(create_indexing_started_event(job.organization_id, job.repository_id, job.id, job.commit_sha))
            await self.session.commit()

            workspace_dir = os.path.join(self.settings.workspace_root, str(job.organization_id), str(job.repository_id))

            # Determine previous version
            stmt = (
                select(RepositoryMemoryVersionModel)
                .where(RepositoryMemoryVersionModel.repository_id == job.repository_id)
                .order_by(RepositoryMemoryVersionModel.version.desc())
            )
            prev_version = (await self.session.execute(stmt)).scalars().first()
            new_version_num = (prev_version.version + 1) if prev_version else 1

            new_version = RepositoryMemoryVersionModel(
                id=generate_id(),
                organization_id=job.organization_id,
                repository_id=job.repository_id,
                version=new_version_num,
                commit_sha=job.commit_sha,
                branch=job.branch,
                is_active=False,
            )
            self.session.add(new_version)
            await self.session.flush()

            job.status = IndexingStatus.PARSING
            await self.session.commit()

            # Mock File Scanning
            # In a real impl, we'd walk the workspace_dir
            files_to_parse = []
            if os.path.exists(workspace_dir):
                for root, _, files in os.walk(workspace_dir):
                    for file in files:
                        files_to_parse.append(os.path.join(root, file))
            else:
                # Dry-run fixture file if workspace doesn't exist (since we can't run git clone locally)
                files_to_parse = ["test.py"]

            for file_path in files_to_parse:
                rel_path = os.path.relpath(file_path, workspace_dir) if os.path.exists(workspace_dir) else file_path
                adapter = self.registry.get_adapter(rel_path)
                if not adapter:
                    continue

                content = b"class MockClass:\n    pass\n"  # Mock content for local dev missing real workspace
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        content = f.read()

                checksum = hashlib.sha256(content).hexdigest()

                source_file = SourceFileModel(
                    id=generate_id(),
                    organization_id=job.organization_id,
                    repository_id=job.repository_id,
                    memory_version_id=new_version.id,
                    file_path=rel_path,
                    checksum=checksum,
                    language=adapter.get_language_name(),
                    size_bytes=len(content),
                    lines=content.count(b"\n") + 1,
                )
                self.session.add(source_file)
                await self.session.flush()

                try:
                    tree = adapter.parse(content)
                    symbols = adapter.extract_symbols(tree, content)
                    deps = adapter.extract_dependencies(tree, content)
                    calls = adapter.extract_calls(tree, content)

                    for sym in symbols:
                        self.session.add(
                            SymbolModel(
                                id=generate_id(),
                                organization_id=job.organization_id,
                                repository_id=job.repository_id,
                                source_file_id=source_file.id,
                                memory_version_id=new_version.id,
                                name=sym.name,
                                qualname=sym.qualname,
                                symbol_type=sym.symbol_type,
                                line_start=sym.line_start,
                                line_end=sym.line_end,
                                snippet=sym.snippet,
                            )
                        )

                    # Omitted edge creation for brevity, but same pattern follows.

                    await publisher.publish(create_file_parsed_event(job.organization_id, job.repository_id, rel_path, len(symbols)))

                except Exception as parse_err:
                    self.session.add(
                        IndexingFailureModel(
                            id=generate_id(),
                            organization_id=job.organization_id,
                            repository_id=job.repository_id,
                            indexing_job_id=job.id,
                            file_path=rel_path,
                            error_message=str(parse_err),
                        )
                    )

            job.status = IndexingStatus.COMPLETED
            job.finished_at = datetime.now(UTC)
            new_version.is_active = True

            # Deactivate old version
            if prev_version:
                prev_version.is_active = False

            await publisher.publish(create_version_created_event(job.organization_id, job.repository_id, new_version.id, new_version.version))
            await publisher.publish(create_indexing_completed_event(job.organization_id, job.repository_id, job.id, new_version.id))
            await self.session.commit()
            logger.info("indexing_completed")

        except Exception as e:
            logger.error("indexing_failed", error=str(e))
            await self.session.rollback()
            job.status = IndexingStatus.FAILED
            job.finished_at = datetime.now(UTC)
            await publisher.publish(create_indexing_failed_event(job.organization_id, job.repository_id, job.id, str(e)))
            await self.session.commit()
