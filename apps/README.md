# Application entry points

The `apps` directory contains Forge's deployable processes. Business behavior stays in
`services`, while shared infrastructure and data models stay in `packages`.

## API

`apps/api/main.py` assembles the FastAPI application, middleware, lifecycle hooks, and
service routers. Start it for local development with:

```bash
uv run uvicorn apps.api.main:app --reload --port 8000
```

The API expects PostgreSQL and Redis to be available and reads configuration from the
root environment file.

## Worker

`apps/worker/main.py` runs the Redis Streams consumers that process repository import,
planning, execution, verification, audit, and related outbox events. Run it separately
from the API:

```bash
uv run python -m apps.worker.main
```

Only one process should own a given consumer identity. Scale workers through the
deployment configuration rather than starting duplicate local processes accidentally.

## Frontend

`apps/frontend` is the Next.js interface for authentication, tasks, execution status,
and provider settings. Its environment is independent of the Python processes:

```bash
cd apps/frontend
cp .env.example .env.local
npm ci
npm run dev
```

The frontend consumes the public API; it must not receive database credentials,
encryption keys, provider secrets, or Docker access.
