import json
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
Nodes have 'id', 'type' ('command', 'edit_file', or 'verify'), 'target' ('workspace' or file path), and 'parameters'.
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
            # Fallback if AI didn't return valid JSON
            plan_data = {
                "nodes": [{"id": "fallback", "type": "command", "target": "workspace", "parameters": {"command": "echo 'Invalid JSON from AI'"}}],
                "edges": [],
            }

        nodes = []
        edges = []
        node_id_map = {}

        for n_data in plan_data.get("nodes", []):
            node_id = generate_id()
            node_id_map[n_data.get("id")] = node_id
            nodes.append(
                TaskNodeModel(
                    id=node_id,
                    organization_id=self.organization_id,
                    plan_id=self.plan_id,
                    action_type=n_data.get("type", "unknown"),
                    target=n_data.get("target", "workspace"),
                    parameters=n_data.get("parameters", {}),
                )
            )

        import networkx as nx
        dag = nx.DiGraph()
        
        for e_data in plan_data.get("edges", []):
            from_id = node_id_map.get(e_data.get("from"))
            to_id = node_id_map.get(e_data.get("to"))
            if from_id and to_id:
                dag.add_edge(from_id, to_id)
                try:
                    nx.find_cycle(dag)
                    # cycle found, reject this edge
                    dag.remove_edge(from_id, to_id)
                except nx.NetworkXNoCycle:
                    edges.append(
                        TaskEdgeModel(
                            id=generate_id(),
                            organization_id=self.organization_id,
                            plan_id=self.plan_id,
                            from_node_id=from_id,
                            to_node_id=to_id,
                            condition=e_data.get("condition", "on_success"),
                        )
                    )

        return nodes, edges
