
# RFC-004 (Part 1)
# Execution Engine — Foundations & Architecture

**Status:** Draft v1.0

## Executive Summary
The Execution Engine is responsible for safely executing approved engineering plans.
It consumes immutable Execution Plans from the Planning Engine and performs deterministic repository modifications through isolated workers.

## Goals
- Execute approved plans
- Preserve determinism
- Isolate execution
- Support retries
- Produce verifiable artifacts
- Emit execution events

## Non-Goals
- Intent analysis
- Repository indexing
- Long-term memory
- Risk assessment

## Execution Philosophy
1. Plans are immutable.
2. Execution never replans.
3. Every mutation is traceable.
4. Every action is reversible.
5. Verification follows every mutation.

## High-Level Architecture

User Approval
→ Execution API
→ Queue
→ Worker
→ Tool Runtime
→ Patch Engine
→ Verification
→ Git Layer
→ Result Publisher

## Core Components

### Execution API
Accepts approved execution plans and creates execution jobs.

### Queue Manager
Schedules work, enforces ordering, retries transient failures.

### Worker Runtime
Runs tasks inside isolated execution contexts.

### Tool Runtime
Provides controlled access to:
- Filesystem
- Git
- Search
- Build
- Test
- Formatter

### Patch Engine
Applies atomic file modifications and records every diff.

### Verification Dispatcher
Invokes compile, lint, unit and integration verification.

## Execution Lifecycle

PENDING
→ QUEUED
→ RUNNING
→ VERIFYING
→ COMPLETED

Failure States

FAILED

CANCELLED

ROLLBACK

## Execution Context

Contains

- execution_id
- repository_id
- branch
- graph_version
- commit_sha
- task_id
- workspace

Contexts are immutable after creation.

## Isolation Model

Each execution receives:

- isolated workspace
- temporary credentials
- dedicated logs
- resource limits

No execution shares writable state.

## Functional Requirements

- Execute task graph
- Track progress
- Persist execution state
- Emit events
- Retry transient failures
- Support rollback

## Non-Functional Requirements

- Deterministic
- Observable
- Fault tolerant
- Horizontally scalable
- Secure
- Auditable

## Acceptance Criteria

- Approved plans execute
- Workers isolated
- Patch engine operational
- Verification invoked
- Execution events emitted
- Rollback supported

## Next

RFC-004 Part 2:
Execution DAG, worker scheduling, sandbox internals, filesystem abstraction,
resource management, retries and orchestration.
