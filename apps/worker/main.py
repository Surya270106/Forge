import asyncio
import os
import signal
from uuid import UUID

import redis.asyncio as redis
import structlog

from packages.database.engine import get_engine, get_session_factory
from packages.database.models.execution import ExecutionJobModel
from packages.database.models.planning import TaskNodeModel
from packages.database.models.repository import RepositoryModel
from sqlalchemy import select
from packages.events.worker import EventWorker
from packages.shared.config import get_settings
from services.execution.sandbox import DockerSandbox
from services.execution.worker import ExecutionWorker
from services.execution.runtime import select_execution_image
from services.repository_import.worker import ImportWorker

logger = structlog.get_logger(__name__)


async def run_worker():
    settings = get_settings()

    redis_client = redis.from_url(settings.redis_url)
    engine = get_engine(settings.database_url)
    session_maker = get_session_factory(engine)

    import_worker = ImportWorker(settings.database_url)

    event_worker = EventWorker(
        redis_client=redis_client,
        session_maker=session_maker,
        consumer_group="forge_worker_group",
        consumer_name=os.getenv("HOSTNAME", "worker-1"),
        streams=["forge:events:execution", "forge:events:repository", "forge:events:verification", "forge:events:repair", "forge:events:patch"],
    )

    async def handle_import(event_data: dict, session):
        import json
        payload_str = event_data.get("payload", "{}")
        payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
        job_id_str = payload.get("job_id")
        if job_id_str:
            job_id = UUID(job_id_str)
            logger.info("Starting import job", job_id=str(job_id))
            await import_worker.process_job(job_id)

    async def handle_execution(event_data: dict, session):
        import json
        payload_str = event_data.get("payload", "{}")
        payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
        job_id_str = payload.get("job_id") or event_data.get("aggregate_id")
        if job_id_str:
            job_id = UUID(job_id_str)
            logger.info("Starting execution job", job_id=str(job_id))
            job = await session.get(ExecutionJobModel, job_id)
            if not job or str(job.organization_id) != event_data.get("organization_id"):
                raise ValueError("Execution job not found for event organization")
            workspace = os.path.join(settings.workspace_root, str(job.organization_id), str(job.repository_id))
            repo = await session.get(RepositoryModel, job.repository_id)
            if not repo or repo.organization_id != job.organization_id:
                raise ValueError("Repository unavailable for execution")
            commands = (await session.execute(
                select(TaskNodeModel.parameters).where(
                    TaskNodeModel.plan_id == job.plan_id,
                    TaskNodeModel.organization_id == job.organization_id,
                    TaskNodeModel.action_type == "command",
                )
            )).scalars().all()
            image = select_execution_image(
                repo.primary_language,
                [params.get("command", "") for params in commands],
                settings.sandbox_images,
            )
            sandbox = DockerSandbox(workspace_root=workspace, image=image)
            try:
                worker = ExecutionWorker(session, sandbox)
                await worker.execute_job(job_id)
            finally:
                await sandbox.cleanup()

    async def handle_indexing(event_data: dict, session):
        import json

        from services.repository_memory.service import IndexingCoordinator
        payload_str = event_data.get("payload", "{}")
        payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
        job_id_str = payload.get("job_id")
        if job_id_str:
            job_id = UUID(job_id_str)
            logger.info("Starting indexing job", job_id=str(job_id))
            coordinator = IndexingCoordinator(session)
            await coordinator.execute_job(job_id)

    async def handle_verification(event_data: dict, session):
        import json

        from services.verification.service import VerificationDispatcher
        payload_str = event_data.get("payload", "{}")
        payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
        job_id_str = payload.get("verification_job_id") or payload.get("job_id")
        org_id_str = payload.get("organization_id")
        if job_id_str and org_id_str:
            job_id = UUID(job_id_str)
            org_id = UUID(org_id_str)
            logger.info("Starting verification job", job_id=str(job_id))
            dispatcher = VerificationDispatcher(session, org_id, settings)
            await dispatcher.run_verification(job_id)

    # Register handlers for available events
    event_worker.register_handler("repository.import_started", handle_import)
    event_worker.register_handler("repository.memory.indexing_requested", handle_indexing)
    event_worker.register_handler("execution.requested", handle_execution)
    event_worker.register_handler("verification.requested", handle_verification)

    from services.verification.repair_worker import handle_repair_attempted
    event_worker.register_handler("repair.attempted", handle_repair_attempted)
    from services.verification.repair_worker import handle_repair_plan_requested
    event_worker.register_handler("repair.plan_requested", handle_repair_plan_requested)

    async def handle_patch_publish(event_data: dict, session):
        from services.patch.publisher import PatchPublisher
        payload = event_data.get("payload", {})
        await PatchPublisher(session, UUID(event_data["organization_id"]), settings).publish(
            UUID(payload["patch_id"]), UUID(payload["requested_by"])
        )

    event_worker.register_handler("patch.publish_requested", handle_patch_publish)

    from services.audit.worker import handle_audit_event
    event_worker.register_global_handler(handle_audit_event)

    from packages.events.outbox import OutboxRelay

    relay = OutboxRelay(session_maker, redis_client)
    await relay.start()

    await event_worker.start()

    async def sweep_stale_jobs():
        from sqlalchemy import select

        from packages.database.models.auth import OrganizationModel
        from packages.database.tenant import set_system_context, set_tenant
        from services.worker_recovery import fail_stale_jobs

        while True:
            try:
                set_system_context()
                async with session_maker() as recovery_session:
                    organization_ids = (await recovery_session.execute(select(OrganizationModel.id))).scalars().all()
                for organization_id in organization_ids:
                    set_tenant(organization_id)
                    async with session_maker() as recovery_session:
                        counts = await fail_stale_jobs(
                            recovery_session, organization_id,
                            execution_timeout_seconds=settings.execution_timeout_seconds,
                        )
                        if any(counts.values()):
                            logger.warning("stale_jobs_failed", organization_id=str(organization_id), **counts)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error("stale_job_sweep_failed", error_type=type(error).__name__)
            await asyncio.sleep(60)

    recovery_task = asyncio.create_task(sweep_stale_jobs())

    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Received stop signal")
        stop_event.set()

    import sys
    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            asyncio.get_running_loop().add_signal_handler(sig, _signal_handler)

    await stop_event.wait()
    recovery_task.cancel()
    try:
        await recovery_task
    except asyncio.CancelledError:
        pass
    await relay.stop()
    await event_worker.stop()
    await redis_client.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_worker())
