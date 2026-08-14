# Shared packages

The `packages` directory contains reusable infrastructure that may be imported by more
than one service or application. Domain workflows belong in `services`; deployable
process assembly belongs in `apps`.

| Package | Responsibility |
| --- | --- |
| `database` | SQLAlchemy engine setup, tenant context, and persistent models |
| `events` | Transactional outbox publication and worker coordination |
| `sdk` | Repository manifest and MCP protocol primitives |
| `shared` | Configuration, cryptography, identifiers, logging, errors, and result types |

Keep dependencies directed inward: applications may import services and packages,
services may import packages, and packages should not import application entry points.
Cross-service domain behavior should use explicit events or service interfaces instead
of reaching into another service's internal modules.

Changes to database models require an Alembic migration. Changes to shared configuration
or event contracts should be reviewed against both the API and worker because they load
the same package code in separate processes.
