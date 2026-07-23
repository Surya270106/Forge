import os
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.execution import ExecutionJobModel, ExecutionStatus
from packages.database.models.verification import (
    DiagnosticType,
    RepairAttemptModel,
    VerificationJobModel,
    VerificationResultModel,
    VerificationStatus,
)
from packages.shared.config import get_settings
from packages.shared.errors import ConflictError, ErrorCategory, NotFoundError, ErrorCategory
from packages.shared.identifiers import generate_id
from services.execution.sandbox import LocalProcessSandbox

from .events import (
    VerificationEventPublisher,
    create_repair_attempted_event,
    create_verification_completed_event,
    create_verification_started_event,
)

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
        await self.session.commit()
        return job

    async def run_verification(self, verification_job_id: UUID) -> None:
        job = await self.session.get(VerificationJobModel, verification_job_id)
        if not job or job.status != VerificationStatus.PENDING:
            return

        job.status = VerificationStatus.RUNNING
        job.started_at = datetime.now(UTC)
        await self.publisher.publish(create_verification_started_event(self.organization_id, job.repository_id, job.id, job.execution_job_id))
        await self.session.commit()

        workspace_dir = os.path.join(self.settings.workspace_root, str(job.organization_id), str(job.repository_id))
        sandbox = LocalProcessSandbox(workspace_dir)

        try:
            # 1. Run Linter (Mocking the process for demonstration, usually we'd parse repo language config)
            lint_res = await sandbox.run_command(["npm", "run", "lint"])
            lint_passed = lint_res.exit_code == 0

            res_lint = VerificationResultModel(
                id=generate_id(),
                organization_id=self.organization_id,
                verification_job_id=job.id,
                diagnostic_type=DiagnosticType.LINT,
                is_passed=lint_passed,
                output=lint_res.stdout + "\n" + lint_res.stderr,
            )
            self.session.add(res_lint)

            # 2. Run Tests
            test_res = await sandbox.run_command(["npm", "run", "test"])
            test_passed = test_res.exit_code == 0

            res_test = VerificationResultModel(
                id=generate_id(),
                organization_id=self.organization_id,
                verification_job_id=job.id,
                diagnostic_type=DiagnosticType.UNIT_TEST,
                is_passed=test_passed,
                output=test_res.stdout + "\n" + test_res.stderr,
            )
            self.session.add(res_test)

            all_passed = lint_passed and test_passed
            job.status = VerificationStatus.PASSED if all_passed else VerificationStatus.FAILED
            job.finished_at = datetime.now(UTC)

            await self.publisher.publish(create_verification_completed_event(self.organization_id, job.repository_id, job.id, all_passed))
            await self.session.commit()

            if not all_passed:
                await self._trigger_repair(job, res_lint, res_test)

        except Exception as e:
            logger.error("verification_error", error=str(e))
            job.status = VerificationStatus.ERROR
            job.finished_at = datetime.now(UTC)
            await self.session.commit()

    async def _trigger_repair(
        self,
        job: VerificationJobModel,
        lint_res: VerificationResultModel,
        test_res: VerificationResultModel,
    ):
        # In RFC-005, if verification fails, we trigger a repair loop (Phase 5/6 combo)
        # We would invoke the AI Context Engine to build a repair plan, then create an ExecutionJob.
        # This is a stub for that integration point.
        repair = RepairAttemptModel(
            id=generate_id(),
            organization_id=self.organization_id,
            repository_id=job.repository_id,
            verification_job_id=job.id,
            repair_execution_id=generate_id(),  # Mocked new execution job ID
            prompt_used="Fix the following lint and test errors: ...",
        )
        self.session.add(repair)
        await self.publisher.publish(create_repair_attempted_event(self.organization_id, job.repository_id, repair.id, job.id))
        await self.session.commit()
