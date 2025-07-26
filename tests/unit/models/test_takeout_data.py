"""
Tests for takeout data models.

Comprehensive test coverage for Google Takeout data parsing models.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pytest

from chronovista.models.takeout.takeout_data import (
    TakeoutData,
    TakeoutPlaylist,
    TakeoutPlaylistItem,
    TakeoutSubscription,
    TakeoutWatchEntry,
)


class TestTakeoutWatchEntry:
    """Tests for TakeoutWatchEntry model."""

    def test_basic_creation(self):
        """Test basic watch entry creation."""
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            channel_name="Test Channel",
        )
        assert entry.title == "Test Video"
        assert entry.title_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert entry.channel_name == "Test Channel"
        assert entry.video_id == "dQw4w9WgXcQ"  # Should be extracted from URL

    def test_video_id_extraction_simple_url(self):
        """Test video ID extraction from simple YouTube URL."""
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        assert entry.video_id == "dQw4w9WgXcQ"

    def test_video_id_extraction_url_with_params(self):
        """Test video ID extraction from URL with additional parameters."""
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123s&list=PLtest",
        )
        assert entry.video_id == "dQw4w9WgXcQ"

    def test_video_id_extraction_unicode_escaped_url(self):
        """Test video ID extraction from Unicode-escaped URL."""
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://www.youtube.com/watch?v\\u003ddQw4w9WgXcQ\\u0026t\\u003d123s",
        )
        assert entry.video_id == "dQw4w9WgXcQ"

    def test_video_id_extraction_fallback_parsing(self):
        """Test video ID extraction using URL parsing fallback."""
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://www.youtube.com/embed/dQw4w9WgXcQ?start=123",
        )
        # Should not extract video ID from embed URLs without v= parameter
        assert entry.video_id is None

    def test_video_id_extraction_regex_fallback(self):
        """Test video ID extraction using regex fallback."""
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://example.com/redirect?v=dQw4w9WgXcQ&other=param",
        )
        assert entry.video_id == "dQw4w9WgXcQ"

    def test_video_id_extraction_invalid_url(self):
        """Test video ID extraction from invalid URL."""
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="not-a-valid-url",
        )
        assert entry.video_id is None

    def test_video_id_extraction_no_video_id_in_url(self):
        """Test video ID extraction when URL has no video ID."""
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://www.youtube.com/channel/UCtest",
        )
        assert entry.video_id is None

    def test_video_id_provided_explicitly(self):
        """Test that explicitly provided video ID is preserved."""
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://www.youtube.com/watch?v=different",
            video_id="explicit_id",
        )
        assert entry.video_id == "explicit_id"

    def test_channel_id_extraction_from_url(self):
        """Test channel ID extraction from channel URL."""
        # Note: The validator only runs when channel_id is not explicitly provided
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            channel_url="https://www.youtube.com/channel/UCtest123",
            # Don't provide channel_id so validator can extract it
        )
        assert entry.channel_id == "UCtest123"

    def test_channel_id_extraction_invalid_url(self):
        """Test channel ID extraction from invalid channel URL."""
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            channel_url="https://www.youtube.com/user/testuser",
        )
        assert entry.channel_id is None

    def test_channel_id_provided_explicitly(self):
        """Test that explicitly provided channel ID is preserved."""
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            channel_url="https://www.youtube.com/channel/UCdifferent",
            channel_id="explicit_channel_id",
        )
        assert entry.channel_id == "explicit_channel_id"

    def test_watched_at_parsing_iso_format(self):
        """Test watched_at parsing from ISO format."""
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            raw_time="2023-01-15T14:30:00Z",
        )
        expected_time = datetime(2023, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        assert entry.watched_at == expected_time

    def test_watched_at_parsing_iso_format_with_timezone(self):
        """Test watched_at parsing from ISO format with timezone."""
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            raw_time="2023-01-15T14:30:00+05:00",
        )
        # Should preserve the timezone offset
        assert entry.watched_at is not None
        assert entry.watched_at.year == 2023
        assert entry.watched_at.month == 1
        assert entry.watched_at.day == 15

    def test_watched_at_parsing_invalid_format(self):
        """Test watched_at parsing with invalid time format."""
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            raw_time="invalid-time-format",
        )
        assert entry.watched_at is None

    def test_watched_at_provided_explicitly(self):
        """Test that explicitly provided watched_at is preserved."""
        explicit_time = datetime(2023, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            raw_time="2023-06-15T14:30:00Z",
            watched_at=explicit_time,
        )
        assert entry.watched_at == explicit_time

    def test_all_fields_present(self):
        """Test creation with all fields present."""
        watched_time = datetime(2023, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        entry = TakeoutWatchEntry(
            video_id="dQw4w9WgXcQ",
            title="Test Video",
            title_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            channel_name="Test Channel",
            channel_url="https://www.youtube.com/channel/UCtest123",
            channel_id="UCtest123",
            watched_at=watched_time,
            raw_time="2023-01-15T14:30:00Z",
        )
        assert entry.video_id == "dQw4w9WgXcQ"
        assert entry.title == "Test Video"
        assert entry.title_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert entry.channel_name == "Test Channel"
        assert entry.channel_url == "https://www.youtube.com/channel/UCtest123"
        assert entry.channel_id == "UCtest123"
        assert entry.watched_at == watched_time
        assert entry.raw_time == "2023-01-15T14:30:00Z"


class TestTakeoutPlaylistItem:
    """Tests for TakeoutPlaylistItem model."""

    def test_basic_creation(self):
        """Test basic playlist item creation."""
        item = TakeoutPlaylistItem(
            video_id="dQw4w9WgXcQ",
            raw_timestamp="2023-01-15T14:30:00+00:00",
        )
        assert item.video_id == "dQw4w9WgXcQ"
        assert item.raw_timestamp == "2023-01-15T14:30:00+00:00"
        assert item.creation_timestamp is not None
        assert item.creation_timestamp.year == 2023

    def test_timestamp_parsing_from_raw(self):
        """Test creation_timestamp parsing from raw_timestamp."""
        item = TakeoutPlaylistItem(
            video_id="dQw4w9WgXcQ",
            raw_timestamp="2023-01-15T14:30:00+00:00",
        )
        expected_time = datetime.fromisoformat("2023-01-15T14:30:00+00:00")
        assert item.creation_timestamp == expected_time

    def test_timestamp_parsing_invalid_format(self):
        """Test creation_timestamp parsing with invalid raw_timestamp."""
        item = TakeoutPlaylistItem(
            video_id="dQw4w9WgXcQ",
            raw_timestamp="invalid-timestamp",
        )
        assert item.creation_timestamp is None

    def test_timestamp_parsing_empty_raw(self):
        """Test creation_timestamp parsing with empty raw_timestamp."""
        item = TakeoutPlaylistItem(
            video_id="dQw4w9WgXcQ",
            raw_timestamp="",
        )
        assert item.creation_timestamp is None

    def test_explicit_creation_timestamp_preserved(self):
        """Test that explicitly provided creation_timestamp is preserved."""
        explicit_time = datetime(2023, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        item = TakeoutPlaylistItem(
            video_id="dQw4w9WgXcQ",
            raw_timestamp="2023-06-15T14:30:00+00:00",
            creation_timestamp=explicit_time,
        )
        assert item.creation_timestamp == explicit_time

    def test_no_raw_timestamp(self):
        """Test creation without raw_timestamp."""
        item = TakeoutPlaylistItem(video_id="dQw4w9WgXcQ")
        assert item.video_id == "dQw4w9WgXcQ"
        assert item.raw_timestamp is None
        assert item.creation_timestamp is None


class TestTakeoutPlaylist:
    """Tests for TakeoutPlaylist model."""

    def test_basic_creation(self):
        """Test basic playlist creation."""
        playlist = TakeoutPlaylist(
            name="My Playlist",
            file_path=Path("/path/to/playlist.csv"),
        )
        assert playlist.name == "My Playlist"
        assert playlist.file_path == Path("/path/to/playlist.csv")
        assert playlist.videos == []
        assert playlist.video_count == 0

    def test_playlist_with_videos(self):
        """Test playlist creation with videos."""
        videos = [
            TakeoutPlaylistItem(video_id="video1"),
            TakeoutPlaylistItem(video_id="video2"),
            TakeoutPlaylistItem(video_id="video3"),
        ]
        playlist = TakeoutPlaylist(
            name="My Playlist",
            file_path=Path("/path/to/playlist.csv"),
            videos=videos,
        )
        assert playlist.name == "My Playlist"
        assert len(playlist.videos) == 3
        assert playlist.video_count == 3
        assert playlist.videos[0].video_id == "video1"

    def test_video_count_validation(self):
        """Test that video_count is automatically calculated when not provided."""
        videos = [
            TakeoutPlaylistItem(video_id="video1"),
            TakeoutPlaylistItem(video_id="video2"),
        ]
        playlist = TakeoutPlaylist(
            name="My Playlist",
            file_path=Path("/path/to/playlist.csv"),
            videos=videos,
            # Don't provide video_count so it gets calculated automatically
        )
        assert playlist.video_count == 2  # Should be calculated from videos list

    def test_explicit_video_count_preserved(self):
        """Test that explicitly provided video_count is preserved."""
        videos = [
            TakeoutPlaylistItem(video_id="video1"),
            TakeoutPlaylistItem(video_id="video2"),
        ]
        playlist = TakeoutPlaylist(
            name="My Playlist",
            file_path=Path("/path/to/playlist.csv"),
            videos=videos,
            video_count=999,  # Explicit value should be preserved
        )
        assert playlist.video_count == 999  # Should preserve explicit value


class TestTakeoutSubscription:
    """Tests for TakeoutSubscription model."""

    def test_basic_creation(self):
        """Test basic subscription creation."""
        subscription = TakeoutSubscription(
            channel_title="Test Channel",
            channel_url="https://www.youtube.com/channel/UCtest123",
        )
        assert subscription.channel_title == "Test Channel"
        assert subscription.channel_url == "https://www.youtube.com/channel/UCtest123"
        assert subscription.channel_id == "UCtest123"  # Should be extracted

    def test_channel_id_extraction_from_url(self):
        """Test channel ID extraction from channel URL."""
        subscription = TakeoutSubscription(
            channel_title="Test Channel",
            channel_url="https://www.youtube.com/channel/UCtest123",
        )
        assert subscription.channel_id == "UCtest123"

    def test_channel_id_extraction_custom_url(self):
        """Test channel ID extraction from custom URL (should return None)."""
        subscription = TakeoutSubscription(
            channel_title="Test Channel",
            channel_url="https://www.youtube.com/c/testchannel",
        )
        assert subscription.channel_id is None

    def test_channel_id_provided_explicitly(self):
        """Test that explicitly provided channel ID is preserved."""
        subscription = TakeoutSubscription(
            channel_title="Test Channel",
            channel_url="https://www.youtube.com/channel/UCdifferent",
            channel_id="explicit_id",
        )
        assert subscription.channel_id == "explicit_id"

    def test_channel_id_extraction_invalid_url(self):
        """Test channel ID extraction from invalid URL."""
        subscription = TakeoutSubscription(
            channel_title="Test Channel",
            channel_url="https://example.com/invalid",
        )
        assert subscription.channel_id is None


class TestTakeoutData:
    """Tests for TakeoutData model."""

    def test_basic_creation(self):
        """Test basic takeout data creation."""
        data = TakeoutData(takeout_path=Path("/path/to/takeout"))
        assert data.takeout_path == Path("/path/to/takeout")
        assert data.watch_history == []
        assert data.playlists == []
        assert data.subscriptions == []
        assert data.total_videos_watched == 0
        assert data.total_playlists == 0
        assert data.total_subscriptions == 0
        assert data.date_range is None

    def test_creation_with_data(self):
        """Test takeout data creation with actual data."""
        watch_entries = [
            TakeoutWatchEntry(
                title="Video 1",
                title_url="https://www.youtube.com/watch?v=video1",
                video_id="video1",
            ),
            TakeoutWatchEntry(
                title="Video 2",
                title_url="https://www.youtube.com/watch?v=video2",
                video_id="video2",
            ),
            TakeoutWatchEntry(
                title="Video 1 Again",  # Duplicate video
                title_url="https://www.youtube.com/watch?v=video1",
                video_id="video1",
            ),
        ]

        playlists = [
            TakeoutPlaylist(
                name="Playlist 1",
                file_path=Path("/path/to/playlist1.csv"),
                videos=[TakeoutPlaylistItem(video_id="video1")],
            ),
            TakeoutPlaylist(
                name="Playlist 2",
                file_path=Path("/path/to/playlist2.csv"),
                videos=[],
            ),
        ]

        subscriptions = [
            TakeoutSubscription(
                channel_title="Channel 1",
                channel_url="https://www.youtube.com/channel/UC1",
            ),
            TakeoutSubscription(
                channel_title="Channel 2",
                channel_url="https://www.youtube.com/channel/UC2",
            ),
            TakeoutSubscription(
                channel_title="Channel 3",
                channel_url="https://www.youtube.com/channel/UC3",
            ),
        ]

        data = TakeoutData(
            takeout_path=Path("/path/to/takeout"),
            watch_history=watch_entries,
            playlists=playlists,
            subscriptions=subscriptions,
        )

        assert data.total_videos_watched == 2  # Unique videos only
        assert data.total_playlists == 2
        assert data.total_subscriptions == 3

    def test_unique_video_count_calculation(self):
        """Test that unique video count is calculated correctly."""
        watch_entries = [
            TakeoutWatchEntry(
                title="Video 1",
                title_url="https://www.youtube.com/watch?v=video1",
                video_id="video1",
            ),
            TakeoutWatchEntry(
                title="Video 2",
                title_url="https://www.youtube.com/watch?v=video2",
                video_id="video2",
            ),
            TakeoutWatchEntry(
                title="Video 1 Repeat",
                title_url="https://www.youtube.com/watch?v=video1",
                video_id="video1",
            ),
            TakeoutWatchEntry(
                title="Video without ID",
                title_url="https://invalid-url",
                video_id=None,
            ),
        ]

        data = TakeoutData(
            takeout_path=Path("/path/to/takeout"),
            watch_history=watch_entries,
        )

        assert data.total_videos_watched == 2  # Only video1 and video2

    def test_date_range_calculation(self):
        """Test date range calculation from watch history."""
        time1 = datetime(2023, 1, 15, tzinfo=timezone.utc)
        time2 = datetime(2023, 6, 15, tzinfo=timezone.utc)
        time3 = datetime(2023, 3, 15, tzinfo=timezone.utc)

        watch_entries = [
            TakeoutWatchEntry(
                title="Video 1",
                title_url="https://www.youtube.com/watch?v=video1",
                watched_at=time1,
            ),
            TakeoutWatchEntry(
                title="Video 2",
                title_url="https://www.youtube.com/watch?v=video2",
                watched_at=time2,
            ),
            TakeoutWatchEntry(
                title="Video 3",
                title_url="https://www.youtube.com/watch?v=video3",
                watched_at=time3,
            ),
            TakeoutWatchEntry(
                title="Video 4",
                title_url="https://www.youtube.com/watch?v=video4",
                watched_at=None,  # Should be ignored
            ),
        ]

        data = TakeoutData(
            takeout_path=Path("/path/to/takeout"),
            watch_history=watch_entries,
        )

        assert data.date_range is not None
        assert data.date_range[0] == time1  # Earliest
        assert data.date_range[1] == time2  # Latest

    def test_date_range_no_timestamps(self):
        """Test date range when no timestamps are available."""
        watch_entries = [
            TakeoutWatchEntry(
                title="Video 1",
                title_url="https://www.youtube.com/watch?v=video1",
                watched_at=None,
            ),
        ]

        data = TakeoutData(
            takeout_path=Path("/path/to/takeout"),
            watch_history=watch_entries,
        )

        assert data.date_range is None

    def test_date_range_preserved_when_provided(self):
        """Test that explicitly provided date_range is preserved."""
        time1 = datetime(2023, 1, 15, tzinfo=timezone.utc)
        time2 = datetime(2023, 6, 15, tzinfo=timezone.utc)
        explicit_range = (time1, time2)

        data = TakeoutData(
            takeout_path=Path("/path/to/takeout"),
            date_range=explicit_range,
        )

        assert data.date_range == explicit_range

    def test_get_unique_video_ids(self):
        """Test getting unique video IDs from all sources."""
        watch_entries = [
            TakeoutWatchEntry(
                title="Video 1",
                title_url="https://www.youtube.com/watch?v=video1",
                video_id="video1",
            ),
            TakeoutWatchEntry(
                title="Video 2",
                title_url="https://www.youtube.com/watch?v=video2",
                video_id="video2",
            ),
        ]

        playlists = [
            TakeoutPlaylist(
                name="Playlist 1",
                file_path=Path("/path/to/playlist1.csv"),
                videos=[
                    TakeoutPlaylistItem(video_id="video2"),  # Duplicate
                    TakeoutPlaylistItem(video_id="video3"),  # New
                    TakeoutPlaylistItem(video_id=""),  # Empty, should be ignored
                ],
            ),
        ]

        data = TakeoutData(
            takeout_path=Path("/path/to/takeout"),
            watch_history=watch_entries,
            playlists=playlists,
        )

        unique_ids = data.get_unique_video_ids()
        assert unique_ids == {"video1", "video2", "video3"}

    def test_get_unique_channel_ids(self):
        """Test getting unique channel IDs from all sources."""
        watch_entries = [
            TakeoutWatchEntry(
                title="Video 1",
                title_url="https://www.youtube.com/watch?v=video1",
                channel_id="UC1",
            ),
            TakeoutWatchEntry(
                title="Video 2",
                title_url="https://www.youtube.com/watch?v=video2",
                channel_id="UC2",
            ),
        ]

        subscriptions = [
            TakeoutSubscription(
                channel_title="Channel 2",
                channel_url="https://www.youtube.com/channel/UC2",  # Duplicate
                channel_id="UC2",
            ),
            TakeoutSubscription(
                channel_title="Channel 3",
                channel_url="https://www.youtube.com/channel/UC3",  # New
                channel_id="UC3",
            ),
            TakeoutSubscription(
                channel_title="Channel 4",
                channel_url="https://www.youtube.com/c/custom",  # No ID
                channel_id=None,
            ),
        ]

        data = TakeoutData(
            takeout_path=Path("/path/to/takeout"),
            watch_history=watch_entries,
            subscriptions=subscriptions,
        )

        unique_ids = data.get_unique_channel_ids()
        assert unique_ids == {"UC1", "UC2", "UC3"}

    def test_parsed_at_default(self):
        """Test that parsed_at gets a default value."""
        data = TakeoutData(takeout_path=Path("/path/to/takeout"))
        assert data.parsed_at is not None
        assert isinstance(data.parsed_at, datetime)
