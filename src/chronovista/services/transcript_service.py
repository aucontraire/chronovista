"""
Transcript Service for downloading and processing YouTube transcripts.

This service integrates with the youtube-transcript-api to download transcripts
and convert them to our internal models, with fallback handling and error recovery.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from youtube_transcript_api import FetchedTranscript, YouTubeTranscriptApi

try:
    from youtube_transcript_api import FetchedTranscript, YouTubeTranscriptApi

    TRANSCRIPT_API_AVAILABLE = True
except ImportError:
    YouTubeTranscriptApi = None  # type: ignore
    FetchedTranscript = None  # type: ignore
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
        """Get transcript using youtube-transcript-api (v1.2.2+ API)."""

        if YouTubeTranscriptApi is None:
            raise TranscriptServiceUnavailableError(
                "youtube-transcript-api not available"
            )

        api = YouTubeTranscriptApi()

        # Try to get transcript directly with preferred languages
        try:
            if FetchedTranscript is None:
                raise TranscriptServiceUnavailableError(
                    "FetchedTranscript type not available"
                )

            fetched_transcript_result = api.fetch(video_id, languages=language_codes)

            if fetched_transcript_result is None:
                raise Exception("No transcript data returned")

            # Extract transcript data from the fetched transcript
            transcript_data = []
            for snippet in fetched_transcript_result:
                transcript_data.append(
                    {
                        "text": str(snippet.text),
                        "start": float(snippet.start),
                        "duration": float(snippet.duration),
                    }
                )

            # Get metadata
            used_language = fetched_transcript_result.language_code
            is_generated = fetched_transcript_result.is_generated
            is_translatable = (
                True  # FetchedTranscript doesn't have is_translatable, default to True
            )
            language_name = (
                fetched_transcript_result.language
            )  # Use 'language' instead of 'language_name'

        except Exception as e:
            logger.warning(f"Direct fetch failed for {video_id}: {e}")

            # Fallback: list available transcripts and pick the best one
            try:
                transcript_list = api.list(video_id)

                # Try to find transcript in preferred languages
                transcript = None
                for lang in language_codes:
                    try:
                        transcript = transcript_list.find_transcript([lang])
                        break
                    except Exception:
                        continue

                # If no preferred language found, try any English variant
                if not transcript:
                    try:
                        transcript = transcript_list.find_transcript(["en"])
                    except Exception:
                        pass

                # If still no transcript, get any available generated transcript
                if not transcript:
                    try:
                        transcript = transcript_list.find_generated_transcript(
                            language_codes
                        )
                    except Exception:
                        pass

                # Last resort: get any available transcript
                if not transcript:
                    # Get first available transcript
                    for t in transcript_list:
                        transcript = t
                        break

                if not transcript:
                    raise Exception("No transcripts available")

                # Fetch the transcript content
                fetched_transcript_content = transcript.fetch()

                if fetched_transcript_content is None:
                    raise Exception("No transcript content returned")

                # Extract data
                transcript_data = []
                for snippet in fetched_transcript_content:
                    transcript_data.append(
                        {
                            "text": str(snippet.text),
                            "start": float(snippet.start),
                            "duration": float(snippet.duration),
                        }
                    )

                used_language = transcript.language_code
                is_generated = transcript.is_generated
                is_translatable = transcript.is_translatable
                language_name = transcript.language

            except Exception as fallback_error:
                logger.error(
                    f"All transcript approaches failed for {video_id}: {fallback_error}"
                )
                raise

        # Convert to our format
        snippets = []
        for item in transcript_data:
            # Ensure proper types with validation
            text = str(item["text"]) if item["text"] is not None else ""
            start = (
                float(item["start"])
                if isinstance(item["start"], (int, float, str))
                else 0.0
            )
            duration = (
                float(item["duration"])
                if isinstance(item["duration"], (int, float, str))
                else 0.0
            )

            snippets.append(
                TranscriptSnippet(text=text, start=start, duration=duration)
            )

        # Determine language code enum
        try:
            lang_code = LanguageCode(used_language.lower())
        except (ValueError, AttributeError):
            lang_code = LanguageCode.ENGLISH

        raw_data = RawTranscriptData(
            video_id=video_id,
            language_code=lang_code,
            language_name=language_name,
            snippets=snippets,
            is_generated=is_generated,
            is_translatable=is_translatable,
            source=TranscriptSource.YOUTUBE_TRANSCRIPT_API,
            source_metadata={
                "original_language": language_name,
                "original_language_code": used_language,
                "is_generated": is_generated,
                "transcript_count": len(transcript_data),
                "api_version": "1.2.2+",
            },
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

        Note: This only works for videos owned by the authenticated user
        or videos that have explicitly enabled third-party caption access.
        """
        try:
            from ..services.youtube_service import youtube_service

            logger.info(f"📋 Attempting official YouTube Data API v3 for {video_id}")

            # Get available captions
            captions = await youtube_service.get_video_captions(video_id)
            if not captions:
                logger.info(f"No captions found via official API for {video_id}")
                return None

            # Find best matching caption
            best_caption = None
            for language_code in language_codes:
                for caption in captions:
                    snippet = caption.get("snippet", {})
                    caption_lang = snippet.get("language", "").lower()
                    if caption_lang == language_code.lower():
                        best_caption = caption
                        break
                if best_caption:
                    break

            # If no exact match, try the first available caption
            if not best_caption and captions:
                best_caption = captions[0]

            if not best_caption:
                logger.info(f"No suitable caption found for {video_id}")
                return None

            # Try to download caption content
            caption_id = best_caption.get("id")
            snippet = best_caption.get("snippet", {})

            if caption_id is None:
                logger.warning(f"No caption ID found for {video_id}")
                return None

            caption_content = await youtube_service.download_caption(caption_id)

            if not caption_content:
                logger.warning(
                    f"Could not download caption content for {video_id} (likely permission issue)"
                )
                return None

            # Parse SRT content into our format
            snippets = self._parse_srt_content(caption_content)

            # Determine language code enum
            caption_lang = snippet.get("language", "en").lower()
            try:
                lang_code = LanguageCode(caption_lang)
            except ValueError:
                lang_code = LanguageCode.ENGLISH

            # Create RawTranscriptData
            raw_data = RawTranscriptData(
                video_id=video_id,
                language_code=lang_code,
                language_name=snippet.get("name", f"Language ({caption_lang})"),
                snippets=snippets,
                is_generated=snippet.get("trackKind") == "asr",
                is_translatable=True,  # Official API captions are usually translatable
                source=TranscriptSource.YOUTUBE_DATA_API_V3,
                source_metadata={
                    "caption_id": caption_id,
                    "track_kind": snippet.get("trackKind"),
                    "last_updated": snippet.get("lastUpdated"),
                    "download_format": "srt",
                },
            )

            # Convert to our enhanced model
            transcript = EnhancedVideoTranscriptBase.from_raw_transcript_data(
                raw_data, download_reason=download_reason
            )

            logger.info(
                f"✅ Successfully downloaded transcript for {video_id} from official API"
            )
            return transcript

        except Exception as e:
            logger.warning(f"Official API failed for {video_id}: {e}")
            return None

    def _parse_srt_content(self, srt_content: str) -> List[TranscriptSnippet]:
        """
        Parse SRT format content into TranscriptSnippet objects.

        Args:
            srt_content: SRT format caption content

        Returns:
            List of TranscriptSnippet objects
        """
        snippets = []
        lines = srt_content.strip().split("\n")

        i = 0
        while i < len(lines):
            # Skip empty lines
            if not lines[i].strip():
                i += 1
                continue

            # Skip sequence number line
            if lines[i].strip().isdigit():
                i += 1
                if i >= len(lines):
                    break

            # Parse timestamp line (format: 00:00:00,000 --> 00:00:03,000)
            if i < len(lines) and "-->" in lines[i]:
                timestamp_line = lines[i].strip()
                try:
                    start_str, end_str = timestamp_line.split(" --> ")
                    start_time = self._parse_srt_timestamp(start_str)
                    end_time = self._parse_srt_timestamp(end_str)
                    duration = end_time - start_time

                    i += 1

                    # Collect text lines until next empty line or end
                    text_lines = []
                    while i < len(lines) and lines[i].strip():
                        text_lines.append(lines[i].strip())
                        i += 1

                    if text_lines:
                        text = " ".join(text_lines)
                        snippet = TranscriptSnippet(
                            text=text, start=start_time, duration=duration
                        )
                        snippets.append(snippet)

                except (ValueError, IndexError) as e:
                    logger.warning(
                        f"Could not parse SRT timestamp: {timestamp_line} - {e}"
                    )
                    i += 1
            else:
                i += 1

        return snippets

    def _parse_srt_timestamp(self, timestamp_str: str) -> float:
        """
        Parse SRT timestamp format (HH:MM:SS,mmm) to seconds.

        Args:
            timestamp_str: Timestamp in SRT format

        Returns:
            Timestamp in seconds as float
        """
        # Format: 00:00:12,345
        time_part, ms_part = timestamp_str.split(",")
        hours, minutes, seconds = map(int, time_part.split(":"))
        milliseconds = int(ms_part)

        total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
        return total_seconds

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
        if not self._api_available or YouTubeTranscriptApi is None:
            logger.warning(
                f"Cannot check available languages for {video_id} - API not available"
            )
            return []

        try:
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)
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
