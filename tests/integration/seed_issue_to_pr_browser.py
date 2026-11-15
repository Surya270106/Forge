"""Create a short-lived browser session for an existing disposable Issue-to-PR fixture."""

import asyncio
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.auth import SessionModel
from packages.database.models.issue_workflow import IssueWorkflowModel
from packages.database.tenant import set_system_context
from services.auth.jwt import create_access_token


async def main() -> None:
    assert os.environ.get("FORGE_ISSUE_TEST_CONFIRM_DISPOSABLE") == "1"
    set_system_context()
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as db:
        workflow = (await db.execute(select(IssueWorkflowModel).order_by(
            IssueWorkflowModel.created_at.desc()).limit(1))).scalar_one()
        session_id = uuid4()
        secret = secrets.token_urlsafe(24)
        db.add(SessionModel(id=session_id, user_id=workflow.created_by, session_token=secret,
                            expires_at=(datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None)))
        await db.commit()
        token = create_access_token({"sub": str(workflow.created_by), "session_id": str(session_id),
                                     "session_token": secret})
        Path(os.environ["FORGE_ISSUE_BROWSER_FIXTURE_PATH"]).write_text(json.dumps({
            "organization_id": str(workflow.organization_id), "repository_id": str(workflow.repository_id),
            "plan_id": str(workflow.plan_id), "issue_number": workflow.issue_number, "token": token,
        }))
    await engine.dispose()


asyncio.run(main())
