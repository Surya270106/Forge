"""Tenant-scoped benchmark run creation and progress."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.auth import OrganizationModel
from packages.database.models.bench import BenchmarkRunModel, BenchmarkTrialModel
from packages.shared.events import EventEnvelope
from packages.shared.identifiers import generate_id
from services.execution.events import ExecutionEventPublisher

from .dataset import load_suite
from .scoring import SCORING_VERSION


async def create_run(session: AsyncSession, organization_id: UUID, owner_id: UUID, *,
                     suite_id: str, task_ids: list[str], repetitions: int,
                     idempotency_key: UUID, variant: str = "correct", baseline_run_id: UUID | None = None,
                     budget_seconds: int | None = None) -> BenchmarkRunModel:
    suite = load_suite()
    if suite_id != suite.id or not task_ids or len(task_ids) != len(set(task_ids)) or len(task_ids) * repetitions > 24:
        raise HTTPException(status_code=422, detail="Invalid benchmark selection")
    selected = [task for task in suite.tasks if task.id in task_ids]
    if len(selected) != len(task_ids) or not 1 <= repetitions <= 3:
        raise HTTPException(status_code=422, detail="Invalid benchmark selection")
    if budget_seconds is not None and not 5 <= budget_seconds <= 600:
        raise HTTPException(status_code=422, detail="Invalid execution budget")
    if variant not in {"correct", "incorrect", "regression", "timeout"} or (
        variant != "correct" and task_ids != ["clamp-boundary"]
    ):
        raise HTTPException(status_code=422, detail="Invalid infrastructure demo variant")
    request = {"task_ids": task_ids, "repetitions": repetitions, "variant": variant,
               "baseline_run_id": str(baseline_run_id) if baseline_run_id else None,
               "budget_seconds": budget_seconds}
    request_hash = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    organization = (await session.execute(select(OrganizationModel).where(
        OrganizationModel.id == organization_id).with_for_update())).scalar_one_or_none()
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    prior = (await session.execute(select(BenchmarkRunModel).where(
        BenchmarkRunModel.organization_id == organization_id,
        BenchmarkRunModel.idempotency_key == str(idempotency_key),
    ))).scalar_one_or_none()
    if prior:
        if prior.manifest.get("request_hash") != request_hash:
            raise HTTPException(status_code=409, detail="Idempotency key was used for a different run")
        return prior
    active = (await session.execute(select(BenchmarkRunModel.id).where(
        BenchmarkRunModel.organization_id == organization_id,
        BenchmarkRunModel.status.in_(["PENDING", "RUNNING", "CANCELLING"]),
    ).limit(1))).scalar_one_or_none()
    if active:
        raise HTTPException(status_code=409, detail="Another benchmark run is active")
    if baseline_run_id:
        baseline = await session.get(BenchmarkRunModel, baseline_run_id)
        if not baseline or baseline.organization_id != organization_id or baseline.dataset_digest != suite.digest:
            raise HTTPException(status_code=422, detail="Baseline uses a different dataset")
    solution_digest = hashlib.sha256(
        (Path(__file__).resolve().parents[2] / "bench" / "private" / "solutions.py").read_bytes()
    ).hexdigest()
    manifest = {
        "suite_id": suite.id, "suite_version": suite.version, "dataset_digest": suite.digest,
        "tasks": [{"id": task.id, "version": task.version, "base_commit": task.base_commit,
                   "budget_seconds": 2 if variant == "timeout" else min(task.budget_seconds, budget_seconds or task.budget_seconds)} for task in selected],
        "repetitions": repetitions, "mode": "deterministic_infrastructure_demo", "variant": variant,
        "agent_fingerprint": solution_digest, "provider": "deterministic", "model": "fixture-oracle-v1",
        "tool_fingerprint": hashlib.sha256(b"Forge edit_file, command, DockerSandbox v1").hexdigest(),
        "prompt_revision": None, "forge_version": "0.1.0-alpha.1",
        "sandbox_image": "python:3.12-slim", "grader_version": 1, "scoring_version": SCORING_VERSION,
        "random_seed": None, "request_hash": request_hash,
    }
    run = BenchmarkRunModel(
        id=generate_id(), organization_id=organization_id, owner_id=owner_id,
        suite_id=suite.id, suite_version=suite.version, dataset_digest=suite.digest,
        idempotency_key=str(idempotency_key), manifest=manifest, status="PENDING",
        baseline_run_id=baseline_run_id,
    )
    session.add(run)
    await session.flush()
    session.add_all([
        BenchmarkTrialModel(id=generate_id(), organization_id=organization_id, run_id=run.id,
                            task_id=task.id, task_version=task.version, repetition=repetition,
                            base_commit=task.base_commit, status="PENDING")
        for task in selected for repetition in range(1, repetitions + 1)
    ])
    await ExecutionEventPublisher(session).publish(EventEnvelope(
        event_type="bench.run_requested", organization_id=str(organization_id), aggregate_type="bench",
        aggregate_id=str(run.id), payload={"run_id": str(run.id)},
    ))
    await session.commit()
    return run


async def cancel_run(session: AsyncSession, organization_id: UUID, run_id: UUID, owner_id: UUID) -> BenchmarkRunModel:
    run = (await session.execute(select(BenchmarkRunModel).where(
        BenchmarkRunModel.id == run_id, BenchmarkRunModel.organization_id == organization_id,
    ).with_for_update())).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    if run.status in {"COMPLETED", "CANCELLED", "FAILED"}:
        return run
    trials = (await session.execute(select(BenchmarkTrialModel).where(
        BenchmarkTrialModel.run_id == run_id, BenchmarkTrialModel.organization_id == organization_id,
    ))).scalars().all()
    for trial in trials:
        if trial.status == "PENDING":
            trial.status = "CANCELLED"
            trial.finished_at = datetime.now(UTC)
    current = next((trial for trial in trials if trial.status == "RUNNING" and trial.execution_id), None)
    run.status = "CANCELLING" if current else "CANCELLED"
    if not current:
        run.finished_at = datetime.now(UTC)
    await session.commit()
    if current and current.execution_id is not None:
        from services.execution.cancellation import request_execution_cancellation

        await request_execution_cancellation(session, organization_id, current.execution_id, owner_id)
    return run
