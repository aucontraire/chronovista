"""ST-001 — ledger→DB round-trip (Feature 067, US1).

Crosses the real load seam: parse a record, write it through the loader to a real database,
read the row back, and assert structural equality of ``properties`` (verbatim) and
``external_ids`` (transformed). A mock asserting "the repository was called" would not prove
the JSONB round-trips — this does.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.entity_enrichment import EntityEnrichmentRecord
from chronovista.services.entity_enrichment_loader import load_enrichment
from tests.factories.entity_enrichment_factory import EntityEnrichmentRecordFactory

pytestmark = pytest.mark.asyncio


async def _insert_entity(session: AsyncSession, **kwargs: object) -> uuid.UUID:
    entity = NamedEntityDB(
        canonical_name=kwargs.get("canonical_name", "Example Entity"),
        canonical_name_normalized=kwargs.get(
            "canonical_name_normalized", "example entity"
        ),
        entity_type=kwargs.get("entity_type", "person"),
        status=kwargs.get("status", "active"),
    )
    session.add(entity)
    await session.flush()
    # Normalize uuid_utils.UUID (the model's uuid7 default) to stdlib uuid.UUID, matching
    # the production path where entity_id arrives as a JSON string.
    return uuid.UUID(str(entity.id))


class TestLedgerToDbRoundTrip:
    async def test_properties_and_external_ids_round_trip(
        self, db_session: AsyncSession
    ) -> None:
        entity_id = await _insert_entity(db_session)
        record: EntityEnrichmentRecord = EntityEnrichmentRecordFactory.build(
            entity_id=entity_id
        )

        report = await load_enrichment(db_session, [record], apply=True)
        assert report.written == 1
        assert report.skipped_absent == []

        row = (
            await db_session.execute(
                select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
            )
        ).scalar_one()

        # properties mirrored verbatim
        assert row.properties == record.properties

        # external_ids transformed from the ledger blocks
        expected_external = {
            source: ident.model_dump()
            for source, ident in record.to_external_ids().items()
        }
        assert row.external_ids == expected_external
        assert row.external_ids["wikidata"]["id"] == "Q000009"
        assert (
            row.external_ids["dbpedia"]["link_provenance"] == "owl:sameAs from wikidata"
        )

    async def test_display_fields_untouched(self, db_session: AsyncSession) -> None:
        entity_id = await _insert_entity(
            db_session,
            canonical_name="Human Edited Name",
            canonical_name_normalized="human edited name",
        )
        # Seed a human-authored description too, so the load must leave it intact.
        row0 = (
            await db_session.execute(
                select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
            )
        ).scalar_one()
        row0.description = "Human edited description"
        await db_session.flush()

        record = EntityEnrichmentRecordFactory.build(
            entity_id=entity_id, canonical_name="Different In Ledger"
        )
        await load_enrichment(db_session, [record], apply=True)

        row = (
            await db_session.execute(
                select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
            )
        ).scalar_one()
        # FR-006: the load must NOT overwrite human-authored display fields.
        assert row.canonical_name == "Human Edited Name"
        assert row.canonical_name_normalized == "human edited name"
        assert row.description == "Human edited description"
