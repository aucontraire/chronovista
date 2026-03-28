"""
Repository for TranscriptCorrection database operations.

Provides append-only audit log access following the repository pattern.
Records are immutable once created (FR-018): update() and delete() raise
NotImplementedError.

This repository supports Feature 033: Transcript Corrections Audit (FR-012,
FR-018, NFR-005).
"""

from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.models.batch_correction_models import (
    BatchListItem,
    CorrectionPattern,
    TypeCount,
    VideoCount,
)
from chronovista.models.enums import CorrectionType
from chronovista.models.transcript_correction import TranscriptCorrectionCreate
from chronovista.repositories.base import BaseSQLAlchemyRepository


class TranscriptCorrectionRepository(
    BaseSQLAlchemyRepository[
        TranscriptCorrectionDB,
        TranscriptCorrectionCreate,
        TranscriptCorrectionCreate,  # No separate Update schema — immutable
        UUID,
    ]
):
    """Repository for TranscriptCorrection database operations.

    This is an **append-only** repository. The ``update()`` and ``delete()``
    methods are overridden to raise ``NotImplementedError`` because transcript
    corrections form an immutable audit trail (FR-018).

    Attributes
    ----------
    model : type[TranscriptCorrectionDB]
        The SQLAlchemy model class for transcript corrections.
    """

    def __init__(self) -> None:
        """Initialize repository with TranscriptCorrection model."""
        super().__init__(TranscriptCorrectionDB)

    # ------------------------------------------------------------------
    # Immutability guards (FR-018)
    # ------------------------------------------------------------------

    async def update(
        self,
        session: AsyncSession,
        *,
        db_obj: TranscriptCorrectionDB,
        obj_in: TranscriptCorrectionCreate | dict[str, Any],
    ) -> TranscriptCorrectionDB:
        """Raise unconditionally — corrections are immutable.

        Raises
        ------
        NotImplementedError
            Always. Transcript corrections are an append-only audit table.
        """
        raise NotImplementedError(
            "TranscriptCorrection records are immutable — append-only audit table"
        )

    async def delete(
        self,
        session: AsyncSession,
        *,
        id: UUID,
    ) -> TranscriptCorrectionDB | None:
        """Raise unconditionally — corrections are immutable.

        Raises
        ------
        NotImplementedError
            Always. Transcript corrections are an append-only audit table.
        """
        raise NotImplementedError(
            "TranscriptCorrection records are immutable — append-only audit table"
        )

    # ------------------------------------------------------------------
    # Primary-key lookups
    # ------------------------------------------------------------------

    async def get(
        self,
        session: AsyncSession,
        id: UUID,
    ) -> TranscriptCorrectionDB | None:
        """
        Get a correction by its UUID primary key.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        id : UUID
            Correction primary key (UUIDv7).

        Returns
        -------
        Optional[TranscriptCorrectionDB]
            The correction if found, None otherwise.
        """
        result = await session.execute(
            select(TranscriptCorrectionDB).where(TranscriptCorrectionDB.id == id)
        )
        return result.scalar_one_or_none()

    async def exists(
        self,
        session: AsyncSession,
        id: UUID,
    ) -> bool:
        """
        Check if a correction exists by UUID primary key.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        id : UUID
            Correction primary key (UUIDv7).

        Returns
        -------
        bool
            True if the correction exists, False otherwise.
        """
        result = await session.execute(
            select(TranscriptCorrectionDB.id).where(TranscriptCorrectionDB.id == id)
        )
        return result.first() is not None

    # ------------------------------------------------------------------
    # Domain-specific queries
    # ------------------------------------------------------------------

    async def get_by_segment(
        self,
        session: AsyncSession,
        video_id: str,
        language_code: str,
        segment_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[TranscriptCorrectionDB]:
        """
        Get corrections for a specific segment, ordered by version DESC.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_id : str
            YouTube video ID.
        language_code : str
            BCP-47 language code.
        segment_id : int
            FK to transcript_segments.id.
        skip : int, optional
            Number of rows to skip (default 0).
        limit : int, optional
            Maximum rows to return (default 50).

        Returns
        -------
        list[TranscriptCorrectionDB]
            Corrections ordered by version_number DESC (newest first).
        """
        stmt = (
            select(TranscriptCorrectionDB)
            .where(
                and_(
                    TranscriptCorrectionDB.video_id == video_id,
                    TranscriptCorrectionDB.language_code == language_code,
                    TranscriptCorrectionDB.segment_id == segment_id,
                )
            )
            .order_by(TranscriptCorrectionDB.version_number.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_video(
        self,
        session: AsyncSession,
        video_id: str,
        language_code: str,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[TranscriptCorrectionDB], int]:
        """
        Get paginated corrections for a video transcript.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_id : str
            YouTube video ID.
        language_code : str
            BCP-47 language code.
        skip : int, optional
            Number of rows to skip (default 0).
        limit : int, optional
            Maximum rows to return (default 50).

        Returns
        -------
        tuple[list[TranscriptCorrectionDB], int]
            A tuple of (items, total_count). ``total_count`` reflects all
            corrections for the (video_id, language_code) pair, not just
            the current page.
        """
        # Count query first
        count_stmt = select(func.count()).where(
            and_(
                TranscriptCorrectionDB.video_id == video_id,
                TranscriptCorrectionDB.language_code == language_code,
            )
        ).select_from(TranscriptCorrectionDB)
        count_result = await session.execute(count_stmt)
        total = count_result.scalar_one()

        # Items query
        items_stmt = (
            select(TranscriptCorrectionDB)
            .where(
                and_(
                    TranscriptCorrectionDB.video_id == video_id,
                    TranscriptCorrectionDB.language_code == language_code,
                )
            )
            .order_by(TranscriptCorrectionDB.corrected_at.desc())
            .offset(skip)
            .limit(limit)
        )
        items_result = await session.execute(items_stmt)
        items = list(items_result.scalars().all())

        return items, total

    async def count_by_video(
        self,
        session: AsyncSession,
        video_id: str,
        language_code: str,
    ) -> int:
        """
        Count total corrections for a video transcript.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_id : str
            YouTube video ID.
        language_code : str
            BCP-47 language code.

        Returns
        -------
        int
            Total number of corrections for the (video_id, language_code) pair.
        """
        stmt = select(func.count()).where(
            and_(
                TranscriptCorrectionDB.video_id == video_id,
                TranscriptCorrectionDB.language_code == language_code,
            )
        ).select_from(TranscriptCorrectionDB)
        result = await session.execute(stmt)
        return result.scalar_one()

    async def get_all_filtered(
        self,
        session: AsyncSession,
        *,
        video_ids: list[str] | None = None,
        correction_type: CorrectionType | None = None,
        since: datetime.datetime | None = None,
        until: datetime.datetime | None = None,
    ) -> list[TranscriptCorrectionDB]:
        """
        Get corrections matching the provided filters.

        All filters are optional and combined with AND semantics.  When no
        filters are supplied every correction record is returned.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_ids : list[str] or None, optional
            If provided, restrict results to these YouTube video IDs.
        correction_type : CorrectionType or None, optional
            If provided, restrict results to this correction type.
        since : datetime or None, optional
            Inclusive lower bound (``>=``) on ``corrected_at``.
        until : datetime or None, optional
            Inclusive upper bound (``<=``) on ``corrected_at``.  Date-only
            values (``time() == 00:00:00``) are interpreted as end-of-day
            (``23:59:59.999999``).

        Returns
        -------
        list[TranscriptCorrectionDB]
            Matching corrections ordered by ``corrected_at`` ascending.
        """
        conditions: list[Any] = []

        if video_ids is not None:
            conditions.append(TranscriptCorrectionDB.video_id.in_(video_ids))

        if correction_type is not None:
            conditions.append(
                TranscriptCorrectionDB.correction_type == correction_type.value
            )

        if since is not None:
            conditions.append(TranscriptCorrectionDB.corrected_at >= since)

        if until is not None:
            # Interpret date-only values (midnight) as end-of-day
            effective_until = until
            if until.time() == datetime.time(0, 0, 0):
                effective_until = until.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
            conditions.append(TranscriptCorrectionDB.corrected_at <= effective_until)

        stmt = select(TranscriptCorrectionDB)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.order_by(TranscriptCorrectionDB.corrected_at.asc())

        result = await session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Aggregate statistics (Feature 036 — T007)
    # ------------------------------------------------------------------

    async def get_stats(
        self,
        session: AsyncSession,
        *,
        language: str | None = None,
        top: int = 10,
    ) -> dict[str, Any]:
        """
        Compute aggregate correction statistics.

        Returns a dict whose keys match the ``CorrectionStats`` model fields
        so the service layer can construct the model via
        ``CorrectionStats(**result)``.

        Uses at most 3 SQL round-trips:
        1. Conditional aggregation for totals (corrections, reverts,
           unique segments, unique videos).
        2. GROUP BY correction_type for the ``by_type`` breakdown.
        3. Top-N most-corrected videos with LEFT JOIN for title.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        language : str or None, optional
            If provided, restrict statistics to corrections with this
            ``language_code``.
        top : int, optional
            Number of top videos to return (default 10).

        Returns
        -------
        dict[str, Any]
            Keys: ``total_corrections``, ``total_reverts``,
            ``unique_segments``, ``unique_videos``, ``by_type``,
            ``top_videos``.
        """
        revert_value = CorrectionType.REVERT.value

        # Shared language filter condition
        lang_conditions: list[Any] = []
        if language is not None:
            lang_conditions.append(
                TranscriptCorrectionDB.language_code == language
            )

        # ---- Query 1: conditional aggregation for scalar totals ----
        is_not_revert = TranscriptCorrectionDB.correction_type != revert_value
        is_revert = TranscriptCorrectionDB.correction_type == revert_value

        totals_stmt = select(
            func.count(case((is_not_revert, 1))).label("total_corrections"),
            func.count(case((is_revert, 1))).label("total_reverts"),
            func.count(
                distinct(case((is_not_revert, TranscriptCorrectionDB.segment_id)))
            ).label("unique_segments"),
            func.count(
                distinct(case((is_not_revert, TranscriptCorrectionDB.video_id)))
            ).label("unique_videos"),
        ).select_from(TranscriptCorrectionDB)
        if lang_conditions:
            totals_stmt = totals_stmt.where(and_(*lang_conditions))

        totals_result = await session.execute(totals_stmt)
        totals_row = totals_result.one()

        # ---- Query 2: by_type breakdown (excluding reverts) ----
        by_type_conditions = [is_not_revert] + lang_conditions
        by_type_stmt = (
            select(
                TranscriptCorrectionDB.correction_type,
                func.count().label("cnt"),
            )
            .where(and_(*by_type_conditions))
            .group_by(TranscriptCorrectionDB.correction_type)
            .order_by(func.count().desc())
            .select_from(TranscriptCorrectionDB)
        )

        by_type_result = await session.execute(by_type_stmt)
        by_type = [
            TypeCount(correction_type=row.correction_type, count=row.cnt)
            for row in by_type_result.all()
        ]

        # ---- Query 3: top N most-corrected videos (excluding reverts) ----
        top_conditions = [is_not_revert] + lang_conditions
        top_subq = (
            select(
                TranscriptCorrectionDB.video_id,
                func.count().label("cnt"),
            )
            .where(and_(*top_conditions))
            .group_by(TranscriptCorrectionDB.video_id)
            .order_by(func.count().desc())
            .limit(top)
            .subquery()
        )

        top_stmt = (
            select(
                top_subq.c.video_id,
                VideoDB.title,
                top_subq.c.cnt,
            )
            .outerjoin(VideoDB, top_subq.c.video_id == VideoDB.video_id)
            .order_by(top_subq.c.cnt.desc())
        )

        top_result = await session.execute(top_stmt)
        top_videos = [
            VideoCount(video_id=row.video_id, title=row.title, count=row.cnt)
            for row in top_result.all()
        ]

        return {
            "total_corrections": totals_row.total_corrections,
            "total_reverts": totals_row.total_reverts,
            "unique_segments": totals_row.unique_segments,
            "unique_videos": totals_row.unique_videos,
            "by_type": by_type,
            "top_videos": top_videos,
        }

    # ------------------------------------------------------------------
    # Pattern discovery (Feature 036 — T008)
    # ------------------------------------------------------------------

    async def get_correction_patterns(
        self,
        session: AsyncSession,
        *,
        min_occurrences: int = 2,
        limit: int = 25,
        show_completed: bool = False,
    ) -> list[CorrectionPattern]:
        """
        Discover recurring correction patterns across all transcripts.

        Groups transcript corrections by ``(original_text, corrected_text)``
        pairs (excluding reverts) and counts how many distinct segments share
        each pattern.  For each pair a ``remaining_matches`` count is computed
        by scanning transcript segments whose *effective text* (respecting
        ``has_correction``) still contains the original text — i.e. segments
        that have not yet been corrected.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        min_occurrences : int, optional
            Minimum number of distinct segments with this correction before
            the pattern is included (default 2).
        limit : int, optional
            Maximum number of patterns to return (default 25).
        show_completed : bool, optional
            If ``False`` (default), exclude patterns where
            ``remaining_matches == 0`` (all instances already corrected).

        Returns
        -------
        list[CorrectionPattern]
            Patterns sorted by ``remaining_matches`` DESC (highest-impact
            first), limited to *limit* rows.
        """
        revert_value = CorrectionType.REVERT.value

        # ---- Step 1: grouped pairs with occurrence counts ----
        pairs_stmt = (
            select(
                TranscriptCorrectionDB.original_text,
                TranscriptCorrectionDB.corrected_text,
                func.count(
                    distinct(TranscriptCorrectionDB.segment_id)
                ).label("occurrences"),
            )
            .where(TranscriptCorrectionDB.correction_type != revert_value)
            .group_by(
                TranscriptCorrectionDB.original_text,
                TranscriptCorrectionDB.corrected_text,
            )
            .having(
                func.count(distinct(TranscriptCorrectionDB.segment_id))
                >= min_occurrences
            )
        )

        pairs_result = await session.execute(pairs_stmt)
        pairs = pairs_result.all()

        if not pairs:
            return []

        # ---- Step 2: remaining_matches for each pair ----
        # Build the effective text expression for transcript segments
        effective_text = case(
            (TranscriptSegmentDB.has_correction, TranscriptSegmentDB.corrected_text),
            else_=TranscriptSegmentDB.text,
        )

        patterns: list[CorrectionPattern] = []
        for row in pairs:
            remaining_stmt = (
                select(func.count())
                .select_from(TranscriptSegmentDB)
                .where(
                    effective_text.contains(row.original_text)
                )
            )
            remaining_result = await session.execute(remaining_stmt)
            remaining = remaining_result.scalar_one()

            if not show_completed and remaining == 0:
                continue

            patterns.append(
                CorrectionPattern(
                    original_text=row.original_text,
                    corrected_text=row.corrected_text,
                    occurrences=row.occurrences,
                    remaining_matches=remaining,
                )
            )

        # Sort by remaining_matches DESC, then limit
        patterns.sort(key=lambda p: p.remaining_matches, reverse=True)
        return patterns[:limit]

    async def get_by_batch_id(
        self,
        session: AsyncSession,
        batch_id: UUID,
    ) -> list[TranscriptCorrectionDB]:
        """
        Get all corrections belonging to a specific batch.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        batch_id : UUID
            The batch identifier (UUIDv7).

        Returns
        -------
        list[TranscriptCorrectionDB]
            Corrections sharing the given batch_id, ordered by
            ``corrected_at`` ascending.
        """
        stmt = (
            select(TranscriptCorrectionDB)
            .where(TranscriptCorrectionDB.batch_id == batch_id)
            .order_by(TranscriptCorrectionDB.corrected_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_batch_list(
        self,
        session: AsyncSession,
        *,
        offset: int = 0,
        limit: int = 20,
        corrected_by_user_id: str | None = None,
    ) -> list[BatchListItem]:
        """
        List batch correction groups with aggregated metadata.

        Aggregates corrections by ``batch_id`` (excluding NULLs), returning
        summary rows sorted by earliest ``corrected_at`` descending (most
        recent batches first).

        Parameters
        ----------
        session : AsyncSession
            Database session.
        offset : int, optional
            Number of rows to skip (default 0).
        limit : int, optional
            Maximum rows to return (default 20).
        corrected_by_user_id : str or None, optional
            If provided, restrict to batches by this user/actor.

        Returns
        -------
        list[BatchListItem]
            Summary rows for each batch group.
        """
        conditions: list[Any] = [
            TranscriptCorrectionDB.batch_id.isnot(None),
        ]
        if corrected_by_user_id is not None:
            conditions.append(
                TranscriptCorrectionDB.corrected_by_user_id == corrected_by_user_id
            )

        stmt = (
            select(
                TranscriptCorrectionDB.batch_id,
                func.count().label("correction_count"),
                func.min(TranscriptCorrectionDB.corrected_by_user_id).label(
                    "corrected_by_user_id"
                ),
                func.min(TranscriptCorrectionDB.original_text).label("pattern"),
                func.min(TranscriptCorrectionDB.corrected_text).label("replacement"),
                func.min(TranscriptCorrectionDB.corrected_at).label(
                    "batch_timestamp"
                ),
            )
            .where(and_(*conditions))
            .group_by(TranscriptCorrectionDB.batch_id)
            .order_by(func.min(TranscriptCorrectionDB.corrected_at).desc())
            .offset(offset)
            .limit(limit)
        )

        result = await session.execute(stmt)
        return [
            BatchListItem(
                batch_id=row.batch_id,
                correction_count=row.correction_count,
                corrected_by_user_id=row.corrected_by_user_id or "",
                pattern=row.pattern or "",
                replacement=row.replacement or "",
                batch_timestamp=row.batch_timestamp,
            )
            for row in result.all()
        ]

    async def get_latest_version(
        self,
        session: AsyncSession,
        video_id: str,
        language_code: str,
        segment_id: int,
    ) -> int:
        """
        Get the highest version_number for a segment's correction chain.

        Uses ``SELECT ... FOR UPDATE`` to prevent concurrent inserts from
        creating duplicate version numbers (NFR-005).

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_id : str
            YouTube video ID.
        language_code : str
            BCP-47 language code.
        segment_id : int
            FK to transcript_segments.id.

        Returns
        -------
        int
            The highest version_number, or 0 if no corrections exist yet.
        """
        # Lock the matching rows first, then compute max in Python.
        # PostgreSQL does not allow FOR UPDATE with aggregate functions.
        stmt = (
            select(TranscriptCorrectionDB.version_number)
            .where(
                and_(
                    TranscriptCorrectionDB.video_id == video_id,
                    TranscriptCorrectionDB.language_code == language_code,
                    TranscriptCorrectionDB.segment_id == segment_id,
                )
            )
            .with_for_update()
        )
        result = await session.execute(stmt)
        versions = result.scalars().all()
        return max(versions) if versions else 0


__all__ = ["TranscriptCorrectionRepository"]
