"""
YouTube Data API service for fetching user data.

Provides high-level methods for interacting with YouTube Data API v3,
including channel info, videos, playlists, and watch history.

Implements retry logic with exponential backoff for transient failures
and quota exceeded detection per FR-051 and FR-052.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError

from chronovista.auth import youtube_oauth
from chronovista.exceptions import NetworkError, QuotaExceededException
from chronovista.models.youtube_types import ChannelId, PlaylistId, VideoId

logger = logging.getLogger(__name__)

# Retry configuration for transient failures (FR-052)
MAX_RETRIES = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]  # Exponential backoff: 1s, 2s, 4s

# HTTP status codes
HTTP_FORBIDDEN = 403
HTTP_TOO_MANY_REQUESTS = 429
HTTP_INTERNAL_ERROR = 500
HTTP_BAD_GATEWAY = 502
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_GATEWAY_TIMEOUT = 504

# Retryable HTTP status codes (transient server errors)
RETRYABLE_STATUS_CODES = {
    HTTP_TOO_MANY_REQUESTS,
    HTTP_INTERNAL_ERROR,
    HTTP_BAD_GATEWAY,
    HTTP_SERVICE_UNAVAILABLE,
    HTTP_GATEWAY_TIMEOUT,
}

# Quota exceeded error reasons from YouTube API
QUOTA_EXCEEDED_REASONS = {
    "quotaExceeded",
    "userRateLimitExceeded",
    "rateLimitExceeded",
    "dailyLimitExceeded",
}


class YouTubeService:
    """
    YouTube Data API service.

    Provides methods for fetching YouTube data using authenticated API client.
    """

    def __init__(self) -> None:
        """Initialize YouTube service."""
        self._service = None
        self._videos_processed: int = 0  # Track for quota exceeded reporting

    def _is_quota_exceeded_error(self, error: HttpError) -> bool:
        """
        Check if an HttpError indicates quota exceeded.

        Detects quota exceeded errors by checking HTTP status code (403)
        and error reason from YouTube API response.

        Parameters
        ----------
        error : HttpError
            The HTTP error from YouTube API.

        Returns
        -------
        bool
            True if this is a quota exceeded error.
        """
        if error.resp.status != HTTP_FORBIDDEN:
            return False

        # Check error content for quota exceeded reasons
        try:
            error_content = error.content.decode("utf-8") if error.content else ""
            for reason in QUOTA_EXCEEDED_REASONS:
                if reason in error_content:
                    return True
        except (UnicodeDecodeError, AttributeError):
            pass

        return False

    def _is_retryable_error(self, error: Exception) -> bool:
        """
        Check if an error is retryable (transient).

        Parameters
        ----------
        error : Exception
            The error to check.

        Returns
        -------
        bool
            True if the error is retryable.
        """
        if isinstance(error, HttpError):
            return error.resp.status in RETRYABLE_STATUS_CODES

        # Network-level errors are retryable
        error_type_name = type(error).__name__
        retryable_error_types = {
            "ConnectionError",
            "TimeoutError",
            "ConnectionResetError",
            "BrokenPipeError",
            "SSLError",
            "socket.timeout",
        }
        return error_type_name in retryable_error_types

    def _execute_with_retry(self, request: Any) -> Any:
        """
        Execute a YouTube API request with retry logic.

        Implements exponential backoff retry (1s, 2s, 4s) for transient
        failures per FR-052. Raises QuotaExceededException for quota
        errors per FR-051.

        Parameters
        ----------
        request : Any
            The YouTube API request object to execute.

        Returns
        -------
        Any
            The API response.

        Raises
        ------
        QuotaExceededException
            If YouTube API quota is exceeded.
        NetworkError
            If all retry attempts fail.
        """
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                return request.execute()
            except HttpError as e:
                # Check for quota exceeded - don't retry these
                if self._is_quota_exceeded_error(e):
                    logger.error(
                        f"YouTube API quota exceeded after processing "
                        f"{self._videos_processed} videos"
                    )
                    raise QuotaExceededException(
                        message="YouTube API quota exceeded. Daily limit reached.",
                        daily_quota_exceeded=True,
                        videos_processed=self._videos_processed,
                    ) from e

                # Check if retryable
                if self._is_retryable_error(e) and attempt < MAX_RETRIES:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        f"Transient HTTP error (status={e.resp.status}), "
                        f"retry {attempt + 1}/{MAX_RETRIES} in {delay}s"
                    )
                    time.sleep(delay)
                    last_error = e
                    continue

                # Non-retryable HTTP error
                raise

            except Exception as e:
                # Check if retryable network error
                if self._is_retryable_error(e) and attempt < MAX_RETRIES:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        f"Network error ({type(e).__name__}), "
                        f"retry {attempt + 1}/{MAX_RETRIES} in {delay}s"
                    )
                    time.sleep(delay)
                    last_error = e
                    continue

                # Non-retryable error
                raise

        # All retries exhausted
        raise NetworkError(
            message=f"API request failed after {MAX_RETRIES} retries",
            original_error=last_error,
            retry_count=MAX_RETRIES,
        )

    @property
    def service(self) -> Any:
        """Get authenticated YouTube API service client."""
        if self._service is None:
            self._service = youtube_oauth.get_authenticated_service()
        return self._service

    async def get_my_channel(self) -> Dict[str, Any]:
        """
        Get information about the authenticated user's channel.

        Returns
        -------
        Dict[str, Any]
            Channel information including id, title, description, statistics
        """
        request = self.service.channels().list(
            part="id,snippet,statistics,contentDetails,status,brandingSettings,topicDetails",
            mine=True,
        )
        response = request.execute()

        if not response.get("items"):
            raise ValueError("No channel found for authenticated user")

        return dict(response["items"][0])

    async def get_channel_details(self, channel_id: ChannelId) -> Dict[str, Any]:
        """
        Get detailed information about a specific channel.

        Parameters
        ----------
        channel_id : ChannelId
            The channel ID to fetch details for (validated)

        Returns
        -------
        Dict[str, Any]
            Channel information including id, title, description, statistics
        """
        request = self.service.channels().list(
            part="id,snippet,statistics,contentDetails,status,brandingSettings,topicDetails",
            id=channel_id,
        )
        response = request.execute()

        if not response.get("items"):
            raise ValueError(f"Channel {channel_id} not found")

        return dict(response["items"][0])

    async def get_channel_videos(
        self, channel_id: ChannelId, max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get videos from a specific channel.

        Parameters
        ----------
        channel_id : ChannelId
            The channel ID to fetch videos from (validated)
        max_results : int
            Maximum number of videos to return (default 50)

        Returns
        -------
        List[Dict[str, Any]]
            List of video information
        """
        # First get the uploads playlist ID
        request = self.service.channels().list(part="contentDetails", id=channel_id)
        response = request.execute()

        if not response.get("items"):
            raise ValueError(f"Channel {channel_id} not found")

        uploads_playlist_id = response["items"][0]["contentDetails"][
            "relatedPlaylists"
        ]["uploads"]

        # Get videos from uploads playlist
        request = self.service.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=max_results,
        )
        response = request.execute()

        return list(response.get("items", []))

    async def get_video_details(self, video_ids: list[VideoId]) -> list[Dict[str, Any]]:
        """
        Get detailed information about specific videos.

        Uses retry logic with exponential backoff for transient failures
        and detects quota exceeded errors.

        Parameters
        ----------
        video_ids : List[VideoId]
            List of video IDs to fetch details for (max 50, validated)

        Returns
        -------
        List[Dict[str, Any]]
            List of detailed video information

        Raises
        ------
        QuotaExceededException
            If YouTube API quota is exceeded.
        ValueError
            If more than 50 video IDs are provided.
        """
        # YouTube API allows max 50 video IDs per request
        if len(video_ids) > 50:
            raise ValueError("Maximum 50 video IDs allowed per request")

        request = self.service.videos().list(
            part="id,snippet,statistics,contentDetails,status,localizations,topicDetails",
            id=",".join(video_ids),
        )
        response = self._execute_with_retry(request)

        return list(response.get("items", []))

    async def fetch_videos_batched(
        self, video_ids: List[str], batch_size: int = 50
    ) -> tuple[List[Dict[str, Any]], set[str]]:
        """
        Fetch video details in batches, handling pagination for large lists.

        This method automatically splits large video ID lists into batches of
        up to 50 (YouTube API limit) and aggregates the results. It properly
        handles partial API responses where some videos are found and some
        return 404 (T094).

        Implements:
        - T091: Quota exceeded handling - raises QuotaExceededException
        - T092: Retry with exponential backoff for transient failures
        - T094: Partial API response handling (some found, some 404)

        Parameters
        ----------
        video_ids : List[str]
            List of video IDs to fetch (can be any size)
        batch_size : int, optional
            Number of videos per batch (default 50, max 50)

        Returns
        -------
        tuple[List[Dict[str, Any]], set[str]]
            Tuple of (list of video details, set of video IDs not found)
            Videos not returned by API are considered deleted/private.

        Raises
        ------
        QuotaExceededException
            If YouTube API quota is exceeded. The exception includes
            the number of videos processed before quota was exhausted.

        Examples
        --------
        >>> videos, not_found = await service.fetch_videos_batched(video_ids)
        >>> print(f"Found {len(videos)}, missing {len(not_found)}")
        """
        batch_size = min(batch_size, 50)  # YouTube API max is 50
        all_videos: List[Dict[str, Any]] = []
        requested_ids = set(video_ids)
        found_ids: set[str] = set()

        # Reset processed counter for this batch operation
        self._videos_processed = 0

        for i in range(0, len(video_ids), batch_size):
            batch = video_ids[i : i + batch_size]
            batch_number = i // batch_size + 1
            try:
                logger.debug(
                    f"Fetching batch {batch_number} ({len(batch)} videos)"
                )
                batch_results = await self.get_video_details(batch)
                all_videos.extend(batch_results)

                # T094: Track which IDs were found (partial response handling)
                # Videos not in response are deleted/private
                for video in batch_results:
                    video_id = video.get("id", "")
                    if video_id:
                        found_ids.add(video_id)

                # Update processed count for quota exceeded reporting
                self._videos_processed += len(batch)
                logger.debug(
                    f"Batch {batch_number}: Found {len(batch_results)}/{len(batch)} videos"
                )

            except QuotaExceededException:
                # Re-raise quota exceeded - let caller handle it
                logger.error(
                    f"Quota exceeded at batch {batch_number} after processing "
                    f"{self._videos_processed} videos"
                )
                raise

            except Exception as e:
                # Log error but continue with remaining batches
                # This handles cases where individual batches fail but others succeed
                logger.warning(f"Error fetching batch {batch_number}: {e}")

        # T094: Not found = requested but not in response (deleted/private)
        not_found = requested_ids - found_ids
        if not_found:
            logger.info(
                f"Batch fetch complete: {len(found_ids)} found, "
                f"{len(not_found)} not found (deleted/private)"
            )

        return all_videos, not_found

    def check_credentials(self) -> bool:
        """
        Check if YouTube API credentials are configured and valid.

        Returns
        -------
        bool
            True if credentials are valid and API is accessible.

        Examples
        --------
        >>> if not service.check_credentials():
        ...     print("Run 'chronovista auth setup' to configure credentials")
        """
        try:
            # Try to initialize the service
            _ = self.service
            return True
        except Exception:
            return False

    async def get_my_playlists(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Get playlists owned by the authenticated user.

        Parameters
        ----------
        max_results : int
            Maximum number of playlists to return (default 50)

        Returns
        -------
        List[Dict[str, Any]]
            List of playlist information
        """
        request = self.service.playlists().list(
            part="id,snippet,status,contentDetails", mine=True, maxResults=max_results
        )
        response = request.execute()

        return list(response.get("items", []))

    async def get_playlist_videos(
        self, playlist_id: PlaylistId, max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get videos from a specific playlist.

        Parameters
        ----------
        playlist_id : PlaylistId
            The playlist ID to fetch videos from (validated)
        max_results : int
            Maximum number of videos to return (default 50)

        Returns
        -------
        List[Dict[str, Any]]
            List of video information from the playlist
        """
        request = self.service.playlistItems().list(
            part="snippet,contentDetails,status",
            playlistId=playlist_id,
            maxResults=max_results,
        )
        response = request.execute()

        return list(response.get("items", []))

    async def search_my_videos(
        self, query: str, max_results: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Search through the authenticated user's videos.

        Parameters
        ----------
        query : str
            Search query string
        max_results : int
            Maximum number of results to return (default 25)

        Returns
        -------
        List[Dict[str, Any]]
            List of matching video information
        """
        request = self.service.search().list(
            part="id,snippet",
            forMine=True,
            q=query,
            type="video",
            maxResults=max_results,
        )
        response = request.execute()

        return list(response.get("items", []))

    async def get_video_captions(self, video_id: VideoId) -> List[Dict[str, Any]]:
        """
        Get available captions/transcripts for a video.

        Parameters
        ----------
        video_id : VideoId
            The video ID to get captions for (validated)

        Returns
        -------
        List[Dict[str, Any]]
            List of available caption tracks
        """
        try:
            request = self.service.captions().list(part="id,snippet", videoId=video_id)
            response = request.execute()
            return list(response.get("items", []))
        except Exception as e:
            # Captions API may not be accessible for all videos
            print(f"Could not fetch captions for video {video_id}: {e}")
            return []

    async def download_caption(
        self, caption_id: str, fmt: str = "srt"
    ) -> Optional[str]:
        """
        Download caption content using YouTube Data API v3.

        Parameters
        ----------
        caption_id : str
            The caption track ID to download
        fmt : str
            Format to download (srt, vtt, etc.). Default is 'srt'

        Returns
        -------
        Optional[str]
            Caption content as string, or None if download failed
        """
        try:
            request = self.service.captions().download(id=caption_id, tfmt=fmt)
            caption_content = request.execute()

            # The response should be the caption content as bytes
            if isinstance(caption_content, bytes):
                return caption_content.decode("utf-8")
            elif isinstance(caption_content, str):
                return caption_content
            else:
                print(f"Unexpected caption content type: {type(caption_content)}")
                return None

        except Exception as e:
            print(f"Could not download caption {caption_id}: {e}")
            return None

    async def get_my_watch_later_videos(
        self, max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get videos in the authenticated user's Watch Later playlist.

        Parameters
        ----------
        max_results : int
            Maximum number of videos to return (default 50)

        Returns
        -------
        List[Dict[str, Any]]
            List of Watch Later video information
        """
        try:
            # First get user's channel to find watch later playlist
            my_channel = await self.get_my_channel()

            # Get the watch later playlist ID
            watch_later_playlist_id = my_channel["contentDetails"]["relatedPlaylists"][
                "watchLater"
            ]

            # Get videos from watch later playlist
            request = self.service.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=watch_later_playlist_id,
                maxResults=max_results,
            )
            response = request.execute()

            return list(response.get("items", []))
        except Exception as e:
            print(f"Could not fetch Watch Later videos: {e}")
            return []

    async def check_video_in_playlist(
        self, video_id: VideoId, playlist_id: PlaylistId
    ) -> bool:
        """
        Check if a specific video exists in a playlist.

        Parameters
        ----------
        video_id : VideoId
            The video ID to check for (validated)
        playlist_id : PlaylistId
            The playlist ID to check in (validated)

        Returns
        -------
        bool
            True if video is in playlist, False otherwise
        """
        try:
            request = self.service.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                videoId=video_id,
                maxResults=1,
            )
            response = request.execute()

            return len(response.get("items", [])) > 0
        except Exception as e:
            print(f"Could not check video {video_id} in playlist {playlist_id}: {e}")
            return False

    async def get_user_playlists_for_video(self, video_id: VideoId) -> List[str]:
        """
        Get all user playlists that contain a specific video.

        Parameters
        ----------
        video_id : VideoId
            The video ID to search for (validated)

        Returns
        -------
        List[str]
            List of playlist IDs that contain the video
        """
        try:
            # Get all user playlists
            all_playlists = await self.get_my_playlists(max_results=50)

            video_playlists = []

            # Check each playlist for the video
            for playlist in all_playlists:
                playlist_id = playlist["id"]
                if await self.check_video_in_playlist(video_id, playlist_id):
                    video_playlists.append(playlist_id)

            return video_playlists
        except Exception as e:
            print(f"Could not get playlists for video {video_id}: {e}")
            return []

    async def get_liked_videos(self, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Get videos that the authenticated user has liked.

        Parameters
        ----------
        max_results : int
            Maximum number of liked videos to return (default 10, max 50)

        Returns
        -------
        List[Dict[str, Any]]
            List of liked videos with details
        """
        try:
            # First get the liked videos playlist ID
            request = self.service.channels().list(part="contentDetails", mine=True)
            response = request.execute()

            if not response.get("items"):
                raise ValueError("No channel found for authenticated user")

            # Get the liked videos playlist ID
            content_details = response["items"][0].get("contentDetails", {})
            related_playlists = content_details.get("relatedPlaylists", {})
            liked_playlist_id = related_playlists.get("likes")

            if not liked_playlist_id:
                return []  # No liked videos playlist available

            # Get videos from liked playlist
            request = self.service.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=liked_playlist_id,
                maxResults=min(max_results, 50),  # API max is 50
            )
            response = request.execute()

            playlist_items = response.get("items", [])

            if not playlist_items:
                return []

            # Extract video IDs to get detailed video information
            video_ids = [
                item["contentDetails"]["videoId"]
                for item in playlist_items
                if item.get("contentDetails", {}).get("videoId")
            ]

            if not video_ids:
                return []

            # Get detailed video information
            detailed_videos = await self.get_video_details(video_ids)

            return detailed_videos

        except Exception as e:
            print(f"Could not fetch liked videos: {e}")
            return []

    async def get_subscription_channels(
        self, max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get channels that the authenticated user is subscribed to.

        Parameters
        ----------
        max_results : int
            Maximum number of subscriptions to return (default 50)

        Returns
        -------
        List[Dict[str, Any]]
            List of subscribed channels
        """
        request = self.service.subscriptions().list(
            part="id,snippet,subscriberSnippet", mine=True, maxResults=max_results
        )
        response = request.execute()

        return list(response.get("items", []))

    async def get_playlist_details(
        self, playlist_ids: list[str]
    ) -> list[Dict[str, Any]]:
        """
        Get detailed information about specific playlists.

        Uses retry logic with exponential backoff for transient failures.

        Parameters
        ----------
        playlist_ids : List[str]
            List of playlist IDs to fetch details for (max 50)

        Returns
        -------
        List[Dict[str, Any]]
            List of detailed playlist information

        Raises
        ------
        QuotaExceededException
            If YouTube API quota is exceeded.
        ValueError
            If more than 50 playlist IDs are provided
        """
        # YouTube API allows max 50 playlist IDs per request
        if len(playlist_ids) > 50:
            raise ValueError("Maximum 50 playlist IDs allowed per request")

        request = self.service.playlists().list(
            part="id,snippet,status,contentDetails",
            id=",".join(playlist_ids),
        )
        response = self._execute_with_retry(request)

        return list(response.get("items", []))

    async def fetch_playlists_batched(
        self, playlist_ids: List[str], batch_size: int = 50
    ) -> tuple[List[Dict[str, Any]], set[str]]:
        """
        Fetch playlist details in batches, handling pagination for large lists.

        This method automatically splits large playlist ID lists into batches of
        up to 50 (YouTube API limit) and aggregates the results.

        Parameters
        ----------
        playlist_ids : List[str]
            List of playlist IDs to fetch (can be any size)
        batch_size : int, optional
            Number of playlists per batch (default 50, max 50)

        Returns
        -------
        tuple[List[Dict[str, Any]], set[str]]
            Tuple of (list of playlist details, set of playlist IDs not found)
            Playlists not returned by API are considered deleted/private.

        Examples
        --------
        >>> playlists, not_found = await service.fetch_playlists_batched(playlist_ids)
        >>> print(f"Found {len(playlists)}, missing {len(not_found)}")
        """
        batch_size = min(batch_size, 50)  # YouTube API max is 50
        all_playlists: List[Dict[str, Any]] = []
        requested_ids = set(playlist_ids)
        found_ids: set[str] = set()

        for i in range(0, len(playlist_ids), batch_size):
            batch = playlist_ids[i : i + batch_size]
            try:
                batch_results = await self.get_playlist_details(batch)
                all_playlists.extend(batch_results)
                # Track which IDs were found
                for playlist in batch_results:
                    found_ids.add(playlist.get("id", ""))
            except Exception as e:
                # Log error but continue with remaining batches
                print(f"Error fetching playlist batch {i // batch_size + 1}: {e}")

        not_found = requested_ids - found_ids
        return all_playlists, not_found

    async def get_video_categories(
        self, region_code: str = "US"
    ) -> List[Dict[str, Any]]:
        """
        Get YouTube video categories for a specific region.

        Parameters
        ----------
        region_code : str
            Two-character ISO 3166-1 country code (default "US").
            Examples: "US", "GB", "DE", "JP", "FR", "CA", "AU"

        Returns
        -------
        List[Dict[str, Any]]
            List of video category information including id, title, and channel ID.
            Each category contains:
            - id: Category ID (e.g., "1", "10", "15")
            - snippet.title: Category name (e.g., "Film & Animation", "Music", "Pets & Animals")
            - snippet.channelId: Channel ID that owns the category
            - snippet.assignable: Whether the category can be assigned to videos

        Raises
        ------
        ValueError
            If region_code is not a valid 2-character country code or API request fails
        """
        if len(region_code) != 2:
            raise ValueError(
                f"Invalid region code: {region_code}. Must be 2 characters (e.g., 'US', 'GB')"
            )

        try:
            request = self.service.videoCategories().list(
                part="id,snippet", regionCode=region_code.upper()
            )
            response = request.execute()

            categories = response.get("items", [])
            if not categories:
                raise ValueError(f"No video categories found for region: {region_code}")

            return list(categories)

        except Exception as e:
            raise ValueError(
                f"Failed to fetch video categories for region {region_code}: {str(e)}"
            )

    def close(self) -> None:
        """Clean up resources."""
        self._service = None


# Global YouTube service instance
youtube_service = YouTubeService()
