from uuid import UUID

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from packages.shared.identifiers import OrganizationId


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # In a real environment, this extracts the tenant ID from the JWT token
        # or the X-Organization-ID header, validates against RoleBindingModel,
        # and injects it into the request state.

        # Mocking for architectural skeleton
        org_id_str = request.headers.get("X-Organization-ID", "00000000-0000-0000-0000-000000000000")
        try:
            org_id = OrganizationId(UUID(org_id_str))
            request.state.organization_id = org_id
        except ValueError:
            pass  # Handle invalid UUIDs properly in real code

        response = await call_next(request)
        return response
