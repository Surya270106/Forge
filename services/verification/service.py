import os
import time
from datetime import UTC, datetime
from uuid import UUID

import structlog
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
        )
        self.session.add(job)
        await self.session.commit()
        return job

    async def run_verification(self, verification_job_id: UUID) -> None:
        job = await self.session.get(VerificationJobModel, verification_job_id)
        if not job:
            return

        job.started_at = datetime.now(UTC)
        await self.publisher.publish(create_verification_started_event(self.organization_id, job.repository_id, job.id, job.execution_job_id))
        await self.session.commit()

        workspace_dir = os.path.join(self.settings.workspace_root, str(job.organization_id), str(job.repository_id))
        sandbox = DockerSandbox(workspace_dir, network_disabled=True)
        registry = VerificationRegistry(workspace_dir)

        verifiers = registry.get_verifiers()

        try:
            await sandbox._ensure_container()

            all_passed = True

            for verifier in verifiers:
                if not verifier.enabled:
                    continue

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
                    diagnostics=self._parse_diagnostics(verifier, res.stdout, res.stderr),
                )
                self.session.add(res_model)
                await self.session.commit()

            job.finished_at = datetime.now(UTC)
            await self.publisher.publish(create_verification_completed_event(self.organization_id, job.repository_id, job.id, all_passed))
            await self.session.commit()

            if not all_passed:
                await self._trigger_repair(job)

        except Exception as e:
            logger.error("verification_error", error=str(e))
            job.finished_at = datetime.now(UTC)
            await self.session.commit()
        finally:
            await sandbox.cleanup()

    def _parse_diagnostics(self, verifier: VerifierDefinition, stdout: str, stderr: str) -> list[dict]:
        # Simple stub for diagnostic parsing
        # In the future, this would use regex or JSON parsing based on verifier.diagnostic_parser
        if not stdout and not stderr:
            return []

        return [
            {
                "severity": "error",
                "code": "EXEC_FAIL",
                "message": "Process returned non-zero exit code or had output",
                "file": "",
                "line": 0,
                "column": 0,
                "end_line": 0,
                "end_column": 0,
                "blocking": verifier.blocking,
            }
        ]

    async def _trigger_repair(self, job: VerificationJobModel):
        repair = RepairAttemptModel(
            id=generate_id(),
            organization_id=self.organization_id,
            repository_id=job.repository_id,
            verification_job_id=job.id,
            status=RepairAttemptStatus.QUEUED,
            attempt_number=1,
            prompt_used="Fix the following lint and test errors: ...",
        )
        self.session.add(repair)
        await self.publisher.publish(create_repair_attempted_event(self.organization_id, job.repository_id, repair.id, job.id))
        await self.session.commit()
