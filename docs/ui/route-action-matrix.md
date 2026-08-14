# Forge UI Route and Action Matrix

| Route | Screen | Control | User action | API/service | Loading | Success | Error | Permission |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/` | Dashboard | "Import Repository" Button | Redirects to import screen | N/A | Fast | Navigates | None | Auth required |
| `/` | Dashboard | Repository Card | Redirects to Repo detail | `GET /api/v1/repositories/imported` | Spin/Skeleton | Display | None | Auth required |
| `/login` | Login | "Continue with Github" | Initiates OAuth | `GET /api/v1/auth/github/login` | Redirecting | OAuth redirect | Log failure | None |
| `/repositories` | Import | Search Input | Client-side filter | N/A | None | Filtered | None | Auth required |
| `/repositories` | Import | "Import" Button | Imports github repo | `POST /api/v1/repositories/import` | Button Spinner | Nav to `/` | Alert Modal | Auth required |
| `/repositories/[id]` | Repo Details | Tab Selector | Switches view (Overview/Memory/Plans/Runs) | N/A | Fast | Render Tab | None | Auth required |
| `/repositories/[id]` | Repo Details | "Index Codebase" | Triggers memory indexing | `POST /api/v1/memory/repositories/[id]/index` | Button disable | Status update | Alert | Auth required |
| `/repositories/[id]` | Repo Details | "Plan Task" Button | Creates new engineering plan | `POST /api/v1/repositories/[id]/plans` | Spinner | Nav to Plan | Alert | Auth required |
| `/tasks` | Runs List | Search Input | Filters plan intents | `GET /api/v1/plans` | Table load | Filtered | None | Auth required |
| `/tasks/[id]` | Task Details | Tab Selector | Switch between Plan/Execution | N/A | Fast | Tab Switch | None | Auth required |
| `/tasks/[id]` | Task Details | "Approve Plan" | Approves a task plan | `POST /api/v1/plans/[id]/approve` | Button spin | State change | Console err | Auth required |
| `/tasks/[id]` | Task Details | "Start Execution" | Begins execution engine | `POST /api/v1/executions/plans/[id]` | Loading | Exec Log load | State fail | Auth required |
| `/settings/provider` | Settings | "Save Config" | Saves LLM provider config | `PUT /api/v1/auth/workspaces/current/provider` | Button spin | Success Msg | Console err | Auth required |
