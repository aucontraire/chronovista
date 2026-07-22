"""Integration tests for classify with an explicit display_name (Feature 057, T025; US2).

Verifies POST /api/v1/entities/classify honours ``display_name``:
- the created entity's ``canonical_name`` is stored verbatim (no re-casing),
- the entity is still linked to the source tag by its normalized form (FR-011),
- the operation is logged with the web actor ``user:local`` (FR-018),
- omitting ``display_name`` preserves today's auto-derived behavior (FR-010).

Requires the integration database (chronovista_integration_test).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import TagOperationLog as TagOperationLogDB

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio


async def _seed_tag(
    factory: async_sessionmaker[AsyncSession],
    *,
    normalized_form: str,
    canonical_form: str,
) -> uuid.UUID:
    """Seed a canonical tag + one alias; return the tag id."""
    tag_id = uuid.UUID(bytes=uuid7().bytes)
    async with factory() as session:
        await _purge(session, normalized_form)
        session.add(
            CanonicalTagDB(
                id=tag_id,
                canonical_form=canonical_form,
                normalized_form=normalized_form,
                alias_count=1,
                video_count=0,
                status="active",
            )
        )
        await session.commit()
        session.add(
            TagAliasDB(
                id=uuid.UUID(bytes=uuid7().bytes),
                raw_form=canonical_form,
                normalized_form=normalized_form,
                canonical_tag_id=tag_id,
                creation_method="auto_normalize",
                occurrence_count=1,
            )
        )
        await session.commit()
    return tag_id


async def _purge(session: AsyncSession, normalized_form: str) -> None:
    """Delete any tag/entity rows for a normalized form (both entity types)."""
    tag = (
        await session.execute(
            select(CanonicalTagDB).where(
                CanonicalTagDB.normalized_form == normalized_form
            )
        )
    ).scalar_one_or_none()
    if tag is not None and tag.entity_id is not None:
        linked_entity_id = tag.entity_id
        # Clear the tag->entity FK before deleting the entity row.
        tag.entity_id = None
        tag.entity_type = None
        session.add(tag)
        await session.flush()
        await session.execute(
            delete(EntityAliasDB).where(EntityAliasDB.entity_id == linked_entity_id)
        )
        # The created entity's normalized form is the folded display_name
        # (e.g. "openai"), not the tag's normalized_form — delete it by id.
        await session.execute(
            delete(NamedEntityDB).where(NamedEntityDB.id == linked_entity_id)
        )
    await session.execute(
        delete(NamedEntityDB).where(
            NamedEntityDB.canonical_name_normalized == normalized_form
        )
    )
    await session.execute(
        delete(TagAliasDB).where(TagAliasDB.normalized_form == normalized_form)
    )
    await session.execute(
        delete(CanonicalTagDB).where(CanonicalTagDB.normalized_form == normalized_form)
    )
    await session.commit()


@pytest.fixture
async def openai_tag(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[str, None]:
    """Seed the ``openai`` tag (lowercase canonical form)."""
    normalized = "ect057 openai"
    tag_id = await _seed_tag(
        integration_session_factory,
        normalized_form=normalized,
        canonical_form="ect057 openai",
    )
    yield normalized
    async with integration_session_factory() as session:
        await _purge(session, normalized)
    _ = tag_id


class TestClassifyDisplayName:
    async def test_display_name_stored_verbatim_and_linked(
        self,
        async_client: AsyncClient,
        openai_tag: str,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """display_name is stored verbatim; entity linked by normalized form."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                "/api/v1/entities/classify",
                json={
                    "normalized_form": openai_tag,
                    "entity_type": "organization",
                    "display_name": "OpenAI",
                },
            )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["canonical_name"] == "OpenAI"  # verbatim
        assert body["entity_id"] is not None
        operation_id = uuid.UUID(body["operation_id"])

        async with integration_session_factory() as session:
            # Tag is linked to the created entity by normalized form.
            tag = (
                await session.execute(
                    select(CanonicalTagDB).where(
                        CanonicalTagDB.normalized_form == openai_tag
                    )
                )
            ).scalar_one()
            assert tag.entity_id is not None
            assert str(tag.entity_id) == body["entity_id"]

            entity = (
                await session.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == tag.entity_id)
                )
            ).scalar_one()
            assert entity.canonical_name == "OpenAI"
            assert entity.canonical_name_normalized == "openai"

            # Web actor recorded on the classify operation log.
            log = (
                await session.execute(
                    select(TagOperationLogDB).where(
                        TagOperationLogDB.id == operation_id
                    )
                )
            ).scalar_one()
            assert log.performed_by == "user:local"

    async def test_absent_display_name_auto_cases(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Without display_name, the entity name is auto-derived (title-cased)."""
        normalized = "ect057 tesla"
        await _seed_tag(
            integration_session_factory,
            normalized_form=normalized,
            canonical_form="ect057 tesla",
        )
        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.post(
                    "/api/v1/entities/classify",
                    json={
                        "normalized_form": normalized,
                        "entity_type": "organization",
                    },
                )
            assert response.status_code == 201, response.text
            body = response.json()
            assert body["canonical_name"] == "Ect057 Tesla"
        finally:
            async with integration_session_factory() as session:
                await _purge(session, normalized)
