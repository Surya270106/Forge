import asyncio
import os
import signal
from uuid import UUID

import redis.asyncio as redis
import structlog

from packages.database.engine import get_engine, get_session_factory
from packages.events.worker import EventWorker
from packages.shared.config import get_settings
from services.execution.sandbox import DockerSandbox
from services.execution.worker import ExecutionWorker
from services.repository_import.worker import ImportWorker

logger = structlog.get_logger(__name__)


async def run_worker():
    settings = get_settings()

    redis_client = redis.from_url(settings.redis_url)
    engine = get_engine(settings.database_url)
    session_maker = get_session_factory(engine)

    import_worker = ImportWorker(settings.database_url)

    # In Docker context, we might use LocalProcessSandbox or DockerSandbox
    # but since this runs inside Docker and needs to execute code,
    # if it's DockerSandbox, it talks to the host Docker daemon.
    sandbox = DockerSandbox(workspace_root=settings.workspace_root)

    event_worker = EventWorker(
        redis_client=redis_client,
        session_maker=session_maker,
        consumer_group="forge_worker_group",
        consumer_name=os.getenv("HOSTNAME", "worker-1"),
        streams=["forge:events:execution", "forge:events:repository", "forge:events:verification"],
    )

    async def handle_import(event_data: dict, session):
        job_id_str = event_data.get("aggregate_id")
        if job_id_str:
            job_id = UUID(job_id_str)
            logger.info("Starting import job", job_id=str(job_id))
            await import_worker.process_job(job_id)

    async def handle_execution(event_data: dict, session):
        job_id_str = event_data.get("aggregate_id")
        if job_id_str:
            job_id = UUID(job_id_str)
            logger.info("Starting execution job", job_id=str(job_id))
            worker = ExecutionWorker(session, sandbox)
            await worker.execute_job(job_id)

    # Register handlers for available events
    event_worker.register_handler("repository.import_started", handle_import)
    event_worker.register_handler("execution.started", handle_execution)
    
    from services.verification.repair_worker import handle_repair_attempted
    event_worker.register_handler("verification.repair_attempted", handle_repair_attempted)

    from services.audit.worker import handle_audit_event
    event_worker.register_global_handler(handle_audit_event)

    from packages.events.outbox import OutboxRelay

    relay = OutboxRelay(session_maker, redis_client)
    await relay.start()

    await event_worker.start()

    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Received stop signal")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, _signal_handler)

    await stop_event.wait()
    await relay.stop()
    await event_worker.stop()
    await redis_client.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_worker())
