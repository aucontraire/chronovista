"""Integration tests for the ``product`` entity type end to end (Feature 103, US1).

Covers US1 acceptance against the real integration database:
  - Standalone creation (``POST /api/v1/entities``) with ``entity_type='product'`` persists and is
    returned by the entity list filtered to ``?type=product`` (scenarios 1-2; SC-004).
  - A canonical tag classified as ``product`` (``POST /api/v1/entities/classify``) promotes to a
    product entity, exercising ``chk_canonical_tag_entity_type_valid`` and ``chk_entity_type_valid``
    end to end (spec Edge Case "canonical tag typed as a product").

Candidate ``type_hint='product'`` acceptance (US1 scenario 3) is proven without a brittle
15-column ``candidate_suggestions`` insert (no factory exists for it): the scan-request validator
accepts it (``tests/unit/architecture/test_entity_type_single_source_fitness.py``
::``test_scan_validator_is_derived_from_single_source``) and ``chk_candidate_type_hint_valid``
includes ``'product'`` (migration ``b4d8f2a6c0e1`` + the single-source fitness guard's pinned
``type_hint`` SQL, SC-006).

No library content: a fictional placeholder product name is used throughout.
Stable ID / name prefix: ``pt_`` (Product Type) to avoid collisions with other integration files.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid_utils import uuid7

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB

pytestmark = pytest.mark.asyncio

# Fictional placeholder product (no library content).
_PRODUCT_NAME = "pt placeholder product app"
_PRODUCT_NORMALIZED = "pt placeholder product app"


def _create_entity_url() -> str:
    return "/api/v1/entities"


def _classify_url() -> str:
    return "/api/v1/entities/classify"


async def _wipe_product_entity(session: AsyncSession) -> None:
    rows = (
        (
            await session.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.canonical_name_normalized == _PRODUCT_NORMALIZED,
                    NamedEntityDB.entity_type == "product",
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        await session.execute(
            delete(EntityAliasDB).where(EntityAliasDB.entity_id == row.id)
        )
    await session.execute(
        delete(NamedEntityDB).where(
            NamedEntityDB.canonical_name_normalized == _PRODUCT_NORMALIZED,
            NamedEntityDB.entity_type == "product",
        )
    )
    await session.commit()


class TestStandaloneProductEntity:
    """POST /api/v1/entities with entity_type='product' — create, persist, list-filter."""

    @pytest.fixture(autouse=True)
    async def cleanup(
        self, integration_session_factory: async_sessionmaker[AsyncSession]
    ) -> AsyncGenerator[None, None]:
        async with integration_session_factory() as session:
            await _wipe_product_entity(session)
        yield
        async with integration_session_factory() as session:
            await _wipe_product_entity(session)

    async def test_create_and_filter_product_entity(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # Create a standalone product entity (US1 scenario 1).
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            created = await async_client.post(
                _create_entity_url(),
                json={"name": _PRODUCT_NAME, "entity_type": "product", "aliases": []},
            )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["entity_type"] == "product", body
        entity_id = body["entity_id"]

        # Persisted with entity_type='product' (DB truth).
        async with integration_session_factory() as session:
            db_entity = await session.get(NamedEntityDB, uuid.UUID(entity_id))
            assert db_entity is not None
            assert db_entity.entity_type == "product"
            assert db_entity.status == "active"

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Returned by the list filtered to product (US1 scenario 2).
            in_product = await async_client.get(
                _create_entity_url(),
                params={"search": _PRODUCT_NAME, "type": "product"},
            )
            # Excluded when filtered to a different type.
            in_org = await async_client.get(
                _create_entity_url(),
                params={"search": _PRODUCT_NAME, "type": "organization"},
            )
        assert in_product.status_code == 200, in_product.text
        product_ids = {e["entity_id"] for e in in_product.json()["data"]}
        assert (
            entity_id in product_ids
        ), "product entity missing from ?type=product list"

        assert in_org.status_code == 200, in_org.text
        org_ids = {e["entity_id"] for e in in_org.json()["data"]}
        assert (
            entity_id not in org_ids
        ), "product entity leaked into ?type=organization list"


class TestClassifyTagAsProduct:
    """POST /api/v1/entities/classify with entity_type='product' — the "canonical tag typed as a
    product" edge case: the tag-inclusive CHECK accepts it and it promotes to a product entity.
    """

    _TAG_NORMALIZED = "pt classify product"
    _TAG_CANONICAL = "Pt Classify Product"

    @pytest.fixture
    async def seed_product_tag(
        self, integration_session_factory: async_sessionmaker[AsyncSession]
    ) -> AsyncGenerator[dict[str, Any], None]:
        tag_id = uuid.UUID(bytes=uuid7().bytes)

        async def _wipe(session: AsyncSession) -> None:
            tag_row = (
                await session.execute(
                    select(CanonicalTagDB).where(
                        CanonicalTagDB.normalized_form == self._TAG_NORMALIZED
                    )
                )
            ).scalar_one_or_none()
            if tag_row is not None and tag_row.entity_id is not None:
                await session.execute(
                    delete(EntityAliasDB).where(
                        EntityAliasDB.entity_id == tag_row.entity_id
                    )
                )
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id == tag_row.entity_id)
                )
            await session.execute(
                delete(TagAliasDB).where(
                    TagAliasDB.normalized_form == self._TAG_NORMALIZED
                )
            )
            await session.execute(
                delete(CanonicalTagDB).where(
                    CanonicalTagDB.normalized_form == self._TAG_NORMALIZED
                )
            )
            await session.commit()

        async with integration_session_factory() as session:
            await _wipe(session)
            tag = CanonicalTagDB(
                id=tag_id,
                canonical_form=self._TAG_CANONICAL,
                normalized_form=self._TAG_NORMALIZED,
                alias_count=1,
                video_count=0,
                status="active",
            )
            session.add(tag)
            await session.commit()
            session.add(
                TagAliasDB(
                    id=uuid.UUID(bytes=uuid7().bytes),
                    raw_form=self._TAG_CANONICAL,
                    normalized_form=self._TAG_NORMALIZED,
                    canonical_tag_id=tag_id,
                    creation_method="auto_normalize",
                    occurrence_count=1,
                )
            )
            await session.commit()

        yield {"tag_id": tag_id, "normalized_form": self._TAG_NORMALIZED}

        async with integration_session_factory() as session:
            await _wipe(session)

    async def test_classify_tag_as_product_promotes_to_product_entity(
        self,
        async_client: AsyncClient,
        seed_product_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.post(
                _classify_url(),
                json={
                    "normalized_form": seed_product_tag["normalized_form"],
                    "entity_type": "product",
                },
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["entity_type"] == "product", body
        assert body["entity_created"] is True

        async with integration_session_factory() as session:
            entity = await session.get(NamedEntityDB, uuid.UUID(body["entity_id"]))
            assert entity is not None and entity.entity_type == "product"
            tag = await session.get(CanonicalTagDB, seed_product_tag["tag_id"])
            assert tag is not None and tag.entity_type == "product"
            assert tag.entity_id == entity.id
