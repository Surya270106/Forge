from datetime import UTC, datetime
from secrets import compare_digest
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, WebSocket
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.auth import RoleBindingModel, SessionModel, UserModel
from packages.shared.identifiers import OrganizationId
from services.auth.jwt import decode_access_token


async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)):
    token = request.cookies.get("forge_session")
    if not token:
        # Check Authorization header as fallback for API clients
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return await authenticate_access_token(token, session)


async def authenticate_access_token(token: str, session: AsyncSession) -> dict:
    """Validate a signed token against its active server-side session."""
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    try:
        user_id = UUID(payload["sub"])
        session_id = UUID(payload["session_id"])
        session_token = payload["session_token"]
        if not isinstance(session_token, str) or not session_token:
            raise ValueError("Missing session token")
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid token payload") from None

    stmt = select(SessionModel).where(SessionModel.id == session_id)
    db_session = (await session.execute(stmt)).scalar_one_or_none()
    if not db_session or not db_session.is_active or db_session.user_id != user_id:
        raise HTTPException(status_code=401, detail="Session revoked")
    if not compare_digest(db_session.session_token, session_token):
        raise HTTPException(status_code=401, detail="Invalid session")
    if db_session.expires_at < datetime.now(UTC).replace(tzinfo=None):
        raise HTTPException(status_code=401, detail="Session expired")

    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    return {"id": str(user.id), "email": user.email, "name": user.name,
            "session_token": session_token}


async def require_github_token(user: dict, session: AsyncSession) -> str:
    """Read a GitHub credential only for an operation that actually needs it."""
    from packages.shared.crypto import CryptoService

    db_user = await session.get(UserModel, UUID(user["id"]))
    if not db_user or not db_user.github_token:
        raise HTTPException(status_code=401, detail="Reconnect GitHub to continue")
    try:
        return CryptoService.decrypt(db_user.github_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Reconnect GitHub to continue") from None


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
    request: Request | WebSocket | None,
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

    from packages.database.tenant import set_tenant

    set_tenant(org_uuid)
    # Authentication queries may already have opened this transaction, so the
    # after_begin hook alone cannot set the PostgreSQL RLS value here.
    await session.execute(text("SELECT set_config('forge.organization_id', :organization_id, true)"),
                          {"organization_id": str(org_uuid)})
    stmt = select(RoleBindingModel).where(RoleBindingModel.organization_id == org_uuid, RoleBindingModel.user_id == user["id"])
    result = await session.execute(stmt)
    binding = result.scalar_one_or_none()

    if not binding:
        raise HTTPException(status_code=403, detail="Forbidden: You do not have access to this organization")

    if action:
        from services.auth.permissions import has_permission
        if not has_permission(binding.role, action):
            raise HTTPException(status_code=403, detail=f"Forbidden: Missing permission '{action}'")

    org_id = OrganizationId(org_uuid)
    set_tenant(org_id)
    return org_id
