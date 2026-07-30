# Forge UI Overhaul

This source package contains the complete Forge application with the redesigned
frontend integrated into the existing API workflows.

## What changed

- Replaced the generic dashboard shell with an editorial white-and-rich-blue
  interface.
- Preserved the approved interactive WebGL blob, including its geometry,
  wireframe shader, animation, cursor response, fallback renderer, and fixed
  background position.
- Added the blob at full visual strength on the dashboard and login hero, then
  reduced its opacity behind dense workspace screens.
- Rebuilt the dashboard, GitHub repository import, repository workbench, plan
  review, execution stream, run history, provider settings, workspace settings,
  login, and callback states as one responsive design system.
- Kept the real repository import, indexing, planning, approval, execution,
  polling, logs, mutations, provider configuration, workspace creation, workspace
  switching, authentication, and sign-out actions.
- Removed UI controls that did not have corresponding backend actions.

## Frontend routes

| Route | Purpose |
| --- | --- |
| `/` | Workspace hero and imported-repository ledger |
| `/repositories` | GitHub repository search and import |
| `/repositories/[id]` | Repository task, memory, plans, and run workspace |
| `/tasks` | Plan and execution history |
| `/tasks/[id]` | Plan approval, execution, logs, and mutation evidence |
| `/settings/provider` | Workspace AI provider configuration |
| `/settings/workspaces` | Workspace creation and switching |
| `/login` | GitHub authentication entry |
| `/login/callback` | Authentication callback state |

## Run the frontend

```bash
cd apps/frontend
npm ci
npm run dev
```

The frontend reads `NEXT_PUBLIC_API_BASE_URL` from `apps/frontend/.env.local`.
Use `apps/frontend/.env.example` as the configuration template.

## Verification

The final source passed the Next.js production build, lint, TypeScript checks,
static generation for all routes, desktop browser rendering, and mobile overflow
checks at 390px.
