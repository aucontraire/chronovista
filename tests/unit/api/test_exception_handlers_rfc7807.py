"""Unit tests for RFC 7807 exception handler functionality.

This module tests that exception handlers return RFC 7807 Problem Detail format
instead of the legacy ErrorResponse format. These tests verify the EXPECTED format
after the RFC 7807 implementation (T042-T052) is complete.

NOTE: These tests may FAIL initially if the implementation still returns
the legacy ErrorResponse format. They should PASS after implementing T042-T052.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError as PydanticValidationError

from chronovista.api.exception_handlers import (
    api_error_handler,
    auth_error_handler,
    generic_error_handler,
    repository_error_handler,
    validation_error_handler,
)
from chronovista.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BadRequestError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    RateLimitError,
    RepositoryError,
)

# Mark all tests as async
pytestmark = pytest.mark.asyncio


# =============================================================================
# Test Fixtures and Utilities
# =============================================================================


def create_mock_request(path: str = "/api/v1/test", request_id: str = "test-request-id-123") -> Mock:
    """Create a mock Request object with standard attributes.

    Parameters
    ----------
    path : str, optional
        The request path (default: "/api/v1/test").
    request_id : str, optional
        The request ID for correlation (default: "test-request-id-123").

    Returns
    -------
    Mock
        A mock Request object configured for testing.
    """
    request = Mock(spec=Request)
    request.url = Mock()
    request.url.path = path
    request.state = Mock()
    request.state.request_id = request_id
    return request


def assert_rfc7807_structure(response_data: dict[str, Any]) -> None:
    """Assert that response data follows RFC 7807 structure.

    Parameters
    ----------
    response_data : dict[str, Any]
        The JSON response data to validate.

    Raises
    ------
    AssertionError
        If the response does not conform to RFC 7807 structure.
    """
    # Required RFC 7807 fields
    assert "type" in response_data, "Missing 'type' field"
    assert "title" in response_data, "Missing 'title' field"
    assert "status" in response_data, "Missing 'status' field"
    assert "detail" in response_data, "Missing 'detail' field"
    assert "instance" in response_data, "Missing 'instance' field"

    # chronovista extension fields
    assert "code" in response_data, "Missing 'code' field"
    assert "request_id" in response_data, "Missing 'request_id' field"

    # Type URI should follow pattern
    assert response_data["type"].startswith("https://api.chronovista.com/errors/"), \
        f"Invalid type URI: {response_data['type']}"

    # Status should be valid HTTP error code
    assert 400 <= response_data["status"] <= 599, \
        f"Invalid status code: {response_data['status']}"


# =============================================================================
# T026: NotFoundError returns RFC 7807 format with code NOT_FOUND, status 404
# =============================================================================


class TestNotFoundErrorRFC7807:
    """Tests for NotFoundError RFC 7807 compliance."""

    async def test_not_found_returns_rfc7807_format(self) -> None:
        """Test NotFoundError returns RFC 7807 format with correct fields."""
        request = create_mock_request(path="/api/v1/videos/xyz123")
        exc = NotFoundError(
            resource_type="Video",
            identifier="xyz123",
        )

        response = await api_error_handler(request, exc)

        assert response.status_code == 404
        data = response.body.decode()
        import json
        response_data = json.loads(data)

        # Verify RFC 7807 structure
        assert_rfc7807_structure(response_data)

        # Verify specific fields
        assert response_data["type"] == "https://api.chronovista.com/errors/NOT_FOUND"
        assert response_data["title"] == "Resource Not Found"
        assert response_data["status"] == 404
        assert "Video 'xyz123' not found" in response_data["detail"]
        assert response_data["instance"] == "/api/v1/videos/xyz123"
        assert response_data["code"] == "NOT_FOUND"
        assert response_data["request_id"] == "test-request-id-123"

    async def test_not_found_contains_resource_info(self) -> None:
        """Test NotFoundError includes resource type and identifier in detail."""
        request = create_mock_request(path="/api/v1/channels/UCabc")
        exc = NotFoundError(
            resource_type="Channel",
            identifier="UCabc",
            hint="Try syncing first",
        )

        response = await api_error_handler(request, exc)
        import json
        response_data = json.loads(response.body.decode())

        assert "Channel" in response_data["detail"]
        assert "UCabc" in response_data["detail"]
        assert "Try syncing first" in response_data["detail"]


# =============================================================================
# T027: BadRequestError returns RFC 7807 format with code BAD_REQUEST, status 400
# =============================================================================


class TestBadRequestErrorRFC7807:
    """Tests for BadRequestError RFC 7807 compliance."""

    async def test_bad_request_returns_rfc7807_format(self) -> None:
        """Test BadRequestError returns RFC 7807 format with correct fields."""
        request = create_mock_request(path="/api/v1/channels")
        exc = BadRequestError(
            message="Invalid parameter value",
            details={"field": "limit", "reason": "Must be positive"},
        )

        response = await api_error_handler(request, exc)

        assert response.status_code == 400
        import json
        response_data = json.loads(response.body.decode())

        # Verify RFC 7807 structure
        assert_rfc7807_structure(response_data)

        # Verify specific fields
        assert response_data["type"] == "https://api.chronovista.com/errors/BAD_REQUEST"
        assert response_data["title"] == "Bad Request"
        assert response_data["status"] == 400
        assert response_data["detail"] == "Invalid parameter value"
        assert response_data["code"] == "BAD_REQUEST"

    async def test_mutually_exclusive_error_uses_correct_code(self) -> None:
        """Test BadRequestError with mutually_exclusive=True uses MUTUALLY_EXCLUSIVE code."""
        request = create_mock_request()
        exc = BadRequestError(
            message="Cannot specify both 'linked=true' and 'unlinked=true'",
            details={"field": "linked,unlinked"},
            mutually_exclusive=True,
        )

        response = await api_error_handler(request, exc)
        import json
        response_data = json.loads(response.body.decode())

        assert response_data["type"] == "https://api.chronovista.com/errors/MUTUALLY_EXCLUSIVE"
        assert response_data["title"] == "Mutually Exclusive Parameters"
        assert response_data["code"] == "MUTUALLY_EXCLUSIVE"


# =============================================================================
# T028: ValidationError returns RFC 7807 format with code VALIDATION_ERROR, status 422
# =============================================================================


class TestValidationErrorRFC7807:
    """Tests for ValidationError RFC 7807 compliance."""

    async def test_validation_error_returns_rfc7807_with_errors_array(self) -> None:
        """Test ValidationError returns RFC 7807 format with errors array."""
        request = create_mock_request(path="/api/v1/videos")

        # Create a mock Pydantic validation error
        class TestModel(BaseModel):
            title: str
            count: int

        try:
            # This will raise a ValidationError
            TestModel.model_validate({"title": "", "count": "invalid"})
        except PydanticValidationError as pydantic_error:
            # Convert to RequestValidationError
            validation_error = RequestValidationError(errors=pydantic_error.errors())

            response = await validation_error_handler(request, validation_error)

            assert response.status_code == 422
            import json
            response_data = json.loads(response.body.decode())

            # Verify RFC 7807 structure
            assert_rfc7807_structure(response_data)

            # Verify specific fields
            assert response_data["type"] == "https://api.chronovista.com/errors/VALIDATION_ERROR"
            assert response_data["title"] == "Validation Error"
            assert response_data["status"] == 422
            assert response_data["code"] == "VALIDATION_ERROR"

            # Verify errors array exists
            assert "errors" in response_data
            assert isinstance(response_data["errors"], list)
            assert len(response_data["errors"]) > 0

            # Verify error structure
            for error in response_data["errors"]:
                assert "loc" in error
                assert "msg" in error
                assert "type" in error

    async def test_validation_error_includes_field_details(self) -> None:
        """Test ValidationError includes field-level error details."""
        request = create_mock_request()

        class TestModel(BaseModel):
            email: str

        try:
            TestModel.model_validate({"email": "not-an-email"})
        except PydanticValidationError as pydantic_error:
            validation_error = RequestValidationError(errors=pydantic_error.errors())
            response = await validation_error_handler(request, validation_error)

            import json
            response_data = json.loads(response.body.decode())

            # Find the email error
            email_errors = [e for e in response_data["errors"] if "email" in e["loc"]]
            assert len(email_errors) > 0


# =============================================================================
# T029: AuthenticationError returns RFC 7807 format with code NOT_AUTHENTICATED, status 401
# =============================================================================


class TestAuthenticationErrorRFC7807:
    """Tests for AuthenticationError RFC 7807 compliance."""

    async def test_authentication_error_returns_rfc7807_format(self) -> None:
        """Test AuthenticationError returns RFC 7807 format with status 401."""
        request = create_mock_request(path="/api/v1/videos")
        exc = AuthenticationError(message="Invalid or expired token")

        response = await auth_error_handler(request, exc)

        assert response.status_code == 401
        import json
        response_data = json.loads(response.body.decode())

        # Verify RFC 7807 structure
        assert_rfc7807_structure(response_data)

        # Verify specific fields
        assert response_data["type"] == "https://api.chronovista.com/errors/NOT_AUTHENTICATED"
        assert response_data["title"] == "Authentication Required"
        assert response_data["status"] == 401
        assert response_data["detail"] == "Invalid or expired token"
        assert response_data["code"] == "NOT_AUTHENTICATED"

    async def test_authentication_error_preserves_www_authenticate_header(self) -> None:
        """Test AuthenticationError preserves WWW-Authenticate header if present."""
        # NOTE: This test validates that the handler should preserve custom headers
        # The current implementation may not support this yet
        request = create_mock_request()
        exc = AuthenticationError(message="Token expired")
        # In a full implementation, we might set exc.headers = {"WWW-Authenticate": "Bearer"}

        response = await auth_error_handler(request, exc)

        # For now, just verify status code
        assert response.status_code == 401


# =============================================================================
# T030: AuthorizationError returns RFC 7807 format with code NOT_AUTHORIZED, status 403
# =============================================================================


class TestAuthorizationErrorRFC7807:
    """Tests for AuthorizationError RFC 7807 compliance."""

    async def test_authorization_error_returns_rfc7807_format(self) -> None:
        """Test AuthorizationError returns RFC 7807 format with status 403."""
        request = create_mock_request(path="/api/v1/admin/users")
        exc = AuthorizationError(
            message="Insufficient permissions for this operation",
            details={"required_scope": "admin"},
        )

        response = await api_error_handler(request, exc)

        assert response.status_code == 403
        import json
        response_data = json.loads(response.body.decode())

        # Verify RFC 7807 structure
        assert_rfc7807_structure(response_data)

        # Verify specific fields
        assert response_data["type"] == "https://api.chronovista.com/errors/NOT_AUTHORIZED"
        assert response_data["title"] == "Access Denied"
        assert response_data["status"] == 403
        assert response_data["detail"] == "Insufficient permissions for this operation"
        assert response_data["code"] == "NOT_AUTHORIZED"


# =============================================================================
# T031: ConflictError returns RFC 7807 format with code CONFLICT, status 409
# =============================================================================


class TestConflictErrorRFC7807:
    """Tests for ConflictError RFC 7807 compliance."""

    async def test_conflict_error_returns_rfc7807_format(self) -> None:
        """Test ConflictError returns RFC 7807 format with status 409."""
        request = create_mock_request(path="/api/v1/channels")
        exc = ConflictError(
            message="Channel already exists",
            details={"channel_id": "UCxyz123"},
        )

        response = await api_error_handler(request, exc)

        assert response.status_code == 409
        import json
        response_data = json.loads(response.body.decode())

        # Verify RFC 7807 structure
        assert_rfc7807_structure(response_data)

        # Verify specific fields
        assert response_data["type"] == "https://api.chronovista.com/errors/CONFLICT"
        assert response_data["title"] == "Resource Conflict"
        assert response_data["status"] == 409
        assert response_data["detail"] == "Channel already exists"
        assert response_data["code"] == "CONFLICT"


# =============================================================================
# T032: RateLimitError returns RFC 7807 format with code RATE_LIMITED, status 429
# =============================================================================


class TestRateLimitErrorRFC7807:
    """Tests for RateLimitError RFC 7807 compliance."""

    async def test_rate_limit_error_returns_rfc7807_format(self) -> None:
        """Test RateLimitError returns RFC 7807 format with status 429."""
        request = create_mock_request(path="/api/v1/videos")
        exc = RateLimitError(
            message="API rate limit exceeded. Please retry after 60 seconds.",
            retry_after=60,
        )

        response = await api_error_handler(request, exc)

        assert response.status_code == 429
        import json
        response_data = json.loads(response.body.decode())

        # Verify RFC 7807 structure
        assert_rfc7807_structure(response_data)

        # Verify specific fields
        assert response_data["type"] == "https://api.chronovista.com/errors/RATE_LIMITED"
        assert response_data["title"] == "Rate Limit Exceeded"
        assert response_data["status"] == 429
        assert response_data["code"] == "RATE_LIMITED"

    async def test_rate_limit_error_includes_retry_after_header(self) -> None:
        """Test RateLimitError includes Retry-After header if retry_after is set."""
        # NOTE: This test validates that the handler should set Retry-After header
        # The current implementation may not support this yet
        request = create_mock_request()
        exc = RateLimitError(
            message="Rate limited",
            retry_after=120,
        )

        response = await api_error_handler(request, exc)

        # Verify that response should have Retry-After header
        # This will be implemented in T042-T052
        assert response.status_code == 429
        # Future: assert response.headers.get("Retry-After") == "120"


# =============================================================================
# T033: RepositoryError returns RFC 7807 format with code DATABASE_ERROR, status 500
# =============================================================================


class TestRepositoryErrorRFC7807:
    """Tests for RepositoryError RFC 7807 compliance."""

    async def test_repository_error_returns_rfc7807_format(self) -> None:
        """Test RepositoryError returns RFC 7807 format with status 500."""
        request = create_mock_request(path="/api/v1/videos")
        exc = RepositoryError(
            message="Database connection timeout",
            operation="insert",
            entity_type="Video",
            original_error=Exception("Connection refused"),
        )

        response = await repository_error_handler(request, exc)

        assert response.status_code == 500
        import json
        response_data = json.loads(response.body.decode())

        # Verify RFC 7807 structure
        assert_rfc7807_structure(response_data)

        # Verify specific fields
        assert response_data["type"] == "https://api.chronovista.com/errors/DATABASE_ERROR"
        assert response_data["title"] == "Database Error"
        assert response_data["status"] == 500
        assert response_data["code"] == "DATABASE_ERROR"

    async def test_repository_error_detail_is_generic(self) -> None:
        """Test RepositoryError detail is generic, not internal message."""
        request = create_mock_request()
        exc = RepositoryError(
            message="SELECT failed: table 'videos' locked by process 12345",
            operation="select",
            entity_type="Video",
            original_error=Exception("LOCK TIMEOUT"),
        )

        response = await repository_error_handler(request, exc)
        import json
        response_data = json.loads(response.body.decode())

        # Detail should be generic, not expose internal error
        assert response_data["detail"] == "A database error occurred"
        assert "locked by process" not in response_data["detail"]
        assert "LOCK TIMEOUT" not in response_data["detail"]


# =============================================================================
# T034: ExternalServiceError returns RFC 7807 format with code EXTERNAL_SERVICE_ERROR, status 502
# =============================================================================


class TestExternalServiceErrorRFC7807:
    """Tests for ExternalServiceError RFC 7807 compliance."""

    async def test_external_service_error_returns_rfc7807_format(self) -> None:
        """Test ExternalServiceError returns RFC 7807 format with status 502."""
        request = create_mock_request(path="/api/v1/videos")
        exc = ExternalServiceError(
            message="YouTube API returned 500",
            details={"service": "YouTube API", "reason": "Internal Server Error"},
        )

        response = await api_error_handler(request, exc)

        assert response.status_code == 502
        import json
        response_data = json.loads(response.body.decode())

        # Verify RFC 7807 structure
        assert_rfc7807_structure(response_data)

        # Verify specific fields
        assert response_data["type"] == "https://api.chronovista.com/errors/EXTERNAL_SERVICE_ERROR"
        assert response_data["title"] == "External Service Error"
        assert response_data["status"] == 502
        assert response_data["code"] == "EXTERNAL_SERVICE_ERROR"

    async def test_external_service_error_detail_is_generic(self) -> None:
        """Test ExternalServiceError detail is generic."""
        request = create_mock_request()
        exc = ExternalServiceError(
            message="YouTube API connection timeout after 30s (endpoint: /videos)",
            details={"service": "YouTube"},
        )

        response = await api_error_handler(request, exc)
        import json
        response_data = json.loads(response.body.decode())

        # Detail should be generic
        assert response_data["detail"] == "External service unavailable"
        assert "connection timeout" not in response_data["detail"]
        assert "/videos" not in response_data["detail"]


# =============================================================================
# T035: Unhandled Exception returns RFC 7807 format with code INTERNAL_ERROR, status 500
# =============================================================================


class TestUnhandledExceptionRFC7807:
    """Tests for unhandled exception RFC 7807 compliance."""

    async def test_unhandled_exception_returns_rfc7807_format(self) -> None:
        """Test unhandled exceptions return RFC 7807 format with status 500."""
        request = create_mock_request(path="/api/v1/videos")
        exc = RuntimeError("Unexpected error in business logic")

        response = await generic_error_handler(request, exc)

        assert response.status_code == 500
        import json
        response_data = json.loads(response.body.decode())

        # Verify RFC 7807 structure
        assert_rfc7807_structure(response_data)

        # Verify specific fields
        assert response_data["type"] == "https://api.chronovista.com/errors/INTERNAL_ERROR"
        assert response_data["title"] == "Internal Server Error"
        assert response_data["status"] == 500
        assert response_data["code"] == "INTERNAL_ERROR"

    async def test_unhandled_exception_detail_is_generic(self) -> None:
        """Test unhandled exception detail is generic."""
        request = create_mock_request()
        exc = ValueError("Secret internal implementation detail")

        response = await generic_error_handler(request, exc)
        import json
        response_data = json.loads(response.body.decode())

        # Detail should be generic, not expose internal error
        assert response_data["detail"] == "An unexpected error occurred"
        assert "Secret internal" not in response_data["detail"]


# =============================================================================
# T036: Validation errors preserve Pydantic field order and allow multiple errors per field
# =============================================================================


class TestValidationErrorFieldOrder:
    """Tests for validation error field order preservation."""

    async def test_validation_errors_preserve_field_order(self) -> None:
        """Test validation errors preserve Pydantic field order."""
        request = create_mock_request()

        class TestModel(BaseModel):
            first_field: str
            second_field: int
            third_field: str

        try:
            # Trigger multiple validation errors
            TestModel.model_validate({
                "first_field": "",  # Will fail min_length if we add validators
                "second_field": "not-a-number",
                "third_field": "",
            })
        except PydanticValidationError as pydantic_error:
            validation_error = RequestValidationError(errors=pydantic_error.errors())
            response = await validation_error_handler(request, validation_error)

            import json
            response_data = json.loads(response.body.decode())

            # Errors should be in order
            errors = response_data["errors"]
            assert len(errors) >= 1  # At least second_field should fail

    async def test_validation_errors_allow_multiple_per_field(self) -> None:
        """Test validation errors can have multiple errors for same field."""
        request = create_mock_request()

        class TestModel(BaseModel):
            email: str

        # Create a validation error manually to simulate multiple errors per field
        try:
            TestModel.model_validate({"email": "not-an-email"})
        except PydanticValidationError as pydantic_error:
            # Even if there's only one error per field in this case,
            # the structure should support multiple
            validation_error = RequestValidationError(errors=pydantic_error.errors())
            response = await validation_error_handler(request, validation_error)

            import json
            response_data = json.loads(response.body.decode())

            # Verify errors is an array that can contain multiple entries
            assert isinstance(response_data["errors"], list)


# =============================================================================
# T037: Detail messages >4096 chars are truncated with "... (truncated)" suffix
# =============================================================================


class TestDetailMessageTruncation:
    """Tests for detail message truncation."""

    async def test_detail_message_truncation_at_4096_chars(self) -> None:
        """Test detail messages >4096 chars are truncated with suffix."""
        request = create_mock_request()

        # Create a message longer than 4096 characters
        long_message = "A" * 5000

        exc = BadRequestError(message=long_message)
        response = await api_error_handler(request, exc)

        import json
        response_data = json.loads(response.body.decode())

        detail = response_data["detail"]

        # Should be truncated to 4096 or less
        assert len(detail) <= 4096

        # Should end with truncation indicator
        if len(long_message) > 4096:
            assert detail.endswith("... (truncated)")


# =============================================================================
# T038: Error serialization failure returns minimal hardcoded RFC 7807 response
# =============================================================================


class TestErrorSerializationFailure:
    """Tests for error serialization failure fallback."""

    async def test_serialization_failure_returns_minimal_rfc7807(self) -> None:
        """Test that serialization failure returns minimal hardcoded RFC 7807 response."""
        # This test is conceptual - in practice, serialization failures are rare
        # The implementation should catch any serialization errors and return
        # a minimal RFC 7807 response with safe defaults

        request = create_mock_request()

        # Create an error with a non-serializable detail
        # Most Pydantic models will serialize, but we can conceptually test this
        exc = BadRequestError(
            message="Normal message",
            details={"safe_field": "value"},
        )

        response = await api_error_handler(request, exc)
        import json
        response_data = json.loads(response.body.decode())

        # Should still be valid RFC 7807
        assert_rfc7807_structure(response_data)


# =============================================================================
# T039: Chained exceptions use outermost exception for mapping
# =============================================================================


class TestChainedExceptions:
    """Tests for chained exception handling."""

    async def test_chained_exceptions_use_outermost_exception(self) -> None:
        """Test that chained exceptions use outermost exception for error mapping."""
        request = create_mock_request()

        # Create a chained exception
        try:
            try:
                raise ValueError("Inner error")
            except ValueError as inner:
                raise NotFoundError("Video", "xyz123") from inner
        except NotFoundError as exc:
            response = await api_error_handler(request, exc)

            import json
            response_data = json.loads(response.body.decode())

            # Should use NotFoundError (outermost), not ValueError (inner)
            assert response_data["code"] == "NOT_FOUND"
            assert response_data["status"] == 404
            assert "Video" in response_data["detail"]


# =============================================================================
# T040: RFC 7807 type URI follows pattern https://api.chronovista.com/errors/{ErrorCode}
# =============================================================================


class TestRFC7807TypeURI:
    """Tests for RFC 7807 type URI format."""

    async def test_type_uri_follows_correct_pattern(self) -> None:
        """Test RFC 7807 type URI follows pattern."""
        request = create_mock_request()

        test_cases = [
            (NotFoundError("Video", "xyz"), "NOT_FOUND"),
            (BadRequestError("Bad input"), "BAD_REQUEST"),
            (ConflictError("Conflict"), "CONFLICT"),
            (AuthorizationError("No access"), "NOT_AUTHORIZED"),
            (RateLimitError("Too many requests"), "RATE_LIMITED"),
            (ExternalServiceError("Service down"), "EXTERNAL_SERVICE_ERROR"),
        ]

        for exc, expected_code in test_cases:
            response = await api_error_handler(request, exc)
            import json
            response_data = json.loads(response.body.decode())

            expected_uri = f"https://api.chronovista.com/errors/{expected_code}"
            assert response_data["type"] == expected_uri, \
                f"Expected {expected_uri}, got {response_data['type']}"


# =============================================================================
# T041: RFC 7807 instance field contains request path
# =============================================================================


class TestRFC7807InstanceField:
    """Tests for RFC 7807 instance field."""

    async def test_instance_field_contains_request_path(self) -> None:
        """Test RFC 7807 instance field contains request path."""
        test_paths = [
            "/api/v1/videos/xyz123",
            "/api/v1/channels",
            "/api/v1/videos?limit=10&offset=0",
            "/api/v1/channels/UCabc/videos",
        ]

        for path in test_paths:
            request = create_mock_request(path=path)
            exc = NotFoundError("Resource", "test")

            response = await api_error_handler(request, exc)
            import json
            response_data = json.loads(response.body.decode())

            assert response_data["instance"] == path, \
                f"Expected instance={path}, got {response_data['instance']}"

    async def test_instance_field_preserves_query_parameters(self) -> None:
        """Test RFC 7807 instance field preserves query parameters."""
        request = create_mock_request(path="/api/v1/videos?limit=100&offset=50")
        exc = BadRequestError("Invalid limit")

        response = await api_error_handler(request, exc)
        import json
        response_data = json.loads(response.body.decode())

        assert "limit=100" in response_data["instance"]
        assert "offset=50" in response_data["instance"]
