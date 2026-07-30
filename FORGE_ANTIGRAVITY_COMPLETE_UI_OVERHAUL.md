# Forge AI — Complete Antigravity UI Overhaul

Use this file as the master implementation prompt inside the existing Forge
repository:

`https://github.com/Surya270106/Forge`

The `reference-ui/` directory supplied beside this file contains the exact
approved website implementation. Treat those files as source material, not as
loose inspiration.

---

## Your role

Act as the lead product engineer, frontend architect, interaction designer,
accessibility engineer, and QA owner for Forge AI.

Your task is to perform a complete UI and UX overhaul of the existing Forge
application while preserving its working backend, API contracts, database
models, authentication, execution behavior, and engineering architecture.

This is not a static mockup, a marketing-only redesign, or a collection of
unconnected pages. Deliver a complete, responsive, production-quality product
interface connected to the real Forge functionality.

Do not stop after creating the shell or dashboard. Finish every existing
user-facing route, state, workflow, button, form, modal, table, empty state,
loading state, error state, and responsive layout.

---

## Required design skills

Before editing UI code, read and apply the design and interaction guidance from:

1. `https://github.com/leonxlnx/taste-skill`
2. `https://github.com/emilkowalski/skills`
3. `https://github.com/pbakaus/impeccable`

If the skills are already installed, invoke them directly. If they are not
available in the environment, use the design rules in this document as the
binding fallback. Do not stop the implementation merely because a skill cannot
be installed.

Use those skills to improve hierarchy, typography, motion, spacing,
interaction feedback, focus management, responsive behavior, and final visual
QA. They must not override the non-negotiable Forge design constraints below.

---

## Product truth

Forge AI is an autonomous software engineering platform. It is not a generic
chatbot and not an autocomplete interface.

Its core workflow is:

`User Request → Intent Analysis → Repository Cognition → Impact Analysis →
Planning → Approval → Execution → Sandbox → Verification → Repair Loop →
Evaluation → Git/Patch → Pull Request`

Forge should make that mechanism inspectable. The UI must show what the system
understands, what it plans, what it changes, which checks passed or failed, and
why a run advanced or stopped.

The interface should feel like a calm, premium engineering workspace:

- information-rich without feeling crowded;
- precise without looking like a dated admin dashboard;
- highly visual without inventing meaningless charts;
- confident without fabricating production claims;
- animated where motion explains state;
- safe around approvals, execution, cancellation, and destructive actions.

---

## Phase 0 — Protect the current application

Before making changes:

1. Inspect the entire repository and identify the frontend application,
   routing, shared components, API clients, authentication, state management,
   tests, and build commands.
2. Record all existing routes and every interactive control.
3. Record the real backend endpoints used by each screen.
4. Run the current lint, type-check, tests, and production build. Save the
   results as the baseline.
5. Create a recoverable Git backup commit and a clearly named backup branch or
   tag before the overhaul.
6. Do not delete working features to make the redesign easier.
7. Do not rewrite backend services or database behavior unless a frontend
   integration bug requires a small, proven fix.
8. Never use destructive Git commands and never overwrite unrelated user work.

Produce `docs/UI_OVERHAUL_BASELINE.md` containing the route inventory,
component inventory, API mapping, existing test status, and backup reference.

---

## Absolute visual non-negotiable: preserve the exact blob

The blue WebGL blob is the signature of Forge. It has already been approved and
must remain exact.

Use `reference-ui/app/blob-scene.tsx` as the canonical implementation.

Do not redesign, regenerate, simplify, recolor, replace, reinterpret, or
approximate it. Preserve:

- the `IcosahedronGeometry(1.22, 30)` geometry;
- the simplex-noise displacement shader;
- the solid blue surface shader;
- the additive blue wireframe shader;
- the exact time progression and breathing motion;
- the exact pointer-following rotation;
- the exact rich navy/electric-blue color values;
- the transparent WebGL background;
- the 2D canvas fallback;
- the fixed centered viewport position;
- the reduced-motion behavior;
- the transparent render overscan that prevents clipping;
- the current desktop and mobile size;
- the current camera framing at `z = 5.15`.

The blob must never expose a rectangular canvas boundary. Deformed vertices,
wireframe lines, glow, or antialiasing must not be clipped by the render field.
Do not add `overflow: hidden` to the blob stage.

Canonical stage CSS:

```css
.blob-stage {
  position: fixed;
  z-index: 0;
  top: 73px;
  left: 50%;
  width: min(760px, 48vw);
  height: 720px;
  opacity: var(--blob-page-opacity);
  transform: translateX(-50%);
  filter: saturate(1.12) contrast(1.08);
  pointer-events: none;
  transition: opacity 180ms linear;
  will-change: transform, opacity;
}

.blob-stage canvas {
  position: relative;
  z-index: 1;
  display: block;
  width: 100%;
  height: 100%;
  mix-blend-mode: multiply;
}

.blob-glow {
  position: absolute;
  inset: 18% 20%;
  border-radius: 50%;
  background: radial-gradient(circle, rgb(0 84 214 / 25%), transparent 68%);
  filter: blur(55px);
}

@media (max-width: 760px) {
  .blob-stage {
    top: 78px;
    width: 540px;
    height: 580px;
  }
}

@media (max-width: 430px) {
  .blob-stage {
    top: 81px;
    width: 480px;
    height: 560px;
  }
}
```

The blob stays in the same viewport position while the page scrolls. Scrolling
must not translate, resize, parallax, or push it into a new section. Only its
opacity changes after the hero:

- hero: opacity `1`;
- application and story content: approximately `0.12–0.22`;
- dialogs or dense code/log surfaces may reduce it to `0.06–0.10`;
- never remove it completely from ordinary product routes.

Pointer movement should remain subtle. The blob responds to the cursor without
chasing it across the page.

---

## Design system

### North star

**Rich Air / Living Core**

Rich off-white creates air and trust. Saturated blue carries the product
signal. Deep navy provides legible technical structure. The fixed blue blob is
the living intelligence behind the interface.

### Color tokens

Use semantic tokens. Do not scatter raw hex values through components.

```css
:root {
  --forge-white: #f3f6fa;
  --forge-paper: #edf2f7;
  --forge-paper-blue: #e7eef7;
  --forge-ink: #061a36;
  --forge-muted: #58708f;
  --forge-line: #cbdcf2;
  --forge-blue: #075bea;
  --forge-blue-bright: #2f7dff;
  --forge-blue-deep: #063fae;
  --forge-navy: #041d49;
  --forge-success: #087a55;
  --forge-warning: #a05a00;
  --forge-danger: #b4233c;
  --forge-focus: #58a0ff;
  --forge-ease: cubic-bezier(0.22, 1, 0.36, 1);
}
```

The default page background is `#f3f6fa`, not pure white. Use a faint technical
grid:

```css
background:
  linear-gradient(90deg, rgb(7 91 234 / 0.035) 1px, transparent 1px),
  linear-gradient(rgb(7 91 234 / 0.025) 1px, transparent 1px),
  var(--forge-white);
background-size: 88px 88px;
```

Blue is the only strong decorative accent. Red, amber, and green exist only for
real semantic status.

### Typography

- Interface and display: Geist Sans.
- Technical evidence: Geist Mono.
- Use no more than these two type families.
- Do not use a generic Inter-style dashboard appearance.
- Headings use medium weight, tight tracking, and compact line-height.
- Body text stays readable at 15–18px.
- Mono text is reserved for IDs, stages, timestamps, commands, file paths,
  diagnostics, event names, and technology evidence.
- Never set whole paragraphs in monospace.

### Shape

- Use generous whitespace and thin structural dividers.
- Avoid a screen made from many identical rounded cards.
- Reserve rounded containers for the floating shell, actions, filters, command
  surfaces, dialogs, and selected interactive modules.
- Tables, timelines, audit records, file changes, and verification results
  should use strong rows, columns, and dividers.
- Standard control radius: 10–12px.
- Major floating shell radius: 16–20px.
- Avoid excessive pills.

### Depth

- Use soft blue-gray borders and restrained shadows.
- Glass is permitted only for the floating navigation, overlays, and controls
  that sit directly above the blob.
- Do not blur every panel.
- Do not use black backgrounds for the main application.

### Motion

- Default transition duration: 160–240ms.
- Default easing: `cubic-bezier(0.22, 1, 0.36, 1)`.
- Use motion to explain route changes, expanded detail, stage progress, DAG
  updates, approval state, verification completion, and drawers.
- Do not animate every element on every render.
- Avoid bouncing, spinning, floating cards, or ornamental motion.
- Respect `prefers-reduced-motion`.

---

## Application shell

Create a clean, reusable application shell based on the reference website.

### Desktop

- A floating off-white header with the Forge mark, workspace/repository
  context, global search or command trigger when a real action exists, and the
  authenticated user menu.
- A calm left navigation rail for primary product destinations.
- Main content uses a wide editorial grid with generous spacing.
- The fixed blob remains centered behind the content at reduced opacity.
- Content panes use translucent off-white only when necessary for legibility.
- Keep important actions visible without turning the header into a toolbar.

### Tablet and mobile

- Collapse the left rail into an accessible menu or bottom navigation chosen
  from the repository’s existing structure.
- Never create horizontal page scrolling.
- Tables become compact rows or stacked records without losing essential
  status, ownership, and actions.
- Drawers become full-screen sheets.
- DAGs and diffs may scroll inside their own bounded region.
- Preserve the blob’s fixed center and overscan.

### Primary navigation

Use the product’s actual route structure. The baseline information
architecture is:

1. Home
2. Repositories
3. Plans
4. Runs
5. Verification
6. Analytics
7. Settings

If the repository already has additional real routes, keep and restyle them.
Do not add empty navigation destinations.

Show the active route clearly with blue signal, weight, and position—not only a
subtle color difference.

---

## Required product screens

Inspect the code before implementation and adapt these requirements to the real
routes and API contracts. Do not fabricate data or endpoints.

### 1. Home

Purpose: give the operator the shortest path back into useful work.

Include:

- a strong welcome/operating headline;
- a primary “Import repository” or “New request” action, whichever is valid for
  the current account state;
- recent repositories;
- plans needing approval;
- active or recently completed runs;
- verification failures that need attention;
- a concise activity/event stream;
- honest empty states for a new user.

Do not fill the page with vanity statistics. Every number must come from real
data and link to a meaningful filtered view.

### 2. Repositories

Repository list:

- search;
- filter by provider, state, language, or ownership only when data exists;
- import/connect action;
- state, last indexed time, default branch, and relevant activity;
- loading, empty, partial-failure, and permission states.

Repository import must visibly follow the real lifecycle:

`PENDING → AUTHENTICATING → CLONING → SCANNING → DETECTING →
BUILDING_MANIFEST → PERSISTING → READY`

Do not simulate progress. Reflect server state and handle retryable and terminal
errors.

Repository workspace baseline tabs:

1. Overview
2. Architecture
3. Symbols
4. Dependencies
5. Plans
6. Runs
7. Verification
8. Context
9. Settings

Required behaviors:

- preserve deep links and browser history;
- show repository identity and current branch consistently;
- support keyboard navigation;
- keep destructive repository actions inside a confirmed danger area;
- never hide an import/indexing error behind a generic toast.

### 3. Plans

Plans list:

- repository, title/request, risk, status, owner, updated time;
- meaningful filters;
- clear “New plan” action;
- no fake AI scores.

Plan creation:

- accept natural-language engineering intent;
- select the real repository/workspace;
- show context or scope options only when supported;
- display validation and API errors inline;
- make submission state unmistakable.

Plan detail:

- intent summary;
- impact analysis;
- affected files/symbols/dependencies;
- ordered task DAG;
- tool and command requirements;
- verification strategy;
- risk and approval state;
- event/provenance timeline.

Actions, when supported by the backend:

- Approve;
- Reject with reason;
- Edit or regenerate;
- Execute;
- Cancel;
- Copy/share plan link.

Approval and execution are consequential. They require unambiguous labels,
pending states, disabled duplicate submissions, success confirmation, and
recoverable errors.

### 4. Runs

Runs list:

- current state;
- repository;
- linked plan;
- initiator;
- start time and duration;
- latest stage;
- verification result;
- filter and search.

Run workspace baseline tabs:

1. Summary
2. Plan
3. Execution
4. Changes
5. Verification
6. Context
7. Events
8. Audit

Summary should show the current stage and next required decision.

Execution should show:

- DAG node status;
- command/tool ownership;
- start/end/duration;
- bounded live logs if supported;
- timeouts and sandbox errors;
- mutations produced by each step.

Changes should show:

- files added, modified, deleted, or renamed;
- diff viewer;
- summary by task;
- patch metadata;
- branch/commit/PR state when available.

Run controls, only when real APIs exist:

- pause;
- resume;
- cancel/stop;
- retry failed node or run;
- rerun verification;
- prepare/download patch;
- open pull request.

Do not display a working-looking button with no behavior. Hide unsupported
actions or mark them clearly as unavailable with a truthful reason.

### 5. Verification

Create an inspectable verification experience:

- overall result;
- format, lint, type-check, tests, build, and security check groups;
- pass/fail/skipped/running states;
- duration;
- diagnostic output;
- source file and line references;
- repair attempts;
- retry or repair action when supported.

Use green only for verified success. A run that did not execute a check is
“Skipped” or “Not configured,” never “Passed.”

### 6. Analytics

Only show metrics the repository genuinely supports.

Good candidates when real data exists:

- run completion over time;
- verification pass/fail distribution;
- average time by lifecycle stage;
- repair-loop frequency;
- repository activity;
- common failure categories.

Every chart requires:

- accessible label;
- visible unit and time range;
- loading, empty, and error state;
- table or textual alternative;
- no invented benchmarks.

If meaningful analytics are not implemented, provide an honest empty state and
do not manufacture a dashboard.

### 7. Settings

Map settings to the implemented product:

- profile/account;
- Git provider connection;
- organization/workspace/project context;
- repository defaults;
- execution and sandbox policy;
- verification configuration;
- notifications;
- appearance/accessibility;
- API or integration credentials only if they already exist.

Separate ordinary settings from destructive actions. Never reveal secrets after
creation. Use masked values, explicit permission descriptions, and safe
re-authentication patterns.

---

## Reusable components

Create a coherent component system rather than styling each screen separately.
At minimum, derive reusable components for:

- `AppShell`
- `FloatingHeader`
- `PrimaryNavigation`
- `RepositoryContext`
- `BlobScene` copied from the reference implementation
- `PageHeader`
- `SectionLabel`
- `PrimaryButton`, `SecondaryButton`, `QuietButton`, `DangerButton`
- `StatusBadge` with semantic state mapping
- `DataTable` or structured record list
- `FilterBar`
- `SearchField`
- `EmptyState`
- `ErrorState`
- `LoadingSkeleton`
- `ConfirmDialog`
- `Drawer` or `DetailPanel`
- `LifecycleRail`
- `PlanDag`
- `RunTimeline`
- `LogViewer`
- `DiffViewer`
- `VerificationResult`
- `EventTimeline`
- `Toast` for supplemental feedback only

Use one shared status vocabulary across the application. Do not allow each
screen to invent different colors or labels for the same state.

---

## Functional requirements

1. Every existing button must perform its intended action.
2. Every navigation item must reach a real route.
3. Every form must validate, submit, disable duplicate requests, and report
   server errors.
4. Every list must support loading, empty, error, and success states.
5. Every optimistic update must reconcile with the server.
6. Every destructive action must show the exact affected object and require
   deliberate confirmation.
7. Every long operation must show real progress or a truthful indeterminate
   state.
8. Every run/plan/repository ID must remain deep-linkable.
9. Browser back/forward navigation must work.
10. Refreshing a detail page must restore the correct server-backed state.
11. Authentication and authorization errors must lead to the correct recovery
    action.
12. Do not use static placeholder arrays in production routes.
13. Do not replace errors with silent console logs.
14. Do not add dead buttons, fake exports, fake search, or fake filters.

---

## Engineering constraints

Preserve the Forge engineering constitution:

- Route → Service → Repository layering.
- No Route → Database access.
- No UI → Database access.
- No circular imports.
- No regex-based code understanding where AST, Tree-sitter, symbols, or
  dependency graphs are required.
- Never execute without a plan.
- AI must not edit blindly.
- Every request must preserve intent, risk, impact, task graph, tools, and
  verification strategy.
- Repository Memory remains the source of truth for code understanding.
- Control plane and execution plane remain separate.
- Tenant context must remain immutable and auditable.
- Worker and sandbox isolation must not be weakened for frontend convenience.

Prefer the frontend stack already present in the repository. Do not replace the
framework or introduce a competing styling/state system without strong
technical necessity.

Use strict TypeScript. Avoid `any`, hidden type errors, duplicated domain
models, and frontend-only status strings that disagree with the API.

---

## Accessibility

- Semantic landmarks and heading order.
- Full keyboard navigation.
- Visible focus using the approved blue focus token.
- Correct tab, dialog, menu, combobox, and live-region semantics.
- Focus trap and focus return for dialogs and drawers.
- Minimum readable contrast on translucent surfaces.
- Text alternatives for charts and diagrams.
- Do not communicate status through color alone.
- Respect zoom, font scaling, and reduced motion.
- Touch targets should be at least 40–44px.

---

## Responsive quality bar

Verify at least:

- 1440 × 900 desktop;
- 1280 × 800 laptop;
- 1024 × 768 tablet landscape;
- 768 × 1024 tablet portrait;
- 430 × 932 mobile;
- 390 × 844 mobile;
- 320px minimum width.

At every size:

- no page-level horizontal overflow;
- no clipped blob or visible WebGL canvas box;
- no headings outside their container;
- no overlapping fixed navigation;
- no unreachable actions;
- no unreadable tables;
- no accidental tiny text;
- no layout shift after fonts or data load.

---

## Exact blob QA

The overhaul is not accepted unless all of these pass:

- Blob visual matches `reference-ui/app/blob-scene.tsx`.
- Blob stays horizontally centered.
- Blob stays in the same vertical viewport position while scrolling.
- Cursor movement changes surface orientation subtly.
- Cursor leaving the viewport eases the blob back to neutral.
- Scroll only reduces opacity; it does not move or resize the blob.
- Blob remains faintly visible on every normal application route.
- No canvas rectangle becomes visible.
- No deformed pixels or wireframe lines are clipped.
- The fallback canvas is visually consistent.
- Reduced motion produces a stable, intentional frame.
- Blob never blocks clicks or pointer interaction.

---

## Testing and verification

Do not report completion until:

1. Install and build from a clean dependency state.
2. Lint passes.
3. Type-check passes.
4. Unit tests pass.
5. Integration tests pass.
6. Existing backend tests still pass.
7. Production build passes.
8. Critical routes render without console errors.
9. Authentication flow is verified.
10. Repository import is verified.
11. Plan creation and approval are verified.
12. Run detail and execution state are verified.
13. Verification results and repair states are verified.
14. All buttons and links are exercised.
15. Empty, loading, error, permission, and success states are exercised.
16. Keyboard navigation is verified.
17. Responsive screenshots are reviewed at the required breakpoints.
18. The exact blob QA checklist passes.
19. No placeholder text, fake data, or dead controls remain.
20. Git diff is reviewed for accidental backend or infrastructure changes.

If Docker or another external dependency is unavailable, do not pretend that
its test passed. Complete everything possible, record the exact blocker, and
keep the UI honest about unavailable execution capabilities.

---

## Required final deliverables

Create:

1. the complete implemented UI overhaul;
2. `docs/UI_OVERHAUL_BASELINE.md`;
3. `docs/UI_DESIGN_SYSTEM.md`;
4. `docs/UI_ROUTE_AND_ACTION_MATRIX.md`;
5. `docs/UI_OVERHAUL_VERIFICATION.md`;
6. a concise final report with:
   - changed routes;
   - reusable components created;
   - API integrations preserved or repaired;
   - tests run and results;
   - known blockers;
   - screenshots or preview instructions;
   - the backup branch/tag or commit.

The route/action matrix must list every screen and control with:

| Route | Screen | Control | User action | API/service | Loading | Success | Error | Permission |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

No row may say “TODO”.

---

## Definition of done

Forge should feel like one coherent premium product built from the approved
white-and-rich-blue website—not a marketing page attached to an unrelated
dashboard.

The result is done only when:

- the original blob is preserved exactly;
- the blob remains the subtle living background across the whole product;
- all real Forge routes use the same design system;
- the complete repository, planning, execution, verification, and patch
  experience works;
- every existing function remains connected;
- unsupported capabilities are represented honestly;
- no fake data or decorative claims are introduced;
- the application is responsive and accessible;
- lint, types, tests, and production build are green;
- the pre-overhaul state is recoverable;
- the application is ready for a human to use end to end.

Begin by auditing the repository and producing the baseline. Then implement the
overhaul fully. Do not ask broad design questions whose answers are already in
this specification. Use the existing source as truth when routes or endpoint
names differ from the baseline information architecture.

