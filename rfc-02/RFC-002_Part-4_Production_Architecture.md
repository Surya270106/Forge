
# RFC-002 (Part 4)
# Persistence, Services, Security, Operations & Production Readiness

Status: Draft v1.0

## Purpose

This document finalizes the Repository Memory Engine (RME) specification by
defining persistence, service contracts, operational architecture, resilience,
deployment, and production requirements.

---

# Persistence Architecture

Repository Memory is persisted independently of the source repository.

Storage Layers

- PostgreSQL (metadata)
- Graph Store (nodes & edges)
- Redis (hot cache)
- Snapshot Storage (serialized graph versions)

Each graph version is immutable once committed.

---

# Database Schema

## memory_graphs

- id (UUID)
- repository_id
- version
- commit_sha
- node_count
- edge_count
- created_at

## memory_nodes

- id
- graph_id
- symbol_id
- type
- language
- name
- file_path
- metadata (JSONB)

## memory_edges

- id
- graph_id
- source_symbol
- target_symbol
- relationship
- metadata (JSONB)

Indexes

- symbol_id
- graph_id
- relationship
- repository_id

---

# Service Interfaces

RepositoryMemoryService

- build()
- rebuild()
- query()
- snapshot()
- restore()

GraphQueryService

- neighbors()
- shortest_path()
- dependencies()
- callers()
- callees()

ContextRankingService

- rank()
- explain()

ParserRegistry

- register()
- resolve()
- supported_languages()

---

# Dependency Injection

All services depend on interfaces only.

Example

Planner
    │
    ▼
RepositoryMemoryService
    │
    ▼
RepositoryMemoryRepository

Concrete implementations remain replaceable.

---

# Event Contracts

Events

memory.build.started

memory.graph.created

memory.graph.updated

memory.snapshot.created

memory.query.executed

memory.failed

Every event contains

- repository_id
- graph_version
- timestamp
- worker_id
- correlation_id

Events are append-only.

---

# Security Model

Repository Memory never stores:

- GitHub tokens
- secrets
- environment variables
- decrypted credentials

Access Control

- Repository owner
- Team members
- Organization administrators

All API requests require authorization.

---

# Failure Recovery

Recoverable

- parser failure
- graph build timeout
- cache miss
- partial extraction

Fatal

- graph corruption
- snapshot corruption
- storage failure

Recovery Strategy

1. Preserve previous graph
2. Roll back to last valid snapshot
3. Retry incremental rebuild
4. Escalate if recovery fails

---

# Deployment Architecture

Production Topology

```text
           Next.js Dashboard
                   │
                   ▼
              FastAPI Gateway
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
 Repository Memory      Planner API
        │
        ▼
 Worker Queue (Redis)
        │
        ▼
 Index Workers
        │
        ▼
 PostgreSQL + Graph Store
```

Workers are stateless and horizontally scalable.

---

# Observability

Metrics

- memory_build_duration_seconds
- graph_nodes_total
- graph_edges_total
- graph_queries_total
- graph_query_latency_ms
- cache_hit_ratio
- snapshot_restore_total

Tracing

Every request spans:

- parser
- extractor
- graph builder
- persistence
- ranking

---

# Operational Runbook

Graph Build Failure

1. Validate parser diagnostics
2. Compare graph version
3. Restore previous snapshot
4. Trigger incremental rebuild

Cache Corruption

1. Invalidate cache
2. Reload graph from storage
3. Rebuild ranking cache

Snapshot Failure

1. Mark snapshot invalid
2. Retain previous snapshot
3. Schedule background rebuild

---

# Testing Matrix

Unit

- parser registry
- graph builder
- ranking
- cache

Integration

- Next.js project
- FastAPI project
- Monorepo
- Polyglot repository

Load

- 1M nodes
- 5M edges
- 500 concurrent queries

Chaos

- worker crash
- database restart
- cache eviction
- disk exhaustion

---

# Performance Objectives

Repository Build

< 60 seconds (100k files)

Incremental Update

< 5 seconds

Graph Query

< 100 milliseconds

Cache Hit Ratio

> 90%

Memory Consumption

Linear with repository size

---

# Definition of Done

RFC-002 is complete when:

✓ Repository Memory builds successfully

✓ Multi-language parsing operational

✓ Stable symbol identities maintained

✓ Dependency graph generated

✓ Call graph generated

✓ Incremental indexing implemented

✓ Graph versioning supported

✓ Snapshot restoration operational

✓ Context ranking functional

✓ Public APIs documented

✓ Metrics exported

✓ Security enforced

✓ Tests passing

---

# Future Extensions

Deferred to future RFCs

- Semantic search
- Cross-repository graphs
- Team knowledge graphs
- Architecture drift detection
- Automatic ownership inference
- AI-assisted graph summarization

---

# RFC-002 Completion Summary

The Repository Memory Engine provides the canonical engineering representation
used throughout Forge AI. All downstream systems—including the Planner,
Execution Engine, Verification Engine, and AI Context Builder—consume Repository
Memory rather than raw source code.

This architecture enables deterministic reasoning, efficient incremental
updates, and scalable multi-language repository understanding.

**END OF RFC-002**
