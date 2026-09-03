"""
Named entity repository for entity extraction and management.

Handles CRUD operations for named entities discovered from tags and transcripts,
supporting entity resolution, merge tracking, and confidence scoring.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import bindparam, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.named_entity import NamedEntityCreate, NamedEntityUpdate
from chronovista.repositories.base import BaseSQLAlchemyRepository
from chronovista.repositories.entity_mention_repository import _folded


class NamedEntityRepository(
    BaseSQLAlchemyRepository[
        NamedEntityDB,
        NamedEntityCreate,
        NamedEntityUpdate,
        uuid.UUID,
    ]
):
    """Repository for named entity CRUD operations."""

    def __init__(self) -> None:
        """Initialize repository with NamedEntity model."""
        super().__init__(NamedEntityDB)

    async def get(self, session: AsyncSession, id: uuid.UUID) -> NamedEntityDB | None:
        """Get named entity by UUID primary key."""
        result = await session.execute(
            select(NamedEntityDB).where(NamedEntityDB.id == id)
        )
        return result.scalar_one_or_none()

    async def find_by_name_or_alias(
        self, session: AsyncSession, name: str
    ) -> tuple[uuid.UUID | None, str | None]:
        """Look up a named entity by canonical name or alias (issue #256).

        Matches ``name`` case-insensitively against ``canonical_name`` first, then
        against ``entity_aliases.alias_name``; on an alias hit the entity's
        canonical name is resolved for display.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        name : str
            The text to match against canonical_name or alias_name.

        Returns
        -------
        tuple[uuid.UUID | None, str | None]
            ``(entity_id, entity_name)`` if found, otherwise ``(None, None)``.
        """
        stmt = (
            select(NamedEntityDB.id, NamedEntityDB.canonical_name)
            .where(NamedEntityDB.canonical_name.ilike(name))
            .limit(1)
        )
        row = (await session.execute(stmt)).first()
        if row is not None:
            return row.id, row.canonical_name

        alias_stmt = (
            select(EntityAliasDB.entity_id, EntityAliasDB.alias_name)
            .where(EntityAliasDB.alias_name.ilike(name))
            .limit(1)
        )
        alias_row = (await session.execute(alias_stmt)).first()
        if alias_row is not None:
            entity_stmt = select(NamedEntityDB.canonical_name).where(
                NamedEntityDB.id == alias_row.entity_id
            )
            entity_name_val = (await session.execute(entity_stmt)).scalar_one_or_none()
            return alias_row.entity_id, entity_name_val

        return None, None

    async def exists(self, session: AsyncSession, id: uuid.UUID) -> bool:
        """Check if named entity exists by UUID primary key."""
        result = await session.execute(
            select(NamedEntityDB.id).where(NamedEntityDB.id == id)
        )
        return result.first() is not None

    async def get_existing_ids(
        self, session: AsyncSession, ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Return which of the given entity ids exist, in one query.

        Used to reject unknown entity ids on the video filter before running
        the intersection (a conjunctive filter must not silently drop a
        required entity).

        Parameters
        ----------
        session : AsyncSession
            Database session.
        ids : Sequence[uuid.UUID]
            Candidate entity ids.

        Returns
        -------
        set[uuid.UUID]
            The subset of ``ids`` that exist. Empty when ``ids`` is empty.
        """
        id_list = list(ids)
        if not id_list:
            return set()
        result = await session.execute(
            select(NamedEntityDB.id).where(NamedEntityDB.id.in_(id_list))
        )
        return set(result.scalars().all())

    async def find_active_by_normalized_and_type(
        self, session: AsyncSession, normalized_name: str, entity_type: str
    ) -> NamedEntityDB | None:
        """Return the active entity with this normalized name + type (#256).

        The duplicate check for standalone entity creation. The
        ``uq_named_entity_canonical`` unique constraint on
        ``(canonical_name_normalized, entity_type)`` guarantees at most one row
        exists for the pair regardless of status, so filtering to ``active``
        yields zero or one — ``scalar_one_or_none`` is safe.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        normalized_name : str
            The normalized canonical name to match.
        entity_type : str
            The entity type value (e.g. ``"person"``).

        Returns
        -------
        NamedEntityDB | None
            The active matching entity, or ``None`` if none exists.
        """
        result = await session.execute(
            select(NamedEntityDB).where(
                NamedEntityDB.canonical_name_normalized == normalized_name,
                NamedEntityDB.entity_type == entity_type,
                NamedEntityDB.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def get_with_aliases(
        self, session: AsyncSession, id: uuid.UUID
    ) -> NamedEntityDB | None:
        """Get a named entity with its aliases eager-loaded (#256).

        Used by the detail endpoint, which renders the entity's aliases; the
        ``selectinload`` avoids a lazy load when the router iterates them.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        id : uuid.UUID
            The entity's UUID primary key.

        Returns
        -------
        NamedEntityDB | None
            The entity with ``.aliases`` populated, or ``None`` if absent.
        """
        result = await session.execute(
            select(NamedEntityDB)
            .where(NamedEntityDB.id == id)
            .options(selectinload(NamedEntityDB.aliases))
        )
        return result.scalar_one_or_none()

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        status: str = "active",
        entity_type: str | None = None,
        has_mentions: bool | None = None,
        search: str | None = None,
        search_aliases: bool = False,
        exclude_alias_types: list[str] | None = None,
        sort: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[NamedEntityDB], int]:
        """List named entities with status/type/mention/search filters (#256).

        Mirrors the entity-list endpoint's query. ``search`` is a case- AND
        accent-insensitive substring on ``canonical_name`` (folded via the shared
        ``lower(unaccent(...))`` expression — Feature 072); when ``search_aliases``
        is set it also matches ``entity_aliases.alias_name`` (minus any
        ``exclude_alias_types``) via a scalar sub-select. The count is taken over
        the filtered-but-unpaginated set so totals reflect every filter.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        status : str
            Entity status to filter by (default ``"active"``).
        entity_type : str | None
            Restrict to a single entity type.
        has_mentions : bool | None
            ``True`` → ``mention_count > 0``; ``False`` → ``== 0``.
        search : str | None
            Substring to match on ``canonical_name`` (and aliases when
            ``search_aliases``).
        search_aliases : bool
            Also match on ``entity_aliases.alias_name``.
        exclude_alias_types : list[str] | None
            Alias types to exclude from the alias match. Empty/``None`` excludes
            nothing.
        sort : str | None
            ``"mentions"`` → mention_count desc then name asc; else name asc.
        skip : int
            Pagination offset.
        limit : int
            Page size.

        Returns
        -------
        tuple[list[NamedEntityDB], int]
            The page of entities and the total matching count.
        """
        base = select(NamedEntityDB).where(NamedEntityDB.status == status)

        if entity_type is not None:
            base = base.where(NamedEntityDB.entity_type == entity_type)

        if has_mentions is True:
            base = base.where(NamedEntityDB.mention_count > 0)
        elif has_mentions is False:
            base = base.where(NamedEntityDB.mention_count == 0)

        if search:
            # Feature 072: fold BOTH the matched columns and the query pattern with
            # the same lower(unaccent(...)) fold, so accent variants and case never
            # split a search — symmetrically, in both directions (FR-001/FR-002).
            # The columns use the shared `_folded` helper; the pattern uses the
            # identical expression inline because `_folded` takes a column, not a
            # bare string (FR-003 — one fold definition, applied both sides). `.like`
            # (not `.ilike`) since both sides are already lowercased. Wildcard chars
            # in `search` are intentionally left unescaped (pre-existing; out of scope).
            folded_pattern = func.lower(func.unaccent(f"%{search}%"))
            if search_aliases:
                alias_select = select(EntityAliasDB.entity_id).where(
                    _folded(EntityAliasDB.alias_name).like(folded_pattern)
                )
                if exclude_alias_types:
                    alias_select = alias_select.where(
                        EntityAliasDB.alias_type.notin_(exclude_alias_types)
                    )
                base = base.where(
                    or_(
                        _folded(NamedEntityDB.canonical_name).like(folded_pattern),
                        NamedEntityDB.id.in_(alias_select.scalar_subquery()),
                    )
                )
            else:
                base = base.where(
                    _folded(NamedEntityDB.canonical_name).like(folded_pattern)
                )

        # Count over the filtered-but-unsorted/unpaginated set. Derived from the
        # same `base`, so a future filter cannot drift the count from the page.
        total = (
            await session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar() or 0

        if sort == "mentions":
            base = base.order_by(
                NamedEntityDB.mention_count.desc(),
                NamedEntityDB.canonical_name.asc(),
            )
        else:
            base = base.order_by(NamedEntityDB.canonical_name.asc())

        base = base.offset(skip).limit(limit)
        result = await session.execute(base)
        return list(result.scalars().all()), total

    async def replace_enrichment(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        *,
        properties: dict[str, Any],
        external_ids: dict[str, Any],
    ) -> int:
        """Full-replacement write of knowledge-base enrichment for one entity (Feature 067).

        Sets exactly ``properties`` and ``external_ids`` — never a JSONB merge — so a value
        removed upstream does not survive (FR-005). The SET clause contains only these two
        columns and never the human-authored display fields (FR-006); this is asserted by the
        SET-clause guard test (ST-001). UPDATE-only: if no row matches ``entity_id`` the
        entity is absent and the caller skips it (FR-005b) — nothing is inserted.

        Parameters
        ----------
        session : AsyncSession
            The active database session.
        entity_id : uuid.UUID
            Target entity's primary key.
        properties : dict[str, Any]
            The property bag, mirrored verbatim into ``named_entities.properties``.
        external_ids : dict[str, Any]
            The structured identifier map for ``named_entities.external_ids``.

        Returns
        -------
        int
            Number of rows updated: 1 if the entity existed, 0 if it was absent.
        """
        stmt = (
            update(NamedEntityDB)
            .where(NamedEntityDB.id == entity_id)
            .values(properties=properties, external_ids=external_ids)
        )
        result = await session.execute(stmt)
        return result.rowcount

    async def replace_properties(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        *,
        properties: dict[str, Any],
    ) -> int:
        """Properties-only write of knowledge-base enrichment for one entity (Feature 068).

        Sets only ``properties`` (plus the automatic ``updated_at`` bump from the column's
        ``onupdate``). The SET clause never contains ``external_ids`` (so the verified grounding
        identifier set at create survives — the anti-clobber guard, research D4) nor the
        human-authored display fields (``canonical_name``, ``canonical_name_normalized``,
        ``description``). It is deliberately narrower than ``replace_enrichment``, which sets both
        ``properties`` and ``external_ids``. UPDATE-only: 0 rows means the entity is absent.

        **Full-replace, not a merge.** This overwrites the whole ``properties`` bag. It is intended
        for the create-time on-approval path only, where the entity's bag is empty (``create_entity``
        / ``classify`` do not set ``properties``), so a fresh grounded entity's fetched bag is exactly
        what a later batch load would write (FR-002). Do NOT use it to refresh an entity that may hold
        hand-set or description-parsed fields — the pipeline's rank-aware merge owns that (FR-011; the
        Feature 069 follow-up), and a full-replace here would silently wipe those fields.

        Parameters
        ----------
        session : AsyncSession
            The active database session.
        entity_id : uuid.UUID
            Target entity's primary key.
        properties : dict[str, Any]
            The property bag, mirrored verbatim into ``named_entities.properties``.

        Returns
        -------
        int
            Number of rows updated: 1 if the entity existed, 0 if it was absent.
        """
        stmt = (
            update(NamedEntityDB)
            .where(NamedEntityDB.id == entity_id)
            .values(properties=properties)
        )
        result = await session.execute(stmt)
        return result.rowcount

    async def add_external_id(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        *,
        source: str,
        identifier: dict[str, Any],
    ) -> int:
        """Merge one external identifier into ``external_ids`` without disturbing the others.

        Uses a JSONB **merge** (``external_ids = external_ids || {source: identifier}``), NOT a full
        replacement — so adding, say, a DBpedia link on approval preserves the verified Wikidata
        identifier already stored (the anti-clobber invariant that makes ``replace_properties``
        properties-only; here the same invariant is met by merging rather than replacing). If
        ``source`` already exists it is overwritten; every other key survives. UPDATE-only: 0 rows
        means the entity is absent.

        Parameters
        ----------
        session : AsyncSession
            The active database session.
        entity_id : uuid.UUID
            Target entity's primary key.
        source : str
            The identifier source key, e.g. ``"dbpedia"``.
        identifier : dict[str, Any]
            The structured identifier value (an ``ExternalIdentifier`` dump).

        Returns
        -------
        int
            Number of rows updated: 1 if the entity existed, 0 if it was absent.
        """
        merge = bindparam("merge", value={source: identifier}, type_=JSONB())
        stmt = (
            update(NamedEntityDB)
            .where(NamedEntityDB.id == entity_id)
            .values(external_ids=NamedEntityDB.external_ids.op("||")(merge))
        )
        result = await session.execute(stmt)
        return result.rowcount
