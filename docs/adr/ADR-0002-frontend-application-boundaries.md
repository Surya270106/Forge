# ADR 0002: Frontend Application Boundaries

## Context
The repository previously contained two Next.js frontend applications:
- `apps/web`: An experimental legacy frontend used to prototype API calls using inline styles.
- `apps/frontend`: A heavily scaffolded canonical production frontend configured with Tailwind CSS, Zustand, React Query, and Radix UI.

Having two frontends caused ambiguity regarding the official production entrypoint, configuration drift, and duplicated build steps.

## Decision
We have decided to:
1. Establish `apps/frontend` as the **canonical production frontend**.
2. Decommission and remove `apps/web` entirely.
3. Consolidate all E2E testing, API clients, and UI component development into `apps/frontend`.

## Consequences
- A single source of truth for the Next.js frontend.
- Simplified CI/CD pipeline.
- Reduced dependency duplication across the monorepo.
- The `apps/web` experimental application is permanently retired.
