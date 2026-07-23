
# RFC-001 (Part 3)
# Repository Scanner Internals, Detection Algorithms & Manifest Generation

## Purpose

This document specifies the internal design of the Repository Scanner. The scanner
is responsible for transforming a cloned repository into a normalized repository
manifest that can be consumed by later stages of the Repository Memory Engine.

---

# Scanner Responsibilities

The scanner SHALL:

- Traverse the repository safely
- Respect ignore rules
- Classify every file
- Detect repository boundaries
- Build a normalized file inventory
- Produce metadata for downstream systems

The scanner SHALL NOT:

- Parse ASTs
- Execute source code
- Generate embeddings
- Call LLMs

---

# Scanner Pipeline

```text
Workspace
    │
    ▼
Directory Walker
    │
    ▼
Ignore Engine
    │
    ▼
File Classifier
    │
    ▼
Language Detector
    │
    ▼
Framework Detector
    │
    ▼
Manifest Builder
    │
    ▼
Metadata Store
```

---

# Directory Walker

Traversal requirements:

- Depth-first traversal
- Deterministic ordering
- Symlink detection
- Hidden file support
- Configurable depth limits

Traversal outputs:

- Absolute path
- Relative path
- File size
- Last modified timestamp
- SHA-256 checksum (optional for large repositories)

---

# Ignore Engine

Ignore priority:

1. System ignore rules
2. User-defined rules
3. .gitignore
4. Generated artifact patterns

Default ignored directories:

- .git
- node_modules
- .next
- build
- dist
- out
- target
- coverage
- .venv
- __pycache__

Ignored file types:

- binaries
- archives
- media
- compiled artifacts

---

# File Classification

Each file is assigned a category.

Categories:

- Source
- Configuration
- Documentation
- Test
- Build
- Dependency
- Asset
- Generated
- Unknown

Example:

src/main.py -> Source

README.md -> Documentation

package.json -> Configuration

pytest.ini -> Test Configuration

---

# Language Detection Algorithm

Priority order:

1. File extension
2. Shebang
3. Build system
4. Package manifest
5. Content heuristic

Supported Languages (MVP):

- Python
- TypeScript
- JavaScript
- Go

Future:

- Rust
- Java
- Kotlin
- C#
- C++
- Swift

Confidence score SHALL be produced for each language.

---

# Framework Detection Heuristics

Node.js

package.json:

- next
- react
- express
- nestjs
- remix

Python

requirements.txt / pyproject.toml:

- fastapi
- flask
- django

Java

pom.xml

- spring-boot

Go

go.mod

Framework detection stores:

- framework name
- version (if available)
- confidence
- detection source

---

# Manifest Builder

Manifest sections:

Repository

Languages

Frameworks

Directory Tree

Entrypoints

Configurations

Dependency Files

Documentation

Test Locations

Assets

Statistics

The manifest SHALL be versioned.

---

# Repository Statistics

Generate:

- total files
- source files
- test files
- documentation files
- largest directories
- language distribution
- repository size
- average file size

---

# Performance Budget

Target metrics:

- 100k files supported
- Scan throughput > 5000 files/sec
- Ignore engine < 10 ms lookup
- Manifest generation < 5 s (medium repository)

---

# Caching Strategy

Cache:

- manifest
- language detection
- framework detection
- directory hashes

Incremental scan:

If directory hash unchanged:

Skip subtree.

Else:

Rescan only modified subtree.

---

# Error Handling

Recoverable:

- unreadable file
- permission issue
- broken symlink

Fatal:

- workspace missing
- repository corruption

Scanner continues whenever safe.

---

# Testing Matrix

Unit Tests

- directory traversal
- ignore rules
- language detection
- framework detection
- manifest serialization

Integration Tests

- Next.js repository
- FastAPI repository
- Monorepo
- Large repository
- Empty repository

Performance Tests

- 10k files
- 50k files
- 100k files

---

# Folder Structure

packages/cognition/scanner/

walker.py

ignore_engine.py

classifier.py

language_detector.py

framework_detector.py

manifest_builder.py

statistics.py

cache.py

tests/

---

# Acceptance Criteria

✓ Traverses repository deterministically

✓ Ignores generated artifacts

✓ Detects supported languages

✓ Detects frameworks

✓ Generates versioned manifest

✓ Produces repository statistics

✓ Supports incremental scanning

✓ Meets performance targets

---

# Next

RFC-001 Part 4

- PostgreSQL schema
- API contracts
- Event bus
- Interface definitions
- Dependency injection
- Configuration
- Sequence diagrams
- Observability
- Metrics
