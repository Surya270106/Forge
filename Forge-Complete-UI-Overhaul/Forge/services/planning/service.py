from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from packages.database.models.memory import RepositoryMemoryVersionModel
from packages.database.models.planning import PlanModel, PlanStatus
from packages.database.models.repository import RepositoryModel
from packages.shared.errors import ConflictError, ErrorCategory, NotFoundError
from packages.shared.identifiers import generate_id

from .events import (
    PlanningEventPublisher,
    create_plan_approved_event,
    create_plan_created_event,
    create_plan_rejected_event,
)

logger = structlog.get_logger(__name__)


class PlanningService:
    def __init__(self, session: AsyncSession, organization_id: UUID):
        self.session = session
        self.organization_id = organization_id
        self.publisher = PlanningEventPublisher(session)

    async def create_plan(self, repository_id: UUID, intent: str, memory_version_id: UUID | None = None) -> PlanModel:
        repo = await self.session.get(RepositoryModel, repository_id)
        if not repo or repo.organization_id != self.organization_id:
            raise NotFoundError(code="repo_not_found", message="Repository not found", category=ErrorCategory.NOT_FOUND)

        # Validate memory version if provided, otherwise pick active
        if memory_version_id:
            mem_ver = await self.session.get(RepositoryMemoryVersionModel, memory_version_id)
            if not mem_ver or mem_ver.repository_id != repository_id or mem_ver.organization_id != self.organization_id:
                raise NotFoundError(
                    code="memory_not_found",
                    message="Memory version not found",
                    category=ErrorCategory.NOT_FOUND,
                )
        else:
            stmt = select(RepositoryMemoryVersionModel).where(
                RepositoryMemoryVersionModel.repository_id == repository_id,
                RepositoryMemoryVersionModel.is_active,
            )
            mem_ver = (await self.session.execute(stmt)).scalars().first()
            if mem_ver:
                memory_version_id = mem_ver.id

        # 1. Draft the Plan
        plan = PlanModel(
            id=generate_id(),
            organization_id=self.organization_id,
            repository_id=repository_id,
            memory_version_id=memory_version_id,
            status=PlanStatus.DRAFT,
            intent=intent,
            context_snapshot={},
        )
        self.session.add(plan)
        await self.session.flush()

        # 2. Invoke AI Context Engine
        from .planner import AIPlanner

        planner = AIPlanner(self.session, self.organization_id, plan.id)
        nodes, edges = await planner.build_plan(repository_id, intent)
        self.session.add_all(nodes)
        self.session.add_all(edges)
        await self.session.flush()

        # 3. Finalize plan creation
        plan.status = PlanStatus.PENDING_APPROVAL

        await self.publisher.publish(create_plan_created_event(self.organization_id, repository_id, plan.id))
        await self.session.commit()

        # Reload with relations
        stmt_reload = select(PlanModel).options(selectinload(PlanModel.nodes)).where(PlanModel.id == plan.id)

        return (await self.session.execute(stmt_reload)).scalars().first()  # type: ignore

    async def get_plan(self, plan_id: UUID) -> PlanModel:
        stmt = (
            select(PlanModel).options(selectinload(PlanModel.nodes)).where(PlanModel.id == plan_id, PlanModel.organization_id == self.organization_id)
        )
        plan = (await self.session.execute(stmt)).scalars().first()
        if not plan:
            raise NotFoundError(code="plan_not_found", message="Plan not found", category=ErrorCategory.NOT_FOUND)
        return plan

    async def approve_plan(self, plan_id: UUID) -> PlanModel:
        plan = await self.get_plan(plan_id)
        if plan.status != PlanStatus.PENDING_APPROVAL:
            raise ConflictError(
                code="invalid_plan_state",
                message=f"Cannot approve plan in state {plan.status.value}",
                category=ErrorCategory.CONFLICT,
            )

        plan.status = PlanStatus.APPROVED
        await self.publisher.publish(create_plan_approved_event(self.organization_id, plan.repository_id, plan.id))
        await self.session.commit()
        return plan

    async def reject_plan(self, plan_id: UUID, reason: str) -> PlanModel:
        plan = await self.get_plan(plan_id)
        if plan.status != PlanStatus.PENDING_APPROVAL:
            raise ConflictError(
                code="invalid_plan_state",
                message=f"Cannot reject plan in state {plan.status.value}",
                category=ErrorCategory.CONFLICT,
            )

        plan.status = PlanStatus.REJECTED
        await self.publisher.publish(create_plan_rejected_event(self.organization_id, plan.repository_id, plan.id, reason))
        await self.session.commit()
        return plan

    async def revise_plan(self, plan_id: UUID, feedback: str, memory_version_id: UUID | None = None) -> PlanModel:
        old_plan = await self.get_plan(plan_id)
        if old_plan.status not in (PlanStatus.PENDING_APPROVAL, PlanStatus.DRAFT):
            raise ConflictError(
                code="invalid_plan_state",
                message=f"Cannot revise plan in state {old_plan.status.value}",
                category=ErrorCategory.CONFLICT,
            )

        old_plan.status = PlanStatus.SUPERSEDED

        mem_id = memory_version_id or old_plan.memory_version_id

        new_plan = PlanModel(
            id=generate_id(),
            organization_id=self.organization_id,
            repository_id=old_plan.repository_id,
            memory_version_id=mem_id,
            status=PlanStatus.DRAFT,
            intent=old_plan.intent,
            parent_plan_id=old_plan.id,
            feedback=feedback,
            context_snapshot={},
        )
        self.session.add(new_plan)
        await self.session.flush()

        from .planner import AIPlanner

        combined_intent = f"Original Intent: {old_plan.intent}\nUser Feedback to Revise: {feedback}"
        planner = AIPlanner(self.session, self.organization_id, new_plan.id)
        nodes, edges = await planner.build_plan(old_plan.repository_id, combined_intent)
        self.session.add_all(nodes)
        self.session.add_all(edges)
        await self.session.flush()

        new_plan.status = PlanStatus.PENDING_APPROVAL

        await self.publisher.publish(create_plan_created_event(self.organization_id, old_plan.repository_id, new_plan.id))
        await self.session.commit()

        stmt_reload = select(PlanModel).options(selectinload(PlanModel.nodes)).where(PlanModel.id == new_plan.id)
        return (await self.session.execute(stmt_reload)).scalars().first()  # type: ignore
