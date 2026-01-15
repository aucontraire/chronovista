"""
YouTube Data API service for fetching user data.

Provides high-level methods for interacting with YouTube Data API v3,
including channel info, videos, playlists, and watch history.

Implements retry logic with exponential backoff for transient failures
and quota exceeded detection per FR-051 and FR-052.

All methods return strongly-typed Pydantic models (FR-005, FR-006, FR-007)
instead of Dict[str, Any] for improved type safety and runtime validation.
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Optional

from googleapiclient.errors import HttpError
from pydantic import ValidationError as PydanticValidationError

from chronovista.auth import youtube_oauth
from chronovista.config.settings import settings
from chronovista.exceptions import (
    NetworkError,
    QuotaExceededException,
    ValidationError,
    YouTubeAPIError,
)
from chronovista.models.api_responses import (
    YouTubeCaptionResponse,
    YouTubeChannelResponse,
    YouTubePlaylistItemResponse,
    YouTubePlaylistResponse,
    YouTubeSearchResponse,
    YouTubeSubscriptionResponse,
    YouTubeVideoCategoryResponse,
    YouTubeVideoResponse,
)
from chronovista.models.youtube_types import ChannelId, PlaylistId, VideoId
from chronovista.services.interfaces import YouTubeServiceInterface

logger = logging.getLogger(__name__)

# Retry configuration for transient failures (FR-052)
# Uses settings.retry_attempts and settings.retry_backoff for configurability
MAX_RETRIES = settings.retry_attempts
RETRY_DELAYS = [1.0 * (settings.retry_backoff**i) for i in range(settings.retry_attempts)]

# HTTP status codes
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
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


class YouTubeService(YouTubeServiceInterface):
    """
    YouTube Data API service.

    Provides methods for fetching YouTube data using authenticated API client.
    Implements YouTubeServiceInterface for dependency injection and testability.
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

    def _extract_error_reason(self, error: HttpError) -> str | None:
        """
        Extract error reason from YouTube API HttpError response.

        Parameters
        ----------
        error : HttpError
            The HTTP error from YouTube API.

        Returns
        -------
        str | None
            The error reason from the API response, or None if not found.
        """
        try:
            error_content = error.content.decode("utf-8") if error.content else ""
            # Try to parse JSON error response
            import json

            error_json = json.loads(error_content)
            errors = error_json.get("error", {}).get("errors", [])
            if errors:
                return str(errors[0].get("reason", "unknown"))
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, KeyError):
            pass
        return None

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

                # Non-retryable HTTP error - wrap in YouTubeAPIError
                error_reason = self._extract_error_reason(e)
                raise YouTubeAPIError(
                    message=f"YouTube API error: {e.reason}",
                    status_code=e.resp.status,
                    error_reason=error_reason,
                ) from e

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
        ValueError
            If no channel is found for the authenticated user.
        """
        request = self.service.channels().list(
            part="id,snippet,statistics,contentDetails,status,brandingSettings,topicDetails",
            mine=True,
        )
        response = request.execute()

        if not response.get("items"):
            raise YouTubeAPIError(
                message="No channel found for authenticated user",
                status_code=HTTP_NOT_FOUND,
                error_reason="channelNotFound",
            )

        try:
            return YouTubeChannelResponse.model_validate(response["items"][0])
        except PydanticValidationError as e:
            logger.warning(f"Failed to parse channel response: {e}")
            raise ValidationError(
                message=f"Failed to parse channel response: {e}",
                field_name="channel_response",
            ) from e

    async def get_channel_details(
        self, channel_id: ChannelId | list[ChannelId]
    ) -> list[YouTubeChannelResponse]:
        """
        Get detailed information about one or more channels.

        Parameters
        ----------
        channel_id : ChannelId | list[ChannelId]
            The channel ID(s) to fetch details for (validated)

        Returns
        -------
        list[YouTubeChannelResponse]
            List containing channel information.

        Raises
        ------
        ValueError
            If no channels are found.
        """
        # Handle both single channel ID and list of channel IDs
        if isinstance(channel_id, list):
            channel_ids_str = ",".join(channel_id)
        else:
            channel_ids_str = channel_id

        request = self.service.channels().list(
            part="id,snippet,statistics,contentDetails,status,brandingSettings,topicDetails",
            id=channel_ids_str,
        )
        response = request.execute()

        if not response.get("items"):
            raise YouTubeAPIError(
                message=f"Channels {channel_ids_str} not found",
                status_code=HTTP_NOT_FOUND,
                error_reason="channelNotFound",
            )

        results: list[YouTubeChannelResponse] = []
        for item in response.get("items", []):
            try:
                results.append(YouTubeChannelResponse.model_validate(item))
            except PydanticValidationError as e:
                logger.warning(f"Failed to parse channel response: {e}")
        return results

    async def get_channel_videos(
        self, channel_id: ChannelId, max_results: int = 50
    ) -> list[YouTubePlaylistItemResponse]:
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
        list[YouTubePlaylistItemResponse]
            List of playlist item information representing channel videos.

        Raises
        ------
        YouTubeAPIError
            If the channel is not found.
        """
        # First get the uploads playlist ID
        request = self.service.channels().list(part="contentDetails", id=channel_id)
        response = request.execute()

        if not response.get("items"):
            raise YouTubeAPIError(
                message=f"Channel {channel_id} not found",
                status_code=HTTP_NOT_FOUND,
                error_reason="channelNotFound",
            )

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

        results: list[YouTubePlaylistItemResponse] = []
        for item in response.get("items", []):
            try:
                results.append(YouTubePlaylistItemResponse.model_validate(item))
            except PydanticValidationError as e:
                logger.warning(f"Failed to parse playlist item response: {e}")
        return results

    async def get_video_details(
        self, video_ids: list[VideoId]
    ) -> list[YouTubeVideoResponse]:
        """
        Get detailed information about specific videos.

        Uses retry logic with exponential backoff for transient failures
        and detects quota exceeded errors.

        Parameters
        ----------
        video_ids : list[VideoId]
            List of video IDs to fetch details for (max 50, validated)

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
        # YouTube API allows max 50 video IDs per request
        if len(video_ids) > 50:
            raise ValidationError(
                message="Maximum 50 video IDs allowed per request",
                field_name="video_ids",
                invalid_value=len(video_ids),
            )

        request = self.service.videos().list(
            part="id,snippet,statistics,contentDetails,status,localizations,topicDetails",
            id=",".join(video_ids),
        )
        response = self._execute_with_retry(request)

        results: list[YouTubeVideoResponse] = []
        for item in response.get("items", []):
            try:
                results.append(YouTubeVideoResponse.model_validate(item))
            except PydanticValidationError as e:
                logger.warning(f"Failed to parse video response: {e}")
        return results

    async def fetch_videos_batched(
        self, video_ids: List[str], batch_size: int = 50
    ) -> tuple[list[YouTubeVideoResponse], set[str]]:
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
        tuple[list[YouTubeVideoResponse], set[str]]
            Tuple of (list of video details as typed models, set of video IDs not found)
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
        all_videos: list[YouTubeVideoResponse] = []
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
                    if video.id:
                        found_ids.add(video.id)

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

    async def get_my_playlists(
        self, max_results: int | None = None, fetch_all: bool = True
    ) -> list[YouTubePlaylistResponse]:
        """
        Get playlists owned by the authenticated user.

        Supports pagination to fetch all playlists. The YouTube API returns
        a maximum of 50 items per page, so this method automatically paginates
        through all results when fetch_all is True.

        Parameters
        ----------
        max_results : int | None
            Maximum number of playlists to return. None (default) means no limit.
            When fetch_all is True, this is the total limit across all pages.
            When fetch_all is False, this is passed directly to the API (max 50).
        fetch_all : bool
            If True (default), automatically paginate through all results up to
            max_results. If False, make a single API call (max 50 per page).

        Returns
        -------
        list[YouTubePlaylistResponse]
            List of playlist information as typed models.
        """
        results: list[YouTubePlaylistResponse] = []
        page_token: str | None = None

        while True:
            # Determine page size for this request
            if fetch_all:
                if max_results is not None:
                    remaining = max_results - len(results)
                    if remaining <= 0:
                        break
                    page_size = min(remaining, 50)
                else:
                    page_size = 50  # No limit, use max per page
            else:
                page_size = min(max_results, 50) if max_results else 50

            request = self.service.playlists().list(
                part="id,snippet,status,contentDetails",
                mine=True,
                maxResults=page_size,
                pageToken=page_token,
            )
            response = request.execute()

            for item in response.get("items", []):
                try:
                    results.append(YouTubePlaylistResponse.model_validate(item))
                except PydanticValidationError as e:
                    logger.warning(f"Failed to parse playlist response: {e}")

            # Check if we should continue pagination
            if not fetch_all:
                # Single page mode - stop after first request
                break

            page_token = response.get("nextPageToken")
            if not page_token:
                break

            # Stop if we've reached the limit
            if max_results is not None and len(results) >= max_results:
                break

        return results

    async def get_playlist_videos(
        self, playlist_id: PlaylistId, max_results: int | None = None, fetch_all: bool = True
    ) -> list[YouTubePlaylistItemResponse]:
        """
        Get videos from a specific playlist.

        Supports pagination to fetch all videos. The YouTube API returns
        a maximum of 50 items per page, so this method automatically paginates
        through all results when fetch_all is True.

        Parameters
        ----------
        playlist_id : PlaylistId
            The playlist ID to fetch videos from (validated)
        max_results : int | None
            Maximum number of videos to return. None (default) means no limit.
            When fetch_all is True, this is the total limit across all pages.
            When fetch_all is False, this is passed directly to the API (max 50).
        fetch_all : bool
            If True (default), automatically paginate through all results up to
            max_results. If False, make a single API call (max 50 per page).

        Returns
        -------
        list[YouTubePlaylistItemResponse]
            List of playlist item information as typed models.
        """
        results: list[YouTubePlaylistItemResponse] = []
        page_token: str | None = None

        while True:
            # Determine page size for this request
            if fetch_all:
                if max_results is not None:
                    remaining = max_results - len(results)
                    if remaining <= 0:
                        break
                    page_size = min(remaining, 50)
                else:
                    page_size = 50  # No limit, use max per page
            else:
                page_size = min(max_results, 50) if max_results else 50

            request = self.service.playlistItems().list(
                part="snippet,contentDetails,status",
                playlistId=playlist_id,
                maxResults=page_size,
                pageToken=page_token,
            )
            response = request.execute()

            for item in response.get("items", []):
                try:
                    results.append(YouTubePlaylistItemResponse.model_validate(item))
                except PydanticValidationError as e:
                    logger.warning(f"Failed to parse playlist item response: {e}")

            # Check if we should continue pagination
            if not fetch_all:
                # Single page mode - stop after first request
                break

            page_token = response.get("nextPageToken")
            if not page_token:
                break

            # Stop if we've reached the limit
            if max_results is not None and len(results) >= max_results:
                break

        return results

    async def search_my_videos(
        self, query: str, max_results: int = 25
    ) -> list[YouTubeSearchResponse]:
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
        list[YouTubeSearchResponse]
            List of matching search results as typed models.
        """
        request = self.service.search().list(
            part="id,snippet",
            forMine=True,
            q=query,
            type="video",
            maxResults=max_results,
        )
        response = request.execute()

        results: list[YouTubeSearchResponse] = []
        for item in response.get("items", []):
            try:
                results.append(YouTubeSearchResponse.model_validate(item))
            except PydanticValidationError as e:
                logger.warning(f"Failed to parse search response: {e}")
        return results

    async def get_video_captions(
        self, video_id: VideoId
    ) -> list[YouTubeCaptionResponse]:
        """
        Get available captions/transcripts for a video.

        Parameters
        ----------
        video_id : VideoId
            The video ID to get captions for (validated)

        Returns
        -------
        list[YouTubeCaptionResponse]
            List of available caption tracks as typed models.
        """
        try:
            request = self.service.captions().list(part="id,snippet", videoId=video_id)
            response = request.execute()

            results: list[YouTubeCaptionResponse] = []
            for item in response.get("items", []):
                try:
                    results.append(YouTubeCaptionResponse.model_validate(item))
                except PydanticValidationError as e:
                    logger.warning(f"Failed to parse caption response: {e}")
            return results
        except Exception as e:
            # Captions API may not be accessible for all videos
            logger.warning(f"Could not fetch captions for video {video_id}: {e}")
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
    ) -> list[YouTubePlaylistItemResponse]:
        """
        Get videos in the authenticated user's Watch Later playlist.

        Parameters
        ----------
        max_results : int
            Maximum number of videos to return (default 50)

        Returns
        -------
        list[YouTubePlaylistItemResponse]
            List of Watch Later playlist item information as typed models.
        """
        try:
            # First get user's channel to find watch later playlist
            my_channel = await self.get_my_channel()
            if my_channel is None:
                logger.warning("No channel found for authenticated user")
                return []

            # Get the watch later playlist ID from typed model
            content_details = my_channel.content_details
            if content_details is None:
                logger.warning("No content details found for channel")
                return []

            watch_later_playlist_id = content_details.related_playlists.watch_later
            if watch_later_playlist_id is None:
                logger.warning("No Watch Later playlist found for channel")
                return []

            # Get videos from watch later playlist
            request = self.service.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=watch_later_playlist_id,
                maxResults=max_results,
            )
            response = request.execute()

            results: list[YouTubePlaylistItemResponse] = []
            for item in response.get("items", []):
                try:
                    results.append(YouTubePlaylistItemResponse.model_validate(item))
                except PydanticValidationError as e:
                    logger.warning(f"Failed to parse playlist item response: {e}")
            return results
        except Exception as e:
            logger.warning(f"Could not fetch Watch Later videos: {e}")
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

    async def get_user_playlists_for_video(self, video_id: VideoId) -> list[str]:
        """
        Get all user playlists that contain a specific video.

        Parameters
        ----------
        video_id : VideoId
            The video ID to search for (validated)

        Returns
        -------
        list[str]
            List of playlist IDs that contain the video
        """
        try:
            # Get all user playlists
            all_playlists = await self.get_my_playlists(max_results=50)

            video_playlists: list[str] = []

            # Check each playlist for the video
            for playlist in all_playlists:
                playlist_id = playlist.id
                if await self.check_video_in_playlist(video_id, playlist_id):
                    video_playlists.append(playlist_id)

            return video_playlists
        except Exception as e:
            logger.warning(f"Could not get playlists for video {video_id}: {e}")
            return []

    async def get_liked_videos(
        self, max_results: Optional[int] = None
    ) -> list[YouTubeVideoResponse]:
        """
        Get videos that the authenticated user has liked.

        Supports pagination to fetch all liked videos. The YouTube API
        returns a maximum of 50 items per page, so this method automatically
        paginates through all results.

        Parameters
        ----------
        max_results : Optional[int]
            Maximum number of liked videos to return. If None (default),
            fetches ALL liked videos by paginating through the entire playlist.

        Returns
        -------
        list[YouTubeVideoResponse]
            List of liked videos with details as typed models.

        Raises
        ------
        QuotaExceededException
            If YouTube API quota is exceeded during pagination.
        YouTubeAPIError
            If a non-retryable API error occurs.
        """
        logger.info("Fetching liked videos from YouTube API")

        try:
            # First get the liked videos playlist ID
            request = self.service.channels().list(part="contentDetails", mine=True)
            response = self._execute_with_retry(request)

            if not response.get("items"):
                raise YouTubeAPIError(
                    message="No channel found for authenticated user",
                    status_code=HTTP_NOT_FOUND,
                    error_reason="channelNotFound",
                )

            # Get the liked videos playlist ID
            content_details = response["items"][0].get("contentDetails", {})
            related_playlists = content_details.get("relatedPlaylists", {})
            liked_playlist_id = related_playlists.get("likes")

            if not liked_playlist_id:
                logger.warning("No liked videos playlist found for user")
                return []

            logger.debug(f"Liked playlist ID: {liked_playlist_id}")

            # Paginate through all liked videos
            all_video_ids: list[str] = []
            page_token: Optional[str] = None
            page_number = 0

            while True:
                page_number += 1

                # Determine how many to fetch in this page
                if max_results is not None:
                    remaining = max_results - len(all_video_ids)
                    if remaining <= 0:
                        break
                    page_size = min(remaining, 50)
                else:
                    page_size = 50  # API max per page

                # Get videos from liked playlist with retry logic
                request = self.service.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=liked_playlist_id,
                    maxResults=page_size,
                    pageToken=page_token,
                )
                response = self._execute_with_retry(request)

                playlist_items = response.get("items", [])
                items_in_page = len(playlist_items)

                # Extract video IDs
                for item in playlist_items:
                    video_id = item.get("contentDetails", {}).get("videoId")
                    if video_id:
                        all_video_ids.append(video_id)

                logger.debug(
                    f"Liked videos page {page_number}: fetched {items_in_page} items, "
                    f"total so far: {len(all_video_ids)}"
                )

                # Check for next page
                page_token = response.get("nextPageToken")
                if not page_token:
                    logger.debug(
                        f"Pagination complete after {page_number} pages, "
                        f"no more nextPageToken"
                    )
                    break

                # Stop if we've reached the limit
                if max_results is not None and len(all_video_ids) >= max_results:
                    logger.debug(f"Reached max_results limit: {max_results}")
                    break

            logger.info(
                f"Fetched {len(all_video_ids)} liked video IDs "
                f"across {page_number} pages"
            )

            if not all_video_ids:
                return []

            # Get detailed video information (returns typed models)
            # Process in batches of 50 (API limit)
            all_detailed_videos: list[YouTubeVideoResponse] = []
            for i in range(0, len(all_video_ids), 50):
                batch_ids = all_video_ids[i : i + 50]
                detailed_videos = await self.get_video_details(batch_ids)
                all_detailed_videos.extend(detailed_videos)

            logger.info(
                f"Retrieved details for {len(all_detailed_videos)} liked videos "
                f"({len(all_video_ids) - len(all_detailed_videos)} unavailable/deleted)"
            )

            return all_detailed_videos

        except QuotaExceededException:
            # Re-raise quota exceptions so callers can handle them
            logger.error("Quota exceeded while fetching liked videos")
            raise

        except YouTubeAPIError:
            # Re-raise API errors so callers can handle them
            logger.error("YouTube API error while fetching liked videos")
            raise

        except Exception as e:
            # Log unexpected errors with full context, but still raise them
            logger.error(
                f"Unexpected error fetching liked videos: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise

    async def get_subscription_channels(
        self, max_results: int = 50
    ) -> list[YouTubeSubscriptionResponse]:
        """
        Get channels that the authenticated user is subscribed to.

        Parameters
        ----------
        max_results : int
            Maximum number of subscriptions to return (default 50)

        Returns
        -------
        list[YouTubeSubscriptionResponse]
            List of subscribed channels as typed models.
        """
        request = self.service.subscriptions().list(
            part="id,snippet,subscriberSnippet", mine=True, maxResults=max_results
        )
        response = request.execute()

        results: list[YouTubeSubscriptionResponse] = []
        for item in response.get("items", []):
            try:
                results.append(YouTubeSubscriptionResponse.model_validate(item))
            except PydanticValidationError as e:
                logger.warning(f"Failed to parse subscription response: {e}")
        return results

    async def get_playlist_details(
        self, playlist_ids: list[str]
    ) -> list[YouTubePlaylistResponse]:
        """
        Get detailed information about specific playlists.

        Uses retry logic with exponential backoff for transient failures.

        Parameters
        ----------
        playlist_ids : list[str]
            List of playlist IDs to fetch details for (max 50)

        Returns
        -------
        list[YouTubePlaylistResponse]
            List of detailed playlist information as typed models.

        Raises
        ------
        QuotaExceededException
            If YouTube API quota is exceeded.
        ValidationError
            If more than 50 playlist IDs are provided
        """
        # YouTube API allows max 50 playlist IDs per request
        if len(playlist_ids) > 50:
            raise ValidationError(
                message="Maximum 50 playlist IDs allowed per request",
                field_name="playlist_ids",
                invalid_value=len(playlist_ids),
            )

        request = self.service.playlists().list(
            part="id,snippet,status,contentDetails",
            id=",".join(playlist_ids),
        )
        response = self._execute_with_retry(request)

        results: list[YouTubePlaylistResponse] = []
        for item in response.get("items", []):
            try:
                results.append(YouTubePlaylistResponse.model_validate(item))
            except PydanticValidationError as e:
                logger.warning(f"Failed to parse playlist response: {e}")
        return results

    async def fetch_playlists_batched(
        self, playlist_ids: List[str], batch_size: int = 50
    ) -> tuple[list[YouTubePlaylistResponse], set[str]]:
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
        tuple[list[YouTubePlaylistResponse], set[str]]
            Tuple of (list of playlist details as typed models, set of playlist IDs not found)
            Playlists not returned by API are considered deleted/private.

        Examples
        --------
        >>> playlists, not_found = await service.fetch_playlists_batched(playlist_ids)
        >>> print(f"Found {len(playlists)}, missing {len(not_found)}")
        """
        batch_size = min(batch_size, 50)  # YouTube API max is 50
        all_playlists: list[YouTubePlaylistResponse] = []
        requested_ids = set(playlist_ids)
        found_ids: set[str] = set()

        for i in range(0, len(playlist_ids), batch_size):
            batch = playlist_ids[i : i + batch_size]
            try:
                batch_results = await self.get_playlist_details(batch)
                all_playlists.extend(batch_results)
                # Track which IDs were found (now using typed model)
                for playlist in batch_results:
                    found_ids.add(playlist.id)
            except Exception as e:
                # Log error but continue with remaining batches
                logger.warning(f"Error fetching playlist batch {i // batch_size + 1}: {e}")

        not_found = requested_ids - found_ids
        return all_playlists, not_found

    async def get_video_categories(
        self, region_code: str = "US"
    ) -> list[YouTubeVideoCategoryResponse]:
        """
        Get YouTube video categories for a specific region.

        Parameters
        ----------
        region_code : str
            Two-character ISO 3166-1 country code (default "US").
            Examples: "US", "GB", "DE", "JP", "FR", "CA", "AU"

        Returns
        -------
        list[YouTubeVideoCategoryResponse]
            List of video category information as typed models.
            Each category contains:
            - id: Category ID (e.g., "1", "10", "15")
            - snippet.title: Category name (e.g., "Film & Animation", "Music", "Pets & Animals")
            - snippet.channel_id: Channel ID that owns the category
            - snippet.assignable: Whether the category can be assigned to videos

        Raises
        ------
        ValidationError
            If region_code is not a valid 2-character country code.
        YouTubeAPIError
            If no categories found for region or API request fails.
        """
        if len(region_code) != 2:
            raise ValidationError(
                message=f"Invalid region code: {region_code}. Must be 2 characters (e.g., 'US', 'GB')",
                field_name="region_code",
                invalid_value=region_code,
            )

        try:
            request = self.service.videoCategories().list(
                part="id,snippet", regionCode=region_code.upper()
            )
            response = request.execute()

            items = response.get("items", [])
            if not items:
                raise YouTubeAPIError(
                    message=f"No video categories found for region: {region_code}",
                    status_code=HTTP_NOT_FOUND,
                    error_reason="videoCategoriesNotFound",
                )

            results: list[YouTubeVideoCategoryResponse] = []
            for item in items:
                try:
                    results.append(YouTubeVideoCategoryResponse.model_validate(item))
                except PydanticValidationError as e:
                    logger.warning(f"Failed to parse video category response: {e}")
            return results

        except (ValidationError, YouTubeAPIError):
            raise
        except Exception as e:
            raise YouTubeAPIError(
                message=f"Failed to fetch video categories for region {region_code}: {str(e)}",
                error_reason="videoCategoriesFetchFailed",
            ) from e

    def close(self) -> None:
        """Clean up resources."""
        self._service = None


# Global YouTube service instance
youtube_service = YouTubeService()
