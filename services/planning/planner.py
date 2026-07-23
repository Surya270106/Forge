import re
from typing import Any
from uuid import UUID

from packages.database.models.planning import TaskEdgeModel, TaskNodeModel
from packages.shared.identifiers import generate_id


class PlannerHeuristic:
    """
    A heuristic planner that generates a DAG based on intents until the AI Context Engine (RFC-006) is available.
    """

    def __init__(self, organization_id: UUID, plan_id: UUID):
        self.organization_id = organization_id
        self.plan_id = plan_id

    def build_plan(self, intent: str) -> tuple[list[TaskNodeModel], list[TaskEdgeModel]]:
        nodes = []
        edges = []

        intent_lower = intent.lower()

        # Step 1: Tool Selection and Risk Analysis (Mocked via heuristics)
        if "install" in intent_lower or "dependency" in intent_lower:
            cmd = "npm install" if "npm" in intent_lower else "uv pip install"
            install_node = self._create_node("command", "workspace", {"command": cmd})
            nodes.append(install_node)

        # Step 2: Source code modifications
        if "implement" in intent_lower or "update" in intent_lower or "edit" in intent_lower:
            # Extract basic file paths if present
            files_to_edit = re.findall(r"([a-zA-Z0-9_\-\./]+\.(?:ts|js|py|md))", intent)
            if not files_to_edit:
                files_to_edit = ["src/index.ts"]  # Fallback

            edit_nodes = []
            for file in files_to_edit:
                node = self._create_node("edit_file", file, {"changes": f"Apply intent: {intent[:50]}..."})
                nodes.append(node)
                edit_nodes.append(node)

            # Link install -> edits
            install_node = next((n for n in nodes if n.action_type == "command"), None)
            if install_node:
                for en in edit_nodes:
                    edges.append(self._create_edge(install_node.id, en.id, "on_success"))

        # Step 3: Verification Planning
        verify_node = self._create_node("verify", "workspace", {"strategy": "lint_and_test"})
        nodes.append(verify_node)

        # Link all edits -> verify
        edit_nodes = [n for n in nodes if n.action_type == "edit_file"]
        if not edit_nodes:
            # Link install -> verify
            install_node = next((n for n in nodes if n.action_type == "command"), None)
            if install_node:
                edges.append(self._create_edge(install_node.id, verify_node.id, "on_success"))
        else:
            for en in edit_nodes:
                edges.append(self._create_edge(en.id, verify_node.id, "on_success"))

        # If no nodes were added, add a fallback
        if not nodes:
            fallback = self._create_node("review", "workspace", {"reason": "Could not determine actions from intent"})
            nodes.append(fallback)

        return nodes, edges

    def _create_node(self, action_type: str, target: str, parameters: dict[str, Any]) -> TaskNodeModel:
        return TaskNodeModel(
            id=generate_id(),
            organization_id=self.organization_id,
            plan_id=self.plan_id,
            action_type=action_type,
            target=target,
            parameters=parameters,
        )

    def _create_edge(self, from_id: UUID, to_id: UUID, condition: str) -> TaskEdgeModel:
        return TaskEdgeModel(
            id=generate_id(),
            organization_id=self.organization_id,
            plan_id=self.plan_id,
            from_node_id=from_id,
            to_node_id=to_id,
            condition=condition,
        )
