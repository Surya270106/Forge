import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.atlas import AtlasSnapshotModel
from packages.database.models.context_lens import ContextChangeSetModel
from packages.database.models.execution import ExecutionJobModel, ExecutionStatus, MutationModel
from packages.database.models.patch import PatchModel, PatchStatus
from packages.database.models.repository import RepositoryModel
from packages.database.models.verification import RepairAttemptModel, VerificationJobModel, VerificationStatus
from packages.shared.config import get_settings
from packages.shared.errors import ConflictError, ErrorCategory, NotFoundError
from packages.shared.identifiers import generate_id
from services.context_lens.service import capture_file_changes
from services.execution.flight_recorder import record_event

logger = structlog.get_logger(__name__)


class PatchService:
    def __init__(self, session: AsyncSession, organization_id: UUID, settings=None):
        self.session = session
        self.organization_id = organization_id
        self.settings = settings or get_settings()

    async def generate_patch(self, execution_job_id: UUID, *, commit: bool = True) -> PatchModel:
        exec_job = (
            await self.session.execute(
                select(ExecutionJobModel).where(ExecutionJobModel.id == execution_job_id)
                .with_for_update().execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if not exec_job or exec_job.organization_id != self.organization_id:
            raise NotFoundError("execution_not_found", "Execution job not found", ErrorCategory.NOT_FOUND)
        if exec_job.status != ExecutionStatus.COMPLETED:
            raise ConflictError("execution_not_complete", "Execution must complete before patch review", ErrorCategory.CONFLICT)
        if exec_job.cancellation_requested_at:
            raise ConflictError("execution_cancellation_requested", "Verification cancellation is pending", ErrorCategory.CONFLICT)
        repo = await self.session.get(RepositoryModel, exec_job.repository_id)
        if not repo or repo.organization_id != self.organization_id or not repo.commit_sha:
            raise ConflictError("repository_base_missing", "Imported repository base commit is unavailable", ErrorCategory.CONFLICT)

        # Check if patch already exists for this execution
        stmt = select(PatchModel).where(PatchModel.execution_job_id == execution_job_id, PatchModel.organization_id == self.organization_id)
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

        # Fetch mutations
        mutations = await self._mutations_for_execution(execution_job_id)
        digest = self._review_digest(exec_job.commit_sha_before, mutations)
        file_changes = capture_file_changes(mutations)

        additions = 0
        deletions = 0
        files_changed = len({mutation.file_path for mutation in mutations})

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
            base_commit_sha=exec_job.commit_sha_before,
            review_digest=digest,
            publish_status="NOT_REQUESTED",
        )
        self.session.add(patch)
        base_snapshot_id = (await self.session.execute(select(AtlasSnapshotModel.id).where(
            AtlasSnapshotModel.organization_id == self.organization_id,
            AtlasSnapshotModel.repository_id == exec_job.repository_id,
            AtlasSnapshotModel.commit_sha == exec_job.commit_sha_before,
            AtlasSnapshotModel.dirty.is_(False), AtlasSnapshotModel.status == "PUBLISHED",
        ).order_by(AtlasSnapshotModel.completed_at.desc()).limit(1))).scalar_one_or_none()
        self.session.add(ContextChangeSetModel(
            organization_id=self.organization_id, repository_id=exec_job.repository_id,
            execution_job_id=execution_job_id, patch_id=patch.id, base_snapshot_id=base_snapshot_id,
            base_commit_sha=exec_job.commit_sha_before, review_digest=digest,
            file_changes=file_changes, schema_version=1, created_at=datetime.now(UTC),
        ))
        await record_event(self.session, self.organization_id, execution_job_id, "patch.created", "system", "patch.service",
                           data={"patch_id": patch.id, "review_digest": digest, "file_count": files_changed},
                           idempotency_key=f"patch-created-{patch.id}")
        if commit:
            await self.session.commit()
        return patch

    @staticmethod
    def _review_digest(base_commit_sha: str, mutations: list[MutationModel]) -> str:
        if not re.fullmatch(r"[0-9a-f]{40}", base_commit_sha or "") or not mutations or len(mutations) > 50:
            raise ConflictError("invalid_patch", "Patch has no valid base or exceeds the file limit", ErrorCategory.CONFLICT)
        total_size = 0
        changes = []
        for mutation in mutations:
            path = mutation.file_path
            parsed = PurePosixPath(path)
            if (not re.fullmatch(r"[A-Za-z0-9_./-]{1,240}", path) or parsed.is_absolute()
                or ".." in parsed.parts or ".git" in parsed.parts or path.startswith("-")
                or parsed.as_posix() != path):
                raise ConflictError("invalid_patch_path", "Patch contains an unsafe file path", ErrorCategory.CONFLICT)
            diff = mutation.diff_hunk or ""
            if not diff.startswith(f"--- {path}\n+++ {path}\n@@ ") or "\x00" in diff:
                raise ConflictError("invalid_patch_diff", "Patch contains an invalid unified diff", ErrorCategory.CONFLICT)
            if any(line.startswith(("--- ", "+++ ", "diff --git ", "GIT binary patch")) for line in diff.splitlines()[2:]):
                raise ConflictError("invalid_patch_diff", "Patch contains more than one file or a binary payload", ErrorCategory.CONFLICT)
            total_size += len(diff.encode("utf-8"))
            if total_size > 1024 * 1024:
                raise ConflictError("patch_too_large", "Patch exceeds the 1 MiB review limit", ErrorCategory.CONFLICT)
            changes.append({"id": str(mutation.id), "path": path, "diff": diff})
        serialized = json.dumps({"base": base_commit_sha, "changes": changes}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    async def review_patch(self, patch_id: UUID) -> dict:
        patch = await self.session.get(PatchModel, patch_id)
        if not patch or patch.organization_id != self.organization_id:
            raise NotFoundError("patch_not_found", "Patch not found", ErrorCategory.NOT_FOUND)
        mutations = await self._mutations(patch)
        digest = self._review_digest(patch.base_commit_sha or "", mutations)
        if digest != patch.review_digest:
            raise ConflictError("stale_patch", "Patch changed since it was prepared", ErrorCategory.CONFLICT)
        return {"patch_id": str(patch.id), "base_commit_sha": patch.base_commit_sha,
                "review_digest": digest, "changes": [{"path": m.file_path, "diff": m.diff_hunk} for m in mutations]}

    async def _mutations(self, patch: PatchModel) -> list[MutationModel]:
        return await self._mutations_for_execution(patch.execution_job_id)

    async def _mutations_for_execution(self, execution_job_id: UUID) -> list[MutationModel]:
        lineage: list[UUID] = []
        current = execution_job_id
        for _ in range(4):
            if current in lineage:
                raise ConflictError("repair_cycle", "Repair execution lineage is cyclic", ErrorCategory.CONFLICT)
            lineage.append(current)
            repair = (
                await self.session.execute(
                    select(RepairAttemptModel).where(
                        RepairAttemptModel.repair_execution_id == current,
                        RepairAttemptModel.organization_id == self.organization_id,
                    )
                )
            ).scalar_one_or_none()
            if not repair:
                break
            source = await self.session.get(VerificationJobModel, repair.verification_job_id)
            if not source or source.organization_id != self.organization_id:
                raise ConflictError("repair_source_missing", "Repair source is unavailable", ErrorCategory.CONFLICT)
            current = source.execution_job_id
        else:
            raise ConflictError("repair_limit", "Repair lineage exceeds the supported limit", ErrorCategory.CONFLICT)
        mutations: list[MutationModel] = []
        for job_id in reversed(lineage):
            stmt = select(MutationModel).where(
                MutationModel.execution_job_id == job_id,
                MutationModel.organization_id == self.organization_id,
                MutationModel.is_reverted.is_(False),
            ).order_by(MutationModel.created_at, MutationModel.id)
            mutations.extend((await self.session.execute(stmt)).scalars().all())
        return mutations

    async def accept_patch(self, patch_id: UUID, review_digest: str, user_id: UUID) -> PatchModel:
        patch = await self.session.get(PatchModel, patch_id)
        if not patch or patch.organization_id != self.organization_id:
            raise NotFoundError("patch_not_found", "Patch not found", ErrorCategory.NOT_FOUND)

        if patch.status != PatchStatus.GENERATED and patch.status != PatchStatus.UNDER_REVIEW:
            raise ConflictError("patch_not_ready", f"Patch is in status {patch.status}", ErrorCategory.CONFLICT)
        review = await self.review_patch(patch_id)
        if review_digest != review["review_digest"]:
            raise ConflictError("stale_approval", "Review the latest patch before approving", ErrorCategory.CONFLICT)

        # Mark as accepted
        patch.status = PatchStatus.ACCEPTED
        patch.reviewed_at = datetime.now(UTC)
        patch.reviewed_by = user_id
        await record_event(self.session, self.organization_id, patch.execution_job_id, "patch.approved", "user", "patch.service",
                           actor_id=str(user_id), data={"patch_id": patch.id, "review_digest": patch.review_digest},
                           idempotency_key=f"patch-approved-{patch.id}")
        await self.session.commit()

        # Approval records the review decision only. Branch pushes and pull request
        # creation require separate, explicit actions and real GitHub responses.
        return patch

    async def request_publish(self, patch_id: UUID, user_id: UUID) -> PatchModel:
        patch = (
            await self.session.execute(
                select(PatchModel).where(PatchModel.id == patch_id).with_for_update().execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if not patch or patch.organization_id != self.organization_id:
            raise NotFoundError("patch_not_found", "Patch not found", ErrorCategory.NOT_FOUND)
        if patch.reviewed_by != user_id:
            raise ConflictError("approval_required", "Approve this exact patch before publishing", ErrorCategory.CONFLICT)
        if patch.publish_status == "SUCCEEDED" and patch.status == PatchStatus.PULL_REQUEST_CREATED:
            return patch
        if patch.status not in {PatchStatus.ACCEPTED, PatchStatus.COMMITTED}:
            raise ConflictError("approval_required", "Approve this exact patch before publishing", ErrorCategory.CONFLICT)
        if patch.publish_status in {"QUEUED", "RUNNING"}:
            return patch
        verification = (
            await self.session.execute(
                select(VerificationJobModel).where(
                    VerificationJobModel.execution_job_id == patch.execution_job_id,
                    VerificationJobModel.organization_id == self.organization_id,
                ).order_by(VerificationJobModel.created_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        if not verification or verification.status != VerificationStatus.PASSED:
            raise ConflictError("verification_required", "A passing verification is required before publishing", ErrorCategory.CONFLICT)
        review = await self.review_patch(patch_id)
        if review["review_digest"] != patch.review_digest:
            raise ConflictError("stale_patch", "Patch changed after approval", ErrorCategory.CONFLICT)
        from packages.database.models.execution import ExecutionJobModel
        from services.safety.policy import decide
        from services.safety.service import as_document, current_policy, from_document

        execution = await self.session.get(ExecutionJobModel, patch.execution_job_id)
        if not execution or execution.organization_id != self.organization_id:
            raise ConflictError("execution_unavailable", "Patch execution is unavailable", ErrorCategory.CONFLICT)
        current = await current_policy(self.session, self.organization_id)
        if execution.safety_policy_snapshot is None:
            execution.safety_policy_snapshot = as_document(current)
        decision = decide("patch_publish", str(patch.id), from_document(execution.safety_policy_snapshot), current,
                          repository_id=patch.repository_id)
        if decision.effect == "DENY":
            await record_event(self.session, self.organization_id, execution.id, "safety.permission_denied", "system",
                               "safety.policy", data={"capability": "patch:publish", "decision": "DENY",
                                                      "policy_version": current.version, "reason_code": decision.reason},
                               idempotency_key=f"safety-publish-denied-{patch.id}-{current.version}")
            await self.session.commit()
            raise ConflictError("safety_policy_denied", "Safety Gate blocks publication", ErrorCategory.CONFLICT)
        await record_event(self.session, self.organization_id, execution.id, "safety.permission_granted", "user",
                           "safety.policy", actor_id=str(user_id),
                           data={"capability": "patch:publish", "decision": "ALLOW", "policy_version": current.version,
                                 "review_digest": patch.review_digest},
                           idempotency_key=f"safety-publish-requested-{patch.id}")
        patch.branch_name = f"forge/{patch.id.hex}"
        patch.publish_status = "QUEUED"
        patch.publish_error = None
        from packages.shared.events import EventEnvelope
        from services.repository_memory.events import OutboxEventPublisher
        event = EventEnvelope(
            event_type="patch.publish_requested", aggregate_type="patch",
            aggregate_id=str(patch.id), organization_id=str(self.organization_id),
            payload={"patch_id": str(patch.id), "requested_by": str(user_id)},
        )
        await OutboxEventPublisher(self.session).publish(event)
        await self.session.commit()
        return patch

    async def reject_patch(self, patch_id: UUID, user_id: UUID | None = None) -> PatchModel:
        patch = await self.session.get(PatchModel, patch_id)
        if not patch or patch.organization_id != self.organization_id:
            raise NotFoundError("patch_not_found", "Patch not found", ErrorCategory.NOT_FOUND)
        if patch.status not in {PatchStatus.GENERATED, PatchStatus.UNDER_REVIEW}:
            raise ConflictError("patch_not_ready", "Published or approved patches cannot be rejected", ErrorCategory.CONFLICT)

        patch.status = PatchStatus.REJECTED
        patch.reviewed_at = datetime.now(UTC)
        patch.reviewed_by = user_id
        await record_event(self.session, self.organization_id, patch.execution_job_id, "patch.rejected", "user", "patch.service",
                           actor_id=str(user_id) if user_id else None, data={"patch_id": patch.id},
                           idempotency_key=f"patch-rejected-{patch.id}")
        await self.session.commit()
        return patch

    async def revise_patch(self, patch_id: UUID, feedback: str, user_id: UUID | None = None) -> PatchModel:
        patch = await self.session.get(PatchModel, patch_id)
        if not patch or patch.organization_id != self.organization_id:
            raise NotFoundError("patch_not_found", "Patch not found", ErrorCategory.NOT_FOUND)

        if patch.status not in (PatchStatus.GENERATED, PatchStatus.UNDER_REVIEW):
            raise ConflictError("patch_not_ready", f"Cannot revise patch in status {patch.status}", ErrorCategory.CONFLICT)

        patch.status = PatchStatus.REJECTED
        patch.reviewed_at = datetime.now(UTC)
        patch.reviewed_by = user_id

        # We need to inform the planning engine to generate a new plan based on the feedback
        exec_job = await self.session.get(ExecutionJobModel, patch.execution_job_id)
        if exec_job and exec_job.plan_id:
            from services.planning.service import PlanningService
            planning_svc = PlanningService(self.session, self.organization_id)
            try:
                await planning_svc.revise_plan(exec_job.plan_id, f"Patch rejected. Feedback: {feedback}")
            except Exception as e:
                logger.error("patch_revise_plan_trigger_failed", error=str(e))

        await self.session.commit()
        return patch
