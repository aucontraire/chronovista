"""ST-006 + FR-005b — coverage completeness and UPDATE-only load (Feature 067, US1).

ST-006: coverage is measured against the active-entity count (status='active' AND
merged_into_id IS NULL), not per-row fidelity — a stale partial export fails coverage even
when every write succeeds (the 482-vs-545 hazard). FR-005b: a record whose entity_id is not
in the database is skipped and reported, never inserted.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.entity_enrichment import EntityEnrichmentRecord
from chronovista.services.entity_enrichment_loader import load_enrichment

pytestmark = pytest.mark.asyncio


async def _insert(
    session: AsyncSession, status: str = "active", merged: bool = False
) -> uuid.UUID:
    e = NamedEntityDB(
        canonical_name="Example Entity",
        canonical_name_normalized=f"example {uuid.uuid4().hex[:8]}",
        entity_type="person",
        status=status,
    )
    session.add(e)
    await session.flush()
    if merged:
        target = await _insert(session)
        e.merged_into_id = target
        e.status = "merged"
        await session.flush()
    return uuid.UUID(str(e.id))


def _rec(entity_id: uuid.UUID) -> EntityEnrichmentRecord:
    return EntityEnrichmentRecord(
        entity_id=entity_id,
        canonical_name="Example Entity",
        properties={"occupation": {"values": ["a"], "qids": ["Q1"]}},
    )


class TestCoverage:
    async def test_incomplete_when_export_misses_active_entities(
        self, db_session: AsyncSession
    ) -> None:
        covered = await _insert(db_session, status="active")
        missing = await _insert(db_session, status="active")
        await db_session.flush()

        report = await load_enrichment(db_session, [_rec(covered)], apply=True)

        # active count reflects only active, non-merged rows
        active_in_db = (
            await db_session.execute(
                select(func.count())
                .select_from(NamedEntityDB)
                .where(
                    NamedEntityDB.status == "active",
                    NamedEntityDB.merged_into_id.is_(None),
                )
            )
        ).scalar_one()
        assert report.active_entity_count == active_in_db
        assert report.coverage_complete is False
        assert str(missing) in report.missing_active
        assert str(covered) not in report.missing_active

    async def test_merged_and_deprecated_excluded_from_active(
        self, db_session: AsyncSession
    ) -> None:
        active = await _insert(db_session, status="active")
        await _insert(db_session, status="deprecated")
        await _insert(db_session, merged=True)  # merged row + its (active) target
        await db_session.flush()

        # export covers the active one AND the merge target; the deprecated + merged rows
        # are not active, so covering just `active` should still leave the merge-target missing
        report = await load_enrichment(db_session, [_rec(active)], apply=True)
        # deprecated and merged-source rows must NOT count toward active
        for mid in report.missing_active:
            row = (
                await db_session.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == uuid.UUID(mid))
                )
            ).scalar_one()
            assert row.status == "active" and row.merged_into_id is None


class TestUpdateOnly:
    async def test_record_for_absent_entity_is_skipped_not_inserted(
        self, db_session: AsyncSession
    ) -> None:
        """FR-005b: a record whose entity_id is not in the DB is skipped, never inserted."""
        ghost = uuid.uuid4()
        before = (
            await db_session.execute(select(func.count()).select_from(NamedEntityDB))
        ).scalar_one()

        report = await load_enrichment(db_session, [_rec(ghost)], apply=True)
        await db_session.flush()

        after = (
            await db_session.execute(select(func.count()).select_from(NamedEntityDB))
        ).scalar_one()
        assert after == before, "the load must not INSERT for an absent entity_id"
        assert report.written == 0
        assert str(ghost) in report.skipped_absent
