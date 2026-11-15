import os
import re
import time
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.execution import ExecutionJobModel, ExecutionStatus
from packages.database.models.verification import (
    RepairAttemptModel,
    RepairAttemptStatus,
    VerificationJobModel,
    VerificationResultModel,
    VerificationStatus,
)
from packages.shared.config import get_settings
from packages.shared.errors import ConflictError, ErrorCategory, NotFoundError
from packages.shared.identifiers import generate_id
from services.execution.sandbox import DockerSandbox

from .events import (
    VerificationEventPublisher,
    create_repair_attempted_event,
    create_verification_completed_event,
    create_verification_started_event,
)
from .registry import VerificationRegistry, VerifierDefinition

logger = structlog.get_logger(__name__)


class VerificationDispatcher:
    def __init__(self, session: AsyncSession, organization_id: UUID, settings=None):
        self.session = session
        self.organization_id = organization_id
        self.settings = settings or get_settings()
        self.publisher = VerificationEventPublisher(session)

    async def trigger_verification(self, execution_job_id: UUID) -> VerificationJobModel:
        exec_job = await self.session.get(ExecutionJobModel, execution_job_id)
        if not exec_job or exec_job.organization_id != self.organization_id:
            raise NotFoundError(code="execution_not_found", message="Execution job not found", category=ErrorCategory.NOT_FOUND)

        if exec_job.status != ExecutionStatus.COMPLETED:
            raise ConflictError(
                code="execution_not_ready",
                message="Execution must be COMPLETED before verification",
                category=ErrorCategory.CONFLICT,
            )

        job = VerificationJobModel(
            id=generate_id(),
            organization_id=self.organization_id,
            repository_id=exec_job.repository_id,
            execution_job_id=execution_job_id,
            status=VerificationStatus.PENDING,
        )
        self.session.add(job)

        repair = (
            await self.session.execute(
                select(RepairAttemptModel).where(
                    RepairAttemptModel.repair_execution_id == execution_job_id,
                    RepairAttemptModel.organization_id == self.organization_id,
                    RepairAttemptModel.status == RepairAttemptStatus.EXECUTING,
                )
            )
        ).scalar_one_or_none()
        if repair:
            repair.status = RepairAttemptStatus.REVERIFYING

        from .events import create_verification_requested_event
        await self.publisher.publish(create_verification_requested_event(self.organization_id, job.repository_id, job.id, execution_job_id))

        await self.session.commit()
        return job

    async def run_verification(self, verification_job_id: UUID) -> None:
        job = (
            await self.session.execute(
                select(VerificationJobModel)
                .where(VerificationJobModel.id == verification_job_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if not job or job.organization_id != self.organization_id or job.status != VerificationStatus.PENDING:
            return

        job.started_at = datetime.now(UTC)
        job.status = VerificationStatus.RUNNING
        await self.publisher.publish(create_verification_started_event(self.organization_id, job.repository_id, job.id, job.execution_job_id))
        await self.session.commit()

        workspace_dir = os.path.join(self.settings.workspace_root, str(job.organization_id), str(job.repository_id))
        registry = VerificationRegistry(workspace_dir)
        languages = registry.config.languages if registry.config else []
        image_prefix = "python:" if "python" in languages else "node:"
        image = next((candidate for candidate in self.settings.sandbox_images if candidate.startswith(image_prefix)), None)
        if image is None:
            job.status = VerificationStatus.BLOCKED
            job.finished_at = datetime.now(UTC)
            await self._finish_repair(job, False, "Verifier sandbox image is unavailable")
            await self.publisher.publish(create_verification_completed_event(self.organization_id, job.repository_id, job.id, False))
            await self.session.commit()
            return
        sandbox = DockerSandbox(workspace_dir, image=image, network_disabled=True)

        verifiers = registry.get_verifiers()

        try:
            if not any(verifier.enabled for verifier in verifiers):
                job.status = VerificationStatus.NOT_CONFIGURED
                job.finished_at = datetime.now(UTC)
                await self._finish_repair(job, False, "No verification checks were configured")
                await self.publisher.publish(create_verification_completed_event(self.organization_id, job.repository_id, job.id, False))
                await self.session.commit()
                return
            await sandbox._ensure_container()

            all_passed = True
            checks_run = 0

            for verifier in verifiers:
                if not verifier.enabled:
                    continue
                checks_run += 1

                full_cmd = verifier.command + verifier.arguments
                start_time = time.time()

                res = await sandbox.run_command(full_cmd, cwd=verifier.working_directory)

                duration_ms = int((time.time() - start_time) * 1000)
                is_passed = res.exit_code == 0

                if verifier.blocking and not is_passed:
                    all_passed = False

                res_model = VerificationResultModel(
                    id=generate_id(),
                    organization_id=self.organization_id,
                    verification_job_id=job.id,
                    execution_id=job.execution_job_id,
                    verifier=verifier.identifier,
                    status=VerificationStatus.PASSED if is_passed else VerificationStatus.FAILED,
                    exit_code=res.exit_code,
                    started_at=datetime.fromtimestamp(start_time, UTC),
                    finished_at=datetime.now(UTC),
                    duration_ms=duration_ms,
                    stdout=res.stdout[:50000],  # Truncate to avoid massive logs
                    stderr=res.stderr[:50000],
                    stdout_truncated=len(res.stdout) > 50000,
                    stderr_truncated=len(res.stderr) > 50000,
                    blocking=verifier.blocking,
                    attempt=1,
                    diagnostics=self._parse_diagnostics(verifier, res.exit_code, res.stdout, res.stderr),
                )
                self.session.add(res_model)
                await self.session.commit()

            locked_job = (
                await self.session.execute(
                    select(VerificationJobModel).where(VerificationJobModel.id == job.id)
                    .with_for_update().execution_options(populate_existing=True)
                )
            ).scalar_one()
            if locked_job.status != VerificationStatus.RUNNING:
                return
            job.finished_at = datetime.now(UTC)
            job.status = VerificationStatus.NOT_CONFIGURED if checks_run == 0 else VerificationStatus.PASSED if all_passed else VerificationStatus.FAILED
            if checks_run == 0:
                all_passed = False
            await self._finish_repair(job, all_passed)
            await self.publisher.publish(create_verification_completed_event(self.organization_id, job.repository_id, job.id, all_passed))
            await self.session.commit()

            if checks_run and not all_passed:
                await self._trigger_repair(job)

        except Exception as e:
            logger.error("verification_error", error=str(e))
            job.status = VerificationStatus.FAILED
            job.finished_at = datetime.now(UTC)
            await self._finish_repair(job, False, "Verification could not complete")
            await self.publisher.publish(create_verification_completed_event(self.organization_id, job.repository_id, job.id, False))
            await self.session.commit()
        finally:
            await sandbox.cleanup()

    def _parse_diagnostics(self, verifier: VerifierDefinition, exit_code: int, stdout: str, stderr: str) -> list[dict]:
        if exit_code == 0:
            return []
        diagnostics = []
        for line in (stderr + "\n" + stdout).splitlines():
            match = re.match(r"^(?P<file>[^:\s]+):(?P<line>\d+)(?::(?P<column>\d+))?:\s*(?P<message>.+)$", line)
            if match:
                diagnostics.append({
                    "severity": "error", "code": "CHECK_FAILED", "message": match["message"][:500],
                    "file": match["file"], "line": int(match["line"]),
                    "column": int(match["column"] or 0), "end_line": 0, "end_column": 0,
                    "blocking": verifier.blocking,
                })
            if len(diagnostics) >= 100:
                break
        if diagnostics:
            return diagnostics
        detail = next((line.strip() for line in stderr.splitlines() + stdout.splitlines() if line.strip()), "No diagnostic output")
        return [{"severity": "error", "code": "CHECK_FAILED", "message": f"Exit {exit_code}: {detail[:500]}",
                 "file": "", "line": 0, "column": 0, "end_line": 0, "end_column": 0, "blocking": verifier.blocking}]

    async def _finish_repair(self, job: VerificationJobModel, passed: bool, error: str | None = None) -> None:
        repair = (
            await self.session.execute(
                select(RepairAttemptModel).where(
                    RepairAttemptModel.repair_execution_id == job.execution_job_id,
                    RepairAttemptModel.organization_id == self.organization_id,
                )
            )
        ).scalar_one_or_none()
        if repair and repair.status in {RepairAttemptStatus.EXECUTING, RepairAttemptStatus.REVERIFYING}:
            repair.status = RepairAttemptStatus.SUCCEEDED if passed else RepairAttemptStatus.FAILED
            repair.error_message = error

    async def _trigger_repair(self, job: VerificationJobModel):
        existing = await self.session.execute(
            select(RepairAttemptModel.id).where(RepairAttemptModel.verification_job_id == job.id)
        )
        if existing.scalar_one_or_none() is not None:
            return
        prior = (
            await self.session.execute(
                select(RepairAttemptModel).where(
                    RepairAttemptModel.repair_execution_id == job.execution_job_id,
                    RepairAttemptModel.organization_id == self.organization_id,
                )
            )
        ).scalar_one_or_none()
        next_attempt = (prior.attempt_number + 1) if prior else 1
        if next_attempt > 3:
            if prior:
                prior.status = RepairAttemptStatus.EXHAUSTED
                prior.error_message = "Three repair attempts have been used"
                await self.session.commit()
            return
        repair = RepairAttemptModel(
            id=generate_id(),
            organization_id=self.organization_id,
            repository_id=job.repository_id,
            verification_job_id=job.id,
            status=RepairAttemptStatus.QUEUED,
            attempt_number=next_attempt,
            prompt_used=None,
        )
        self.session.add(repair)
        await self.publisher.publish(create_repair_attempted_event(self.organization_id, job.repository_id, repair.id, job.id))
        await self.session.commit()
