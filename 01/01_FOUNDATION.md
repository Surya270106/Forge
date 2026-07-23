# Forge AI — 01_FOUNDATION.md

**Version:** 0.1.0 (Draft)  
**Status:** Living Architecture Document

---

# Executive Summary

Forge AI is **not** an AI coding assistant.

Forge AI is an **Autonomous Software Engineering Platform** that can understand an entire software system, reason about engineering work, execute code changes, verify correctness, and produce production-ready pull requests.

The LLM is one component of the system—not the system itself.

---

# Vision

Create the most trustworthy autonomous software engineer for real-world repositories.

Core philosophy:

- Understand before changing.
- Plan before coding.
- Verify before committing.
- Measure everything.
- Keep humans in control of high-risk actions.

---

# Problem Statement

Current AI coding tools:

- operate on limited context
- repeatedly rediscover repositories
- generate code before understanding architecture
- provide little observability
- rarely verify changes end-to-end

Forge solves these problems with persistent repository understanding and deterministic engineering workflows.

---

# Product Goals

## Primary Goals

1. Repository Cognition
2. Autonomous Planning
3. Safe Code Execution
4. Continuous Verification
5. Pull Request Generation
6. Engineering Observability

## Non-Goals

- General chatbot
- "Chat with your repo"
- Another RAG demo
- IDE autocomplete competitor

---

# Five Pillars

## 1. Repository Cognition

Build a persistent knowledge model of every repository.

Includes:

- AST
- Symbols
- Dependency graph
- API graph
- Database schema
- Component hierarchy
- Test map

---

## 2. Engineering Planning

Every request becomes a Task Graph.

Example:

Issue

↓

Impact Analysis

↓

Architecture Validation

↓

Execution Plan

---

## 3. Autonomous Execution

Capabilities:

- create files
- modify files
- refactor
- rename
- update configs
- migrations
- documentation

---

## 4. Verification

Every change must pass:

- compilation
- linting
- unit tests
- integration tests
- security checks

No successful verification = no merge recommendation.

---

## 5. Continuous Learning

Store execution metadata:

- latency
- retries
- failures
- success rate
- cost
- confidence

Future runs improve using these observations.

---

# High-Level Workflow

```text
User Request
      │
      ▼
Intent Analysis
      │
      ▼
Repository Cognition Engine
      │
      ▼
Impact Analysis
      │
      ▼
Planning Engine
      │
      ▼
Execution Engine
      │
      ▼
Sandbox
      │
      ▼
Verification
      │
      ▼
Repair Loop
      │
      ▼
Evaluation
      │
      ▼
Git Engine
      │
      ▼
Pull Request
```

---

# System Components

- Repository Cognition Engine
- Planner
- Context Engine
- Execution Engine
- Sandbox
- Verification Engine
- Repair Engine
- Git Engine
- Evaluation Engine
- Web Dashboard

---

# Engineering Principles

1. AI never edits blindly.
2. Repository understanding precedes execution.
3. Every action is observable.
4. Every decision has rationale.
5. Human approval for destructive actions.
6. Architecture over prompts.
7. Deterministic pipelines wherever possible.

---

# Technology Stack

## Frontend

- Next.js
- React
- Tailwind CSS
- shadcn/ui
- Zustand
- TanStack Query

## Backend

- FastAPI
- Python

## Storage

- PostgreSQL
- Redis

## Parsing

- Tree-sitter

## Search

- Hybrid semantic + structural retrieval

## Infrastructure

- Docker
- GitHub
- Vercel (frontend)
- Railway/Fly/Render (backend workers)

---

# Repository Structure

```text
forge-ai/
├── apps/
│   ├── web/
│   └── api/
├── packages/
│   ├── core/
│   ├── planner/
│   ├── cognition/
│   ├── execution/
│   ├── evaluation/
│   └── shared/
├── workers/
├── docs/
└── docker/
```

---

# Success Metrics

- Repository indexing < 2 minutes
- Planning accuracy > 90%
- Test pass rate > 95%
- Full audit trail for every execution
- PR generation with reproducible workflow

---

# Future Vision

Forge AI evolves into an Engineering Operating System where AI agents collaborate with humans across planning, implementation, verification, deployment, and maintenance.

This document is the architectural source of truth. Future documents (02_CORE_ENGINE.md, 03_PRODUCT.md, and 04_INFRASTRUCTURE.md) expand each subsystem in implementation-level detail.
