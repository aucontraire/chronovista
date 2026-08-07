"""Integration tests for linking an existing tag to an existing entity (#183).

Covers ``link_entity_id`` on POST /api/v1/entities/classify:
- the tag is attached to the named entity and no second entity is created,
- ``entity_type`` may be omitted and is inferred from the target entity,
- a link target that does not exist reports *NamedEntity* rather than the tag,
- an inactive target and a ``description`` paired with a link are both refused.

These run over real HTTP against the integration database on purpose. The
request schema is ``strict=True``, and strict mode will not build a UUID from
the string an HTTP client sends — a defect no service-level test can observe,
because a service call passes a real ``uuid.UUID`` and never crosses the
boundary where the coercion happens.

Requires the integration database (chronovista_integration_test).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio

# Neutral fixture data, prefixed so the purge cannot touch real rows.
TAG_NORM = "ect183 harbour authority"
TAG_CANON = "ect183 harbour authority"
ENTITY_NAME = "Ect183 Harbour Authority"
ENTITY_NORM = "ect183 harbour authority"


async def _purge(session: AsyncSession) -> None:
    """Remove any rows this module created, in FK-safe order."""
    tag = (
        await session.execute(
            select(CanonicalTagDB).where(CanonicalTagDB.normalized_form == TAG_NORM)
        )
    ).scalar_one_or_none()
    if tag is not None:
        tag.entity_id = None
        tag.entity_type = None
        session.add(tag)
        await session.flush()
    entity_ids = (
        (
            await session.execute(
                select(NamedEntityDB.id).where(
                    NamedEntityDB.canonical_name_normalized == ENTITY_NORM
                )
            )
        )
        .scalars()
        .all()
    )
    for entity_id in entity_ids:
        await session.execute(
            delete(EntityAliasDB).where(EntityAliasDB.entity_id == entity_id)
        )
    await session.execute(
        delete(NamedEntityDB).where(
            NamedEntityDB.canonical_name_normalized == ENTITY_NORM
        )
    )
    await session.execute(
        delete(TagAliasDB).where(TagAliasDB.normalized_form == TAG_NORM)
    )
    await session.execute(
        delete(CanonicalTagDB).where(CanonicalTagDB.normalized_form == TAG_NORM)
    )
    await session.commit()


@pytest.fixture
async def unlinked_tag(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[str, None]:
    """An active canonical tag with one alias and no entity link."""
    async with integration_session_factory() as session:
        await _purge(session)
        tag_id = uuid.UUID(bytes=uuid7().bytes)
        session.add(
            CanonicalTagDB(
                id=tag_id,
                canonical_form=TAG_CANON,
                normalized_form=TAG_NORM,
                alias_count=1,
                video_count=0,
                status="active",
            )
        )
        await session.commit()
        session.add(
            TagAliasDB(
                id=uuid.UUID(bytes=uuid7().bytes),
                raw_form=TAG_CANON,
                normalized_form=TAG_NORM,
                canonical_tag_id=tag_id,
                creation_method="auto_normalize",
                occurrence_count=1,
            )
        )
        await session.commit()
    yield TAG_NORM
    async with integration_session_factory() as session:
        await _purge(session)


async def _seed_entity(
    factory: async_sessionmaker[AsyncSession],
    *,
    status: str = "active",
) -> uuid.UUID:
    """Create the target entity and return its id."""
    entity_id = uuid.UUID(bytes=uuid7().bytes)
    async with factory() as session:
        session.add(
            NamedEntityDB(
                id=entity_id,
                canonical_name=ENTITY_NAME,
                canonical_name_normalized=ENTITY_NORM,
                entity_type="organization",
                status=status,
            )
        )
        await session.commit()
    return entity_id


class TestClassifyLinkEntity:
    async def test_links_tag_to_entity_without_creating_another(
        self,
        async_client: AsyncClient,
        unlinked_tag: str,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The whole point: attach to the existing entity, create nothing new."""
        entity_id = await _seed_entity(integration_session_factory)

        response = await async_client.post(
            "/api/v1/entities/classify",
            json={
                "normalized_form": unlinked_tag,
                "link_entity_id": str(entity_id),
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["entity_id"] == str(entity_id)

        async with integration_session_factory() as session:
            tag = (
                await session.execute(
                    select(CanonicalTagDB).where(
                        CanonicalTagDB.normalized_form == TAG_NORM
                    )
                )
            ).scalar_one()
            assert tag.entity_id == entity_id
            # entity_type is inferred from the target, not defaulted.
            assert tag.entity_type == "organization"

            # No second entity was created alongside the one we linked to.
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(NamedEntityDB)
                    .where(NamedEntityDB.canonical_name_normalized == ENTITY_NORM)
                )
            ).scalar_one()
            assert count == 1, "classify created an entity instead of linking"

    async def test_accepts_an_explicit_entity_type_alongside_the_link(
        self,
        async_client: AsyncClient,
        unlinked_tag: str,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Sending entity_type as well is allowed and stays backward compatible."""
        entity_id = await _seed_entity(integration_session_factory)

        response = await async_client.post(
            "/api/v1/entities/classify",
            json={
                "normalized_form": unlinked_tag,
                "entity_type": "organization",
                "link_entity_id": str(entity_id),
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["entity_id"] == str(entity_id)

    async def test_missing_link_target_names_the_entity_not_the_tag(
        self,
        async_client: AsyncClient,
        unlinked_tag: str,
    ) -> None:
        """A 404 must identify the resource that was actually missing.

        The service raises ValueError("Entity '...' not found.") and the
        router's error mapping keys on the substring "not found", so without
        resolving the target first this returned a 404 blaming the CanonicalTag
        — which exists and is fine.
        """
        response = await async_client.post(
            "/api/v1/entities/classify",
            json={
                "normalized_form": unlinked_tag,
                "link_entity_id": str(uuid.UUID(bytes=uuid7().bytes)),
            },
        )

        assert response.status_code == 404, response.text
        detail = response.text.lower()
        assert "namedentity" in detail.replace(" ", "")
        assert "canonicaltag" not in detail.replace(" ", "")

    async def test_inactive_link_target_is_a_conflict(
        self,
        async_client: AsyncClient,
        unlinked_tag: str,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Linking to a merged or deprecated entity would strand the tag."""
        entity_id = await _seed_entity(integration_session_factory, status="merged")

        response = await async_client.post(
            "/api/v1/entities/classify",
            json={
                "normalized_form": unlinked_tag,
                "link_entity_id": str(entity_id),
            },
        )

        assert response.status_code == 409, response.text

    async def test_entity_type_is_still_required_without_a_link(
        self,
        async_client: AsyncClient,
        unlinked_tag: str,
    ) -> None:
        """Omitting both leaves nothing to classify the tag as."""
        response = await async_client.post(
            "/api/v1/entities/classify",
            json={"normalized_form": unlinked_tag},
        )

        assert response.status_code == 422, response.text

    async def test_description_with_a_link_is_refused_not_ignored(
        self,
        async_client: AsyncClient,
        unlinked_tag: str,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The linking branch never reads description, so accepting it would
        silently discard what the caller wrote."""
        entity_id = await _seed_entity(integration_session_factory)

        response = await async_client.post(
            "/api/v1/entities/classify",
            json={
                "normalized_form": unlinked_tag,
                "link_entity_id": str(entity_id),
                "description": "would be dropped on the floor",
            },
        )

        assert response.status_code == 422, response.text

    async def test_display_name_with_a_link_cannot_inject_an_alias(
        self,
        async_client: AsyncClient,
        unlinked_tag: str,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """display_name is not inert when linking — it is written as an alias.

        The service uses it to name the self-alias it creates, and in the
        linking branch that alias lands on the *target* entity. Accepting it
        would let a request that only claims to point at an entity write an
        arbitrary name onto that entity's alias list.
        """
        entity_id = await _seed_entity(integration_session_factory)

        response = await async_client.post(
            "/api/v1/entities/classify",
            json={
                "normalized_form": unlinked_tag,
                "link_entity_id": str(entity_id),
                "display_name": "Unrelated Injected Name",
            },
        )

        assert response.status_code == 422, response.text

        async with integration_session_factory() as session:
            names = (
                (
                    await session.execute(
                        select(EntityAliasDB.alias_name).where(
                            EntityAliasDB.entity_id == entity_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert "Unrelated Injected Name" not in names

    async def test_entity_type_disagreeing_with_the_target_is_a_conflict(
        self,
        async_client: AsyncClient,
        unlinked_tag: str,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """A tag must not claim a type its own linked entity contradicts.

        The service writes the caller's entity_type onto the tag while
        pointing it at the target, so accepting a mismatch left
        ``tag.entity_type == "person"`` on a tag linked to an organization.
        """
        entity_id = await _seed_entity(integration_session_factory)

        response = await async_client.post(
            "/api/v1/entities/classify",
            json={
                "normalized_form": unlinked_tag,
                "entity_type": "person",  # target is an organization
                "link_entity_id": str(entity_id),
            },
        )

        assert response.status_code == 409, response.text

        async with integration_session_factory() as session:
            tag = (
                await session.execute(
                    select(CanonicalTagDB).where(
                        CanonicalTagDB.normalized_form == TAG_NORM
                    )
                )
            ).scalar_one()
            assert tag.entity_id is None, "a rejected link must not be written"
            assert tag.entity_type is None

    async def test_linking_records_the_tag_form_as_an_entity_alias(
        self,
        async_client: AsyncClient,
        unlinked_tag: str,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Pinning two side effects of linking, so they stay deliberate.

        The service creates a self-alias on the target named after the tag,
        which is what makes the linked form findable by mention detection, and
        title-cases the tag's canonical form on the way through. Both are
        inherited from the CLI path; neither is obvious from the endpoint.
        """
        entity_id = await _seed_entity(integration_session_factory)

        response = await async_client.post(
            "/api/v1/entities/classify",
            json={"normalized_form": unlinked_tag, "link_entity_id": str(entity_id)},
        )
        assert response.status_code == 201, response.text

        async with integration_session_factory() as session:
            names = (
                (
                    await session.execute(
                        select(EntityAliasDB.alias_name).where(
                            EntityAliasDB.entity_id == entity_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert ENTITY_NAME in names

            tag = (
                await session.execute(
                    select(CanonicalTagDB).where(
                        CanonicalTagDB.normalized_form == TAG_NORM
                    )
                )
            ).scalar_one()
            assert tag.canonical_form == ENTITY_NAME, "tag form is title-cased"
