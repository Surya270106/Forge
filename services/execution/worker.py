import asyncio
import os
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
            import redis.asyncio as redis_async
            import json
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
        job = await self.session.get(ExecutionJobModel, job_id)
        if not job or job.status != ExecutionStatus.PENDING:
            return

        plan = await self.session.get(PlanModel, job.plan_id)
        repo = await self.session.get(RepositoryModel, job.repository_id)
        if not plan or not repo:
            return

        job.status = ExecutionStatus.RUNNING
        job.started_at = datetime.now(UTC)
        plan.status = PlanStatus.EXECUTING
        await self.publisher.publish(create_execution_started_event(job.organization_id, job.repository_id, job.id, plan.id))
        await self.session.commit()

        await self._log(job.id, job.organization_id, f"Execution {job.id} started.")

        workspace_dir = os.path.join(self.settings.workspace_root, str(job.organization_id), str(job.repository_id))
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
            await self._log(job.id, job.organization_id, job.error_message, level="ERROR")
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
                            # Trigger Verification & Repair loop
                            from packages.database.models.verification import VerificationJobModel, VerificationResultModel, VerificationStatus
                            from services.verification.service import VerificationDispatcher
                            
                            v_job = VerificationJobModel(
                                id=generate_id(),
                                organization_id=job.organization_id,
                                repository_id=job.repository_id,
                                execution_job_id=job.id,
                                started_at=datetime.now(UTC),
                                finished_at=datetime.now(UTC)
                            )
                            self.session.add(v_job)
                            
                            v_res = VerificationResultModel(
                                id=generate_id(),
                                organization_id=job.organization_id,
                                verification_job_id=v_job.id,
                                execution_id=job.id,
                                verifier="command_execution",
                                status=VerificationStatus.FAILED,
                                exit_code=result.exit_code,
                                stdout=result.stdout[:50000] if result.stdout else "",
                                stderr=result.stderr[:50000] if result.stderr else "",
                                diagnostics=[{"severity": "error", "message": f"Command {cmd_str} failed"}],
                            )
                            self.session.add(v_res)
                            await self.session.flush()
                            
                            dispatcher = VerificationDispatcher(self.session, job.organization_id, self.settings)
                            await dispatcher._trigger_repair(v_job)
                            
                            raise RuntimeError(f"Command failed with exit code {result.exit_code}. Repair attempt triggered.")

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

            job.status = ExecutionStatus.COMPLETED
            job.finished_at = datetime.now(UTC)
            plan.status = PlanStatus.COMPLETED

            await self._log(job.id, job.organization_id, "Execution completed successfully.")

            # Attempt to commit and push changes to GitHub
            try:
                await self._commit_and_push_to_github(job)
            except Exception as e:
                await self._log(job.id, job.organization_id, f"Warning: Failed to push to GitHub: {str(e)}")

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
            
        except asyncio.TimeoutError:
            job.status = ExecutionStatus.FAILED
            job.finished_at = datetime.now(UTC)
            job.error_message = f"Execution timed out after {self.settings.execution_timeout_seconds} seconds."
            plan.status = PlanStatus.FAILED

            await self._log(job.id, job.organization_id, job.error_message, level="ERROR")
            await self.publisher.publish(create_execution_failed_event(job.organization_id, job.repository_id, job.id, job.error_message))
            await self.session.commit()

        except Exception as e:
            job.status = ExecutionStatus.FAILED
            job.finished_at = datetime.now(UTC)
            job.error_message = str(e)
            plan.status = PlanStatus.FAILED

            await self._log(job.id, job.organization_id, f"Execution failed: {str(e)}", level="ERROR")
            await self.publisher.publish(create_execution_failed_event(job.organization_id, job.repository_id, job.id, str(e)))
            await self.session.commit()

    async def _commit_and_push_to_github(self, job: ExecutionJobModel) -> None:
        from packages.database.models.auth import RoleBindingModel, UserModel
        from packages.database.models.repository import RepositoryModel
        from sqlalchemy import select

        # Find owner token
        stmt = select(UserModel).join(RoleBindingModel).where(
            RoleBindingModel.organization_id == job.organization_id,
            RoleBindingModel.role == "OWNER",
            UserModel.github_token.is_not(None)
        )
        owner = (await self.session.execute(stmt)).scalars().first()
        if not owner or not owner.github_token:
            raise ValueError("No GitHub token found for organization owner")

        repo = await self.session.get(RepositoryModel, job.repository_id)
        if not repo:
            raise ValueError("Repository not found")

        # Format URL for push
        clone_url = repo.clone_url
        if clone_url.startswith("https://"):
            from packages.shared.crypto import CryptoService
            decrypted_token = CryptoService.decrypt(owner.github_token)
            auth_url = f"https://x-access-token:{decrypted_token}@{clone_url[8:]}"
        else:
            auth_url = clone_url

        workspace_path = f"{self.settings.workspace_root}/{job.organization_id}/{job.repository_id}"

        import asyncio

        async def run_git(cmd: list[str]) -> None:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"Git command {' '.join(cmd)} failed: {stderr.decode()}")
            await self._log(job.id, job.organization_id, f"Git {' '.join(cmd)}: {stdout.decode()}")

        await run_git(["git", "config", "user.name", "Forge AI"])
        await run_git(["git", "config", "user.email", "bot@forge.ai"])
        await run_git(["git", "add", "."])
        
        # Check if there are changes to commit
        proc = await asyncio.create_subprocess_exec(
            "git", "status", "--porcelain",
            cwd=workspace_path,
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if not stdout.strip():
            await self._log(job.id, job.organization_id, "No changes to commit.")
            return

        await run_git(["git", "commit", "-m", f"Forge AI: Execution {job.id}"])
        await run_git(["git", "push", auth_url, repo.default_branch])
        await self._log(job.id, job.organization_id, f"Successfully pushed changes to {repo.full_name}")
