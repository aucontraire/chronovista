"""The invariant audit (``chronovista audit-invariants``) against the integration database.

Each check is seeded with one violation and one clean record, and the test asserts
the exact keys the seeding added (``after - before``), so it stays exact whatever else
the database holds. Each docstring names the ``Mutation`` that turns it red.
Placeholder names only.
"""

from __future__ import annotations

import logging
import os
import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.config import database as database_module
from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import VideoTag as VideoTagDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.entity_mention import EntityMentionCreate
from chronovista.services.invariant_audit_service import (
    REGISTRY,
    CheckRun,
    InvariantCheck,
    compare,
    exit_code,
    run_checks,
    select_checks,
)
from chronovista.services.mention_repair_service import MentionRepairService
from tests.factories.mention_world import (
    A_NAME,
    B_NAME,
    batch_service,
    make_entity,
    mark_corrected,
    new_video_id,
    place,
    seed_world,
)
from tests.factories.proximity_seed import seed_mention, seed_segment, seed_video

pytestmark = pytest.mark.asyncio

DATABASE_URL = "postgresql+asyncpg://audit@localhost:5434/chronovista_integration_test"
INTEGRATION_URL = "postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test"


class TestReadOnly:
    async def test_a_writing_check_is_refused_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        """A check that tries to write fails as an error and changes nothing.

        Mutation: drop ``SET TRANSACTION READ ONLY`` in ``_run_one``; the UPDATE then
        succeeds, the check holds, and this test goes red.
        """
        entity_id = await make_entity(db_session, A_NAME)

        async def writes(session: AsyncSession) -> dict[str, set[str]]:
            await session.execute(
                update(NamedEntityDB)
                .where(NamedEntityDB.id == entity_id)
                .values(mention_count=999)
            )
            return {"Z9-writes": set()}

        check = InvariantCheck(
            check_id="Z9-writes",
            register_entry="Z9",
            rule="test-only: a check that writes",
            rule_version=1,
            key_kind="row_id",
            run=writes,
        )

        run = await run_checks(
            db_session, [check], database_url=DATABASE_URL, take_snapshot=False
        )

        [result] = run.results
        assert result.outcome == "error"
        assert result.error is not None and "25006" in result.error
        stored = await db_session.scalar(
            select(NamedEntityDB.mention_count).where(NamedEntityDB.id == entity_id)
        )
        assert stored == 0

    async def test_the_read_only_session_cannot_write_even_after_a_commit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``db_manager.session(read_only=True)`` refuses a write, including in the
        transaction a stray ``commit()`` starts.

        Mutation: drop ``default_transaction_read_only`` from the read-only engine; the
        second write succeeds and this test goes red.
        """
        monkeypatch.setattr(
            database_module,
            "settings",
            SimpleNamespace(
                effective_database_url=os.getenv(
                    "DATABASE_INTEGRATION_URL", INTEGRATION_URL
                ),
                db_log_queries=False,
                is_development_database=True,
            ),
        )
        manager = database_module.DatabaseManager()
        try:
            async with manager.session(read_only=True) as session:
                with pytest.raises(DBAPIError, match="read-only"):
                    await session.execute(text("CREATE TEMP TABLE audit_probe (x int)"))
                await session.rollback()
                await session.commit()
                with pytest.raises(DBAPIError, match="read-only"):
                    await session.execute(text("CREATE TEMP TABLE audit_probe (x int)"))
        finally:
            await manager.close()

    async def test_an_error_message_never_reaches_the_result(
        self, db_session: AsyncSession
    ) -> None:
        """An exception's message can quote a key; only its class is kept (FR-009a).

        Mutation: put ``str(exc)`` into ``_describe_error``; the key then appears in
        the result and this test goes red.
        """

        async def leaks(session: AsyncSession) -> dict[str, set[str]]:
            raise ValueError("row Abcdefghij9/en is bad")

        run = await run_checks(
            db_session,
            [_check("Z6-leaks", leaks)],
            database_url=DATABASE_URL,
            take_snapshot=False,
        )

        assert run.results[0].outcome == "error"
        assert run.results[0].error is not None
        assert "Abcdefghij9" not in run.results[0].error

    async def test_a_failing_check_does_not_stop_the_next(
        self, db_session: AsyncSession
    ) -> None:
        """One check errors, the next still runs and reports.

        Mutation: let ``_run_one`` re-raise; the run aborts and this test goes red.
        """

        async def fails(session: AsyncSession) -> dict[str, set[str]]:
            await session.execute(text("select 1/0"))
            return {}

        async def holds(session: AsyncSession) -> dict[str, set[str]]:
            return {"Z8-holds": set()}

        checks = [
            InvariantCheck(
                check_id="Z7-fails",
                register_entry="Z7",
                rule="test-only",
                rule_version=1,
                key_kind="row_id",
                run=fails,
            ),
            InvariantCheck(
                check_id="Z8-holds",
                register_entry="Z8",
                rule="test-only",
                rule_version=1,
                key_kind="row_id",
                run=holds,
            ),
        ]

        run = await run_checks(
            db_session, checks, database_url=DATABASE_URL, take_snapshot=False
        )

        assert [r.outcome for r in run.results] == ["error", "holds"]


def _check(check_id: str, run: CheckRun) -> InvariantCheck:
    return InvariantCheck(
        check_id=check_id,
        register_entry=check_id.split("-")[0],
        rule="test-only",
        rule_version=1,
        key_kind="row_id",
        run=run,
    )


class TestContainment:
    async def test_every_check_reads_one_repeatable_read_snapshot(
        self, db_session: AsyncSession
    ) -> None:
        """Mutation: drop the ``SET TRANSACTION ISOLATION LEVEL`` in ``run_checks``;
        the check then sees ``read committed`` and this test goes red.
        """
        seen: list[str] = []

        async def observe(session: AsyncSession) -> dict[str, set[str]]:
            seen.append(str(await session.scalar(text("SHOW transaction_isolation"))))
            return {"Z5-observe": set()}

        await run_checks(
            db_session, [_check("Z5-observe", observe)], database_url=DATABASE_URL
        )

        assert seen == ["repeatable read"]

    async def test_a_session_that_already_ran_a_query_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        """Without this, the snapshot would be skipped silently."""
        await db_session.execute(text("select 1"))
        with pytest.raises(RuntimeError, match="fresh session"):
            await run_checks(db_session, [], database_url=DATABASE_URL)

    async def test_a_check_that_ends_the_transaction_fails_it_and_the_rest(
        self, db_session: AsyncSession
    ) -> None:
        """A check that commits loses the snapshot: it and later checks are errors,
        and the run still finishes.

        Mutation: drop the ``savepoint.is_active`` check in ``_run_one``; the
        rollback of a closed savepoint then raises out of ``run_checks``.
        """

        async def commits(session: AsyncSession) -> dict[str, set[str]]:
            await session.commit()
            return {"Z4-commits": set()}

        async def later(session: AsyncSession) -> dict[str, set[str]]:
            return {"Z3-later": set()}

        run = await run_checks(
            db_session,
            [_check("Z4-commits", commits), _check("Z3-later", later)],
            database_url=DATABASE_URL,
        )

        assert [r.outcome for r in run.results] == ["error", "error"]
        assert run.results[1].error is not None
        assert "earlier check" in run.results[1].error

    async def test_keys_returned_under_the_wrong_id_are_an_error(
        self, db_session: AsyncSession
    ) -> None:
        """Mutation: fall back to an empty set for a missing ID; the typo then reads
        as "holds" and this test goes red.
        """

        async def typo(session: AsyncSession) -> dict[str, set[str]]:
            return {"Z2-typo": {"1", "2"}}

        run = await run_checks(
            db_session,
            [_check("Z2-real", typo)],
            database_url=DATABASE_URL,
            take_snapshot=False,
        )

        assert run.results[0].outcome == "error"

    async def test_a_session_setting_does_not_reach_the_next_read_only_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A caller that turns read-only off for its connection does not poison the
        pool.

        Mutation: drop ``RESET ALL`` from the read-only session's cleanup; the next
        session reuses the connection with read-only off and this test goes red.
        """
        monkeypatch.setattr(
            database_module,
            "settings",
            SimpleNamespace(
                effective_database_url=os.getenv(
                    "DATABASE_INTEGRATION_URL", INTEGRATION_URL
                ),
                db_log_queries=False,
                is_development_database=True,
            ),
        )
        manager = database_module.DatabaseManager()
        try:
            async with manager.session(read_only=True) as session:
                await session.execute(
                    text("SET SESSION default_transaction_read_only = off")
                )
                await session.commit()
            async with manager.session(read_only=True) as session:
                assert await session.scalar(text("SHOW transaction_read_only")) == "on"
        finally:
            await manager.close()


# ---------------------------------------------------------------------------
# The registered checks. Each runs, seeds one violation and one clean record, runs
# again, and asserts exactly the violation's key was added.
# ---------------------------------------------------------------------------


async def _keys(session: AsyncSession, check_id: str) -> set[str]:
    run = await run_checks(
        session,
        select_checks(REGISTRY, [check_id]),
        database_url=DATABASE_URL,
        take_snapshot=False,
    )
    [result] = run.results
    assert result.outcome != "error", result.error
    return result.keys


async def _transcript(session: AsyncSession, video_id: str) -> VideoTranscriptDB:
    return (
        await session.execute(
            select(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == video_id,
                VideoTranscriptDB.language_code == "en",
            )
        )
    ).scalar_one()


async def _tag(
    session: AsyncSession,
    form: str,
    *,
    status: str = "active",
    entity_id: uuid.UUID | None = None,
    merged_into: uuid.UUID | None = None,
    alias_count: int = 0,
    video_count: int = 0,
) -> uuid.UUID:
    tag = CanonicalTagDB(
        canonical_form=form,
        normalized_form=form.lower(),
        status=status,
        entity_id=entity_id,
        merged_into_id=merged_into,
        alias_count=alias_count,
        video_count=video_count,
    )
    session.add(tag)
    await session.flush()
    return uuid.UUID(str(tag.id))


async def _alias(
    session: AsyncSession, tag_id: uuid.UUID, raw: str, normalized: str | None = None
) -> uuid.UUID:
    alias = TagAliasDB(
        raw_form=raw, normalized_form=normalized or raw.lower(), canonical_tag_id=tag_id
    )
    session.add(alias)
    await session.flush()
    return uuid.UUID(str(alias.id))


async def _bare_transcript(session: AsyncSession) -> tuple[str, int]:
    """A video with an English transcript and two segments, and no entities."""
    video_id = new_video_id()
    await seed_video(session, video_id)
    first = await seed_segment(session, video_id, "en", 10.0, 0)
    await seed_segment(session, video_id, "en", 14.0, 1)
    return video_id, first


class TestTranscriptChecks:
    async def test_t1_flag(self, db_session: AsyncSession) -> None:
        """Both directions: corrected segments with the flag false, and the flag true
        with no corrected segment.

        Mutation: flag only ``has_corrections IS FALSE`` with corrected segments; the
        second case is then missed and this test goes red.
        """
        before = await _keys(db_session, "T1-correction-flag")
        bad = await seed_world(db_session)
        await mark_corrected(db_session, bad.seg_a["en"], "fixed words")
        flag_without_segment, _ = await _bare_transcript(db_session)
        (await _transcript(db_session, flag_without_segment)).has_corrections = True
        await _bare_transcript(db_session)  # clean: uncorrected, flag false
        await db_session.flush()

        after = await _keys(db_session, "T1-correction-flag")

        assert after - before == {f"{bad.video_id}/en", f"{flag_without_segment}/en"}

    async def test_t1_count_counts_corrected_segments_not_corrections(
        self, db_session: AsyncSession
    ) -> None:
        """A re-corrected segment counts once.

        Both directions: one segment counted twice, and a corrected segment not counted.

        Mutation: flag only a count above the corrected segments (``>`` for ``!=``);
        the under-count is then missed and this test goes red.
        """
        before = await _keys(db_session, "T1-correction-count")
        bad = await seed_world(db_session)
        await mark_corrected(db_session, bad.seg_a["en"], "fixed words")
        (await _transcript(db_session, bad.video_id)).correction_count = 2
        under_video, under_segment = await _bare_transcript(db_session)
        await mark_corrected(db_session, under_segment, "fixed words")
        clean_video, clean_segment = await _bare_transcript(db_session)
        await mark_corrected(db_session, clean_segment, "fixed again")
        (await _transcript(db_session, clean_video)).correction_count = 1
        await db_session.flush()

        after = await _keys(db_session, "T1-correction-count")

        assert after - before == {f"{bad.video_id}/en", f"{under_video}/en"}

    async def test_t7_matches_the_rebuild(self, db_session: AsyncSession) -> None:
        """T7 flags a stale corrected transcript, and holds for it once the rebuild
        has run: the check and the rebuild share one rule.

        A corrected segment with no correction text reads as empty, as in the rebuild.

        Mutation: join the segments in reverse order, or with another separator, or drop
        the ``coalesce``; a transcript is then misjudged and this test goes red.
        """
        before = await _keys(db_session, "T7-stored-full-text")
        stale = await seed_world(db_session)
        await mark_corrected(db_session, stale.seg_a["en"], "fixed words")
        await _bare_transcript(db_session)  # uncorrected, text differs: out of scope
        missing_video, missing_segment = await _bare_transcript(db_session)
        await db_session.execute(
            update(TranscriptSegmentDB)
            .where(TranscriptSegmentDB.id == missing_segment)
            .values(has_correction=True, corrected_text=None)
        )
        # A corrected segment with no correction text reads as empty: " placeholder".
        (await _transcript(db_session, missing_video)).transcript_text = " placeholder"
        await db_session.flush()

        assert await _keys(db_session, "T7-stored-full-text") - before == {
            f"{stale.video_id}/en"
        }

        (await _transcript(db_session, stale.video_id)).has_corrections = True
        await db_session.flush()
        await batch_service().rebuild_text(
            db_session, video_ids=[stale.video_id], dry_run=False
        )

        assert await _keys(db_session, "T7-stored-full-text") - before == set()


class TestTagChecks:
    async def test_g1_alias_placement(self, db_session: AsyncSession) -> None:
        """Mutation: drop the active-status condition; the alias on the deprecated
        tag is then flagged and this test goes red.
        """
        before = await _keys(db_session, "G1-alias-placement")
        active = await _tag(db_session, "Quux Topic")
        await _alias(db_session, active, "Quux Topic")
        wrong_form = await _alias(db_session, active, "Quux Topik", "quux topik")
        merged = await _tag(db_session, "Quux Old", status="merged", merged_into=active)
        on_merged = await _alias(db_session, merged, "Quux Old")
        deprecated = await _tag(db_session, "Quux Gone", status="deprecated")
        await _alias(db_session, deprecated, "Quux Gone", "something else")

        after = await _keys(db_session, "G1-alias-placement")

        assert after - before == {str(wrong_form), str(on_merged)}

    async def test_g2_merge_state(self, db_session: AsyncSession) -> None:
        """Each arm adds its key.

        Mutation: remove any one arm of ``merge_state_violations``, or drop the
        active-status condition from the one-active-tag arm; a key is then missing (or
        the clean entity is flagged) and this test goes red.
        """
        before = await _keys(db_session, "G2-merge-state")
        target = await _tag(db_session, "Zeta Target")
        no_target = await _tag(db_session, "Zeta A", status="merged")
        to_self = await _tag(db_session, "Zeta B", status="merged")
        to_self_row = await db_session.get(CanonicalTagDB, to_self)
        assert to_self_row is not None
        to_self_row.merged_into_id = to_self
        entity = await make_entity(db_session, A_NAME)
        keeps_entity = await _tag(
            db_session, "Zeta C", status="merged", merged_into=target, entity_id=entity
        )
        owns_alias = await _tag(
            db_session, "Zeta D", status="merged", merged_into=target
        )
        await _alias(db_session, owns_alias, "Zeta D")
        shared = await make_entity(db_session, B_NAME)
        await _tag(db_session, "Zeta E", entity_id=shared)
        await _tag(db_session, "Zeta F", entity_id=shared)
        await _tag(db_session, "Zeta Fine", status="merged", merged_into=target)
        # Clean: one active tag and one deprecated tag for the same entity.
        kept = await make_entity(db_session, "Quux Kept")
        await _tag(db_session, "Zeta G", entity_id=kept)
        await _tag(db_session, "Zeta H", status="deprecated", entity_id=kept)
        await db_session.flush()

        after = await _keys(db_session, "G2-merge-state")

        assert after - before == {
            str(no_target),
            str(to_self),
            str(keeps_entity),
            str(owns_alias),
            f"entity:{shared}",
        }

    async def test_g3_tag_counters(self, db_session: AsyncSession) -> None:
        """Mutation: join ``video_tags`` on the normalized form instead of the raw
        form; the video-count drift is then missed and this test goes red.
        """
        before = await _keys(db_session, "G3-tag-counters")
        video_id = new_video_id()
        await seed_video(db_session, video_id)
        wrong_aliases = await _tag(db_session, "Gamma One", alias_count=5)
        await _alias(db_session, wrong_aliases, "Gamma One")
        wrong_videos = await _tag(db_session, "Gamma Two", alias_count=1, video_count=0)
        await _alias(db_session, wrong_videos, "Gamma-Two-Raw", "gamma two")
        db_session.add(VideoTagDB(video_id=video_id, tag="Gamma-Two-Raw"))
        right = await _tag(db_session, "Gamma Three", alias_count=1, video_count=0)
        await _alias(db_session, right, "Gamma Three")
        frozen = await _tag(
            db_session, "Gamma Old", status="merged", merged_into=right, alias_count=9
        )
        assert frozen
        await db_session.flush()

        after = await _keys(db_session, "G3-tag-counters")

        assert after - before == {str(wrong_aliases), str(wrong_videos)}


class TestMentionChecks:
    async def test_c3_counts_asr_matches(self, db_session: AsyncSession) -> None:
        """An ``asr_match`` mention counts; an entity whose mentions are all gone but
        whose counters are not is drift too; a correctly counted entity is clean.

        Mutation: drop the ``asr_match`` arm of the shared counting rule, make the
        recount join inner, or double the recount; one case is then misjudged and this
        test goes red.
        """
        before = await _keys(db_session, "C3-entity-counters")
        world = await seed_world(db_session, a_mentioned=False)
        await seed_mention(
            db_session,
            entity_id=world.a,
            video_id=world.video_id,
            language_code="en",
            segment_id=world.seg_a["en"],
            mention_text="a garbled form",
            detection_method="asr_match",
        )
        clean = await make_entity(db_session, "Quux Lone")
        # B has one counted mention; store its counters correctly, so it is clean.
        counted = await db_session.get(NamedEntityDB, world.b)
        assert counted is not None
        counted.mention_count, counted.video_count = 1, 1
        emptied = await make_entity(db_session, "Quux Emptied")
        stored = await db_session.get(NamedEntityDB, emptied)
        assert stored is not None
        stored.mention_count, stored.video_count = 3, 1
        await db_session.flush()

        after = await _keys(db_session, "C3-entity-counters")

        assert after - before == {str(world.a), str(emptied)}
        assert str(clean) not in after and str(world.b) not in after

    @pytest.mark.parametrize(
        "arm",
        [
            "manual_with_segment",
            "manual_with_start",
            "manual_with_end",
            "manual_with_end_segment",
            "alias_on_asr",
            "video",
            "language",
            "end_segment_language",
        ],
    )
    async def test_m9_mention_shape(self, db_session: AsyncSession, arm: str) -> None:
        """Each arm is flagged; a manual row with a confidence (an observation) is not.

        Mutation: remove an arm (or one condition of the manual arm) from
        ``mention_shape_violations``; its case is then missed and this test goes red.
        """
        before = await _keys(db_session, "M9-mention-shape")
        world = await seed_world(db_session, a_mentioned=False, languages=("en", "fr"))
        other_video, _ = await _bare_transcript(db_session)
        alias_id = (
            await db_session.execute(
                select(EntityAliasDB.id).where(EntityAliasDB.entity_id == world.a)
            )
        ).scalar_one()
        fields: dict[str, object] = {
            "entity_id": world.a,
            "video_id": world.video_id,
            "language_code": "en",
            "segment_id": world.seg_a["en"],
            "mention_text": A_NAME,
            "detection_method": "rule_match",
            "mention_source": "transcript",
        }
        manual = {"detection_method": "manual", "mention_source": "manual"}
        if arm == "manual_with_segment":
            fields.update(manual)
            with pytest.raises(ValidationError):
                EntityMentionCreate.model_validate(fields)
        elif arm in ("manual_with_start", "manual_with_end", "manual_with_end_segment"):
            fields.update(manual, segment_id=None, language_code=None)
            fields.update(
                {
                    "manual_with_start": {"match_start": 0},
                    "manual_with_end": {"match_end": 4},
                    "manual_with_end_segment": {"end_segment_id": world.seg_b["en"]},
                }[arm]
            )
            with pytest.raises(ValidationError):
                EntityMentionCreate.model_validate(fields)
        elif arm == "end_segment_language":
            # Same video, other language: only the end segment's language differs.
            fields.update(end_segment_id=world.seg_a["fr"])
        elif arm == "alias_on_asr":
            fields.update(detection_method="asr_match", alias_id=alias_id)
            with pytest.raises(ValidationError):
                EntityMentionCreate.model_validate(fields)
        elif arm == "video":
            fields.update(video_id=other_video)
        else:
            fields.update(language_code="fr")
        bad = EntityMentionDB(**fields)
        db_session.add(bad)
        db_session.add(
            EntityMentionDB(
                entity_id=world.a,
                video_id=other_video,
                mention_text=A_NAME,
                detection_method="manual",
                mention_source="manual",
                confidence=1.0,
            )
        )
        await db_session.flush()

        after = await _keys(db_session, "M9-mention-shape")

        assert after - before == {str(bad.id)}

    async def test_m1_m2_come_from_the_repair_plan(
        self, db_session: AsyncSession
    ) -> None:
        """A stale mention is M1, a second row over one occurrence is M2, and both agree
        with the repair's own counts.

        Mutation: record duplicates under ``stale_ids``; the M1 and M2 sets then mix
        and this test goes red.
        """
        before_m1 = await _keys(db_session, "M1-mention-reads")
        before_m2 = await _keys(db_session, "M2-one-row-per-occurrence")
        entity, video_id, segment = await _corrected_world(
            db_session, f"we saw {A_NAME} here"
        )
        await place(
            db_session,
            entity_id=entity,
            video_id=video_id,
            segment_id=segment,
            start=7,
            mention_text=A_NAME,
        )
        await place(
            db_session,
            entity_id=entity,
            video_id=video_id,
            segment_id=segment,
            start=12,
            mention_text="Quux",
            method="user_correction",
        )
        stale_entity = await make_entity(db_session, "Quux Stale")
        stale_video, stale_segment = await _bare_transcript(db_session)
        await mark_corrected(db_session, stale_segment, "nothing named here")
        await place(
            db_session,
            entity_id=stale_entity,
            video_id=stale_video,
            segment_id=stale_segment,
            start=0,
            mention_text=A_NAME,
        )
        m1 = await _keys(db_session, "M1-mention-reads") - before_m1
        m2 = await _keys(db_session, "M2-one-row-per-occurrence") - before_m2
        report = await MentionRepairService().repair(db_session, dry_run=True)

        assert len(m1) == 1 and len(m2) == 1 and m1.isdisjoint(m2)
        # The integration database is fresh per test, so the repair's report covers
        # exactly these rows.
        assert report.stale_moved + report.stale_removed == len(m1 | before_m1)
        assert report.duplicates_removed == len(m2 | before_m2)


async def _corrected_world(
    session: AsyncSession, text_value: str
) -> tuple[uuid.UUID, str, int]:
    world = await seed_world(
        session, a_mentioned=False, a_segment_text="(original words)"
    )
    await mark_corrected(session, world.seg_a["en"], text_value)
    return world.a, world.video_id, world.seg_a["en"]


class TestBeforeAndAfter:
    async def test_save_then_compare_reports_new_and_resolved(
        self, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
    ) -> None:
        """One violation resolved and another added: the comparison reports both and
        fails, although the total did not rise. No key reaches the logs.

        Mutation: compare violation counts instead of keys; one in, one out then
        reads as no change and this test goes red.
        """
        tag = await _tag(db_session, "Delta Topic")
        first = await _alias(db_session, tag, "Delta One", "delta one wrong")
        checks = select_checks(REGISTRY, ["G1"])
        with caplog.at_level(logging.DEBUG):
            baseline = await run_checks(
                db_session, checks, database_url=DATABASE_URL, take_snapshot=False
            )
            first_alias = await db_session.get(TagAliasDB, first)
            assert first_alias is not None
            first_alias.normalized_form = "delta topic"
            second = await _alias(db_session, tag, "Delta Two", "delta two wrong")
            await db_session.flush()
            current = await run_checks(
                db_session, checks, database_url=DATABASE_URL, take_snapshot=False
            )

        [comparison] = compare(baseline, current, sample=5, show_library_keys=False)

        assert (comparison.new, comparison.resolved) == (1, 1)
        assert comparison.sample_new == [str(second)]
        assert exit_code(current, [comparison]) == 1
        for key in (str(first), str(second)):
            assert key not in caplog.text


class TestWholeRegistry:
    async def test_every_check_runs_from_the_real_snapshot_on_an_empty_library(
        self, db_session: AsyncSession
    ) -> None:
        """The full registry, through the real repeatable-read read-only snapshot.

        On an empty library every rule holds; an error here means a check's SQL does
        not run under the read-only snapshot.
        """
        run = await run_checks(db_session, REGISTRY, database_url=DATABASE_URL)

        assert {r.check_id: r.outcome for r in run.results} == {
            c.check_id: "holds" for c in REGISTRY
        }
