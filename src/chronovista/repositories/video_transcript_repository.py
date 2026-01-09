"""
Video transcript repository.

Provides data access layer for video transcripts with multi-language support,
quality indicators, and specialized queries for transcript management.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
