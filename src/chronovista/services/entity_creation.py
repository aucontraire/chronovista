"""Shared entity-creation core (Feature 101).

One home for "how a named entity comes into being". All five creation paths — manual
``POST /entities``, tag→entity classify, candidate approve, CLI ``entities create``, and the
offline ``entity_resolution`` loader — route through :func:`create_and_ground_entity`. Each
caller keeps only its own *policy*: the conflict reaction, the entity-type source, the
description source, and the enrichment mode. The core owns everything common — the all-status
duplicate lookup, the insert, and the canonical ``NAME_VARIANT`` self-alias (plus de-duplicated
extra aliases).

Transaction (FR-011): the core takes an existing ``AsyncSession`` and performs **no** transaction
control — it never commits and never rolls back. The caller owns the boundary, preserving the
batch loader's per-batch commits and every ``--dry-run`` rollback.

I/O (FR-004 / the Feature-094 held-session lesson): the core performs **no** network I/O.
Enrichment is triggered by the caller *after* this returns and the caller commits — never inside
the creation transaction.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.entity_alias import EntityAliasCreate
from chronovista.models.entity_enrichment import ExternalIdentifier, IdentifierStatus
from chronovista.models.enums import EntityAliasType
from chronovista.models.named_entity import NamedEntityCreate
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.services.tag_normalization import TagNormalizationService

# The conflict REACTION is the one legitimately per-caller decision (FR-005). The core calls this
# with the existing (any-status) entity when the all-status lookup finds a collision; the callback
# may raise (reject / HTTP 409), return the existing entity (supersede / link), or return ``None``
# (skip). Whatever it returns is what the core returns. The core never encodes this policy itself.
OnConflict = Callable[[NamedEntityDB], Awaitable[NamedEntityDB | None]]

_normalizer = TagNormalizationService()


def build_grounding(
    source: str,
    identifier: str | None,
    *,
    verified: bool,
    status: IdentifierStatus = "confirmed",
) -> dict[str, Any]:
    """Return ``{source: ExternalIdentifier(...).model_dump()}`` — the structured grounding shape.

    The **sole** sanctioned constructor of an ``external_ids`` grounding entry (FR-003). No call
    site may hand-build the dict, and ``NamedEntityRepository.add_external_id(identifier=…)`` must
    be handed this helper's result, never a literal. Fixes the bulk-script bare-QID bug (SC-003).
    """
    return {
        source: ExternalIdentifier(
            id=identifier, verified=verified, status=status
        ).model_dump()
    }


async def create_and_ground_entity(
    session: AsyncSession,
    obj_in: NamedEntityCreate,
    *,
    extra_aliases: Sequence[str] = (),
    on_conflict: OnConflict,
    entity_repo: NamedEntityRepository | None = None,
    alias_repo: EntityAliasRepository | None = None,
) -> NamedEntityDB | None:
    """Persist a new named entity and wire its canonical ``NAME_VARIANT`` self-alias.

    Owns (common to all five paths):

    1. the all-status duplicate **lookup** (``find_by_normalized_and_type``) — FR-005/FR-007;
    2. the insert via ``NamedEntityRepository.insert_new_entity`` — FR-001;
    3. the canonical name registered as the first ``NAME_VARIANT`` self-alias (occ=0) — FR-001;
    4. any ``extra_aliases`` de-duplicated by normalized form (canonical always wins) — FR-001.

    Does **not** own (caller policy): the conflict *reaction* (``on_conflict``), the entity-type
    and description sources (already decided in ``obj_in``), and enrichment (the caller triggers it
    after this returns and commits).

    Parameters
    ----------
    session
        An existing session. The core flushes only; it never commits or rolls back (FR-011).
    obj_in
        The prepared entity — normalized name + verbatim-cased ``canonical_name`` already set by
        the caller (FR-006: no path re-cases).
    extra_aliases
        Raw alias strings to register in addition to the canonical self-alias; de-duplicated by
        normalized form, and any that normalize to empty or collide are skipped.
    on_conflict
        Caller policy invoked with the existing entity when the all-status lookup finds a
        collision. May raise, return the existing entity, or return ``None``.

    Returns
    -------
    NamedEntityDB | None
        The newly created entity, or whatever ``on_conflict`` returned on a collision.
    """
    entity_repo = entity_repo or NamedEntityRepository()
    alias_repo = alias_repo or EntityAliasRepository()

    existing = await entity_repo.find_by_normalized_and_type(
        session, obj_in.canonical_name_normalized, obj_in.entity_type.value
    )
    if existing is not None:
        return await on_conflict(existing)

    entity = await entity_repo.insert_new_entity(session, obj_in=obj_in)
    await _register_aliases(session, alias_repo, entity, obj_in, extra_aliases)
    return entity


async def _register_aliases(
    session: AsyncSession,
    alias_repo: EntityAliasRepository,
    entity: NamedEntityDB,
    obj_in: NamedEntityCreate,
    extra_aliases: Sequence[str],
) -> None:
    """Seed the canonical self-alias (occ=0), then any extra aliases deduped by normalized form.

    The canonical normalized form is reserved first, so an extra alias that normalizes to the same
    string is dropped rather than creating a duplicate ``entity_aliases`` row (FR-001).
    """
    seen_normalized = {obj_in.canonical_name_normalized}
    await alias_repo.create(
        session,
        obj_in=EntityAliasCreate(
            entity_id=entity.id,
            alias_name=obj_in.canonical_name,
            alias_name_normalized=obj_in.canonical_name_normalized,
            alias_type=EntityAliasType.NAME_VARIANT,
            occurrence_count=0,
        ),
    )
    for raw in extra_aliases:
        normalized = _normalizer.normalize(raw)
        if not normalized or normalized in seen_normalized:
            continue
        seen_normalized.add(normalized)
        await alias_repo.create(
            session,
            obj_in=EntityAliasCreate(
                entity_id=entity.id,
                alias_name=raw.strip(),
                alias_name_normalized=normalized,
                alias_type=EntityAliasType.NAME_VARIANT,
                occurrence_count=0,
            ),
        )
