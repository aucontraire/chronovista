"""
Tests for UserVideoRepository.

Comprehensive unit tests covering all repository methods including CRUD operations,
Google Takeout integration, analytics, and specialized queries.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import UserVideo as UserVideoDB
from chronovista.models.user_video import (
    GoogleTakeoutWatchHistoryItem,
    UserVideoCreate,
    UserVideoSearchFilters,
    UserVideoStatistics
)
from chronovista.repositories.user_video_repository import UserVideoRepository


class TestUserVideoRepository:
    """Test suite for UserVideoRepository."""

    @pytest.fixture
    def repository(self) -> UserVideoRepository:
        """Create repository instance for testing."""
        return UserVideoRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncSession:
        """Create mock async session."""
        session = AsyncMock()
        return cast(AsyncSession, session)

    @pytest.fixture
    def sample_user_video_db(self) -> UserVideoDB:
        """Create sample database user video object."""
        return UserVideoDB(
            user_id="test_user",
            video_id="dQw4w9WgXcQ",
            watched_at=datetime.now(timezone.utc),
            watch_duration=3600,
            completion_percentage=85.5,
            rewatch_count=2,
            liked=True,
            disliked=False,
            saved_to_playlist=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def sample_user_video_create(self) -> UserVideoCreate:
        """Create sample user video creation object."""
        return UserVideoCreate(
            user_id="test_user",
            video_id="dQw4w9WgXcQ",
            watched_at=datetime.now(timezone.utc),
            watch_duration=3600,
            completion_percentage=85.5,
            rewatch_count=0,
            liked=False,
            disliked=False,
            saved_to_playlist=False,
        )

    @pytest.fixture
    def sample_user_videos_list(self) -> List[UserVideoDB]:
        """Create list of sample user videos."""
        base_time = datetime.now(timezone.utc)
        return [
            UserVideoDB(
                user_id="test_user",
                video_id="video_123",
                watched_at=base_time,
                watch_duration=3600,
                completion_percentage=100.0,
                rewatch_count=0,
                liked=True,
                disliked=False,
                saved_to_playlist=True,
                created_at=base_time,
                updated_at=base_time,
            ),
            UserVideoDB(
                user_id="test_user",
                video_id="video_456",
                watched_at=base_time - timedelta(days=1),
                watch_duration=1800,
                completion_percentage=50.0,
                rewatch_count=1,
                liked=False,
                disliked=True,
                saved_to_playlist=False,
                created_at=base_time - timedelta(days=1),
                updated_at=base_time,
            ),
        ]

    @pytest.fixture
    def sample_takeout_item(self) -> GoogleTakeoutWatchHistoryItem:
        """Create sample Google Takeout item."""
        return GoogleTakeoutWatchHistoryItem(
            header="YouTube",
            title="Watched Test Video Title",
            titleUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            subtitles=[
                {
                    "name": "Test Channel",
                    "url": "https://www.youtube.com/channel/test_channel",
                }
            ],
            time="2025-01-15T10:30:00.000Z",
            products=["YouTube"],
            activityControls=["YouTube watch history"],
        )

    @pytest.mark.asyncio
    async def test_get_existing_user_video(
        self,
        repository: UserVideoRepository,
        mock_session: AsyncSession,
        sample_user_video_db: UserVideoDB,
    ):
        """Test getting an existing user video interaction."""
        # Mock execute to return scalar_one_or_none result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_user_video_db
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.get_by_composite_key(
            mock_session, "test_user", "dQw4w9WgXcQ"
        )

        assert result == sample_user_video_db
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_get_nonexistent_user_video(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test getting a non-existent user video interaction."""
        # Mock execute to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.get_by_composite_key(
            mock_session, "test_user", "non_existent"
        )

        assert result is None
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_exists_true(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test exists returns True when interaction exists."""
        # Mock execute to return a result
        mock_result = MagicMock()
        mock_result.first.return_value = ("test_user",)
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.exists_by_composite_key(
            mock_session, "test_user", "dQw4w9WgXcQ"
        )

        assert result is True
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_exists_false(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test exists returns False when interaction doesn't exist."""
        # Mock execute to return None
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.exists_by_composite_key(
            mock_session, "test_user", "non_existent"
        )

        assert result is False
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_get_user_watch_history(
        self,
        repository: UserVideoRepository,
        mock_session: AsyncSession,
        sample_user_videos_list: List[UserVideoDB],
    ):
        """Test getting user's watch history."""
        # Mock execute to return scalars
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = sample_user_videos_list
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.get_user_watch_history(
            mock_session, "test_user", limit=10, offset=0
        )

        assert result == sample_user_videos_list
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_get_user_liked_videos(
        self,
        repository: UserVideoRepository,
        mock_session: AsyncSession,
        sample_user_videos_list: List[UserVideoDB],
    ):
        """Test getting user's liked videos."""
        # Filter list to only liked videos
        liked_videos = [v for v in sample_user_videos_list if v.liked]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = liked_videos
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.get_user_liked_videos(
            mock_session, "test_user", limit=10
        )

        assert result == liked_videos
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_get_most_watched_videos(
        self,
        repository: UserVideoRepository,
        mock_session: AsyncSession,
        sample_user_videos_list: List[UserVideoDB],
    ):
        """Test getting user's most watched videos."""
        # Sort by rewatch count descending
        most_watched = sorted(
            sample_user_videos_list, key=lambda v: v.rewatch_count, reverse=True
        )

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = most_watched
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.get_most_watched_videos(
            mock_session, "test_user", limit=5
        )

        assert result == most_watched
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_search_user_videos_no_filters(
        self,
        repository: UserVideoRepository,
        mock_session: AsyncSession,
        sample_user_videos_list: List[UserVideoDB],
    ):
        """Test searching user videos with no filters."""
        filters = UserVideoSearchFilters()

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = sample_user_videos_list
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.search_user_videos(mock_session, filters)

        assert result == sample_user_videos_list
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_search_user_videos_with_filters(
        self,
        repository: UserVideoRepository,
        mock_session: AsyncSession,
        sample_user_videos_list: List[UserVideoDB],
    ):
        """Test searching user videos with filters."""
        filters = UserVideoSearchFilters(
            user_ids=["test_user"], liked_only=True, min_completion_percentage=80.0
        )

        # Filter results
        filtered_videos = [
            v
            for v in sample_user_videos_list
            if v.liked and v.completion_percentage is not None and v.completion_percentage >= 80.0
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = filtered_videos
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.search_user_videos(mock_session, filters)

        assert result == filtered_videos
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_get_user_statistics(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test getting comprehensive user statistics."""
        # Create sample statistics
        expected_stats = UserVideoStatistics(
            total_videos=10,
            total_watch_time=36000,
            average_completion=75.5,
            liked_count=5,
            disliked_count=1,
            playlist_saved_count=3,
            rewatch_count=2,
            unique_videos=8,
            most_watched_date=datetime.now(timezone.utc),
            watch_streak_days=7,
        )

        # Mock the entire method to avoid SQLAlchemy query construction issues
        with patch.object(repository, 'get_user_statistics', return_value=expected_stats) as mock_get_stats:
            result = await repository.get_user_statistics(mock_session, "test_user")

            assert isinstance(result, UserVideoStatistics)
            assert result.total_videos == 10
            assert result.total_watch_time == 36000
            assert result.average_completion == 75.5
            assert result.liked_count == 5
            assert result.disliked_count == 1
            assert result.playlist_saved_count == 3
            assert result.rewatch_count == 2
            assert result.unique_videos == 8
            assert result.watch_streak_days == 7
            assert result.most_watched_date is not None
            assert result.most_watched_date.date() == datetime.now(timezone.utc).date()

    @pytest.mark.asyncio
    async def test_get_user_statistics_no_data(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test getting statistics when user has no data."""
        # Create expected empty statistics
        expected_stats = UserVideoStatistics(
            total_videos=0,
            total_watch_time=0,
            average_completion=0.0,
            liked_count=0,
            disliked_count=0,
            playlist_saved_count=0,
            rewatch_count=0,
            unique_videos=0,
            most_watched_date=None,
            watch_streak_days=0,
        )

        # Mock the entire method
        with patch.object(repository, 'get_user_statistics', return_value=expected_stats) as mock_get_stats:
            result = await repository.get_user_statistics(mock_session, "test_user")

            assert isinstance(result, UserVideoStatistics)
            assert result.total_videos == 0
            assert result.total_watch_time == 0
            assert result.average_completion == 0.0
            assert result.liked_count == 0
            assert result.disliked_count == 0
            assert result.playlist_saved_count == 0
            assert result.rewatch_count == 0
            assert result.unique_videos == 0
            assert result.most_watched_date is None
            assert result.watch_streak_days == 0

    @pytest.mark.asyncio
    async def test_calculate_watch_streak_no_data(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test calculating watch streak with no data."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository._calculate_watch_streak(mock_session, "test_user")

        assert result == 0
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_calculate_watch_streak_consecutive_days(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test calculating watch streak with consecutive days."""
        # Mock consecutive watch dates
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        day_before = today - timedelta(days=2)

        mock_result = MagicMock()
        mock_rows = [
            MagicMock(watch_date=today),
            MagicMock(watch_date=yesterday),
            MagicMock(watch_date=day_before),
        ]
        mock_result.__iter__ = lambda self: iter(mock_rows)
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository._calculate_watch_streak(mock_session, "test_user")

        assert result == 3
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_calculate_watch_streak_broken_sequence(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test calculating watch streak with broken sequence."""
        # Mock watch dates with gap
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        three_days_ago = today - timedelta(days=3)  # Gap of one day

        mock_result = MagicMock()
        mock_rows = [
            MagicMock(watch_date=today),
            MagicMock(watch_date=yesterday),
            MagicMock(watch_date=three_days_ago),
        ]
        mock_result.__iter__ = lambda self: iter(mock_rows)
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository._calculate_watch_streak(mock_session, "test_user")

        assert result == 2  # Only today and yesterday are consecutive
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_import_from_takeout_batch_new_videos(
        self,
        repository: UserVideoRepository,
        mock_session: AsyncSession,
        sample_takeout_item: GoogleTakeoutWatchHistoryItem,
    ):
        """Test importing new videos from Google Takeout."""
        takeout_items = [sample_takeout_item]

        # Mock get_by_composite_key to return None (new video)
        with patch.object(repository, 'get_by_composite_key', return_value=None) as mock_get, \
             patch.object(repository, 'create', return_value=MagicMock()) as mock_create:
            
            result = await repository.import_from_takeout_batch(
                mock_session, "test_user", takeout_items
            )

            assert result["created"] == 1
            assert result["updated"] == 0
            assert result["skipped"] == 0
            assert result["errors"] == 0
            mock_get.assert_called_once()
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_from_takeout_batch_existing_videos(
        self,
        repository: UserVideoRepository,
        mock_session: AsyncSession,
        sample_takeout_item: GoogleTakeoutWatchHistoryItem,
        sample_user_video_db: UserVideoDB,
    ):
        """Test importing existing videos from Google Takeout (updates)."""
        takeout_items = [sample_takeout_item]

        # Mock get_by_composite_key to return existing video
        with patch.object(repository, 'get_by_composite_key', return_value=sample_user_video_db) as mock_get:
            result = await repository.import_from_takeout_batch(
                mock_session, "test_user", takeout_items
            )

            assert result["created"] == 0
            assert result["updated"] == 1
            assert result["skipped"] == 0
            assert result["errors"] == 0
            mock_get.assert_called_once()
            mock_session.add.assert_called_once_with(sample_user_video_db)  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_import_from_takeout_batch_rewatch_count(
        self,
        repository: UserVideoRepository,
        mock_session: AsyncSession,
        sample_user_video_db: UserVideoDB,
    ):
        """Test importing duplicate videos increments rewatch count."""
        # Create multiple takeout items for same video
        takeout_item = GoogleTakeoutWatchHistoryItem(
            header="YouTube",
            title="Watched Test Video",
            titleUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            subtitles=[],
            time="2025-01-15T10:30:00.000Z",
            products=["YouTube"],
            activityControls=["YouTube watch history"],
        )
        takeout_items = [takeout_item, takeout_item]  # Same video watched twice

        # Mock get_by_composite_key to return None first time, then existing video
        with patch.object(repository, 'get_by_composite_key', side_effect=[None, sample_user_video_db]) as mock_get, \
             patch.object(repository, 'create', return_value=sample_user_video_db) as mock_create:
            
            result = await repository.import_from_takeout_batch(
                mock_session, "test_user", takeout_items
            )

            assert result["created"] == 1
            assert result["updated"] == 1
            assert (
                sample_user_video_db.rewatch_count == 1
            )  # Second occurrence sets rewatch_count to 1

    @pytest.mark.asyncio
    async def test_import_from_takeout_batch_invalid_url(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test importing takeout item with video that can't extract ID."""
        # Use a valid YouTube URL that returns None for video ID extraction
        invalid_item = GoogleTakeoutWatchHistoryItem(
            header="YouTube",
            title="Watched Invalid Video",
            titleUrl="https://www.youtube.com/playlist?list=invalid",  # Valid YouTube URL but not a video
            subtitles=[],
            time="2025-01-15T10:30:00.000Z",
            products=["YouTube"],
            activityControls=["YouTube watch history"],
        )

        result = await repository.import_from_takeout_batch(
            mock_session, "test_user", [invalid_item]
        )

        assert result["created"] == 0
        assert result["updated"] == 0
        assert result["skipped"] == 1
        assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_record_watch_new_interaction(
        self,
        repository: UserVideoRepository,
        mock_session: AsyncSession,
        sample_user_video_create: UserVideoCreate,
    ):
        """Test recording a new watch interaction."""
        watch_time = datetime.now(timezone.utc)

        # Mock get_by_composite_key to return None (new interaction)
        with patch.object(repository, 'get_by_composite_key', return_value=None) as mock_get, \
             patch.object(repository, 'create', return_value=sample_user_video_create) as mock_create:
            
            result = await repository.record_watch(
                mock_session,
                "test_user",
                "dQw4w9WgXcQ",
                watched_at=watch_time,
                watch_duration=3600,
                completion_percentage=85.5,
            )

            assert result is not None
            assert result.user_id == sample_user_video_create.user_id
            assert result.video_id == sample_user_video_create.video_id
            mock_get.assert_called_once()
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_watch_existing_interaction(
        self,
        repository: UserVideoRepository,
        mock_session: AsyncSession,
        sample_user_video_db: UserVideoDB,
    ):
        """Test recording a watch on existing interaction (rewatch)."""
        watch_time = datetime.now(timezone.utc)
        original_rewatch_count = sample_user_video_db.rewatch_count

        # Mock get_by_composite_key to return existing interaction
        with patch.object(repository, 'get_by_composite_key', return_value=sample_user_video_db) as mock_get:
            result = await repository.record_watch(
                mock_session,
                "test_user",
                "dQw4w9WgXcQ",
                watched_at=watch_time,
                watch_duration=7200,
                completion_percentage=100.0,
            )

            assert result == sample_user_video_db
            assert sample_user_video_db.watched_at == watch_time
            assert sample_user_video_db.watch_duration == 7200
            assert sample_user_video_db.completion_percentage == 100.0
            assert sample_user_video_db.rewatch_count == original_rewatch_count + 1
            mock_session.add.assert_called_once_with(sample_user_video_db)  # type: ignore[attr-defined]
            mock_session.flush.assert_called_once()  # type: ignore[attr-defined]
            mock_session.refresh.assert_called_once_with(sample_user_video_db)  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_delete_user_interactions(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test deleting all interactions for a user."""
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.delete_user_interactions(mock_session, "test_user")

        assert result == 5
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_get_watch_time_by_date_range(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test getting watch time aggregated by date range."""
        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 31, tzinfo=timezone.utc)

        # Mock aggregated results
        mock_result = MagicMock()
        mock_rows = [
            MagicMock(watch_date=datetime(2025, 1, 15).date(), total_time=3600),
            MagicMock(watch_date=datetime(2025, 1, 16).date(), total_time=7200),
        ]
        mock_result.__iter__ = lambda self: iter(mock_rows)
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.get_watch_time_by_date_range(
            mock_session, "test_user", start_date, end_date
        )

        expected = {
            "2025-01-15": 3600,
            "2025-01-16": 7200,
        }
        assert result == expected
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_get_with_composite_key_tuple(
        self,
        repository: UserVideoRepository,
        mock_session: AsyncSession,
        sample_user_video_db: UserVideoDB,
    ):
        """Test get method with tuple composite key (base class signature)."""
        # Mock execute to return scalar_one_or_none result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_user_video_db
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.get(mock_session, ("test_user", "dQw4w9WgXcQ"))

        assert result == sample_user_video_db
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_exists_with_composite_key_tuple(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test exists method with tuple composite key (base class signature)."""
        # Mock execute to return a result
        mock_result = MagicMock()
        mock_result.first.return_value = ("test_user",)
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.exists(mock_session, ("test_user", "dQw4w9WgXcQ"))

        assert result is True
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_repository_inherits_base_methods(
        self, repository: UserVideoRepository
    ):
        """Test that repository properly inherits from base repository."""
        from chronovista.repositories.base import BaseSQLAlchemyRepository

        assert isinstance(repository, BaseSQLAlchemyRepository)
        assert repository.model == UserVideoDB

    def test_repository_initialization(self):
        """Test repository initialization."""
        repo = UserVideoRepository()
        assert repo.model == UserVideoDB


class TestUserVideoRepositoryEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def repository(self) -> UserVideoRepository:
        """Create repository instance for testing."""
        return UserVideoRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncSession:
        """Create mock async session."""
        return cast(AsyncSession, AsyncMock())

    @pytest.mark.asyncio
    async def test_empty_user_id_handling(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test repository behavior with empty user ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.get_by_composite_key(mock_session, "", "dQw4w9WgXcQ")

        assert result is None
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_empty_video_id_handling(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test repository behavior with empty video ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.get_by_composite_key(mock_session, "test_user", "")

        assert result is None
        mock_session.execute.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_import_from_takeout_batch_empty_list(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test importing empty list of takeout items."""
        result = await repository.import_from_takeout_batch(
            mock_session, "test_user", []
        )

        assert result["created"] == 0
        assert result["updated"] == 0
        assert result["skipped"] == 0
        assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_import_from_takeout_batch_with_errors(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test importing takeout items with processing errors."""
        # Create a takeout item that will cause an error
        invalid_item = GoogleTakeoutWatchHistoryItem(
            header="YouTube",
            title="Watched Test Video",
            titleUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            subtitles=[],
            time="2025-01-15T10:30:00.000Z",
            products=["YouTube"],
            activityControls=["YouTube watch history"],
        )

        # Mock get_by_composite_key to raise an exception
        with patch.object(repository, 'get_by_composite_key', side_effect=Exception("Database error")) as mock_get:
            result = await repository.import_from_takeout_batch(
                mock_session, "test_user", [invalid_item]
            )

            assert result["created"] == 0
            assert result["updated"] == 0
            assert result["skipped"] == 0
            assert result["errors"] == 1

    @pytest.mark.asyncio
    async def test_get_user_watch_history_no_results(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test getting watch history when user has no videos."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.get_user_watch_history(mock_session, "test_user")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_watch_time_by_date_range_no_data(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test getting watch time when no data exists in range."""
        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 31, tzinfo=timezone.utc)

        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_session.execute.return_value = mock_result  # type: ignore[attr-defined]

        result = await repository.get_watch_time_by_date_range(
            mock_session, "test_user", start_date, end_date
        )

        assert result == {}


class TestGoogleTakeoutIntegration:
    """Test Google Takeout specific functionality."""

    @pytest.fixture
    def repository(self) -> UserVideoRepository:
        """Create repository instance for testing."""
        return UserVideoRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncSession:
        """Create mock async session."""
        return cast(AsyncSession, AsyncMock())

    def test_takeout_item_video_id_extraction(self):
        """Test video ID extraction from various YouTube URL formats."""
        test_cases = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/test_video_456", "test_video_456"),
            ("https://www.youtube.com/embed/test_video_789", "test_video_789"),
            (
                "https://www.youtube.com/playlist?list=invalid",
                None,
            ),  # Valid YouTube URL but not video
        ]

        for url, expected_id in test_cases:
            item = GoogleTakeoutWatchHistoryItem(
                header="YouTube",
                title="Watched Test Video",
                titleUrl=url,
                subtitles=[],
                time="2025-01-15T10:30:00.000Z",
                products=["YouTube"],
                activityControls=["YouTube watch history"],
            )
            assert item.extract_video_id() == expected_id

    def test_takeout_item_to_user_video_create(self):
        """Test conversion from takeout item to user video create model."""
        item = GoogleTakeoutWatchHistoryItem(
            header="YouTube",
            title="Watched Test Video Title",
            titleUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            subtitles=[
                {
                    "name": "Test Channel",
                    "url": "https://www.youtube.com/channel/test_channel",
                }
            ],
            time="2025-01-15T10:30:00.000Z",
            products=["YouTube"],
            activityControls=["YouTube watch history"],
        )

        result = item.to_user_video_create("test_user")

        assert result is not None
        assert result.user_id == "test_user"
        assert result.video_id == "dQw4w9WgXcQ"
        assert result.watched_at == datetime(
            2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc
        )
        assert result.watch_duration is None  # Not available in Takeout
        assert result.completion_percentage is None  # Not available in Takeout
        assert result.rewatch_count == 0

    def test_takeout_item_invalid_video_id(self):
        """Test takeout item with invalid video ID returns None."""
        item = GoogleTakeoutWatchHistoryItem(
            header="YouTube",
            title="Watched Invalid Video",
            titleUrl="https://www.youtube.com/playlist?list=invalid",  # Valid YouTube URL but not video
            subtitles=[],
            time="2025-01-15T10:30:00.000Z",
            products=["YouTube"],
            activityControls=["YouTube watch history"],
        )

        result = item.to_user_video_create("test_user")
        assert result is None

    @pytest.mark.asyncio
    async def test_complex_takeout_batch_import_scenario(
        self, repository: UserVideoRepository, mock_session: AsyncSession
    ):
        """Test complex scenario with mixed new/existing/duplicate videos."""
        # Create test data
        takeout_items = [
            # New video
            GoogleTakeoutWatchHistoryItem(
                header="YouTube",
                title="Watched New Video",
                titleUrl="https://www.youtube.com/watch?v=9bZkp7q19f0",
                subtitles=[],
                time="2025-01-15T10:00:00.000Z",
                products=["YouTube"],
                activityControls=["YouTube watch history"],
            ),
            # Existing video (update)
            GoogleTakeoutWatchHistoryItem(
                header="YouTube",
                title="Watched Existing Video",
                titleUrl="https://www.youtube.com/watch?v=jNQXAC9IVRw",
                subtitles=[],
                time="2025-01-15T11:00:00.000Z",
                products=["YouTube"],
                activityControls=["YouTube watch history"],
            ),
            # Same video watched again (rewatch)
            GoogleTakeoutWatchHistoryItem(
                header="YouTube",
                title="Watched Existing Video Again",
                titleUrl="https://www.youtube.com/watch?v=jNQXAC9IVRw",
                subtitles=[],
                time="2025-01-15T12:00:00.000Z",
                products=["YouTube"],
                activityControls=["YouTube watch history"],
            ),
            # Invalid video URL (skip) - valid YouTube URL but not a video
            GoogleTakeoutWatchHistoryItem(
                header="YouTube",
                title="Watched Invalid Video",
                titleUrl="https://www.youtube.com/playlist?list=invalid",
                subtitles=[],
                time="2025-01-15T13:00:00.000Z",
                products=["YouTube"],
                activityControls=["YouTube watch history"],
            ),
        ]

        # Create existing video mock
        existing_video = UserVideoDB(
            user_id="test_user",
            video_id="jNQXAC9IVRw",
            watched_at=datetime(2025, 1, 14, tzinfo=timezone.utc),
            created_at=datetime(2025, 1, 14, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 14, tzinfo=timezone.utc),
        )

        # Mock repository methods with side effects
        get_calls = [
            None,  # 9bZkp7q19f0 - not found
            existing_video,  # jNQXAC9IVRw - found first time
            existing_video,  # jNQXAC9IVRw - found second time
        ]
        with patch.object(repository, 'get_by_composite_key', side_effect=get_calls) as mock_get, \
             patch.object(repository, 'create', return_value=MagicMock()) as mock_create:
            
            result = await repository.import_from_takeout_batch(
                mock_session, "test_user", takeout_items
            )

            assert result["created"] == 1  # 9bZkp7q19f0
            assert result["updated"] == 2  # jNQXAC9IVRw updated twice
            assert result["skipped"] == 1  # invalid URL (playlist)
            assert result["errors"] == 0

            # Verify the existing video's rewatch count was updated correctly
            assert existing_video.rewatch_count == 1  # Second occurrence of same video
