# Operational scripts

Scripts are grouped by intent so routine development helpers are not confused with
diagnostic or destructive maintenance commands.

| Directory | Use |
| --- | --- |
| `development` | Start local PostgreSQL or Redis processes |
| `database` | Initialize, inspect, or repair local database state |
| `diagnostics` | Check local PostgreSQL and Redis behavior |
| `windows` | PowerShell-specific migration helper |

Run scripts from the repository root with the project environment active. Review a
script's arguments and environment checks before use; these utilities target local
development and are not a production operations interface.

`scripts/database/reset_db.py` is destructive by design. It requires
`ENVIRONMENT=test`, an explicit `--confirm` flag, a loopback database host, and a
database name containing `test`. Do not weaken those guards or point development
helpers at a shared database.

Prefer Alembic for schema changes. A maintenance script is appropriate for diagnosis or
one-time local recovery, but it should not replace a versioned migration or application
behavior.
