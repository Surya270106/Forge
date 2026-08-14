# Container definitions

Forge keeps every maintained Dockerfile in this directory and uses the repository root
as the build context. `docker-compose.yml` is the canonical local stack definition.

## Images

| Dockerfile | Purpose |
| --- | --- |
| `Dockerfile.api` | FastAPI application and migration job |
| `Dockerfile.worker` | Redis Streams worker with Docker CLI access |
| `Dockerfile.frontend` | Production Next.js server |
| `Dockerfile.sandbox-python` | Reviewed Python execution base |
| `Dockerfile.sandbox-node` | Reviewed Node.js execution base |

Build an individual image from the repository root so shared files remain available:

```bash
docker build -f docker/Dockerfile.api -t forge-api .
docker build -f docker/Dockerfile.worker -t forge-worker .
docker build -f docker/Dockerfile.frontend -t forge-frontend .
```

## Local stack

```bash
docker compose config
docker compose up --build
```

The stack starts PostgreSQL and Redis, applies Alembic migrations, then starts the API
and worker. The frontend image is maintained independently and is not currently part of
the Compose stack.

The development database password and application secret fallbacks in Compose are local
defaults only. Supply unique secrets and a non-development `ENVIRONMENT` for any shared
deployment.

## Docker socket boundary

The worker mounts `/var/run/docker.sock` to create execution containers. Access to that
socket is effectively host-level control, even when the worker itself runs in a container.
Run Forge only on a dedicated, trusted Docker host; do not expose the socket to the API or
frontend. Set `DOCKER_GID` to the numeric group that owns the host socket.

Container isolation is one layer of the execution boundary, not a substitute for host
hardening. Keep the sandbox image allowlist narrow, disable network access for workloads
that do not require it, and run the Docker integration and security tests after changes.
