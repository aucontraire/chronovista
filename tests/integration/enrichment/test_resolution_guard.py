"""ST-005 — negative-result / verified honored by a later pass (Feature 067, US4).

Seeds a real searched-absent row and a real human-verified row through the loader, reads them
back from a real database, and asserts the tracked resolution guard (which the untracked
pipeline adopts) decides skip/preserve correctly. Mutation-verify: break either predicate and
these tests fail. FR-017.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.entity_enrichment import EntityEnrichmentRecord, LedgerWikidata
from chronovista.services.entity_enrichment_loader import (
    is_verified_locked,
    load_enrichment,
    should_requery_source,
)

pytestmark = pytest.mark.asyncio


async def _insert(session: AsyncSession) -> uuid.UUID:
    e = NamedEntityDB(
        canonical_name="Example Entity",
        canonical_name_normalized=f"example {uuid.uuid4().hex[:8]}",
        entity_type="person",
        status="active",
    )
    session.add(e)
    await session.flush()
    return uuid.UUID(str(e.id))


async def _external_ids(session: AsyncSession, entity_id: uuid.UUID) -> dict[str, Any]:
    row = (
        await session.execute(
            select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
        )
    ).scalar_one()
    return dict(row.external_ids)


class TestResolutionGuardHonorsStoredState:
    async def test_absent_source_is_not_requeried(
        self, db_session: AsyncSession
    ) -> None:
        entity_id = await _insert(db_session)
        # A searched-and-absent Wikidata result, landed through the loader.
        await load_enrichment(
            db_session,
            [
                EntityEnrichmentRecord(
                    entity_id=entity_id,
                    canonical_name="Example Entity",
                    wikidata=LedgerWikidata(qid=None, status="absent", verified=False),
                )
            ],
            apply=True,
        )
        await db_session.flush()
        ext = await _external_ids(db_session, entity_id)

        assert ext["wikidata"]["status"] == "absent"
        # A later pass must NOT re-query this source.
        assert should_requery_source(ext, "wikidata") is False
        # A source never recorded is fair game to query.
        assert should_requery_source(ext, "dbpedia") is True

    async def test_verified_identifier_is_locked(
        self, db_session: AsyncSession
    ) -> None:
        entity_id = await _insert(db_session)
        await load_enrichment(
            db_session,
            [
                EntityEnrichmentRecord(
                    entity_id=entity_id,
                    canonical_name="Example Entity",
                    wikidata=LedgerWikidata(
                        qid="Q000009", status="found", verified=True
                    ),
                )
            ],
            apply=True,
        )
        await db_session.flush()
        ext = await _external_ids(db_session, entity_id)

        assert ext["wikidata"]["verified"] is True
        assert is_verified_locked(ext, "wikidata") is True
        # An unverified/confirmed identifier is not locked.
        assert (
            is_verified_locked(
                {"wikidata": {"id": "Q1", "verified": False}}, "wikidata"
            )
            is False
        )


class TestThreeStatePopulation:
    """T034 — confirmed / verified / absent are all actually producible and readable."""

    async def test_all_three_states_land_and_read_back(
        self, db_session: AsyncSession
    ) -> None:
        confirmed_id = await _insert(db_session)
        verified_id = await _insert(db_session)
        absent_id = await _insert(db_session)
        await load_enrichment(
            db_session,
            [
                EntityEnrichmentRecord(
                    entity_id=confirmed_id,
                    canonical_name="Example Entity",
                    wikidata=LedgerWikidata(qid="Q1", status="found", verified=False),
                ),
                EntityEnrichmentRecord(
                    entity_id=verified_id,
                    canonical_name="Example Entity",
                    wikidata=LedgerWikidata(qid="Q2", status="found", verified=True),
                ),
                EntityEnrichmentRecord(
                    entity_id=absent_id,
                    canonical_name="Example Entity",
                    wikidata=LedgerWikidata(qid=None, status="absent", verified=False),
                ),
            ],
            apply=True,
        )
        await db_session.flush()

        assert (await _external_ids(db_session, confirmed_id))["wikidata"][
            "status"
        ] == "confirmed"
        assert (await _external_ids(db_session, verified_id))["wikidata"][
            "status"
        ] == "verified"
        assert (await _external_ids(db_session, absent_id))["wikidata"][
            "status"
        ] == "absent"
