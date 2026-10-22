"""Async repository for ``entity_categories`` (Feature 083).

The normalized entity↔category assignment, plus the shared-category **bridge**: a self-join
on ``category_id`` that answers "which entities share a category with X", optionally capped
by category specificity (``global_size``).
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from chronovista.db.models import EntityCategory as EntityCategoryDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import WikipediaCategory as WikipediaCategoryDB
from chronovista.models.wikipedia_category import (
    BridgeNeighbor,
    CategoryMember,
    SharedCategoryNeighbour,
    SharedCategoryRef,
    WikipediaCategory,
)


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

    async def delete_for_entity(
        self, session: AsyncSession, entity_id: uuid.UUID
    ) -> int:
        """Remove all of ``entity_id``'s category assignments; return the count removed.

        Enables the Feature 084 **replace** (delete-then-add) for the existing DBpedia-sourced
        373: the batch deletes their assignments, then re-adds the Wikipedia namespace. Scoped to
        the one entity by ``entity_id`` — it never touches another entity's rows (the SET/WHERE
        the mock test asserts). Add-only callers (the 1,441 and the on-approval seam) keep using
        :meth:`add` and never call this.
        """
        result = await session.execute(
            delete(EntityCategoryDB).where(EntityCategoryDB.entity_id == entity_id)
        )
        return result.rowcount or 0

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

    async def shared_category_neighbours(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        max_category_size: int,
    ) -> list[SharedCategoryNeighbour]:
        """Aggregated shared-category neighbours for the entity-page surface (Feature 085).

        One row **per neighbour entity** (unlike :meth:`shared_category_bridge`, which is one row
        per shared category), produced by a single grouped self-join:

        - **active neighbours only** (``named_entities.status = 'active'``), excluding the entity
          itself;
        - a shared category counts only when its ``global_size`` is **unknown (NULL)** or at/below
          ``max_category_size`` — so a neighbour whose *only* shared categories are known mega-hubs
          contributes nothing and does not appear (hub suppression);
        - ranked by **shared-category count descending**, ties broken by **specificity** (the
          smallest shared category's ``global_size`` ascending, NULLs last);
        - ``shared_categories`` lists the matched categories most-specific-first, each as an
          ``{id, name}`` ref (Feature 086 — the id lets a chip link to the category page);
        - bounded by ``limit``/``offset``.

        Read-only. ``shared_category_bridge`` is unchanged.
        """
        ec1 = aliased(EntityCategoryDB)
        ec2 = aliased(EntityCategoryDB)
        min_size = func.min(WikipediaCategoryDB.global_size)
        # Both array_aggs share this ORDER BY. global_size alone is not a total order (ties, and
        # NULLs), so a second `id` key makes it total — guaranteeing names[i] and ids[i] are the
        # SAME category when we zip them into {id, name} refs below (Feature 086).
        _cat_order = (
            WikipediaCategoryDB.global_size.asc().nullslast(),
            WikipediaCategoryDB.id.asc(),
        )
        stmt = (
            select(
                ec2.entity_id.label("entity_id"),
                NamedEntityDB.entity_type.label("entity_type"),
                NamedEntityDB.canonical_name.label("canonical_name"),
                func.count().label("shared_category_count"),
                func.array_agg(
                    aggregate_order_by(WikipediaCategoryDB.name, *_cat_order)
                ).label("shared_category_names"),
                func.array_agg(
                    aggregate_order_by(WikipediaCategoryDB.id, *_cat_order)
                ).label("shared_category_ids"),
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
            .join(
                NamedEntityDB,
                and_(
                    NamedEntityDB.id == ec2.entity_id,
                    NamedEntityDB.status == "active",
                ),
            )
            .where(ec1.entity_id == entity_id)
            .where(
                or_(
                    WikipediaCategoryDB.global_size.is_(None),
                    WikipediaCategoryDB.global_size <= max_category_size,
                )
            )
            .group_by(
                ec2.entity_id,
                NamedEntityDB.entity_type,
                NamedEntityDB.canonical_name,
            )
            # Final tiebreak on entity_id makes the order TOTAL, so LIMIT/OFFSET paging is stable
            # when count and specificity tie (otherwise a row could be skipped/repeated across pages).
            .order_by(
                func.count().desc(),
                min_size.asc().nullslast(),
                ec2.entity_id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return [
            SharedCategoryNeighbour(
                entity_id=row.entity_id,
                entity_type=row.entity_type,
                canonical_name=row.canonical_name,
                shared_categories=[
                    SharedCategoryRef(id=cat_id, name=cat_name)
                    # strict=True: the aligned total ORDER BY guarantees equal lengths today, so
                    # this never trips in correct operation — but it turns any FUTURE desync (one
                    # array_agg's ORDER BY changed without the other) into a loud error instead of
                    # a silent mispairing that zip() would otherwise truncate past.
                    for cat_id, cat_name in zip(
                        row.shared_category_ids,
                        row.shared_category_names,
                        strict=True,
                    )
                ],
                shared_category_count=row.shared_category_count,
            )
            for row in result.all()
        ]

    async def entities_in_category(
        self,
        session: AsyncSession,
        category_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> list[CategoryMember]:
        """Active library entities assigned to ``category_id`` (Feature 086).

        The inverse of the shared-category bridge: given a category, list its members. One
        indexed join ``entity_categories → named_entities`` (served by
        ``idx_entity_categories_category_id``), **active only**
        (``named_entities.status = 'active'``, mirroring Feature 085), ordered by a **total**
        key — ``lower(canonical_name)`` then ``id`` — so ``LIMIT``/``OFFSET`` paging never skips
        or repeats a member when two names collide case-insensitively. Read-only.
        """
        stmt = (
            select(
                NamedEntityDB.id.label("entity_id"),
                NamedEntityDB.entity_type.label("entity_type"),
                NamedEntityDB.canonical_name.label("canonical_name"),
            )
            .select_from(EntityCategoryDB)
            .join(
                NamedEntityDB,
                and_(
                    NamedEntityDB.id == EntityCategoryDB.entity_id,
                    NamedEntityDB.status == "active",
                ),
            )
            .where(EntityCategoryDB.category_id == category_id)
            .order_by(
                func.lower(NamedEntityDB.canonical_name).asc(),
                NamedEntityDB.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return [
            CategoryMember(
                entity_id=row.entity_id,
                entity_type=row.entity_type,
                canonical_name=row.canonical_name,
            )
            for row in result.all()
        ]

    async def count_active_members(
        self, session: AsyncSession, category_id: uuid.UUID
    ) -> int:
        """Count the active library entities assigned to ``category_id`` (Feature 086).

        The total behind the member list's pagination and the page's member count. Same
        active-only filter as :meth:`entities_in_category`; a single ``count(*)`` over the
        indexed join, no row materialisation.
        """
        stmt = (
            select(func.count())
            .select_from(EntityCategoryDB)
            .join(
                NamedEntityDB,
                and_(
                    NamedEntityDB.id == EntityCategoryDB.entity_id,
                    NamedEntityDB.status == "active",
                ),
            )
            .where(EntityCategoryDB.category_id == category_id)
        )
        result = await session.execute(stmt)
        return int(result.scalar_one())
