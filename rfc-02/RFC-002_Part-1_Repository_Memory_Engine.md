
# RFC-002 (Part 1)
# Repository Memory Engine (RME)

Status: Draft v1.0

## Executive Summary

The Repository Memory Engine (RME) is the core intelligence layer of Forge AI.
It transforms a cloned repository into a structured, queryable engineering
representation. Unlike vector-only approaches, RME builds deterministic program
understanding from syntax trees and semantic relationships.

This RFC specifies the architecture for:

- Tree-sitter parsing
- AST cache
- Symbol extraction
- Dependency graph
- Call graph
- Repository graph
- Incremental indexing
- Context ranking interfaces

LLMs are consumers of Repository Memory, not creators of it.

---

# Goals

- Deterministic repository understanding
- Fast incremental indexing
- Language-agnostic architecture
- Persistent graph storage
- Rich semantic queries

# Non-Goals

- Code generation
- Planning
- Execution
- Verification

---

# High-Level Pipeline

```text
Repository
   │
   ▼
Tree-sitter Parser
   │
   ▼
AST Cache
   │
   ▼
Symbol Extractor
   │
   ▼
Relationship Builder
   │
   ▼
Repository Memory Graph
   │
   ▼
Context Ranking
```

---

# Core Components

1. Parser Registry
2. AST Builder
3. AST Cache
4. Symbol Extractor
5. Import Resolver
6. Dependency Graph Builder
7. Call Graph Builder
8. Repository Graph Store
9. Context Ranking API

---

# Tree-sitter Architecture

Every supported language implements:

- Grammar
- Parser adapter
- Node mapper
- Diagnostics
- Incremental parser

Common interface:

parse(file)->AST
supports(language)->bool
version()->str

---

# AST Model

Each AST stores:

- file id
- language
- parser version
- syntax tree
- diagnostics
- content hash

Hashes enable incremental indexing.

---

# Incremental Indexing

If content hash unchanged:

Reuse AST.

Else:

Reparse file.

Only affected downstream graphs are rebuilt.

---

# Symbol Extraction

Extract:

- classes
- functions
- methods
- interfaces
- enums
- constants
- modules
- routes

Every symbol receives a globally unique Symbol ID.

---

# Relationships

Supported edges:

DECLARES

CALLS

IMPORTS

IMPLEMENTS

EXTENDS

USES

REFERENCES

OWNS

---

# Repository Memory

Repository Memory stores:

Nodes

- files
- directories
- classes
- functions
- APIs
- database models

Edges

- imports
- calls
- ownership
- inheritance
- dependency

Repository Memory becomes the canonical engineering model.

---

# Performance Targets

100k files

Incremental update <5s

AST cache hit >90%

Index throughput >500 files/sec

---

# Acceptance Criteria

✓ Parse repository

✓ Cache ASTs

✓ Extract symbols

✓ Build graph nodes

✓ Build graph edges

✓ Persist Repository Memory

Next: Part 2 - Graph algorithms, dependency resolution, context ranking,
storage schema, APIs, testing and benchmarking.
