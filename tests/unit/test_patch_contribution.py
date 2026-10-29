import difflib
import subprocess
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock
from unittest.mock import patch as mock_patch
from uuid import uuid4

import httpx
import pytest

from packages.database.models.auth import RoleBindingModel, UserModel
from packages.database.models.patch import PatchModel, PatchStatus
from packages.database.models.repository import RepositoryModel
from packages.database.models.verification import RepairAttemptModel, VerificationJobModel, VerificationStatus
from packages.shared.errors import ConflictError
from services.patch.publisher import ContributionError, PatchPublisher
from services.patch.service import PatchService
from services.repository_memory.events import OutboxEventPublisher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from packages.database.models.execution import MutationModel


def _diff(path: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), fromfile=path, tofile=path))


def _git(*args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def test_review_digest_rejects_extra_file_header():
    mutation = SimpleNamespace(id=uuid4(), file_path="a.txt", diff=_diff("a.txt", "one\n", "two\n"))
    mutation.diff_hunk = mutation.diff + "--- b.txt\n+++ b.txt\n@@ -0,0 +1 @@\n+bad\n"
    with pytest.raises(ConflictError):
        PatchService._review_digest("a" * 40, [cast("MutationModel", mutation)])


@pytest.mark.asyncio
async def test_partial_publication_can_be_requeued_without_reapproval():
    organization_id, requester, patch_id = uuid4(), uuid4(), uuid4()
    patch = SimpleNamespace(
        id=patch_id,
        organization_id=organization_id,
        reviewed_by=requester,
        status=PatchStatus.COMMITTED,
        publish_status="FAILED",
        publish_error="GITHUB_REQUEST_FAILED",
        execution_job_id=uuid4(),
        review_digest="a" * 64,
        branch_name="forge/existing",
    )

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    calls = 0

    async def execute(_statement):
        nonlocal calls
        calls += 1
        return Result(patch if calls == 1 else SimpleNamespace(status=VerificationStatus.PASSED))

    session = SimpleNamespace(execute=execute, commit=AsyncMock())
    with (
        mock_patch.object(PatchService, "review_patch", new=AsyncMock(return_value={"review_digest": patch.review_digest})),
        mock_patch.object(OutboxEventPublisher, "publish", new=AsyncMock()) as publish,
    ):
        result = await PatchService(cast("AsyncSession", session), organization_id).request_publish(patch_id, requester)

    assert result.publish_status == "QUEUED"
    assert result.publish_error is None
    assert publish.await_count == 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_publication_denies_other_tenant_before_side_effects():
    patch = SimpleNamespace(id=uuid4(), organization_id=uuid4(), reviewed_by=uuid4(), publish_status="QUEUED", status=PatchStatus.ACCEPTED)
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: patch)), get=AsyncMock(), commit=AsyncMock())
    with pytest.raises(ContributionError):
        await PatchPublisher(cast("AsyncSession", session), uuid4()).publish(patch.id, patch.reviewed_by)
    session.get.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_repair_patch_includes_original_and_repair_mutations_in_order():
    organization_id, original_id, repair_id, verification_id = (uuid4() for _ in range(4))
    original = SimpleNamespace(id=uuid4(), file_path="a.txt", diff_hunk="original")
    revised = SimpleNamespace(id=uuid4(), file_path="a.txt", diff_hunk="repair")
    link = SimpleNamespace(verification_job_id=verification_id)
    source = SimpleNamespace(organization_id=organization_id, execution_job_id=original_id)

    class Result:
        def __init__(self, value=None, items=None):
            self.value, self.items = value, items

        def scalar_one_or_none(self):
            return self.value

        def scalars(self):
            return SimpleNamespace(all=lambda: self.items)

    async def execute(statement):
        entity = statement.column_descriptions[0]["entity"]
        job_id = [
            criterion.right.value
            for criterion in statement._where_criteria
            if getattr(criterion.left, "key", "") in {"repair_execution_id", "execution_job_id"}
        ][0]
        if entity is RepairAttemptModel:
            return Result(value=link if job_id == repair_id else None)
        return Result(items=[original] if job_id == original_id else [revised])

    session = SimpleNamespace(execute=execute, get=AsyncMock(return_value=source))
    mutations = await PatchService(cast("AsyncSession", session), organization_id)._mutations_for_execution(repair_id)
    assert mutations == [original, revised]


@pytest.mark.parametrize("pr_response_lost", [False, True])
@pytest.mark.parametrize("push_response_lost", [False, True])
@pytest.mark.asyncio
async def test_publisher_creates_real_commit_and_records_mocked_pull_request(tmp_path, pr_response_lost, push_response_lost):
    organization_id, repository_id, requester, patch_id, execution_id = (uuid4() for _ in range(5))
    workspace = tmp_path / str(organization_id) / str(repository_id)
    workspace.mkdir(parents=True)
    _git("init", "-b", "main", cwd=workspace)
    (workspace / "a.txt").write_text("one\n")
    _git("add", "a.txt", cwd=workspace)
    _git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "base", cwd=workspace)
    _git("remote", "add", "origin", "https://github.com/owner/repo.git", cwd=workspace)
    base_sha = _git("rev-parse", "HEAD", cwd=workspace)
    mutation = SimpleNamespace(id=uuid4(), file_path="a.txt", diff_hunk=_diff("a.txt", "one\n", "two\n"))
    digest = PatchService._review_digest(base_sha, [cast("MutationModel", mutation)])
    patch = SimpleNamespace(
        id=patch_id,
        organization_id=organization_id,
        repository_id=repository_id,
        execution_job_id=execution_id,
        reviewed_by=requester,
        status=PatchStatus.ACCEPTED,
        publish_status="QUEUED",
        publish_error=None,
        base_commit_sha=base_sha,
        review_digest=digest,
        branch_name=None,
        branch_url=None,
        commit_sha=None,
        pull_request_number=None,
        pull_request_url=None,
    )
    repo = SimpleNamespace(
        id=repository_id,
        organization_id=organization_id,
        commit_sha=base_sha,
        full_name="owner/repo",
        clone_url="https://github.com/owner/repo.git",
        default_branch="main",
    )
    user = SimpleNamespace(is_active=True, github_token="encrypted")
    binding = SimpleNamespace(role="OWNER")
    verification = SimpleNamespace(status=VerificationStatus.PASSED)

    class Result:
        def __init__(self, value=None, items=None):
            self.value, self.items = value, items

        def scalar_one_or_none(self):
            return self.value

        def scalars(self):
            return SimpleNamespace(all=lambda: self.items or [])

    async def execute(statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is PatchModel:
            return Result(patch)
        if entity is RoleBindingModel:
            return Result(binding)
        if entity is VerificationJobModel:
            return Result(verification)
        return Result(items=[mutation])

    async def get(model, key):
        return {PatchModel: patch, RepositoryModel: repo, UserModel: user}.get(model)

    session = SimpleNamespace(execute=execute, get=get, commit=AsyncMock())
    requests = []
    post_attempts = 0
    remote_commit = {}

    def github(request):
        nonlocal post_attempts
        requests.append((request.method, request.url.path))
        if request.url.path == "/repos/owner/repo":
            return httpx.Response(200, json={"full_name": "owner/repo", "permissions": {"push": True}, "archived": False, "default_branch": "main"})
        if request.url.raw_path.endswith(("/git/ref/heads/forge%2F" + patch_id.hex).encode()):
            if remote_commit:
                return httpx.Response(200, json={"object": {"sha": remote_commit["sha"]}})
            return httpx.Response(404)
        if request.url.path.endswith(f"/git/commits/{remote_commit.get('sha')}") and remote_commit:
            return httpx.Response(200, json={"tree": {"sha": remote_commit["tree"]}, "parents": [{"sha": base_sha}]})
        if request.url.path.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json={"object": {"sha": base_sha}})
        if request.method == "GET" and request.url.path.endswith("/pulls"):
            if post_attempts and pr_response_lost:
                return httpx.Response(
                    200,
                    json=[
                        {
                            "number": 7,
                            "html_url": "https://github.com/owner/repo/pull/7",
                            "head": {"sha": patch.commit_sha},
                            "state": "open",
                        }
                    ],
                )
            return httpx.Response(200, json=[])
        if request.method == "POST" and request.url.path.endswith("/pulls"):
            post_attempts += 1
            if pr_response_lost:
                raise httpx.ReadTimeout("Response lost after pull request creation")
            return httpx.Response(201, json={"number": 7, "html_url": "https://github.com/owner/repo/pull/7"})
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(github), base_url="https://api.github.com") as client:
        publisher = PatchPublisher(cast("AsyncSession", session), organization_id, SimpleNamespace(workspace_root=str(tmp_path)), client)
        original_git = publisher._git
        pushes = []

        async def git_without_network(args, cwd, **kwargs):
            if "push" in args:
                pushes.append(args)
                remote_commit.update(sha=_git("rev-parse", "HEAD", cwd=cwd), tree=_git("rev-parse", "HEAD^{tree}", cwd=cwd))
                if push_response_lost and len(pushes) == 1:
                    raise ContributionError("GIT_TIMEOUT", "Push response lost")
                return ""
            try:
                return await original_git(args, cwd, **kwargs)
            except Exception as error:
                raise AssertionError(f"Git command failed: {args}") from error

        publisher._git = git_without_network
        with mock_patch("services.patch.publisher.CryptoService.decrypt", return_value="test-token"):
            if push_response_lost:
                first = await publisher.publish(patch_id, requester)
                assert first is not None
                assert first.publish_status == "FAILED"
                assert first.status == PatchStatus.ACCEPTED
                patch.publish_status = "QUEUED"
            result = await publisher.publish(patch_id, requester)

    assert result is not None
    assert result.publish_status == "SUCCEEDED"
    assert result.status == PatchStatus.PULL_REQUEST_CREATED
    assert result.pull_request_url == "https://github.com/owner/repo/pull/7"
    assert result.branch_url == f"https://github.com/owner/repo/tree/forge/{patch_id.hex}"
    assert len(pushes) == 1
    assert pushes[0][-1] == f"HEAD:refs/heads/forge/{patch_id.hex}"
    assert (workspace / "a.txt").read_text() == "one\n"
    assert ("POST", "/repos/owner/repo/pulls") in requests
    assert post_attempts == 1
