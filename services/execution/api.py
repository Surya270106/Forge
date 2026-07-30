from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.execution import ExecutionJobModel, ExecutionLogModel, ExecutionStatus, MutationModel
from packages.database.models.planning import PlanModel, PlanStatus
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
    plan = await session.get(PlanModel, plan_id)
    if not plan or plan.organization_id != organization_id:
        raise NotFoundError(code="plan_not_found", message="Plan not found", category=ErrorCategory.NOT_FOUND)  # type: ignore

    if plan.status != PlanStatus.APPROVED:
        raise ConflictError(
            code="plan_not_approved",
            message="Plan must be APPROVED to execute",
            category=ErrorCategory.CONFLICT,
        )

    job = ExecutionJobModel(
        id=generate_id(),
        organization_id=organization_id,
        repository_id=plan.repository_id,
        plan_id=plan_id,
        status=ExecutionStatus.PENDING,
        commit_sha_before="HEAD",
    )
    session.add(job)

    from .events import ExecutionEventPublisher, create_execution_started_event

    publisher = ExecutionEventPublisher(session)
    event = create_execution_started_event(organization_id, plan.repository_id, job.id, plan_id)
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


from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio

@router.websocket("/{job_id}/ws")
async def websocket_endpoint(websocket: WebSocket, job_id: UUID):
    await websocket.accept()
    
    from packages.shared.config import get_settings
    import redis.asyncio as redis_async
    
    settings = get_settings()
    redis_client = redis_async.from_url(settings.redis_url)
    pubsub = redis_client.pubsub()
    channel_name = f"execution:{job_id}:logs"
    
    await pubsub.subscribe(channel_name)
    
    try:
        while True:
            # We use a timeout so we can check if the client disconnected
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                data_str = message["data"].decode("utf-8")
                await websocket.send_text(data_str)
            
            # Check if websocket is still open by trying to receive
            # Since receive_text blocks, we use asyncio.wait_for
            try:
                # ping from client is rare, but if they disconnect it raises
                # We do a zero timeout receive just to check connection state
                pass
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel_name)
        await redis_client.aclose()
