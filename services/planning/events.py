from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.outbox_event import OutboxEventModel
from packages.shared.events import EventEnvelope, EventPublisher


class PlanningEventPublisher(EventPublisher):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def publish(self, event: EventEnvelope) -> None:
        outbox_event = OutboxEventModel(
            id=event.event_id,
            event_type=event.event_type,
            organization_id=event.organization_id,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            aggregate_version=event.aggregate_version,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            schema_version=event.schema_version,
            payload=event.payload,
            occurred_at=event.occurred_at,
        )
        self.session.add(outbox_event)
        await self.session.flush()


def create_plan_created_event(org_id: UUID, repo_id: UUID, plan_id: UUID) -> EventEnvelope:
    return EventEnvelope(
        event_type="plan.created",
        aggregate_type="plan",
        aggregate_id=str(plan_id),
        organization_id=str(org_id),
        payload={"organization_id": str(org_id), "repository_id": str(repo_id)},
    )


def create_plan_approved_event(org_id: UUID, repo_id: UUID, plan_id: UUID) -> EventEnvelope:
    return EventEnvelope(
        event_type="plan.approved",
        aggregate_type="plan",
        aggregate_id=str(plan_id),
        organization_id=str(org_id),
        payload={"organization_id": str(org_id), "repository_id": str(repo_id)},
    )


def create_plan_rejected_event(org_id: UUID, repo_id: UUID, plan_id: UUID, reason: str) -> EventEnvelope:
    return EventEnvelope(
        event_type="plan.rejected",
        aggregate_type="plan",
        aggregate_id=str(plan_id),
        organization_id=str(org_id),
        payload={"organization_id": str(org_id), "repository_id": str(repo_id), "reason": reason},
    )
