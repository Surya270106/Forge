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
                    # Using Sandbox
                    result = await self.sandbox.run_command(cmd_str.split(), cwd=node.target)

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
                        raise RuntimeError(f"Command failed with exit code {result.exit_code}")

                elif node.action_type == "edit_file":
                    new_content = node.parameters.get("changes", "")
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

            job.status = ExecutionStatus.COMPLETED
            job.finished_at = datetime.now(UTC)
            plan.status = PlanStatus.COMPLETED

            await self._log(job.id, job.organization_id, "Execution completed successfully.")
            await self.publisher.publish(create_execution_completed_event(job.organization_id, job.repository_id, job.id))
            await self.session.commit()

        except Exception as e:
            job.status = ExecutionStatus.FAILED
            job.finished_at = datetime.now(UTC)
            job.error_message = str(e)
            plan.status = PlanStatus.FAILED

            await self._log(job.id, job.organization_id, f"Execution failed: {str(e)}", level="ERROR")
            await self.publisher.publish(create_execution_failed_event(job.organization_id, job.repository_id, job.id, str(e)))
            await self.session.commit()
