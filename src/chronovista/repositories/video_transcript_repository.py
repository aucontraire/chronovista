"""
Video transcript repository.

Provides data access layer for video transcripts with multi-language support,
quality indicators, and specialized queries for transcript management.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db.models import TranscriptSegment as TranscriptSegmentDB
from ..db.models import Video as VideoDB
from ..db.models import VideoTranscript as VideoTranscriptDB
from ..models.enums import DownloadReason, LanguageCode, TrackKind, TranscriptType
from ..models.video_transcript import (
    TranscriptSearchFilters,
    VideoTranscript,
    VideoTranscriptCreate,
    VideoTranscriptUpdate,
    VideoTranscriptWithQuality,
)
from ..models.youtube_types import VideoId
from .base import BaseSQLAlchemyRepository

logger = logging.getLogger(__name__)


class VideoTranscriptRepository(
    BaseSQLAlchemyRepository[
        VideoTranscriptDB,
        VideoTranscriptCreate,
        VideoTranscriptUpdate,
        Tuple[str, str],
    ]
):
    """Repository for video transcripts with multi-language and quality support."""

    def __init__(self) -> None:
        """Initialize repository with VideoTranscript model."""
        super().__init__(VideoTranscriptDB)

    async def get(
        self, session: AsyncSession, id: Tuple[str, str]
    ) -> Optional[VideoTranscriptDB]:
        """
        Get video transcript by composite primary key.

        Parameters
        ----------
        session : AsyncSession
            Database session
        id : Tuple[str, str]
            Composite key (video_id, language_code)

        Returns
        -------
        Optional[VideoTranscriptDB]
            Video transcript if found, None otherwise
        """
        video_id, language_code = id
        result = await session.execute(
            select(VideoTranscriptDB).where(
                and_(
                    VideoTranscriptDB.video_id == video_id,
                    VideoTranscriptDB.language_code == language_code.lower(),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_composite_key(
        self, session: AsyncSession, video_id: VideoId, language_code: str
    ) -> Optional[VideoTranscriptDB]:
        """
        Get video transcript by composite primary key (convenience method).

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : str
            YouTube video identifier
        language_code : str
            BCP-47 language code

        Returns
        -------
        Optional[VideoTranscriptDB]
            Video transcript if found, None otherwise
        """
        return await self.get(session, (video_id, language_code))

    async def exists(self, session: AsyncSession, id: Tuple[str, str]) -> bool:
        """
        Check if video transcript exists.

        Parameters
        ----------
        session : AsyncSession
            Database session
        id : Tuple[str, str]
            Composite key (video_id, language_code)

        Returns
        -------
        bool
            True if transcript exists, False otherwise
        """
        video_id, language_code = id
        result = await session.execute(
            select(VideoTranscriptDB.video_id).where(
                and_(
                    VideoTranscriptDB.video_id == video_id,
                    VideoTranscriptDB.language_code == language_code.lower(),
                )
            )
        )
        return result.first() is not None

    async def exists_by_composite_key(
        self, session: AsyncSession, video_id: VideoId, language_code: str
    ) -> bool:
        """
        Check if video transcript exists (convenience method).

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : str
            YouTube video identifier
        language_code : str
            BCP-47 language code

        Returns
        -------
        bool
            True if transcript exists, False otherwise
        """
        return await self.exists(session, (video_id, language_code))

    async def get_video_transcripts(
        self, session: AsyncSession, video_id: VideoId
    ) -> List[VideoTranscriptDB]:
        """
        Get all transcripts for a specific video, ordered by quality.

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : str
            YouTube video identifier

        Returns
        -------
        List[VideoTranscriptDB]
            List of video transcripts ordered by quality (CC first, then by confidence)
        """
        result = await session.execute(
            select(VideoTranscriptDB)
            .where(VideoTranscriptDB.video_id == video_id)
            .order_by(
                VideoTranscriptDB.is_cc.desc(),  # Closed captions first
                VideoTranscriptDB.confidence_score.desc().nulls_last(),  # High confidence first
                VideoTranscriptDB.transcript_type.asc(),  # MANUAL before AUTO
            )
        )
        return list(result.scalars().all())

    async def get_transcripts_by_language(
        self, session: AsyncSession, language_code: str, limit: Optional[int] = None
    ) -> List[VideoTranscriptDB]:
        """
        Get all transcripts for a specific language.

        Parameters
        ----------
        session : AsyncSession
            Database session
        language_code : str
            BCP-47 language code
        limit : Optional[int]
            Maximum number of results to return

        Returns
        -------
        List[VideoTranscriptDB]
            List of transcripts in the specified language
        """
        query = (
            select(VideoTranscriptDB)
            .where(VideoTranscriptDB.language_code == language_code.lower())
            .order_by(VideoTranscriptDB.downloaded_at.desc())
        )

        if limit:
            query = query.limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_high_quality_transcripts(
        self, session: AsyncSession, video_id: VideoId
    ) -> List[VideoTranscriptDB]:
        """
        Get high-quality transcripts for a video (CC, manual, or high confidence).

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : str
            YouTube video identifier

        Returns
        -------
        List[VideoTranscriptDB]
            List of high-quality transcripts
        """
        result = await session.execute(
            select(VideoTranscriptDB)
            .where(
                and_(
                    VideoTranscriptDB.video_id == video_id,
                    or_(
                        VideoTranscriptDB.is_cc.is_(True),
                        VideoTranscriptDB.transcript_type
                        == TranscriptType.MANUAL.value,
                        VideoTranscriptDB.confidence_score >= 0.8,
                    ),
                )
            )
            .order_by(
                VideoTranscriptDB.is_cc.desc(),
                VideoTranscriptDB.confidence_score.desc().nulls_last(),
            )
        )
        return list(result.scalars().all())

    async def search_transcripts(
        self, session: AsyncSession, filters: TranscriptSearchFilters
    ) -> List[VideoTranscriptDB]:
        """
        Search transcripts with advanced filtering.

        Parameters
        ----------
        session : AsyncSession
            Database session
        filters : TranscriptSearchFilters
            Search filters to apply

        Returns
        -------
        List[VideoTranscriptDB]
            List of matching transcripts
        """
        query = select(VideoTranscriptDB)
        conditions: List[Any] = []

        # Video ID filters
        if filters.video_ids:
            conditions.append(VideoTranscriptDB.video_id.in_(filters.video_ids))

        # Language filters
        if filters.language_codes:
            normalized_langs = [lang.lower() for lang in filters.language_codes]
            conditions.append(VideoTranscriptDB.language_code.in_(normalized_langs))

        # Type filters
        if filters.transcript_types:
            # Handle both enum objects and string values
            type_values = []
            for t in filters.transcript_types:
                if hasattr(t, "value"):
                    type_values.append(t.value)
                else:
                    type_values.append(str(t))
            conditions.append(VideoTranscriptDB.transcript_type.in_(type_values))

        # Download reason filters
        if filters.download_reasons:
            # Handle both enum objects and string values
            reason_values = []
            for r in filters.download_reasons:
                if hasattr(r, "value"):
                    reason_values.append(r.value)
                else:
                    reason_values.append(str(r))
            conditions.append(VideoTranscriptDB.download_reason.in_(reason_values))

        # Track kind filters
        if filters.track_kinds:
            # Handle both enum objects and string values
            kind_values = []
            for k in filters.track_kinds:
                if hasattr(k, "value"):
                    kind_values.append(k.value)
                else:
                    kind_values.append(str(k))
            conditions.append(VideoTranscriptDB.track_kind.in_(kind_values))

        # Quality filters
        if filters.min_confidence is not None:
            conditions.append(
                VideoTranscriptDB.confidence_score >= filters.min_confidence
            )

        if filters.is_cc_only:
            conditions.append(VideoTranscriptDB.is_cc.is_(True))

        if filters.is_manual_only:
            conditions.append(VideoTranscriptDB.is_auto_synced.is_(False))

        # Date filters
        if filters.downloaded_after:
            conditions.append(
                VideoTranscriptDB.downloaded_at >= filters.downloaded_after
            )

        if filters.downloaded_before:
            conditions.append(
                VideoTranscriptDB.downloaded_at <= filters.downloaded_before
            )

        # Apply all conditions
        if conditions:
            query = query.where(and_(*conditions))

        # Default ordering by quality and recency
        query = query.order_by(
            VideoTranscriptDB.is_cc.desc(),
            VideoTranscriptDB.confidence_score.desc().nulls_last(),
            VideoTranscriptDB.downloaded_at.desc(),
        )

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_available_languages(
        self, session: AsyncSession, video_id: VideoId
    ) -> List[str]:
        """
        Get list of available languages for a video.

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : str
            YouTube video identifier

        Returns
        -------
        List[str]
            List of available language codes
        """
        result = await session.execute(
            select(VideoTranscriptDB.language_code)
            .where(VideoTranscriptDB.video_id == video_id)
            .distinct()
            .order_by(VideoTranscriptDB.language_code.asc())
        )
        return [lang for lang in result.scalars().all()]

    async def get_transcript_statistics(
        self, session: AsyncSession, video_id: Optional[VideoId] = None
    ) -> Dict[str, Any]:
        """
        Get transcript statistics by type and language.

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : Optional[str]
            Specific video ID to get stats for, or None for global stats

        Returns
        -------
        Dict[str, Any]
            Statistics about transcripts (by type, language, quality)
        """
        query = select(
            VideoTranscriptDB.transcript_type,
            VideoTranscriptDB.language_code,
            VideoTranscriptDB.is_cc,
            func.count().label("count"),
        )

        if video_id:
            query = query.where(VideoTranscriptDB.video_id == video_id)

        query = query.group_by(
            VideoTranscriptDB.transcript_type,
            VideoTranscriptDB.language_code,
            VideoTranscriptDB.is_cc,
        )

        result = await session.execute(query)

        stats: Dict[str, Any] = {
            "total": 0,
            "by_type": {},
            "by_language": {},
            "cc_count": 0,
            "auto_count": 0,
        }

        for transcript_type, language_code, is_cc, count in result:
            count_int = int(count)
            stats["total"] += count_int

            # By type
            by_type_dict = stats["by_type"]
            if transcript_type not in by_type_dict:
                by_type_dict[transcript_type] = 0
            by_type_dict[transcript_type] += count_int

            # By language
            by_language_dict = stats["by_language"]
            if language_code not in by_language_dict:
                by_language_dict[language_code] = 0
            by_language_dict[language_code] += count_int

            # By quality
            if is_cc:
                stats["cc_count"] += count_int
            else:
                stats["auto_count"] += count_int

        return stats

    async def delete_video_transcripts(
        self, session: AsyncSession, video_id: VideoId
    ) -> int:
        """
        Delete all transcripts for a specific video.

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : str
            YouTube video identifier

        Returns
        -------
        int
            Number of transcripts deleted
        """
        result = await session.execute(
            delete(VideoTranscriptDB).where(VideoTranscriptDB.video_id == video_id)
        )
        return result.rowcount

    async def delete_transcript_by_language(
        self, session: AsyncSession, video_id: VideoId, language_code: str
    ) -> bool:
        """
        Delete a specific transcript by video and language.

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : str
            YouTube video identifier
        language_code : str
            BCP-47 language code

        Returns
        -------
        bool
            True if transcript was deleted, False if not found
        """
        result = await session.execute(
            delete(VideoTranscriptDB).where(
                and_(
                    VideoTranscriptDB.video_id == video_id,
                    VideoTranscriptDB.language_code == language_code.lower(),
                )
            )
        )
        return result.rowcount > 0

    async def update_transcript_quality(
        self,
        session: AsyncSession,
        video_id: VideoId,
        language_code: str,
        confidence_score: Optional[float] = None,
        is_cc: Optional[bool] = None,
        transcript_type: Optional[TranscriptType] = None,
    ) -> Optional[VideoTranscriptDB]:
        """
        Update quality indicators for a transcript.

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : str
            YouTube video identifier
        language_code : str
            BCP-47 language code
        confidence_score : Optional[float]
            New confidence score
        is_cc : Optional[bool]
            Whether it's closed captions
        transcript_type : Optional[TranscriptType]
            New transcript type

        Returns
        -------
        Optional[VideoTranscriptDB]
            Updated transcript if found, None otherwise
        """
        transcript = await self.get_by_composite_key(session, video_id, language_code)
        if not transcript:
            return None

        # Update provided fields
        if confidence_score is not None:
            transcript.confidence_score = confidence_score
        if is_cc is not None:
            transcript.is_cc = is_cc
        if transcript_type is not None:
            transcript.transcript_type = transcript_type.value

        session.add(transcript)
        await session.flush()
        await session.refresh(transcript)
        return transcript

    async def get_transcripts_with_quality_scores(
        self, session: AsyncSession, video_id: VideoId
    ) -> List[VideoTranscriptWithQuality]:
        """
        Get transcripts with computed quality scores.

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : str
            YouTube video identifier

        Returns
        -------
        List[VideoTranscriptWithQuality]
            Transcripts with quality metrics
        """
        transcripts = await self.get_video_transcripts(session, video_id)
        quality_transcripts = []

        for transcript in transcripts:
            # Compute quality score based on multiple factors
            quality_score = self._compute_quality_score(transcript)
            is_high_quality = quality_score >= 0.7

            # Convert to Pydantic model with quality info
            quality_transcript = VideoTranscriptWithQuality(
                video_id=transcript.video_id,
                language_code=self._convert_language_code(transcript.language_code),
                transcript_text=transcript.transcript_text,
                transcript_type=TranscriptType(transcript.transcript_type),
                download_reason=DownloadReason(transcript.download_reason),
                confidence_score=transcript.confidence_score,
                is_cc=transcript.is_cc,
                is_auto_synced=transcript.is_auto_synced,
                track_kind=TrackKind(transcript.track_kind),
                caption_name=transcript.caption_name,
                downloaded_at=transcript.downloaded_at,
                quality_score=quality_score,
                is_high_quality=is_high_quality,
            )
            quality_transcripts.append(quality_transcript)

        return quality_transcripts

    def _compute_quality_score(self, transcript: VideoTranscriptDB) -> float:
        """
        Compute quality score for a transcript based on multiple factors.

        Parameters
        ----------
        transcript : VideoTranscriptDB
            Transcript to evaluate

        Returns
        -------
        float
            Quality score between 0.0 and 1.0
        """
        score = 0.0

        # Base score from confidence if available
        if transcript.confidence_score:
            score += transcript.confidence_score * 0.4
        else:
            score += 0.2  # Default for missing confidence

        # Closed captions bonus
        if transcript.is_cc:
            score += 0.3

        # Manual transcript bonus
        if transcript.transcript_type == TranscriptType.MANUAL.value:
            score += 0.2
        elif transcript.transcript_type == TranscriptType.TRANSLATED.value:
            score += 0.1

        # Track kind bonus
        if transcript.track_kind == TrackKind.STANDARD.value:
            score += 0.1
        elif transcript.track_kind == TrackKind.FORCED.value:
            score += 0.05

        return min(score, 1.0)  # Cap at 1.0

    def _convert_language_code(self, language_code: str) -> LanguageCode:
        """
        Convert string language code to LanguageCode enum.

        Parameters
        ----------
        language_code : str
            Language code string from database

        Returns
        -------
        LanguageCode
            LanguageCode enum value
        """
        # Try to find the language code in the enum
        normalized_code = language_code.lower()

        # First try exact match
        for enum_member in LanguageCode:
            if normalized_code == enum_member.value.lower():
                return enum_member

        # If no exact match found, try to create from the string value
        # Since LanguageCode is a string enum, we can try to construct it
        try:
            return LanguageCode(language_code)
        except ValueError:
            # If all else fails, default to English
            # This provides a fallback for unknown language codes
            return LanguageCode.ENGLISH

    def _derive_metadata(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Derive metadata columns from raw transcript data.

        Parameters
        ----------
        raw_data : Dict[str, Any]
            Output from RawTranscriptData.model_dump().

        Returns
        -------
        Dict[str, Any]
            Derived metadata: has_timestamps, segment_count,
            total_duration, source.
        """
        snippets = raw_data.get("snippets", [])

        # Handle None snippets gracefully (treat as empty list)
        if snippets is None:
            snippets = []
            logger.debug(
                "Snippets is None in raw_transcript_data, treating as empty list"
            )

        has_timestamps = len(snippets) > 0
        # NOTE: Pydantic model uses 'snippet_count', but DB column is 'segment_count'.
        # This mapping is intentional to maintain consistency between the domain
        # model (which uses snippet terminology from youtube-transcript-api) and
        # the database schema (which uses the more generic 'segment' terminology).
        segment_count = len(snippets) if snippets else None

        if snippets:
            last_snippet = snippets[-1]
            total_duration = last_snippet.get("start", 0) + last_snippet.get(
                "duration", 0
            )
        else:
            total_duration = None
            logger.debug(
                "Empty snippets array in raw_transcript_data, "
                "setting has_timestamps=False, total_duration=None"
            )

        source = raw_data.get("source", "youtube_transcript_api")
        if "source" not in raw_data:
            logger.debug(
                "Source field missing from raw_transcript_data, "
                "defaulting to 'youtube_transcript_api'"
            )

        return {
            "has_timestamps": has_timestamps,
            "segment_count": segment_count,
            "total_duration": total_duration,
            "source": source,
        }

    async def create_or_update(
        self,
        session: AsyncSession,
        obj_in: VideoTranscriptCreate,
        *,
        raw_transcript_data: Optional[Dict[str, Any]] = None,
    ) -> VideoTranscriptDB:
        """
        Create or update a transcript with optional raw data.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        obj_in : VideoTranscriptCreate
            Transcript creation data (existing schema).
        raw_transcript_data : Optional[Dict[str, Any]]
            Complete raw transcript response including timestamps.
            When provided, derives: has_timestamps, segment_count,
            total_duration, source.

        Returns
        -------
        VideoTranscriptDB
            The created or updated transcript record.
        """
        video_id = obj_in.video_id
        language_code = obj_in.language_code

        # Check for existing transcript
        existing = await self.get_by_composite_key(session, video_id, language_code)

        # Prepare base data from obj_in
        if hasattr(obj_in, "model_dump"):
            obj_data = obj_in.model_dump()
        else:
            obj_data = obj_in.dict()

        # Process raw_transcript_data if provided
        if raw_transcript_data is not None:
            obj_data["raw_transcript_data"] = raw_transcript_data

            # Derive metadata with error handling
            try:
                metadata = self._derive_metadata(raw_transcript_data)
                logger.debug(
                    "Derived metadata for video_id=%s, language_code=%s: "
                    "has_timestamps=%s, segment_count=%s, total_duration=%s, source=%s",
                    video_id,
                    language_code,
                    metadata["has_timestamps"],
                    metadata["segment_count"],
                    metadata["total_duration"],
                    metadata["source"],
                )
            except Exception as e:
                logger.warning(
                    "Metadata derivation failed for video_id=%s: %s", video_id, e
                )
                # Fallback: Save raw data with minimal metadata
                metadata = {
                    "has_timestamps": False,
                    "segment_count": None,
                    "total_duration": None,
                    "source": raw_transcript_data.get("source", "youtube_transcript_api"),
                }

            # Apply derived metadata to obj_data
            obj_data.update(metadata)
        else:
            # When raw_transcript_data is not provided, set sensible defaults
            # for the new metadata fields to maintain backward compatibility
            obj_data["raw_transcript_data"] = None
            obj_data["has_timestamps"] = True  # Assume timestamps exist by default
            obj_data["segment_count"] = None
            obj_data["total_duration"] = None
            obj_data["source"] = "youtube_transcript_api"
            logger.debug(
                "No raw_transcript_data provided for video_id=%s, using default metadata",
                video_id,
            )

        if existing:
            # Update existing transcript
            logger.info(
                "Updating existing transcript for video_id=%s, language_code=%s",
                video_id,
                language_code,
            )

            # Build update dict excluding primary key fields
            update_fields = {
                k: v
                for k, v in obj_data.items()
                if k not in ("video_id", "language_code")
            }

            db_obj = await self.update(session, db_obj=existing, obj_in=update_fields)
        else:
            # Create new transcript
            logger.info(
                "Creating new transcript for video_id=%s, language_code=%s",
                video_id,
                language_code,
            )

            # Create database object directly since obj_data contains fields
            # (raw_transcript_data, has_timestamps, etc.) that aren't in VideoTranscriptCreate
            db_obj = VideoTranscriptDB(**obj_data)
            session.add(db_obj)
            await session.flush()
            await session.refresh(db_obj)

        # Create segments from raw_transcript_data if provided
        if raw_transcript_data is not None:
            await self._create_segments_from_raw_data(
                session, video_id, language_code, raw_transcript_data
            )

        return db_obj

    async def _create_segments_from_raw_data(
        self,
        session: AsyncSession,
        video_id: str,
        language_code: str,
        raw_data: Dict[str, Any],
    ) -> int:
        """
        Create transcript segments from raw transcript data.

        Implements idempotent segment creation: deletes existing segments
        before inserting new ones. This mirrors the backfill migration logic.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_id : str
            YouTube video ID.
        language_code : str
            BCP-47 language code.
        raw_data : Dict[str, Any]
            Raw transcript data containing snippets array.

        Returns
        -------
        int
            Number of segments created.

        Notes
        -----
        Malformed snippets are logged and skipped, not failed.
        This follows the same error handling as the backfill migration
        (FR-MIG-15-19).
        """
        snippets = raw_data.get("snippets", [])

        # Skip if snippets is not a list or is empty
        if not isinstance(snippets, list):
            logger.warning(
                "Skipping segment creation for %s/%s: snippets is not a list",
                video_id,
                language_code,
            )
            return 0

        if not snippets:
            logger.debug(
                "No snippets to process for %s/%s",
                video_id,
                language_code,
            )
            # Delete any existing segments (idempotent)
            await session.execute(
                delete(TranscriptSegmentDB).where(
                    and_(
                        TranscriptSegmentDB.video_id == video_id,
                        TranscriptSegmentDB.language_code == language_code,
                    )
                )
            )
            return 0

        # Delete existing segments for idempotent operation
        delete_result = await session.execute(
            delete(TranscriptSegmentDB).where(
                and_(
                    TranscriptSegmentDB.video_id == video_id,
                    TranscriptSegmentDB.language_code == language_code,
                )
            )
        )
        deleted_count = delete_result.rowcount
        if deleted_count > 0:
            logger.debug(
                "Deleted %d existing segments for %s/%s before recreating",
                deleted_count,
                video_id,
                language_code,
            )

        # Create segments from snippets
        segment_count = 0
        snippet_errors = 0

        for seq, snippet in enumerate(snippets):
            try:
                # Validate required fields
                text_content = snippet.get("text")
                start = snippet.get("start")
                duration_val = snippet.get("duration")

                if text_content is None or start is None or duration_val is None:
                    logger.warning(
                        "Skipping snippet %d in %s/%s: "
                        "missing required field (text/start/duration)",
                        seq,
                        video_id,
                        language_code,
                    )
                    snippet_errors += 1
                    continue

                # Type conversion with error handling
                start_time = float(start)
                duration = float(duration_val)
                end_time = start_time + duration

                # Create segment
                segment = TranscriptSegmentDB(
                    video_id=video_id,
                    language_code=language_code,
                    text=text_content,
                    start_time=start_time,
                    duration=duration,
                    end_time=end_time,
                    sequence_number=seq,
                    has_correction=False,
                )
                session.add(segment)
                segment_count += 1

            except (TypeError, ValueError) as e:
                logger.warning(
                    "Skipping snippet %d in %s/%s: type conversion error: %s",
                    seq,
                    video_id,
                    language_code,
                    e,
                )
                snippet_errors += 1
                continue

        await session.flush()

        if snippet_errors > 0:
            logger.info(
                "Created %d segments for %s/%s (%d snippets skipped)",
                segment_count,
                video_id,
                language_code,
                snippet_errors,
            )
        else:
            logger.debug(
                "Created %d segments for %s/%s",
                segment_count,
                video_id,
                language_code,
            )

        return segment_count

    async def filter_by_metadata(
        self,
        session: AsyncSession,
        *,
        has_timestamps: Optional[bool] = None,
        min_segment_count: Optional[int] = None,
        max_segment_count: Optional[int] = None,
        min_duration: Optional[float] = None,
        max_duration: Optional[float] = None,
        source: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[VideoTranscriptDB]:
        """
        Filter transcripts by metadata criteria.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        has_timestamps : Optional[bool]
            Filter by timestamp availability.
        min_segment_count : Optional[int]
            Minimum number of segments.
        max_segment_count : Optional[int]
            Maximum number of segments.
        min_duration : Optional[float]
            Minimum duration in seconds.
        max_duration : Optional[float]
            Maximum duration in seconds.
        source : Optional[str]
            Transcript source identifier.
        limit : int
            Maximum results to return (default 100).
        offset : int
            Results offset for pagination (default 0).

        Returns
        -------
        List[VideoTranscriptDB]
            Transcripts matching the criteria.

        Notes
        -----
        - All provided filters are combined with AND logic (conjunctive)
        - None values for filters are ignored (not applied)
        """
        query = select(VideoTranscriptDB)
        conditions: List[Any] = []

        # Filter by timestamp availability
        if has_timestamps is not None:
            conditions.append(VideoTranscriptDB.has_timestamps == has_timestamps)

        # Filter by segment count range
        if min_segment_count is not None:
            conditions.append(VideoTranscriptDB.segment_count >= min_segment_count)

        if max_segment_count is not None:
            conditions.append(VideoTranscriptDB.segment_count <= max_segment_count)

        # Filter by duration range
        if min_duration is not None:
            conditions.append(VideoTranscriptDB.total_duration >= min_duration)

        if max_duration is not None:
            conditions.append(VideoTranscriptDB.total_duration <= max_duration)

        # Filter by source
        if source is not None:
            conditions.append(VideoTranscriptDB.source == source)

        # Apply all conditions with AND logic
        if conditions:
            query = query.where(and_(*conditions))

        # Apply pagination
        query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        transcripts = list(result.scalars().all())

        # Log if results exceed 100 (large result set)
        if len(transcripts) > 100:
            logger.info(
                "filter_by_metadata returned >100 results: count=%d, "
                "has_timestamps=%s, min_segment_count=%s, max_segment_count=%s, "
                "min_duration=%s, max_duration=%s, source=%s, limit=%d, offset=%d",
                len(transcripts),
                has_timestamps,
                min_segment_count,
                max_segment_count,
                min_duration,
                max_duration,
                source,
                limit,
                offset,
            )

        return transcripts

    async def get_with_timestamps(
        self,
        session: AsyncSession,
        video_id: str,
        language_code: str,
    ) -> Optional[VideoTranscriptDB]:
        """
        Retrieve transcript with raw timestamp data.

        Returns None if transcript exists but has_timestamps is False.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_id : str
            YouTube video identifier.
        language_code : str
            BCP-47 language code.

        Returns
        -------
        Optional[VideoTranscriptDB]
            Transcript with timestamps if available, None otherwise.
        """
        transcript = await self.get_by_composite_key(session, video_id, language_code)

        # Return None if transcript doesn't exist or lacks timestamps
        if transcript is None:
            return None

        if not transcript.has_timestamps:
            return None

        return transcript
