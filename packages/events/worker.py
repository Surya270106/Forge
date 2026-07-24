import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

import redis.asyncio as redis_async
import redis.exceptions
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.processed_event import ProcessedEventModel
from packages.database.tenant import set_tenant
from packages.shared.identifiers import OrganizationId

logger = structlog.get_logger(__name__)

EventHandler = Callable[[dict, AsyncSession], Awaitable[None]]


class EventWorker:
    def __init__(
        self,
        redis_client: redis_async.Redis,
        session_maker,
        consumer_group: str,
        consumer_name: str,
        streams: list[str],
        max_retries: int = 3,
        dead_letter_stream: str = "forge:events:dead-letter",
    ):
        self.redis = redis_client
        self.session_maker = session_maker
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name
        self.streams = streams
        self.handlers: dict[str, EventHandler] = {}
        self.global_handlers: list[EventHandler] = []
        self.max_retries = max_retries
        self.dead_letter_stream = dead_letter_stream
        self._running = False
        self._task = None

    def register_handler(self, event_type: str, handler: EventHandler):
        self.handlers[event_type] = handler

    def register_global_handler(self, handler: EventHandler):
        self.global_handlers.append(handler)

    async def start(self):
        # Create consumer groups
        for stream in self.streams:
            try:
                await self.redis.xgroup_create(stream, self.consumer_group, id="0", mkstream=True)
                logger.info("Created consumer group", stream=stream, group=self.consumer_group)
            except redis.exceptions.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Event worker started", consumer=self.consumer_name)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Event worker stopped", consumer=self.consumer_name)

    async def _run(self):
        while self._running:
            try:
                # Recover pending events first
                await self._recover_pending()

                # Read new events
                streams = {stream: ">" for stream in self.streams}
                results = await self.redis.xreadgroup(  # type: ignore  # pyright: ignore  # pyright: ignore
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams=streams,  # pyright: ignore
                    count=10,
                    block=2000,
                )

                if not results:
                    continue

                for stream, messages in results:
                    for message_id, message_data in messages:  # type: ignore[reportGeneralTypeIssues]
                        await self._process_message(stream.decode("utf-8"), message_id.decode("utf-8"), message_data)  # type: ignore

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in event worker loop", error=str(e))
                await asyncio.sleep(1)

    async def _recover_pending(self):
        for stream in self.streams:
            # Find messages pending for more than 10 seconds
            pending = await self.redis.xautoclaim(stream, self.consumer_group, self.consumer_name, 10000, "0", count=10)

            # xautoclaim returns (next_start_id, messages)
            messages = pending[1]
            if not messages:
                continue

            for message_id, message_data in messages:  # type: ignore[reportGeneralTypeIssues]
                if message_data is None:
                    # Message was deleted
                    continue

                message_id_str = message_id.decode("utf-8")
                logger.info("Recovered pending message", stream=stream, message_id=message_id_str)

                # Check delivery count via XPENDING
                pending_info = await self.redis.xpending_range(stream, self.consumer_group, message_id_str, message_id_str, 1)

                delivery_count = 1
                if pending_info:
                    delivery_count = pending_info[0]["times_delivered"]

                if int(delivery_count) > self.max_retries:
                    await self._dead_letter(stream, message_id_str, message_data, "Max retries exceeded")
                    await self.redis.xack(stream, self.consumer_group, message_id_str)
                    continue

                await self._process_message(stream, message_id_str, message_data)

    async def _dead_letter(self, original_stream: str, message_id: str, message_data: dict, reason: str):
        decoded_data = {k.decode("utf-8"): v.decode("utf-8") for k, v in message_data.items()}

        dlq_entry = {
            "original_stream": original_stream,
            "original_message_id": message_id,
            "reason": reason,
            "dead_lettered_at": datetime.now(UTC).isoformat(),
            **decoded_data,
        }
        await self.redis.xadd(self.dead_letter_stream, dlq_entry)
        logger.error("Message dead lettered", message_id=message_id, reason=reason)

    async def _process_message(self, stream: str, message_id: str, message_data: dict):
        # Decode message
        data = {k.decode("utf-8"): v.decode("utf-8") for k, v in message_data.items()}

        event_type = data.get("event_type")
        event_id = data.get("event_id")
        org_id_str = data.get("organization_id")

        if not event_type or not event_id or not org_id_str:
            logger.error("Malformed event received", message_id=message_id, data=data)
            await self._dead_letter(stream, message_id, message_data, "Malformed event")
            await self.redis.xack(stream, self.consumer_group, message_id)
            return

        handler = self.handlers.get(event_type)
        if not handler and not self.global_handlers:
            logger.debug("No handler for event", event_type=event_type)
            await self.redis.xack(stream, self.consumer_group, message_id)
            return

        try:
            async with self.session_maker() as session:
                org_id = OrganizationId(UUID(org_id_str))
                set_tenant(org_id)

                # Check idempotency
                stmt = select(ProcessedEventModel).where(
                    ProcessedEventModel.organization_id == org_id_str,
                    ProcessedEventModel.consumer_name == self.consumer_name,
                    ProcessedEventModel.event_id == event_id,
                )
                result = await session.execute(stmt)
                if result.scalar_one_or_none():
                    logger.info("Event already processed, acknowledging", event_id=event_id)
                    await self.redis.xack(stream, self.consumer_group, message_id)
                    return

                # Deserialization of payload
                if "payload" in data and isinstance(data["payload"], str):
                    data["payload"] = json.loads(data["payload"])

                for g_handler in self.global_handlers:
                    try:
                        await g_handler(data, session)
                    except Exception as ge:
                        logger.error("Global handler failed", event_type=event_type, error=str(ge))

                if handler:
                    await handler(data, session)

                # Mark processed for idempotency
                processed = ProcessedEventModel(
                    organization_id=org_id_str,
                    consumer_name=self.consumer_name,
                    event_id=event_id,
                    processed_at=datetime.now(UTC),
                    result="success",
                )
                session.add(processed)

                await session.commit()

            await self.redis.xack(stream, self.consumer_group, message_id)
            logger.info("Successfully processed event", event_type=event_type, event_id=event_id)

        except Exception as e:
            logger.error("Failed to process event", event_type=event_type, event_id=event_id, error=str(e))
            # DO NOT XACK here. Let the recovery loop handle it and eventually dead letter.
