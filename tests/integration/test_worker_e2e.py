"""Run the real worker and Docker sandbox against disposable local CI services."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch as mock_patch
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
import redis.asyncio as redis_async
from redis.exceptions import ResponseError
from sqlalchemy import select

from packages.database.engine import dispose_engine, get_engine, get_session_factory
from packages.database.models.atlas import AtlasJobModel, AtlasNodeModel, AtlasSnapshotModel
from packages.database.models.auth import OrganizationModel, RoleBindingModel, UserModel
from packages.database.models.execution import ExecutionJobModel, ExecutionStatus
from packages.database.models.issue_workflow import IssueWorkflowModel
from packages.database.models.outbox_event import OutboxEventModel
from packages.database.models.patch import PatchStatus
from packages.database.models.planning import PlanModel, PlanStatus, TaskEdgeModel, TaskNodeModel
from packages.database.models.processed_event import ProcessedEventModel
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.models.run_capsule import RunCapsuleModel
from packages.database.models.verification import VerificationJobModel, VerificationResultModel, VerificationStatus
from packages.database.models.verification_intelligence import VerificationPlanModel
from packages.database.tenant import set_system_context
from services.auth.dependencies import _verify_and_set_tenant
from services.execution.api import execution_timeline, get_execution_logs, get_execution_mutations, get_execution_status, start_execution
from services.execution.schemas import StartExecutionRequest
from services.execution.workspace import execution_workspace_path
from services.issue_to_pr.api import get_workflow
from services.patch.publisher import PatchPublisher
from services.patch.service import PatchService
from services.verification.api import get_latest_verification


def _selective_fixture_repository(workspace: Path) -> str:
    workspace.mkdir(parents=True)
    (workspace / "tests").mkdir()
    (workspace / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n")
    (workspace / "tests" / "test_b.py").write_text("def test_b():\n    assert True\n")
    (workspace / "forge.yaml").write_text(json.dumps({
        "version": 1, "languages": ["python"], "verification": {"test": [
            {"identifier": "focused", "display_name": "Focused", "category": "test",
             "command": ["pytest", "tests/test_a.py"]},
            {"identifier": "unrelated", "display_name": "Unrelated", "category": "test",
             "command": ["pytest", "tests/test_b.py"]},
        ]},
    }))
    _git(workspace, "init", "-b", "main")
    _git(workspace, "add", "tests/test_a.py", "tests/test_b.py", "forge.yaml")
    _git(workspace, "-c", "user.name=Forge CI", "-c", "user.email=forge-ci@example.invalid", "commit", "-m", "fixture")
    return _git(workspace, "rev-parse", "HEAD")


def _git(workspace: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={workspace.as_posix()}", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode:
        raise AssertionError(f"Fixture Git command failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _fixture_repository(workspace: Path, language: str = "javascript") -> str:
    workspace.mkdir(parents=True)
    workspace.chmod(0o755)
    (workspace / "result.txt").write_text("original\n")
    (workspace / "forge.yaml").write_text(
        json.dumps(
            {
                "version": 1,
                "languages": [language],
                "verification": {
                    "test": [
                        {
                            "identifier": "fixture-result",
                            "display_name": "Fixture result",
                            "category": "test",
                            "command": (["python3", "-c", "import pathlib,sys; sys.exit(0 if pathlib.Path('result.txt').read_text().startswith('expected') else 1)"]
                                        if language == "python" else ["sh", "-c", "grep -q '^expected' result.txt"]),
                        }
                    ]
                },
            }
        )
    )
    _git(workspace, "init", "-b", "main")
    _git(workspace, "add", "result.txt", "forge.yaml")
    _git(workspace, "-c", "user.name=Forge CI", "-c", "user.email=forge-ci@example.invalid", "commit", "-m", "fixture")
    return _git(workspace, "rev-parse", "HEAD")


def _require_isolated_services() -> tuple[str, str]:
    if os.getenv("FORGE_REQUIRE_WORKER_E2E") != "1":
        pytest.skip("Set FORGE_REQUIRE_WORKER_E2E=1 with disposable local PostgreSQL, Redis, and Docker")
    database_url = os.getenv("DATABASE_URL", "")
    redis_url = os.getenv("REDIS_URL", "")
    database = urlsplit(database_url)
    cache = urlsplit(redis_url)
    if (
        database.hostname not in {"localhost", "127.0.0.1"}
        or not database.path.lstrip("/").startswith("forge_e2e_")
        or cache.hostname not in {"localhost", "127.0.0.1"}
        or database.username != "postgres"
    ):
        pytest.fail("Worker E2E requires local disposable PostgreSQL and Redis, and a forge_e2e_* database")
    return database_url, redis_url


async def _wait_for_worker(redis_client: redis_async.Redis, process: subprocess.Popen[str], log_path: Path, consumer_name: str) -> None:
    async with asyncio.timeout(30):
        while True:
            if process.poll() is not None:
                pytest.fail(f"Worker exited before queue registration:\n{log_path.read_text()[-4000:]}")
            try:
                consumers = await redis_client.xinfo_consumers("forge:events:execution", "forge_worker_group")
                if any(consumer["name"] == consumer_name.encode() for consumer in consumers):
                    return
            except ResponseError:
                pass
            await asyncio.sleep(0.1)


def _cleanup_owned_sandboxes(workspace_root: Path) -> None:
    """Remove only test sandboxes whose workspace mount is inside this test's root."""
    result = subprocess.run(
        ["docker", "ps", "-aq", "--filter", "name=forge-sandbox-"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    for container_id in result.stdout.splitlines():
        inspected = subprocess.run(
            ["docker", "inspect", "--format", "{{json .Mounts}}", container_id],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if inspected.returncode:
            if "no such object" in inspected.stderr.lower() or "no such container" in inspected.stderr.lower():
                continue  # Docker --rm removed it between ps and inspect.
            raise RuntimeError(f"Cannot inspect test sandbox {container_id}: {inspected.stderr.strip()}")
        mounts = json.loads(inspected.stdout)
        if any(
            mount.get("Destination") == "/workspace" and Path(mount.get("Source", "")).resolve().is_relative_to(workspace_root.resolve())
            for mount in mounts
        ):
            removed = subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, text=True, timeout=10)
            if removed.returncode and "no such container" not in removed.stderr.lower():
                raise RuntimeError(f"Cannot remove test sandbox {container_id}: {removed.stderr.strip()}")


@pytest.mark.asyncio
async def test_worker_queue_sandbox_verification_and_authorized_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_url, redis_url = _require_isolated_services()
    subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], check=True, capture_output=True, timeout=10)
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    workspace_root.chmod(0o755)
    monkeypatch.setenv("WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setenv("SANDBOX_IMAGES", '["node:20-slim", "python:3.12-slim"]')
    git_config = tmp_path / "fixture-gitconfig"
    git_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(git_config))
    engine = get_engine(database_url)
    session_maker = get_session_factory(engine)
    redis_client = redis_async.from_url(redis_url)
    worker_log = tmp_path / "worker.log"
    process: subprocess.Popen[str] | None = None
    consumer_name = f"forge-e2e-{uuid4().hex}"

    try:
        async with redis_client:
            with worker_log.open("w") as output:
                process = subprocess.Popen(
                    [sys.executable, "-m", "apps.worker.main"],
                    cwd=Path(__file__).resolve().parents[2],
                    env={**os.environ, "HOSTNAME": consumer_name, "PYTHONUNBUFFERED": "1"},
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                await _wait_for_worker(redis_client, process, worker_log, consumer_name)

                for content, expected_verification, language, command in (
                    ("expected\n", VerificationStatus.PASSED, "javascript", None),
                    ("wrong\n", VerificationStatus.FAILED, "javascript", None),
                    ("expected\n", VerificationStatus.PASSED, "python", None),
                    ("wrong\n", VerificationStatus.FAILED, "python", None),
                    ("expected\n", None, "javascript", "node -e 'process.exit(2)'"),
                ):
                    organization_id, user_id, repository_id, plan_id = (uuid4() for _ in range(4))
                    workspace = workspace_root / str(organization_id) / str(repository_id)
                    workspace.parent.mkdir(mode=0o755)
                    with git_config.open("a") as config:
                        config.write(f"[safe]\n\tdirectory = {workspace.as_posix()}\n")
                    base_sha = _fixture_repository(workspace, language)
                    edit_id, command_id = uuid4(), uuid4()
                    set_system_context()
                    async with session_maker() as session:
                        session.add_all(
                            [
                                OrganizationModel(id=organization_id, name=f"forge-e2e-{organization_id}"),
                                UserModel(id=user_id, email=f"{user_id}@example.invalid", name="Forge CI"),
                            ]
                        )
                        await session.flush()
                        session.add_all(
                            [
                                RoleBindingModel(id=uuid4(), organization_id=organization_id, user_id=user_id, role="OWNER"),
                                RepositoryModel(
                                    id=repository_id,
                                    organization_id=organization_id,
                                    owner="fixture",
                                    name=str(repository_id),
                                    full_name=f"fixture/{repository_id}",
                                    clone_url="https://example.invalid/fixture.git",
                                    status=RepositoryStatus.READY,
                                    commit_sha=base_sha,
                                    primary_language=language,
                                ),
                            ]
                        )
                        await session.flush()
                        session.add(
                            PlanModel(
                                id=plan_id,
                                organization_id=organization_id,
                                repository_id=repository_id,
                                status=PlanStatus.APPROVED,
                                intent="Test the worker",
                                context_snapshot={},
                            )
                        )
                        await session.flush()
                        session.add_all(
                            [
                                TaskNodeModel(
                                    id=edit_id,
                                    organization_id=organization_id,
                                    plan_id=plan_id,
                                    action_type="edit_file",
                                    target="result.txt",
                                    parameters={"changes": content},
                                ),
                                TaskNodeModel(
                                    id=command_id,
                                    organization_id=organization_id,
                                    plan_id=plan_id,
                                    action_type="command",
                                    target="workspace",
                                    parameters={"command": command or ("python3 -c 'import pathlib; assert pathlib.Path(\"result.txt\").is_file()'"
                                                               if language == "python" else "test -f result.txt")},
                                ),
                            ]
                        )
                        await session.flush()
                        session.add(
                            TaskEdgeModel(
                                id=uuid4(),
                                organization_id=organization_id,
                                plan_id=plan_id,
                                from_node_id=edit_id,
                                to_node_id=command_id,
                            )
                        )
                        await session.commit()

                    async with session_maker() as session:
                        authorized = await _verify_and_set_tenant(None, str(organization_id), {"id": user_id}, session, "plan:approve")
                        submitted = await start_execution(plan_id, StartExecutionRequest(), authorized, session)
                        job_id: UUID = submitted.id
                        event = (
                            await session.execute(
                                select(OutboxEventModel).where(
                                    OutboxEventModel.event_type == "execution.requested",
                                    OutboxEventModel.aggregate_id == str(job_id),
                                )
                            )
                        ).scalar_one()
                        event_id = str(event.id)

                    try:
                        async with asyncio.timeout(90):
                            while True:
                                if process.poll() is not None:
                                    pytest.fail(f"Worker exited during execution:\n{worker_log.read_text()[-4000:]}")
                                async with session_maker() as session:
                                    execution = await session.get(ExecutionJobModel, job_id)
                                    if expected_verification is None and execution and execution.status == ExecutionStatus.FAILED:
                                        processed_id = await session.scalar(select(ProcessedEventModel.id).where(
                                            ProcessedEventModel.event_id == event_id,
                                            ProcessedEventModel.consumer_name == "forge_worker_group",
                                        ))
                                        if processed_id:
                                            break
                                    verification = (
                                        await session.execute(
                                            select(VerificationJobModel).where(
                                                VerificationJobModel.execution_job_id == job_id,
                                                VerificationJobModel.organization_id == organization_id,
                                            )
                                        )
                                    ).scalar_one_or_none()
                                    if verification and verification.status in {
                                        VerificationStatus.PASSED,
                                        VerificationStatus.FAILED,
                                        VerificationStatus.BLOCKED,
                                        VerificationStatus.NOT_CONFIGURED,
                                    }:
                                        break
                                await asyncio.sleep(0.2)
                    except TimeoutError:
                        pytest.fail(f"Worker did not finish job {job_id}:\n{worker_log.read_text()[-4000:]}")

                    async with session_maker() as session:
                        authorized = await _verify_and_set_tenant(None, str(organization_id), {"id": user_id}, session, "exec:read")
                        delivered_job = await get_execution_status(job_id, authorized, session)
                        delivered_mutations = await get_execution_mutations(job_id, authorized, session)
                        delivered_logs = await get_execution_logs(job_id, authorized, session)
                        timeline = await execution_timeline(job_id, 0, 100, None, None, None, authorized, session)
                        delivered_verification = (await get_latest_verification(job_id, authorized, session)
                                                  if expected_verification is not None else None)
                        processed = (
                            await session.execute(
                                select(ProcessedEventModel).where(
                                    ProcessedEventModel.event_id == event_id,
                                    ProcessedEventModel.consumer_name == "forge_worker_group",
                                )
                            )
                        ).scalar_one_or_none()

                    assert processed is not None
                    event_types = [entry["event_type"] for entry in timeline["events"]]
                    assert [entry["sequence"] for entry in timeline["events"]] == list(range(1, len(event_types) + 1))
                    assert {"task.created", "execution.queued", "worker.claimed", "execution.started", "repository.change_detected",
                            "sandbox.created", "sandbox.command_started",
                            "sandbox.cleanup_completed"} <= set(event_types)
                    execution_workspace = execution_workspace_path(str(workspace_root), organization_id, repository_id, job_id, 1)
                    assert (workspace / "result.txt").read_text() == "original\n"
                    if expected_verification is None:
                        assert delivered_job.status == ExecutionStatus.FAILED
                        assert delivered_mutations["mutations"] == []
                        assert "execution.failed" in event_types
                        assert "sandbox.command_failed" in event_types
                        assert "repository.mutation_committed" not in event_types
                        assert delivered_job.error_message is not None
                        assert "Command failed with exit code 2" in delivered_job.error_message
                        assert (execution_workspace / "result.txt").read_text() == "expected\n"
                    else:
                        assert delivered_job.status == ExecutionStatus.COMPLETED
                        assert delivered_mutations["mutations"][0]["file_path"] == "result.txt"
                        assert delivered_mutations["mutations"][0]["diff_hunk"]
                        assert {"execution.completed", "repository.mutation_committed", "verification.started",
                                "verification.completed", "sandbox.command_completed"} <= set(event_types)
                        assert delivered_verification is not None
                        assert any("Execution completed successfully" in entry.message for entry in delivered_logs)
                        assert delivered_verification["status"] == expected_verification
                        assert delivered_verification["results"][0].status == expected_verification
                        assert (execution_workspace / "result.txt").read_text() == content
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, 5)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait, 5)
        try:
            _cleanup_owned_sandboxes(workspace_root)
        finally:
            try:
                await redis_client.aclose()
            finally:
                try:
                    await dispose_engine()
                finally:
                    if sys.platform != "win32":
                        shutil.rmtree(tmp_path)


@pytest.mark.parametrize("multi_file", [False, True], ids=["single-file", "multi-file"])
@pytest.mark.asyncio
async def test_worker_runs_selected_pytest_and_records_capsule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                               multi_file: bool) -> None:
    database_url, redis_url = _require_isolated_services()
    image = os.getenv("FORGE_WORKER_E2E_PYTEST_IMAGE")
    if not image or not image.startswith("python:"):
        pytest.skip("Set FORGE_WORKER_E2E_PYTEST_IMAGE to an approved local Python image with pytest")
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    workspace_root.chmod(0o755)
    monkeypatch.setenv("WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setenv("SANDBOX_IMAGES", json.dumps([image]))
    git_config = tmp_path / "fixture-gitconfig"
    git_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(git_config))
    org, user, repo, plan, task, atlas_job, snapshot, node, workflow_id = (uuid4() for _ in range(9))
    workspace = workspace_root / str(org) / str(repo)
    workspace.parent.mkdir(mode=0o755)
    with git_config.open("a") as config:
        config.write(f"[safe]\n\tdirectory = {workspace.as_posix()}\n")
    base_sha = _selective_fixture_repository(workspace)
    _git(workspace, "remote", "add", "origin", "https://github.com/owner/repo.git")
    engine = get_engine(database_url)
    sessions = get_session_factory(engine)
    redis_client = redis_async.from_url(redis_url)
    worker_log = tmp_path / "selected-worker.log"
    consumer_name = f"forge-selected-{uuid4().hex}"
    process: subprocess.Popen[str] | None = None
    try:
        set_system_context()
        async with sessions() as session:
            session.add_all([OrganizationModel(id=org, name=f"capsule-selected-{org}"),
                             UserModel(id=user, email=f"{user}@example.invalid", name="Forge CI")])
            await session.flush()
            session.add_all([RoleBindingModel(id=uuid4(), organization_id=org, user_id=user, role="OWNER"),
                             RepositoryModel(id=repo, organization_id=org, owner="owner", name="repo",
                                             full_name="owner/repo", clone_url="https://github.com/owner/repo.git",
                                             status=RepositoryStatus.READY, commit_sha=base_sha, primary_language="Python",
                                             github_repository_id=17)])
            await session.flush()
            session.add(PlanModel(id=plan, organization_id=org, repository_id=repo, status=PlanStatus.APPROVED,
                                  intent="Edit one test", context_snapshot={}))
            session.add(AtlasJobModel(id=atlas_job, organization_id=org, repository_id=repo,
                                      requested_by=user, idempotency_key=uuid4(), status="SUCCEEDED", attempts=1))
            await session.flush()
            session.add(IssueWorkflowModel(id=workflow_id, organization_id=org, repository_id=repo, created_by=user,
                                           idempotency_key=uuid4(), github_repository_id=17,
                                           github_issue_id=20, issue_number=3,
                                           issue_snapshot={"title": "Edit one test", "number": 3, "body": "fixture"},
                                           base_commit_sha=base_sha, plan_id=plan))
            session.add(AtlasSnapshotModel(id=snapshot, organization_id=org, repository_id=repo,
                                           job_id=atlas_job, commit_sha=base_sha, tree_sha="b" * 40,
                                           source_fingerprint="c" * 64, dirty=False, indexer_version="atlas-test",
                                           parser_versions={}, config_fingerprint="d" * 64, status="BUILDING",
                                           stats={}, warnings=[], completed_at=datetime.now(UTC)))
            await session.flush()
            session.add(AtlasNodeModel(id=node, organization_id=org, repository_id=repo,
                                       snapshot_id=snapshot, stable_key="file:tests/test_a.py",
                                       kind="test_file", name="tests/test_a.py", path="tests/test_a.py"))
            session.add(TaskNodeModel(id=task, organization_id=org, plan_id=plan, action_type="edit_file",
                                      target="tests/test_a.py", parameters={"changes": "def test_a():\n    assert 1 == 1\n"}))
            if multi_file:
                session.add(TaskNodeModel(id=uuid4(), organization_id=org, plan_id=plan, action_type="edit_file",
                                          target="tests/test_b.py", parameters={"changes": "def test_b():\n    assert 2 == 2\n"}))
            await session.flush()
            (await session.get(AtlasSnapshotModel, snapshot)).status = "PUBLISHED"
            await session.commit()

        with worker_log.open("w") as output:
            process = subprocess.Popen([sys.executable, "-m", "apps.worker.main"],
                                       cwd=Path(__file__).resolve().parents[2],
                                       env={**os.environ, "HOSTNAME": consumer_name, "PYTHONUNBUFFERED": "1"},
                                       stdout=output, stderr=subprocess.STDOUT, text=True)
            async with redis_client:
                await _wait_for_worker(redis_client, process, worker_log, consumer_name)
                async with sessions() as session:
                    authorized = await _verify_and_set_tenant(None, str(org), {"id": user}, session, "plan:approve")
                    submitted = await start_execution(plan, StartExecutionRequest(), authorized, session)
                    execution_id = submitted.id
                async with asyncio.timeout(90):
                    while True:
                        if process.poll() is not None:
                            pytest.fail(f"Selected worker exited:\n{worker_log.read_text()[-4000:]}")
                        set_system_context()
                        async with sessions() as session:
                            verification = await session.scalar(select(VerificationJobModel).where(
                                VerificationJobModel.execution_job_id == execution_id,
                                VerificationJobModel.organization_id == org))
                            if verification and verification.status not in {VerificationStatus.PENDING, VerificationStatus.RUNNING}:
                                break
                        await asyncio.sleep(0.2)
                set_system_context()
                async with sessions() as session:
                    execution = await session.get(ExecutionJobModel, execution_id)
                    workflow = await get_workflow(workflow_id, org, session)
                    selection = await session.scalar(select(VerificationPlanModel).where(
                        VerificationPlanModel.execution_job_id == execution_id))
                    results = (await session.execute(select(VerificationResultModel).where(
                        VerificationResultModel.execution_id == execution_id))).scalars().all()
                    capsules = (await session.execute(select(RunCapsuleModel).where(
                        RunCapsuleModel.execution_job_id == execution_id).order_by(RunCapsuleModel.created_at))).scalars().all()
                assert execution.status == ExecutionStatus.COMPLETED
                assert workflow["execution_id"] == str(execution_id)
                assert workflow["verification_status"] == "PASSED"
                assert verification.status == VerificationStatus.PASSED, worker_log.read_text()[-4000:]
                expected_results = [("focused", "PASSED"), ("unrelated", "PASSED" if multi_file else "SKIPPED")]
                assert selection is not None
                assert selection.decision["selected_verifiers"] == (["focused", "unrelated"] if multi_file else ["focused"])
                assert sorted((result.verifier, result.status.value) for result in results) == expected_results
                assert capsules[-1].state == "FINAL"
                assert capsules[-1].manifest["selection_plan_id"] == str(selection.id)
                assert capsules[-1].manifest["patch_digest"] == selection.patch_digest
                assert any(item["status"] == "PASSED" for item in capsules[-1].manifest["verification_results"])
            process.terminate()
            await asyncio.to_thread(process.wait, 5)
            set_system_context()
            async with sessions() as session:
                patch = await PatchService(session, org).generate_patch(execution_id)
                review = await PatchService(session, org).review_patch(patch.id)
                assert review["review_digest"] == patch.review_digest
                assert len(review["changes"]) == (2 if multi_file else 1)
                await PatchService(session, org).accept_patch(patch.id, review["review_digest"], user)
                queued = await PatchService(session, org).request_publish(patch.id, user)
                assert queued.publish_status == "QUEUED"
                workflow = await get_workflow(workflow_id, org, session)
                assert workflow["state"] == "PUBLISHING"
                owner = await session.get(UserModel, user)
                owner.github_token = "fixture-encrypted-token"
                await session.commit()

            remote_commit: dict[str, str] = {}
            posted: list[dict] = []

            def github(request: httpx.Request) -> httpx.Response:
                path = request.url.path
                if path == "/repos/owner/repo":
                    return httpx.Response(200, json={"id": 17, "full_name": "owner/repo", "permissions": {"push": True},
                                                     "archived": False, "default_branch": "main"})
                if path == "/repos/owner/repo/issues/3":
                    return httpx.Response(200, json={"id": 20, "state": "open"})
                if b"/git/ref/heads/forge%2F" in request.url.raw_path:
                    return httpx.Response(404)
                if path.endswith("/git/ref/heads/main"):
                    return httpx.Response(200, json={"object": {"sha": base_sha}})
                if path.endswith("/pulls") and request.method == "GET":
                    return httpx.Response(200, json=[])
                if path.endswith("/pulls") and request.method == "POST":
                    posted.append(json.loads(request.content))
                    return httpx.Response(201, json={"number": 7, "html_url": "https://github.com/owner/repo/pull/7"})
                return httpx.Response(500)

            async with (httpx.AsyncClient(transport=httpx.MockTransport(github), base_url="https://api.github.com") as client,
                        sessions() as session):
                publisher = PatchPublisher(session, org, settings=SimpleNamespace(workspace_root=str(workspace_root)), client=client)
                real_git = publisher._git

                async def fixture_git(args, cwd, **kwargs):
                    if "push" in args:
                        remote_commit["sha"] = _git(cwd, "rev-parse", "HEAD")
                        return ""
                    return await real_git(args, cwd, **kwargs)

                publisher._git = fixture_git
                with mock_patch("services.patch.publisher.CryptoService.decrypt", return_value="fixture-token"):
                    published = await publisher.publish(patch.id, user)
                assert published.publish_status == "SUCCEEDED"
                assert published.status == PatchStatus.PULL_REQUEST_CREATED
                assert remote_commit["sha"] == published.commit_sha
                assert posted and "Fixes #3." in posted[0]["body"]
                workflow = await get_workflow(workflow_id, org, session)
                assert workflow["state"] == "PUBLISHED"
                assert workflow["pull_request_url"] == "https://github.com/owner/repo/pull/7"
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, 5)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait, 5)
        _cleanup_owned_sandboxes(workspace_root)
        await redis_client.aclose()
        await dispose_engine()
        if sys.platform != "win32":
            shutil.rmtree(tmp_path)
