# Security policy

## Supported versions

Forge is currently an alpha project. Security fixes are applied to the latest commit on the default branch; older commits and alpha snapshots are not separately supported.

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
