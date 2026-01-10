"""
Google Takeout data parser for YouTube watch history.

Parses JSON data from Google Takeout exports and converts it
to chronovista data models.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field

from chronovista.exceptions import ValidationError


class WatchHistoryEntry(BaseModel):
    """
    Parsed watch history entry from Google Takeout.
    """

    # Video identification
    video_id: Optional[str] = None
    video_url: str

    # Video metadata
    title: str
    action: str = Field(description="'Watched' or 'Viewed'")

    # Channel information
    channel_name: Optional[str] = None
    channel_id: Optional[str] = None
    channel_url: Optional[str] = None

    # Timing
    watched_at: datetime

    # Source data
    products: List[str] = Field(default_factory=list)
    activity_controls: List[str] = Field(default_factory=list)


class TakeoutParser:
    """
    Parser for Google Takeout YouTube data.
    """

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """
        Extract video ID from YouTube URL.

        Handles various YouTube URL formats:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://m.youtube.com/watch?v=VIDEO_ID
        """
        if not url:
            return None

        # Parse URL
        parsed = urlparse(url)

        # Standard youtube.com/watch URLs
        if parsed.netloc in ["www.youtube.com", "youtube.com", "m.youtube.com"]:
            if parsed.path == "/watch":
                query_params = parse_qs(parsed.query)
                return query_params.get("v", [None])[0]

        # Short youtu.be URLs
        elif parsed.netloc == "youtu.be":
            # Path is /VIDEO_ID
            video_id = parsed.path.lstrip("/")
            if video_id and len(video_id) == 11:  # YouTube video IDs are 11 chars
                return video_id

        # YouTube posts/community posts (not videos)
        elif "/post/" in url:
            return None

        return None

    @staticmethod
    def extract_channel_id(url: str) -> Optional[str]:
        """
        Extract channel ID from YouTube channel URL.

        Handles formats:
        - https://www.youtube.com/channel/CHANNEL_ID
        - https://www.youtube.com/c/CHANNEL_NAME
        - https://www.youtube.com/@CHANNEL_HANDLE
        """
        if not url:
            return None

        parsed = urlparse(url)

        if parsed.netloc in ["www.youtube.com", "youtube.com"]:
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) >= 2:
                if path_parts[0] == "channel":
                    # Direct channel ID: /channel/UC...
                    return path_parts[1]
                # For custom URLs and handles, we can't extract channel ID
                # without additional API calls

        return None

    @staticmethod
    def parse_action(title: str) -> Tuple[str, str]:
        """
        Parse action type and clean title from Takeout title.

        Returns (action, clean_title)
        """
        title = title.strip()

        # Extract action prefix
        if title.startswith("Watched "):
            return ("Watched", title[8:])
        elif title.startswith("Viewed "):
            return ("Viewed", title[7:])
        else:
            return ("Unknown", title)

    @classmethod
    def parse_watch_history_file(
        cls, file_path: Path
    ) -> Generator[WatchHistoryEntry, None, None]:
        """
        Parse Google Takeout watch history JSON file.

        Yields WatchHistoryEntry objects for each valid entry.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            raise ValidationError(
                message=f"Failed to parse JSON file {file_path}: {e}",
                field_name="file_path",
                invalid_value=str(file_path),
            ) from e

        if not isinstance(data, list):
            raise ValidationError(
                message="Expected JSON array at root level",
                field_name="data",
                invalid_value=type(data).__name__,
            )

        for i, entry in enumerate(data):
            try:
                # Skip non-YouTube entries
                if entry.get("header") != "YouTube":
                    continue

                # Parse basic fields
                title = entry.get("title", "")
                title_url = entry.get("titleUrl", "")
                time_str = entry.get("time", "")

                if not title or not title_url or not time_str:
                    continue

                # Parse timestamp
                try:
                    watched_at = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                except ValueError:
                    continue

                # Parse action and clean title
                action, clean_title = cls.parse_action(title)

                # Extract video ID
                video_id = cls.extract_video_id(title_url)

                # Skip non-video entries (like community posts)
                if not video_id:
                    continue

                # Parse channel info from subtitles
                channel_name = None
                channel_id = None
                channel_url = None

                subtitles = entry.get("subtitles", [])
                if subtitles and isinstance(subtitles, list) and len(subtitles) > 0:
                    subtitle = subtitles[0]
                    channel_name = subtitle.get("name")
                    channel_url = subtitle.get("url")
                    if channel_url:
                        channel_id = cls.extract_channel_id(channel_url)

                # Create entry
                watch_entry = WatchHistoryEntry(
                    video_id=video_id,
                    video_url=title_url,
                    title=clean_title,
                    action=action,
                    channel_name=channel_name,
                    channel_id=channel_id,
                    channel_url=channel_url,
                    watched_at=watched_at,
                    products=entry.get("products", []),
                    activity_controls=entry.get("activityControls", []),
                )

                yield watch_entry

            except Exception as e:
                # Log error but continue processing
                print(f"Warning: Failed to parse entry {i}: {e}")
                continue

    @classmethod
    def count_entries(cls, file_path: Path) -> Dict[str, int]:
        """
        Count different types of entries in watch history file.

        Returns dictionary with counts.
        """
        counts = {
            "total": 0,
            "youtube": 0,
            "videos": 0,
            "community_posts": 0,
            "other": 0,
            "watched": 0,
            "viewed": 0,
        }

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading file: {e}")
            return counts

        if not isinstance(data, list):
            return counts

        for entry in data:
            counts["total"] += 1

            if entry.get("header") == "YouTube":
                counts["youtube"] += 1

                title = entry.get("title", "")
                title_url = entry.get("titleUrl", "")

                if cls.extract_video_id(title_url):
                    counts["videos"] += 1

                    if title.startswith("Watched "):
                        counts["watched"] += 1
                    elif title.startswith("Viewed "):
                        counts["viewed"] += 1

                elif "/post/" in title_url:
                    counts["community_posts"] += 1
                else:
                    counts["other"] += 1

        return counts
