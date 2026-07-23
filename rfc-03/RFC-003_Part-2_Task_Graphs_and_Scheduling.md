
# RFC-003 (Part 2)
# Task Graphs, Dependency Scheduling & Planner Algorithms

**Status:** Draft v1.0

## Purpose

This document specifies how the Planning Engine converts engineering intent into
a deterministic Directed Acyclic Graph (DAG) of executable tasks. It defines the
planner's scheduling algorithms, dependency resolution, approval workflow, and
execution contracts.

---

# Task Graph Model

Each engineering request is represented as a DAG.

Node Types

- Feature Task
- Refactor Task
- Test Task
- Documentation Task
- Migration Task
- Infrastructure Task

Edge Types

- DEPENDS_ON
- BLOCKS
- PARALLEL_WITH
- VERIFIES

Rules

- No cycles permitted
- Every graph has exactly one root request
- Leaf nodes must be executable

---

# Task Structure

Every task contains:

- task_id
- title
- description
- priority
- complexity
- estimated_duration
- owner
- affected_symbols
- dependencies
- verification_plan
- approval_required

---

# Dependency Resolution

The planner resolves dependencies from:

- Repository Memory Graph
- Import graph
- Call graph
- Ownership graph
- API relationships

Dependency types:

- Hard dependency
- Soft dependency
- Optional dependency

Circular dependencies are rejected.

---

# DAG Construction Algorithm

Pipeline

Natural Language
      │
      ▼
Intent
      │
      ▼
Impact Analysis
      │
      ▼
Candidate Tasks
      │
      ▼
Dependency Resolver
      │
      ▼
Cycle Detection
      │
      ▼
Task Graph

Pseudo-code

```
tasks = decompose(intent)

edges = resolve_dependencies(tasks)

assert is_dag(tasks, edges)

return TaskGraph(tasks, edges)
```

---

# Scheduling Strategy

Objectives

- Maximize safe parallelism
- Preserve correctness
- Respect dependencies
- Minimize completion time

Scheduling Order

1. Root task
2. Independent tasks
3. Dependency chains
4. Verification tasks
5. Documentation

---

# Critical Path Analysis

Planner computes:

- longest dependency chain
- blocking tasks
- parallel opportunities
- total estimated duration

Critical path tasks receive highest scheduling priority.

---

# Cost Estimation

Signals

- files affected
- symbols affected
- dependency depth
- architectural layer
- historical complexity

Output

- Small
- Medium
- Large
- Very Large

---

# Confidence Scoring

Inputs

- intent clarity
- Repository Memory coverage
- dependency confidence
- graph completeness
- ambiguity score

Output

0.0 → 1.0

Confidence < 0.70 requires clarification.

---

# Approval Gates

Automatic Approval

- docs
- formatting
- comments

Manual Approval

- authentication
- payments
- infrastructure
- migrations
- security
- destructive operations

---

# Planner State Machine

```text
NEW
 │
 ▼
ANALYZING
 │
 ▼
PLANNING
 │
 ▼
WAITING_APPROVAL
 │
 ▼
APPROVED
 │
 ▼
READY_FOR_EXECUTION
 │
 ▼
COMPLETED
```

Failure states:

FAILED

CANCELLED

---

# Sequence Diagram

```text
User
 │
 ▼
Planning API
 │
 ▼
Intent Analyzer
 │
 ▼
Repository Memory
 │
 ▼
Impact Analyzer
 │
 ▼
Task Graph Builder
 │
 ▼
Risk Engine
 │
 ▼
Execution Plan
```

---

# Failure Handling

Recoverable

- incomplete context
- missing symbols
- ambiguous request

Fatal

- Repository Memory unavailable
- graph corruption
- planner invariant violation

---

# Planner Invariants

- Plans are immutable
- Graphs are acyclic
- Every task is verifiable
- Dependencies are explicit
- Risk is calculated before execution

---

# Acceptance Criteria

✓ DAG generated

✓ Dependencies resolved

✓ Critical path identified

✓ Parallel tasks detected

✓ Cost estimated

✓ Confidence scored

✓ Approval gates inserted

✓ Planner state transitions validated

---

# Next

RFC-003 Part 3

- Tool Selection Engine
- Context Retrieval
- Prompt Planning
- Incremental Replanning
- Planning Cache
- Failure Recovery
- Optimization
- Complexity Analysis
