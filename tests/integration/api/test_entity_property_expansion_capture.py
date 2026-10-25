"""Feature 095 capture seam: the new relationship and attribute facts are stored on grounding
and surface through the detail endpoint; the write is scoped to the grounded entity.

Crosses the real seam end-to-end: ``WikidataClient.fetch_properties`` (the only mocked boundary,
Constitution VI) -> ``EntityEnrichmentService._write_properties`` ->
``NamedEntityRepository.replace_properties`` -> a REAL Postgres UPDATE -> ``GET
/api/v1/entities/{entity_id}`` -> ``_build_enrichment``. Mirrors the Feature 079 capture test.

Also proves FR-011/SC-005: grounding one entity leaves a separate pre-seeded entity's properties
byte-for-byte unchanged (the mutation is scoped to its target). Neutral placeholders only.
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

_SET_AT = "2026-01-01T00:00:00+00:00"


def _item(qid: str, label: str) -> dict[str, Any]:
    return wp.assemble_block([qid], [], {qid: label}, _SET_AT)


# Grounded bags built from the REAL assemblers, one per entity type — a representative slice of the
# new relationship edges and node attributes. Deliberately omits some fields to exercise the
# absent-fact path.
_PERSON: dict[str, Any] = {
    "award_received": _item("Q000101", "Placeholder Award"),
    "notable_work": _item("Q000102", "Placeholder Work"),
    "participant_in": _item("Q000103", "Placeholder Event"),
    "religion_or_worldview": _item("Q000104", "Placeholder Worldview"),
    "ethnic_group": _item("Q000105", "Placeholder Group"),
}
_ORG: dict[str, Any] = {
    "parent_organization": _item("Q000111", "Placeholder Parent Org"),
    "owned_by": _item("Q000112", "Placeholder Owner"),
    "chairperson": _item("Q000113", "Placeholder Chair"),
    "ceo": _item("Q000114", "Placeholder CEO"),
    "affiliation": _item("Q000115", "Placeholder Affiliation"),
    "legal_form": _item("Q000116", "Placeholder Legal Form"),
    "industry": _item("Q000117", "Placeholder Industry"),
    "head_position": _item("Q000118", "Placeholder Office"),
}
_WORK: dict[str, Any] = {
    "creator": _item("Q000121", "Placeholder Creator"),
    "production_company": _item("Q000122", "Placeholder Studio"),
    "original_broadcaster": _item("Q000123", "Placeholder Network"),
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


async def _seed(
    factory: async_sessionmaker[AsyncSession],
    entity_type: str,
    qid: str,
    properties: dict[str, Any] | None = None,
) -> uuid.UUID:
    suffix = uuid.uuid4().hex[:8]
    entity = create_named_entity_db(
        canonical_name=f"Placeholder {entity_type} {suffix}",
        canonical_name_normalized=f"placeholder {entity_type} {suffix}",
        entity_type=entity_type,
        external_ids={"wikidata": {"id": qid, "verified": True, "status": "verified"}},
        properties=properties or {},
    )
    async with factory() as s:
        s.add(entity)
        await s.flush()
        eid = uuid.UUID(str(entity.id))
        await s.commit()
    return eid


async def _ground(
    factory: async_sessionmaker[AsyncSession],
    eid: uuid.UUID,
    qid: str,
    bag: dict[str, Any],
) -> None:
    service = EntityEnrichmentService(
        factory,
        client_factory=lambda: _FakeClient(bag),
        dbpedia_factory=lambda: _NoDbpedia(),
    )
    await service.enrich_on_approval(eid, qid)


@pytest.mark.parametrize(
    ("entity_type", "qid", "bag"),
    [
        ("person", "Q000100", _PERSON),
        ("organization", "Q000110", _ORG),
        ("work", "Q000120", _WORK),
    ],
)
async def test_new_facts_are_captured_and_surface(
    async_client: AsyncClient,
    integration_session_factory: async_sessionmaker[AsyncSession],
    entity_type: str,
    qid: str,
    bag: dict[str, Any],
) -> None:
    """Each entity type stores its new facts and returns them verbatim through the detail endpoint."""
    eid = await _seed(integration_session_factory, entity_type, qid)
    await _ground(integration_session_factory, eid, qid, bag)

    resp = await async_client.get(f"/api/v1/entities/{eid}")
    assert resp.status_code == 200, resp.text
    props = resp.json()["data"]["enrichment"]["properties"]

    for key, block in bag.items():
        assert props[key] == block, key
    # Absent-fact path: a new field NOT in the bag is simply not present (no null, no error).
    assert "owned_by" not in props or entity_type == "organization"


async def test_grounding_is_scoped_to_its_target(
    async_client: AsyncClient,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """FR-011/SC-005: grounding one entity leaves a separate pre-seeded entity's properties intact."""
    bystander_props = {"occupation": _item("Q000131", "Placeholder Occupation")}
    bystander = await _seed(
        integration_session_factory, "person", "Q000130", properties=bystander_props
    )
    target = await _seed(integration_session_factory, "person", "Q000140")

    await _ground(integration_session_factory, target, "Q000140", _PERSON)

    # The bystander's stored properties are byte-for-byte unchanged by the target's grounding.
    async with integration_session_factory() as s:
        row = (
            await s.execute(select(NamedEntityDB).where(NamedEntityDB.id == bystander))
        ).scalar_one()
        assert row.properties == bystander_props
