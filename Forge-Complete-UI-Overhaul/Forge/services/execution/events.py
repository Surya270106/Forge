from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.outbox_event import OutboxEventModel
from packages.shared.events import EventEnvelope, EventPublisher


class ExecutionEventPublisher(EventPublisher):
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


def create_execution_started_event(org_id: UUID, repo_id: UUID, exec_id: UUID, plan_id: UUID) -> EventEnvelope:
    return EventEnvelope(
        event_type="execution.started",
        aggregate_type="execution",
        aggregate_id=str(exec_id),
        organization_id=str(org_id),
        payload={
            "organization_id": str(org_id),
            "repository_id": str(repo_id),
            "plan_id": str(plan_id),
        },
    )


def create_execution_completed_event(org_id: UUID, repo_id: UUID, exec_id: UUID) -> EventEnvelope:
    return EventEnvelope(
        event_type="execution.completed",
        aggregate_type="execution",
        aggregate_id=str(exec_id),
        organization_id=str(org_id),
        payload={"organization_id": str(org_id), "repository_id": str(repo_id)},
    )


def create_execution_failed_event(org_id: UUID, repo_id: UUID, exec_id: UUID, error: str) -> EventEnvelope:
    return EventEnvelope(
        event_type="execution.failed",
        aggregate_type="execution",
        aggregate_id=str(exec_id),
        organization_id=str(org_id),
        payload={"organization_id": str(org_id), "repository_id": str(repo_id), "error": error},
    )


def create_mutation_applied_event(org_id: UUID, repo_id: UUID, exec_id: UUID, file_path: str, diff_hunk: str) -> EventEnvelope:
    return EventEnvelope(
        event_type="mutation.applied",
        aggregate_type="execution",
        aggregate_id=str(exec_id),
        organization_id=str(org_id),
        payload={
            "organization_id": str(org_id),
            "repository_id": str(repo_id),
            "file_path": file_path,
            "diff_hunk": diff_hunk,
        },
    )
