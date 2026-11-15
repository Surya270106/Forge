# Forge Context Lens

## Architecture and implementation plan

Forge's execution worker commits `MutationModel` rows only after an edit survives its lease fence. `PatchService` aggregates those mutations, validates their unified diffs and computes a SHA-256 review digest before human approval. Verification has job and command-result rows; Flight Recorder has append-only execution events. Publication has separate requested, running, succeeded, and failed states. Atlas publishes immutable repository graphs. Context Lens reads these records; it neither runs tests nor approves or publishes a patch.

1. Capture bounded, content-free file and hunk metadata with the patch digest in one immutable, tenant-scoped change-set row when a patch is prepared. Link the base Atlas snapshot only when its clean commit equals the patch base. A missing post-change snapshot remains missing.
2. Expose an authenticated execution-scoped read API that combines that snapshot with current patch, verification, and publication facts. Recompute the review digest before claiming an approval is current. Keep inferred Atlas impact and potentially relevant tests separate from executed verification commands.
3. Add a task-workspace panel that loads the API and shows provenance, changed regions, impact, verification, approval, and publication with distinct uncertainty states.
4. Test diff mapping, digest drift, tenant RLS, API ownership, Atlas association, and command-result semantics. Run migrations, backend and frontend checks, and Docker builds in disposable local infrastructure.

## Evidence boundaries

The durable change-set row is a snapshot of patch preparation, not a copy of source or full diff. It stores mutation and task-node IDs, safe repository-relative paths, change type, hunk ranges, and line counts. It cannot prove which exact agent reasoning step authored a line; a mutation's task-node ID is the strongest available operation link. `command` nodes are not attributed to files because the worker rejects unreviewable command changes. File and symbol mapping is based on a matching clean **base** Atlas snapshot, and is labelled as base-state evidence. An Atlas test association means potentially relevant, not selected or executed. Verification results are command-level records, not per-test-case results or coverage. A branch move cannot alter the captured base commit or digest.

The API has fixed limits for changed files, impact paths, verification records, and timeline pages. It returns references and safe metadata, not diff bodies, test stdout/stderr, source contents, credentials, or host paths. Context Lens never authorizes execution, file access, patch approval, or GitHub publication. The existing Safety Gate, patch digest check, and publisher remain enforcement points.

## Persistence and API

Migration `e1b4c8d29070` adds `context_change_sets` after Atlas head `d6a1f8b2c340`. The table has a unique patch foreign key, execution/repository/organization ownership references, an optional same-tenant base-snapshot foreign key, a digest, a schema version, and bounded JSON hunk metadata. PostgreSQL forces tenant RLS and rejects updates/deletes with the existing append-only trigger function. Patch preparation inserts this row and `patch.created` Flight Recorder evidence in the same transaction. Duplicate patch-generation calls return the original patch; they do not append a second change set. Patches prepared before this migration have no captured change set and are shown as legacy evidence unavailable.

`GET /api/v1/executions/{execution_id}/context?cursor=0` requires `exec:read`, a valid session and workspace, and a matching execution, repository, patch, change set, and Atlas snapshot. It returns `execution`, `change_set`, `atlas`, `verification`, `review`, and `timeline` objects. A change set includes IDs, base commit, digest, changed paths, operation IDs, hunk line ranges, and line counts. `atlas.base_snapshot_id` is non-null only when a clean, published snapshot of that exact base commit existed at patch preparation; `post_snapshot_id` is null until a trustworthy post-change identity is available. Direct symbols are base-range overlaps. Impact entries include depth, relationship path, confidence, resolution and evidence location. Relevant tests are inferred graph associations. `verification.results` contains command-level status, exit code and timing from actual result rows. It intentionally omits stdout/stderr and does not assert per-test execution or coverage. `review.current` compares the captured digest with current mutation records; `review.publication` uses the publisher's persisted terminal state, not a queued request.

Example shape (identifiers shortened here):

```json
{
  "execution": {"id": "...", "status": "COMPLETED", "base_commit_sha": "..."},
  "change_set": {"id": "...", "review_digest": "...", "files": [{"path": "src/a.py", "type": "modified", "hunks": [{"before_start": 4, "before_count": 1, "after_start": 4, "after_count": 2}]}]},
  "atlas": {"base_snapshot_id": "...", "post_snapshot_id": null, "direct_symbols": [], "impacted": [], "relevant_tests": [], "truncated": false},
  "verification": {"results": [], "summary": {"selected_tests": null, "executed_commands": 0, "coverage_claimed": false}, "truncated": false},
  "review": {"approved": false, "current": true, "publication": "not_requested"},
  "timeline": {"events": [], "next_cursor": null}
}
```

The task workspace's Context Lens tab loads this API. It labels structure as inferred, command results as actual, and pending publication separately from completed publication. It supports refresh, loading and authorization errors, and event-page navigation. Its text is rendered by React rather than injected as HTML.

## Limits and interpretation

Patch preparation already limits mutations to 50 and full review diffs to 1 MiB. Context Lens stores only metadata for those mutations. They are sequential patch operations; an earlier hunk may be superseded by a later hunk in the same file. They are not a proven final net diff or line-level model attribution. Existing patch review remains the source for the exact reviewable sequence. Binary payloads and renames are rejected by the current patch review format, so Context Lens does not invent those change types. File change types come from persisted mutation types; an empty-file hunk alone does not prove creation or deletion. A matching base Atlas snapshot can map old lines to symbols; newly added files or lines without a base symbol remain unresolved. No full repository scan is triggered by this endpoint.

The read path processes at most 50 edit records, 500 matching Atlas nodes, 10 changed file impact traversals (20 results each, depth three), 20 verification jobs, 100 command results, and 50 timeline events per page. `truncated` flags indicate incomplete evidence. Verification summaries count only returned command records when truncated. A relevant test cannot be called selected, executed or passed without a corresponding test-level record, which Forge's current verifier does not persist. Publication history remains in Flight Recorder; the current patch row reports the latest request/result. A later digest mismatch invalidates current approval but does not erase a previously recorded successful publication.

One local ASGI/PostgreSQL fixture read on 2026-11-13 took 146.6 ms and returned 3,222 bytes. This is a single small-fixture measurement, not a load or hosted latency guarantee.

## Deployment and validation

Apply Alembic head before starting updated API or worker images. The API and patch service need the existing PostgreSQL and organization context; Context Lens adds no queue, Redis command, model-provider call, or execution capability. Existing Vercel/Render hosting remains subject to the separate Docker-capable worker requirement. Local tests use disposable PostgreSQL, and no hosted evidence claim follows from them. Browser interaction, hosted OAuth, GitHub publication, and a real repository execution-to-Context-Lens journey require separate end-to-end validation.
