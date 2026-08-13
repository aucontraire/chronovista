"""Integration tests for the recovery-provenance write path — ADR-011.

Deliberately integration rather than unit tests. The behaviour being protected
is *what the database ends up holding* after two sources touch the same row —
an ON CONFLICT clause, a composite primary key and a derived column working
together. A mocked session would assert that the code called the functions it
calls, which is precisely the class of test that let the original defect ship.

The defect: a Filmot pass overwrote `recovery_source` on 92 rows previously
recovered by Wayback, destroying both the attribution and the snapshot
timestamp packed inside it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.models.recovery_provenance import RecoverySourceRecord
from chronovista.repositories.recovery_provenance_repository import (
    RecoveryProvenanceRepository,
)

pytestmark = pytest.mark.asyncio


async def _seed_video(session: AsyncSession, video_id: str, channel_id: str) -> None:
    await session.execute(
        text(
            """
            INSERT INTO channels (channel_id, title, is_subscribed, availability_status)
            VALUES (:cid, 'Provenance Test Channel', false, 'unavailable')
            ON CONFLICT (channel_id) DO NOTHING
            """
        ),
        {"cid": channel_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO videos (video_id, channel_id, title, upload_date, duration,
                                made_for_kids, self_declared_made_for_kids,
                                availability_status)
            VALUES (:vid, :cid, 'Provenance Test Video', now(), 42, false, false,
                    'unavailable')
            ON CONFLICT (video_id) DO NOTHING
            """
        ),
        {"vid": video_id, "cid": channel_id},
    )
    await session.flush()


class TestAppendNeverOverwrite:
    """The invariant the whole ADR exists to enforce."""

    async def test_second_source_does_not_erase_the_first(
        self, db_session: AsyncSession
    ) -> None:
        """This is the 2026-08-09 incident, as a test.

        Wayback recovers a video; Filmot later fills a gap on the same row.
        Both facts must survive. Under the previous single-column model the
        second write destroyed the first.
        """
        repo = RecoveryProvenanceRepository()
        vid, cid = "prov_appnd1", "UCprovappend0000000001"
        await _seed_video(db_session, vid, cid)

        earlier = datetime.now(UTC) - timedelta(days=200)
        await repo.record_video(
            db_session,
            vid,
            RecoverySourceRecord(
                source="wayback",
                source_detail="20210101080938",
                recovered_at=earlier,
                fields_written=["title", "description"],
            ),
        )
        await repo.record_video(
            db_session,
            vid,
            RecoverySourceRecord(source="filmot", fields_written=["duration"]),
        )

        rows = await repo.get_video_sources(db_session, vid)
        by_source = {r.source: r for r in rows}

        assert set(by_source) == {"wayback", "filmot"}
        # The snapshot timestamp — the thing actually lost in the incident.
        assert by_source["wayback"].source_detail == "20210101080938"
        assert by_source["wayback"].fields_written == ["title", "description"]
        assert by_source["filmot"].fields_written == ["duration"]

    async def test_same_source_twice_updates_rather_than_duplicates(
        self, db_session: AsyncSession
    ) -> None:
        """A retry refreshes its own row and creates no second one."""
        repo = RecoveryProvenanceRepository()
        vid, cid = "prov_retry1", "UCprovretry000000000001"
        await _seed_video(db_session, vid, cid)

        await repo.record_video(
            db_session,
            vid,
            RecoverySourceRecord(source="filmot", fields_written=["title"]),
        )
        await repo.record_video(
            db_session,
            vid,
            RecoverySourceRecord(source="filmot", fields_written=["title", "duration"]),
        )

        rows = await repo.get_video_sources(db_session, vid)
        assert len(rows) == 1
        # Sorted, not insertion-ordered: the column is a set of fields this
        # source has written, so it must not depend on run order (#228).
        assert sorted(rows[0].fields_written) == ["duration", "title"]


class TestFieldListAccumulates:
    """#228. A repeat contribution adds to the record, it does not replace it.

    The path is ordinary rather than rare, which is why it reached production:
    a run fills a title while the owning channel is still unknown, the channel
    is synced later, and a second run fills the channel. Replacing the list
    meant the row then claimed the source had written only the channel.

    The pre-existing idempotency test could not catch this — it covers the
    *fully filled* row, where the second pass writes nothing at all.
    """

    async def test_a_later_pass_filling_a_different_field_keeps_the_earlier_one(
        self, db_session: AsyncSession
    ) -> None:
        repo = RecoveryProvenanceRepository()
        vid, cid = "prov_accum1", "UCprovaccum00000000001"
        await _seed_video(db_session, vid, cid)

        await repo.record_video(
            db_session,
            vid,
            RecoverySourceRecord(source="filmot", fields_written=["title"]),
        )
        await repo.record_video(
            db_session,
            vid,
            RecoverySourceRecord(source="filmot", fields_written=["channel_id"]),
        )

        rows = await repo.get_video_sources(db_session, vid)
        assert len(rows) == 1, "still one row per (video, source)"
        assert sorted(rows[0].fields_written) == ["channel_id", "title"], (
            "the earlier contribution was discarded — the row now understates "
            "what this source wrote"
        )

    async def test_repeating_the_same_field_does_not_duplicate_it(
        self, db_session: AsyncSession
    ) -> None:
        """Accumulating must not mean growing without bound."""
        repo = RecoveryProvenanceRepository()
        vid, cid = "prov_accum2", "UCprovaccum00000000002"
        await _seed_video(db_session, vid, cid)

        for _ in range(3):
            await repo.record_video(
                db_session,
                vid,
                RecoverySourceRecord(source="filmot", fields_written=["title"]),
            )

        rows = await repo.get_video_sources(db_session, vid)
        assert rows[0].fields_written == ["title"]

    async def test_one_source_accumulating_does_not_touch_another(
        self, db_session: AsyncSession
    ) -> None:
        """The union is per (row, source), never across sources."""
        repo = RecoveryProvenanceRepository()
        vid, cid = "prov_accum3", "UCprovaccum00000000003"
        await _seed_video(db_session, vid, cid)

        await repo.record_video(
            db_session,
            vid,
            RecoverySourceRecord(source="wayback", fields_written=["description"]),
        )
        await repo.record_video(
            db_session,
            vid,
            RecoverySourceRecord(source="filmot", fields_written=["title"]),
        )
        await repo.record_video(
            db_session,
            vid,
            RecoverySourceRecord(source="filmot", fields_written=["duration"]),
        )

        by_source = {r.source: r for r in await repo.get_video_sources(db_session, vid)}
        assert sorted(by_source["filmot"].fields_written) == ["duration", "title"]
        assert by_source["wayback"].fields_written == [
            "description"
        ], "another source's field list was absorbed into the union"

    async def test_channel_provenance_accumulates_the_same_way(
        self, db_session: AsyncSession
    ) -> None:
        """Both paths, or the column means two different things."""
        repo = RecoveryProvenanceRepository()
        cid = "UCprovaccum00000000004"
        await db_session.execute(
            text(
                """
                INSERT INTO channels (channel_id, title, is_subscribed,
                                      availability_status)
                VALUES (:cid, 'Provenance Channel', false, 'unavailable')
                ON CONFLICT (channel_id) DO NOTHING
                """
            ),
            {"cid": cid},
        )
        await db_session.flush()

        await repo.record_channel(
            db_session,
            cid,
            RecoverySourceRecord(source="wayback", fields_written=["title"]),
        )
        await repo.record_channel(
            db_session,
            cid,
            RecoverySourceRecord(source="wayback", fields_written=["description"]),
        )

        rows = await repo.get_channel_sources(db_session, cid)
        assert len(rows) == 1
        assert sorted(rows[0].fields_written) == ["description", "title"]


class TestDenormalisedProjection:
    """`videos.recovery_source` is derived, and only this repository writes it."""

    async def test_denormalised_column_tracks_the_most_recent_source(
        self, db_session: AsyncSession
    ) -> None:
        repo = RecoveryProvenanceRepository()
        vid, cid = "prov_denorm", "UCprovdenorm00000000001"
        await _seed_video(db_session, vid, cid)

        await repo.record_video(
            db_session,
            vid,
            RecoverySourceRecord(
                source="wayback",
                source_detail="20210101080938",
                recovered_at=datetime.now(UTC) - timedelta(days=200),
            ),
        )
        await repo.record_video(db_session, vid, RecoverySourceRecord(source="filmot"))

        stored = (
            await db_session.execute(
                text("SELECT recovery_source FROM videos WHERE video_id = :v"),
                {"v": vid},
            )
        ).scalar_one()
        assert stored == "filmot"

    async def test_packed_form_is_reconstructed_for_existing_readers(
        self, db_session: AsyncSession
    ) -> None:
        """The legacy `source:detail` shape survives for current consumers."""
        repo = RecoveryProvenanceRepository()
        vid, cid = "prov_packed", "UCprovpacked00000000001"
        await _seed_video(db_session, vid, cid)

        await repo.record_video(
            db_session,
            vid,
            RecoverySourceRecord(source="wayback", source_detail="20220106075526"),
        )

        stored = (
            await db_session.execute(
                text("SELECT recovery_source FROM videos WHERE video_id = :v"),
                {"v": vid},
            )
        ).scalar_one()
        assert stored == "wayback:20220106075526"


class TestChannels:
    async def test_channel_provenance_is_recorded_and_projected(
        self, db_session: AsyncSession
    ) -> None:
        repo = RecoveryProvenanceRepository()
        cid = "UCprovchannel0000000001"
        await db_session.execute(
            text(
                """
                INSERT INTO channels (channel_id, title, is_subscribed, availability_status)
                VALUES (:cid, 'Provenance Channel', false, 'unavailable')
                ON CONFLICT (channel_id) DO NOTHING
                """
            ),
            {"cid": cid},
        )
        await db_session.flush()

        await repo.record_channel(
            db_session,
            cid,
            RecoverySourceRecord(source="filmot", fields_written=["title"]),
        )

        rows = await repo.get_channel_sources(db_session, cid)
        assert [r.source for r in rows] == ["filmot"]

        stored = (
            await db_session.execute(
                text("SELECT recovery_source FROM channels WHERE channel_id = :c"),
                {"c": cid},
            )
        ).scalar_one()
        assert stored == "filmot"


# Model-level validation (the packed-source rejection, trimming, field bounds)
# needs no database and lives in tests/unit/models/test_recovery_provenance.py.
