
# RFC-006 (Part 1)
# AI Context Engine & Prompt Orchestrator — Foundations

**Status:** Draft v1.0

## Executive Summary

The AI Context Engine (ACE) is the intelligence gateway of Forge AI. It bridges
Repository Memory, the Planning Engine, the Execution Engine, and the Verification
Engine with large language models (LLMs).

Rather than sending raw repositories to an LLM, ACE assembles deterministic,
minimal, and explainable engineering context.

Prompt Orchestrator is responsible for building reproducible prompts, selecting
models, enforcing constraints, and producing auditable AI interactions.

---

# Purpose

ACE ensures:

- Deterministic context retrieval
- Minimal context windows
- Explainable prompt construction
- Model independence
- Versioned prompt templates
- Safe AI interactions

---

# Goals

- Assemble repository context
- Build deterministic prompts
- Route requests to appropriate models
- Support multiple providers
- Track prompt versions
- Preserve reproducibility

---

# Non-Goals

- Repository parsing
- Planning
- Code execution
- Verification
- Deployment

Those responsibilities belong to previous RFCs.

---

# AI Philosophy

1. Repository Memory is the only source of engineering truth.
2. Context should be minimal but sufficient.
3. Prompt templates are version-controlled artifacts.
4. Models are interchangeable.
5. Every AI decision must be traceable.

---

# High-Level Architecture

```text
Repository Memory
        │
        ▼
Context Retrieval Engine
        │
        ▼
Context Optimizer
        │
        ▼
Prompt Orchestrator
        │
        ▼
Model Router
        │
        ▼
LLM Provider
        │
        ▼
Response Validator
```

---

# Core Components

## Context Retrieval Engine

Retrieves:

- files
- symbols
- APIs
- dependencies
- documentation
- architectural notes

Retrieval is deterministic.

---

## Context Optimizer

Responsibilities

- remove redundant context
- compress metadata
- preserve semantic relationships
- enforce token budgets

---

## Prompt Orchestrator

Constructs prompts from:

- system instructions
- repository context
- engineering objective
- constraints
- verification requirements

Prompt generation is deterministic.

---

## Model Router

Chooses the best model using:

- task type
- context size
- latency budget
- cost budget
- reasoning complexity

Supported Providers

- Anthropic Claude
- OpenAI
- Google Gemini
- Local models

---

## Response Validator

Ensures responses:

- follow schema
- satisfy constraints
- contain required sections
- remain deterministic where possible

---

# Context Pipeline

```text
Engineering Request
        │
        ▼
Repository Memory Query
        │
        ▼
Ranking
        │
        ▼
Optimization
        │
        ▼
Prompt Assembly
        │
        ▼
Model Routing
        │
        ▼
LLM Response
        │
        ▼
Validation
```

---

# Functional Requirements

- Deterministic retrieval
- Prompt versioning
- Multi-provider routing
- Context optimization
- Structured responses
- Full observability

---

# Non-Functional Requirements

- Stateless
- Explainable
- Observable
- Provider agnostic
- Scalable
- Reproducible

---

# Acceptance Criteria

✓ Context retrieved

✓ Prompt assembled

✓ Model selected

✓ Response validated

✓ Prompt version recorded

✓ Traceability maintained

---

# Next

RFC-006 Part 2

- Retrieval ranking algorithms
- Token budgeting
- Prompt template engine
- Model routing algorithms
- Provider abstraction
- Caching
- Context compression
- Prompt lifecycle
