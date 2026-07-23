
# RFC-001 (Part 1)
# Repository Import & Repository Memory Bootstrap

**Status:** Draft v1.0  
**Authors:** Forge AI Team  
**Last Updated:** 2026-07-18

---

# Revision History

| Version | Date | Changes |
|---|---|---|
|0.1|2026-07-18|Initial engineering RFC (Part 1)|

---

# Table of Contents

1. Executive Summary
2. Background
3. Problem Statement
4. Goals
5. Non-Goals
6. Functional Requirements
7. Non-Functional Requirements
8. Assumptions
9. Constraints
10. Terminology
11. High-Level Architecture
12. Design Principles

---

# Executive Summary

The Repository Import & Repository Memory Bootstrap service is the first subsystem
executed inside Forge AI.

Its responsibility is to transform an arbitrary GitHub repository into an
internal representation that every later subsystem can consume.

At the completion of this RFC the system SHALL be capable of:

- Authenticating with GitHub
- Importing public and private repositories
- Cloning repositories safely
- Detecting languages
- Detecting frameworks
- Building a repository manifest
- Persisting repository metadata
- Publishing a RepositoryReady event

No AST parsing, symbol extraction, dependency graphs, or LLM interaction are
performed in this RFC.

---

# Background

Existing AI coding tools frequently rely on ad-hoc repository inspection or
stateless prompt construction. This creates inconsistent understanding, repeated
work, and poor scalability.

Forge AI introduces the concept of **Repository Memory**.

Repository Memory is a persistent engineering representation that survives
between sessions and becomes the source of truth for every future planning,
execution, and verification operation.

Repository Import is therefore not just a cloning operation. It is the gateway
into the entire platform.

---

# Problem Statement

Without deterministic repository onboarding:

- repositories are repeatedly analyzed
- prompts become inconsistent
- indexing is duplicated
- execution latency increases
- engineering context becomes unreliable

The system requires a standardized bootstrap pipeline before any intelligence
can operate.

---

# Goals

Primary goals:

1. Import repositories safely.
2. Produce deterministic metadata.
3. Detect languages automatically.
4. Detect frameworks.
5. Generate a normalized repository manifest.
6. Store persistent metadata.
7. Emit lifecycle events.
8. Prepare the repository for later cognition stages.

Success Criteria:

- Repository imported successfully.
- Metadata stored.
- Repository marked READY.
- Average onboarding time under two minutes for medium repositories.

---

# Non-Goals

This RFC intentionally excludes:

- Tree-sitter parsing
- AST generation
- Symbol extraction
- Dependency graph construction
- Embedding generation
- LLM prompt assembly
- Execution planning
- Code modification

Those capabilities are specified in later RFCs.

---

# Functional Requirements

FR-001 Validate GitHub credentials.

FR-002 Import repositories from HTTPS URLs.

FR-003 Support branch selection.

FR-004 Clone repository to isolated workspace.

FR-005 Ignore generated artifacts.

FR-006 Detect repository languages.

FR-007 Detect frameworks.

FR-008 Count files and directories.

FR-009 Build repository manifest.

FR-010 Persist metadata.

FR-011 Publish RepositoryReady event.

---

# Non-Functional Requirements

- Deterministic outputs
- Idempotent imports
- Structured logging
- Retry-safe operations
- Observable execution
- Horizontal scalability
- Portable implementation
- Test-first development

Performance Targets

- Clone < 60 s (typical)
- Manifest generation < 10 s
- Detection accuracy > 95%
- Import success > 99%

---

# Assumptions

- GitHub is reachable.
- User possesses required permissions.
- Git is available on workers.
- Storage is persistent.
- PostgreSQL is operational.

---

# Constraints

- Repository size limit configurable.
- Binary assets are ignored.
- Import executes in isolated workers.
- Secrets are never persisted.
- Workspace is cleaned after failures.

---

# Terminology

Repository Memory:
Persistent representation of a repository.

Repository Manifest:
Normalized description of repository structure.

Workspace:
Temporary clone location.

Bootstrap:
The complete onboarding pipeline executed before indexing.

---

# High-Level Architecture

```text
GitHub
   │
   ▼
Authentication
   │
   ▼
Repository Import
   │
   ▼
Clone Service
   │
   ▼
Repository Scanner
   │
   ▼
Language Detection
   │
   ▼
Framework Detection
   │
   ▼
Manifest Builder
   │
   ▼
Metadata Store
   │
   ▼
Repository Ready
```

---

# Design Principles

1. Deterministic over clever.
2. Fail safely.
3. Never mutate user repositories.
4. Every stage observable.
5. Small composable services.
6. Persistent metadata.
7. Clear ownership boundaries.
8. Platform before AI.
9. Repository understanding before execution.
10. Build foundations that later RFCs extend.

---

**End of Part 1**

Next document:
RFC-001 Part 2 — Repository Import Pipeline, OAuth, Clone Service,
Lifecycle, Sequence Diagrams and State Machines.
