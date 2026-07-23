# Forge AI — 04_PLANNER.md

**Version:** 0.1.0  
**Component:** Planning Engine

---

# Purpose

The Planning Engine transforms a human engineering request into a deterministic, executable Task Graph.

The planner NEVER edits code.

Its responsibility is to understand the request, analyze repository impact, decompose work into safe tasks, estimate risk, and prepare execution.

---

# Responsibilities

- Understand user intent
- Classify request type
- Analyze repository impact
- Estimate risk
- Generate Task Graph
- Select required tools
- Produce verification strategy
- Request human approval when necessary

---

# Planner Pipeline

```text
Natural Language Request
        │
        ▼
Intent Analyzer
        │
        ▼
Request Classification
        │
        ▼
Repository Context
        │
        ▼
Impact Analysis
        │
        ▼
Task Decomposition
        │
        ▼
Dependency Resolution
        │
        ▼
Tool Selection
        │
        ▼
Verification Planning
        │
        ▼
Execution Plan
```

---

# Intent Analyzer

Convert free-form language into structured intent.

Example

Input:

> Add JWT authentication.

Output

```yaml
type: feature
domain:
  - backend
  - frontend
risk: medium
requires_database: false
requires_tests: true
```

---

# Request Categories

Supported request types:

- Feature
- Bug Fix
- Refactor
- Documentation
- Performance
- Security
- Test Generation
- Dependency Upgrade
- Configuration
- Code Cleanup

Every request belongs to exactly one primary category.

---

# Risk Assessment

Risk Levels

## Low

- Documentation
- Tests
- Comments

## Medium

- New feature
- Refactor
- API update

## High

- Authentication
- Database
- Payments
- Infrastructure
- Secrets
- Large-scale rename

High-risk operations require explicit approval.

---

# Impact Analysis

Planner requests data from the Repository Cognition Engine.

Outputs:

- impacted files
- affected APIs
- services
- components
- tests
- database entities
- dependencies

Example

```text
Affected Files: 12
APIs: 3
React Components: 5
Database Tables: 0
Tests: 4
```

---

# Task Decomposition

Large requests are split into atomic tasks.

Example

```text
Feature
│
├── Create JWT Utility
├── Middleware
├── Login API
├── Frontend UI
├── Unit Tests
└── Documentation
```

Rules

- One responsibility per task
- Retryable
- Independent when possible
- Explicit dependencies

---

# Task Graph

Tasks form a Directed Acyclic Graph (DAG).

Example

```text
JWT Utility
      │
      ▼
Middleware
      │
      ▼
Login API
      ├─────────┐
      ▼         ▼
Frontend     Unit Tests
      │
      ▼
Documentation
```

Cycles are forbidden.

---

# Tool Selection

Planner maps each task to tools.

Examples

| Task | Tools |
|------|-------|
| Edit file | ReadFile, WriteFile |
| Rename | SearchSymbol, RenameSymbol |
| Verify | RunTests, Build |
| Git | CreateBranch, Commit |

Planner never executes tools.

---

# Verification Strategy

Each task declares required verification.

Possible checks:

- Build
- Type Check
- Lint
- Unit Tests
- Integration Tests
- Security Scan

Verification is planned before execution begins.

---

# Human Approval Gates

Planner pauses execution when:

- High-risk task
- Large file count
- Database migration
- Secret modification
- File deletion
- Dependency removal

Approval payload contains:

- summary
- impact
- risk
- estimated duration

---

# Planner Output

The planner emits a structured execution plan.

Example

```yaml
request:
  feature: JWT Authentication

risk: Medium

tasks:
  - JWT Utility
  - Middleware
  - Login API
  - Frontend
  - Tests

verification:
  - build
  - lint
  - unit_tests

estimated_files: 12
estimated_duration: 8m
```

---

# Failure Handling

Planner failures include:

- Missing repository
- Unsupported language
- Ambiguous request
- Insufficient context

Planner must fail safely and request clarification.

---

# Metrics

Track:

- planning latency
- task count
- graph depth
- approval rate
- execution success
- planner accuracy

---

# Design Principles

1. Planning before execution.
2. Deterministic outputs.
3. Small executable tasks.
4. Explainable reasoning.
5. Safe defaults.
6. Human oversight for high-risk work.

---

# Future Roadmap

- Multi-agent planning
- Parallel task scheduling
- Automatic issue decomposition
- Cross-repository planning
- Cost-aware planning
- Learning from historical executions

---

# Engineering Principle

A great engineer never starts coding immediately.

Forge follows the same philosophy.

The planner exists to ensure every execution begins with understanding, structure, and measurable intent rather than guesswork.
