import hashlib
import hmac

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from packages.shared.config import get_settings

router = APIRouter(prefix="/api/v1/github/webhooks", tags=["GitHub Webhooks"])
logger = structlog.get_logger(__name__)

async def verify_signature(request: Request, x_hub_signature_256: str = Header(None)):
    settings = get_settings()
    secret = settings.github_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

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

        # Synchronization is not implemented. Avoid a cross-tenant repository
        # lookup under forced RLS for an event that schedules no work.
        logger.info("github_webhook_push_not_scheduled")
        return {"status": "not_scheduled", "reason": "Repository synchronization is not implemented"}

    elif x_github_event == "ping":
        return {"status": "pong"}

    return {"status": "ignored", "reason": f"unhandled event type: {x_github_event}"}
