"""Async repository for ``wikipedia_categories`` (Feature 083).

One row per distinct category, holding the stable ``global_size``. ``upsert`` is the
idempotent insert-or-get used by the backfill and the on-approval enrichment seam.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import WikipediaCategory as WikipediaCategoryDB
from chronovista.models.wikipedia_category import WikipediaCategory


class WikipediaCategoryRepository:
    """Data access for Wikipedia categories."""

    async def get_by_name(
        self, session: AsyncSession, name: str
    ) -> WikipediaCategory | None:
        """Return the category with this exact name, or None."""
        result = await session.execute(
            select(WikipediaCategoryDB).where(WikipediaCategoryDB.name == name)
        )
        row = result.scalar_one_or_none()
        return WikipediaCategory.model_validate(row) if row is not None else None

    async def upsert(self, session: AsyncSession, name: str) -> WikipediaCategory:
        """Insert the category if absent, else return the existing one (idempotent).

        Uses ``ON CONFLICT (name) DO NOTHING`` against the UNIQUE ``name`` constraint,
        then reads the row back (new or pre-existing) within the same transaction.
        """
        await session.execute(
            pg_insert(WikipediaCategoryDB)
            .values(name=name)
            .on_conflict_do_nothing(index_elements=["name"])
        )
        row = await self.get_by_name(session, name)
        if row is None:  # pragma: no cover — UNIQUE name guarantees a row exists here
            raise RuntimeError(f"upsert failed to persist category {name!r}")
        return row

    async def set_global_size(
        self,
        session: AsyncSession,
        category_id: uuid.UUID,
        global_size: int,
        fetched_at: datetime.datetime,
    ) -> None:
        """Set ``global_size`` + ``global_size_fetched_at`` on one category row.

        Single source of truth: the size lives once, on the category, never duplicated
        onto assignments.
        """
        await session.execute(
            update(WikipediaCategoryDB)
            .where(WikipediaCategoryDB.id == category_id)
            .values(global_size=global_size, global_size_fetched_at=fetched_at)
        )

    async def names_without_global_size(
        self, session: AsyncSession, names: list[str]
    ) -> list[str]:
        """Of ``names``, return those whose category row still has a NULL ``global_size``.

        Lets a size fetch be **incremental**: a re-run after a rate-limited pass asks the API only
        for the categories still missing a size, instead of re-fetching every one.
        """
        if not names:
            return []
        result = await session.execute(
            select(WikipediaCategoryDB.name).where(
                WikipediaCategoryDB.name.in_(names),
                WikipediaCategoryDB.global_size.is_(None),
            )
        )
        return list(result.scalars().all())
