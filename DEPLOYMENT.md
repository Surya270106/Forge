# Forge: zero-cost deployment guide

This configuration targets personal/demo use without a payment card:

- Vercel Hobby for the Next.js frontend.
- Render Free for the FastAPI web service.
- Neon Free for PostgreSQL.
- Upstash Free Redis over its native TLS TCP protocol for the API/demo.
- No hosted execution worker is included. Real Docker execution needs a separate Docker-capable machine.

Free plans and eligibility can change. Check the linked provider limits before creating accounts. Vercel Hobby is for personal, non-commercial use. This setup is a demo, not production-grade availability or backup coverage.

## 1. Create the Vercel Hobby frontend

1. Sign up for a personal Vercel account and stay on Hobby. Import `Surya270106/Forge` from GitHub.
2. Set **Root Directory** to `apps/frontend`; keep the Next.js framework preset, default Next output directory, and detected `npm ci` / `npm run build` commands. Set the project Node.js version to `24.x`.
3. Set these Production environment variables (set Preview too if you intend to test preview deployments):

   | Variable | Value |
   | --- | --- |
   | `NEXT_PUBLIC_API_BASE_URL` | `https://<render-service>.onrender.com` |
   | `FORGE_API_ORIGIN` | Same Render HTTPS origin; server-side Next.js API proxy target |
   | `NEXT_PUBLIC_EVENT_URL` | `wss://<render-service>.onrender.com` |
   | `STRICT_PROD` | `true` |

   Browser HTTP calls use same-origin `/api/v1` routes on Vercel. The Next.js server forwards only the session cookie, organization header, and request body to the Render API at `FORGE_API_ORIGIN` (falling back to `NEXT_PUBLIC_API_BASE_URL`). `NEXT_PUBLIC_EVENT_URL` is used for direct WebSocket connections with one-time tickets. After changing an origin, redeploy Vercel. The strict production check requires HTTPS and WSS.
4. You can create the Vercel project before the API. Until the real Render URL is known, either wait to deploy or use temporary HTTPS/WSS values; API calls and sign-in will not work with placeholders.

Vercel Hobby is free for personal, non-commercial use, subject to its usage quotas and fair-use terms; check [Hobby plan limits](https://vercel.com/docs/plans/hobby) before relying on a quota-bound demo. Avoid paid add-ons, team upgrades, and paid custom-domain purchases.

## 2. Create a Neon Free PostgreSQL database

1. Create a Neon account and choose its Free plan; do not add a payment method.
2. Create a project in a region near the Render service. Create/select the default database and a database role.
3. In the Neon Console, open **Connect**, choose the branch, database, and role, turn **Connection pooling off**, and copy the direct connection string. The direct connection is used for the API and startup migrations.
4. Keep `sslmode=require` in the query string. Neon may also include `channel_binding=require`; the Forge URL normalizer removes that asyncpg-incompatible option while retaining the required TLS setting.
5. Do not put the connection string in this repository, `render.yaml`, a committed `.env`, or a chat message. Add it only to Render's API environment as `DATABASE_URL`, using the dashboard's secret environment-variable field.

Neon Free currently includes 1 GB storage per project and 100 CU-hours per project each month, with compute scaling to zero while idle; the first database request may be slower. See [Neon Free plan details](https://neon.com/blog/neon-free-plan-1-gb) and [current pricing](https://neon.com/pricing) for changes. The app uses PostgreSQL's asyncpg driver and preserves TLS while normalizing Neon URLs.

## 3. Create Upstash Free Redis for the API/demo

1. Create an Upstash account and a Redis database on the Free plan; do not add a payment method. Choose a region close to Render.
2. In the database's **Connect** panel, select **TCP** and copy the TLS connection string. It should look like `rediss://default:<password>@<host>:<port>`.
3. In Render, set that value as the secret `REDIS_URL`. Do **not** use the REST URL/token or a read-only token: Forge uses the redis-py TCP client and needs write, stream, and Pub/Sub commands.
4. Never put the URL or password in Git, `render.yaml`, or a committed `.env` file.

Forge currently uses `XGROUP CREATE`, `XREADGROUP ... BLOCK 2000`, `XAUTOCLAIM`, `XPENDING`, `XACK`, `XADD`, `PUBLISH`, and Pub/Sub subscriptions. Upstash documents support for these Redis stream/Pub/Sub operations through the Redis protocol. Its **REST API** explicitly does not support blocking `XREAD`/`XREADGROUP`, which is why the TCP URL is required. See [Upstash Redis/Render connection instructions](https://upstash.com/docs/redis/quickstarts/render), [Redis protocol compatibility](https://upstash.com/docs/redis/overall/compatibility), and [REST API command limitations](https://upstash.com/docs/redis/features/restapi).

There is an important free-quota limitation: while idle, the current always-running worker makes three `XAUTOCLAIM` calls and one blocking `XREADGROUP` call about every two seconds. That is approximately **5.2 million Redis commands per 30 days**, before useful work, while Upstash Free currently includes **500,000 commands/month**, 256 MB, and 10 GB bandwidth. Therefore Upstash Free is suitable for the API-only demo or brief on-demand worker tests, but **not for a continuously running Forge worker**. Do not leave a worker polling Upstash Free around the clock. Check [Upstash pricing](https://upstash.com/pricing/redis) because quotas can change.

For a fully local no-card end-to-end test, use the repository's `docker-compose.yml`, which runs PostgreSQL, Redis, API, migrations, and the Docker worker on your own Docker machine. For a remote Vercel/Render API demo without a worker, Upstash Free is sufficient for low-volume API health checks and real-time API features; queue-backed jobs will remain unprocessed until a worker is connected.

## 4. Create the free Render API service and enter its variables

1. Sign up for Render and stay on a Free workspace/service plan; do not add a payment method or upgrade the service.
2. Connect the GitHub repository and create/sync the Blueprint from the repository's `render.yaml`, on the branch containing these reviewed changes. The Blueprint creates **only** the `forge-api` Docker web service with `plan: free`; it does not create a paid database, paid Key Value, or worker.
3. Add these variables to the Render API service's **Environment** page. Values marked secret must use Render's secret environment-variable controls.

   | Variable | Value |
   | --- | --- |
   | `ENVIRONMENT` | `production` (set by the Blueprint) |
   | `DATABASE_URL` | Neon **direct** connection string, with `sslmode=require` |
   | `REDIS_URL` | Upstash **TCP** `rediss://` connection string |
   | `FRONTEND_URL` | Exact Vercel origin, e.g. `https://forge-ui.vercel.app` |
   | `CORS_ORIGINS` | JSON array with that exact origin, e.g. `["https://forge-ui.vercel.app"]` |
   | `SECRET_KEY` | New random stable secret, generated outside Git |
   | `ENCRYPTION_KEY` | New random secret, generated outside Git; required by production settings |
   | `GITHUB_CLIENT_ID` | GitHub OAuth App client ID |
   | `GITHUB_CLIENT_SECRET` | GitHub OAuth App secret |
   | `GITHUB_WEBHOOK_SECRET` | Random webhook secret; needed if configuring the webhook |
   | `SANDBOX_IMAGES` | Blueprint default JSON list; currently `python:3.12-slim` and `node:20-slim` |

   Generate two separate secret values locally, for example by running `python -c "import secrets; print(secrets.token_urlsafe(48))"` twice. Paste them directly into Render's dashboard; do not save them in the repository. Keep `SECRET_KEY` stable: the current `CryptoService` derives the Fernet key used for stored credentials from `SECRET_KEY`. `ENCRYPTION_KEY` is required by production settings but is not currently used by `CryptoService`.
4. The Render Docker command runs `/app/.venv/bin/alembic upgrade head` before starting Uvicorn. This replaces the paid-only Render pre-deploy command. It is a forward-only Alembic upgrade and does not reset or drop the database. If the migration command fails, the shell exits and the API does not start; migration errors are visible in Render logs. It runs again on each service start, which is safe for already-applied Alembic revisions. Use the Neon direct URL for this step, not a pooled URL.
5. Render's Blueprint health check uses `/health` for process liveness, matching the dashboard setting. Separately request `/ready` to check Neon and Redis; a sleeping Neon database may make the first readiness request slow. `/ready` returns only dependency availability, not connection details. Copy the actual Render hostname, then set the real `FRONTEND_URL`, `CORS_ORIGINS`, and Vercel `NEXT_PUBLIC_API_BASE_URL` / `NEXT_PUBLIC_EVENT_URL` values and redeploy both services as needed.

The Render Free service is constrained to low CPU/memory, one instance, and an ephemeral filesystem. Render Free web services spin down after 15 minutes without inbound traffic and can take about a minute to wake. They have 750 free instance hours per workspace per month, shared usage limits for bandwidth/builds, can restart, and cannot use pre-deploy commands, one-off jobs, persistent disks, or multiple instances. If no payment method is on the account, exceeding some workspace allowances can suspend services or builds rather than charge a card. See [Render Free service limits](https://render.com/docs/free).

Neon is external to Render, so the free Render service connects over the public network using Neon TLS. Render may suspend Free services that initiate unusually high external traffic. Monitor Render, Neon, and Upstash quotas. The Blueprint does not create any Render Postgres or Key Value resource.

## 5. GitHub OAuth and webhook settings

1. In GitHub Developer Settings, create an OAuth App. Set its homepage URL to the exact Vercel origin.
2. Set its Authorization callback URL to:

   `https://<render-service>.onrender.com/api/v1/auth/github/callback`

3. Put the OAuth client ID and secret into Render's `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`. The application begins login through Vercel's same-origin API proxy and returns the user to the Vercel `/login/callback` page with a short-lived, single-use exchange code. Vercel's `/api/auth/exchange` route redeems it server-side and sets a host-only, `HttpOnly`, `Secure`, `SameSite=Lax` session cookie; neither the redirect nor browser JavaScript receives the application token. Unsafe proxy requests require the exact frontend `Origin` header. Redis must be available for the exchange and for short-lived WebSocket tickets.
4. If enabling push webhooks, set the repository webhook endpoint to `https://<render-service>.onrender.com/api/v1/github/webhooks/` and use the same secret as `GITHUB_WEBHOOK_SECRET`. The endpoint requires a valid signature in every environment. Valid default-branch push events return `not_scheduled` because repository synchronization is not yet implemented; they do not enqueue work or query tenant repositories.

## 6. Demo without a hosted Docker worker

The Vercel frontend and Render API can be deployed without a worker. You can verify that the UI loads, OAuth completes, API authentication works, and health/readiness checks pass. Do not treat a queued repository import, indexing job, plan execution, or verification as completed: those jobs are consumed by the worker and will remain pending without it. WebSocket access requires a one-use, 45-second ticket issued by the authenticated API; live logs still need the worker to publish them.

The Docker worker cannot run on Vercel or an ordinary Render web service. Render Free has no free background-worker plan, and the worker needs a host Docker Engine socket. The zero-cost full-workflow option is a machine you control with Docker installed: run local `docker-compose.yml` for a local stack, or run `docker-compose.worker.yml` with a protected workspace and credentials for the remote API's Neon/Redis services. Do not expose the Docker socket or an unauthenticated Redis port to the public internet. A remotely connected worker must have a reliable Docker host and a Redis plan/quota that can sustain the polling loop; Upstash Free is not suitable for a continuously running worker at the current polling rate.

The worker mounts each repository workspace into its own restricted Docker sandbox. The Compose path `/srv/forge/workspaces` must refer to the same directory on the worker and Docker host; verify that bind mount on a Linux Docker host before accepting untrusted repositories. Indexing requires a real checked-out repository workspace; missing workspaces and parser failures are reported as failures. Failed verification prepares bounded repair feedback and can generate a new plan on explicit request. The repair plan requires normal plan approval before execution and is limited to files changed by the failed execution, with at most three attempts. Accepting a patch records approval of its exact review digest; a separate explicit publish request queues a worker job to create a dedicated `forge/<patch-id>` branch and GitHub pull request. The API reports success only after GitHub confirms a pull request. These actions require a connected GitHub account with repository write access and an online Docker worker. A partially published branch can be retried after a pull-request failure; never assume a queued or failed status means a pull request exists. Hosted end-to-end execution and pull-request creation remain unverified.

Before running `docker-compose.worker.yml` on a Linux Docker host, create an **untracked** `.env.worker` in the repository root using a protected local secret store or file editor. It must contain the API's `DATABASE_URL` (Neon direct TLS URL), `REDIS_URL` (TCP TLS URL), `SECRET_KEY`, and `ENCRYPTION_KEY`. Set `ENVIRONMENT=production`, `FRONTEND_URL`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, and `GITHUB_WEBHOOK_SECRET` as required by production settings. Never commit `.env.worker` or copy credentials into this guide. Set `DOCKER_GID` in the shell or an untracked Compose `.env` file to the numeric group ID of the mounted Docker socket, obtained on the Docker host with `stat -c %g /var/run/docker.sock`. Check that this group grants only the intended worker access; Docker socket membership is host-equivalent privilege. Validate with `docker compose -f docker-compose.worker.yml config --quiet`, then start with `docker compose -f docker-compose.worker.yml up -d --build` and stop with `docker compose -f docker-compose.worker.yml down`. Do not use `down -v` for this remote-worker setup.

## Worker contribution and repair checks

1. On the worker host, install Docker Engine and ensure the worker image contains `git`. Set `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ENCRYPTION_KEY`, and `WORKSPACE_ROOT` consistently with the API; use a shared protected workspace mount for the Docker host and worker. Do not copy GitHub tokens into worker environment variables: the worker reads the requester's encrypted credential from PostgreSQL and checks that the user still has the required role.
2. Run `alembic upgrade head` against the Neon **direct** TLS URL before accepting work. The new migration adds patch review/publish state and repair plan links, scopes repository identity uniqueness by organization, and enables patch row-level security. Back up the database before migrations; do not downgrade a database containing newer repair states.
   The older `c171ce8c8213` migration previously dropped the `patches` table. This revision now preserves it on new upgrades, and the latest migration recreates the table if that older revision already removed it. Recreating an absent table cannot recover rows deleted by an earlier deployment; restore those rows from a database backup if needed. Verify the database role used by the API has neither `rolsuper` nor `rolbypassrls` in `pg_roles` and is **not named `forge_admin`**. The current policies explicitly exempt that role name. Test cross-tenant reads with the actual API role before accepting hosted traffic. The local CI RLS test uses a separate restricted PostgreSQL role; it does not prove a hosted Neon role is restricted.
3. Import a repository through the connected GitHub account. Confirm that the import and index jobs complete and that the repository records a real 40-character base commit. Repository workspaces are preserved if an import is retried; the worker will not replace a workspace containing local changes.
4. Submit and approve a plan, execute it in the Docker worker, then inspect persisted logs, mutations, and verification results. Failed verification can produce a repair proposal; review its feedback, request a bounded plan, approve it, execute it, and inspect the new verification. A missing worker leaves queue-backed jobs pending.
   Before plan creation, configure a real model provider and API key in Forge's provider settings. Forge now rejects missing credentials, malformed plans, unsupported actions, unsafe paths, and cyclic plans instead of creating placeholder execution tasks.
5. Generate a patch only from a completed execution. Review the full diff and digest, approve that digest, then separately request publication. Verify the returned pull-request URL on GitHub and compare its changed files with the reviewed diff. Forge never pushes to the default branch. If the API shows `FAILED`, inspect the sanitized publish error code, reconnect GitHub or re-import when indicated, and retry only after checking whether the deterministic branch or pull request already exists.
   For a repair execution, the reviewed patch includes the original execution and every repair attempt in order, so the published branch reconstructs the verified result from the imported base commit.

The OAuth app requests `repo` scope for private repository import and contribution. GitHub credentials can expire or be revoked; publication rechecks the requester's role, GitHub push permission, selected repository, base commit, verification, and approved digest. Protect the Docker host and Redis connection because the worker has privileged access to repository workspaces and the Docker socket.

The worker checks for stale `RUNNING` execution and verification jobs and stale import/repair jobs about once a minute. Jobs older than the configured execution timeout plus a safety window are marked failed; filesystem actions are **not** replayed automatically because they may have partially completed. Inspect the workspace and recorded mutations before starting a new plan or import. A queued publish request can be retried safely against its deterministic branch after an interruption.

## Deployment and verification order

1. Create Neon and Upstash Free accounts/databases; copy the TLS direct PostgreSQL URL and Upstash TCP Redis URL.
2. Create the Vercel Hobby project from GitHub with `apps/frontend` as root and note its `vercel.app` origin.
3. If reusing an existing Neon database, take and verify a restorable backup before creating or redeploying Render: its start command automatically applies Alembic migrations. Inspect the current revision and plan recovery from the backup before allowing that startup. A fresh empty database needs no data backup.
4. Create/sync the Render Free Blueprint. Set all external URLs, secrets, OAuth credentials, `FRONTEND_URL`, and exact-origin `CORS_ORIGINS` in Render's environment dashboard.
5. Confirm the Render start logs show a successful Alembic upgrade followed by Uvicorn startup, then confirm `/health` responds and `/ready` reports both dependencies available.
6. Enter the actual Render HTTPS/WSS URLs in Vercel Production variables and redeploy. Verify `/login`, GitHub OAuth, authenticated API calls, and the execution-log WebSocket.
7. For actual repository execution, start a Docker-capable worker and test a repository import and execution. The remote demo is not a complete Forge workflow until that succeeds.

No service is deployed by this configuration change. Treat provider dashboard setup, GitHub connection, database migration, and worker testing as separate steps.
