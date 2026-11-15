# Security policy

## Supported versions

Forge is currently an alpha project. Security fixes are applied to the latest commit on the default branch; older commits and alpha snapshots are not separately supported.

## Security boundaries

Forge imports repositories, stores credentials, and executes repository commands. Its
primary boundaries are:

- API authentication, role-based permissions, and organization-scoped database access;
- PostgreSQL row-level security for tenant-owned records;
- encryption for stored provider credentials;
- organization/repository-scoped workspaces and allowlisted Docker images for execution;
- network-disabled containers for verification workloads that do not require egress;
- audit records for sensitive workflow changes.

These controls reduce risk but do not make the internal alpha a hardened multi-tenant
service. Authorization must be enforced for background jobs as well as HTTP requests,
and RLS must remain enabled and tested on the deployed PostgreSQL instance.

The OAuth redirect carries a short-lived, single-use exchange code. The Next.js server
redeems it and stores the application session in a host-only, HttpOnly, Secure cookie on
the frontend origin. Browser API requests pass through a same-origin proxy with Origin
checks on mutations. Direct WebSocket connections use short-lived, one-use tickets
instead of session tokens. Server-side session revocation is enforced on logout.
Legacy plaintext credentials are accepted only for recognizable GitHub and supported
provider token formats; malformed ciphertext fails closed. Rotate or migrate any
unsupported legacy plaintext records before relying on the stricter decoder.

## Execution and deployment expectations

The Compose worker mounts the Docker daemon socket. Possession of that socket is
effectively host-level privilege: a compromised worker or sandbox-management path may be
able to control the Docker host. Use a dedicated host, restrict access to the worker, keep
the sandbox image allowlist narrow, and review resource and network policy before running
repository code.

Sandbox command capture stops a command after 64 KiB on either stdout or stderr,
marks the result failed, and removes its Docker container. This bounds command
output held in worker memory before logs or verification results are persisted.
Command nodes fail if they change tracked or untracked repository files; reviewable
changes must come from `edit_file` mutations so verification cannot pass against
source changes missing from patch approval and publication.
An OS-level worker kill bypasses Python's sandbox cleanup and can leave a running
`forge-sandbox-*` container behind. Until a host-side reaper with verified job
ownership exists, inspect these containers and their `/workspace` mounts after a
crash; stop only containers whose owning execution or verification is inactive.
Each execution attempt uses a separate Git worktree at the recorded base commit.
The imported checkout remains separate. Attempt worktrees are retained for review
and crash recovery; no automatic retention cleanup is implemented yet. Protect
the worker host from disk exhaustion and remove old worktrees only after confirming
their jobs are inactive and their review evidence is no longer needed.

Abuse-sensitive API operations use atomic Redis rate limits keyed by authenticated
user and organization, or by client IP before login. The default window is 60
seconds, with separate configurable limits for auth, model, repository,
execution, and patch operations. Organization budgets are three times the
per-user budget. These operations return 429 with `Retry-After` when exhausted
and 503 when Redis cannot enforce the limit. Forwarded IP headers are ignored
unless the immediate peer matches `TRUSTED_PROXY_CIDRS`; configure only known
proxy networks. These request limits do not cap concurrent worker jobs or model
spend.

`LocalProcessSandbox` executes directly on the host and is intended only for trusted
development fixtures. It is not an isolation boundary and must never run arbitrary or
untrusted repositories.

Development defaults in `.env.example` and `docker-compose.yml` are not deployment
secrets. A shared environment requires unique signing and encryption keys, protected
GitHub credentials, restricted database and Redis exposure, TLS at the ingress, and
production configuration validation. Do not expose the API, worker, data services, or
Docker socket directly to the public internet.

## Reporting a vulnerability

Forge executes repository code, controls Docker workloads, and stores GitHub and provider credentials. Please do not publicly disclose or exploit a suspected vulnerability before the maintainer has had a reasonable opportunity to investigate it.

Use GitHub's **Report a vulnerability** option on the repository Security tab when private vulnerability reporting is enabled. If that option is unavailable, contact the maintainer through the GitHub profile associated with this repository and ask for a private reporting channel. Do not put exploit details, credentials, or sensitive logs in a public issue.

Include:

- the affected component and commit;
- the prerequisites and minimal reproduction steps;
- the expected and observed security boundary;
- the likely impact;
- any safe mitigation you have tested.

## Sensitive data

Never commit secrets, OAuth credentials, tokens, private keys, `.env` files, repository clones, or execution workspaces. If a credential is exposed, remove it from the current tree and rotate it immediately; deleting a file in a later commit does not remove it from Git history.
