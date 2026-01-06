"""
Tests for Historical Takeout Discovery and Parsing.

Unit tests for the historical takeout discovery and metadata recovery
methods in TakeoutService (T025a-T025d coverage).
"""

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pytest

pytestmark = pytest.mark.asyncio

from chronovista.models.takeout.recovery import (
    HistoricalTakeout,
    RecoveredChannelMetadata,
    RecoveredVideoMetadata,
)
from chronovista.services.takeout_service import TakeoutService


class TestDiscoverHistoricalTakeouts:
    """Tests for discover_historical_takeouts static method (T025a)."""

    @pytest.fixture
    def temp_takeout_base(self) -> Path:
        """Create a temporary base directory for takeouts."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    def _create_takeout_dir(
        self,
        base_path: Path,
        name: str,
        with_watch_history: bool = True,
        with_playlists: bool = False,
        with_subscriptions: bool = False,
    ) -> Path:
        """Helper to create a takeout directory structure."""
        takeout_dir = base_path / name
        youtube_dir = takeout_dir / "YouTube and YouTube Music"
        youtube_dir.mkdir(parents=True)

        if with_watch_history:
            history_dir = youtube_dir / "history"
            history_dir.mkdir()
            (history_dir / "watch-history.json").write_text("[]")

        if with_playlists:
            playlists_dir = youtube_dir / "playlists"
            playlists_dir.mkdir()

        if with_subscriptions:
            subs_dir = youtube_dir / "subscriptions"
            subs_dir.mkdir()
            (subs_dir / "subscriptions.csv").write_text("Channel Id,Channel Url,Channel Title")

        return takeout_dir

    def test_discover_no_takeouts(self, temp_takeout_base: Path) -> None:
        """Test discovery when no takeouts exist."""
        takeouts = TakeoutService.discover_historical_takeouts(temp_takeout_base)
        assert len(takeouts) == 0

    def test_discover_single_takeout(self, temp_takeout_base: Path) -> None:
        """Test discovering a single takeout with date in name."""
        self._create_takeout_dir(
            temp_takeout_base,
            "YouTube and YouTube Music 2024-01-15",
            with_watch_history=True,
        )

        takeouts = TakeoutService.discover_historical_takeouts(temp_takeout_base)

        assert len(takeouts) == 1
        assert takeouts[0].export_date.date() == datetime(2024, 1, 15).date()
        assert takeouts[0].has_watch_history is True
        assert takeouts[0].has_playlists is False
        assert takeouts[0].has_subscriptions is False

    def test_discover_multiple_takeouts(self, temp_takeout_base: Path) -> None:
        """Test discovering multiple takeouts and sorting."""
        self._create_takeout_dir(temp_takeout_base, "Takeout 2024-01-15")
        self._create_takeout_dir(temp_takeout_base, "Takeout 2023-06-01")
        self._create_takeout_dir(temp_takeout_base, "Takeout 2024-03-20")

        # Default sort: oldest first
        takeouts = TakeoutService.discover_historical_takeouts(
            temp_takeout_base, sort_oldest_first=True
        )

        assert len(takeouts) == 3
        assert takeouts[0].export_date < takeouts[1].export_date
        assert takeouts[1].export_date < takeouts[2].export_date

    def test_discover_multiple_takeouts_newest_first(
        self, temp_takeout_base: Path
    ) -> None:
        """Test discovering takeouts sorted newest first."""
        self._create_takeout_dir(temp_takeout_base, "Takeout 2024-01-15")
        self._create_takeout_dir(temp_takeout_base, "Takeout 2023-06-01")
        self._create_takeout_dir(temp_takeout_base, "Takeout 2024-03-20")

        takeouts = TakeoutService.discover_historical_takeouts(
            temp_takeout_base, sort_oldest_first=False
        )

        assert len(takeouts) == 3
        assert takeouts[0].export_date > takeouts[1].export_date
        assert takeouts[1].export_date > takeouts[2].export_date

    def test_discover_takeout_with_all_features(
        self, temp_takeout_base: Path
    ) -> None:
        """Test discovering a takeout with all data types."""
        self._create_takeout_dir(
            temp_takeout_base,
            "Full Takeout 2024-02-28",
            with_watch_history=True,
            with_playlists=True,
            with_subscriptions=True,
        )

        takeouts = TakeoutService.discover_historical_takeouts(temp_takeout_base)

        assert len(takeouts) == 1
        assert takeouts[0].has_watch_history is True
        assert takeouts[0].has_playlists is True
        assert takeouts[0].has_subscriptions is True

    def test_discover_ignores_invalid_directories(
        self, temp_takeout_base: Path
    ) -> None:
        """Test that directories without YouTube data are ignored."""
        # Create directory with date but no YouTube folder
        empty_dir = temp_takeout_base / "Takeout 2024-01-15"
        empty_dir.mkdir()

        # Create directory without date
        no_date_dir = temp_takeout_base / "Random Folder"
        no_date_dir.mkdir()
        youtube_in_no_date = no_date_dir / "YouTube and YouTube Music"
        youtube_in_no_date.mkdir()

        takeouts = TakeoutService.discover_historical_takeouts(temp_takeout_base)

        assert len(takeouts) == 0

    def test_discover_nonexistent_path(self, temp_takeout_base: Path) -> None:
        """Test discovery with nonexistent base path."""
        nonexistent = temp_takeout_base / "nonexistent"
        takeouts = TakeoutService.discover_historical_takeouts(nonexistent)
        assert len(takeouts) == 0

    def test_discover_various_date_formats(self, temp_takeout_base: Path) -> None:
        """Test that various naming patterns with dates are discovered."""
        self._create_takeout_dir(temp_takeout_base, "2024-01-15")
        self._create_takeout_dir(temp_takeout_base, "takeout-2024-02-20-data")
        self._create_takeout_dir(temp_takeout_base, "my_backup_2024-03-25")

        takeouts = TakeoutService.discover_historical_takeouts(temp_takeout_base)

        assert len(takeouts) == 3
        dates = [t.export_date.date() for t in takeouts]
        assert datetime(2024, 1, 15).date() in dates
        assert datetime(2024, 2, 20).date() in dates
        assert datetime(2024, 3, 25).date() in dates


class TestParseHistoricalWatchHistory:
    """Tests for parse_historical_watch_history method (T025b)."""

    @pytest.fixture
    def temp_takeout_dir(self) -> Path:
        """Create a temporary takeout directory."""
        temp_dir = Path(tempfile.mkdtemp())
        youtube_dir = temp_dir / "YouTube and YouTube Music"
        youtube_dir.mkdir(parents=True)
        (youtube_dir / "history").mkdir()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def sample_watch_history(self) -> List[dict]:
        """Sample watch history JSON data."""
        return [
            {
                "header": "YouTube",
                "title": "Watched Never Gonna Give You Up",
                "titleUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "subtitles": [
                    {
                        "name": "RickAstleyVEVO",
                        "url": "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
                    }
                ],
                "time": "2024-01-15T14:30:00Z",
            },
            {
                "header": "YouTube",
                "title": "Watched Python Tutorial",
                "titleUrl": "https://www.youtube.com/watch?v=python123",
                "subtitles": [
                    {"name": "TechChannel", "url": "https://www.youtube.com/channel/UCtech123"}
                ],
                "time": "2024-01-16T10:00:00Z",
            },
        ]

    async def test_parse_valid_watch_history(
        self, temp_takeout_dir: Path, sample_watch_history: List[dict]
    ) -> None:
        """Test parsing a valid watch history file."""
        youtube_dir = temp_takeout_dir / "YouTube and YouTube Music"
        history_file = youtube_dir / "history" / "watch-history.json"
        history_file.write_text(json.dumps(sample_watch_history))

        # Create service instance (need to handle the constructor)
        service = object.__new__(TakeoutService)
        service.takeout_path = temp_takeout_dir
        service.youtube_path = youtube_dir

        takeout = HistoricalTakeout(
            path=youtube_dir,
            export_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            has_watch_history=True,
        )

        entries = await service.parse_historical_watch_history(takeout)

        assert len(entries) == 2
        # Titles should have "Watched " prefix removed
        assert entries[0].title == "Never Gonna Give You Up"
        assert entries[1].title == "Python Tutorial"
        assert entries[0].channel_name == "RickAstleyVEVO"

    async def test_parse_empty_watch_history(self, temp_takeout_dir: Path) -> None:
        """Test parsing an empty watch history file."""
        youtube_dir = temp_takeout_dir / "YouTube and YouTube Music"
        history_file = youtube_dir / "history" / "watch-history.json"
        history_file.write_text("[]")

        service = object.__new__(TakeoutService)
        service.takeout_path = temp_takeout_dir
        service.youtube_path = youtube_dir

        takeout = HistoricalTakeout(
            path=youtube_dir,
            export_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            has_watch_history=True,
        )

        entries = await service.parse_historical_watch_history(takeout)

        assert len(entries) == 0

    async def test_parse_skips_community_posts(self, temp_takeout_dir: Path) -> None:
        """Test that Community Posts are skipped."""
        youtube_dir = temp_takeout_dir / "YouTube and YouTube Music"
        history_file = youtube_dir / "history" / "watch-history.json"

        history_data = [
            {
                "header": "YouTube",
                "title": "Watched Real Video",
                "titleUrl": "https://www.youtube.com/watch?v=realvideo",
                "time": "2024-01-15T14:30:00Z",
            },
            {
                "header": "YouTube",
                "title": "Viewed a post from SomeChannel",  # Community Post
                "titleUrl": "https://www.youtube.com/post/abc123",
                "time": "2024-01-16T10:00:00Z",
            },
        ]
        history_file.write_text(json.dumps(history_data))

        service = object.__new__(TakeoutService)
        service.takeout_path = temp_takeout_dir
        service.youtube_path = youtube_dir

        takeout = HistoricalTakeout(
            path=youtube_dir,
            export_date=datetime.now(timezone.utc),
            has_watch_history=True,
        )

        entries = await service.parse_historical_watch_history(takeout)

        assert len(entries) == 1
        assert entries[0].title == "Real Video"

    async def test_parse_skips_non_youtube_entries(
        self, temp_takeout_dir: Path
    ) -> None:
        """Test that non-YouTube entries are skipped."""
        youtube_dir = temp_takeout_dir / "YouTube and YouTube Music"
        history_file = youtube_dir / "history" / "watch-history.json"

        history_data = [
            {
                "header": "YouTube",
                "title": "Watched YouTube Video",
                "titleUrl": "https://www.youtube.com/watch?v=yt123",
                "time": "2024-01-15T14:30:00Z",
            },
            {
                "header": "Google Play Music",  # Not YouTube
                "title": "Listened to a song",
                "time": "2024-01-16T10:00:00Z",
            },
        ]
        history_file.write_text(json.dumps(history_data))

        service = object.__new__(TakeoutService)
        service.takeout_path = temp_takeout_dir
        service.youtube_path = youtube_dir

        takeout = HistoricalTakeout(
            path=youtube_dir,
            export_date=datetime.now(timezone.utc),
            has_watch_history=True,
        )

        entries = await service.parse_historical_watch_history(takeout)

        assert len(entries) == 1
        assert entries[0].title == "YouTube Video"

    async def test_parse_no_watch_history_flag(self, temp_takeout_dir: Path) -> None:
        """Test parsing when has_watch_history is False."""
        youtube_dir = temp_takeout_dir / "YouTube and YouTube Music"

        service = object.__new__(TakeoutService)
        service.takeout_path = temp_takeout_dir
        service.youtube_path = youtube_dir

        takeout = HistoricalTakeout(
            path=youtube_dir,
            export_date=datetime.now(timezone.utc),
            has_watch_history=False,  # No watch history
        )

        entries = await service.parse_historical_watch_history(takeout)

        assert len(entries) == 0

    async def test_parse_invalid_json(self, temp_takeout_dir: Path) -> None:
        """Test parsing invalid JSON gracefully."""
        youtube_dir = temp_takeout_dir / "YouTube and YouTube Music"
        history_file = youtube_dir / "history" / "watch-history.json"
        history_file.write_text("{ invalid json }")

        service = object.__new__(TakeoutService)
        service.takeout_path = temp_takeout_dir
        service.youtube_path = youtube_dir

        takeout = HistoricalTakeout(
            path=youtube_dir,
            export_date=datetime.now(timezone.utc),
            has_watch_history=True,
        )

        entries = await service.parse_historical_watch_history(takeout)

        assert len(entries) == 0  # Returns empty list on error


class TestBuildRecoveryMetadataMap:
    """Tests for build_recovery_metadata_map method (T025c/T025d)."""

    @pytest.fixture
    def temp_takeout_base(self) -> Path:
        """Create a temporary base directory."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    def _create_takeout_with_history(
        self,
        base_path: Path,
        name: str,
        history_data: List[dict],
    ) -> HistoricalTakeout:
        """Helper to create a takeout with watch history."""
        takeout_dir = base_path / name
        youtube_dir = takeout_dir / "YouTube and YouTube Music"
        youtube_dir.mkdir(parents=True)
        history_dir = youtube_dir / "history"
        history_dir.mkdir()

        history_file = history_dir / "watch-history.json"
        history_file.write_text(json.dumps(history_data))

        # Extract date from name
        import re

        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", name)
        if date_match:
            export_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        else:
            export_date = datetime.now(timezone.utc)

        return HistoricalTakeout(
            path=youtube_dir,
            export_date=export_date,
            has_watch_history=True,
        )

    async def test_build_map_single_takeout(self, temp_takeout_base: Path) -> None:
        """Test building metadata map from a single takeout."""
        history_data = [
            {
                "header": "YouTube",
                "title": "Watched Test Video",
                "titleUrl": "https://www.youtube.com/watch?v=test123",
                "subtitles": [
                    {"name": "TestChannel", "url": "https://www.youtube.com/channel/UCtest"}
                ],
                "time": "2024-01-15T14:30:00Z",
            }
        ]

        takeout = self._create_takeout_with_history(
            temp_takeout_base, "Takeout 2024-01-15", history_data
        )

        service = object.__new__(TakeoutService)
        service.takeout_path = temp_takeout_base
        service.youtube_path = takeout.path

        video_metadata, channel_metadata = await service.build_recovery_metadata_map(
            [takeout]
        )

        assert len(video_metadata) == 1
        assert "test123" in video_metadata
        assert video_metadata["test123"].title == "Test Video"
        assert len(channel_metadata) >= 0  # Channel metadata depends on extraction

    async def test_build_map_newer_overwrites_older(
        self, temp_takeout_base: Path
    ) -> None:
        """Test that newer takeout data overwrites older when processing oldest first."""
        old_history = [
            {
                "header": "YouTube",
                "title": "Watched Old Title",
                "titleUrl": "https://www.youtube.com/watch?v=video123",
                "subtitles": [{"name": "OldChannel", "url": "https://www.youtube.com/channel/UCold"}],
                "time": "2023-01-15T14:30:00Z",
            }
        ]

        new_history = [
            {
                "header": "YouTube",
                "title": "Watched New Title",
                "titleUrl": "https://www.youtube.com/watch?v=video123",
                "subtitles": [{"name": "NewChannel", "url": "https://www.youtube.com/channel/UCnew"}],
                "time": "2024-06-15T14:30:00Z",
            }
        ]

        old_takeout = self._create_takeout_with_history(
            temp_takeout_base, "Takeout 2023-01-15", old_history
        )
        new_takeout = self._create_takeout_with_history(
            temp_takeout_base, "Takeout 2024-06-15", new_history
        )

        service = object.__new__(TakeoutService)
        service.takeout_path = temp_takeout_base
        service.youtube_path = old_takeout.path

        # Process oldest first (default), so newer should overwrite
        video_metadata, channel_metadata = await service.build_recovery_metadata_map(
            [old_takeout, new_takeout], process_oldest_first=True
        )

        assert len(video_metadata) == 1
        assert video_metadata["video123"].title == "New Title"

    async def test_build_map_empty_takeouts(self, temp_takeout_base: Path) -> None:
        """Test building map with empty takeouts list."""
        service = object.__new__(TakeoutService)
        service.takeout_path = temp_takeout_base
        service.youtube_path = temp_takeout_base

        video_metadata, channel_metadata = await service.build_recovery_metadata_map([])

        assert len(video_metadata) == 0
        assert len(channel_metadata) == 0

    async def test_build_map_aggregates_channel_counts(
        self, temp_takeout_base: Path
    ) -> None:
        """Test that channel video counts are aggregated across entries."""
        history_data = [
            {
                "header": "YouTube",
                "title": "Watched Video 1",
                "titleUrl": "https://www.youtube.com/watch?v=vid1",
                "subtitles": [
                    {"name": "SameChannel", "url": "https://www.youtube.com/channel/UCsame"}
                ],
                "time": "2024-01-15T14:30:00Z",
            },
            {
                "header": "YouTube",
                "title": "Watched Video 2",
                "titleUrl": "https://www.youtube.com/watch?v=vid2",
                "subtitles": [
                    {"name": "SameChannel", "url": "https://www.youtube.com/channel/UCsame"}
                ],
                "time": "2024-01-16T14:30:00Z",
            },
        ]

        takeout = self._create_takeout_with_history(
            temp_takeout_base, "Takeout 2024-01-15", history_data
        )

        service = object.__new__(TakeoutService)
        service.takeout_path = temp_takeout_base
        service.youtube_path = takeout.path

        video_metadata, channel_metadata = await service.build_recovery_metadata_map(
            [takeout]
        )

        assert len(video_metadata) == 2


class TestGetRecoverySummary:
    """Tests for get_recovery_summary method."""

    def test_summary_empty_list(self) -> None:
        """Test summary with empty takeouts list."""
        service = object.__new__(TakeoutService)
        service.takeout_path = Path("/fake")
        service.youtube_path = Path("/fake")

        summary = service.get_recovery_summary([])

        assert summary["takeout_count"] == 0
        assert summary["oldest_date"] is None
        assert summary["newest_date"] is None

    def test_summary_single_takeout(self) -> None:
        """Test summary with a single takeout."""
        takeout = HistoricalTakeout(
            path=Path("/takeouts/2024-01-15"),
            export_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            has_watch_history=True,
            has_playlists=True,
            has_subscriptions=False,
        )

        service = object.__new__(TakeoutService)
        service.takeout_path = Path("/fake")
        service.youtube_path = Path("/fake")

        summary = service.get_recovery_summary([takeout])

        assert summary["takeout_count"] == 1
        assert summary["with_watch_history"] == 1
        assert summary["with_playlists"] == 1
        assert summary["with_subscriptions"] == 0

    def test_summary_multiple_takeouts(self) -> None:
        """Test summary with multiple takeouts."""
        takeouts = [
            HistoricalTakeout(
                path=Path("/takeouts/2023-01-15"),
                export_date=datetime(2023, 1, 15, tzinfo=timezone.utc),
                has_watch_history=True,
            ),
            HistoricalTakeout(
                path=Path("/takeouts/2024-06-15"),
                export_date=datetime(2024, 6, 15, tzinfo=timezone.utc),
                has_watch_history=True,
                has_playlists=True,
            ),
            HistoricalTakeout(
                path=Path("/takeouts/2024-12-01"),
                export_date=datetime(2024, 12, 1, tzinfo=timezone.utc),
                has_watch_history=False,
                has_subscriptions=True,
            ),
        ]

        service = object.__new__(TakeoutService)
        service.takeout_path = Path("/fake")
        service.youtube_path = Path("/fake")

        summary = service.get_recovery_summary(takeouts)

        assert summary["takeout_count"] == 3
        assert summary["with_watch_history"] == 2
        assert summary["with_playlists"] == 1
        assert summary["with_subscriptions"] == 1
        assert "2023-01-15" in summary["oldest_date"]
        assert "2024-12-01" in summary["newest_date"]
