# Contributing to Forge AI

## Development Setup
- **Backend Setup**: Use `uv` for python dependencies. Run `uv sync --frozen --all-extras` to ensure a clean, reproducible environment.
- **Frontend Setup**: Use `npm ci` in `apps/frontend` for deterministic installs.
- **Services**: Ensure PostgreSQL and Redis are running locally.

## Formatting & Linting
- **Backend**: Run `uv run ruff format .` and `uv run ruff check .`
- **Frontend**: Run `npm run lint` and `npm run typecheck`
- **Type Checking**: Run `uv run pyright` for Python.

## Testing
- Unit and integration tests must pass before submitting a pull request:
  - `uv run pytest tests -v`
- Frontend E2E tests must pass:
  - `npx playwright test` inside `apps/frontend`.

## Migration Rules
- **Immutability**: The pre-release migration baseline is frozen. Never regenerate the full migration history.
- **No Revision Editing**: Never edit an already shared migration revision.
- **Schema Changes**: Every schema change requires a new migration.
- **Explicit RLS**: Every RLS change requires an explicit, manually reviewed migration. Alembic does not autogenerate RLS.
- **Verification**: CI must verify migrations from a clean PostgreSQL database.

## Architectural Layering
Forge AI strictly follows this layering:
`Route -> Service -> Repository`
- **Routes** handle HTTP parsing and responses.
- **Services** contain business logic.
- **Repositories** handle database queries.

## Frontend Conventions
- `apps/frontend` is the single canonical frontend.
- Utilize Tailwind CSS, Zustand, React Query, and Radix UI.

## Engineering Priority
When contributing, adhere to the following priority hierarchy:
1. **Correctness**
2. **Security**
3. **Maintainability**
4. **Observability**
5. **Performance**
6. **Developer Experience**

## Pull Request Verification Checklist
- [ ] Dependencies are synchronized (`uv sync --frozen --all-extras`, `npm ci`)
- [ ] Formatting and linting pass (`ruff`, `eslint`, `pyright`, `tsc`)
- [ ] Tests pass (`pytest`, `playwright`)
- [ ] Migrations are valid and include RLS if necessary
- [ ] No secrets are included
