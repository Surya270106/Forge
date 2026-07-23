
# RFC-004 (Part 3)
# File Mutation Engine, Git Integration & Transaction System

**Status:** Draft v1.0

## Purpose

This RFC defines how Forge safely mutates repositories, manages multi-file
transactions, integrates with Git, resolves conflicts, and produces auditable
artifacts.

The File Mutation Engine is responsible for ensuring every repository change is
atomic, reversible, deterministic, and fully traceable.

---

# High-Level Architecture

```text
Execution Worker
      │
      ▼
Mutation Planner
      │
      ▼
Transaction Manager
      │
      ▼
Patch Engine
      │
      ▼
Git Layer
      │
      ▼
Verification
      │
      ▼
Artifact Publisher
```

---

# File Mutation Engine

## Responsibilities

- Apply file modifications
- Coordinate multi-file changes
- Preserve formatting
- Generate patches
- Detect conflicts
- Produce audit records

All mutations are executed through transactions.

---

# Mutation Types

Supported operations:

- Create File
- Update File
- Rename File
- Move File
- Delete File
- Batch Update
- Directory Creation
- Directory Removal

Each operation is represented as an immutable mutation object.

---

# Transaction Model

Every execution is wrapped in a transaction.

Transaction States

NEW

↓

OPEN

↓

PATCHING

↓

VERIFYING

↓

COMMITTED

Failure States

ROLLED_BACK

FAILED

ABORTED

Transactions never partially commit.

---

# Multi-File Transactions

A transaction may modify:

- source code
- tests
- configuration
- documentation
- infrastructure

Commit succeeds only when every mutation succeeds.

---

# Patch Engine

Every mutation produces:

- Original Hash
- Updated Hash
- Unified Diff
- File Metadata
- Timestamp
- Execution ID

Patch records are immutable.

---

# Conflict Detection

Conflicts are detected using:

- file hashes
- git status
- branch comparison
- graph version
- symbol ownership

Conflict Types

- File Conflict
- Symbol Conflict
- Merge Conflict
- Repository Drift

---

# Conflict Resolution

Automatic

- formatting
- whitespace
- documentation

Manual

- overlapping edits
- semantic conflicts
- API contract changes

Manual conflicts pause execution.

---

# Git Integration

Supported operations:

- branch creation
- checkout
- status
- diff
- add
- commit
- restore

Direct pushes are never performed automatically.

---

# Commit Strategy

Commit Message Format

```
forge(exec-<id>): <summary>

Execution: <execution-id>
Plan: <plan-id>
Graph: <graph-version>
```

Every commit references the originating execution plan.

---

# Artifact Generation

Execution produces:

- unified patch
- execution report
- verification report
- metrics snapshot
- structured logs

Artifacts are immutable.

---

# Rollback Engine

Rollback restores:

- files
- git state
- transaction metadata
- execution status

Rollback never deletes audit history.

---

# Internal Services

MutationService

- begin()
- mutate()
- commit()
- rollback()

GitService

- branch()
- commit()
- diff()
- restore()

PatchService

- generate()
- validate()
- apply()

ArtifactService

- publish()
- archive()

---

# Performance Budgets

Single file mutation

< 25 ms

Patch generation

< 50 ms

Transaction commit

< 500 ms

Rollback

< 2 seconds

Git commit

< 1 second

---

# Observability

Metrics

- mutations_total
- transaction_duration_ms
- rollback_total
- conflicts_detected_total
- git_operations_total
- patch_generation_ms

Tracing

- mutation planner
- transaction manager
- git layer
- patch engine
- artifact publisher

---

# Acceptance Criteria

✓ Atomic transactions implemented

✓ Multi-file mutations supported

✓ Git integration operational

✓ Conflict detection functional

✓ Rollback validated

✓ Artifact generation completed

✓ Immutable audit history maintained

---

# Next

RFC-004 Part 4

- Verification pipeline
- Build orchestration
- Testing framework
- Security validation
- Deployment architecture
- Event contracts
- REST APIs
- Database schema
- Operational runbooks
- Production readiness
- Final acceptance criteria
