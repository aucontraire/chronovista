"""Async repository for entity↔video exclusions (Feature 091).

The per-(entity, video) negative association. CRUD only — the subtraction that makes an
exclusion take effect lives in the single shared association definition
(``EntityMentionRepository._tag_inclusive_association_arms``), never here.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityVideoExclusion as EntityVideoExclusionDB
from chronovista.models.entity_video_exclusion import EntityVideoExclusion


class EntityVideoExclusionRepository:
    """Data access for entity→video exclusions (Feature 091)."""

    async def add(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        video_id: str,
        excluded_by: str,
        reason: str | None = None,
    ) -> bool:
        """Insert an exclusion for ``(entity_id, video_id)``.

        Returns ``True`` when a new exclusion was created, ``False`` when the pair was
        already excluded (idempotent no-op, FR-006). Does not commit — the caller owns
        the transaction.
        """
        result = await session.execute(
            pg_insert(EntityVideoExclusionDB)
            .values(
                entity_id=entity_id,
                video_id=video_id,
                excluded_by=excluded_by,
                reason=reason,
            )
            .on_conflict_do_nothing(index_elements=["entity_id", "video_id"])
        )
        return bool(result.rowcount)

    async def remove(
        self, session: AsyncSession, entity_id: uuid.UUID, video_id: str
    ) -> bool:
        """Delete the exclusion for ``(entity_id, video_id)``; return ``True`` if one was removed."""
        result = await session.execute(
            delete(EntityVideoExclusionDB).where(
                EntityVideoExclusionDB.entity_id == entity_id,
                EntityVideoExclusionDB.video_id == video_id,
            )
        )
        return bool(result.rowcount)

    async def exists(
        self, session: AsyncSession, entity_id: uuid.UUID, video_id: str
    ) -> bool:
        """Whether ``(entity_id, video_id)`` is currently excluded."""
        result = await session.execute(
            select(EntityVideoExclusionDB.entity_id)
            .where(
                EntityVideoExclusionDB.entity_id == entity_id,
                EntityVideoExclusionDB.video_id == video_id,
            )
            .limit(1)
        )
        return result.first() is not None

    async def get(
        self, session: AsyncSession, entity_id: uuid.UUID, video_id: str
    ) -> EntityVideoExclusion | None:
        """Return the stored exclusion for ``(entity_id, video_id)``, or ``None``."""
        row = (
            await session.execute(
                select(EntityVideoExclusionDB).where(
                    EntityVideoExclusionDB.entity_id == entity_id,
                    EntityVideoExclusionDB.video_id == video_id,
                )
            )
        ).scalar_one_or_none()
        return EntityVideoExclusion.model_validate(row) if row is not None else None

    async def list_for_entity(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[EntityVideoExclusion], int]:
        """Return ``(page, total)`` of ``entity_id``'s exclusions, most-recent-first.

        ``total`` is the unpaginated count, for the list response's pagination metadata.
        """
        total = await session.scalar(
            select(func.count())
            .select_from(EntityVideoExclusionDB)
            .where(EntityVideoExclusionDB.entity_id == entity_id)
        )
        rows = (
            (
                await session.execute(
                    select(EntityVideoExclusionDB)
                    .where(EntityVideoExclusionDB.entity_id == entity_id)
                    .order_by(
                        EntityVideoExclusionDB.excluded_at.desc(),
                        EntityVideoExclusionDB.video_id,
                    )
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return (
            [EntityVideoExclusion.model_validate(row) for row in rows],
            int(total or 0),
        )
