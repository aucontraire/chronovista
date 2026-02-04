"""API response envelope schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict


class ErrorCode(str, Enum):
    """Standardized error codes for API responses.

    These codes provide machine-readable error identification for API consumers.
    Each code maps to a specific HTTP status code range.

    4xx Client Errors:
        NOT_FOUND: Resource does not exist (404)
        BAD_REQUEST: Invalid request parameters (400)
        VALIDATION_ERROR: Request validation failed (422)
        NOT_AUTHENTICATED: Authentication required (401)
        FORBIDDEN: Access denied (403)
        CONFLICT: Resource conflict (409)
        MUTUALLY_EXCLUSIVE: Conflicting parameters provided (400)

    5xx Server Errors:
        INTERNAL_ERROR: Unexpected server error (500)
        DATABASE_ERROR: Database operation failed (500)
        SERVICE_UNAVAILABLE: Service temporarily unavailable (503)
    """

    # 4xx Client Errors
    NOT_FOUND = "NOT_FOUND"
    BAD_REQUEST = "BAD_REQUEST"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    MUTUALLY_EXCLUSIVE = "MUTUALLY_EXCLUSIVE"

    # 5xx Server Errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"

T = TypeVar("T")


class PaginationMeta(BaseModel):
    """Pagination metadata for list responses."""

    model_config = ConfigDict(strict=True)

    total: int  # Total items matching query
    limit: int  # Items per page
    offset: int  # Current offset
    has_more: bool  # More items available (offset + limit < total)


class ApiError(BaseModel):
    """Standard error response."""

    model_config = ConfigDict(strict=True)

    code: str  # Machine-readable error code (e.g., NOT_FOUND, NOT_AUTHENTICATED)
    message: str  # Human-readable message
    details: dict[str, Any] | None = None


class ApiResponse(BaseModel, Generic[T]):
    """Standard API response wrapper."""

    model_config = ConfigDict(strict=True)

    data: T
    pagination: PaginationMeta | None = None


class ErrorResponse(BaseModel):
    """Standard error response wrapper."""

    model_config = ConfigDict(strict=True)

    error: ApiError
