from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.execution import ExecutionJobModel, MutationModel
from packages.database.models.patch import PatchModel, PatchStatus
from packages.database.models.repository import RepositoryModel
from packages.shared.config import get_settings
from packages.shared.errors import ConflictError, ErrorCategory, NotFoundError
from packages.shared.identifiers import generate_id
from services.execution.git_client import GitClient
from services.execution.sandbox import LocalProcessSandbox

logger = structlog.get_logger(__name__)


class PatchService:
    def __init__(self, session: AsyncSession, organization_id: UUID, settings=None):
        self.session = session
        self.organization_id = organization_id
        self.settings = settings or get_settings()

    async def generate_patch(self, execution_job_id: UUID) -> PatchModel:
        exec_job = await self.session.get(ExecutionJobModel, execution_job_id)
        if not exec_job or exec_job.organization_id != self.organization_id:
            raise NotFoundError("execution_not_found", "Execution job not found", ErrorCategory.NOT_FOUND)

        # Check if patch already exists for this execution
        stmt = select(PatchModel).where(PatchModel.execution_job_id == execution_job_id)
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

        # Fetch mutations
        stmt = select(MutationModel).where(MutationModel.execution_job_id == execution_job_id)
        mutations = (await self.session.execute(stmt)).scalars().all()

        additions = 0
        deletions = 0
        files_changed = len(mutations)

        for mutation in mutations:
            diff = mutation.diff_hunk
            for line in diff.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    additions += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deletions += 1

        patch = PatchModel(
            id=generate_id(),
            organization_id=self.organization_id,
            repository_id=exec_job.repository_id,
            execution_job_id=execution_job_id,
            status=PatchStatus.GENERATED,
            total_additions=additions,
            total_deletions=deletions,
            files_changed=files_changed,
        )
        self.session.add(patch)
        await self.session.commit()
        return patch

    async def accept_patch(self, patch_id: UUID, user_id: UUID | None = None) -> PatchModel:
        patch = await self.session.get(PatchModel, patch_id)
        if not patch or patch.organization_id != self.organization_id:
            raise NotFoundError("patch_not_found", "Patch not found", ErrorCategory.NOT_FOUND)

        if patch.status != PatchStatus.GENERATED and patch.status != PatchStatus.UNDER_REVIEW:
            raise ConflictError("patch_not_ready", f"Patch is in status {patch.status}", ErrorCategory.CONFLICT)

        # Mark as accepted
        patch.status = PatchStatus.ACCEPTED
        patch.reviewed_at = datetime.now(UTC)
        patch.reviewed_by = user_id
        await self.session.commit()

        # Apply to branch logic
        repo = await self.session.get(RepositoryModel, patch.repository_id)
        if not repo:
            return patch

        workspace_dir = f"{self.settings.workspace_root}/{patch.organization_id}/{patch.repository_id}"
        sandbox = LocalProcessSandbox(workspace_dir)
        git_client = GitClient(sandbox)

        # Check out new branch
        branch_name = f"forge-patch-{patch.id.hex[:8]}"
        await git_client.checkout(branch_name, create=True)

        # Commit changes
        await git_client.add(".")
        commit_res = await git_client.commit(f"Apply patch {patch.id}")

        if commit_res.exit_code == 0:
            patch.status = PatchStatus.COMMITTED
            patch.branch_name = branch_name
            # Simulating PR creation
            patch.status = PatchStatus.PULL_REQUEST_CREATED
            patch.pull_request_url = "https://github.com/mock/mock/pull/1"
        else:
            patch.status = PatchStatus.FAILED

        await self.session.commit()
        return patch

    async def reject_patch(self, patch_id: UUID, user_id: UUID | None = None) -> PatchModel:
        patch = await self.session.get(PatchModel, patch_id)
        if not patch or patch.organization_id != self.organization_id:
            raise NotFoundError("patch_not_found", "Patch not found", ErrorCategory.NOT_FOUND)

        patch.status = PatchStatus.REJECTED
        patch.reviewed_at = datetime.now(UTC)
        patch.reviewed_by = user_id
        await self.session.commit()
        return patch
