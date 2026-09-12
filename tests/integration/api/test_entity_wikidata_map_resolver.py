"""``GET /entities/wikidata-map`` — QID -> local-entity resolver (Feature 079, US3).

Real-DB integration test (``async_client``): seeds one Wikidata-grounded entity and crosses the
real seam — ``NamedEntityRepository.get_by_wikidata_qids`` -> a real Postgres query -> the
router's pipe-parsing/regex-filtering -> the JSON envelope — rather than asserting against a
mocked repository return value. Also proves the routing-order guard (FR — registered BEFORE
``/entities/{entity_id}``, so this static path is never captured as an entity id).

Uses a distinctive QID so the assertions target only this test's own row — the integration DB is
shared and never reset between test runs. Neutral placeholders only (Constitution VI).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.factories.named_entity_orm_factory import create_named_entity_db

pytestmark = pytest.mark.asyncio

_SEEDED_QID = "Q900301"
_UNKNOWN_QID = "Q900999"  # syntactically valid, matches no local entity


async def _seed_grounded(
    factory: async_sessionmaker[AsyncSession], qid: str, canonical_name: str
) -> uuid.UUID:
    entity = create_named_entity_db(
        canonical_name=canonical_name,
        canonical_name_normalized=canonical_name.lower(),
        entity_type="person",
        external_ids={"wikidata": {"id": qid, "verified": True, "status": "verified"}},
    )
    async with factory() as s:
        s.add(entity)
        await s.commit()
        return uuid.UUID(str(entity.id))


async def test_only_matched_qid_present_unknown_and_garbage_ignored(
    async_client: AsyncClient,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A known QID resolves; an unmatched QID and a malformed token are silently dropped."""
    canonical_name = f"Placeholder WikidataMap {uuid.uuid4().hex[:8]}"
    entity_id = await _seed_grounded(
        integration_session_factory, _SEEDED_QID, canonical_name
    )

    resp = await async_client.get(
        "/api/v1/entities/wikidata-map",
        params={"qids": f"{_SEEDED_QID}|{_UNKNOWN_QID}|not-a-qid"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # Only the seeded, MATCHED qid is present — the unknown qid and the garbage token are absent,
    # never surfaced as an error or as a null/empty entry.
    assert set(data) == {_SEEDED_QID}
    assert data[_SEEDED_QID]["entity_id"] == str(entity_id)
    assert data[_SEEDED_QID]["canonical_name"] == canonical_name


async def test_fully_garbage_or_empty_qids_returns_empty_map(
    async_client: AsyncClient,
) -> None:
    """No syntactically-valid qid at all -> ``{"data": {}}``, 200, never a 422."""
    resp_garbage = await async_client.get(
        "/api/v1/entities/wikidata-map", params={"qids": "not-a-qid|also-garbage"}
    )
    assert resp_garbage.status_code == 200, resp_garbage.text
    assert resp_garbage.json() == {"data": {}}

    resp_empty = await async_client.get(
        "/api/v1/entities/wikidata-map", params={"qids": ""}
    )
    assert resp_empty.status_code == 200, resp_empty.text
    assert resp_empty.json() == {"data": {}}


async def test_wikidata_map_path_resolves_to_map_shape_not_entity_detail(
    async_client: AsyncClient,
) -> None:
    """Ordering guard: ``wikidata-map`` must be routed here, not into ``/entities/{entity_id}``.

    If this static route were registered AFTER the ``{entity_id}`` route, "wikidata-map" would be
    parsed as the path param, fail ``uuid.UUID(...)``, and 404. It must instead return 200 with
    the qid-keyed map shape (``{"data": {qid: {...}}}``), never the entity-detail shape
    (``{"data": {"entity_id": ..., "canonical_name": ..., "description": ..., ...}}``).
    """
    resp = await async_client.get(
        "/api/v1/entities/wikidata-map", params={"qids": "Q1"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert isinstance(data, dict)
    # The entity-detail shape puts these keys directly under "data"; the map shape never does —
    # each key under "data" is instead a qid whose value holds entity_id/canonical_name.
    assert "canonical_name" not in data
    assert "entity_id" not in data
    assert "description" not in data
