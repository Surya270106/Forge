# Forge AI — 03_REPOSITORY_COGNITION.md

**Version:** 0.1.0

# Purpose

The Repository Cognition Engine (RCE) is Forge AI's competitive advantage.

Unlike traditional RAG systems, the RCE builds and maintains a persistent, structured understanding of an entire software repository.

The objective is not to answer questions about code.

The objective is to reason like a senior engineer before making changes.

---

# Responsibilities

- Clone and synchronize repositories
- Detect languages and frameworks
- Parse every source file into an AST
- Extract symbols
- Build dependency relationships
- Build a Repository Knowledge Graph
- Support incremental indexing
- Produce optimized engineering context

---

# Architecture

```text
Git Repository
      │
      ▼
Repository Scanner
      │
      ▼
Language Detector
      │
      ▼
Tree-sitter Parser
      │
      ▼
AST Generator
      │
      ▼
Graph Builders
 ├─ Symbol Graph
 ├─ Dependency Graph
 ├─ Call Graph
 ├─ API Graph
 ├─ Database Graph
 └─ Component Graph
      │
      ▼
Repository Knowledge Graph
      │
      ▼
Context Ranking Engine
      │
      ▼
Prompt Assembly
```

---

# Repository Scanner

Collects:

- file tree
- configuration files
- lockfiles
- package manifests
- build systems
- environment files
- documentation
- test locations

Outputs a normalized repository manifest.

---

# Framework Detection

Automatically identifies technologies.

Examples

- Next.js
- React
- FastAPI
- Django
- Flask
- Express
- Spring Boot
- Prisma
- Drizzle
- PostgreSQL
- Redis

Framework detection influences downstream planning.

---

# Tree-sitter Pipeline

Every supported language is parsed into an Abstract Syntax Tree.

Supported initially

- Python
- TypeScript
- JavaScript
- Go

Future

- Java
- Rust
- C#
- Kotlin

Never rely on regex for code understanding.

---

# Symbol Extraction

Extract:

- classes
- interfaces
- functions
- methods
- enums
- types
- decorators
- routes
- models
- constants

Every symbol receives a stable identifier.

---

# Dependency Graph

Track relationships between files and modules.

Example

```text
LoginPage
    │
    ▼
AuthService
    │
    ▼
JWT
    │
    ▼
Database
```

Used for impact analysis.

---

# Call Graph

Track function-to-function relationships.

Example

```text
login()

↓

authenticate()

↓

createToken()

↓

saveSession()
```

Supports context ranking and repair.

---

# API Graph

Discover

- REST endpoints
- handlers
- middleware
- request models
- response models
- authentication

---

# Database Graph

Extract

- ORM models
- migrations
- tables
- relationships
- indexes
- constraints

---

# Component Graph

Frontend understanding.

Includes

- React components
- layouts
- routes
- hooks
- providers
- state stores

---

# Repository Knowledge Graph

The central representation.

Node Types

- File
- Symbol
- Component
- Service
- API
- Database
- Test
- Configuration

Edge Types

- imports
- calls
- owns
- depends_on
- tested_by
- exposes
- implements

This graph is persistent and updated incrementally.

---

# Incremental Indexing

Never rebuild everything.

Pipeline

```text
Git Change
    │
    ▼
Changed Files
    │
    ▼
Reparse
    │
    ▼
Update Graph
```

---

# Context Ranking

Ranking signals

- dependency distance
- graph centrality
- semantic similarity
- recent modifications
- planner relevance
- execution history

The highest-ranked nodes become execution context.

---

# Prompt Assembly

Context package contains

- repository summary
- relevant files
- symbols
- dependencies
- APIs
- database entities
- tests
- architectural rules

The full repository is never sent to the LLM.

---

# Caching Strategy

Cache

- AST
- graphs
- embeddings
- summaries
- framework metadata

Invalidate only affected nodes after repository updates.

---

# Performance Targets

- Initial indexing < 120 seconds
- Incremental indexing < 5 seconds
- Graph lookup < 50 ms
- Context assembly < 1 second

---

# Failure Handling

If parsing fails

1. log error
2. isolate file
3. continue indexing
4. mark repository partially indexed
5. retry asynchronously

Repository indexing should never fail because of one broken file.

---

# Future Roadmap

- Cross-repository reasoning
- Monorepo awareness
- Ownership graph
- Architecture drift detection
- Technical debt scoring
- Repository evolution timeline
- AI-generated architecture diagrams
- Automatic ADR extraction

---

# Engineering Principle

Forge never asks:

"What files look similar?"

Forge asks:

"How is this software system constructed, and what is the safest way to evolve it?"

That principle guides every decision inside the Repository Cognition Engine.
