import json
from typing import Any
from uuid import UUID

from packages.database.models.planning import TaskEdgeModel, TaskNodeModel
from packages.shared.identifiers import generate_id
from services.context_engine.service import AgentOrchestrator
from sqlalchemy.ext.asyncio import AsyncSession


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
Nodes have 'id', 'type' (e.g. 'command', 'edit_file', 'verify'), 'target' (e.g. 'workspace' or file path), and 'parameters'.
Edges have 'from', 'to', and 'condition' (e.g. 'on_success').

Example JSON:
{{
  "nodes": [
    {{"id": "n1", "type": "command", "target": "workspace", "parameters": {{"command": "npm install"}}}},
    {{"id": "n2", "type": "edit_file", "target": "src/index.ts", "parameters": {{"changes": "Fix bug"}}}}
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
                "edges": []
            }

        nodes = []
        edges = []
        node_id_map = {}

        for n_data in plan_data.get("nodes", []):
            node_id = generate_id()
            node_id_map[n_data.get("id")] = node_id
            nodes.append(TaskNodeModel(
                id=node_id,
                organization_id=self.organization_id,
                plan_id=self.plan_id,
                action_type=n_data.get("type", "unknown"),
                target=n_data.get("target", "workspace"),
                parameters=n_data.get("parameters", {}),
            ))

        for e_data in plan_data.get("edges", []):
            from_id = node_id_map.get(e_data.get("from"))
            to_id = node_id_map.get(e_data.get("to"))
            if from_id and to_id:
                edges.append(TaskEdgeModel(
                    id=generate_id(),
                    organization_id=self.organization_id,
                    plan_id=self.plan_id,
                    from_node_id=from_id,
                    to_node_id=to_id,
                    condition=e_data.get("condition", "on_success"),
                ))

        return nodes, edges
