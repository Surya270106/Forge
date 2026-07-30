from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.context import AgentInteractionModel, ContextSnapshotModel
from packages.shared.errors import ErrorCategory, NotFoundError
from packages.shared.identifiers import OrganizationId

from .schemas import AgentInteractionResponse, ContextSnapshotResponse

router = APIRouter(prefix="/api/v1/context", tags=["context"])


async def get_tenant_organization_id() -> OrganizationId:
    return OrganizationId(UUID("00000000-0000-0000-0000-000000000000"))


@router.get("/snapshots/{snapshot_id}", response_model=ContextSnapshotResponse)
async def get_snapshot(
    snapshot_id: UUID,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_session),
):
    snapshot = await session.get(ContextSnapshotModel, snapshot_id)
    if not snapshot or snapshot.organization_id != organization_id:
        raise NotFoundError(code="snapshot_not_found", message="Context snapshot not found", category=ErrorCategory.NOT_FOUND)  # type: ignore
    return snapshot


@router.get("/interactions/{interaction_id}", response_model=AgentInteractionResponse)
async def get_interaction(
    interaction_id: UUID,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_session),
):
    interaction = await session.get(AgentInteractionModel, interaction_id)
    if not interaction or interaction.organization_id != organization_id:
        raise NotFoundError(
            code="interaction_not_found",
            message="Agent interaction not found",
            category=ErrorCategory.NOT_FOUND,
        )
    return interaction
