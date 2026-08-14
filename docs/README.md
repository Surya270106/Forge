# Forge documentation

This directory separates current engineering references from historical implementation
records. Component-level guides live beside the code they describe.

## Architecture and operations

- [Project overview](../README.md) — architecture, setup, operations, and validation.
- [Application entry points](../apps/README.md) — API, worker, and frontend responsibilities.
- [Container definitions](../docker/README.md) — images, Compose, and the Docker socket boundary.
- [Shared packages](../packages/README.md) — reusable infrastructure and dependency direction.
- [Domain services](../services/README.md) — capability ownership and service boundaries.
- [Operational scripts](../scripts/README.md) — local helpers and destructive-operation guards.
- [Verification suites](../tests/README.md) — test groups, prerequisites, and known skipped coverage.

## Product interface

- [UI design system](ui/design-system.md) — visual tokens, typography, layout, and component guidance.
- [UI route and action matrix](ui/route-action-matrix.md) — route-level behavior and API integration notes.

## Project policy

- [Contributor guide](../CONTRIBUTING.md) — contributor workflow and quality checks.
- [Security policy](../SECURITY.md) — trust boundaries and vulnerability reporting.
- [Changelog](../CHANGELOG.md) — release history and unreleased maintenance work.

## Historical records

The files under [`archive/ui-overhaul/`](archive/ui-overhaul/) capture the baseline,
delivery report, and verification notes for the completed UI-overhaul effort. They are
retained for project history and should not be treated as current requirements.
