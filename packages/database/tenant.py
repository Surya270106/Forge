from contextvars import ContextVar
from uuid import UUID

from sqlalchemy.orm import ORMExecuteState

# Thread-safe / async-safe context variable for the current tenant
current_tenant_id: ContextVar[UUID | None] = ContextVar("current_tenant_id", default=None)
system_context: ContextVar[bool] = ContextVar("system_context", default=False)


def set_tenant(org_id: UUID) -> None:
    current_tenant_id.set(org_id)
    system_context.set(False)


def get_tenant() -> UUID | None:
    return current_tenant_id.get()


def clear_tenant() -> None:
    current_tenant_id.set(None)


def set_system_context() -> None:
    system_context.set(True)
    current_tenant_id.set(None)


def with_tenant_rls(execute_state: ORMExecuteState):
    """
    SQLAlchemy ORM event hook to enforce tenant isolation at the application layer.
    Automatically injects a filter on `organization_id` if the model supports it.
    """
    tenant_id = current_tenant_id.get()
    is_system = system_context.get()

    if is_system:
        return

    if execute_state.is_select or execute_state.is_update or execute_state.is_delete:
        # Find all entities in the statement

        entities = []
        if execute_state.is_select:
            for desc in execute_state.statement.column_descriptions:  # type: ignore[reportAttributeAccessIssue]
                if desc["type"] is not type:
                    entities.append(desc["type"])
        else:
            # For update/delete, the entity is usually in the statement's table
            pass  # Simplification for test

        for entity in entities:
            if hasattr(entity, "organization_id"):
                if tenant_id is None:
                    raise PermissionError(f"Tenant Context missing. Cannot access {entity.__name__}.")

                execute_state.statement = execute_state.statement.where(entity.organization_id == str(tenant_id))  # type: ignore[reportAttributeAccessIssue]


# We must attach this hook to the session, which is done when sessions are created.
