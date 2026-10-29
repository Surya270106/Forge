from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.shared.identifiers import OrganizationId
from services.auth.dependencies import get_current_user, require_github_token, require_permission

from .schemas import AcceptPatchRequest, PatchResponse, RejectPatchRequest, RevisePatchRequest
from .service import PatchService

router = APIRouter(prefix="/api/v1/patches", tags=["patch"])


@router.post("/executions/{execution_job_id}/generate", response_model=PatchResponse)
async def generate_patch(
    execution_job_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("patch:approve")),
    session: AsyncSession = Depends(get_session),
):
    service = PatchService(session, organization_id)
    return await service.generate_patch(execution_job_id)


@router.get("/executions/{execution_job_id}", response_model=PatchResponse)
async def get_patch_for_execution(
    execution_job_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("patch:read")),
    session: AsyncSession = Depends(get_session),
):
    from packages.database.models.patch import PatchModel
    from packages.shared.errors import ErrorCategory, NotFoundError

    patch = (
        await session.execute(
            select(PatchModel)
            .where(
                PatchModel.execution_job_id == execution_job_id,
                PatchModel.organization_id == organization_id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if not patch:
        raise NotFoundError("patch_not_found", "Patch not found", ErrorCategory.NOT_FOUND)
    return patch


@router.post("/{patch_id}/accept", response_model=PatchResponse)
async def accept_patch(
    patch_id: UUID,
    request: AcceptPatchRequest,
    organization_id: OrganizationId = Depends(require_permission("patch:approve")),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = PatchService(session, organization_id)
    return await service.accept_patch(patch_id, request.review_digest, UUID(user["id"]))


@router.get("/{patch_id}/review")
async def review_patch(
    patch_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("patch:read")),
    session: AsyncSession = Depends(get_session),
):
    return await PatchService(session, organization_id).review_patch(patch_id)


@router.get("/{patch_id}", response_model=PatchResponse)
async def get_patch(
    patch_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("patch:read")),
    session: AsyncSession = Depends(get_session),
):
    from packages.database.models.patch import PatchModel
    from packages.shared.errors import ErrorCategory, NotFoundError

    patch = await session.get(PatchModel, patch_id)
    if not patch or patch.organization_id != organization_id:
        raise NotFoundError("patch_not_found", "Patch not found", ErrorCategory.NOT_FOUND)
    return patch


@router.post("/{patch_id}/publish", response_model=PatchResponse)
async def publish_patch(
    patch_id: UUID,
    organization_id: OrganizationId = Depends(require_permission("patch:approve")),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await require_github_token(user, session)
    return await PatchService(session, organization_id).request_publish(patch_id, UUID(user["id"]))


@router.post("/{patch_id}/reject", response_model=PatchResponse)
async def reject_patch(
    patch_id: UUID,
    request: RejectPatchRequest,
    organization_id: OrganizationId = Depends(require_permission("patch:reject")),
    session: AsyncSession = Depends(get_session),
):
    service = PatchService(session, organization_id)
    return await service.reject_patch(patch_id)


@router.post("/{patch_id}/revise", response_model=PatchResponse)
async def revise_patch(
    patch_id: UUID,
    request: RevisePatchRequest,
    organization_id: OrganizationId = Depends(require_permission("patch:reject")),
    session: AsyncSession = Depends(get_session),
):
    service = PatchService(session, organization_id)
    return await service.revise_patch(patch_id, request.feedback)
