
# RFC-001 (Part 2)
# Repository Import Pipeline & Lifecycle

## Scope

This document specifies the runtime pipeline responsible for importing a GitHub
repository into Forge AI and transitioning it into a READY state.

---

# End-to-End Pipeline

```text
User
 │
 ▼
Dashboard
 │
 ▼
POST /repositories/import
 │
 ▼
Auth Service
 │
 ▼
Repository Service
 │
 ▼
Clone Worker
 │
 ▼
Scanner
 │
 ▼
Language Detector
 │
 ▼
Framework Detector
 │
 ▼
Manifest Builder
 │
 ▼
Database
 │
 ▼
repository.ready Event
```

---

# GitHub Authentication

Goals

- Validate OAuth token
- Confirm repository access
- Retrieve repository metadata
- Resolve default branch

Failure Codes

- AUTH_INVALID
- TOKEN_EXPIRED
- REPOSITORY_FORBIDDEN
- REPOSITORY_NOT_FOUND

---

# Repository Import API

POST /api/repositories/import

Request

```json
{
 "repositoryUrl":"https://github.com/org/repo",
 "branch":"main"
}
```

Response

```json
{
 "repositoryId":"uuid",
 "status":"IMPORTING"
}
```

---

# Import Lifecycle

```text
PENDING
  │
  ▼
AUTHENTICATING
  │
  ▼
CLONING
  │
  ▼
SCANNING
  │
  ▼
DETECTING
  │
  ▼
BUILDING_MANIFEST
  │
  ▼
PERSISTING
  │
  ▼
READY
```

Error transitions always end in FAILED with retry support.

---

# Clone Service

Responsibilities

- Create isolated workspace
- Clone shallow by default
- Checkout branch
- Record commit SHA
- Verify repository integrity

Workspace

/workspaces/<repository-id>

Cleanup occurs after successful indexing or terminal failure.

---

# Repository Scanner

Ignore paths

- .git
- node_modules
- .next
- dist
- build
- target
- .venv
- __pycache__

Collect

- directories
- files
- configs
- package manifests
- lockfiles
- README
- licenses

---

# Language Detection

Signals

- extensions
- package manifests
- build files

Output

- primary language
- secondary languages
- percentages

---

# Framework Detection

Examples

Next.js -> next.config.*

FastAPI -> fastapi import

Django -> manage.py

Express -> express dependency

Spring -> pom.xml

---

# Repository Manifest

Contains

- repository metadata
- directory tree
- detected frameworks
- detected languages
- configuration files
- entry points
- test locations

Stored as versioned JSON.

---

# Worker Architecture

Importer API
    │
    ▼
Queue
    │
    ▼
Import Worker
    │
    ▼
Scanner Worker
    │
    ▼
Persistence Worker

Workers are stateless and horizontally scalable.

---

# Events

repository.created

repository.cloned

repository.scanned

repository.detected

repository.manifest.created

repository.ready

repository.failed

---

# Retry Policy

Clone failures:
3 retries with exponential backoff.

Authentication failures:
No retry.

Transient IO:
Automatic retry.

Permanent errors:
FAILED state.

---

# Logging

Every stage logs

- repository id
- branch
- commit sha
- duration
- status
- warnings
- errors
- worker id

---

# Security

- Never persist GitHub tokens.
- Read-only clone.
- Validate repository ownership.
- Isolated filesystem.
- Delete temporary workspaces.

---

# Acceptance Criteria

✓ Import completes successfully.

✓ Lifecycle transitions are observable.

✓ Manifest generated.

✓ Metadata persisted.

✓ READY event emitted.

✓ Failures recover safely.

---

Next:
Part 3 - Repository Scanner internals, algorithms, language detection heuristics,
framework rules, manifest generation, performance budgets.
