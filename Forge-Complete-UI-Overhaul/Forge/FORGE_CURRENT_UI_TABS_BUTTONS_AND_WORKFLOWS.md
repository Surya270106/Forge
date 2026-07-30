# Forge AI Repository Frontend Audit

## 1. Application structure

*   **Frontend framework and version**: Next.js 14.2.35 (React 18)
*   **Frontend application directory**: `apps/frontend/app`
*   **Routing system**: Next.js App Router
*   **Styling system**: Tailwind CSS 3.4.1, Autoprefixer
*   **Component libraries**: Lucide React (icons), Radix UI (dialog, slot available but largely unused), class-variance-authority, clsx, tailwind-merge
*   **State-management libraries**: React standard state (`useState`, `useEffect`), Zustand (installed but not seen in core pages), React Query (installed but `fetch` is heavily used directly)
*   **Authentication system**: Custom token-based (`localStorage.getItem("forge_token")`), integrated with GitHub OAuth. 
*   **API client implementation**: Native `fetch` wrapper inside `useEffect` and event handlers. Headers manually attach `Authorization: Bearer <token>` and `X-Organization-Id: <org_id>`. No unified Axios or Fetch interceptor is implemented.
*   **Main application entry points**:
    *   `apps/frontend/app/page.tsx` (Dashboard)
    *   `apps/frontend/app/login/page.tsx` (Login)
*   **Shared layouts and navigation components**: `apps/frontend/app/components/AppShell.tsx` provides the main authenticated layout, sidebar, and top-level navigation. `layout.tsx` also contains a fallback shell for non-client contexts.

## 2. Complete route inventory

| Route | Page name | Purpose | Layout used | Authentication required | Implemented status |
| ----- | --------- | ------- | ----------- | ----------------------- | ------------------ |
| `/` | DashboardPage | Shows imported repos and active runs | `AppShell.tsx` | Yes | Working |
| `/login` | LoginPage | Landing page with GitHub login | None | No | Working |
| `/login/callback` | CallbackPage | Handles OAuth callback redirect | None | No | Unknown/Partial |
| `/repositories` | RepositoriesPage | Lists GitHub repos to import | `AppShell.tsx` | Yes | Working |
| `/repositories/[id]` | RepositoryDetailPage | Shows repo details, indexing status, plan creation | `AppShell.tsx` | Yes | Working |
| `/tasks` | RunsPage | Lists plan/task execution history | `AppShell.tsx` | Yes | Working |
| `/tasks/[id]` | TaskPage | View plan graph, approve, execute, logs | `AppShell.tsx` | Yes | Working |
| `/settings` | SettingsPage | Redirects to `/settings/provider` | `AppShell.tsx` | Yes | Working |
| `/settings/provider` | ProviderSettingsPage | Configure LLM Provider/Key/Model | `AppShell.tsx` | Yes | Working |
| `/settings/workspaces` | WorkspacesPage | List and manage workspaces | `AppShell.tsx` | Yes | Partial |

## 3. Navigation inventory

| Navigation area | Visible label | Destination | Icon | Visibility condition | Working? |
| --------------- | ------------- | ----------- | ---- | -------------------- | -------- |
| Sidebar | Dashboard | `/` | LayoutDashboard | Authenticated | Yes |
| Sidebar | Repositories | `/repositories` | Database | Authenticated | Yes |
| Sidebar | Runs | `/tasks` | Activity | Authenticated | Yes |
| Sidebar | Settings | `/settings` | Settings | Authenticated | Yes |
| User Menu | Sign out | `/login` (via handler) | LogOut | Authenticated | Yes |
| Content | Back to Dashboard | `/` | ArrowLeft | `/repositories`, `/repositories/[id]` | Yes |
| Content | View | `/repositories/[id]` | ArrowRight | `/` (Dashboard) | Yes |

## 4. Tab inventory

Currently, there are **no traditional UI tab components** (e.g., Radix Tabs) implemented across the interface. 
*   **Repository workspace**: Single scrolling page showing Status, Source, Memory Index, and Autonomous Tasks intent input.
*   **Plan/Task detail**: Two-column layout (Task Graph on the left, Execution Logs on the right).
*   **Settings**: Sub-routes exist (`/settings/provider`, `/settings/workspaces`) but lack a unified tabbed navigation header to switch between them easily inside the UI.

## 5. Button and action inventory

| Route/page | Section | Button label | Component/file | What should happen | API/service called | Confirmation? | Current status |
| ---------- | ------- | ------------ | -------------- | ------------------ | ------------------ | ------------- | -------------- |
| `/login` | Login | Continue with GitHub | `login/page.tsx` | Redirects to GitHub OAuth | GET `/api/v1/auth/github/login` | No | Working |
| `/` | Header | Import Repository | `page.tsx` | Navigates to `/repositories` | None | No | Working |
| `/repositories` | Repo List | Import | `repositories/page.tsx` | Imports a repo | POST `/api/v1/repositories/import` | No | Working |
| `/repositories/[id]` | Header | Index Codebase | `repositories/[id]/page.tsx`| Triggers repo memory indexing | POST `/api/v1/memory/repositories/{id}/index`| No | Working |
| `/repositories/[id]` | Tasks | Create Plan | `repositories/[id]/page.tsx`| Creates a new AI execution plan | POST `/api/v1/repositories/{id}/plans` | No | Working |
| `/tasks/[id]` | Plan Actions| Reject | `tasks/[id]/page.tsx` | Rejects the proposed plan | None (Missing Handler) | No | **UI Only / Broken** |
| `/tasks/[id]` | Plan Actions| Approve Plan | `tasks/[id]/page.tsx` | Approves plan for execution | POST `/api/v1/plans/{id}/approve` | No | Working |
| `/tasks/[id]` | Plan Actions| Start Execution | `tasks/[id]/page.tsx` | Starts sandbox execution | POST `/api/v1/executions/plans/{id}` | No | Working |
| `/tasks/[id]` | Logs Footer | Create Pull Request | `tasks/[id]/page.tsx` | Creates a PR on GitHub | None (Missing Handler) | No | **UI Only / Broken** |
| `/settings/provider` | Form | Save Configuration | `settings/provider/page.tsx`| Saves LLM credentials | PUT `/api/v1/auth/workspaces/current/provider`| No | Working |
| `/settings/workspaces`| Header | Create | `settings/workspaces/page.tsx`| Creates a new org/workspace | POST `/auth/workspaces` | No | Working |
| `/settings/workspaces`| Card | Switch to Workspace | `settings/workspaces/page.tsx`| Changes active workspace context | Updates `localStorage`, reloads window | No | Partial (Hack) |
| `/settings/workspaces`| Card | Settings | `settings/workspaces/page.tsx`| Navigates to org settings | None (Missing Handler) | No | **UI Only / Broken** |
| `/settings/workspaces`| Card | Members | `settings/workspaces/page.tsx`| Opens org members view | None (Missing Handler) | No | **UI Only / Broken** |
| `AppShell.tsx` | Sidebar | Sign out | `AppShell.tsx` | Clears local storage, redirects | None (Frontend Only) | No | Working |

## 6. Forms and inputs

| Route/page | Form | Field | Type | Required? | Validation | Submitted to | Error handling |
| ---------- | ---- | ----- | ---- | --------- | ---------- | ------------ | -------------- |
| `/repositories/[id]` | Intent Input | `intent` | Text Input | Yes | `!intent.trim()` | POST `/api/v1/repositories/{id}/plans` | Alerts native `alert()` on error |
| `/tasks` | Search | `search` | Text Input | No | None (Client-side) | Filters `runs` array | None |
| `/settings/provider` | LLM Config | `provider` | Select | Yes | None | PUT `/api/v1/auth/workspaces/current/provider` | Console error |
| `/settings/provider` | LLM Config | `apiKey` | Password | Yes | `!apiKey` | PUT `/api/v1/auth/workspaces/current/provider` | Console error |
| `/settings/provider` | LLM Config | `model` | Text Input | Yes | None | PUT `/api/v1/auth/workspaces/current/provider` | Console error |
| `/settings/workspaces`| Create WS | `newWorkspaceName` | Text Input | Yes | `!newWorkspaceName`| POST `/auth/workspaces` | Console error |

## 7. Modals, drawers, menus, and popovers

Currently, there are **no implemented modals, drawers, or popovers** in the UI.

## 8. User workflows

1. **Sign in and sign out**:
   *   **Route**: `/login`
   *   **Steps**: Click "Continue with GitHub" -> Fetch OAuth URL -> Redirect -> Backend handles callback -> Set local storage -> Dashboard.
   *   **Endpoints**: GET `/api/v1/auth/github/login`

2. **Import a repository**:
   *   **Route**: `/repositories`
   *   **Steps**: List repos -> Click Import -> Redirect to Dashboard.
   *   **Endpoints**: GET `/api/v1/repositories/github-repos`, POST `/api/v1/repositories/import`

3. **Wait for repository indexing**:
   *   **Route**: `/repositories/[id]`
   *   **Steps**: Click "Index Codebase" -> Polling 5s interval on GET `/api/v1/repositories/imported`
   *   **Endpoints**: POST `/api/v1/memory/repositories/{id}/index`

4. **Submit a natural-language engineering request (Create Plan)**:
   *   **Route**: `/repositories/[id]`
   *   **Steps**: Type in input box -> Click "Create Plan" -> Redirects to `/tasks/[id]`.
   *   **Endpoints**: POST `/api/v1/repositories/{id}/plans`

5. **Approve and Execute**:
   *   **Route**: `/tasks/[id]`
   *   **Steps**: View Plan -> Click "Approve Plan" -> Click "Start Execution" -> Polls logs and status.
   *   **Endpoints**: POST `/api/v1/plans/{id}/approve`, POST `/api/v1/executions/plans/{id}`, GET `/api/v1/executions/{id}`, GET `/api/v1/executions/{id}/logs`, GET `/api/v1/executions/{id}/mutations`

6. **Missing Workflows**:
   *   Connecting GitHub (outside of initial login).
   *   Verifying results (no Verification UI exists).
   *   Retrying/repairing tasks (no Repair UI exists).
   *   Generating/downloading patches (no UI exists).
   *   Creating Pull Requests (Button exists, completely broken/unwired).

## 9. API-to-UI mapping

| Method | Endpoint | Frontend caller | Route/page | Purpose | Implemented? |
| ------ | -------- | --------------- | ---------- | ------- | ------------ |
| GET | `/api/v1/auth/github/login` | `handleGithubLogin` | `/login` | Get OAuth redirect URL | Yes |
| GET | `/api/v1/auth/me` | `useEffect` | `AppShell.tsx` | Validate token / get user | Yes |
| GET | `/api/v1/auth/workspaces/current/provider` | `fetchConfig` | `/settings/provider` | Get LLM config | Yes |
| PUT | `/api/v1/auth/workspaces/current/provider` | `handleSave` | `/settings/provider` | Update LLM config | Yes |
| GET | `/auth/workspaces` | `fetchWorkspaces` | `/settings/workspaces` | Get organizations | Yes |
| POST | `/auth/workspaces` | `handleCreate` | `/settings/workspaces` | Create organization | Yes |
| GET | `/api/v1/repositories/imported` | `useEffect` | `/`, `/repositories/[id]` | List imported repos | Yes |
| GET | `/api/v1/repositories/github-repos` | `fetchGithubRepos`| `/repositories` | List GitHub remote repos | Yes |
| POST | `/api/v1/repositories/import` | `handleImport` | `/repositories` | Import repo | Yes |
| POST | `/api/v1/memory/repositories/{id}/index`| `handleIndex` | `/repositories/[id]` | Start memory indexing | Yes |
| GET | `/api/v1/plans` | `fetchRuns` | `/tasks`, `/repositories/[id]` | List plans/runs | Yes |
| POST | `/api/v1/repositories/{id}/plans`| `handleCreatePlan`| `/repositories/[id]` | Create new AI plan | Yes |
| GET | `/api/v1/plans/{id}` | `fetchPlan` | `/tasks/[id]` | Get plan details | Yes |
| POST | `/api/v1/plans/{id}/approve` | `handleApprove` | `/tasks/[id]` | Approve plan | Yes |
| POST | `/api/v1/executions/plans/{id}` | `handleExecute` | `/tasks/[id]` | Start execution | Yes |
| GET | `/api/v1/executions/{id}` | `fetchExecution` | `/tasks/[id]` | Get execution status | Yes |
| GET | `/api/v1/executions/{id}/logs` | `fetchExecution` | `/tasks/[id]` | Get execution logs | Yes |
| GET | `/api/v1/executions/{id}/mutations`| `fetchExecution` | `/tasks/[id]` | Get applied file changes | Yes |

**Missing Backend Endpoints in UI**:
*   `/api/v1/patch/*` (Patch generation, accept, reject)
*   `/api/v1/verification/*` (Verification jobs)
*   `/api/v1/context_engine/*` (Memory context snapshots, interactions)
*   `/api/v1/organizations/*` (Extensive RBAC, invitations, suspending, renaming orgs - completely missing from UI)

## 10. Status vocabulary

| Domain | Status | Where displayed | Actions |
| ------ | ------ | --------------- | ------- |
| Repositories | `READY`, `FAILED`, (Blank) | `/`, `/repositories/[id]` | `READY` allows Create Plan / Index. |
| Indexing | `COMPLETED`, `PARSING`, `SCANNING`, `PENDING`, `FAILED` | `/repositories/[id]` | Visual status only. |
| Plans | `PENDING_APPROVAL`, `APPROVED` | `/tasks/[id]` | `PENDING_APPROVAL` allows Approve. `APPROVED` allows Execute. |
| Executions | `PENDING`, `COMPLETED`, `FAILED` | `/tasks/[id]` | `COMPLETED` shows mutations. |

## 11. Problems and incompleteness

*   **Dead buttons / UI Only**: "Reject" plan (`/tasks/[id]`), "Create Pull Request" (`/tasks/[id]`), "Settings" (`/settings/workspaces`), "Members" (`/settings/workspaces`).
*   **Navigation Limitations**: No sidebar links to Organization Settings or Verification. No sub-tabs for Settings sections; users have to manually navigate or guess URLs.
*   **Unreachable features**: Revisions (revise plan endpoint exists, but no UI). Patches (endpoints exist, no UI). Verification (endpoints exist, no UI).
*   **Hardcoded / Hacks**: `window.location.reload()` is used to switch workspaces. Fetching lacks a unified interceptor, meaning `X-Organization-Id` and `Authorization` headers are manually copy-pasted across every component.
*   **Error States**: Very minimal. Most use browser-native `alert()` or just fail silently with `console.error`.
*   **Loading States**: Polling is heavy-handed. Every 2 seconds for executions, every 5 seconds for repos. Can cause UI flickering.

## 12. Final consolidated product map

### Global navigation
*   Dashboard
*   Repositories
*   Runs
*   Settings

### Repository workspace tabs
*   *None. Rendered as a single long page.*

### Plan workspace tabs
*   *None. Rendered as a split-view page (Task Graph | Execution Logs).*

### Run workspace tabs
*   *None.*

### Verification tabs
*   **MISSING ENTIRELY**

### Settings sections
*   AI Provider (`/settings/provider`)
*   Workspaces (`/settings/workspaces`)

### Primary actions
*   Login with GitHub
*   Import Repository
*   Index Codebase
*   Create Plan
*   Approve Plan
*   Start Execution
*   Save LLM Configuration
*   Create Workspace

### Secondary actions
*   Switch Workspace
*   Sign Out
*   Search Runs (Local filter)

### Destructive actions
*   *None are implemented in the UI. (Repo deletion and Org deletion endpoints exist in API but not accessible).*

### Missing but backend-supported UI
*   Plan Revision
*   Plan Rejection
*   Patch Generation & Download
*   Verification Triggering & Results
*   Context/Memory Inspection
*   Organization Roles & Invitations

### UI-only elements
*   Reject Plan button
*   Create Pull Request button
*   Workspace Settings button
*   Workspace Members button
