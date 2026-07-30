import hmac
import hashlib
from fastapi import APIRouter, Header, Request, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from packages.database.engine import get_session
from packages.database.models.repository import RepositoryModel
from packages.shared.config import get_settings

router = APIRouter(prefix="/api/v1/github/webhooks", tags=["GitHub Webhooks"])
logger = structlog.get_logger(__name__)

async def verify_signature(request: Request, x_hub_signature_256: str = Header(None)):
    settings = get_settings()
    secret = settings.github_webhook_secret
    if not secret:
        # If no secret is configured, we can't verify securely, but we might allow it for dev.
        # For production, we must require it.
        if settings.environment == "production":
            raise HTTPException(status_code=500, detail="Webhook secret not configured in production")
        return True
        
    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="Missing signature")
        
    payload = await request.body()
    expected_signature = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_signature, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")
    return True

@router.post("/")
async def handle_github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    session: AsyncSession = Depends(get_session),
    _verified: bool = Depends(verify_signature)
):
    payload = await request.json()
    
    if x_github_event == "push":
        repository_data = payload.get("repository", {})
        clone_url = repository_data.get("clone_url")
        default_branch = repository_data.get("default_branch")
        ref = payload.get("ref")
        
        if not clone_url or ref != f"refs/heads/{default_branch}":
            return {"status": "ignored", "reason": "not default branch or missing repo info"}
            
        stmt = select(RepositoryModel).where(RepositoryModel.clone_url == clone_url)
        result = await session.execute(stmt)
        repos = result.scalars().all()
        
        if not repos:
            return {"status": "ignored", "reason": "repository not tracked in forge"}
            
        for repo in repos:
            logger.info("github_webhook_push", repo_id=str(repo.id))
            # In a real system, we'd enqueue a sync/update job here via redis stream
            # For now, we'll just log it.
            # Example: 
            # from packages.shared.events import EventPublisher
            # await publisher.publish(RepositoryUpdatedEvent(repository_id=repo.id))
            pass
            
        return {"status": "success", "triggered_repos": [str(r.id) for r in repos]}
        
    elif x_github_event == "ping":
        return {"status": "pong"}
        
    return {"status": "ignored", "reason": f"unhandled event type: {x_github_event}"}
