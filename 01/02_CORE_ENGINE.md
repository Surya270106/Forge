# Forge AI — 02_CORE_ENGINE.md

**Version:** 0.1.0

# Purpose

The Core Engine is the autonomous engineering runtime of Forge AI.
It converts a natural language engineering request into a verified pull request.

---

# Core Pipeline

```text
Request
  ↓
Intent Analyzer
  ↓
Repository Cognition Engine
  ↓
Impact Analyzer
  ↓
Planning Engine
  ↓
Task Graph
  ↓
Context Engine
  ↓
Execution Engine
  ↓
Sandbox
  ↓
Verification Engine
  ↓
Repair Loop
  ↓
Evaluation Engine
  ↓
Git Engine
  ↓
Pull Request
```

---

# Repository Cognition Engine

Responsible for persistent understanding of every repository.

## Responsibilities

- Clone/index repository
- Parse source code using Tree-sitter
- Build symbol graph
- Build dependency graph
- Detect frameworks
- Extract API routes
- Extract database schema
- Build architecture graph
- Maintain repository knowledge graph

## Outputs

- Repository metadata
- Symbol index
- Import graph
- Call graph
- Component graph
- Test map

---

# Knowledge Graph

Stores relationships instead of chunks.

Example

```text
AuthService
 ├── depends_on Prisma
 ├── exposes Login()
 ├── used_by LoginPage
 └── tested_by auth.test.ts
```

---

# Intent Analyzer

Transforms user request into structured intent.

Input:

> Add JWT Authentication

Output

- Feature
- Medium Risk
- Backend + Frontend
- Database changes: No

---

# Impact Analyzer

Determines:

- affected files
- affected modules
- APIs
- tests
- migrations
- dependencies

Produces an Impact Report before planning.

---

# Planning Engine

Creates deterministic Task Graphs.

Example

```text
Task 1
Create JWT utility

↓

Task 2
Middleware

↓

Task 3
Update Login API

↓

Task 4
Frontend

↓

Task 5
Tests
```

Planning rules

- smallest safe task
- explicit dependencies
- resumable
- retryable

---

# Context Engine

Never sends the entire repository.

Ranks context using:

- symbols
- imports
- dependency distance
- architecture relevance
- semantic similarity

Produces optimized prompt context.

---

# Tool Registry

Every capability is a tool.

Examples

- ReadFile
- WriteFile
- SearchSymbol
- RenameSymbol
- RunTests
- GitCommit
- CreateBranch
- ExecuteCommand

The planner selects tools, never hardcodes workflows.

---

# Execution Engine

Executes tasks sequentially.

Capabilities

- create
- modify
- rename
- refactor
- delete
- documentation
- migrations

Every change generates an execution log.

---

# Sandbox

All execution occurs inside isolated containers.

Runs

- npm test
- pytest
- cargo test
- go test
- lint
- build

Never modifies host machine.

---

# Verification Engine

Checks

- compile
- lint
- tests
- type safety
- formatting
- security scan

Only verified changes continue.

---

# Repair Loop

If verification fails:

```text
Failure
 ↓
Collect Logs
 ↓
Analyze Root Cause
 ↓
Generate Fix
 ↓
Re-run Verification
```

Maximum retries configurable.

---

# Evaluation Engine

Records

- latency
- token usage
- retries
- files changed
- confidence
- execution time
- success rate
- estimated cost

Creates permanent execution history.

---

# Git Engine

Responsible for

- branch creation
- commits
- commit messages
- changelog
- pull requests

Commit messages follow Conventional Commits.

---

# Event Bus

Each stage emits events.

Examples

- repository.indexed
- planning.completed
- execution.started
- verification.failed
- repair.completed
- pr.created

Frontend subscribes for live updates.

---

# Database Entities

Core tables

- repositories
- executions
- task_graphs
- tasks
- repository_graph
- evaluations
- pull_requests
- execution_logs

---

# Design Principles

1. AI never skips verification.
2. Repository understanding is persistent.
3. Every action is reproducible.
4. Every decision is observable.
5. Components remain independently replaceable.
6. Humans approve destructive actions.

---

# Future Enhancements

- Multi-agent planner
- Local model fallback
- Distributed workers
- MCP integration
- Browser automation
- Multi-repository reasoning
- Self-optimization
