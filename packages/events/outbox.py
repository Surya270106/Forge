import asyncio
import json
from datetime import UTC, datetime

import redis.asyncio as redis_async
import structlog
from sqlalchemy import select, update

from packages.database.models.outbox_event import OutboxEventModel
from packages.database.tenant import set_system_context

logger = structlog.get_logger(__name__)


class OutboxRelay:
    def __init__(
        self,
        session_maker,
        redis_client: redis_async.Redis,
        batch_size: int = 50,
        poll_interval: float = 1.0,
    ):
        self.session_maker = session_maker
        self.redis = redis_client
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self._running = False
        self._task = None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Outbox relay started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Outbox relay stopped")

    async def _run(self):
        while self._running:
            try:
                await self._process_batch()
            except Exception as e:
                logger.error("Error in outbox relay", error=str(e))
            await asyncio.sleep(self.poll_interval)

    async def _process_batch(self):
        set_system_context()
        async with self.session_maker() as session:
            # Find unpublished events
            stmt = select(OutboxEventModel).where(not OutboxEventModel.published).order_by(OutboxEventModel.occurred_at).limit(self.batch_size)

            result = await session.execute(stmt)
            events = result.scalars().all()

            if not events:
                return

            published_ids = []
            for event in events:
                try:
                    await self._publish_to_redis(event)
                    published_ids.append(event.id)
                except Exception as e:
                    logger.error("Failed to publish event to redis", event_id=event.id, error=str(e))

            if published_ids:
                # Mark as published
                update_stmt = (
                    update(OutboxEventModel).where(OutboxEventModel.id.in_(published_ids)).values(published=True, published_at=datetime.now(UTC))
                )
                await session.execute(update_stmt)
                await session.commit()
                logger.info("Published outbox events", count=len(published_ids))

    async def _publish_to_redis(self, event: OutboxEventModel):
        stream_name = f"forge:events:{event.aggregate_type}"
        payload = {
            "event_id": str(event.id),
            "event_type": event.event_type,
            "organization_id": str(event.organization_id),
            "aggregate_type": event.aggregate_type,
            "aggregate_id": str(event.aggregate_id),
            "aggregate_version": str(event.aggregate_version),
            "correlation_id": str(event.correlation_id) if event.correlation_id else "",
            "causation_id": str(event.causation_id) if event.causation_id else "",
            "schema_version": event.schema_version,
            "occurred_at": event.occurred_at.isoformat(),
            "payload": json.dumps(event.payload),
        }
        await self.redis.xadd(stream_name, payload)  # pyright: ignore
