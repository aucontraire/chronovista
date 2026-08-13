"""Filmot recovery, against a real database (Feature 065, User Story 2).

These assert **the row is there afterwards**, not that a repository method was
called. That distinction is the whole reason this file exists: ADR-011 shipped
with provenance tables nothing wrote to, and every test passed, because a stub
recording a call and a database recording a row are indistinguishable under a
mocked session.

Only the archive is faked. Selection, the merge policy, the conditional write,
the commit and the provenance write all run for real.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

import chronovista.services.recovery.filmot_recovery as filmot_recovery
from chronovista.db.models import Video as VideoDB
from chronovista.repositories.video_repository import VideoRepository
from chronovista.services.recovery.filmot_client import FilmotVideo
from chronovista.services.recovery.filmot_recovery import run_filmot_recovery
from chronovista.services.recovery.merge_policy import (
    is_placeholder_title,
    placeholder_title_condition,
)

pytestmark = pytest.mark.asyncio

_CHANNEL = "UCfilmot00000000000001"
_PLACEHOLDER = "https://www.youtube.com/watch?v={vid}"


async def _seed(
    session: AsyncSession,
    video_id: str,
    *,
    title: str | None = None,
    channel_id: str | None = None,
    duration: int = 0,
    with_channel: bool = True,
) -> None:
    """One unavailable video, plus the owning channel unless told otherwise."""
    if with_channel:
        await session.execute(
            text(
                "INSERT INTO channels (channel_id, title, is_subscribed, "
                "availability_status) VALUES (:c, 'Filmot Test Channel', false, "
                "'available') ON CONFLICT (channel_id) DO NOTHING"
            ),
            {"c": _CHANNEL},
        )
    await session.execute(
        text(
            """
            INSERT INTO videos (video_id, channel_id, title, upload_date, duration,
                                made_for_kids, self_declared_made_for_kids,
                                availability_status)
            VALUES (:v, :c, :t, now(), :d, false, false, 'unavailable')
            ON CONFLICT (video_id) DO NOTHING
            """
        ),
        {
            "v": video_id,
            "c": channel_id,
            "t": title if title is not None else _PLACEHOLDER.format(vid=video_id),
            "d": duration,
        },
    )
    await session.commit()


def _client(records: list[FilmotVideo], unresolved: set[str] | None = None) -> Any:
    client = MagicMock()
    client.is_configured = True
    client.fetch_videos = AsyncMock(return_value=(records, unresolved or set()))
    return client


async def _row(session: AsyncSession, video_id: str) -> Any:
    return (
        await session.execute(
            text(
                "SELECT title, channel_id, duration, recovery_source "
                "FROM videos WHERE video_id = :v"
            ),
            {"v": video_id},
        )
    ).one()


async def _provenance(session: AsyncSession, video_id: str) -> list[Any]:
    return list(
        (
            await session.execute(
                text(
                    "SELECT source, source_detail, fields_written "
                    "FROM video_recovery_sources WHERE video_id = :v ORDER BY source"
                ),
                {"v": video_id},
            )
        ).all()
    )


class TestProvenanceIsRecorded:
    async def test_a_write_leaves_a_contribution_row(
        self, db_session: AsyncSession
    ) -> None:
        """The assertion that was missing when ADR-011 shipped."""
        await _seed(db_session, "filmotprov1")
        client = _client(
            [FilmotVideo(id="filmotprov1", title="Real Title", duration=214)]
        )

        result = await run_filmot_recovery(db_session, client)

        assert result.updated == 1
        rows = await _provenance(db_session, "filmotprov1")
        assert len(rows) == 1
        source, detail, fields = rows[0]
        assert source == "filmot"
        assert detail is None, "the archive supplies no capture time (FR-014)"
        assert sorted(fields) == ["duration", "title"]

    async def test_recorded_fields_match_what_actually_changed(
        self, db_session: AsyncSession
    ) -> None:
        """SC-005, in both directions: no more and no less."""
        await _seed(db_session, "filmotprov2", duration=300)
        client = _client(
            [FilmotVideo(id="filmotprov2", title="Real Title", duration=999)]
        )

        await run_filmot_recovery(db_session, client)

        title, _, duration, _ = await _row(db_session, "filmotprov2")
        fields = (await _provenance(db_session, "filmotprov2"))[0][2]

        assert title == "Real Title"
        assert duration == 300, "a positive duration is never overwritten"
        assert sorted(fields) == ["title"], (
            "the recorded fields must be exactly those that differ — duration "
            "was refused, so claiming it would overstate the contribution"
        )

    async def test_attribution_is_updated_through_the_shared_mechanism(
        self, db_session: AsyncSession
    ) -> None:
        """FR-012a — user-visible, and never written directly."""
        await _seed(db_session, "filmotprov3")
        client = _client([FilmotVideo(id="filmotprov3", title="Real Title")])

        await run_filmot_recovery(db_session, client)

        _, _, _, attribution = await _row(db_session, "filmotprov3")
        assert attribution == "filmot"

    async def test_a_video_with_nothing_written_gains_no_row(
        self, db_session: AsyncSession
    ) -> None:
        """FR-013 — a source that contributed nothing must not claim a
        contribution, or the provenance table stops meaning what it says.

        The video must be a genuine *candidate* for this to mean anything: a
        fully-populated video has no gap and is never selected, so it could
        never reach the policy at all. Here the gap is real (placeholder title)
        and the archive's answer is unusable — it offers a title that is itself
        placeholder-shaped, which FR-004b refuses.
        """
        await _seed(db_session, "filmotprov4", channel_id=_CHANNEL, duration=300)
        client = _client(
            [
                FilmotVideo(
                    id="filmotprov4",
                    title="https://www.youtube.com/watch?v=filmotprov4",
                )
            ]
        )

        result = await run_filmot_recovery(db_session, client)

        assert result.updated == 0
        assert result.held_no_write == 1
        assert "title:incoming_is_placeholder" in result.refused_values
        assert await _provenance(db_session, "filmotprov4") == []


class TestTheFillOnlyInvariant:
    """FR-015. One failing condition: a real value was overwritten."""

    async def test_a_real_title_survives_a_run_that_fills_another_gap(
        self, db_session: AsyncSession
    ) -> None:
        """Also SC-002: no video that had a real title has a different one.

        Seeded with a real title *and* a genuine duration gap, which is the
        only shape in which this invariant can actually fail. The earlier
        version of this test seeded a fully-populated video — no gap, so never
        selected, so it never reached the archive, the policy or the write. It
        asserted that a row the code never looked at was unchanged, which the
        neighbouring test's own docstring warns about.
        """
        await _seed(
            db_session,
            "filmotinv1",
            title="A Real Title",
            channel_id=_CHANNEL,
            duration=0,
        )
        client = _client(
            [
                FilmotVideo(
                    id="filmotinv1",
                    title="Archive Title",
                    channelid="UCother0000000000000x",
                    duration=214,
                )
            ]
        )

        result = await run_filmot_recovery(db_session, client)

        title, channel_id, duration, _ = await _row(db_session, "filmotinv1")
        assert title == "A Real Title", "a real title was contested"
        assert channel_id == _CHANNEL, "a recorded channel was contested"
        assert duration == 214, "the one genuine gap was not filled"
        assert result.updated == 1

    async def test_a_whitespace_title_is_filled_like_any_other_placeholder(
        self, db_session: AsyncSession
    ) -> None:
        """The three-spellings bug, end to end.

        The query trimmed, the policy stripped, and the write gate compared
        against the empty string. A whitespace-only title was therefore
        selected, approved and refused — left untouched for the next run to
        select again, forever, while the log blamed a concurrent writer that
        did not exist. Because all permitted fields move in one statement
        (FR-011a), the row's valid channel and duration fills went with it.
        """
        await _seed(db_session, "filmotblank1", title="   ", duration=0)
        client = _client(
            [
                FilmotVideo(
                    id="filmotblank1",
                    title="Real Title",
                    channelid=_CHANNEL,
                    duration=214,
                )
            ]
        )

        result = await run_filmot_recovery(db_session, client)

        title, channel_id, duration, _ = await _row(db_session, "filmotblank1")
        assert title == "Real Title"
        assert channel_id == _CHANNEL, "the other fills were discarded with the title"
        assert duration == 214
        assert result.updated == 1


class TestSelectionExcludesFilledVideos:
    """The behavioural half of FR-003, which the unit suite cannot show.

    Compiling the statement proves which columns the predicate names. Only a
    real database proves that a video with no remaining gap is genuinely absent
    from the result.
    """

    async def test_a_video_with_no_gap_is_never_a_candidate(
        self, db_session: AsyncSession
    ) -> None:
        await _seed(
            db_session,
            "filmotsel1",
            title="A Real Title",
            channel_id=_CHANNEL,
            duration=300,
        )

        candidates = await VideoRepository().get_filmot_candidates(
            db_session, placeholder_title_condition(VideoDB.title)
        )

        assert "filmotsel1" not in {v.video_id for v in candidates}

    @pytest.mark.parametrize(
        ("gap", "seed"),
        [
            ("title", {"duration": 300, "channel_id": _CHANNEL}),
            ("channel", {"title": "A Real Title", "duration": 300}),
            ("duration", {"title": "A Real Title", "channel_id": _CHANNEL}),
        ],
    )
    async def test_each_remaining_gap_makes_a_video_a_candidate(
        self, db_session: AsyncSession, gap: str, seed: dict[str, Any]
    ) -> None:
        """One disjunct per gap — a missing one silently shrinks the backlog."""
        video_id = f"filmotsel{gap}"
        await _seed(db_session, video_id, **seed)

        candidates = await VideoRepository().get_filmot_candidates(
            db_session, placeholder_title_condition(VideoDB.title)
        )

        assert video_id in {v.video_id for v in candidates}


class TestBlankTitleAgreement:
    """The Python matcher and the SQL predicate, judged by PostgreSQL.

    Restating `btrim` in Python would only assert that Python equals Python.
    Each title here is stored and then selected through the real predicate, so
    a disagreement between the two halves fails the test rather than hiding as
    a row that is selected and then never written.
    """

    @pytest.mark.parametrize(
        ("label", "title"),
        [
            ("empty", ""),
            ("single-space", " "),
            ("spaces", "   "),
            ("tab", "\t"),
            ("newline", "\n"),
            ("mixed", " \t\n "),
            ("real", "A Real Title"),
            ("url-form", "https://www.youtube.com/watch?v=abcdefghijk"),
            ("bracket-form", "[Placeholder] Video abcdefghijk"),
            ("leading-space-real", "  A Real Title"),
        ],
    )
    async def test_both_halves_reach_the_same_verdict(
        self, db_session: AsyncSession, label: str, title: str
    ) -> None:
        video_id = f"filmotagree{abs(hash(label)) % 10**6}"
        await _seed(
            db_session, video_id, title=title, channel_id=_CHANNEL, duration=300
        )

        selected = await db_session.scalar(
            select(VideoDB.video_id).where(
                VideoDB.video_id == video_id,
                placeholder_title_condition(VideoDB.title),
            )
        )

        assert (selected is not None) == is_placeholder_title(title), (
            f"{label!r}: PostgreSQL and the Python matcher disagree, which is "
            "how a row gets selected and then refused at write"
        )

    async def test_a_gate_falsified_after_selection_refuses_the_write(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FR-011b, the mechanism the whole feature rests on.

        Fills the title *between* candidate selection and the write, exactly as
        a concurrent writer would. Without the gate re-asserted in the UPDATE
        itself, this overwrites a real value and fill-only becomes true only by
        timing — which is not true at all.
        """
        await _seed(db_session, "filmotrace1")
        original = filmot_recovery._conditional_update

        async def racing(session: AsyncSession, video: Any, updates: dict[str, Any]):
            await session.execute(
                text("UPDATE videos SET title = :t WHERE video_id = :v"),
                {"t": "Written By Someone Else", "v": "filmotrace1"},
            )
            return await original(session, video, updates)

        monkeypatch.setattr(filmot_recovery, "_conditional_update", racing)
        client = _client(
            [FilmotVideo(id="filmotrace1", title="Filmot Title", duration=214)]
        )

        result = await run_filmot_recovery(db_session, client)

        title, _, _, _ = await _row(db_session, "filmotrace1")
        assert title == "Written By Someone Else", (
            "the conditional write did not re-assert its gate — a concurrent "
            "writer's value was overwritten"
        )
        assert result.updated == 0
        assert await _provenance(db_session, "filmotrace1") == []


class TestASecondContributionToTheSameVideo:
    """The ordinary life-cycle that corrupted attribution.

    A run fills the title while the owning channel is still unknown; the
    channel is synced later; a later run fills `channel_id`. Nothing about that
    is rare, and it is the case the idempotency test does not reach — that one
    covers the *fully filled* video, where the second run writes nothing.
    """

    async def test_the_timestamp_advances_so_attribution_stays_correct(
        self, db_session: AsyncSession
    ) -> None:
        """ADR-011's defect, arriving through the upsert instead of an overwrite.

        `record_video` only advances `recovered_at` when the record carries
        one, and this caller passed none. The second contribution therefore
        kept the first run's timestamp, and `videos.recovery_source` — ordered
        by `recovered_at DESC` — credited whichever *other* source had a newer
        untouched row. The write was Filmot's; the attribution was not.
        """
        await _seed(db_session, "filmot2nd1", duration=0, channel_id=None)
        await run_filmot_recovery(
            db_session,
            _client([FilmotVideo(id="filmot2nd1", title="Real Title")]),
        )
        first = await db_session.scalar(
            text(
                "SELECT recovered_at FROM video_recovery_sources "
                "WHERE video_id = 'filmot2nd1' AND source = 'filmot'"
            )
        )

        await run_filmot_recovery(
            db_session,
            _client(
                [FilmotVideo(id="filmot2nd1", title="Real Title", channelid=_CHANNEL)]
            ),
        )

        second = await db_session.scalar(
            text(
                "SELECT recovered_at FROM video_recovery_sources "
                "WHERE video_id = 'filmot2nd1' AND source = 'filmot'"
            )
        )
        assert second > first, (
            "the second contribution kept the first one's timestamp, so the "
            "attribution projection can credit a source that wrote nothing"
        )
        _, _, _, recovery_source = await _row(db_session, "filmot2nd1")
        assert recovery_source == "filmot"


class TestTheChannelGateIsReAssertedToo:
    async def test_a_channel_deleted_after_the_check_refuses_the_write(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The one Python condition that was not re-asserted in SQL.

        Every other gate is checked twice; this one was checked in Python and
        trusted at write time. A channel deleted in between raised a
        foreign-key violation that no longer belonged to one video — it
        escaped the batch, ended the run, and rolled back that batch's
        already-applied writes. Re-asserting it makes this an ordinary refusal.
        """
        await _seed(db_session, "filmotfk1", channel_id=None, duration=300)
        original = filmot_recovery._conditional_update

        async def racing(session: AsyncSession, video: Any, updates: dict[str, Any]):
            await session.execute(
                text("DELETE FROM videos WHERE channel_id = :c AND video_id <> :v"),
                {"c": _CHANNEL, "v": "filmotfk1"},
            )
            await session.execute(
                text("DELETE FROM channels WHERE channel_id = :c"), {"c": _CHANNEL}
            )
            return await original(session, video, updates)

        monkeypatch.setattr(filmot_recovery, "_conditional_update", racing)
        client = _client(
            [FilmotVideo(id="filmotfk1", title="Real Title", channelid=_CHANNEL)]
        )

        result = await run_filmot_recovery(db_session, client)

        assert result.ended_early is None, "an FK violation ended the whole run"
        assert result.updated == 0
        assert await _provenance(db_session, "filmotfk1") == []


class TestOtherSourcesAreUntouched:
    async def test_an_existing_contribution_survives(
        self, db_session: AsyncSession
    ) -> None:
        """FR-028/FR-029 — the cross-feature contract, read back through the
        contribution-reporting path rather than asserted on a mock."""
        await _seed(db_session, "filmotxf1")
        await db_session.execute(
            text(
                "INSERT INTO video_recovery_sources (video_id, source, "
                "source_detail, fields_written) VALUES (:v, 'wayback', "
                "'20210101080938', ARRAY['description'])"
            ),
            {"v": "filmotxf1"},
        )
        await db_session.commit()

        client = _client([FilmotVideo(id="filmotxf1", title="Real Title")])
        await run_filmot_recovery(db_session, client)

        rows = await _provenance(db_session, "filmotxf1")
        sources = {r[0]: r for r in rows}
        assert set(sources) == {"filmot", "wayback"}
        assert sources["wayback"][1] == "20210101080938", (
            "another source's capture time must survive untouched — losing it "
            "is what cost 92 rows their attribution"
        )


class TestNoSideEffects:
    async def test_no_channel_is_ever_created(self, db_session: AsyncSession) -> None:
        """FR-006/SC-003, and FR-006a: not retried on a later run either."""
        await _seed(db_session, "filmotchan1", with_channel=False)
        before = (
            await db_session.execute(text("SELECT count(*) FROM channels"))
        ).scalar()
        client = _client(
            [
                FilmotVideo(
                    id="filmotchan1",
                    title="Real Title",
                    channelid="UCneverseen0000000001",
                )
            ]
        )

        result = await run_filmot_recovery(db_session, client)
        after = (
            await db_session.execute(text("SELECT count(*) FROM channels"))
        ).scalar()

        assert after == before
        assert result.unknown_channels == ["UCneverseen0000000001"]
        _, channel_id, _, _ = await _row(db_session, "filmotchan1")
        assert channel_id is None

        # A second run must not link it either.
        await run_filmot_recovery(db_session, client)
        _, channel_id, _, _ = await _row(db_session, "filmotchan1")
        assert channel_id is None

    async def test_upload_date_never_changes(self, db_session: AsyncSession) -> None:
        """FR-008/SC-004."""
        await _seed(db_session, "filmotdate1")
        before = (
            await db_session.execute(
                text("SELECT upload_date FROM videos WHERE video_id = 'filmotdate1'")
            )
        ).scalar()

        client = _client(
            [FilmotVideo(id="filmotdate1", title="Real Title", uploaddate="1999-01-01")]
        )
        await run_filmot_recovery(db_session, client)

        after = (
            await db_session.execute(
                text("SELECT upload_date FROM videos WHERE video_id = 'filmotdate1'")
            )
        ).scalar()
        assert after == before


class TestIdempotency:
    async def test_a_second_run_writes_nothing_and_adds_no_row(
        self, db_session: AsyncSession
    ) -> None:
        """FR-023/SC-006."""
        await _seed(db_session, "filmotidem1")
        client = _client(
            [
                FilmotVideo(
                    id="filmotidem1",
                    title="Real Title",
                    channelid=_CHANNEL,
                    duration=214,
                )
            ]
        )

        first = await run_filmot_recovery(db_session, client)
        rows_after_first = len(await _provenance(db_session, "filmotidem1"))
        second = await run_filmot_recovery(db_session, client)

        assert first.updated == 1
        assert second.updated == 0
        assert len(await _provenance(db_session, "filmotidem1")) == rows_after_first


class TestReportingIntegrity:
    async def test_a_failed_lookup_is_never_reported_as_absent(
        self, db_session: AsyncSession
    ) -> None:
        """SC-007. The distinction this whole feature descends from."""
        await _seed(db_session, "filmotfail1")
        client = _client([], unresolved={"filmotfail1"})

        result = await run_filmot_recovery(db_session, client)

        assert result.updated == 0
        assert result.not_held == 0, (
            "a request that did not complete says nothing about whether the "
            "archive holds a record"
        )
        assert result.unresolved == 1

    async def test_the_reconciliation_identity_holds(
        self, db_session: AsyncSession
    ) -> None:
        """FR-022b: updated + held_no_write == returned, when nothing failed."""
        await _seed(db_session, "filmotrec1")
        await _seed(
            db_session,
            "filmotrec2",
            title="A Real Title",
            channel_id=_CHANNEL,
            duration=300,
        )
        client = _client(
            [
                FilmotVideo(id="filmotrec1", title="Real Title"),
                FilmotVideo(id="filmotrec2", title="Archive Title"),
            ]
        )

        result = await run_filmot_recovery(db_session, client)

        assert (
            result.reconciles
        ), f"{result.updated} + {result.held_no_write} != {result.returned}"

    async def test_dry_run_writes_nothing(self, db_session: AsyncSession) -> None:
        """FR-020."""
        await _seed(db_session, "filmotdry1")
        before = await _row(db_session, "filmotdry1")
        client = _client([FilmotVideo(id="filmotdry1", title="Real Title")])

        result = await run_filmot_recovery(db_session, client, dry_run=True)

        assert result.updated == 1, "dry run still reports what it would do"
        assert await _row(db_session, "filmotdry1") == before
        assert await _provenance(db_session, "filmotdry1") == []


class TestUnconfigured:
    async def test_an_unconfigured_source_is_skipped_not_failed(
        self, db_session: AsyncSession
    ) -> None:
        """FR-019/SC-009."""
        client = MagicMock()
        client.is_configured = False
        client.fetch_videos = AsyncMock()

        result = await run_filmot_recovery(db_session, client)

        assert result.ended_early == "not_configured"
        assert result.submitted == 0
        client.fetch_videos.assert_not_awaited()
