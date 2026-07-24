from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.verification import VerificationJobModel, VerificationResultModel
from packages.shared.errors import ErrorCategory, NotFoundError
from packages.shared.identifiers import OrganizationId

from .schemas import TriggerVerificationRequest, VerificationJobResponse
from .service import VerificationDispatcher

router = APIRouter(prefix="/api/v1/verifications", tags=["verification"])


from services.auth.dependencies import get_tenant_context as get_tenant_organization_id


@router.post("/executions/{execution_job_id}", response_model=VerificationJobResponse)
async def trigger_verification(
    execution_job_id: UUID,
    request: TriggerVerificationRequest,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_session),
):
    dispatcher = VerificationDispatcher(session, organization_id)
    job = await dispatcher.trigger_verification(execution_job_id)

    # In reality, this would be queued, but we return the pending job
    return job


@router.get("/{job_id}", response_model=VerificationJobResponse)
async def get_verification(
    job_id: UUID,
    organization_id: OrganizationId = Depends(get_tenant_organization_id),
    session: AsyncSession = Depends(get_session),
):
    job = await session.get(VerificationJobModel, job_id)
    if not job or job.organization_id != organization_id:
        raise NotFoundError(
            code="verification_not_found",
            message="Verification job not found",
            category=ErrorCategory.NOT_FOUND,
        )

    stmt = select(VerificationResultModel).where(VerificationResultModel.verification_job_id == job_id)
    results = (await session.execute(stmt)).scalars().all()

    job_dict = job.__dict__.copy()
    job_dict["results"] = results
    return job_dict
