# RFC-003 (Part 1)

# Planning Engine — Foundations, Intent Analysis & Planning Pipeline

**Status:** Draft v1.0

## Executive Summary

The Planning Engine is the deterministic reasoning layer of Forge AI. It transforms natural-language engineering requests into reproducible execution plans while consuming Repository Memory as its only architectural source of truth.

## Goals

- Understand engineering intent
- Query Repository Memory
- Analyze impact
- Estimate risk
- Build dependency-aware task graphs
- Produce deterministic execution plans

## Non-Goals

- Editing code
- Running commands
- Git operations
- Deployments

## High-Level Architecture

User Request
→ Intent Analyzer
→ Repository Memory Resolver
→ Impact Analyzer
→ Risk Engine
→ Task Graph Builder
→ Tool Planner
→ Verification Planner
→ Execution Plan

## Core Components

### Intent Analyzer
Classifies requests and extracts engineering domains, ambiguity, and confidence.

### Context Resolver
Queries Repository Memory for APIs, services, symbols, dependencies, entrypoints, ownership and architecture.

### Impact Analyzer
Determines affected files, symbols, APIs, tests, and dependency radius.

### Risk Engine
Low: docs/comments
Medium: features/refactors
High: auth, payments, migrations, infrastructure, security.

### Task Graph Builder
Breaks work into dependency-aware atomic tasks.

### Tool Planner
Chooses required execution tools.

### Verification Planner
Creates compile, lint, test and acceptance strategy.

## Functional Requirements

FR-001 Intent classification
FR-002 Repository Memory query
FR-003 Impact estimation
FR-004 Task graph generation
FR-005 Risk scoring
FR-006 Tool planning
FR-007 Verification planning
FR-008 Immutable execution plans

## Non-Functional Requirements

- Deterministic
- Stateless
- Observable
- Horizontally scalable
- Explainable
- Model agnostic

## Acceptance Criteria

- Intent classified
- Repository Memory queried
- Impact analyzed
- Risk calculated
- Task graph generated
- Execution plan produced

## Next

RFC-003 Part 2:
Dependency scheduling, critical path analysis, approval gates, confidence scoring, state machines and sequence diagrams.
