# Security Policy

## Supported Status
Forge AI is currently in the **Full Internal Alpha** phase. It is strictly evaluated as a local development and internal alpha platform. 
**Production deployment is not supported.**

## Reporting a Vulnerability
As this is an internal alpha, please report any security vulnerabilities directly to the Forge AI engineering team via internal channels or the issue tracker. Do not publicly disclose vulnerabilities.

## Sandbox Limitations
The current active sandbox is `LocalProcessSandbox`. It is approved **only** for trusted development fixtures.
- Arbitrary or untrusted repository execution is **not supported** and poses a severe security risk.
- Do not use `LocalProcessSandbox` as a fallback for untrusted code execution.
- `DockerSandbox` and `FirecrackerSandbox` isolation layers are currently blocked or deferred.

## Tenant Isolation
Tenant isolation is enforced via PostgreSQL Row-Level Security (RLS) policies. Any new schema changes involving tenant data must explicitly include RLS policies in a manually reviewed migration. Alembic autogeneration is not sufficient for RLS policies.

## Secret Handling
- Local development secrets must remain in `.env.local` or `.env` files that are ignored by Git.
- Never commit API keys, database credentials, or provider tokens.
- No promise of safe untrusted execution is provided in this release.
