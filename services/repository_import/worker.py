import asyncio
import os
import shutil
from datetime import UTC, datetime
from uuid import UUID

import structlog

from packages.database.engine import get_engine, get_session_factory
from packages.database.models.import_job import ImportJobModel, ImportJobStatus
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.models.repository_manifest import RepositoryManifestModel
from packages.shared.config import get_settings
from packages.shared.identifiers import generate_id

from .scanner.manifest_builder import ManifestBuilder

logger = structlog.get_logger(__name__)


class ImportWorker:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = get_engine(database_url)
        self.session_factory = get_session_factory(self.engine)
        self.settings = get_settings()

    async def process_job(self, job_id: UUID) -> None:
        async with self.session_factory() as session:
            job = await session.get(ImportJobModel, job_id)
            if not job:
                structlog.get_logger().error("import_job_not_found", job_id=str(job_id))
                return

            repo = await session.get(RepositoryModel, job.repository_id)
            if not repo:
                structlog.get_logger(__name__).error("repository_not_found", repository_id=str(job.repository_id))
                return

            log = structlog.get_logger(__name__).bind(job_id=str(job.id), repo_id=str(repo.id), org_id=str(repo.organization_id))

            try:
                # 1. Start Clone
                job.status = ImportJobStatus.CLONING
                job.started_at = datetime.now(UTC)
                repo.status = RepositoryStatus.IMPORTING
                await session.commit()

                workspace_dir = os.path.join(self.settings.workspace_root, str(repo.organization_id), str(repo.id))

                await self._clone_repository(repo.clone_url, job.branch, workspace_dir)

                # 2. Scanning
                job.status = ImportJobStatus.SCANNING
                await session.commit()

                builder = ManifestBuilder(
                    workspace_path=workspace_dir,
                    repo_owner=repo.owner,
                    repo_name=repo.name,
                    commit_sha=job.commit_sha,
                    default_branch=job.branch,
                )

                job.status = ImportJobStatus.BUILDING_MANIFEST
                await session.commit()

                manifest = builder.build()

                # 3. Persisting
                job.status = ImportJobStatus.PERSISTING
                await session.commit()

                manifest_model = RepositoryManifestModel(
                    id=generate_id(),
                    organization_id=repo.organization_id,
                    repository_id=repo.id,
                    version=1,
                    manifest=manifest.to_dict(),
                )
                session.add(manifest_model)

                repo.total_files = manifest.statistics.total_files
                repo.total_size_bytes = manifest.statistics.total_size_bytes
                repo.primary_language = manifest.languages.primary_language
                repo.frameworks = [f.model_dump(mode="json") for f in manifest.frameworks]

                # 4. Completed
                job.status = ImportJobStatus.COMPLETED
                job.finished_at = datetime.now(UTC)
                repo.status = RepositoryStatus.READY
                await session.commit()

                log.info("import_completed_successfully")

            except Exception as e:
                log.error("import_failed", error=str(e))
                await session.rollback()
                job.status = ImportJobStatus.FAILED
                job.error_message = str(e)
                job.finished_at = datetime.now(UTC)
                repo.status = RepositoryStatus.FAILED
                await session.commit()

    async def _clone_repository(self, clone_url: str, branch: str, target_dir: str) -> None:
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        os.makedirs(os.path.dirname(target_dir), exist_ok=True)

        proc = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            "--depth",
            "1",
            "-b",
            branch,
            clone_url,
            target_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Git clone failed: {stderr.decode()}")
