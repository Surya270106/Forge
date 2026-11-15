import asyncio
import json
import os
import secrets
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.auth import OrganizationModel, RoleBindingModel, SessionModel, UserModel
from packages.database.models.planning import PlanModel, PlanStatus, TaskNodeModel
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.tenant import set_system_context
from services.auth.jwt import create_access_token


async def main():
    root = Path(os.environ["WORKSPACE_ROOT"])
    org, user, repo, plan, session_id, node = (uuid4() for _ in range(6))
    source = root / str(org) / str(repo)
    source.mkdir(parents=True)
    source.chmod(0o755)
    (source / "README.md").write_text("cancellation fixture\n")
    for args in (("init", "-b", "main"), ("add", "README.md"),
                 ("-c", "user.name=Forge Test", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture")):
        subprocess.run(["git", "-C", str(source), *args], check=True, capture_output=True)
    revision = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True).stdout.strip()
    session_token = secrets.token_urlsafe(24)
    set_system_context()
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as db:
        db.add(OrganizationModel(id=org, name=f"Browser cancellation {org}"))
        db.add(UserModel(id=user, email=f"browser-{user}@example.invalid", name="Browser Fixture"))
        await db.flush()
        db.add(RoleBindingModel(id=uuid4(), organization_id=org, user_id=user, role="OWNER"))
        db.add(SessionModel(id=session_id, user_id=user, session_token=session_token,
                            expires_at=(datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None)))
        db.add(RepositoryModel(id=repo, organization_id=org, owner="fixture", name="cancel",
                               full_name="fixture/cancel", clone_url="https://example.invalid/cancel.git",
                               status=RepositoryStatus.READY, commit_sha=revision, primary_language="javascript"))
        await db.flush()
        db.add(PlanModel(id=plan, organization_id=org, repository_id=repo, status=PlanStatus.APPROVED,
                         intent="Cancel a long-running local command", context_snapshot={}))
        await db.flush()
        db.add(TaskNodeModel(id=node, organization_id=org, plan_id=plan,
                             action_type="command", target="workspace", parameters={"command": "sleep 60"}))
        await db.commit()
    token = create_access_token({"sub": str(user), "session_id": str(session_id),
                                 "session_token": session_token})
    Path(os.environ["FORGE_CANCEL_FIXTURE_PATH"]).write_text(json.dumps({
        "organization_id": str(org), "user_id": str(user), "plan_id": str(plan), "token": token,
    }))
    await engine.dispose()


asyncio.run(main())
