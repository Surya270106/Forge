import asyncio
import hashlib
import re
import time
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.context_lens import ContextChangeSetModel
from packages.database.models.execution import ExecutionJobModel, ExecutionStatus
from packages.database.models.patch import PatchModel
from packages.database.models.verification import (
    RepairAttemptModel,
    RepairAttemptStatus,
    VerificationJobModel,
    VerificationResultModel,
    VerificationStatus,
)
from packages.database.models.verification_intelligence import VerificationPlanModel
from packages.shared.config import get_settings
from packages.shared.errors import ConflictError, ErrorCategory, NotFoundError
from packages.shared.identifiers import generate_id
from services.execution.flight_recorder import SAFE_STRING, record_event
from services.execution.sandbox import DockerSandbox
from services.execution.workspace import execution_workspace_path
from services.patch.service import PatchService

from .events import (
    VerificationEventPublisher,
    create_repair_attempted_event,
    create_verification_cancelled_event,
    create_verification_completed_event,
    create_verification_started_event,
)
from .intelligence import build_decision, verifier_fingerprint, verifier_ref
from .registry import VerificationRegistry, VerifierDefinition

logger = structlog.get_logger(__name__)


class VerificationDispatcher:
    def __init__(self, session: AsyncSession, organization_id: UUID, settings=None, session_maker=None):
        self.session = session
        self.organization_id = organization_id
        self.settings = settings or get_settings()
        self.publisher = VerificationEventPublisher(session)
        self.session_maker = session_maker
        self._cancel_requested = False

    async def _watch_cancellation(self, execution_id: UUID, verification_id: UUID, running_task: asyncio.Task) -> None:
        if self.session_maker is None:
            return
        from packages.database.tenant import set_tenant

        try:
            while True:
                await asyncio.sleep(1)
                set_tenant(self.organization_id)
                async with self.session_maker() as session:
                    execution = await session.get(ExecutionJobModel, execution_id)
                    verification = await session.get(VerificationJobModel, verification_id)
                    if verification is None or verification.status != VerificationStatus.RUNNING:
                        return
                    if execution and execution.organization_id == self.organization_id and execution.cancellation_requested_at:
                        self._cancel_requested = True
                        running_task.cancel()
                        return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("verification_cancellation_watch_failed", verification_id=str(verification_id))
            running_task.cancel()

    async def trigger_verification(self, execution_job_id: UUID, *, commit: bool = True) -> VerificationJobModel:
        exec_job = (
            await self.session.execute(
                select(ExecutionJobModel).where(ExecutionJobModel.id == execution_job_id)
                .with_for_update().execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if not exec_job or exec_job.organization_id != self.organization_id:
            raise NotFoundError(code="execution_not_found", message="Execution job not found", category=ErrorCategory.NOT_FOUND)

        if exec_job.status != ExecutionStatus.COMPLETED:
            raise ConflictError(
                code="execution_not_ready",
                message="Execution must be COMPLETED before verification",
                category=ErrorCategory.CONFLICT,
            )

        existing = (
            await self.session.execute(
                select(VerificationJobModel).where(
                    VerificationJobModel.execution_job_id == execution_job_id,
                    VerificationJobModel.organization_id == self.organization_id,
                ).order_by(VerificationJobModel.created_at).limit(1)
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        patch_service = PatchService(self.session, self.organization_id, self.settings)
        mutations = await patch_service._mutations_for_execution(execution_job_id)
        patch = None
        if mutations:
            try:
                patch = await patch_service.generate_patch(execution_job_id, commit=False)
            except (ConflictError, ValueError):
                logger.warning("verification_patch_evidence_unavailable", execution_id=str(execution_job_id))

        job = VerificationJobModel(
            id=generate_id(),
            organization_id=self.organization_id,
            repository_id=exec_job.repository_id,
            execution_job_id=execution_job_id,
            status=VerificationStatus.PENDING,
        )
        self.session.add(job)

        if patch:
            change = (await self.session.execute(select(ContextChangeSetModel).where(
                ContextChangeSetModel.patch_id == patch.id,
                ContextChangeSetModel.organization_id == self.organization_id,
                ContextChangeSetModel.repository_id == exec_job.repository_id,
                ContextChangeSetModel.execution_job_id == execution_job_id,
            ))).scalar_one_or_none()
            if change:
                workspace = execution_workspace_path(self.settings.workspace_root, self.organization_id,
                                                     exec_job.repository_id, execution_job_id, exec_job.lease_generation)
                verifiers = VerificationRegistry(str(workspace)).get_verifiers()
                decision = await build_decision(self.session, self.organization_id, exec_job.repository_id,
                                                change, verifiers)
                selection = VerificationPlanModel(
                    organization_id=self.organization_id, repository_id=exec_job.repository_id,
                    execution_job_id=execution_job_id, verification_job_id=job.id,
                    change_set_id=change.id, base_commit_sha=change.base_commit_sha,
                    patch_digest=change.review_digest, schema_version=1, decision=decision,
                    created_at=datetime.now(UTC),
                )
                self.session.add(selection)
                await self.session.flush()
                await record_event(self.session, self.organization_id, execution_job_id,
                                   "verification.plan_selected", "system", "verification.intelligence",
                                   data={"verification_id": job.id, "selection_id": selection.id,
                                         "review_digest": change.review_digest,
                                         "status": decision["strategy"]},
                                   idempotency_key=f"verification-selection-{job.id}")

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

        if commit:
            await self.session.commit()
        return job

    async def run_verification(self, verification_job_id: UUID) -> None:
        if self.session_maker is not None:
            execution_id = (await self.session.execute(select(VerificationJobModel.execution_job_id).where(
                VerificationJobModel.id == verification_job_id,
                VerificationJobModel.organization_id == self.organization_id,
            ))).scalar_one_or_none()
            if execution_id is None:
                return
            await self.session.execute(select(ExecutionJobModel.id).where(
                ExecutionJobModel.id == execution_id,
                ExecutionJobModel.organization_id == self.organization_id,
            ).with_for_update(key_share=True))
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
        await record_event(self.session, self.organization_id, job.execution_job_id, "verification.started", "worker", "verification.service",
                           data={"verification_id": job.id}, idempotency_key=f"verification-started-{job.id}")
        await self.session.commit()

        execution = await self.session.get(ExecutionJobModel, job.execution_job_id)
        if not execution or execution.organization_id != job.organization_id:
            raise RuntimeError("Verification execution is unavailable")
        if execution.cancellation_requested_at:
            job.status = VerificationStatus.CANCELLED
            job.finished_at = datetime.now(UTC)
            repair = (await self.session.execute(select(RepairAttemptModel).where(
                RepairAttemptModel.repair_execution_id == job.execution_job_id,
                RepairAttemptModel.organization_id == self.organization_id,
                RepairAttemptModel.status == RepairAttemptStatus.REVERIFYING,
            ))).scalar_one_or_none()
            if repair:
                repair.status = RepairAttemptStatus.CANCELLED
            await self.publisher.publish(create_verification_cancelled_event(
                self.organization_id, job.repository_id, job.id, job.execution_job_id,
            ))
            await record_event(self.session, self.organization_id, job.execution_job_id,
                               "verification.cancelled", "worker", "verification.service",
                               data={"verification_id": job.id}, idempotency_key=f"verification-cancelled-{job.id}")
            await self.session.commit()
            return
        workspace_dir = str(execution_workspace_path(
            self.settings.workspace_root, job.organization_id, job.repository_id,
            job.execution_job_id, execution.lease_generation,
        ))
        registry = VerificationRegistry(workspace_dir)
        languages = registry.config.languages if registry.config else []
        image_prefix = "python:" if "python" in languages else "node:"
        image = next((candidate for candidate in self.settings.sandbox_images if candidate.startswith(image_prefix)), None)
        if image is None:
            job.status = VerificationStatus.BLOCKED
            job.finished_at = datetime.now(UTC)
            await self._finish_repair(job, False, "Verifier sandbox image is unavailable")
            await self.publisher.publish(create_verification_completed_event(self.organization_id, job.repository_id, job.id, False))
            await record_event(self.session, self.organization_id, job.execution_job_id, "verification.completed", "worker", "verification.service",
                               data={"verification_id": job.id, "status": "BLOCKED"}, idempotency_key=f"verification-completed-{job.id}")
            await self.session.commit()
            return
        sandbox = DockerSandbox(workspace_dir, image=image, network_disabled=True)
        session_maker = self.session_maker
        if session_maker is not None and hasattr(sandbox, "sandbox_id"):
            from packages.database.tenant import set_tenant
            sandbox_execution_id = job.execution_job_id

            async def sandbox_event(event_type: str, data: dict) -> None:
                set_tenant(self.organization_id)
                async with session_maker() as evidence_session:
                    await record_event(evidence_session, self.organization_id, sandbox_execution_id,
                                       event_type, "sandbox", "verification.sandbox", data=data,
                                       idempotency_key=f"sandbox-{sandbox.sandbox_id}-{event_type}")
                    await evidence_session.commit()

            sandbox.event_sink = sandbox_event

        verifiers = registry.get_verifiers()
        selection = (await self.session.execute(select(VerificationPlanModel).where(
            VerificationPlanModel.verification_job_id == job.id,
            VerificationPlanModel.organization_id == self.organization_id,
            VerificationPlanModel.repository_id == job.repository_id,
            VerificationPlanModel.execution_job_id == job.execution_job_id,
        ))).scalar_one_or_none()
        selected_ids = None
        if selection:
            patch = (await self.session.execute(select(PatchModel).where(
                PatchModel.execution_job_id == job.execution_job_id,
                PatchModel.organization_id == self.organization_id,
                PatchModel.repository_id == job.repository_id,
            ))).scalar_one_or_none()
            try:
                mutations = await PatchService(self.session, self.organization_id, self.settings)._mutations_for_execution(job.execution_job_id)
                digest = PatchService._review_digest(selection.base_commit_sha, mutations)
            except ConflictError:
                digest = None
            over_limit = "VERIFIER_LIMIT_EXCEEDED" in selection.decision["fallback_reasons"]
            if (not patch or patch.review_digest != selection.patch_digest or digest != selection.patch_digest
                or over_limit
                or verifier_fingerprint(verifiers) != selection.decision["verifier_fingerprint"]):
                job.status = VerificationStatus.BLOCKED
                job.finished_at = datetime.now(UTC)
                await self._finish_repair(job, False, "Verifier limit exceeded" if over_limit else "Verification selection is stale")
                await self.publisher.publish(create_verification_completed_event(
                    self.organization_id, job.repository_id, job.id, False))
                await record_event(self.session, self.organization_id, job.execution_job_id,
                                   "verification.completed", "worker", "verification.service",
                                   data={"verification_id": job.id, "status": "BLOCKED",
                                         "reason_code": "VERIFIER_LIMIT_EXCEEDED" if over_limit else "STALE_SELECTION"},
                                   idempotency_key=f"verification-completed-{job.id}")
                await self.session.commit()
                return
            selected_ids = set(selection.decision["selected_verifiers"])
        running_task = asyncio.current_task()
        assert running_task is not None
        watcher = asyncio.create_task(self._watch_cancellation(job.execution_job_id, job.id, running_task))
        sandbox_cleaned = False

        try:
            if not any(verifier.enabled for verifier in verifiers):
                job.status = VerificationStatus.NOT_CONFIGURED
                job.finished_at = datetime.now(UTC)
                await self._finish_repair(job, False, "No verification checks were configured")
                await self.publisher.publish(create_verification_completed_event(self.organization_id, job.repository_id, job.id, False))
                await record_event(self.session, self.organization_id, job.execution_job_id, "verification.completed", "worker", "verification.service",
                                   data={"verification_id": job.id, "status": "NOT_CONFIGURED"}, idempotency_key=f"verification-completed-{job.id}")
                await self.session.commit()
                return
            await sandbox._ensure_container()

            all_passed = True
            checks_run = 0

            for verifier in verifiers:
                if not verifier.enabled:
                    continue
                check_ref = verifier.identifier if SAFE_STRING.fullmatch(verifier.identifier) else "sha256:" + hashlib.sha256(verifier.identifier.encode()).hexdigest()
                check_key = hashlib.sha256(verifier.identifier.encode()).hexdigest()
                if selected_ids is not None and verifier_ref(verifier.identifier) not in selected_ids:
                    self.session.add(VerificationResultModel(
                        id=generate_id(), organization_id=self.organization_id, verification_job_id=job.id,
                        execution_id=job.execution_job_id, verifier=verifier.identifier,
                        status=VerificationStatus.SKIPPED, exit_code=None, finished_at=datetime.now(UTC),
                        blocking=verifier.blocking, attempt=1, diagnostics=[],
                    ))
                    await record_event(self.session, self.organization_id, job.execution_job_id,
                                       "verification.check_skipped", "worker", "verification.service",
                                       data={"verification_id": job.id, "check_id": check_ref,
                                             "reason_code": "UNRELATED_EXPLICIT_TEST"},
                                       idempotency_key=f"check-skipped-{job.id}-{check_key}")
                    await self.session.commit()
                    continue
                checks_run += 1

                await record_event(self.session, self.organization_id, job.execution_job_id, "verification.check_started", "worker", "verification.service",
                                   data={"verification_id": job.id, "check_id": check_ref},
                                   idempotency_key=f"check-started-{job.id}-{check_key}")
                await self.session.commit()

                full_cmd = verifier.command + verifier.arguments
                sandbox.timeout_seconds = min(max(verifier.timeout, 1), 300)
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
                await record_event(self.session, self.organization_id, job.execution_job_id,
                                   "verification.check_passed" if is_passed else "verification.check_failed",
                                   "worker", "verification.service",
                                   data={"verification_id": job.id, "result_id": res_model.id,
                                         "check_id": check_ref, "duration_ms": duration_ms, "exit_code": res.exit_code},
                                   idempotency_key=f"check-finished-{job.id}-{check_key}")
                await self.session.commit()

            if self.session_maker is not None:
                current_execution = (await self.session.execute(select(ExecutionJobModel).where(
                    ExecutionJobModel.id == job.execution_job_id,
                    ExecutionJobModel.organization_id == self.organization_id,
                ).with_for_update(key_share=True).execution_options(populate_existing=True))).scalar_one()
                if current_execution.cancellation_requested_at:
                    self._cancel_requested = True
                    raise asyncio.CancelledError
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
            await record_event(self.session, self.organization_id, job.execution_job_id, "verification.completed", "worker", "verification.service",
                               data={"verification_id": job.id, "status": job.status.value},
                               idempotency_key=f"verification-completed-{job.id}")
            await self.session.commit()

            if checks_run and not all_passed:
                await self._trigger_repair(job)

        except asyncio.CancelledError:
            if not self._cancel_requested:
                raise
            verification_id, execution_id, repository_id = job.id, job.execution_job_id, job.repository_id
            await self.session.rollback()
            await record_event(self.session, self.organization_id, execution_id,
                               "verification.cancellation_started", "worker", "verification.service",
                               data={"verification_id": verification_id},
                               idempotency_key=f"verification-cancellation-started-{verification_id}")
            await self.session.commit()
            try:
                await sandbox.cleanup()
            except Exception:
                logger.exception("verification_cancellation_cleanup_failed", verification_id=str(verification_id))
                cleanup_failed = True
            else:
                cleanup_failed = False
            sandbox_cleaned = True
            execution = (await self.session.execute(select(ExecutionJobModel).where(
                ExecutionJobModel.id == execution_id,
                ExecutionJobModel.organization_id == self.organization_id,
            ).with_for_update(key_share=True).execution_options(populate_existing=True))).scalar_one_or_none()
            current = (await self.session.execute(select(VerificationJobModel).where(
                VerificationJobModel.id == verification_id,
                VerificationJobModel.organization_id == self.organization_id,
            ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
            if not current or current.status != VerificationStatus.RUNNING or not execution or not execution.cancellation_requested_at:
                await self.session.rollback()
                return
            current.finished_at = datetime.now(UTC)
            if cleanup_failed:
                current.status = VerificationStatus.FAILED
                event_type = "verification.cancellation_failed"
                await self._finish_repair(current, False, "Verification cancellation cleanup failed")
                await self.publisher.publish(create_verification_completed_event(
                    self.organization_id, repository_id, verification_id, False,
                ))
            else:
                current.status = VerificationStatus.CANCELLED
                event_type = "verification.cancelled"
                repair = (await self.session.execute(select(RepairAttemptModel).where(
                    RepairAttemptModel.repair_execution_id == execution_id,
                    RepairAttemptModel.organization_id == self.organization_id,
                    RepairAttemptModel.status == RepairAttemptStatus.REVERIFYING,
                ))).scalar_one_or_none()
                if repair:
                    repair.status = RepairAttemptStatus.CANCELLED
                await self.publisher.publish(create_verification_cancelled_event(
                    self.organization_id, repository_id, verification_id, execution_id,
                ))
            await record_event(self.session, self.organization_id, execution_id, event_type,
                               "worker", "verification.service", data={"verification_id": verification_id},
                               idempotency_key=f"verification-cancelled-{verification_id}")
            await self.session.commit()
        except Exception as e:
            logger.error("verification_error", error=str(e))
            job.status = VerificationStatus.FAILED
            job.finished_at = datetime.now(UTC)
            await self._finish_repair(job, False, "Verification could not complete")
            await self.publisher.publish(create_verification_completed_event(self.organization_id, job.repository_id, job.id, False))
            await record_event(self.session, self.organization_id, job.execution_job_id, "verification.completed", "worker", "verification.service",
                               data={"verification_id": job.id, "status": "FAILED"},
                               idempotency_key=f"verification-completed-{job.id}")
            await self.session.commit()
        finally:
            watcher.cancel()
            try:
                await watcher
            except asyncio.CancelledError:
                pass
            if not sandbox_cleaned:
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
