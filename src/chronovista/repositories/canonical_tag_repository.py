"""
Canonical tag repository for tag normalization management.

Handles CRUD operations for canonical tags that represent the normalized,
deduplicated form of video tags with lifecycle management and merge tracking.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import desc, distinct, exists, func, or_, select
from sqlalchemy.sql import Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTag
from chronovista.models.canonical_tag import CanonicalTagCreate, CanonicalTagUpdate
from chronovista.repositories.base import BaseSQLAlchemyRepository


class CanonicalTagRepository(
    BaseSQLAlchemyRepository[
        CanonicalTagDB,
        CanonicalTagCreate,
        CanonicalTagUpdate,
        uuid.UUID,
    ]
):
    """Repository for canonical tag CRUD operations."""

    def __init__(self) -> None:
        """Initialize repository with CanonicalTag model."""
        super().__init__(CanonicalTagDB)

    async def get(
        self, session: AsyncSession, id: uuid.UUID
    ) -> Optional[CanonicalTagDB]:
        """Get canonical tag by UUID primary key."""
        result = await session.execute(
            select(CanonicalTagDB).where(CanonicalTagDB.id == id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, id: uuid.UUID) -> bool:
        """Check if canonical tag exists by UUID primary key."""
        result = await session.execute(
            select(CanonicalTagDB.id).where(CanonicalTagDB.id == id)
        )
        return result.first() is not None

    async def search(
        self,
        session: AsyncSession,
        *,
        q: str | None = None,
        status: str = "active",
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[CanonicalTagDB], int]:
        """
        Search canonical tags with optional prefix matching and pagination.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        q : str | None, optional
            Prefix search query applied to canonical_form and normalized_form
            via ILIKE (case-insensitive). When None, no text filter is applied.
        status : str, optional
            Tag lifecycle status filter (default ``"active"``).
        skip : int, optional
            Number of rows to skip for pagination (default 0).
        limit : int, optional
            Maximum rows to return (default 20).

        Returns
        -------
        tuple[list[CanonicalTagDB], int]
            A tuple of ``(items, total_count)`` where *items* is the paginated
            result list ordered by ``video_count DESC`` and *total_count* is
            the total number of matching rows (ignoring pagination).
        """
        base_query = select(CanonicalTagDB).where(
            CanonicalTagDB.status == status
        )

        if q is not None:
            pattern = f"{q}%"
            # Match canonical tags whose alias raw_form starts with the query.
            # EXISTS avoids row duplication when a tag has multiple matching aliases.
            alias_match = exists(
                select(TagAliasDB.id).where(
                    TagAliasDB.canonical_tag_id == CanonicalTagDB.id,
                    TagAliasDB.raw_form.ilike(pattern),
                )
            )
            base_query = base_query.where(
                or_(
                    CanonicalTagDB.canonical_form.ilike(pattern),
                    CanonicalTagDB.normalized_form.ilike(pattern),
                    alias_match,
                )
            )

        # Total count (without pagination)
        count_subquery = base_query.subquery()
        count_query = select(func.count()).select_from(count_subquery)
        total_result = await session.execute(count_query)
        total_count: int = total_result.scalar_one()

        # Paginated items ordered by video_count descending
        items_query = (
            base_query
            .order_by(desc(CanonicalTagDB.video_count))
            .offset(skip)
            .limit(limit)
        )
        items_result = await session.execute(items_query)
        items: list[CanonicalTagDB] = list(items_result.scalars().all())

        return items, total_count

    async def get_by_normalized_form(
        self,
        session: AsyncSession,
        normalized_form: str,
        *,
        status: str = "active",
    ) -> CanonicalTagDB | None:
        """
        Look up a single canonical tag by its unique normalized form.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        normalized_form : str
            The normalized (lowered, stripped) tag string.
        status : str, optional
            Required lifecycle status (default ``"active"``).

        Returns
        -------
        CanonicalTagDB | None
            The matching canonical tag, or ``None`` if not found.
        """
        result = await session.execute(
            select(CanonicalTagDB).where(
                CanonicalTagDB.normalized_form == normalized_form,
                CanonicalTagDB.status == status,
            )
        )
        return result.scalar_one_or_none()

    async def get_top_aliases(
        self,
        session: AsyncSession,
        canonical_tag_id: uuid.UUID,
        *,
        limit: int = 5,
    ) -> list[TagAliasDB]:
        """
        Return the top aliases for a canonical tag ordered by usage frequency.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        canonical_tag_id : uuid.UUID
            Primary key of the canonical tag.
        limit : int, optional
            Maximum number of aliases to return (default 5).

        Returns
        -------
        list[TagAliasDB]
            Aliases ordered by ``occurrence_count DESC``.
        """
        result = await session.execute(
            select(TagAliasDB)
            .where(TagAliasDB.canonical_tag_id == canonical_tag_id)
            .order_by(desc(TagAliasDB.occurrence_count))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_videos_by_normalized_form(
        self,
        session: AsyncSession,
        normalized_form: str,
        *,
        include_unavailable: bool = False,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[VideoDB], int]:
        """
        Fetch videos linked to a canonical tag via the 3-table join path.

        Join path: ``canonical_tags -> tag_aliases (canonical_tag_id)
        -> video_tags (raw_form = tag) -> videos (video_id)``.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        normalized_form : str
            The normalized tag string to look up.
        include_unavailable : bool, optional
            When ``False`` (default), only videos with
            ``availability_status = 'available'`` are returned.
        skip : int, optional
            Pagination offset (default 0).
        limit : int, optional
            Maximum rows to return (default 20).

        Returns
        -------
        tuple[list[VideoDB], int]
            A tuple of ``(items, total_count)`` where *items* are distinct
            videos ordered by ``upload_date DESC`` with eagerly-loaded
            ``channel``, ``transcripts``, and ``category`` relationships,
            and *total_count* is the full count ignoring pagination.
        """
        # --- Total count (distinct videos, no eager loading) ---
        count_query = (
            select(func.count(distinct(VideoDB.video_id)))
            .select_from(CanonicalTagDB)
            .join(TagAliasDB, TagAliasDB.canonical_tag_id == CanonicalTagDB.id)
            .join(VideoTag, VideoTag.tag == TagAliasDB.raw_form)
            .join(VideoDB, VideoDB.video_id == VideoTag.video_id)
            .where(
                CanonicalTagDB.normalized_form == normalized_form,
                CanonicalTagDB.status == "active",
            )
        )
        if not include_unavailable:
            count_query = count_query.where(
                VideoDB.availability_status == "available"
            )

        total_result = await session.execute(count_query)
        total_count: int = total_result.scalar_one()

        # --- Paginated items with eagerly-loaded channel, transcripts, and category ---
        items_query = (
            select(VideoDB)
            .distinct()
            .join(VideoTag, VideoTag.video_id == VideoDB.video_id)
            .join(TagAliasDB, TagAliasDB.raw_form == VideoTag.tag)
            .join(CanonicalTagDB, CanonicalTagDB.id == TagAliasDB.canonical_tag_id)
            .where(
                CanonicalTagDB.normalized_form == normalized_form,
                CanonicalTagDB.status == "active",
            )
            .options(selectinload(VideoDB.channel))
            .options(selectinload(VideoDB.transcripts))
            .options(selectinload(VideoDB.category))
            .order_by(desc(VideoDB.upload_date))
            .offset(skip)
            .limit(limit)
        )
        if not include_unavailable:
            items_query = items_query.where(
                VideoDB.availability_status == "available"
            )

        items_result = await session.execute(items_query)
        items: list[VideoDB] = list(items_result.scalars().all())

        return items, total_count

    async def resolve_by_raw_form(
        self,
        session: AsyncSession,
        raw_form: str,
    ) -> CanonicalTagDB | None:
        """
        Resolve a raw tag string to its canonical tag via exact alias lookup.

        Performs case-insensitive exact match on tag_aliases.raw_form,
        returning the linked active canonical tag or None.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        raw_form : str
            The exact raw tag string to look up.

        Returns
        -------
        CanonicalTagDB | None
            The linked canonical tag if found and active, else None.
        """
        result = await session.execute(
            select(CanonicalTagDB)
            .join(TagAliasDB, TagAliasDB.canonical_tag_id == CanonicalTagDB.id)
            .where(
                TagAliasDB.raw_form.ilike(raw_form),
                CanonicalTagDB.status == "active",
            )
        )
        return result.scalars().first()

    async def build_canonical_tag_video_subqueries(
        self,
        session: AsyncSession,
        normalized_forms: list[str],
    ) -> list[Select[Any]]:
        """
        Build SQLAlchemy subqueries for filtering videos by canonical tags.

        For each normalized_form, builds a subquery that selects video_ids
        linked to that canonical tag via the 3-table join path:
        canonical_tags -> tag_aliases -> video_tags.

        Uses OR semantics: the caller UNIONs the subqueries so that
        videos matching ANY of the canonical tags are returned.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        normalized_forms : list[str]
            List of canonical tag normalized forms to filter by.

        Returns
        -------
        list[Select[Any]]
            List of SQLAlchemy Select subqueries for recognized canonical
            tags.  Unrecognized normalized_forms are silently skipped
            (OR semantics — valid tags still produce results).
        """
        if not normalized_forms:
            return []

        subqueries: list[Select[Any]] = []

        for nf in normalized_forms:
            # Check if the canonical tag exists and is active
            ct = await self.get_by_normalized_form(session, nf, status="active")
            if ct is None:
                # Skip unrecognized tags — OR semantics means we still
                # show results for the remaining valid tags.
                continue

            # Build subquery for this canonical tag
            sq = (
                select(VideoTag.video_id)
                .join(TagAliasDB, TagAliasDB.raw_form == VideoTag.tag)
                .join(
                    CanonicalTagDB,
                    CanonicalTagDB.id == TagAliasDB.canonical_tag_id,
                )
                .where(
                    CanonicalTagDB.normalized_form == nf,
                    CanonicalTagDB.status == "active",
                )
                .distinct()
            )
            subqueries.append(sq)

        return subqueries
