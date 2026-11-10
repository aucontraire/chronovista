"""Integration test for ChannelPrincipalRepository (DESIGN-CHANNEL-PRINCIPALS).

Real-DB via the ``db_session`` fixture (create_all + drop_all per test, so the schema —
including ``channel_principals`` and its partial index — is built from the ORM each time
and no cleanup is needed). Asserts the cast reads separate *current* from *former* and
exclude non-cast tombstones, and that upsert is idempotent on ``(channel_id, entity_id)``.
Name-free placeholders only (Constitution VI).
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.channel_principal_repository import (
    ChannelPrincipalRepository,
)
from tests.factories.entity_association_orm_factory import seed_channel_with_videos
from tests.factories.named_entity_orm_factory import create_named_entity_db

pytestmark = pytest.mark.asyncio

_CH = ("UCcp" + "0" * 24)[:24]
_NOW = datetime.datetime(2026, 11, 10, tzinfo=datetime.UTC)


async def _seed_entity(session: AsyncSession, label: str) -> uuid.UUID:
    """Persist one active person entity and return its id (unique, name-free)."""
    eid = uuid.uuid4()
    name = f"{label} {eid.hex}"
    session.add(
        create_named_entity_db(
            id=eid,
            canonical_name=name,
            canonical_name_normalized=name.lower(),
            entity_type="person",
            status="active",
        )
    )
    await session.flush()
    return eid


class TestChannelPrincipalRepository:
    async def test_cast_current_vs_former_and_tombstones(
        self, db_session: AsyncSession
    ) -> None:
        repo = ChannelPrincipalRepository()
        await seed_channel_with_videos(db_session, channel_id=_CH, available=[])
        current = await _seed_entity(db_session, "Current Host")
        former = await _seed_entity(db_session, "Former Host")
        guest = await _seed_entity(db_session, "Guest")

        await repo.upsert_review(
            db_session,
            channel_id=_CH,
            entity_id=current,
            decision="cast",
            decided_at=_NOW,
            decided_reason="host",
        )
        await repo.upsert_review(
            db_session,
            channel_id=_CH,
            entity_id=former,
            decision="cast",
            decided_at=_NOW,
            decided_reason="former host",
            through=datetime.date(2022, 1, 1),
        )
        await repo.upsert_review(
            db_session,
            channel_id=_CH,
            entity_id=guest,
            decision="stuffing",
            decided_at=_NOW,
            decided_reason="tombstone",
        )
        await db_session.flush()

        # Current roster: only the current cast (not the former, not the tombstone).
        current_roster = await repo.list_cast_for_channel(
            db_session, _CH, current_only=True
        )
        assert {p.entity_id for p in current_roster} == {current}

        # All-time roster: current + former cast, but never the tombstone.
        all_time = await repo.list_cast_for_channel(db_session, _CH, current_only=False)
        assert {p.entity_id for p in all_time} == {current, former}

        # The former principal carries its through date; the tombstone exists as a
        # non-cast row (so a re-run skips it) but is absent from the cast reads.
        former_row = await repo.get(db_session, _CH, former)
        assert former_row is not None
        assert former_row.decision == "cast"
        assert former_row.through == datetime.date(2022, 1, 1)
        guest_row = await repo.get(db_session, _CH, guest)
        assert guest_row is not None
        assert guest_row.decision == "stuffing"

    async def test_upsert_is_idempotent(self, db_session: AsyncSession) -> None:
        repo = ChannelPrincipalRepository()
        await seed_channel_with_videos(db_session, channel_id=_CH, available=[])
        eid = await _seed_entity(db_session, "Host")

        await repo.upsert_review(
            db_session,
            channel_id=_CH,
            entity_id=eid,
            decision="cast",
            decided_at=_NOW,
            decided_reason="first",
        )
        await repo.upsert_review(
            db_session,
            channel_id=_CH,
            entity_id=eid,
            decision="cast",
            decided_at=_NOW,
            decided_reason="second",
        )
        await db_session.flush()

        rows = await repo.list_cast_for_channel(db_session, _CH, current_only=False)
        assert len(rows) == 1  # one row per (channel, entity), updated in place
        assert rows[0].decided_reason == "second"

    async def test_missing_pair_returns_none(self, db_session: AsyncSession) -> None:
        repo = ChannelPrincipalRepository()
        assert await repo.get(db_session, _CH, uuid.uuid4()) is None
