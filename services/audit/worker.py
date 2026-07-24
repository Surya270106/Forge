import json
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.audit import AuditLogModel

logger = structlog.get_logger(__name__)


async def handle_audit_event(payload: dict[str, Any], session: AsyncSession) -> None:
    """
    Project domain events into the AuditLogModel for fast frontend querying.
    """
    try:
        organization_id = UUID(payload["organization_id"])
        
        # Aggregate info
        aggregate_type = payload["aggregate_type"]
        aggregate_id = UUID(payload["aggregate_id"])
        event_type = payload["event_type"]
        
        # We need to extract actor_id and repository_id if available.
        # This requires looking into the specific payload structure or metadata.
        # For simplicity, we assume some common payload keys if present.
        event_payload = payload.get("payload", {})
        if isinstance(event_payload, str):
            try:
                event_payload = json.loads(event_payload)
            except json.JSONDecodeError:
                pass
                
        repository_id = None
        if "repository_id" in event_payload:
            repository_id = UUID(event_payload["repository_id"])
        elif "repository_id" in payload:
            repository_id = UUID(payload["repository_id"])

        actor_id = None
        actor_type = "system"
        if "actor_id" in event_payload:
            actor_id = UUID(event_payload["actor_id"])
            actor_type = "user"
            
        # Parse the occurred_at timestamp
        occurred_at_str = payload.get("occurred_at")
        if occurred_at_str:
            timestamp = datetime.fromisoformat(occurred_at_str)
        else:
            timestamp = datetime.utcnow()

        audit_log = AuditLogModel(
            organization_id=organization_id,
            repository_id=repository_id,
            actor_id=actor_id,
            actor_type=actor_type,
            action=event_type,
            resource_type=aggregate_type,
            resource_id=aggregate_id,
            metadata_payload=event_payload,
            timestamp=timestamp,
        )

        session.add(audit_log)
        await session.commit()
        logger.debug("projected_audit_log", event_type=event_type, aggregate_id=str(aggregate_id))

    except Exception as e:
        logger.error("failed_to_project_audit_log", error=str(e), payload=payload)
