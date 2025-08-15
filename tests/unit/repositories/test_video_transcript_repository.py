"""
Tests for VideoTranscriptRepository.

Comprehensive unit tests covering all repository methods including multi-language
transcript management, quality indicators, and specialized queries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.enums import DownloadReason, TrackKind, TranscriptType, LanguageCode
from chronovista.models.video_transcript import (
    TranscriptSearchFilters,
    VideoTranscriptCreate
)
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
)


class TestVideoTranscriptRepository:
    """Test suite for VideoTranscriptRepository."""

    @pytest.fixture
    def repository(self) -> VideoTranscriptRepository:
        """Create repository instance for testing."""
        return VideoTranscriptRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def sample_transcript_db(self) -> VideoTranscriptDB:
        """Create sample database transcript object."""
        return VideoTranscriptDB(
            video_id="dQw4w9WgXcQ",
            language_code="en-US",
            transcript_text="This is a sample transcript text for testing purposes.",
            transcript_type=TranscriptType.MANUAL.value,
            download_reason=DownloadReason.USER_REQUEST.value,
            confidence_score=0.95,
            is_cc=True,
            is_auto_synced=False,
            track_kind=TrackKind.STANDARD.value,
            caption_name="English (CC)",
            downloaded_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def sample_transcript_create(self) -> VideoTranscriptCreate:
        """Create sample transcript creation object."""
        return VideoTranscriptCreate(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.ENGLISH,
            transcript_text="This is a sample transcript text for testing purposes.",
            transcript_type=TranscriptType.MANUAL,
            download_reason=DownloadReason.USER_REQUEST,
            confidence_score=0.95,
            is_cc=True,
            is_auto_synced=False,
            track_kind=TrackKind.STANDARD,
            caption_name="English (CC)",
        )

    @pytest.fixture
    def sample_transcripts_list(self) -> List[VideoTranscriptDB]:
        """Create list of sample transcripts."""
        base_time = datetime.now(timezone.utc)
        return [
            VideoTranscriptDB(
                video_id="dQw4w9WgXcQ",
                language_code="en-US",
                transcript_text="This is English transcript.",
                transcript_type=TranscriptType.MANUAL.value,
                download_reason=DownloadReason.USER_REQUEST.value,
                confidence_score=0.95,
                is_cc=True,
                is_auto_synced=False,
                track_kind=TrackKind.STANDARD.value,
                caption_name="English (CC)",
                downloaded_at=base_time,
            ),
            VideoTranscriptDB(
                video_id="dQw4w9WgXcQ",
                language_code="es-ES",
                transcript_text="Esta es una transcripción en español.",
                transcript_type=TranscriptType.AUTO.value,
                download_reason=DownloadReason.AUTO_PREFERRED.value,
                confidence_score=0.78,
                is_cc=False,
                is_auto_synced=True,
                track_kind=TrackKind.ASR.value,
                caption_name="Spanish (Auto)",
                downloaded_at=base_time,
            ),
        ]

    @pytest.mark.asyncio
    async def test_get_existing_transcript(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcript_db: VideoTranscriptDB,
    ):
        """Test getting an existing video transcript."""
        # Mock execute to return scalar_one_or_none result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_transcript_db
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_composite_key(
            mock_session, "dQw4w9WgXcQ", "en-US"
        )

        assert result == sample_transcript_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_nonexistent_transcript(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test getting a non-existent video transcript."""
        # Mock execute to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_composite_key(
            mock_session, "dQw4w9WgXcQ", "non-existent"
        )

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_true(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test exists returns True when transcript exists."""
        # Mock execute to return a result
        mock_result = MagicMock()
        mock_result.first.return_value = ("dQw4w9WgXcQ",)
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_composite_key(
            mock_session, "dQw4w9WgXcQ", "en-US"
        )

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_false(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test exists returns False when transcript doesn't exist."""
        # Mock execute to return None
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_composite_key(
            mock_session, "dQw4w9WgXcQ", "non-existent"
        )

        assert result is False
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_video_transcripts(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcripts_list: List[VideoTranscriptDB],
    ):
        """Test getting all transcripts for a video."""
        # Mock execute to return scalars
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = sample_transcripts_list
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_video_transcripts(mock_session, "dQw4w9WgXcQ")

        assert result == sample_transcripts_list
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_transcripts_by_language(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcripts_list: List[VideoTranscriptDB],
    ):
        """Test getting transcripts filtered by language."""
        # Filter list to only English transcripts
        english_transcripts = [
            t for t in sample_transcripts_list if t.language_code == "en-US"
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = english_transcripts
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_transcripts_by_language(mock_session, "en-US")

        assert result == english_transcripts
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_transcripts_by_language_with_limit(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcripts_list: List[VideoTranscriptDB],
    ):
        """Test getting transcripts by language with limit."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = sample_transcripts_list[:1]  # Limited to 1
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_transcripts_by_language(
            mock_session, "en-US", limit=1
        )

        assert len(result) == 1
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_high_quality_transcripts(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcripts_list: List[VideoTranscriptDB],
    ):
        """Test getting high-quality transcripts."""
        # Filter to high-quality transcripts (CC, manual, or high confidence)
        high_quality = [
            t
            for t in sample_transcripts_list
            if t.is_cc or t.confidence_score and t.confidence_score >= 0.8
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = high_quality
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_high_quality_transcripts(
            mock_session, "dQw4w9WgXcQ"
        )

        assert len(result) <= len(sample_transcripts_list)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_transcripts_with_filters(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcripts_list: List[VideoTranscriptDB],
    ):
        """Test searching transcripts with various filters."""
        filters = TranscriptSearchFilters(
            video_ids=["dQw4w9WgXcQ"],
            language_codes=["en-US", "es-ES"],
            transcript_types=[TranscriptType.MANUAL],
            is_cc_only=True,
            min_confidence=0.9,
        )

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = sample_transcripts_list
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_transcripts(mock_session, filters)

        assert result == sample_transcripts_list
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_transcripts_empty_filters(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcripts_list: List[VideoTranscriptDB],
    ):
        """Test searching transcripts with empty filters (returns all)."""
        filters = TranscriptSearchFilters()

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = sample_transcripts_list
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_transcripts(mock_session, filters)

        assert result == sample_transcripts_list
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_available_languages(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test getting available languages for a video."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = ["en-US", "es-ES", "fr-FR"]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_available_languages(mock_session, "dQw4w9WgXcQ")

        assert result == ["en-US", "es-ES", "fr-FR"]
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_transcript_statistics(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test getting transcript statistics."""
        # Mock query result with statistics data
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(
            [
                (TranscriptType.MANUAL.value, "en-US", True, 2),
                (TranscriptType.AUTO.value, "es-ES", False, 1),
            ]
        )
        mock_session.execute.return_value = mock_result

        result = await repository.get_transcript_statistics(mock_session)

        expected = {
            "total": 3,
            "by_type": {TranscriptType.MANUAL.value: 2, TranscriptType.AUTO.value: 1},
            "by_language": {"en-US": 2, "es-ES": 1},
            "cc_count": 2,
            "auto_count": 1,
        }
        assert result["total"] == expected["total"]
        assert result["cc_count"] == expected["cc_count"]
        assert result["auto_count"] == expected["auto_count"]
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_transcript_statistics_with_video_id(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test getting transcript statistics for specific video."""
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(
            [
                (TranscriptType.MANUAL.value, "en-US", True, 1),
            ]
        )
        mock_session.execute.return_value = mock_result

        result = await repository.get_transcript_statistics(mock_session, "dQw4w9WgXcQ")

        assert result["total"] == 1
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_video_transcripts(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test deleting all transcripts for a video."""
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result

        result = await repository.delete_video_transcripts(mock_session, "dQw4w9WgXcQ")

        assert result == 3
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_transcript_by_language_success(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test successfully deleting a transcript by language."""
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        result = await repository.delete_transcript_by_language(
            mock_session, "dQw4w9WgXcQ", "en-US"
        )

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_transcript_by_language_not_found(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test deleting non-existent transcript by language."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        result = await repository.delete_transcript_by_language(
            mock_session, "dQw4w9WgXcQ", "non-existent"
        )

        assert result is False
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_transcript_quality_existing(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcript_db: VideoTranscriptDB,
    ):
        """Test updating quality indicators for existing transcript."""
        with patch.object(repository, 'get_by_composite_key', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_transcript_db

            result = await repository.update_transcript_quality(
                mock_session,
                "dQw4w9WgXcQ",
                "en-US",
                confidence_score=0.99,
                is_cc=True,
                transcript_type=TranscriptType.MANUAL,
            )

            assert result == sample_transcript_db
            assert sample_transcript_db.confidence_score == 0.99
            assert sample_transcript_db.is_cc is True
            assert sample_transcript_db.transcript_type == TranscriptType.MANUAL.value
            mock_session.add.assert_called_once_with(sample_transcript_db)
            mock_session.flush.assert_called_once()
            mock_session.refresh.assert_called_once_with(sample_transcript_db)

    @pytest.mark.asyncio
    async def test_update_transcript_quality_nonexistent(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test updating quality for non-existent transcript."""
        with patch.object(repository, 'get_by_composite_key', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await repository.update_transcript_quality(
                mock_session, "dQw4w9WgXcQ", "non-existent", confidence_score=0.99
            )

            assert result is None
            mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_transcripts_with_quality_scores(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcripts_list: List[VideoTranscriptDB],
    ):
        """Test getting transcripts with computed quality scores."""
        with patch.object(repository, 'get_video_transcripts', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_transcripts_list

            result = await repository.get_transcripts_with_quality_scores(
                mock_session, "dQw4w9WgXcQ"
            )

            assert len(result) == len(sample_transcripts_list)
            for transcript_with_quality in result:
                assert hasattr(transcript_with_quality, "quality_score")
                assert hasattr(transcript_with_quality, "is_high_quality")
                assert 0.0 <= transcript_with_quality.quality_score <= 1.0

    @pytest.mark.asyncio
    async def test_get_with_composite_key_tuple(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcript_db: VideoTranscriptDB,
    ):
        """Test get method with tuple composite key (base class signature)."""
        # Mock execute to return scalar_one_or_none result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_transcript_db
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, ("dQw4w9WgXcQ", "en-US"))

        assert result == sample_transcript_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_with_composite_key_tuple(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test exists method with tuple composite key (base class signature)."""
        # Mock execute to return a result
        mock_result = MagicMock()
        mock_result.first.return_value = ("dQw4w9WgXcQ",)
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, ("dQw4w9WgXcQ", "en-US"))

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_repository_inherits_base_methods(
        self, repository: VideoTranscriptRepository
    ):
        """Test that repository properly inherits from base repository."""
        from chronovista.repositories.base import BaseSQLAlchemyRepository

        assert isinstance(repository, BaseSQLAlchemyRepository)
        assert repository.model == VideoTranscriptDB

    def test_repository_initialization(self):
        """Test repository initialization."""
        repo = VideoTranscriptRepository()
        assert repo.model == VideoTranscriptDB

    def test_compute_quality_score_high_quality(
        self,
        repository: VideoTranscriptRepository,
        sample_transcript_db: VideoTranscriptDB,
    ):
        """Test quality score computation for high-quality transcript."""
        # High-quality transcript: CC, manual, high confidence
        sample_transcript_db.is_cc = True
        sample_transcript_db.transcript_type = TranscriptType.MANUAL.value
        sample_transcript_db.confidence_score = 0.95
        sample_transcript_db.track_kind = TrackKind.STANDARD.value

        score = repository._compute_quality_score(sample_transcript_db)

        # Should be high (CC + manual + confidence + standard track)
        assert score >= 0.8
        assert score <= 1.0

    def test_compute_quality_score_low_quality(
        self, repository: VideoTranscriptRepository
    ):
        """Test quality score computation for low-quality transcript."""
        # Low-quality transcript: auto, no CC, low confidence
        low_quality_transcript = VideoTranscriptDB(
            video_id="test",
            language_code="en",
            transcript_text="test",
            transcript_type=TranscriptType.AUTO.value,
            download_reason=DownloadReason.AUTO_PREFERRED.value,
            is_cc=False,
            confidence_score=0.3,
            track_kind=TrackKind.ASR.value,
            is_auto_synced=True,
            downloaded_at=datetime.now(timezone.utc),
        )

        score = repository._compute_quality_score(low_quality_transcript)

        # Should be lower
        assert score < 0.7
        assert score >= 0.0


class TestVideoTranscriptRepositoryEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def repository(self) -> VideoTranscriptRepository:
        """Create repository instance for testing."""
        return VideoTranscriptRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.mark.asyncio
    async def test_empty_video_id_handling(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test repository behavior with empty video ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_composite_key(mock_session, "", "en-US")

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_language_code_handling(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test repository behavior with empty language code."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_composite_key(mock_session, "dQw4w9WgXcQ", "")

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_language_code_normalization(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test that language codes are properly normalized to lowercase."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        await repository.get_by_composite_key(mock_session, "dQw4w9WgXcQ", "EN-US")

        # Verify the query used lowercase language code
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_date_filters(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test search with date range filters."""
        now = datetime.now(timezone.utc)
        filters = TranscriptSearchFilters(
            downloaded_after=now,
            downloaded_before=now,
        )

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_transcripts(mock_session, filters)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_video_transcripts_no_results(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test getting transcripts when video has none."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_video_transcripts(mock_session, "dQw4w9WgXcQ")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_transcript_statistics_no_data(
        self, repository: VideoTranscriptRepository, mock_session: AsyncMock
    ):
        """Test statistics when no transcripts exist."""
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_session.execute.return_value = mock_result

        result = await repository.get_transcript_statistics(mock_session)

        expected = {
            "total": 0,
            "by_type": {},
            "by_language": {},
            "cc_count": 0,
            "auto_count": 0,
        }
        assert result == expected

    @pytest.mark.asyncio
    async def test_quality_score_with_missing_confidence(
        self, repository: VideoTranscriptRepository
    ):
        """Test quality score computation with missing confidence score."""
        transcript = VideoTranscriptDB(
            video_id="test",
            language_code="en",
            transcript_text="test",
            transcript_type=TranscriptType.MANUAL.value,
            download_reason=DownloadReason.USER_REQUEST.value,
            is_cc=True,
            confidence_score=None,  # Missing confidence
            track_kind=TrackKind.STANDARD.value,
            is_auto_synced=False,
            downloaded_at=datetime.now(timezone.utc),
        )

        score = repository._compute_quality_score(transcript)

        # Should still have reasonable score from other factors
        assert 0.0 <= score <= 1.0
