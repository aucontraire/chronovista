"""Centralized exception handlers for FastAPI with RFC 7807 compliance.

This module provides centralized exception handling for the chronovista API,
converting domain exceptions to RFC 7807 Problem Details format for standardized
error responses.

All API endpoints use these handlers to ensure consistent RFC 7807 compliant
error response structure across the entire API surface.

RFC 7807 Reference: https://tools.ietf.org/html/rfc7807
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from chronovista.api.middleware.request_id import get_request_id
from chronovista.api.schemas.responses import (
    ERROR_TITLES,
    ErrorCode,
    FieldError,
    ProblemDetail,
    ProblemJSONResponse,
    ValidationProblemDetail,
    get_error_type_uri,
)
from chronovista.exceptions import (
    APIError,
    AuthenticationError,
    AuthorizationError,
    ExternalServiceError,
    RateLimitError,
    RepositoryError,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# =============================================================================
# Constants for Detail Message Truncation (T051)
# =============================================================================

MAX_DETAIL_LENGTH = 4096
"""Maximum allowed length for detail messages before truncation."""

TRUNCATION_SUFFIX = "... (truncated)"
"""Suffix appended to truncated detail messages."""


# =============================================================================
# Helper Functions
# =============================================================================


def _truncate_detail(detail: str) -> str:
    """Truncate detail message if it exceeds maximum length.

    Parameters
    ----------
    detail : str
        The detail message to potentially truncate.

    Returns
    -------
    str
        The original message if within limits, or truncated with suffix.
    """
    if len(detail) <= MAX_DETAIL_LENGTH:
        return detail
    # Account for suffix length when truncating
    truncate_at = MAX_DETAIL_LENGTH - len(TRUNCATION_SUFFIX)
    return detail[:truncate_at] + TRUNCATION_SUFFIX


def _get_request_id_with_fallback(request: Request | None = None) -> str:
    """Get request ID from context variable with request.state fallback.

    Parameters
    ----------
    request : Request | None, optional
        The FastAPI request object for fallback (default: None).

    Returns
    -------
    str
        The request ID, or "-" if not available.
    """
    # First try context variable (set by middleware)
    request_id = get_request_id()
    if request_id:
        return request_id

    # Fallback to request.state if available (for testing/edge cases)
    if request is not None:
        try:
            state_request_id = getattr(request.state, "request_id", None)
            if state_request_id:
                return str(state_request_id)
        except Exception:
            pass

    return "-"


def _create_problem_detail(
    code: ErrorCode,
    status: int,
    detail: str,
    instance: str,
    request: Request | None = None,
) -> ProblemDetail:
    """Create a ProblemDetail instance with request_id from context.

    Parameters
    ----------
    code : ErrorCode
        The error code for the problem.
    status : int
        HTTP status code for the response.
    detail : str
        Human-readable explanation of the problem.
    instance : str
        URI reference of the specific occurrence.
    request : Request | None, optional
        The FastAPI request for fallback request_id retrieval.

    Returns
    -------
    ProblemDetail
        A fully populated ProblemDetail instance.
    """
    return ProblemDetail(
        type=get_error_type_uri(code),
        title=ERROR_TITLES.get(code, "Error"),
        status=status,
        detail=_truncate_detail(detail),
        instance=instance,
        code=code.value,
        request_id=_get_request_id_with_fallback(request),
    )


def _safe_problem_response(
    code: ErrorCode,
    status: int,
    detail: str,
    instance: str,
    headers: dict[str, str] | None = None,
    request: Request | None = None,
) -> ProblemJSONResponse:
    """Create ProblemJSONResponse with meta-error fallback (T052).

    Attempts to create a proper RFC 7807 response. If serialization fails,
    returns a minimal hardcoded RFC 7807 response to ensure the client
    always receives a valid error response.

    Parameters
    ----------
    code : ErrorCode
        The error code for the problem.
    status : int
        HTTP status code for the response.
    detail : str
        Human-readable explanation of the problem.
    instance : str
        URI reference of the specific occurrence.
    headers : dict[str, str] | None, optional
        Additional headers to include in the response.
    request : Request | None, optional
        The FastAPI request for fallback request_id retrieval.

    Returns
    -------
    ProblemJSONResponse
        RFC 7807 compliant JSON response.
    """
    try:
        problem = _create_problem_detail(code, status, detail, instance, request)
        return ProblemJSONResponse(
            content=problem.model_dump(),
            status_code=status,
            headers=headers,
        )
    except Exception as e:
        logger.error("Error serializing error response: %s", e, exc_info=True)
        # Hardcoded minimal RFC 7807 response for meta-error handling
        return ProblemJSONResponse(
            content={
                "type": "https://api.chronovista.com/errors/INTERNAL_ERROR",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "An unexpected error occurred",
                "instance": instance,
                "code": "INTERNAL_ERROR",
                "request_id": _get_request_id_with_fallback(request),
            },
            status_code=500,
        )


# =============================================================================
# Exception Handlers
# =============================================================================


async def api_error_handler(request: Request, exc: APIError) -> ProblemJSONResponse:
    """Handle APIError subclasses and convert to RFC 7807 Problem Detail.

    This handler processes all APIError subclasses including:
    - NotFoundError (404)
    - BadRequestError (400)
    - ConflictError (409)
    - AuthorizationError (403)
    - RateLimitError (429)
    - ExternalServiceError (502)

    For ExternalServiceError, the detail is replaced with a generic message
    and the internal error is logged.

    For RateLimitError, the Retry-After header is added if retry_after is set.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    exc : APIError
        The APIError exception that was raised.

    Returns
    -------
    ProblemJSONResponse
        RFC 7807 compliant JSON response with appropriate status code.
    """
    instance = str(request.url.path)
    headers: dict[str, str] | None = None

    # Handle RateLimitError - add Retry-After header (T046)
    if isinstance(exc, RateLimitError) and exc.retry_after is not None:
        headers = {"Retry-After": str(exc.retry_after)}

    # Handle ExternalServiceError - use generic detail, log internal (T048)
    if isinstance(exc, ExternalServiceError):
        logger.error(
            "External service error: %s (details=%s)",
            exc.message,
            exc.details,
            exc_info=True,
        )
        return _safe_problem_response(
            code=exc.error_code,
            status=exc.status_code,
            detail="External service unavailable",
            instance=instance,
            headers=headers,
            request=request,
        )

    # Standard APIError handling - use exception's message directly
    return _safe_problem_response(
        code=exc.error_code,
        status=exc.status_code,
        detail=exc.message,
        instance=instance,
        headers=headers,
        request=request,
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> ProblemJSONResponse:
    """Handle Pydantic RequestValidationError and convert to RFC 7807 format.

    Creates a ValidationProblemDetail with an array of FieldError instances
    preserving Pydantic's field order and allowing multiple errors per field.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    exc : RequestValidationError
        The Pydantic validation error.

    Returns
    -------
    ProblemJSONResponse
        RFC 7807 compliant JSON response with status 422 and errors array.
    """
    instance = str(request.url.path)

    try:
        # Build the errors array from Pydantic validation errors
        errors = [
            FieldError(
                loc=list(error.get("loc", [])),
                msg=error.get("msg", ""),
                type=error.get("type", ""),
            )
            for error in exc.errors()
        ]

        validation_problem = ValidationProblemDetail(
            type=get_error_type_uri(ErrorCode.VALIDATION_ERROR),
            title=ERROR_TITLES[ErrorCode.VALIDATION_ERROR],
            status=422,
            detail="Request validation failed",
            instance=instance,
            code=ErrorCode.VALIDATION_ERROR.value,
            request_id=_get_request_id_with_fallback(request),
            errors=errors,
        )

        return ProblemJSONResponse(
            content=validation_problem.model_dump(),
            status_code=422,
        )
    except Exception as e:
        logger.error("Error serializing validation error response: %s", e, exc_info=True)
        # Fallback to minimal RFC 7807 response
        return ProblemJSONResponse(
            content={
                "type": "https://api.chronovista.com/errors/VALIDATION_ERROR",
                "title": "Validation Error",
                "status": 422,
                "detail": "Request validation failed",
                "instance": instance,
                "code": "VALIDATION_ERROR",
                "request_id": _get_request_id_with_fallback(request),
                "errors": [],
            },
            status_code=422,
        )


async def auth_error_handler(
    request: Request, exc: AuthenticationError
) -> ProblemJSONResponse:
    """Handle AuthenticationError and convert to RFC 7807 Problem Detail.

    Preserves WWW-Authenticate header from the exception if present.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    exc : AuthenticationError
        The authentication error.

    Returns
    -------
    ProblemJSONResponse
        RFC 7807 compliant JSON response with 401 status.
    """
    instance = str(request.url.path)
    headers: dict[str, str] | None = None

    # Preserve WWW-Authenticate header if present on exception (T044)
    if hasattr(exc, "www_authenticate") and exc.www_authenticate:
        headers = {"WWW-Authenticate": exc.www_authenticate}

    return _safe_problem_response(
        code=ErrorCode.NOT_AUTHENTICATED,
        status=401,
        detail=exc.message,
        instance=instance,
        headers=headers,
        request=request,
    )


async def authorization_error_handler(
    request: Request, exc: AuthorizationError
) -> ProblemJSONResponse:
    """Handle AuthorizationError and convert to RFC 7807 Problem Detail.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    exc : AuthorizationError
        The authorization error.

    Returns
    -------
    ProblemJSONResponse
        RFC 7807 compliant JSON response with 403 status.
    """
    instance = str(request.url.path)

    return _safe_problem_response(
        code=ErrorCode.NOT_AUTHORIZED,
        status=403,
        detail=exc.message,
        instance=instance,
        request=request,
    )


async def rate_limit_error_handler(
    request: Request, exc: RateLimitError
) -> ProblemJSONResponse:
    """Handle RateLimitError and convert to RFC 7807 Problem Detail.

    Includes Retry-After header if retry_after is set on the exception.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    exc : RateLimitError
        The rate limit error.

    Returns
    -------
    ProblemJSONResponse
        RFC 7807 compliant JSON response with 429 status and Retry-After header.
    """
    instance = str(request.url.path)
    headers: dict[str, str] | None = None

    # Add Retry-After header if retry_after is set (T046)
    if exc.retry_after is not None:
        headers = {"Retry-After": str(exc.retry_after)}

    return _safe_problem_response(
        code=ErrorCode.RATE_LIMITED,
        status=429,
        detail=exc.message,
        instance=instance,
        headers=headers,
        request=request,
    )


async def external_service_error_handler(
    request: Request, exc: ExternalServiceError
) -> ProblemJSONResponse:
    """Handle ExternalServiceError and convert to RFC 7807 Problem Detail.

    Uses a generic detail message to avoid exposing internal service details.
    The internal error is logged for debugging.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    exc : ExternalServiceError
        The external service error.

    Returns
    -------
    ProblemJSONResponse
        RFC 7807 compliant JSON response with 502 status and generic detail.
    """
    instance = str(request.url.path)

    # Log the actual error for debugging (T048)
    logger.error(
        "External service error: %s (details=%s)",
        exc.message,
        exc.details,
        exc_info=True,
    )

    return _safe_problem_response(
        code=ErrorCode.EXTERNAL_SERVICE_ERROR,
        status=502,
        detail="External service unavailable",
        instance=instance,
        request=request,
    )


async def repository_error_handler(
    request: Request, exc: RepositoryError
) -> ProblemJSONResponse:
    """Handle RepositoryError and convert to RFC 7807 Problem Detail.

    Uses a generic detail message to avoid exposing database implementation
    details. The internal error is logged for debugging.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    exc : RepositoryError
        The repository/database error.

    Returns
    -------
    ProblemJSONResponse
        RFC 7807 compliant JSON response with 500 status and generic detail.
    """
    instance = str(request.url.path)

    # Log the actual error for debugging (T047)
    logger.error(
        "Repository error: %s (operation=%s, entity=%s)",
        exc.message,
        exc.operation,
        exc.entity_type,
        exc_info=exc.original_error,
    )

    return _safe_problem_response(
        code=ErrorCode.DATABASE_ERROR,
        status=500,
        detail="A database error occurred",
        instance=instance,
        request=request,
    )


async def generic_error_handler(
    request: Request, exc: Exception
) -> ProblemJSONResponse:
    """Handle unexpected exceptions and convert to RFC 7807 Problem Detail.

    This is the catch-all handler for any unhandled exceptions.
    Internal error details are not exposed to the client for security.
    Full stack trace is logged for debugging.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    exc : Exception
        The unhandled exception.

    Returns
    -------
    ProblemJSONResponse
        RFC 7807 compliant JSON response with 500 status and generic message.
    """
    instance = str(request.url.path)

    # Log the full exception with stack trace for debugging (T049)
    logger.exception("Unhandled exception: %s", exc)

    return _safe_problem_response(
        code=ErrorCode.INTERNAL_ERROR,
        status=500,
        detail="An unexpected error occurred",
        instance=instance,
        request=request,
    )


# =============================================================================
# Handler Registration
# =============================================================================


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI app.

    This function registers handlers for:
    - APIError and its subclasses (NotFoundError, BadRequestError, ConflictError,
      AuthorizationError, RateLimitError, ExternalServiceError)
    - RequestValidationError (Pydantic validation)
    - AuthenticationError
    - AuthorizationError (separate handler)
    - RateLimitError (separate handler)
    - ExternalServiceError (separate handler)
    - RepositoryError
    - Generic Exception (catch-all)

    All handlers return RFC 7807 Problem Detail format responses.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.

    Examples
    --------
    >>> from fastapi import FastAPI
    >>> from chronovista.api.exception_handlers import register_exception_handlers
    >>> app = FastAPI()
    >>> register_exception_handlers(app)
    """
    # Register APIError handler (handles all APIError subclasses including
    # NotFoundError, BadRequestError, ConflictError, AuthorizationError,
    # RateLimitError, ExternalServiceError) (T042, T045, T046, T048)
    app.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]

    # Register Pydantic validation error handler (T043)
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]

    # Register authentication error handler (T044)
    app.add_exception_handler(AuthenticationError, auth_error_handler)  # type: ignore[arg-type]

    # Register repository error handler (T047)
    app.add_exception_handler(RepositoryError, repository_error_handler)  # type: ignore[arg-type]

    # Register generic catch-all handler (T049)
    app.add_exception_handler(Exception, generic_error_handler)
