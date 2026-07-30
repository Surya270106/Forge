# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Forge AI is for software engineers and platform teams evaluating or operating an agentic CI/CD system against source repositories.

## Product Purpose

Forge AI turns a natural-language engineering intent into a planned, executed, verified repository change and prepares the resulting patch for review.

## Positioning

Forge is built as a distributed execution system rather than a single chat interface. Repository context, DAG planning, execution, verification, repair, audit, and patch submission are separate services joined by durable events.

## Operating Context

The system works with Git repositories, a Next.js frontend, FastAPI services, PostgreSQL, Redis Streams, and isolated execution environments. Repository-specific checks can be declared in `forge.yaml`.

## Capabilities and Constraints

- Repository import, context assembly, DAG planning, execution, verification, patch generation, and audit models exist in the source.
- Docker-isolated execution is designed to disable network access, drop capabilities, and prevent privilege escalation.
- The repository currently identifies itself as internal alpha.
- Production readiness, external beta, and untrusted repository execution are not accepted in the current implementation status.
- Pricing is not published.

## Brand Commitments

- The product name is Forge AI and the visible wordmark is `FORGE.AI`.
- The approved first viewport and its interactive blue WebGL blob must remain unchanged.
- The site remains dark, technical, and precise.
- New typography should follow the PRism reference: Geist Sans for interface copy and DM Serif Display for selected editorial headlines.

## Evidence on Hand

- Product source and README: `https://github.com/Surya270106/Forge`
- Local source review confirms services for context, planning, execution, verification, patching, repository import, audit, and event handling.
- The repository contains internal alpha acceptance and implementation status reports.
- No customer logos, testimonials, production benchmarks, or public pricing evidence are available and must not be fabricated.

## Product Principles

- Show the mechanism instead of making vague AI claims.
- Keep execution reviewable and verification explicit.
- Treat isolation and tenant boundaries as product architecture.
- State alpha-stage limitations honestly.
- Preserve the approved interactive hero as the product's signature.

## Accessibility & Inclusion

Maintain semantic HTML, visible keyboard focus, reduced-motion behavior, readable contrast, and explicit mobile layout fallbacks.
