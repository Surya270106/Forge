
# RFC-002 (Part 2)
# Graph Construction, Dependency Resolution & Context Ranking

Status: Draft v1.0

## Purpose

This document defines how Forge AI transforms parsed syntax trees into a
persistent Repository Memory Graph (RMG). The graph is the canonical engineering
representation consumed by the Planner, Execution Engine, and AI Context Builder.

---

# Repository Memory Graph (RMG)

The RMG is a directed, typed property graph.

Nodes represent engineering artifacts.

Edges represent semantic relationships.

Example

Repository
 ├── Directory
 │    └── File
 │          ├── Class
 │          ├── Function
 │          └── Interface

Relationships

IMPORTS

CALLS

DECLARES

EXTENDS

IMPLEMENTS

USES

OWNS

REFERENCES

---

# Graph Construction Pipeline

```text
AST Cache
   │
   ▼
Symbol Extractor
   │
   ▼
Relationship Resolver
   │
   ▼
Dependency Builder
   │
   ▼
Call Graph Builder
   │
   ▼
Repository Memory Graph
```

Graph construction MUST be deterministic.

---

# Symbol Identity

Every symbol receives a globally unique identifier.

Format

repository-id:file-id:symbol-path

Examples

repo123:api.py:AuthService.login

repo123:user.ts:UserController.create

IDs remain stable across incremental indexing when the symbol signature is
unchanged.

---

# Dependency Resolution

The dependency engine resolves:

- local imports
- package imports
- namespace imports
- relative imports
- alias imports

Outputs

- resolved dependency
- unresolved dependency
- circular dependency (flag only)

---

# Call Graph Builder

The call graph models execution flow.

Node Types

- Function
- Method
- API Route
- Background Task

Edges

CALLS

ASYNC_CALLS

EVENT_EMITS

EVENT_HANDLES

Graph queries should answer:

- Who calls this function?
- What does this API depend on?
- Which modules are affected?

---

# Repository Memory Storage

Graph Storage Schema

Node

- id
- type
- name
- language
- file
- metadata (JSON)

Edge

- id
- source
- target
- relationship
- metadata

The graph MUST support versioning.

---

# Incremental Graph Updates

Pipeline

Changed File
    │
    ▼
Reparse
    │
    ▼
Extract Symbols
    │
    ▼
Update Nodes
    │
    ▼
Update Edges
    │
    ▼
Invalidate Ranking Cache

Only affected graph regions are rebuilt.

---

# Context Ranking

Purpose

Select the smallest set of engineering artifacts that fully describe a user's
request.

Ranking Signals

- graph distance
- symbol ownership
- call frequency
- dependency depth
- recency of modification
- repository entrypoints
- API boundaries

Output

Ordered list of Repository Memory nodes.

---

# Public APIs

GET /api/v1/memory/{repositoryId}

Returns repository graph metadata.

GET /api/v1/memory/{repositoryId}/symbols

Returns extracted symbols.

GET /api/v1/memory/{repositoryId}/dependencies

Returns dependency graph.

POST /api/v1/memory/query

Input

{
  "query": "authentication flow"
}

Returns ranked engineering context.

---

# Performance Targets

Graph Build

< 60 seconds (100k file repository)

Incremental Update

< 5 seconds

Memory Query

< 100 ms

Graph Traversal

< 50 ms average

---

# Testing Strategy

Unit Tests

- symbol identity
- dependency resolution
- graph creation
- graph updates

Integration Tests

- Next.js application
- FastAPI service
- Monorepo
- Polyglot repository

Benchmark Tests

- 10k nodes
- 100k nodes
- 1M edges

---

# Failure Handling

Recoverable

- unresolved imports
- parser diagnostics
- partial graph generation

Fatal

- graph corruption
- storage failure

System MUST preserve previous graph until new graph is validated.

---

# Acceptance Criteria

✓ Repository Memory Graph generated

✓ Stable symbol identities

✓ Dependency graph built

✓ Call graph generated

✓ Incremental graph updates supported

✓ Context ranking operational

✓ Public APIs available

---

Next

RFC-002 Part 3

- Language-specific extraction rules
- Advanced graph algorithms
- Memory cache internals
- Prompt assembly interfaces
- Optimization
- Benchmark methodology
