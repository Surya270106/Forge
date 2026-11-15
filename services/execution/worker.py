import asyncio
import hashlib
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import networkx as nx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.execution import (
    ExecutionJobModel,
    ExecutionLogModel,
    ExecutionStatus,
    MutationModel,
)
from packages.database.models.planning import PlanModel, PlanStatus, TaskEdgeModel, TaskNodeModel
from packages.database.models.repository import RepositoryModel
from packages.database.models.verification import RepairAttemptModel, RepairAttemptStatus
from packages.shared.config import get_settings
from packages.shared.identifiers import generate_id
from services.safety.policy import decide, parse_command, workspace_has_sensitive_files
from services.safety.service import as_document, current_policy, from_document

from .events import (
    ExecutionEventPublisher,
    create_execution_cancelled_event,
    create_execution_completed_event,
    create_execution_failed_event,
    create_execution_started_event,
    create_mutation_applied_event,
)
from .flight_recorder import record_event
from .lease import claim_execution, owns_execution, renew_execution
from .patch_engine import PatchEngine
from .sandbox import DockerSandbox, SandboxRuntime
from .workspace import prepare_execution_workspace, workspace_change_fingerprint

logger = structlog.get_logger(__name__)


class ExecutionWorker:
    def __init__(self, session: AsyncSession, sandbox: SandboxRuntime, settings=None, session_maker=None):
        self.session = session
        self.sandbox = sandbox
        self.settings = settings or get_settings()
        self.publisher = ExecutionEventPublisher(session)
        self.session_maker = session_maker
        self.owner = str(uuid4())
        self._lost_lease = False
        self._sandbox_running = False
        self._cancel_requested = False

    async def _watch_cancellation(self, job: ExecutionJobModel, generation: int, running_task: asyncio.Task) -> None:
        if self.session_maker is None:
            return
        from packages.database.tenant import set_tenant

        try:
            while True:
                await asyncio.sleep(1)
                set_tenant(job.organization_id)
                async with self.session_maker() as session:
                    current = (await session.execute(select(ExecutionJobModel).where(
                        ExecutionJobModel.id == job.id,
                        ExecutionJobModel.organization_id == job.organization_id,
                    ))).scalar_one_or_none()
                    if not current or not owns_execution(current, self.owner, generation):
                        self._lost_lease = True
                        running_task.cancel()
                        return
                    if current.cancellation_requested_at:
                        self._cancel_requested = True
                        running_task.cancel()
                        return
                    if (await current_policy(session, job.organization_id)).stopped:
                        current.cancellation_requested_at = datetime.now(UTC)
                        await session.commit()
                        self._cancel_requested = True
                        running_task.cancel()
                        return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("execution_cancellation_watch_failed", execution_id=str(job.id))
            self._lost_lease = True
            running_task.cancel()

    async def _finish_cancellation(self, job: ExecutionJobModel, generation: int) -> None:
        job_id, organization_id = job.id, job.organization_id
        await self.session.rollback()  # Discard provisional mutations and logs.
        current = (await self.session.execute(select(ExecutionJobModel).where(
            ExecutionJobModel.id == job_id, ExecutionJobModel.organization_id == organization_id,
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not current or not owns_execution(current, self.owner, generation) or not current.cancellation_requested_at:
            await self.session.rollback()
            return
        await record_event(self.session, organization_id, job_id, "execution.cancellation_started", "worker",
                           "execution.worker", owner=self.owner, generation=generation,
                           idempotency_key=f"cancellation-started-{generation}")
        await self.session.commit()
        try:
            await self.sandbox.cleanup()
        except Exception:
            logger.exception("execution_cancellation_cleanup_failed", execution_id=str(job_id))
            cleanup_failed = True
        else:
            cleanup_failed = False
        current = (await self.session.execute(select(ExecutionJobModel).where(
            ExecutionJobModel.id == job_id, ExecutionJobModel.organization_id == organization_id,
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not current or not owns_execution(current, self.owner, generation) or not current.cancellation_requested_at:
            await self.session.rollback()
            return
        plan = await self.session.get(PlanModel, current.plan_id)
        if cleanup_failed:
            current.status = ExecutionStatus.FAILED
            failure = "Cancellation cleanup failed; inspect the sandbox before retrying"
            current.error_message = failure
            if plan and plan.status == PlanStatus.EXECUTING:
                plan.status = PlanStatus.FAILED
            await self._fail_linked_repair(current, failure)
            await self.publisher.publish(create_execution_failed_event(
                organization_id, current.repository_id, current.id, failure,
            ))
            event_type = "execution.cancellation_failed"
        else:
            current.status = ExecutionStatus.CANCELLED
            if plan and plan.status == PlanStatus.EXECUTING:
                plan.status = PlanStatus.CANCELLED
            repair = (await self.session.execute(select(RepairAttemptModel).where(
                RepairAttemptModel.repair_execution_id == current.id,
                RepairAttemptModel.organization_id == current.organization_id,
                RepairAttemptModel.status == RepairAttemptStatus.EXECUTING,
            ))).scalar_one_or_none()
            if repair:
                repair.status = RepairAttemptStatus.CANCELLED
            await self.publisher.publish(create_execution_cancelled_event(
                organization_id, current.repository_id, current.id, current.plan_id,
            ))
            event_type = "execution.cancelled"
        current.finished_at = datetime.now(UTC)
        await record_event(self.session, organization_id, job_id, event_type, "worker", "execution.worker",
                           data={"generation": generation}, owner=self.owner, generation=generation,
                           idempotency_key=f"cancellation-result-{generation}")
        await self.session.commit()

    async def _heartbeat(self, job: ExecutionJobModel, generation: int, running_task: asyncio.Task) -> None:
        if self.session_maker is None:
            return
        from packages.database.tenant import set_tenant

        try:
            while True:
                await asyncio.sleep(30)
                set_tenant(job.organization_id)
                async with self.session_maker() as session:
                    if not await renew_execution(session, job.id, job.organization_id, self.owner, generation, 180):
                        self._lost_lease = True
                        if self._sandbox_running:
                            running_task.cancel()
                        return
        except asyncio.CancelledError:
            raise
        except Exception:
            self._lost_lease = True
            if self._sandbox_running:
                running_task.cancel()

    async def _fail_linked_repair(self, job: ExecutionJobModel, message: str) -> None:
        repair = (
            await self.session.execute(
                select(RepairAttemptModel).where(
                    RepairAttemptModel.repair_execution_id == job.id,
                    RepairAttemptModel.organization_id == job.organization_id,
                    RepairAttemptModel.status == RepairAttemptStatus.EXECUTING,
                )
            )
        ).scalar_one_or_none()
        if repair:
            repair.status = RepairAttemptStatus.FAILED
            repair.error_message = message[:255]

    async def _log(
        self,
        job_id: UUID,
        org_id: UUID,
        message: str | None,
        node_id: UUID | None = None,
        level: str = "INFO",
        stream: str = "stdout",
    ):
        log_entry = ExecutionLogModel(
            id=generate_id(),
            organization_id=org_id,
            execution_job_id=job_id,
            task_node_id=node_id,
            level=level,
            message=message,
            stream=stream,
        )
        self.session.add(log_entry)

        # Publish to Redis for real-time WebSockets
        try:
            import json

            import redis.asyncio as redis_async
            redis_client = redis_async.from_url(self.settings.redis_url)
            channel_name = f"execution:{job_id}:logs"
            payload = {
                "id": str(log_entry.id),
                "created_at": log_entry.created_at.isoformat() if log_entry.created_at else datetime.now(UTC).isoformat(),
                "level": log_entry.level,
                "message": log_entry.message,
                "stream": log_entry.stream
            }
            await redis_client.publish(channel_name, json.dumps(payload))
            await redis_client.aclose()
        except Exception as e:
            logger.warning("Failed to publish log to redis", error=str(e))

        await self.session.flush()

    async def execute_job(self, job_id: UUID) -> None:
        job = (
            await self.session.execute(
                select(ExecutionJobModel).where(ExecutionJobModel.id == job_id).with_for_update().execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if not job or job.status != ExecutionStatus.PENDING:
            return

        plan = await self.session.get(PlanModel, job.plan_id)
        repo = await self.session.get(RepositoryModel, job.repository_id)
        if (not plan or not repo or plan.organization_id != job.organization_id or repo.organization_id != job.organization_id
            or plan.status not in ({PlanStatus.APPROVED, PlanStatus.EXECUTING} if getattr(job, "lease_generation", 0) else {PlanStatus.APPROVED})):
            job.status = ExecutionStatus.FAILED
            job.finished_at = datetime.now(UTC)
            job.error_message = "Approved plan or repository is unavailable for this execution."
            await self._fail_linked_repair(job, job.error_message or "Execution failed")
            await self.publisher.publish(create_execution_failed_event(job.organization_id, job.repository_id, job.id, job.error_message or "Execution failed"))
            await record_event(self.session, job.organization_id, job.id, "execution.failed", "worker", "execution.worker",
                               data={"reason_code": "PLAN_UNAVAILABLE"}, idempotency_key="plan-unavailable")
            await self.session.commit()
            return

        source_dir = os.path.join(self.settings.workspace_root, str(job.organization_id), str(job.repository_id))
        try:
            revision = (await asyncio.to_thread(
                subprocess.run, ["git", "-C", source_dir, "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10, check=True,
            )).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            revision = None
        if not revision or revision != job.commit_sha_before or revision != repo.commit_sha:
            job.status = ExecutionStatus.FAILED
            job.finished_at = datetime.now(UTC)
            job.error_message = "Repository workspace base changed or is unavailable."
            await self._fail_linked_repair(job, job.error_message or "Execution failed")
            await self.publisher.publish(create_execution_failed_event(job.organization_id, job.repository_id, job.id, job.error_message or "Execution failed"))
            await record_event(self.session, job.organization_id, job.id, "execution.failed", "worker", "execution.worker",
                               data={"reason_code": "BASE_CHANGED"}, idempotency_key="base-changed")
            await self.session.commit()
            return

        generation = await claim_execution(self.session, job.id, job.organization_id, self.owner, 180, commit=False)
        if generation is None:
            await self.session.rollback()
            return
        resolved_policy = await current_policy(self.session, job.organization_id)
        if job.safety_policy_snapshot is None:
            job.safety_policy_snapshot = as_document(resolved_policy)
        snapshot = from_document(job.safety_policy_snapshot)
        plan.status = PlanStatus.EXECUTING
        await self.publisher.publish(create_execution_started_event(job.organization_id, job.repository_id, job.id, plan.id))
        await record_event(self.session, job.organization_id, job.id, "worker.claimed", "worker", "execution.worker",
                           actor_id=self.owner, data={"generation": generation}, owner=self.owner, generation=generation,
                           idempotency_key=f"claimed-{generation}")
        if generation > 1:
            await record_event(self.session, job.organization_id, job.id, "worker.reclaimed", "worker", "execution.worker",
                               actor_id=self.owner, data={"generation": generation}, owner=self.owner, generation=generation,
                               idempotency_key=f"reclaimed-{generation}")
        await record_event(self.session, job.organization_id, job.id, "execution.started", "worker", "execution.worker",
                           data={"plan_id": plan.id, "generation": generation}, owner=self.owner, generation=generation,
                           idempotency_key=f"started-{generation}")
        await record_event(self.session, job.organization_id, job.id, "agent.started", "agent", "execution.worker",
                           data={"plan_id": plan.id}, owner=self.owner, generation=generation,
                           idempotency_key=f"agent-started-{generation}")
        await record_event(self.session, job.organization_id, job.id, "safety.policy_resolved", "worker", "safety.policy",
                           data={"policy_version": resolved_policy.version, "generation": generation},
                           owner=self.owner, generation=generation, idempotency_key=f"safety-policy-{generation}")
        await self.session.commit()

        running_task = asyncio.current_task()
        assert running_task is not None
        heartbeat = asyncio.create_task(self._heartbeat(job, generation, running_task))
        running_task.add_done_callback(lambda _: heartbeat.cancel())
        try:
            workspace_dir = str(await asyncio.to_thread(
                prepare_execution_workspace,
                self.settings.workspace_root, job.organization_id, job.repository_id, job.id, job.commit_sha_before, generation,
            ))
            if isinstance(self.sandbox, DockerSandbox):
                self.sandbox.workspace_root = workspace_dir
            from services.patch.service import PatchService

            prior_mutations = await PatchService(self.session, job.organization_id)._mutations_for_execution(job.id)
            if prior_mutations:
                PatchService._review_digest(job.commit_sha_before, prior_mutations)
                for mutation in prior_mutations:
                    for args in (("apply", "-p0", "--check", "-"), ("apply", "-p0", "-")):
                        await asyncio.to_thread(
                            subprocess.run, ["git", "-C", workspace_dir, *args], input=mutation.diff_hunk,
                            text=True, capture_output=True, timeout=30, check=True,
                        )
            await record_event(self.session, job.organization_id, job.id,
                               "repository.worktree_recovered" if prior_mutations else "repository.worktree_created",
                               "worker", "execution.workspace", data={"base_commit": job.commit_sha_before, "generation": generation},
                               owner=self.owner, generation=generation, idempotency_key=f"workspace-{generation}")
            await self.session.commit()
        except (OSError, RuntimeError, subprocess.SubprocessError):
            if not await self._still_owned(job.id, generation):
                await self.session.rollback()
                heartbeat.cancel()
                return
            job.status = ExecutionStatus.FAILED
            job.finished_at = datetime.now(UTC)
            failure = "Execution workspace could not be prepared safely."
            job.error_message = failure
            await self._fail_linked_repair(job, failure)
            await self.publisher.publish(create_execution_failed_event(job.organization_id, job.repository_id, job.id, failure))
            await record_event(self.session, job.organization_id, job.id, "execution.failed", "worker", "execution.worker",
                               data={"reason_code": "WORKSPACE_UNAVAILABLE"}, owner=self.owner, generation=generation,
                               idempotency_key=f"workspace-failed-{generation}")
            await record_event(self.session, job.organization_id, job.id, "agent.failed", "agent", "execution.worker",
                               data={"reason_code": "WORKSPACE_UNAVAILABLE"}, owner=self.owner, generation=generation,
                               idempotency_key=f"agent-failed-{generation}")
            await self.session.commit()
            heartbeat.cancel()
            return

        await self._log(job.id, job.organization_id, f"Execution {job.id} started.")

        patch_engine = PatchEngine(workspace_dir)

        # Build DAG
        stmt_nodes = select(TaskNodeModel).where(TaskNodeModel.plan_id == plan.id)
        nodes = (await self.session.execute(stmt_nodes)).scalars().all()

        stmt_edges = select(TaskEdgeModel).where(TaskEdgeModel.plan_id == plan.id)
        edges = (await self.session.execute(stmt_edges)).scalars().all()

        dag = nx.DiGraph()
        for n in nodes:
            dag.add_node(n.id, data=n)
        for e in edges:
            dag.add_edge(e.from_node_id, e.to_node_id, condition=e.condition)

        if not nx.is_directed_acyclic_graph(dag):
            if not await self._still_owned(job.id, generation):
                await self.session.rollback()
                heartbeat.cancel()
                return
            job.status = ExecutionStatus.FAILED
            job.error_message = "Plan contains cyclic dependencies."
            plan.status = PlanStatus.FAILED
            job.finished_at = datetime.now(UTC)
            await self._fail_linked_repair(job, job.error_message or "Execution failed")
            await self._log(job.id, job.organization_id, job.error_message, level="ERROR")
            await self.publisher.publish(create_execution_failed_event(job.organization_id, job.repository_id, job.id, job.error_message or "Execution failed"))
            await record_event(self.session, job.organization_id, job.id, "execution.failed", "worker", "execution.worker",
                               data={"reason_code": "PLAN_CYCLE"}, owner=self.owner, generation=generation,
                               idempotency_key=f"cycle-{generation}")
            await record_event(self.session, job.organization_id, job.id, "agent.failed", "agent", "execution.worker",
                               data={"reason_code": "PLAN_CYCLE"}, owner=self.owner, generation=generation,
                               idempotency_key=f"agent-failed-{generation}")
            await self.session.commit()
            heartbeat.cancel()
            return

        self._sandbox_running = True
        if self._lost_lease or not await self._still_owned(job.id, generation, lock=False):
            await self.session.rollback()
            heartbeat.cancel()
            return
        watcher = asyncio.create_task(self._watch_cancellation(job, generation, running_task))
        try:
            async def _execute_nodes():
                assert job is not None
                # Keep mutations and their evidence provisional until final ownership is fenced.
                pending_mutations = False
                mutation_events: list[tuple[UUID, UUID]] = []

                async def step_event(event_type: str, actor: str, source: str, node: TaskNodeModel, data: dict, key: str) -> None:
                    assert job is not None
                    if self.session_maker is None:
                        await record_event(self.session, job.organization_id, job.id, event_type, actor, source,
                                           task_node_id=node.id, data=data, owner=self.owner, generation=generation,
                                           idempotency_key=key)
                        if not pending_mutations:
                            await self.session.commit()
                        return
                    async with self.session_maker() as evidence_session:
                        await record_event(evidence_session, job.organization_id, job.id, event_type, actor, source,
                                           task_node_id=node.id, data=data, owner=self.owner, generation=generation,
                                           idempotency_key=key)
                        await evidence_session.commit()

                for node_id in nx.topological_sort(dag):
                    node: TaskNodeModel = dag.nodes[node_id]["data"]
                    if self.session_maker is None:
                        active_policy = await current_policy(self.session, job.organization_id)
                    else:
                        from packages.database.tenant import set_tenant

                        set_tenant(job.organization_id)
                        async with self.session_maker() as policy_session:
                            active_policy = await current_policy(policy_session, job.organization_id)
                    action_target = node.parameters.get("command", "") if node.action_type == "command" else node.target
                    decision = decide(node.action_type, action_target, snapshot, active_policy,
                                      repository_id=job.repository_id)
                    await step_event("safety.permission_granted" if decision.effect == "ALLOW" else
                                     "safety.approval_required" if decision.effect == "REQUIRES_APPROVAL" else
                                     "safety.permission_denied", "worker", "safety.policy", node,
                                     {"action_type": node.action_type, "decision": decision.effect,
                                      "reason_code": decision.reason, "policy_version": decision.policy_version,
                                      "risk": decision.risk or "UNKNOWN", "capability": decision.capability or "UNKNOWN",
                                      "action_digest": hashlib.sha256(str(action_target).encode()).hexdigest()},
                                     f"safety-{generation}-{node.id}")
                    if decision.effect != "ALLOW":
                        raise PermissionError(f"Safety Gate blocked {node.action_type}: {decision.reason}")
                    await step_event("agent.step_started", "agent", "execution.worker", node,
                                     {"node_id": node.id, "action_type": node.action_type}, f"node-start-{generation}-{node.id}")
                    await self._log(
                        job.id,
                        job.organization_id,
                        f"Executing task {node.action_type} on {node.target}",
                        node_id=node.id,
                    )

                    if node.action_type == "command":
                        cmd_str = node.parameters.get("command", "")
                        if await asyncio.to_thread(workspace_has_sensitive_files, Path(workspace_dir)):
                            await step_event("safety.permission_denied", "worker", "safety.policy", node,
                                             {"action_type": "command", "reason_code": "SENSITIVE_WORKSPACE",
                                              "capability": "command:execute", "decision": "DENY",
                                              "policy_version": active_policy.version},
                                             f"safety-sensitive-{generation}-{node.id}")
                            raise PermissionError("Safety Gate blocks commands in a workspace containing sensitive files")
                        if isinstance(self.sandbox, DockerSandbox) and self.sandbox.event_sink and not self.sandbox.container_id:
                            await self.sandbox._ensure_container()
                        await step_event("tool.started", "tool", "execution.worker", node,
                                         {"node_id": node.id, "action_type": "command"}, f"tool-start-{generation}-{node.id}")
                        await step_event("sandbox.command_started", "sandbox", "execution.sandbox", node,
                                         {"node_id": node.id}, f"command-start-{generation}-{node.id}")
                        before = await asyncio.to_thread(workspace_change_fingerprint, workspace_dir)

                        # Normalize target to absolute container path
                        target = node.target if node.target and node.target != "workspace" else ""
                        container_cwd = "/workspace"
                        if target:
                            container_cwd = f"/workspace/{target}"

                        # Using Sandbox
                        try:
                            result = await self.sandbox.run_command(parse_command(cmd_str), cwd=container_cwd)
                        except Exception:
                            await step_event("tool.failed", "tool", "execution.worker", node,
                                             {"node_id": node.id, "reason_code": "SANDBOX_ERROR"},
                                             f"tool-end-{generation}-{node.id}")
                            raise
                        await step_event("sandbox.command_completed" if result.exit_code == 0 else "sandbox.command_failed",
                                         "sandbox", "execution.sandbox", node,
                                         {"node_id": node.id, "exit_code": result.exit_code,
                                          "stdout_bytes": len(result.stdout.encode()), "stderr_bytes": len(result.stderr.encode())},
                                         f"command-end-{generation}-{node.id}")
                        if result.exit_code == -1:
                            reason = ("sandbox.timed_out" if result.stderr.startswith("Command timed out") else
                                      "sandbox.output_limit_exceeded" if result.stderr.startswith("Command exceeded the output limit") else None)
                            if reason:
                                await step_event(reason, "sandbox", "execution.sandbox", node,
                                                 {"node_id": node.id}, f"command-abort-{generation}-{node.id}")
                        await step_event("tool.completed" if result.exit_code == 0 else "tool.failed", "tool", "execution.worker", node,
                                         {"node_id": node.id, "action_type": "command", "exit_code": result.exit_code},
                                         f"tool-end-{generation}-{node.id}")

                        if result.stdout:
                            await self._log(job.id, job.organization_id, result.stdout, node_id=node.id)
                        if result.stderr:
                            await self._log(
                                job.id,
                                job.organization_id,
                                result.stderr,
                                node_id=node.id,
                                stream="stderr",
                            )

                        if result.exit_code != 0:
                            raise RuntimeError(f"Command failed with exit code {result.exit_code}.")
                        if await asyncio.to_thread(workspace_change_fingerprint, workspace_dir) != before:
                            raise RuntimeError("Command changed repository files outside reviewable edit_file nodes.")

                    elif node.action_type == "edit_file":
                        await step_event("tool.started", "tool", "execution.patch_engine", node,
                                         {"node_id": node.id, "action_type": "edit_file"}, f"tool-start-{generation}-{node.id}")
                        new_content = node.parameters.get("changes", "")
                        if isinstance(new_content, (dict, list)):
                            import json
                            new_content = json.dumps(new_content, indent=2)
                        elif not isinstance(new_content, str):
                            new_content = str(new_content)
                        try:
                            diff = await asyncio.to_thread(patch_engine.apply_patch, node.target, new_content)
                        except Exception:
                            await step_event("tool.failed", "tool", "execution.patch_engine", node,
                                             {"node_id": node.id, "reason_code": "PATCH_ERROR"},
                                             f"tool-end-{generation}-{node.id}")
                            raise

                        mutation = MutationModel(
                            id=generate_id(),
                            organization_id=job.organization_id,
                            repository_id=job.repository_id,
                            execution_job_id=job.id,
                            task_node_id=node.id,
                            file_path=node.target,
                            mutation_type="UPDATE",
                            diff_hunk=diff,
                        )
                        self.session.add(mutation)
                        pending_mutations = True
                        mutation_events.append((node.id, mutation.id))
                        await step_event("tool.completed", "tool", "execution.patch_engine", node,
                                         {"node_id": node.id, "action_type": "edit_file", "status": "PROVISIONAL"},
                                         f"tool-end-{generation}-{node.id}")
                        await step_event("repository.change_detected", "agent", "execution.patch_engine", node,
                                         {"node_id": node.id, "status": "PROVISIONAL"}, f"change-{generation}-{node.id}")
                        await self._log(
                            job.id,
                            job.organization_id,
                            f"Applied patch to {node.target}",
                            node_id=node.id,
                        )
                        await self.publisher.publish(create_mutation_applied_event(job.organization_id, job.repository_id, job.id, node.target, diff))

                    await step_event("agent.step_completed", "agent", "execution.worker", node,
                                     {"node_id": node.id, "action_type": node.action_type}, f"node-end-{generation}-{node.id}")

                return mutation_events

            # Execute with timeout
            timeout_seconds = min(self.settings.execution_timeout_seconds,
                                  int(plan.context_snapshot.get("bench_budget_seconds", self.settings.execution_timeout_seconds)))
            mutation_events = await asyncio.wait_for(_execute_nodes(), timeout=timeout_seconds)

            locked_job = (
                await self.session.execute(
                    select(ExecutionJobModel).where(ExecutionJobModel.id == job.id)
                    .with_for_update().execution_options(populate_existing=True)
                )
            ).scalar_one()
            if not owns_execution(locked_job, self.owner, generation):
                await self.session.rollback()
                return
            if locked_job.cancellation_requested_at:
                self._cancel_requested = True
                raise asyncio.CancelledError

            job.status = ExecutionStatus.COMPLETED
            job.finished_at = datetime.now(UTC)
            plan.status = PlanStatus.COMPLETED
            for node_id, mutation_id in mutation_events:
                await record_event(self.session, job.organization_id, job.id, "repository.mutation_committed", "agent", "execution.patch_engine",
                                   task_node_id=node_id, data={"mutation_id": mutation_id, "node_id": node_id},
                                   owner=self.owner, generation=generation,
                                   idempotency_key=f"mutation-{generation}-{node_id}")

            await self._log(job.id, job.organization_id, "Execution completed successfully.")

            # Trigger Post-Execution Verification DAG
            try:
                from services.verification.service import VerificationDispatcher
                dispatcher = VerificationDispatcher(self.session, job.organization_id, self.settings)
                await dispatcher.trigger_verification(job.id, commit=False)
                await self._log(job.id, job.organization_id, "Triggered Verification DAG.")
            except Exception as e:
                await self._log(job.id, job.organization_id, f"Warning: Failed to trigger Verification DAG: {str(e)}")

            # Trigger Repository Memory Re-indexing
            try:
                from services.repository_memory.service import MemoryService
                memory_service = MemoryService(self.session, job.organization_id)
                await memory_service.start_indexing(job.repository_id, force_reindex=True, commit=False)
                await self._log(job.id, job.organization_id, "Triggered Repository Memory Re-indexing.")
            except Exception as e:
                await self._log(job.id, job.organization_id, f"Warning: Failed to trigger Memory Re-indexing: {str(e)}")

            await self.publisher.publish(create_execution_completed_event(job.organization_id, job.repository_id, job.id))
            await record_event(self.session, job.organization_id, job.id, "agent.completed", "agent", "execution.worker",
                               data={"generation": generation}, owner=self.owner, generation=generation,
                               idempotency_key=f"agent-completed-{generation}")
            await record_event(self.session, job.organization_id, job.id, "execution.completed", "worker", "execution.worker",
                               data={"generation": generation}, owner=self.owner, generation=generation,
                               idempotency_key=f"completed-{generation}")
            await self.session.commit()

        except TimeoutError:
            await self.session.rollback()  # Discard provisional mutations before recording failure.
            if not await self._still_owned(job_id, generation):
                await self.session.rollback()
                return
            job = (await self.session.execute(select(ExecutionJobModel).where(
                ExecutionJobModel.id == job_id,
            ).execution_options(populate_existing=True))).scalar_one()
            plan = (await self.session.get(PlanModel, job.plan_id))
            assert plan is not None
            if job.cancellation_requested_at:
                self._cancel_requested = True
                await self._finish_cancellation(job, generation)
                return
            job.status = ExecutionStatus.FAILED
            job.finished_at = datetime.now(UTC)
            job.error_message = f"Execution timed out after {timeout_seconds} seconds."
            plan.status = PlanStatus.FAILED
            await self._fail_linked_repair(job, job.error_message or "Execution failed")

            await self._log(job.id, job.organization_id, job.error_message, level="ERROR")
            await self.publisher.publish(create_execution_failed_event(job.organization_id, job.repository_id, job.id, job.error_message or "Execution failed"))
            await record_event(self.session, job.organization_id, job.id, "execution.failed", "worker", "execution.worker",
                               data={"reason_code": "TIMEOUT"}, owner=self.owner, generation=generation,
                               idempotency_key=f"timeout-{generation}")
            await record_event(self.session, job.organization_id, job.id, "agent.failed", "agent", "execution.worker",
                               data={"reason_code": "TIMEOUT"}, owner=self.owner, generation=generation,
                               idempotency_key=f"agent-failed-{generation}")
            await self.session.commit()

        except Exception as e:
            await self.session.rollback()  # A denied later node must not commit an earlier provisional edit.
            if not await self._still_owned(job_id, generation):
                await self.session.rollback()
                return
            job = (await self.session.execute(select(ExecutionJobModel).where(
                ExecutionJobModel.id == job_id,
            ).execution_options(populate_existing=True))).scalar_one()
            plan = (await self.session.get(PlanModel, job.plan_id))
            assert plan is not None
            if job.cancellation_requested_at:
                self._cancel_requested = True
                await self._finish_cancellation(job, generation)
                return
            job.status = ExecutionStatus.FAILED
            job.finished_at = datetime.now(UTC)
            job.error_message = str(e)
            plan.status = PlanStatus.FAILED
            await self._fail_linked_repair(job, job.error_message or "Execution failed")

            await self._log(job.id, job.organization_id, f"Execution failed: {str(e)}", level="ERROR")
            await self.publisher.publish(create_execution_failed_event(job.organization_id, job.repository_id, job.id, str(e)))
            await record_event(self.session, job.organization_id, job.id, "execution.failed", "worker", "execution.worker",
                               data={"reason_code": "EXECUTION_ERROR"}, owner=self.owner, generation=generation,
                               idempotency_key=f"failed-{generation}")
            await record_event(self.session, job.organization_id, job.id, "agent.failed", "agent", "execution.worker",
                               data={"reason_code": "EXECUTION_ERROR"}, owner=self.owner, generation=generation,
                               idempotency_key=f"agent-failed-{generation}")
            await self.session.commit()
        except asyncio.CancelledError:
            if self._cancel_requested and not self._lost_lease:
                await self._finish_cancellation(job, generation)
            else:
                await self.session.rollback()
            if not self._cancel_requested and not self._lost_lease:
                raise
        finally:
            watcher.cancel()
            try:
                await watcher
            except asyncio.CancelledError:
                pass
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

    async def _still_owned(self, job_id: UUID, generation: int, *, lock: bool = True) -> bool:
        query = select(ExecutionJobModel).where(ExecutionJobModel.id == job_id)
        if lock:
            query = query.with_for_update()
        locked = (await self.session.execute(query.execution_options(populate_existing=True))).scalar_one_or_none()
        return bool(locked and owns_execution(locked, self.owner, generation))
