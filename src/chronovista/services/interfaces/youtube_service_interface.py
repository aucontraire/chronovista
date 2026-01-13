"""
Abstract Base Class for YouTube Data API services.

This interface defines the contract for YouTube API access, enabling:
- Testability via mock implementations
- Swappable implementations (e.g., caching layer, offline mode)
- Clear API boundaries for IDE support and type checking
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ...models.api_responses import (
    YouTubeCaptionResponse,
    YouTubeChannelResponse,
    YouTubePlaylistItemResponse,
    YouTubePlaylistResponse,
    YouTubeSearchResponse,
    YouTubeSubscriptionResponse,
    YouTubeVideoCategoryResponse,
    YouTubeVideoResponse,
)
from ...models.youtube_types import ChannelId, PlaylistId, VideoId


class YouTubeServiceInterface(ABC):
    """
    Abstract interface for YouTube Data API access.

    Implementations of this interface provide methods for fetching YouTube data
    using the authenticated API client. All async methods follow the same
    pattern of returning strongly-typed Pydantic models.

    Implementations should handle:
    - Retry logic with exponential backoff for transient failures
    - Quota exceeded detection and reporting
    - Proper error handling and logging

    Examples
    --------
    >>> class MockYouTubeService(YouTubeServiceInterface):
    ...     async def get_my_channel(self) -> Optional[YouTubeChannelResponse]:
    ...         return None  # Mock implementation
    """

    # -------------------------------------------------------------------------
    # Channel Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_my_channel(self) -> Optional[YouTubeChannelResponse]:
        """
        Get information about the authenticated user's channel.

        Returns
        -------
        Optional[YouTubeChannelResponse]
            Channel information including id, title, description, statistics.
            Returns None if no channel found.

        Raises
        ------
        YouTubeAPIError
            If no channel is found for the authenticated user.
        """
        pass

    @abstractmethod
    async def get_channel_details(
        self, channel_id: ChannelId | list[ChannelId]
    ) -> list[YouTubeChannelResponse]:
        """
        Get detailed information about one or more channels.

        Parameters
        ----------
        channel_id : ChannelId | list[ChannelId]
            The channel ID(s) to fetch details for.

        Returns
        -------
        list[YouTubeChannelResponse]
            List containing channel information.

        Raises
        ------
        YouTubeAPIError
            If no channels are found.
        """
        pass

    @abstractmethod
    async def get_channel_videos(
        self, channel_id: ChannelId, max_results: int = 50
    ) -> list[YouTubePlaylistItemResponse]:
        """
        Get videos from a specific channel.

        Parameters
        ----------
        channel_id : ChannelId
            The channel ID to fetch videos from.
        max_results : int
            Maximum number of videos to return (default 50).

        Returns
        -------
        list[YouTubePlaylistItemResponse]
            List of playlist item information representing channel videos.

        Raises
        ------
        YouTubeAPIError
            If the channel is not found.
        """
        pass

    # -------------------------------------------------------------------------
    # Video Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_video_details(
        self, video_ids: list[VideoId]
    ) -> list[YouTubeVideoResponse]:
        """
        Get detailed information about specific videos.

        Parameters
        ----------
        video_ids : list[VideoId]
            List of video IDs to fetch details for (max 50).

        Returns
        -------
        list[YouTubeVideoResponse]
            List of detailed video information as typed models.

        Raises
        ------
        QuotaExceededException
            If YouTube API quota is exceeded.
        ValidationError
            If more than 50 video IDs are provided.
        """
        pass

    @abstractmethod
    async def fetch_videos_batched(
        self, video_ids: List[str], batch_size: int = 50
    ) -> tuple[list[YouTubeVideoResponse], set[str]]:
        """
        Fetch video details in batches, handling pagination for large lists.

        Parameters
        ----------
        video_ids : List[str]
            List of video IDs to fetch (can be any size).
        batch_size : int, optional
            Number of videos per batch (default 50, max 50).

        Returns
        -------
        tuple[list[YouTubeVideoResponse], set[str]]
            Tuple of (list of video details, set of video IDs not found).
            Videos not returned by API are considered deleted/private.

        Raises
        ------
        QuotaExceededException
            If YouTube API quota is exceeded.
        """
        pass

    @abstractmethod
    async def get_video_captions(
        self, video_id: VideoId
    ) -> list[YouTubeCaptionResponse]:
        """
        Get available captions/transcripts for a video.

        Parameters
        ----------
        video_id : VideoId
            The video ID to get captions for.

        Returns
        -------
        list[YouTubeCaptionResponse]
            List of available caption tracks as typed models.
        """
        pass

    @abstractmethod
    async def download_caption(
        self, caption_id: str, fmt: str = "srt"
    ) -> Optional[str]:
        """
        Download caption content using YouTube Data API v3.

        Parameters
        ----------
        caption_id : str
            The caption track ID to download.
        fmt : str
            Format to download (srt, vtt, etc.). Default is 'srt'.

        Returns
        -------
        Optional[str]
            Caption content as string, or None if download failed.
        """
        pass

    @abstractmethod
    async def get_video_categories(
        self, region_code: str = "US"
    ) -> list[YouTubeVideoCategoryResponse]:
        """
        Get YouTube video categories for a specific region.

        Parameters
        ----------
        region_code : str
            Two-character ISO 3166-1 country code (default "US").

        Returns
        -------
        list[YouTubeVideoCategoryResponse]
            List of video category information as typed models.

        Raises
        ------
        ValidationError
            If region_code is not a valid 2-character country code.
        YouTubeAPIError
            If no categories found for region or API request fails.
        """
        pass

    # -------------------------------------------------------------------------
    # Playlist Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_my_playlists(
        self, max_results: int = 50, fetch_all: bool = True
    ) -> list[YouTubePlaylistResponse]:
        """
        Get playlists owned by the authenticated user.

        Supports pagination to fetch all playlists. The YouTube API returns
        a maximum of 50 items per page, so this method automatically paginates
        through all results when fetch_all is True.

        Parameters
        ----------
        max_results : int
            Maximum number of playlists to return (default 50).
            When fetch_all is True, this is the total limit across all pages.
            When fetch_all is False, this is passed directly to the API (max 50).
        fetch_all : bool
            If True (default), automatically paginate through all results up to
            max_results. If False, make a single API call with max_results (max 50).

        Returns
        -------
        list[YouTubePlaylistResponse]
            List of playlist information as typed models.
        """
        pass

    @abstractmethod
    async def get_playlist_videos(
        self, playlist_id: PlaylistId, max_results: int = 50, fetch_all: bool = True
    ) -> list[YouTubePlaylistItemResponse]:
        """
        Get videos from a specific playlist.

        Supports pagination to fetch all videos. The YouTube API returns
        a maximum of 50 items per page, so this method automatically paginates
        through all results when fetch_all is True.

        Parameters
        ----------
        playlist_id : PlaylistId
            The playlist ID to fetch videos from.
        max_results : int
            Maximum number of videos to return (default 50).
            When fetch_all is True, this is the total limit across all pages.
            When fetch_all is False, this is passed directly to the API (max 50).
        fetch_all : bool
            If True (default), automatically paginate through all results up to
            max_results. If False, make a single API call with max_results (max 50).

        Returns
        -------
        list[YouTubePlaylistItemResponse]
            List of playlist item information as typed models.
        """
        pass

    @abstractmethod
    async def get_playlist_details(
        self, playlist_ids: list[str]
    ) -> list[YouTubePlaylistResponse]:
        """
        Get detailed information about specific playlists.

        Parameters
        ----------
        playlist_ids : list[str]
            List of playlist IDs to fetch details for (max 50).

        Returns
        -------
        list[YouTubePlaylistResponse]
            List of detailed playlist information as typed models.

        Raises
        ------
        QuotaExceededException
            If YouTube API quota is exceeded.
        ValidationError
            If more than 50 playlist IDs are provided.
        """
        pass

    @abstractmethod
    async def fetch_playlists_batched(
        self, playlist_ids: List[str], batch_size: int = 50
    ) -> tuple[list[YouTubePlaylistResponse], set[str]]:
        """
        Fetch playlist details in batches, handling pagination for large lists.

        Parameters
        ----------
        playlist_ids : List[str]
            List of playlist IDs to fetch (can be any size).
        batch_size : int, optional
            Number of playlists per batch (default 50, max 50).

        Returns
        -------
        tuple[list[YouTubePlaylistResponse], set[str]]
            Tuple of (list of playlist details, set of playlist IDs not found).
        """
        pass

    @abstractmethod
    async def get_my_watch_later_videos(
        self, max_results: int = 50
    ) -> list[YouTubePlaylistItemResponse]:
        """
        Get videos in the authenticated user's Watch Later playlist.

        Parameters
        ----------
        max_results : int
            Maximum number of videos to return (default 50).

        Returns
        -------
        list[YouTubePlaylistItemResponse]
            List of Watch Later playlist item information as typed models.
        """
        pass

    @abstractmethod
    async def check_video_in_playlist(
        self, video_id: VideoId, playlist_id: PlaylistId
    ) -> bool:
        """
        Check if a specific video exists in a playlist.

        Parameters
        ----------
        video_id : VideoId
            The video ID to check for.
        playlist_id : PlaylistId
            The playlist ID to check in.

        Returns
        -------
        bool
            True if video is in playlist, False otherwise.
        """
        pass

    @abstractmethod
    async def get_user_playlists_for_video(self, video_id: VideoId) -> list[str]:
        """
        Get all user playlists that contain a specific video.

        Parameters
        ----------
        video_id : VideoId
            The video ID to search for.

        Returns
        -------
        list[str]
            List of playlist IDs that contain the video.
        """
        pass

    # -------------------------------------------------------------------------
    # User Activity Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_liked_videos(
        self, max_results: Optional[int] = None
    ) -> list[YouTubeVideoResponse]:
        """
        Get videos that the authenticated user has liked.

        Supports pagination to fetch all liked videos.

        Parameters
        ----------
        max_results : Optional[int]
            Maximum number of liked videos to return. If None (default),
            fetches ALL liked videos by paginating through the entire playlist.

        Returns
        -------
        list[YouTubeVideoResponse]
            List of liked videos with details as typed models.
        """
        pass

    @abstractmethod
    async def get_subscription_channels(
        self, max_results: int = 50
    ) -> list[YouTubeSubscriptionResponse]:
        """
        Get channels that the authenticated user is subscribed to.

        Parameters
        ----------
        max_results : int
            Maximum number of subscriptions to return (default 50).

        Returns
        -------
        list[YouTubeSubscriptionResponse]
            List of subscribed channels as typed models.
        """
        pass

    # -------------------------------------------------------------------------
    # Search Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def search_my_videos(
        self, query: str, max_results: int = 25
    ) -> list[YouTubeSearchResponse]:
        """
        Search through the authenticated user's videos.

        Parameters
        ----------
        query : str
            Search query string.
        max_results : int
            Maximum number of results to return (default 25).

        Returns
        -------
        list[YouTubeSearchResponse]
            List of matching search results as typed models.
        """
        pass

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    @abstractmethod
    def check_credentials(self) -> bool:
        """
        Check if YouTube API credentials are configured and valid.

        Returns
        -------
        bool
            True if credentials are valid and API is accessible.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Clean up resources."""
        pass
