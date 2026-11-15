"""Transaction-bound execution evidence. Payloads contain references, never content."""

import hashlib
import json
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.execution import ExecutionEventModel, ExecutionJobModel
from packages.shared.identifiers import generate_id

EVENTS = {
    "task.created", "execution.queued", "execution.started", "execution.completed", "execution.failed",
    "execution.cancel_requested", "execution.cancellation_started", "execution.cancelled", "execution.cancellation_failed",
    "execution.recovered", "worker.claimed", "worker.lease_expired", "worker.reclaimed",
    "agent.started", "agent.step_started", "agent.step_completed", "agent.failed", "agent.completed",
    "tool.started", "tool.completed", "tool.failed", "sandbox.created", "sandbox.start_failed",
    "sandbox.cleanup_started", "sandbox.cleanup_completed", "sandbox.cleanup_failed", "sandbox.command_started",
    "sandbox.command_completed", "sandbox.command_failed", "sandbox.timed_out",
    "sandbox.output_limit_exceeded", "sandbox.cancelled", "repository.worktree_created",
    "repository.worktree_recovered", "repository.change_detected", "repository.mutation_committed", "verification.started",
    "verification.plan_selected", "verification.check_started", "verification.check_passed", "verification.check_failed",
    "verification.check_skipped",
    "verification.completed", "verification.cancellation_started", "verification.cancelled",
    "verification.cancellation_failed",
    "model.completed", "patch.created", "patch.updated", "patch.reviewed",
    "patch.approved", "patch.rejected", "patch.publication_started", "patch.published",
    "patch.publication_failed", "patch.publication_uncertain",
    "bench.trial_started", "bench.trial_scored", "bench.trial_failed",
    "safety.policy_resolved", "safety.permission_granted", "safety.permission_denied",
    "safety.approval_required", "safety.emergency_stop", "safety.policy_changed",
    "atlas.index_requested", "atlas.index_started", "atlas.files_parsed",
    "atlas.snapshot_published", "atlas.index_failed",
}
ACTORS = {"user", "worker", "agent", "tool", "sandbox", "system"}
SAFE_KEYS = {
    "plan_id", "selection_id", "repository_id", "node_id", "verification_id", "result_id", "patch_id",
    "review_digest", "base_commit", "commit_sha", "branch_name", "generation",
    "duration_ms", "exit_code", "stdout_bytes", "stderr_bytes", "action_type",
    "check_id", "status", "reason_code", "mutation_id", "file_count", "retry_count",
    "interaction_id", "provider", "model", "prompt_tokens", "completion_tokens", "latency_ms", "sandbox_id",
    "run_id", "trial_id",
    "capability", "policy_version", "decision", "risk", "action_digest",
    "atlas_job_id", "atlas_snapshot_id", "indexer_version", "node_count", "edge_count",
    "image_ref", "image_digest",
}
SAFE_STRING = re.compile(r"^[A-Za-z0-9_.:/-]{1,128}$")
SENSITIVE_VALUE = re.compile(r"(?i)(?:^sk-|^gh[pousr]_|^github_pat_|^xox[baprs]-|^AIza|^bearer|password|secret|api[_-]?key)")


async def record_event(
    session: AsyncSession,
    organization_id: UUID,
    execution_id: UUID,
    event_type: str,
    actor_type: str,
    source: str,
    *,
    data: dict | None = None,
    task_node_id: UUID | None = None,
    actor_id: str | None = None,
    idempotency_key: str | None = None,
    owner: str | None = None,
    generation: int | None = None,
    occurred_at: datetime | None = None,
) -> ExecutionEventModel:
    if event_type not in EVENTS or actor_type not in ACTORS or not SAFE_STRING.fullmatch(source):
        raise ValueError("Invalid execution event category")
    if actor_id is not None and (not SAFE_STRING.fullmatch(actor_id) or SENSITIVE_VALUE.search(actor_id)):
        raise ValueError("Invalid actor identifier")
    if idempotency_key is not None and not SAFE_STRING.fullmatch(idempotency_key):
        raise ValueError("Invalid event idempotency key")
    safe_data: dict = {}
    for key, value in (data or {}).items():
        if key not in SAFE_KEYS or not isinstance(value, (str, int, bool, UUID)):
            raise ValueError("Unsafe execution event metadata")
        if isinstance(value, UUID):
            value = str(value)
        if isinstance(value, str) and not SAFE_STRING.fullmatch(value):
            raise ValueError("Unsafe execution event metadata")
        if isinstance(value, str) and SENSITIVE_VALUE.search(value):
            value = "sha256:" + hashlib.sha256(value.encode()).hexdigest()
        safe_data[key] = value
    if len(json.dumps(safe_data)) > 2048:
        raise ValueError("Execution event metadata exceeds limit")
    job = (await session.execute(
        select(ExecutionJobModel).where(ExecutionJobModel.id == execution_id, ExecutionJobModel.organization_id == organization_id)
        .with_for_update(key_share=True).execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if job is None:
        raise ValueError("Execution unavailable for event")
    if owner is not None and (
        job.lease_owner != owner or job.lease_generation != generation
        or job.lease_expires_at is None or job.lease_expires_at <= datetime.now(UTC)
    ):
        raise ValueError("Execution ownership changed")
    if idempotency_key:
        prior = (await session.execute(select(ExecutionEventModel).where(
            ExecutionEventModel.execution_job_id == execution_id,
            ExecutionEventModel.idempotency_key == idempotency_key,
        ))).scalar_one_or_none()
        if prior:
            return prior
    sequence = ((await session.scalar(select(func.coalesce(func.max(ExecutionEventModel.sequence), 0)).where(
        ExecutionEventModel.execution_job_id == execution_id,
    ))) or 0) + 1
    event = ExecutionEventModel(
        id=generate_id(), organization_id=organization_id, execution_job_id=execution_id,
        task_node_id=task_node_id, sequence=sequence, attempt=job.lease_generation,
        event_type=event_type, occurred_at=occurred_at or datetime.now(UTC), actor_type=actor_type,
        actor_id=actor_id, source=source, summary=event_type.replace(".", " ").replace("_", " ").capitalize(),
        data=safe_data, correlation_id=str(execution_id), idempotency_key=idempotency_key, schema_version=1,
    )
    session.add(event)
    await session.flush()
    if event_type in {"execution.started", "worker.lease_expired", "execution.completed", "execution.failed",
                      "execution.cancelled", "execution.cancellation_failed", "verification.completed",
                      "verification.cancelled", "verification.cancellation_failed"}:
        from services.execution.run_capsules import capture_event_capsule

        await capture_event_capsule(session, event, job)
    return event
