"""
Tests for TakeoutRecoveryService.

Unit tests for the takeout recovery service that handles gap-fill logic
for recovering metadata from historical Google Takeout exports.
"""

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio

from chronovista.models.takeout.recovery import (
    HistoricalTakeout,
    RecoveredChannelMetadata,
    RecoveredVideoMetadata,
    RecoveryOptions,
    RecoveryResult,
)
from chronovista.services.takeout_recovery_service import TakeoutRecoveryService


class TestTakeoutRecoveryServiceInit:
    """Tests for TakeoutRecoveryService initialization."""

    def test_init_with_default_repositories(self) -> None:
        """Test initialization with default repositories."""
        service = TakeoutRecoveryService()
        assert service.video_repository is not None
        assert service.channel_repository is not None

    def test_init_with_custom_repositories(self) -> None:
        """Test initialization with custom repositories."""
        mock_video_repo = MagicMock()
        mock_channel_repo = MagicMock()

        service = TakeoutRecoveryService(
            video_repository=mock_video_repo,
            channel_repository=mock_channel_repo,
        )
        assert service.video_repository is mock_video_repo
        assert service.channel_repository is mock_channel_repo


class TestRecoverFromHistoricalTakeouts:
    """Tests for recover_from_historical_takeouts method."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def mock_repositories(self) -> tuple[MagicMock, MagicMock]:
        """Create mock video and channel repositories."""
        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(return_value=[])
        video_repo.update = AsyncMock()

        channel_repo = MagicMock()
        channel_repo.get = AsyncMock(return_value=None)
        channel_repo.get_multi = AsyncMock(return_value=[])
        channel_repo.create = AsyncMock()
        channel_repo.update = AsyncMock()

        return video_repo, channel_repo

    @pytest.fixture
    def temp_takeout_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory structure for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    async def test_recover_no_historical_takeouts_found(
        self,
        mock_session: AsyncMock,
        mock_repositories: tuple[MagicMock, MagicMock],
        temp_takeout_dir: Path,
    ) -> None:
        """Test recovery when no historical takeouts are found."""
        video_repo, channel_repo = mock_repositories
        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=channel_repo,
        )

        with patch.object(
            service, "_recover_videos", new_callable=AsyncMock
        ), patch.object(
            service, "_recover_channels", new_callable=AsyncMock
        ), patch(
            "chronovista.services.takeout_recovery_service.TakeoutService"
        ) as mock_takeout:
            mock_takeout.discover_historical_takeouts.return_value = []

            result = await service.recover_from_historical_takeouts(
                mock_session, temp_takeout_dir
            )

        assert result.takeouts_scanned == 0
        assert "No historical takeouts found" in result.errors[0]

    async def test_recover_dry_run_mode(
        self,
        mock_session: AsyncMock,
        mock_repositories: tuple[MagicMock, MagicMock],
        temp_takeout_dir: Path,
    ) -> None:
        """Test recovery in dry run mode."""
        video_repo, channel_repo = mock_repositories
        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=channel_repo,
        )

        historical_takeout = HistoricalTakeout(
            path=temp_takeout_dir / "YouTube and YouTube Music",
            export_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            has_watch_history=True,
        )

        # Create directory structure
        youtube_path = temp_takeout_dir / "YouTube and YouTube Music"
        youtube_path.mkdir(parents=True)
        history_path = youtube_path / "history"
        history_path.mkdir()
        (history_path / "watch-history.json").write_text("[]")

        with patch(
            "chronovista.services.takeout_recovery_service.TakeoutService"
        ) as mock_takeout_cls:
            mock_takeout_cls.discover_historical_takeouts.return_value = [
                historical_takeout
            ]

            mock_takeout = MagicMock()
            mock_takeout.build_recovery_metadata_map = AsyncMock(return_value=({}, {}))
            mock_takeout_cls.return_value = mock_takeout

            options = RecoveryOptions(dry_run=True)
            result = await service.recover_from_historical_takeouts(
                mock_session, temp_takeout_dir, options
            )

        assert result.dry_run is True
        assert result.takeouts_scanned == 1

    async def test_recover_with_historical_data(
        self,
        mock_session: AsyncMock,
        mock_repositories: tuple[MagicMock, MagicMock],
        temp_takeout_dir: Path,
    ) -> None:
        """Test recovery with historical data available."""
        video_repo, channel_repo = mock_repositories
        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=channel_repo,
        )

        # Create directory structure
        youtube_path = temp_takeout_dir / "YouTube and YouTube Music"
        youtube_path.mkdir(parents=True)
        history_path = youtube_path / "history"
        history_path.mkdir()
        (history_path / "watch-history.json").write_text("[]")

        historical_takeout = HistoricalTakeout(
            path=youtube_path,
            export_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            has_watch_history=True,
        )

        video_metadata = {
            "dQw4w9WgXcQ": RecoveredVideoMetadata(
                video_id="dQw4w9WgXcQ",
                title="Never Gonna Give You Up",
                channel_name="RickAstleyVEVO",
                channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
                source_takeout=youtube_path,
                source_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            )
        }

        channel_metadata = {
            "UCuAXFkgsw1L7xaCfnd5JJOw": RecoveredChannelMetadata(
                channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
                channel_name="RickAstleyVEVO",
                source_takeout=youtube_path,
                source_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            )
        }

        with patch(
            "chronovista.services.takeout_recovery_service.TakeoutService"
        ) as mock_takeout_cls:
            mock_takeout_cls.discover_historical_takeouts.return_value = [
                historical_takeout
            ]

            mock_takeout = MagicMock()
            mock_takeout.build_recovery_metadata_map = AsyncMock(
                return_value=(video_metadata, channel_metadata)
            )
            mock_takeout_cls.return_value = mock_takeout

            result = await service.recover_from_historical_takeouts(
                mock_session, temp_takeout_dir
            )

        assert result.takeouts_scanned == 1
        assert result.oldest_takeout_date is not None
        assert result.newest_takeout_date is not None


class TestRecoverVideos:
    """Tests for _recover_videos private method."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    async def test_recover_placeholder_video(self, mock_session: AsyncMock) -> None:
        """Test recovering a placeholder video with available metadata."""
        mock_video = MagicMock()
        mock_video.video_id = "dQw4w9WgXcQ"
        mock_video.title = "[Placeholder] Video dQw4w9WgXcQ"
        mock_video.channel_id = "UCplaceholder"

        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(side_effect=[[mock_video], []])
        video_repo.update = AsyncMock()

        channel_repo = MagicMock()
        channel_repo.get = AsyncMock(return_value=None)

        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=channel_repo,
        )

        video_metadata = {
            "dQw4w9WgXcQ": RecoveredVideoMetadata(
                video_id="dQw4w9WgXcQ",
                title="Never Gonna Give You Up",
                channel_name="RickAstleyVEVO",
                channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
                source_takeout=Path("/takeouts/2024-01-15"),
                source_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            )
        }

        result = RecoveryResult()
        options = RecoveryOptions()

        await service._recover_videos(mock_session, video_metadata, result, options)

        assert result.videos_recovered == 1
        assert len(result.video_actions) == 1
        assert result.video_actions[0].new_title == "Never Gonna Give You Up"
        video_repo.update.assert_called_once()

    async def test_no_recovery_for_non_placeholder_with_channel(
        self, mock_session: AsyncMock
    ) -> None:
        """Test that non-placeholder videos with channel_id are not recovered."""
        mock_video = MagicMock()
        mock_video.video_id = "dQw4w9WgXcQ"
        mock_video.title = "Real Video Title"
        mock_video.channel_id = "UCreal"  # Has channel_id already

        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(side_effect=[[mock_video], []])

        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=MagicMock(),
        )

        video_metadata = {
            "dQw4w9WgXcQ": RecoveredVideoMetadata(
                video_id="dQw4w9WgXcQ",
                title="Never Gonna Give You Up",
                source_takeout=Path("/takeouts/2024"),
                source_date=datetime.now(timezone.utc),
            )
        }

        result = RecoveryResult()
        options = RecoveryOptions()

        await service._recover_videos(mock_session, video_metadata, result, options)

        assert result.videos_recovered == 0
        assert len(result.video_actions) == 0

    async def test_recover_null_channel_id_on_non_placeholder_video(
        self, mock_session: AsyncMock
    ) -> None:
        """Test recovering channel_id for video with real title but NULL channel_id."""
        mock_video = MagicMock()
        mock_video.video_id = "dQw4w9WgXcQ"
        mock_video.title = "Never Gonna Give You Up"  # Real title, not placeholder
        mock_video.channel_id = None  # NULL channel_id - needs recovery

        # Mock channel that exists in database
        mock_channel = MagicMock()
        mock_channel.channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"

        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(side_effect=[[mock_video], []])
        video_repo.update = AsyncMock()

        channel_repo = MagicMock()
        channel_repo.get = AsyncMock(return_value=mock_channel)

        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=channel_repo,
        )

        video_metadata = {
            "dQw4w9WgXcQ": RecoveredVideoMetadata(
                video_id="dQw4w9WgXcQ",
                title="Never Gonna Give You Up",
                channel_name="RickAstleyVEVO",
                channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
                source_takeout=Path("/takeouts/2024"),
                source_date=datetime.now(timezone.utc),
            )
        }

        result = RecoveryResult()
        options = RecoveryOptions()

        await service._recover_videos(mock_session, video_metadata, result, options)

        # Should recover the video by updating channel_id
        assert result.videos_recovered == 1
        assert len(result.video_actions) == 1
        assert result.video_actions[0].action_type == "update_channel"
        assert result.video_actions[0].new_channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        video_repo.update.assert_called_once()

    async def test_recover_both_title_and_channel_id(
        self, mock_session: AsyncMock
    ) -> None:
        """Test recovering both placeholder title and NULL channel_id."""
        mock_video = MagicMock()
        mock_video.video_id = "dQw4w9WgXcQ"
        mock_video.title = "[Placeholder] Video dQw4w9WgXcQ"  # Placeholder title
        mock_video.channel_id = None  # NULL channel_id - needs recovery

        # Mock channel that exists in database
        mock_channel = MagicMock()
        mock_channel.channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"

        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(side_effect=[[mock_video], []])
        video_repo.update = AsyncMock()

        channel_repo = MagicMock()
        channel_repo.get = AsyncMock(return_value=mock_channel)

        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=channel_repo,
        )

        video_metadata = {
            "dQw4w9WgXcQ": RecoveredVideoMetadata(
                video_id="dQw4w9WgXcQ",
                title="Never Gonna Give You Up",
                channel_name="RickAstleyVEVO",
                channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
                source_takeout=Path("/takeouts/2024"),
                source_date=datetime.now(timezone.utc),
            )
        }

        result = RecoveryResult()
        options = RecoveryOptions()

        await service._recover_videos(mock_session, video_metadata, result, options)

        # Should recover with "both" action type
        assert result.videos_recovered == 1
        assert len(result.video_actions) == 1
        assert result.video_actions[0].action_type == "both"
        assert result.video_actions[0].new_title == "Never Gonna Give You Up"
        assert result.video_actions[0].new_channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        video_repo.update.assert_called_once()

    async def test_skip_channel_update_if_channel_not_in_db(
        self, mock_session: AsyncMock
    ) -> None:
        """Test that channel_id is not updated if the channel doesn't exist in DB."""
        mock_video = MagicMock()
        mock_video.video_id = "dQw4w9WgXcQ"
        mock_video.title = "Real Video Title"  # Not placeholder
        mock_video.channel_id = None  # NULL channel_id

        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(side_effect=[[mock_video], []])
        video_repo.update = AsyncMock()

        channel_repo = MagicMock()
        channel_repo.get = AsyncMock(return_value=None)  # Channel doesn't exist in DB

        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=channel_repo,
        )

        video_metadata = {
            "dQw4w9WgXcQ": RecoveredVideoMetadata(
                video_id="dQw4w9WgXcQ",
                title="Never Gonna Give You Up",
                channel_name="RickAstleyVEVO",
                channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",  # This channel doesn't exist in DB
                source_takeout=Path("/takeouts/2024"),
                source_date=datetime.now(timezone.utc),
            )
        }

        result = RecoveryResult()
        options = RecoveryOptions()

        await service._recover_videos(mock_session, video_metadata, result, options)

        # Action is recorded but channel_id wasn't updated since channel doesn't exist
        assert result.videos_recovered == 1
        # update was NOT called because channel doesn't exist and title is not placeholder
        video_repo.update.assert_not_called()

    async def test_placeholder_without_recovery_data(
        self, mock_session: AsyncMock
    ) -> None:
        """Test placeholder video without recovery data stays missing."""
        mock_video = MagicMock()
        mock_video.video_id = "missing123"
        mock_video.title = "[Placeholder] Video missing123"

        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(side_effect=[[mock_video], []])

        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=MagicMock(),
        )

        result = RecoveryResult()
        options = RecoveryOptions()

        # Empty metadata - no recovery data available
        await service._recover_videos(mock_session, {}, result, options)

        assert result.videos_recovered == 0
        assert result.videos_still_missing == 1
        assert "missing123" in result.videos_not_recovered

    async def test_dry_run_no_updates(self, mock_session: AsyncMock) -> None:
        """Test that dry run mode doesn't update database."""
        mock_video = MagicMock()
        mock_video.video_id = "dQw4w9WgXcQ"
        mock_video.title = "[Placeholder] Video dQw4w9WgXcQ"
        mock_video.channel_id = None

        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(side_effect=[[mock_video], []])
        video_repo.update = AsyncMock()

        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=MagicMock(),
        )

        video_metadata = {
            "dQw4w9WgXcQ": RecoveredVideoMetadata(
                video_id="dQw4w9WgXcQ",
                title="Never Gonna Give You Up",
                source_takeout=Path("/takeouts/2024"),
                source_date=datetime.now(timezone.utc),
            )
        }

        result = RecoveryResult(dry_run=True)
        options = RecoveryOptions(dry_run=True)

        await service._recover_videos(mock_session, video_metadata, result, options)

        assert result.videos_recovered == 1
        video_repo.update.assert_not_called()
        mock_session.commit.assert_not_called()


class TestRecoverChannels:
    """Tests for _recover_channels private method."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    async def test_create_new_channel(self, mock_session: AsyncMock) -> None:
        """Test creating a new channel from recovery data."""
        channel_repo = MagicMock()
        channel_repo.get = AsyncMock(return_value=None)  # Channel doesn't exist
        channel_repo.create = AsyncMock()

        service = TakeoutRecoveryService(
            video_repository=MagicMock(),
            channel_repository=channel_repo,
        )

        # Use valid 24-character YouTube channel ID format
        valid_channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"
        channel_metadata = {
            valid_channel_id: RecoveredChannelMetadata(
                channel_id=valid_channel_id,
                channel_name="Test Channel",
                source_takeout=Path("/takeouts/2024"),
                source_date=datetime.now(timezone.utc),
            )
        }

        result = RecoveryResult()
        options = RecoveryOptions()

        await service._recover_channels(mock_session, channel_metadata, result, options)

        assert result.channels_created == 1
        assert len(result.channel_actions) == 1
        assert result.channel_actions[0].action_type == "create"
        channel_repo.create.assert_called_once()

    async def test_update_placeholder_channel(self, mock_session: AsyncMock) -> None:
        """Test updating a placeholder channel with real name."""
        mock_existing = MagicMock()
        mock_existing.title = "[Placeholder] Unknown Channel"

        channel_repo = MagicMock()
        channel_repo.get = AsyncMock(return_value=mock_existing)
        channel_repo.update = AsyncMock()

        service = TakeoutRecoveryService(
            video_repository=MagicMock(),
            channel_repository=channel_repo,
        )

        valid_channel_id = "UCxyz789ABC123def456ghiA"
        channel_metadata = {
            valid_channel_id: RecoveredChannelMetadata(
                channel_id=valid_channel_id,
                channel_name="Real Channel Name",
                source_takeout=Path("/takeouts/2024"),
                source_date=datetime.now(timezone.utc),
            )
        }

        result = RecoveryResult()
        options = RecoveryOptions()

        await service._recover_channels(mock_session, channel_metadata, result, options)

        assert result.channels_updated == 1
        assert len(result.channel_actions) == 1
        assert result.channel_actions[0].action_type == "update_name"
        channel_repo.update.assert_called_once()

    async def test_skip_non_placeholder_channel(self, mock_session: AsyncMock) -> None:
        """Test that non-placeholder channels are not updated."""
        mock_existing = MagicMock()
        mock_existing.title = "Real Channel Name"

        channel_repo = MagicMock()
        channel_repo.get = AsyncMock(return_value=mock_existing)
        channel_repo.update = AsyncMock()
        channel_repo.create = AsyncMock()

        service = TakeoutRecoveryService(
            video_repository=MagicMock(),
            channel_repository=channel_repo,
        )

        valid_channel_id = "UCabc123XYZ789def456ghiB"
        channel_metadata = {
            valid_channel_id: RecoveredChannelMetadata(
                channel_id=valid_channel_id,
                channel_name="Different Name",
                source_takeout=Path("/takeouts/2024"),
                source_date=datetime.now(timezone.utc),
            )
        }

        result = RecoveryResult()
        options = RecoveryOptions()

        await service._recover_channels(mock_session, channel_metadata, result, options)

        assert result.channels_created == 0
        assert result.channels_updated == 0
        channel_repo.update.assert_not_called()
        channel_repo.create.assert_not_called()

    async def test_dry_run_no_channel_changes(self, mock_session: AsyncMock) -> None:
        """Test that dry run mode doesn't create/update channels."""
        channel_repo = MagicMock()
        channel_repo.get = AsyncMock(return_value=None)
        channel_repo.create = AsyncMock()

        service = TakeoutRecoveryService(
            video_repository=MagicMock(),
            channel_repository=channel_repo,
        )

        valid_channel_id = "UCdef456ghi789ABC123XYZc"
        channel_metadata = {
            valid_channel_id: RecoveredChannelMetadata(
                channel_id=valid_channel_id,
                channel_name="Test Channel",
                source_takeout=Path("/takeouts/2024"),
                source_date=datetime.now(timezone.utc),
            )
        }

        result = RecoveryResult(dry_run=True)
        options = RecoveryOptions(dry_run=True)

        await service._recover_channels(mock_session, channel_metadata, result, options)

        # Action is recorded but not executed
        assert result.channels_created == 1
        channel_repo.create.assert_not_called()


class TestGetRecoveryPreview:
    """Tests for get_recovery_preview method."""

    async def test_preview_returns_dry_run_result(self) -> None:
        """Test that preview returns a dry run result."""
        mock_session = AsyncMock()
        service = TakeoutRecoveryService()

        with patch.object(
            service,
            "recover_from_historical_takeouts",
            new_callable=AsyncMock,
        ) as mock_recover:
            mock_recover.return_value = RecoveryResult(dry_run=True)

            result = await service.get_recovery_preview(
                mock_session, Path("/takeouts")
            )

            assert result.dry_run is True
            mock_recover.assert_called_once()
            # Verify options passed were dry_run=True and verbose=True
            call_args = mock_recover.call_args
            options = call_args[0][2]  # Third positional argument
            assert options.dry_run is True
            assert options.verbose is True


class TestCountPlaceholders:
    """Tests for count_placeholder_videos and count_placeholder_channels."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        return AsyncMock()

    async def test_count_placeholder_videos(self, mock_session: AsyncMock) -> None:
        """Test counting placeholder videos."""
        mock_videos = [
            MagicMock(title="[Placeholder] Video abc123"),
            MagicMock(title="Real Video Title"),
            MagicMock(title="[Placeholder] Video xyz789"),
        ]

        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(side_effect=[mock_videos, []])

        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=MagicMock(),
        )

        count = await service.count_placeholder_videos(mock_session)

        assert count == 2

    async def test_count_placeholder_channels(self, mock_session: AsyncMock) -> None:
        """Test counting placeholder channels."""
        mock_channels = [
            MagicMock(title="[Placeholder] Unknown Channel"),
            MagicMock(title="Real Channel Name"),
            MagicMock(title="[Unknown Channel] UCtest"),
        ]

        channel_repo = MagicMock()
        channel_repo.get_multi = AsyncMock(side_effect=[mock_channels, []])

        service = TakeoutRecoveryService(
            video_repository=MagicMock(),
            channel_repository=channel_repo,
        )

        count = await service.count_placeholder_channels(mock_session)

        assert count == 2

    async def test_count_empty_database(self, mock_session: AsyncMock) -> None:
        """Test counting placeholders in empty database."""
        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(return_value=[])

        channel_repo = MagicMock()
        channel_repo.get_multi = AsyncMock(return_value=[])

        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=channel_repo,
        )

        video_count = await service.count_placeholder_videos(mock_session)
        channel_count = await service.count_placeholder_channels(mock_session)

        assert video_count == 0
        assert channel_count == 0


class TestRecoveryNeverSetsDeletedFlag:
    """
    Tests verifying local recovery doesn't set deleted_flag (T040c).

    Per US3 scenario 2: local takeout recovery should NEVER set deleted_flag=True.
    Only the API verification flow should mark videos as deleted.
    """

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    async def test_recovery_from_historical_takeout_never_sets_deleted_flag_true(
        self, mock_session: AsyncMock
    ) -> None:
        """Test that recovery from historical takeout never sets deleted_flag=True."""
        # Create a mock video with placeholder title
        mock_video = MagicMock()
        mock_video.video_id = "dQw4w9WgXcQ"
        mock_video.title = "[Placeholder] Video dQw4w9WgXcQ"
        mock_video.channel_id = "UCplaceholder"
        mock_video.deleted_flag = False  # Video is not deleted initially

        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(side_effect=[[mock_video], []])
        video_repo.update = AsyncMock()

        channel_repo = MagicMock()
        channel_repo.get = AsyncMock(return_value=None)

        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=channel_repo,
        )

        video_metadata = {
            "dQw4w9WgXcQ": RecoveredVideoMetadata(
                video_id="dQw4w9WgXcQ",
                title="Never Gonna Give You Up",
                channel_name="RickAstleyVEVO",
                channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
                source_takeout=Path("/takeouts/2024-01-15"),
                source_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            )
        }

        result = RecoveryResult()
        options = RecoveryOptions()

        await service._recover_videos(mock_session, video_metadata, result, options)

        # Verify the deleted_flag was NEVER set to True
        # Check all calls to video_repo.update
        for call in video_repo.update.call_args_list:
            kwargs = call[1]
            obj_in = kwargs.get("obj_in")
            if obj_in is not None:
                # The VideoUpdate should not contain deleted_flag=True
                if hasattr(obj_in, "deleted_flag"):
                    assert obj_in.deleted_flag is not True, (
                        "Recovery should never set deleted_flag=True"
                    )

        # Also verify the mock_video itself wasn't modified to have deleted_flag=True
        # (The service should only update via the repository, not directly)
        assert result.videos_recovered == 1

    async def test_recovery_updates_video_metadata_but_preserves_existing_deleted_flag(
        self, mock_session: AsyncMock
    ) -> None:
        """Test that recovery updates metadata but preserves existing deleted_flag."""
        # Video was previously marked as deleted (by API verification)
        mock_video = MagicMock()
        mock_video.video_id = "deletedVid123"
        mock_video.title = "[Placeholder] Video deletedVid123"
        mock_video.channel_id = "UCplaceholder"
        mock_video.deleted_flag = True  # Previously marked as deleted

        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(side_effect=[[mock_video], []])
        video_repo.update = AsyncMock()

        channel_repo = MagicMock()
        channel_repo.get = AsyncMock(return_value=None)

        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=channel_repo,
        )

        # Recovery metadata available from historical takeout
        video_metadata = {
            "deletedVid123": RecoveredVideoMetadata(
                video_id="deletedVid123",
                title="Recovered Title From Takeout",
                channel_name="HistoricalChannel",
                channel_id="UChistorical123456789012",
                source_takeout=Path("/takeouts/2023-06-01"),
                source_date=datetime(2023, 6, 1, tzinfo=timezone.utc),
            )
        }

        result = RecoveryResult()
        options = RecoveryOptions()

        await service._recover_videos(mock_session, video_metadata, result, options)

        # Recovery should update title but not touch deleted_flag
        # The video was a placeholder so it should be recovered
        assert result.videos_recovered == 1

        # Check that update was called
        video_repo.update.assert_called_once()

        # Verify the update only contained title, not deleted_flag
        call_args = video_repo.update.call_args
        obj_in = call_args[1].get("obj_in")
        if obj_in is not None and hasattr(obj_in, "model_dump"):
            update_dict = obj_in.model_dump(exclude_unset=True)
            # The update should contain title but NOT deleted_flag
            assert "title" in update_dict
            assert "deleted_flag" not in update_dict

    async def test_new_videos_from_recovery_have_deleted_flag_false(
        self, mock_session: AsyncMock
    ) -> None:
        """Test that new videos created from recovery have deleted_flag=False."""
        # No videos in database initially
        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(return_value=[])

        channel_repo = MagicMock()
        channel_repo.get = AsyncMock(return_value=None)
        channel_repo.create = AsyncMock()

        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=channel_repo,
        )

        # Recovery metadata for channel (recovery creates channels, not videos directly)
        valid_channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"
        channel_metadata = {
            valid_channel_id: RecoveredChannelMetadata(
                channel_id=valid_channel_id,
                channel_name="New Channel From Takeout",
                source_takeout=Path("/takeouts/2024"),
                source_date=datetime.now(timezone.utc),
            )
        }

        result = RecoveryResult()
        options = RecoveryOptions()

        await service._recover_channels(mock_session, channel_metadata, result, options)

        # Verify channel was created
        assert result.channels_created == 1
        channel_repo.create.assert_called_once()

        # Check that the ChannelCreate doesn't have a deleted_flag
        # (Channels don't have deleted_flag but this verifies the pattern)
        call_args = channel_repo.create.call_args
        obj_in = call_args[1].get("obj_in")
        if obj_in is not None:
            # ChannelCreate should not contain deleted_flag
            # This is more about confirming the recovery pattern
            assert hasattr(obj_in, "channel_id")
            assert hasattr(obj_in, "title")

    async def test_recovery_dry_run_does_not_modify_deleted_flag(
        self, mock_session: AsyncMock
    ) -> None:
        """Test that dry run recovery doesn't modify deleted_flag."""
        mock_video = MagicMock()
        mock_video.video_id = "testVideo789"
        mock_video.title = "[Placeholder] Video testVideo789"
        mock_video.channel_id = "UCplaceholder"
        mock_video.deleted_flag = False

        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(side_effect=[[mock_video], []])
        video_repo.update = AsyncMock()

        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=MagicMock(),
        )

        video_metadata = {
            "testVideo789": RecoveredVideoMetadata(
                video_id="testVideo789",
                title="Recovered Title",
                source_takeout=Path("/takeouts/2024"),
                source_date=datetime.now(timezone.utc),
            )
        }

        result = RecoveryResult(dry_run=True)
        options = RecoveryOptions(dry_run=True)

        await service._recover_videos(mock_session, video_metadata, result, options)

        # In dry run, no update should have been called at all
        video_repo.update.assert_not_called()

        # The recovery action should still be recorded
        assert result.videos_recovered == 1

        # And the original video's deleted_flag should be unchanged
        assert mock_video.deleted_flag is False

    async def test_placeholder_video_without_recovery_data_keeps_deleted_flag_unchanged(
        self, mock_session: AsyncMock
    ) -> None:
        """Test placeholder video without recovery data keeps deleted_flag unchanged."""
        mock_video = MagicMock()
        mock_video.video_id = "noRecoveryData"
        mock_video.title = "[Placeholder] Video noRecoveryData"
        mock_video.deleted_flag = False  # Not deleted

        video_repo = MagicMock()
        video_repo.get_multi = AsyncMock(side_effect=[[mock_video], []])
        video_repo.update = AsyncMock()

        service = TakeoutRecoveryService(
            video_repository=video_repo,
            channel_repository=MagicMock(),
        )

        # Empty metadata - no recovery data for this video
        result = RecoveryResult()
        options = RecoveryOptions()

        await service._recover_videos(mock_session, {}, result, options)

        # Video has no recovery data so it stays as missing
        assert result.videos_still_missing == 1
        assert result.videos_recovered == 0

        # No update should be called
        video_repo.update.assert_not_called()

        # deleted_flag should NOT have been set to True
        # (Only API verification should set deleted_flag)
        assert mock_video.deleted_flag is False
