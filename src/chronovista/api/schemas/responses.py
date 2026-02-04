"""API response envelope schemas."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

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
