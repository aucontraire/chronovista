"""Unit tests for API dependencies."""

from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

# CRITICAL: This line ensures async tests work with coverage


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
                async for _session in get_db():
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


class TestGetStatsRepositories:
    """Tests for the get_stats_repositories dependency (issue #256)."""

    def test_wires_each_field_to_its_repository_type(self) -> None:
        """Each StatsRepositories field is the correct concrete repository type.

        Guards against a transposition bug in the bundle (e.g. wiring the
        playlist factory into the channel field), which would silently count the
        wrong table yet pass every mock-based settings test.
        """
        from chronovista.api.deps import StatsRepositories, get_stats_repositories
        from chronovista.repositories import (
            CanonicalTagRepository,
            ChannelRepository,
            PlaylistRepository,
            VideoRepository,
            VideoTranscriptRepository,
        )
        from chronovista.repositories.transcript_correction_repository import (
            TranscriptCorrectionRepository,
        )

        repos = get_stats_repositories()

        assert isinstance(repos, StatsRepositories)
        assert isinstance(repos.video, VideoRepository)
        assert isinstance(repos.channel, ChannelRepository)
        assert isinstance(repos.playlist, PlaylistRepository)
        assert isinstance(repos.transcript, VideoTranscriptRepository)
        assert isinstance(repos.correction, TranscriptCorrectionRepository)
        assert isinstance(repos.canonical_tag, CanonicalTagRepository)


class TestRepositoryAndServiceDependencies:
    """Tests for the repository/service dependencies added for issue #256."""

    def test_get_video_repository_returns_video_repository(self) -> None:
        from chronovista.api.deps import get_video_repository
        from chronovista.repositories import VideoRepository

        assert isinstance(get_video_repository(), VideoRepository)

    def test_get_canonical_tag_repository_returns_correct_type(self) -> None:
        from chronovista.api.deps import get_canonical_tag_repository
        from chronovista.repositories import CanonicalTagRepository

        assert isinstance(get_canonical_tag_repository(), CanonicalTagRepository)

    def test_get_transcript_segment_repository_returns_correct_type(self) -> None:
        from chronovista.api.deps import get_transcript_segment_repository
        from chronovista.repositories import TranscriptSegmentRepository

        assert isinstance(
            get_transcript_segment_repository(), TranscriptSegmentRepository
        )

    def test_get_transcript_correction_repository_returns_correct_type(self) -> None:
        from chronovista.api.deps import get_transcript_correction_repository
        from chronovista.repositories.transcript_correction_repository import (
            TranscriptCorrectionRepository,
        )

        assert isinstance(
            get_transcript_correction_repository(), TranscriptCorrectionRepository
        )

    def test_get_transcript_correction_service_wires_correct_repos(self) -> None:
        """The service is built with the three correct repository types.

        Guards against a wiring transposition (e.g. passing the transcript repo
        where the segment repo belongs), which mock-based endpoint tests miss.
        """
        from chronovista.api.deps import get_transcript_correction_service
        from chronovista.repositories import (
            TranscriptSegmentRepository,
            VideoTranscriptRepository,
        )
        from chronovista.repositories.transcript_correction_repository import (
            TranscriptCorrectionRepository,
        )
        from chronovista.services.transcript_correction_service import (
            TranscriptCorrectionService,
        )

        service = get_transcript_correction_service()

        assert isinstance(service, TranscriptCorrectionService)
        assert isinstance(service._correction_repo, TranscriptCorrectionRepository)
        assert isinstance(service._segment_repo, TranscriptSegmentRepository)
        assert isinstance(service._transcript_repo, VideoTranscriptRepository)


class TestBatchAndEntityDependencies:
    """Tests for the batch/entity dependencies added for issue #256."""

    def test_get_named_entity_repository_returns_correct_type(self) -> None:
        from chronovista.api.deps import get_named_entity_repository
        from chronovista.repositories import NamedEntityRepository

        assert isinstance(get_named_entity_repository(), NamedEntityRepository)

    def test_get_batch_correction_service_wires_correct_types(self) -> None:
        """The batch service is built with the correct repo/service types.

        Guards against a wiring transposition in the composed dependency, which
        mock-based endpoint tests (they override the whole service) would miss.
        """
        from chronovista.api.deps import get_batch_correction_service
        from chronovista.repositories.transcript_correction_repository import (
            TranscriptCorrectionRepository,
        )
        from chronovista.repositories.transcript_segment_repository import (
            TranscriptSegmentRepository,
        )
        from chronovista.services.batch_correction_service import (
            BatchCorrectionService,
        )
        from chronovista.services.transcript_correction_service import (
            TranscriptCorrectionService,
        )

        service = get_batch_correction_service()

        assert isinstance(service, BatchCorrectionService)
        assert isinstance(service._correction_repo, TranscriptCorrectionRepository)
        assert isinstance(service._segment_repo, TranscriptSegmentRepository)
        assert isinstance(service._correction_service, TranscriptCorrectionService)
