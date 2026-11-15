"""Conservative test suggestions and configured-verifier selection."""

import hashlib
import json
from pathlib import PurePosixPath
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.atlas import AtlasNodeModel, AtlasSnapshotModel
from packages.database.models.context_lens import ContextChangeSetModel
from services.atlas.graph import is_test_path
from services.atlas.service import impact_from_db
from services.execution.flight_recorder import SAFE_STRING, SENSITIVE_VALUE
from services.safety.policy import _protected_path


def _risk_path(path: str) -> bool:
    return (path.startswith(("services/auth/", "services/safety/", "services/execution/",
                             "services/verification/", "packages/database/", "packages/shared/",
                             "packages/events/", "migrations/", ".github/", "docker/", "apps/worker/",
                             "tests/security/", "services/github/", "services/patch/", "apps/frontend/config/"))
            or PurePosixPath(path).name in {"package.json", "package-lock.json", "pnpm-lock.yaml",
                                             "yarn.lock", "pyproject.toml", "uv.lock", "requirements.txt",
                                             "forge.yaml", "docker-compose.yml", "render.yaml", "vercel.json"})


def _explicit_test_target(verifier) -> str | None:
    command = [*verifier.command, *verifier.arguments]
    if not command:
        return None
    if command[0] in {"pytest", "pytest-3"}:
        args = command[1:]
    elif len(command) >= 3 and command[:3] in (["python", "-m", "pytest"], ["python3", "-m", "pytest"]):
        args = command[3:]
    else:
        return None
    targets = [arg for arg in args if is_test_path(arg) and not _protected_path(arg)
               and PurePosixPath(arg).as_posix() == arg]
    if len(targets) != 1 or any(arg.endswith((".py", ".js", ".ts", ".tsx")) and arg not in targets for arg in args):
        return None
    return targets[0]


def verifier_ref(identifier: str) -> str:
    return identifier if SAFE_STRING.fullmatch(identifier) and not SENSITIVE_VALUE.search(identifier) else (
        "sha256:" + hashlib.sha256(identifier.encode()).hexdigest())


def select_verification(file_changes: list[dict], graph_tests: list[dict], base_paths: set[str],
                        snapshot_id: str | None, verifiers: list, *, graph_truncated: bool = False,
                        graph_uncertain: bool = False) -> dict:
    paths = sorted({item["path"] for item in file_changes})
    reasons = []
    if not snapshot_id:
        reasons.append("MISSING_BASE_GRAPH")
    if graph_truncated or len(paths) > 10:
        reasons.append("GRAPH_TRUNCATED")
    if graph_uncertain:
        reasons.append("UNRESOLVED_RELATIONSHIP")
    if any(item["type"] in {"added", "deleted", "renamed", "unknown"} or item["path"] not in base_paths
           for item in file_changes) and snapshot_id:
        reasons.append("NEW_OR_DELETED_CODE")
    if any(_risk_path(path) for path in paths):
        reasons.append("CROSS_CUTTING_CHANGE")

    candidates: dict[str, dict] = {}
    for path in paths:
        if is_test_path(path) and not _protected_path(path):
            candidates[path] = {"path": path, "score": 100, "confidence": "HIGH", "scope": "DIRECT",
                                "risk": "HIGH" if _risk_path(path) else "NORMAL",
                                "reason_codes": ["CHANGED_TEST_FILE"], "source_paths": [path]}
    if snapshot_id:
        for item in graph_tests[:500]:
            path = item["path"]
            source = item["source_path"]
            if source not in paths or not is_test_path(path) or _protected_path(path) or path in candidates:
                continue
            depth = item["depth"]
            confidence = item["confidence"] if item["confidence"] in {"HIGH", "MEDIUM", "LOW"} else "LOW"
            score = max(1, 80 - min(depth, 5) * 10 - {"HIGH": 0, "MEDIUM": 5, "LOW": 15}[confidence])
            existing = candidates.get(path)
            if existing:
                existing["source_paths"] = sorted(set(existing["source_paths"] + [source]))
                if score > existing["score"]:
                    existing["score"] = score
                    existing["confidence"] = confidence
            else:
                candidates[path] = {"path": path, "score": score, "confidence": confidence,
                                    "scope": "INFERRED", "risk": "NORMAL",
                                    "reason_codes": ["ATLAS_TEST_ASSOCIATION"], "source_paths": [source]}
    suggestions = sorted(candidates.values(), key=lambda item: (-item["score"], item["path"]))[:100]
    if not suggestions:
        reasons.append("NO_TEST_MAPPING")
    mapped_sources = {source for item in suggestions for source in item["source_paths"]}
    if snapshot_id and suggestions and any(path not in mapped_sources for path in paths):
        reasons.append("PARTIAL_TEST_MAPPING")
    if any(item["confidence"] == "LOW" for item in suggestions):
        reasons.append("LOW_CONFIDENCE_TEST_MAPPING")
    if len(candidates) > 100:
        reasons.append("GRAPH_TRUNCATED")

    enabled = [verifier for verifier in verifiers if verifier.enabled]
    if len(enabled) > 100:
        reasons.append("VERIFIER_LIMIT_EXCEEDED")
        enabled = enabled[:100]
    tests = [verifier for verifier in enabled if verifier.category == "test"]
    targets = {verifier_ref(verifier.identifier): _explicit_test_target(verifier) for verifier in tests}
    candidate_paths = {item["path"] for item in suggestions}
    if not tests:
        reasons.append("NO_CONFIGURED_TEST_VERIFIER")
    elif (len({verifier_ref(verifier.identifier) for verifier in enabled}) != len(enabled)
          or any(target is None for target in targets.values())
          or not candidate_paths <= set(targets.values())):
        reasons.append("UNMAPPED_VERIFIER_COMMAND")

    broad = bool(reasons)
    selected = [verifier_ref(verifier.identifier) for verifier in enabled
                if broad or verifier.category != "test" or targets[verifier_ref(verifier.identifier)] in candidate_paths]
    deferred = [{"id": verifier_ref(verifier.identifier), "reason": "UNRELATED_EXPLICIT_TEST"}
                for verifier in enabled if verifier_ref(verifier.identifier) not in selected]
    target_paths = {identifier: path for identifier, path in targets.items() if path}
    selected_reasons = {verifier_ref(verifier.identifier): (
        "BROAD_FALLBACK" if broad else "SUGGESTED_TEST" if verifier.category == "test" else "REQUIRED_NON_TEST")
        for verifier in enabled if verifier_ref(verifier.identifier) in selected}
    return {"version": 1, "strategy": "BROAD_CONFIGURED" if broad else "EXPLICIT_TEST_TARGETS",
            "snapshot_id": snapshot_id, "changed_paths": paths[:50], "suggested_tests": suggestions,
            "selected_verifiers": selected, "deferred_verifiers": deferred,
            "verifier_targets": target_paths, "selected_verifier_reasons": selected_reasons,
            "fallback_reasons": sorted(set(reasons)), "coverage_claimed": False}


def verifier_fingerprint(verifiers: list) -> str:
    settings = [{"id": item.identifier, "category": item.category, "enabled": item.enabled,
                 "command": item.command, "arguments": item.arguments,
                 "working_directory": item.working_directory, "timeout": item.timeout,
                 "blocking": item.blocking} for item in verifiers[:101]]
    return hashlib.sha256(json.dumps({"count": len(verifiers), "checks": settings},
                                  sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def build_decision(session: AsyncSession, organization_id: UUID, repository_id: UUID,
                         change: ContextChangeSetModel, verifiers: list) -> dict:
    paths = sorted({item["path"] for item in change.file_changes})
    snapshot = None
    if change.base_snapshot_id:
        snapshot = (await session.execute(select(AtlasSnapshotModel).where(
            AtlasSnapshotModel.id == change.base_snapshot_id,
            AtlasSnapshotModel.organization_id == organization_id,
            AtlasSnapshotModel.repository_id == repository_id,
            AtlasSnapshotModel.commit_sha == change.base_commit_sha,
            AtlasSnapshotModel.dirty.is_(False), AtlasSnapshotModel.status == "PUBLISHED",
        ))).scalar_one_or_none()
    base_paths: set[str] = set()
    associations: list[dict] = []
    truncated = len(paths) > 10
    uncertain = False
    if snapshot:
        base_paths = {path for path in (await session.execute(select(AtlasNodeModel.path).where(
            AtlasNodeModel.snapshot_id == snapshot.id, AtlasNodeModel.organization_id == organization_id,
            AtlasNodeModel.repository_id == repository_id, AtlasNodeModel.kind.in_(("file", "test_file")),
            AtlasNodeModel.path.in_(paths),
        ))).scalars().all() if path is not None}
        for source in paths[:10]:
            if source not in base_paths:
                continue
            try:
                impact = await impact_from_db(session, organization_id, repository_id, snapshot.id,
                                              f"file:{source}", max_depth=3, max_results=40)
            except ValueError:
                truncated = True
                continue
            truncated = truncated or impact.truncated
            uncertain = uncertain or bool(impact.unresolved)
            for item in impact.items:
                if not item.key.startswith("file:") or not is_test_path(item.key[5:]):
                    continue
                confidence = "LOW" if any(edge.confidence == "LOW" for edge in item.via) else (
                    "MEDIUM" if any(edge.confidence == "MEDIUM" for edge in item.via) else "HIGH")
                associations.append({"path": item.key[5:], "source_path": source, "depth": item.depth,
                                     "confidence": confidence, "relationship": item.via[0].kind})
    decision = select_verification(change.file_changes, associations, base_paths,
                                   str(snapshot.id) if snapshot else None, verifiers,
                                   graph_truncated=truncated, graph_uncertain=uncertain)
    decision["verifier_fingerprint"] = verifier_fingerprint(verifiers)
    return decision
