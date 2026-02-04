"""Unit tests for API dependencies."""
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


class TestGetDb:
    """Tests for get_db dependency."""

    async def test_get_db_yields_session(self) -> None:
        """Test that get_db yields a database session."""
        from chronovista.api.deps import get_db

        mock_session = AsyncMock()

        async def mock_get_session():
            yield mock_session

        with patch("chronovista.api.deps.db_manager") as mock_db:
            mock_db.get_session = mock_get_session

            async for session in get_db():
                assert session == mock_session

    async def test_get_db_can_be_called_multiple_times(self) -> None:
        """Test that get_db can be called multiple times successfully."""
        from chronovista.api.deps import get_db

        mock_session = AsyncMock()

        async def mock_get_session():
            yield mock_session

        with patch("chronovista.api.deps.db_manager") as mock_db:
            mock_db.get_session = mock_get_session

            # First call
            async for session in get_db():
                assert session == mock_session
                break

            # Second call should also work
            async for session in get_db():
                assert session == mock_session
                break

    async def test_get_db_propagates_database_errors(self) -> None:
        """Test that get_db propagates database connection errors."""
        from chronovista.api.deps import get_db

        async def mock_get_session():
            raise ConnectionError("Database unavailable")
            yield  # type: ignore[unreachable]  # Unreachable, but needed for async generator syntax

        with patch("chronovista.api.deps.db_manager") as mock_db:
            mock_db.get_session = mock_get_session

            with pytest.raises(ConnectionError, match="Database unavailable"):
                async for session in get_db():
                    pass


class TestRequireAuth:
    """Tests for require_auth dependency."""

    async def test_require_auth_passes_when_authenticated(self) -> None:
        """Test require_auth passes when user is authenticated."""
        from chronovista.api.deps import require_auth

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Should not raise
            await require_auth()
            # Function returns None, no assertion needed

    async def test_require_auth_raises_401_when_not_authenticated(self) -> None:
        """Test require_auth raises HTTPException when not authenticated."""
        from chronovista.api.deps import require_auth

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False

            with pytest.raises(HTTPException) as exc_info:
                await require_auth()

            assert exc_info.value.status_code == 401
            detail = cast(dict[str, Any], exc_info.value.detail)
            assert detail["code"] == "NOT_AUTHENTICATED"
            assert "chronovista auth login" in detail["message"]

    async def test_require_auth_checks_oauth_service(self) -> None:
        """Test require_auth calls is_authenticated on oauth service."""
        from chronovista.api.deps import require_auth

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            await require_auth()

            # Verify is_authenticated was called
            mock_oauth.is_authenticated.assert_called_once()

    async def test_require_auth_error_message_format(self) -> None:
        """Test require_auth returns properly formatted error message."""
        from chronovista.api.deps import require_auth

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False

            with pytest.raises(HTTPException) as exc_info:
                await require_auth()

            # Verify error structure
            detail = cast(dict[str, Any], exc_info.value.detail)
            assert "code" in detail
            assert "message" in detail
            assert detail["code"] == "NOT_AUTHENTICATED"

    async def test_require_auth_multiple_calls_when_authenticated(self) -> None:
        """Test require_auth can be called multiple times when authenticated."""
        from chronovista.api.deps import require_auth

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Should not raise on multiple calls
            await require_auth()
            await require_auth()
            await require_auth()

            # Verify called three times
            assert mock_oauth.is_authenticated.call_count == 3

    async def test_require_auth_multiple_calls_when_not_authenticated(self) -> None:
        """Test require_auth consistently raises on multiple calls when not authenticated."""
        from chronovista.api.deps import require_auth

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False

            # All calls should raise
            with pytest.raises(HTTPException):
                await require_auth()

            with pytest.raises(HTTPException):
                await require_auth()

            with pytest.raises(HTTPException):
                await require_auth()

            assert mock_oauth.is_authenticated.call_count == 3
