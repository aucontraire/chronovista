"""
Repository for TranscriptSegment database operations.

Provides timestamp-based query methods following the repository pattern
with half-open interval semantics per Decision 11 (FR-EDGE-01).

This repository supports Feature 008: Transcript Segment Table (Phase 2)
User Story 6: Repository Methods and Tests (T019-T025).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from sqlalchemy import ColumnElement, and_, case, delete, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.models.transcript_segment import TranscriptSegmentCreate
from chronovista.models.youtube_types import VideoId
from chronovista.repositories.base import BaseSQLAlchemyRepository


def translate_python_regex_to_posix(pattern: str) -> str:
    """Translate Python regex word-boundary syntax to PostgreSQL POSIX equivalents.

    Python's ``re`` module uses ``\\b`` and ``\\B`` for word-boundary and
    non-word-boundary assertions respectively.  PostgreSQL's POSIX ``~``
    operator uses ``\\y`` and ``\\Y`` instead.

    The function validates the pattern with ``re.compile()`` first and
    raises ``ValueError`` for malformed patterns.

    Parameters
    ----------
    pattern : str
        A Python-flavoured regular expression string.

    Returns
    -------
    str
        The pattern with ``\\b`` → ``\\y`` and ``\\B`` → ``\\Y`` outside
        character classes.  ``\\b`` inside ``[...]`` (backspace) and
        escaped backslashes (``\\\\b``) are left unchanged.

    Raises
    ------
    ValueError
        If the pattern is not a valid regular expression.
    """
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(
            f"Invalid regex pattern '{pattern}': {exc}"
        ) from exc

    result: list[str] = []
    i = 0
    in_char_class = False

    while i < len(pattern):
        ch = pattern[i]

        if ch == "\\" and i + 1 < len(pattern):
            next_ch = pattern[i + 1]
            if next_ch == "\\":
                # Escaped backslash — emit both and skip ahead
                result.append("\\\\")
                i += 2
                continue
            if not in_char_class and next_ch in ("b", "B"):
                # Word-boundary assertion outside char class
                result.append("\\y" if next_ch == "b" else "\\Y")
                i += 2
                continue
            # Any other escape sequence — pass through unchanged
            result.append(ch)
            result.append(next_ch)
            i += 2
            continue

        if ch == "[" and not in_char_class:
            in_char_class = True
        elif ch == "]" and in_char_class:
            in_char_class = False

        result.append(ch)
        i += 1

    return "".join(result)


def _escape_like_pattern(text: str) -> str:
    """Escape SQL LIKE/ILIKE wildcard characters for literal matching.

    Parameters
    ----------
    text : str
        The text to escape.

    Returns
    -------
    str
        The escaped text safe for use in LIKE/ILIKE patterns.
    """
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
    ) -> TranscriptSegmentDB | None:
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
    ) -> TranscriptSegmentDB | None:
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
        segments: list[TranscriptSegmentCreate],
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
        stmt = select(func.count()).where(
            and_(
                TranscriptSegmentDB.video_id == str(video_id),
                TranscriptSegmentDB.language_code == language_code,
            )
        )
        result = await session.execute(stmt)
        return result.scalar() or 0

    async def find_by_text_pattern(
        self,
        session: AsyncSession,
        *,
        pattern: str,
        regex: bool = False,
        case_insensitive: bool = False,
        language: str | None = None,
        channel: str | None = None,
        video_ids: list[str] | None = None,
    ) -> Sequence[TranscriptSegmentDB]:
        """
        Find segments whose effective text matches a pattern.

        Effective text is defined as: corrected_text if has_correction is True,
        otherwise the original text. Filtering is done database-side using SQL
        CASE expressions for efficiency.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        pattern : str
            The search pattern (substring or regex).
        regex : bool, optional
            If True, use PostgreSQL regex operators (~ or ~*).
            If False (default), use LIKE/ILIKE substring matching.
        case_insensitive : bool, optional
            If True, use case-insensitive matching (ILIKE or ~*).
            If False (default), use case-sensitive matching (LIKE or ~).
        language : str, optional
            Filter by language_code column.
        channel : str, optional
            Filter by channel_id via join to videos table.
        video_ids : list of str, optional
            Filter by video_id column (list of video IDs).

        Returns
        -------
        Sequence[TranscriptSegmentDB]
            Matching segment ORM objects, ordered by video_id and
            sequence_number.

        Raises
        ------
        ValueError
            If regex=True and the pattern is not a valid regular expression.
        """
        # Pre-validate regex pattern before constructing SQL query
        if regex:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(
                    f"Invalid regex pattern '{pattern}': {exc}"
                ) from exc

        # Translate Python word-boundary syntax to PostgreSQL POSIX equivalent
        sql_pattern = translate_python_regex_to_posix(pattern) if regex else pattern

        # Build the effective text expression using SQL CASE
        effective_text = case(
            (TranscriptSegmentDB.has_correction, TranscriptSegmentDB.corrected_text),
            else_=TranscriptSegmentDB.text,
        )

        # Build pattern matching condition
        if regex:
            if case_insensitive:
                text_condition = effective_text.op("~*")(sql_pattern)
            else:
                text_condition = effective_text.op("~")(sql_pattern)
        else:
            escaped = _escape_like_pattern(pattern)
            like_pattern = f"%{escaped}%"
            if case_insensitive:
                text_condition = effective_text.ilike(like_pattern)
            else:
                text_condition = effective_text.like(like_pattern)

        # Start building the query
        conditions: list[ColumnElement[bool]] = [text_condition]

        if language is not None:
            conditions.append(TranscriptSegmentDB.language_code == language)

        if video_ids is not None:
            conditions.append(TranscriptSegmentDB.video_id.in_(video_ids))

        # Build query — join to videos table only when channel filter is needed
        if channel is not None:
            stmt = (
                select(TranscriptSegmentDB)
                .join(
                    VideoDB,
                    TranscriptSegmentDB.video_id == VideoDB.video_id,
                )
                .where(and_(*conditions, VideoDB.channel_id == channel))
                .order_by(
                    TranscriptSegmentDB.video_id,
                    TranscriptSegmentDB.sequence_number,
                )
            )
        else:
            stmt = (
                select(TranscriptSegmentDB)
                .where(and_(*conditions))
                .order_by(
                    TranscriptSegmentDB.video_id,
                    TranscriptSegmentDB.sequence_number,
                )
            )

        result = await session.execute(stmt)
        return result.scalars().all()

    async def count_filtered(
        self,
        session: AsyncSession,
        *,
        language: str | None = None,
        channel: str | None = None,
        video_ids: list[str] | None = None,
    ) -> int:
        """
        Count segments matching the given filter criteria.

        Returns the total number of segments that match the filter parameters
        before any text pattern matching. This count is used to populate
        the ``total_scanned`` field in batch correction summaries.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        language : str, optional
            Filter by language_code column.
        channel : str, optional
            Filter by channel_id via join to videos table.
        video_ids : list of str, optional
            Filter by video_id column (list of video IDs).

        Returns
        -------
        int
            Total number of segments matching the filters.
        """
        conditions: list[ColumnElement[bool]] = []

        if language is not None:
            conditions.append(TranscriptSegmentDB.language_code == language)

        if video_ids is not None:
            conditions.append(TranscriptSegmentDB.video_id.in_(video_ids))

        if channel is not None:
            stmt = (
                select(func.count())
                .select_from(TranscriptSegmentDB)
                .join(
                    VideoDB,
                    TranscriptSegmentDB.video_id == VideoDB.video_id,
                )
                .where(and_(*conditions, VideoDB.channel_id == channel))
            )
        else:
            stmt = select(func.count()).select_from(TranscriptSegmentDB)
            if conditions:
                stmt = stmt.where(and_(*conditions))

        result = await session.execute(stmt)
        return result.scalar() or 0

    async def find_candidate_video_ids_for_cross_segment(
        self,
        session: AsyncSession,
        *,
        tokens: list[str],
        language: str | None = None,
        channel: str | None = None,
        case_insensitive: bool = False,
    ) -> list[str]:
        """
        Return distinct video_ids that contain at least one of the given tokens.

        This is a lightweight pre-filter for cross-segment search: instead of
        loading every segment in the database, we first identify which videos
        could possibly contribute to a cross-segment match by finding videos
        that already contain any token from the search pattern. Only those
        videos are then passed to ``find_segments_in_scope()``.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        tokens : list of str
            Substring tokens to search for (e.g. individual words of the
            pattern, or boundary fragments).  An empty list causes every
            video_id to be returned — callers must guard against this.
        language : str, optional
            Filter by language_code column (applied before DISTINCT).
        channel : str, optional
            Filter by channel_id via join to the videos table.
        case_insensitive : bool, optional
            When True use ILIKE instead of LIKE for token matching.

        Returns
        -------
        list of str
            Distinct video_ids whose segments contain at least one token.
            Returns an empty list when ``tokens`` is empty.
        """
        if not tokens:
            return []

        # Build effective-text expression (mirrors find_by_text_pattern)
        effective_text = case(
            (TranscriptSegmentDB.has_correction, TranscriptSegmentDB.corrected_text),
            else_=TranscriptSegmentDB.text,
        )

        # OR together a LIKE/ILIKE condition for every token
        like_conditions: list[ColumnElement[bool]] = []
        for token in tokens:
            like_pat = f"%{token}%"
            if case_insensitive:
                like_conditions.append(effective_text.ilike(like_pat))
            else:
                like_conditions.append(effective_text.like(like_pat))

        token_condition: ColumnElement[bool] = or_(*like_conditions)

        # Optional scope filters
        scope_conditions: list[ColumnElement[bool]] = [token_condition]
        if language is not None:
            scope_conditions.append(TranscriptSegmentDB.language_code == language)

        if channel is not None:
            stmt = (
                select(distinct(TranscriptSegmentDB.video_id))
                .join(
                    VideoDB,
                    TranscriptSegmentDB.video_id == VideoDB.video_id,
                )
                .where(and_(*scope_conditions, VideoDB.channel_id == channel))
            )
        else:
            stmt = (
                select(distinct(TranscriptSegmentDB.video_id))
                .where(and_(*scope_conditions))
            )

        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def find_segments_in_scope(
        self,
        session: AsyncSession,
        *,
        language: str | None = None,
        channel: str | None = None,
        video_ids: list[str] | None = None,
    ) -> Sequence[TranscriptSegmentDB]:
        """
        Return all segments matching filter criteria without pattern filtering.

        This method retrieves every segment within the specified scope,
        ordered for cross-segment pairing. It applies the same filter
        logic as ``find_by_text_pattern()`` (language, channel, video_ids)
        but omits the text/pattern matching step, returning all segments
        in scope.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        language : str, optional
            Filter by language_code column.
        channel : str, optional
            Filter by channel_id via join to videos table.
        video_ids : list of str, optional
            Filter by video_id column (list of video IDs).

        Returns
        -------
        Sequence[TranscriptSegmentDB]
            All segments matching the filters, ordered by
            ``(video_id, language_code, sequence_number)`` for
            cross-segment pairing.
        """
        conditions: list[ColumnElement[bool]] = []

        if language is not None:
            conditions.append(TranscriptSegmentDB.language_code == language)

        if video_ids is not None:
            conditions.append(TranscriptSegmentDB.video_id.in_(video_ids))

        order = (
            TranscriptSegmentDB.video_id,
            TranscriptSegmentDB.language_code,
            TranscriptSegmentDB.sequence_number,
        )

        if channel is not None:
            stmt = (
                select(TranscriptSegmentDB)
                .join(
                    VideoDB,
                    TranscriptSegmentDB.video_id == VideoDB.video_id,
                )
                .where(and_(*conditions, VideoDB.channel_id == channel))
                .order_by(*order)
            )
        else:
            stmt = select(TranscriptSegmentDB).order_by(*order)
            if conditions:
                stmt = stmt.where(and_(*conditions))

        result = await session.execute(stmt)
        return result.scalars().all()


__all__ = ["TranscriptSegmentRepository"]
