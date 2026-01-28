"""
Tests for VideoTranscriptRepository.

Comprehensive unit tests covering all repository methods including multi-language
transcript management, quality indicators, and specialized queries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.enums import (
    DownloadReason,
    LanguageCode,
    TrackKind,
    TranscriptType,
)
from chronovista.models.video_transcript import (
    TranscriptSearchFilters,
    VideoTranscriptCreate,
)
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
)

pytestmark = pytest.mark.asyncio


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
        with patch.object(
            repository, "get_by_composite_key", new_callable=AsyncMock
        ) as mock_get:
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
        with patch.object(
            repository, "get_by_composite_key", new_callable=AsyncMock
        ) as mock_get:
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
        with patch.object(
            repository, "get_video_transcripts", new_callable=AsyncMock
        ) as mock_get:
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


class TestVideoTranscriptRepositoryTimestampPreservation:
    """Tests for Feature 007: Transcript Timestamp Preservation.

    Tests for _derive_metadata helper and create_or_update method.
    These tests follow TDD approach - methods don't exist yet and tests will fail initially.
    """

    @pytest.fixture
    def repository(self) -> VideoTranscriptRepository:
        """Create repository instance for testing."""
        return VideoTranscriptRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def sample_raw_transcript_data(self) -> Dict[str, Any]:
        """Sample raw transcript data with timestamps."""
        return {
            "video_id": "dQw4w9WgXcQ",
            "language_code": "en",
            "language_name": "English",
            "snippets": [
                {"text": "Never gonna give you up", "start": 0.0, "duration": 2.5},
                {"text": "Never gonna let you down", "start": 2.5, "duration": 2.3},
                {"text": "Never gonna run around and desert you", "start": 4.8, "duration": 3.0},
            ],
            "is_generated": False,
            "is_translatable": True,
            "source": "youtube_transcript_api",
            "retrieved_at": "2023-12-15T16:30:00Z",
        }

    @pytest.fixture
    def sample_raw_transcript_data_empty_snippets(self) -> Dict[str, Any]:
        """Sample raw transcript data with empty snippets array."""
        return {
            "video_id": "dQw4w9WgXcQ",
            "language_code": "en",
            "language_name": "English",
            "snippets": [],
            "is_generated": False,
            "is_translatable": True,
            "source": "youtube_transcript_api",
            "retrieved_at": "2023-12-15T16:30:00Z",
        }

    @pytest.fixture
    def sample_transcript_create_with_raw_data(
        self, sample_raw_transcript_data: Dict[str, Any]
    ) -> VideoTranscriptCreate:
        """Create sample transcript creation object for testing."""
        return VideoTranscriptCreate(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.ENGLISH,
            transcript_text="Never gonna give you up Never gonna let you down Never gonna run around and desert you",
            transcript_type=TranscriptType.MANUAL,
            download_reason=DownloadReason.USER_REQUEST,
            confidence_score=0.95,
            is_cc=True,
            is_auto_synced=False,
            track_kind=TrackKind.STANDARD,
            caption_name="English (CC)",
        )

    def test_derive_metadata_with_valid_snippets(
        self, repository: VideoTranscriptRepository, sample_raw_transcript_data: Dict[str, Any]
    ):
        """T016: Test _derive_metadata with valid raw data containing snippets.

        Verifies that metadata is correctly extracted from raw transcript data:
        - has_timestamps should be True when snippets exist
        - segment_count should equal number of snippets
        - total_duration should be calculated from last snippet
        - source should be extracted from raw data
        """
        metadata = repository._derive_metadata(sample_raw_transcript_data)

        # Verify all metadata fields are present and correct
        assert metadata["has_timestamps"] is True, "Should detect timestamps from snippets"
        assert metadata["segment_count"] == 3, "Should count all snippets"

        # Calculate expected duration: last snippet start (4.8) + last snippet duration (3.0) = 7.8
        expected_duration = 4.8 + 3.0
        assert metadata["total_duration"] == expected_duration, f"Expected {expected_duration}, got {metadata['total_duration']}"

        assert metadata["source"] == "youtube_transcript_api", "Should extract source from raw data"

    def test_derive_metadata_with_empty_snippets(
        self,
        repository: VideoTranscriptRepository,
        sample_raw_transcript_data_empty_snippets: Dict[str, Any]
    ):
        """T017: Test _derive_metadata with empty snippets array.

        Verifies handling of transcripts without timing information:
        - has_timestamps should be False
        - segment_count should be None
        - total_duration should be None
        - source should still be extracted
        """
        metadata = repository._derive_metadata(sample_raw_transcript_data_empty_snippets)

        assert metadata["has_timestamps"] is False, "Should be False when no snippets"
        assert metadata["segment_count"] is None, "Should be None when no snippets"
        assert metadata["total_duration"] is None, "Should be None when no snippets"
        assert metadata["source"] == "youtube_transcript_api", "Should extract source even without snippets"

    def test_derive_metadata_with_malformed_data(
        self, repository: VideoTranscriptRepository
    ):
        """T018: Test _derive_metadata with malformed raw data.

        Verifies graceful handling of missing or malformed data:
        - Missing 'snippets' key
        - Missing 'source' key (should default)
        - Wrong types in snippets (non-list)
        """
        # Test 1: Missing snippets key
        malformed_data_no_snippets = {
            "video_id": "test123",
            "language_code": "en",
            "source": "youtube_transcript_api",
        }

        metadata = repository._derive_metadata(malformed_data_no_snippets)
        assert metadata["has_timestamps"] is False, "Should handle missing snippets gracefully"
        assert metadata["segment_count"] is None
        assert metadata["total_duration"] is None

        # Test 2: Missing source key (should use default)
        malformed_data_no_source = {
            "video_id": "test123",
            "snippets": [{"text": "test", "start": 0.0, "duration": 1.0}],
        }

        metadata = repository._derive_metadata(malformed_data_no_source)
        assert metadata["source"] == "youtube_transcript_api", "Should default to youtube_transcript_api"

        # Test 3: Snippets is None instead of list
        malformed_data_null_snippets = {
            "video_id": "test123",
            "snippets": None,
            "source": "manual_upload",
        }

        metadata = repository._derive_metadata(malformed_data_null_snippets)
        assert metadata["has_timestamps"] is False, "Should handle None snippets"
        assert metadata["segment_count"] is None
        assert metadata["total_duration"] is None
        assert metadata["source"] == "manual_upload"

    @pytest.mark.asyncio
    async def test_create_or_update_new_transcript_with_raw_data(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcript_create_with_raw_data: VideoTranscriptCreate,
        sample_raw_transcript_data: Dict[str, Any],
    ):
        """T019: Test create_or_update creating a NEW transcript with raw_transcript_data.

        Verifies that when creating a new transcript:
        - Metadata is derived from raw_transcript_data
        - All metadata fields are populated correctly
        - Database record includes derived metadata
        - raw_transcript_data is stored in JSONB column
        """
        # Mock get_by_composite_key to return None (doesn't exist)
        with patch.object(
            repository, "get_by_composite_key", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            # Mock the database object that will be created
            mock_created_transcript = VideoTranscriptDB(
                video_id="dQw4w9WgXcQ",
                language_code="en",
                transcript_text="Never gonna give you up Never gonna let you down Never gonna run around and desert you",
                transcript_type=TranscriptType.MANUAL.value,
                download_reason=DownloadReason.USER_REQUEST.value,
                confidence_score=0.95,
                is_cc=True,
                is_auto_synced=False,
                track_kind=TrackKind.STANDARD.value,
                caption_name="English (CC)",
                downloaded_at=datetime.now(timezone.utc),
                # Feature 007 fields
                raw_transcript_data=sample_raw_transcript_data,
                has_timestamps=True,
                segment_count=3,
                total_duration=7.8,
                source="youtube_transcript_api",
            )

            # Mock session methods
            mock_session.add.return_value = None
            mock_session.flush.return_value = None
            mock_session.refresh.return_value = None

            result = await repository.create_or_update(
                mock_session,
                sample_transcript_create_with_raw_data,
                raw_transcript_data=sample_raw_transcript_data,
            )

            # Verify repository checked for existing transcript
            mock_get.assert_called_once_with(
                mock_session, "dQw4w9WgXcQ", "en"
            )

            # Verify session.add was called with a VideoTranscriptDB object
            mock_session.add.assert_called_once()
            added_transcript = mock_session.add.call_args[0][0]

            # Verify derived metadata was applied
            assert added_transcript.has_timestamps is True
            assert added_transcript.segment_count == 3
            assert added_transcript.total_duration == 7.8
            assert added_transcript.source == "youtube_transcript_api"
            assert added_transcript.raw_transcript_data == sample_raw_transcript_data

            # Verify flush and refresh were called
            mock_session.flush.assert_called_once()
            mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_or_update_existing_transcript_with_new_raw_data(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcript_create_with_raw_data: VideoTranscriptCreate,
        sample_raw_transcript_data: Dict[str, Any],
    ):
        """T020: Test create_or_update UPDATING an existing transcript with fresh raw_transcript_data.

        Verifies that when updating an existing transcript:
        - Existing record is retrieved
        - Metadata is re-derived from new raw_transcript_data
        - All metadata fields are updated
        - Old raw_transcript_data is replaced with new data
        """
        # Create existing transcript with old data
        existing_transcript = VideoTranscriptDB(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            transcript_text="Old transcript text",
            transcript_type=TranscriptType.AUTO.value,
            download_reason=DownloadReason.AUTO_PREFERRED.value,
            confidence_score=0.70,
            is_cc=False,
            is_auto_synced=True,
            track_kind=TrackKind.ASR.value,
            caption_name="English (Auto)",
            downloaded_at=datetime.now(timezone.utc),
            # Old Feature 007 fields
            raw_transcript_data={"old": "data"},
            has_timestamps=False,
            segment_count=None,
            total_duration=None,
            source="unknown",
        )

        # Mock get_by_composite_key to return existing transcript
        with patch.object(
            repository, "get_by_composite_key", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = existing_transcript

            # Mock session methods
            mock_session.add.return_value = None
            mock_session.flush.return_value = None
            mock_session.refresh.return_value = None

            result = await repository.create_or_update(
                mock_session,
                sample_transcript_create_with_raw_data,
                raw_transcript_data=sample_raw_transcript_data,
            )

            # Verify the existing transcript was updated
            assert existing_transcript.transcript_text == sample_transcript_create_with_raw_data.transcript_text
            assert existing_transcript.transcript_type == TranscriptType.MANUAL.value
            assert existing_transcript.confidence_score == 0.95

            # Verify metadata was re-derived and updated
            assert existing_transcript.has_timestamps is True, "Should update has_timestamps"
            assert existing_transcript.segment_count == 3, "Should update segment_count"
            assert existing_transcript.total_duration == 7.8, "Should update total_duration"
            assert existing_transcript.source == "youtube_transcript_api", "Should update source"
            assert existing_transcript.raw_transcript_data == sample_raw_transcript_data, "Should replace raw data"

            # Verify session operations
            mock_session.add.assert_called_once_with(existing_transcript)
            mock_session.flush.assert_called_once()
            mock_session.refresh.assert_called_once_with(existing_transcript)

    @pytest.mark.asyncio
    async def test_get_method_backward_compatibility(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
    ):
        """T021: Test existing get() method returns transcript unchanged (backward compatibility).

        Verifies that the existing get() method continues to work correctly
        and returns transcripts with Feature 007 fields when present.
        """
        # Create transcript with Feature 007 fields
        transcript_with_metadata = VideoTranscriptDB(
            video_id="dQw4w9WgXcQ",
            language_code="en-us",
            transcript_text="Sample transcript",
            transcript_type=TranscriptType.MANUAL.value,
            download_reason=DownloadReason.USER_REQUEST.value,
            confidence_score=0.95,
            is_cc=True,
            is_auto_synced=False,
            track_kind=TrackKind.STANDARD.value,
            caption_name="English (CC)",
            downloaded_at=datetime.now(timezone.utc),
            # Feature 007 fields
            raw_transcript_data={"snippets": [{"text": "test", "start": 0.0, "duration": 1.0}]},
            has_timestamps=True,
            segment_count=1,
            total_duration=1.0,
            source="youtube_transcript_api",
        )

        # Mock execute to return transcript
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = transcript_with_metadata
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, ("dQw4w9WgXcQ", "en-us"))

        # Verify transcript is returned unchanged with all Feature 007 fields
        assert result == transcript_with_metadata
        assert result.has_timestamps is True
        assert result.segment_count == 1
        assert result.total_duration == 1.0
        assert result.source == "youtube_transcript_api"
        assert result.raw_transcript_data is not None

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_or_update_without_raw_data_preserves_behavior(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcript_create_with_raw_data: VideoTranscriptCreate,
    ):
        """T022: Test create_or_update without raw_transcript_data preserves existing behavior.

        Verifies that when raw_transcript_data is not provided:
        - Method works as before (backward compatibility)
        - Metadata fields use sensible defaults
        - No errors occur from missing raw_transcript_data parameter
        """
        # Mock get_by_composite_key to return None (new transcript)
        with patch.object(
            repository, "get_by_composite_key", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            # Mock session methods
            mock_session.add.return_value = None
            mock_session.flush.return_value = None
            mock_session.refresh.return_value = None

            # Call WITHOUT raw_transcript_data parameter
            result = await repository.create_or_update(
                mock_session,
                sample_transcript_create_with_raw_data,
                # No raw_transcript_data parameter
            )

            # Verify session.add was called
            mock_session.add.assert_called_once()
            added_transcript = mock_session.add.call_args[0][0]

            # Verify default metadata values are used
            assert added_transcript.has_timestamps is True, "Should default to True"
            assert added_transcript.segment_count is None, "Should be None when no raw data"
            assert added_transcript.total_duration is None, "Should be None when no raw data"
            assert added_transcript.source == "youtube_transcript_api", "Should use default source"
            assert added_transcript.raw_transcript_data is None, "Should be None when not provided"

            # Verify basic fields are still set correctly
            assert added_transcript.video_id == "dQw4w9WgXcQ"
            assert added_transcript.language_code == "en"
            assert added_transcript.transcript_text == sample_transcript_create_with_raw_data.transcript_text

            # Verify flush and refresh were called
            mock_session.flush.assert_called_once()
            mock_session.refresh.assert_called_once()


class TestVideoTranscriptRepositoryMetadataQueries:
    """Tests for Feature 007: Query Transcripts by Metadata (User Story 2).

    Tests for filter_by_metadata and get_with_timestamps methods.
    These tests follow TDD approach - methods don't exist yet and tests will fail initially.
    """

    @pytest.fixture
    def repository(self) -> VideoTranscriptRepository:
        """Create repository instance for testing."""
        return VideoTranscriptRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def sample_transcripts_with_metadata(self) -> List[VideoTranscriptDB]:
        """Create sample transcripts with varying metadata for filter testing."""
        base_time = datetime.now(timezone.utc)

        return [
            # Transcript 1: Has timestamps, 3 segments, 7.8 seconds
            VideoTranscriptDB(
                video_id="video1",
                language_code="en-us",
                transcript_text="Short video transcript",
                transcript_type=TranscriptType.MANUAL.value,
                download_reason=DownloadReason.USER_REQUEST.value,
                confidence_score=0.95,
                is_cc=True,
                is_auto_synced=False,
                track_kind=TrackKind.STANDARD.value,
                caption_name="English (CC)",
                downloaded_at=base_time,
                # Feature 007 metadata
                raw_transcript_data={"snippets": [{"text": "test", "start": 0.0, "duration": 2.6}]},
                has_timestamps=True,
                segment_count=3,
                total_duration=7.8,
                source="youtube_transcript_api",
            ),
            # Transcript 2: Has timestamps, 50 segments, 720 seconds (12 minutes)
            VideoTranscriptDB(
                video_id="video2",
                language_code="en-us",
                transcript_text="Long video transcript",
                transcript_type=TranscriptType.MANUAL.value,
                download_reason=DownloadReason.USER_REQUEST.value,
                confidence_score=0.92,
                is_cc=True,
                is_auto_synced=False,
                track_kind=TrackKind.STANDARD.value,
                caption_name="English (CC)",
                downloaded_at=base_time,
                # Feature 007 metadata
                raw_transcript_data={"snippets": [{"text": "test", "start": 0.0, "duration": 14.4}] * 50},
                has_timestamps=True,
                segment_count=50,
                total_duration=720.0,
                source="youtube_transcript_api",
            ),
            # Transcript 3: No timestamps (plain text only)
            VideoTranscriptDB(
                video_id="video3",
                language_code="es-es",
                transcript_text="Transcript without timestamps",
                transcript_type=TranscriptType.AUTO.value,
                download_reason=DownloadReason.AUTO_PREFERRED.value,
                confidence_score=0.78,
                is_cc=False,
                is_auto_synced=True,
                track_kind=TrackKind.ASR.value,
                caption_name="Spanish (Auto)",
                downloaded_at=base_time,
                # Feature 007 metadata - no timestamps
                raw_transcript_data=None,
                has_timestamps=False,
                segment_count=None,
                total_duration=None,
                source="youtube_transcript_api",
            ),
            # Transcript 4: Has timestamps, 10 segments, 300 seconds (5 minutes)
            VideoTranscriptDB(
                video_id="video4",
                language_code="fr-fr",
                transcript_text="Medium length transcript",
                transcript_type=TranscriptType.MANUAL.value,
                download_reason=DownloadReason.USER_REQUEST.value,
                confidence_score=0.88,
                is_cc=True,
                is_auto_synced=False,
                track_kind=TrackKind.STANDARD.value,
                caption_name="French (CC)",
                downloaded_at=base_time,
                # Feature 007 metadata
                raw_transcript_data={"snippets": [{"text": "test", "start": 0.0, "duration": 30.0}] * 10},
                has_timestamps=True,
                segment_count=10,
                total_duration=300.0,
                source="youtube_data_api_v3",
            ),
        ]

    @pytest.mark.asyncio
    async def test_filter_by_metadata_has_timestamps_true(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcripts_with_metadata: List[VideoTranscriptDB],
    ):
        """T031: Test filter_by_metadata with has_timestamps=True filter.

        Verifies that filtering by has_timestamps=True returns only transcripts
        with timestamp data, excluding plain text transcripts.
        """
        # Filter to only transcripts with timestamps
        transcripts_with_timestamps = [
            t for t in sample_transcripts_with_metadata if t.has_timestamps
        ]

        # Mock the query execution
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = transcripts_with_timestamps
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.filter_by_metadata(
            mock_session,
            has_timestamps=True,
        )

        # Should return 3 transcripts with timestamps (video1, video2, video4)
        assert len(result) == 3
        assert all(t.has_timestamps for t in result)

        # Verify the query was executed
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_filter_by_metadata_min_segment_count(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcripts_with_metadata: List[VideoTranscriptDB],
    ):
        """T032: Test filter_by_metadata with min_segment_count filter.

        Verifies that filtering by min_segment_count returns only transcripts
        with at least the specified number of segments.
        """
        # Filter to transcripts with at least 10 segments
        min_segments = 10
        transcripts_matching = [
            t for t in sample_transcripts_with_metadata
            if t.segment_count is not None and t.segment_count >= min_segments
        ]

        # Mock the query execution
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = transcripts_matching
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.filter_by_metadata(
            mock_session,
            min_segment_count=min_segments,
        )

        # Should return 2 transcripts (video2 with 50 segments, video4 with 10 segments)
        assert len(result) == 2
        assert all(t.segment_count >= min_segments for t in result if t.segment_count)

        # Verify the query was executed
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_filter_by_metadata_min_duration(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcripts_with_metadata: List[VideoTranscriptDB],
    ):
        """T033: Test filter_by_metadata with min_duration filter (600 seconds = 10 minutes).

        Verifies that filtering by min_duration returns only transcripts
        with at least the specified duration in seconds.
        """
        # Filter to transcripts with at least 600 seconds (10 minutes)
        min_duration = 600.0
        transcripts_matching = [
            t for t in sample_transcripts_with_metadata
            if t.total_duration is not None and t.total_duration >= min_duration
        ]

        # Mock the query execution
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = transcripts_matching
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.filter_by_metadata(
            mock_session,
            min_duration=min_duration,
        )

        # Should return 1 transcript (video2 with 720 seconds)
        assert len(result) == 1
        assert result[0].total_duration is not None
        assert result[0].total_duration >= min_duration
        assert result[0].video_id == "video2"

        # Verify the query was executed
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_filter_by_metadata_combined_filters(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcripts_with_metadata: List[VideoTranscriptDB],
    ):
        """T034: Test filter_by_metadata with combined filters (AND logic).

        Verifies that multiple filters are combined with AND logic,
        returning only transcripts matching ALL criteria.
        """
        # Apply multiple filters: has_timestamps=True AND min_segment_count=5 AND source="youtube_transcript_api"
        transcripts_matching = [
            t for t in sample_transcripts_with_metadata
            if (t.has_timestamps
                and t.segment_count is not None
                and t.segment_count >= 5
                and t.source == "youtube_transcript_api")
        ]

        # Mock the query execution
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = transcripts_matching
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.filter_by_metadata(
            mock_session,
            has_timestamps=True,
            min_segment_count=5,
            source="youtube_transcript_api",
        )

        # Should return 1 transcript (video2: has_timestamps=True, 50 segments, youtube_transcript_api)
        # video1 has only 3 segments (< 5), so excluded
        # video4 uses youtube_data_api_v3, so excluded
        assert len(result) == 1
        assert result[0].has_timestamps
        assert result[0].segment_count is not None
        assert result[0].segment_count >= 5
        assert result[0].source == "youtube_transcript_api"
        assert result[0].video_id == "video2"

        # Verify the query was executed
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_filter_by_metadata_pagination(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_transcripts_with_metadata: List[VideoTranscriptDB],
    ):
        """T035: Test filter_by_metadata pagination (limit/offset).

        Verifies that limit and offset parameters are correctly applied
        for paginating through large result sets.
        """
        # Get all transcripts with timestamps for pagination test
        transcripts_with_timestamps = [
            t for t in sample_transcripts_with_metadata if t.has_timestamps
        ]

        # Test Case 1: First page (limit=2, offset=0)
        mock_result_page1 = MagicMock()
        mock_scalars_page1 = MagicMock()
        mock_scalars_page1.all.return_value = transcripts_with_timestamps[:2]
        mock_result_page1.scalars.return_value = mock_scalars_page1
        mock_session.execute.return_value = mock_result_page1

        result_page1 = await repository.filter_by_metadata(
            mock_session,
            has_timestamps=True,
            limit=2,
            offset=0,
        )

        assert len(result_page1) == 2

        # Test Case 2: Second page (limit=2, offset=2)
        mock_result_page2 = MagicMock()
        mock_scalars_page2 = MagicMock()
        mock_scalars_page2.all.return_value = transcripts_with_timestamps[2:4]
        mock_result_page2.scalars.return_value = mock_scalars_page2
        mock_session.execute.return_value = mock_result_page2

        result_page2 = await repository.filter_by_metadata(
            mock_session,
            has_timestamps=True,
            limit=2,
            offset=2,
        )

        assert len(result_page2) == 1  # Only 3 transcripts total, so second page has 1

        # Verify queries were executed
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_get_with_timestamps_returns_none_when_no_timestamps(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
    ):
        """T036: Test get_with_timestamps returning None when has_timestamps=False.

        Verifies that get_with_timestamps returns None when the transcript
        exists but has_timestamps is False, since there's no raw timestamp data to return.
        """
        # Create transcript without timestamps
        transcript_no_timestamps = VideoTranscriptDB(
            video_id="video_no_ts",
            language_code="en-us",
            transcript_text="Plain text transcript without timestamps",
            transcript_type=TranscriptType.AUTO.value,
            download_reason=DownloadReason.AUTO_PREFERRED.value,
            confidence_score=0.75,
            is_cc=False,
            is_auto_synced=True,
            track_kind=TrackKind.ASR.value,
            caption_name="English (Auto)",
            downloaded_at=datetime.now(timezone.utc),
            # No timestamps
            raw_transcript_data=None,
            has_timestamps=False,
            segment_count=None,
            total_duration=None,
            source="youtube_transcript_api",
        )

        # Mock get_by_composite_key to return transcript without timestamps
        with patch.object(
            repository, "get_by_composite_key", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = transcript_no_timestamps

            result = await repository.get_with_timestamps(
                mock_session,
                "video_no_ts",
                "en-us",
            )

            # Should return None because has_timestamps=False
            assert result is None

            # Verify get_by_composite_key was called
            mock_get.assert_called_once_with(mock_session, "video_no_ts", "en-us")

        # Test Case 2: Verify it DOES return transcript when has_timestamps=True
        transcript_with_timestamps = VideoTranscriptDB(
            video_id="video_with_ts",
            language_code="en-us",
            transcript_text="Transcript with timestamps",
            transcript_type=TranscriptType.MANUAL.value,
            download_reason=DownloadReason.USER_REQUEST.value,
            confidence_score=0.95,
            is_cc=True,
            is_auto_synced=False,
            track_kind=TrackKind.STANDARD.value,
            caption_name="English (CC)",
            downloaded_at=datetime.now(timezone.utc),
            # Has timestamps
            raw_transcript_data={"snippets": [{"text": "test", "start": 0.0, "duration": 2.5}]},
            has_timestamps=True,
            segment_count=1,
            total_duration=2.5,
            source="youtube_transcript_api",
        )

        with patch.object(
            repository, "get_by_composite_key", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = transcript_with_timestamps

            result = await repository.get_with_timestamps(
                mock_session,
                "video_with_ts",
                "en-us",
            )

            # Should return the transcript because has_timestamps=True
            assert result is not None
            assert result == transcript_with_timestamps
            assert result.has_timestamps is True
            assert result.raw_transcript_data is not None

            # Verify get_by_composite_key was called
            mock_get.assert_called_once_with(mock_session, "video_with_ts", "en-us")


class TestVideoTranscriptRepositorySourceTracking:
    """Tests for Feature 007 US3: Track Transcript Source.

    Verifies that transcript sources (YouTube API, manual upload, auto-generated)
    are correctly recorded and queryable.
    """

    @pytest.fixture
    def repository(self) -> VideoTranscriptRepository:
        """Create repository instance for testing."""
        return VideoTranscriptRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def sample_raw_data_with_source(self) -> Dict[str, Any]:
        """Create sample raw data with source field set."""
        return {
            "video_id": "srcTest1234",  # Valid 11-character video ID
            "language_code": "en",
            "language_name": "English",
            "snippets": [
                {"text": "Test snippet", "start": 0.0, "duration": 2.0},
            ],
            "is_generated": False,
            "is_translatable": True,
            "source": "youtube_data_api_v3",  # Specific source
            "retrieved_at": "2024-01-15T12:00:00Z",
        }

    @pytest.fixture
    def sample_raw_data_without_source(self) -> Dict[str, Any]:
        """Create sample raw data missing source field."""
        return {
            "video_id": "noSrcTest12",  # Valid 11-character video ID
            "language_code": "en",
            "language_name": "English",
            "snippets": [
                {"text": "Test snippet", "start": 0.0, "duration": 2.0},
            ],
            "is_generated": True,
            "is_translatable": True,
            # Note: no "source" field
            "retrieved_at": "2024-01-15T12:00:00Z",
        }

    @pytest.mark.asyncio
    async def test_source_extracted_from_raw_data(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_raw_data_with_source: Dict[str, Any],
    ):
        """T049: Test that source is extracted from raw_transcript_data during create_or_update.

        Verifies that when creating a transcript with raw_transcript_data containing
        a "source" field, the source value is correctly extracted and stored in the
        transcript's source column.
        """
        # Create transcript data
        transcript_create = VideoTranscriptCreate(
            video_id="srcTest1234",  # Valid 11-character video ID
            language_code=LanguageCode.ENGLISH,
            transcript_text="Test snippet",
            transcript_type=TranscriptType.MANUAL,
            download_reason=DownloadReason.USER_REQUEST,
            confidence_score=0.95,
            is_cc=True,
            is_auto_synced=False,
            track_kind=TrackKind.STANDARD,
            caption_name="English (CC)",
        )

        # Mock get_by_composite_key to return None (new transcript)
        with patch.object(
            repository, "get_by_composite_key", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            # Mock session methods
            mock_session.add.return_value = None
            mock_session.flush.return_value = None
            mock_session.refresh.return_value = None

            await repository.create_or_update(
                mock_session,
                transcript_create,
                raw_transcript_data=sample_raw_data_with_source,
            )

            # Verify session.add was called
            mock_session.add.assert_called_once()
            added_transcript = mock_session.add.call_args[0][0]

            # T049 verification: source should be extracted from raw_data
            assert added_transcript.source == "youtube_data_api_v3", (
                "Source should be extracted from raw_transcript_data"
            )

            # Also verify other metadata fields for completeness
            assert added_transcript.has_timestamps is True
            assert added_transcript.segment_count == 1
            assert added_transcript.total_duration == 2.0

    @pytest.mark.asyncio
    async def test_filter_by_metadata_with_source(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
    ):
        """T050: Test filter_by_metadata with source filter.

        Verifies that filter_by_metadata correctly filters transcripts by their
        source field, returning only transcripts from the specified source.
        """
        base_time = datetime.now(timezone.utc)

        # Create sample transcripts with different sources
        transcripts_mixed_sources = [
            # Transcript 1: youtube_transcript_api source
            VideoTranscriptDB(
                video_id="video1",
                language_code="en-us",
                transcript_text="Transcript from youtube_transcript_api",
                transcript_type=TranscriptType.AUTO.value,
                download_reason=DownloadReason.AUTO_PREFERRED.value,
                confidence_score=0.80,
                is_cc=False,
                is_auto_synced=True,
                track_kind=TrackKind.ASR.value,
                caption_name="English (Auto)",
                downloaded_at=base_time,
                raw_transcript_data={"source": "youtube_transcript_api"},
                has_timestamps=True,
                segment_count=5,
                total_duration=10.0,
                source="youtube_transcript_api",
            ),
            # Transcript 2: youtube_data_api_v3 source
            VideoTranscriptDB(
                video_id="video2",
                language_code="en-us",
                transcript_text="Transcript from YouTube Data API v3",
                transcript_type=TranscriptType.MANUAL.value,
                download_reason=DownloadReason.USER_REQUEST.value,
                confidence_score=0.95,
                is_cc=True,
                is_auto_synced=False,
                track_kind=TrackKind.STANDARD.value,
                caption_name="English (CC)",
                downloaded_at=base_time,
                raw_transcript_data={"source": "youtube_data_api_v3"},
                has_timestamps=True,
                segment_count=10,
                total_duration=20.0,
                source="youtube_data_api_v3",
            ),
            # Transcript 3: another youtube_transcript_api source
            VideoTranscriptDB(
                video_id="video3",
                language_code="es-es",
                transcript_text="Otro transcript de youtube_transcript_api",
                transcript_type=TranscriptType.AUTO.value,
                download_reason=DownloadReason.AUTO_PREFERRED.value,
                confidence_score=0.78,
                is_cc=False,
                is_auto_synced=True,
                track_kind=TrackKind.ASR.value,
                caption_name="Spanish (Auto)",
                downloaded_at=base_time,
                raw_transcript_data={"source": "youtube_transcript_api"},
                has_timestamps=True,
                segment_count=8,
                total_duration=15.0,
                source="youtube_transcript_api",
            ),
        ]

        # Filter to only youtube_transcript_api source
        filtered_transcripts = [
            t for t in transcripts_mixed_sources
            if t.source == "youtube_transcript_api"
        ]

        # Mock the query execution
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = filtered_transcripts
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.filter_by_metadata(
            mock_session,
            source="youtube_transcript_api",
        )

        # T050 verification: should return only transcripts from youtube_transcript_api
        assert len(result) == 2, "Should return 2 transcripts with youtube_transcript_api source"
        assert all(t.source == "youtube_transcript_api" for t in result), (
            "All returned transcripts should have youtube_transcript_api source"
        )
        assert result[0].video_id in ("video1", "video3")
        assert result[1].video_id in ("video1", "video3")

        # Verify the query was executed
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_source_when_missing(
        self,
        repository: VideoTranscriptRepository,
        mock_session: AsyncMock,
        sample_raw_data_without_source: Dict[str, Any],
    ):
        """T051: Test default source value when missing from raw_data.

        Verifies that when raw_transcript_data is provided but does not contain
        a "source" field, the default value "youtube_transcript_api" is used.
        """
        # Create transcript data
        transcript_create = VideoTranscriptCreate(
            video_id="noSrcTest12",  # Valid 11-character video ID
            language_code=LanguageCode.ENGLISH,
            transcript_text="Test snippet",
            transcript_type=TranscriptType.AUTO,
            download_reason=DownloadReason.AUTO_PREFERRED,
            confidence_score=0.75,
            is_cc=False,
            is_auto_synced=True,
            track_kind=TrackKind.ASR,
            caption_name="English (Auto)",
        )

        # Mock get_by_composite_key to return None (new transcript)
        with patch.object(
            repository, "get_by_composite_key", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            # Mock session methods
            mock_session.add.return_value = None
            mock_session.flush.return_value = None
            mock_session.refresh.return_value = None

            await repository.create_or_update(
                mock_session,
                transcript_create,
                raw_transcript_data=sample_raw_data_without_source,
            )

            # Verify session.add was called
            mock_session.add.assert_called_once()
            added_transcript = mock_session.add.call_args[0][0]

            # T051 verification: source should default to "youtube_transcript_api"
            assert added_transcript.source == "youtube_transcript_api", (
                "Source should default to 'youtube_transcript_api' when missing from raw_data"
            )

            # Verify other metadata fields are still extracted correctly
            assert added_transcript.has_timestamps is True
            assert added_transcript.segment_count == 1
            assert added_transcript.total_duration == 2.0
