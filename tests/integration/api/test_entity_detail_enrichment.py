"""Detail-page enrichment block (Feature 067, US2 — FR-009/010/011 + clarification).

Grounded entity → properties + identifier links + verified indicator. Ungrounded → a clean
"not grounded" state, no error, no raw empty object. The backend-only meta-facts (`status`,
`link_provenance`) MUST NOT appear in the payload (US2 clarification).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import NamedEntity as NamedEntityDB

pytestmark = pytest.mark.asyncio


async def _seed(factory: async_sessionmaker[AsyncSession], **cols: object) -> uuid.UUID:
    eid = uuid.uuid4()
    name = f"DetailEnrich {eid.hex[:10]}"
    async with factory() as s:
        s.add(
            NamedEntityDB(
                id=eid,
                canonical_name=name,
                canonical_name_normalized=name.lower(),
                entity_type="person",
                status="active",
                **cols,
            )
        )
        await s.commit()
    return eid


class TestDetailEnrichment:
    async def test_grounded_entity_shows_block(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed(
            integration_session_factory,
            external_ids={
                "wikidata": {"id": "Q000009", "verified": True, "status": "verified"},
                "dbpedia": {
                    "id": "http://dbpedia.org/resource/Example",
                    "verified": False,
                    "status": "confirmed",
                    "link_provenance": "owl:sameAs from wikidata",
                },
            },
            properties={"occupation": {"values": ["placeholder"], "qids": ["Q1"]}},
        )

        r = await async_client.get(f"/api/v1/entities/{eid}")
        assert r.status_code == 200, r.text
        enr = r.json()["data"]["enrichment"]

        assert enr["grounded"] is True
        assert enr["properties"]["occupation"]["values"] == ["placeholder"]
        by_source = {i["source"]: i for i in enr["identifiers"]}
        assert by_source["wikidata"]["verified"] is True
        assert by_source["wikidata"]["url"] == "https://www.wikidata.org/wiki/Q000009"
        assert by_source["dbpedia"]["url"] == "http://dbpedia.org/resource/Example"

    async def test_backend_only_meta_facts_absent_from_payload(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed(
            integration_session_factory,
            external_ids={
                "dbpedia": {
                    "id": "http://dbpedia.org/resource/Example",
                    "verified": False,
                    "status": "confirmed",
                    "link_provenance": "owl:sameAs from wikidata",
                }
            },
        )

        r = await async_client.get(f"/api/v1/entities/{eid}")
        assert r.status_code == 200, r.text
        identifiers = r.json()["data"]["enrichment"]["identifiers"]
        for ident in identifiers:
            # US2 clarification: these stay backend-only, never rendered.
            assert "status" not in ident
            assert "link_provenance" not in ident

    async def test_absent_identifier_is_not_a_link(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed(
            integration_session_factory,
            external_ids={
                "wikidata": {"id": None, "verified": False, "status": "absent"}
            },
        )
        r = await async_client.get(f"/api/v1/entities/{eid}")
        assert r.status_code == 200, r.text
        enr = r.json()["data"]["enrichment"]
        # A searched-and-absent record is not a viewer-facing link, and with no other
        # enrichment the entity reads as not grounded.
        assert enr["identifiers"] == []
        assert enr["grounded"] is False

    async def test_ungrounded_entity_renders_not_grounded(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed(integration_session_factory)  # no external_ids, no properties
        r = await async_client.get(f"/api/v1/entities/{eid}")
        assert r.status_code == 200, r.text
        enr = r.json()["data"]["enrichment"]
        assert enr["grounded"] is False
        assert enr["properties"] == {}
        assert enr["identifiers"] == []
