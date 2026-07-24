from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
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
            data={"client_id": settings.github_client_id, "client_secret": settings.github_client_secret.get_secret_value(), "code": code},
        )
        token_data = token_response.json()

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Failed to authenticate with GitHub")

    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            GITHUB_USER_URL, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"}
        )
        if user_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch GitHub profile")
        github_user = user_response.json()

        emails_response = await client.get(
            GITHUB_EMAILS_URL, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"}
        )
        emails = emails_response.json()
        primary_email = next((e["email"] for e in emails if e.get("primary")), None)

        if not primary_email:
            raise HTTPException(status_code=400, detail="No primary email found on GitHub account")

    stmt = select(UserModel).where(UserModel.email == primary_email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    from packages.shared.crypto import CryptoService

    encrypted_token = CryptoService.encrypt(access_token)

    if not user:
        user = UserModel(
            id=generate_id(), email=primary_email, name=github_user.get("name") or github_user.get("login"), is_active=True, github_token=encrypted_token
        )
        session.add(user)

        org = OrganizationModel(id=generate_id(), name=f"{user.name}'s Workspace", billing_plan="FREE", is_active=True)
        session.add(org)

        binding = RoleBindingModel(id=generate_id(), organization_id=org.id, user_id=user.id, role="OWNER")
        session.add(binding)
    else:
        user.github_token = encrypted_token

    await session.commit()

    org_stmt = select(RoleBindingModel.organization_id).where(RoleBindingModel.user_id == user.id)
    org_result = await session.execute(org_stmt)
    org_ids = [row[0] for row in org_result.fetchall()]
    default_org_id = org_ids[0] if org_ids else None

    jwt_token = create_access_token(data={"sub": str(user.id), "email": user.email}, expires_delta=timedelta(days=7))

    frontend_url = settings.cors_origins[0] if settings.cors_origins else "http://localhost:3000"
    redirect_url = f"{frontend_url}/login/success?org_id={str(default_org_id)}"

    response = RedirectResponse(url=redirect_url)
    response.set_cookie(
        key="forge_session",
        value=jwt_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60, # 7 days
    )
    return response

@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("forge_session", httponly=True, secure=True, samesite="lax")
    return response



@router.get("/me")
async def get_current_user_profile(user: dict = Depends(get_current_user)):
    return user


@router.get("/workspaces")
async def get_workspaces(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    stmt = (
        select(OrganizationModel, RoleBindingModel.role)
        .join(RoleBindingModel, OrganizationModel.id == RoleBindingModel.organization_id)
        .where(RoleBindingModel.user_id == user["id"])
        .where(OrganizationModel.is_active)
    )
    result = await session.execute(stmt)

    workspaces = []
    for org, role in result.all():
        workspaces.append({"id": str(org.id), "name": org.name, "role": role, "billing_plan": org.billing_plan})

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
        from packages.shared.crypto import CryptoService
        decrypted_key = CryptoService.decrypt(config["api_key"])
        config["api_key"] = f"sk-...{decrypted_key[-4:]}" if len(decrypted_key) > 4 else "sk-..."

    return {"config": config or {}}


@router.put("/workspaces/current/provider")
async def update_provider_config(request: Request, session: AsyncSession = Depends(get_session)):
    org_id_str = request.headers.get("X-Organization-Id")
    if not org_id_str:
        raise HTTPException(status_code=400, detail="Missing X-Organization-Id")

    from packages.shared.crypto import CryptoService

    data = await request.json()
    provider = data.get("provider")
    api_key = data.get("api_key")
    model = data.get("model")

    budget_usd = data.get("budget_usd")

    if not provider or not api_key:
        raise HTTPException(status_code=400, detail="Provider and API key are required")

    stmt = select(OrganizationModel).where(OrganizationModel.id == org_id_str)
    result = await session.execute(stmt)
    org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # If the user sends a masked key back, don't overwrite the actual key
    if api_key.startswith("sk-..."):
        api_key = CryptoService.decrypt(org.provider_config.get("api_key", "")) if org.provider_config else ""

    encrypted_key = CryptoService.encrypt(api_key)

    new_config = {
        "provider": provider,
        "api_key": encrypted_key,
        "model": model or "gpt-4o",
        "budget_usd": float(budget_usd) if budget_usd is not None else (org.provider_config.get("budget_usd", 100.0) if org.provider_config else 100.0),
        "spend_usd": org.provider_config.get("spend_usd", 0.0) if org.provider_config else 0.0
    }
    org.provider_config = new_config
    await session.commit()

    return {"status": "updated"}

@router.post("/workspaces/current/provider/test")
async def test_provider_config(request: Request, session: AsyncSession = Depends(get_session)):
    org_id_str = request.headers.get("X-Organization-Id")
    if not org_id_str:
        raise HTTPException(status_code=400, detail="Missing X-Organization-Id")

    from packages.shared.crypto import CryptoService

    data = await request.json()
    provider = data.get("provider")
    api_key = data.get("api_key")

    if not provider or not api_key:
        # fallback to db if none provided
        stmt = select(OrganizationModel.provider_config).where(OrganizationModel.id == org_id_str)
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()
        if not config:
            raise HTTPException(status_code=400, detail="Provider and API key are required")
        provider = config.get("provider")
        api_key = CryptoService.decrypt(config.get("api_key", ""))

    # if it's masked from the frontend, fetch from DB
    if api_key.startswith("sk-..."):
        stmt = select(OrganizationModel.provider_config).where(OrganizationModel.id == org_id_str)
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()
        if not config:
            raise HTTPException(status_code=400, detail="Invalid masked API key")
        api_key = CryptoService.decrypt(config.get("api_key", ""))

    try:
        async with httpx.AsyncClient() as client:
            if provider.lower() == "openai":
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0,
                )
                if resp.status_code != 200:
                    raise HTTPException(status_code=400, detail=f"OpenAI error: {resp.text}")
            elif provider.lower() == "anthropic":
                # Anthropic doesn't have a simple /models endpoint, test via a cheap message
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                    json={"model": "claude-3-haiku-20240307", "max_tokens": 10, "messages": [{"role": "user", "content": "hello"}]},
                    timeout=10.0,
                )
                if resp.status_code != 200:
                    raise HTTPException(status_code=400, detail=f"Anthropic error: {resp.text}")
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok", "message": "Connection successful"}
