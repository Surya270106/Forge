from uuid import UUID
from fastapi import Request, Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.auth import UserModel, RoleBindingModel, OrganizationModel
from packages.shared.identifiers import OrganizationId
from services.auth.jwt import decode_access_token

async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    user_id = payload.get("sub")
    
    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")
        
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "github_token": user.github_token
    }

async def get_tenant_context(
    request: Request,
    x_organization_id: str | None = Header(None, alias="X-Organization-Id"),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> OrganizationId:
    if not x_organization_id:
        raise HTTPException(status_code=400, detail="Missing X-Organization-Id header")
        
    try:
        org_uuid = UUID(x_organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid X-Organization-Id format")
        
    # Verify user has access to this organization
    stmt = select(RoleBindingModel).where(
        RoleBindingModel.organization_id == org_uuid,
        RoleBindingModel.user_id == user["id"]
    )
    result = await session.execute(stmt)
    binding = result.scalar_one_or_none()
    
    if not binding:
        raise HTTPException(status_code=403, detail="Forbidden: You do not have access to this organization")
        
    from packages.database.tenant import set_tenant
    org_id = OrganizationId(org_uuid)
    set_tenant(org_id)
    
    return org_id
