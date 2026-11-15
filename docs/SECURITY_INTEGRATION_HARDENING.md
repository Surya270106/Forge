# Security and integration hardening — 14 November 2026

## A. Executive summary

This review covered the uncommitted Forge worktree, its API, browser proxy, PostgreSQL schema and row-level security (RLS), Redis queues, Docker worker, evidence records, and deployment/CI configuration. It preserved the existing Git history and hosted services. The production Python lock was updated to patched versions, the OAuth browser state was bound to a short-lived HTTP-only cookie, and the session loading screen now has an explicit timeout state. The PostgreSQL/Redis backend suite and a real local Docker worker run passed. Hosted OAuth, hosted worker operation, and GitHub publication were not tested.

The original state was 57 modified tracked files, 294 untracked files, and no staged files at `99151ea250b56be7a2d0b208f7e6a7c626d817be` on `codex/deployment-only`. This work adds to those uncommitted changes. Nothing was staged or committed.

## B. Dependency findings

The audit exported the production dependency set pinned by `uv.lock` and ran `pip-audit -r <export> -f json`. The initial 46 **records** were in eight packages; repeated IDs mean these are not 46 independent exploit paths. A fresh scan of `uv export --no-dev --frozen --no-emit-project --no-hashes` returned **zero findings** after the lock update. `pyproject.toml` constraints were unchanged. Versions below are lockfile versions.

| Package | Before → after | Recorded advisory IDs | Verified severity | Direct or transitive / Forge exposure | Assessment |
| --- | --- | --- | --- | --- | --- |
| aiohttp | 3.14.3 → 3.14.4 | CVE-2026-111064, -123817, -111063, -111750, -111066, -111749, -111065, -111748 | Not established here | Transitive through LiteLLM; HTTP client may be used by provider calls. Aiohttp server behavior is not a Forge API entry point. | Patched; reachability of individual advisories unverified. |
| multidict | 6.7.1 → 6.9.1 | PYSEC-2026-4244 | Not established here | Transitive through aiohttp/yarl. | Patched. |
| certifi | 2026.6.17 → 2026.10.18 | PYSEC-2026-4320 (recorded twice) | Not established here | Transitive HTTP trust store; outbound calls may use it. | Patched. |
| cryptography | 49.0.0 → 50.0.0 | PYSEC-2026-3552 (recorded twice); [GHSA-g6cj-pr64-35w5](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5) | Moderate per maintainer advisory | Direct dependency; Forge uses Fernet. The advisory concerns PKCS#7, which was not found in Forge's direct use. | Patched; no vulnerable Forge path demonstrated. |
| filelock | 3.32.0 → 4.2.1 | CVE-2026-112940, -112913, -112907, -112938, -112936, -112910, -112909, -112911, -112939, -112915, -112935, -112908 | Not established here | Transitive through Hugging Face dependencies of LiteLLM. | Patched; runtime reachability unverified. |
| LiteLLM | 1.94.0 → 1.103.1 | PYSEC-2026-4066, CVE-2026-114612, [GHSA-g5ff-637f-6q2m](https://github.com/BerriAI/litellm/security/advisories/GHSA-g5ff-637f-6q2m) | High for linked GHSA; others not established here | Direct provider client (`acompletion`). Some advisories concern the LiteLLM proxy, which Forge does not start. | Patched; new boto3/botocore and HTTP/2 transitive packages increase image size. |
| PyJWT | 2.13.0 → 2.15.0 | PYSEC-2026-4145, -4146, -4149, -4152, -4144, -4143, -4148, -4140, -4141, -4147, -4151, -4150, -4142, -4183; GHSA-pxh4-856f-4h89 | Not established here | Direct session signing and validation; Forge pins the accepted algorithm to HS256. | Patched; one initial scanner record lacked a fix version, but the final pinned audit reports zero. |
| urllib3 | 2.7.0 → 2.8.0 | PYSEC-2026-4177, -4176, -4175 | Not established here | Transitive via requests/tiktoken/LiteLLM; outbound client use is possible. | Patched. |

`yarl` also moved from 1.24.5 to 1.25.1 as part of resolution. The lock update is larger than the direct version changes because wheel metadata and LiteLLM transitives changed. The API and worker images built after the lock update, and the backend suite and local worker run exercised the updated imports. No advisory was suppressed.

`npm audit` on the frontend lock still returns six moderate development-tool records: `@typescript-eslint/eslint-plugin`, `parser`, `type-utils`, `typescript-estree`, `utils`, and `minimatch`. A fresh `npm audit --omit=dev` returned **zero**. A trial `npm audit fix --package-lock-only --ignore-scripts` on a disposable copy did not eliminate the six records; it introduced another vulnerable minimatch resolution. The real frontend manifests and lockfile were left unchanged. These findings affect lint/build tooling, not the production runtime dependency audit. Before using an untrusted repository branch in CI, review the eslint/minimatch chain and available compatible releases; this risk is **unresolved**, not accepted.

## C. Security findings

| Status | Finding and boundary |
| --- | --- |
| Fixed | The browser's OAuth exchange previously accepted a valid one-use code without proving that this browser initiated its GitHub login. The Next proxy now stores the backend-issued OAuth `state` in a 10-minute HTTP-only, SameSite=Lax cookie; the callback forwards `state`; exchange compares it before contacting the API and clears it on success. The backend still validates its own Redis-backed state and one-use exchange code. Local proxy and restricted-role tests cover the binding. Live GitHub OAuth remains unverified. |
| Fixed | A slow/aborted `/auth/me` check could leave `AppShell` on “Establishing workspace” indefinitely. The timer now shows an explicit retry state and aborts the request. Edge/Playwright confirmed the retry state after a delayed session request. |
| Mitigated | Session JWTs are checked against an active database session and user; HS256 is explicitly specified. Tenant access uses organization role checks and database RLS. Restricted-role RLS tests ran on disposable PostgreSQL. |
| Mitigated | Docker commands are constrained by workspace/path policy, capability decisions, resource and output limits, network-off default, non-root execution, cancellation, and cleanup checks. A trusted worker with Docker socket access still has host-level power. A killed process may leave an identifiable container requiring targeted operator cleanup; this was observed in safe fault tests. |
| Unverified | Hosted cookie, redirect, CORS, TLS, proxy-origin, and GitHub callback behavior; real external provider secrets; real publication. No production credentials or hosted configuration were used. |

The audit did not find a justification to disable RLS, weaken CSRF checks, or bypass patch digest approval. Sensitive mutation and evidence routes use authenticated, tenant-scoped dependencies; the worker revalidates policy around execution. A review of every tenant-owned table and every route under adversarial traffic remains a release gate, rather than a claim of complete authorization proof.

## D. Architecture and integration results

The current flow is: GitHub OAuth/session → Next same-origin API proxy → FastAPI authorization and tenant context → PostgreSQL transaction/outbox → Redis queue → fenced worker lease → isolated repository workspace → Docker sandbox → verification and patch records → Flight Recorder, Atlas, Context Lens, Verification Intelligence, Run Capsules → digest-bound human approval → GitHub publisher. The frontend reads persisted records through authenticated API routes. The API and worker share database models and event contracts; Redis delivery is retryable and processed-event IDs provide deduplication.

The disposable local worker E2E ran two tests in the first pass: five safe Python/Node pass/fail/command-fail scenarios, selected pytest verification, skipped unrelated checks, mutation/patch digest, and capsule evidence. The selected pytest/capsule test passed again on a new tmpfs PostgreSQL/Redis stack after mounting the Windows worktree at Docker Desktop's shared `/run/desktop/mnt/host/d/...` path. A prior rerun using `/workspace` as a nested Docker bind failed because the sandbox could not see `tests/test_a.py`; that was a test harness mount error, not a passing verification. The Edge/Playwright browser then used a short-lived real database session to load that successful execution from the actual local FastAPI service, read its persisted evidence and Run Capsule, reload, and display the capsule again: **1 passed**. This is a local browser → API → persisted worker-evidence integration pass. It does not include live GitHub OAuth or a browser-triggered new execution. GitHub publication tests use mocks and do not establish a successful remote contribution.

## E. Reliability

The existing tests cover outbox retries, duplicate event delivery, worker ownership/fencing, recovery, cancellation, append-only evidence, capsule integrity, and stale patch approval. The real worker run confirmed Docker command execution and persisted evidence under the patched lock. The initial full PostgreSQL/Redis run failed seven tests because the restricted test role had not yet been created and `REDIS_URL` was absent; rerunning with the documented disposable role/setup and both Redis URLs passed. CI now provisions Redis in its PostgreSQL integration job and runs the integration/rate-limit group after its RLS setup. That workflow has **not** run remotely.

One Docker sandbox test exceeded its outer five-second harness deadline on Windows Docker Desktop; measured startup was about 3.09 seconds and command timeout/cleanup about 2.19 seconds. Its production one-second command deadline and cleanup assertions were preserved; only the test's outer guard was raised to 15 seconds. With Docker access restored, the affected test passed and the complete real sandbox file passed **10/10** in 46.28 seconds. The earlier automatic approval review usage-limit rejection was temporary and did not indicate an unsafe command.

## F. Validation record

| Check (local, 14 November 2026) | Result |
| --- | --- |
| `uv export --no-dev --frozen --no-emit-project --no-hashes`; `pip-audit -r <export> -f json` before/after | 46 records in 8 packages → **0 findings** on fresh final scan. |
| `npm audit --json`; `npm audit --omit=dev --json` | Fresh scans: **6 moderate dev records**, **0 production records**. Frontend lock unchanged. |
| `pytest -q` in patched worker image, without optional infrastructure | 200 passed, 76 skipped, 23 warnings. |
| `pytest -q -ra tests` with disposable PostgreSQL, Redis, RLS and Atlas test URLs | Final rerun **242 passed, 34 skipped, 57 warnings** in 189.33 s; no failures. Prior configured run had the same counts in 61.61 s. The first underconfigured attempt had 7 environment-related failures. |
| `pytest -q tests/integration/test_worker_e2e.py` with disposable PostgreSQL, Redis, Docker socket and safe workspace | 2 passed, 4 warnings in 98.76 s. |
| Real Docker sandbox security suite | Initial outer-harness timing failure was corrected without changing sandbox timeout or cleanup assertions; focused test **1 passed**, full file **10 passed** in 46.28 s. |
| Playwright OAuth-state tests against local Next dev, API and Redis | **2 passed** with `FORGE_REQUEST_ORIGIN=http://0.0.0.0:3000`, the internal origin Next calculated behind Docker port forwarding. Missing/mismatched state denied; cookie is HttpOnly, SameSite=Lax, Max-Age=600. Live GitHub OAuth not exercised. |
| Local one-use OAuth exchange and expiry | Disposable Redis code: first exchange 200, repeat without state cookie 403, replay with state cookie 400; an expired database state was rejected at callback with 400 before GitHub access. Dummy token only. |
| Playwright signed-in persisted evidence reload | **1 passed** in 11.8 s after warming the local API route; actual FastAPI, tmpfs PostgreSQL/Redis and a prior successful Docker worker run. |
| Playwright session timeout test | **1 passed** in 21.8 s; intercepted delayed auth response produced a visible retry state. This check uses a controlled delayed response, not a live backend outage. |
| `alembic upgrade head`; `alembic check` on fresh and seeded legacy tmpfs databases | Passed; single head `a4d1e8c2b930`; no model operations pending. At legacy `c9f2a6b8d741`, a seeded accepted patch retained digest, reviewer, execution and plan after upgrade. Reviewer no-action foreign key exists. |
| API and worker Docker builds with patched lock | Passed in the prior phase. Final frontend Docker build passed with configured Google fonts and standalone output. |
| `node node_modules/typescript/bin/tsc --noEmit` | Passed after final frontend edits. |
| `node node_modules/next/dist/bin/next lint` | Passed with no ESLint warnings or errors after final frontend edits. |
| `node node_modules/next/dist/bin/next build` on Windows host | Failed in the earlier restricted host environment: `fonts.googleapis.com` DNS lookup failed and `.next/types` mkdir returned `EPERM`. A separate final Docker build of the same current application source passed; no source or font fallback was changed. These host errors are environmental for this run, though host permissions should be fixed before relying on a host build. |
| `docker compose config --quiet`; worker Compose with `DOCKER_GID=1000 --no-env-resolution` | Both passed without starting services or reading a production worker env file. |
| Forge CI Ruff command (`--select E,F --ignore E402,E501`) | Passed. Full Ruff rules found 63 style findings versus 66 in an archived HEAD baseline; only one current-only import-order finding in `packages/database/models/__init__.py`. No new E/F defect. |
| Pinned Pyright, production Python source | 170 files analyzed, **0 errors/warnings** with explicit Python venv. Repository-wide run including tests: **41 test-fixture type errors**, 0 warnings; no production-source errors. |
| CI YAML parse with installed `js-yaml` | Passed; six jobs, Redis service and expanded integration step present. The workflow has not run on GitHub. |
| Frontend package manifest/lock consistency | npm lockfile v3 root dependencies and devDependencies match `package.json`. |
| Added-line credential-pattern scan | No private-key, GitHub-token or embedded Postgres/Redis credential patterns in tracked diff additions or untracked source. This is a heuristic scan, not a full secret audit. |
| `git diff --check` | Passed; Git emitted only existing LF/CRLF conversion warnings. |

The 34 full-suite skips comprise **10** Docker security cases, **16** other Docker/workspace/socket/kill-path cases, **2** separately gated worker E2E cases, **4** intentionally fake-sandbox-only cases, and **2** obsolete tests. The dedicated real worker runs and 10-case Docker security run cover important gaps; Bench, cancellation, and Safety Gate Docker integration tests remain separately gated and did not run in the full suite. The 57 warnings are **15** Pydantic V2 `class Config` deprecations (future V3 compatibility), **40** PyJWT warnings from the short default *local test* key (production operators must use a strong random key of at least 32 bytes), **1** Starlette/httpx test-client deprecation, and **1** LiteLLM/Pydantic `ReadOnly` schema warning. None was suppressed. The production settings reject the unchanged default key but do not enforce a length/entropy floor on a replacement; validate the deployed key separately before launch. Test-fixture Pyright errors are quality debt; production Python source has no Pyright errors. None of these results demonstrates a passing hosted environment.

## G. Performance and resources

The local full infrastructure suite took 61.61 seconds and the two real worker tests took 98.76 seconds on this Windows/Docker Desktop machine. These are test durations, not production throughput. Docker Desktop reported data root `/var/lib/docker`, backed by the WSL VHD at `D:\Docker\WSL\disk\docker_data.vhdx` (about 15 GB when inspected); no persistent Docker volume was deleted. The LiteLLM lock change pulls additional packages and may increase API/worker image size. Free Render services can cold-start, and the previous five-second session UI timeout now surfaces a retry rather than an endless spinner. No load test or capacity claim was made.

## H. Worktree inventory and review strategy

At report drafting: 63 modified tracked files, 298 untracked leaf files, no staged files, branch `codex/deployment-only`, HEAD `99151ea250b56be7a2d0b208f7e6a7c626d817be`. Recheck these counts before any staging. This is a mixed, accumulated worktree; never stage it wholesale.

| Area | Files to review together |
| --- | --- |
| Deployment/config | `.dockerignore`, `.env.example`, `DEPLOYMENT.md`, `docker-compose.yml`, `.github/workflows/ci.yml`, `uv.lock` |
| Auth/security | `services/auth/*`, `apps/frontend/app/api/*`, `apps/frontend/app/login/callback/page.tsx`, `apps/frontend/app/components/AppShell.tsx`, `tests/security/*`, `SECURITY.md` |
| Worker/recovery/cancellation/Safety Gate | `apps/worker/main.py`, `services/execution/*`, `services/worker_recovery.py`, `services/safety/*`, related migrations/tests |
| Evidence features | `services/atlas/*`, `services/context_lens/*`, `services/verification/*`, `services/execution/flight_recorder.py`, `services/execution/run_capsules*`, related models, migrations and UI components |
| Bench/product frontend | `bench/*`, `services/bench/*`, `apps/frontend/app/bench/*`, `apps/frontend/app/tasks/*`, `apps/frontend/app/repositories/*`, `apps/frontend/app/page.tsx`, product CSS/components |
| Documentation and tests | `README.md`, `DESIGN.md`, `PRODUCT.md`, `docs/*`, `tests/*`, frontend `e2e/*` |
| Unrelated or uncertain | `.agents/` and `skills-lock.json` are untracked local skill material; inspect individually before considering any commit. |

Shared files such as `apps/api/main.py`, `apps/worker/main.py`, `services/execution/worker.py`, `services/verification/service.py`, `apps/frontend/app/tasks/[id]/page.tsx`, and `.github/workflows/ci.yml` contain multiple feature changes and require hunk-level review. Ignored `.tmp` contains disposable audit outputs and test fixtures. Neither the broad historical worktree nor `.agents/` should be assumed releasable. A future commit sequence should isolate dependencies/security, worker reliability, evidence schemas/services, UI, and docs/tests after each slice has fresh validation; no staging was done here.

## I. Release blockers and unverified gates

1. **Security:** six moderate npm development-tool advisories remain; review actual CI exposure. Real GitHub OAuth and hosted cookie/redirect behavior remain unverified. The local Docker Next server calculated its own origin as `http://0.0.0.0:3000` behind host port `3005`, so a browser-origin POST using `http://localhost:3005` received the intended strict 403. OAuth tests used the server's internal origin; actual hosted Vercel origin forwarding must be verified, without weakening the same-origin check.
2. **Migration:** local fresh and seeded legacy upgrades passed; a production backup, migration rehearsal against production-like data and hosted rollout are still absent.
3. **Local validation:** final full backend suite, production-source Pyright, CI Ruff, Docker sandbox, frontend lint/type/build, and Compose checks pass. Repository-wide Pyright still has 41 test-fixture typing errors, and full Ruff has 63 mainly style findings; these are disclosed quality debt, not passing checks. Host Windows Next build failed environmentally; the final isolated Docker frontend build passed.
4. **Remote infrastructure:** CI changes have not run on GitHub. Vercel and Render configurations were not changed or deployed in this task. The Docker worker requires a separate capable host; no hosted worker E2E passed.
5. **GitHub:** no real OAuth, import from a live account, or remote publication was performed. The safe local tests cannot prove production token scopes or PR behavior.

The five continuation containers under `forge-hardening-1114-` were inspected: PostgreSQL and both Redis instances used tmpfs, the frontend had a read-only worktree mount, and the API had no mounts. They and their now-empty `forge-hardening-1114-net` network were removed by exact name after validation; the final prefixed container/network inventory was empty. No persistent volume or unrelated Docker resource was deleted. Ignored `.tmp/security-hardening-e2e` retains audit outputs and diagnostic fixtures for review.

## J. Issue-to-PR readiness

The architecture has the required primitives—tenant-scoped repositories, durable execution, fenced worker ownership, sandbox policy, immutable evidence, digest-bound approval, and a publisher that records remote success only after the GitHub operation. The local integration evidence is sufficient to **begin** Issue-to-PR development on this feature worktree, with the unresolved test-fixture typing, dev-tool advisories, origin-forwarding verification and hosted gates tracked explicitly. It is **not production-ready**. Review the large uncommitted diff in feature-sized pieces, run remote CI, and verify a deployment with a separately hosted Docker worker before claiming the complete Forge workflow works. No real repository publication should be inferred from mocked publisher tests.
