"""ST-002 — idempotency, refresh-by-replacement, and mirror directions (Feature 067, US1).

Every case starts from a **pre-populated** row (a clean-insert idempotency test is a no-op —
feedback_idempotency_tests_hide_partial_repeats). Covers FR-004 (re-run = zero diff), FR-005
(refresh replaces, never merges), and both directions of FR-005a.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.entity_enrichment import EntityEnrichmentRecord, LedgerWikidata
from chronovista.services.entity_enrichment_loader import load_enrichment

pytestmark = pytest.mark.asyncio


async def _insert_entity(session: AsyncSession, **kwargs: object) -> uuid.UUID:
    entity = NamedEntityDB(
        canonical_name="Example Entity",
        canonical_name_normalized=f"example {uuid.uuid4().hex[:8]}",
        entity_type="person",
        status=kwargs.get("status", "active"),
    )
    session.add(entity)
    await session.flush()
    return uuid.UUID(str(entity.id))


async def _row(session: AsyncSession, entity_id: uuid.UUID) -> NamedEntityDB:
    return (
        await session.execute(
            select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
        )
    ).scalar_one()


class TestIdempotencyAndRefresh:
    async def test_rerun_unchanged_input_is_zero_diff(
        self, db_session: AsyncSession
    ) -> None:
        entity_id = await _insert_entity(db_session)
        record = EntityEnrichmentRecord(
            entity_id=entity_id,
            canonical_name="Example Entity",
            properties={"occupation": {"values": ["a", "b"], "qids": ["Q1", "Q2"]}},
            wikidata=LedgerWikidata(qid="Q9", status="found", verified=True),
        )
        await load_enrichment(db_session, [record], apply=True)
        await db_session.flush()
        first = await _row(db_session, entity_id)
        first_props, first_ext = dict(first.properties), dict(first.external_ids)

        # second run, unchanged
        await load_enrichment(db_session, [record], apply=True)
        await db_session.flush()
        second = await _row(db_session, entity_id)
        assert second.properties == first_props
        assert second.external_ids == first_ext

    async def test_refresh_drops_removed_multivalue(
        self, db_session: AsyncSession
    ) -> None:
        """FR-005: a value removed upstream must not survive (replace, not merge)."""
        entity_id = await _insert_entity(db_session)
        rec_two = EntityEnrichmentRecord(
            entity_id=entity_id,
            canonical_name="Example Entity",
            properties={"occupation": {"values": ["a", "b"], "qids": ["Q1", "Q2"]}},
        )
        await load_enrichment(db_session, [rec_two], apply=True)
        await db_session.flush()
        assert (await _row(db_session, entity_id)).properties["occupation"][
            "values"
        ] == [
            "a",
            "b",
        ]

        # upstream drops "b"
        rec_one = EntityEnrichmentRecord(
            entity_id=entity_id,
            canonical_name="Example Entity",
            properties={"occupation": {"values": ["a"], "qids": ["Q1"]}},
        )
        await load_enrichment(db_session, [rec_one], apply=True)
        await db_session.flush()
        occ = (await _row(db_session, entity_id)).properties["occupation"]
        assert occ["values"] == ["a"], "dropped value 'b' must not survive a refresh"
        assert occ["qids"] == ["Q1"]

    async def test_present_in_export_is_cleared_when_grounding_removed(
        self, db_session: AsyncSession
    ) -> None:
        """FR-005a direction 1: grounding removed upstream → cleared in DB."""
        entity_id = await _insert_entity(db_session)
        grounded = EntityEnrichmentRecord(
            entity_id=entity_id,
            canonical_name="Example Entity",
            properties={"occupation": {"values": ["a"], "qids": ["Q1"]}},
            wikidata=LedgerWikidata(qid="Q9", status="found", verified=False),
        )
        await load_enrichment(db_session, [grounded], apply=True)
        await db_session.flush()
        assert "wikidata" in (await _row(db_session, entity_id)).external_ids

        # upstream removed the QID (now searched-absent, empty properties)
        ungrounded = EntityEnrichmentRecord(
            entity_id=entity_id,
            canonical_name="Example Entity",
            properties={},
            wikidata=LedgerWikidata(qid=None, status="absent", verified=False),
        )
        await load_enrichment(db_session, [ungrounded], apply=True)
        await db_session.flush()
        row = await _row(db_session, entity_id)
        assert row.properties == {}
        assert row.external_ids["wikidata"]["status"] == "absent"
        assert row.external_ids["wikidata"]["id"] is None
        assert "dbpedia" not in row.external_ids

    async def test_absent_from_export_is_untouched(
        self, db_session: AsyncSession
    ) -> None:
        """FR-005a direction 2: an entity not in the export keeps its existing enrichment."""
        kept_id = await _insert_entity(db_session)
        other_id = await _insert_entity(db_session)

        # seed both
        for eid in (kept_id, other_id):
            await load_enrichment(
                db_session,
                [
                    EntityEnrichmentRecord(
                        entity_id=eid,
                        canonical_name="Example Entity",
                        properties={"occupation": {"values": ["a"], "qids": ["Q1"]}},
                        wikidata=LedgerWikidata(
                            qid="Q9", status="found", verified=False
                        ),
                    )
                ],
                apply=True,
            )
        await db_session.flush()

        # a load that only mentions kept_id must not touch other_id
        await load_enrichment(
            db_session,
            [
                EntityEnrichmentRecord(
                    entity_id=kept_id,
                    canonical_name="Example Entity",
                    properties={"occupation": {"values": ["z"], "qids": ["Q99"]}},
                )
            ],
            apply=True,
        )
        await db_session.flush()

        untouched = await _row(db_session, other_id)
        assert untouched.properties["occupation"]["values"] == ["a"]
        assert untouched.external_ids["wikidata"]["id"] == "Q9"
