import asyncio
import os
import subprocess
from datetime import UTC, datetime
from uuid import UUID

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

from .events import (
    ExecutionEventPublisher,
    create_execution_completed_event,
    create_execution_failed_event,
    create_execution_started_event,
    create_mutation_applied_event,
)
from .patch_engine import PatchEngine
from .sandbox import SandboxRuntime

logger = structlog.get_logger(__name__)


class ExecutionWorker:
    def __init__(self, session: AsyncSession, sandbox: SandboxRuntime, settings=None):
        self.session = session
        self.sandbox = sandbox
        self.settings = settings or get_settings()
        self.publisher = ExecutionEventPublisher(session)

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
        if not plan or not repo or plan.organization_id != job.organization_id or repo.organization_id != job.organization_id or plan.status != PlanStatus.APPROVED:
            job.status = ExecutionStatus.FAILED
            job.finished_at = datetime.now(UTC)
            job.error_message = "Approved plan or repository is unavailable for this execution."
            await self._fail_linked_repair(job, job.error_message or "Execution failed")
            await self.publisher.publish(create_execution_failed_event(job.organization_id, job.repository_id, job.id, job.error_message or "Execution failed"))
            await self.session.commit()
            return

        workspace_dir = os.path.join(self.settings.workspace_root, str(job.organization_id), str(job.repository_id))
        try:
            revision = subprocess.run(
                ["git", "-C", workspace_dir, "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10, check=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            revision = None
        if not revision or revision != job.commit_sha_before or revision != repo.commit_sha:
            job.status = ExecutionStatus.FAILED
            job.finished_at = datetime.now(UTC)
            job.error_message = "Repository workspace base changed or is unavailable."
            await self._fail_linked_repair(job, job.error_message or "Execution failed")
            await self.publisher.publish(create_execution_failed_event(job.organization_id, job.repository_id, job.id, job.error_message or "Execution failed"))
            await self.session.commit()
            return

        job.status = ExecutionStatus.RUNNING
        job.started_at = datetime.now(UTC)
        plan.status = PlanStatus.EXECUTING
        await self.publisher.publish(create_execution_started_event(job.organization_id, job.repository_id, job.id, plan.id))
        await self.session.commit()

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
            job.status = ExecutionStatus.FAILED
            job.error_message = "Plan contains cyclic dependencies."
            plan.status = PlanStatus.FAILED
            job.finished_at = datetime.now(UTC)
            await self._fail_linked_repair(job, job.error_message or "Execution failed")
            await self._log(job.id, job.organization_id, job.error_message, level="ERROR")
            await self.publisher.publish(create_execution_failed_event(job.organization_id, job.repository_id, job.id, job.error_message or "Execution failed"))
            await self.session.commit()
            return

        try:
            async def _execute_nodes():
                for node_id in nx.topological_sort(dag):
                    node: TaskNodeModel = dag.nodes[node_id]["data"]
                    await self._log(
                        job.id,
                        job.organization_id,
                        f"Executing task {node.action_type} on {node.target}",
                        node_id=node.id,
                    )

                    if node.action_type == "command":
                        cmd_str = node.parameters.get("command", "")

                        # Normalize target to absolute container path
                        target = node.target if node.target and node.target != "workspace" else ""
                        container_cwd = "/workspace"
                        if target:
                            container_cwd = f"/workspace/{target}"

                        # Using Sandbox
                        result = await self.sandbox.run_command(["sh", "-c", cmd_str], cwd=container_cwd)

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

                    elif node.action_type == "edit_file":
                        new_content = node.parameters.get("changes", "")
                        if isinstance(new_content, (dict, list)):
                            import json
                            new_content = json.dumps(new_content, indent=2)
                        elif not isinstance(new_content, str):
                            new_content = str(new_content)
                        diff = patch_engine.apply_patch(node.target, new_content)

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
                        await self._log(
                            job.id,
                            job.organization_id,
                            f"Applied patch to {node.target}",
                            node_id=node.id,
                        )
                        await self.publisher.publish(create_mutation_applied_event(job.organization_id, job.repository_id, job.id, node.target, diff))

                    await self.session.flush()

            # Execute with timeout
            await asyncio.wait_for(_execute_nodes(), timeout=self.settings.execution_timeout_seconds)

            locked_job = (
                await self.session.execute(
                    select(ExecutionJobModel).where(ExecutionJobModel.id == job.id)
                    .with_for_update().execution_options(populate_existing=True)
                )
            ).scalar_one()
            if locked_job.status != ExecutionStatus.RUNNING:
                raise RuntimeError("Execution was interrupted before completion")

            job.status = ExecutionStatus.COMPLETED
            job.finished_at = datetime.now(UTC)
            plan.status = PlanStatus.COMPLETED

            await self._log(job.id, job.organization_id, "Execution completed successfully.")

            # Trigger Post-Execution Verification DAG
            try:
                from services.verification.service import VerificationDispatcher
                dispatcher = VerificationDispatcher(self.session, job.organization_id, self.settings)
                await dispatcher.trigger_verification(job.id)
                await self._log(job.id, job.organization_id, "Triggered Verification DAG.")
            except Exception as e:
                await self._log(job.id, job.organization_id, f"Warning: Failed to trigger Verification DAG: {str(e)}")

            # Trigger Repository Memory Re-indexing
            try:
                from services.repository_memory.service import MemoryService
                memory_service = MemoryService(self.session, job.organization_id)
                await memory_service.start_indexing(job.repository_id, force_reindex=True)
                await self._log(job.id, job.organization_id, "Triggered Repository Memory Re-indexing.")
            except Exception as e:
                await self._log(job.id, job.organization_id, f"Warning: Failed to trigger Memory Re-indexing: {str(e)}")

            await self.publisher.publish(create_execution_completed_event(job.organization_id, job.repository_id, job.id))
            await self.session.commit()

        except TimeoutError:
            job.status = ExecutionStatus.FAILED
            job.finished_at = datetime.now(UTC)
            job.error_message = f"Execution timed out after {self.settings.execution_timeout_seconds} seconds."
            plan.status = PlanStatus.FAILED
            await self._fail_linked_repair(job, job.error_message or "Execution failed")

            await self._log(job.id, job.organization_id, job.error_message, level="ERROR")
            await self.publisher.publish(create_execution_failed_event(job.organization_id, job.repository_id, job.id, job.error_message or "Execution failed"))
            await self.session.commit()

        except Exception as e:
            job.status = ExecutionStatus.FAILED
            job.finished_at = datetime.now(UTC)
            job.error_message = str(e)
            plan.status = PlanStatus.FAILED
            await self._fail_linked_repair(job, job.error_message or "Execution failed")

            await self._log(job.id, job.organization_id, f"Execution failed: {str(e)}", level="ERROR")
            await self.publisher.publish(create_execution_failed_event(job.organization_id, job.repository_id, job.id, str(e)))
            await self.session.commit()
