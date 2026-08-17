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


class _NoDbpedia:
    async def resolve(self, qid: str) -> tuple[str, str] | None:
        return None


class _LinkDbpedia:
    async def resolve(self, qid: str) -> tuple[str, str] | None:
        return "http://dbpedia.org/resource/Placeholder", "owl:sameAs from wikidata"


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
            factory,
            client_factory=lambda: _FakeClient(fetched),
            dbpedia_factory=lambda: _NoDbpedia(),
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
            # ... and the verified identifier is UNCHANGED (anti-clobber; no DBpedia resolved).
            assert row.external_ids == {
                "wikidata": {"id": qid, "verified": True, "status": "verified"}
            }

    async def test_dbpedia_merged_without_clobbering_identifier(
        self, db_session: AsyncSession
    ) -> None:
        # When DBpedia resolves, its link is MERGED into external_ids — the verified Wikidata
        # identifier must survive the merge (the JSONB `||` write, not a replace).
        qid = "Q000043"
        entity_id = await _insert_grounded_entity(db_session, qid)
        factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
        service = EntityEnrichmentService(
            factory,
            client_factory=lambda: _FakeClient(
                {"country": {"values": ["X"], "qids": [], "source": "wikidata"}}
            ),
            dbpedia_factory=lambda: _LinkDbpedia(),
        )
        await service.enrich_on_approval(entity_id, qid)

        async with factory() as s2:
            row = (
                await s2.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
                )
            ).scalar_one()
            # Wikidata identifier preserved through the merge ...
            assert row.external_ids["wikidata"] == {
                "id": qid,
                "verified": True,
                "status": "verified",
            }
            # ... and DBpedia added as a confirmed (not human-verified) identifier.
            assert (
                row.external_ids["dbpedia"]["id"]
                == "http://dbpedia.org/resource/Placeholder"
            )
            assert row.external_ids["dbpedia"]["verified"] is False
            assert row.external_ids["dbpedia"]["status"] == "confirmed"
