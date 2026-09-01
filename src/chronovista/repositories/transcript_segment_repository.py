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

from sqlalchemy import (
    ColumnElement,
    and_,
    case,
    delete,
    distinct,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as TranscriptDB
from chronovista.models.enums import AvailabilityStatus
from chronovista.models.transcript_segment import TranscriptSegmentCreate
from chronovista.models.youtube_types import VideoId
from chronovista.repositories.base import (
    BaseSQLAlchemyRepository,
    escape_like_pattern,
)


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
        raise ValueError(f"Invalid regex pattern '{pattern}': {exc}") from exc

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

    async def get(self, session: AsyncSession, id: int) -> TranscriptSegmentDB | None:
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
                raise ValueError(f"Invalid regex pattern '{pattern}': {exc}") from exc

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
            escaped = escape_like_pattern(pattern)
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

    async def count_whole_word_matches(
        self,
        session: AsyncSession,
        token: str,
        whole_word_regex: str,
        *,
        cap: int,
    ) -> int:
        r"""Count segments whose effective text contains ``token`` as a whole word.

        Word-boundary, **not** substring: the token does not match inside a larger
        word, so ``"ACME"`` does not count ``"ACMES"``. The caller supplies
        ``whole_word_regex`` (a POSIX ``\y…\y`` pattern) as the exact recheck; this
        is the same boundary rule the Find & Replace search uses, so the count
        agrees with what a replace would actually change. Case-sensitive.

        The trigram-eligible substring super-set on the raw columns is kept as an
        index prefilter (a whole-word match implies the substring is present, so
        nothing true is dropped), with the word-boundary regex as the exact
        recheck on the effective (post-correction) text. The count is capped at
        ``cap`` (#212).

        Parameters
        ----------
        session : AsyncSession
            The database session.
        token : str
            The raw token, used for the trigram-index substring prefilter.
        whole_word_regex : str
            POSIX regex matching ``token`` as a whole word, used for the exact
            recheck against the effective text.
        cap : int
            Upper bound on the count (bounds the heap fetch; #212).

        Returns
        -------
        int
            Number of matching segments, capped at ``cap``.
        """
        effective_text = case(
            (TranscriptSegmentDB.has_correction, TranscriptSegmentDB.corrected_text),
            else_=TranscriptSegmentDB.text,
        )
        matching_rows = (
            select(literal(1))
            .select_from(TranscriptSegmentDB)
            .where(
                # Index-eligible super-set on the RAW columns so PostgreSQL can use
                # the pg_trgm GIN indexes (idx_segments_text_trgm /
                # idx_segments_corrected_text_trgm). A CASE expression is opaque to
                # them and forces a parallel seq scan of ~2M rows — once per token.
                # Same fix as #150.
                or_(
                    TranscriptSegmentDB.text.contains(token),
                    TranscriptSegmentDB.corrected_text.contains(token),
                ),
                # Exact recheck against the super-set: whole-word (word boundary),
                # not substring. A segment whose correction removed the token is
                # excluded too, because the recheck runs on the effective
                # (post-correction) text.
                effective_text.op("~")(whole_word_regex),
            )
            # The ceiling bounds the heap fetch (#212).
            .limit(cap)
            .subquery()
        )
        result = await session.execute(select(func.count()).select_from(matching_rows))
        return int(result.scalar_one())

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
            stmt = select(distinct(TranscriptSegmentDB.video_id)).where(
                and_(*scope_conditions)
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

    async def search_segments(
        self,
        session: AsyncSession,
        *,
        query_text: str,
        video_id: str | None = None,
        language: str | None = None,
        include_unavailable: bool = False,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[
        list[tuple[TranscriptSegmentDB, TranscriptDB, VideoDB, ChannelDB | None]],
        int,
    ]:
        """Search transcript segments by literal text, with paginated results.

        Case-insensitive substring (ILIKE) match against both the original
        ``text`` and the ``corrected_text`` so corrections are findable. The
        query is escaped for literal matching. Joins the transcript (for the
        language row), the video (for title / upload date / availability), and
        left-joins the channel (for display title — ``None`` when absent).

        Parameters
        ----------
        session : AsyncSession
            Database session.
        query_text : str
            The already-validated search phrase (escaped internally).
        video_id : str, optional
            Restrict to a single video.
        language : str, optional
            Restrict to a single language code (case-insensitive comparison for
            BCP-47 casing variations). Applied to the results and the count, but
            NOT to :meth:`get_matching_languages` — the facet reflects every
            language the phrase matches so a caller can switch.
        include_unavailable : bool, optional
            Include segments of unavailable videos (default False).
        skip : int, optional
            Pagination offset (default 0).
        limit : int, optional
            Page size (default 20).

        Returns
        -------
        tuple[list[tuple[TranscriptSegmentDB, TranscriptDB, VideoDB, ChannelDB | None]], int]
            The page of ``(segment, transcript, video, channel)`` rows and the
            total matching count (before pagination).

        Notes
        -----
        Ordered by ``upload_date DESC, start_time ASC, id ASC``. The trailing
        ``id`` tiebreak makes the page boundary deterministic — without it,
        segments sharing an ``(upload_date, start_time)`` could be silently
        repeated or skipped across pages of this paginated endpoint.
        """
        escaped = escape_like_pattern(query_text)
        text_match = or_(
            TranscriptSegmentDB.text.ilike(f"%{escaped}%"),
            TranscriptSegmentDB.corrected_text.ilike(f"%{escaped}%"),
        )

        query = (
            select(TranscriptSegmentDB, TranscriptDB, VideoDB, ChannelDB)
            .join(
                TranscriptDB,
                and_(
                    TranscriptSegmentDB.video_id == TranscriptDB.video_id,
                    TranscriptSegmentDB.language_code == TranscriptDB.language_code,
                ),
            )
            .join(VideoDB, TranscriptSegmentDB.video_id == VideoDB.video_id)
            .outerjoin(ChannelDB, VideoDB.channel_id == ChannelDB.channel_id)
        )

        if not include_unavailable:
            query = query.where(
                VideoDB.availability_status == AvailabilityStatus.AVAILABLE
            )

        query = query.where(text_match)

        if video_id:
            query = query.where(TranscriptSegmentDB.video_id == video_id)

        if language:
            query = query.where(
                func.lower(TranscriptSegmentDB.language_code) == func.lower(language)
            )

        count_query = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_query)).scalar() or 0

        query = (
            query.order_by(
                VideoDB.upload_date.desc(),
                TranscriptSegmentDB.start_time.asc(),
                TranscriptSegmentDB.id.asc(),
            )
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(query)
        rows: list[
            tuple[TranscriptSegmentDB, TranscriptDB, VideoDB, ChannelDB | None]
        ] = [(row[0], row[1], row[2], row[3]) for row in result.all()]
        return rows, total

    async def get_matching_languages(
        self,
        session: AsyncSession,
        *,
        query_text: str,
        video_id: str | None = None,
        include_unavailable: bool = False,
    ) -> list[str]:
        """Return the distinct language codes whose segments match the phrase.

        The text / availability / video filters mirror :meth:`search_segments`,
        but the ``language`` filter is intentionally omitted so the result is
        the full set of languages a caller could switch to for the same phrase.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        query_text : str
            The already-validated search phrase (escaped internally).
        video_id : str, optional
            Restrict to a single video.
        include_unavailable : bool, optional
            Include segments of unavailable videos (default False).

        Returns
        -------
        list[str]
            Distinct matching language codes, sorted ascending.
        """
        escaped = escape_like_pattern(query_text)
        query = select(TranscriptSegmentDB.language_code).join(
            VideoDB, TranscriptSegmentDB.video_id == VideoDB.video_id
        )

        if not include_unavailable:
            query = query.where(
                VideoDB.availability_status == AvailabilityStatus.AVAILABLE
            )

        query = query.where(
            or_(
                TranscriptSegmentDB.text.ilike(f"%{escaped}%"),
                TranscriptSegmentDB.corrected_text.ilike(f"%{escaped}%"),
            )
        )

        if video_id:
            query = query.where(TranscriptSegmentDB.video_id == video_id)

        result = await session.execute(query.distinct())
        return sorted(lang for (lang,) in result.all())

    async def get_adjacent_segment_text(
        self,
        session: AsyncSession,
        *,
        segment_ids: list[int],
        video_ids: list[str],
        language_codes: list[str],
    ) -> dict[int, tuple[str | None, str | None]]:
        """Return the previous / next segment text for each given segment.

        Batch-fetches adjacent-segment context for a page of search results in a
        single query, eliminating the per-result N+1. ``LAG``/``LEAD`` window
        functions run over each ``(video_id, language_code)`` partition ordered
        by ``start_time``; the window computation is bounded to the supplied
        ``video_ids`` / ``language_codes`` (the partitions the results live in).
        Adjacent text uses ``corrected_text`` when present, else ``text``.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        segment_ids : list[int]
            The result segment ids to return context for.
        video_ids : list[str]
            Distinct video ids of the result set (bounds the window scan).
        language_codes : list[str]
            Distinct language codes of the result set (bounds the window scan).

        Returns
        -------
        dict[int, tuple[str | None, str | None]]
            Maps each in-scope segment id to ``(previous_text, next_text)``;
            either side is ``None`` at a partition boundary. Empty when
            ``segment_ids`` is empty.
        """
        if not segment_ids:
            return {}

        partition = [TranscriptSegmentDB.video_id, TranscriptSegmentDB.language_code]
        order = TranscriptSegmentDB.start_time.asc()
        display_text = func.coalesce(
            TranscriptSegmentDB.corrected_text, TranscriptSegmentDB.text
        )

        context_cte = (
            select(
                TranscriptSegmentDB.id.label("seg_id"),
                func.lag(display_text, 1)
                .over(partition_by=partition, order_by=order)
                .label("prev_text"),
                func.lead(display_text, 1)
                .over(partition_by=partition, order_by=order)
                .label("next_text"),
            )
            .where(
                and_(
                    TranscriptSegmentDB.video_id.in_(video_ids),
                    TranscriptSegmentDB.language_code.in_(language_codes),
                )
            )
            .cte("context_cte")
        )

        context_query = select(
            context_cte.c.seg_id,
            context_cte.c.prev_text,
            context_cte.c.next_text,
        ).where(context_cte.c.seg_id.in_(segment_ids))
        result = await session.execute(context_query)
        return {
            seg_id: (prev_text, next_text)
            for seg_id, prev_text, next_text in result.all()
        }

    async def get_video_ids_with_corrections(
        self, session: AsyncSession, video_ids: list[str]
    ) -> set[str]:
        """Return which of the given video ids have a corrected segment.

        A single batched lookup for a page of results (avoids an N+1 over rows).

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_ids : list[str]
            Candidate video ids (typically one page of results).

        Returns
        -------
        set[str]
            The subset of ``video_ids`` that have at least one segment with
            ``has_correction`` set. Empty when ``video_ids`` is empty.
        """
        if not video_ids:
            return set()
        result = await session.execute(
            select(TranscriptSegmentDB.video_id)
            .where(
                TranscriptSegmentDB.video_id.in_(video_ids),
                TranscriptSegmentDB.has_correction.is_(True),
            )
            .distinct()
        )
        return {row[0] for row in result.all()}

    async def video_has_corrections(
        self, session: AsyncSession, video_id: VideoId
    ) -> bool:
        """Return whether a single video has any corrected segment.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_id : VideoId
            YouTube video identifier.

        Returns
        -------
        bool
            True if at least one segment for the video has ``has_correction``
            set, False otherwise.
        """
        result = await session.execute(
            select(TranscriptSegmentDB.id)
            .where(
                TranscriptSegmentDB.video_id == video_id,
                TranscriptSegmentDB.has_correction.is_(True),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def list_segments_page(
        self,
        session: AsyncSession,
        video_id: str,
        language: str,
        *,
        start_time: float | None,
        end_time: float | None,
        offset: int,
        limit: int,
    ) -> tuple[int, list[TranscriptSegmentDB]]:
        """List a page of segments for a video+language, with total count.

        Matches the language case-insensitively (RFC 5646), applies optional
        time-window filters, derives the total from the same filtered query, and
        returns the page ordered by ``start_time`` ascending.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_id : str
            YouTube video identifier.
        language : str
            BCP-47 language code (matched case-insensitively).
        start_time : float | None
            When set, keep segments with ``start_time >= start_time``.
        end_time : float | None
            When set, keep segments with ``end_time <= end_time``.
        offset, limit : int
            Pagination window.

        Returns
        -------
        tuple[int, list[TranscriptSegmentDB]]
            The total matching count and the page of segments.
        """
        base_query = (
            select(TranscriptSegmentDB)
            .where(TranscriptSegmentDB.video_id == video_id)
            .where(func.lower(TranscriptSegmentDB.language_code) == language.lower())
        )
        if start_time is not None:
            base_query = base_query.where(TranscriptSegmentDB.start_time >= start_time)
        if end_time is not None:
            base_query = base_query.where(TranscriptSegmentDB.end_time <= end_time)

        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await session.execute(count_query)).scalar() or 0

        paginated_query = (
            base_query.order_by(TranscriptSegmentDB.start_time.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(paginated_query)
        segments = list(result.scalars().all())
        return total, segments


__all__ = ["TranscriptSegmentRepository"]
