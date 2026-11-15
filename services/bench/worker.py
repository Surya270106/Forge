"""Advance benchmark trials through the existing execution outbox and Docker worker."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bench.private.solutions import deterministic_edits
from packages.database.models.bench import BenchmarkRunModel, BenchmarkTrialModel
from packages.database.models.execution import ExecutionJobModel, ExecutionStatus
from packages.database.models.planning import PlanModel, PlanStatus, TaskNodeModel
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.models.verification import VerificationJobModel
from packages.shared.events import EventEnvelope
from packages.shared.identifiers import generate_id
from services.execution.events import ExecutionEventPublisher, create_execution_requested_event
from services.execution.flight_recorder import record_event
from services.execution.workspace import execution_workspace_path
from services.safety.service import as_document, current_policy

from .dataset import load_suite
from .fixture import materialize_fixture
from .grader import GradingInfrastructureError, grade_candidate
from .scoring import score_trial


async def start_next_trial(session: AsyncSession, organization_id: UUID, run_id: UUID, settings) -> None:
    run = (await session.execute(select(BenchmarkRunModel).where(
        BenchmarkRunModel.id == run_id, BenchmarkRunModel.organization_id == organization_id,
    ).with_for_update())).scalar_one_or_none()
    if run is None or run.status in {"COMPLETED", "CANCELLED", "FAILED"}:
        return
    trials = (await session.execute(select(BenchmarkTrialModel).where(
        BenchmarkTrialModel.run_id == run_id, BenchmarkTrialModel.organization_id == organization_id,
    ).order_by(BenchmarkTrialModel.created_at, BenchmarkTrialModel.id).with_for_update())).scalars().all()
    if any(trial.status == "RUNNING" for trial in trials):
        return
    if run.status == "CANCELLING":
        run.status = "CANCELLED"
        run.finished_at = datetime.now(UTC)
        await session.commit()
        return
    trial = next((trial for trial in trials if trial.status == "PENDING"), None)
    if trial is None:
        run.status = "COMPLETED"
        run.finished_at = datetime.now(UTC)
        await session.commit()
        return
    suite = load_suite()
    if run.dataset_digest != suite.digest:
        trial.status = "ERROR"
        trial.failure_category = "dataset_changed"
        run.status = "FAILED"
        run.finished_at = trial.finished_at = datetime.now(UTC)
        await session.commit()
        return
    task = next(task for task in suite.tasks if task.id == trial.task_id)
    repo_id = trial.id  # Stable across a redelivered scheduling event.
    root = Path(settings.workspace_root).resolve()
    workspace = root / str(organization_id) / str(repo_id)
    if not workspace.resolve().is_relative_to(root):
        raise ValueError("Benchmark workspace escaped the configured root")
    try:
        materialize_fixture(workspace, trial.base_commit)
    except (OSError, ValueError):
        trial.status = "ERROR"
        trial.failure_category = "fixture_unavailable"
        run.status = "FAILED"
        run.finished_at = trial.finished_at = datetime.now(UTC)
        await session.commit()
        return
    repository = await session.get(RepositoryModel, repo_id)
    if repository is None:
        repository = RepositoryModel(
            id=repo_id, organization_id=organization_id, owner="forge-bench", name=str(trial.id),
            full_name=f"forge-bench/{trial.id}", clone_url=str(workspace), status=RepositoryStatus.READY,
            commit_sha=trial.base_commit, primary_language="Python", is_private=True,
        )
        session.add(repository)
        await session.flush()
    plan = PlanModel(
        id=generate_id(), organization_id=organization_id, repository_id=repo_id, status=PlanStatus.APPROVED,
        intent=task.instruction, context_snapshot={"bench_budget_seconds": next(
            item["budget_seconds"] for item in run.manifest["tasks"] if item["id"] == task.id)},
    )
    session.add(plan)
    await session.flush()
    variant = run.manifest["variant"]
    edits = deterministic_edits(task.id, variant)
    if variant == "timeout":
        session.add(TaskNodeModel(id=generate_id(), organization_id=organization_id, plan_id=plan.id,
                                  action_type="command", target="workspace", parameters={"command": "sleep 10"}))
    else:
        session.add_all([
            TaskNodeModel(id=generate_id(), organization_id=organization_id, plan_id=plan.id,
                          action_type="edit_file", target=path, parameters={"changes": content})
            for path, content in edits
        ])
    await session.flush()
    execution = ExecutionJobModel(
        id=generate_id(), organization_id=organization_id, repository_id=repo_id,
        plan_id=plan.id, status=ExecutionStatus.PENDING, commit_sha_before=trial.base_commit,
        safety_policy_snapshot=as_document(await current_policy(session, organization_id)),
    )
    session.add(execution)
    await session.flush()
    trial.execution_id = execution.id
    trial.plan_id = plan.id
    trial.status = "RUNNING"
    trial.started_at = datetime.now(UTC)
    run.status = "RUNNING"
    run.started_at = run.started_at or trial.started_at
    await session.flush()
    await record_event(session, organization_id, execution.id, "bench.trial_started", "worker", "bench.worker",
                       data={"run_id": run.id, "trial_id": trial.id}, idempotency_key=f"bench-start-{trial.id}")
    await ExecutionEventPublisher(session).publish(
        create_execution_requested_event(organization_id, repo_id, execution.id, plan.id)
    )
    await session.commit()


async def finish_trial(session: AsyncSession, organization_id: UUID, execution_id: UUID, settings) -> None:
    trial_ref = (await session.execute(select(BenchmarkTrialModel.run_id).where(
        BenchmarkTrialModel.execution_id == execution_id,
        BenchmarkTrialModel.organization_id == organization_id,
    ))).scalar_one_or_none()
    if trial_ref is None:
        return
    run = (await session.execute(select(BenchmarkRunModel).where(
        BenchmarkRunModel.id == trial_ref, BenchmarkRunModel.organization_id == organization_id,
    ).with_for_update())).scalar_one()
    trial = (await session.execute(select(BenchmarkTrialModel).where(
        BenchmarkTrialModel.execution_id == execution_id,
        BenchmarkTrialModel.organization_id == organization_id,
    ).with_for_update())).scalar_one()
    if trial.status != "RUNNING":
        return
    execution = await session.get(ExecutionJobModel, execution_id)
    if not execution or execution.status not in {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}:
        return
    trial.finished_at = datetime.now(UTC)
    if execution.status == ExecutionStatus.COMPLETED and run.status != "CANCELLING":
        suite = load_suite()
        if suite.digest != run.dataset_digest:
            trial.status = "ERROR"
            trial.failure_category = "dataset_changed"
            run.status = "FAILED"
            run.finished_at = datetime.now(UTC)
            await session.commit()
            return
        task = next(task for task in suite.tasks if task.id == trial.task_id)
        workspace = execution_workspace_path(settings.workspace_root, organization_id, execution.repository_id,
                                             execution_id, execution.lease_generation)
        try:
            if not workspace.resolve().is_relative_to(Path(settings.workspace_root).resolve()):
                raise GradingInfrastructureError("Candidate workspace escaped the configured root")
            grade = await grade_candidate(task, workspace)
        except GradingInfrastructureError:
            trial.status = "ERROR"
            trial.failure_category = "infrastructure"
        else:
            verification = (await session.execute(select(VerificationJobModel).where(
                VerificationJobModel.execution_job_id == execution_id,
                VerificationJobModel.organization_id == organization_id,
            ).order_by(VerificationJobModel.created_at.desc()).limit(1))).scalar_one_or_none()
            ended_at = execution.finished_at or trial.finished_at or datetime.now(UTC)
            started_at = execution.started_at or trial.started_at or ended_at
            duration_ms = round((ended_at - started_at).total_seconds() * 1000)
            checks = [*grade["checks"], {"id": "execution-completed", "category": "reliability",
                      "required": True, "status": "passed", "duration_ms": 0, "exit_code": 0, "output_sha256": None}]
            result = score_trial(checks, {
                "duration_ms": duration_ms,
                "budget_ms": next(item["budget_seconds"] * 1000 for item in run.manifest["tasks"] if item["id"] == task.id),
                "token_count": None, "retry_count": max(0, execution.lease_generation - 1),
                "verification_status": verification.status.value if verification else None,
            })
            result.update({"patch_digest": grade["patch_digest"], "grader_version": grade["grader_version"],
                           "changed_paths": grade["changed_paths"], "execution_id": str(execution_id),
                           "attempt_generation": execution.lease_generation})
            trial.patch_digest = grade["patch_digest"]
            trial.result = result
            trial.status = "PASSED" if result["passed"] else "FAILED"
            trial.failure_category = None if result["passed"] else "agent"
            await record_event(session, organization_id, execution_id, "bench.trial_scored", "worker", "bench.worker",
                               data={"run_id": run.id, "trial_id": trial.id}, idempotency_key=f"bench-score-{trial.id}")
    else:
        trial.status = "CANCELLED" if execution.status == ExecutionStatus.CANCELLED or run.status == "CANCELLING" else "FAILED"
        trial.failure_category = "cancelled" if trial.status == "CANCELLED" else "agent"
        await record_event(session, organization_id, execution_id, "bench.trial_failed", "worker", "bench.worker",
                           data={"run_id": run.id, "trial_id": trial.id}, idempotency_key=f"bench-fail-{trial.id}")
    await ExecutionEventPublisher(session).publish(EventEnvelope(
        event_type="bench.run_requested", organization_id=str(organization_id), aggregate_type="bench",
        aggregate_id=str(run.id), payload={"run_id": str(run.id)},
    ))
    await session.commit()
