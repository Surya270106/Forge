
# RFC-003 (Part 3)
# Tool Selection, Context Retrieval, Prompt Planning & Incremental Replanning

**Status:** Draft v1.0

## Purpose

This document specifies the internal reasoning systems that transform a validated
Task Graph into an execution-ready plan. It defines how Forge selects tools,
retrieves Repository Memory context, assembles prompts, optimizes plans, and
replans after failures.

---

# Architecture

```text
Task Graph
    │
    ▼
Context Retrieval
    │
    ▼
Tool Selection
    │
    ▼
Prompt Planning
    │
    ▼
Execution Contract
    │
    ▼
Optimization Engine
    │
    ▼
Execution Queue
```

---

# Context Retrieval Engine

The Context Retrieval Engine (CRE) is responsible for selecting the smallest set
of Repository Memory artifacts that fully describe a task.

Inputs

- task
- repository_id
- graph_version

Outputs

- files
- symbols
- dependencies
- APIs
- tests
- architectural notes

---

# Retrieval Signals

Primary

- graph distance
- dependency ownership
- API boundary
- entrypoint proximity

Secondary

- recent modifications
- historical execution relevance
- documentation references

---

# Retrieval Algorithm

Pseudo-code

```python
def retrieve(task):
    seeds = task.affected_symbols
    neighborhood = graph.expand(seeds, depth=2)
    ranked = rank(neighborhood)
    return trim(ranked, token_budget)
```

Determinism is required.

---

# Context Budgeting

Targets

- Small task: 2–8 files
- Medium task: 5–20 files
- Large task: 15–50 files

Hard limits

- 50 files
- 200 symbols
- 100k tokens equivalent

Exceeding limits triggers plan refinement.

---

# Tool Selection Engine

The Tool Selection Engine maps tasks to execution capabilities.

Capabilities

- filesystem
- search
- git
- build
- test
- formatter
- package_manager
- migration
- deployment

Selection depends on task type and repository architecture.

---

# Tool Matrix

| Task Type | Tools |
|---|---|
| Feature | filesystem, search, build, test |
| Refactor | filesystem, search, build, test |
| Migration | filesystem, migration, build, test |
| Documentation | filesystem |
| Dependency Upgrade | package_manager, build, test |

---

# Prompt Planning

The Prompt Planner converts task + context into a structured execution contract.

Sections

- objective
- constraints
- repository context
- allowed operations
- verification requirements
- expected outputs

No free-form prompting is allowed.

---

# Prompt Template

```text
Objective:
Implement JWT authentication.

Constraints:
- Preserve existing APIs.
- Do not change database schema.

Context:
- AuthService
- UserRepository
- LoginRoute

Verification:
- Build
- Unit tests
- Integration tests
```

---

# Execution Contract

The planner emits an immutable contract.

Fields

- task_id
- context_ids
- tools
- verification_plan
- risk_level
- token_budget
- timeout_budget

Execution Engine may not expand scope beyond this contract.

---

# Incremental Replanning

Replanning occurs when:

- verification fails
- context changes
- dependencies change
- execution exceeds budget
- human feedback arrives

Replanning must preserve completed tasks.

---

# Replanning Algorithm

```python
def replan(graph, failure):
    impacted = dependency_closure(failure.task)
    invalidate(impacted)
    regenerate(impacted)
    merge(graph, regenerated)
```

---

# Planning Cache

Cache keys

- repository_id
- graph_version
- normalized_intent
- risk_level

Cache stores:

- task graph
- context selection
- tool plan
- verification plan

Invalidation triggers

- graph version change
- dependency update
- planner version change

---

# Optimization Engine

Objectives

- minimize context size
- maximize parallelism
- reduce execution cost
- reduce verification duplication

Techniques

- context deduplication
- shared verification tasks
- task batching
- graph compression

---

# Complexity Analysis

Let:

- V = graph nodes
- E = graph edges
- T = tasks

Retrieval

O(V + E)

Scheduling

O(T + E)

Critical Path

O(T + E)

Replanning

O(impacted subgraph)

---

# Performance Budgets

- Intent analysis: < 200 ms
- Context retrieval: < 500 ms
- Task graph generation: < 1 s
- Full planning: < 2 s
- Replanning: < 500 ms

---

# Failure Handling

Recoverable

- missing symbol
- unresolved dependency
- cache miss

Fatal

- graph unavailable
- planner invariant violation
- corrupted execution contract

Planner must fail before execution.

---

# Internal APIs

```python
plan(request) -> ExecutionPlan

retrieve_context(task) -> ContextBundle

select_tools(task) -> ToolSet

replan(plan, failure) -> ExecutionPlan
```

---

# Observability

Metrics

- planning_duration_ms
- context_files_selected
- context_tokens_selected
- replans_total
- cache_hit_ratio
- planner_failures_total

Tracing spans

- retrieval
- ranking
- tool selection
- prompt assembly
- optimization

---

# Acceptance Criteria

✓ Context retrieval deterministic

✓ Tool selection reproducible

✓ Prompt planning structured

✓ Execution contracts immutable

✓ Incremental replanning functional

✓ Planning cache operational

✓ Performance budgets met

✓ Failure modes handled

---

# Next

RFC-003 Part 4

- Database schema
- REST APIs
- Event contracts
- Service interfaces
- Dependency injection
- Observability
- Security model
- Testing matrix
- Production deployment
- Operational runbooks
- Definition of Done
