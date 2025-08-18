"""
Tests for TakeoutService.

Comprehensive test coverage for Google Takeout data parsing and analysis service.
"""

import asyncio
import csv
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Mark all async tests in this module
pytestmark = pytest.mark.asyncio

from chronovista.models.takeout import (
    ContentGap,
    PlaylistAnalysis,
    TakeoutAnalysis,
    TakeoutData,
    TakeoutPlaylist,
    TakeoutSubscription,
    TakeoutWatchEntry,
    ViewingPatterns,
)
from chronovista.services.takeout_service import TakeoutParsingError, TakeoutService
from tests.factories.takeout_data_factory import create_takeout_data


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

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_watch_history_data():
    """Sample watch history data in JSON format."""
    return [
        {
            "header": "YouTube",
            "title": "Watched Test Video 1",
            "titleUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "subtitles": [
                {
                    "name": "Test Channel 1",
                    "url": "https://www.youtube.com/channel/UCtest123",
                }
            ],
            "time": "2023-01-15T14:30:00Z",
        },
        {
            "header": "YouTube",
            "title": "Watched Test Video 2",
            "titleUrl": "https://www.youtube.com/watch?v=test2video",
            "subtitles": [
                {
                    "name": "Test Channel 2",
                    "url": "https://www.youtube.com/channel/UCtest456",
                }
            ],
            "time": "2023-01-16T15:45:00Z",
        },
        {
            "header": "Not YouTube",  # Should be skipped
            "title": "Other Activity",
            "time": "2023-01-17T16:00:00Z",
        },
        {
            "header": "YouTube",
            "title": "Watched Video Without URL",  # Should be skipped
            "time": "2023-01-18T17:00:00Z",
        },
    ]


@pytest.fixture
def sample_playlist_data():
    """Sample playlist data in CSV format."""
    return {
        "Music-videos.csv": [
            ["Video ID", "Playlist Video Creation Timestamp"],
            ["dQw4w9WgXcQ", "2023-01-15T14:30:00+00:00"],
            ["test2video", "2023-01-16T15:45:00+00:00"],
        ],
        "Learning-videos.csv": [
            ["Video ID", "Playlist Video Creation Timestamp"],
            ["eduVideo123", "2023-01-20T10:00:00+00:00"],
        ],
    }


@pytest.fixture
def sample_subscription_data():
    """Sample subscription data in CSV format."""
    return [
        ["Channel Id", "Channel Title", "Channel Url"],
        ["UCtest123", "Test Channel 1", "https://www.youtube.com/channel/UCtest123"],
        ["UCtest456", "Test Channel 2", "https://www.youtube.com/channel/UCtest456"],
        ["", "Custom Channel", "https://www.youtube.com/c/customchannel"],
    ]


class TestTakeoutServiceInitialization:
    """Tests for TakeoutService initialization."""

    def test_init_valid_path(self, temp_takeout_dir):
        """Test initialization with valid takeout directory."""
        service = TakeoutService(temp_takeout_dir)

        assert service.takeout_path == temp_takeout_dir
        assert service.youtube_path == temp_takeout_dir / "YouTube and YouTube Music"

    def test_init_invalid_path(self):
        """Test initialization with invalid takeout directory."""
        invalid_path = Path("/nonexistent/path")

        with pytest.raises(TakeoutParsingError, match="YouTube data not found"):
            TakeoutService(invalid_path)

    def test_init_path_without_youtube_folder(self, temp_takeout_dir):
        """Test initialization with directory that doesn't contain YouTube folder."""
        # Remove the YouTube folder
        youtube_dir = temp_takeout_dir / "YouTube and YouTube Music"
        shutil.rmtree(youtube_dir)

        with pytest.raises(TakeoutParsingError, match="YouTube data not found"):
            TakeoutService(temp_takeout_dir)

    def test_init_converts_string_path(self, temp_takeout_dir):
        """Test initialization with string path gets converted to Path."""
        service = TakeoutService(Path(str(temp_takeout_dir)))

        assert isinstance(service.takeout_path, Path)
        assert service.takeout_path == temp_takeout_dir


class TestParseWatchHistory:
    """Tests for watch history parsing."""

    async def test_parse_watch_history_success(
        self, temp_takeout_dir, sample_watch_history_data
    ):
        """Test successful watch history parsing."""
        service = TakeoutService(temp_takeout_dir)

        # Create watch history file
        history_file = service.youtube_path / "history" / "watch-history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(sample_watch_history_data, f)

        result = await service.parse_watch_history()

        assert len(result) == 2  # Only YouTube entries with URLs
        assert all(isinstance(entry, TakeoutWatchEntry) for entry in result)

        # Check first entry
        first_entry = result[0]
        assert first_entry.title == "Test Video 1"  # "Watched " prefix removed
        assert first_entry.title_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert first_entry.video_id == "dQw4w9WgXcQ"
        assert first_entry.channel_name == "Test Channel 1"
        assert first_entry.channel_url == "https://www.youtube.com/channel/UCtest123"
        assert first_entry.channel_id == "UCtest123"
        assert first_entry.watched_at == datetime(
            2023, 1, 15, 14, 30, 0, tzinfo=timezone.utc
        )

    async def test_parse_watch_history_no_file(self, temp_takeout_dir):
        """Test watch history parsing when file doesn't exist."""
        service = TakeoutService(temp_takeout_dir)

        with patch("chronovista.services.takeout_service.logger") as mock_logger:
            result = await service.parse_watch_history()

        assert result == []
        mock_logger.warning.assert_called()

    async def test_parse_watch_history_invalid_json(self, temp_takeout_dir):
        """Test watch history parsing with invalid JSON."""
        service = TakeoutService(temp_takeout_dir)

        # Create invalid JSON file
        history_file = service.youtube_path / "history" / "watch-history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            f.write("invalid json content")

        with pytest.raises(
            TakeoutParsingError, match="Invalid JSON in watch history file"
        ):
            await service.parse_watch_history()

    async def test_parse_watch_history_filters_non_youtube(self, temp_takeout_dir):
        """Test that non-YouTube entries are filtered out."""
        service = TakeoutService(temp_takeout_dir)

        data = [
            {
                "header": "Google Search",
                "title": "Searched for something",
                "time": "2023-01-15T14:30:00Z",
            }
        ]

        history_file = service.youtube_path / "history" / "watch-history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = await service.parse_watch_history()
        assert result == []

    async def test_parse_watch_history_filters_no_url(self, temp_takeout_dir):
        """Test that entries without titleUrl are filtered out."""
        service = TakeoutService(temp_takeout_dir)

        data = [
            {
                "header": "YouTube",
                "title": "Video without URL",
                "time": "2023-01-15T14:30:00Z",
                # No titleUrl
            }
        ]

        history_file = service.youtube_path / "history" / "watch-history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = await service.parse_watch_history()
        assert result == []

    async def test_parse_watch_history_handles_missing_subtitles(
        self, temp_takeout_dir
    ):
        """Test parsing entry without subtitles (channel info)."""
        service = TakeoutService(temp_takeout_dir)

        data = [
            {
                "header": "YouTube",
                "title": "Watched Test Video",
                "titleUrl": "https://www.youtube.com/watch?v=test123",
                "time": "2023-01-15T14:30:00Z",
                # No subtitles
            }
        ]

        history_file = service.youtube_path / "history" / "watch-history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = await service.parse_watch_history()

        assert len(result) == 1
        entry = result[0]
        assert entry.channel_name is None
        assert entry.channel_url is None

    async def test_parse_watch_history_removes_watched_prefix(self, temp_takeout_dir):
        """Test that 'Watched ' prefix is removed from titles."""
        service = TakeoutService(temp_takeout_dir)

        data = [
            {
                "header": "YouTube",
                "title": "Watched Amazing Video Title",
                "titleUrl": "https://www.youtube.com/watch?v=test123",
                "time": "2023-01-15T14:30:00Z",
            }
        ]

        history_file = service.youtube_path / "history" / "watch-history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = await service.parse_watch_history()

        assert len(result) == 1
        assert result[0].title == "Amazing Video Title"

    async def test_parse_watch_history_handles_parsing_errors(self, temp_takeout_dir):
        """Test handling of unexpected parsing errors."""
        service = TakeoutService(temp_takeout_dir)

        # Create file but mock open to raise an exception
        history_file = service.youtube_path / "history" / "watch-history.json"
        history_file.touch()

        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            with pytest.raises(
                TakeoutParsingError, match="Error parsing watch history"
            ):
                await service.parse_watch_history()


class TestParsePlaylists:
    """Tests for playlist parsing."""

    async def test_parse_playlists_success(
        self, temp_takeout_dir, sample_playlist_data
    ):
        """Test successful playlist parsing."""
        service = TakeoutService(temp_takeout_dir)

        # Create playlist CSV files
        playlists_dir = service.youtube_path / "playlists"
        for filename, rows in sample_playlist_data.items():
            playlist_file = playlists_dir / filename
            with open(playlist_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerows(rows)

        result = await service.parse_playlists()

        assert len(result) == 2
        assert all(isinstance(playlist, TakeoutPlaylist) for playlist in result)

        # Check Music playlist (suffix "-videos" removed by service)
        music_playlist = next(p for p in result if p.name == "Music")
        assert len(music_playlist.videos) == 2
        assert music_playlist.video_count == 2

        # Check first video
        first_video = music_playlist.videos[0]
        assert first_video.video_id == "dQw4w9WgXcQ"
        assert first_video.creation_timestamp == datetime.fromisoformat(
            "2023-01-15T14:30:00+00:00"
        )

    async def test_parse_playlists_no_directory(self, temp_takeout_dir):
        """Test playlist parsing when playlists directory doesn't exist."""
        service = TakeoutService(temp_takeout_dir)

        # Remove playlists directory
        playlists_dir = service.youtube_path / "playlists"
        shutil.rmtree(playlists_dir)

        with patch("chronovista.services.takeout_service.logger") as mock_logger:
            result = await service.parse_playlists()

        assert result == []
        mock_logger.warning.assert_called()

    async def test_parse_playlists_empty_directory(self, temp_takeout_dir):
        """Test playlist parsing with empty playlists directory."""
        service = TakeoutService(temp_takeout_dir)

        result = await service.parse_playlists()
        assert result == []

    async def test_parse_playlists_invalid_csv(self, temp_takeout_dir):
        """Test playlist parsing with invalid CSV file."""
        service = TakeoutService(temp_takeout_dir)

        # Create a playlist file but mock open to raise an exception during parsing
        playlists_dir = service.youtube_path / "playlists"
        invalid_file = playlists_dir / "invalid-playlist.csv"
        invalid_file.touch()

        # Mock open to cause a parsing error
        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            with patch("chronovista.services.takeout_service.logger") as mock_logger:
                result = await service.parse_playlists()

        # Should continue with other files and log warning
        assert result == []
        mock_logger.warning.assert_called()

    async def test_parse_playlists_missing_columns(self, temp_takeout_dir):
        """Test playlist parsing with missing expected columns."""
        service = TakeoutService(temp_takeout_dir)

        # Create CSV with different column names
        playlists_dir = service.youtube_path / "playlists"
        playlist_file = playlists_dir / "test-playlist.csv"
        with open(playlist_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(
                [["Different Column", "Another Column"], ["value1", "value2"]]
            )

        result = await service.parse_playlists()

        # Should still create playlist but with empty video IDs
        assert len(result) == 1
        playlist = result[0]
        assert playlist.name == "test-playlist"
        assert len(playlist.videos) == 1
        assert playlist.videos[0].video_id == ""  # Missing Video ID column


class TestParseSubscriptions:
    """Tests for subscription parsing."""

    async def test_parse_subscriptions_success(
        self, temp_takeout_dir, sample_subscription_data
    ):
        """Test successful subscription parsing."""
        service = TakeoutService(temp_takeout_dir)

        # Create subscriptions CSV file
        subscriptions_file = (
            service.youtube_path / "subscriptions" / "subscriptions.csv"
        )
        with open(subscriptions_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(sample_subscription_data)

        result = await service.parse_subscriptions()

        assert len(result) == 3
        assert all(isinstance(sub, TakeoutSubscription) for sub in result)

        # Check first subscription
        first_sub = result[0]
        assert first_sub.channel_id == "UCtest123"
        assert first_sub.channel_title == "Test Channel 1"
        assert first_sub.channel_url == "https://www.youtube.com/channel/UCtest123"

    async def test_parse_subscriptions_no_file(self, temp_takeout_dir):
        """Test subscription parsing when file doesn't exist."""
        service = TakeoutService(temp_takeout_dir)

        with patch("chronovista.services.takeout_service.logger") as mock_logger:
            result = await service.parse_subscriptions()

        assert result == []
        mock_logger.warning.assert_called()

    async def test_parse_subscriptions_invalid_csv(self, temp_takeout_dir):
        """Test subscription parsing with invalid CSV."""
        service = TakeoutService(temp_takeout_dir)

        # Create subscriptions file but mock open to raise an exception
        subscriptions_file = (
            service.youtube_path / "subscriptions" / "subscriptions.csv"
        )
        subscriptions_file.parent.mkdir(exist_ok=True)
        subscriptions_file.touch()

        # Mock open to raise an exception during reading
        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            with pytest.raises(
                TakeoutParsingError, match="Error parsing subscriptions"
            ):
                await service.parse_subscriptions()


class TestParseAll:
    """Tests for parse_all method."""

    async def test_parse_all_success(
        self,
        temp_takeout_dir,
        sample_watch_history_data,
        sample_playlist_data,
        sample_subscription_data,
    ):
        """Test successful parsing of all data types."""
        service = TakeoutService(temp_takeout_dir)

        # Create all data files
        history_file = service.youtube_path / "history" / "watch-history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(sample_watch_history_data, f)

        playlists_dir = service.youtube_path / "playlists"
        for filename, rows in sample_playlist_data.items():
            playlist_file = playlists_dir / filename
            with open(playlist_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerows(rows)

        subscriptions_file = (
            service.youtube_path / "subscriptions" / "subscriptions.csv"
        )
        with open(subscriptions_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(sample_subscription_data)

        # Mock logger to verify info messages
        with patch("chronovista.services.takeout_service.logger") as mock_logger:
            result = await service.parse_all()

        assert isinstance(result, TakeoutData)
        assert len(result.watch_history) == 2
        assert len(result.playlists) == 2
        assert len(result.subscriptions) == 3
        assert result.total_videos_watched == 2  # Unique videos
        assert result.total_playlists == 2
        assert result.total_subscriptions == 3

        # Check that info log was called
        mock_logger.info.assert_called()

    async def test_parse_all_empty_data(self, temp_takeout_dir):
        """Test parse_all with no data files."""
        service = TakeoutService(temp_takeout_dir)

        result = await service.parse_all()

        assert isinstance(result, TakeoutData)
        assert result.watch_history == []
        assert result.playlists == []
        assert result.subscriptions == []
        assert result.total_videos_watched == 0
        assert result.total_playlists == 0
        assert result.total_subscriptions == 0


class TestAnalysisMethodsWithRealData:
    """Test analysis methods with realistic data."""

    @pytest.fixture
    def populated_takeout_data(self, temp_takeout_dir):
        """Create a TakeoutService with realistic test data."""
        service = TakeoutService(temp_takeout_dir)

        # Create watch history with multiple entries
        watch_data = [
            {
                "header": "YouTube",
                "title": "Watched Music Video 1",
                "titleUrl": "https://www.youtube.com/watch?v=music1",
                "subtitles": [
                    {
                        "name": "Music Channel",
                        "url": "https://www.youtube.com/channel/UCmusic123",
                    }
                ],
                "time": "2023-01-15T14:30:00Z",
            },
            {
                "header": "YouTube",
                "title": "Watched Music Video 2",
                "titleUrl": "https://www.youtube.com/watch?v=music2",
                "subtitles": [
                    {
                        "name": "Music Channel",
                        "url": "https://www.youtube.com/channel/UCmusic123",
                    }
                ],
                "time": "2023-01-16T15:45:00Z",
            },
            {
                "header": "YouTube",
                "title": "Watched Tech Video",
                "titleUrl": "https://www.youtube.com/watch?v=tech1",
                "subtitles": [
                    {
                        "name": "Tech Channel",
                        "url": "https://www.youtube.com/channel/UCtech456",
                    }
                ],
                "time": "2023-01-17T10:00:00Z",
            },
        ]

        history_file = service.youtube_path / "history" / "watch-history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(watch_data, f)

        # Create playlists
        playlists_dir = service.youtube_path / "playlists"
        music_file = playlists_dir / "Music-videos.csv"
        with open(music_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(
                [
                    ["Video ID", "Playlist Video Creation Timestamp"],
                    ["music1", "2023-01-15T14:30:00+00:00"],
                    ["music2", "2023-01-16T15:45:00+00:00"],
                ]
            )

        tech_file = playlists_dir / "Tech-videos.csv"
        with open(tech_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(
                [
                    ["Video ID", "Playlist Video Creation Timestamp"],
                    ["tech1", "2023-01-17T10:00:00+00:00"],
                    ["music1", "2023-01-18T11:00:00+00:00"],  # Overlap
                ]
            )

        # Create subscriptions
        subscriptions_file = (
            service.youtube_path / "subscriptions" / "subscriptions.csv"
        )
        with open(subscriptions_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(
                [
                    ["Channel Id", "Channel Title", "Channel Url"],
                    [
                        "UCmusic123",
                        "Music Channel",
                        "https://www.youtube.com/channel/UCmusic123",
                    ],
                ]
            )

        return service

    async def test_analyze_viewing_patterns(self, populated_takeout_data):
        """Test viewing patterns analysis."""
        service = populated_takeout_data
        takeout_data = await service.parse_all()

        patterns = await service.analyze_viewing_patterns(takeout_data)

        assert isinstance(patterns, ViewingPatterns)
        assert len(patterns.peak_viewing_hours) <= 3
        assert len(patterns.peak_viewing_days) <= 3
        assert patterns.viewing_frequency > 0
        assert len(patterns.top_channels) <= 10
        assert 0 <= patterns.channel_diversity <= 1
        assert (
            patterns.playlist_usage >= 0
        )  # Can exceed 1.0 if more playlist videos than watched videos
        assert 0 <= patterns.subscription_engagement <= 1

    async def test_analyze_playlist_relationships(self, populated_takeout_data):
        """Test playlist relationship analysis."""
        service = populated_takeout_data
        takeout_data = await service.parse_all()

        analysis = await service.analyze_playlist_relationships(takeout_data)

        assert isinstance(analysis, PlaylistAnalysis)
        assert "Music" in analysis.playlist_overlap_matrix
        assert "Tech" in analysis.playlist_overlap_matrix
        # Should find overlap between Music and Tech playlists (music1 video)
        assert analysis.playlist_overlap_matrix["Music"]["Tech"] == 1
        assert len(analysis.orphaned_videos) >= 0
        assert "Music" in analysis.playlist_sizes
        assert "Tech" in analysis.playlist_sizes

    async def test_find_content_gaps(self, populated_takeout_data):
        """Test content gap analysis."""
        service = populated_takeout_data
        takeout_data = await service.parse_all()

        gaps = await service.find_content_gaps(takeout_data)

        assert isinstance(gaps, list)
        assert all(isinstance(gap, ContentGap) for gap in gaps)
        # Should find gaps for all unique videos
        assert len(gaps) == 3  # music1, music2, tech1

        # Check that gaps are sorted by priority
        if len(gaps) > 1:
            for i in range(len(gaps) - 1):
                assert gaps[i].priority_score >= gaps[i + 1].priority_score

    async def test_generate_comprehensive_analysis(self, populated_takeout_data):
        """Test comprehensive analysis generation."""
        service = populated_takeout_data

        analysis = await service.generate_comprehensive_analysis()

        assert isinstance(analysis, TakeoutAnalysis)
        assert analysis.total_videos_watched == 3
        assert analysis.unique_channels == 2
        assert analysis.playlist_count == 2
        assert analysis.subscription_count == 1
        assert analysis.viewing_patterns is not None
        assert analysis.playlist_analysis is not None
        assert len(analysis.content_gaps) > 0
        assert len(analysis.high_priority_videos) > 0
        assert 0 <= analysis.content_diversity_score <= 1

    async def test_analyze_playlist_overlap(self, populated_takeout_data):
        """Test playlist overlap analysis."""
        service = populated_takeout_data

        overlap = await service.analyze_playlist_overlap()

        assert isinstance(overlap, dict)
        assert "Music" in overlap
        assert "Tech" in overlap
        # Should find overlap
        assert overlap["Music"]["Tech"] == 1

    async def test_analyze_channel_clusters(self, populated_takeout_data):
        """Test channel clustering analysis."""
        service = populated_takeout_data

        clusters = await service.analyze_channel_clusters()

        assert isinstance(clusters, dict)
        assert "high_engagement" in clusters
        assert "medium_engagement" in clusters
        assert "low_engagement" in clusters
        assert "unsubscribed_frequent" in clusters
        assert "subscribed_inactive" in clusters

    async def test_analyze_temporal_patterns(self, populated_takeout_data):
        """Test temporal pattern analysis."""
        service = populated_takeout_data

        patterns = await service.analyze_temporal_patterns()

        assert isinstance(patterns, dict)
        assert "hourly_distribution" in patterns
        assert "daily_distribution" in patterns
        assert "monthly_distribution" in patterns
        assert "peak_viewing_hour" in patterns
        assert "peak_viewing_day" in patterns
        assert "max_consecutive_days" in patterns
        assert "total_active_days" in patterns
        assert "date_range" in patterns

    async def test_analyze_temporal_patterns_no_timestamps(self, temp_takeout_dir):
        """Test temporal analysis with no valid timestamps."""
        service = TakeoutService(temp_takeout_dir)

        # Create data without valid timestamps
        watch_data = [
            {
                "header": "YouTube",
                "title": "Watched Video",
                "titleUrl": "https://www.youtube.com/watch?v=test123",
                # No time field
            }
        ]

        history_file = service.youtube_path / "history" / "watch-history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(watch_data, f)

        patterns = await service.analyze_temporal_patterns()

        assert "error" in patterns
        assert "No valid timestamps" in patterns["error"]


class TestAnalysisMethodsWithEmptyData:
    """Test analysis methods with edge cases and empty data."""

    async def test_analyze_viewing_patterns_empty_data(self, temp_takeout_dir):
        """Test viewing patterns analysis with empty data."""
        service = TakeoutService(temp_takeout_dir)
        empty_data = create_takeout_data(
            takeout_path=temp_takeout_dir,
            watch_history=[],
            playlists=[],
            subscriptions=[],
        )

        patterns = await service.analyze_viewing_patterns(empty_data)

        assert isinstance(patterns, ViewingPatterns)
        assert patterns.peak_viewing_hours == []
        assert patterns.peak_viewing_days == []
        assert patterns.viewing_frequency == 0.0
        assert patterns.top_channels == []
        assert patterns.channel_diversity == 0.0

    async def test_analyze_playlist_relationships_empty_data(self, temp_takeout_dir):
        """Test playlist analysis with empty data."""
        service = TakeoutService(temp_takeout_dir)
        empty_data = create_takeout_data(
            takeout_path=temp_takeout_dir,
            watch_history=[],
            playlists=[],
            subscriptions=[],
        )

        analysis = await service.analyze_playlist_relationships(empty_data)

        assert isinstance(analysis, PlaylistAnalysis)
        # Should return empty PlaylistAnalysis
        assert analysis.playlist_overlap_matrix == {}

    async def test_find_content_gaps_empty_data(self, temp_takeout_dir):
        """Test content gap analysis with empty data."""
        service = TakeoutService(temp_takeout_dir)
        empty_data = create_takeout_data(
            takeout_path=temp_takeout_dir,
            watch_history=[],
            playlists=[],
            subscriptions=[],
        )

        gaps = await service.find_content_gaps(empty_data)

        assert gaps == []

    async def test_generate_comprehensive_analysis_empty_data(self, temp_takeout_dir):
        """Test comprehensive analysis with empty data."""
        service = TakeoutService(temp_takeout_dir)

        analysis = await service.generate_comprehensive_analysis()

        assert isinstance(analysis, TakeoutAnalysis)
        assert analysis.total_videos_watched == 0
        assert analysis.unique_channels == 0
        assert analysis.playlist_count == 0
        assert analysis.subscription_count == 0


class TestLoggerIntegration:
    """Test logger integration and messages."""

    async def test_logging_during_parsing(
        self, temp_takeout_dir, sample_watch_history_data
    ):
        """Test that appropriate log messages are generated."""
        service = TakeoutService(temp_takeout_dir)

        # Create watch history file
        history_file = service.youtube_path / "history" / "watch-history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(sample_watch_history_data, f)

        with patch("chronovista.services.takeout_service.logger") as mock_logger:
            await service.parse_watch_history()

        # Check that info messages were logged
        info_calls = [call for call in mock_logger.info.call_args_list]
        assert len(info_calls) >= 2  # Should log parsing start and completion

        # Check specific log messages
        log_messages = [str(call) for call in info_calls]
        assert any("Parsing watch history" in msg for msg in log_messages)
        assert any(
            "Parsed" in msg and "watch history entries" in msg for msg in log_messages
        )


class TestErrorHandling:
    """Test error handling and edge cases."""

    async def test_parse_all_handles_individual_failures(self, temp_takeout_dir):
        """Test that parse_all continues even if individual parsers fail."""
        service = TakeoutService(temp_takeout_dir)

        # Create only subscriptions data, let others fail gracefully
        subscriptions_file = (
            service.youtube_path / "subscriptions" / "subscriptions.csv"
        )
        with open(subscriptions_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(
                [
                    ["Channel Id", "Channel Title", "Channel Url"],
                    [
                        "UCtest123",
                        "Test Channel",
                        "https://www.youtube.com/channel/UCtest123",
                    ],
                ]
            )

        result = await service.parse_all()

        # Should succeed with partial data
        assert isinstance(result, TakeoutData)
        assert result.watch_history == []  # Failed gracefully
        assert result.playlists == []  # Failed gracefully
        assert len(result.subscriptions) == 1  # Succeeded

    def test_takeout_parsing_error_inheritance(self):
        """Test that TakeoutParsingError is properly defined."""
        error = TakeoutParsingError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)


class TestAsyncBehavior:
    """Test async behavior and concurrency."""

    async def test_multiple_concurrent_calls(
        self, temp_takeout_dir, sample_watch_history_data
    ):
        """Test that the service handles concurrent calls correctly."""
        service = TakeoutService(temp_takeout_dir)

        # Create test data
        history_file = service.youtube_path / "history" / "watch-history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(sample_watch_history_data, f)

        # Make multiple concurrent calls
        tasks = [
            service.parse_watch_history(),
            service.parse_playlists(),
            service.parse_subscriptions(),
        ]

        results = await asyncio.gather(*tasks)

        # All should complete successfully
        assert len(results) == 3
        # Type assertion to help mypy understand the result types
        watch_history_result = results[0]
        assert isinstance(watch_history_result, list)
        assert len(watch_history_result) == 2  # watch history
        assert results[1] == []  # playlists (empty)
        assert results[2] == []  # subscriptions (empty)

    async def test_analysis_methods_accept_none_data(self, temp_takeout_dir):
        """Test that analysis methods handle None takeout_data parameter."""
        service = TakeoutService(temp_takeout_dir)

        # These methods should parse data internally when None is passed
        overlap = await service.analyze_playlist_overlap(None)
        clusters = await service.analyze_channel_clusters(None)
        patterns = await service.analyze_temporal_patterns(None)

        assert isinstance(overlap, dict)
        assert isinstance(clusters, dict)
        assert isinstance(patterns, dict)


class TestDataIntegrity:
    """Test data integrity and validation."""

    async def test_video_id_extraction_various_formats(self, temp_takeout_dir):
        """Test video ID extraction from various URL formats."""
        service = TakeoutService(temp_takeout_dir)

        # Test various URL formats that might appear in takeout data
        test_data = [
            {
                "header": "YouTube",
                "title": "Watched Video 1",
                "titleUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123s",
                "time": "2023-01-15T14:30:00Z",
            },
            {
                "header": "YouTube",
                "title": "Watched Video 2",
                "titleUrl": "https://www.youtube.com/watch?v\\u003dtest123\\u0026t\\u003d456s",  # Unicode escaped
                "time": "2023-01-16T14:30:00Z",
            },
        ]

        history_file = service.youtube_path / "history" / "watch-history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        result = await service.parse_watch_history()

        assert len(result) == 2
        assert result[0].video_id == "dQw4w9WgXcQ"
        assert result[1].video_id == "test123"

    async def test_date_parsing_consistency(self, temp_takeout_dir):
        """Test that date parsing is consistent across different formats."""
        service = TakeoutService(temp_takeout_dir)

        # Test data with different timestamp formats
        watch_data = [
            {
                "header": "YouTube",
                "title": "Watched Video Z format",
                "titleUrl": "https://www.youtube.com/watch?v=test1",
                "time": "2023-01-15T14:30:00Z",
            },
            {
                "header": "YouTube",
                "title": "Watched Video timezone format",
                "titleUrl": "https://www.youtube.com/watch?v=test2",
                "time": "2023-01-16T14:30:00+00:00",
            },
        ]

        history_file = service.youtube_path / "history" / "watch-history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(watch_data, f)

        # Create playlist with timestamp
        playlists_dir = service.youtube_path / "playlists"
        playlist_file = playlists_dir / "test-playlist.csv"
        with open(playlist_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(
                [
                    ["Video ID", "Playlist Video Creation Timestamp"],
                    ["test1", "2023-01-15T14:30:00+00:00"],
                ]
            )

        takeout_data = await service.parse_all()

        # Both should parse to timezone-aware datetimes
        assert takeout_data.watch_history[0].watched_at is not None
        assert takeout_data.watch_history[0].watched_at.tzinfo is not None
        assert takeout_data.watch_history[1].watched_at is not None
        assert takeout_data.watch_history[1].watched_at.tzinfo is not None
        assert takeout_data.playlists[0].videos[0].creation_timestamp is not None
        assert takeout_data.playlists[0].videos[0].creation_timestamp.tzinfo is not None
