# Changelog

All notable changes to Forge AI will be documented in this file.

## [Unreleased]

### Changed

- Consolidated API and worker container definitions under `docker/` and aligned Compose with the canonical paths.
- Organized active UI references separately from archived UI-overhaul reports.
- Categorized operational and diagnostic scripts and removed obsolete one-off maintenance helpers.
- Replaced repository ignore rules with coverage for Python, Next.js, Playwright, local runtime data, caches, and secrets.
- Added contributor, security, pull request, dependency automation, and CI maintenance configuration.
- Fact-checked the root README against current versions, routes, environment variables, and validation commands.

### Security

- Excluded local environment files and Forge runtime data from Git and Docker build contexts.
- Removed the insecure production-secret fallback from the production configuration path; Compose defaults remain development-only and production validation rejects them.

## [v0.1.0-alpha.1] - Full Internal Alpha

### Added
* **Repository Import Workflow:** HTTP-based repository import workflow.
* **Repository Memory:** Tree-sitter parsing for supported languages. Symbol and graph-memory persistence.
* **Planning Engine:** Planning DAG creation and approval workflow.
* **Execution Engine:** Controlled execution through `LocalProcessSandbox` for trusted development fixtures.
* **Verification Engine:** Verification dispatch for supported checks.
* **Context Engine:** Jinja2 sandboxed prompt rendering.
* **Security:** Tenant-aware HTTP and database access controls (PostgreSQL RLS).
* **Worker:** Redis Streams and outbox worker reliability for async tasks.
* **Frontend:** Canonical Next.js frontend with browser E2E verification.
* **Plugin System:** MCP stdio JSON-RPC communication.

### Limitations at release time
* **DockerSandbox:** Blocked due to unavailability of the Docker daemon.
* **FirecrackerSandbox:** Deferred.
* **Untrusted Execution:** `LocalProcessSandbox` must not be used for arbitrary or untrusted repositories.
* **External Beta / Production:** Not accepted or ready.
