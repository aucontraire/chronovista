"""
Tests for custom exceptions module.

This module tests all custom exception classes, their attributes,
inheritance hierarchy, and exit codes.
"""

from __future__ import annotations

import pytest

from chronovista.exceptions import (
    EXIT_CODE_AUTHENTICATION_FAILED,
    EXIT_CODE_GENERAL_ERROR,
    EXIT_CODE_INTERRUPTED,
    EXIT_CODE_INVALID_ARGS,
    EXIT_CODE_PREREQUISITES_MISSING,
    EXIT_CODE_QUOTA_EXCEEDED,
    EXIT_CODE_SUCCESS,
    AuthenticationError,
    ChronovistaError,
    GracefulShutdownException,
    NetworkError,
    PrerequisiteError,
    QuotaExceededException,
    RepositoryError,
    ValidationError,
    YouTubeAPIError,
)


class TestChronovistaError:
    """Tests for base ChronovistaError exception."""

    def test_base_error_with_message(self) -> None:
        """Test base error stores message correctly."""
        error = ChronovistaError("Test error message")
        assert error.message == "Test error message"
        assert str(error) == "Test error message"

    def test_base_error_inherits_from_exception(self) -> None:
        """Test ChronovistaError inherits from Exception."""
        assert issubclass(ChronovistaError, Exception)

    def test_base_error_can_be_raised(self) -> None:
        """Test ChronovistaError can be raised and caught."""
        with pytest.raises(ChronovistaError, match="Test error"):
            raise ChronovistaError("Test error")


class TestQuotaExceededException:
    """Tests for QuotaExceededException."""

    def test_default_values(self) -> None:
        """Test default attribute values."""
        error = QuotaExceededException()
        assert error.message == "YouTube API quota exceeded"
        assert error.daily_quota_exceeded is True
        assert error.videos_processed == 0

    def test_custom_values(self) -> None:
        """Test custom attribute values."""
        error = QuotaExceededException(
            message="Custom quota message",
            daily_quota_exceeded=False,
            videos_processed=42,
        )
        assert error.message == "Custom quota message"
        assert error.daily_quota_exceeded is False
        assert error.videos_processed == 42

    def test_inherits_from_chronovista_error(self) -> None:
        """Test QuotaExceededException inherits from ChronovistaError."""
        assert issubclass(QuotaExceededException, ChronovistaError)
        error = QuotaExceededException()
        assert isinstance(error, ChronovistaError)

    def test_can_be_caught_as_base_error(self) -> None:
        """Test exception can be caught as base ChronovistaError."""
        with pytest.raises(ChronovistaError):
            raise QuotaExceededException()


class TestNetworkError:
    """Tests for NetworkError exception."""

    def test_default_values(self) -> None:
        """Test default attribute values."""
        error = NetworkError()
        assert error.message == "Network error occurred"
        assert error.original_error is None
        assert error.retry_count == 0

    def test_custom_values(self) -> None:
        """Test custom attribute values."""
        original = ConnectionError("Connection failed")
        error = NetworkError(
            message="Custom network error",
            original_error=original,
            retry_count=3,
        )
        assert error.message == "Custom network error"
        assert error.original_error is original
        assert error.retry_count == 3

    def test_inherits_from_chronovista_error(self) -> None:
        """Test NetworkError inherits from ChronovistaError."""
        assert issubclass(NetworkError, ChronovistaError)


class TestGracefulShutdownException:
    """Tests for GracefulShutdownException."""

    def test_default_values(self) -> None:
        """Test default attribute values."""
        error = GracefulShutdownException()
        assert error.message == "Graceful shutdown requested"
        assert error.signal_received == "SIGINT"

    def test_custom_values(self) -> None:
        """Test custom attribute values."""
        error = GracefulShutdownException(
            message="Shutdown via SIGTERM",
            signal_received="SIGTERM",
        )
        assert error.message == "Shutdown via SIGTERM"
        assert error.signal_received == "SIGTERM"

    def test_inherits_from_chronovista_error(self) -> None:
        """Test GracefulShutdownException inherits from ChronovistaError."""
        assert issubclass(GracefulShutdownException, ChronovistaError)


class TestPrerequisiteError:
    """Tests for PrerequisiteError exception."""

    def test_default_values(self) -> None:
        """Test default attribute values."""
        error = PrerequisiteError()
        assert error.message == "Prerequisite data is missing"
        assert error.missing_tables == []

    def test_custom_values(self) -> None:
        """Test custom attribute values."""
        error = PrerequisiteError(
            message="Missing required tables",
            missing_tables=["topic_categories", "video_categories"],
        )
        assert error.message == "Missing required tables"
        assert error.missing_tables == ["topic_categories", "video_categories"]

    def test_none_missing_tables_becomes_empty_list(self) -> None:
        """Test None missing_tables defaults to empty list."""
        error = PrerequisiteError(missing_tables=None)
        assert error.missing_tables == []

    def test_inherits_from_chronovista_error(self) -> None:
        """Test PrerequisiteError inherits from ChronovistaError."""
        assert issubclass(PrerequisiteError, ChronovistaError)


class TestYouTubeAPIError:
    """Tests for YouTubeAPIError exception."""

    def test_default_values(self) -> None:
        """Test default attribute values."""
        error = YouTubeAPIError()
        assert error.message == "YouTube API error occurred"
        assert error.status_code is None
        assert error.error_reason is None

    def test_custom_values(self) -> None:
        """Test custom attribute values."""
        error = YouTubeAPIError(
            message="Video not found",
            status_code=404,
            error_reason="videoNotFound",
        )
        assert error.message == "Video not found"
        assert error.status_code == 404
        assert error.error_reason == "videoNotFound"

    def test_inherits_from_chronovista_error(self) -> None:
        """Test YouTubeAPIError inherits from ChronovistaError."""
        assert issubclass(YouTubeAPIError, ChronovistaError)

    def test_can_be_caught_as_base_error(self) -> None:
        """Test exception can be caught as base ChronovistaError."""
        with pytest.raises(ChronovistaError):
            raise YouTubeAPIError(status_code=403)

    def test_status_code_types(self) -> None:
        """Test various HTTP status codes."""
        # Client errors
        error_400 = YouTubeAPIError(status_code=400, error_reason="badRequest")
        assert error_400.status_code == 400

        # Not found
        error_404 = YouTubeAPIError(status_code=404, error_reason="notFound")
        assert error_404.status_code == 404

        # Server errors
        error_500 = YouTubeAPIError(status_code=500, error_reason="internalError")
        assert error_500.status_code == 500


class TestAuthenticationError:
    """Tests for AuthenticationError exception."""

    def test_default_values(self) -> None:
        """Test default attribute values."""
        error = AuthenticationError()
        assert error.message == "Authentication failed"
        assert error.expired is False
        assert error.scope is None

    def test_custom_values(self) -> None:
        """Test custom attribute values."""
        error = AuthenticationError(
            message="Token expired",
            expired=True,
            scope="https://www.googleapis.com/auth/youtube.readonly",
        )
        assert error.message == "Token expired"
        assert error.expired is True
        assert error.scope == "https://www.googleapis.com/auth/youtube.readonly"

    def test_inherits_from_chronovista_error(self) -> None:
        """Test AuthenticationError inherits from ChronovistaError."""
        assert issubclass(AuthenticationError, ChronovistaError)

    def test_expired_token_scenario(self) -> None:
        """Test typical expired token error."""
        error = AuthenticationError(
            message="Access token has expired",
            expired=True,
        )
        assert error.expired is True
        assert error.scope is None

    def test_missing_scope_scenario(self) -> None:
        """Test typical missing scope error."""
        error = AuthenticationError(
            message="Missing required scope",
            expired=False,
            scope="https://www.googleapis.com/auth/youtube.force-ssl",
        )
        assert error.expired is False
        assert "force-ssl" in (error.scope or "")


class TestValidationError:
    """Tests for ValidationError exception."""

    def test_default_values(self) -> None:
        """Test default attribute values."""
        error = ValidationError()
        assert error.message == "Validation failed"
        assert error.field_name is None
        assert error.invalid_value is None

    def test_custom_values(self) -> None:
        """Test custom attribute values."""
        error = ValidationError(
            message="Invalid video ID format",
            field_name="video_id",
            invalid_value="invalid-id-format",
        )
        assert error.message == "Invalid video ID format"
        assert error.field_name == "video_id"
        assert error.invalid_value == "invalid-id-format"

    def test_inherits_from_chronovista_error(self) -> None:
        """Test ValidationError inherits from ChronovistaError."""
        assert issubclass(ValidationError, ChronovistaError)

    def test_various_invalid_value_types(self) -> None:
        """Test invalid_value can be any type."""
        # String value
        error_str = ValidationError(field_name="title", invalid_value="")
        assert error_str.invalid_value == ""

        # Integer value
        error_int = ValidationError(field_name="count", invalid_value=-1)
        assert error_int.invalid_value == -1

        # None value
        error_none = ValidationError(field_name="required_field", invalid_value=None)
        assert error_none.invalid_value is None

        # List value
        error_list = ValidationError(field_name="tags", invalid_value=[])
        assert error_list.invalid_value == []


class TestRepositoryError:
    """Tests for RepositoryError exception."""

    def test_default_values(self) -> None:
        """Test default attribute values."""
        error = RepositoryError()
        assert error.message == "Repository operation failed"
        assert error.operation is None
        assert error.entity_type is None
        assert error.original_error is None

    def test_custom_values(self) -> None:
        """Test custom attribute values."""
        original = ValueError("Constraint violation")
        error = RepositoryError(
            message="Failed to insert video",
            operation="insert",
            entity_type="Video",
            original_error=original,
        )
        assert error.message == "Failed to insert video"
        assert error.operation == "insert"
        assert error.entity_type == "Video"
        assert error.original_error is original

    def test_inherits_from_chronovista_error(self) -> None:
        """Test RepositoryError inherits from ChronovistaError."""
        assert issubclass(RepositoryError, ChronovistaError)

    def test_various_operations(self) -> None:
        """Test various database operations."""
        operations = ["insert", "update", "delete", "select", "upsert"]
        for op in operations:
            error = RepositoryError(operation=op)
            assert error.operation == op

    def test_various_entity_types(self) -> None:
        """Test various entity types."""
        entities = ["Video", "Channel", "Playlist", "UserVideo", "Transcript"]
        for entity in entities:
            error = RepositoryError(entity_type=entity)
            assert error.entity_type == entity


class TestExitCodes:
    """Tests for CLI exit codes."""

    def test_exit_code_values(self) -> None:
        """Test exit code values are correct."""
        assert EXIT_CODE_SUCCESS == 0
        assert EXIT_CODE_GENERAL_ERROR == 1
        assert EXIT_CODE_INVALID_ARGS == 2
        assert EXIT_CODE_QUOTA_EXCEEDED == 3
        assert EXIT_CODE_PREREQUISITES_MISSING == 4
        assert EXIT_CODE_AUTHENTICATION_FAILED == 5
        assert EXIT_CODE_INTERRUPTED == 130

    def test_exit_codes_are_unique(self) -> None:
        """Test all exit codes have unique values."""
        exit_codes = [
            EXIT_CODE_SUCCESS,
            EXIT_CODE_GENERAL_ERROR,
            EXIT_CODE_INVALID_ARGS,
            EXIT_CODE_QUOTA_EXCEEDED,
            EXIT_CODE_PREREQUISITES_MISSING,
            EXIT_CODE_AUTHENTICATION_FAILED,
            EXIT_CODE_INTERRUPTED,
        ]
        assert len(exit_codes) == len(set(exit_codes))

    def test_interrupted_follows_unix_convention(self) -> None:
        """Test interrupted exit code follows Unix convention (128 + signal)."""
        # SIGINT is signal 2, so 128 + 2 = 130
        assert EXIT_CODE_INTERRUPTED == 130


class TestExceptionHierarchy:
    """Tests for exception inheritance hierarchy."""

    def test_all_exceptions_inherit_from_base(self) -> None:
        """Test all custom exceptions inherit from ChronovistaError."""
        exception_classes = [
            QuotaExceededException,
            NetworkError,
            GracefulShutdownException,
            PrerequisiteError,
            YouTubeAPIError,
            AuthenticationError,
            ValidationError,
            RepositoryError,
        ]
        for exc_class in exception_classes:
            assert issubclass(exc_class, ChronovistaError), (
                f"{exc_class.__name__} does not inherit from ChronovistaError"
            )

    def test_exception_message_propagation(self) -> None:
        """Test message propagation through inheritance chain."""
        error = YouTubeAPIError("Custom message")
        # Message accessible via attribute
        assert error.message == "Custom message"
        # Message accessible via str()
        assert str(error) == "Custom message"
        # Message accessible via args
        assert error.args[0] == "Custom message"

    def test_catching_with_base_class(self) -> None:
        """Test all exceptions can be caught with base class."""
        exceptions_to_raise = [
            QuotaExceededException("quota"),
            NetworkError("network"),
            GracefulShutdownException("shutdown"),
            PrerequisiteError("prereq"),
            YouTubeAPIError("api"),
            AuthenticationError("auth"),
            ValidationError("validation"),
            RepositoryError("repo"),
        ]
        for exc in exceptions_to_raise:
            with pytest.raises(ChronovistaError):
                raise exc
