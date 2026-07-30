from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from .identifiers import CorrelationId, EventId, generate_id


class EventEnvelope(BaseModel):
    event_id: EventId = Field(default_factory=lambda: EventId(generate_id()))
    event_type: str
    organization_id: str
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int = 1
    correlation_id: CorrelationId | None = None
    causation_id: EventId | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = "1.0"
    payload: dict[str, Any]

    model_config = {"frozen": True}


class EventPublisher:
    """Abstract event publisher interface."""

    async def publish(self, event: EventEnvelope) -> None:
        raise NotImplementedError

    async def publish_batch(self, events: list[EventEnvelope]) -> None:
        for event in events:
            await self.publish(event)
