# Forge Verification Intelligence

## Implementation plan

1. Reuse the execution's immutable Context Lens change set and exact clean Atlas base snapshot. Rank changed tests and reverse graph test associations; mark new code, missing/stale graphs, and cross-cutting paths as uncertain.
2. Persist one versioned, tenant-scoped, append-only decision per verification job. Store suggested tests, configured verifier decisions, digest, fallback reason, and snapshot reference. Keep actual outcomes in existing verification jobs/results and Flight Recorder events.
3. Only narrow existing `forge.yaml` test verifier entries when each has one explicit, safe Python test-file target, every suggested test has such an entry, and no risk fallback applies. Run other configured checks as before. Never construct or execute commands from graph data.
4. Expose authenticated read/preview data and a small task-workspace view. Test selection semantics, PostgreSQL RLS/immutability, API tenant scope, worker behavior, migrations, builds, and dependency findings.

## Evidence boundary

Atlas associations suggest relevance, not execution or coverage. The base snapshot cannot describe newly added code. A verifier command's persisted result proves only that command's exit status; Forge has no trusted per-test-case parser. Existing Safety Gate, sandbox, approval digest, and publisher remain the enforcement boundaries.

## Sources of truth and lifecycle

The worker commits `MutationModel` rows after its lease fence, then queues a `VerificationJobModel`. At that point `VerificationDispatcher` prepares the existing `PatchModel` and immutable Context Lens change set in the same transaction, if reviewable mutations exist. The review digest is calculated from the pinned execution base commit and ordered mutation diffs. Command-only executions and older jobs have no change-set-backed selection plan and retain the existing verifier behavior. The UI's later patch-generation request returns the already prepared patch. A malformed patch cannot be approved or published; its metadata is validated before the patch object enters the session.

One `verification_plans` row is written per verification job when a Context Lens change set exists. It stores organization, repository, execution, verification job, change set, base commit, patch digest, version, creation time and bounded JSON decision. The new migration `f2c7d4e9a110` follows Context Lens head `e1b4c8d29070`. It adds a composite tenant/repository foreign key, unique job association, forced tenant RLS and an append-only trigger. Replayed requests return the existing job and decision. The decision is historical; a later mutation or patch change does not rewrite it.

`verification.plan_selected` is written to Flight Recorder in the same transaction as the plan and outbox request. The existing verifier writes check start, pass/fail and completion events; a deliberately deferred configured check writes `verification.check_skipped` and a `SKIPPED` result without starting a sandbox command. A selected check with no result remains queued, running, cancelled or never executed according to the actual job state. A stale digest or changed verifier configuration blocks the job before a command runs. No selector decision grants an execution capability or publication approval.

## Selection and fallback

The selector reads only the Context Lens file-change metadata and its exact clean, published **base** Atlas snapshot. It adds a directly changed test file at high confidence. It traverses reverse Atlas relationships for other test files with bounded depth three, at most 10 source paths and 40 impact results per path. Each suggestion records its path, source path, confidence, scope, rank and reason code. An import or test edge is a relevance clue, not proof that the test covers the changed lines. The response is capped at 100 suggestions. Missing snapshot, graph truncation, and newly added or deleted paths retain uncertainty.

Broad configured verification is mandatory for auth, Safety Gate, execution, verification, database, migration, GitHub publication, shared infrastructure, CI, Docker, dependency or deployment configuration changes; for missing, unresolved or truncated Atlas evidence; for new/deleted/unmapped files; for low-confidence or partial test mappings; and when no test association exists. An absent test verifier or a command that cannot be tied to one explicit file also forces broad configured checks. These conditions appear as reason codes in the decision. Forge does not invent test commands from Atlas paths.

Selective execution is limited to existing enabled `forge.yaml` Python `pytest` commands that each name exactly one safe test file. Every suggested test must have a matching configured verifier. The plan links each selected verifier to its explicit target and reason. Other enabled format, lint, typecheck, build and security checks always run. Unrelated explicit test-file verifiers are recorded as deferred and produce a `SKIPPED` result. More than 100 enabled verifiers blocks the job before execution and keeps the decision bounded. JavaScript/TypeScript commands and broad `pytest` commands currently run in full because Forge has no reliable target-to-command mapping for them. The worker executes the unchanged configured argument vector in the existing network-disabled Docker sandbox, with each configured timeout clamped to 1–300 seconds and the sandbox's existing CPU, memory, process and output limits. No model call or new queue is introduced.

The existing `forge.yaml` verifier registry is repository supplied. Verification Intelligence does not make those commands trusted; operator review of verifier configuration remains necessary. Forge Bench's private tests are not present in its agent-visible fixture or Atlas graph, so the selector correctly falls back rather than claiming to have discovered or run them.

## API and workspace

Both routes require the existing authenticated `exec:read` permission and verify execution/repository ownership within the active organization:

- `GET /api/v1/verifications/executions/{id}/intelligence/preview` is read-only. A prepared change set is required. It returns candidate paths, risk fallbacks, snapshot identity and current-digest state, but does not inspect worker-only verifier configuration or claim that a command was selected.
- `GET /api/v1/verifications/executions/{id}/intelligence` returns the latest job, immutable plan if present, Flight Recorder decision-event reference, at most 100 actual command results and a truncation flag. It omits stdout, stderr, source, command arguments, secrets and host paths. A missing plan is explicit. `current` compares the persisted patch digest with current mutations without altering historical outcomes.

The task workspace embeds a Verification Intelligence card in Context Lens. It shows changed scope, suggested tests and reasons, selected/deferred configured checks, fallback reasons, job state and actual command results. It does not label a suggested test as executed or claim coverage. Loading, authorization errors, retries and refresh have separate states.

## Operations, performance and limits

Apply Alembic head before deploying updated API or worker images. API and worker must share PostgreSQL and the same code revision. The worker also needs the existing repository workspace, Redis and Docker sandbox infrastructure. Vercel and an ordinary Render web service cannot execute repository checks. No hosted service has been validated by this work.

The API reads persisted rows and bounded Atlas data; it does not reindex a repository. A verifier configuration fingerprint and recomputed digest prevent a stale selection from silently executing. Existing results may still be command-level only, so a zero exit code is not converted into individual test-case success or a coverage percentage. A missing `forge.yaml` may leave a job `NOT_CONFIGURED`; the plan records that gap. The existing publication gate still uses its verification job state and digest-bound human approval.

Local tests use disposable PostgreSQL and a mocked sandbox for selection-specific dispatch behavior. They do not prove a hosted Docker worker, real repository test run, browser session, or external publication. Two local ASGI/PostgreSQL reads of the same small fixture took 171.3 ms and 34.7 ms, each returning 1,174 bytes (2026-11-13). These are diagnostic samples, not a load or hosted latency guarantee.

## Local validation and deployment notes

On 2026-11-13, the final full backend suite without optional infrastructure had 196 passed, 72 skipped, and 22 warnings. Focused Verification Intelligence and Context Lens PostgreSQL integration had 4 passed, 48 warnings; the selection test used a mocked sandbox. A broader PostgreSQL run had 16 passed, 7 skipped and one Atlas API 503 because its rate limiter had no Redis. With an isolated Redis service supplied, that Atlas tenant test passed and the existing outbox/Atlas queue tests had 3 passed. The 503 was an infrastructure-dependent test result, not a corrected authorization assertion.

A fresh disposable database upgraded to the single Alembic head `f2c7d4e9a110`; `alembic check` reported no pending operations. A seeded pre-intelligence database upgraded from `e1b4c8d29070` and retained its patch and organization/repository/execution relationships. Focused Ruff and Pyright passed. The frontend lint, TypeScript check and production Docker build passed; API and worker images built, and `docker compose config --quiet` passed. The frontend's current lockfile returned zero advisories from `npm audit` in a local Node container. An earlier build had reported six moderate advisories, but the current audit no longer returns package records for them; no frontend dependency or lockfile was changed for this feature.

Docker Desktop uses the `desktop-linux` context and keeps its WSL data disk at `D:\Docker\WSL\disk\docker_data.vhdx` on this machine; `/var/lib/docker` is the daemon's path inside Linux. The disposable PostgreSQL and Redis containers were left intact. A real shared-workspace Docker worker run, local signed-in browser journey, and hosted validation remain outstanding. Run those before treating selected checks or publication as production-proven.
