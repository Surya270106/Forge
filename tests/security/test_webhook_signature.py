from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from services.github import webhooks


def webhook_request() -> Request:
    async def receive():
        return {"type": "http.request", "body": b'{"ref":"refs/heads/main"}', "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/webhook", "headers": []}, receive)


@pytest.mark.asyncio
async def test_webhook_requires_configured_secret(monkeypatch):
    monkeypatch.setattr(webhooks, "get_settings", lambda: SimpleNamespace(github_webhook_secret=None))
    with pytest.raises(HTTPException) as error:
        await webhooks.verify_signature(webhook_request(), "sha256=invalid")
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr(webhooks, "get_settings", lambda: SimpleNamespace(github_webhook_secret="test-secret"))
    with pytest.raises(HTTPException) as error:
        await webhooks.verify_signature(webhook_request(), "sha256=invalid")
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_default_branch_push_needs_no_tenant_database_context():
    async def receive():
        return {"type": "http.request", "body": b'{"ref":"refs/heads/main","repository":{"clone_url":"https://github.com/example/repo.git","default_branch":"main"}}', "more_body": False}

    request = Request({"type": "http", "method": "POST", "path": "/webhook", "headers": []}, receive)
    result = await webhooks.handle_github_webhook(request, "push", True)
    assert result == {"status": "not_scheduled", "reason": "Repository synchronization is not implemented"}
