"""Endpoint integration for on-approval enrichment (Feature 068, T010).

Exercises the full detached-task path via ASGITransport: a grounded create/classify schedules the
background fetch (research D1, ``asyncio.create_task``); the effect is observed by polling the detail
endpoint (mirrors the scan tests' ``_poll_scan_job``). Covers FR-005 (background), FR-009 (no fetch on
link), and SC-003 (create returns before the fetch completes). The Wikidata client is injected via a
``get_enrichment_service`` dependency override — no live calls (Constitution VI). Neutral placeholders.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid_utils import uuid7

from chronovista.api.main import app
from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.services.entity_enrichment_service import (
    EntityEnrichmentService,
    get_enrichment_service,
)

pytestmark = pytest.mark.asyncio

_FETCHED: dict[str, Any] = {
    "occupation": {
        "values": ["Placeholder Occupation"],
        "qids": ["Q000010"],
        "source": "wikidata",
        "set_at": "2026-08-17T00:00:00+00:00",
    }
}


class _FakeClient:
    async def fetch_properties(self, qid: str) -> dict[str, Any]:
        return dict(_FETCHED)


class _BlockingClient:
    """Blocks on an event before returning — models a slow fetch (SC-003)."""

    def __init__(self, gate: asyncio.Event) -> None:
        self._gate = gate

    async def fetch_properties(self, qid: str) -> dict[str, Any]:
        await self._gate.wait()
        return dict(_FETCHED)


def _install_service(factory: async_sessionmaker[AsyncSession], client: Any) -> None:
    service = EntityEnrichmentService(factory, client_factory=lambda: client)
    app.dependency_overrides[get_enrichment_service] = lambda: service


async def _properties(client: AsyncClient, entity_id: str) -> dict[str, Any]:
    r = await client.get(f"/api/v1/entities/{entity_id}")
    assert r.status_code == 200, r.text
    props: dict[str, Any] = r.json()["data"]["enrichment"]["properties"]
    return props


async def _drain_until_enriched(client: AsyncClient, entity_id: str) -> dict[str, Any]:
    for _ in range(80):
        await asyncio.sleep(0.05)
        props = await _properties(client, entity_id)
        if props:
            return props
    pytest.fail("properties never appeared after the background fetch window")


async def _assert_stays_empty(client: AsyncClient, entity_id: str) -> None:
    for _ in range(6):
        await asyncio.sleep(0.05)
        assert await _properties(client, entity_id) == {}, "no fetch should have run"


async def _seed_tag(factory: async_sessionmaker[AsyncSession]) -> str:
    norm = f"enrich classify {uuid.uuid4().hex[:10]}"
    async with factory() as s:
        s.add(
            CanonicalTagDB(
                id=uuid.UUID(bytes=uuid7().bytes),
                canonical_form=norm.title(),
                normalized_form=norm,
                alias_count=1,
                video_count=0,
                status="active",
            )
        )
        await s.commit()
    return norm


async def _seed_entity(factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with factory() as s:
        e = NamedEntityDB(
            canonical_name=f"Placeholder {uuid.uuid4().hex[:8]}",
            canonical_name_normalized=f"placeholder {uuid.uuid4().hex[:8]}",
            entity_type="person",
            status="active",
        )
        s.add(e)
        await s.commit()
        return uuid.UUID(str(e.id))


class TestOnApprovalEnrichmentEndpoints:
    async def test_grounded_create_enriches(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        _install_service(integration_session_factory, _FakeClient())
        r = await async_client.post(
            "/api/v1/entities",
            json={
                "name": f"Grounded {uuid.uuid4().hex[:10]}",
                "entity_type": "person",
                "approved_identifier": {"source": "wikidata", "id": "Q000009"},
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["grounded"] is True
        entity_id = r.json()["entity_id"]

        props = await _drain_until_enriched(async_client, entity_id)
        assert props == _FETCHED
        # Identifier still present after the properties-only write.
        detail = await async_client.get(f"/api/v1/entities/{entity_id}")
        ids = detail.json()["data"]["enrichment"]["identifiers"]
        assert any(i["source"] == "wikidata" and i["id"] == "Q000009" for i in ids)

    async def test_ungrounded_create_no_fetch(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        _install_service(integration_session_factory, _FakeClient())
        r = await async_client.post(
            "/api/v1/entities",
            json={
                "name": f"Ungrounded {uuid.uuid4().hex[:10]}",
                "entity_type": "person",
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["grounded"] is False
        await _assert_stays_empty(async_client, r.json()["entity_id"])

    async def test_grounded_classify_enriches(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        _install_service(integration_session_factory, _FakeClient())
        norm = await _seed_tag(integration_session_factory)
        r = await async_client.post(
            "/api/v1/entities/classify",
            json={
                "normalized_form": norm,
                "entity_type": "person",
                "approved_identifier": {"source": "wikidata", "id": "Q000009"},
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["entity_created"] is True and r.json()["grounded"] is True
        props = await _drain_until_enriched(async_client, r.json()["entity_id"])
        assert props == _FETCHED

    async def test_classify_link_existing_no_fetch(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # Linking a tag to an EXISTING entity is not a creation → no fetch, even if an identifier is
        # supplied (FR-009). The existing entity's properties stay empty.
        _install_service(integration_session_factory, _FakeClient())
        existing_id = await _seed_entity(integration_session_factory)
        norm = await _seed_tag(integration_session_factory)
        r = await async_client.post(
            "/api/v1/entities/classify",
            json={
                "normalized_form": norm,
                "entity_type": "person",
                "link_entity_id": str(existing_id),
                "approved_identifier": {"source": "wikidata", "id": "Q000009"},
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["entity_created"] is False
        await _assert_stays_empty(async_client, str(existing_id))

    async def test_create_returns_before_fetch_completes(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # SC-003: the create action is not delayed by the fetch. With a client that blocks on a gate,
        # the 201 returns and the entity is still un-enriched (task pending); releasing the gate then
        # lets the properties land. Observable precisely because the task is detached (create_task).
        gate = asyncio.Event()
        _install_service(integration_session_factory, _BlockingClient(gate))
        r = await async_client.post(
            "/api/v1/entities",
            json={
                "name": f"Blocking {uuid.uuid4().hex[:10]}",
                "entity_type": "person",
                "approved_identifier": {"source": "wikidata", "id": "Q000009"},
            },
        )
        assert r.status_code == 201, r.text
        entity_id = r.json()["entity_id"]
        # Fetch is still blocked → properties not yet present.
        assert await _properties(async_client, entity_id) == {}
        gate.set()
        props = await _drain_until_enriched(async_client, entity_id)
        assert props == _FETCHED
