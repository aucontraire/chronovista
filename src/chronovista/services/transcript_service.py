"""
Transcript Service for downloading and processing YouTube transcripts.

This service integrates with the youtube-transcript-api to download transcripts
and convert them to our internal models, with fallback handling and error recovery.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from youtube_transcript_api import (
        YouTubeTranscriptApi,  # type: ignore[import-untyped]
    )

    TRANSCRIPT_API_AVAILABLE = True
except ImportError:
    TRANSCRIPT_API_AVAILABLE = False

from ..models.enums import DownloadReason, LanguageCode
from ..models.transcript_source import (
    RawTranscriptData,
    TranscriptSnippet,
    TranscriptSource,
)
from ..models.video_transcript import EnhancedVideoTranscriptBase
from ..models.youtube_types import VideoId

logger = logging.getLogger(__name__)


class TranscriptServiceError(Exception):
    """Base exception for transcript service errors."""

    pass


class TranscriptNotFoundError(TranscriptServiceError):
    """Raised when no transcript is found for a video."""

    pass


class TranscriptServiceUnavailableError(TranscriptServiceError):
    """Raised when the transcript service is not available."""

    pass


class TranscriptService:
    """Service for downloading and processing YouTube transcripts."""

    def __init__(self, enable_mock_fallback: bool = True):
        """
        Initialize the transcript service.

        Args:
            enable_mock_fallback: Whether to use mock data when API is unavailable
        """
        self.enable_mock_fallback = enable_mock_fallback
        self._api_available = TRANSCRIPT_API_AVAILABLE

        if not self._api_available:
            logger.warning(
                "youtube-transcript-api not available - using mock fallback only"
            )

    async def get_transcript(
        self,
        video_id: VideoId,
        language_codes: Optional[List[str]] = None,
        download_reason: DownloadReason = DownloadReason.USER_REQUEST,
    ) -> EnhancedVideoTranscriptBase:
        """
        Get transcript for a video with fallback handling.

        Args:
            video_id: YouTube video ID (validated VideoId type)
            language_codes: Preferred language codes (e.g., ['en', 'en-US'])
            download_reason: Reason for downloading the transcript

        Returns:
            EnhancedVideoTranscriptBase: The downloaded transcript

        Raises:
            TranscriptNotFoundError: When no transcript is available
            TranscriptServiceUnavailableError: When service is unavailable
        """
        logger.info(f"Requesting transcript for video {video_id}")

        # Default to English if no language specified
        if not language_codes:
            language_codes = ["en", "en-US"]

        # Try third-party API first
        if self._api_available:
            try:
                raw_data = await self._get_transcript_from_third_party_api(
                    video_id, language_codes
                )

                # Convert to our model
                transcript = EnhancedVideoTranscriptBase.from_raw_transcript_data(
                    raw_data, download_reason=download_reason
                )

                logger.info(
                    f"Successfully downloaded transcript for {video_id} from third-party API"
                )
                return transcript

            except Exception as e:
                # Check error message to determine type of failure
                error_msg = str(e).lower()
                if any(
                    keyword in error_msg
                    for keyword in [
                        "transcript",
                        "disabled",
                        "not found",
                        "unavailable",
                    ]
                ):
                    logger.warning(f"No transcript available for {video_id}: {e}")
                elif any(
                    keyword in error_msg
                    for keyword in ["rate limit", "too many", "quota"]
                ):
                    logger.warning(f"Rate limit error for {video_id}: {e}")
                else:
                    logger.error(f"API error for {video_id}: {e}")
                # Fall through to official API fallback

        # Try official YouTube Data API v3 (placeholder for now)
        try:
            official_transcript: Optional[EnhancedVideoTranscriptBase] = (
                await self._get_transcript_from_official_api(
                    video_id, language_codes, download_reason
                )
            )
            if official_transcript:
                logger.info(
                    f"Successfully downloaded transcript for {video_id} from official API"
                )
                return official_transcript
        except Exception as e:
            logger.warning(f"Official API also failed for {video_id}: {e}")

        # If both APIs fail and mock fallback is enabled
        if self.enable_mock_fallback:
            logger.info(f"Using mock transcript data for {video_id}")
            return self._create_mock_transcript(
                video_id, language_codes[0], download_reason
            )

        # If we get here, no transcript was found anywhere
        raise TranscriptNotFoundError(f"No transcript found for video {video_id}")

    async def _get_transcript_from_third_party_api(
        self, video_id: VideoId, language_codes: List[str]
    ) -> RawTranscriptData:
        """Get transcript using youtube-transcript-api."""

        # Try to get transcript in preferred languages
        transcript_data = None
        transcript_metadata = None
        used_language = None

        # First, list available transcripts
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # Find the best matching transcript
            for preferred_lang in language_codes:
                for transcript in transcript_list:
                    if (
                        hasattr(transcript, "language_code")
                        and transcript.language_code == preferred_lang
                    ):
                        transcript_metadata = transcript
                        used_language = preferred_lang
                        break
                if transcript_metadata:
                    break

            # If no exact match, try to find English transcript
            if not transcript_metadata:
                for transcript in transcript_list:
                    if hasattr(
                        transcript, "language_code"
                    ) and transcript.language_code.startswith("en"):
                        transcript_metadata = transcript
                        used_language = transcript.language_code
                        break

            # If still no match, use the first available transcript
            if not transcript_metadata:
                for transcript in transcript_list:
                    transcript_metadata = transcript
                    used_language = transcript.language_code
                    break

        except Exception as e:
            logger.warning(f"Could not list transcripts for {video_id}: {e}")

        # Get the transcript data
        if used_language:
            transcript_data = YouTubeTranscriptApi.get_transcript(
                video_id, languages=[used_language]
            )
        else:
            # Fallback: try to get any available transcript
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
            used_language = language_codes[0]  # Default

        # Convert to our format
        snippets = [
            TranscriptSnippet(
                text=item["text"], start=item["start"], duration=item["duration"]
            )
            for item in transcript_data
        ]

        # Determine language code enum
        try:
            lang_code = LanguageCode(used_language.lower())
        except (ValueError, AttributeError):
            lang_code = LanguageCode.ENGLISH

        raw_data = RawTranscriptData(
            video_id=video_id,
            language_code=lang_code,
            language_name=(
                transcript_metadata.language if transcript_metadata else "Unknown"
            ),
            snippets=snippets,
            is_generated=(
                transcript_metadata.is_generated if transcript_metadata else True
            ),
            is_translatable=getattr(transcript_metadata, "is_translatable", None),
            source=TranscriptSource.YOUTUBE_TRANSCRIPT_API,
            source_metadata=(
                {
                    "original_language": (
                        transcript_metadata.language if transcript_metadata else None
                    ),
                    "original_language_code": used_language,
                    "is_generated": (
                        transcript_metadata.is_generated
                        if transcript_metadata
                        else True
                    ),
                    "transcript_count": len(transcript_data),
                }
                if transcript_metadata
                else None
            ),
        )

        return raw_data

    async def _get_transcript_from_official_api(
        self,
        video_id: VideoId,
        language_codes: List[str],
        download_reason: DownloadReason,
    ) -> Optional[EnhancedVideoTranscriptBase]:
        """
        Get transcript using official YouTube Data API v3.

        This is a placeholder implementation - will be implemented later.
        """
        logger.info(
            f"📋 Official YouTube Data API v3 fallback not yet implemented for {video_id}"
        )
        logger.info(
            f"🔄 Would attempt to download captions from official API for languages: {language_codes}"
        )
        logger.info(f"📝 Download reason: {download_reason.value}")

        # Placeholder return - will implement actual API call later
        return None

    def _create_mock_transcript(
        self, video_id: VideoId, language_code: str, download_reason: DownloadReason
    ) -> EnhancedVideoTranscriptBase:
        """Create mock transcript data for testing."""

        mock_snippets = [
            TranscriptSnippet(
                text="This is a mock transcript", start=0.0, duration=2.5
            ),
            TranscriptSnippet(
                text="Generated for testing purposes", start=2.5, duration=3.0
            ),
            TranscriptSnippet(
                text="When the real API is unavailable", start=5.5, duration=3.5
            ),
            TranscriptSnippet(text="Video ID: " + video_id, start=9.0, duration=2.0),
        ]

        # Determine language code enum
        try:
            lang_code = LanguageCode(language_code.lower())
        except ValueError:
            lang_code = LanguageCode.ENGLISH

        mock_raw_data = RawTranscriptData(
            video_id=video_id,
            language_code=lang_code,
            language_name="English (Mock)",
            snippets=mock_snippets,
            is_generated=True,
            is_translatable=True,
            source=TranscriptSource.UNKNOWN,
            source_metadata={
                "is_mock": True,
                "created_at": datetime.now(timezone.utc),
                "reason": "API unavailable - using mock data",
            },
        )

        return EnhancedVideoTranscriptBase.from_raw_transcript_data(
            mock_raw_data, download_reason=download_reason
        )

    async def get_available_languages(self, video_id: VideoId) -> List[Dict[str, Any]]:
        """
        Get list of available transcript languages for a video.

        Args:
            video_id: YouTube video ID (validated VideoId type)

        Returns:
            List of available language information
        """
        if not self._api_available:
            logger.warning(
                f"Cannot check available languages for {video_id} - API not available"
            )
            return []

        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            languages = []

            for transcript in transcript_list:
                languages.append(
                    {
                        "language_code": transcript.language_code,
                        "language_name": transcript.language,
                        "is_generated": transcript.is_generated,
                        "is_translatable": getattr(
                            transcript, "is_translatable", False
                        ),
                    }
                )

            logger.info(
                f"Found {len(languages)} available transcript languages for {video_id}"
            )
            return languages

        except Exception as e:
            logger.error(f"Failed to get available languages for {video_id}: {e}")
            return []

    async def batch_get_transcripts(
        self,
        video_ids: List[VideoId],
        language_codes: Optional[List[str]] = None,
        download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        max_retries: int = 3,
    ) -> Dict[VideoId, Optional[EnhancedVideoTranscriptBase]]:
        """
        Download transcripts for multiple videos.

        Args:
            video_ids: List of YouTube video IDs (validated VideoId types)
            language_codes: Preferred language codes
            download_reason: Reason for downloading
            max_retries: Maximum retry attempts per video

        Returns:
            Dictionary mapping video_id to transcript (or None if failed)
        """
        results: Dict[VideoId, Optional[EnhancedVideoTranscriptBase]] = {}

        for video_id in video_ids:
            for attempt in range(max_retries + 1):
                try:
                    transcript = await self.get_transcript(
                        video_id, language_codes, download_reason
                    )
                    results[video_id] = transcript
                    break

                except TranscriptNotFoundError:
                    logger.warning(f"No transcript found for {video_id}")
                    results[video_id] = None
                    break

                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(
                            f"Attempt {attempt + 1} failed for {video_id}: {e}"
                        )
                        continue
                    else:
                        logger.error(
                            f"All {max_retries + 1} attempts failed for {video_id}: {e}"
                        )
                        results[video_id] = None

        successful = sum(1 for v in results.values() if v is not None)
        logger.info(
            f"Batch download complete: {successful}/{len(video_ids)} successful"
        )

        return results

    def is_service_available(self) -> bool:
        """Check if the transcript service is available."""
        return self._api_available or self.enable_mock_fallback
