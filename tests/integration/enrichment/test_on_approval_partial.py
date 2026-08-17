"""Partial-resolution persistence for on-approval enrichment (Feature 068, T017 / US2, FR-007).

A fetch that only partly resolves value labels still stores what it resolved — an unresolved value
reference is persisted as its bare QID (as the pipeline stores it pending resolution), never dropped,
never a crash, never a half-written bag. This crosses the real DB seam via the service. Neutral
placeholders (Constitution VI).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.services.entity_enrichment_service import EntityEnrichmentService

pytestmark = pytest.mark.asyncio

# A partial bag: 'occupation' has one resolved label and one still-unresolved value-QID.
_PARTIAL: dict[str, Any] = {
    "occupation": {
        "values": ["Placeholder Occupation A", "Q000011"],
        "qids": ["Q000010", "Q000011"],
        "source": "wikidata",
        "set_at": "2026-08-17T00:00:00+00:00",
    }
}


class _PartialClient:
    async def fetch_properties(self, qid: str) -> dict[str, Any]:
        return _PARTIAL


class _NoDbpedia:
    async def resolve(self, qid: str) -> tuple[str, str] | None:
        return None


class TestPartialPersistence:
    async def test_partial_bag_persisted_unresolved_qid_kept(
        self, db_session: AsyncSession
    ) -> None:
        entity = NamedEntityDB(
            canonical_name=f"Placeholder {uuid.uuid4().hex[:8]}",
            canonical_name_normalized=f"placeholder {uuid.uuid4().hex[:8]}",
            entity_type="person",
            status="active",
            properties={},
        )
        db_session.add(entity)
        await db_session.commit()
        entity_id = uuid.UUID(str(entity.id))

        factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
        service = EntityEnrichmentService(
            factory,
            client_factory=lambda: _PartialClient(),
            dbpedia_factory=lambda: _NoDbpedia(),
        )
        await service.enrich_on_approval(entity_id, "Q000001")

        async with factory() as s2:
            row = (
                await s2.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
                )
            ).scalar_one()
        # The resolved label AND the unresolved QID are both present, in order.
        assert row.properties["occupation"]["values"] == [
            "Placeholder Occupation A",
            "Q000011",
        ]
