
# RFC-004 (Part 2)
# Execution DAG, Worker Scheduling & Sandbox Runtime

**Status:** Draft v1.0

## Purpose

This document specifies the runtime architecture responsible for executing
approved plans. It defines execution DAGs, worker orchestration, sandbox
isolation, resource management, retry policies, and execution contracts.

---

# Execution DAG

The Execution Engine transforms an immutable Execution Plan into an Execution
Directed Acyclic Graph (EDAG).

Node Types

- File Mutation
- Test
- Build
- Verification
- Git
- Cleanup

Edge Types

- DEPENDS_ON
- PARALLEL_WITH
- VERIFY_AFTER
- CLEANUP_AFTER

Rules

- No cycles
- Every node executable
- Verification nodes are mandatory
- Cleanup always executes

---

# Worker Architecture

```text
Execution API
      │
      ▼
Queue Manager
      │
      ▼
Scheduler
      │
      ▼
Execution Worker
      │
      ▼
Sandbox Runtime
      │
      ▼
Tool Runtime
      │
      ▼
Patch Engine
```

Workers are stateless and horizontally scalable.

---

# Scheduling Algorithm

Objectives

- Preserve dependency order
- Maximize safe parallelism
- Avoid resource contention
- Respect approval constraints

Pseudo-code

```python
ready = graph.ready_nodes()

while ready:
    schedule(ready)
    wait_for_completion()
    ready = graph.next_ready()
```

---

# Execution States

NEW

↓

QUEUED

↓

ALLOCATING_WORKSPACE

↓

RUNNING

↓

VERIFYING

↓

COMPLETED

Failure States

FAILED

ROLLBACK

CANCELLED

---

# Sandbox Runtime

Every execution receives:

- isolated filesystem
- temporary workspace
- scoped credentials
- CPU limits
- memory limits
- execution timeout

Sandbox guarantees:

- no shared writes
- deterministic environment
- automatic cleanup

---

# Filesystem Abstraction

Operations

- read
- write
- move
- delete
- diff
- snapshot

All writes pass through the Patch Engine.

---

# Patch Engine

Responsibilities

- atomic writes
- conflict detection
- rollback metadata
- diff generation
- audit trail

Every modification produces:

- before hash
- after hash
- unified diff
- timestamp

---

# Resource Management

Limits

- max concurrent workers
- max execution time
- memory quota
- disk quota

Workers exceeding limits are terminated gracefully.

---

# Retry Policy

Retryable

- network interruption
- temporary filesystem errors
- transient build failures

Non-retryable

- invalid execution plan
- sandbox corruption
- authorization failure

Exponential backoff

1s → 2s → 5s → FAILED

---

# Failure Recovery

Recoverable

- worker restart
- cache miss
- temporary timeout

Fatal

- corrupted workspace
- invalid patch
- repository inconsistency

Recovery

1. restore snapshot
2. recreate workspace
3. replay safe tasks
4. continue execution

---

# Internal APIs

ExecutionService

- execute()
- cancel()
- rollback()

WorkerService

- allocate()
- run()
- cleanup()

PatchService

- apply()
- revert()
- diff()

SandboxService

- create()
- destroy()
- snapshot()

---

# Performance Budgets

Workspace allocation

< 1 second

Patch application

< 50 ms/file

Task dispatch

< 25 ms

Rollback

< 2 seconds

Worker startup

< 500 ms

---

# Observability

Metrics

- execution_jobs_total
- worker_latency_ms
- sandbox_start_ms
- patch_duration_ms
- retries_total
- rollback_total

Tracing

- scheduler
- worker
- sandbox
- patch engine
- verification

---

# Acceptance Criteria

✓ Execution DAG created

✓ Workers scheduled correctly

✓ Sandboxes isolated

✓ Patch engine operational

✓ Resource limits enforced

✓ Retry strategy implemented

✓ Recovery workflow validated

---

# Next

RFC-004 Part 3

- Git integration
- File mutation engine
- Multi-file transactions
- Conflict resolution
- Verification orchestration
- Artifact generation
- Commit strategies
- Merge safety
