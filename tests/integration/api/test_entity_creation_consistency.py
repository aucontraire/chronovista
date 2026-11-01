"""Cross-path entity-creation consistency (Feature 101, US2).

These prove the shared creation core makes the entry points agree: the same inputs resolve to
one entity whichever entry point is used, and a reader consumes the structured grounding shape every
path now writes. Complements the per-path suites in ``test_entity_creation_integration.py``
(which cover each entry point in isolation).

Requires the integration database (chronovista_integration_test). Each test seeds its own rows
and cleans up in FK-reverse order. Names are neutral public figures used only as fixtures, per
the convention in the sibling creation suites.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

_NAME = "Grace Hopper"
_NORMALIZED = "grace hopper"
_QID = "Q11641"


def _authenticated() -> patch[object]:
    return patch("chronovista.api.deps.youtube_oauth")


class TestCrossPathConsistency:
    """Manual POST and classify agree via the shared core (SC-001..SC-004)."""

    @pytest.fixture(autouse=True)
    async def cleanup(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[None, None]:
        async def _wipe(session: AsyncSession) -> None:
            rows = (
                (
                    await session.execute(
                        select(NamedEntityDB).where(
                            NamedEntityDB.canonical_name_normalized == _NORMALIZED,
                            NamedEntityDB.entity_type == "person",
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
                    NamedEntityDB.canonical_name_normalized == _NORMALIZED,
                    NamedEntityDB.entity_type == "person",
                )
            )
            await session.execute(
                delete(TagAliasDB).where(TagAliasDB.normalized_form == _NORMALIZED)
            )
            await session.execute(
                delete(CanonicalTagDB).where(
                    CanonicalTagDB.normalized_form == _NORMALIZED
                )
            )
            await session.commit()

        async with integration_session_factory() as session:
            await _wipe(session)
        yield
        async with integration_session_factory() as session:
            await _wipe(session)

    async def _seed_tag(self, factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory() as session:
            session.add(
                CanonicalTagDB(
                    id=uuid.UUID(bytes=uuid7().bytes),
                    canonical_form=_NAME,
                    normalized_form=_NORMALIZED,
                    alias_count=0,
                    video_count=0,
                    status="active",
                )
            )
            await session.commit()

    async def test_manual_create_then_classify_links_same_entity(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """A manually-created entity is LINKED (not duplicated) when a tag with the same
        normalized name+type is classified — both paths resolve through one all-status lookup
        in the core (FR-005/FR-007); exactly one entity row results (SC-001)."""
        with _authenticated() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            create = await async_client.post(
                "/api/v1/entities",
                json={
                    "name": _NAME,
                    "entity_type": "person",
                    "approved_identifier": {"source": "wikidata", "id": _QID},
                },
            )
        assert create.status_code == 201, create.text
        created = create.json()
        assert created["canonical_name"] == _NAME  # verbatim casing (SC-002)
        entity_id = created["entity_id"]

        await self._seed_tag(integration_session_factory)

        with _authenticated() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            classify = await async_client.post(
                "/api/v1/entities/classify",
                json={"normalized_form": _NORMALIZED, "entity_type": "person"},
            )
        assert classify.status_code == 201, classify.text
        linked = classify.json()
        # Classify LINKED to the manually-created entity — no second row.
        assert linked["entity_created"] is False
        assert linked["entity_id"] == entity_id

        async with integration_session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(NamedEntityDB).where(
                            NamedEntityDB.canonical_name_normalized == _NORMALIZED,
                            NamedEntityDB.entity_type == "person",
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert len(rows) == 1, f"expected one entity across both paths, got {len(rows)}"

    async def test_reader_consumes_structured_grounding(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """A grounded entity's external_ids use the structured {id,verified,status} shape every
        path now writes (SC-003) — the shape the offline-script fix aligns with — and the
        entity-detail reader consumes it without error (cross-feature data contract)."""
        with _authenticated() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            create = await async_client.post(
                "/api/v1/entities",
                json={
                    "name": _NAME,
                    "entity_type": "person",
                    "approved_identifier": {"source": "wikidata", "id": _QID},
                },
            )
        assert create.status_code == 201, create.text
        entity_id = create.json()["entity_id"]

        async with integration_session_factory() as session:
            entity = await session.get(NamedEntityDB, uuid.UUID(entity_id))
            assert entity is not None
            # Structured dump, never a bare string.
            assert entity.external_ids["wikidata"]["id"] == _QID
            assert entity.external_ids["wikidata"]["verified"] is True

        with _authenticated() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            detail = await async_client.get(f"/api/v1/entities/{entity_id}")
        assert detail.status_code == 200, detail.text
        assert _QID in detail.text


_COLLIDE_NAME = "Barbara Liskov"
_COLLIDE_NORMALIZED = "barbara liskov"


class TestAllStatusCollisionNeverErrors:
    """A name+type collision with an entity in ANY status returns 409, never a 500 (SC-004).

    The core's duplicate lookup is all-status, so the global ``uq_named_entity_canonical``
    constraint can never surface as an unhandled ``IntegrityError`` on the manual path — in any
    status, not just active (FR-007). Generalizes the 0.105.3 fix structurally.
    """

    @pytest.fixture(autouse=True)
    async def cleanup(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[None, None]:
        async def _wipe(session: AsyncSession) -> None:
            rows = (
                (
                    await session.execute(
                        select(NamedEntityDB).where(
                            NamedEntityDB.canonical_name_normalized
                            == _COLLIDE_NORMALIZED,
                            NamedEntityDB.entity_type == "person",
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
                    NamedEntityDB.canonical_name_normalized == _COLLIDE_NORMALIZED,
                    NamedEntityDB.entity_type == "person",
                )
            )
            await session.commit()

        async with integration_session_factory() as session:
            await _wipe(session)
        yield
        async with integration_session_factory() as session:
            await _wipe(session)

    @pytest.mark.parametrize("status", ["active", "merged", "deprecated"])
    async def test_collision_in_each_status_returns_409(
        self,
        status: str,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        with _authenticated() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            first = await async_client.post(
                "/api/v1/entities",
                json={"name": _COLLIDE_NAME, "entity_type": "person"},
            )
        assert first.status_code == 201, first.text
        entity_id = uuid.UUID(first.json()["entity_id"])

        if status != "active":
            async with integration_session_factory() as session:
                await session.execute(
                    update(NamedEntityDB)
                    .where(NamedEntityDB.id == entity_id)
                    .values(status=status)
                )
                await session.commit()

        with _authenticated() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            second = await async_client.post(
                "/api/v1/entities",
                json={"name": _COLLIDE_NAME, "entity_type": "person"},
            )
        # Deterministic 409 — never a 500 from an unhandled IntegrityError.
        assert second.status_code == 409, (
            f"collision with a {status} entity returned {second.status_code}, "
            f"expected 409: {second.text}"
        )
