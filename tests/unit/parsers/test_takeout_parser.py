"""
Tests for Google Takeout parser functionality.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pytest

from chronovista.parsers.takeout_parser import TakeoutParser, WatchHistoryEntry


class TestWatchHistoryEntry:
    """Test WatchHistoryEntry Pydantic model."""

    def test_watch_history_entry_creation(self):
        """Test creating a WatchHistoryEntry."""
        entry = WatchHistoryEntry(
            video_id="dQw4w9WgXcQ",
            video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            title="Never Gonna Give You Up",
            action="Watched",
            channel_name="RickAstleyVEVO",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            channel_url="https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
            watched_at=datetime.now(),
            products=["YouTube"],
            activity_controls=["YouTube watch history"],
        )

        assert entry.video_id == "dQw4w9WgXcQ"
        assert entry.title == "Never Gonna Give You Up"
        assert entry.action == "Watched"
        assert entry.channel_name == "RickAstleyVEVO"

    def test_watch_history_entry_defaults(self):
        """Test WatchHistoryEntry with default values."""
        entry = WatchHistoryEntry(
            video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            title="Test Video",
            action="Watched",
            watched_at=datetime.now(),
        )

        assert entry.video_id is None
        assert entry.channel_name is None
        assert entry.channel_id is None
        assert entry.channel_url is None
        assert entry.products == []
        assert entry.activity_controls == []


class TestTakeoutParserVideoId:
    """Test video ID extraction functionality."""

    def test_extract_video_id_standard_youtube_url(self):
        """Test extracting video ID from standard YouTube URLs."""
        test_cases = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxx", "dQw4w9WgXcQ"),
        ]

        for url, expected_id in test_cases:
            result = TakeoutParser.extract_video_id(url)
            assert result == expected_id, f"Failed for URL: {url}"

    def test_extract_video_id_short_youtube_url(self):
        """Test extracting video ID from short YouTube URLs."""
        test_cases = [
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ?t=42", "dQw4w9WgXcQ"),
        ]

        for url, expected_id in test_cases:
            result = TakeoutParser.extract_video_id(url)
            assert result == expected_id, f"Failed for URL: {url}"

    def test_extract_video_id_invalid_urls(self):
        """Test video ID extraction with invalid URLs."""
        invalid_urls = [
            "",
            None,
            "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
            "https://www.youtube.com/post/Ugkx1234567890",
            "https://www.youtube.com/c/RickAstleyVEVO",
            "https://www.youtube.com/@rickastleyvevo",
            "https://www.google.com/search?q=youtube",
            "not-a-url",
            "https://youtu.be/",  # Empty video ID
            "https://youtu.be/invalid-length",  # Invalid length
        ]

        for url in invalid_urls:
            result = TakeoutParser.extract_video_id(url)
            assert result is None, f"Should return None for URL: {url}"

    def test_extract_video_id_community_posts(self):
        """Test that community posts return None."""
        community_urls = [
            "https://www.youtube.com/post/Ugkx1234567890",
            "https://www.youtube.com/channel/UC123/post/Ugkx1234567890",
        ]

        for url in community_urls:
            result = TakeoutParser.extract_video_id(url)
            assert result is None, f"Community post should return None: {url}"


class TestTakeoutParserChannelId:
    """Test channel ID extraction functionality."""

    def test_extract_channel_id_valid_urls(self):
        """Test extracting channel ID from valid channel URLs."""
        test_cases = [
            (
                "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
                "UCuAXFkgsw1L7xaCfnd5JJOw",
            ),
            (
                "https://youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
                "UCuAXFkgsw1L7xaCfnd5JJOw",
            ),
        ]

        for url, expected_id in test_cases:
            result = TakeoutParser.extract_channel_id(url)
            assert result == expected_id, f"Failed for URL: {url}"

    def test_extract_channel_id_custom_urls(self):
        """Test that custom URLs return None (can't extract ID without API)."""
        custom_urls = [
            "https://www.youtube.com/c/RickAstleyVEVO",
            "https://www.youtube.com/@rickastleyvevo",
            "https://www.youtube.com/user/rickastley",
        ]

        for url in custom_urls:
            result = TakeoutParser.extract_channel_id(url)
            assert result is None, f"Custom URL should return None: {url}"

    def test_extract_channel_id_invalid_urls(self):
        """Test channel ID extraction with invalid URLs."""
        invalid_urls = [
            "",
            None,
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.google.com/",
            "not-a-url",
        ]

        for url in invalid_urls:
            result = TakeoutParser.extract_channel_id(url)
            assert result is None, f"Should return None for URL: {url}"


class TestTakeoutParserAction:
    """Test action parsing functionality."""

    def test_parse_action_watched(self):
        """Test parsing 'Watched' action."""
        test_cases = [
            ("Watched Never Gonna Give You Up", ("Watched", "Never Gonna Give You Up")),
            ("Watched Video Title", ("Watched", "Video Title")),
            (
                "Watched Rick Roll Video - Official",
                ("Watched", "Rick Roll Video - Official"),
            ),
        ]

        for title, expected in test_cases:
            result = TakeoutParser.parse_action(title)
            assert result == expected, f"Failed for title: {title}"

    def test_parse_action_viewed(self):
        """Test parsing 'Viewed' action."""
        test_cases = [
            ("Viewed Never Gonna Give You Up", ("Viewed", "Never Gonna Give You Up")),
            ("Viewed Video Title", ("Viewed", "Video Title")),
            ("Viewed Community Post", ("Viewed", "Community Post")),
        ]

        for title, expected in test_cases:
            result = TakeoutParser.parse_action(title)
            assert result == expected, f"Failed for title: {title}"

    def test_parse_action_unknown(self):
        """Test parsing unknown actions."""
        test_cases = [
            ("Never Gonna Give You Up", ("Unknown", "Never Gonna Give You Up")),
            (
                "Liked Never Gonna Give You Up",
                ("Unknown", "Liked Never Gonna Give You Up"),
            ),
            ("", ("Unknown", "")),
            ("   ", ("Unknown", "")),  # Should be stripped
            ("Watched", ("Unknown", "Watched")),  # No space after Watched
            ("Viewed", ("Unknown", "Viewed")),  # No space after Viewed
        ]

        for title, expected in test_cases:
            result = TakeoutParser.parse_action(title)
            assert result == expected, f"Failed for title: {title}"


class TestTakeoutParserFileProcessing:
    """Test file parsing functionality."""

    def create_test_file(self, data: List[Dict]) -> Path:
        """Create a temporary JSON file with test data."""
        temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, temp_file)
        temp_file.flush()
        return Path(temp_file.name)

    def test_parse_watch_history_file_valid_data(self):
        """Test parsing a valid watch history file."""
        test_data = [
            {
                "header": "YouTube",
                "title": "Watched Never Gonna Give You Up",
                "titleUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "time": "2023-12-01T10:30:00Z",
                "subtitles": [
                    {
                        "name": "RickAstleyVEVO",
                        "url": "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
                    }
                ],
                "products": ["YouTube"],
                "activityControls": ["YouTube watch history"],
            },
            {
                "header": "YouTube",
                "title": "Viewed Community Post",
                "titleUrl": "https://www.youtube.com/post/Ugkx1234567890",
                "time": "2023-12-01T11:00:00Z",
                "products": ["YouTube"],
            },
        ]

        file_path = self.create_test_file(test_data)

        try:
            entries = list(TakeoutParser.parse_watch_history_file(file_path))

            # Should only have video entries, not community posts
            assert len(entries) == 1

            entry = entries[0]
            assert entry.video_id == "dQw4w9WgXcQ"
            assert entry.title == "Never Gonna Give You Up"
            assert entry.action == "Watched"
            assert entry.channel_name == "RickAstleyVEVO"
            assert entry.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
            assert entry.products == ["YouTube"]

        finally:
            file_path.unlink()  # Clean up

    def test_parse_watch_history_file_empty_data(self):
        """Test parsing an empty file."""
        test_data = []
        file_path = self.create_test_file(test_data)

        try:
            entries = list(TakeoutParser.parse_watch_history_file(file_path))
            assert len(entries) == 0
        finally:
            file_path.unlink()

    def test_parse_watch_history_file_non_youtube_entries(self):
        """Test parsing file with non-YouTube entries."""
        test_data = [
            {
                "header": "Google Search",
                "title": "Searched for cats",
                "time": "2023-12-01T10:30:00Z",
            },
            {
                "header": "YouTube",
                "title": "Watched Cat Video",
                "titleUrl": "https://www.youtube.com/watch?v=abc123defgh",
                "time": "2023-12-01T11:00:00Z",
            },
        ]

        file_path = self.create_test_file(test_data)

        try:
            entries = list(TakeoutParser.parse_watch_history_file(file_path))
            assert len(entries) == 1
            assert entries[0].title == "Cat Video"
        finally:
            file_path.unlink()

    def test_parse_watch_history_file_invalid_entries(self):
        """Test parsing file with invalid entries."""
        test_data = [
            {
                "header": "YouTube",
                "title": "",  # Empty title
                "titleUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "time": "2023-12-01T10:30:00Z",
            },
            {
                "header": "YouTube",
                "title": "Watched Valid Video",
                "titleUrl": "",  # Empty URL
                "time": "2023-12-01T10:30:00Z",
            },
            {
                "header": "YouTube",
                "title": "Watched Another Video",
                "titleUrl": "https://www.youtube.com/watch?v=abc123defgh",
                "time": "",  # Empty time
            },
            {
                "header": "YouTube",
                "title": "Watched Valid Video 2",
                "titleUrl": "https://www.youtube.com/watch?v=xyz987vwxyz",
                "time": "invalid-date-format",  # Invalid date
            },
        ]

        file_path = self.create_test_file(test_data)

        try:
            entries = list(TakeoutParser.parse_watch_history_file(file_path))
            assert len(entries) == 0  # All entries should be filtered out
        finally:
            file_path.unlink()

    def test_parse_watch_history_file_no_subtitles(self):
        """Test parsing entries without subtitle information."""
        test_data = [
            {
                "header": "YouTube",
                "title": "Watched Video Without Channel Info",
                "titleUrl": "https://www.youtube.com/watch?v=abc123defgh",
                "time": "2023-12-01T10:30:00Z",
                "products": ["YouTube"],
            }
        ]

        file_path = self.create_test_file(test_data)

        try:
            entries = list(TakeoutParser.parse_watch_history_file(file_path))
            assert len(entries) == 1

            entry = entries[0]
            assert entry.channel_name is None
            assert entry.channel_id is None
            assert entry.channel_url is None
        finally:
            file_path.unlink()

    def test_parse_watch_history_file_invalid_json(self):
        """Test parsing invalid JSON file."""
        temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        temp_file.write("{ invalid json")
        temp_file.flush()
        file_path = Path(temp_file.name)

        try:
            with pytest.raises(ValueError, match="Failed to parse JSON file"):
                list(TakeoutParser.parse_watch_history_file(file_path))
        finally:
            file_path.unlink()

    def test_parse_watch_history_file_not_found(self):
        """Test parsing non-existent file."""
        file_path = Path("/nonexistent/file.json")

        with pytest.raises(ValueError, match="Failed to parse JSON file"):
            list(TakeoutParser.parse_watch_history_file(file_path))

    def test_parse_watch_history_file_not_array(self):
        """Test parsing JSON that's not an array."""
        test_data = {"not": "an array"}
        file_path = self.create_test_file(test_data)

        try:
            with pytest.raises(ValueError, match="Expected JSON array at root level"):
                list(TakeoutParser.parse_watch_history_file(file_path))
        finally:
            file_path.unlink()


class TestTakeoutParserCounting:
    """Test entry counting functionality."""

    def create_test_file(self, data: List[Dict]) -> Path:
        """Create a temporary JSON file with test data."""
        temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, temp_file)
        temp_file.flush()
        return Path(temp_file.name)

    def test_count_entries_mixed_data(self):
        """Test counting different types of entries."""
        test_data = [
            {
                "header": "Google Search",
                "title": "Searched for cats",
                "time": "2023-12-01T10:30:00Z",
            },
            {
                "header": "YouTube",
                "title": "Watched Cat Video",
                "titleUrl": "https://www.youtube.com/watch?v=abc123defgh",
                "time": "2023-12-01T11:00:00Z",
            },
            {
                "header": "YouTube",
                "title": "Viewed Community Post",
                "titleUrl": "https://www.youtube.com/post/Ugkx1234567890",
                "time": "2023-12-01T11:30:00Z",
            },
            {
                "header": "YouTube",
                "title": "Viewed Dog Video",
                "titleUrl": "https://www.youtube.com/watch?v=xyz987vwxyz",
                "time": "2023-12-01T12:00:00Z",
            },
            {
                "header": "YouTube",
                "title": "Something else",
                "titleUrl": "https://www.youtube.com/other/something",
                "time": "2023-12-01T12:30:00Z",
            },
        ]

        file_path = self.create_test_file(test_data)

        try:
            counts = TakeoutParser.count_entries(file_path)

            assert counts["total"] == 5
            assert counts["youtube"] == 4
            assert counts["videos"] == 2
            assert counts["community_posts"] == 1
            assert counts["other"] == 1
            assert counts["watched"] == 1
            assert counts["viewed"] == 1
        finally:
            file_path.unlink()

    def test_count_entries_empty_file(self):
        """Test counting entries in empty file."""
        test_data = []
        file_path = self.create_test_file(test_data)

        try:
            counts = TakeoutParser.count_entries(file_path)

            for count in counts.values():
                assert count == 0
        finally:
            file_path.unlink()

    def test_count_entries_invalid_file(self):
        """Test counting entries in invalid file."""
        file_path = Path("/nonexistent/file.json")

        counts = TakeoutParser.count_entries(file_path)

        # Should return zero counts without raising exception
        for count in counts.values():
            assert count == 0

    def test_count_entries_invalid_json(self):
        """Test counting entries with invalid JSON structure."""
        test_data = {"not": "an array"}
        file_path = self.create_test_file(test_data)

        try:
            counts = TakeoutParser.count_entries(file_path)

            # Should return zero counts without raising exception
            for count in counts.values():
                assert count == 0
        finally:
            file_path.unlink()


class TestTakeoutParserEdgeCases:
    """Test edge cases and error handling."""

    def create_test_file(self, data: List[Dict]) -> Path:
        """Create a temporary JSON file with test data."""
        temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, temp_file)
        temp_file.flush()
        return Path(temp_file.name)

    def test_malformed_entry_handling(self):
        """Test handling of malformed entries."""
        test_data = [
            {
                "header": "YouTube",
                "title": "Watched Good Video",
                "titleUrl": "https://www.youtube.com/watch?v=abc123defgh",
                "time": "2023-12-01T10:30:00Z",
            },
            {
                # Missing required fields
                "header": "YouTube"
            },
            {
                "header": "YouTube",
                "title": "Watched Another Video",
                "titleUrl": "https://www.youtube.com/watch?v=xyz987vwxyz",
                "time": "2023-12-01T11:30:00Z",
            },
        ]

        file_path = self.create_test_file(test_data)

        try:
            entries = list(TakeoutParser.parse_watch_history_file(file_path))
            # Should skip malformed entry and continue with valid ones
            assert len(entries) == 2
        finally:
            file_path.unlink()

    def test_special_characters_in_titles(self):
        """Test handling of special characters in titles."""
        test_data = [
            {
                "header": "YouTube",
                "title": "Watched 🎵 Music Video with émojis & spëcîál çhārs 🎬",
                "titleUrl": "https://www.youtube.com/watch?v=abc123defgh",
                "time": "2023-12-01T10:30:00Z",
            }
        ]

        file_path = self.create_test_file(test_data)

        try:
            entries = list(TakeoutParser.parse_watch_history_file(file_path))
            assert len(entries) == 1
            assert "🎵 Music Video with émojis & spëcîál çhārs 🎬" in entries[0].title
        finally:
            file_path.unlink()

    def test_timezone_handling(self):
        """Test handling of different timezone formats."""
        test_data = [
            {
                "header": "YouTube",
                "title": "Watched UTC Video",
                "titleUrl": "https://www.youtube.com/watch?v=abc123defgh",
                "time": "2023-12-01T10:30:00Z",
            },
            {
                "header": "YouTube",
                "title": "Watched ISO Video",
                "titleUrl": "https://www.youtube.com/watch?v=xyz987vwxyz",
                "time": "2023-12-01T10:30:00+00:00",
            },
        ]

        file_path = self.create_test_file(test_data)

        try:
            entries = list(TakeoutParser.parse_watch_history_file(file_path))
            assert len(entries) == 2

            # Both should parse successfully
            for entry in entries:
                assert isinstance(entry.watched_at, datetime)
        finally:
            file_path.unlink()
