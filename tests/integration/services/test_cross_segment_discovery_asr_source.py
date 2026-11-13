"""US2 discovery-parity: CrossSegmentDiscovery reads the dedicated ASR-error store.

After Feature 110's relocation, ``CrossSegmentDiscovery._load_multiword_asr_aliases``
must source its candidates from ``entity_asr_errors`` (not the name store), with the
same output shape and multi-word filter as before — so the ``/corrections/batch``
candidate set is unchanged (FR-006, SC-003).

These run against the isolated function-scoped integration DB (``db_session``). The
``BatchCorrectionService`` collaborator is not exercised by the method under test, so a
``MagicMock`` stands in for it; the real seam (service → repository → database) runs
against a real connection.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityAsrError, NamedEntity
from chronovista.services.cross_segment_discovery import CrossSegmentDiscovery

pytestmark = pytest.mark.asyncio


def _service() -> CrossSegmentDiscovery:
    return CrossSegmentDiscovery(batch_service=MagicMock())


async def _seed_entity(db_session: AsyncSession, name: str) -> NamedEntity:
    entity = NamedEntity(
        entity_type="person",
        canonical_name=name,
        canonical_name_normalized=name.lower(),
    )
    db_session.add(entity)
    await db_session.flush()
    return entity


@pytest.mark.db
@pytest.mark.integration
class TestDiscoveryReadsDedicatedStore:
    async def test_returns_multiword_from_dedicated_store_only(
        self, db_session: AsyncSession
    ) -> None:
        """Multi-word forms in entity_asr_errors are returned; single-word excluded."""
        entity = await _seed_entity(db_session, "Invented Person")
        # Add one row at a time: a client-side uuid7 default trips SQLAlchemy's
        # insertmanyvalues sentinel matching when batched, and the real write path
        # (the registration hook) also inserts one row per call.
        for form in ("split garble form", "singleword"):
            db_session.add(
                EntityAsrError(
                    entity_id=entity.id,
                    alias_name=form,
                    alias_name_normalized=form,
                )
            )
            await db_session.flush()

        rows = await _service()._load_multiword_asr_aliases(db_session)

        assert rows == [("split garble form", "Invented Person", "person")], (
            "Expected exactly the multi-word dedicated-store form, with the "
            "(alias_name, canonical_name, entity_type) shape."
        )

    # Note: a test seeding a legacy asr_error row in entity_aliases and proving the
    # reader ignores it is no longer possible — Feature 110's CHECK forbids that row
    # entirely (see tests/integration/test_entity_aliases_check.py). The reader reading
    # only the dedicated store is covered by the test above.

    async def test_entity_name_filter(self, db_session: AsyncSession) -> None:
        """The optional canonical-name substring filter is preserved."""
        entity = await _seed_entity(db_session, "Invented Person")
        db_session.add(
            EntityAsrError(
                entity_id=entity.id,
                alias_name="filterable garble form",
                alias_name_normalized="filterable garble form",
            )
        )
        await db_session.flush()

        hit = await _service()._load_multiword_asr_aliases(
            db_session, entity_name="invented"
        )
        miss = await _service()._load_multiword_asr_aliases(
            db_session, entity_name="nonexistent-entity"
        )

        assert [r[0] for r in hit] == ["filterable garble form"]
        assert miss == []
