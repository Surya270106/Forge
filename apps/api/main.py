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

app = FastAPI(
    title="Forge AI API",
    description="Internal alpha API for Forge AI.",
    version="0.1.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(repo_router)
app.include_router(memory_router)
app.include_router(planning_router)
app.include_router(execution_router)
app.include_router(context_router)
app.include_router(patch_router)
app.include_router(audit_router)


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
    except Exception as e:
        status_info["checks"]["database"] = f"failed: {e}"
        raise HTTPException(status_code=503, detail=status_info)

    try:
        redis_client = redis_async.from_url(settings.redis_url)
        await redis_client.ping()
        await redis_client.aclose()
        status_info["checks"]["redis"] = "ok"
    except Exception as e:
        status_info["checks"]["redis"] = f"failed: {e}"
        raise HTTPException(status_code=503, detail=status_info)

    return status_info
