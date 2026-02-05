"""API response envelope schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse


class ErrorCode(str, Enum):
    """Standardized error codes for API responses.

    These codes provide machine-readable error identification for API consumers.
    Each code maps to a specific HTTP status code range.

    4xx Client Errors:
        NOT_FOUND: Resource does not exist (404)
        BAD_REQUEST: Invalid request parameters (400)
        VALIDATION_ERROR: Request validation failed (422)
        NOT_AUTHENTICATED: Authentication required (401)
        NOT_AUTHORIZED: Access denied - insufficient permissions (403)
        FORBIDDEN: Access denied (403)
        CONFLICT: Resource conflict (409)
        MUTUALLY_EXCLUSIVE: Conflicting parameters provided (400)
        RATE_LIMITED: Too many requests (429)

    5xx Server Errors:
        INTERNAL_ERROR: Unexpected server error (500)
        DATABASE_ERROR: Database operation failed (500)
        EXTERNAL_SERVICE_ERROR: External service unavailable (502)
        SERVICE_UNAVAILABLE: Service temporarily unavailable (503)
    """

    # 4xx Client Errors
    NOT_FOUND = "NOT_FOUND"
    BAD_REQUEST = "BAD_REQUEST"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    MUTUALLY_EXCLUSIVE = "MUTUALLY_EXCLUSIVE"
    RATE_LIMITED = "RATE_LIMITED"

    # 5xx Server Errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


# RFC 7807 Constants and Utilities
ERROR_TYPE_BASE: str = "https://api.chronovista.com/errors"
"""Base URI for constructing RFC 7807 type URIs."""


def get_error_type_uri(code: ErrorCode) -> str:
    """Generate RFC 7807 type URI from error code.

    Parameters
    ----------
    code : ErrorCode
        The error code to generate a URI for.

    Returns
    -------
    str
        The full RFC 7807 type URI for the error code.

    Examples
    --------
    >>> get_error_type_uri(ErrorCode.NOT_FOUND)
    'https://api.chronovista.com/errors/NOT_FOUND'
    """
    return f"{ERROR_TYPE_BASE}/{code.value}"


# RFC 7807 Error Title Mapping
ERROR_TITLES: dict[ErrorCode, str] = {
    ErrorCode.NOT_FOUND: "Resource Not Found",
    ErrorCode.BAD_REQUEST: "Bad Request",
    ErrorCode.VALIDATION_ERROR: "Validation Error",
    ErrorCode.NOT_AUTHENTICATED: "Authentication Required",
    ErrorCode.NOT_AUTHORIZED: "Access Denied",
    ErrorCode.FORBIDDEN: "Access Denied",
    ErrorCode.CONFLICT: "Resource Conflict",
    ErrorCode.MUTUALLY_EXCLUSIVE: "Mutually Exclusive Parameters",
    ErrorCode.RATE_LIMITED: "Rate Limit Exceeded",
    ErrorCode.INTERNAL_ERROR: "Internal Server Error",
    ErrorCode.DATABASE_ERROR: "Database Error",
    ErrorCode.EXTERNAL_SERVICE_ERROR: "External Service Error",
    ErrorCode.SERVICE_UNAVAILABLE: "Service Unavailable",
}
"""Mapping from ErrorCode to human-readable RFC 7807 title."""

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


# RFC 7807 Problem Details Models


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details response for API errors.

    This model implements the Problem Details for HTTP APIs specification (RFC 7807),
    providing a standardized format for error responses with machine-readable fields.

    Attributes
    ----------
    type : str
        URI identifying the problem type.
    title : str
        Short human-readable summary of the problem type.
    status : int
        HTTP status code (4xx or 5xx).
    detail : str
        Human-readable explanation of the specific problem occurrence.
    instance : str
        URI reference of the specific occurrence.
    code : str
        Application-specific error code from ErrorCode enum.
    request_id : str
        Unique request identifier for correlation and debugging.
    """

    type: str = Field(
        ...,
        description="URI identifying the problem type",
        examples=["https://api.chronovista.com/errors/NOT_FOUND"],
    )
    title: str = Field(
        ...,
        description="Short human-readable summary",
        examples=["Resource Not Found"],
    )
    status: int = Field(
        ...,
        ge=400,
        le=599,
        description="HTTP status code",
        examples=[404],
    )
    detail: str = Field(
        ...,
        description="Human-readable explanation of the problem",
        examples=["Video 'xyz123' not found"],
    )
    instance: str = Field(
        ...,
        description="URI reference of the specific occurrence",
        examples=["/api/v1/videos/xyz123"],
    )
    code: str = Field(
        ...,
        description="Application-specific error code",
        examples=["NOT_FOUND"],
    )
    request_id: str = Field(
        ...,
        description="Unique request identifier for correlation",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "https://api.chronovista.com/errors/NOT_FOUND",
                "title": "Resource Not Found",
                "status": 404,
                "detail": "Video 'xyz123' not found",
                "instance": "/api/v1/videos/xyz123",
                "code": "NOT_FOUND",
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        }
    )


class FieldError(BaseModel):
    """Individual field validation error for RFC 7807 validation responses.

    This model represents a single field-level validation error, typically used
    within ValidationProblemDetail to provide detailed information about which
    fields failed validation and why.

    Attributes
    ----------
    loc : list[str | int]
        Location of the error as a field path (e.g., ["query", "limit"]).
    msg : str
        Human-readable error message.
    type : str
        Error type identifier (e.g., "value_error.number.not_le").
    """

    loc: list[str | int] = Field(
        ...,
        description="Location of the error (field path)",
        examples=[["query", "limit"]],
    )
    msg: str = Field(
        ...,
        description="Error message",
        examples=["ensure this value is less than or equal to 100"],
    )
    type: str = Field(
        ...,
        description="Error type identifier",
        examples=["value_error.number.not_le"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "loc": ["query", "limit"],
                "msg": "ensure this value is less than or equal to 100",
                "type": "value_error.number.not_le",
            }
        }
    )


class ValidationProblemDetail(ProblemDetail):
    """RFC 7807 Problem Details with validation errors for 422 responses.

    Extends ProblemDetail with an array of field-level validation errors,
    providing detailed information about which fields failed validation.

    Attributes
    ----------
    errors : list[FieldError]
        List of field-level validation errors.
    """

    errors: list[FieldError] = Field(
        ...,
        description="List of field-level validation errors",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "https://api.chronovista.com/errors/VALIDATION_ERROR",
                "title": "Validation Error",
                "status": 422,
                "detail": "Request validation failed",
                "instance": "/api/v1/videos",
                "code": "VALIDATION_ERROR",
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
                "errors": [
                    {
                        "loc": ["query", "limit"],
                        "msg": "ensure this value is less than or equal to 100",
                        "type": "value_error.number.not_le",
                    }
                ],
            }
        }
    )


class ProblemJSONResponse(JSONResponse):
    """FastAPI JSONResponse subclass for RFC 7807 Problem Details.

    This response class sets the appropriate media type for RFC 7807
    compliant error responses (application/problem+json).

    Examples
    --------
    >>> from fastapi import FastAPI
    >>> app = FastAPI()
    >>> @app.exception_handler(HTTPException)
    ... async def http_exception_handler(request, exc):
    ...     return ProblemJSONResponse(
    ...         status_code=exc.status_code,
    ...         content=problem_detail.model_dump(),
    ...     )
    """

    media_type = "application/problem+json"
