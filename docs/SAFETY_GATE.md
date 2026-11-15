# Forge Safety Gate

Safety Gate v1 enforces a small capability catalog at Forge's existing worker and publication boundaries. It is local implementation work, not a claim that hosted Forge or every agent operation is safe. The principal threats are model-controlled plan nodes, path and command injection, stale organization permissions, stale workers, credential leakage, and unauthorized GitHub publication. The threat model follows [OWASP Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/) and the [OWASP AI Agent Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html).

## Effective policy

The platform registers three capabilities: `repository:write`, `command:execute`, and `patch:publish`. Only the real `edit_file` and `command` worker nodes and approved patch publication map to them. An unknown action or capability is denied. Platform restrictions block protected paths, shell operators, unsupported executables, and sandbox network access without an enforceable egress mechanism. Organization and repository policies can **deny** registered capabilities; they cannot override platform restrictions. Policy conflicts resolve to the most restrictive decision. The policy has no executable expressions or model-provided rules.

An organization policy revision stores its version, denied capabilities, optional repository UUID to denied-capability mappings, emergency-stop state, creator, and timestamp in `safety_policies`. Rows are append-only and tenant RLS is forced. A new execution stores its immutable starting snapshot in `execution_jobs.safety_policy_snapshot`. At each node, the worker evaluates both that snapshot and the latest organization revision. A later expansion cannot grant an active execution a new capability; a later restriction or emergency stop blocks it. Legacy executions with no snapshot receive the then-current policy on their next claim. A malformed or unavailable policy fails the operation.

The decision contains `ALLOW`, `DENY`, or `REQUIRES_APPROVAL`, reason, capability, risk tier, policy version, and timestamp. Only registered operations can be allowed. `patch:publish` is critical and requires the existing human patch approval. Agent-produced identity or approval claims are never used. Policy update and stop endpoints require the existing workspace settings write permission; viewers and members cannot use them.

## Actual enforcement boundaries

| Boundary | Enforced behavior | Remaining limit |
| --- | --- | --- |
| Execution worker | Rechecks policy before each `edit_file` or `command` node; unknown nodes fail; records a decision before invoking the tool. | A running command is interrupted by the cancellation watcher, normally within one second after emergency stop; already completed side effects cannot be undone. |
| PatchEngine | Rejects traversal, protected paths and symlinks. On the Linux worker, directory-descriptor traversal with `O_NOFOLLOW` prevents a path-swap write outside the worktree. | Windows local process fallback checks paths but lacks the Linux descriptor guarantee. |
| Command dispatch | Parses a simple command into argv and executes it directly. Shell syntax, `sudo`, Docker CLI, destructive Git, package installation, and unsupported commands are denied. Commands cannot run if recognized credential files are present in the worktree. | An allowed interpreter or package script can still execute arbitrary code *inside* the restricted sandbox; command parsing is not a general code sanitizer. Arbitrary secret content in ordinary source files is not detected. |
| Docker sandbox | `--network none`, non-root user, read-only root filesystem, dropped capabilities, `no-new-privileges`, CPU/memory/PID limits, bounded output and timeout, one execution workspace mount, no Docker socket. Explicit environment variables are allowlisted. | The trusted worker still controls the host Docker daemon socket. Rootless Docker or a dedicated execution host would reduce this host trust boundary; test cgroup behavior before adopting rootless mode. See [Docker Engine security](https://docs.docker.com/engine/security/) and [rootless mode](https://docs.docker.com/engine/security/rootless/). |
| Local process sandbox | Does not inherit Forge secrets in its process environment. | It is for local development; it is not a hostile-code isolation boundary. Use the Docker worker for untrusted plans. |
| Patch publication | Rechecks current policy before GitHub credential access. Existing human approval is bound to the patch review digest, execution, repository, reviewer and passing verification; the publisher rechecks them before remote actions. | No new generic approval queue exists. Agent-originated high-risk operations beyond this existing publication flow are denied or unsupported. |

Network egress is disabled for the Docker sandbox. There is no destination allowlist, proxy, DNS redirect inspection, or package-registry egress control; those require dedicated host or network infrastructure. No claim of unrestricted network support is made. The worker's Docker socket must never be mounted into agent containers.

## Emergency stop and evidence

`POST /api/v1/safety/emergency-stop` appends a stopped policy version and records `safety.emergency_stop` on active execution timelines. New API executions are rejected. Workers recheck the revision before each operation; the running-execution watcher records cancellation intent and interrupts the sandbox. `POST /api/v1/safety/resume` appends another version. Resume permits *new* executions; an old snapshot never gains capabilities that it lacked at creation.

Flight Recorder stores safe decision metadata: capability, risk, policy version, reason code, and an action SHA-256 digest. It does not store full command arguments, credential values, or policy internals. Events include `safety.policy_resolved`, `safety.permission_granted`, `safety.permission_denied`, `safety.approval_required`, `safety.policy_changed`, and `safety.emergency_stop`. Existing patch approval and publication events remain the evidence for the human step.

## API and UI

All endpoints require an authenticated session and `X-Organization-Id`:

| Route | Permission | Purpose |
| --- | --- | --- |
| `GET /api/v1/safety/policy` | Workspace settings read | Current effective restrictions and stop state |
| `GET /api/v1/safety/history` | Workspace settings read | Last 50 immutable revisions |
| `PUT /api/v1/safety/policy` | Workspace settings write | Replace organization and repository deny lists |
| `POST /api/v1/safety/emergency-stop` | Workspace settings write | Stop new work and signal active workers |
| `POST /api/v1/safety/resume` | Workspace settings write | Resume new work after review |

The settings UI at `/settings/safety` shows current version, capability restrictions, history, and confirmed stop/resume controls. Repository-specific restrictions are available through the API; the UI currently preserves them when saving organization restrictions. Patch approval and publication remain in the existing task workspace.

## Validation and gaps

For a local integration run, start only the documented Compose dependencies with `docker compose up -d postgres redis`, then apply `docker compose run --rm migration` before starting the API and Docker-capable worker with `docker compose up -d api worker`. Use a dedicated development Docker host and keep its socket accessible only to the trusted worker. Do not use `docker compose down -v` on an existing installation. Production must apply Alembic head `a3f9c2b7d610` before updated API and worker images start, retain PostgreSQL RLS, provide the existing database/Redis/OAuth secrets through the host's secret configuration, and provision a separate Docker-capable worker. The Vercel frontend and ordinary Render web service cannot execute agent containers.

The policy API and UI require an authenticated organization owner or admin for updates and emergency stop. To validate the stop path, run a long command in a disposable execution, call the stop endpoint as that administrator, and confirm the job becomes `CANCELLED` and its sandbox is removed. The local Docker integration test exercises this path through the persisted policy revision and worker watcher; it does not exercise a hosted OAuth browser session.

The Safety Gate tests cover deterministic decisions, policy versioning and RLS, protected paths, symlink-swap resistance on Linux, shell-injection denial, real Docker-worker denial before mutation, sandbox environment isolation, and existing worker/Bench behavior. A denial test asserts that no unauthorized file or mutation exists and that Flight Recorder recorded the denial.

The following remain outside this v1 slice: a generic pending-approval inbox and one-time approval tokens for new agent tools; full destination-level egress control; guaranteed secret detection in arbitrary source files; a hostile-code guarantee for Windows local execution; a hosted worker security assessment; and rootless Docker validation. Do not add a new high-impact agent tool until it has an exact-action, durable approval and an operation-boundary test. Do not claim the complete Safety Gate objective is met by policy evaluation alone.
