from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.auth import RoleBindingModel, UserModel
from packages.shared.identifiers import OrganizationId
from services.auth.jwt import decode_access_token


async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    token = request.cookies.get("forge_session")

    if not token:
        # Fallback for programmatic API access
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")

    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    from packages.shared.crypto import CryptoService
    decrypted_github_token = CryptoService.decrypt(user.github_token) if user.github_token else None

    return {"id": str(user.id), "email": user.email, "name": user.name, "github_token": decrypted_github_token}


async def get_tenant_context(
    request: Request,
    x_organization_id: str | None = Header(None, alias="X-Organization-Id"),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OrganizationId:
    # This is a base dependency used directly if no specific permission is required.
    # It acts exactly like a viewer role check for the organization.
    return await _verify_and_set_tenant(request, x_organization_id, user, session, None)

def require_permission(action: str):
    async def permission_checker(
        request: Request,
        x_organization_id: str | None = Header(None, alias="X-Organization-Id"),
        user: dict = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> OrganizationId:
        return await _verify_and_set_tenant(request, x_organization_id, user, session, action)
    return permission_checker

async def _verify_and_set_tenant(
    request: Request,
    x_organization_id: str | None,
    user: dict,
    session: AsyncSession,
    action: str | None,
) -> OrganizationId:
    if not x_organization_id:
        raise HTTPException(status_code=400, detail="Missing X-Organization-Id header")

    try:
        org_uuid = UUID(x_organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid X-Organization-Id format")

    stmt = select(RoleBindingModel).where(RoleBindingModel.organization_id == org_uuid, RoleBindingModel.user_id == user["id"])
    result = await session.execute(stmt)
    binding = result.scalar_one_or_none()

    if not binding:
        raise HTTPException(status_code=403, detail="Forbidden: You do not have access to this organization")

    if action:
        from services.auth.permissions import has_permission
        if not has_permission(binding.role, action):
            raise HTTPException(status_code=403, detail=f"Forbidden: Missing permission '{action}'")

    from packages.database.tenant import set_tenant
    org_id = OrganizationId(org_uuid)
    set_tenant(org_id)
    return org_id
