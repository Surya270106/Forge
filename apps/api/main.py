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
    return {"status": "ok"}


@app.get("/ready")
async def readiness_check():
    import os

    from fastapi import HTTPException
    from sqlalchemy import text

    from packages.database.engine import get_engine

    try:
        url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://forge:forge@localhost:5432/forge")
        engine = get_engine(url)
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}")
