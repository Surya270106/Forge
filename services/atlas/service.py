"""Atlas jobs share Forge's outbox and worker, then publish one atomic graph snapshot."""

import asyncio
import hashlib
import re
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from packages.database.models.atlas import AtlasEdgeModel, AtlasFileFactModel, AtlasJobModel, AtlasNodeModel, AtlasSnapshotModel
from packages.database.models.execution import ExecutionJobModel
from packages.database.models.repository import RepositoryModel
from packages.shared.events import EventEnvelope
from packages.shared.identifiers import generate_id
from services.execution.flight_recorder import record_event
from services.repository_memory.events import OutboxEventPublisher

from .graph import (
    IGNORED_DIRS,
    INDEXER_VERSION,
    MAX_FILE_BYTES,
    MAX_FILES,
    CallFact,
    FileFact,
    Graph,
    GraphEdge,
    GraphNode,
    ImpactItem,
    ImpactResult,
    ImportFact,
    InheritanceFact,
    SymbolFact,
    build_graph,
    scan_git_revision,
    scan_repository,
)

CONFIG_FINGERPRINT = hashlib.sha256(f"{sorted(IGNORED_DIRS)}:{MAX_FILES}:{MAX_FILE_BYTES}:{INDEXER_VERSION}".encode()).hexdigest()


def _event(name: str, organization_id: UUID, repository_id: UUID, job_id: UUID, **data: str | int) -> EventEnvelope:
    return EventEnvelope(event_type=f"repository.atlas.{name}", aggregate_type="repository",
                         aggregate_id=str(repository_id), organization_id=str(organization_id),
                         payload={"organization_id": str(organization_id), "job_id": str(job_id), **data})


async def _flight_event(session: AsyncSession, job: AtlasJobModel, name: str, **data: str | int | UUID) -> None:
    if job.execution_id is None:
        return
    actor = "user" if name == "index_requested" and job.attempts == 0 else "worker"
    await record_event(session, job.organization_id, job.execution_id, f"atlas.{name}", actor,
                       "atlas.service", data={"repository_id": job.repository_id, "atlas_job_id": job.id,
                                              "indexer_version": INDEXER_VERSION, "retry_count": job.attempts, **data},
                       idempotency_key=f"atlas-{job.id}-{name}-{job.attempts}")


def _fact_from_document(document: dict) -> FileFact:
    return FileFact(path=document["path"], checksum=document["checksum"], language=document["language"],
                    parser_version=document["parser_version"],
                    symbols=tuple(SymbolFact(**item) for item in document["symbols"]),
                    imports=tuple(ImportFact(item["module"], tuple(tuple(pair) for pair in item["names"]),
                                             item["line"], item["dynamic"]) for item in document["imports"]),
                    calls=tuple(CallFact(**item) for item in document["calls"]),
                    inherits=tuple(InheritanceFact(**item) for item in document.get("inherits", [])))


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          check=True, timeout=15).stdout.strip()


async def create_job(session: AsyncSession, organization_id: UUID, repository_id: UUID, requester_id: UUID,
                     idempotency_key: UUID, requested_revision: str | None = None,
                     execution_id: UUID | None = None) -> AtlasJobModel:
    if requested_revision is not None and not re.fullmatch(r"[0-9a-f]{40}", requested_revision):
        raise ValueError("A full commit SHA is required")
    repository = (await session.execute(select(RepositoryModel).where(
        RepositoryModel.id == repository_id, RepositoryModel.organization_id == organization_id,
    ).with_for_update())).scalar_one_or_none()
    if repository is None:
        raise ValueError("Repository unavailable")
    if execution_id is not None:
        execution = await session.get(ExecutionJobModel, execution_id)
        if execution is None or execution.organization_id != organization_id or execution.repository_id != repository_id:
            raise ValueError("Execution unavailable for Atlas job")
    existing = (await session.execute(select(AtlasJobModel).where(
        AtlasJobModel.organization_id == organization_id, AtlasJobModel.repository_id == repository_id,
        AtlasJobModel.idempotency_key == idempotency_key,
    ))).scalar_one_or_none()
    if existing:
        if existing.requested_revision != requested_revision or existing.execution_id != execution_id:
            raise ValueError("Idempotency key refers to another Atlas request")
        return existing
    job = AtlasJobModel(id=generate_id(), organization_id=organization_id, repository_id=repository_id,
                        requested_by=requester_id, idempotency_key=idempotency_key,
                        requested_revision=requested_revision, execution_id=execution_id,
                        status="QUEUED", attempts=0)
    session.add(job)
    await OutboxEventPublisher(session).publish(_event("index_requested", organization_id, repository_id, job.id))
    await _flight_event(session, job, "index_requested")
    return job


async def run_job(sessions: async_sessionmaker[AsyncSession], job_id: UUID, workspace_root: Path) -> None:
    owner = str(uuid4())
    async with sessions() as session:
        job = (await session.execute(select(AtlasJobModel).where(AtlasJobModel.id == job_id)
                                     .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not job or job.status != "QUEUED":
            return
        if job.attempts >= 3:
            job.status = "FAILED"
            job.error_code = "RETRY_LIMIT"
            job.finished_at = datetime.now(UTC)
            await _flight_event(session, job, "index_failed", reason_code="RETRY_LIMIT")
            await session.commit()
            return
        job.status = "RUNNING"
        job.attempts += 1
        job.lease_owner = owner
        # Two bounded scans may take 240s; leave room for graph persistence before recovery.
        job.lease_expires_at = datetime.now(UTC) + timedelta(minutes=10)
        job.started_at = datetime.now(UTC)
        organization_id, repository_id, requested_revision = job.organization_id, job.repository_id, job.requested_revision
        await OutboxEventPublisher(session).publish(_event("index_started", organization_id, repository_id, job_id))
        await _flight_event(session, job, "index_started")
        await session.commit()

    root = Path(workspace_root).resolve()
    workspace = root / str(organization_id) / str(repository_id)
    try:
        if workspace.is_symlink() or not workspace.is_dir() or not workspace.resolve().is_relative_to(root):
            raise ValueError("Repository workspace unavailable")
        async with sessions() as session:
            latest = (await session.execute(select(AtlasSnapshotModel).where(
                AtlasSnapshotModel.organization_id == organization_id,
                AtlasSnapshotModel.repository_id == repository_id,
                AtlasSnapshotModel.status == "PUBLISHED",
                AtlasSnapshotModel.indexer_version == INDEXER_VERSION,
                AtlasSnapshotModel.config_fingerprint == CONFIG_FINGERPRINT,
            ).order_by(AtlasSnapshotModel.completed_at.desc()).limit(1))).scalar_one_or_none()
            previous: dict[str, FileFact] = {}
            if latest:
                rows = (await session.execute(select(AtlasFileFactModel).where(
                    AtlasFileFactModel.snapshot_id == latest.id,
                    AtlasFileFactModel.organization_id == organization_id,
                ))).scalars().all()
                previous = {row.path: _fact_from_document(row.fact) for row in rows}
        commit = await asyncio.to_thread(_git, workspace, "rev-parse", requested_revision or "HEAD")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Repository revision unavailable")
        tree = await asyncio.to_thread(_git, workspace, "rev-parse", f"{commit}^{{tree}}")
        dirty_before = False if requested_revision else bool(await asyncio.to_thread(_git, workspace, "status", "--porcelain", "--untracked-files=all"))
        if requested_revision:
            scan = await asyncio.wait_for(asyncio.to_thread(scan_git_revision, workspace, commit, previous=previous), timeout=120)
        else:
            scan = await asyncio.wait_for(asyncio.to_thread(scan_repository, workspace, previous=previous), timeout=120)
            repeat = await asyncio.wait_for(asyncio.to_thread(scan_repository, workspace,
                                                                previous={fact.path: fact for fact in scan.facts}), timeout=120)
            if scan.fingerprint != repeat.fingerprint or commit != await asyncio.to_thread(_git, workspace, "rev-parse", "HEAD"):
                raise ValueError("Repository changed during indexing")
        graph = build_graph(scan.facts)
        if len(graph.nodes) > 50_000 or len(graph.edges) > 100_000:
            raise ValueError("Atlas graph exceeds node or edge limit")
        async with sessions() as session:
            job = (await session.execute(select(AtlasJobModel).where(AtlasJobModel.id == job_id)
                                         .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
            if not job or job.status != "RUNNING" or job.lease_owner != owner or not job.lease_expires_at or job.lease_expires_at <= datetime.now(UTC):
                await session.rollback()
                return
            snapshot_id = generate_id()
            parser_versions = {fact.language: fact.parser_version for fact in scan.facts}
            snapshot = AtlasSnapshotModel(
                id=snapshot_id, organization_id=organization_id, repository_id=repository_id, job_id=job_id,
                commit_sha=commit, tree_sha=tree, source_fingerprint=scan.fingerprint, dirty=dirty_before,
                indexer_version=INDEXER_VERSION, parser_versions=parser_versions,
                config_fingerprint=CONFIG_FINGERPRINT, status="BUILDING", warnings=list(scan.warnings[:100]),
                stats={"files": len(scan.facts), "nodes": len(graph.nodes), "edges": len(graph.edges),
                       "reused_files": scan.reused_files},
            )
            session.add(snapshot)
            await session.flush()
            session.add_all(AtlasFileFactModel(id=generate_id(), organization_id=organization_id,
                                               repository_id=repository_id, snapshot_id=snapshot_id,
                                               path=fact.path, checksum=fact.checksum, fact=asdict(fact))
                            for fact in scan.facts)
            node_ids = {node.key: uuid5(snapshot_id, node.key) for node in graph.nodes}
            session.add_all(AtlasNodeModel(id=node_ids[node.key], organization_id=organization_id,
                                           repository_id=repository_id, snapshot_id=snapshot_id,
                                           stable_key=node.key, kind=node.kind, name=node.name, path=node.path,
                                           line_start=node.line_start, line_end=node.line_end, language=node.language,
                                           content_hash=node.content_hash, parser_version=node.parser_version)
                            for node in graph.nodes)
            await session.flush()
            session.add_all(AtlasEdgeModel(id=generate_id(), organization_id=organization_id,
                                           repository_id=repository_id, snapshot_id=snapshot_id,
                                           from_node_id=node_ids[edge.source],
                                           to_node_id=node_ids[edge.target] if edge.target else None,
                                           kind=edge.kind, target_name=edge.target_name,
                                           evidence_path=edge.evidence_path, evidence_line=edge.evidence_line,
                                           resolution=edge.resolution, confidence=edge.confidence,
                                           method=edge.method) for edge in graph.edges)
            await session.flush()
            snapshot.status = "PUBLISHED"
            snapshot.completed_at = datetime.now(UTC)
            job.status = "SUCCEEDED"
            job.finished_at = snapshot.completed_at
            job.lease_owner = None
            job.lease_expires_at = None
            await OutboxEventPublisher(session).publish(_event("snapshot_published", organization_id, repository_id,
                                                               job_id, snapshot_id=str(snapshot_id),
                                                               node_count=len(graph.nodes), edge_count=len(graph.edges)))
            await _flight_event(session, job, "files_parsed", file_count=len(scan.facts))
            await _flight_event(session, job, "snapshot_published", atlas_snapshot_id=snapshot_id,
                                node_count=len(graph.nodes), edge_count=len(graph.edges))
            await session.commit()
    except Exception as error:
        async with sessions() as session:
            job = (await session.execute(select(AtlasJobModel).where(AtlasJobModel.id == job_id)
                                         .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
            if job and job.status == "RUNNING" and job.lease_owner == owner:
                job.status = "FAILED"
                job.error_code = type(error).__name__[:60]
                job.finished_at = datetime.now(UTC)
                job.lease_owner = None
                job.lease_expires_at = None
                await OutboxEventPublisher(session).publish(_event("index_failed", organization_id, repository_id,
                                                                   job_id, reason_code=type(error).__name__[:60]))
                await _flight_event(session, job, "index_failed", reason_code=type(error).__name__[:60])
                await session.commit()


async def recover_stale_jobs(session: AsyncSession, organization_id: UUID) -> int:
    now = datetime.now(UTC)
    rows = (await session.execute(select(AtlasJobModel).where(
        AtlasJobModel.organization_id == organization_id,
        AtlasJobModel.status == "RUNNING",
        AtlasJobModel.lease_expires_at < now,
    ).with_for_update(skip_locked=True).limit(100))).scalars().all()
    for job in rows:
        job.lease_owner = None
        job.lease_expires_at = None
        if job.attempts >= 3:
            job.status = "FAILED"
            job.error_code = "RETRY_LIMIT"
            job.finished_at = now
            await OutboxEventPublisher(session).publish(_event("index_failed", organization_id, job.repository_id,
                                                               job.id, reason_code="RETRY_LIMIT"))
            await _flight_event(session, job, "index_failed", reason_code="RETRY_LIMIT")
        else:
            job.status = "QUEUED"
            await OutboxEventPublisher(session).publish(_event("index_requested", organization_id, job.repository_id,
                                                               job.id, retry_count=job.attempts))
            await _flight_event(session, job, "index_requested")
    return len(rows)


async def get_graph(session: AsyncSession, organization_id: UUID, repository_id: UUID, snapshot_id: UUID) -> Graph:
    repository = await session.get(RepositoryModel, repository_id)
    snapshot = await session.get(AtlasSnapshotModel, snapshot_id)
    if not repository or repository.organization_id != organization_id or not snapshot or snapshot.organization_id != organization_id or snapshot.repository_id != repository_id or snapshot.status != "PUBLISHED":
        raise ValueError("Atlas snapshot unavailable")
    nodes = (await session.execute(select(AtlasNodeModel).where(
        AtlasNodeModel.snapshot_id == snapshot_id, AtlasNodeModel.organization_id == organization_id,
    ).order_by(AtlasNodeModel.stable_key).limit(50_001))).scalars().all()
    if len(nodes) > 50_000:
        raise ValueError("Atlas graph exceeds query budget")
    edges = (await session.execute(select(AtlasEdgeModel).where(
        AtlasEdgeModel.snapshot_id == snapshot_id, AtlasEdgeModel.organization_id == organization_id,
    ).order_by(AtlasEdgeModel.id).limit(100_001))).scalars().all()
    if len(edges) > 100_000:
        raise ValueError("Atlas graph exceeds query budget")
    keys = {node.id: node.stable_key for node in nodes}
    return Graph(tuple(GraphNode(node.stable_key, node.kind, node.name, node.path, node.line_start, node.line_end,
                                 node.language, node.content_hash, node.parser_version) for node in nodes),
                 tuple(GraphEdge(edge.kind, keys[edge.from_node_id], keys.get(edge.to_node_id) if edge.to_node_id else None, edge.target_name,
                                 edge.evidence_path, edge.evidence_line, edge.resolution, edge.confidence, edge.method)
                       for edge in edges))


async def impact_from_db(session: AsyncSession, organization_id: UUID, repository_id: UUID, snapshot_id: UUID,
                         start_key: str, *, max_depth: int = 3, max_results: int = 100,
                         kinds: frozenset[str] = frozenset({"IMPORTS", "CALLS", "TESTS", "EXTENDS", "IMPLEMENTS"}),
                         min_confidence: str = "LOW") -> ImpactResult:
    if not 0 <= max_depth <= 5 or not 1 <= max_results <= 200 or min_confidence not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValueError("Atlas query budget exceeded")
    if not kinds <= {"IMPORTS", "CALLS", "TESTS", "EXTENDS", "IMPLEMENTS", "REFERENCES"}:
        raise ValueError("Unknown relationship type")
    snapshot = await session.get(AtlasSnapshotModel, snapshot_id)
    repository = await session.get(RepositoryModel, repository_id)
    if not snapshot or snapshot.organization_id != organization_id or snapshot.repository_id != repository_id or snapshot.status != "PUBLISHED" or not repository or repository.organization_id != organization_id:
        raise ValueError("Atlas snapshot unavailable")
    start = (await session.execute(select(AtlasNodeModel).where(
        AtlasNodeModel.snapshot_id == snapshot_id, AtlasNodeModel.organization_id == organization_id,
        AtlasNodeModel.stable_key == start_key,
    ))).scalar_one_or_none()
    if start is None:
        raise ValueError("Atlas node unavailable")
    confidence = {"LOW": ("LOW", "MEDIUM", "HIGH"), "MEDIUM": ("MEDIUM", "HIGH"), "HIGH": ("HIGH",)}[min_confidence]
    frontier = [(start.id, ())]
    seen = {start.id}
    found: list[ImpactItem] = []
    truncated = False
    for depth in range(1, max_depth + 1):
        if not frontier:
            break
        sources = (await session.execute(select(AtlasEdgeModel, AtlasNodeModel).join(
            AtlasNodeModel, AtlasEdgeModel.from_node_id == AtlasNodeModel.id,
        ).where(
            AtlasEdgeModel.snapshot_id == snapshot_id, AtlasEdgeModel.organization_id == organization_id,
            AtlasEdgeModel.to_node_id.in_([item[0] for item in frontier]),
            AtlasEdgeModel.kind.in_(kinds), AtlasEdgeModel.confidence.in_(confidence),
            AtlasEdgeModel.resolution != "UNRESOLVED",
        ).order_by(AtlasNodeModel.stable_key, AtlasEdgeModel.id).limit(1001))).all()
        if len(sources) > 1000:
            truncated = True
        paths = dict(frontier)
        next_frontier = []
        target_ids = {edge.to_node_id for edge, _ in sources}
        target_nodes = (await session.execute(select(AtlasNodeModel).where(
            AtlasNodeModel.snapshot_id == snapshot_id, AtlasNodeModel.id.in_(target_ids),
        ))).scalars().all()
        target_keys = {node.id: node.stable_key for node in target_nodes}
        for edge, source in sources[:1000]:
            if source.id in seen or edge.to_node_id not in paths:
                continue
            if len(found) >= max_results:
                truncated = True
                break
            seen.add(source.id)
            evidence = GraphEdge(edge.kind, source.stable_key, target_keys.get(edge.to_node_id),
                                 edge.target_name, edge.evidence_path, edge.evidence_line,
                                 edge.resolution, edge.confidence, edge.method)
            chain = (*paths[edge.to_node_id], evidence)
            found.append(ImpactItem(source.stable_key, depth, chain))
            next_frontier.append((source.id, chain))
        frontier = next_frontier
        if truncated:
            break
    unresolved_rows = (await session.execute(select(AtlasEdgeModel, AtlasNodeModel).join(
        AtlasNodeModel, AtlasEdgeModel.from_node_id == AtlasNodeModel.id,
    ).where(AtlasEdgeModel.snapshot_id == snapshot_id, AtlasEdgeModel.organization_id == organization_id,
            AtlasEdgeModel.from_node_id.in_(seen), AtlasEdgeModel.resolution == "UNRESOLVED",
            AtlasEdgeModel.kind.in_(kinds)).order_by(AtlasNodeModel.stable_key, AtlasEdgeModel.id)
                                  .limit(max_results))).all()
    unresolved = tuple(GraphEdge(edge.kind, node.stable_key, None, edge.target_name, edge.evidence_path,
                                 edge.evidence_line, edge.resolution, edge.confidence, edge.method)
                       for edge, node in unresolved_rows)
    return ImpactResult(tuple(found), truncated, unresolved)
