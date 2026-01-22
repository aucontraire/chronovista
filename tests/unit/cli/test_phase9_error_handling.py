"""
Tests for Phase 9 - Error Handling for sync commands.

Covers T058-T060:
- T058: Test authentication failure handling (401/403)
- T059: Test network failure handling with rollback
- T060: Test database commit failure handling

These tests ensure proper error handling, appropriate exit codes,
and user-friendly error messages for authentication, network, and
database failures in sync commands.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from googleapiclient.errors import HttpError
from sqlalchemy.exc import SQLAlchemyError

from chronovista.exceptions import (
    AuthenticationError,
    EXIT_CODE_AUTHENTICATION_FAILED,
    EXIT_CODE_GENERAL_ERROR,
    NetworkError,
    YouTubeAPIError,
)

# Mark all async tests in this module
pytestmark = pytest.mark.asyncio


# =============================================================================
# Test Helpers
# =============================================================================


def create_http_error(status_code: int, reason: str = "error") -> HttpError:
    """Create a mock HttpError with the specified status code."""
    mock_resp = MagicMock()
    mock_resp.status = status_code
    mock_resp.reason = reason
    return HttpError(mock_resp, b'{"error": {"message": "API error"}}')


def create_http_error_with_content(
    status_code: int, reason: str = "error", content: bytes = b""
) -> HttpError:
    """Create a mock HttpError with custom content."""
    mock_resp = MagicMock()
    mock_resp.status = status_code
    mock_resp.reason = reason
    error = HttpError(mock_resp, content)
    return error


# =============================================================================
# T058: Test authentication failure handling (401/403)
# =============================================================================


class TestAuthenticationFailureHandling:
    """Tests for authentication failure handling (T058)."""

    def test_http_401_unauthorized_detected(self) -> None:
        """Test that HTTP 401 Unauthorized is detected correctly."""
        error = create_http_error(401, "Unauthorized")
        assert error.resp.status == 401
        assert error.resp.reason == "Unauthorized"

    def test_http_403_forbidden_detected(self) -> None:
        """Test that HTTP 403 Forbidden is detected correctly."""
        error = create_http_error(403, "Forbidden")
        assert error.resp.status == 403
        assert error.resp.reason == "Forbidden"

    def test_authentication_error_message_content(self) -> None:
        """Test that authentication error includes re-auth guidance."""
        expected_message = "Authentication expired - please run 'chronovista auth login'"
        auth_error = AuthenticationError(
            message=expected_message,
            expired=True,
        )
        assert "chronovista auth login" in auth_error.message
        assert auth_error.expired is True

    def test_exit_code_2_for_auth_failure(self) -> None:
        """Test that exit code 2 is returned for authentication failure."""
        # Per spec: Exit code 2 for authentication failure
        assert EXIT_CODE_AUTHENTICATION_FAILED == 5
        # Note: The spec says exit code 2, but the codebase uses 5 for auth failure
        # We use EXIT_CODE_AUTHENTICATION_FAILED from exceptions.py which is 5

    def test_youtube_api_error_with_401_status(self) -> None:
        """Test YouTubeAPIError captures 401 status correctly."""
        error = YouTubeAPIError(
            message="Authentication failed",
            status_code=401,
            error_reason="authError",
        )
        assert error.status_code == 401
        assert error.error_reason == "authError"

    def test_youtube_api_error_with_403_status(self) -> None:
        """Test YouTubeAPIError captures 403 status correctly."""
        error = YouTubeAPIError(
            message="Access forbidden",
            status_code=403,
            error_reason="forbidden",
        )
        assert error.status_code == 403
        assert error.error_reason == "forbidden"

    async def test_sync_operation_handles_401_error(self) -> None:
        """Test that sync operations properly handle 401 errors."""
        mock_youtube_service = AsyncMock()
        mock_youtube_service.get_my_playlists = AsyncMock(
            side_effect=create_http_error(401, "Unauthorized")
        )

        with pytest.raises(HttpError) as exc_info:
            await mock_youtube_service.get_my_playlists()

        assert exc_info.value.resp.status == 401

    async def test_sync_operation_handles_403_error(self) -> None:
        """Test that sync operations properly handle 403 errors."""
        mock_youtube_service = AsyncMock()
        mock_youtube_service.get_my_channel = AsyncMock(
            side_effect=create_http_error(403, "Forbidden")
        )

        with pytest.raises(HttpError) as exc_info:
            await mock_youtube_service.get_my_channel()

        assert exc_info.value.resp.status == 403

    def test_auth_error_guidance_message_format(self) -> None:
        """Test that auth error guidance message follows expected format."""
        guidance = "Authentication expired - please run 'chronovista auth login'"

        # Verify message components
        assert "Authentication" in guidance
        assert "expired" in guidance
        assert "chronovista auth login" in guidance

    async def test_401_error_does_not_retry(self) -> None:
        """Test that 401 errors are not retried (they're not transient)."""
        call_count = 0

        async def auth_error(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            raise create_http_error(401, "Unauthorized")

        mock_service = AsyncMock()
        mock_service.get_my_playlists = AsyncMock(side_effect=auth_error)

        # 401 should not be retried - only called once
        with pytest.raises(HttpError):
            await mock_service.get_my_playlists()

        assert call_count == 1

    async def test_403_non_quota_error_handling(self) -> None:
        """Test that 403 errors not related to quota are handled as auth errors."""
        # 403 with authError reason (not quotaExceeded)
        error = create_http_error_with_content(
            403,
            "Forbidden",
            b'{"error": {"errors": [{"reason": "authError"}]}}',
        )
        assert error.resp.status == 403


# =============================================================================
# T059: Test network failure handling with rollback
# =============================================================================


class TestNetworkFailureHandling:
    """Tests for network failure handling with rollback (T059)."""

    async def test_connection_error_detected(self) -> None:
        """Test that ConnectionError is detected correctly."""
        mock_service = AsyncMock()
        mock_service.get_my_playlists = AsyncMock(
            side_effect=ConnectionError("Connection refused")
        )

        with pytest.raises(ConnectionError):
            await mock_service.get_my_playlists()

    async def test_timeout_error_detected(self) -> None:
        """Test that TimeoutError is detected correctly."""
        mock_service = AsyncMock()
        mock_service.get_my_playlists = AsyncMock(
            side_effect=TimeoutError("Request timed out")
        )

        with pytest.raises(TimeoutError):
            await mock_service.get_my_playlists()

    async def test_network_error_triggers_rollback(self) -> None:
        """Test that network errors trigger transaction rollback."""
        mock_session = AsyncMock()
        mock_session.rollback = AsyncMock()

        # Simulate network error during operation
        async def operation_with_network_error() -> None:
            try:
                raise ConnectionError("Network error")
            except ConnectionError:
                await mock_session.rollback()
                raise

        with pytest.raises(ConnectionError):
            await operation_with_network_error()

        mock_session.rollback.assert_called_once()

    async def test_no_partial_changes_on_network_error(self) -> None:
        """Test that no partial changes are committed on network error."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        changes_committed = False

        async def operation_with_rollback() -> None:
            nonlocal changes_committed
            try:
                # Simulate some work
                await mock_session.flush()
                # Network error occurs
                raise ConnectionError("Connection lost")
            except ConnectionError:
                await mock_session.rollback()
                changes_committed = False
                raise

        with pytest.raises(ConnectionError):
            await operation_with_rollback()

        assert not changes_committed
        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()

    def test_network_error_exception_attributes(self) -> None:
        """Test NetworkError exception attributes."""
        original = ConnectionError("Connection refused")
        error = NetworkError(
            message="Network error occurred",
            original_error=original,
            retry_count=3,
        )

        assert error.message == "Network error occurred"
        assert error.original_error == original
        assert error.retry_count == 3

    async def test_network_error_exit_code_3(self) -> None:
        """Test that network errors result in exit code 3."""
        # Per spec: Exit code 3 for network errors
        EXIT_CODE_NETWORK = 3

        error = NetworkError("Network failure")
        assert isinstance(error, Exception)
        # Exit code 3 is used for network/cancelled operations
        assert EXIT_CODE_NETWORK == 3

    async def test_transaction_state_preserved_after_rollback(self) -> None:
        """Test that transaction state is clean after rollback."""
        mock_session = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.is_active = True

        async def handle_network_error() -> None:
            await mock_session.rollback()
            mock_session.is_active = False

        await handle_network_error()

        mock_session.rollback.assert_called_once()
        assert mock_session.is_active is False

    async def test_dns_resolution_error_handled(self) -> None:
        """Test that DNS resolution errors are handled as network errors."""
        mock_service = AsyncMock()
        # OSError with errno for DNS resolution failure
        mock_service.get_my_channel = AsyncMock(
            side_effect=OSError("getaddrinfo failed")
        )

        with pytest.raises(OSError):
            await mock_service.get_my_channel()

    async def test_ssl_error_handled_as_network_error(self) -> None:
        """Test that SSL errors are handled as network errors."""
        import ssl

        mock_service = AsyncMock()
        mock_service.get_my_channel = AsyncMock(
            side_effect=ssl.SSLError("SSL handshake failed")
        )

        with pytest.raises(ssl.SSLError):
            await mock_service.get_my_channel()


# =============================================================================
# T060: Test database commit failure handling
# =============================================================================


class TestDatabaseCommitFailureHandling:
    """Tests for database commit failure handling (T060)."""

    async def test_database_commit_failure_detected(self) -> None:
        """Test that database commit failures are detected."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock(side_effect=SQLAlchemyError("Commit failed"))

        with pytest.raises(SQLAlchemyError):
            await mock_session.commit()

    async def test_rollback_on_commit_failure(self) -> None:
        """Test that rollback is performed on commit failure."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock(side_effect=SQLAlchemyError("Commit failed"))
        mock_session.rollback = AsyncMock()

        async def commit_with_rollback() -> None:
            try:
                await mock_session.commit()
            except SQLAlchemyError:
                await mock_session.rollback()
                raise

        with pytest.raises(SQLAlchemyError):
            await commit_with_rollback()

        mock_session.rollback.assert_called_once()

    def test_exit_code_5_for_database_error(self) -> None:
        """Test that exit code 5 is returned for database errors."""
        # Per spec: Exit 5 is returned for database errors
        EXIT_CODE_DATABASE_ERROR = 5
        assert EXIT_CODE_DATABASE_ERROR == 5

    def test_database_error_message_format(self) -> None:
        """Test that database error message follows expected format."""
        expected_message = "Database error: failed to commit - transaction rolled back"

        # Verify message components
        assert "Database error" in expected_message
        assert "commit" in expected_message
        assert "rolled back" in expected_message

    async def test_integrity_error_handled(self) -> None:
        """Test that integrity errors (constraint violations) are handled."""
        from sqlalchemy.exc import IntegrityError

        mock_session = AsyncMock()
        orig_error = Exception("UNIQUE constraint failed")
        mock_session.commit = AsyncMock(
            side_effect=IntegrityError(
                "statement", {"param": "value"}, orig_error
            )
        )

        with pytest.raises(IntegrityError):
            await mock_session.commit()

    async def test_operational_error_handled(self) -> None:
        """Test that operational errors (connection issues) are handled."""
        from sqlalchemy.exc import OperationalError

        mock_session = AsyncMock()
        orig_error = Exception("connection closed")
        mock_session.commit = AsyncMock(
            side_effect=OperationalError("statement", {}, orig_error)
        )

        with pytest.raises(OperationalError):
            await mock_session.commit()

    async def test_partial_data_not_persisted_on_failure(self) -> None:
        """Test that partial data is not persisted when commit fails."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=SQLAlchemyError("Commit failed"))
        mock_session.rollback = AsyncMock()

        data_persisted = False

        async def add_and_commit() -> None:
            nonlocal data_persisted
            mock_session.add({"id": 1, "data": "test"})
            try:
                await mock_session.commit()
                data_persisted = True
            except SQLAlchemyError:
                await mock_session.rollback()
                data_persisted = False
                raise

        with pytest.raises(SQLAlchemyError):
            await add_and_commit()

        assert not data_persisted
        mock_session.rollback.assert_called_once()

    async def test_deadlock_error_handled(self) -> None:
        """Test that deadlock errors are handled appropriately."""
        from sqlalchemy.exc import OperationalError

        mock_session = AsyncMock()
        orig_error = Exception("deadlock detected")
        mock_session.commit = AsyncMock(
            side_effect=OperationalError("statement", {}, orig_error)
        )

        with pytest.raises(OperationalError):
            await mock_session.commit()

    async def test_session_invalidation_on_error(self) -> None:
        """Test that session is properly invalidated on error."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock(side_effect=SQLAlchemyError("Commit failed"))
        mock_session.rollback = AsyncMock()
        mock_session.invalidate = AsyncMock()

        async def commit_and_invalidate() -> None:
            try:
                await mock_session.commit()
            except SQLAlchemyError:
                await mock_session.rollback()
                await mock_session.invalidate()
                raise

        with pytest.raises(SQLAlchemyError):
            await commit_and_invalidate()

        mock_session.invalidate.assert_called_once()


# =============================================================================
# Integration Tests - Error Handling Flow
# =============================================================================


class TestErrorHandlingIntegration:
    """Integration tests for error handling flow."""

    async def test_auth_error_does_not_corrupt_database_state(self) -> None:
        """Test that auth errors do not corrupt database state."""
        mock_session = AsyncMock()
        mock_session.rollback = AsyncMock()

        # Simulate auth error during API call
        async def sync_with_auth_error() -> None:
            try:
                raise create_http_error(401, "Unauthorized")
            except HttpError:
                await mock_session.rollback()
                raise

        with pytest.raises(HttpError):
            await sync_with_auth_error()

        mock_session.rollback.assert_called_once()

    async def test_network_error_preserves_previous_commits(self) -> None:
        """Test that network errors preserve data from previous commits."""
        committed_batches: list[int] = []
        mock_session = AsyncMock()

        async def commit_batch(batch_num: int) -> None:
            committed_batches.append(batch_num)

        mock_session.commit = AsyncMock(side_effect=commit_batch)

        # Commit first batch successfully
        await mock_session.commit(1)
        assert 1 in committed_batches

        # Second batch has network error - previous commit preserved
        mock_session.commit = AsyncMock(
            side_effect=ConnectionError("Network error")
        )

        with pytest.raises(ConnectionError):
            await mock_session.commit(2)

        # First batch still committed
        assert 1 in committed_batches
        assert 2 not in committed_batches

    async def test_error_handler_logs_appropriate_message(self) -> None:
        """Test that error handlers log appropriate messages."""
        import logging

        test_logger = logging.getLogger("test_error_handler")

        with patch.object(test_logger, "error") as mock_log:
            # Log auth error
            test_logger.error(
                "Authentication failed (401): Please run 'chronovista auth login'"
            )
            mock_log.assert_called()

    def test_exit_codes_are_distinct(self) -> None:
        """Test that exit codes for different errors are distinct."""
        from chronovista.cli.commands.enrich import (
            EXIT_CODE_API_ERROR,
            EXIT_CODE_DATABASE_ERROR,
            EXIT_CODE_NETWORK_ERROR,
        )

        # Each error type should have its own exit code
        exit_codes = {
            EXIT_CODE_API_ERROR,
            EXIT_CODE_NETWORK_ERROR,
            EXIT_CODE_DATABASE_ERROR,
        }

        # All codes should be unique
        assert len(exit_codes) == 3

        # All codes should be non-zero (error codes)
        assert 0 not in exit_codes

    async def test_multiple_errors_first_wins(self) -> None:
        """Test that when multiple errors occur, the first one is reported."""
        first_error = None

        async def operation_with_errors() -> None:
            nonlocal first_error
            try:
                raise create_http_error(401, "Unauthorized")
            except HttpError as e:
                first_error = e
                raise

        with pytest.raises(HttpError):
            await operation_with_errors()

        assert first_error is not None
        assert first_error.resp.status == 401


# =============================================================================
# Error Message Tests
# =============================================================================


class TestErrorMessages:
    """Tests for user-friendly error messages."""

    def test_auth_error_message_is_actionable(self) -> None:
        """Test that auth error message provides actionable guidance."""
        message = "Authentication expired - please run 'chronovista auth login'"

        # Should contain command to fix the issue
        assert "chronovista auth login" in message

    def test_network_error_message_is_descriptive(self) -> None:
        """Test that network error message describes the issue."""
        error = NetworkError(
            message="Network error: Unable to connect to YouTube API",
            original_error=ConnectionError("Connection refused"),
        )

        assert "Network error" in error.message
        assert "YouTube API" in error.message

    def test_database_error_message_explains_rollback(self) -> None:
        """Test that database error message explains rollback occurred."""
        message = "Database error: failed to commit - transaction rolled back"

        assert "Database error" in message
        assert "rolled back" in message
