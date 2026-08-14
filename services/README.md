# Domain services

Forge organizes backend behavior by capability. Each service owns its API schemas,
workflow logic, and event handling while relying on `packages` for shared infrastructure.

| Service | Responsibility |
| --- | --- |
| `auth` and `organizations` | Identity, authorization, organization membership, and tenant context |
| `repository_import` | Repository scanning, classification, manifests, and import jobs |
| `repository_memory` | Parsed symbols and repository knowledge retrieval |
| `planning` | Plan creation, dependency graphs, and approval state |
| `execution` | Git workspaces, patch application, and sandbox runtimes |
| `verification` | Check dispatch, results, and repair coordination |
| `context_engine` | Prompt context assembly and sandboxed template rendering |
| `patch` | Patch review and GitHub publication workflow |
| `github` | GitHub webhook ingestion |
| `audit` | Tenant-visible audit records and worker processing |

The API layer validates requests and establishes tenant identity. Long-running work is
published through the transactional outbox and consumed by the worker. Service code must
preserve organization scoping in both HTTP queries and background jobs; a worker event is
not an authorization bypass.

Avoid circular service imports. When a workflow crosses capability boundaries, prefer a
small public interface or a typed event and keep persistence details in `packages/database`.
