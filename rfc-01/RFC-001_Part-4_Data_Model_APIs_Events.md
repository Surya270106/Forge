
# RFC-001 (Part 4)
# Data Model, API Contracts, Event Bus & System Interfaces

## Purpose

This section defines the persistent storage, service interfaces, event-driven
architecture and API contracts for the Repository Import subsystem.

---

# Logical Architecture

```text
Dashboard
    │
 REST API
    │
Repository Service
    │
 ├── GitHub Adapter
 ├── Clone Service
 ├── Scanner
 ├── Manifest Builder
 └── Event Publisher
    │
 PostgreSQL
 Redis
 Event Bus
```

---

# Database Schema

## repositories

| Field | Type |
|--------|------|
| id | UUID |
| owner | TEXT |
| name | TEXT |
| default_branch | TEXT |
| framework | JSONB |
| languages | JSONB |
| status | TEXT |
| commit_sha | TEXT |
| created_at | TIMESTAMP |
| updated_at | TIMESTAMP |

Indexes

- owner
- status
- commit_sha

---

## repository_manifests

| Field | Type |
|--------|------|
| id | UUID |
| repository_id | UUID |
| version | INTEGER |
| manifest | JSONB |
| created_at | TIMESTAMP |

---

## import_jobs

Tracks lifecycle of every import.

Fields

- id
- repository_id
- worker_id
- state
- retries
- duration_ms
- started_at
- finished_at

---

# REST API

## Import Repository

POST /api/v1/repositories/import

Returns

202 Accepted

---

## List Repositories

GET /api/v1/repositories

---

## Repository Details

GET /api/v1/repositories/{id}

---

## Import Status

GET /api/v1/imports/{id}

---

# Response Model

```json
{
 "id":"",
 "status":"READY",
 "framework":"nextjs",
 "languages":["typescript"],
 "files":1324
}
```

---

# Event Bus

Events emitted

repository.created

repository.authenticated

repository.cloned

repository.scanned

repository.detected

repository.manifest.saved

repository.ready

repository.failed

All events are immutable.

---

# Event Payload

```json
{
 "event":"repository.ready",
 "repositoryId":"",
 "timestamp":"",
 "workerId":"",
 "durationMs":0
}
```

---

# Service Interfaces

RepositoryImporter

- import()
- cancel()
- retry()

RepositoryScanner

- scan()

FrameworkDetector

- detect()

ManifestBuilder

- build()

RepositoryStore

- save()
- update()
- find()

---

# Dependency Injection

Every component depends on interfaces,
never concrete implementations.

Example

RepositoryImporter

↓

RepositoryScannerInterface

↓

ScannerImplementation

Allows testing and future replacement.

---

# Configuration

Environment Variables

GITHUB_CLIENT_ID

GITHUB_CLIENT_SECRET

DATABASE_URL

REDIS_URL

WORKSPACE_ROOT

MAX_REPOSITORY_SIZE

IMPORT_TIMEOUT

---

# Sequence Diagram

```text
User
 │
 ▼
API
 │
 ▼
Importer
 │
 ▼
Clone
 │
 ▼
Scanner
 │
 ▼
Manifest
 │
 ▼
Database
 │
 ▼
Event Bus
 │
 ▼
Dashboard
```

---

# Observability

Every request receives

- request id
- correlation id
- worker id

Metrics exported

- import_duration_seconds
- clone_duration_seconds
- repositories_total
- failed_imports_total
- scanner_duration_seconds

---

# Logging Standard

Structured JSON logs only.

Required fields

- timestamp
- request_id
- repository_id
- service
- operation
- duration
- status
- error_code

---

# Error Codes

AUTH_INVALID

CLONE_FAILED

SCAN_FAILED

FRAMEWORK_UNKNOWN

IMPORT_TIMEOUT

DATABASE_ERROR

MANIFEST_ERROR

---

# Acceptance Criteria

✓ API documented

✓ Database normalized

✓ Interfaces defined

✓ Events published

✓ Structured logging

✓ Metrics exported

✓ Dependency injection enforced

---

Next:
RFC-001 Part 5
Security, retry algorithms, deployment, monitoring,
complete testing strategy, appendices and final acceptance.
