from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    EXTERNAL_SERVICE = "external_service"
    INFRASTRUCTURE = "infrastructure"
    BUSINESS_LOGIC = "business_logic"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"


@dataclass(frozen=True)
class ForgeError(Exception):
    code: str
    message: str
    category: ErrorCategory
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    details: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ValidationError(ForgeError):
    pass


class AuthenticationError(ForgeError):
    pass


class AuthorizationError(ForgeError):
    pass


class NotFoundError(ForgeError):
    pass


class ConflictError(ForgeError):
    pass


class ExternalServiceError(ForgeError):
    pass


class InfrastructureError(ForgeError):
    pass


class TimeoutError(ForgeError):
    pass
