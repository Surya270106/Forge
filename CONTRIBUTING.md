# Contributing to Forge

Forge accepts focused changes that preserve the repository-import, planning, execution, and verification lifecycle. Please discuss architectural redesigns before implementing them.

## Setup

1. Install Python 3.12, `uv`, Node.js 20 or newer, npm, Docker Engine, and Docker Compose.
2. Copy `.env.example` to `.env` and `apps/frontend/.env.example` to `apps/frontend/.env.local`.
3. Run `uv sync --frozen --all-extras`.
4. Run `npm ci` from `apps/frontend`.
5. Start PostgreSQL and Redis with `docker compose up -d postgres redis`, then run `uv run alembic upgrade head`.

## Checks

Before opening a pull request, run the checks relevant to your change.

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest tests -v
```

```bash
cd apps/frontend
npm run lint
npm run typecheck
npm run build
npx playwright test
```

For container or execution changes, also run `docker compose config`, build the affected Dockerfiles, and run the Docker integration and security tests.

## Branches and pull requests

- Use a descriptive branch such as `feat/short-name`, `fix/short-name`, `docs/short-name`, or `chore/short-name`.
- Keep commits scoped and use an imperative, conventional subject where practical.
- Explain the behavior and motivation, identify migrations or security impact, and report the exact checks run.
- Update tests and documentation when interfaces, configuration, or operational behavior change.
- Keep unrelated formatting and refactors out of the pull request.

## Security

Never commit credentials, `.env` files, provider tokens, private keys, cloned repositories, or generated workspaces. Do not weaken authentication, RBAC, RLS, sandbox, network, or Docker security checks to make CI pass. Report vulnerabilities according to [SECURITY.md](SECURITY.md).
