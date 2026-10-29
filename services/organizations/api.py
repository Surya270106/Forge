from datetime import datetime, timedelta, timezone
from uuid import UUID
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.auth import OrganizationModel, RoleBindingModel, InvitationModel, UserModel
from packages.shared.identifiers import generate_id, OrganizationId
from services.auth.dependencies import get_current_user, require_permission, get_tenant_context

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])

class CreateWorkspaceRequest(BaseModel):
    name: str

class RenameWorkspaceRequest(BaseModel):
    name: str

class InviteMemberRequest(BaseModel):
    email: str
    role: str

class ChangeRoleRequest(BaseModel):
    role: str

class TransferOwnershipRequest(BaseModel):
    new_owner_id: str

@router.post("")
async def create_workspace(request: CreateWorkspaceRequest, user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    org = OrganizationModel(
        id=generate_id(),
        name=request.name,
        billing_plan="FREE",
        is_active=True
    )
    session.add(org)

    binding = RoleBindingModel(
        id=generate_id(),
        organization_id=org.id,
        user_id=UUID(user["id"]),
        role="OWNER"
    )
    session.add(binding)
    
    await session.commit()
    return {"id": str(org.id), "name": org.name, "role": "OWNER"}


@router.get("")
async def list_workspaces(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    stmt = (
        select(OrganizationModel, RoleBindingModel.role)
        .join(RoleBindingModel, OrganizationModel.id == RoleBindingModel.organization_id)
        .where(RoleBindingModel.user_id == UUID(user["id"]))
        .where(OrganizationModel.is_active)
    )
    result = await session.execute(stmt)

    workspaces = []
    for org, role in result.all():
        workspaces.append({"id": str(org.id), "name": org.name, "role": role, "billing_plan": org.billing_plan})

    return {"workspaces": workspaces}


@router.post("/current/rename")
async def rename_workspace(
    request: RenameWorkspaceRequest,
    org_id: OrganizationId = Depends(require_permission("workspace:settings:write")),
    session: AsyncSession = Depends(get_session)
):
    stmt = select(OrganizationModel).where(OrganizationModel.id == org_id)
    result = await session.execute(stmt)
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    org.name = request.name
    await session.commit()
    return {"status": "renamed", "name": org.name}


@router.post("/current/invitations")
async def invite_member(
    request: InviteMemberRequest,
    org_id: OrganizationId = Depends(require_permission("workspace:settings:write")),
    session: AsyncSession = Depends(get_session)
):
    if request.role not in ["ADMIN", "MEMBER", "VIEWER"]:
        raise HTTPException(status_code=400, detail="Invalid role")

    # Check if already a member
    stmt = select(UserModel).where(UserModel.email == request.email)
    res = await session.execute(stmt)
    existing_user = res.scalar_one_or_none()
    
    if existing_user:
        binding_stmt = select(RoleBindingModel).where(
            RoleBindingModel.organization_id == org_id,
            RoleBindingModel.user_id == existing_user.id
        )
        res_binding = await session.execute(binding_stmt)
        if res_binding.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="User is already a member")

    # Create invitation
    token = secrets.token_urlsafe(32)
    invitation = InvitationModel(
        id=generate_id(),
        organization_id=org_id,
        email=request.email,
        role=request.role,
        token=token,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7),
        is_accepted=False
    )
    session.add(invitation)
    try:
        await session.commit()
    except Exception:
        raise HTTPException(status_code=400, detail="Invitation already sent to this email")

    return {"status": "invited", "token": token}


@router.post("/invitations/{token}/accept")
async def accept_invitation(
    token: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    stmt = select(InvitationModel).where(InvitationModel.token == token)
    result = await session.execute(stmt)
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
        
    if invitation.is_accepted:
        raise HTTPException(status_code=400, detail="Invitation already accepted")
        
    if invitation.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="Invitation expired")
        
    if invitation.email != user["email"]:
        raise HTTPException(status_code=403, detail="Invitation is for a different email")

    invitation.is_accepted = True
    
    # Create binding
    binding = RoleBindingModel(
        id=generate_id(),
        organization_id=invitation.organization_id,
        user_id=UUID(user["id"]),
        role=invitation.role
    )
    session.add(binding)
    await session.commit()
    
    return {"status": "accepted", "workspace_id": str(invitation.organization_id)}


@router.delete("/current/invitations/{invitation_id}")
async def revoke_invitation(
    invitation_id: str,
    org_id: OrganizationId = Depends(require_permission("workspace:settings:write")),
    session: AsyncSession = Depends(get_session)
):
    stmt = select(InvitationModel).where(
        InvitationModel.id == UUID(invitation_id),
        InvitationModel.organization_id == org_id
    )
    res = await session.execute(stmt)
    invitation = res.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
        
    await session.delete(invitation)
    await session.commit()
    return {"status": "revoked"}


@router.put("/current/members/{target_user_id}/role")
async def change_role(
    target_user_id: str,
    request: ChangeRoleRequest,
    user: dict = Depends(get_current_user),
    org_id: OrganizationId = Depends(require_permission("workspace:settings:write")),
    session: AsyncSession = Depends(get_session)
):
    if request.role not in ["ADMIN", "MEMBER", "VIEWER"]:
        raise HTTPException(status_code=400, detail="Invalid role or cannot assign OWNER")

    stmt = select(RoleBindingModel).where(
        RoleBindingModel.organization_id == org_id,
        RoleBindingModel.user_id == UUID(target_user_id)
    )
    res = await session.execute(stmt)
    binding = res.scalar_one_or_none()
    
    if not binding:
        raise HTTPException(status_code=404, detail="Member not found")
        
    if binding.role == "OWNER":
        raise HTTPException(status_code=400, detail="Cannot change role of an owner")
        
    binding.role = request.role
    await session.commit()
    return {"status": "updated", "role": binding.role}


@router.delete("/current/members/{target_user_id}")
async def remove_member(
    target_user_id: str,
    user: dict = Depends(get_current_user),
    org_id: OrganizationId = Depends(require_permission("workspace:settings:write")),
    session: AsyncSession = Depends(get_session)
):
    stmt = select(RoleBindingModel).where(
        RoleBindingModel.organization_id == org_id,
        RoleBindingModel.user_id == UUID(target_user_id)
    )
    res = await session.execute(stmt)
    binding = res.scalar_one_or_none()
    
    if not binding:
        raise HTTPException(status_code=404, detail="Member not found")
        
    if binding.role == "OWNER":
        raise HTTPException(status_code=400, detail="Cannot remove an owner")
        
    await session.delete(binding)
    await session.commit()
    return {"status": "removed"}


@router.post("/current/leave")
async def leave_workspace(
    user: dict = Depends(get_current_user),
    org_id: OrganizationId = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session)
):
    stmt = select(RoleBindingModel).where(
        RoleBindingModel.organization_id == org_id,
        RoleBindingModel.user_id == UUID(user["id"])
    )
    res = await session.execute(stmt)
    binding = res.scalar_one_or_none()
    
    if not binding:
        raise HTTPException(status_code=404, detail="Not a member")
        
    if binding.role == "OWNER":
        raise HTTPException(status_code=400, detail="Owner cannot leave without transferring ownership first")
        
    await session.delete(binding)
    await session.commit()
    return {"status": "left"}


@router.post("/current/transfer")
async def transfer_ownership(
    request: TransferOwnershipRequest,
    user: dict = Depends(get_current_user),
    org_id: OrganizationId = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session)
):
    # Check if current user is owner
    stmt_owner = select(RoleBindingModel).where(
        RoleBindingModel.organization_id == org_id,
        RoleBindingModel.user_id == UUID(user["id"]),
        RoleBindingModel.role == "OWNER"
    )
    res_owner = await session.execute(stmt_owner)
    owner_binding = res_owner.scalar_one_or_none()
    if not owner_binding:
        raise HTTPException(status_code=403, detail="Only owners can transfer ownership")
        
    stmt_new = select(RoleBindingModel).where(
        RoleBindingModel.organization_id == org_id,
        RoleBindingModel.user_id == UUID(request.new_owner_id)
    )
    res_new = await session.execute(stmt_new)
    new_owner_binding = res_new.scalar_one_or_none()
    if not new_owner_binding:
        raise HTTPException(status_code=404, detail="Target user is not a member of this workspace")
        
    # Swap roles
    owner_binding.role = "ADMIN"
    new_owner_binding.role = "OWNER"
    await session.commit()
    
    return {"status": "transferred"}


@router.post("/current/suspend")
async def suspend_workspace(
    user: dict = Depends(get_current_user),
    org_id: OrganizationId = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session)
):
    # Only owner
    stmt = select(RoleBindingModel).where(
        RoleBindingModel.organization_id == org_id,
        RoleBindingModel.user_id == UUID(user["id"]),
        RoleBindingModel.role == "OWNER"
    )
    res = await session.execute(stmt)
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Only owners can suspend workspace")
        
    org_stmt = select(OrganizationModel).where(OrganizationModel.id == org_id)
    org_res = await session.execute(org_stmt)
    org = org_res.scalar_one_or_none()
    
    if org:
        org.is_active = False
        await session.commit()
        
    return {"status": "suspended"}


@router.delete("/current")
async def delete_workspace(
    user: dict = Depends(get_current_user),
    org_id: OrganizationId = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session)
):
    # Only owner
    stmt = select(RoleBindingModel).where(
        RoleBindingModel.organization_id == org_id,
        RoleBindingModel.user_id == UUID(user["id"]),
        RoleBindingModel.role == "OWNER"
    )
    res = await session.execute(stmt)
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Only owners can delete workspace")
        
    org_stmt = select(OrganizationModel).where(OrganizationModel.id == org_id)
    org_res = await session.execute(org_stmt)
    org = org_res.scalar_one_or_none()
    
    if org:
        await session.delete(org)
        await session.commit()
        
    return {"status": "deleted"}
