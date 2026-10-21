"""Async repository for ``entity_categories`` (Feature 083).

The normalized entity↔category assignment, plus the shared-category **bridge**: a self-join
on ``category_id`` that answers "which entities share a category with X", optionally capped
by category specificity (``global_size``).
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from chronovista.db.models import EntityCategory as EntityCategoryDB
from chronovista.db.models import WikipediaCategory as WikipediaCategoryDB
from chronovista.models.wikipedia_category import BridgeNeighbor, WikipediaCategory


class EntityCategoryRepository:
    """Data access for entity→category assignments and the shared-category bridge."""

    async def add(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        category_id: uuid.UUID,
        source: str,
        set_at: datetime.datetime | None = None,
    ) -> None:
        """Add an assignment; a duplicate ``(entity_id, category_id)`` is a no-op (idempotent)."""
        await session.execute(
            pg_insert(EntityCategoryDB)
            .values(
                entity_id=entity_id,
                category_id=category_id,
                source=source,
                set_at=set_at,
            )
            .on_conflict_do_nothing(index_elements=["entity_id", "category_id"])
        )

    async def categories_for(
        self, session: AsyncSession, entity_id: uuid.UUID
    ) -> list[WikipediaCategory]:
        """Return the categories assigned to one entity."""
        result = await session.execute(
            select(WikipediaCategoryDB)
            .join(
                EntityCategoryDB,
                EntityCategoryDB.category_id == WikipediaCategoryDB.id,
            )
            .where(EntityCategoryDB.entity_id == entity_id)
        )
        return [WikipediaCategory.model_validate(r) for r in result.scalars().all()]

    async def shared_category_bridge(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        max_global_size: int | None = None,
    ) -> list[BridgeNeighbor]:
        """Entities that share a category with ``entity_id`` (excluding itself).

        Self-joins ``entity_categories`` on ``category_id`` (served by
        ``idx_entity_categories_category_id``). When ``max_global_size`` is given, a shared
        category is kept only if its ``global_size`` is known and ``<=`` the cap — a category
        of unknown size is treated as non-specific and excluded (FR-006).
        """
        ec1 = aliased(EntityCategoryDB)
        ec2 = aliased(EntityCategoryDB)
        stmt = (
            select(
                ec2.entity_id.label("neighbor_id"),
                WikipediaCategoryDB.name.label("shared_category"),
                WikipediaCategoryDB.global_size.label("global_size"),
            )
            .select_from(ec1)
            .join(
                ec2,
                and_(
                    ec2.category_id == ec1.category_id,
                    ec2.entity_id != ec1.entity_id,
                ),
            )
            .join(WikipediaCategoryDB, WikipediaCategoryDB.id == ec1.category_id)
            .where(ec1.entity_id == entity_id)
        )
        if max_global_size is not None:
            stmt = stmt.where(
                WikipediaCategoryDB.global_size.is_not(None),
                WikipediaCategoryDB.global_size <= max_global_size,
            )
        result = await session.execute(stmt)
        return [
            BridgeNeighbor(
                neighbor_id=row.neighbor_id,
                shared_category=row.shared_category,
                global_size=row.global_size,
            )
            for row in result.all()
        ]
