"""
Repository for TranscriptSegment database operations.

Provides timestamp-based query methods following the repository pattern
with half-open interval semantics per Decision 11 (FR-EDGE-01).

This repository supports Feature 008: Transcript Segment Table (Phase 2)
User Story 6: Repository Methods and Tests (T019-T025).
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.models.transcript_segment import TranscriptSegmentCreate
from chronovista.models.youtube_types import VideoId
from chronovista.repositories.base import BaseSQLAlchemyRepository


class TranscriptSegmentRepository(
    BaseSQLAlchemyRepository[
        TranscriptSegmentDB,
        TranscriptSegmentCreate,
        TranscriptSegmentCreate,  # No separate Update schema for now
        int,  # Primary key is integer id
    ]
):
    """Repository for TranscriptSegment database operations.

    Implements timestamp-based queries with half-open interval semantics:
    - A segment contains timestamp t if: start_time <= t < end_time
    - Timestamp at exact boundary (e.g., 2.5) returns segment starting at 2.5
    - Gap handling: if timestamp is in a gap, returns the previous segment

    This follows Decision 11 (FR-EDGE-01) for half-open intervals.

    Attributes
    ----------
    model : type[TranscriptSegmentDB]
        The SQLAlchemy model class for transcript segments.

    Examples
    --------
    >>> repo = TranscriptSegmentRepository()
    >>> segment = await repo.get_segment_at_time(session, "dQw4w9WgXcQ", "en", 1.5)
    >>> segments = await repo.get_segments_in_range(session, "dQw4w9WgXcQ", "en", 0.0, 10.0)
    """

    def __init__(self) -> None:
        """Initialize repository with TranscriptSegment model."""
        super().__init__(TranscriptSegmentDB)

    async def get(
        self, session: AsyncSession, id: int
    ) -> Optional[TranscriptSegmentDB]:
        """
        Get segment by primary key (id).

        Parameters
        ----------
        session : AsyncSession
            Database session.
        id : int
            Segment primary key.

        Returns
        -------
        Optional[TranscriptSegmentDB]
            The segment if found, None otherwise.
        """
        result = await session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, id: int) -> bool:
        """
        Check if segment exists by primary key.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        id : int
            Segment primary key.

        Returns
        -------
        bool
            True if segment exists, False otherwise.
        """
        result = await session.execute(
            select(TranscriptSegmentDB.id).where(TranscriptSegmentDB.id == id)
        )
        return result.first() is not None

    async def get_segment_at_time(
        self,
        session: AsyncSession,
        video_id: VideoId,
        language_code: str,
        timestamp: float,
    ) -> Optional[TranscriptSegmentDB]:
        """
        Get the segment containing the given timestamp.

        Uses half-open interval [start, end) per FR-EDGE-01.
        If timestamp is in a gap, returns the previous segment.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_id : VideoId
            YouTube video ID.
        language_code : str
            BCP-47 language code.
        timestamp : float
            Time in seconds.

        Returns
        -------
        Optional[TranscriptSegmentDB]
            The segment at that time, or None if before first segment.

        Notes
        -----
        Half-open interval semantics mean:
        - Segment [0.0, 2.5) contains timestamps 0.0, 1.0, 2.4999 but NOT 2.5
        - Timestamp 2.5 would be contained by segment [2.5, 5.0)

        Gap handling: if timestamp falls between two segments (gap),
        returns the previous segment that ended before the timestamp.
        """
        # First, try exact match with half-open interval [start, end)
        stmt = (
            select(TranscriptSegmentDB)
            .where(
                and_(
                    TranscriptSegmentDB.video_id == str(video_id),
                    TranscriptSegmentDB.language_code == language_code,
                    TranscriptSegmentDB.start_time <= timestamp,
                    TranscriptSegmentDB.end_time > timestamp,
                )
            )
            .order_by(TranscriptSegmentDB.start_time.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        segment = result.scalar_one_or_none()

        if segment:
            return segment

        # If no exact match, timestamp might be in a gap - return previous segment
        # Find the segment that ends at or before the timestamp
        stmt = (
            select(TranscriptSegmentDB)
            .where(
                and_(
                    TranscriptSegmentDB.video_id == str(video_id),
                    TranscriptSegmentDB.language_code == language_code,
                    TranscriptSegmentDB.end_time <= timestamp,
                )
            )
            .order_by(TranscriptSegmentDB.end_time.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_segments_in_range(
        self,
        session: AsyncSession,
        video_id: VideoId,
        language_code: str,
        start: float,
        end: float,
    ) -> Sequence[TranscriptSegmentDB]:
        """
        Get all segments overlapping with the given time range.

        Overlap defined as: segment.start_time < range_end AND segment.end_time > range_start
        per spec US6 acceptance criteria.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_id : VideoId
            YouTube video ID.
        language_code : str
            BCP-47 language code.
        start : float
            Range start time in seconds.
        end : float
            Range end time in seconds.

        Returns
        -------
        Sequence[TranscriptSegmentDB]
            All segments overlapping the range, ordered by start_time.

        Notes
        -----
        A segment overlaps with range [start, end] if:
        - The segment starts before the range ends: segment.start_time < end
        - The segment ends after the range starts: segment.end_time > start

        Zero-duration segments at the boundary may or may not be included
        depending on the exact boundary conditions.
        """
        stmt = (
            select(TranscriptSegmentDB)
            .where(
                and_(
                    TranscriptSegmentDB.video_id == str(video_id),
                    TranscriptSegmentDB.language_code == language_code,
                    TranscriptSegmentDB.start_time < end,
                    TranscriptSegmentDB.end_time > start,
                )
            )
            .order_by(TranscriptSegmentDB.start_time)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_context_window(
        self,
        session: AsyncSession,
        video_id: VideoId,
        language_code: str,
        timestamp: float,
        window_seconds: float,
    ) -> Sequence[TranscriptSegmentDB]:
        """
        Get segments within a context window around a timestamp.

        Returns segments from (timestamp - window_seconds) to (timestamp + window_seconds).
        Start time is clamped to 0.0 (no negative times).

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_id : VideoId
            YouTube video ID.
        language_code : str
            BCP-47 language code.
        timestamp : float
            Center timestamp in seconds.
        window_seconds : float
            Window size in seconds (applied both before and after).

        Returns
        -------
        Sequence[TranscriptSegmentDB]
            All segments within the window, ordered by start_time.

        Examples
        --------
        >>> # Get 5 seconds of context around timestamp 30.0
        >>> segments = await repo.get_context_window(session, "vid", "en", 30.0, 5.0)
        >>> # Returns segments overlapping with range [25.0, 35.0]
        """
        start = max(0.0, timestamp - window_seconds)
        end = timestamp + window_seconds
        return await self.get_segments_in_range(
            session, video_id, language_code, start, end
        )

    async def bulk_create_segments(
        self,
        session: AsyncSession,
        segments: List[TranscriptSegmentCreate],
    ) -> int:
        """
        Create multiple segments in bulk.

        This method is optimized for creating many segments at once,
        such as during transcript migration or backfill operations.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        segments : List[TranscriptSegmentCreate]
            Segments to create.

        Returns
        -------
        int
            Number of segments created.

        Notes
        -----
        Uses session.add_all() for efficient bulk insertion.
        The caller is responsible for committing the transaction.
        """
        db_segments = [
            TranscriptSegmentDB(
                video_id=str(seg.video_id),
                language_code=seg.language_code,
                text=seg.text,
                start_time=seg.start_time,
                duration=seg.duration,
                end_time=seg.end_time,
                sequence_number=seg.sequence_number,
            )
            for seg in segments
        ]
        session.add_all(db_segments)
        await session.flush()
        return len(db_segments)

    async def delete_segments_for_transcript(
        self,
        session: AsyncSession,
        video_id: VideoId,
        language_code: str,
    ) -> int:
        """
        Delete all segments for a transcript (for idempotent backfill).

        This method supports idempotent migration operations where
        segments may need to be recreated from raw transcript data.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_id : VideoId
            YouTube video ID.
        language_code : str
            BCP-47 language code.

        Returns
        -------
        int
            Number of segments deleted.

        Notes
        -----
        This operation is idempotent - calling it when no segments exist
        returns 0 without error. The caller is responsible for committing
        the transaction.
        """
        stmt = delete(TranscriptSegmentDB).where(
            and_(
                TranscriptSegmentDB.video_id == str(video_id),
                TranscriptSegmentDB.language_code == language_code,
            )
        )
        result = await session.execute(stmt)
        return result.rowcount

    async def get_segments_for_transcript(
        self,
        session: AsyncSession,
        video_id: VideoId,
        language_code: str,
    ) -> Sequence[TranscriptSegmentDB]:
        """
        Get all segments for a transcript, ordered by sequence number.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_id : VideoId
            YouTube video ID.
        language_code : str
            BCP-47 language code.

        Returns
        -------
        Sequence[TranscriptSegmentDB]
            All segments for the transcript, ordered by sequence_number.
        """
        stmt = (
            select(TranscriptSegmentDB)
            .where(
                and_(
                    TranscriptSegmentDB.video_id == str(video_id),
                    TranscriptSegmentDB.language_code == language_code,
                )
            )
            .order_by(TranscriptSegmentDB.sequence_number)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def count_segments_for_transcript(
        self,
        session: AsyncSession,
        video_id: VideoId,
        language_code: str,
    ) -> int:
        """
        Count segments for a transcript.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_id : VideoId
            YouTube video ID.
        language_code : str
            BCP-47 language code.

        Returns
        -------
        int
            Number of segments for the transcript.
        """
        from sqlalchemy import func

        stmt = select(func.count()).where(
            and_(
                TranscriptSegmentDB.video_id == str(video_id),
                TranscriptSegmentDB.language_code == language_code,
            )
        )
        result = await session.execute(stmt)
        return result.scalar() or 0


__all__ = ["TranscriptSegmentRepository"]
