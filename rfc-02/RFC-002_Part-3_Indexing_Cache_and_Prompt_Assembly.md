
# RFC-002 (Part 3)
# Language Extraction, Indexing Engine, Cache Architecture & Prompt Assembly

Status: Draft v1.0

## Purpose

This document defines the internal indexing pipeline that converts parser output
into a continuously updated Repository Memory. It specifies language-specific
symbol extraction, graph maintenance, cache invalidation, and how downstream AI
systems consume Repository Memory without reparsing source code.

---

# Indexing Pipeline

```text
Changed Repository
        │
        ▼
File Change Detector
        │
        ▼
Incremental Parser
        │
        ▼
Symbol Extractor
        │
        ▼
Relationship Builder
        │
        ▼
Repository Memory Update
        │
        ▼
Ranking Cache Update
        │
        ▼
Prompt Assembly API
```

The pipeline is event-driven and idempotent.

---

# Language Adapters

Every language implements the same contract.

Interface

```
supports(language)

parse(file)

extract_symbols(ast)

extract_relationships(ast)

validate(ast)
```

### Python

Extract:

- modules
- classes
- functions
- async functions
- decorators
- imports
- dataclasses
- FastAPI routes
- Pydantic models

### TypeScript / JavaScript

Extract:

- React components
- hooks
- classes
- interfaces
- enums
- exported functions
- Next.js routes
- middleware

### Go

Extract:

- packages
- structs
- interfaces
- methods
- goroutines
- handlers

Future adapters:

- Rust
- Java
- Kotlin
- C#
- Swift

---

# Symbol Metadata

Each symbol stores:

- Symbol ID
- Name
- Kind
- Language
- Visibility
- Parent Symbol
- File
- Line Range
- Signature
- Documentation
- Hash
- Last Indexed

Hashes are computed from normalized signatures to preserve identity across edits.

---

# Advanced Graph Algorithms

Supported traversals:

- Breadth-First Search (BFS)
- Depth-First Search (DFS)
- Shortest Path
- Reachability
- Connected Components
- Dependency Closure

Example queries:

- What depends on this service?
- Which APIs call this repository?
- What breaks if this interface changes?

---

# Cache Architecture

Layers

L1

In-memory graph cache

L2

Persistent graph database

L3

Serialized Repository Memory snapshots

Cache Keys

repository-id

graph-version

commit-sha

symbol-id

---

# Cache Invalidation

Triggers

- File modified
- File deleted
- Branch switched
- Merge completed
- Dependency updated

Invalidation is localized to affected graph regions.

---

# Prompt Assembly Interface

The Prompt Assembly Engine MUST NOT inspect raw repositories.

Instead it requests Repository Memory.

Request

```json
{
  "intent":"Add JWT authentication",
  "repositoryId":"..."
}
```

Response

Ordered engineering context:

- Relevant files
- Symbols
- APIs
- Dependencies
- Architectural notes

Prompt assembly remains deterministic.

---

# Optimization Strategy

Optimizations

- Parallel parsing
- Parallel symbol extraction
- Lazy graph expansion
- AST reuse
- Cached traversal paths

Target utilization:

- CPU bound parsing
- Memory efficient graph storage

---

# Benchmark Methodology

Repository Sizes

Small (<10k LOC)

Medium (100k LOC)

Large (1M LOC)

Measure

- Parse time
- Index time
- Graph build
- Cache hit ratio
- Query latency
- Incremental update latency

---

# Observability

Metrics

repository_memory_nodes

repository_memory_edges

graph_query_duration_ms

incremental_updates_total

cache_hit_ratio

parse_failures_total

Distributed tracing SHOULD span:

- parsing
- extraction
- graph update
- ranking
- prompt assembly

---

# Production Guidelines

Repository Memory is immutable per graph version.

All updates produce a new graph version.

Rollback is supported by activating a previous graph snapshot.

---

# Acceptance Criteria

✓ Multi-language extraction implemented

✓ Stable symbol metadata

✓ Graph algorithms operational

✓ Three-layer cache implemented

✓ Incremental invalidation working

✓ Prompt Assembly API consumes Repository Memory only

✓ Benchmarks meet latency targets

---

# Next

RFC-002 Part 4

- Database schema
- Service interfaces
- Event contracts
- Security model
- Failure recovery
- Deployment architecture
- Testing matrix
- Final acceptance
