import json
import re
from pathlib import PurePosixPath
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.planning import TaskEdgeModel, TaskNodeModel
from packages.shared.identifiers import generate_id
from services.context_engine.service import AgentOrchestrator


class AIPlanner:
    """
    A real planner that invokes the AI Context Engine to generate a DAG based on intents.
    """

    def __init__(self, session: AsyncSession, organization_id: UUID, plan_id: UUID):
        self.session = session
        self.organization_id = organization_id
        self.plan_id = plan_id

    async def build_plan(self, repository_id: UUID, intent: str) -> tuple[list[TaskNodeModel], list[TaskEdgeModel]]:
        orchestrator = AgentOrchestrator(self.session, self.organization_id)

        # Override the template in the DB or pass the prompt directly
        # For simplicity, we just pass the prompt directly in the query and use a default template name
        prompt = f"""
You are an autonomous AI software engineer. Your task is to plan the execution of the following intent.
Intent: {intent}

Output a JSON object with 'nodes' and 'edges'.
Nodes have 'id', 'type' ('command' or 'edit_file'), 'target' ('workspace' or file path), and 'parameters'.
Edges have 'from', 'to', and 'condition' ('on_success' or 'on_failure').

CRITICAL RULES:
1. For 'command' nodes, the 'command' parameter MUST be a valid Linux bash shell command (e.g., 'npm install', 'mkdir -p src/components', 'touch file.ts'). DO NOT use imaginary commands like 'create' or 'dark-mode-toggle'.
2. For 'edit_file' nodes, the 'target' MUST be a specific file path, and 'changes' MUST contain the actual code/text to apply.
3. The resulting graph MUST be a Directed Acyclic Graph (DAG). There MUST NOT be any cyclic dependencies. Do NOT create retry loops or backward edges.
4. DO NOT append 'npm run build' or 'npm test' commands as verification steps unless explicitly requested by the user, as the target repository might not have these scripts defined.

Example JSON:
{{
  "nodes": [
    {{"id": "n1", "type": "command", "target": "workspace", "parameters": {{"command": "npm install tailwind-merge"}}}},
    {{"id": "n2", "type": "edit_file", "target": "src/index.ts", "parameters": {{"changes": "export const toggle = () => {{}};"}}}}
  ],
  "edges": [
    {{"from": "n1", "to": "n2", "condition": "on_success"}}
  ]
}}
"""
        # Call the orchestrator
        interaction = await orchestrator.invoke_agent(repository_id, prompt, "planning_template", self.plan_id)

        try:
            plan_data = json.loads(interaction.response_text)
        except json.JSONDecodeError:
            raise ValueError("Model provider returned an invalid plan; retry after reviewing provider settings") from None
        if not isinstance(plan_data, dict) or not isinstance(plan_data.get("nodes"), list) or not plan_data["nodes"]:
            raise ValueError("Model provider returned an empty or invalid plan")
        raw_nodes = plan_data["nodes"]
        raw_edges = plan_data.get("edges", [])
        if len(raw_nodes) > 50 or not isinstance(raw_edges, list) or len(raw_edges) > 100:
            raise ValueError("Model provider returned a plan above the size limit")

        nodes = []
        edges = []
        node_id_map = {}

        for n_data in raw_nodes:
            if not isinstance(n_data, dict) or not isinstance(n_data.get("id"), str) or not n_data["id"] or n_data["id"] in node_id_map:
                raise ValueError("Model provider returned duplicate or invalid plan node IDs")
            action = n_data.get("type")
            target = n_data.get("target")
            parameters = n_data.get("parameters")
            if action not in {"command", "edit_file"} or not isinstance(target, str) or not isinstance(parameters, dict):
                raise ValueError("Model provider returned an unsupported plan action")
            if action == "edit_file":
                path = PurePosixPath(target)
                if (not re.fullmatch(r"[A-Za-z0-9_./-]{1,240}", target) or path.is_absolute()
                    or ".." in path.parts or ".git" in path.parts or path.as_posix() != target
                    or not isinstance(parameters.get("changes"), str)
                    or len(parameters["changes"].encode("utf-8")) > 1024 * 1024):
                    raise ValueError("Model provider returned an unsafe file edit")
            else:
                path = PurePosixPath(target)
                if (target != "workspace" and (
                    not re.fullmatch(r"[A-Za-z0-9_./-]{1,240}", target) or path.is_absolute()
                    or ".." in path.parts or ".git" in path.parts or path.as_posix() != target
                )) or not isinstance(parameters.get("command"), str) or len(parameters["command"]) > 4096:
                    raise ValueError("Model provider returned an invalid command")
            node_id = generate_id()
            node_id_map[n_data["id"]] = node_id
            nodes.append(
                TaskNodeModel(
                    id=node_id,
                    organization_id=self.organization_id,
                    plan_id=self.plan_id,
                    action_type=action,
                    target=target,
                    parameters=parameters,
                )
            )

        import networkx as nx
        dag = nx.DiGraph()
        
        for e_data in raw_edges:
            if not isinstance(e_data, dict) or e_data.get("condition") not in {"on_success", "on_failure"}:
                raise ValueError("Model provider returned an invalid plan edge")
            from_id = node_id_map.get(e_data.get("from"))
            to_id = node_id_map.get(e_data.get("to"))
            if not from_id or not to_id:
                raise ValueError("Model provider returned an edge with a missing node")
            dag.add_edge(from_id, to_id)
            if not nx.is_directed_acyclic_graph(dag):
                raise ValueError("Model provider returned a cyclic plan")
            edges.append(
                TaskEdgeModel(
                    id=generate_id(),
                    organization_id=self.organization_id,
                    plan_id=self.plan_id,
                    from_node_id=from_id,
                    to_node_id=to_id,
                    condition=e_data["condition"],
                )
            )

        return nodes, edges
