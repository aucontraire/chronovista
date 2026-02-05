"""Request ID middleware for request correlation and tracing.

This module provides async-safe request ID propagation using contextvars,
allowing request IDs to be accessed from anywhere in the async call stack
(logging, exception handlers, etc.) without passing the request object.

The middleware extracts X-Request-ID from incoming requests or generates
a new UUID v4 if not provided. The request ID is then:
1. Set in contextvars for async-safe access
2. Stored in request.state for direct access
3. Added to response headers for client correlation
"""

from __future__ import annotations

import contextvars
import logging
import time
import uuid
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint

logger = logging.getLogger(__name__)

# Maximum length for request ID header values
MAX_REQUEST_ID_LENGTH = 128

# Header name for request ID (case-insensitive per HTTP spec)
REQUEST_ID_HEADER = "X-Request-ID"

# Context variable for async-safe request ID propagation
# Default empty string indicates no request ID is set
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)


def get_request_id() -> str:
    """Get the current request ID from context.

    Returns the request ID set by RequestIdMiddleware for the current
    async context. Returns empty string if no request ID is set (e.g.,
    when called outside of a request context).

    Returns
    -------
    str
        The current request ID, or empty string if not set.

    Examples
    --------
    >>> from chronovista.api.middleware.request_id import get_request_id
    >>> # Inside a request context:
    >>> request_id = get_request_id()
    >>> logger.info("Processing request", extra={"request_id": request_id})
    """
    return request_id_var.get()


def _generate_request_id() -> str:
    """Generate a new request ID using UUID v4.

    Falls back to timestamp-based ID if UUID generation fails
    (extremely rare, typically only in resource-exhausted scenarios).

    Returns
    -------
    str
        A new unique request ID.
    """
    try:
        return str(uuid.uuid4())
    except Exception:
        # Fallback for extremely rare UUID generation failures
        fallback_id = f"fallback-{int(time.time() * 1000)}"
        logger.warning(
            "UUID generation failed, using fallback: %s",
            fallback_id,
        )
        return fallback_id


def _is_valid_request_id(value: str) -> bool:
    """Check if a request ID value contains only valid ASCII printable characters.

    Valid characters are ASCII printable characters (code points 33-126),
    which excludes control characters and extended ASCII.

    Parameters
    ----------
    value : str
        The request ID value to validate.

    Returns
    -------
    bool
        True if all characters are ASCII printable (33-126), False otherwise.
    """
    return all(33 <= ord(c) <= 126 for c in value)


def _sanitize_request_id(header_value: str | None) -> str:
    """Sanitize and validate a request ID header value.

    Applies the following rules:
    - None or empty string: generate new UUID v4
    - Non-ASCII-printable chars (outside 33-126): reject, generate new UUID, log WARNING
    - >128 chars: truncate from END (preserve prefix)
    - Valid 1-128 chars: return unchanged

    Parameters
    ----------
    header_value : str | None
        The raw X-Request-ID header value.

    Returns
    -------
    str
        A valid request ID (either sanitized input or newly generated).
    """
    # Empty or missing: generate new
    if not header_value:
        return _generate_request_id()

    # Check for invalid characters
    if not _is_valid_request_id(header_value):
        logger.warning(
            "X-Request-ID contains non-ASCII-printable characters, generating new ID"
        )
        return _generate_request_id()

    # Truncate if too long (preserve prefix)
    if len(header_value) > MAX_REQUEST_ID_LENGTH:
        truncated = header_value[:MAX_REQUEST_ID_LENGTH]
        logger.debug(
            "X-Request-ID truncated from %d to %d characters",
            len(header_value),
            MAX_REQUEST_ID_LENGTH,
        )
        return truncated

    return header_value


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware that manages request ID propagation for correlation and tracing.

    This middleware:
    1. Extracts X-Request-ID from incoming request headers
    2. Validates and sanitizes the header value
    3. Generates a new UUID v4 if header is missing/invalid
    4. Sets the request ID in contextvars for async-safe access
    5. Stores in request.state.request_id for direct access
    6. Adds X-Request-ID to response headers

    The middleware should be registered early in the middleware chain
    to ensure request ID is available throughout request processing.

    Examples
    --------
    >>> from fastapi import FastAPI
    >>> from chronovista.api.middleware import RequestIdMiddleware
    >>> app = FastAPI()
    >>> app.add_middleware(RequestIdMiddleware)
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process request with request ID propagation.

        Parameters
        ----------
        request : Request
            The incoming HTTP request.
        call_next : RequestResponseEndpoint
            The next middleware or route handler.

        Returns
        -------
        Response
            The HTTP response with X-Request-ID header.
        """
        # Extract and sanitize request ID from header (case-insensitive)
        raw_request_id = request.headers.get(REQUEST_ID_HEADER)
        request_id = _sanitize_request_id(raw_request_id)

        # Set in contextvars for async-safe propagation
        token = request_id_var.set(request_id)

        try:
            # Store in request.state for direct access
            request.state.request_id = request_id

            # Process request
            response = await call_next(request)

            # Add request ID to response headers
            response.headers[REQUEST_ID_HEADER] = request_id

            return response
        finally:
            # Reset context variable to prevent leaking to other requests
            request_id_var.reset(token)


class RequestIdFilter(logging.Filter):
    """Logging filter that adds request_id to all log records.

    This filter uses the request_id_var context variable to add
    the current request ID to log records. If no request ID is set,
    "-" is used as a placeholder.

    This allows log formatters to include %(request_id)s in their
    format string without explicit passing of request context.

    Examples
    --------
    >>> import logging
    >>> from chronovista.api.middleware import RequestIdFilter
    >>> handler = logging.StreamHandler()
    >>> handler.addFilter(RequestIdFilter())
    >>> handler.setFormatter(logging.Formatter(
    ...     "%(levelname)s [%(request_id)s] %(message)s"
    ... ))
    >>> logger = logging.getLogger("my_logger")
    >>> logger.addHandler(handler)
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Add request_id attribute to the log record.

        Parameters
        ----------
        record : logging.LogRecord
            The log record to modify.

        Returns
        -------
        bool
            Always returns True to allow the record to be logged.
        """
        record.request_id = request_id_var.get() or "-"
        return True
