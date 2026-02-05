"""Shared OpenAPI response definitions for RFC 7807 compliance.

This module provides reusable response definitions for API endpoints that
follow RFC 7807 Problem Details specification. These definitions ensure
consistent error schema exposure in OpenAPI documentation.
"""

from __future__ import annotations

from typing import Any

from chronovista.api.schemas.responses import (
    ProblemDetail,
    ValidationProblemDetail,
)

# Standard error responses for OpenAPI documentation
PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"

# Type alias for FastAPI responses parameter
ResponsesType = dict[int | str, dict[str, Any]]

# Common error responses
NOT_FOUND_RESPONSE: ResponsesType = {
    404: {
        "model": ProblemDetail,
        "description": "Resource not found",
        "content": {PROBLEM_JSON_MEDIA_TYPE: {}},
    }
}

BAD_REQUEST_RESPONSE: ResponsesType = {
    400: {
        "model": ProblemDetail,
        "description": "Bad request",
        "content": {PROBLEM_JSON_MEDIA_TYPE: {}},
    }
}

VALIDATION_ERROR_RESPONSE: ResponsesType = {
    422: {
        "model": ValidationProblemDetail,
        "description": "Validation error",
        "content": {PROBLEM_JSON_MEDIA_TYPE: {}},
    }
}

UNAUTHORIZED_RESPONSE: ResponsesType = {
    401: {
        "model": ProblemDetail,
        "description": "Authentication required",
        "content": {PROBLEM_JSON_MEDIA_TYPE: {}},
    }
}

CONFLICT_RESPONSE: ResponsesType = {
    409: {
        "model": ProblemDetail,
        "description": "Resource conflict",
        "content": {PROBLEM_JSON_MEDIA_TYPE: {}},
    }
}

INTERNAL_ERROR_RESPONSE: ResponsesType = {
    500: {
        "model": ProblemDetail,
        "description": "Internal server error",
        "content": {PROBLEM_JSON_MEDIA_TYPE: {}},
    }
}

# Combined response sets for common endpoint patterns

STANDARD_ERRORS: ResponsesType = {
    **VALIDATION_ERROR_RESPONSE,
    **UNAUTHORIZED_RESPONSE,
    **INTERNAL_ERROR_RESPONSE,
}
"""Standard errors for most endpoints (422, 401, 500)."""

GET_ITEM_ERRORS: ResponsesType = {
    **NOT_FOUND_RESPONSE,
    **VALIDATION_ERROR_RESPONSE,
    **UNAUTHORIZED_RESPONSE,
    **INTERNAL_ERROR_RESPONSE,
}
"""Errors for GET single item endpoints (404, 422, 401, 500)."""

LIST_ERRORS: ResponsesType = {
    **VALIDATION_ERROR_RESPONSE,
    **UNAUTHORIZED_RESPONSE,
    **INTERNAL_ERROR_RESPONSE,
}
"""Errors for GET list/collection endpoints (422, 401, 500)."""

CREATE_ERRORS: ResponsesType = {
    **BAD_REQUEST_RESPONSE,
    **VALIDATION_ERROR_RESPONSE,
    **UNAUTHORIZED_RESPONSE,
    **CONFLICT_RESPONSE,
    **INTERNAL_ERROR_RESPONSE,
}
"""Errors for POST create/action endpoints (400, 422, 401, 409, 500)."""

UPDATE_ERRORS: ResponsesType = {
    **NOT_FOUND_RESPONSE,
    **BAD_REQUEST_RESPONSE,
    **VALIDATION_ERROR_RESPONSE,
    **UNAUTHORIZED_RESPONSE,
    **CONFLICT_RESPONSE,
    **INTERNAL_ERROR_RESPONSE,
}
"""Errors for PUT/PATCH update endpoints (404, 400, 422, 401, 409, 500)."""

DELETE_ERRORS: ResponsesType = {
    **NOT_FOUND_RESPONSE,
    **VALIDATION_ERROR_RESPONSE,
    **UNAUTHORIZED_RESPONSE,
    **INTERNAL_ERROR_RESPONSE,
}
"""Errors for DELETE endpoints (404, 422, 401, 500)."""

# Health endpoint - no auth required, only internal errors
HEALTH_ERRORS: ResponsesType = {
    **INTERNAL_ERROR_RESPONSE,
}
"""Errors for health endpoint (500 only)."""
