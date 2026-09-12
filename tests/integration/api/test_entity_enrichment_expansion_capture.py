"""Feature 079 capture seam: expanded Wikidata blocks surface through the detail endpoint,
curated fields untouched (T009, FR-006, FR-024, Constitution Principle V).

Crosses the real seam end-to-end: ``WikidataClient.fetch_properties`` (the only mocked
boundary, per Constitution VI — no live external calls in tests) ->
``EntityEnrichmentService._write_properties`` -> ``NamedEntityRepository.replace_properties``
-> a REAL Postgres UPDATE -> ``GET /api/v1/entities/{entity_id}`` -> ``_build_enrichment``. A
mock standing in for the DB or the endpoint could not prove the write actually reaches the row
the detail page reads back out; this test never mocks either.

Pre-seeds the entity with a curated ``description`` and one curated ``EntityAlias`` row BEFORE
the properties write, captures their values, then proves FR-006 (the expanded blocks never touch
curated fields) against those captured values — through the same endpoint response a viewer sees,
and again directly against the row. Neutral placeholders only (Constitution VI).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.services import wikidata_properties as wp
from chronovista.services.entity_enrichment_service import EntityEnrichmentService
from tests.factories.entity_association_orm_factory import EntityAliasDBFactory
from tests.factories.named_entity_orm_factory import create_named_entity_db

pytestmark = pytest.mark.asyncio

_QID = "Q000091"
_SET_AT = "2026-01-01T00:00:00+00:00"

# The fixed expanded bag a grounded fetch returns (Feature 079): one relation block
# (spouse), one literal/image block, and the two display-only reference blocks — built
# from the REAL assemblers in wikidata_properties.py rather than a hand-rolled dict, so
# the shape this test pins is the shape production code actually emits.
_FETCHED: dict[str, Any] = {
    "image": wp.assemble_block([], ["Placeholder_Portrait.jpg"], {}, _SET_AT),
    "spouse": wp.assemble_block(
        ["Q000092"], [], {"Q000092": "Placeholder Spouse"}, _SET_AT
    ),
    "wikidata_description": wp.assemble_reference_block(
        ["a placeholder one-line description"], _SET_AT
    ),
    "wikidata_aliases": wp.assemble_reference_block(
        ["Placeholder Alias One", "Placeholder Alias Two"], _SET_AT
    ),
}


class _FakeClient:
    """Stands in for ``WikidataClient`` at the network boundary (Constitution VI)."""

    def __init__(self, properties: dict[str, Any]) -> None:
        self._properties = properties

    async def fetch_properties(self, qid: str) -> dict[str, Any]:
        return dict(self._properties)


class _NoDbpedia:
    async def resolve(self, qid: str) -> tuple[str, str] | None:
        return None


async def test_expanded_properties_surface_through_detail_curated_fields_untouched(
    async_client: AsyncClient,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Ground an already-curated entity, write the expanded bag, read it back for real."""
    curated_description = f"Curated placeholder biography {uuid.uuid4().hex[:8]}."
    curated_alias_name = f"Curated Placeholder Alias {uuid.uuid4().hex[:8]}"

    entity = create_named_entity_db(
        canonical_name=f"Placeholder Entity {uuid.uuid4().hex[:8]}",
        canonical_name_normalized=f"placeholder entity {uuid.uuid4().hex[:8]}",
        entity_type="person",
        description=curated_description,
        external_ids={"wikidata": {"id": _QID, "verified": True, "status": "verified"}},
        properties={},
    )
    async with integration_session_factory() as s:
        s.add(entity)
        await s.flush()
        entity_id = uuid.UUID(str(entity.id))
        s.add(
            EntityAliasDBFactory.build(
                entity_id=entity_id,
                alias_name=curated_alias_name,
                alias_name_normalized=curated_alias_name.lower(),
                alias_type="nickname",
            )
        )
        await s.commit()

    # The write path: only WikidataClient is mocked (the external boundary); the service,
    # the repository's UPDATE, and Postgres below are all real.
    service = EntityEnrichmentService(
        integration_session_factory,
        client_factory=lambda: _FakeClient(_FETCHED),
        dbpedia_factory=lambda: _NoDbpedia(),
    )
    await service.enrich_on_approval(entity_id, _QID)

    resp = await async_client.get(f"/api/v1/entities/{entity_id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    props = data["enrichment"]["properties"]

    # The new Feature-079 blocks made it through the real DB write onto the real
    # detail-endpoint read — the capture seam FR-024 requires.
    assert props["image"] == _FETCHED["image"]
    assert props["spouse"]["values"] == ["Placeholder Spouse"]
    assert props["spouse"]["qids"] == ["Q000092"]
    assert props["wikidata_description"]["values"] == [
        "a placeholder one-line description"
    ]
    assert (
        "qids" not in props["wikidata_description"]
    )  # reference block, not a relation
    assert props["wikidata_aliases"]["values"] == [
        "Placeholder Alias One",
        "Placeholder Alias Two",
    ]

    # FR-006: the curated description column and the curated alias row are untouched by
    # the properties-only write — asserted through the same endpoint response a viewer
    # sees, byte-for-byte against the values captured before the write.
    assert data["description"] == curated_description
    aliases_by_name = {a["alias_name"]: a for a in data["aliases"]}
    assert curated_alias_name in aliases_by_name
    assert aliases_by_name[curated_alias_name]["alias_type"] == "nickname"

    # And directly against Postgres — the endpoint response is a rendering of these
    # columns, not proof by itself that the underlying row is untouched.
    async with integration_session_factory() as s2:
        row = (
            await s2.execute(select(NamedEntityDB).where(NamedEntityDB.id == entity_id))
        ).scalar_one()
        assert row.description == curated_description
        alias_rows = (
            (
                await s2.execute(
                    select(EntityAliasDB).where(EntityAliasDB.entity_id == entity_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(alias_rows) == 1
        assert alias_rows[0].alias_name == curated_alias_name
