"""
Transcript Service for downloading and processing YouTube transcripts.

This service integrates with the youtube-transcript-api to download transcripts
and convert them to our internal models, with fallback handling and error recovery.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from youtube_transcript_api import FetchedTranscript, YouTubeTranscriptApi

try:
    from youtube_transcript_api import (
        FetchedTranscript,
        IpBlocked,
        RequestBlocked,
        YouTubeTranscriptApi,
    )

    TRANSCRIPT_API_AVAILABLE = True
except ImportError:
    YouTubeTranscriptApi = None  # type: ignore
    FetchedTranscript = None  # type: ignore
    RequestBlocked = None  # type: ignore
    IpBlocked = None  # type: ignore
    TRANSCRIPT_API_AVAILABLE = False

from ..models.enums import DownloadReason, LanguageCode
from ..models.transcript_source import (
    RawTranscriptData,
    TranscriptSnippet,
    TranscriptSource,
    resolve_language_code,
)
from ..models.video_transcript import EnhancedVideoTranscriptBase
from ..models.youtube_types import VideoId
from ..services.interfaces import TranscriptServiceInterface

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


class TranscriptService(TranscriptServiceInterface):
    """Service for downloading and processing YouTube transcripts."""

    def __init__(self, enable_mock_fallback: bool = False):
        """
        Initialize the transcript service.

        Args:
            enable_mock_fallback: Whether to use mock data when API is unavailable.
                Defaults to False so failed downloads don't create placeholder
                records. Set to True only in tests.
        """
        self.enable_mock_fallback = enable_mock_fallback
        self._api_available = TRANSCRIPT_API_AVAILABLE

        if not self._api_available:
            logger.warning(
                "youtube-transcript-api not available - transcript downloads will fail"
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
        # Try exact match first, then lowercase, then base language fallback
        lang_code = self._resolve_language_code(used_language)

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
                    snippet = caption.snippet
                    caption_lang = snippet.language.lower() if snippet else ""
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
            caption_id = best_caption.id
            snippet = best_caption.snippet

            caption_content = await youtube_service.download_caption(caption_id)

            if not caption_content:
                logger.warning(
                    f"Could not download caption content for {video_id} (likely permission issue)"
                )
                return None

            # Parse SRT content into our format
            snippets = self._parse_srt_content(caption_content)

            # Determine language code enum using centralized resolver
            caption_lang = snippet.language if snippet else "en"
            lang_code = self._resolve_language_code(caption_lang)

            # Create RawTranscriptData
            raw_data = RawTranscriptData(
                video_id=video_id,
                language_code=lang_code,
                language_name=snippet.name if snippet else f"Language ({caption_lang})",
                snippets=snippets,
                is_generated=(snippet.track_kind == "asr") if snippet else False,
                is_translatable=True,  # Official API captions are usually translatable
                source=TranscriptSource.YOUTUBE_DATA_API_V3,
                source_metadata={
                    "caption_id": caption_id,
                    "track_kind": snippet.track_kind if snippet else None,
                    "last_updated": snippet.last_updated.isoformat() if snippet and snippet.last_updated else None,
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

    def _resolve_language_code(self, language_code_str: str) -> Union[LanguageCode, str]:
        """
        Resolve a language code string to a LanguageCode enum or normalized string.

        Delegates to the shared resolve_language_code function but adds logging
        when fallback to English is used.

        Parameters
        ----------
        language_code_str : str
            Language code from API response (e.g., 'es-MX', 'en', 'zh-Hans')

        Returns
        -------
        Union[LanguageCode, str]
            LanguageCode enum value if known, otherwise normalized string code
        """
        result = resolve_language_code(language_code_str)

        # Log warning if we fell back to English from a non-English code
        if result == LanguageCode.ENGLISH and language_code_str and not language_code_str.lower().startswith("en"):
            logger.warning(
                f"Could not resolve language code '{language_code_str}' to LanguageCode enum, "
                f"falling back to ENGLISH. Consider adding this language code to the enum."
            )

        return result

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

        # Determine language code enum using the centralized resolver
        lang_code = self._resolve_language_code(language_code)

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

    def _convert_fetched_to_raw_data(
        self,
        video_id: VideoId,
        used_language_code: str,
        language_name: str,
        is_generated: bool,
        is_translatable: bool,
        transcript_data: List[Dict[str, Any]],
    ) -> RawTranscriptData:
        """
        Convert raw snippet dicts from ``youtube-transcript-api`` into a
        ``RawTranscriptData`` model.

        This helper centralises the conversion logic that was previously
        duplicated between the direct-fetch and list-fallback paths inside
        ``_get_transcript_from_third_party_api()``.

        Parameters
        ----------
        video_id : VideoId
            YouTube video ID.
        used_language_code : str
            The language code returned by the API (e.g. ``'en'``, ``'es-MX'``).
        language_name : str
            Human-readable language name from the API (e.g. ``'English'``).
        is_generated : bool
            Whether the transcript was auto-generated by YouTube.
        is_translatable : bool
            Whether the transcript can be translated via the API.
        transcript_data : List[Dict[str, Any]]
            List of ``{'text': str, 'start': float, 'duration': float}`` dicts.

        Returns
        -------
        RawTranscriptData
            Fully validated transcript data ready for persistence.
        """
        snippets = []
        for item in transcript_data:
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
            snippets.append(TranscriptSnippet(text=text, start=start, duration=duration))

        lang_code = self._resolve_language_code(used_language_code)

        return RawTranscriptData(
            video_id=video_id,
            language_code=lang_code,
            language_name=language_name,
            snippets=snippets,
            is_generated=is_generated,
            is_translatable=is_translatable,
            source=TranscriptSource.YOUTUBE_TRANSCRIPT_API,
            source_metadata={
                "original_language": language_name,
                "original_language_code": used_language_code,
                "is_generated": is_generated,
                "transcript_count": len(transcript_data),
                "api_version": "1.2.2+",
            },
        )

    @staticmethod
    def _is_ip_block_error(exc: Exception) -> bool:
        """
        Return True when *exc* indicates YouTube is blocking requests from this IP.

        Checks both the exception type (``RequestBlocked`` / ``IpBlocked`` from
        youtube-transcript-api) and the error message string as a secondary
        guard for cases where the exception is wrapped or re-raised as a generic
        type.

        Parameters
        ----------
        exc : Exception
            The exception to inspect.

        Returns
        -------
        bool
            True if the failure is attributable to an IP-level block.
        """
        # Primary check: named exception types from youtube-transcript-api
        if RequestBlocked is not None and isinstance(exc, RequestBlocked):
            return True
        # Secondary check: message-based heuristic for wrapped exceptions
        error_msg = str(exc)
        ip_block_phrases = (
            "blocking requests",
            "ip blocked",
            "ipblocked",
            "requestblocked",
            "your ip",
        )
        return any(phrase in error_msg.lower() for phrase in ip_block_phrases)

    async def get_transcripts_for_languages(
        self,
        video_id: VideoId,
        language_codes: List[str],
        download_reason: DownloadReason = DownloadReason.USER_REQUEST,
    ) -> Dict[str, Optional[EnhancedVideoTranscriptBase]]:
        """
        Get transcripts for multiple languages with minimal API calls.

        Calls ``api.list()`` exactly once, builds a map of available native
        transcripts, and then for each requested language either fetches the
        native transcript directly, falls back to translation from the best
        available source, or records ``None`` if the language is unavailable.

        This reduces YouTube API calls from ``O(N)`` (one ``api.fetch()`` per
        language) to ``1 + O(fetches)`` — typically 1–3 total calls regardless
        of how many languages are requested.

        When the third-party API is not installed (``self._api_available`` is
        ``False``), falls back to calling ``get_transcript()`` per language so
        that mock/test environments continue to work.

        Parameters
        ----------
        video_id : VideoId
            YouTube video ID (validated VideoId type).
        language_codes : List[str]
            BCP-47 language codes to download (e.g., ``['en', 'es', 'fr']``).
        download_reason : DownloadReason
            Reason for downloading the transcripts.

        Returns
        -------
        Dict[str, Optional[EnhancedVideoTranscriptBase]]
            Mapping of language_code → transcript, or ``None`` if the language
            is not available for this video.
        """
        results: Dict[str, Optional[EnhancedVideoTranscriptBase]] = {}

        if not language_codes:
            return results

        # --- API unavailable: degrade gracefully to per-language calls ---
        if not self._api_available or YouTubeTranscriptApi is None:
            logger.warning(
                "youtube-transcript-api not available; falling back to "
                "per-language get_transcript() calls for video %s",
                video_id,
            )
            for lang_code in language_codes:
                try:
                    results[lang_code] = await self.get_transcript(
                        video_id=video_id,
                        language_codes=[lang_code],
                        download_reason=download_reason,
                    )
                except TranscriptNotFoundError:
                    logger.info(
                        "No transcript available in '%s' for video %s — skipped",
                        lang_code,
                        video_id,
                    )
                    results[lang_code] = None
                except Exception:
                    logger.warning(
                        "Failed to download '%s' transcript for video %s",
                        lang_code,
                        video_id,
                        exc_info=True,
                    )
                    results[lang_code] = None
            return results

        # --- Single api.list() call ---
        try:
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)
        except Exception as exc:
            if self._is_ip_block_error(exc):
                # YouTube is blocking this IP — every subsequent call will also
                # fail, so we must NOT loop through all languages.  Attempt one
                # final English-only fetch as a last resort, then give up.
                logger.error(
                    "api.list() for video %s failed due to IP block (%s). "
                    "Skipping per-language fallback to avoid burning request budget. "
                    "Attempting single English fetch as last resort.",
                    video_id,
                    exc,
                )
                try:
                    results["en"] = await self.get_transcript(
                        video_id=video_id,
                        language_codes=["en", "en-US"],
                        download_reason=download_reason,
                    )
                    logger.info(
                        "Last-resort English fetch succeeded for video %s",
                        video_id,
                    )
                except Exception as en_exc:
                    logger.warning(
                        "Last-resort English fetch also failed for video %s: %s — "
                        "all languages set to None",
                        video_id,
                        en_exc,
                    )
                    results["en"] = None
                # Mark every other requested language as unavailable
                for lang_code in language_codes:
                    if lang_code not in results:
                        results[lang_code] = None
                # If ALL results are None, IP blocking is the dominant failure
                # mode — raise so callers (e.g. the router) can return 503
                # instead of a misleading 404.
                if all(v is None for v in results.values()):
                    raise TranscriptServiceUnavailableError(
                        "YouTube is temporarily blocking requests from this IP "
                        "address. Please try again later."
                    )
                return results

            # Non-IP-block failure: keep the per-language fallback but terminate
            # early if consecutive IP-block errors accumulate.
            logger.error(
                "api.list() failed for video %s: %s — falling back to "
                "per-language get_transcript() calls",
                video_id,
                exc,
            )
            consecutive_ip_blocks = 0
            for lang_code in language_codes:
                if consecutive_ip_blocks >= 2:
                    logger.error(
                        "Stopping per-language fallback for video %s after %d "
                        "consecutive IP-block errors — remaining languages set to None",
                        video_id,
                        consecutive_ip_blocks,
                    )
                    results[lang_code] = None
                    continue
                try:
                    results[lang_code] = await self.get_transcript(
                        video_id=video_id,
                        language_codes=[lang_code],
                        download_reason=download_reason,
                    )
                    consecutive_ip_blocks = 0
                except TranscriptNotFoundError:
                    logger.info(
                        "No transcript available in '%s' for video %s — skipped",
                        lang_code,
                        video_id,
                    )
                    results[lang_code] = None
                    consecutive_ip_blocks = 0
                except Exception as lang_exc:
                    if self._is_ip_block_error(lang_exc):
                        consecutive_ip_blocks += 1
                        logger.warning(
                            "IP block detected on '%s' fetch for video %s "
                            "(consecutive=%d): %s",
                            lang_code,
                            video_id,
                            consecutive_ip_blocks,
                            lang_exc,
                        )
                    else:
                        consecutive_ip_blocks = 0
                        logger.warning(
                            "Failed to download '%s' transcript for video %s",
                            lang_code,
                            video_id,
                            exc_info=True,
                        )
                    results[lang_code] = None
            # If ALL results are None AND IP blocking was detected (>=2
            # consecutive), raise so callers can return 503 instead of 404.
            if (
                consecutive_ip_blocks >= 2
                and results
                and all(v is None for v in results.values())
            ):
                raise TranscriptServiceUnavailableError(
                    "YouTube is temporarily blocking requests from this IP "
                    "address. Please try again later."
                )
            return results

        # Build a map of native transcripts: language_code (lower) → Transcript
        native_map: Dict[str, Any] = {}
        for transcript in transcript_list:
            lc = transcript.language_code.lower()
            # Prefer manual (non-generated) transcripts if there is a duplicate
            if lc not in native_map or not transcript.is_generated:
                native_map[lc] = transcript

        # Identify the best translation source: prefer manual over auto-generated
        translation_source: Optional[Any] = None
        for _lc, t in native_map.items():
            if not t.is_generated and getattr(t, "is_translatable", False):
                translation_source = t
                break
        if translation_source is None:
            # Fall back to any translatable transcript
            for _lc, t in native_map.items():
                if getattr(t, "is_translatable", False):
                    translation_source = t
                    break

        # --- Fetch each requested language ---
        consecutive_ip_blocks = 0
        for lang_code in language_codes:
            # Early-terminate if we have seen 2+ consecutive IP-block errors.
            # Remaining languages are all going to fail for the same reason.
            if consecutive_ip_blocks >= 2:
                logger.error(
                    "Stopping language fetch loop for video %s after %d consecutive "
                    "IP-block errors — remaining languages set to None",
                    video_id,
                    consecutive_ip_blocks,
                )
                results[lang_code] = None
                continue

            lc_lower = lang_code.lower()
            try:
                if lc_lower in native_map:
                    # Native match: fetch it directly (1 API call)
                    native_t = native_map[lc_lower]
                    fetched = native_t.fetch()
                    transcript_data = [
                        {
                            "text": str(snippet.text),
                            "start": float(snippet.start),
                            "duration": float(snippet.duration),
                        }
                        for snippet in fetched
                    ]
                    raw_data = self._convert_fetched_to_raw_data(
                        video_id=video_id,
                        used_language_code=native_t.language_code,
                        language_name=native_t.language,
                        is_generated=native_t.is_generated,
                        is_translatable=getattr(native_t, "is_translatable", True),
                        transcript_data=transcript_data,
                    )
                    results[lang_code] = EnhancedVideoTranscriptBase.from_raw_transcript_data(
                        raw_data, download_reason=download_reason
                    )
                    logger.info(
                        "Downloaded native '%s' transcript for video %s",
                        lang_code,
                        video_id,
                    )
                    consecutive_ip_blocks = 0

                elif translation_source is not None:
                    # Attempt translation (1 API call)
                    translated_t = translation_source.translate(lang_code)
                    fetched = translated_t.fetch()
                    transcript_data = [
                        {
                            "text": str(snippet.text),
                            "start": float(snippet.start),
                            "duration": float(snippet.duration),
                        }
                        for snippet in fetched
                    ]
                    raw_data = self._convert_fetched_to_raw_data(
                        video_id=video_id,
                        used_language_code=lang_code,
                        language_name=getattr(translated_t, "language", lang_code),
                        is_generated=getattr(
                            translated_t, "is_generated", translation_source.is_generated
                        ),
                        is_translatable=False,  # translated transcripts cannot be re-translated
                        transcript_data=transcript_data,
                    )
                    results[lang_code] = EnhancedVideoTranscriptBase.from_raw_transcript_data(
                        raw_data, download_reason=download_reason
                    )
                    logger.info(
                        "Downloaded translated '%s' transcript for video %s",
                        lang_code,
                        video_id,
                    )
                    consecutive_ip_blocks = 0

                else:
                    # No native match and no translation source available
                    logger.info(
                        "No transcript available in '%s' for video %s — skipped",
                        lang_code,
                        video_id,
                    )
                    results[lang_code] = None

            except Exception as exc:
                if self._is_ip_block_error(exc):
                    consecutive_ip_blocks += 1
                    logger.error(
                        "IP block detected while fetching '%s' transcript for "
                        "video %s (consecutive=%d): %s",
                        lang_code,
                        video_id,
                        consecutive_ip_blocks,
                        exc,
                    )
                    results[lang_code] = None
                else:
                    consecutive_ip_blocks = 0
                    error_msg = str(exc).lower()
                    if any(
                        kw in error_msg
                        for kw in ["transcript", "disabled", "not found", "unavailable", "no translation"]
                    ):
                        logger.info(
                            "No transcript available in '%s' for video %s: %s — skipped",
                            lang_code,
                            video_id,
                            exc,
                        )
                    else:
                        logger.warning(
                            "Failed to download '%s' transcript for video %s: %s",
                            lang_code,
                            video_id,
                            exc,
                        )
                    results[lang_code] = None

        # If ALL results are None AND IP blocking was the dominant failure,
        # raise so callers can return 503 instead of a misleading 404.
        if (
            consecutive_ip_blocks >= 2
            and results
            and all(v is None for v in results.values())
        ):
            raise TranscriptServiceUnavailableError(
                "YouTube is temporarily blocking requests from this IP "
                "address. Please try again later."
            )

        return results

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

    def _update_segment_text(
        self,
        segment: Any,
        new_text: str,
        force_overwrite: bool = False,
    ) -> None:
        """
        Update a transcript segment's raw text with re-download protection.

        Implements FR-015 and FR-016 from Feature 033: if a segment has an
        existing manual correction (has_correction=True), the corrected_text is
        preserved by default so that human corrections are not silently lost
        during a transcript re-download.

        Parameters
        ----------
        segment : Any
            ORM or domain object with attributes: ``text``, ``corrected_text``,
            ``has_correction``.  Mutated in-place.
        new_text : str
            The fresh raw text from the re-downloaded transcript.
        force_overwrite : bool, optional
            When True, bypass correction protection: clear ``corrected_text``,
            set ``has_correction = False``, and update ``text`` with
            ``new_text``.  Callers MUST recompute the parent transcript's
            ``has_corrections`` / ``correction_count`` after processing all
            segments.  Defaults to False.

        Notes
        -----
        - When *force_overwrite* is False and the segment has a correction, a
          WARNING is logged about the divergence between raw and corrected text
          (FR-016).
        - When *force_overwrite* is True, an INFO message is logged.
        - When the segment has no correction, the update proceeds silently.
        - This method does **not** touch the database; it only mutates the
          in-memory object.  The caller is responsible for flushing/committing.
        - Recomputation of transcript-level ``has_corrections`` and
          ``correction_count`` after a force-overwrite is the caller's
          responsibility (EC-FORCE-OVERWRITE-AUDIT).
        """
        if segment.has_correction:
            if force_overwrite:
                logger.info(
                    "Segment %s: force-overwrite requested; "
                    "clearing corrected_text and resetting has_correction",
                    getattr(segment, "id", "<unknown>"),
                )
                segment.text = new_text
                segment.corrected_text = None
                segment.has_correction = False
            else:
                # FR-015: preserve corrected_text; only update the raw column
                # FR-016: warn about divergence between raw and corrected text
                logger.warning(
                    "Segment %s has correction; raw text updated but "
                    "corrected_text preserved",
                    getattr(segment, "id", "<unknown>"),
                )
                segment.text = new_text
                # corrected_text intentionally left unchanged
        else:
            # No correction — update normally
            segment.text = new_text

    def is_service_available(self) -> bool:
        """Check if the transcript service is available."""
        return self._api_available or self.enable_mock_fallback
