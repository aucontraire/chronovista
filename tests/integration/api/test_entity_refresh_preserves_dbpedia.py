"""Regression test: refreshing an existing entity's Wikidata properties must not wipe other
sources' blocks (Feature 073 "Refresh" x Feature 079 data-loss bug, now fixed).

The bug: ``EntityEnrichmentService._write_properties`` used to full-replace
(``replace_properties(properties=fresh)``). The Feature-073 "Refresh" button schedules
``enrich_on_approval`` on an EXISTING, already-enriched entity — not just a freshly-created one —
so a refresh silently wiped any non-Wikidata block already on the row (e.g. a ``source="dbpedia"``
``category`` block). The fix loads the entity's current ``properties`` and writes
``wp.merge_wikidata_blocks(existing.properties, fresh)``: Wikidata-sourced blocks are fully
replaced, every other source's block survives.

Crosses the real seam: only ``WikidataClient.fetch_properties`` is mocked (the network boundary);
``EntityEnrichmentService``, ``NamedEntityRepository``, and the Postgres UPDATE are all real, read
back both directly and through ``GET /api/v1/entities/{entity_id}``. Neutral placeholders only
(Constitution VI).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.services import wikidata_properties as wp
from chronovista.services.entity_enrichment_service import EntityEnrichmentService
from tests.factories.named_entity_orm_factory import create_named_entity_db

pytestmark = pytest.mark.asyncio

_QID = "Q000501"
_SET_AT_STALE = "2020-01-01T00:00:00+00:00"
_SET_AT_FRESH = "2026-01-01T00:00:00+00:00"

# The stale wikidata-sourced block already on the row — must be REPLACED by the fresh fetch.
_STALE_WIKIDATA_BLOCK: dict[str, Any] = wp.assemble_block(
    [], ["Stale Placeholder Occupation"], {}, _SET_AT_STALE
)
# The dbpedia-sourced block already on the row — must SURVIVE unchanged. This is the core
# assertion: the data-loss guard.
_DBPEDIA_BLOCK: dict[str, Any] = {
    "values": ["Placeholder Category"],
    "source": "dbpedia",
    "set_at": _SET_AT_STALE,
}
# The fresh wikidata bag the (mocked) refetch returns — different from the stale block, and
# deliberately carries NO "category" key of its own.
_FRESH: dict[str, Any] = {
    "occupation": wp.assemble_block(
        [], ["Fresh Placeholder Occupation"], {}, _SET_AT_FRESH
    ),
    "wikidata_description": wp.assemble_reference_block(
        ["a fresh placeholder one-line description"], _SET_AT_FRESH
    ),
}


class _FakeClient:
    """Stands in for WikidataClient at the network boundary (Constitution VI)."""

    def __init__(self, properties: dict[str, Any]) -> None:
        self._properties = properties

    async def fetch_properties(self, qid: str) -> dict[str, Any]:
        return dict(self._properties)


class _NoDbpedia:
    async def resolve(self, qid: str) -> tuple[str, str] | None:
        return None


async def test_refresh_replaces_wikidata_blocks_preserves_dbpedia_and_curated_description(
    async_client: AsyncClient,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A refresh of an existing, already-enriched entity must not wipe its dbpedia block."""
    curated_description = f"Curated placeholder biography {uuid.uuid4().hex[:8]}."

    entity = create_named_entity_db(
        canonical_name=f"Placeholder Refresh {uuid.uuid4().hex[:8]}",
        canonical_name_normalized=f"placeholder refresh {uuid.uuid4().hex[:8]}",
        entity_type="person",
        description=curated_description,
        external_ids={"wikidata": {"id": _QID, "verified": True, "status": "verified"}},
        properties={
            "occupation": dict(_STALE_WIKIDATA_BLOCK),
            "category": dict(_DBPEDIA_BLOCK),
        },
    )
    async with integration_session_factory() as s:
        s.add(entity)
        await s.commit()
        entity_id = uuid.UUID(str(entity.id))

    # The refresh path: only WikidataClient is mocked; the service, the repo's UPDATE, and
    # Postgres below are all real.
    service = EntityEnrichmentService(
        integration_session_factory,
        client_factory=lambda: _FakeClient(_FRESH),
        dbpedia_factory=lambda: _NoDbpedia(),
    )
    await service.enrich_on_approval(entity_id, _QID)

    # Fresh-session direct read.
    async with integration_session_factory() as s2:
        row = (
            await s2.execute(select(NamedEntityDB).where(NamedEntityDB.id == entity_id))
        ).scalar_one()
        # The data-loss guard — the core assertion: dbpedia block SURVIVED, byte-for-byte.
        assert row.properties["category"] == _DBPEDIA_BLOCK
        # The stale wikidata block was REPLACED by the fresh one.
        assert row.properties["occupation"] == _FRESH["occupation"]
        assert row.properties["occupation"] != _STALE_WIKIDATA_BLOCK
        # The fresh fetch's other new block also landed.
        assert row.properties["wikidata_description"] == _FRESH["wikidata_description"]
        # Curated description untouched.
        assert row.description == curated_description

    # And through the real detail endpoint.
    resp = await async_client.get(f"/api/v1/entities/{entity_id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    props = data["enrichment"]["properties"]
    assert props["category"] == _DBPEDIA_BLOCK
    assert props["occupation"] == _FRESH["occupation"]
    assert data["description"] == curated_description
