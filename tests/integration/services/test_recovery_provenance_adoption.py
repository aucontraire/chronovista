"""A real recovery run must leave a provenance row behind (#219).

ADR-011 shipped the tables, the migration, the repository and its tests, and
then nothing called it: `record_video` and `record_channel` had zero callers in
`src/` while four sites went on assigning the packed column directly. The join
table was a snapshot frozen at migration time.

Every test that existed at the time passed. That is the point of this file.
The repository was covered in isolation, so a helper that is never invoked and
a helper that is invoked look identical from outside — and the unit tests for
the orchestrator hand it a mocked session, where a stub recording a call and a
database recording a row are equally indistinguishable.

So these go through the database. The assertion is not "the orchestrator called
the repository"; it is **"the row is there afterwards"**.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.services.recovery import orchestrator
from chronovista.services.recovery.models import RecoveredVideoData

pytestmark = pytest.mark.asyncio

_VIDEO_ID = "provAdopt01"
_CHANNEL_ID = "UCprovadopt0000000001"


async def _seed_unavailable_video(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            INSERT INTO channels (channel_id, title, is_subscribed, availability_status)
            VALUES (:cid, 'Adoption Test Channel', false, 'unavailable')
            ON CONFLICT (channel_id) DO NOTHING
            """
        ),
        {"cid": _CHANNEL_ID},
    )
    await session.execute(
        text(
            """
            INSERT INTO videos (video_id, channel_id, title, upload_date, duration,
                                made_for_kids, self_declared_made_for_kids,
                                availability_status)
            VALUES (:vid, :cid, 'Adoption Test Video', now(), 42, false, false,
                    'unavailable')
            ON CONFLICT (video_id) DO NOTHING
            """
        ),
        {"vid": _VIDEO_ID, "cid": _CHANNEL_ID},
    )
    await session.flush()


def _stub_wayback(snapshot: str) -> tuple[Any, Any, Any]:
    """CDX client, page parser and rate limiter that yield one usable capture.

    Only the network edge is faked. Everything from the overwrite policy
    inwards — including the provenance write this file exists to check — runs
    for real against the database.
    """
    snap = MagicMock()
    snap.timestamp = snapshot

    cdx = MagicMock()
    cdx.fetch_snapshots = AsyncMock(return_value=[snap])

    parser = MagicMock()
    parser.extract_metadata = AsyncMock(
        return_value=RecoveredVideoData(
            snapshot_timestamp=snapshot,
            title="Recovered Title",
            description="Recovered Description",
        )
    )

    limiter = MagicMock()
    limiter.acquire = AsyncMock(return_value=None)
    return cdx, parser, limiter


async def _sources_for(session: AsyncSession, video_id: str) -> list[tuple[str, str]]:
    rows = await session.execute(
        text(
            "SELECT source, source_detail FROM video_recovery_sources "
            "WHERE video_id = :v ORDER BY source"
        ),
        {"v": video_id},
    )
    return [(r[0], r[1]) for r in rows]


class TestRecoveryLeavesProvenance:
    async def test_a_successful_run_writes_a_row(
        self, db_session: AsyncSession
    ) -> None:
        """The assertion that was missing when ADR-011 shipped."""
        await _seed_unavailable_video(db_session)
        cdx, parser, limiter = _stub_wayback("20220106075526")

        result = await orchestrator.recover_video(
            session=db_session,
            video_id=_VIDEO_ID,
            cdx_client=cdx,
            page_parser=parser,
            rate_limiter=limiter,
        )

        assert result.success, f"recovery failed: {result.failure_reason}"
        assert await _sources_for(db_session, _VIDEO_ID) == [
            ("wayback", "20220106075526")
        ], "a successful recovery must leave a provenance row naming its source"

    async def test_the_snapshot_timestamp_is_stored_as_data(
        self, db_session: AsyncSession
    ) -> None:
        """Not packed into the source string.

        Packing is what destroyed the timestamps in the original incident:
        overwriting the source took the capture time with it.
        """
        await _seed_unavailable_video(db_session)
        cdx, parser, limiter = _stub_wayback("20210101080938")

        await orchestrator.recover_video(
            session=db_session,
            video_id=_VIDEO_ID,
            cdx_client=cdx,
            page_parser=parser,
            rate_limiter=limiter,
        )

        source, detail = (await _sources_for(db_session, _VIDEO_ID))[0]
        assert source == "wayback", "the source must not carry the timestamp"
        assert detail == "20210101080938"

    async def test_a_dry_run_records_nothing(self, db_session: AsyncSession) -> None:
        """A dry run must not claim a contribution it did not make."""
        await _seed_unavailable_video(db_session)
        cdx, parser, limiter = _stub_wayback("20220106075526")

        await orchestrator.recover_video(
            session=db_session,
            video_id=_VIDEO_ID,
            cdx_client=cdx,
            page_parser=parser,
            rate_limiter=limiter,
            dry_run=True,
        )

        assert await _sources_for(db_session, _VIDEO_ID) == []


class TestRecencyReadsTheRecord:
    """Tier 2 of the merge policy, against the table rather than the projection."""

    async def test_an_older_capture_does_not_overwrite_a_newer_one(
        self, db_session: AsyncSession
    ) -> None:
        """The bug this replaces, end to end.

        Previously the prior timestamp was parsed out of `videos.recovery_source`.
        Once any other source became the most recent contributor that parse
        returned nothing, the comparison answered "newer", and an older capture
        overwrote a newer one while reporting success.
        """
        await _seed_unavailable_video(db_session)

        cdx, parser, limiter = _stub_wayback("20230101000000")
        first = await orchestrator.recover_video(
            session=db_session,
            video_id=_VIDEO_ID,
            cdx_client=cdx,
            page_parser=parser,
            rate_limiter=limiter,
        )
        # Without this, a run that silently failed would leave the title
        # unchanged and the final assertion would pass for the wrong reason.
        assert first.success, f"setup recovery failed: {first.failure_reason}"
        newer_title = (
            await db_session.execute(
                text("SELECT title FROM videos WHERE video_id = :v"), {"v": _VIDEO_ID}
            )
        ).scalar_one()

        # Simulate another source becoming the most recent contributor, which
        # is what used to defeat the parse.
        await db_session.execute(
            text("UPDATE videos SET recovery_source = 'filmot' WHERE video_id = :v"),
            {"v": _VIDEO_ID},
        )
        await db_session.flush()

        cdx2, parser2, limiter2 = _stub_wayback("20200101000000")
        parser2.extract_metadata = AsyncMock(
            return_value=RecoveredVideoData(
                snapshot_timestamp="20200101000000",
                title="Stale Title From An Older Capture",
            )
        )
        second = await orchestrator.recover_video(
            session=db_session,
            video_id=_VIDEO_ID,
            cdx_client=cdx2,
            page_parser=parser2,
            rate_limiter=limiter2,
        )
        assert second.success, f"second recovery failed: {second.failure_reason}"

        title_now = (
            await db_session.execute(
                text("SELECT title FROM videos WHERE video_id = :v"), {"v": _VIDEO_ID}
            )
        ).scalar_one()
        assert title_now == newer_title, (
            "an older capture overwrote a newer one — the recency check is "
            "reading the projection again"
        )

    async def test_the_same_source_running_twice_keeps_one_row(
        self, db_session: AsyncSession
    ) -> None:
        """Idempotent per (video, source): a re-run refreshes, never duplicates."""
        await _seed_unavailable_video(db_session)

        for snapshot in ("20220106075526", "20240202000000"):
            cdx, parser, limiter = _stub_wayback(snapshot)
            await orchestrator.recover_video(
                session=db_session,
                video_id=_VIDEO_ID,
                cdx_client=cdx,
                page_parser=parser,
                rate_limiter=limiter,
            )

        rows = await _sources_for(db_session, _VIDEO_ID)
        assert len(rows) == 1
        assert rows[0] == (
            "wayback",
            "20240202000000",
        ), "the later capture should have refreshed this source's own row"
