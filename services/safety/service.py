"""Tenant-scoped policy history and execution snapshots."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.auth import OrganizationModel
from packages.database.models.safety import SafetyPolicyModel
from packages.shared.identifiers import generate_id

from .policy import CAPABILITIES, PolicyState


def as_document(state: PolicyState) -> dict:
    return {"version": state.version, "denied": sorted(state.denied),
            "repository_denies": {key: sorted(value) for key, value in state.repository_denies.items()},
            "stopped": state.stopped}


def from_document(document: dict | None) -> PolicyState:
    if document is None:
        raise ValueError("Execution safety snapshot is missing")
    try:
        if not isinstance(document["denied"], list) or not isinstance(document["repository_denies"], dict):
            raise ValueError("Invalid policy document")
        return PolicyState(version=document["version"], denied=frozenset(document["denied"]),
                           repository_denies={key: frozenset(value) for key, value in document["repository_denies"].items()},
                           stopped=document["stopped"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Invalid policy document") from error


async def current_policy(session: AsyncSession, organization_id: UUID) -> PolicyState:
    row = (await session.execute(select(SafetyPolicyModel).where(
        SafetyPolicyModel.organization_id == organization_id,
    ).order_by(SafetyPolicyModel.version.desc()).limit(1))).scalar_one_or_none()
    if row is None:
        return PolicyState(version=0)
    return from_document({"version": row.version, "denied": row.denied,
                          "repository_denies": row.repository_denies, "stopped": row.stopped})


async def revise_policy(session: AsyncSession, organization_id: UUID, actor_id: UUID, *,
                        denied: list[str] | None = None, repository_denies: dict[str, list[str]] | None = None,
                        stopped: bool | None = None) -> PolicyState:
    organization = (await session.execute(select(OrganizationModel).where(
        OrganizationModel.id == organization_id,
    ).with_for_update())).scalar_one_or_none()
    if organization is None:
        raise ValueError("Organization unavailable")
    prior = await current_policy(session, organization_id)
    proposed = PolicyState(version=prior.version + 1,
                           denied=frozenset(denied) if denied is not None else prior.denied,
                           repository_denies={key: frozenset(value) for key, value in repository_denies.items()}
                           if repository_denies is not None else prior.repository_denies,
                           stopped=stopped if stopped is not None else prior.stopped)
    if not proposed.denied <= CAPABILITIES:
        raise ValueError("Unknown capability")
    session.add(SafetyPolicyModel(id=generate_id(), organization_id=organization_id, created_by=actor_id,
                                  version=proposed.version, denied=sorted(proposed.denied),
                                  repository_denies={key: sorted(value) for key, value in proposed.repository_denies.items()},
                                  stopped=proposed.stopped))
    await session.flush()
    return proposed
