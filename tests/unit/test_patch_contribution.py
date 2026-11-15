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
from packages.database.models.execution import ExecutionJobModel
from packages.database.models.issue_workflow import IssueWorkflowModel
from packages.database.models.patch import PatchModel, PatchStatus
from packages.database.models.repository import RepositoryModel
from packages.database.models.verification import RepairAttemptModel, VerificationJobModel, VerificationResultModel, VerificationStatus
from packages.shared.errors import ConflictError
from services.patch.publisher import ContributionError, PatchPublisher, _issue_workflow_for_execution
from services.patch.service import PatchService
from services.repository_memory.events import OutboxEventPublisher
from services.safety.policy import PolicyState
from services.safety.service import as_document

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
async def test_repair_publication_keeps_source_issue_link():
    org, repo, original_plan, repair_plan, original_id, repair_id, verification_id = (uuid4() for _ in range(7))
    original = SimpleNamespace(id=original_id, plan_id=original_plan, repository_id=repo, organization_id=org)
    repaired = SimpleNamespace(id=repair_id, plan_id=repair_plan, repository_id=repo, organization_id=org)
    source = SimpleNamespace(id=uuid4(), repository_id=repo, organization_id=org)
    repair = SimpleNamespace(verification_job_id=verification_id)
    verification = SimpleNamespace(id=verification_id, execution_job_id=original_id, organization_id=org)

    async def execute(statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is IssueWorkflowModel:
            return SimpleNamespace(scalar_one_or_none=lambda: source if original_plan in [
                criterion.right.value for criterion in statement._where_criteria
                if getattr(criterion.left, "key", "") == "plan_id"
            ] else None)
        return SimpleNamespace(scalar_one_or_none=lambda: repair)

    async def get(model, key):
        return verification if model is VerificationJobModel else original if key == original_id else None

    session = SimpleNamespace(execute=execute, get=get)
    assert await _issue_workflow_for_execution(cast("AsyncSession", session), org, repaired) is source


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(429, "GITHUB_RATE_LIMIT"), (503, "GITHUB_REQUEST_FAILED")])
async def test_github_publication_handles_rate_limit_and_server_errors(status, code):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(status)),
                                 base_url="https://api.github.com") as client:
        publisher = PatchPublisher(cast("AsyncSession", SimpleNamespace()), uuid4(), client=client)
        with pytest.raises(ContributionError) as error:
            await publisher._github("GET", "/repos/owner/repo", "fixture-token")
        assert error.value.code == code


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
        repository_id=uuid4(),
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

    execution = SimpleNamespace(id=patch.execution_job_id, organization_id=organization_id,
                                safety_policy_snapshot=as_document(PolicyState(version=0)))
    session = SimpleNamespace(execute=execute, get=AsyncMock(return_value=execution), commit=AsyncMock())
    with (
        mock_patch.object(PatchService, "review_patch", new=AsyncMock(return_value={"review_digest": patch.review_digest})),
        mock_patch.object(OutboxEventPublisher, "publish", new=AsyncMock()) as publish,
        mock_patch("services.safety.service.current_policy", new=AsyncMock(return_value=PolicyState(version=0))),
        mock_patch("services.patch.service.record_event", new=AsyncMock()),
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
async def test_revoked_publication_never_reads_github_credential():
    organization_id, requester, patch_id, execution_id, repository_id = (uuid4() for _ in range(5))
    patch = SimpleNamespace(id=patch_id, organization_id=organization_id, reviewed_by=requester,
                            publish_status="QUEUED", publish_error=None, status=PatchStatus.ACCEPTED,
                            execution_job_id=execution_id, repository_id=repository_id)
    execution = SimpleNamespace(id=execution_id, organization_id=organization_id, plan_id=uuid4(),
                                safety_policy_snapshot=as_document(PolicyState(version=0)))
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: patch)),
        get=AsyncMock(return_value=execution), commit=AsyncMock(),
    )
    with (mock_patch("services.patch.publisher.current_policy", new=AsyncMock(return_value=PolicyState(
        version=1, denied=frozenset({"patch:publish"})))),
          mock_patch("services.patch.publisher.record_event", new=AsyncMock()) as evidence,
          mock_patch("services.patch.publisher.CryptoService.decrypt") as decrypt,
          pytest.raises(ContributionError) as blocked):
        await PatchPublisher(cast("AsyncSession", session), organization_id).publish(patch_id, requester)
    assert blocked.value.code == "SAFETY_POLICY_DENIED"
    assert patch.publish_status == "FAILED"
    decrypt.assert_not_called()
    evidence.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_repair_patch_includes_original_and_repair_mutations_in_order():
    organization_id, original_id, repair_id, verification_id = (uuid4() for _ in range(4))
    original = SimpleNamespace(id=uuid4(), file_path="a.txt", diff_hunk=_diff("a.txt", "one\n", "two\n"))
    revised = SimpleNamespace(id=uuid4(), file_path="a.txt", diff_hunk=_diff("a.txt", "two\n", "three\n"))
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
    assert PatchService._review_digest("a" * 40, [cast("MutationModel", original)]) != PatchService._review_digest(
        "a" * 40, [cast("MutationModel", original), cast("MutationModel", revised)])


def test_multi_file_issue_patch_has_digest_bound_to_both_files():
    first = SimpleNamespace(id=uuid4(), file_path="src/parser.py", diff_hunk=_diff("src/parser.py", "old\n", "new\n"))
    second = SimpleNamespace(id=uuid4(), file_path="tests/test_parser.py",
                             diff_hunk=_diff("tests/test_parser.py", "assert False\n", "assert True\n"))
    base = "a" * 40
    digest = PatchService._review_digest(base, [cast("MutationModel", first), cast("MutationModel", second)])
    assert digest != PatchService._review_digest(base, [cast("MutationModel", first)])
    assert digest != PatchService._review_digest(base, [cast("MutationModel", second)])
    assert digest != PatchService._review_digest(base, [cast("MutationModel", second), cast("MutationModel", first)])


@pytest.mark.asyncio
async def test_publication_requires_the_actual_reviewer():
    org, reviewer, outsider = uuid4(), uuid4(), uuid4()
    patch = SimpleNamespace(id=uuid4(), organization_id=org, reviewed_by=reviewer,
                            status=PatchStatus.ACCEPTED, publish_status="QUEUED")
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: patch)),
                              get=AsyncMock(), commit=AsyncMock())
    service = PatchService(cast("AsyncSession", session), org)
    with pytest.raises(ConflictError):
        await service.request_publish(patch.id, outsider)
    session.get.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_publication_request_stays_queued_without_new_outbox_event():
    org, reviewer = uuid4(), uuid4()
    patch = SimpleNamespace(id=uuid4(), organization_id=org, reviewed_by=reviewer,
                            status=PatchStatus.ACCEPTED, publish_status="QUEUED")
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: patch)),
                              get=AsyncMock(), commit=AsyncMock())
    service = PatchService(cast("AsyncSession", session), org)
    assert await service.request_publish(patch.id, reviewer) is patch
    assert await service.request_publish(patch.id, reviewer) is patch
    session.get.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.parametrize("pr_response_lost,push_response_lost,revoke_before_push,issue_case", [
    (False, False, False, False), (False, True, False, False), (True, False, False, False), (True, True, False, False),
    (False, False, True, False), (False, False, False, True),
])
@pytest.mark.asyncio
async def test_publisher_creates_real_commit_and_records_mocked_pull_request(tmp_path, pr_response_lost, push_response_lost, revoke_before_push, issue_case):
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
    verification = SimpleNamespace(id=uuid4(), status=VerificationStatus.PASSED)
    execution = SimpleNamespace(id=execution_id, organization_id=organization_id, plan_id=uuid4(),
                                safety_policy_snapshot=as_document(PolicyState(version=0)))
    workflow = SimpleNamespace(repository_id=repository_id, base_commit_sha=base_sha,
                               github_repository_id=17, github_issue_id=20, issue_number=3) if issue_case else None

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
        if entity is VerificationResultModel:
            return Result(items=[])
        if entity is IssueWorkflowModel:
            return Result(workflow)
        return Result(items=[mutation])

    async def get(model, key):
        return {PatchModel: patch, RepositoryModel: repo, UserModel: user,
                ExecutionJobModel: execution}.get(model)

    session = SimpleNamespace(execute=execute, get=get, commit=AsyncMock(), rollback=AsyncMock())
    requests = []
    posted_bodies = []
    post_attempts = 0
    remote_commit = {}

    def github(request):
        nonlocal post_attempts
        requests.append((request.method, request.url.path))
        if request.url.path == "/repos/owner/repo":
            return httpx.Response(200, json={"id": 17, "full_name": "owner/repo", "permissions": {"push": True}, "archived": False, "default_branch": "main"})
        if request.url.path == "/repos/owner/repo/issues/3":
            return httpx.Response(200, json={"id": 20, "state": "open"})
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
            posted_bodies.append(request.content.decode())
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
        policy_reads = 0

        async def changing_policy(*_args):
            nonlocal policy_reads
            policy_reads += 1
            if revoke_before_push and policy_reads > 1:
                return PolicyState(version=1, denied=frozenset({"patch:publish"}))
            return PolicyState(version=0)

        with (mock_patch("services.patch.publisher.CryptoService.decrypt", return_value="test-token"),
              mock_patch("services.patch.publisher.record_event", new=AsyncMock()),
              mock_patch("services.patch.publisher.current_policy", new=AsyncMock(side_effect=changing_policy))):
            if push_response_lost:
                first = await publisher.publish(patch_id, requester)
                assert first is not None
                assert first.publish_status == "UNKNOWN"
                assert first.status == PatchStatus.ACCEPTED
                patch.publish_status = "QUEUED"
            result = await publisher.publish(patch_id, requester)

    assert result is not None
    if revoke_before_push:
        assert result.publish_status == "FAILED"
        assert result.publish_error == "SAFETY_POLICY_DENIED"
        assert not pushes
        assert post_attempts == 0
        return
    assert result.publish_status == "SUCCEEDED"
    assert result.status == PatchStatus.PULL_REQUEST_CREATED
    assert result.pull_request_url == "https://github.com/owner/repo/pull/7"
    assert result.branch_url == f"https://github.com/owner/repo/tree/forge/{patch_id.hex}"
    assert len(pushes) == 1
    assert pushes[0][-1] == f"HEAD:refs/heads/forge/{patch_id.hex}"
    assert (workspace / "a.txt").read_text() == "one\n"
    assert ("POST", "/repos/owner/repo/pulls") in requests
    assert post_attempts == 1
    if issue_case:
        assert 'Fixes #3.' in posted_bodies[0]
