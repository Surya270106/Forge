from enum import Enum


class Action(str, Enum):
    # Repository
    REPO_IMPORT = "repo:import"
    REPO_READ = "repo:read"
    REPO_DELETE = "repo:delete"

    # Planning
    PLAN_CREATE = "plan:create"
    PLAN_READ = "plan:read"
    PLAN_APPROVE = "plan:approve"

    # Patch
    PATCH_READ = "patch:read"
    PATCH_APPROVE = "patch:approve"
    PATCH_REJECT = "patch:reject"

    # Execution
    EXEC_READ = "exec:read"
    EXEC_CANCEL = "exec:cancel"

    # Workspace
    WORKSPACE_SETTINGS_READ = "workspace:settings:read"
    WORKSPACE_SETTINGS_WRITE = "workspace:settings:write"


class Role(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    VIEWER = "VIEWER"


# Centralized RBAC catalogue
ROLE_PERMISSIONS: dict[str, set[Action]] = {
    Role.OWNER: set(Action),  # Owners get all permissions
    Role.ADMIN: {
        Action.REPO_IMPORT,
        Action.REPO_READ,
        Action.PLAN_CREATE,
        Action.PLAN_READ,
        Action.PLAN_APPROVE,
        Action.PATCH_READ,
        Action.PATCH_APPROVE,
        Action.PATCH_REJECT,
        Action.EXEC_READ,
        Action.EXEC_CANCEL,
        Action.WORKSPACE_SETTINGS_READ,
    },
    Role.VIEWER: {
        Action.REPO_READ,
        Action.PLAN_READ,
        Action.PATCH_READ,
        Action.EXEC_READ,
    },
}


def has_permission(role: str, action: str) -> bool:
    if role not in ROLE_PERMISSIONS:
        return False
    # Validate action string maps to Action enum
    try:
        action_enum = Action(action)
    except ValueError:
        return False
        
    return action_enum in ROLE_PERMISSIONS[role]
