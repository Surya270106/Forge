
# RFC-006 (Part 2)
# Retrieval Ranking, Prompt Templates & Model Routing

**Status:** Draft v1.0

## Purpose

Defines the internal algorithms of the AI Context Engine (ACE): deterministic
context retrieval, token budgeting, prompt template management, provider
abstraction, routing, caching, and optimization.

---

# Retrieval Ranking Engine

Signals:

- graph distance
- symbol references
- call graph proximity
- import relationships
- ownership
- recency
- semantic similarity

Final score is a weighted deterministic ranking.

---

# Context Budgeting

Budgets by task:

| Size | Files | Target Tokens |
|------|------:|--------------:|
| Small | ≤5 | 8k |
| Medium | ≤20 | 24k |
| Large | ≤50 | 64k |
| Enterprise | Adaptive | 128k+ |

Priority order:

1. Active symbols
2. Direct dependencies
3. Related tests
4. Documentation
5. Historical context

---

# Context Compression

Methods

- remove duplicates
- summarize metadata
- collapse repeated imports
- keep symbol boundaries
- preserve file references

Compression must never remove required context.

---

# Prompt Template Engine

Prompt sections:

- System
- Repository Context
- Objective
- Constraints
- Acceptance Criteria
- Output Schema

Templates are versioned and immutable.

---

# Prompt Lifecycle

Draft

↓

Validated

↓

Published

↓

Deprecated

↓

Archived

---

# Provider Abstraction

Supported providers:

- Anthropic Claude
- OpenAI
- Google Gemini
- Local models

Common interface:

- generate()
- stream()
- embeddings()
- health()

---

# Model Routing

Routing inputs:

- reasoning complexity
- latency budget
- token budget
- cost budget
- provider health
- user preference

Fallback order is configurable.

---

# Prompt Cache

Cache Keys

- prompt version
- repository graph
- request hash
- provider
- model

Invalidation:

- graph changes
- template changes
- model updates

---

# Internal APIs

ContextService
- retrieve()
- rank()
- compress()

PromptService
- build()
- validate()
- version()

RouterService
- select()
- fallback()

ProviderAdapter
- invoke()
- stream()

---

# Performance Budgets

Context retrieval <150ms

Ranking <75ms

Prompt assembly <200ms

Routing <25ms

Cache hit >90%

---

# Observability

Metrics

- context_tokens
- retrieval_latency_ms
- routing_latency_ms
- prompt_cache_hits
- provider_failovers
- prompt_versions_total

Tracing

- retrieval
- ranking
- compression
- routing
- provider call

---

# Acceptance Criteria

✓ Deterministic retrieval

✓ Token budgeting enforced

✓ Prompt templates versioned

✓ Multi-provider routing operational

✓ Cache implemented

✓ Metrics exported

---

# Next

RFC-006 Part 3

- Response normalization
- Structured output validation
- Guardrails
- AI memory integration
- Conversation state
- Safety policies
- Self-evaluation
- Production architecture
