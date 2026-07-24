
import httpx
import structlog

logger = structlog.get_logger(__name__)


class GitHubClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    async def create_pull_request(
        self, owner: str, repo: str, title: str, head: str, base: str, body: str | None = None
    ) -> dict:
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/repos/{owner}/{repo}/pulls"
            payload = {
                "title": title,
                "head": head,
                "base": base,
            }
            if body:
                payload["body"] = body

            response = await client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()
