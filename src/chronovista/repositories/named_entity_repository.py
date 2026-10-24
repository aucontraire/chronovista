"""
Named entity repository for entity extraction and management.

Handles CRUD operations for named entities discovered from tags and transcripts,
supporting entity resolution, merge tracking, and confidence scoring.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import bindparam, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.entity_image import ImageSource
from chronovista.models.entity_relations import InboundRelationMatch
from chronovista.models.named_entity import NamedEntityCreate, NamedEntityUpdate
from chronovista.repositories.base import BaseSQLAlchemyRepository
from chronovista.repositories.entity_mention_repository import _folded


class ManualImageMissingError(Exception):
    """Raised when ``manual`` is requested as the image source but no manual image exists.

    The caller is expected to have already verified the entity exists (the route does an
    existence check first, mirroring Feature 091); a guarded UPDATE that touches zero rows
    therefore means the entity has no uploaded image (``manual_image_ext IS NULL``).
    """


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

    async def set_manual_image(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        *,
        ext: str,
        uploaded_at: datetime.datetime,
    ) -> int:
        """Record an uploaded manual image and make it the displayed source (Feature 092).

        Sets ``manual_image_ext``, ``manual_image_uploaded_at`` and flips
        ``image_source_preference`` to ``'manual'`` in one UPDATE. The SET clause touches only
        the three manual-image columns — never ``properties`` / ``external_ids`` — so this write
        is independent of the enrichment store (FR-010). UPDATE-only: 0 rows means the entity is
        absent.

        Parameters
        ----------
        session : AsyncSession
            The active database session.
        entity_id : uuid.UUID
            Target entity's primary key.
        ext : str
            The resolved file extension (``jpg`` / ``png`` / ``webp``).
        uploaded_at : datetime.datetime
            Upload time (the cache-buster version and audit signal).

        Returns
        -------
        int
            Number of rows updated: 1 if the entity existed, 0 if it was absent.
        """
        stmt = (
            update(NamedEntityDB)
            .where(NamedEntityDB.id == entity_id)
            .values(
                manual_image_ext=ext,
                manual_image_uploaded_at=uploaded_at,
                image_source_preference="manual",
            )
        )
        result = await session.execute(stmt)
        return result.rowcount

    async def clear_manual_image(
        self, session: AsyncSession, entity_id: uuid.UUID
    ) -> int:
        """Clear the manual image and revert the displayed source to automated (Feature 092).

        Sets ``manual_image_ext`` and ``manual_image_uploaded_at`` to NULL and resets
        ``image_source_preference`` to ``'wikidata'`` so the portrait falls back to the automated
        image (or the placeholder). The on-disk file is removed by the service layer. UPDATE-only:
        0 rows means the entity is absent (which the idempotent DELETE route handles as a no-op).

        Parameters
        ----------
        session : AsyncSession
            The active database session.
        entity_id : uuid.UUID
            Target entity's primary key.

        Returns
        -------
        int
            Number of rows updated: 1 if the entity existed, 0 if it was absent.
        """
        stmt = (
            update(NamedEntityDB)
            .where(NamedEntityDB.id == entity_id)
            .values(
                manual_image_ext=None,
                manual_image_uploaded_at=None,
                image_source_preference="wikidata",
            )
        )
        result = await session.execute(stmt)
        return result.rowcount

    async def set_image_source(
        self, session: AsyncSession, entity_id: uuid.UUID, source: ImageSource
    ) -> int:
        """Set which image source the portrait displays, keeping the file (Feature 092).

        Writes only ``image_source_preference`` — the uploaded file and the two manual columns are
        untouched, so a later switch back needs no re-upload. Requesting ``'manual'`` is guarded:
        the UPDATE only matches a row whose ``manual_image_ext IS NOT NULL``, so if the entity has
        no uploaded image the write affects zero rows and :class:`ManualImageMissingError` is
        raised (the caller verifies existence first, per the route's existence-check-before-write).

        Parameters
        ----------
        session : AsyncSession
            The active database session.
        entity_id : uuid.UUID
            Target entity's primary key.
        source : ImageSource
            ``'manual'`` or ``'wikidata'``.

        Returns
        -------
        int
            Number of rows updated: 1 if the entity existed, 0 if it was absent.

        Raises
        ------
        ManualImageMissingError
            If ``source == 'manual'`` but the entity has no uploaded image.
        """
        if source == "manual":
            stmt = (
                update(NamedEntityDB)
                .where(
                    NamedEntityDB.id == entity_id,
                    NamedEntityDB.manual_image_ext.isnot(None),
                )
                .values(image_source_preference="manual")
            )
            result = await session.execute(stmt)
            if result.rowcount == 0:
                raise ManualImageMissingError(
                    "cannot set source to 'manual': no uploaded image for this entity"
                )
            return result.rowcount

        stmt = (
            update(NamedEntityDB)
            .where(NamedEntityDB.id == entity_id)
            .values(image_source_preference=source)
        )
        result = await session.execute(stmt)
        return result.rowcount

    async def list_wikidata_grounded(
        self, session: AsyncSession
    ) -> Sequence[NamedEntityDB]:
        """Return every entity grounded to a Wikidata item (Feature 079 backfill work-list).

        Grounded == ``external_ids -> 'wikidata' ->> 'id'`` is present. Ordered by ``id`` for a
        stable, resumable sweep. Read-only.

        The predicate is a function-wrapped JSONB extraction with no index, so it seq-scans
        ``named_entities``. This is acceptable at the current scale (low thousands of grounded
        rows); revisit with an ``EXPLAIN ANALYZE``-measured functional GIN index only if the table
        grows an order of magnitude.

        Parameters
        ----------
        session : AsyncSession
            The active database session.

        Returns
        -------
        Sequence[NamedEntityDB]
            Every Wikidata-grounded entity, ordered by ``id``.
        """
        stmt = (
            select(NamedEntityDB)
            .where(NamedEntityDB.external_ids["wikidata"]["id"].as_string().isnot(None))
            .order_by(NamedEntityDB.id)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_by_wikidata_qids(
        self, session: AsyncSession, qids: Sequence[str]
    ) -> dict[str, tuple[uuid.UUID, str]]:
        """Map each given Wikidata QID to the local entity grounded to it (Feature 079).

        Read-only — backs the entity-detail relation-linking resolver. Callers bound ``qids`` (the
        endpoint caps it at 100) so the ``IN`` list stays small; the JSONB predicate seq-scans but is
        cheap at the current table size (see :meth:`list_wikidata_grounded` on indexing).

        Parameters
        ----------
        session : AsyncSession
            The active database session.
        qids : Sequence[str]
            Wikidata QIDs to resolve.

        Returns
        -------
        dict[str, tuple[uuid.UUID, str]]
            ``{qid: (entity_id, canonical_name)}`` for QIDs matching an **active** local entity;
            unmatched QIDs (including those grounding only to a non-active entity) are absent. Empty
            when ``qids`` is empty.
        """
        qid_list = list(qids)
        if not qid_list:
            return {}
        wikidata_id = NamedEntityDB.external_ids["wikidata"]["id"].as_string()
        stmt = select(
            wikidata_id.label("qid"),
            NamedEntityDB.id,
            NamedEntityDB.canonical_name,
        ).where(
            wikidata_id.in_(qid_list),
            # Resolve only to ACTIVE entities (Feature 082): a relation target that
            # grounds to a merged/deleted/inactive entity must NOT become an in-app
            # link — it falls back to its external Wikidata link instead. Without
            # this, correctness would rest only on the data happening to hold no
            # non-active grounded entities.
            NamedEntityDB.status == "active",
        )
        result = await session.execute(stmt)
        return {row.qid: (row.id, row.canonical_name) for row in result.all()}

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

    async def merge_properties(
        self, session: AsyncSession, entity_id: uuid.UUID, patch: dict[str, Any]
    ) -> int:
        """Shallow-merge ``patch`` into ``properties`` without disturbing the other fields (087).

        Uses a JSONB **merge** (``properties = properties || :patch``), NOT a full replacement — so a
        backfill that adds ``founder`` / ``significant_person`` keeps every other stored property
        intact (the full-replace trap in :meth:`replace_properties`). ``||`` is a shallow top-level
        merge, which is exactly right: each ``patch`` key is a whole per-field block. An empty patch is
        a no-op (returns 0 without a write).

        Parameters
        ----------
        session : AsyncSession
            The active database session.
        entity_id : uuid.UUID
            The entity to update.
        patch : dict[str, Any]
            The per-field blocks to add/refresh, e.g. ``{"founder": {"values": [...], "qids": [...]}}``.

        Returns
        -------
        int
            Number of rows updated: 1 if the entity existed, 0 if absent or ``patch`` was empty.
        """
        if not patch:
            return 0
        merge = bindparam("patch", value=patch, type_=JSONB())
        stmt = (
            update(NamedEntityDB)
            .where(NamedEntityDB.id == entity_id)
            .values(properties=NamedEntityDB.properties.op("||")(merge))
        )
        result = await session.execute(stmt)
        return result.rowcount

    async def inbound_relations(
        self, session: AsyncSession, target_qid: str, fields: Sequence[str]
    ) -> list[InboundRelationMatch]:
        """Active entities whose relation ``qids`` arrays contain ``target_qid`` (Feature 087).

        The inverse of the stored forward relations: for each requested ``WANTED`` field, an entity
        matches when ``properties->'<field>'->'qids'`` (a JSONB array) **contains** ``target_qid``
        (``@>`` — unambiguous array containment; ``?`` is avoided for its placeholder clash). Returns
        one row per matching **active** entity with the list of fields that matched; the caller folds
        these into display groups (the repository holds no grouping semantics). One statement; a
        missing field is NULL and simply does not match. The result set is small (a highly-referenced
        entity has a few dozen), so there is no DB-side paging.

        Performance: a **path** containment (`(properties->'f'->'qids') @> …`) cannot use a GIN index
        on the whole ``properties`` column, so this seq-scans — fine at the current ~1,900-row scale.
        If a measurement (T020) ever shows it too slow, rewrite to whole-column containment
        (`properties @> '{"f":{"qids":[…]}}'`) which a ``jsonb_path_ops`` GIN can serve.

        Parameters
        ----------
        session : AsyncSession
            The active database session.
        target_qid : str
            The viewed entity's Wikidata QID; referencing entities point at it.
        fields : Sequence[str]
            The ``WANTED`` field names to search (e.g. ``INBOUND_FIELDS``).

        Returns
        -------
        list[InboundRelationMatch]
            One per active referencing entity, with ``matched_fields`` and its resolved
            ``instance_of`` labels (de-duplicated; ``[]`` if absent). Empty when either input is empty.
        """
        if not target_qid or not fields:
            return []
        # One JSONB containment predicate per field; labelled in SELECT, OR-ed in WHERE.
        match_exprs = {
            f: NamedEntityDB.properties[f]["qids"].contains([target_qid])
            for f in fields
        }
        stmt = (
            select(
                NamedEntityDB.id,
                NamedEntityDB.entity_type,
                NamedEntityDB.canonical_name,
                # Feature 088: the referencing entity's instance_of labels, for the type filter.
                # A path NULL (entity has no instance_of) yields None → coerced to [] below.
                NamedEntityDB.properties["instance_of"]["values"].label(
                    "instance_of_values"
                ),
                *[expr.label(f) for f, expr in match_exprs.items()],
            )
            .where(NamedEntityDB.status == "active")
            .where(or_(*match_exprs.values()))
            .order_by(func.lower(NamedEntityDB.canonical_name), NamedEntityDB.id)
        )
        result = await session.execute(stmt)
        out: list[InboundRelationMatch] = []
        for row in result.all():
            # Read by key via _mapping (not getattr) so a future field named like a Row tuple
            # method (count/index) or a base column can't masquerade as a match.
            matched = [f for f in fields if row._mapping[f]]
            if matched:
                raw_iof = row._mapping["instance_of_values"]
                # Filter to strings before de-duplicating: `properties` is an open JSONB bag, so a
                # stray non-string (or unhashable nested value) must not 500 the endpoint.
                instance_of = (
                    list(dict.fromkeys(v for v in raw_iof if isinstance(v, str)))
                    if isinstance(raw_iof, list)
                    else []
                )
                out.append(
                    InboundRelationMatch(
                        entity_id=row.id,
                        entity_type=row.entity_type,
                        canonical_name=row.canonical_name,
                        matched_fields=matched,
                        instance_of=instance_of,
                    )
                )
        return out
