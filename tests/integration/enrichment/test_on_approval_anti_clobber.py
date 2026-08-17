"""Anti-clobber seam for on-approval enrichment (Feature 068, T009 / D4).

Crosses the real DB seam: a grounded entity (verified ``external_ids``) is enriched via
``EntityEnrichmentService.enrich_on_approval`` — which opens its OWN session and commits — then the
row is read back. The properties-only write MUST leave the verified identifier untouched (FR-008,
research D4) while populating ``properties``. A mock asserting "replace_properties was called" would
not prove the identifier survived a real UPDATE — this does. Neutral placeholders (Constitution VI).
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


class _FakeClient:
    """Returns fixed properties; stands in for WikidataClient (no live calls)."""

    def __init__(self, properties: dict[str, Any]) -> None:
        self._properties = properties

    async def fetch_properties(self, qid: str) -> dict[str, Any]:
        return self._properties


async def _insert_grounded_entity(session: AsyncSession, qid: str) -> uuid.UUID:
    entity = NamedEntityDB(
        canonical_name=f"Placeholder {uuid.uuid4().hex[:8]}",
        canonical_name_normalized=f"placeholder {uuid.uuid4().hex[:8]}",
        entity_type="person",
        status="active",
        external_ids={"wikidata": {"id": qid, "verified": True, "status": "verified"}},
        properties={},
    )
    session.add(entity)
    await session.commit()
    return uuid.UUID(str(entity.id))


class TestAntiClobber:
    async def test_properties_written_identifier_preserved(
        self, db_session: AsyncSession
    ) -> None:
        qid = "Q000042"
        entity_id = await _insert_grounded_entity(db_session, qid)

        fetched = {
            "occupation": {
                "values": ["Placeholder Occupation"],
                "qids": ["Q000010"],
                "source": "wikidata",
                "set_at": "2026-08-17T00:00:00+00:00",
            }
        }
        # The service opens its own session on the same engine and commits.
        factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
        service = EntityEnrichmentService(
            factory, client_factory=lambda: _FakeClient(fetched)
        )
        await service.enrich_on_approval(entity_id, qid)

        # Read back in a fresh session (avoid identity-map staleness).
        async with factory() as s2:
            row = (
                await s2.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
                )
            ).scalar_one()
            # properties populated ...
            assert row.properties == fetched
            # ... and the verified identifier is UNCHANGED (anti-clobber).
            assert row.external_ids == {
                "wikidata": {"id": qid, "verified": True, "status": "verified"}
            }
