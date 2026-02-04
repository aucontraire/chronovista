"""Unit tests for API exception handlers.

Tests centralized exception handling for FastAPI endpoints,
ensuring all exception types return correct HTTP status codes
and ErrorResponse format.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from chronovista.api.exception_handlers import (
    api_error_handler,
    auth_error_handler,
    generic_error_handler,
    register_exception_handlers,
    repository_error_handler,
    validation_error_handler,
)
from chronovista.api.schemas.responses import ErrorCode
from chronovista.exceptions import (
    APIError,
    APIValidationError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    RepositoryError,
)

# Mark all tests as async
pytestmark = pytest.mark.asyncio


class TestNotFoundError:
    """Tests for NotFoundError exception handling."""

    async def test_not_found_error_returns_404(self) -> None:
        """Test NotFoundError returns 404 with correct format."""
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/test")
        async def raise_not_found() -> None:
            raise NotFoundError(
                resource_type="Channel",
                identifier="UCxyz123456789",
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "NOT_FOUND"
        assert "Channel" in data["error"]["message"]
        assert "UCxyz123456789" in data["error"]["message"]
        assert data["error"]["details"]["resource_type"] == "Channel"
        assert data["error"]["details"]["identifier"] == "UCxyz123456789"

    async def test_not_found_error_with_hint(self) -> None:
        """Test NotFoundError includes hint in message."""
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/test")
        async def raise_not_found() -> None:
            raise NotFoundError(
                resource_type="Channel",
                identifier="UCxyz123456789",
                hint="Verify the channel ID or run a sync.",
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 404
        data = response.json()
        assert "Verify the channel ID" in data["error"]["message"]


class TestBadRequestError:
    """Tests for BadRequestError exception handling."""

    async def test_bad_request_error_returns_400(self) -> None:
        """Test BadRequestError returns 400 with correct format."""
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/test")
        async def raise_bad_request() -> None:
            raise BadRequestError(
                message="Invalid parameter value",
                details={"field": "limit", "reason": "Must be positive"},
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "BAD_REQUEST"
        assert data["error"]["message"] == "Invalid parameter value"
        assert data["error"]["details"]["field"] == "limit"

    async def test_mutually_exclusive_error_returns_400(self) -> None:
        """Test BadRequestError with mutually_exclusive flag uses correct code."""
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/test")
        async def raise_mutually_exclusive() -> None:
            raise BadRequestError(
                message="Cannot specify both linked=true and unlinked=true",
                details={"field": "linked,unlinked", "constraint": "mutually_exclusive"},
                mutually_exclusive=True,
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "MUTUALLY_EXCLUSIVE"


class TestAPIValidationError:
    """Tests for APIValidationError exception handling."""

    async def test_api_validation_error_returns_422(self) -> None:
        """Test APIValidationError returns 422 with correct format."""
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/test")
        async def raise_validation_error() -> None:
            raise APIValidationError(
                message="Request validation failed",
                details={"errors": [{"loc": ["body", "title"], "msg": "field required"}]},
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"


class TestConflictError:
    """Tests for ConflictError exception handling."""

    async def test_conflict_error_returns_409(self) -> None:
        """Test ConflictError returns 409 with correct format."""
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/test")
        async def raise_conflict() -> None:
            raise ConflictError(
                message="Resource already exists",
                details={"channel_id": "UCxyz123456789"},
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "CONFLICT"
        assert data["error"]["message"] == "Resource already exists"


class TestAuthenticationError:
    """Tests for AuthenticationError exception handling."""

    async def test_auth_error_returns_401(self) -> None:
        """Test AuthenticationError returns 401 with correct format."""
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/test")
        async def raise_auth_error() -> None:
            raise AuthenticationError(message="Invalid or expired token")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 401
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "NOT_AUTHENTICATED"
        assert data["error"]["message"] == "Invalid or expired token"


class TestRepositoryError:
    """Tests for RepositoryError exception handling."""

    async def test_repository_error_returns_500(self) -> None:
        """Test RepositoryError returns 500 without exposing internal details."""
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/test")
        async def raise_repo_error() -> None:
            raise RepositoryError(
                message="Database connection failed",
                operation="insert",
                entity_type="Video",
                original_error=ValueError("sensitive error details"),
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "DATABASE_ERROR"
        # Should not expose internal details
        assert "Database connection failed" not in data["error"]["message"]
        assert "sensitive error details" not in data["error"]["message"]
        assert "An internal database error" in data["error"]["message"]


class TestPydanticValidationError:
    """Tests for Pydantic RequestValidationError handling."""

    async def test_pydantic_validation_error_returns_422(self) -> None:
        """Test Pydantic validation errors return 422 with field details."""
        app = FastAPI()
        register_exception_handlers(app)

        class RequestBody(BaseModel):
            title: str = Field(..., min_length=1)
            count: int = Field(..., ge=0)

        @app.post("/test")
        async def validate_body(body: RequestBody) -> dict[str, str]:
            return {"status": "ok"}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Send invalid data
            response = await client.post("/test", json={"title": "", "count": -1})

        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "errors" in data["error"]["details"]
        assert len(data["error"]["details"]["errors"]) > 0


class TestGenericExceptionHandler:
    """Tests for generic exception handling."""

    async def test_generic_error_returns_500(self) -> None:
        """Test generic exceptions return 500 without exposing details."""
        # Debug must be False for exception handlers to catch generic exceptions
        app = FastAPI(debug=False)
        register_exception_handlers(app)

        @app.get("/test")
        async def raise_generic_error() -> None:
            raise RuntimeError("Internal implementation detail")

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "INTERNAL_ERROR"
        # Should not expose internal details
        assert "Internal implementation detail" not in data["error"]["message"]
        assert "unexpected error occurred" in data["error"]["message"]


class TestAPIErrorBase:
    """Tests for APIError base class."""

    async def test_api_error_returns_500_by_default(self) -> None:
        """Test base APIError returns 500 by default."""
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/test")
        async def raise_api_error() -> None:
            raise APIError(message="Something went wrong")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "INTERNAL_ERROR"
        assert data["error"]["message"] == "Something went wrong"


class TestErrorResponseFormat:
    """Tests for consistent error response format across all handlers."""

    async def test_all_errors_have_error_wrapper(self) -> None:
        """Test all error responses are wrapped in 'error' key."""
        # Debug must be False for exception handlers to catch generic exceptions
        app = FastAPI(debug=False)
        register_exception_handlers(app)

        @app.get("/not-found")
        async def raise_not_found() -> None:
            raise NotFoundError("Video", "xyz123")

        @app.get("/bad-request")
        async def raise_bad_request() -> None:
            raise BadRequestError("Bad input")

        @app.get("/auth-error")
        async def raise_auth() -> None:
            raise AuthenticationError("Not authenticated")

        @app.get("/generic")
        async def raise_generic() -> None:
            raise ValueError("oops")

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for endpoint in ["/not-found", "/bad-request", "/auth-error", "/generic"]:
                response = await client.get(endpoint)
                data = response.json()
                # All responses should have "error" key at top level
                assert "error" in data, f"{endpoint} response missing 'error' key"
                # All errors should have code and message
                assert "code" in data["error"], f"{endpoint} error missing 'code'"
                assert "message" in data["error"], f"{endpoint} error missing 'message'"


class TestErrorCodeEnum:
    """Tests for ErrorCode enum values."""

    def test_error_code_values(self) -> None:
        """Test ErrorCode enum has expected values."""
        # 4xx errors
        assert ErrorCode.NOT_FOUND.value == "NOT_FOUND"
        assert ErrorCode.BAD_REQUEST.value == "BAD_REQUEST"
        assert ErrorCode.VALIDATION_ERROR.value == "VALIDATION_ERROR"
        assert ErrorCode.NOT_AUTHENTICATED.value == "NOT_AUTHENTICATED"
        assert ErrorCode.FORBIDDEN.value == "FORBIDDEN"
        assert ErrorCode.CONFLICT.value == "CONFLICT"
        assert ErrorCode.MUTUALLY_EXCLUSIVE.value == "MUTUALLY_EXCLUSIVE"

        # 5xx errors
        assert ErrorCode.INTERNAL_ERROR.value == "INTERNAL_ERROR"
        assert ErrorCode.DATABASE_ERROR.value == "DATABASE_ERROR"
        assert ErrorCode.SERVICE_UNAVAILABLE.value == "SERVICE_UNAVAILABLE"


class TestExceptionToApiErrorConversion:
    """Tests for exception to_api_error method."""

    def test_not_found_error_to_api_error(self) -> None:
        """Test NotFoundError converts to ApiError correctly."""
        exc = NotFoundError(
            resource_type="Channel",
            identifier="UCxyz123456789",
            hint="Try syncing first.",
        )

        api_error = exc.to_api_error()

        assert api_error.code == "NOT_FOUND"
        assert "Channel" in api_error.message
        assert "UCxyz123456789" in api_error.message
        assert "Try syncing first" in api_error.message
        assert api_error.details is not None
        assert api_error.details["resource_type"] == "Channel"
        assert api_error.details["identifier"] == "UCxyz123456789"

    def test_bad_request_error_to_api_error(self) -> None:
        """Test BadRequestError converts to ApiError correctly."""
        exc = BadRequestError(
            message="Invalid limit value",
            details={"field": "limit", "max": 100},
        )

        api_error = exc.to_api_error()

        assert api_error.code == "BAD_REQUEST"
        assert api_error.message == "Invalid limit value"
        assert api_error.details is not None
        assert api_error.details["field"] == "limit"

    def test_api_error_error_code_property(self) -> None:
        """Test APIError error_code property returns correct enum."""
        exc = NotFoundError("Video", "xyz")
        assert exc.error_code == ErrorCode.NOT_FOUND

        exc2 = BadRequestError("bad", mutually_exclusive=True)
        assert exc2.error_code == ErrorCode.MUTUALLY_EXCLUSIVE
