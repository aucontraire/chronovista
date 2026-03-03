"""
Repository for TranscriptCorrection database operations.

Provides append-only audit log access following the repository pattern.
Records are immutable once created (FR-018): update() and delete() raise
NotImplementedError.

This repository supports Feature 033: Transcript Corrections Audit (FR-012,
FR-018, NFR-005).
"""

from __future__ import annotations

from typing import Any, Optional, Union
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
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
        obj_in: Union[TranscriptCorrectionCreate, dict[str, Any]],
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
    ) -> Optional[TranscriptCorrectionDB]:
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
    ) -> Optional[TranscriptCorrectionDB]:
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
