from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.shared.identifiers import OrganizationId
from services.auth.dependencies import get_tenant_context as get_tenant_organization_id

from .schemas import AcceptPatchRequest, PatchResponse, RejectPatchRequest
from .service import PatchService

router = APIRouter(prefix="/api/v1/patches", tags=["patch"])


@router.post("/executions/{execution_job_id}/generate", response_model=PatchResponse)
async def generate_patch(
    execution_job_id: UUID,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_session),
):
    service = PatchService(session, organization_id)
    return await service.generate_patch(execution_job_id)


@router.post("/{patch_id}/accept", response_model=PatchResponse)
async def accept_patch(
    patch_id: UUID,
    request: AcceptPatchRequest,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_session),
):
    service = PatchService(session, organization_id)
    return await service.accept_patch(patch_id)


@router.post("/{patch_id}/reject", response_model=PatchResponse)
async def reject_patch(
    patch_id: UUID,
    request: RejectPatchRequest,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_session),
):
    service = PatchService(session, organization_id)
    return await service.reject_patch(patch_id)
