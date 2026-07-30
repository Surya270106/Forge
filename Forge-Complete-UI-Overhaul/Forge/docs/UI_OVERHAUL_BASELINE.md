# UI Overhaul Baseline

## 1. Route Inventory

| Route | Page | Component File |
|-------|------|----------------|
| `/` | Dashboard | `apps/frontend/app/page.tsx` |
| `/login` | Login | `apps/frontend/app/login/page.tsx` |
| `/login/callback` | OAuth Callback | `apps/frontend/app/login/callback/page.tsx` |
| `/repositories` | Repositories List | `apps/frontend/app/repositories/page.tsx` |
| `/repositories/[id]` | Repository Detail | `apps/frontend/app/repositories/[id]/page.tsx` |
| `/tasks` | Runs List | `apps/frontend/app/tasks/page.tsx` |
| `/tasks/[id]` | Task Detail | `apps/frontend/app/tasks/[id]/page.tsx` |
| `/settings` | Settings Index | `apps/frontend/app/settings/page.tsx` |
| `/settings/provider` | Provider Config | `apps/frontend/app/settings/provider/page.tsx` |
| `/settings/workspaces`| Workspaces Config | `apps/frontend/app/settings/workspaces/page.tsx` |

## 2. Component Inventory

*   **AppShell**: Authenticated layout containing the Sidebar and basic structure.
*   **Icons**: Lucide-react standard icons.
*   **Blob**: Missing from current baseline, to be introduced from `reference-ui`.

## 3. API Mapping

| UI Action | API Endpoint |
|-----------|--------------|
| Login Redirect | `GET /api/v1/auth/github/login` |
| Fetch Profile | `GET /api/v1/auth/me` |
| Get Repositories | `GET /api/v1/repositories/imported` |
| Import Repo | `POST /api/v1/repositories/import` |
| Index Codebase | `POST /api/v1/memory/repositories/{id}/index` |
| Fetch Plans | `GET /api/v1/plans` |
| Create Plan | `POST /api/v1/repositories/{id}/plans` |
| Approve Plan | `POST /api/v1/plans/{id}/approve` |
| Start Execution | `POST /api/v1/executions/plans/{id}` |
| Get Execution | `GET /api/v1/executions/{id}` |
| Get Provider | `GET /api/v1/auth/workspaces/current/provider` |
| Set Provider | `PUT /api/v1/auth/workspaces/current/provider` |

## 4. Test & Build Status

*   **Linting**: Verified as passing/green.
*   **Type-checking**: Verified as passing/green.
*   **Tests (`pytest`)**: Run separately and confirmed passing.
*   **Next.js Production Build**: Verified as successfully built.

## 5. Backup Reference

*   **Backup branch**: `backup/pre-ui-overhaul-v2`
*   **Parent branch**: `feat/complete-production-application`
