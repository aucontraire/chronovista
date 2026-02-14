"""
Data transformation utilities for sync commands.

Provides reusable transformers for converting YouTube API responses
to chronovista database models.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from chronovista.models.api_responses import (
    YouTubeChannelResponse,
    YouTubePlaylistItemResponse,
    YouTubePlaylistResponse,
    YouTubeVideoCategoryResponse,
    YouTubeVideoResponse,
)
from chronovista.models.channel import ChannelCreate
from chronovista.models.enums import AvailabilityStatus, LanguageCode, PrivacyStatus, TopicType
from chronovista.models.playlist import PlaylistCreate
from chronovista.models.playlist_membership import PlaylistMembershipCreate
from chronovista.models.topic_category import TopicCategoryCreate
from chronovista.models.video import VideoCreate


class DataTransformers:
    """
    Static utility class for data transformations.

    Provides methods to convert YouTube API response models to
    chronovista Pydantic create models for database insertion.
    """

    @staticmethod
    def parse_duration(duration_str: Optional[str]) -> int:
        """
        Parse ISO 8601 duration string to seconds.

        Parameters
        ----------
        duration_str : Optional[str]
            Duration in ISO 8601 format (e.g., "PT1H2M3S", "PT5M", "PT30S").

        Returns
        -------
        int
            Duration in seconds.

        Examples
        --------
        >>> DataTransformers.parse_duration("PT1H2M3S")
        3723
        >>> DataTransformers.parse_duration("PT5M30S")
        330
        >>> DataTransformers.parse_duration(None)
        0
        """
        if not duration_str or not duration_str.startswith("PT"):
            return 0

        pattern = r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
        match = re.match(pattern, duration_str)

        if not match:
            return 0

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        return hours * 3600 + minutes * 60 + seconds

    @staticmethod
    def cast_language_code(language_str: Optional[str]) -> Optional[LanguageCode]:
        """
        Safely cast a language string to LanguageCode enum.

        Parameters
        ----------
        language_str : Optional[str]
            Language code string (e.g., "en", "es", "fr").

        Returns
        -------
        Optional[LanguageCode]
            LanguageCode enum value if valid, None otherwise.

        Examples
        --------
        >>> DataTransformers.cast_language_code("en")
        <LanguageCode.EN: 'en'>
        >>> DataTransformers.cast_language_code("invalid")
        None
        """
        if not language_str:
            return None

        try:
            return LanguageCode(language_str)
        except ValueError:
            return None

    @staticmethod
    def extract_topic_category_create(
        category: YouTubeVideoCategoryResponse,
    ) -> TopicCategoryCreate:
        """
        Convert YouTube video category to TopicCategoryCreate.

        Parameters
        ----------
        category : YouTubeVideoCategoryResponse
            YouTube API video category response.

        Returns
        -------
        TopicCategoryCreate
            Pydantic model for database insertion.
        """
        snippet = category.snippet
        category_name = snippet.title if snippet else ""

        return TopicCategoryCreate(
            topic_id=category.id,
            category_name=category_name,
            parent_topic_id=None,  # YouTube categories don't have hierarchy
            topic_type=TopicType.YOUTUBE,
        )

    @staticmethod
    def extract_channel_create(
        channel: YouTubeChannelResponse,
    ) -> ChannelCreate:
        """
        Convert YouTube channel response to ChannelCreate.

        Parameters
        ----------
        channel : YouTubeChannelResponse
            YouTube API channel response.

        Returns
        -------
        ChannelCreate
            Pydantic model for database insertion.
        """
        snippet = channel.snippet
        statistics = channel.statistics

        # Extract thumbnail URL
        thumbnail_url: Optional[str] = None
        if snippet and snippet.thumbnails:
            high_thumb = snippet.thumbnails.get("high")
            if high_thumb:
                thumbnail_url = high_thumb.url

        # Extract language code
        default_language = DataTransformers.cast_language_code(
            snippet.default_language if snippet else None
        )

        return ChannelCreate(
            channel_id=channel.id,
            title=snippet.title if snippet else "",
            description=snippet.description if snippet else "",
            subscriber_count=statistics.subscriber_count if statistics else None,
            video_count=statistics.video_count if statistics else None,
            default_language=default_language,
            country=snippet.country if snippet else None,
            thumbnail_url=thumbnail_url,
        )

    @staticmethod
    def extract_video_create(
        video: YouTubeVideoResponse,
        channel_id: Optional[str] = None,
    ) -> VideoCreate:
        """
        Convert YouTube video response to VideoCreate.

        Parameters
        ----------
        video : YouTubeVideoResponse
            YouTube API video response.
        channel_id : Optional[str]
            Override channel ID (useful when channel is known).

        Returns
        -------
        VideoCreate
            Pydantic model for database insertion.
        """
        snippet = video.snippet
        content_details = video.content_details
        status = video.status

        # Extract duration
        duration_str = content_details.duration if content_details else None
        duration = DataTransformers.parse_duration(duration_str)

        # Extract language code
        default_language = DataTransformers.cast_language_code(
            snippet.default_language if snippet else None
        )

        # Handle upload date - required field, default to epoch if missing
        upload_date = snippet.published_at if snippet else None
        if upload_date is None:
            upload_date = datetime.now(timezone.utc)

        # T050: Channel ID from snippet or override, with NULL support
        # If we have a valid channel_id (override or from snippet), use it
        # Otherwise, set channel_id=None and preserve channel_name_hint for future resolution
        effective_channel_id = channel_id or (snippet.channel_id if snippet else None)
        channel_name_hint = None
        if effective_channel_id is None and snippet and snippet.channel_title:
            channel_name_hint = snippet.channel_title

        # Handle made_for_kids fields - ensure bool, not None
        made_for_kids = status.made_for_kids if status and status.made_for_kids is not None else False
        self_declared = (
            status.self_declared_made_for_kids
            if status and status.self_declared_made_for_kids is not None
            else False
        )

        return VideoCreate(
            video_id=video.id,
            channel_id=effective_channel_id,
            channel_name_hint=channel_name_hint,
            title=snippet.title if snippet else "",
            description=snippet.description if snippet else None,
            upload_date=upload_date,
            duration=duration,
            default_language=default_language,
            category_id=snippet.category_id if snippet else None,
            made_for_kids=made_for_kids,
            self_declared_made_for_kids=self_declared,
            availability_status=AvailabilityStatus.AVAILABLE,
        )

    @staticmethod
    def extract_topic_ids(channel_or_video: YouTubeChannelResponse | YouTubeVideoResponse) -> list[str]:
        """
        Extract topic IDs from a channel or video response.

        Parameters
        ----------
        channel_or_video : YouTubeChannelResponse | YouTubeVideoResponse
            YouTube API response with topic_details.

        Returns
        -------
        list[str]
            List of topic IDs, empty if none found.
        """
        topic_details = channel_or_video.topic_details
        if not topic_details:
            return []

        return topic_details.topic_ids or []

    @staticmethod
    def extract_playlist_create(
        playlist: YouTubePlaylistResponse,
    ) -> PlaylistCreate:
        """
        Convert YouTube playlist response to PlaylistCreate.

        Parameters
        ----------
        playlist : YouTubePlaylistResponse
            YouTube API playlist response.

        Returns
        -------
        PlaylistCreate
            Pydantic model for database insertion.
        """
        snippet = playlist.snippet
        content_details = playlist.content_details
        status = playlist.status

        # Extract language code
        default_language = DataTransformers.cast_language_code(
            snippet.default_language if snippet else None
        )

        # Extract privacy status
        privacy_status = PrivacyStatus.PRIVATE
        if status and status.privacy_status:
            try:
                privacy_status = PrivacyStatus(status.privacy_status)
            except ValueError:
                privacy_status = PrivacyStatus.PRIVATE

        # Extract video count
        video_count = content_details.item_count if content_details else 0

        # Extract published_at
        published_at = snippet.published_at if snippet else None

        return PlaylistCreate(
            playlist_id=playlist.id,
            title=snippet.title if snippet else "",
            description=snippet.description if snippet else None,
            default_language=default_language,
            privacy_status=privacy_status,
            channel_id=snippet.channel_id if snippet else None,
            video_count=video_count,
            published_at=published_at,
        )

    @staticmethod
    def extract_playlist_membership_create(
        item: YouTubePlaylistItemResponse,
    ) -> Optional[PlaylistMembershipCreate]:
        """
        Convert YouTube playlist item response to PlaylistMembershipCreate.

        Parameters
        ----------
        item : YouTubePlaylistItemResponse
            YouTube API playlist item response.

        Returns
        -------
        Optional[PlaylistMembershipCreate]
            Pydantic model for database insertion, or None if required data is missing.
        """
        snippet = item.snippet
        content_details = item.content_details

        # Return None if snippet or content_details missing
        if not snippet or not content_details:
            return None

        # Extract video_id from content_details
        video_id = content_details.video_id
        if not video_id:
            return None

        # Extract playlist_id from snippet
        playlist_id = snippet.playlist_id

        # Extract position from snippet
        position = snippet.position

        # Extract added_at from snippet.published_at
        added_at = snippet.published_at

        return PlaylistMembershipCreate(
            playlist_id=playlist_id,
            video_id=video_id,
            position=position,
            added_at=added_at,
        )
