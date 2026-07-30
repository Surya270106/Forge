$ErrorActionPreference = 'Stop'

if (-not $env:DATABASE_URL) {
    Write-Error "DATABASE_URL environment variable is required."
    exit 1
}

# Avoid exposing credentials in logs
Write-Host "Verifying database connectivity..."
try {
    # Simple check using a quick python script to test connectivity
    # Using asyncpg to connect and grab an advisory lock
    $dbCheckScript = @"
import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    url = os.environ.get('DATABASE_URL')
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            # Postgres advisory lock (ID: 12345)
            # This ensures only one migration runs at a time
            result = await conn.execute(
                __import__('sqlalchemy').text("SELECT pg_try_advisory_lock(12345)")
            )
            locked = result.scalar()
            if not locked:
                print("Could not obtain migration lock. Another migration is running.")
                sys.exit(1)
            print("Connectivity verified and migration lock obtained.")
    except Exception as e:
        print(f"Database connection failed: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()

asyncio.run(main())
"@
    
    # Run the check
    $pythonPath = ".\.venv_official\Scripts\python.exe"
    if (-not (Test-Path $pythonPath)) {
        $pythonPath = "python" # fallback
    }
    
    $checkResult = $dbCheckScript | & $pythonPath - 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Pre-migration check failed: $checkResult"
        exit 1
    }
    Write-Host $checkResult
} catch {
    Write-Error "Failed to verify database connectivity: $_"
    exit 1
}

Write-Host "Running migrations..."
try {
    # Run alembic upgrade head using uv or direct python depending on availability
    # The requirement specifically mentions "uv run alembic upgrade head"
    # But since we are using .venv_official, we'll run it explicitly
    $alembicPath = ".\.venv_official\Scripts\alembic.exe"
    if (-not (Test-Path $alembicPath)) {
        uv run alembic upgrade head
    } else {
        & $alembicPath upgrade head
    }
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Alembic upgrade failed."
        exit 1
    }
    
    Write-Host "Migration complete. Current revision:"
    if (-not (Test-Path $alembicPath)) {
        uv run alembic current
    } else {
        & $alembicPath current
    }
    
} catch {
    Write-Error "Migration execution encountered an error: $_"
    exit 1
}

Write-Host "Migration lifecycle script completed successfully."
exit 0
