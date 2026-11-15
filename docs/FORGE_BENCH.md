# Forge Bench

Forge Bench v1 is a deterministic **infrastructure demonstration**. It runs pinned coding tasks through Forge's existing PostgreSQL outbox, Redis Streams, execution worker, per-attempt Git worktree, Docker sandbox, Flight Recorder, and an independent Docker grader. It does not invoke a model provider and does not measure coding-model quality. The deterministic planner knows the fixture solutions; its scores must not be used as model benchmarks.

## Architecture and data

`bench/core-v1.json` defines the suite ID, version, pinned fixture commit, public task instructions, budgets, and private check references. `bench/fixture/` is the agent-visible repository. `bench/private/test_cases.py` contains independent grader checks; `bench/private/solutions.py` supplies the deterministic demo plans. Only fixture files are copied into a trial's repository workspace. Hidden tests and solutions are never copied there or returned by the suite API.

Every run stores an immutable manifest and dataset digest. The SHA-256 digest covers the canonical suite JSON and private tests. Each trial records its task version, repetition, execution ID, attempt generation, pinned base commit, exact candidate workspace fingerprint, check results, raw measurements, scorer version, and Flight Recorder execution ID. The `benchmark_runs` and `benchmark_trials` tables use tenant RLS; a PostgreSQL trigger prevents changing a result or patch digest once recorded. Submission uses a caller-provided UUID idempotency key. One active run per organization is enforced by locking its organization row. A run contains at most 24 trials and at most three repetitions per task. Trials execute sequentially.

The worker materializes a deterministic Git repository at the pinned commit, creates a normal approved Forge plan and execution job, then publishes `execution.requested` through the existing outbox. The ordinary worker owns the execution lease, runs the plan in its attempt worktree, creates mutations, and emits normal execution events. The completion event triggers grading. Duplicate completion delivery returns the existing trial result. The next trial is scheduled through another outbox event. A cancelled run cancels pending trials and requests cancellation of its active execution.

The grader checks the base commit and candidate fingerprint, runs private `unittest` cases in the existing restricted `DockerSandbox`, and verifies that the candidate fingerprint did not change. The candidate workspace is mounted read-only. Private tests are transferred into a root-owned directory in the grader container after agent execution and are loaded ahead of candidate paths. Docker network access is disabled, CPU and memory are bounded by Forge's sandbox defaults, each command has a 30-second timeout, and sandbox output is capped by the existing 64 KiB limit. Only output SHA-256 hashes, bounded durations, exit codes, and check statuses are stored; raw stdout/stderr and secrets are not stored in benchmark rows. The grader also checks the allowed patch scope and protected paths. This is objective grading, not a security certification.

## Scoring

Scoring algorithm version 1 uses fixed weights: correctness 45%, regression prevention 20%, patch quality 10%, execution reliability 10%, efficiency 10%, and safety 5%. A dimension with no evidence is `null` in the breakdown; it contributes no points to the weighted total. Correctness and all required checks must pass for the trial to pass. A failing required check caps the score at 49/100, regardless of speed. Efficiency is `max(0, min(100, 100 × (budget_ms - duration_ms) / budget_ms))` when both measurements exist. The safety dimension currently checks protected file paths; it does not certify all sandbox behavior.

Run averages include every scored trial and assign zero to agent executions that failed before grading. Infrastructure errors and user cancellations are shown separately and excluded from the agent-score denominator. The API reports the denominator, pass rate, median, variation, duration, token availability, and failure distribution. Small samples do not imply statistical confidence. A comparison requires the same dataset digest and selected task versions; it reports score, pass-rate, duration, token, and dimension deltas. A baseline is a reference to an earlier compatible run; it never rewrites either result.

Token counts, provider latency, exact monetary cost, and resource peaks are unavailable in the deterministic demo and are represented as `null`, not invented zeroes. The run manifest records a SHA-256 fingerprint of the deterministic solution source, tool configuration fingerprint, Forge version, model/provider identifiers (`deterministic` / `fixture-oracle-v1`), sandbox image tag, task budgets, grader/scorer versions, and `null` where a random seed or prompt revision is unavailable. It stores no provider API key or secret environment values.

## Initial suite

| Task | Category | Difficulty | Independent behavior |
| --- | --- | --- | --- |
| `clamp-boundary` | Bug fix | Easy | Inclusive upper and lower bounds |
| `port-validation` | Bug fix | Medium | Decimal TCP port validation |
| `slug-normalization` | Feature | Easy | Trim and collapse whitespace |
| `divide-zero` | Regression | Easy | Zero denominator with normal division preserved |
| `state-transition` | Reliability | Medium | Valid state transitions only |
| `row-parsing` | Bug fix | Medium | Blank lines and cell trimming |
| `stable-dedupe` | Regression | Medium | First-seen order preserved |
| `retry-cap` | Reliability | Medium | Bounded retry delay |
| `runtime-selection` | Repository understanding | Medium | Correct language selector and unsupported input |
| `output-limit` | Bug fix | Easy | Exact byte limit and negative input |
| `api-port-contract` | Multi-file | Hard | API default and shared port parser |
| `worker-retry-contract` | Multi-file | Hard | Worker schedule and shared delay |

Each task has a correctness check, a regression check, a scope check, a known expected outcome, a pinned base revision, and a 120–180 second default budget. A task is graded only against its own check class. The fixture deliberately contains defects outside the current task; a task score does not mean the whole fixture repository is correct.

## API and UI

All `/api/v1/bench` routes require an authenticated session and `X-Organization-Id`. Owners and admins can create and cancel runs; members and viewers have read access. Create and cancel requests use Forge's existing user and organization rate limits.

| Route | Purpose |
| --- | --- |
| `GET /suites`, `GET /suites/{id}` | Discover version and public task list |
| `GET /suites/{id}/tasks/{task_id}` | Read one public task definition |
| `POST /runs` | Create an idempotent deterministic demo run |
| `GET /runs?cursor=&limit=` | Cursor-paginated history |
| `GET /runs/{id}`, `GET /trials/{id}` | Status, evidence, and results |
| `POST /runs/{id}/cancel` | Cancel pending and active work |
| `GET /runs/{id}/export` | Export JSON manifest and results |
| `GET /compare?left=&right=` | Compare compatible runs |

Example request body: `{"suite_id":"forge-core-v1","task_ids":["clamp-boundary"],"repetitions":1,"budget_seconds":60,"idempotency_key":"<new UUID>"}`. The authenticated caller must supply the organization header; do not place a session token in a URL. The UI at `/bench` lists tasks and recent runs, starts a deterministic run, and links to `/bench/{run_id}` for live status, check results, comparison, export, cancellation, and the existing execution/Flight Recorder page. It does not fabricate progress.

## Local demonstration

1. Use a disposable local PostgreSQL and Redis or the project's documented `docker compose` stack. Apply `alembic upgrade head` and confirm `alembic check`. Do not run `docker compose down -v` against existing volumes.
2. Build and start the API and **Docker-capable worker** from the same local source revision. The worker and Docker host must see the same protected `WORKSPACE_ROOT`; the worker needs its existing Docker socket access. Start the Next.js frontend with `npm run dev` in `apps/frontend` and sign in to a local workspace with owner or admin permission.
3. Open `/bench`, select `clamp-boundary`, and start one trial. The run should move from `PENDING` to `RUNNING` to `COMPLETED`; the trial should be `PASSED`. Open its execution link to inspect the Flight Recorder timeline, then reload the page to verify persisted results.
4. For negative infrastructure demonstrations, the API accepts `variant: "incorrect"`, `"regression"`, or `"timeout"` only with `task_ids: ["clamp-boundary"]`. Use a fresh idempotency UUID for each run. Incorrect and regression variants must fail their respective private checks; the timeout variant must fail safely. These variants are for testing the pipeline, not measuring a model.
5. Create a second run with the same task selection and dataset digest to compare results. A run with different task IDs or a changed dataset digest is rejected as incompatible.

The automated local tests in `tests/integration/test_bench_worker_e2e.py` and `test_bench_queue_e2e.py` exercise real PostgreSQL, Redis, Forge worker execution, nested Docker sandboxing, independent grading, and persisted Flight Recorder events. They require disposable services, a Docker socket, and a workspace volume mounted at the same absolute path for the worker and Docker daemon. Browser testing requires a configured local OAuth session; mocked browser responses are not evidence of a working end-to-end benchmark.

## Adding a task

Before publishing a suite version, add a unique entry to `bench/core-v1.json`, add independent correctness and regression methods in `bench/private/test_cases.py`, and add a deterministic plan in `bench/private/solutions.py`. Keep all grader-only assertions and solutions out of `bench/fixture/`. If the fixture source changes, regenerate and record its deterministic base commit (Git author/committer `Forge Bench <bench@forge.invalid>`, timestamp `2024-01-01T00:00:00Z`, non-executable file modes) and rerun all task checks. No scoring or execution worker code needs to change for a new task.

After a suite is published, preserve the old manifest and private checks, create a new version and dataset digest for changes, and keep old workers available while runs of the old version are active. The current v1 loader exposes one checked-in suite; automatic multi-version discovery and historical suite execution are not yet implemented. Editing v1 during an active run fails closed on dataset-digest mismatch rather than silently grading against changed rules.

## Deployment and limits

The Vercel frontend and Render Free API can display Bench, but runs cannot progress without Forge's separate Docker-capable worker. The same PostgreSQL, Redis, dataset, and code revision must be available to API and worker. The Render service does not host the worker or its sandbox. Upstash Free's command quota is unsuitable for Forge's continuously polling worker, as described in `DEPLOYMENT.md`. Do not expose the Docker socket or grader fixtures to the public internet.

Only the deterministic infrastructure mode is implemented. Configured live model evaluation, provider token/cost capture, automatic multi-version suite registry, browser E2E against a signed-in local stack, and hosted execution are not yet validated. A model-quality score or a comparison between models requires those pieces and actual comparable model runs; deterministic demo results must never be represented as such.

Issue-to-PR also has a separate versioned invariant catalog in `bench/issue-to-pr-cases-v1.json`, run by `bench/run_issue_to_pr_cases.py`. It reuses the existing Bench convention of deterministic, checked-in fixtures, while exercising workflow tests against disposable services. Its pass/fail cases do not enter `forge-core-v1` scores, trials, comparisons, or model-quality claims. See `docs/ISSUE_TO_PR.md` for its coverage and environment requirements.
