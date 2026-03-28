"""
Abstract Base Class for transcript services.

This interface defines the contract for transcript acquisition, enabling:
- Multiple transcript sources (youtube-transcript-api, official API, mock)
- Testability via mock implementations
- Clear API boundaries for type checking
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ...models.enums import DownloadReason
from ...models.video_transcript import EnhancedVideoTranscriptBase
from ...models.youtube_types import VideoId


class TranscriptServiceInterface(ABC):
    """
    Abstract interface for transcript acquisition.

    Implementations of this interface provide methods for downloading and
    processing YouTube transcripts. Implementations should handle:
    - Multiple transcript sources with fallback logic
    - Language preference handling
    - Error recovery and mock fallback

    Examples
    --------
    >>> class MockTranscriptService(TranscriptServiceInterface):
    ...     async def get_transcript(
    ...         self, video_id: VideoId, language_codes: Optional[List[str]] = None,
    ...         download_reason: DownloadReason = DownloadReason.USER_REQUEST
    ...     ) -> EnhancedVideoTranscriptBase:
    ...         # Mock implementation
    ...         pass
    """

    @abstractmethod
    async def get_transcript(
        self,
        video_id: VideoId,
        language_codes: list[str] | None = None,
        download_reason: DownloadReason = DownloadReason.USER_REQUEST,
    ) -> EnhancedVideoTranscriptBase:
        """
        Get transcript for a video with fallback handling.

        Parameters
        ----------
        video_id : VideoId
            YouTube video ID (validated VideoId type).
        language_codes : Optional[List[str]]
            Preferred language codes (e.g., ['en', 'en-US']).
            Defaults to English if not specified.
        download_reason : DownloadReason
            Reason for downloading the transcript.

        Returns
        -------
        EnhancedVideoTranscriptBase
            The downloaded transcript with metadata.

        Raises
        ------
        TranscriptNotFoundError
            When no transcript is available for the video.
        TranscriptServiceUnavailableError
            When the transcript service is not available.
        """
        pass

    @abstractmethod
    async def get_available_languages(self, video_id: VideoId) -> list[dict[str, Any]]:
        """
        Get list of available transcript languages for a video.

        Parameters
        ----------
        video_id : VideoId
            YouTube video ID (validated VideoId type).

        Returns
        -------
        List[Dict[str, Any]]
            List of available language information, each containing:
            - language_code: str
            - language_name: str
            - is_generated: bool
            - is_translatable: bool
        """
        pass

    @abstractmethod
    async def batch_get_transcripts(
        self,
        video_ids: list[VideoId],
        language_codes: list[str] | None = None,
        download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        max_retries: int = 3,
    ) -> dict[VideoId, EnhancedVideoTranscriptBase | None]:
        """
        Download transcripts for multiple videos.

        Parameters
        ----------
        video_ids : List[VideoId]
            List of YouTube video IDs (validated VideoId types).
        language_codes : Optional[List[str]]
            Preferred language codes.
        download_reason : DownloadReason
            Reason for downloading.
        max_retries : int
            Maximum retry attempts per video.

        Returns
        -------
        Dict[VideoId, Optional[EnhancedVideoTranscriptBase]]
            Dictionary mapping video_id to transcript (or None if failed).
        """
        pass

    @abstractmethod
    async def get_transcripts_for_languages(
        self,
        video_id: VideoId,
        language_codes: list[str],
        download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        include_translations: bool = False,
    ) -> dict[str, EnhancedVideoTranscriptBase | None]:
        """
        Get transcripts for multiple languages with minimal API calls.

        Uses a single ``api.list()`` call to enumerate available transcripts,
        then selectively fetches only native transcripts for the requested
        languages.  When ``include_translations`` is ``True``, languages
        without a native transcript are attempted via YouTube's translation
        API as a fallback.

        Parameters
        ----------
        video_id : VideoId
            YouTube video ID (validated VideoId type).
        language_codes : List[str]
            BCP-47 language codes to download (e.g., ['en', 'es', 'fr']).
        download_reason : DownloadReason
            Reason for downloading the transcripts.
        include_translations : bool
            When ``False`` (default), only native transcripts are fetched.
            When ``True``, languages without a native transcript are
            attempted via translation, which uses additional YouTube API
            calls and may trigger IP-based rate limiting.

        Returns
        -------
        Dict[str, Optional[EnhancedVideoTranscriptBase]]
            Mapping of language_code → transcript (or ``None`` if the language
            is not available for this video).
        """
        pass

    @abstractmethod
    def is_service_available(self) -> bool:
        """
        Check if the transcript service is available.

        Returns
        -------
        bool
            True if the service can provide transcripts (via API or mock).
        """
        pass
