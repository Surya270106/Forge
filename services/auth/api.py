from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.auth import OrganizationModel, RoleBindingModel, UserModel
from packages.shared.config import get_settings
from packages.shared.identifiers import generate_id
from services.auth.dependencies import get_current_user
from services.auth.jwt import create_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

GITHUB_OAUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

@router.get("/github/login")
async def github_login():
    settings = get_settings()
    if not settings.github_client_id:
        raise HTTPException(status_code=500, detail="GitHub Client ID not configured")

    redirect_uri = f"{GITHUB_OAUTH_URL}?client_id={settings.github_client_id}&scope=user:email repo"
    return {"url": redirect_uri}

@router.get("/github/callback")
async def github_callback(code: str, request: Request, session: AsyncSession = Depends(get_session)):
    settings = get_settings()
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(status_code=500, detail="GitHub credentials not configured")

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret.get_secret_value(),
                "code": code
            }
        )
        token_data = token_response.json()

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Failed to authenticate with GitHub")

    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"}
        )
        if user_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch GitHub profile")
        github_user = user_response.json()

        emails_response = await client.get(
            GITHUB_EMAILS_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"}
        )
        emails = emails_response.json()
        primary_email = next((e["email"] for e in emails if e.get("primary")), None)

        if not primary_email:
            raise HTTPException(status_code=400, detail="No primary email found on GitHub account")

    stmt = select(UserModel).where(UserModel.email == primary_email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        user = UserModel(
            id=generate_id(),
            email=primary_email,
            name=github_user.get("name") or github_user.get("login"),
            is_active=True,
            github_token=access_token
        )
        session.add(user)

        org = OrganizationModel(
            id=generate_id(),
            name=f"{user.name}'s Workspace",
            billing_plan="FREE",
            is_active=True
        )
        session.add(org)

        binding = RoleBindingModel(
            id=generate_id(),
            organization_id=org.id,
            user_id=user.id,
            role="OWNER"
        )
        session.add(binding)
    else:
        user.github_token = access_token

    await session.commit()

    org_stmt = select(RoleBindingModel.organization_id).where(RoleBindingModel.user_id == user.id)
    org_result = await session.execute(org_stmt)
    org_ids = [row[0] for row in org_result.fetchall()]
    default_org_id = org_ids[0] if org_ids else None

    jwt_token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(days=7)
    )

    frontend_url = settings.cors_origins[0] if settings.cors_origins else "http://localhost:3000"
    redirect_url = f"{frontend_url}/login/callback?token={jwt_token}&org_id={str(default_org_id)}"
    return RedirectResponse(url=redirect_url)

@router.get("/me")
async def get_current_user_profile(user: dict = Depends(get_current_user)):
    return user

@router.get("/workspaces")
async def get_workspaces(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    stmt = (
        select(OrganizationModel, RoleBindingModel.role)
        .join(RoleBindingModel, OrganizationModel.id == RoleBindingModel.organization_id)
        .where(RoleBindingModel.user_id == user["id"])
        .where(OrganizationModel.is_active == True)
    )
    result = await session.execute(stmt)

    workspaces = []
    for org, role in result.all():
        workspaces.append({
            "id": str(org.id),
            "name": org.name,
            "role": role,
            "billing_plan": org.billing_plan
        })

    return {"workspaces": workspaces}

@router.get("/workspaces/current/provider")
async def get_provider_config(request: Request, session: AsyncSession = Depends(get_session)):
    org_id_str = request.headers.get("X-Organization-Id")
    if not org_id_str:
        raise HTTPException(status_code=400, detail="Missing X-Organization-Id")

    stmt = select(OrganizationModel.provider_config).where(OrganizationModel.id == org_id_str)
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()

    if config and "api_key" in config:
        config["api_key"] = f"sk-...{config['api_key'][-4:]}" if len(config['api_key']) > 4 else "sk-..."

    return {"config": config or {}}

@router.put("/workspaces/current/provider")
async def update_provider_config(request: Request, session: AsyncSession = Depends(get_session)):
    org_id_str = request.headers.get("X-Organization-Id")
    if not org_id_str:
        raise HTTPException(status_code=400, detail="Missing X-Organization-Id")

    data = await request.json()
    provider = data.get("provider")
    api_key = data.get("api_key")
    model = data.get("model")

    if not provider or not api_key:
        raise HTTPException(status_code=400, detail="Provider and API key are required")

    stmt = select(OrganizationModel).where(OrganizationModel.id == org_id_str)
    result = await session.execute(stmt)
    org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(status_code=404, detail="Workspace not found")

    org.provider_config = {
        "provider": provider,
        "api_key": api_key,
        "model": model or "gpt-4o"
    }
    await session.commit()

    return {"status": "updated"}
