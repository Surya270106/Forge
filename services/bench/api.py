"""Authenticated tenant-scoped Forge Bench API."""

from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.bench import BenchmarkRunModel, BenchmarkTrialModel
from packages.shared.identifiers import OrganizationId
from services.auth.dependencies import get_current_user, require_permission

from .dataset import load_suite
from .scoring import compare_results, summarize_trials
from .service import cancel_run, create_run

router = APIRouter(prefix="/api/v1/bench", tags=["bench"])


class CreateRunRequest(BaseModel):
    suite_id: str
    task_ids: list[str] = Field(min_length=1, max_length=12)
    repetitions: int = Field(default=1, ge=1, le=3)
    idempotency_key: UUID
    variant: str = "correct"
    baseline_run_id: UUID | None = None
    budget_seconds: int | None = Field(default=None, ge=5, le=600)


def _run_response(run: BenchmarkRunModel, trials: Sequence[BenchmarkTrialModel] | None = None) -> dict:
    response = {
        "id": str(run.id), "suite_id": run.suite_id, "suite_version": run.suite_version,
        "dataset_digest": run.dataset_digest, "status": run.status, "manifest": run.manifest,
        "baseline_run_id": str(run.baseline_run_id) if run.baseline_run_id else None,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }
    if trials is not None:
        response["trials"] = [_trial_response(trial) for trial in trials]
        response.update(summarize_trials([{"status": trial.status, "result": trial.result,
                                           "failure_category": trial.failure_category} for trial in trials]))
    return response


def _trial_response(trial: BenchmarkTrialModel) -> dict:
    return {
        "id": str(trial.id), "run_id": str(trial.run_id), "task_id": trial.task_id,
        "task_version": trial.task_version, "repetition": trial.repetition,
        "status": trial.status, "execution_id": str(trial.execution_id) if trial.execution_id else None,
        "plan_id": str(trial.plan_id) if trial.plan_id else None,
        "base_commit": trial.base_commit, "patch_digest": trial.patch_digest,
        "failure_category": trial.failure_category, "result": trial.result,
        "started_at": trial.started_at.isoformat() if trial.started_at else None,
        "finished_at": trial.finished_at.isoformat() if trial.finished_at else None,
    }


async def _visible_run(session: AsyncSession, organization_id: UUID, run_id: UUID) -> BenchmarkRunModel:
    run = (await session.execute(select(BenchmarkRunModel).where(
        BenchmarkRunModel.id == run_id, BenchmarkRunModel.organization_id == organization_id,
    ))).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    return run


@router.get("/suites")
async def list_suites(organization_id: OrganizationId = Depends(require_permission("bench:read"))):
    suite = load_suite()
    return {"suites": [{"id": suite.id, "version": suite.version, "name": suite.name,
                        "dataset_digest": suite.digest, "task_count": len(suite.tasks)}]}


@router.get("/suites/{suite_id}")
async def get_suite(suite_id: str, organization_id: OrganizationId = Depends(require_permission("bench:read"))):
    suite = load_suite()
    if suite.id != suite_id:
        raise HTTPException(status_code=404, detail="Benchmark suite not found")
    return {"id": suite.id, "version": suite.version, "name": suite.name,
            "dataset_digest": suite.digest, "tasks": [task.public() for task in suite.tasks]}


@router.get("/suites/{suite_id}/tasks/{task_id}")
async def get_task(suite_id: str, task_id: str,
                   organization_id: OrganizationId = Depends(require_permission("bench:read"))):
    suite = load_suite()
    if suite_id != suite.id:
        raise HTTPException(status_code=404, detail="Benchmark suite not found")
    task = next((task for task in suite.tasks if task.id == task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail="Benchmark task not found")
    return task.public()


@router.post("/runs", status_code=202)
async def start_run(
    request: CreateRunRequest,
    organization_id: OrganizationId = Depends(require_permission("bench:create", rate_category="execution")),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    run = await create_run(session, organization_id, UUID(user["id"]), **request.model_dump())
    return _run_response(run)


@router.get("/runs")
async def list_runs(
    cursor: UUID | None = None, limit: int = Query(20, ge=1, le=50),
    organization_id: OrganizationId = Depends(require_permission("bench:read")),
    session: AsyncSession = Depends(get_session),
):
    query = select(BenchmarkRunModel).where(BenchmarkRunModel.organization_id == organization_id)
    if cursor:
        previous = await _visible_run(session, organization_id, cursor)
        query = query.where(or_(BenchmarkRunModel.created_at < previous.created_at,
                                and_(BenchmarkRunModel.created_at == previous.created_at,
                                     BenchmarkRunModel.id < previous.id)))
    rows = (await session.execute(query.order_by(BenchmarkRunModel.created_at.desc(),
                                                 BenchmarkRunModel.id.desc()).limit(limit + 1))).scalars().all()
    return {"runs": [_run_response(run) for run in rows[:limit]],
            "next_cursor": str(rows[limit - 1].id) if len(rows) > limit else None}


@router.get("/runs/{run_id}")
async def get_run(
    run_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("bench:read")),
    session: AsyncSession = Depends(get_session),
):
    run = await _visible_run(session, organization_id, run_id)
    trials = (await session.execute(select(BenchmarkTrialModel).where(
        BenchmarkTrialModel.run_id == run_id, BenchmarkTrialModel.organization_id == organization_id,
    ).order_by(BenchmarkTrialModel.created_at, BenchmarkTrialModel.id))).scalars().all()
    return _run_response(run, trials)


@router.get("/trials/{trial_id}")
async def get_trial(
    trial_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("bench:read")),
    session: AsyncSession = Depends(get_session),
):
    trial = (await session.execute(select(BenchmarkTrialModel).where(
        BenchmarkTrialModel.id == trial_id, BenchmarkTrialModel.organization_id == organization_id,
    ))).scalar_one_or_none()
    if trial is None:
        raise HTTPException(status_code=404, detail="Benchmark trial not found")
    return _trial_response(trial)


@router.post("/runs/{run_id}/cancel")
async def cancel_benchmark_run(
    run_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("bench:cancel", rate_category="execution")),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return _run_response(await cancel_run(session, organization_id, run_id, UUID(user["id"])))


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("bench:read")),
    session: AsyncSession = Depends(get_session),
):
    return await get_run(run_id, organization_id, session)


@router.get("/compare")
async def compare_runs(
    left: UUID, right: UUID,
    organization_id: OrganizationId = Depends(require_permission("bench:read")),
    session: AsyncSession = Depends(get_session),
):
    first, second = await _visible_run(session, organization_id, left), await _visible_run(session, organization_id, right)
    if (first.dataset_digest != second.dataset_digest or first.manifest["tasks"] != second.manifest["tasks"]):
        raise HTTPException(status_code=422, detail="Benchmark datasets or selected tasks differ")
    first_trials = (await session.execute(select(BenchmarkTrialModel).where(
        BenchmarkTrialModel.run_id == left, BenchmarkTrialModel.organization_id == organization_id,
    ))).scalars().all()
    second_trials = (await session.execute(select(BenchmarkTrialModel).where(
        BenchmarkTrialModel.run_id == right, BenchmarkTrialModel.organization_id == organization_id,
    ))).scalars().all()
    first_result, second_result = _run_response(first, first_trials), _run_response(second, second_trials)
    first_result["task_ids"] = [task["id"] for task in first.manifest["tasks"]]
    second_result["task_ids"] = [task["id"] for task in second.manifest["tasks"]]
    return {"left": first_result, "right": second_result, "delta": compare_results(first_result, second_result)}
