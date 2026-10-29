import asyncio
import json
import secrets
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.auth import SessionModel
from packages.database.models.execution import ExecutionJobModel, ExecutionLogModel, ExecutionStatus, MutationModel
from packages.database.models.planning import PlanModel, PlanStatus
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.models.verification import RepairAttemptModel, RepairAttemptStatus
from packages.shared.errors import ConflictError, ErrorCategory, NotFoundError
from packages.shared.identifiers import OrganizationId, generate_id

from .schemas import ExecutionJobResponse, ExecutionLogResponse, StartExecutionRequest

router = APIRouter(prefix="/api/v1/executions", tags=["execution"])


from services.auth.dependencies import require_permission


@router.post("/plans/{plan_id}", response_model=ExecutionJobResponse)
async def start_execution(
    plan_id: UUID,
    request: StartExecutionRequest,
    organization_id: OrganizationId = Depends(require_permission("plan:approve")),
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

    job = ExecutionJobModel(
        id=generate_id(),
        organization_id=organization_id,
        repository_id=plan.repository_id,
        plan_id=plan_id,
        status=ExecutionStatus.PENDING,
        commit_sha_before=repository.commit_sha,
    )
    session.add(job)
    if linked_repair:
        linked_repair.repair_execution_id = job.id
        linked_repair.status = RepairAttemptStatus.EXECUTING

    from .events import ExecutionEventPublisher, create_execution_requested_event

    publisher = ExecutionEventPublisher(session)
    event = create_execution_requested_event(organization_id, plan.repository_id, job.id, plan_id)
    await publisher.publish(event)

    await session.commit()
    return job


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
        raise NotFoundError(code="job_not_found", message="Execution not found", category=ErrorCategory.NOT_FOUND)
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
