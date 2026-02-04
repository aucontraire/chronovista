"""Centralized exception handlers for FastAPI.

This module provides centralized exception handling for the chronovista API,
converting domain exceptions to standardized ErrorResponse JSON format.

All API endpoints use these handlers to ensure consistent error response
structure across the entire API surface.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from chronovista.api.schemas.responses import ApiError, ErrorCode, ErrorResponse
from chronovista.exceptions import (
    APIError,
    AuthenticationError,
    RepositoryError,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handle APIError subclasses and convert to ErrorResponse JSON.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    exc : APIError
        The APIError exception that was raised.

    Returns
    -------
    JSONResponse
        JSON response with ErrorResponse format.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=exc.to_api_error()).model_dump(),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic RequestValidationError and convert to ErrorResponse JSON.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    exc : RequestValidationError
        The Pydantic validation error.

    Returns
    -------
    JSONResponse
        JSON response with ErrorResponse format and validation details.
    """
    # Format validation errors for the response
    errors = []
    for error in exc.errors():
        errors.append({
            "loc": list(error.get("loc", [])),
            "msg": error.get("msg", ""),
            "type": error.get("type", ""),
        })

    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error=ApiError(
                code=ErrorCode.VALIDATION_ERROR.value,
                message="Request validation failed",
                details={"errors": errors},
            )
        ).model_dump(),
    )


async def auth_error_handler(
    request: Request, exc: AuthenticationError
) -> JSONResponse:
    """Handle AuthenticationError and convert to ErrorResponse JSON.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    exc : AuthenticationError
        The authentication error.

    Returns
    -------
    JSONResponse
        JSON response with 401 status and ErrorResponse format.
    """
    return JSONResponse(
        status_code=401,
        content=ErrorResponse(
            error=ApiError(
                code=ErrorCode.NOT_AUTHENTICATED.value,
                message=str(exc),
            )
        ).model_dump(),
    )


async def repository_error_handler(
    request: Request, exc: RepositoryError
) -> JSONResponse:
    """Handle RepositoryError and convert to ErrorResponse JSON.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    exc : RepositoryError
        The repository/database error.

    Returns
    -------
    JSONResponse
        JSON response with 500 status and ErrorResponse format.
        Internal details are not exposed to the client.
    """
    # Log the actual error for debugging
    logger.error(
        "Repository error: %s (operation=%s, entity=%s)",
        exc.message,
        exc.operation,
        exc.entity_type,
        exc_info=exc.original_error,
    )

    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=ApiError(
                code=ErrorCode.DATABASE_ERROR.value,
                message="An internal database error occurred. Please try again.",
            )
        ).model_dump(),
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions and convert to ErrorResponse JSON.

    This is the catch-all handler for any unhandled exceptions.
    Internal error details are not exposed to the client for security.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    exc : Exception
        The unhandled exception.

    Returns
    -------
    JSONResponse
        JSON response with 500 status and generic error message.
    """
    # Log the full exception for debugging
    logger.exception("Unhandled exception: %s", exc)

    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=ApiError(
                code=ErrorCode.INTERNAL_ERROR.value,
                message="An unexpected error occurred. Please try again later.",
            )
        ).model_dump(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI app.

    This function registers handlers for:
    - APIError and its subclasses (NotFoundError, BadRequestError, etc.)
    - RequestValidationError (Pydantic validation)
    - AuthenticationError
    - RepositoryError
    - Generic Exception (catch-all)

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
    # Register APIError handler (handles all subclasses too)
    app.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]

    # Register Pydantic validation error handler
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]

    # Register authentication error handler
    app.add_exception_handler(AuthenticationError, auth_error_handler)  # type: ignore[arg-type]

    # Register repository error handler
    app.add_exception_handler(RepositoryError, repository_error_handler)  # type: ignore[arg-type]

    # Register generic catch-all handler
    app.add_exception_handler(Exception, generic_error_handler)
