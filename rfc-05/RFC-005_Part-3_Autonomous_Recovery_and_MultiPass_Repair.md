
# RFC-005 (Part 3)
# Autonomous Recovery, Root Cause Analysis & Multi-Pass Repair

**Status:** Draft v1.0

## Purpose

This document specifies Forge AI's autonomous recovery architecture. It defines
how the Verification Engine analyzes failures, determines root causes,
constructs deterministic repair strategies, and safely retries execution without
introducing uncontrolled behavior.

---

# Recovery Philosophy

Core principles:

1. Never hide failures.
2. Every repair must be explainable.
3. Repairs must be deterministic.
4. Infinite repair loops are prohibited.
5. Rollback is preferred over unsafe mutation.

---

# Recovery Pipeline

```text
Verification Failure
        │
        ▼
Failure Classifier
        │
        ▼
Root Cause Analyzer
        │
        ▼
Repair Planner
        │
        ▼
Patch Generator
        │
        ▼
Verification
        │
        ▼
Success / Rollback
```

---

# Root Cause Analysis

Inputs

- compiler diagnostics
- test failures
- stack traces
- repository memory
- execution artifacts
- mutation history

Outputs

- primary cause
- secondary causes
- confidence score
- affected symbols
- repair candidates

---

# Failure Categories

Compile

- syntax
- type mismatch
- missing imports

Runtime

- null references
- dependency injection
- configuration

Verification

- failing assertions
- snapshot drift
- integration failures

Infrastructure

- network
- storage
- build environment

Security

- policy violations
- dependency vulnerabilities
- secret exposure

---

# Repair Planner

Responsibilities

- prioritize repair candidates
- minimize code changes
- preserve execution intent
- produce deterministic repair plans

Repairs are ranked by:

- confidence
- blast radius
- verification history
- complexity

---

# Multi-Pass Repair Loop

Maximum repair attempts: 3

Workflow

```text
Attempt 1
    │
Verify
    │
Pass? ── Yes → Complete
    │
    No
    ▼
Analyze
    ▼
Repair
    ▼
Verify
    ▼
Repeat
```

After the final failed attempt:

→ Rollback

→ Human approval required

---

# Delta Patch Generation

Each repair generates:

- minimal unified diff
- affected symbols
- rationale
- execution reference
- verification reference

Large rewrites are prohibited.

---

# Repair History

Stored metadata

- repair_id
- execution_id
- failure_type
- root_cause
- applied_patch
- outcome
- duration
- confidence

Repair history is immutable.

---

# Learning Cache

Purpose

Reuse previously successful repair strategies.

Cache Keys

- error signature
- language
- framework
- repository graph version

Cache never bypasses verification.

---

# Rollback Strategy

Rollback triggers

- repair limit exceeded
- confidence below threshold
- security regression
- repository inconsistency

Rollback restores

- files
- execution state
- transaction
- workspace snapshot

---

# Safety Guards

Hard limits

- max repair attempts
- max patch size
- max modified files
- forbidden directories
- protected configuration

Unsafe repairs are rejected.

---

# Internal APIs

RootCauseService

- analyze()
- explain()

RepairPlanner

- create_plan()
- rank()

RecoveryService

- retry()
- rollback()

LearningCache

- lookup()
- store()

---

# Performance Budgets

Root cause analysis

< 2 seconds

Repair planning

< 3 seconds

Patch generation

< 1 second

Repair verification

< 30 seconds

Rollback

< 2 seconds

---

# Observability

Metrics

- recovery_attempts_total
- repair_success_rate
- rollback_total
- root_cause_latency_ms
- repair_duration_ms
- learning_cache_hits

Tracing

- diagnosis
- repair planning
- patch generation
- verification
- rollback

---

# Acceptance Criteria

✓ Root causes identified

✓ Repair plans generated

✓ Multi-pass repair operational

✓ Learning cache implemented

✓ Rollback validated

✓ Safety guards enforced

✓ Immutable repair history maintained

---

# Next

RFC-005 Part 4

- Database schema
- REST APIs
- Event contracts
- Service interfaces
- Security model
- Deployment architecture
- Operational runbooks
- Testing matrix
- Production readiness
- Definition of Done
