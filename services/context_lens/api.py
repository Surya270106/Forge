"""Authenticated, bounded execution change evidence."""

import hashlib
from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.atlas import AtlasNodeModel, AtlasSnapshotModel
from packages.database.models.context_lens import ContextChangeSetModel
from packages.database.models.execution import ExecutionEventModel, ExecutionJobModel
from packages.database.models.patch import PatchModel
from packages.database.models.repository import RepositoryModel
from packages.database.models.verification import VerificationJobModel, VerificationResultModel
from packages.shared.errors import ConflictError
from packages.shared.identifiers import OrganizationId
from services.atlas.graph import is_test_path
from services.atlas.service import impact_from_db
from services.auth.dependencies import require_permission
from services.execution.flight_recorder import SAFE_STRING, SENSITIVE_VALUE
from services.patch.service import PatchService

from .service import approval_evidence, verification_summary

router = APIRouter(prefix="/api/v1/executions", tags=["context-lens"])


@router.get("/{execution_id}/context")
async def execution_context(
    execution_id: UUID, cursor: int = Query(0, ge=0),
    organization_id: OrganizationId = Depends(require_permission("exec:read")),
    session: AsyncSession = Depends(get_session),
):
    execution = (await session.execute(select(ExecutionJobModel).where(
        ExecutionJobModel.id == execution_id, ExecutionJobModel.organization_id == organization_id,
    ))).scalar_one_or_none()
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution unavailable")
    repository = (await session.execute(select(RepositoryModel.id).where(
        RepositoryModel.id == execution.repository_id, RepositoryModel.organization_id == organization_id,
    ))).scalar_one_or_none()
    if repository is None:
        raise HTTPException(status_code=404, detail="Execution unavailable")

    patch = (await session.execute(select(PatchModel).where(
        PatchModel.execution_job_id == execution_id, PatchModel.organization_id == organization_id,
        PatchModel.repository_id == execution.repository_id,
    ).order_by(PatchModel.created_at.desc()).limit(1))).scalar_one_or_none()
    change_set = None
    if patch:
        change_set = (await session.execute(select(ContextChangeSetModel).where(
            ContextChangeSetModel.patch_id == patch.id,
            ContextChangeSetModel.execution_job_id == execution_id,
            ContextChangeSetModel.repository_id == execution.repository_id,
            ContextChangeSetModel.organization_id == organization_id,
        ))).scalar_one_or_none()

    files = change_set.file_changes if change_set else []
    current_digest = None
    if patch:
        try:
            mutations = await PatchService(session, organization_id)._mutations(patch)
            current_digest = PatchService._review_digest(patch.base_commit_sha or "", mutations)
        except (ConflictError, ValueError):
            pass
    review = approval_evidence(patch, current_digest, change_set.review_digest if change_set else None) if patch else None

    atlas = {"base_snapshot_id": None, "post_snapshot_id": None, "identity": "base_commit_only",
             "direct_symbols": [], "impacted": [], "relevant_tests": [], "unresolved_files": [],
             "truncated": False}
    if change_set and change_set.base_snapshot_id:
        snapshot = (await session.execute(select(AtlasSnapshotModel).where(
            AtlasSnapshotModel.id == change_set.base_snapshot_id,
            AtlasSnapshotModel.organization_id == organization_id,
            AtlasSnapshotModel.repository_id == execution.repository_id,
            AtlasSnapshotModel.commit_sha == change_set.base_commit_sha,
            AtlasSnapshotModel.dirty.is_(False), AtlasSnapshotModel.status == "PUBLISHED",
        ))).scalar_one_or_none()
        if snapshot:
            atlas["base_snapshot_id"] = str(snapshot.id)
            paths = sorted({item["path"] for item in files})
            nodes = (await session.execute(select(AtlasNodeModel).where(
                AtlasNodeModel.snapshot_id == snapshot.id,
                AtlasNodeModel.organization_id == organization_id,
                AtlasNodeModel.path.in_(paths),
            ).order_by(AtlasNodeModel.stable_key).limit(501))).scalars().all()
            atlas["truncated"] = len(nodes) > 500 or len(paths) > 10
            by_path: dict[str, list] = {}
            file_keys = set()
            for node in nodes[:500]:
                if node.path is None:
                    continue
                by_path.setdefault(node.path, []).append(node)
                if node.kind in {"file", "test_file"}:
                    file_keys.add(node.stable_key)
            for item in files:
                candidates = by_path.get(item["path"], [])
                for node in candidates:
                    if node.kind not in {"function", "method", "class", "interface", "test_case"} or node.line_start is None or node.line_end is None:
                        continue
                    if any(node.line_start <= max(h["before_start"], 1) + max(h["before_count"], 1) - 1
                           and node.line_end >= max(h["before_start"], 1) for h in item["hunks"]):
                        atlas["direct_symbols"].append({"mutation_id": item["mutation_id"], "node_key": node.stable_key,
                                                        "kind": node.kind, "name": node.name, "path": node.path,
                                                        "line_start": node.line_start, "line_end": node.line_end,
                                                        "classification": "base_range_overlap"})
            atlas["unresolved_files"] = [path for path in paths if f"file:{path}" not in file_keys]
            impacted: dict[str, dict] = {}
            tests: dict[str, dict] = {}
            for path in paths[:10]:
                if f"file:{path}" not in file_keys:
                    continue
                result = await impact_from_db(session, organization_id, execution.repository_id, snapshot.id,
                                              f"file:{path}", max_depth=3, max_results=20)
                atlas["truncated"] = atlas["truncated"] or result.truncated
                for entry in result.items:
                    evidence = {"node_key": entry.key, "depth": entry.depth,
                                "classification": "inferred_test" if entry.key.startswith("file:") and is_test_path(entry.key[5:])
                                else "direct_dependency" if entry.depth == 1 else "indirect_impact",
                                "snapshot_id": str(snapshot.id), "via": [asdict(edge) for edge in entry.via]}
                    if evidence["classification"] == "inferred_test":
                        tests.setdefault(entry.key, evidence)
                    else:
                        impacted.setdefault(entry.key, evidence)
            atlas["impacted"] = list(impacted.values())[:100]
            atlas["relevant_tests"] = list(tests.values())[:100]
            atlas["truncated"] = atlas["truncated"] or len(impacted) > 100 or len(tests) > 100

    jobs = (await session.execute(select(VerificationJobModel).where(
        VerificationJobModel.organization_id == organization_id,
        VerificationJobModel.repository_id == execution.repository_id,
        VerificationJobModel.execution_job_id == execution_id,
    ).order_by(VerificationJobModel.created_at.desc()).limit(21))).scalars().all()
    job_ids = [job.id for job in jobs[:20]]
    results = (await session.execute(select(VerificationResultModel).where(
        VerificationResultModel.organization_id == organization_id,
        VerificationResultModel.execution_id == execution_id,
        VerificationResultModel.verification_job_id.in_(job_ids),
    ).order_by(VerificationResultModel.created_at).limit(101))).scalars().all() if job_ids else []
    result_rows = []
    for result in results[:100]:
        verifier = result.verifier
        if not SAFE_STRING.fullmatch(verifier) or SENSITIVE_VALUE.search(verifier):
            verifier = "sha256:" + hashlib.sha256(verifier.encode()).hexdigest()
        result_rows.append({"id": str(result.id), "job_id": str(result.verification_job_id),
                            "verifier": verifier, "status": result.status.value, "exit_code": result.exit_code,
                            "started_at": result.started_at, "finished_at": result.finished_at,
                            "duration_ms": result.duration_ms, "attempt": result.attempt})

    event_rows = (await session.execute(select(ExecutionEventModel).where(
        ExecutionEventModel.organization_id == organization_id,
        ExecutionEventModel.execution_job_id == execution_id,
        ExecutionEventModel.sequence > cursor,
    ).order_by(ExecutionEventModel.sequence).limit(51))).scalars().all()
    events = [{"id": str(event.id), "sequence": event.sequence, "type": event.event_type,
               "occurred_at": event.occurred_at} for event in event_rows[:50]]
    return {
        "execution": {"id": str(execution.id), "repository_id": str(execution.repository_id),
                      "status": execution.status.value, "base_commit_sha": execution.commit_sha_before},
        "change_set": ({"id": str(change_set.id), "patch_id": str(change_set.patch_id),
                        "review_digest": change_set.review_digest, "base_commit_sha": change_set.base_commit_sha,
                        "captured_at": change_set.created_at, "files": files,
                        "additions": sum(item["additions"] for item in files),
                        "deletions": sum(item["deletions"] for item in files)} if change_set else None),
        "atlas": atlas,
        "verification": {"jobs": [{"id": str(job.id), "status": job.status.value,
                                    "started_at": job.started_at, "finished_at": job.finished_at} for job in jobs[:20]],
                         "results": result_rows,
                         "summary": verification_summary(results[:100], len(atlas["relevant_tests"])),
                         "truncated": len(jobs) > 20 or len(results) > 100},
        "review": review,
        "timeline": {"events": events, "next_cursor": events[-1]["sequence"] if len(event_rows) > 50 else None},
    }
