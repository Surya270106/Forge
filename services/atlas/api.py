"""Authenticated, bounded Atlas queries over published repository snapshots."""

from collections.abc import Sequence
from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.engine import get_session
from packages.database.models.atlas import AtlasEdgeModel, AtlasJobModel, AtlasNodeModel, AtlasSnapshotModel
from packages.database.models.repository import RepositoryModel
from packages.shared.identifiers import OrganizationId
from services.auth.dependencies import get_current_user, require_permission

from .graph import GraphDiff, compare_graphs, is_test_path
from .service import create_job, get_graph, impact_from_db

router = APIRouter(prefix="/api/v1/repositories/{repository_id}/atlas", tags=["atlas"])


class IndexRequest(BaseModel):
    idempotency_key: UUID
    revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    execution_id: UUID | None = None


def _job_document(job: AtlasJobModel) -> dict:
    return {"id": str(job.id), "repository_id": str(job.repository_id), "status": job.status,
            "execution_id": str(job.execution_id) if job.execution_id else None,
            "attempts": job.attempts, "requested_revision": job.requested_revision,
            "error_code": job.error_code, "created_at": job.created_at, "started_at": job.started_at,
            "finished_at": job.finished_at}


def _snapshot_document(snapshot: AtlasSnapshotModel) -> dict:
    return {"id": str(snapshot.id), "job_id": str(snapshot.job_id), "commit_sha": snapshot.commit_sha,
            "tree_sha": snapshot.tree_sha, "source_fingerprint": snapshot.source_fingerprint,
            "dirty": snapshot.dirty, "indexer_version": snapshot.indexer_version,
            "parser_versions": snapshot.parser_versions, "status": snapshot.status,
            "stats": snapshot.stats, "warnings": snapshot.warnings,
            "created_at": snapshot.created_at, "completed_at": snapshot.completed_at}


def _node_document(node: AtlasNodeModel) -> dict:
    return {"id": str(node.id), "key": node.stable_key, "kind": node.kind, "name": node.name,
            "path": node.path, "line_start": node.line_start, "line_end": node.line_end,
            "language": node.language, "content_hash": node.content_hash, "parser_version": node.parser_version}


def _edge_document(edge: AtlasEdgeModel, keys: dict[UUID, str]) -> dict:
    return {"id": str(edge.id), "kind": edge.kind, "source": keys[edge.from_node_id],
            "target": keys.get(edge.to_node_id) if edge.to_node_id else None, "target_name": edge.target_name,
            "evidence_path": edge.evidence_path, "evidence_line": edge.evidence_line,
            "resolution": edge.resolution, "confidence": edge.confidence, "method": edge.method}


def _bounded_diff(diff: GraphDiff) -> dict:
    changes = asdict(diff)
    totals = {kind: len(items) for kind, items in changes.items()}
    return {kind: items[:500] for kind, items in changes.items()} | {
        "totals": totals, "truncated": any(count > 500 for count in totals.values()),
    }


async def _visible_repository(session: AsyncSession, organization_id: UUID, repository_id: UUID) -> RepositoryModel:
    repository = (await session.execute(select(RepositoryModel).where(
        RepositoryModel.id == repository_id, RepositoryModel.organization_id == organization_id,
    ))).scalar_one_or_none()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository unavailable")
    return repository


async def _visible_snapshot(session: AsyncSession, organization_id: UUID, repository_id: UUID,
                            snapshot_id: UUID) -> AtlasSnapshotModel:
    await _visible_repository(session, organization_id, repository_id)
    snapshot = (await session.execute(select(AtlasSnapshotModel).where(
        AtlasSnapshotModel.id == snapshot_id, AtlasSnapshotModel.organization_id == organization_id,
        AtlasSnapshotModel.repository_id == repository_id, AtlasSnapshotModel.status == "PUBLISHED",
    ))).scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Atlas snapshot unavailable")
    return snapshot


async def _edge_keys(session: AsyncSession, snapshot_id: UUID, edges: Sequence[AtlasEdgeModel]) -> dict[UUID, str]:
    ids = {edge.from_node_id for edge in edges} | {edge.to_node_id for edge in edges if edge.to_node_id}
    if not ids:
        return {}
    nodes = (await session.execute(select(AtlasNodeModel.id, AtlasNodeModel.stable_key).where(
        AtlasNodeModel.snapshot_id == snapshot_id, AtlasNodeModel.id.in_(ids),
    ))).all()
    return {node_id: stable_key for node_id, stable_key in nodes}


@router.post("/index", status_code=status.HTTP_202_ACCEPTED)
async def request_index(repository_id: UUID, request: IndexRequest,
                        organization_id: OrganizationId = Depends(require_permission("repo:import", rate_category="repository")),
                        user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await _visible_repository(session, organization_id, repository_id)
    try:
        job = await create_job(session, organization_id, repository_id, UUID(user["id"]),
                               request.idempotency_key, request.revision, request.execution_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    await session.commit()
    return _job_document(job)


@router.get("/jobs/{job_id}")
async def job_status(repository_id: UUID, job_id: UUID,
                     organization_id: OrganizationId = Depends(require_permission("repo:read")),
                     session: AsyncSession = Depends(get_session)):
    await _visible_repository(session, organization_id, repository_id)
    job = (await session.execute(select(AtlasJobModel).where(
        AtlasJobModel.id == job_id, AtlasJobModel.organization_id == organization_id,
        AtlasJobModel.repository_id == repository_id,
    ))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Atlas job unavailable")
    return _job_document(job)


@router.get("/snapshots")
async def snapshots(repository_id: UUID, page: int = Query(1, ge=1, le=1000),
                    page_size: int = Query(20, ge=1, le=100),
                    organization_id: OrganizationId = Depends(require_permission("repo:read")),
                    session: AsyncSession = Depends(get_session)):
    await _visible_repository(session, organization_id, repository_id)
    filters = (AtlasSnapshotModel.organization_id == organization_id,
               AtlasSnapshotModel.repository_id == repository_id, AtlasSnapshotModel.status == "PUBLISHED")
    total = await session.scalar(select(func.count()).select_from(AtlasSnapshotModel).where(*filters))
    rows = (await session.execute(select(AtlasSnapshotModel).where(*filters).order_by(
        AtlasSnapshotModel.completed_at.desc(), AtlasSnapshotModel.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [_snapshot_document(row) for row in rows], "total": total or 0,
            "page": page, "page_size": page_size}


@router.get("/snapshots/{snapshot_id}")
async def snapshot_detail(repository_id: UUID, snapshot_id: UUID,
                          organization_id: OrganizationId = Depends(require_permission("repo:read")),
                          session: AsyncSession = Depends(get_session)):
    return _snapshot_document(await _visible_snapshot(session, organization_id, repository_id, snapshot_id))


@router.get("/graph")
async def graph_page(repository_id: UUID, snapshot_id: UUID,
                     page: int = Query(1, ge=1, le=1000), page_size: int = Query(50, ge=1, le=100),
                     organization_id: OrganizationId = Depends(require_permission("repo:read")),
                     session: AsyncSession = Depends(get_session)):
    await _visible_snapshot(session, organization_id, repository_id, snapshot_id)
    node_filters = (AtlasNodeModel.snapshot_id == snapshot_id, AtlasNodeModel.organization_id == organization_id)
    edge_filters = (AtlasEdgeModel.snapshot_id == snapshot_id, AtlasEdgeModel.organization_id == organization_id)
    nodes = (await session.execute(select(AtlasNodeModel).where(*node_filters).order_by(AtlasNodeModel.stable_key)
                                   .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    edges = (await session.execute(select(AtlasEdgeModel).where(*edge_filters).order_by(AtlasEdgeModel.id)
                                   .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    keys = await _edge_keys(session, snapshot_id, edges)
    return {"nodes": [_node_document(node) for node in nodes],
            "edges": [_edge_document(edge, keys) for edge in edges],
            "node_total": await session.scalar(select(func.count()).select_from(AtlasNodeModel).where(*node_filters)),
            "edge_total": await session.scalar(select(func.count()).select_from(AtlasEdgeModel).where(*edge_filters)),
            "page": page, "page_size": page_size}


@router.get("/symbols")
async def symbols(repository_id: UUID, snapshot_id: UUID,
                  query: str = Query("", max_length=100), page: int = Query(1, ge=1, le=1000),
                  page_size: int = Query(20, ge=1, le=100),
                  organization_id: OrganizationId = Depends(require_permission("repo:read")),
                  session: AsyncSession = Depends(get_session)):
    await _visible_snapshot(session, organization_id, repository_id, snapshot_id)
    filters = [AtlasNodeModel.snapshot_id == snapshot_id, AtlasNodeModel.organization_id == organization_id,
               AtlasNodeModel.kind.in_(["class", "function", "method", "interface", "test_case"])]
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filters.append(AtlasNodeModel.name.ilike(f"%{escaped}%", escape="\\"))
    rows = (await session.execute(select(AtlasNodeModel).where(*filters).order_by(
        AtlasNodeModel.name, AtlasNodeModel.stable_key,
    ).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [_node_document(row) for row in rows],
            "total": await session.scalar(select(func.count()).select_from(AtlasNodeModel).where(*filters)),
            "page": page, "page_size": page_size}


@router.get("/impact")
async def impact_query(repository_id: UUID, snapshot_id: UUID,
                       node_key: str = Query(..., max_length=600), depth: int = Query(3, ge=0, le=5),
                       limit: int = Query(100, ge=1, le=200),
                       kinds: str = Query("IMPORTS,CALLS,TESTS,EXTENDS,IMPLEMENTS", max_length=80),
                       min_confidence: str = Query("LOW", pattern="^(LOW|MEDIUM|HIGH)$"),
                       organization_id: OrganizationId = Depends(require_permission("repo:read")),
                       session: AsyncSession = Depends(get_session)):
    await _visible_snapshot(session, organization_id, repository_id, snapshot_id)
    selected_kinds = frozenset(kinds.split(","))
    if not selected_kinds or not selected_kinds <= {"IMPORTS", "CALLS", "TESTS", "EXTENDS", "IMPLEMENTS"}:
        raise HTTPException(status_code=422, detail="Unknown Atlas relationship type")
    try:
        result = await impact_from_db(session, organization_id, repository_id, snapshot_id, node_key,
                                      max_depth=depth, max_results=limit, kinds=selected_kinds,
                                      min_confidence=min_confidence)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"snapshot_id": str(snapshot_id), "start": node_key,
            "items": [asdict(item) for item in result.items], "truncated": result.truncated,
            "unresolved": [asdict(edge) for edge in result.unresolved]}


@router.get("/tests")
async def relevant_tests(repository_id: UUID, snapshot_id: UUID,
                         node_key: str = Query(..., max_length=600),
                         organization_id: OrganizationId = Depends(require_permission("repo:read")),
                         session: AsyncSession = Depends(get_session)):
    await _visible_snapshot(session, organization_id, repository_id, snapshot_id)
    start = (await session.execute(select(AtlasNodeModel).where(
        AtlasNodeModel.snapshot_id == snapshot_id, AtlasNodeModel.organization_id == organization_id,
        AtlasNodeModel.stable_key == node_key,
    ))).scalar_one_or_none()
    if start is None:
        raise HTTPException(status_code=404, detail="Atlas node unavailable")
    # Test imports identify a source file; a symbol inherits only that file-level association.
    association_key = f"file:{start.path}" if start.path and start.kind in {"class", "function", "method", "interface", "test_case", "module"} else node_key
    try:
        result = await impact_from_db(session, organization_id, repository_id, snapshot_id, association_key,
                                      max_depth=3, max_results=100, kinds=frozenset({"IMPORTS", "TESTS"}))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"snapshot_id": str(snapshot_id), "association_key": association_key, "items": [asdict(item) for item in result.items
            if item.key.startswith("file:") and is_test_path(item.key.removeprefix("file:"))],
            "truncated": result.truncated, "coverage_claimed": False}


@router.get("/diff")
async def snapshot_diff(repository_id: UUID, left: UUID, right: UUID,
                        organization_id: OrganizationId = Depends(require_permission("repo:read")),
                        session: AsyncSession = Depends(get_session)):
    older = await _visible_snapshot(session, organization_id, repository_id, left)
    newer = await _visible_snapshot(session, organization_id, repository_id, right)
    if older.indexer_version != newer.indexer_version or older.parser_versions != newer.parser_versions:
        raise HTTPException(status_code=409, detail="Atlas snapshot parser versions are incompatible")
    if any(snapshot.stats.get("nodes", 0) > 10_000 or snapshot.stats.get("edges", 0) > 30_000
           for snapshot in (older, newer)):
        raise HTTPException(status_code=413, detail="Atlas comparison exceeds query budget")
    diff = compare_graphs(await get_graph(session, organization_id, repository_id, left),
                          await get_graph(session, organization_id, repository_id, right))
    return {"left": str(left), "right": str(right), **_bounded_diff(diff)}


@router.get("/nodes/{node_id}")
async def node_detail(repository_id: UUID, node_id: UUID,
                      organization_id: OrganizationId = Depends(require_permission("repo:read")),
                      session: AsyncSession = Depends(get_session)):
    await _visible_repository(session, organization_id, repository_id)
    node = (await session.execute(select(AtlasNodeModel).join(
        AtlasSnapshotModel, AtlasNodeModel.snapshot_id == AtlasSnapshotModel.id,
    ).where(AtlasNodeModel.id == node_id, AtlasNodeModel.organization_id == organization_id,
            AtlasNodeModel.repository_id == repository_id, AtlasSnapshotModel.status == "PUBLISHED"))).scalar_one_or_none()
    if node is None:
        raise HTTPException(status_code=404, detail="Atlas node unavailable")
    edges = (await session.execute(select(AtlasEdgeModel).where(
        AtlasEdgeModel.snapshot_id == node.snapshot_id, AtlasEdgeModel.organization_id == organization_id,
        AtlasEdgeModel.from_node_id == node.id,
    ).order_by(AtlasEdgeModel.id).limit(100))).scalars().all()
    keys = await _edge_keys(session, node.snapshot_id, edges)
    return {"snapshot_id": str(node.snapshot_id), "node": _node_document(node),
            "relationships": [_edge_document(edge, keys) for edge in edges]}
