from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.audit.worker import handle_audit_event


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_payload", ["not-json", "[]", "null"])
async def test_audit_projection_normalizes_non_object_payload(raw_payload: str) -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    event = {
        "organization_id": str(uuid4()),
        "aggregate_type": "repository",
        "aggregate_id": str(uuid4()),
        "event_type": "repository.tested",
        "payload": raw_payload,
    }

    await handle_audit_event(event, session)

    audit_log = session.add.call_args.args[0]
    assert audit_log.metadata_payload == {}
    session.commit.assert_not_awaited()
