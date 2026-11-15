import asyncio
import base64
import os
import shutil
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select, update

from packages.database.engine import get_engine, get_session_factory
from packages.database.models.auth import UserModel
from packages.database.models.import_job import ImportJobModel, ImportJobStatus
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.models.repository_manifest import RepositoryManifestModel
from packages.shared.config import get_settings
from packages.shared.crypto import CryptoService
from packages.shared.identifiers import generate_id

from .scanner.manifest_builder import ManifestBuilder

logger = structlog.get_logger(__name__)


async def claim_import_job(session, job_id: UUID) -> bool:
    claimed = await session.execute(
        update(ImportJobModel)
        .where(ImportJobModel.id == job_id, ImportJobModel.status == ImportJobStatus.PENDING)
        .values(status=ImportJobStatus.AUTHENTICATING, started_at=datetime.now(UTC))
        .returning(ImportJobModel.id)
    )
    if claimed.scalar_one_or_none() is None:
        await session.rollback()
        return False
    await session.commit()
    return True


class ImportWorker:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = get_engine(database_url)
        self.session_factory = get_session_factory(self.engine)
        self.settings = get_settings()

    async def process_job(self, job_id: UUID) -> None:
        async with self.session_factory() as session:
            # Commit the claim before filesystem or network work. A duplicate
            # event sees a non-pending state and cannot start another clone.
            if not await claim_import_job(session, job_id):
                return
            job = await session.get(ImportJobModel, job_id)
            if not job:
                structlog.get_logger().error("import_job_not_found", job_id=str(job_id))
                return

            repo = await session.get(RepositoryModel, job.repository_id)
            log = structlog.get_logger(__name__).bind(job_id=str(job.id), repo_id=str(job.repository_id), org_id=str(job.organization_id))

            try:
                if not repo or repo.organization_id != job.organization_id:
                    raise ValueError("Repository unavailable for import")
                repo.status = RepositoryStatus.IMPORTING
                await session.commit()
                requester = (job.metadata_ or {}).get("requested_by")
                user = await session.get(UserModel, UUID(requester)) if requester else None
                if not user or not user.is_active or not user.github_token:
                    raise ValueError("GitHub access is unavailable; reconnect before importing")
                token = CryptoService.decrypt(user.github_token)

                # 1. Start Clone
                job.status = ImportJobStatus.CLONING
                job.started_at = datetime.now(UTC)
                await session.commit()

                workspace_dir = os.path.join(self.settings.workspace_root, str(repo.organization_id), str(repo.id))

                await self._clone_repository(repo.clone_url, job.branch, workspace_dir, token, job.id)
                revision = await self._git_revision(workspace_dir)
                job.commit_sha = revision
                repo.commit_sha = revision

                # 2. Scanning
                job.status = ImportJobStatus.SCANNING
                await session.commit()

                builder = ManifestBuilder(
                    workspace_path=workspace_dir,
                    repo_owner=repo.owner,
                    repo_name=repo.name,
                    commit_sha=job.commit_sha or "",
                    default_branch=job.branch,
                )

                job.status = ImportJobStatus.BUILDING_MANIFEST
                await session.commit()

                manifest = builder.build()

                # 3. Persisting
                job.status = ImportJobStatus.PERSISTING
                await session.commit()

                stmt = select(RepositoryManifestModel).where(RepositoryManifestModel.repository_id == repo.id).order_by(RepositoryManifestModel.version.desc())
                prev_manifest = (await session.execute(stmt)).scalars().first()
                new_version = (prev_manifest.version + 1) if prev_manifest else 1

                manifest_model = RepositoryManifestModel(
                    id=generate_id(),
                    organization_id=repo.organization_id,
                    repository_id=repo.id,
                    version=new_version,
                    manifest=manifest.to_dict(),
                )
                session.add(manifest_model)

                repo.total_files = manifest.statistics.total_files
                repo.total_size_bytes = manifest.statistics.total_size_bytes
                repo.primary_language = manifest.languages.primary_language
                repo.frameworks = [f.model_dump(mode="json") for f in manifest.frameworks]  # type: ignore

                # 4. Completed
                locked_job = (
                    await session.execute(
                        select(ImportJobModel).where(ImportJobModel.id == job.id)
                        .with_for_update().execution_options(populate_existing=True)
                    )
                ).scalar_one()
                if locked_job.status != ImportJobStatus.PERSISTING:
                    raise RuntimeError("Import was interrupted before completion")
                job.status = ImportJobStatus.COMPLETED
                job.finished_at = datetime.now(UTC)
                repo.status = RepositoryStatus.READY

                # start_indexing commits the index request and import completion
                # together. A replay cannot lose an index event after success.
                from services.repository_memory.service import MemoryService
                memory_service = MemoryService(session, repo.organization_id)
                await memory_service.start_indexing(repo.id, branch=job.branch)

                log.info("import_completed_successfully")

            except Exception as e:
                log.error("import_failed", error_type=type(e).__name__)
                await session.rollback()
                locked_job = (
                    await session.execute(
                        select(ImportJobModel).where(ImportJobModel.id == job_id)
                        .with_for_update().execution_options(populate_existing=True)
                    )
                ).scalar_one()
                # Recovery may have failed the stale claim while the worker
                # was blocked. Never overwrite a terminal state.
                if locked_job.status in {ImportJobStatus.COMPLETED, ImportJobStatus.FAILED, ImportJobStatus.CANCELLED}:
                    await session.rollback()
                    return
                job.status = ImportJobStatus.FAILED
                job.error_message = (
                    str(e) if isinstance(e, (FileExistsError, TimeoutError))
                    else "Repository import failed; check worker connectivity and GitHub access"
                )
                job.finished_at = datetime.now(UTC)
                if repo and repo.organization_id == job.organization_id:
                    repo.status = RepositoryStatus.FAILED
                await session.commit()

    async def _clone_repository(self, clone_url: str, branch: str, target_dir: str, token: str, job_id: UUID) -> None:
        # The API stores only a canonical GitHub URL after verifying access.
        if not clone_url.startswith("https://github.com/") or "@" in clone_url or "?" in clone_url:
            raise ValueError("Repository clone URL is not a canonical GitHub URL")
        if os.path.exists(target_dir):
            raise FileExistsError("Repository workspace already exists; refusing to replace local changes")
        os.makedirs(os.path.dirname(target_dir), exist_ok=True)
        staging_dir = f"{target_dir}.incoming-{job_id}"
        if os.path.exists(staging_dir):
            raise FileExistsError("An earlier clone staging directory needs review")
        header = base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")
        env = os.environ.copy()
        env.update({
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {header}",
        })
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "clone", "--quiet", "--depth", "1", "--branch", branch,
                clone_url, staging_dir, env=env,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=120)
            except TimeoutError:
                proc.kill()
                await proc.communicate()
                raise TimeoutError("GitHub clone timed out") from None
            if proc.returncode != 0:
                raise RuntimeError("GitHub clone failed; check repository access and branch")
            if os.path.exists(target_dir):
                raise FileExistsError("Repository workspace appeared during clone; refusing replacement")
            os.replace(staging_dir, target_dir)
        finally:
            env.pop("GIT_CONFIG_VALUE_0", None)
            if os.path.exists(staging_dir):
                shutil.rmtree(staging_dir)

    async def _git_revision(self, workspace_dir: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", workspace_dir, "rev-parse", "HEAD",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        sha = stdout.decode("ascii", errors="ignore").strip()
        if proc.returncode != 0 or len(sha) != 40:
            raise RuntimeError("Could not determine imported repository commit")
        return sha
