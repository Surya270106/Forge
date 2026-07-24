from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.context_engine.api import router as context_router
from services.execution.api import router as execution_router
from services.patch.api import router as patch_router
from services.planning.api import router as planning_router
from services.repository_import.api import router as import_router
from services.repository_memory.api import router as memory_router
from services.verification.api import router as verification_router

app = FastAPI(
    title="Forge AI",
    description="Autonomous Software Engineering Platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(context_router)
app.include_router(execution_router)
app.include_router(planning_router)
app.include_router(import_router)
app.include_router(memory_router)
app.include_router(verification_router)


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
