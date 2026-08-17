"""ST-003 — external_ids shape transition from a real bare-string row (Feature 067, US2).

The identifier field's value shape changes from a bare string (legacy) to a structured object
(Feature 067) as a coordinated change with no compatibility shim. This test starts from a row
in the REAL pre-change shape and asserts the detail endpoint still works and renders the
identifier — a fixture pre-shaped in the new object form would not exercise the seam.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import NamedEntity as NamedEntityDB

pytestmark = pytest.mark.asyncio


class TestExternalIdsShapeTransition:
    async def test_legacy_bare_string_external_ids_still_renders(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = uuid.uuid4()
        name = f"ShapeTransition {eid.hex[:10]}"
        async with integration_session_factory() as s:
            s.add(
                NamedEntityDB(
                    id=eid,
                    canonical_name=name,
                    canonical_name_normalized=name.lower(),
                    entity_type="person",
                    status="active",
                    # LEGACY shape: a bare string value, as written before Feature 067.
                    external_ids={"wikidata": "Q000009"},
                    properties={
                        "occupation": {"values": ["placeholder"], "qids": ["Q1"]}
                    },
                )
            )
            await s.commit()

        r = await async_client.get(f"/api/v1/entities/{eid}")
        assert r.status_code == 200, r.text
        enrichment = r.json()["data"]["enrichment"]

        assert enrichment["grounded"] is True
        wd = next(i for i in enrichment["identifiers"] if i["source"] == "wikidata")
        assert wd["id"] == "Q000009"
        assert wd["url"] == "https://www.wikidata.org/wiki/Q000009"
        assert wd["verified"] is False  # a legacy bare string carries no verified flag
        assert enrichment["properties"]["occupation"]["values"] == ["placeholder"]

    async def test_new_structured_external_ids_renders(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = uuid.uuid4()
        name = f"ShapeTransition {eid.hex[:10]}"
        async with integration_session_factory() as s:
            s.add(
                NamedEntityDB(
                    id=eid,
                    canonical_name=name,
                    canonical_name_normalized=name.lower(),
                    entity_type="person",
                    status="active",
                    external_ids={
                        "wikidata": {
                            "id": "Q000009",
                            "verified": True,
                            "status": "verified",
                        }
                    },
                )
            )
            await s.commit()

        r = await async_client.get(f"/api/v1/entities/{eid}")
        assert r.status_code == 200, r.text
        wd = next(
            i
            for i in r.json()["data"]["enrichment"]["identifiers"]
            if i["source"] == "wikidata"
        )
        assert wd["id"] == "Q000009"
        assert wd["verified"] is True
