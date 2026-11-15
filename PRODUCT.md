# Forge product context

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Individual developers working on GitHub repositories. They need to understand and approve each step of an agent-assisted code change.

## Product Purpose

Forge turns a task request into a repository-aware plan, runs an approved plan in an isolated Docker workspace, verifies the result, and lets the developer review the exact patch before requesting GitHub publication.

## Operating Context

The developer connects GitHub, selects a workspace, imports and indexes a repository, configures a model provider, creates a task, approves a plan, inspects execution and verification evidence, and explicitly approves and publishes a patch. The frontend is Next.js; the API is FastAPI; a separate Docker-capable worker is required for repository operations and execution.

## Capabilities and Constraints

- Workspaces scope repositories, plans, credentials, jobs, and audit records.
- Import, indexing, execution, verification, repair, and publication are asynchronous. An accepted request is not a completed job.
- Plan approval, patch review digest approval, and publication are separate decisions.
- The UI must reflect persisted backend state and must never invent worker availability, verification success, or a pull request URL.
- Credentials are handled by the API and must never be displayed in full or retained in browser storage.

## Brand Commitments

Keep the Forge name, logo, navy and cobalt palette, editorial typography, animated blue motif, and focused engineering-tool character. Improve the signed-in experience without replacing that identity with a generic dashboard.

## Evidence on Hand

The repository contains real API contracts, application screens, execution events, verification diagnostics, patch review data, and GitHub publication status. No sample production tasks, usage statistics, or customer claims were supplied; do not fabricate them.

## Product Principles

1. Make the next authorized action obvious.
2. Keep the complete lifecycle and its evidence inspectable.
3. Preserve precise boundaries between proposed, queued, running, verified, approved, and published states.
4. Keep long logs and diffs readable on small screens and lower-powered devices.

## Accessibility & Inclusion

Support keyboard navigation, visible focus, readable contrast, responsive layouts, and reduced motion.
