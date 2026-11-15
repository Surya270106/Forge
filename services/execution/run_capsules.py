"""Capture bounded, immutable facts at execution and verification state transitions."""

import hashlib
import json
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.context_lens import ContextChangeSetModel
from packages.database.models.execution import ExecutionEventModel, ExecutionJobModel
from packages.database.models.patch import PatchModel
from packages.database.models.run_capsule import RunCapsuleArtifactModel, RunCapsuleModel
from packages.database.models.verification import VerificationJobModel, VerificationResultModel
from packages.database.models.verification_intelligence import VerificationPlanModel
from packages.shared.config import get_settings
from packages.shared.identifiers import generate_id
from services.verification.intelligence import verifier_ref

CAPTURE_EVENTS = {
    "execution.started", "worker.lease_expired", "execution.completed", "execution.failed",
    "execution.cancelled", "execution.cancellation_failed", "verification.completed",
    "verification.cancelled", "verification.cancellation_failed",
}
FINAL_EVENTS = CAPTURE_EVENTS - {"execution.started", "worker.lease_expired", "execution.completed"}
MAX_ARTIFACT_BYTES = 16_384


def canonical_bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def content_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def verified_artifact(artifact: RunCapsuleArtifactModel) -> bytes:
    content = artifact.content.encode("utf-8")
    if len(content) != artifact.size_bytes or content_sha256(content) != artifact.sha256:
        raise ValueError("Capsule artifact integrity check failed")
    return content


async def capture_event_capsule(session: AsyncSession, event: ExecutionEventModel, job: ExecutionJobModel) -> None:
    if event.event_type not in CAPTURE_EVENTS:
        return
    prior = await session.scalar(select(RunCapsuleModel.id).where(RunCapsuleModel.event_id == event.id))
    if prior:
        return

    scope = (event.organization_id, event.execution_job_id, job.repository_id)
    change = (await session.execute(select(ContextChangeSetModel).where(
        ContextChangeSetModel.organization_id == scope[0],
        ContextChangeSetModel.execution_job_id == scope[1],
        ContextChangeSetModel.repository_id == scope[2],
    ).order_by(ContextChangeSetModel.created_at.desc()).limit(1))).scalar_one_or_none()
    patch = (await session.execute(select(PatchModel).where(
        PatchModel.organization_id == scope[0], PatchModel.execution_job_id == scope[1],
        PatchModel.repository_id == scope[2],
    ).order_by(PatchModel.created_at.desc()).limit(1))).scalar_one_or_none()
    if change and (not patch or change.patch_id != patch.id or change.review_digest != patch.review_digest):
        change = None
    verification_id = event.data.get("verification_id") if event.event_type.startswith("verification.") else None
    verification = (await session.execute(select(VerificationJobModel).where(
        VerificationJobModel.id == UUID(verification_id),
        VerificationJobModel.organization_id == scope[0],
        VerificationJobModel.repository_id == scope[2],
        VerificationJobModel.execution_job_id == scope[1],
    ))).scalar_one_or_none() if verification_id else None
    if verification is None and event.event_type.startswith("verification."):
        verification = (await session.execute(select(VerificationJobModel).where(
            VerificationJobModel.organization_id == scope[0], VerificationJobModel.repository_id == scope[2],
            VerificationJobModel.execution_job_id == scope[1],
        ).order_by(VerificationJobModel.created_at.desc()).limit(1))).scalar_one_or_none()
    selection = (await session.execute(select(VerificationPlanModel).where(
        VerificationPlanModel.organization_id == scope[0], VerificationPlanModel.repository_id == scope[2],
        VerificationPlanModel.execution_job_id == scope[1],
        VerificationPlanModel.verification_job_id == verification.id,
    ))).scalar_one_or_none() if verification else None
    results = (await session.execute(select(VerificationResultModel).where(
        VerificationResultModel.organization_id == scope[0],
        VerificationResultModel.execution_id == scope[1],
        VerificationResultModel.verification_job_id == verification.id,
    ).order_by(VerificationResultModel.created_at, VerificationResultModel.id).limit(41))).scalars().all() if verification else []
    events = (await session.execute(select(ExecutionEventModel).where(
        ExecutionEventModel.organization_id == scope[0],
        ExecutionEventModel.execution_job_id == scope[1],
        ExecutionEventModel.sequence <= event.sequence,
    ).order_by(ExecutionEventModel.sequence.desc()).limit(101))).scalars().all()
    model_event = next((row for row in events if row.event_type == "model.completed"), None)
    sandbox_event = next((row for row in events if row.event_type == "sandbox.created" and row.attempt == event.attempt), None)
    missing = []
    if not change:
        missing.append("change_set")
    if not patch:
        missing.append("patch_digest")
    if not selection:
        missing.append("verification_selection")
    if selection and (not change or selection.change_set_id != change.id
                      or selection.patch_digest != change.review_digest):
        missing.append("selection_digest_mismatch")
    if not sandbox_event:
        missing.append("sandbox_image")
    if len(events) > 100:
        missing.append("earlier_flight_events")
    if len(results) > 40:
        missing.append("additional_verification_results")
    if not model_event:
        missing.append("model_metadata")
    missing.append("source_release_revision")
    try:
        app_version = version("forge-ai")
    except PackageNotFoundError:
        app_version = None
        missing.append("runtime_version")
    policy_hash = content_sha256(canonical_bytes(job.safety_policy_snapshot)) if job.safety_policy_snapshot else None
    if policy_hash is None:
        missing.append("safety_policy_snapshot")
    image_ref = sandbox_event.data.get("image_ref") if sandbox_event else None
    image_digest = sandbox_event.data.get("image_digest") if sandbox_event else None
    if image_digest is None:
        missing.append("sandbox_image_digest")

    result_rows = [{"id": str(row.id), "verifier": verifier_ref(row.verifier), "status": row.status.value,
                    "exit_code": row.exit_code, "duration_ms": row.duration_ms,
                    "attempt": row.attempt,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                    "finished_at": row.finished_at.isoformat() if row.finished_at else None}
                   for row in results[:40]]
    summary = {"execution_status": job.status.value, "verification_status": verification.status.value if verification else None,
               "reason_event": event.event_type, "reason_code": event.data.get("reason_code"),
               "started_at": job.started_at.isoformat() if job.started_at else None,
               "finished_at": job.finished_at.isoformat() if job.finished_at else None,
               "verification_finished_at": verification.finished_at.isoformat() if verification and verification.finished_at else None}
    payloads = {"execution-summary": canonical_bytes(summary),
                "verification-results": canonical_bytes({"results": result_rows, "truncated": len(results) > 40})}
    artifacts = []
    settings = get_settings()
    artifact_max_bytes = min(MAX_ARTIFACT_BYTES, settings.capsule_artifact_max_bytes)
    artifact_max_count = settings.capsule_artifact_max_count
    for kind, content in payloads.items():
        if len(artifacts) >= artifact_max_count:
            missing.append(f"{kind}_count_limit")
            continue
        if len(content) > artifact_max_bytes:
            missing.append(f"{kind}_size_limit")
            continue
        artifacts.append({"id": str(generate_id()), "kind": kind, "sha256": content_sha256(content),
                          "size_bytes": len(content)})
    manifest = {
        "schema_version": 1, "execution_id": str(job.id), "attempt": event.attempt,
        "organization_id": str(job.organization_id), "workspace_id": str(job.organization_id),
        "repository_id": str(job.repository_id), "base_commit_sha": job.commit_sha_before,
        "event_id": str(event.id), "event_sequence": event.sequence, "state": "FINAL" if event.event_type in FINAL_EVENTS else "PARTIAL",
        "transition_event": event.event_type, "transition_at": event.occurred_at.isoformat(),
        "reason_code": event.data.get("reason_code"),
        "execution_status": job.status.value, "verification_job_id": str(verification.id) if verification else None,
        "verification_status": verification.status.value if verification else None,
        "patch_id": str(patch.id) if patch else None,
        "patch_digest": patch.review_digest if patch else None,
        "change_set_id": str(change.id) if change else None,
        "selection_plan_id": str(selection.id) if selection else None,
        "selection_patch_digest": selection.patch_digest if selection else None,
        "safety_policy_sha256": policy_hash,
        "runtime": {"forge_version": app_version, "provider": model_event.data.get("provider") if model_event else None,
                    "model": model_event.data.get("model") if model_event else None},
        "sandbox": {"image_ref": image_ref, "image_digest": image_digest,
                    "network_disabled": True if sandbox_event else None},
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "verification_started_at": verification.started_at.isoformat() if verification and verification.started_at else None,
        "verification_finished_at": verification.finished_at.isoformat() if verification and verification.finished_at else None,
        "captured_at": datetime.now(UTC).isoformat(),
        "flight_event_ids": [str(row.id) for row in reversed(events[:100])],
        "verification_results": result_rows,
        "artifacts": artifacts, "missing_evidence": sorted(set(missing)),
        "provenance": {"base_commit_sha": "execution_jobs", "patch_digest": "patches",
                       "change_set_id": "context_change_sets", "selection_plan_id": "verification_plans",
                       "verification_results": "verification_results", "flight_event_ids": "execution_events"},
    }
    capsule = RunCapsuleModel(id=generate_id(), organization_id=scope[0], repository_id=scope[2],
                              execution_job_id=scope[1], event_id=event.id, attempt=event.attempt,
                              state=manifest["state"], manifest=manifest,
                              manifest_sha256=content_sha256(canonical_bytes(manifest)), created_at=datetime.now(UTC))
    session.add(capsule)
    await session.flush()
    for descriptor in artifacts:
        session.add(RunCapsuleArtifactModel(id=UUID(descriptor["id"]), organization_id=scope[0],
                                          capsule_id=capsule.id, kind=descriptor["kind"],
                                          content=payloads[descriptor["kind"]].decode("utf-8"),
                                          sha256=descriptor["sha256"], size_bytes=descriptor["size_bytes"]))
    await session.flush()
