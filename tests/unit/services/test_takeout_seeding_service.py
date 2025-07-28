"""
Tests for TakeoutSeedingService.

Comprehensive test suite covering data transformation, dependency resolution,
seeding operations, and error handling scenarios.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from chronovista.services.takeout_seeding_service import (
    TakeoutSeedingService,
    TakeoutDataTransformer,
    DependencyResolver,
    SeedingProgress,
    SeedingResult,
)
from chronovista.models.takeout.takeout_data import (
    TakeoutData,
    TakeoutSubscription,
    TakeoutWatchEntry,
    TakeoutPlaylist,
)
from chronovista.models.channel import ChannelCreate
from chronovista.models.video import VideoCreate
from chronovista.models.user_video import UserVideoCreate
from chronovista.models.playlist import PlaylistCreate
from chronovista.models.enums import LanguageCode
from tests.factories.id_factory import YouTubeIdFactory, TestIds


class TestSeedingProgress:
    """Test SeedingProgress model."""
    
    def test_seeding_progress_initialization(self) -> None:
        """Test SeedingProgress model initialization."""
        progress = SeedingProgress()
        
        assert progress.channels_processed == 0
        assert progress.channels_total == 0
        assert progress.videos_processed == 0
        assert progress.videos_total == 0
        assert progress.user_videos_processed == 0
        assert progress.user_videos_total == 0
        assert progress.playlists_processed == 0
        assert progress.playlists_total == 0
        assert progress.errors == []
        assert progress.warnings == []
    
    def test_total_processed_calculation(self) -> None:
        """Test total_processed property calculation."""
        progress = SeedingProgress(
            channels_processed=10,
            videos_processed=50,
            user_videos_processed=100,
            playlists_processed=5,
        )
        
        assert progress.total_processed == 165
    
    def test_total_items_calculation(self) -> None:
        """Test total_items property calculation."""
        progress = SeedingProgress(
            channels_total=20,
            videos_total=100,
            user_videos_total=200,
            playlists_total=10,
        )
        
        assert progress.total_items == 330
    
    def test_completion_percentage_calculation(self) -> None:
        """Test completion_percentage property calculation."""
        progress = SeedingProgress(
            channels_processed=5,
            channels_total=10,
            videos_processed=25,
            videos_total=50,
            user_videos_processed=50,
            user_videos_total=100,
            playlists_processed=3,
            playlists_total=5,
        )
        
        # Total processed: 83, Total items: 165
        expected_percentage = (83 / 165) * 100
        assert abs(progress.completion_percentage - expected_percentage) < 0.01
    
    def test_completion_percentage_empty_case(self) -> None:
        """Test completion_percentage with no items."""
        progress = SeedingProgress()
        assert progress.completion_percentage == 100.0


class TestSeedingResult:
    """Test SeedingResult model."""
    
    def test_seeding_result_initialization(self) -> None:
        """Test SeedingResult model initialization."""
        result = SeedingResult()
        
        assert result.channels_seeded == 0
        assert result.channels_updated == 0
        assert result.channels_failed == 0
        assert result.videos_seeded == 0
        assert result.videos_updated == 0
        assert result.videos_failed == 0
        assert result.user_videos_created == 0
        assert result.user_videos_failed == 0
        assert result.playlists_seeded == 0
        assert result.playlists_updated == 0
        assert result.playlists_failed == 0
        assert result.duration_seconds == 0.0
        assert result.data_quality_score == 0.0
        assert result.integrity_issues == []
        assert result.suggestions == []
    
    def test_total_seeded_calculation(self) -> None:
        """Test total_seeded property calculation."""
        result = SeedingResult(
            channels_seeded=10,
            videos_seeded=50,
            user_videos_created=100,
            playlists_seeded=5,
        )
        
        assert result.total_seeded == 165
    
    def test_total_failed_calculation(self) -> None:
        """Test total_failed property calculation."""
        result = SeedingResult(
            channels_failed=2,
            videos_failed=5,
            user_videos_failed=10,
            playlists_failed=1,
        )
        
        assert result.total_failed == 18
    
    def test_success_rate_calculation(self) -> None:
        """Test success_rate property calculation."""
        result = SeedingResult(
            channels_seeded=8,
            channels_failed=2,
            videos_seeded=45,
            videos_failed=5,
        )
        
        # Total seeded: 53, Total failed: 7, Success rate: 53/60 = 88.33%
        expected_rate = (53 / 60) * 100
        assert abs(result.success_rate - expected_rate) < 0.01
    
    def test_success_rate_no_attempts(self) -> None:
        """Test success_rate with no attempted operations."""
        result = SeedingResult()
        assert result.success_rate == 100.0


class TestTakeoutDataTransformer:
    """Test TakeoutDataTransformer class."""
    
    def test_transformer_initialization(self) -> None:
        """Test TakeoutDataTransformer initialization."""
        transformer = TakeoutDataTransformer()
        assert transformer.default_user_id == "takeout_user"
        
        custom_transformer = TakeoutDataTransformer("custom_user")
        assert custom_transformer.default_user_id == "custom_user"
    
    def test_transform_subscription_to_channel(self) -> None:
        """Test subscription to channel transformation."""
        transformer = TakeoutDataTransformer()
        
        subscription = TakeoutSubscription(
            channel_id=TestIds.TEST_CHANNEL_1,
            channel_title="Test Channel",
            channel_url=f"https://www.youtube.com/channel/{TestIds.TEST_CHANNEL_1}",
        )
        
        channel_create = transformer.transform_subscription_to_channel(subscription)
        
        assert isinstance(channel_create, ChannelCreate)
        assert channel_create.channel_id == TestIds.TEST_CHANNEL_1
        assert channel_create.title == "Test Channel"
        assert channel_create.description == ""
        assert channel_create.default_language == LanguageCode.ENGLISH
        assert channel_create.country is None
        assert channel_create.subscriber_count is None
        assert channel_create.video_count is None
        assert channel_create.thumbnail_url is None
    
    def test_transform_subscription_without_channel_id(self) -> None:
        """Test subscription transformation without channel ID."""
        transformer = TakeoutDataTransformer()
        
        subscription = TakeoutSubscription(
            channel_id=None,
            channel_title="Test Channel",
            channel_url="https://www.youtube.com/c/TestChannel",
        )
        
        channel_create = transformer.transform_subscription_to_channel(subscription)
        
        # Should generate a valid 24-character channel ID starting with UC
        assert channel_create.channel_id.startswith("UC")
        assert len(channel_create.channel_id) == 24
        assert channel_create.title == "Test Channel"
    
    def test_transform_watch_entry_to_channel(self) -> None:
        """Test watch entry to channel transformation."""
        transformer = TakeoutDataTransformer()
        
        watch_entry = TakeoutWatchEntry(
            video_id=TestIds.NEVER_GONNA_GIVE_YOU_UP,
            title="Never Gonna Give You Up",
            title_url=f"https://www.youtube.com/watch?v={TestIds.NEVER_GONNA_GIVE_YOU_UP}",
            channel_name="Rick Astley",
            channel_url=f"https://www.youtube.com/channel/{TestIds.RICK_ASTLEY_CHANNEL}",
            channel_id=TestIds.RICK_ASTLEY_CHANNEL,
            watched_at=datetime.now(timezone.utc),
        )
        
        channel_create = transformer.transform_watch_entry_to_channel(watch_entry)
        
        assert channel_create is not None
        assert isinstance(channel_create, ChannelCreate)
        assert channel_create.channel_id == TestIds.RICK_ASTLEY_CHANNEL
        assert channel_create.title == "Rick Astley"
        assert channel_create.description == ""
        assert channel_create.default_language == LanguageCode.ENGLISH
    
    def test_transform_watch_entry_to_channel_no_channel_name(self) -> None:
        """Test watch entry transformation with no channel name."""
        transformer = TakeoutDataTransformer()
        
        watch_entry = TakeoutWatchEntry(
            video_id=TestIds.NEVER_GONNA_GIVE_YOU_UP,
            title="Never Gonna Give You Up",
            title_url=f"https://www.youtube.com/watch?v={TestIds.NEVER_GONNA_GIVE_YOU_UP}",
            channel_name=None,
            channel_url=None,
            channel_id=None,
        )
        
        channel_create = transformer.transform_watch_entry_to_channel(watch_entry)
        assert channel_create is None
    
    def test_transform_watch_entry_to_video(self) -> None:
        """Test watch entry to video transformation."""
        transformer = TakeoutDataTransformer()
        
        watch_entry = TakeoutWatchEntry(
            video_id=TestIds.NEVER_GONNA_GIVE_YOU_UP,
            title="Never Gonna Give You Up",
            title_url=f"https://www.youtube.com/watch?v={TestIds.NEVER_GONNA_GIVE_YOU_UP}",
            channel_name="Rick Astley",
            channel_id=TestIds.RICK_ASTLEY_CHANNEL,
            watched_at=datetime.now(timezone.utc),
        )
        
        video_create = transformer.transform_watch_entry_to_video(watch_entry)
        
        assert isinstance(video_create, VideoCreate)
        assert video_create.video_id == TestIds.NEVER_GONNA_GIVE_YOU_UP
        assert video_create.channel_id == TestIds.RICK_ASTLEY_CHANNEL
        assert video_create.title == "Never Gonna Give You Up"
        assert video_create.description == ""
        assert video_create.duration == 0
        assert video_create.deleted_flag is False  # Has proper video_id
        assert video_create.default_language == LanguageCode.ENGLISH
    
    def test_transform_watch_entry_to_video_missing_ids(self) -> None:
        """Test video transformation with missing IDs."""
        transformer = TakeoutDataTransformer()
        
        watch_entry = TakeoutWatchEntry(
            video_id=None,
            title="Deleted Video",
            title_url="https://www.youtube.com/watch?deleted=true",
            channel_name="Unknown Channel",
            channel_id=None,
            watched_at=datetime.now(timezone.utc),
        )
        
        video_create = transformer.transform_watch_entry_to_video(watch_entry)
        
        # Should generate valid IDs with proper lengths since originals were missing/invalid
        assert len(video_create.video_id) == 11  # Valid video ID length
        assert len(video_create.channel_id) == 24  # Valid channel ID length  
        assert video_create.channel_id.startswith("UC")  # Valid channel ID prefix
        assert video_create.title == "Deleted Video"
        assert video_create.deleted_flag is True  # Originally had video_id=None or invalid
    
    def test_transform_watch_entry_to_user_video(self) -> None:
        """Test watch entry to user video transformation."""
        transformer = TakeoutDataTransformer("test_user")
        
        watch_entry = TakeoutWatchEntry(
            video_id=TestIds.NEVER_GONNA_GIVE_YOU_UP,
            title="Never Gonna Give You Up",
            title_url=f"https://www.youtube.com/watch?v={TestIds.NEVER_GONNA_GIVE_YOU_UP}",
            watched_at=datetime.now(timezone.utc),
        )
        
        user_video_create = transformer.transform_watch_entry_to_user_video(watch_entry)
        
        assert user_video_create is not None
        assert isinstance(user_video_create, UserVideoCreate)
        assert user_video_create.user_id == "test_user"
        assert user_video_create.video_id == TestIds.NEVER_GONNA_GIVE_YOU_UP
        assert user_video_create.watched_at == watch_entry.watched_at
        assert user_video_create.watch_duration is None
        assert user_video_create.completion_percentage is None
        assert user_video_create.rewatch_count == 0
        assert user_video_create.liked is False
        assert user_video_create.disliked is False
        assert user_video_create.saved_to_playlist is False
    
    def test_transform_watch_entry_to_user_video_no_timestamp(self) -> None:
        """Test user video transformation with no watched_at timestamp."""
        transformer = TakeoutDataTransformer()
        
        watch_entry = TakeoutWatchEntry(
            video_id=TestIds.NEVER_GONNA_GIVE_YOU_UP,
            title="Never Gonna Give You Up",
            title_url=f"https://www.youtube.com/watch?v={TestIds.NEVER_GONNA_GIVE_YOU_UP}",
            watched_at=None,
        )
        
        user_video_create = transformer.transform_watch_entry_to_user_video(watch_entry)
        assert user_video_create is None
    
    def test_transform_playlist_to_playlist_create(self) -> None:
        """Test playlist transformation."""
        transformer = TakeoutDataTransformer("test_user")
        
        takeout_playlist = TakeoutPlaylist(
            name="My Favorites",
            file_path=Path("/path/to/My Favorites.csv"),
            videos=[],
            video_count=0,
        )
        
        playlist_create = transformer.transform_playlist_to_playlist_create(
            takeout_playlist, TestIds.TEST_CHANNEL_1
        )
        
        assert isinstance(playlist_create, PlaylistCreate)
        assert playlist_create.playlist_id.startswith("PL")
        assert playlist_create.title == "My Favorites"
        assert playlist_create.description == "Playlist imported from Google Takeout"
        assert playlist_create.channel_id == TestIds.TEST_CHANNEL_1
        assert playlist_create.video_count == 0
        assert playlist_create.default_language == LanguageCode.ENGLISH
        assert playlist_create.privacy_status == "private"


class TestDependencyResolver:
    """Test DependencyResolver class."""
    
    @pytest.fixture
    def mock_repositories(self) -> tuple[AsyncMock, AsyncMock]:
        """Create mock repositories."""
        channel_repo = AsyncMock()
        video_repo = AsyncMock()
        return channel_repo, video_repo
    
    @pytest.fixture
    def dependency_resolver(self, mock_repositories: tuple[AsyncMock, AsyncMock]) -> DependencyResolver:
        """Create DependencyResolver with mock repositories."""
        channel_repo, video_repo = mock_repositories
        transformer = TakeoutDataTransformer()
        return DependencyResolver(channel_repo, video_repo, transformer)
    
    @pytest.mark.asyncio
    async def test_ensure_channel_exists_already_cached(
        self, dependency_resolver: DependencyResolver
    ) -> None:
        """Test ensure_channel_exists with cached channel."""
        # Add to cache
        dependency_resolver._channel_cache.add(TestIds.TEST_CHANNEL_1)
        
        session = AsyncMock()
        result = await dependency_resolver.ensure_channel_exists(session, TestIds.TEST_CHANNEL_1)
        
        assert result == TestIds.TEST_CHANNEL_1
        # Should not call repository methods
        dependency_resolver.channel_repo.get_by_channel_id.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_ensure_channel_exists_in_database(
        self, dependency_resolver: DependencyResolver
    ) -> None:
        """Test ensure_channel_exists with existing channel in database."""
        session = AsyncMock()
        existing_channel = MagicMock()
        dependency_resolver.channel_repo.get_by_channel_id.return_value = existing_channel
        
        result = await dependency_resolver.ensure_channel_exists(session, TestIds.TEST_CHANNEL_1)
        
        assert result == TestIds.TEST_CHANNEL_1
        assert TestIds.TEST_CHANNEL_1 in dependency_resolver._channel_cache
        dependency_resolver.channel_repo.get_by_channel_id.assert_called_once_with(
            session, TestIds.TEST_CHANNEL_1
        )
        dependency_resolver.channel_repo.create.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_ensure_channel_exists_create_new(
        self, dependency_resolver: DependencyResolver
    ) -> None:
        """Test ensure_channel_exists creating new channel."""
        session = AsyncMock()
        dependency_resolver.channel_repo.get_by_channel_id.return_value = None
        dependency_resolver.channel_repo.create.return_value = MagicMock()
        
        channel_data = {"title": "Test Channel", "description": "Test Description"}
        result = await dependency_resolver.ensure_channel_exists(
            session, TestIds.TEST_CHANNEL_1, channel_data
        )
        
        assert result == TestIds.TEST_CHANNEL_1
        assert TestIds.TEST_CHANNEL_1 in dependency_resolver._channel_cache
        dependency_resolver.channel_repo.create.assert_called_once()
        
        # Verify ChannelCreate was created with proper data
        create_call = dependency_resolver.channel_repo.create.call_args
        channel_create = create_call[1]["obj_in"]
        assert isinstance(channel_create, ChannelCreate)
        assert channel_create.channel_id == TestIds.TEST_CHANNEL_1
        assert channel_create.title == "Test Channel"
        assert channel_create.description == "Test Description"
    
    @pytest.mark.asyncio
    async def test_ensure_channel_exists_create_placeholder(
        self, dependency_resolver: DependencyResolver
    ) -> None:
        """Test ensure_channel_exists creating placeholder channel."""
        session = AsyncMock()
        dependency_resolver.channel_repo.get_by_channel_id.return_value = None
        dependency_resolver.channel_repo.create.return_value = MagicMock()
        
        result = await dependency_resolver.ensure_channel_exists(session, TestIds.TEST_CHANNEL_1)
        
        assert result == TestIds.TEST_CHANNEL_1
        dependency_resolver.channel_repo.create.assert_called_once()
        
        # Verify placeholder ChannelCreate was created
        create_call = dependency_resolver.channel_repo.create.call_args
        channel_create = create_call[1]["obj_in"]
        assert channel_create.title == f"[Channel {TestIds.TEST_CHANNEL_1}]"
        assert channel_create.description == "Placeholder channel created from Takeout data"


class TestTakeoutSeedingService:
    """Test TakeoutSeedingService class."""
    
    @pytest.fixture
    def mock_repositories(self) -> tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
        """Create mock repositories."""
        channel_repo = AsyncMock()
        video_repo = AsyncMock()
        user_video_repo = AsyncMock()
        playlist_repo = AsyncMock()
        return channel_repo, video_repo, user_video_repo, playlist_repo
    
    @pytest.fixture
    def seeding_service(
        self, mock_repositories: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock]
    ) -> TakeoutSeedingService:
        """Create TakeoutSeedingService with mock repositories."""
        channel_repo, video_repo, user_video_repo, playlist_repo = mock_repositories
        return TakeoutSeedingService(
            channel_repository=channel_repo,
            video_repository=video_repo,
            user_video_repository=user_video_repo,
            playlist_repository=playlist_repo,
            user_id="test_user",
            batch_size=2,  # Small batch size for testing
        )
    
    @pytest.fixture
    def sample_takeout_data(self) -> TakeoutData:
        """Create sample TakeoutData for testing."""
        return TakeoutData(
            takeout_path=Path("/test/takeout"),
            watch_history=[
                TakeoutWatchEntry(
                    video_id=TestIds.NEVER_GONNA_GIVE_YOU_UP,
                    title="Never Gonna Give You Up",
                    title_url=f"https://www.youtube.com/watch?v={TestIds.NEVER_GONNA_GIVE_YOU_UP}",
                    channel_name="Rick Astley",
                    channel_id=TestIds.RICK_ASTLEY_CHANNEL,
                    watched_at=datetime.now(timezone.utc),
                ),
                TakeoutWatchEntry(
                    video_id=TestIds.TEST_VIDEO_1,
                    title="Test Video 2",
                    title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
                    channel_name="Test Channel",
                    channel_id=TestIds.TEST_CHANNEL_2,
                    watched_at=datetime.now(timezone.utc),
                ),
            ],
            subscriptions=[
                TakeoutSubscription(
                    channel_id=TestIds.RICK_ASTLEY_CHANNEL,
                    channel_title="Rick Astley",
                    channel_url=f"https://www.youtube.com/channel/{TestIds.RICK_ASTLEY_CHANNEL}",
                ),
                TakeoutSubscription(
                    channel_id=TestIds.TEST_CHANNEL_2,
                    channel_title="Test Channel",
                    channel_url=f"https://www.youtube.com/channel/{TestIds.TEST_CHANNEL_2}",
                ),
            ],
            playlists=[
                TakeoutPlaylist(
                    name="My Favorites",
                    file_path=Path("/test/My Favorites.csv"),
                    videos=[],
                    video_count=0,
                ),
            ],
        )
    
    def test_seeding_service_initialization(
        self, mock_repositories: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock]
    ) -> None:
        """Test TakeoutSeedingService initialization."""
        channel_repo, video_repo, user_video_repo, playlist_repo = mock_repositories
        
        service = TakeoutSeedingService(
            channel_repository=channel_repo,
            video_repository=video_repo,
            user_video_repository=user_video_repo,
            playlist_repository=playlist_repo,
            user_id="test_user",
            batch_size=50,
        )
        
        assert service.channel_repo == channel_repo
        assert service.video_repo == video_repo
        assert service.user_video_repo == user_video_repo
        assert service.playlist_repo == playlist_repo
        assert service.user_id == "test_user"
        assert service.batch_size == 50
        assert isinstance(service.transformer, TakeoutDataTransformer)
        assert isinstance(service.dependency_resolver, DependencyResolver)
        assert isinstance(service.progress, SeedingProgress)
    
    @pytest.mark.asyncio
    async def test_initialize_progress(
        self, seeding_service: TakeoutSeedingService, sample_takeout_data: TakeoutData
    ) -> None:
        """Test progress initialization."""
        await seeding_service._initialize_progress(sample_takeout_data)
        
        progress = seeding_service.progress
        assert progress.channels_total == 2  # 2 unique channels
        assert progress.videos_total == 2  # 2 unique videos
        assert progress.user_videos_total == 2  # 2 watch entries with timestamps
        assert progress.playlists_total == 1  # 1 playlist
    
    @pytest.mark.asyncio
    async def test_seed_channels_success(
        self, seeding_service: TakeoutSeedingService, sample_takeout_data: TakeoutData
    ) -> None:
        """Test successful channel seeding."""
        session = AsyncMock()
        
        # Mock repository responses
        seeding_service.channel_repo.get_by_channel_id.return_value = None  # No existing channels
        seeding_service.channel_repo.create.return_value = MagicMock()
        
        result = await seeding_service._seed_channels(session, sample_takeout_data)
        
        assert result["seeded"] == 2
        assert result["updated"] == 0
        assert result["failed"] == 0
        assert seeding_service.channel_repo.create.call_count == 2
    
    @pytest.mark.asyncio
    async def test_seed_channels_with_existing(
        self, seeding_service: TakeoutSeedingService, sample_takeout_data: TakeoutData
    ) -> None:
        """Test channel seeding with existing channels."""
        session = AsyncMock()
        
        # Mock existing channel for first ID
        existing_channel = MagicMock()
        def mock_get_by_channel_id(session, channel_id):
            if channel_id == TestIds.RICK_ASTLEY_CHANNEL:
                return existing_channel
            return None
        
        seeding_service.channel_repo.get_by_channel_id.side_effect = mock_get_by_channel_id
        seeding_service.channel_repo.create.return_value = MagicMock()
        
        result = await seeding_service._seed_channels(session, sample_takeout_data)
        
        assert result["seeded"] == 1  # Only one new channel created
        assert result["updated"] == 1  # One existing channel found
        assert result["failed"] == 0
        assert seeding_service.channel_repo.create.call_count == 1
    
    @pytest.mark.asyncio
    async def test_seed_database_complete_workflow(
        self, seeding_service: TakeoutSeedingService, sample_takeout_data: TakeoutData
    ) -> None:
        """Test complete database seeding workflow."""
        session = AsyncMock()
        
        # Mock all repository methods to return success
        seeding_service.channel_repo.get_by_channel_id.return_value = None
        seeding_service.channel_repo.create.return_value = MagicMock()
        seeding_service.video_repo.get_by_video_id.return_value = None
        seeding_service.video_repo.create.return_value = MagicMock()
        seeding_service.user_video_repo.get_by_composite_key.return_value = None
        seeding_service.user_video_repo.create.return_value = MagicMock()
        seeding_service.playlist_repo.get_by_playlist_id.return_value = None
        seeding_service.playlist_repo.create.return_value = MagicMock()
        
        result = await seeding_service.seed_database(session, sample_takeout_data)
        
        assert isinstance(result, SeedingResult)
        assert result.channels_seeded > 0
        assert result.videos_seeded > 0
        assert result.user_videos_created > 0
        assert result.playlists_seeded > 0
        assert result.duration_seconds > 0
        assert 0 <= result.data_quality_score <= 1
        assert result.success_rate > 0
    
    @pytest.mark.asyncio
    async def test_seed_database_with_errors(
        self, seeding_service: TakeoutSeedingService, sample_takeout_data: TakeoutData
    ) -> None:
        """Test database seeding with some errors."""
        session = AsyncMock()
        
        # Mock some failures
        seeding_service.channel_repo.get_by_channel_id.return_value = None
        # Provide enough mock responses for all channel creation attempts
        seeding_service.channel_repo.create.side_effect = [
            MagicMock(),  # First channel succeeds
            Exception("Channel creation failed"),  # Second channel fails
            MagicMock(),  # User channel for playlists succeeds
            MagicMock(),  # Additional placeholder channels succeed
            MagicMock(),
            MagicMock(),
        ]
        seeding_service.video_repo.get_by_video_id.return_value = None
        seeding_service.video_repo.create.return_value = MagicMock()
        seeding_service.user_video_repo.get_by_composite_key.return_value = None
        seeding_service.user_video_repo.create.return_value = MagicMock()
        seeding_service.playlist_repo.get_by_playlist_id.return_value = None
        seeding_service.playlist_repo.create.return_value = MagicMock()
        
        result = await seeding_service.seed_database(session, sample_takeout_data)
        
        assert result.channels_failed > 0
        assert result.success_rate < 100.0
    
    @pytest.mark.asyncio
    async def test_report_progress(
        self, seeding_service: TakeoutSeedingService, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test progress reporting."""
        seeding_service.progress.channels_processed = 5
        seeding_service.progress.channels_total = 10
        seeding_service.progress.videos_processed = 20
        seeding_service.progress.videos_total = 40
        
        await seeding_service.report_progress()
        
        # Note: Progress is printed to stdout AND logged
        # Check that progress was logged (method runs without errors)
        # Progress output: 50.0% = (25/50) * 100
        # The method should complete successfully
        pass  # Test verifies method runs without exception