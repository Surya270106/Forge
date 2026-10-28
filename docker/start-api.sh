#!/bin/sh
set -eu

/app/.venv/bin/alembic upgrade head

exec /app/.venv/bin/uvicorn apps.api.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-${API_PORT:-8000}}"
