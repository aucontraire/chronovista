"""Factories for entity↔video associations (ORM), for Feature #260 tests.

Builds the two kinds of association the ``/videos`` entity filter must treat
alike:

- a **tag-only** association -- a ``NamedEntity`` reached to a video through
  ``CanonicalTag`` → ``TagAlias`` → ``VideoTag`` with **no** ``EntityMention``
  (the case #260 fixes: previously dropped by the mentions-only filter);
- a **mention-based** association -- a ``NamedEntity`` with an
  ``EntityMention`` whose text equals the entity's canonical name, so it
  satisfies the visible-name rule (#89) the count and filter both apply.

These build persistable ORM rows via factory_boy (mirrors
``named_entity_orm_factory``); the composite ``seed_*`` helpers persist them in
FK-safe order against a real session for the integration seam test. The videos
(and their channel) are assumed to already exist -- seed those separately.

Neutral placeholder data only (this repository is public).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import factory
from factory import LazyFunction
from factory import Sequence as FactorySequence
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTag as VideoTagDB
from chronovista.models.enums import AvailabilityStatus
from chronovista.services.tag_normalization import TagNormalizationService
from tests.factories.named_entity_orm_factory import create_named_entity_db


def _uuid7() -> uuid.UUID:
    """Generate a UUIDv7 as a standard uuid.UUID (ORM PGUUID compatible)."""
    return uuid.UUID(bytes=uuid7().bytes)


class CanonicalTagDBFactory(factory.Factory[CanonicalTagDB]):
    """Factory for CanonicalTag ORM models."""

    class Meta:
        model = CanonicalTagDB

    id: Any = LazyFunction(_uuid7)
    canonical_form: Any = FactorySequence(lambda n: f"assoc260 tag {n}")
    normalized_form: Any = FactorySequence(lambda n: f"assoc260 tag {n}")
    alias_count: Any = LazyFunction(lambda: 1)
    video_count: Any = LazyFunction(lambda: 0)
    entity_type: Any = LazyFunction(lambda: "organization")
    entity_id: Any = LazyFunction(lambda: None)
    status: Any = LazyFunction(lambda: "active")


class TagAliasDBFactory(factory.Factory[TagAliasDB]):
    """Factory for TagAlias ORM models."""

    class Meta:
        model = TagAliasDB

    id: Any = LazyFunction(_uuid7)
    raw_form: Any = FactorySequence(lambda n: f"assoc260 tag {n}")
    normalized_form: Any = FactorySequence(lambda n: f"assoc260 tag {n}")
    canonical_tag_id: Any = LazyFunction(_uuid7)
    creation_method: Any = LazyFunction(lambda: "auto_normalize")
    occurrence_count: Any = LazyFunction(lambda: 1)


class VideoTagDBFactory(factory.Factory[VideoTagDB]):
    """Factory for VideoTag ORM models."""

    class Meta:
        model = VideoTagDB

    video_id: Any = FactorySequence(lambda n: f"assoc260vid{n}"[:20])
    tag: Any = FactorySequence(lambda n: f"assoc260 tag {n}")
    tag_order: Any = LazyFunction(lambda: 0)


class EntityMentionDBFactory(factory.Factory[EntityMentionDB]):
    """Factory for EntityMention ORM models."""

    class Meta:
        model = EntityMentionDB

    id: Any = LazyFunction(_uuid7)
    entity_id: Any = LazyFunction(_uuid7)
    video_id: Any = FactorySequence(lambda n: f"assoc260vid{n}"[:20])
    mention_text: Any = FactorySequence(lambda n: f"Assoc260 Entity {n}")
    detection_method: Any = LazyFunction(lambda: "rule_match")
    mention_source: Any = LazyFunction(lambda: "transcript")


class EntityAliasDBFactory(factory.Factory[EntityAliasDB]):
    """Factory for EntityAlias ORM models."""

    class Meta:
        model = EntityAliasDB

    id: Any = LazyFunction(_uuid7)
    entity_id: Any = LazyFunction(_uuid7)
    alias_name: Any = FactorySequence(lambda n: f"assoc260 alias {n}")
    alias_name_normalized: Any = FactorySequence(lambda n: f"assoc260 alias {n}")
    alias_type: Any = LazyFunction(lambda: "name_variant")
    case_sensitive: Any = LazyFunction(lambda: False)
    occurrence_count: Any = LazyFunction(lambda: 1)


def _new_entity(entity_name: str | None) -> NamedEntityDB:
    """Build an unpersisted NamedEntity with a neutral placeholder name."""
    eid = _uuid7()
    name = entity_name or f"Assoc260 Entity {eid.hex}"
    return create_named_entity_db(
        id=eid,
        canonical_name=name,
        canonical_name_normalized=name.lower(),
        entity_type="organization",
        status="active",
    )


def _video_row(video_id: str, channel_id: str, *, available: bool) -> VideoDB:
    """Build an unpersisted Video with neutral placeholder metadata.

    ``upload_date`` is deliberately OLD (2010) so these fixtures sort to the
    bottom of the default ``/videos`` (``upload_date`` desc) page and never crowd
    page 1 of the shared, never-reset integration DB — otherwise they would push
    other tests' freshly-seeded videos past the default limit (this feature's
    ranking/panel assertions are channel/entity-scoped and never depend on date).
    """
    return VideoDB(
        video_id=video_id,
        channel_id=channel_id,
        title=f"Assoc070 {video_id}",
        upload_date=datetime(2010, 1, 1, tzinfo=UTC),
        duration=60,
        availability_status=(
            AvailabilityStatus.AVAILABLE.value
            if available
            else AvailabilityStatus.UNAVAILABLE.value
        ),
    )


async def seed_channel_with_videos(
    session: AsyncSession,
    *,
    channel_id: str,
    available: Sequence[str],
    unavailable: Sequence[str] = (),
    channel_title: str = "Assoc070 Channel",
) -> None:
    """Persist a ``Channel`` and its videos (available + unavailable), FK-safe.

    The shared primitive for the Feature 070 channel-entity-panel tests: the
    per-entity associations are layered on afterwards with the ``seed_*``
    association helpers. Idempotent per id (skips rows that already exist), so it
    is safe against the never-reset integration DB.

    Parameters
    ----------
    session : AsyncSession
        An open session; the rows are committed before returning.
    channel_id : str
        The channel to create (24-char id).
    available : Sequence[str]
        Video ids to create as ``available``.
    unavailable : Sequence[str], optional
        Video ids to create as ``unavailable`` (all-videos-basis coverage).
    channel_title : str, optional
        Neutral placeholder title for a newly-created channel.
    """
    if await session.get(ChannelDB, channel_id) is None:
        session.add(ChannelDB(channel_id=channel_id, title=channel_title))
        await session.flush()
    for vid in available:
        if await session.get(VideoDB, vid) is None:
            session.add(_video_row(vid, channel_id, available=True))
    for vid in unavailable:
        if await session.get(VideoDB, vid) is None:
            session.add(_video_row(vid, channel_id, available=False))
    await session.commit()


async def seed_tag_only_association(
    session: AsyncSession,
    *,
    video_ids: Sequence[str],
    entity: NamedEntityDB | None = None,
    entity_name: str | None = None,
    tag_form: str | None = None,
) -> NamedEntityDB:
    """Persist a tag-only entity↔video association.

    Creates (or reuses) a ``NamedEntity`` and links it to each of ``video_ids``
    through a ``CanonicalTag`` → ``TagAlias`` → ``VideoTag`` chain, with **no**
    ``EntityMention``. The videos must already exist.

    Parameters
    ----------
    session : AsyncSession
        An open session; the rows are committed before returning.
    video_ids : Sequence[str]
        Videos to tag-associate with the entity.
    entity : NamedEntityDB, optional
        An already-persisted entity to attach to. When omitted, a new one is
        created so the same entity can carry both tag-only and mention
        associations across calls.
    entity_name : str, optional
        Canonical name for a newly-created entity.
    tag_form : str, optional
        The raw/normalized tag form. Defaults to a per-entity unique form.

    Returns
    -------
    NamedEntityDB
        The (persisted) entity carrying the association.
    """
    if entity is None:
        entity = _new_entity(entity_name)
        session.add(entity)
        await session.flush()

    form = tag_form or f"assoc260 tag form {entity.id.hex}"
    canonical_tag = CanonicalTagDBFactory.build(
        canonical_form=form,
        normalized_form=form,
        entity_id=entity.id,
        video_count=len(list(video_ids)),
    )
    session.add(canonical_tag)
    await session.flush()

    session.add(
        TagAliasDBFactory.build(
            raw_form=form,
            normalized_form=form,
            canonical_tag_id=canonical_tag.id,
        )
    )
    for order, vid in enumerate(video_ids):
        session.add(VideoTagDBFactory.build(video_id=vid, tag=form, tag_order=order))
    await session.commit()
    return entity


async def seed_alias_tag_association(
    session: AsyncSession,
    *,
    video_ids: Sequence[str],
    entity: NamedEntityDB | None = None,
    entity_name: str | None = None,
    alias_form: str | None = None,
) -> NamedEntityDB:
    """Persist an **alias-tag** entity↔video association.

    This is the DISTINCT sibling of :func:`seed_tag_only_association`. Where that
    helper seeds the **canonical-tag** path (``CanonicalTag.entity_id`` links the
    entity), this one seeds the path ``_alias_tag_pairs`` resolves: an entity is
    associated with a video when one of its non-ASR ``EntityAlias`` values
    normalises (via ``TagNormalizationService``) to a ``TagAlias.normalized_form``
    whose ``raw_form`` is a ``VideoTag`` on that video — with **no**
    ``EntityMention`` and **no** ``CanonicalTag.entity_id`` link.

    The owning ``CanonicalTag`` is created with ``entity_id = NULL`` on purpose:
    it makes the video reachable **only** via the alias-tag arm, so a test that
    seeds this path alone proves that arm executes (drop the arm from
    ``_tag_inclusive_association_arms`` and the video disappears).

    Persists in FK-safe order (entity → canonical_tag → alias/tag_alias →
    video_tags). The videos must already exist.

    Parameters
    ----------
    session : AsyncSession
        An open session; the rows are committed before returning.
    video_ids : Sequence[str]
        Videos to alias-tag-associate with the entity.
    entity : NamedEntityDB, optional
        An already-persisted entity to attach to. When omitted, a new one is
        created.
    entity_name : str, optional
        Canonical name for a newly-created entity.
    alias_form : str, optional
        The entity alias text (also used, after normalisation, as the tag's
        ``normalized_form``). Defaults to a per-entity unique lowercase form so
        ``TagNormalizationService.normalize`` returns it unchanged.

    Returns
    -------
    NamedEntityDB
        The (persisted) entity carrying the association.
    """
    if entity is None:
        entity = _new_entity(entity_name)
        session.add(entity)
        await session.flush()

    alias_text = alias_form or f"assoc260 aliastag {entity.id.hex}"
    normalized = TagNormalizationService().normalize(alias_text)
    assert normalized is not None, "alias_form must normalise to a non-empty form"
    # A raw tag string distinct from the normalised form; the alias-tag join is
    # VideoTag.tag == TagAlias.raw_form (exact string), independent of the
    # normalisation match on TagAlias.normalized_form.
    raw_tag = f"AliasRaw260 {entity.id.hex}"

    # entity_id=NULL so the canonical-tag arm cannot also catch this video —
    # the association is reachable ONLY through the alias-tag arm.
    canonical_tag = CanonicalTagDBFactory.build(
        canonical_form=raw_tag,
        normalized_form=normalized,
        entity_id=None,
        video_count=len(list(video_ids)),
    )
    session.add(canonical_tag)
    await session.flush()

    session.add(
        EntityAliasDBFactory.build(
            entity_id=entity.id,
            alias_name=alias_text,
            alias_name_normalized=normalized,
            alias_type="name_variant",
        )
    )
    session.add(
        TagAliasDBFactory.build(
            raw_form=raw_tag,
            normalized_form=normalized,
            canonical_tag_id=canonical_tag.id,
        )
    )
    for order, vid in enumerate(video_ids):
        session.add(VideoTagDBFactory.build(video_id=vid, tag=raw_tag, tag_order=order))
    await session.commit()
    return entity


async def seed_mention_association(
    session: AsyncSession,
    *,
    video_ids: Sequence[str],
    entity: NamedEntityDB | None = None,
    entity_name: str | None = None,
    mention_source: str = "transcript",
) -> NamedEntityDB:
    """Persist a mention-based entity↔video association.

    Creates (or reuses) a ``NamedEntity`` and adds one ``EntityMention`` per
    video whose ``mention_text`` equals the entity's canonical name, so it
    satisfies the visible-name rule (#89) that both the count and the filter
    apply. The videos must already exist.

    Parameters
    ----------
    session : AsyncSession
        An open session; the rows are committed before returning.
    video_ids : Sequence[str]
        Videos to mention-associate with the entity.
    entity : NamedEntityDB, optional
        An already-persisted entity to attach to. When omitted, a new one is
        created.
    entity_name : str, optional
        Canonical name for a newly-created entity.
    mention_source : str
        The stored ``mention_source`` (``transcript`` counts under both ``ANY``
        and ``TRANSCRIPT`` scopes; ``title``/``description`` count only at
        ``ANY``).

    Returns
    -------
    NamedEntityDB
        The (persisted) entity carrying the association.
    """
    if entity is None:
        entity = _new_entity(entity_name)
        session.add(entity)
        await session.flush()

    for vid in video_ids:
        session.add(
            EntityMentionDBFactory.build(
                entity_id=entity.id,
                video_id=vid,
                mention_text=entity.canonical_name,
                mention_source=mention_source,
            )
        )
    await session.commit()
    return entity
