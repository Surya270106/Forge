
# RFC-005 (Part 2)
# Verification DAG, Failure Classification & Repair Algorithms

**Status:** Draft v1.0

## Purpose

Defines the internal architecture of the Verification Engine, including validator
orchestration, deterministic repair, retry policies, and execution contracts.

---

# Verification DAG

Each execution generates a Verification DAG (VDAG).

Node Types

- Format
- Lint
- Static Analysis
- Compile
- Unit Test
- Integration Test
- Security Scan
- Artifact Validation

Edges

- DEPENDS_ON
- PARALLEL_WITH
- VERIFY_AFTER

Rules

- DAG must be acyclic
- Compile precedes tests
- Security scan always executes

---

# Validator Scheduler

Objectives

- Maximize parallelism
- Preserve correctness
- Minimize latency

Execution Order

1. Formatter
2. Linter
3. Compiler
4. Static Analysis
5. Unit Tests
6. Integration Tests
7. Security Validation

---

# Failure Classification

Classes

- Syntax Error
- Type Error
- Build Error
- Test Failure
- Dependency Failure
- Security Issue
- Infrastructure Failure

Severity

- Low
- Medium
- High
- Critical

---

# Repair Engine

Automatic Repairs

- formatting
- imports
- missing dependencies
- simple syntax
- generated file updates

Manual Escalation

- failing business logic
- architectural conflicts
- security violations

---

# Retry Policy

Retryable

- flaky infrastructure
- temporary dependency failures

Non-Retryable

- invalid plan
- repeated deterministic failures

Policy

1s → 2s → 5s → abort

---

# Confidence Scoring

Signals

- validator success
- repair count
- failure severity
- graph integrity
- historical success

Output

0.0–1.0

Below 0.75 requires manual approval.

---

# Verification Contracts

Every validator returns

- status
- duration
- diagnostics
- artifacts
- confidence

---

# Internal APIs

VerificationCoordinator

- run()
- rerun()

RepairService

- classify()
- repair()
- validate()

DiagnosticsService

- aggregate()
- export()

---

# Performance Targets

Formatting <100ms

Lint <2s

Compile <30s

Unit Tests <60s

Integration <180s

Repair Pass <10s

---

# Observability

Metrics

- verification_duration_ms
- repairs_total
- retries_total
- validator_failures_total
- confidence_score

---

# Acceptance Criteria

- Verification DAG generated
- Parallel scheduling operational
- Failures classified
- Safe repairs executed
- Retry policy enforced
- Confidence calculated

---

# Next

RFC-005 Part 3

- Autonomous recovery loops
- Root cause analysis
- Multi-pass repair
- Rollback strategy
- Repair history
- Learning cache
- Production optimization
