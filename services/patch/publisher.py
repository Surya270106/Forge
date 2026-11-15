"""Publish an approved, immutable patch from the Docker worker host."""

import asyncio
import base64
import os
import re
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.auth import RoleBindingModel, UserModel
from packages.database.models.patch import PatchModel, PatchStatus
from packages.database.models.repository import RepositoryModel
from packages.database.models.verification import VerificationJobModel, VerificationStatus
from packages.shared.config import get_settings
from packages.shared.crypto import CryptoService
from packages.shared.errors import ConflictError, NotFoundError
from services.auth.permissions import has_permission

from .service import PatchService

logger = structlog.get_logger(__name__)


class ContributionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class PatchPublisher:
    def __init__(self, session: AsyncSession, organization_id: UUID, settings=None, client: httpx.AsyncClient | None = None):
        self.session = session
        self.organization_id = organization_id
        self.settings = settings or get_settings()
        self.client = client

    async def _git(self, args: list[str], cwd: Path, *, stdin: bytes | None = None, env: dict | None = None, timeout: int = 60) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=str(cwd),
                env=env,
                stdin=asyncio.subprocess.PIPE if stdin is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError:
            raise ContributionError("GIT_UNAVAILABLE", "Git is unavailable on the Docker worker") from None
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(stdin), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            raise ContributionError("GIT_TIMEOUT", "Git operation timed out; retry after checking worker connectivity") from None
        if proc.returncode != 0:
            raise ContributionError("GIT_OPERATION_FAILED", "Could not prepare or publish the reviewed patch")
        return stdout.decode("utf-8", errors="replace").strip()

    async def _github(self, method: str, path: str, token: str, *, payload: dict | None = None, params: dict | None = None, allow_404: bool = False):
        client = self.client
        if client is None:
            client = httpx.AsyncClient(timeout=15, base_url="https://api.github.com")
        try:
            response = await client.request(
                method,
                path,
                json=payload,
                params=params,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            )
        except httpx.HTTPError:
            raise ContributionError("GITHUB_UNAVAILABLE", "GitHub is unavailable; retry the contribution") from None
        finally:
            if self.client is None:
                await client.aclose()
        if allow_404 and response.status_code == 404:
            return None
        if response.status_code in (401, 403):
            code = "GITHUB_RATE_LIMIT" if response.headers.get("x-ratelimit-remaining") == "0" else "GITHUB_ACCESS_DENIED"
            raise ContributionError(code, "GitHub denied access; reconnect GitHub or check repository permissions")
        if response.status_code >= 400:
            raise ContributionError("GITHUB_REQUEST_FAILED", "GitHub could not complete the contribution request")
        try:
            return response.json()
        except ValueError:
            raise ContributionError("GITHUB_BAD_RESPONSE", "GitHub returned an unreadable response") from None

    async def publish(self, patch_id: UUID, requested_by: UUID) -> PatchModel | None:
        patch = (
            await self.session.execute(
                select(PatchModel).where(PatchModel.id == patch_id).with_for_update().execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if not patch or patch.organization_id != self.organization_id or patch.reviewed_by != requested_by:
            raise ContributionError("PATCH_ACCESS_DENIED", "Patch approval is unavailable")
        if patch.publish_status == "SUCCEEDED":
            return patch
        if patch.publish_status not in {"QUEUED", "RUNNING"} or patch.status not in {PatchStatus.ACCEPTED, PatchStatus.COMMITTED}:
            raise ContributionError("PATCH_NOT_READY", "Patch is not approved for publication")

        patch.publish_status = "RUNNING"
        try:
            user = await self.session.get(UserModel, requested_by)
            binding = (
                await self.session.execute(
                    select(RoleBindingModel).where(
                        RoleBindingModel.organization_id == self.organization_id,
                        RoleBindingModel.user_id == requested_by,
                    )
                )
            ).scalar_one_or_none()
            repo = await self.session.get(RepositoryModel, patch.repository_id)
            if not user or not user.is_active or not user.github_token or not binding or not has_permission(binding.role, "patch:approve"):
                raise ContributionError("APPROVAL_REVOKED", "GitHub access or workspace permission is no longer available")
            if not repo or repo.organization_id != self.organization_id or repo.commit_sha != patch.base_commit_sha:
                raise ContributionError("REPOSITORY_CHANGED", "Repository base changed; prepare a new patch review")
            verification = (
                await self.session.execute(
                    select(VerificationJobModel)
                    .where(
                        VerificationJobModel.execution_job_id == patch.execution_job_id,
                        VerificationJobModel.organization_id == self.organization_id,
                    )
                    .order_by(VerificationJobModel.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not verification or verification.status != VerificationStatus.PASSED:
                raise ContributionError("VERIFICATION_NOT_PASSED", "The latest verification has not passed")
            base_sha = patch.base_commit_sha
            if not isinstance(base_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", base_sha):
                raise ContributionError("INVALID_BASE", "The imported repository has no valid base commit")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo.full_name):
                raise ContributionError("INVALID_REPOSITORY", "Repository identity is invalid")
            owner, name = repo.full_name.split("/", 1)
            if repo.clone_url != f"https://github.com/{owner}/{name}.git":
                raise ContributionError("INVALID_REPOSITORY", "Repository remote is not the verified GitHub repository")
            try:
                token = CryptoService.decrypt(user.github_token)
            except ValueError:
                raise ContributionError("GITHUB_CREDENTIAL_INVALID", "Reconnect GitHub before publishing") from None
            try:
                review = await PatchService(self.session, self.organization_id).review_patch(patch.id)
            except (ConflictError, NotFoundError):
                raise ContributionError("STALE_APPROVAL", "The reviewed patch changed; approve it again") from None
            if review["review_digest"] != patch.review_digest:
                raise ContributionError("STALE_APPROVAL", "The reviewed patch changed; approve it again")

            api_root = f"/repos/{quote(owner)}/{quote(name)}"
            metadata = await self._github("GET", api_root, token)
            if not isinstance(metadata, dict):
                raise ContributionError("GITHUB_BAD_RESPONSE", "GitHub returned invalid repository metadata")
            permissions = metadata.get("permissions")
            if not isinstance(permissions, dict) or not isinstance(metadata.get("full_name"), str):
                raise ContributionError("GITHUB_BAD_RESPONSE", "GitHub returned invalid repository metadata")
            if metadata["full_name"].casefold() != repo.full_name.casefold() or not permissions.get("push") or metadata.get("archived"):
                raise ContributionError("GITHUB_ACCESS_DENIED", "GitHub did not confirm push access to this repository")
            base_branch = repo.default_branch
            if metadata.get("default_branch") != base_branch or not re.fullmatch(r"[A-Za-z0-9_./-]{1,200}", base_branch) or ".." in base_branch:
                raise ContributionError("BASE_CHANGED", "The repository base branch changed; import it again")
            branch = f"forge/{patch.id.hex}"
            patch.branch_name = branch
            remote_branch = await self._github("GET", f"{api_root}/git/ref/heads/{quote(branch, safe='')}", token, allow_404=True)
            if remote_branch is not None and not isinstance(remote_branch, dict):
                raise ContributionError("GITHUB_BAD_RESPONSE", "GitHub returned an invalid branch reference")
            remote_object = remote_branch.get("object") if remote_branch else None
            if remote_object is not None and not isinstance(remote_object, dict):
                raise ContributionError("GITHUB_BAD_RESPONSE", "GitHub returned an invalid branch reference")
            remote_sha = remote_object.get("sha") if remote_object else None
            if not remote_sha:
                base_ref = await self._github("GET", f"{api_root}/git/ref/heads/{quote(base_branch, safe='')}", token)
                base_object = base_ref.get("object") if isinstance(base_ref, dict) else None
                if not isinstance(base_object, dict) or base_object.get("sha") != base_sha:
                    raise ContributionError("BASE_ADVANCED", "GitHub base branch advanced; re-import and review the patch")

            workspace = Path(self.settings.workspace_root, str(self.organization_id), str(repo.id)).resolve()
            if not workspace.is_dir():
                raise ContributionError("WORKSPACE_MISSING", "Repository workspace is unavailable on the worker")
            if await self._git(["rev-parse", "HEAD"], workspace) != base_sha:
                raise ContributionError("WORKSPACE_CHANGED", "Worker repository base changed; prepare a new patch")
            if await self._git(["remote", "get-url", "origin"], workspace) != repo.clone_url:
                raise ContributionError("REMOTE_CHANGED", "Worker repository remote changed; re-import before publishing")
            contribution_root = workspace.parent / ".forge-contributions"
            try:
                contribution_root.mkdir(exist_ok=True)
            except OSError:
                raise ContributionError("WORKSPACE_UNAVAILABLE", "Worker cannot prepare an isolated contribution worktree") from None
            temp = contribution_root / uuid4().hex
            created = False
            try:
                await self._git(["-c", "core.hooksPath=/dev/null", "worktree", "add", "--detach", str(temp), base_sha], workspace)
                created = True
                paths: set[str] = set()
                for change in review["changes"]:
                    path = change["path"]
                    candidate = temp / path
                    target = candidate.resolve()
                    parts = Path(path).parts
                    if not target.is_relative_to(temp) or any((temp.joinpath(*parts[:index])).is_symlink() for index in range(1, len(parts) + 1)):
                        raise ContributionError("UNSAFE_PATCH", "Patch targets a path outside its isolated worktree")
                    diff = change["diff"].encode("utf-8")
                    await self._git(["apply", "-p0", "--check", "-"], temp, stdin=diff)
                    await self._git(["apply", "-p0", "-"], temp, stdin=diff)
                    paths.add(path)
                await self._git(["add", "--", *sorted(paths)], temp)
                staged = await self._git(["diff", "--cached", "--name-only"], temp)
                if set(staged.splitlines()) != paths:
                    raise ContributionError("PATCH_SCOPE_CHANGED", "Staged files differ from the reviewed patch")
                await self._git(["diff", "--cached", "--check"], temp)
                await self._git(
                    [
                        "-c",
                        "user.name=Forge",
                        "-c",
                        "user.email=forge-bot@users.noreply.github.com",
                        "-c",
                        "commit.gpgsign=false",
                        "-c",
                        "core.hooksPath=/dev/null",
                        "commit",
                        "-m",
                        f"Forge patch {patch.id} ({patch.review_digest})",
                    ],
                    temp,
                )
                local_sha = await self._git(["rev-parse", "HEAD"], temp)
                local_tree = await self._git(["rev-parse", "HEAD^{tree}"], temp)
                if remote_sha:
                    remote_commit = await self._github("GET", f"{api_root}/git/commits/{remote_sha}", token)
                    if not isinstance(remote_commit, dict):
                        raise ContributionError("GITHUB_BAD_RESPONSE", "GitHub returned invalid commit metadata")
                    remote_parents = remote_commit.get("parents")
                    remote_tree = remote_commit.get("tree")
                    if (
                        not isinstance(remote_parents, list)
                        or not isinstance(remote_tree, dict)
                        or not all(isinstance(item, dict) for item in remote_parents)
                    ):
                        raise ContributionError("GITHUB_BAD_RESPONSE", "GitHub returned invalid commit metadata")
                    parents = [item.get("sha") for item in remote_parents]
                    if remote_tree.get("sha") != local_tree or parents != [base_sha]:
                        raise ContributionError("BRANCH_CONFLICT", "The dedicated GitHub branch contains different changes")
                else:
                    header = base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")
                    env = os.environ.copy()
                    env.update(
                        {
                            "GIT_TERMINAL_PROMPT": "0",
                            "GIT_CONFIG_COUNT": "1",
                            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {header}",
                        }
                    )
                    await self._git(["-c", "core.hooksPath=/dev/null", "push", "origin", f"HEAD:refs/heads/{branch}"], temp, env=env, timeout=120)
                    remote_sha = local_sha
                patch.commit_sha = remote_sha
                patch.branch_url = f"https://github.com/{owner}/{name}/tree/{branch}"
                patch.status = PatchStatus.COMMITTED
            finally:
                if created:
                    try:
                        await self._git(["worktree", "remove", "--force", str(temp)], workspace)
                    except ContributionError:
                        logger.warning("contribution_worktree_cleanup_needed", patch_id=str(patch.id))

            existing = await self._github(
                "GET", f"{api_root}/pulls", token, params={"state": "all", "head": f"{owner}:{branch}", "base": base_branch}
            )
            if not isinstance(existing, list):
                raise ContributionError("GITHUB_BAD_RESPONSE", "GitHub returned invalid pull request results")
            if existing:
                pr = next(
                    (
                        item
                        for item in existing
                        if isinstance(item, dict) and isinstance(item.get("head"), dict) and item["head"].get("sha") == remote_sha
                    ),
                    None,
                )
                if not pr or pr.get("state") != "open":
                    raise ContributionError("PR_CONFLICT", "A matching pull request is closed or points to different changes")
            else:
                try:
                    pr = await self._github(
                        "POST",
                        f"{api_root}/pulls",
                        token,
                        payload={
                            "title": f"Forge patch {patch.id.hex[:8]}",
                            "head": branch,
                            "base": base_branch,
                            "body": f"Reviewed Forge patch `{patch.id}`. Review digest: `{patch.review_digest}`.",
                        },
                    )
                except ContributionError as error:
                    if error.code not in {"GITHUB_UNAVAILABLE", "GITHUB_BAD_RESPONSE", "GITHUB_REQUEST_FAILED"}:
                        raise
                    # The request may have succeeded even if its response was lost.
                    recovered = await self._github(
                        "GET", f"{api_root}/pulls", token, params={"state": "all", "head": f"{owner}:{branch}", "base": base_branch}
                    )
                    if not isinstance(recovered, list):
                        raise ContributionError("GITHUB_BAD_RESPONSE", "GitHub returned invalid pull request results")
                    pr = next(
                        (
                            item
                            for item in recovered
                            if isinstance(item, dict)
                            and isinstance(item.get("head"), dict)
                            and item["head"].get("sha") == remote_sha
                            and item.get("state") == "open"
                        ),
                        None,
                    )
                    if pr is None:
                        raise error
            if not isinstance(pr, dict):
                raise ContributionError("GITHUB_BAD_RESPONSE", "GitHub returned an invalid pull request")
            number = pr.get("number")
            url = pr.get("html_url")
            if not isinstance(number, int) or url != f"https://github.com/{owner}/{name}/pull/{number}":
                raise ContributionError("INVALID_PR_RESPONSE", "GitHub returned an invalid pull request identity")
            patch.pull_request_number = number
            patch.pull_request_url = url
            patch.status = PatchStatus.PULL_REQUEST_CREATED
            patch.publish_status = "SUCCEEDED"
            patch.publish_error = None
            await self.session.commit()
            return patch
        except ContributionError as error:
            patch.publish_status = "FAILED"
            patch.publish_error = error.code
            await self.session.commit()
            logger.warning("contribution_failed", patch_id=str(patch.id), code=error.code)
            return patch
        except Exception as error:
            await self.session.rollback()
            patch = await self.session.get(PatchModel, patch_id)
            if patch and patch.organization_id == self.organization_id and patch.publish_status != "SUCCEEDED":
                patch.publish_status = "FAILED"
                patch.publish_error = "PUBLISH_UNEXPECTED_ERROR"
                await self.session.commit()
            logger.error("contribution_unexpected_failure", patch_id=str(patch_id), error_type=type(error).__name__)
            return patch
