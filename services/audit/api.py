import math
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.audit import AuditLogModel
from packages.shared.identifiers import OrganizationId, RepositoryId
from packages.shared.pagination import PaginatedResponse, PaginationParams
from services.audit.schemas import AuditLogResponse
from services.auth.dependencies import require_permission

router = APIRouter(prefix="/api/v1", tags=["audit"])


@router.get(
    "/organizations/{organization_id}/audit-logs",
    response_model=PaginatedResponse[AuditLogResponse],
)
async def list_organization_audit_logs(
    organization_id: UUID,
    pagination: Annotated[PaginationParams, Depends()],
    action: str | None = Query(None, description="Filter by specific action"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    tenant=Depends(require_permission("workspace:settings:read")),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(AuditLogModel).where(AuditLogModel.organization_id == organization_id)

    if action:
        stmt = stmt.where(AuditLogModel.action == action)
    if resource_type:
        stmt = stmt.where(AuditLogModel.resource_type == resource_type)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = await session.scalar(count_stmt) or 0

    # Get paginated results
    stmt = stmt.order_by(AuditLogModel.timestamp.desc())
    stmt = stmt.offset(pagination.offset).limit(pagination.page_size)

    result = await session.execute(stmt)
    logs = result.scalars().all()

    total_pages = math.ceil(total_count / pagination.page_size) if total_count > 0 else 1

    return PaginatedResponse(
        items=[
            AuditLogResponse(
                id=log.id,
                organization_id=log.organization_id,
                repository_id=log.repository_id,
                actor_id=log.actor_id,
                actor_type=log.actor_type,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                metadata_payload=log.metadata_payload,
                timestamp=log.timestamp,
            )
            for log in logs
        ],
        total=total_count,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=total_pages,
        has_next=pagination.page < total_pages,
        has_previous=pagination.page > 1,
    )


@router.get(
    "/repositories/{repository_id}/audit-logs",
    response_model=PaginatedResponse[AuditLogResponse],
)
async def list_repository_audit_logs(
    repository_id: UUID,
    pagination: Annotated[PaginationParams, Depends()],
    action: str | None = Query(None, description="Filter by specific action"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    tenant=Depends(require_permission("repo:read")),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(AuditLogModel).where(AuditLogModel.repository_id == repository_id)

    if action:
        stmt = stmt.where(AuditLogModel.action == action)
    if resource_type:
        stmt = stmt.where(AuditLogModel.resource_type == resource_type)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = await session.scalar(count_stmt) or 0

    stmt = stmt.order_by(AuditLogModel.timestamp.desc())
    stmt = stmt.offset(pagination.offset).limit(pagination.page_size)

    result = await session.execute(stmt)
    logs = result.scalars().all()

    total_pages = math.ceil(total_count / pagination.page_size) if total_count > 0 else 1

    return PaginatedResponse(
        items=[
            AuditLogResponse(
                id=log.id,
                organization_id=log.organization_id,
                repository_id=log.repository_id,
                actor_id=log.actor_id,
                actor_type=log.actor_type,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                metadata_payload=log.metadata_payload,
                timestamp=log.timestamp,
            )
            for log in logs
        ],
        total=total_count,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=total_pages,
        has_next=pagination.page < total_pages,
        has_previous=pagination.page > 1,
    )
