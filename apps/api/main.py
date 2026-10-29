from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.audit.api import router as audit_router
from services.auth.api import router as auth_router
from services.context_engine.api import router as context_router
from services.execution.api import router as execution_router
from services.patch.api import router as patch_router
from services.planning.api import router as planning_router
from services.repository_import.api import router as repo_router
from services.repository_memory.api import router as memory_router
from services.verification.api import router as verification_router
from services.organizations.api import router as organizations_router

app = FastAPI(
    title="Forge AI API",
    description="Internal alpha API for Forge AI.",
    version="0.1.0",
)

# CORS configuration
from packages.shared.config import get_settings
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["X-Frame-Options"] = "DENY"
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router)
app.include_router(repo_router)
app.include_router(memory_router)
app.include_router(planning_router)
app.include_router(execution_router)
app.include_router(verification_router)
app.include_router(context_router)
app.include_router(patch_router)
app.include_router(audit_router)
app.include_router(organizations_router)

from services.github.webhooks import router as github_router
app.include_router(github_router)


from fastapi.responses import RedirectResponse

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

@app.get("/health")
async def health_check():
    import psutil
    from packages.shared.config import get_settings
    settings = get_settings()
    return {
        "status": "ok", 
        "version": app.version,
        "environment": settings.environment,
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent
        }
    }


@app.get("/ready")
async def readiness_check():
    import os

    from fastapi import HTTPException
    from sqlalchemy import text
    import redis.asyncio as redis_async

    from packages.database.engine import get_engine
    from packages.shared.config import get_settings
    
    settings = get_settings()

    status_info = {"status": "ready", "checks": {}}
    
    try:
        url = os.environ.get("DATABASE_URL", settings.database_url)
        engine = get_engine(url)
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        status_info["checks"]["database"] = "ok"
    except Exception:
        status_info["checks"]["database"] = "unavailable"
        raise HTTPException(status_code=503, detail=status_info)

    try:
        redis_client = redis_async.from_url(settings.redis_url)
        await redis_client.ping()
        await redis_client.aclose()
        status_info["checks"]["redis"] = "ok"
    except Exception:
        status_info["checks"]["redis"] = "unavailable"
        raise HTTPException(status_code=503, detail=status_info)

    return status_info
