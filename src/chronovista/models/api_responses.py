"""
Pydantic models for YouTube Data API v3 responses.

These models replace Dict[str, Any] return types in YouTubeService with strongly-typed
Pydantic models that provide runtime validation, serialization, and type safety.

The models follow YouTube API response structures with camelCase to snake_case conversion
handled via Pydantic's alias_generator.

References:
- YouTube Data API v3 Reference: https://developers.google.com/youtube/v3/docs
- FR-005, FR-006, FR-007: Type-safety foundation requirements
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

logger = logging.getLogger(__name__)


# =============================================================================
# Base Configuration
# =============================================================================


class BaseYouTubeModel(BaseModel):
    """
    Base model for all YouTube API response models.

    Configures:
    - populate_by_name: Allow both camelCase (API) and snake_case (Python)
    - alias_generator: Auto-convert snake_case fields to camelCase for API
    - extra='ignore': Ignore unexpected fields from API responses
    """

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        extra="ignore",
    )


# =============================================================================
# Supporting/Utility Models
# =============================================================================


class Thumbnail(BaseYouTubeModel):
    """
    YouTube thumbnail representation.

    YouTube provides different thumbnail sizes: default, medium, high, standard, maxres.
    """

    url: str = Field(default="", description="Thumbnail URL")
    width: int = Field(default=0, description="Thumbnail width in pixels")
    height: int = Field(default=0, description="Thumbnail height in pixels")


class LocalizedString(BaseYouTubeModel):
    """
    Localized text for a specific language.

    Used in localized versions of titles and descriptions.
    """

    title: str = Field(default="", description="Localized title")
    description: str = Field(default="", description="Localized description")


class ResourceId(BaseYouTubeModel):
    """
    Identifies a YouTube resource (video, channel, playlist).

    Used in playlistItems, search results, etc. to identify the referenced resource.
    """

    kind: str = Field(default="", description="Resource type (e.g., youtube#video)")
    video_id: Optional[str] = Field(
        default=None, alias="videoId", description="Video ID if resource is a video"
    )
    channel_id: Optional[str] = Field(
        default=None, alias="channelId", description="Channel ID if resource is a channel"
    )
    playlist_id: Optional[str] = Field(
        default=None,
        alias="playlistId",
        description="Playlist ID if resource is a playlist",
    )


class RegionRestriction(BaseYouTubeModel):
    """
    Region restriction information for videos.

    Either 'allowed' or 'blocked' will be populated, not both.
    """

    allowed: list[str] = Field(
        default_factory=list,
        description="List of region codes where video is viewable",
    )
    blocked: list[str] = Field(
        default_factory=list,
        description="List of region codes where video is blocked",
    )


class TopicDetails(BaseYouTubeModel):
    """
    Topic classification information from YouTube.

    Contains topic IDs from Freebase/Knowledge Graph.
    """

    topic_ids: list[str] = Field(
        default_factory=list,
        alias="topicIds",
        description="Freebase topic IDs (deprecated)",
    )
    relevant_topic_ids: list[str] = Field(
        default_factory=list,
        alias="relevantTopicIds",
        description="Wikipedia URLs for relevant topics",
    )
    topic_categories: list[str] = Field(
        default_factory=list,
        alias="topicCategories",
        description="Wikipedia URLs for topic categories",
    )


class RelatedPlaylists(BaseYouTubeModel):
    """
    Related playlist IDs for a channel.

    Contains IDs for system playlists like uploads, likes, favorites.
    """

    likes: Optional[str] = Field(
        default=None, description="Playlist ID for liked videos"
    )
    uploads: str = Field(default="", description="Playlist ID for channel uploads")
    favorites: Optional[str] = Field(
        default=None, description="Playlist ID for favorited videos (deprecated)"
    )
    watch_history: Optional[str] = Field(
        default=None, alias="watchHistory", description="Playlist ID for watch history"
    )
    watch_later: Optional[str] = Field(
        default=None, alias="watchLater", description="Playlist ID for Watch Later"
    )


# =============================================================================
# Snippet Models
# =============================================================================


class VideoSnippet(BaseYouTubeModel):
    """
    Snippet data for a YouTube video.

    Contains basic metadata like title, description, channel info, and thumbnails.
    """

    published_at: datetime = Field(
        alias="publishedAt", description="Video publish timestamp"
    )
    channel_id: str = Field(alias="channelId", description="ID of the channel")
    title: str = Field(default="", description="Video title")
    description: str = Field(default="", description="Video description")
    thumbnails: dict[str, Thumbnail] = Field(
        default_factory=dict, description="Available thumbnails by size"
    )
    channel_title: str = Field(
        default="", alias="channelTitle", description="Channel name"
    )
    tags: list[str] = Field(default_factory=list, description="Video tags")
    category_id: str = Field(
        default="", alias="categoryId", description="YouTube category ID"
    )
    live_broadcast_content: str = Field(
        default="none",
        alias="liveBroadcastContent",
        description="Live broadcast status (none, live, upcoming)",
    )
    default_language: Optional[str] = Field(
        default=None,
        alias="defaultLanguage",
        description="Default language (BCP-47)",
    )
    default_audio_language: Optional[str] = Field(
        default=None,
        alias="defaultAudioLanguage",
        description="Default audio language (BCP-47)",
    )
    localized: Optional[LocalizedString] = Field(
        default=None, description="Localized title and description"
    )

    @field_validator("thumbnails", mode="before")
    @classmethod
    def parse_thumbnails(cls, v: Any) -> dict[str, Thumbnail]:
        """Parse thumbnail dictionary from API response."""
        if not v:
            return {}
        if isinstance(v, dict):
            result = {}
            for key, thumb_data in v.items():
                if isinstance(thumb_data, dict):
                    result[key] = Thumbnail.model_validate(thumb_data)
                elif isinstance(thumb_data, Thumbnail):
                    result[key] = thumb_data
            return result
        return {}


class ChannelSnippet(BaseYouTubeModel):
    """
    Snippet data for a YouTube channel.

    Contains basic channel metadata.
    """

    title: str = Field(default="", description="Channel name")
    description: str = Field(default="", description="Channel description")
    custom_url: Optional[str] = Field(
        default=None, alias="customUrl", description="Custom channel URL handle"
    )
    published_at: datetime = Field(
        alias="publishedAt", description="Channel creation timestamp"
    )
    thumbnails: dict[str, Thumbnail] = Field(
        default_factory=dict, description="Channel thumbnails"
    )
    default_language: Optional[str] = Field(
        default=None,
        alias="defaultLanguage",
        description="Default language (BCP-47)",
    )
    localized: Optional[LocalizedString] = Field(
        default=None, description="Localized title and description"
    )
    country: Optional[str] = Field(
        default=None, description="Country code (ISO 3166-1)"
    )

    @field_validator("thumbnails", mode="before")
    @classmethod
    def parse_thumbnails(cls, v: Any) -> dict[str, Thumbnail]:
        """Parse thumbnail dictionary from API response."""
        if not v:
            return {}
        if isinstance(v, dict):
            result = {}
            for key, thumb_data in v.items():
                if isinstance(thumb_data, dict):
                    result[key] = Thumbnail.model_validate(thumb_data)
                elif isinstance(thumb_data, Thumbnail):
                    result[key] = thumb_data
            return result
        return {}


class PlaylistSnippet(BaseYouTubeModel):
    """
    Snippet data for a YouTube playlist.

    Contains basic playlist metadata.
    """

    published_at: datetime = Field(
        alias="publishedAt", description="Playlist creation timestamp"
    )
    channel_id: str = Field(alias="channelId", description="ID of the owner channel")
    title: str = Field(default="", description="Playlist title")
    description: str = Field(default="", description="Playlist description")
    thumbnails: dict[str, Thumbnail] = Field(
        default_factory=dict, description="Playlist thumbnails"
    )
    channel_title: str = Field(
        default="", alias="channelTitle", description="Owner channel name"
    )
    default_language: Optional[str] = Field(
        default=None,
        alias="defaultLanguage",
        description="Default language (BCP-47)",
    )
    localized: Optional[LocalizedString] = Field(
        default=None, description="Localized title and description"
    )

    @field_validator("thumbnails", mode="before")
    @classmethod
    def parse_thumbnails(cls, v: Any) -> dict[str, Thumbnail]:
        """Parse thumbnail dictionary from API response."""
        if not v:
            return {}
        if isinstance(v, dict):
            result = {}
            for key, thumb_data in v.items():
                if isinstance(thumb_data, dict):
                    result[key] = Thumbnail.model_validate(thumb_data)
                elif isinstance(thumb_data, Thumbnail):
                    result[key] = thumb_data
            return result
        return {}


class PlaylistItemSnippet(BaseYouTubeModel):
    """
    Snippet data for a playlist item.

    Contains information about a video within a playlist.
    """

    published_at: datetime = Field(
        alias="publishedAt", description="When item was added to playlist"
    )
    channel_id: str = Field(alias="channelId", description="Playlist owner channel ID")
    title: str = Field(default="", description="Video title")
    description: str = Field(default="", description="Video description")
    thumbnails: dict[str, Thumbnail] = Field(
        default_factory=dict, description="Video thumbnails"
    )
    channel_title: str = Field(
        default="", alias="channelTitle", description="Playlist owner channel name"
    )
    playlist_id: str = Field(alias="playlistId", description="ID of the playlist")
    position: int = Field(default=0, description="Position in playlist (0-indexed)")
    resource_id: ResourceId = Field(
        alias="resourceId", description="Identifies the video resource"
    )
    video_owner_channel_title: Optional[str] = Field(
        default=None,
        alias="videoOwnerChannelTitle",
        description="Video owner channel name",
    )
    video_owner_channel_id: Optional[str] = Field(
        default=None,
        alias="videoOwnerChannelId",
        description="Video owner channel ID",
    )

    @field_validator("thumbnails", mode="before")
    @classmethod
    def parse_thumbnails(cls, v: Any) -> dict[str, Thumbnail]:
        """Parse thumbnail dictionary from API response."""
        if not v:
            return {}
        if isinstance(v, dict):
            result = {}
            for key, thumb_data in v.items():
                if isinstance(thumb_data, dict):
                    result[key] = Thumbnail.model_validate(thumb_data)
                elif isinstance(thumb_data, Thumbnail):
                    result[key] = thumb_data
            return result
        return {}


class SearchSnippet(BaseYouTubeModel):
    """
    Snippet data for a search result.

    Contains basic information about a search result (video, channel, or playlist).
    """

    published_at: datetime = Field(
        alias="publishedAt", description="Resource publish timestamp"
    )
    channel_id: str = Field(alias="channelId", description="Channel ID")
    title: str = Field(default="", description="Resource title")
    description: str = Field(default="", description="Resource description")
    thumbnails: dict[str, Thumbnail] = Field(
        default_factory=dict, description="Resource thumbnails"
    )
    channel_title: str = Field(
        default="", alias="channelTitle", description="Channel name"
    )
    live_broadcast_content: str = Field(
        default="none",
        alias="liveBroadcastContent",
        description="Live broadcast status",
    )

    @field_validator("thumbnails", mode="before")
    @classmethod
    def parse_thumbnails(cls, v: Any) -> dict[str, Thumbnail]:
        """Parse thumbnail dictionary from API response."""
        if not v:
            return {}
        if isinstance(v, dict):
            result = {}
            for key, thumb_data in v.items():
                if isinstance(thumb_data, dict):
                    result[key] = Thumbnail.model_validate(thumb_data)
                elif isinstance(thumb_data, Thumbnail):
                    result[key] = thumb_data
            return result
        return {}


class CaptionSnippet(BaseYouTubeModel):
    """
    Snippet data for a caption track.

    Contains information about an available caption/subtitle track.
    """

    video_id: str = Field(alias="videoId", description="ID of the video")
    last_updated: Optional[datetime] = Field(
        default=None, alias="lastUpdated", description="Last update timestamp"
    )
    track_kind: str = Field(
        default="standard",
        alias="trackKind",
        description="Track type (standard, ASR, forced)",
    )
    language: str = Field(default="", description="Language code (BCP-47)")
    name: str = Field(default="", description="Track name/label")
    audio_track_type: str = Field(
        default="unknown",
        alias="audioTrackType",
        description="Audio track type",
    )
    is_cc: bool = Field(
        default=False,
        alias="isCC",
        description="Whether this is a closed caption track",
    )
    is_draft: bool = Field(
        default=False,
        alias="isDraft",
        description="Whether track is still being processed",
    )
    is_auto_synced: bool = Field(
        default=False,
        alias="isAutoSynced",
        description="Whether timing was auto-synced",
    )
    is_easy_reader: bool = Field(
        default=False,
        alias="isEasyReader",
        description="Whether track is simplified for readability",
    )
    is_large: bool = Field(
        default=False,
        alias="isLarge",
        description="Whether track uses large text",
    )
    status: str = Field(
        default="serving",
        description="Caption track status (serving, syncing, failed)",
    )
    failure_reason: Optional[str] = Field(
        default=None,
        alias="failureReason",
        description="Reason for processing failure if any",
    )


class SubscriptionSnippet(BaseYouTubeModel):
    """
    Snippet data for a subscription.

    Contains information about a channel subscription.
    """

    published_at: datetime = Field(
        alias="publishedAt", description="Subscription creation timestamp"
    )
    title: str = Field(default="", description="Subscribed channel title")
    description: str = Field(default="", description="Subscribed channel description")
    resource_id: ResourceId = Field(
        alias="resourceId", description="Identifies the subscribed channel"
    )
    channel_id: str = Field(alias="channelId", description="Subscriber's channel ID")
    thumbnails: dict[str, Thumbnail] = Field(
        default_factory=dict, description="Subscribed channel thumbnails"
    )

    @field_validator("thumbnails", mode="before")
    @classmethod
    def parse_thumbnails(cls, v: Any) -> dict[str, Thumbnail]:
        """Parse thumbnail dictionary from API response."""
        if not v:
            return {}
        if isinstance(v, dict):
            result = {}
            for key, thumb_data in v.items():
                if isinstance(thumb_data, dict):
                    result[key] = Thumbnail.model_validate(thumb_data)
                elif isinstance(thumb_data, Thumbnail):
                    result[key] = thumb_data
            return result
        return {}


class CategorySnippet(BaseYouTubeModel):
    """
    Snippet data for a video category.

    Contains category metadata.
    """

    channel_id: str = Field(
        default="UCBR8-60-B28hp2BmDPdntcQ",
        alias="channelId",
        description="Channel that created the category (always YouTube channel)",
    )
    title: str = Field(default="", description="Category name")
    assignable: bool = Field(
        default=True, description="Whether videos can be assigned to this category"
    )


# =============================================================================
# Statistics Models
# =============================================================================


class VideoStatisticsResponse(BaseYouTubeModel):
    """
    Statistics data for a YouTube video.

    Note: YouTube API returns counts as strings, so we convert to int.
    Some stats may be hidden by the channel owner.
    """

    view_count: int = Field(default=0, alias="viewCount", description="View count")
    like_count: Optional[int] = Field(
        default=None, alias="likeCount", description="Like count (may be hidden)"
    )
    dislike_count: Optional[int] = Field(
        default=None,
        alias="dislikeCount",
        description="Dislike count (deprecated, always 0)",
    )
    favorite_count: int = Field(
        default=0, alias="favoriteCount", description="Favorite count (deprecated)"
    )
    comment_count: Optional[int] = Field(
        default=None, alias="commentCount", description="Comment count (may be hidden)"
    )

    @field_validator(
        "view_count", "like_count", "dislike_count", "favorite_count", "comment_count",
        mode="before"
    )
    @classmethod
    def parse_count(cls, v: Any) -> Optional[int]:
        """Parse count from string or int."""
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return 0
        return 0


class ChannelStatisticsResponse(BaseYouTubeModel):
    """
    Statistics data for a YouTube channel.

    Note: YouTube API returns counts as strings, so we convert to int.
    Subscriber count may be hidden by the channel owner.
    """

    view_count: int = Field(
        default=0, alias="viewCount", description="Total channel view count"
    )
    subscriber_count: Optional[int] = Field(
        default=None,
        alias="subscriberCount",
        description="Subscriber count (may be hidden)",
    )
    hidden_subscriber_count: bool = Field(
        default=False,
        alias="hiddenSubscriberCount",
        description="Whether subscriber count is hidden",
    )
    video_count: int = Field(
        default=0, alias="videoCount", description="Number of public videos"
    )

    @field_validator(
        "view_count", "subscriber_count", "video_count", mode="before"
    )
    @classmethod
    def parse_count(cls, v: Any) -> Optional[int]:
        """Parse count from string or int."""
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return 0
        return 0


# =============================================================================
# ContentDetails Models
# =============================================================================


class VideoContentDetails(BaseYouTubeModel):
    """
    Content details for a YouTube video.

    Contains technical information about the video.
    """

    duration: str = Field(
        default="PT0S", description="Video duration in ISO 8601 format"
    )
    dimension: str = Field(default="2d", description="Video dimension (2d or 3d)")
    definition: str = Field(default="sd", description="Video definition (sd or hd)")
    caption: str = Field(
        default="false", description="Whether captions are available"
    )
    licensed_content: bool = Field(
        default=False,
        alias="licensedContent",
        description="Whether video is licensed content",
    )
    region_restriction: Optional[RegionRestriction] = Field(
        default=None,
        alias="regionRestriction",
        description="Region restrictions for the video",
    )
    content_rating: Optional[dict[str, Any]] = Field(
        default=None,
        alias="contentRating",
        description="Content ratings from various systems",
    )
    projection: str = Field(
        default="rectangular", description="Video projection (rectangular or 360)"
    )


class ChannelContentDetails(BaseYouTubeModel):
    """
    Content details for a YouTube channel.

    Contains related playlist IDs.
    """

    related_playlists: RelatedPlaylists = Field(
        alias="relatedPlaylists", description="Related system playlists"
    )


class PlaylistContentDetails(BaseYouTubeModel):
    """
    Content details for a YouTube playlist.

    Contains item count information.
    """

    item_count: int = Field(
        default=0, alias="itemCount", description="Number of items in playlist"
    )


class PlaylistItemContentDetails(BaseYouTubeModel):
    """
    Content details for a playlist item.

    Contains video ID and availability information.
    """

    video_id: str = Field(alias="videoId", description="ID of the video")
    start_at: Optional[str] = Field(
        default=None, alias="startAt", description="Video start time (ISO 8601)"
    )
    end_at: Optional[str] = Field(
        default=None, alias="endAt", description="Video end time (ISO 8601)"
    )
    note: Optional[str] = Field(default=None, description="User note for the item")
    video_published_at: Optional[datetime] = Field(
        default=None,
        alias="videoPublishedAt",
        description="When the video was published",
    )


# =============================================================================
# Status Models
# =============================================================================


class VideoStatus(BaseYouTubeModel):
    """
    Status information for a YouTube video.

    Contains visibility and licensing information.
    """

    upload_status: str = Field(
        default="processed",
        alias="uploadStatus",
        description="Upload status (processed, uploaded, etc.)",
    )
    failure_reason: Optional[str] = Field(
        default=None,
        alias="failureReason",
        description="Reason for upload failure if any",
    )
    rejection_reason: Optional[str] = Field(
        default=None,
        alias="rejectionReason",
        description="Reason for video rejection if any",
    )
    privacy_status: str = Field(
        default="public",
        alias="privacyStatus",
        description="Privacy status (public, unlisted, private)",
    )
    publish_at: Optional[datetime] = Field(
        default=None,
        alias="publishAt",
        description="Scheduled publish time",
    )
    license: str = Field(
        default="youtube",
        description="Video license (youtube or creativeCommon)",
    )
    embeddable: bool = Field(default=True, description="Whether video is embeddable")
    public_stats_viewable: bool = Field(
        default=True,
        alias="publicStatsViewable",
        description="Whether stats are publicly visible",
    )
    made_for_kids: bool = Field(
        default=False,
        alias="madeForKids",
        description="Whether video is made for kids",
    )
    self_declared_made_for_kids: Optional[bool] = Field(
        default=None,
        alias="selfDeclaredMadeForKids",
        description="Creator's made for kids declaration",
    )


class PlaylistStatus(BaseYouTubeModel):
    """
    Status information for a YouTube playlist.

    Contains visibility information.
    """

    privacy_status: str = Field(
        default="public",
        alias="privacyStatus",
        description="Privacy status (public, unlisted, private)",
    )


class ChannelStatus(BaseYouTubeModel):
    """
    Status information for a YouTube channel.

    Contains visibility and feature availability.
    """

    privacy_status: str = Field(
        default="public",
        alias="privacyStatus",
        description="Privacy status (public, unlisted, private)",
    )
    is_linked: bool = Field(
        default=True,
        alias="isLinked",
        description="Whether channel is linked to a Google Account",
    )
    long_uploads_status: str = Field(
        default="allowed",
        alias="longUploadsStatus",
        description="Whether long uploads are allowed",
    )
    made_for_kids: Optional[bool] = Field(
        default=None,
        alias="madeForKids",
        description="Whether channel is made for kids",
    )
    self_declared_made_for_kids: Optional[bool] = Field(
        default=None,
        alias="selfDeclaredMadeForKids",
        description="Creator's made for kids declaration",
    )


# =============================================================================
# Root Response Models
# =============================================================================


class YouTubeVideoResponse(BaseYouTubeModel):
    """
    YouTube video response from videos.list API.

    Represents a single video item from the YouTube Data API.
    """

    kind: str = Field(default="youtube#video", description="Resource type")
    etag: str = Field(default="", description="ETag for caching")
    id: str = Field(description="Video ID")
    snippet: Optional[VideoSnippet] = Field(
        default=None, description="Basic video metadata"
    )
    content_details: Optional[VideoContentDetails] = Field(
        default=None, alias="contentDetails", description="Technical video details"
    )
    statistics: Optional[VideoStatisticsResponse] = Field(
        default=None, description="Video statistics"
    )
    status: Optional[VideoStatus] = Field(
        default=None, description="Video status information"
    )
    topic_details: Optional[TopicDetails] = Field(
        default=None, alias="topicDetails", description="Topic classification"
    )
    localizations: Optional[dict[str, LocalizedString]] = Field(
        default=None, description="Localized versions"
    )

    @field_validator("localizations", mode="before")
    @classmethod
    def parse_localizations(cls, v: Any) -> Optional[dict[str, LocalizedString]]:
        """Parse localizations dictionary from API response."""
        if not v:
            return None
        if isinstance(v, dict):
            result = {}
            for key, loc_data in v.items():
                if isinstance(loc_data, dict):
                    result[key] = LocalizedString.model_validate(loc_data)
                elif isinstance(loc_data, LocalizedString):
                    result[key] = loc_data
            return result
        return None


class YouTubeChannelResponse(BaseYouTubeModel):
    """
    YouTube channel response from channels.list API.

    Represents a single channel item from the YouTube Data API.
    """

    kind: str = Field(default="youtube#channel", description="Resource type")
    etag: str = Field(default="", description="ETag for caching")
    id: str = Field(description="Channel ID")
    snippet: Optional[ChannelSnippet] = Field(
        default=None, description="Basic channel metadata"
    )
    content_details: Optional[ChannelContentDetails] = Field(
        default=None, alias="contentDetails", description="Related playlists"
    )
    statistics: Optional[ChannelStatisticsResponse] = Field(
        default=None, description="Channel statistics"
    )
    status: Optional[ChannelStatus] = Field(
        default=None, description="Channel status information"
    )
    topic_details: Optional[TopicDetails] = Field(
        default=None, alias="topicDetails", description="Topic classification"
    )
    branding_settings: Optional[dict[str, Any]] = Field(
        default=None, alias="brandingSettings", description="Branding settings"
    )


class YouTubePlaylistResponse(BaseYouTubeModel):
    """
    YouTube playlist response from playlists.list API.

    Represents a single playlist item from the YouTube Data API.
    """

    kind: str = Field(default="youtube#playlist", description="Resource type")
    etag: str = Field(default="", description="ETag for caching")
    id: str = Field(description="Playlist ID")
    snippet: Optional[PlaylistSnippet] = Field(
        default=None, description="Basic playlist metadata"
    )
    content_details: Optional[PlaylistContentDetails] = Field(
        default=None, alias="contentDetails", description="Item count"
    )
    status: Optional[PlaylistStatus] = Field(
        default=None, description="Playlist status information"
    )
    localizations: Optional[dict[str, LocalizedString]] = Field(
        default=None, description="Localized versions"
    )

    @field_validator("localizations", mode="before")
    @classmethod
    def parse_localizations(cls, v: Any) -> Optional[dict[str, LocalizedString]]:
        """Parse localizations dictionary from API response."""
        if not v:
            return None
        if isinstance(v, dict):
            result = {}
            for key, loc_data in v.items():
                if isinstance(loc_data, dict):
                    result[key] = LocalizedString.model_validate(loc_data)
                elif isinstance(loc_data, LocalizedString):
                    result[key] = loc_data
            return result
        return None


class YouTubePlaylistItemResponse(BaseYouTubeModel):
    """
    YouTube playlist item response from playlistItems.list API.

    Represents a single playlist item from the YouTube Data API.
    """

    kind: str = Field(default="youtube#playlistItem", description="Resource type")
    etag: str = Field(default="", description="ETag for caching")
    id: str = Field(description="Playlist item ID")
    snippet: Optional[PlaylistItemSnippet] = Field(
        default=None, description="Playlist item metadata"
    )
    content_details: Optional[PlaylistItemContentDetails] = Field(
        default=None, alias="contentDetails", description="Video ID and timing"
    )
    status: Optional[PlaylistStatus] = Field(
        default=None, description="Item status information"
    )


class YouTubeSearchResponse(BaseYouTubeModel):
    """
    YouTube search result response from search.list API.

    Represents a single search result from the YouTube Data API.
    """

    kind: str = Field(default="youtube#searchResult", description="Resource type")
    etag: str = Field(default="", description="ETag for caching")
    id: ResourceId = Field(description="Identifies the result resource")
    snippet: Optional[SearchSnippet] = Field(
        default=None, description="Search result metadata"
    )


class YouTubeCaptionResponse(BaseYouTubeModel):
    """
    YouTube caption response from captions.list API.

    Represents a single caption track from the YouTube Data API.
    """

    kind: str = Field(default="youtube#caption", description="Resource type")
    etag: str = Field(default="", description="ETag for caching")
    id: str = Field(description="Caption track ID")
    snippet: Optional[CaptionSnippet] = Field(
        default=None, description="Caption track metadata"
    )


class YouTubeSubscriptionResponse(BaseYouTubeModel):
    """
    YouTube subscription response from subscriptions.list API.

    Represents a single subscription from the YouTube Data API.
    """

    kind: str = Field(default="youtube#subscription", description="Resource type")
    etag: str = Field(default="", description="ETag for caching")
    id: str = Field(description="Subscription ID")
    snippet: Optional[SubscriptionSnippet] = Field(
        default=None, description="Subscription metadata"
    )
    subscriber_snippet: Optional[dict[str, Any]] = Field(
        default=None,
        alias="subscriberSnippet",
        description="Subscriber channel info",
    )
    content_details: Optional[dict[str, Any]] = Field(
        default=None,
        alias="contentDetails",
        description="Subscription content details",
    )


class YouTubeVideoCategoryResponse(BaseYouTubeModel):
    """
    YouTube video category response from videoCategories.list API.

    Represents a single video category from the YouTube Data API.
    """

    kind: str = Field(default="youtube#videoCategory", description="Resource type")
    etag: str = Field(default="", description="ETag for caching")
    id: str = Field(description="Category ID")
    snippet: Optional[CategorySnippet] = Field(
        default=None, description="Category metadata"
    )


# =============================================================================
# List Response Wrapper (for pagination info if needed)
# =============================================================================


class YouTubeListResponseMetadata(BaseYouTubeModel):
    """
    Metadata from a YouTube API list response.

    Contains pagination and total result information.
    """

    total_results: int = Field(
        default=0, alias="totalResults", description="Total number of results"
    )
    results_per_page: int = Field(
        default=0, alias="resultsPerPage", description="Results per page"
    )


class PageInfo(BaseYouTubeModel):
    """Page information from YouTube API response."""

    total_results: int = Field(
        default=0, alias="totalResults", description="Total results available"
    )
    results_per_page: int = Field(
        default=0, alias="resultsPerPage", description="Results per page"
    )


# =============================================================================
# Module exports
# =============================================================================

__all__ = [
    # Base
    "BaseYouTubeModel",
    # Supporting models
    "Thumbnail",
    "LocalizedString",
    "ResourceId",
    "RegionRestriction",
    "TopicDetails",
    "RelatedPlaylists",
    # Snippet models
    "VideoSnippet",
    "ChannelSnippet",
    "PlaylistSnippet",
    "PlaylistItemSnippet",
    "SearchSnippet",
    "CaptionSnippet",
    "SubscriptionSnippet",
    "CategorySnippet",
    # Statistics models
    "VideoStatisticsResponse",
    "ChannelStatisticsResponse",
    # ContentDetails models
    "VideoContentDetails",
    "ChannelContentDetails",
    "PlaylistContentDetails",
    "PlaylistItemContentDetails",
    # Status models
    "VideoStatus",
    "PlaylistStatus",
    "ChannelStatus",
    # Root response models
    "YouTubeVideoResponse",
    "YouTubeChannelResponse",
    "YouTubePlaylistResponse",
    "YouTubePlaylistItemResponse",
    "YouTubeSearchResponse",
    "YouTubeCaptionResponse",
    "YouTubeSubscriptionResponse",
    "YouTubeVideoCategoryResponse",
    # Metadata models
    "YouTubeListResponseMetadata",
    "PageInfo",
]
