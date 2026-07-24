import asyncio
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

from packages.database.engine import get_session
from packages.database.models.execution import ExecutionJobModel
from packages.database.models.verification import RepairAttemptModel, VerificationJobModel, VerificationResultModel, VerificationStatus
from packages.shared.config import get_settings
from services.planning.service import PlanningService

logger = structlog.get_logger(__name__)


from sqlalchemy.ext.asyncio import AsyncSession

async def handle_repair_attempted(payload: dict[str, Any], session: AsyncSession) -> None:
    """
    Handles the verification.repair_attempted event.
    Extracts diagnostics from failed verification results and uses the
    PlanningService to revise the original plan (if any) or create a new plan
    to repair the failed checks.
    """
    organization_id = UUID(payload["organization_id"])
    repair_id = UUID(payload["repair_id"])
    verification_job_id = UUID(payload["verification_job_id"])

    try:
        repair = await session.get(RepairAttemptModel, repair_id)
        if not repair:
            logger.error("repair_not_found", repair_id=str(repair_id))
            return

        vjob = await session.get(VerificationJobModel, verification_job_id)
        if not vjob:
            logger.error("verification_job_not_found", verification_job_id=str(verification_job_id))
            return

        exec_job = await session.get(ExecutionJobModel, vjob.execution_job_id)
        if not exec_job:
            logger.error("execution_job_not_found", execution_job_id=str(vjob.execution_job_id))
            return

        # Fetch failed verification results
        stmt = select(VerificationResultModel).where(
            VerificationResultModel.verification_job_id == verification_job_id,
            VerificationResultModel.status == VerificationStatus.FAILED,
        )
        failed_results = (await session.execute(stmt)).scalars().all()

        if not failed_results:
            logger.warning("no_failed_results_found", verification_job_id=str(verification_job_id))
            return

        # Construct feedback prompt
        feedback_lines = ["Verification failed. Please fix the following issues:"]
        for result in failed_results:
            feedback_lines.append(f"\n--- Verifier: {result.verifier} ---")
            feedback_lines.append(f"Exit code: {result.exit_code}")
            if result.stdout:
                feedback_lines.append(f"STDOUT:\n{result.stdout[-2000:]}")
            if result.stderr:
                feedback_lines.append(f"STDERR:\n{result.stderr[-2000:]}")
            if result.diagnostics:
                feedback_lines.append(f"Diagnostics: {result.diagnostics}")

        feedback = "\n".join(feedback_lines)
        
        # Update repair attempt
        repair.prompt_used = feedback
        await session.commit()

        planning_svc = PlanningService(session, organization_id)
        
        if exec_job.plan_id:
            try:
                await planning_svc.revise_plan(exec_job.plan_id, feedback)
                logger.info("repair_plan_revised", plan_id=str(exec_job.plan_id), repair_id=str(repair_id))
            except Exception as e:
                logger.error("repair_plan_revision_failed", error=str(e))
        else:
            # Fallback if there was no plan (e.g. manual execution)
            await planning_svc.create_plan(repair.repository_id, intent=f"Repair verification failures:\n{feedback}")
            logger.info("repair_new_plan_created", repair_id=str(repair_id))

    except Exception as e:
        logger.exception("repair_worker_failed", error=str(e))
