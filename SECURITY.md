# Security policy

## Supported versions

Forge is currently an alpha project. Security fixes are applied to the latest commit on the default branch; older commits and alpha snapshots are not separately supported.

## Security boundaries

Forge imports repositories, stores credentials, and executes repository commands. Its
primary boundaries are:

- API authentication, role-based permissions, and organization-scoped database access;
- PostgreSQL row-level security for tenant-owned records;
- encryption for stored provider credentials;
- per-job workspaces and allowlisted Docker images for execution;
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
