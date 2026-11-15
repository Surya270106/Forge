import asyncio
import hashlib
import json
import secrets
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.auth import SessionModel
from packages.database.models.context import AgentInteractionModel, ContextSnapshotModel
from packages.database.models.execution import ExecutionEventModel, ExecutionJobModel, ExecutionLogModel, ExecutionStatus, MutationModel
from packages.database.models.planning import PlanModel, PlanStatus, TaskNodeModel
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.models.verification import RepairAttemptModel, RepairAttemptStatus, VerificationJobModel, VerificationStatus
from packages.shared.errors import ConflictError, ErrorCategory, NotFoundError
from packages.shared.identifiers import OrganizationId, generate_id

from .flight_recorder import ACTORS, EVENTS, SAFE_KEYS, SAFE_STRING, SENSITIVE_VALUE, record_event
from .schemas import CancelExecutionResponse, ExecutionJobResponse, ExecutionLogResponse, StartExecutionRequest

router = APIRouter(prefix="/api/v1/executions", tags=["execution"])


from services.auth.dependencies import get_current_user, require_permission


@router.post("/{job_id}/cancel", response_model=CancelExecutionResponse)
async def cancel_execution(
    job_id: UUID, response: Response,
    organization_id: OrganizationId = Depends(require_permission("exec:cancel", rate_category="execution")),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from .cancellation import request_execution_cancellation

    job = await request_execution_cancellation(session, organization_id, job_id, UUID(user["id"]))
    verification = None
    if job.status == ExecutionStatus.COMPLETED and job.cancellation_requested_at:
        verification = (await session.execute(select(VerificationJobModel).where(
            VerificationJobModel.execution_job_id == job.id,
            VerificationJobModel.organization_id == organization_id,
        ).order_by(VerificationJobModel.created_at.desc()).limit(1))).scalar_one_or_none()
    if job.status == ExecutionStatus.CANCELLED or (verification and verification.status == VerificationStatus.CANCELLED):
        cancellation_status = "completed"
    elif job.cancellation_requested_at and (job.status == ExecutionStatus.RUNNING or
                                            (verification and verification.status == VerificationStatus.RUNNING)):
        cancellation_status = "requested"
        response.status_code = 202
    elif job.cancellation_requested_at:
        cancellation_status = "failed"
    else:
        cancellation_status = "not_cancellable"
    return {"id": job.id, "status": job.status, "cancellation_status": cancellation_status,
            "cancellation_requested_at": job.cancellation_requested_at}


@router.post("/plans/{plan_id}", response_model=ExecutionJobResponse)
async def start_execution(
    plan_id: UUID,
    request: StartExecutionRequest,
    organization_id: OrganizationId = Depends(require_permission("plan:approve", rate_category="execution")),
    session: AsyncSession = Depends(get_session),
):
    plan = (
        await session.execute(
            select(PlanModel).where(PlanModel.id == plan_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not plan or plan.organization_id != organization_id:
        raise NotFoundError(code="plan_not_found", message="Plan not found", category=ErrorCategory.NOT_FOUND)  # type: ignore

    if plan.status != PlanStatus.APPROVED:
        raise ConflictError(
            code="plan_not_approved",
            message="Plan must be APPROVED to execute",
            category=ErrorCategory.CONFLICT,
        )

    repository = await session.get(RepositoryModel, plan.repository_id)
    if not repository or repository.organization_id != organization_id or repository.status != RepositoryStatus.READY or not repository.commit_sha:
        raise ConflictError(code="repository_not_ready", message="Import and index the repository before execution", category=ErrorCategory.CONFLICT)
    from packages.database.models.issue_workflow import IssueWorkflowModel
    issue_workflow = (await session.execute(select(IssueWorkflowModel).where(
        IssueWorkflowModel.organization_id == organization_id, IssueWorkflowModel.plan_id == plan_id,
    ))).scalar_one_or_none()
    if issue_workflow and (repository.commit_sha != issue_workflow.base_commit_sha or
                           repository.github_repository_id != issue_workflow.github_repository_id):
        raise ConflictError("issue_base_changed", "Issue workflow base changed; capture a new workflow", ErrorCategory.CONFLICT)

    existing = (
        await session.execute(
            select(ExecutionJobModel.id).where(
                ExecutionJobModel.plan_id == plan_id,
                ExecutionJobModel.organization_id == organization_id,
                ExecutionJobModel.status.in_([ExecutionStatus.PENDING, ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED]),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(code="plan_already_executing", message="This plan already has an execution", category=ErrorCategory.CONFLICT)

    linked_repair = (
        await session.execute(
            select(RepairAttemptModel).where(
                RepairAttemptModel.repair_plan_id == plan_id,
                RepairAttemptModel.organization_id == organization_id,
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if linked_repair and linked_repair.status != RepairAttemptStatus.AWAITING_APPROVAL:
        raise ConflictError("repair_not_approved", "Repair proposal is not ready for execution", ErrorCategory.CONFLICT)

    from services.safety.service import as_document, current_policy

    safety_policy = await current_policy(session, organization_id)
    if safety_policy.stopped:
        raise ConflictError("safety_stop_active", "Safety Gate emergency stop is active", ErrorCategory.CONFLICT)

    job = ExecutionJobModel(
        id=generate_id(),
        organization_id=organization_id,
        repository_id=plan.repository_id,
        plan_id=plan_id,
        status=ExecutionStatus.PENDING,
        commit_sha_before=repository.commit_sha,
        safety_policy_snapshot=as_document(safety_policy),
    )
    session.add(job)
    if linked_repair:
        linked_repair.repair_execution_id = job.id
        linked_repair.status = RepairAttemptStatus.EXECUTING

    from .events import ExecutionEventPublisher, create_execution_requested_event

    publisher = ExecutionEventPublisher(session)
    event = create_execution_requested_event(organization_id, plan.repository_id, job.id, plan_id)
    await publisher.publish(event)

    await session.flush()
    interactions = (await session.execute(select(AgentInteractionModel)
        .join(ContextSnapshotModel, AgentInteractionModel.context_snapshot_id == ContextSnapshotModel.id)
        .where(ContextSnapshotModel.plan_id == plan_id, AgentInteractionModel.organization_id == organization_id)
        .order_by(AgentInteractionModel.created_at, AgentInteractionModel.id))).scalars().all()
    nodes = (await session.execute(select(TaskNodeModel).where(
        TaskNodeModel.plan_id == plan_id, TaskNodeModel.organization_id == organization_id,
    ))).scalars().all()
    history: list[tuple[datetime, str, UUID | None, dict, str]] = []
    for interaction in interactions:
        model = interaction.model if SAFE_STRING.fullmatch(interaction.model) else "sha256:" + hashlib.sha256(interaction.model.encode()).hexdigest()
        history.append((interaction.created_at, "model.completed", None,
                        {"interaction_id": interaction.id, "provider": interaction.provider.value,
                         "model": model, "prompt_tokens": interaction.prompt_tokens,
                         "completion_tokens": interaction.completion_tokens, "latency_ms": interaction.latency_ms},
                        f"model-{interaction.id}"))
    for node in nodes:
        history.append((node.created_at, "task.created", node.id,
                        {"node_id": node.id}, f"task-created-{node.id}"))
    for occurred_at, event_type, node_id, data, key in sorted(history, key=lambda item: (item[0], item[4])):
        await record_event(session, organization_id, job.id, event_type, "agent" if event_type == "model.completed" else "system",
                           "planning.context_engine" if event_type == "model.completed" else "planning.service",
                           data=data, task_node_id=node_id, occurred_at=occurred_at, idempotency_key=key)
    await record_event(session, organization_id, job.id, "execution.queued", "user", "execution.api",
                       data={"plan_id": plan_id, "repository_id": plan.repository_id}, idempotency_key="queued")

    await session.commit()
    return job


def _event_response(event: ExecutionEventModel) -> dict:
    # Migration data is private by default, even if a future writer bypasses the service.
    safe = {key: value for key, value in (event.data or {}).items()
            if key in SAFE_KEYS and isinstance(value, (str, int, bool))
            and (not isinstance(value, str) or (SAFE_STRING.fullmatch(value) and not SENSITIVE_VALUE.search(value)))
            and len(str(value)) <= 128}
    event_type = event.event_type if event.event_type in EVENTS else "unknown"
    def safe_ref(value: str | None) -> str | None:
        return value if value and SAFE_STRING.fullmatch(value) and not SENSITIVE_VALUE.search(value) else None
    return {
        "id": str(event.id), "execution_id": str(event.execution_job_id),
        "task_node_id": str(event.task_node_id) if event.task_node_id else None,
        "sequence": event.sequence, "attempt": event.attempt, "event_type": event_type,
        "occurred_at": event.occurred_at.isoformat(), "actor_type": event.actor_type if event.actor_type in ACTORS else "system",
        "actor_id": safe_ref(event.actor_id), "source": safe_ref(event.source) or "unknown",
        "summary": event_type.replace(".", " ").replace("_", " ").capitalize(),
        "data": safe, "correlation_id": safe_ref(event.correlation_id),
        "causation_id": safe_ref(event.causation_id), "schema_version": event.schema_version,
    }


async def _visible_job(session: AsyncSession, job_id: UUID, organization_id: UUID) -> None:
    job = await session.get(ExecutionJobModel, job_id)
    if not job or job.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Execution not found")


@router.get("/{job_id}/timeline")
async def execution_timeline(
    job_id: UUID, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    event_type: str | None = None, actor_type: str | None = None, attempt: int | None = Query(None, ge=0),
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    await _visible_job(session, job_id, organization_id)
    if event_type is not None and event_type not in EVENTS:
        raise HTTPException(status_code=422, detail="Unknown event type")
    if actor_type is not None and actor_type not in ACTORS:
        raise HTTPException(status_code=422, detail="Unknown actor type")
    query = select(ExecutionEventModel).where(
        ExecutionEventModel.organization_id == organization_id,
        ExecutionEventModel.execution_job_id == job_id,
        ExecutionEventModel.sequence > cursor,
    )
    if event_type:
        query = query.where(ExecutionEventModel.event_type == event_type)
    if actor_type:
        query = query.where(ExecutionEventModel.actor_type == actor_type)
    if attempt is not None:
        query = query.where(ExecutionEventModel.attempt == attempt)
    rows = (await session.execute(query.order_by(ExecutionEventModel.sequence).limit(limit + 1))).scalars().all()
    page = rows[:limit]
    return {"events": [_event_response(row) for row in page],
            "next_cursor": page[-1].sequence if len(rows) > limit else None}


@router.get("/{job_id}/timeline/export")
async def export_execution_timeline(
    job_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    await _visible_job(session, job_id, organization_id)
    exported_at = datetime.now(UTC).isoformat()

    async def stream():
        yield json.dumps({"execution_id": str(job_id), "exported_at": exported_at, "schema_version": 1})[:-1] + ',"events":['
        cursor = 0
        first = True
        while True:
            rows = (await session.execute(select(ExecutionEventModel).where(
                ExecutionEventModel.organization_id == organization_id,
                ExecutionEventModel.execution_job_id == job_id,
                ExecutionEventModel.sequence > cursor,
            ).order_by(ExecutionEventModel.sequence).limit(100))).scalars().all()
            if not rows:
                break
            for row in rows:
                yield ("" if first else ",") + json.dumps(_event_response(row))
                first = False
            cursor = rows[-1].sequence
        yield "]}"

    return StreamingResponse(stream(), media_type="application/json",
                             headers={"Content-Disposition": f'attachment; filename="forge-execution-{job_id}.json"'})


@router.get("/{job_id}/timeline/{event_id}")
async def get_execution_event(
    job_id: UUID, event_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    await _visible_job(session, job_id, organization_id)
    event = (await session.execute(select(ExecutionEventModel).where(
        ExecutionEventModel.id == event_id,
        ExecutionEventModel.execution_job_id == job_id,
        ExecutionEventModel.organization_id == organization_id,
    ))).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_response(event)


@router.get("/{job_id}", response_model=ExecutionJobResponse)
async def get_execution_status(
    job_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    job = await session.get(ExecutionJobModel, job_id)
    if not job or job.organization_id != organization_id:
        raise NotFoundError(code="job_not_found", message="Job not found", category=ErrorCategory.NOT_FOUND)  # type: ignore
    return job


@router.get("/plans/{plan_id}/latest", response_model=ExecutionJobResponse)
async def get_latest_execution_for_plan(
    plan_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    job = (
        await session.execute(
            select(ExecutionJobModel).where(
                ExecutionJobModel.plan_id == plan_id,
                ExecutionJobModel.organization_id == organization_id,
            ).order_by(ExecutionJobModel.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Execution not found")
    return job


@router.get("/{job_id}/logs", response_model=list[ExecutionLogResponse])
async def get_execution_logs(
    job_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(ExecutionLogModel)
        .where(
            ExecutionLogModel.execution_job_id == job_id,
            ExecutionLogModel.organization_id == organization_id,
        )
        .order_by(ExecutionLogModel.created_at.asc())
    )

    logs = (await session.execute(stmt)).scalars().all()
    return logs


@router.get("/{job_id}/mutations")
async def get_execution_mutations(
    job_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(MutationModel).where(
        MutationModel.execution_job_id == job_id,
        MutationModel.organization_id == organization_id,
    )
    mutations = (await session.execute(stmt)).scalars().all()

    return {"mutations": [{"id": str(m.id), "file_path": m.file_path, "mutation_type": m.mutation_type, "diff_hunk": m.diff_hunk} for m in mutations]}


@router.post("/{job_id}/ws-ticket")
async def create_websocket_ticket(
    job_id: UUID,
    request: Request,
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    import redis.asyncio as redis_async

    from packages.shared.config import get_settings
    from services.auth.jwt import decode_access_token

    job = await session.get(ExecutionJobModel, job_id)
    if not job or job.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Execution not found")
    token = request.cookies.get("forge_session")
    if not token:
        header = request.headers.get("authorization", "")
        token = header.removeprefix("Bearer ") if header.startswith("Bearer ") else None
    if not token:
        raise HTTPException(status_code=401, detail="Invalid session")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid session")

    ticket = secrets.token_urlsafe(32)
    redis_client = redis_async.from_url(get_settings().redis_url)
    try:
        stored = await redis_client.set(
            f"forge:ws-ticket:{ticket}",
            json.dumps({"job_id": str(job_id), "organization_id": str(organization_id), "user_id": payload["sub"], "session_id": payload["session_id"]}),
            ex=45,
            nx=True,
        )
    finally:
        await redis_client.aclose()
    if not stored:
        raise HTTPException(status_code=503, detail="WebSocket ticket unavailable")
    return {"ticket": ticket, "expires_in": 45}


@router.websocket("/{job_id}/ws")
async def websocket_endpoint(websocket: WebSocket, job_id: UUID):
    import redis.asyncio as redis_async

    from packages.database.engine import get_engine, get_session_factory
    from packages.database.tenant import set_system_context
    from packages.shared.config import get_settings
    from services.auth.dependencies import _verify_and_set_tenant

    settings = get_settings()
    offered = [part.strip() for part in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    ticket = next((part[len("forge.ticket."):] for part in offered if part.startswith("forge.ticket.")), None)
    if not ticket or "forge.v1" not in offered or websocket.headers.get("origin") != settings.frontend_url:
        await websocket.close(code=1008)
        return

    try:
        ticket_redis = redis_async.from_url(settings.redis_url)
        try:
            ticket_data = await ticket_redis.getdel(f"forge:ws-ticket:{ticket}")
        finally:
            await ticket_redis.aclose()
        if not ticket_data:
            raise HTTPException(status_code=401)
        claims = json.loads(ticket_data)
        if claims["job_id"] != str(job_id):
            raise HTTPException(status_code=403)
        set_system_context()
        async with get_session_factory(get_engine(settings.database_url))() as session:
            db_session = await session.get(SessionModel, UUID(claims["session_id"]))
            if not db_session or not db_session.is_active or str(db_session.user_id) != claims["user_id"] or db_session.expires_at < datetime.now(UTC).replace(tzinfo=None):
                raise HTTPException(status_code=401)
            organization_id = await _verify_and_set_tenant(websocket, claims["organization_id"], {"id": claims["user_id"]}, session, "exec:read")
            job = await session.get(ExecutionJobModel, job_id)
            if not job or job.organization_id != organization_id:
                raise HTTPException(status_code=404)
    except (HTTPException, ValueError, KeyError, json.JSONDecodeError):
        await websocket.close(code=1008)
        return

    await websocket.accept(subprotocol="forge.v1")
    redis_client = redis_async.from_url(settings.redis_url)
    pubsub = redis_client.pubsub()
    channel_name = f"execution:{job_id}:logs"
    disconnect_task = asyncio.create_task(websocket.receive())
    try:
        await pubsub.subscribe(channel_name)
        while True:
            if disconnect_task.done():
                event = disconnect_task.result()
                if event["type"] == "websocket.disconnect":
                    break
                disconnect_task = asyncio.create_task(websocket.receive())
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                data_str = message["data"].decode("utf-8")
                await websocket.send_text(data_str)
    except WebSocketDisconnect:
        pass
    finally:
        disconnect_task.cancel()
        await pubsub.unsubscribe(channel_name)
        await pubsub.aclose()
        await redis_client.aclose()
