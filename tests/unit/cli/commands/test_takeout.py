"""
Tests for Takeout CLI Commands.

Comprehensive test coverage for CLI commands that explore and analyze Google Takeout data.
"""

import asyncio
import csv
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mark all async tests in this module
pytestmark = pytest.mark.asyncio

from chronovista.cli.commands.takeout import (
    _analyze_channel_clusters,
    _analyze_playlist_overlap,
    _analyze_temporal_patterns,
    _build_video_title_lookup,
    _detect_csv_type,
    _display_analysis_summary,
    _display_generic_csv,
    _display_generic_json,
    _display_playlist_csv,
    _display_subscriptions_csv,
    _display_watch_history_json,
    _inspect_csv_file,
    _inspect_json_file,
    _peek_comments,
    _peek_live_chats,
    _peek_playlists,
    _peek_subscriptions,
    _peek_watch_history,
    _show_detailed_playlist,
    console,
)
from chronovista.models.takeout import (
    ChannelSummary,
    ContentGap,
    DateRange,
    PlaylistAnalysis,
    TakeoutAnalysis,
    TakeoutData,
    TakeoutPlaylist,
    TakeoutPlaylistItem,
    TakeoutSubscription,
    TakeoutWatchEntry,
    ViewingPatterns,
)
from chronovista.services.takeout_service import TakeoutService


@pytest.fixture
def temp_takeout_dir():
    """Create a temporary directory structure for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    youtube_dir = temp_dir / "YouTube and YouTube Music"
    youtube_dir.mkdir(parents=True)

    # Create subdirectories
    (youtube_dir / "history").mkdir()
    (youtube_dir / "playlists").mkdir()
    (youtube_dir / "subscriptions").mkdir()
    (youtube_dir / "comments").mkdir()
    (youtube_dir / "live_chat").mkdir()

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_progress():
    """Create a mock progress bar for testing."""
    progress = MagicMock()
    progress.update = MagicMock()
    progress.add_task = MagicMock(return_value="mock_task_id")
    return progress


@pytest.fixture
def sample_takeout_data():
    """Create sample takeout data for testing."""
    return TakeoutData(
        takeout_path=Path("/test/path"),
        watch_history=[
            TakeoutWatchEntry(
                video_id="test_video_1",
                title="Test Video 1",
                title_url="https://www.youtube.com/watch?v=test_video_1",
                channel_name="Test Channel",
                watched_at=datetime(2023, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
            ),
            TakeoutWatchEntry(
                video_id="test_video_2",
                title="Test Video 2",
                title_url="https://www.youtube.com/watch?v=test_video_2",
                channel_name="Another Channel",
                watched_at=datetime(2023, 1, 16, 15, 45, 0, tzinfo=timezone.utc),
            ),
        ],
        playlists=[
            TakeoutPlaylist(
                name="Test Playlist",
                file_path=Path("/test/playlist.csv"),
                videos=[
                    TakeoutPlaylistItem(
                        video_id="test_video_1",
                        creation_timestamp=datetime(
                            2023, 1, 15, 14, 30, 0, tzinfo=timezone.utc
                        ),
                    )
                ],
            )
        ],
        subscriptions=[
            TakeoutSubscription(
                channel_id="UC123",
                channel_title="Test Channel",
                channel_url="https://www.youtube.com/channel/UC123",
            )
        ],
    )


@pytest.fixture
def mock_takeout_service(sample_takeout_data):
    """Create a mock TakeoutService for testing."""
    service = MagicMock(spec=TakeoutService)
    service.parse_all = AsyncMock(return_value=sample_takeout_data)
    service.parse_watch_history = AsyncMock(
        return_value=sample_takeout_data.watch_history
    )
    service.parse_playlists = AsyncMock(return_value=sample_takeout_data.playlists)
    service.parse_subscriptions = AsyncMock(
        return_value=sample_takeout_data.subscriptions
    )

    # Mock analysis methods
    service.generate_comprehensive_analysis = AsyncMock(
        return_value=MagicMock(spec=TakeoutAnalysis)
    )
    service.analyze_playlist_overlap = AsyncMock(return_value={})
    service.analyze_channel_clusters = AsyncMock(return_value={})
    service.analyze_temporal_patterns = AsyncMock(return_value={})

    return service


class TestBuildVideoTitleLookup:
    """Tests for _build_video_title_lookup function."""

    async def test_build_video_title_lookup_success(self, mock_takeout_service):
        """Test successful video title lookup building."""
        watch_history = [
            TakeoutWatchEntry(
                video_id="video1",
                title="Video Title 1",
                title_url="https://www.youtube.com/watch?v=video1",
            ),
            TakeoutWatchEntry(
                video_id="video2",
                title="Video Title 2",
                title_url="https://www.youtube.com/watch?v=video2",
            ),
            TakeoutWatchEntry(
                video_id=None,  # Should be skipped
                title="No Video ID",
                title_url="https://example.com/not-youtube",
            ),
        ]
        mock_takeout_service.parse_watch_history = AsyncMock(return_value=watch_history)

        result = await _build_video_title_lookup(mock_takeout_service)

        assert result == {"video1": "Video Title 1", "video2": "Video Title 2"}
        mock_takeout_service.parse_watch_history.assert_called_once()

    async def test_build_video_title_lookup_with_exception(self, mock_takeout_service):
        """Test video title lookup when parse_watch_history fails."""
        mock_takeout_service.parse_watch_history.side_effect = Exception("Parse error")

        result = await _build_video_title_lookup(mock_takeout_service)

        assert result == {}

    async def test_build_video_title_lookup_empty_history(self, mock_takeout_service):
        """Test video title lookup with empty watch history."""
        mock_takeout_service.parse_watch_history.return_value = []

        result = await _build_video_title_lookup(mock_takeout_service)

        assert result == {}


class TestPeekPlaylists:
    """Tests for _peek_playlists function."""

    async def test_peek_playlists_success(self, mock_takeout_service, mock_progress):
        """Test successful playlist peeking."""
        playlists = [
            TakeoutPlaylist(
                name="Test Playlist 1",
                file_path=Path("/test/playlist1.csv"),
                videos=[
                    TakeoutPlaylistItem(video_id="video1"),
                    TakeoutPlaylistItem(video_id="video2"),
                ],
            ),
            TakeoutPlaylist(
                name="Test Playlist 2",
                file_path=Path("/test/playlist2.csv"),
                videos=[TakeoutPlaylistItem(video_id="video3")],
            ),
        ]
        mock_takeout_service.parse_playlists.return_value = playlists

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_playlists(
                mock_takeout_service,
                limit=10,
                sort_order="default",
                progress=mock_progress,
                task_id="test_task",
            )

        mock_takeout_service.parse_playlists.assert_called_once()
        mock_console.print.assert_called()

    async def test_peek_playlists_with_filter(
        self, mock_takeout_service, mock_progress
    ):
        """Test playlist peeking with name filter."""
        playlists = [
            TakeoutPlaylist(
                name="Music Playlist",
                file_path=Path("/test/music.csv"),
                videos=[TakeoutPlaylistItem(video_id="music1")],
            ),
            TakeoutPlaylist(
                name="Tech Playlist",
                file_path=Path("/test/tech.csv"),
                videos=[TakeoutPlaylistItem(video_id="tech1")],
            ),
        ]
        mock_takeout_service.parse_playlists.return_value = playlists

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_playlists(
                mock_takeout_service,
                limit=10,
                sort_order="default",
                progress=mock_progress,
                task_id="test_task",
                filter_name="Music",
            )

        mock_console.print.assert_called()

    async def test_peek_playlists_empty(self, mock_takeout_service, mock_progress):
        """Test playlist peeking with no playlists."""
        mock_takeout_service.parse_playlists.return_value = []

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_playlists(
                mock_takeout_service,
                limit=10,
                sort_order="default",
                progress=mock_progress,
                task_id="test_task",
            )

        mock_console.print.assert_called()

    async def test_peek_playlists_sort_by_size(
        self, mock_takeout_service, mock_progress
    ):
        """Test playlist peeking with size sorting."""
        playlists = [
            TakeoutPlaylist(
                name="Small",
                file_path=Path("/test/small.csv"),
                videos=[TakeoutPlaylistItem(video_id="v1")],
            ),
            TakeoutPlaylist(
                name="Large",
                file_path=Path("/test/large.csv"),
                videos=[TakeoutPlaylistItem(video_id=f"v{i}") for i in range(5)],
            ),
        ]
        mock_takeout_service.parse_playlists.return_value = playlists

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_playlists(
                mock_takeout_service,
                limit=10,
                sort_order="recent",
                progress=mock_progress,
                task_id="test_task",
            )

        mock_console.print.assert_called()


class TestPeekWatchHistory:
    """Tests for _peek_watch_history function."""

    async def test_peek_watch_history_success(
        self, mock_takeout_service, mock_progress
    ):
        """Test successful watch history peeking."""
        history = [
            TakeoutWatchEntry(
                video_id="video1",
                title="Video 1",
                title_url="https://www.youtube.com/watch?v=video1",
                channel_name="Channel 1",
                watched_at=datetime(2023, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
            ),
            TakeoutWatchEntry(
                video_id="video2",
                title="Video 2",
                title_url="https://www.youtube.com/watch?v=video2",
                channel_name="Channel 2",
                watched_at=datetime(2023, 1, 16, 15, 45, 0, tzinfo=timezone.utc),
            ),
        ]
        mock_takeout_service.parse_watch_history.return_value = history

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_watch_history(
                mock_takeout_service,
                limit=10,
                sort_order="default",
                progress=mock_progress,
                task_id="test_task",
            )

        mock_takeout_service.parse_watch_history.assert_called_once()
        mock_console.print.assert_called()

    async def test_peek_watch_history_with_channel_filter(
        self, mock_takeout_service, mock_progress
    ):
        """Test watch history peeking with channel filter."""
        history = [
            TakeoutWatchEntry(
                video_id="video1",
                title="Video 1",
                title_url="https://www.youtube.com/watch?v=video1",
                channel_name="Target Channel",
                watched_at=datetime(2023, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
            ),
            TakeoutWatchEntry(
                video_id="video2",
                title="Video 2",
                title_url="https://www.youtube.com/watch?v=video2",
                channel_name="Other Channel",
                watched_at=datetime(2023, 1, 16, 15, 45, 0, tzinfo=timezone.utc),
            ),
        ]
        mock_takeout_service.parse_watch_history.return_value = history

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_watch_history(
                mock_takeout_service,
                limit=10,
                sort_order="default",
                progress=mock_progress,
                task_id="test_task",
                filter_name="Target",
            )

        mock_console.print.assert_called()

    async def test_peek_watch_history_sort_recent(
        self, mock_takeout_service, mock_progress
    ):
        """Test watch history peeking with recent sorting."""
        history = [
            TakeoutWatchEntry(
                video_id="old_video",
                title="Old Video",
                title_url="https://www.youtube.com/watch?v=old_video",
                watched_at=datetime(2023, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
            TakeoutWatchEntry(
                video_id="new_video",
                title="New Video",
                title_url="https://www.youtube.com/watch?v=new_video",
                watched_at=datetime(2023, 1, 20, 15, 0, 0, tzinfo=timezone.utc),
            ),
        ]
        mock_takeout_service.parse_watch_history.return_value = history

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_watch_history(
                mock_takeout_service,
                limit=10,
                sort_order="recent",
                progress=mock_progress,
                task_id="test_task",
            )

        mock_console.print.assert_called()

    async def test_peek_watch_history_empty(self, mock_takeout_service, mock_progress):
        """Test watch history peeking with empty history."""
        mock_takeout_service.parse_watch_history.return_value = []

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_watch_history(
                mock_takeout_service,
                limit=10,
                sort_order="default",
                progress=mock_progress,
                task_id="test_task",
            )

        mock_console.print.assert_called()


class TestPeekSubscriptions:
    """Tests for _peek_subscriptions function."""

    async def test_peek_subscriptions_success(
        self, mock_takeout_service, mock_progress
    ):
        """Test successful subscriptions peeking."""
        subscriptions = [
            TakeoutSubscription(
                channel_id="UC123",
                channel_title="Test Channel 1",
                channel_url="https://www.youtube.com/channel/UC123",
            ),
            TakeoutSubscription(
                channel_id="UC456",
                channel_title="Test Channel 2",
                channel_url="https://www.youtube.com/channel/UC456",
            ),
        ]
        mock_takeout_service.parse_subscriptions.return_value = subscriptions

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_subscriptions(
                mock_takeout_service,
                limit=10,
                progress=mock_progress,
                task_id="test_task",
            )

        mock_takeout_service.parse_subscriptions.assert_called_once()
        mock_console.print.assert_called()

    async def test_peek_subscriptions_with_filter(
        self, mock_takeout_service, mock_progress
    ):
        """Test subscriptions peeking with channel filter."""
        subscriptions = [
            TakeoutSubscription(
                channel_id="UC123",
                channel_title="Target Channel",
                channel_url="https://www.youtube.com/channel/UC123",
            ),
            TakeoutSubscription(
                channel_id="UC456",
                channel_title="Other Channel",
                channel_url="https://www.youtube.com/channel/UC456",
            ),
        ]
        mock_takeout_service.parse_subscriptions.return_value = subscriptions

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_subscriptions(
                mock_takeout_service,
                limit=10,
                progress=mock_progress,
                task_id="test_task",
                filter_name="Target",
            )

        mock_console.print.assert_called()

    async def test_peek_subscriptions_empty(self, mock_takeout_service, mock_progress):
        """Test subscriptions peeking with no subscriptions."""
        mock_takeout_service.parse_subscriptions.return_value = []

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_subscriptions(
                mock_takeout_service,
                limit=10,
                progress=mock_progress,
                task_id="test_task",
            )

        mock_console.print.assert_called()


class TestShowDetailedPlaylist:
    """Tests for _show_detailed_playlist function."""

    async def test_show_detailed_playlist_success(self):
        """Test detailed playlist display."""
        playlist = TakeoutPlaylist(
            name="Test Playlist",
            file_path=Path("/test/playlist.csv"),
            videos=[
                TakeoutPlaylistItem(
                    video_id="video1",
                    creation_timestamp=datetime(
                        2023, 1, 15, 14, 30, 0, tzinfo=timezone.utc
                    ),
                ),
                TakeoutPlaylistItem(
                    video_id="video2",
                    creation_timestamp=datetime(
                        2023, 1, 16, 15, 45, 0, tzinfo=timezone.utc
                    ),
                ),
            ],
        )

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _show_detailed_playlist(playlist, limit=10)

        mock_console.print.assert_called()

    async def test_show_detailed_playlist_with_video_titles(self, mock_takeout_service):
        """Test detailed playlist display with video title lookup."""
        playlist = TakeoutPlaylist(
            name="Test Playlist",
            file_path=Path("/test/playlist.csv"),
            videos=[
                TakeoutPlaylistItem(video_id="video1"),
                TakeoutPlaylistItem(video_id="video2"),
            ],
        )

        # Mock video title lookup
        mock_takeout_service.parse_watch_history.return_value = [
            TakeoutWatchEntry(
                video_id="video1",
                title="Video Title 1",
                title_url="https://www.youtube.com/watch?v=video1",
            ),
            TakeoutWatchEntry(
                video_id="video2",
                title="Video Title 2",
                title_url="https://www.youtube.com/watch?v=video2",
            ),
        ]

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _show_detailed_playlist(
                playlist, limit=10, takeout_service=mock_takeout_service
            )

        mock_console.print.assert_called()

    async def test_show_detailed_playlist_empty(self):
        """Test detailed playlist display with empty playlist."""
        playlist = TakeoutPlaylist(
            name="Empty Playlist", file_path=Path("/test/empty.csv"), videos=[]
        )

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _show_detailed_playlist(playlist, limit=10)

        mock_console.print.assert_called()


class TestDisplayAnalysisSummary:
    """Tests for _display_analysis_summary function."""

    def test_display_analysis_summary_complete(self):
        """Test analysis summary display with complete data."""
        # Mock analysis object with required attributes
        analysis = MagicMock()
        analysis.total_videos_watched = 100
        analysis.unique_channels = 25
        analysis.playlist_count = 5
        analysis.subscription_count = 30
        analysis.content_diversity_score = 0.7
        analysis.data_completeness = 0.85
        analysis.high_priority_videos = ["video1", "video2"]

        # Mock top channels
        channel_mock = MagicMock()
        channel_mock.channel_name = "Top Channel"
        channel_mock.videos_watched = 15
        channel_mock.is_subscribed = True
        channel_mock.engagement_score = 0.8
        analysis.top_channels = [channel_mock]

        # Mock viewing patterns
        patterns_mock = MagicMock()
        patterns_mock.peak_viewing_hours = [14, 20, 21]
        patterns_mock.peak_viewing_days = ["Saturday", "Sunday"]
        patterns_mock.viewing_frequency = 2.5
        patterns_mock.channel_diversity = 0.7
        patterns_mock.playlist_usage = 0.6
        analysis.viewing_patterns = patterns_mock

        # Mock playlist analysis
        playlist_analysis_mock = MagicMock()
        playlist_analysis_mock.orphaned_videos = ["video1", "video2"]
        playlist_analysis_mock.over_categorized_videos = ["video3"]
        analysis.playlist_analysis = playlist_analysis_mock

        # Mock content gaps
        analysis.content_gaps = []

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            _display_analysis_summary(analysis)

        mock_console.print.assert_called()

    def test_display_analysis_summary_minimal(self):
        """Test analysis summary display with minimal data."""
        # Mock minimal analysis object
        analysis = MagicMock()
        analysis.total_videos_watched = 0
        analysis.unique_channels = 0
        analysis.playlist_count = 0
        analysis.subscription_count = 0
        analysis.content_diversity_score = 0.0
        analysis.data_completeness = 0.0
        analysis.high_priority_videos = []
        analysis.top_channels = []

        # Mock minimal viewing patterns
        patterns_mock = MagicMock()
        patterns_mock.peak_viewing_hours = []
        patterns_mock.peak_viewing_days = []
        patterns_mock.viewing_frequency = 0.0
        patterns_mock.channel_diversity = 0.0
        patterns_mock.playlist_usage = 0.0
        analysis.viewing_patterns = patterns_mock

        # Mock minimal playlist analysis
        playlist_analysis_mock = MagicMock()
        playlist_analysis_mock.orphaned_videos = []
        playlist_analysis_mock.over_categorized_videos = []
        analysis.playlist_analysis = playlist_analysis_mock

        # Mock content gaps
        analysis.content_gaps = []

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            _display_analysis_summary(analysis)

        mock_console.print.assert_called()


class TestAnalysisHelperFunctions:
    """Tests for analysis helper functions."""

    async def test_analyze_playlist_overlap(self, mock_takeout_service, mock_progress):
        """Test playlist overlap analysis."""
        mock_takeout_service.analyze_playlist_overlap = AsyncMock(
            return_value={
                "Playlist1": {"Playlist2": 5, "Playlist3": 2},
                "Playlist2": {"Playlist1": 5, "Playlist3": 1},
                "Playlist3": {"Playlist1": 2, "Playlist2": 1},
            }
        )

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _analyze_playlist_overlap(
                mock_takeout_service, mock_progress, "test_task"
            )

        mock_takeout_service.analyze_playlist_overlap.assert_called_once()
        mock_console.print.assert_called()

    async def test_analyze_channel_clusters(self, mock_takeout_service, mock_progress):
        """Test channel cluster analysis."""
        mock_takeout_service.analyze_channel_clusters = AsyncMock(
            return_value={
                "high_engagement": {
                    "Channel1": {
                        "videos_watched": 25,
                        "avg_frequency": 2.5,
                        "is_subscribed": True,
                    }
                },
                "medium_engagement": {
                    "Channel2": {
                        "videos_watched": 10,
                        "avg_frequency": 1.0,
                        "is_subscribed": True,
                    }
                },
                "low_engagement": {
                    "Channel3": {
                        "videos_watched": 3,
                        "avg_frequency": 0.3,
                        "is_subscribed": False,
                    }
                },
                "unsubscribed_frequent": {
                    "Channel4": {
                        "videos_watched": 15,
                        "avg_frequency": 1.5,
                        "is_subscribed": False,
                    }
                },
                "subscribed_inactive": {
                    "Channel5": {
                        "videos_watched": 0,
                        "avg_frequency": 0.0,
                        "is_subscribed": True,
                    }
                },
            }
        )

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _analyze_channel_clusters(
                mock_takeout_service, mock_progress, "test_task"
            )

        mock_takeout_service.analyze_channel_clusters.assert_called_once()
        mock_console.print.assert_called()

    async def test_analyze_temporal_patterns(self, mock_takeout_service, mock_progress):
        """Test temporal pattern analysis."""
        mock_takeout_service.analyze_temporal_patterns = AsyncMock(
            return_value={
                "hourly_distribution": {14: 25, 20: 30, 21: 35},
                "daily_distribution": {"Monday": 10, "Saturday": 25, "Sunday": 30},
                "monthly_distribution": {"2023-01": 45, "2023-02": 50},
                "peak_viewing_hour": 21,
                "peak_viewing_day": "Sunday",
                "peak_viewing_month": "2023-02",
                "max_consecutive_days": 7,
                "total_active_days": 120,
                "date_range": {
                    "start": "2023-01-01T00:00:00+00:00",
                    "end": "2023-12-31T23:59:59+00:00",
                    "duration_days": 365,
                },
                "channel_time_preferences": {
                    "Channel1": {14: 5, 20: 10},
                    "Channel2": {21: 8},
                },
            }
        )

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _analyze_temporal_patterns(
                mock_takeout_service, mock_progress, "test_task"
            )

        mock_takeout_service.analyze_temporal_patterns.assert_called_once()
        mock_console.print.assert_called()


class TestFileInspectionFunctions:
    """Tests for file inspection functions."""

    def test_detect_csv_type_playlist(self):
        """Test CSV type detection for playlist files."""
        headers = ["Video ID", "Playlist Video Creation Timestamp"]
        file_path = Path("/test/Music-videos.csv")

        result = _detect_csv_type(file_path, headers)

        assert result == "playlist"

    def test_detect_csv_type_subscriptions(self):
        """Test CSV type detection for subscriptions file."""
        headers = ["Channel Id", "Channel Title", "Channel Url"]
        file_path = Path("/test/subscriptions.csv")

        result = _detect_csv_type(file_path, headers)

        assert result == "subscriptions"

    def test_detect_csv_type_generic(self):
        """Test CSV type detection for unknown files."""
        headers = ["Unknown", "Headers"]
        file_path = Path("/test/unknown.csv")

        result = _detect_csv_type(file_path, headers)

        assert result == "generic"

    async def test_inspect_csv_file_success(self, temp_takeout_dir, mock_progress):
        """Test CSV file inspection."""
        # Create a test CSV file
        csv_file = temp_takeout_dir / "test.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(
                [["Column1", "Column2"], ["Value1", "Value2"], ["Value3", "Value4"]]
            )

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _inspect_csv_file(
                csv_file, limit=10, progress=mock_progress, task_id="test_task"
            )

        mock_console.print.assert_called()

    async def test_inspect_json_file_success(self, temp_takeout_dir, mock_progress):
        """Test JSON file inspection."""
        # Create a test JSON file
        json_file = temp_takeout_dir / "test.json"
        test_data = [
            {
                "header": "YouTube",
                "title": "Test Video",
                "time": "2023-01-15T14:30:00Z",
            },
            {
                "header": "YouTube",
                "title": "Another Video",
                "time": "2023-01-16T15:45:00Z",
            },
        ]
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _inspect_json_file(
                json_file, limit=10, progress=mock_progress, task_id="test_task"
            )

        mock_console.print.assert_called()

    async def test_inspect_csv_file_invalid(self, temp_takeout_dir, mock_progress):
        """Test CSV file inspection with invalid file."""
        # Create an invalid CSV file
        csv_file = temp_takeout_dir / "invalid.csv"
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write('invalid csv content\nwith unclosed quote"')

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _inspect_csv_file(
                csv_file, limit=10, progress=mock_progress, task_id="test_task"
            )

        mock_console.print.assert_called()

    async def test_inspect_json_file_invalid(self, temp_takeout_dir, mock_progress):
        """Test JSON file inspection with invalid file."""
        # Create an invalid JSON file
        json_file = temp_takeout_dir / "invalid.json"
        with open(json_file, "w", encoding="utf-8") as f:
            f.write("invalid json content")

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _inspect_json_file(
                json_file, limit=10, progress=mock_progress, task_id="test_task"
            )

        mock_console.print.assert_called()


class TestDisplayFunctions:
    """Tests for display functions."""

    async def test_display_playlist_csv(self):
        """Test playlist CSV display."""
        headers = ["Video ID", "Playlist Video Creation Timestamp"]
        rows = [
            {
                "Video ID": "video1",
                "Playlist Video Creation Timestamp": "2023-01-15T14:30:00+00:00",
            },
            {
                "Video ID": "video2",
                "Playlist Video Creation Timestamp": "2023-01-16T15:45:00+00:00",
            },
        ]
        file_path = Path("/test/playlist.csv")

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _display_playlist_csv(file_path, headers, rows, limit=10)

        mock_console.print.assert_called()

    async def test_display_subscriptions_csv(self):
        """Test subscriptions CSV display."""
        headers = ["Channel Id", "Channel Title", "Channel Url"]
        rows = [
            {
                "Channel Id": "UC123",
                "Channel Title": "Channel 1",
                "Channel Url": "https://www.youtube.com/channel/UC123",
            },
            {
                "Channel Id": "UC456",
                "Channel Title": "Channel 2",
                "Channel Url": "https://www.youtube.com/channel/UC456",
            },
        ]

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _display_subscriptions_csv(headers, rows, limit=10)

        mock_console.print.assert_called()

    async def test_display_generic_csv(self):
        """Test generic CSV display."""
        headers = ["Column1", "Column2"]
        rows = [
            {"Column1": "Value1", "Column2": "Value2"},
            {"Column1": "Value3", "Column2": "Value4"},
        ]

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _display_generic_csv(headers, rows, limit=10)

        mock_console.print.assert_called()

    async def test_display_watch_history_json(self):
        """Test watch history JSON display."""
        data = [
            {
                "header": "YouTube",
                "title": "Watched Video 1",
                "titleUrl": "https://www.youtube.com/watch?v=video1",
                "time": "2023-01-15T14:30:00Z",
            },
            {
                "header": "YouTube",
                "title": "Watched Video 2",
                "titleUrl": "https://www.youtube.com/watch?v=video2",
                "time": "2023-01-16T15:45:00Z",
            },
        ]

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _display_watch_history_json(data, limit=10)

        mock_console.print.assert_called()

    async def test_display_generic_json(self):
        """Test generic JSON display."""
        data = {"key1": "value1", "key2": {"nested": "value2"}}

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _display_generic_json(data, limit=10)

        mock_console.print.assert_called()


class TestPeekCommentsAndChats:
    """Tests for comments and live chats peeking functions."""

    async def test_peek_comments_success(self, temp_takeout_dir, mock_progress):
        """Test successful comments peeking."""
        # Create mock takeout service
        takeout_service = MagicMock(spec=TakeoutService)
        takeout_service.youtube_path = temp_takeout_dir / "YouTube and YouTube Music"

        # Create mock comments directory and files
        comments_dir = takeout_service.youtube_path / "comments"
        comments_dir.mkdir(parents=True, exist_ok=True)

        comment_file = comments_dir / "test_video.csv"
        with open(comment_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(
                [
                    ["Comment ID", "Time", "Text"],
                    ["comment1", "2023-01-15T14:30:00Z", "Great video!"],
                    ["comment2", "2023-01-16T15:45:00Z", "Thanks for sharing"],
                ]
            )

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_comments(
                takeout_service,
                limit=10,
                sort_order="default",
                progress=mock_progress,
                task_id="test_task",
            )

        mock_console.print.assert_called()

    async def test_peek_live_chats_success(self, temp_takeout_dir, mock_progress):
        """Test successful live chats peeking."""
        # Create mock takeout service
        takeout_service = MagicMock(spec=TakeoutService)
        takeout_service.youtube_path = temp_takeout_dir / "YouTube and YouTube Music"

        # Create mock live chat directory and files
        chat_dir = takeout_service.youtube_path / "live_chat"
        chat_dir.mkdir(parents=True, exist_ok=True)

        chat_file = chat_dir / "test_stream.csv"
        with open(chat_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(
                [
                    ["Message ID", "Time", "Author", "Message"],
                    ["msg1", "2023-01-15T14:30:00Z", "User1", "Hello everyone!"],
                    ["msg2", "2023-01-16T15:45:00Z", "User2", "Great stream!"],
                ]
            )

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_live_chats(
                takeout_service,
                limit=10,
                sort_order="default",
                progress=mock_progress,
                task_id="test_task",
            )

        mock_console.print.assert_called()

    async def test_peek_comments_empty_directory(self, temp_takeout_dir, mock_progress):
        """Test comments peeking with empty directory."""
        takeout_service = MagicMock(spec=TakeoutService)
        takeout_service.youtube_path = temp_takeout_dir / "YouTube and YouTube Music"

        # Create empty comments directory
        comments_dir = takeout_service.youtube_path / "comments"
        comments_dir.mkdir(parents=True, exist_ok=True)

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_comments(
                takeout_service,
                limit=10,
                sort_order="default",
                progress=mock_progress,
                task_id="test_task",
            )

        mock_console.print.assert_called()

    async def test_peek_live_chats_empty_directory(
        self, temp_takeout_dir, mock_progress
    ):
        """Test live chats peeking with empty directory."""
        takeout_service = MagicMock(spec=TakeoutService)
        takeout_service.youtube_path = temp_takeout_dir / "YouTube and YouTube Music"

        # Create empty live chat directory
        chat_dir = takeout_service.youtube_path / "live_chat"
        chat_dir.mkdir(parents=True, exist_ok=True)

        with patch("chronovista.cli.commands.takeout.console") as mock_console:
            await _peek_live_chats(
                takeout_service,
                limit=10,
                sort_order="default",
                progress=mock_progress,
                task_id="test_task",
            )

        mock_console.print.assert_called()
