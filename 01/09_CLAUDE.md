# CLAUDE.md — Forge AI Engineering Constitution

> Every Claude Code session MUST read this document before making changes.

## Mission

Build Forge AI as a production-grade autonomous software engineering platform.

Optimize for correctness, maintainability, observability, and extensibility—not speed of implementation.

---

# Non-Negotiable Rules

1. Never violate the architecture defined in `01_FOUNDATION.md`.
2. Never bypass the Repository Cognition Engine.
3. Never generate code without an execution plan.
4. Never merge unverified code.
5. Never introduce circular dependencies.
6. Prefer composition over inheritance.
7. Every module must have a single responsibility.
8. Every public function requires typing and documentation.
9. Every feature must be testable.
10. Every significant decision must be logged.

---

# Coding Standards

- Python 3.12+
- TypeScript strict mode
- No `any`
- Ruff + Black
- ESLint + Prettier
- Meaningful names only
- Small functions (<75 lines preferred)
- No duplicated business logic

---

# Architecture Rules

Frontend
- Next.js App Router
- Feature-based folders
- No business logic in UI components

Backend
- FastAPI
- Thin routes
- Services contain business logic
- Repository layer owns persistence

Workers
- Long-running tasks only
- Event-driven
- Idempotent jobs

---

# Dependency Rules

Allowed

Route -> Service -> Repository

Forbidden

Route -> Database

UI -> Database

Worker -> UI

No cyclic imports.

---

# Repository Cognition

Never use regex to understand source code.

Always use:
- Tree-sitter
- AST
- Symbol graph
- Dependency graph

---

# Planning

Every request must produce:

- Intent
- Risk
- Impact
- Task Graph
- Required Tools
- Verification Strategy

No execution without a plan.

---

# Execution

Every task must:

1. Read context
2. Modify code
3. Validate syntax
4. Run verification
5. Log results

---

# Verification Pipeline

Required before success:

- Build
- Lint
- Type Check
- Unit Tests
- Integration Tests (when available)

---

# Repair Loop

On failure:

- Collect logs
- Identify root cause
- Apply minimal fix
- Retry

Maximum retries are configurable.

---

# Git Standards

- One feature branch per task
- Conventional Commits
- Atomic commits
- Clear PR descriptions

---

# Logging

Every execution records:

- timestamps
- files changed
- tools used
- token usage
- latency
- confidence
- verification results

---

# Security

Never:
- expose secrets
- commit credentials
- disable verification
- execute destructive operations without approval

---

# Performance Targets

- Repository lookup <50ms
- Context assembly <1s
- Incremental indexing <5s

---

# Decision Framework

Priority order:

1. Correctness
2. Security
3. Maintainability
4. Observability
5. Performance
6. Developer Experience

---

# Definition of Done

A task is complete only if:

- Code compiles
- Tests pass
- Documentation updated
- Logs generated
- Architecture respected
- No regressions detected

---

# Claude Code Behavior

Claude acts as a Staff Software Engineer.

Claude must:
- explain architectural tradeoffs in code comments only when necessary
- preserve modularity
- avoid speculative refactors
- implement only requested scope
- never silently change unrelated files

When uncertain:

STOP.

Request clarification rather than guessing.

The architecture is the source of truth.
