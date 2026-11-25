"""Repairing mentions left stale or duplicated before #426 (``entities repair-mentions``).

Each test seeds a shape found in production, as rows written before the fix look,
then runs :class:`MentionRepairService` (or the Typer command over it) against the
integration database. Placeholder names only.

Each docstring names, where the test guards a specific behaviour, the ``Mutation``
that turns it red.
"""

from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
    MentionRelabel,
)
from chronovista.services.mention_repair_service import MentionRepairService
from tests.factories.mention_world import (
    A_NAME,
    B_NAME,
    GARBLE,
    SURNAME,
    World,
    add_alias,
    apply_text,
    assert_mentions_ok,
    correct,
    invoke_cli,
    is_current,
    make_entity,
    mark_corrected,
    new_video_id,
    place,
    positioned,
    scan,
    scope_state,
    seed_segments,
    seed_three_segment_world,
    seed_world,
    set_text,
    settle,
    snapshot,
)
from tests.factories.proximity_seed import (
    seed_mention,
    seed_segment,
    seed_title_mention,
    seed_video,
)

pytestmark = pytest.mark.asyncio


async def _corrected_world(
    session: AsyncSession, text: str
) -> tuple[uuid.UUID, str, int]:
    """A video whose first segment has been corrected to ``text``."""
    world = await seed_world(
        session,
        a_mentioned=False,
        a_segment_text="(original words)",
        b_segment_text=f"then {B_NAME} replied",
    )
    await mark_corrected(session, world.seg_a["en"], text)
    return world.a, world.video_id, world.seg_a["en"]


async def _rows(
    session: AsyncSession, entity_id: uuid.UUID
) -> list[tuple[str, str, int | None, int | None]]:
    return [
        (m.detection_method, m.mention_text, m.match_start, m.match_end)
        for m in (
            await session.execute(
                select(EntityMentionDB)
                .where(EntityMentionDB.entity_id == entity_id)
                .order_by(EntityMentionDB.match_start)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    ]


async def _repair(
    session: AsyncSession, video: str, *, dry_run: bool = False
) -> dict[str, object]:
    """The report of one repair of one video, without its ``dry_run`` flag."""
    report = await MentionRepairService().repair(
        session, video_ids=[video], dry_run=dry_run
    )
    out = report.model_dump()
    out.pop("dry_run")
    return out


def _changes(report: dict[str, object]) -> tuple[object, object, object]:
    return (
        report["stale_moved"],
        report["stale_removed"],
        report["duplicates_removed"],
    )


class TestStaleTwin:
    async def test_the_stale_correction_row_goes_and_the_scan_row_stays(
        self, db_session: AsyncSession
    ) -> None:
        """A correction tagged the name at 7; a later edit moved it to 11; a full
        rescan recorded it again at 11. One occurrence, so one mention."""
        a, video, seg = await _corrected_world(db_session, f"we all saw {A_NAME} here")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg,
            mention_text=A_NAME,
            start=7,
            method="user_correction",
        )
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg,
            mention_text=A_NAME,
            start=11,
        )

        report = await MentionRepairService().repair(
            db_session, video_ids=[video], dry_run=False
        )

        assert await _rows(db_session, a) == [("rule_match", A_NAME, 11, 20)]
        assert (report.stale_removed, report.stale_moved) == (1, 0)

    async def test_a_stale_row_with_no_twin_moves_to_its_words(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg = await _corrected_world(db_session, f"we all saw {A_NAME} here")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg,
            mention_text=A_NAME,
            start=7,
            method="user_correction",
        )

        report = await MentionRepairService().repair(
            db_session, video_ids=[video], dry_run=False
        )

        assert await _rows(db_session, a) == [("user_correction", A_NAME, 11, 20)]
        assert report.stale_moved == 1

    async def test_a_stale_split_name_moves_to_where_it_still_runs_across(
        self, db_session: AsyncSession
    ) -> None:
        """A correction earlier in the first segment shifted where a split name's
        first half starts; the name is still there, so it moves, not goes."""
        world = await seed_world(
            db_session,
            a_mentioned=False,
            a_segment_text="(original)",
            b_segment_text="Quux is here",
        )
        a, video = world.a, world.video_id
        seg_a, seg_b = world.seg_a["en"], world.seg_b["en"]
        await mark_corrected(db_session, seg_a, "and we saw Zeta")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg_a,
            mention_text=A_NAME,
            start=7,
            end=4,
            end_segment_id=seg_b,
            method="asr_match",
        )

        report = await MentionRepairService().repair(
            db_session, video_ids=[video], dry_run=False
        )

        assert await _rows(db_session, a) == [("asr_match", A_NAME, 11, 4)]
        assert report.stale_moved == 1


class TestRelabel:
    async def test_a_stale_asr_match_moved_onto_the_name_is_relabelled(
        self, db_session: AsyncSession
    ) -> None:
        """A recovered ``asr_match`` on the misheard form; the segment was later
        corrected to the name. The row moves onto the name AND reads as the name's
        scan match: ``rule_match``, the name's text, linked to the name's alias.

        Mutation: drop ``relabel_mentions`` from the repair's write step (or the
        relabel from the plan): the row would keep ``asr_match`` and the misheard
        text over offsets that now cover the name.
        """
        a, video, seg = await _corrected_world(db_session, f"we saw {A_NAME} here")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg,
            mention_text=GARBLE,
            start=7,
            method="asr_match",
        )
        alias_id = (
            await db_session.execute(
                select(EntityAliasDB.id).where(
                    EntityAliasDB.entity_id == a, EntityAliasDB.alias_name == A_NAME
                )
            )
        ).scalar_one()

        report = await MentionRepairService().repair(
            db_session, video_ids=[video], dry_run=False
        )

        assert report.stale_moved == 1
        assert await _rows(db_session, a) == [("rule_match", A_NAME, 7, 16)]
        row = (
            await db_session.execute(
                select(EntityMentionDB)
                .where(EntityMentionDB.entity_id == a)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert row.alias_id == alias_id
        await assert_mentions_ok(db_session, video)

    async def test_relabel_mentions_writes_text_method_and_alias(
        self, db_session: AsyncSession
    ) -> None:
        """The repository write for a re-pointed mention sets all three columns.

        Mutation: drop any one of ``mention_text`` / ``detection_method`` /
        ``alias_id`` from the UPDATE's values.
        """
        a, video, seg = await _corrected_world(db_session, f"we saw {A_NAME} here")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg,
            mention_text=GARBLE,
            start=7,
            method="asr_match",
        )
        alias_id = (
            await db_session.execute(
                select(EntityAliasDB.id).where(EntityAliasDB.entity_id == a)
            )
        ).scalar_one()
        mention_id = (
            await db_session.execute(
                select(EntityMentionDB.id).where(EntityMentionDB.entity_id == a)
            )
        ).scalar_one()

        written = await EntityMentionRepository().relabel_mentions(
            db_session,
            [
                MentionRelabel(
                    id=mention_id,
                    mention_text=A_NAME,
                    detection_method="rule_match",
                    alias_id=alias_id,
                )
            ],
        )

        assert written == 1
        row = (
            await db_session.execute(
                select(EntityMentionDB)
                .where(EntityMentionDB.id == mention_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert (row.mention_text, row.detection_method, row.alias_id) == (
            A_NAME,
            "rule_match",
            alias_id,
        )


class TestFragmentOverlap:
    async def test_the_full_name_is_kept_over_the_corrected_fragment(
        self, db_session: AsyncSession
    ) -> None:
        text = f"we saw {A_NAME} here"
        a, video, seg = await _corrected_world(db_session, text)
        await add_alias(db_session, a, SURNAME)
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg,
            mention_text=SURNAME,
            start=text.index(SURNAME),
            method="user_correction",
        )
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg,
            mention_text=A_NAME,
            start=7,
        )

        report = await MentionRepairService().repair(
            db_session, video_ids=[video], dry_run=False
        )

        assert await _rows(db_session, a) == [("rule_match", A_NAME, 7, 16)]
        assert report.duplicates_removed == 1


class TestSplitNameAndItsAlias:
    async def test_the_alias_inside_a_split_name_goes(
        self, db_session: AsyncSession
    ) -> None:
        """The scanner wrote a split "Zeta | Quux" and, separately, the alias "Quux"
        in the second segment: one spoken name."""
        world = await seed_world(
            db_session,
            a_mentioned=False,
            a_segment_text="we saw Zeta",
            b_segment_text="Quux is here",
        )
        a, video = world.a, world.video_id
        seg_a, seg_b = world.seg_a["en"], world.seg_b["en"]
        await add_alias(db_session, a, SURNAME)
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg_a,
            mention_text=A_NAME,
            start=7,
            end=4,
            end_segment_id=seg_b,
        )
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg_b,
            mention_text=SURNAME,
            start=0,
        )

        report = await MentionRepairService().repair(
            db_session, video_ids=[video], dry_run=False
        )

        assert await _rows(db_session, a) == [("rule_match", A_NAME, 7, 4)]
        assert report.duplicates_removed == 1

    async def test_decided_in_the_first_segment_it_still_counts_in_the_second(
        self, db_session: AsyncSession
    ) -> None:
        """Both segments are repair candidates (the first is corrected). The split
        name is decided while repairing the first; the alias inside its second half
        must still be found while repairing the second, in the same run."""
        world = await seed_world(
            db_session,
            a_mentioned=False,
            a_segment_text="(original)",
            b_segment_text="Quux is here",
        )
        a, video = world.a, world.video_id
        seg_a, seg_b = world.seg_a["en"], world.seg_b["en"]
        await mark_corrected(db_session, seg_a, "we saw Zeta")
        await add_alias(db_session, a, SURNAME)
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg_a,
            mention_text=A_NAME,
            start=7,
            end=4,
            end_segment_id=seg_b,
        )
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg_b,
            mention_text=SURNAME,
            start=0,
        )

        first = await MentionRepairService().repair(
            db_session, video_ids=[video], dry_run=False
        )
        second = await MentionRepairService().repair(
            db_session, video_ids=[video], dry_run=True
        )

        assert await _rows(db_session, a) == [("rule_match", A_NAME, 7, 4)]
        assert first.duplicates_removed == 1
        assert second.duplicates_removed == 0


class TestRepairCrossRelocation:
    """A stale split name relocates to where the name still runs across; the unique
    key ``(entity, start segment, start)`` and the same entity's other rows decide
    whether it may land there."""

    async def test_a_stale_twin_of_a_valid_split_name_is_removed_not_moved_onto_it(
        self, db_session: AsyncSession
    ) -> None:
        """Valid split name at 7 and a stale twin at 3 (same segments). The twin's
        nearest crossing occurrence is the valid row's own: it must be removed, not
        moved onto the same (entity, segment, start).

        Mutation: remove the length comparison in the free-occurrence search
        (``any(len(...) >= length for other in blockers)`` -> ``False``), so no row
        blocks a relocation: the twin moves onto the valid row's own start.
        """
        a, video, sa, sb = await seed_segments(
            db_session, "we saw Zeta", "Quux is here"
        )
        await mark_corrected(db_session, sa, "we saw Zeta")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=7,
            end=4,
            mention_text=A_NAME,
            end_segment_id=sb,
        )
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=3,
            end=4,
            mention_text=A_NAME,
            end_segment_id=sb,
            method="user_correction",
        )

        dry = await _repair(db_session, video, dry_run=True)
        real = await _repair(db_session, video)

        await assert_mentions_ok(db_session, video)
        rows = [m for m in await positioned(db_session, video) if m.entity_id == a]
        assert [(m.match_start, m.detection_method) for m in rows] == [
            (7, "rule_match")
        ]
        assert dry == real

    async def test_a_stale_split_name_relocating_onto_a_valid_alias_start_wins_it(
        self, db_session: AsyncSession
    ) -> None:
        """A valid alias row 'Zeta' sits at 7 in the start segment; a stale split name
        at 3 relocates to 7: the same unique key as the alias row. The longer name
        keeps the key and the alias row goes.

        Mutation: treat every blocker as blocking (``if any(...)`` -> ``if
        blockers``): the shorter alias row then stops the longer name relocating.
        """
        a, video, sa, sb = await seed_segments(
            db_session, "we saw Zeta", "Quux is here"
        )
        await add_alias(db_session, a, "Zeta")
        await mark_corrected(db_session, sa, "we saw Zeta")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=7,
            end=11,
            mention_text="Zeta",
        )
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=3,
            end=4,
            mention_text=A_NAME,
            end_segment_id=sb,
        )

        dry = await _repair(db_session, video, dry_run=True)
        real = await _repair(db_session, video)

        await assert_mentions_ok(db_session, video)
        rows = [m for m in await positioned(db_session, video) if m.entity_id == a]
        assert [(r.mention_text, r.end_segment_id) for r in rows] == [(A_NAME, sb)]
        assert dry == real

    async def test_a_stale_split_name_relocating_over_an_alias_in_its_start_segment(
        self, db_session: AsyncSession
    ) -> None:
        """The alias row's start differs from where the span relocates ('Zeta' alias
        at 11 inside 'and we saw Zeta'; span stale at 7). One run settles it: the
        second changes nothing.

        Mutation: do not record a relocated span's new position (the ``placed``
        update after a move), so the overlap step never sees it over the alias row.
        """
        a, video, sa, sb = await seed_segments(db_session, "x", "Quux is here")
        await add_alias(db_session, a, "Zeta")
        await mark_corrected(db_session, sa, "and we saw Zeta")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=11,
            end=15,
            mention_text="Zeta",
        )
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=7,
            end=4,
            mention_text=A_NAME,
            end_segment_id=sb,
        )

        await _repair(db_session, video)

        await assert_mentions_ok(db_session, video)
        assert _changes(await _repair(db_session, video)) == (0, 0, 0)

    async def test_a_relocated_span_overlapping_an_alias_is_settled_in_one_run(
        self, db_session: AsyncSession
    ) -> None:
        """Regression: a stale split name relocates (no start clash) over a valid
        alias row inside its start-segment part. The first run must resolve the
        overlap; before the fix it took a second run to remove the alias.

        Mutation: do not record a relocated span's new position (the ``placed``
        update after a move), so the overlap step never sees it over the alias row.
        """
        c = await make_entity(db_session, "Zeta Quux Nine")
        await add_alias(db_session, c, "Quux")
        _a, video, s1, s2 = await seed_segments(db_session, "x", "Nine is here")
        await mark_corrected(db_session, s1, "we saw Zeta Quux")
        await place(
            db_session,
            entity_id=c,
            video_id=video,
            segment_id=s1,
            start=12,
            end=16,
            mention_text="Quux",
        )
        await place(
            db_session,
            entity_id=c,
            video_id=video,
            segment_id=s1,
            start=3,
            end=4,
            mention_text="Zeta Quux Nine",
            end_segment_id=s2,
        )

        dry = await _repair(db_session, video, dry_run=True)
        first = await _repair(db_session, video)

        assert dry == first
        desc = await assert_mentions_ok(db_session, video)
        second = await _repair(db_session, video)
        assert _changes(second) == (0, 0, 0), (first, second, desc)
        rows = [m for m in await positioned(db_session, video) if m.entity_id == c]
        assert [(r.mention_text, r.match_start) for r in rows] == [
            ("Zeta Quux Nine", 7)
        ]


class TestRepairScope:
    async def test_two_entities_with_overlapping_names_are_both_kept(
        self, db_session: AsyncSession
    ) -> None:
        """Only one entity's own rows compete: another entity's row inside a name is
        not a duplicate of it.

        Mutation: compare mentions across entities in the overlap step.
        """
        c = await make_entity(db_session, "Quux")
        a, video, sa, _sb = await seed_segments(db_session, "x")
        await mark_corrected(db_session, sa, f"we saw {A_NAME} here")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=7,
            mention_text=A_NAME,
        )
        await place(
            db_session,
            entity_id=c,
            video_id=video,
            segment_id=sa,
            start=12,
            mention_text="Quux",
            method="user_correction",
        )
        before = await snapshot(db_session, video)

        report = await _repair(db_session, video)

        assert await snapshot(db_session, video) == before
        assert report["duplicates_removed"] == 0

    async def test_a_stale_row_may_move_into_another_entitys_name(
        self, db_session: AsyncSession
    ) -> None:
        """A stale C row; the only C-text is inside A's valid name. C moves there
        (another entity's row never blocks), and A is untouched."""
        c = await make_entity(db_session, "Quux")
        a, video, sa, _sb = await seed_segments(db_session, "x")
        await mark_corrected(db_session, sa, f"we saw {A_NAME} here")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=7,
            mention_text=A_NAME,
        )
        await place(
            db_session,
            entity_id=c,
            video_id=video,
            segment_id=sa,
            start=0,
            mention_text="Quux",
            method="user_correction",
        )

        await _repair(db_session, video)

        rows = sorted(
            (m.mention_text, m.match_start) for m in await positioned(db_session, video)
        )
        assert rows == [("Quux", 12), (A_NAME, 7)]

    async def test_unpositioned_and_title_rows_are_untouched(
        self, db_session: AsyncSession
    ) -> None:
        a, video, sa, _sb = await seed_segments(db_session, "x")
        await mark_corrected(db_session, sa, f"we all saw {A_NAME} here")
        await seed_title_mention(db_session, entity_id=a, video_id=video)
        # A transcript row with NULL offsets in the corrected segment.
        await seed_mention(
            db_session,
            entity_id=a,
            video_id=video,
            language_code="en",
            segment_id=sa,
        )
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=7,
            mention_text=A_NAME,
            method="user_correction",
        )

        async def _unpositioned() -> list[tuple[object, ...]]:
            rows = (
                await db_session.execute(
                    select(EntityMentionDB)
                    .where(
                        EntityMentionDB.video_id == video,
                        EntityMentionDB.entity_id == a,
                    )
                    .execution_options(populate_existing=True)
                )
            ).scalars()
            return sorted(
                (str(m.id), m.mention_source, m.segment_id, m.match_start)
                for m in rows
                if m.match_start is None
            )

        before = await _unpositioned()
        assert len(before) == 2, "a title row and an unpositioned transcript row"

        await _repair(db_session, video)

        assert await _unpositioned() == before
        await assert_mentions_ok(db_session, video)

    async def test_a_segment_that_ends_one_span_and_starts_another(
        self, db_session: AsyncSession
    ) -> None:
        a, video, s1, s2 = await seed_segments(
            db_session, "we saw Zeta", "Quux met Zeta"
        )
        s3 = await seed_segment(db_session, video, "en", 18.0, 2)
        await set_text(db_session, s3, "Quux again")
        await add_alias(db_session, a, "Quux")
        await mark_corrected(db_session, s2, "Quux met Zeta")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=s1,
            start=7,
            end=4,
            mention_text=A_NAME,
            end_segment_id=s2,
        )
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=s2,
            start=9,
            end=4,
            mention_text=A_NAME,
            end_segment_id=s3,
        )
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=s2,
            start=0,
            end=4,
            mention_text="Quux",
        )
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=s3,
            start=0,
            end=4,
            mention_text="Quux",
        )

        dry = await _repair(db_session, video, dry_run=True)
        real = await _repair(db_session, video)

        await assert_mentions_ok(db_session, video)
        rows = sorted(
            (m.segment_id, m.end_segment_id, m.mention_text)
            for m in await positioned(db_session, video)
            if m.entity_id == a
        )
        assert rows == [(s1, s2, A_NAME), (s2, s3, A_NAME)]
        assert dry == real

    async def test_a_stale_three_segment_span_relocates(
        self, db_session: AsyncSession
    ) -> None:
        c, video, s1, _s2, s3 = await seed_three_segment_world(db_session)
        await mark_corrected(db_session, s1, "and we saw Zeta")
        await place(
            db_session,
            entity_id=c,
            video_id=video,
            segment_id=s1,
            start=7,
            end=4,
            mention_text="Zeta Quux Nine",
            end_segment_id=s3,
        )

        await _repair(db_session, video)

        await assert_mentions_ok(db_session, video)
        rows = [m for m in await positioned(db_session, video) if m.entity_id == c]
        assert [(r.match_start, r.match_end) for r in rows] == [(11, 4)]

    async def test_a_corrected_middle_segment_of_a_three_segment_span_is_repaired(
        self, db_session: AsyncSession
    ) -> None:
        """Regression: the middle segment was corrected before #426, so the name no
        longer runs across all three. Neither the start nor the end segment is
        corrected, so a candidate query that looks only at those never finds the row.
        The name is gone, so the row is removed.

        Mutation: drop the corrected-middle-segment arm of
        ``mention_repair_candidates``.
        """
        c, video, s1, s2, s3 = await seed_three_segment_world(db_session)
        await mark_corrected(db_session, s2, "Blah")
        await place(
            db_session,
            entity_id=c,
            video_id=video,
            segment_id=s1,
            start=7,
            end=4,
            mention_text="Zeta Quux Nine",
            end_segment_id=s3,
        )

        report = await _repair(db_session, video)

        await assert_mentions_ok(db_session, video)
        assert [
            m for m in await positioned(db_session, video) if m.entity_id == c
        ] == []
        assert _changes(report) == (0, 1, 0)

    async def test_the_nearest_uncovered_occurrence_takes_a_stale_correction_row(
        self, db_session: AsyncSession
    ) -> None:
        """A stale correction row; the occurrence it was about is recorded by a scan
        row; the nearest free occurrence is the other one, so it moves there."""
        a, video, sa, _ = await seed_segments(db_session, "x")
        await mark_corrected(db_session, sa, f"we saw {A_NAME} and {A_NAME}")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=7,
            mention_text=A_NAME,
        )
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=3,
            mention_text=A_NAME,
            method="user_correction",
        )

        await _repair(db_session, video)

        rows = sorted(
            (m.match_start, m.detection_method)
            for m in await positioned(db_session, video)
            if m.entity_id == a
        )
        assert rows == [(7, "rule_match"), (21, "user_correction")]


async def _two_videos_with_a_stale_row_each(
    session: AsyncSession,
) -> tuple[World, World]:
    """The same entity has a stale correction row in two videos."""
    first = await seed_world(session, a_mentioned=False, a_segment_text="x")
    other = new_video_id()
    await seed_video(session, other, ("en",))
    seg_a = await seed_segment(session, other, "en", 10.0, 0)
    seg_b = await seed_segment(session, other, "en", 14.0, 1)
    await seed_mention(
        session,
        entity_id=first.b,
        video_id=other,
        language_code="en",
        segment_id=seg_b,
    )
    second = World(
        video_id=other,
        languages=("en",),
        a=first.a,
        b=first.b,
        seg_a={"en": seg_a},
        seg_b={"en": seg_b},
    )
    for world in (first, second):
        await mark_corrected(session, world.seg_a["en"], f"we all saw {A_NAME} here")
        await place(
            session,
            entity_id=world.a,
            video_id=world.video_id,
            segment_id=world.seg_a["en"],
            start=7,
            mention_text=A_NAME,
            method="user_correction",
        )
    return first, second


class TestVideoScoping:
    async def test_repairing_one_video_leaves_the_other_alone(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only the named video's rows move, only its transcript is counted, and only
        its proximity scope is invalidated.

        Mutation: ignore ``video_ids`` in ``mention_repair_candidates``.
        """
        first, second = await _two_videos_with_a_stale_row_each(db_session)
        await db_session.commit()
        for world in (first, second):
            await settle(db_session, monkeypatch, world)
        untouched = await snapshot(db_session, second.video_id)

        report = await _repair(db_session, first.video_id)

        assert report["transcripts_examined"] == 1
        assert report["stale_moved"] == 1
        assert await snapshot(db_session, second.video_id) == untouched
        assert is_current(await scope_state(db_session, second.video_id))
        assert not is_current(await scope_state(db_session, first.video_id))

    async def test_no_video_filter_repairs_every_video(
        self, db_session: AsyncSession
    ) -> None:
        """``video_ids=None`` is the whole library, not none of it."""
        first, second = await _two_videos_with_a_stale_row_each(db_session)

        report = await MentionRepairService().repair(
            db_session, video_ids=None, dry_run=False
        )

        assert report.transcripts_examined == 2
        for world in (first, second):
            assert await _rows(db_session, world.a) == [
                ("user_correction", A_NAME, 11, 20),
                ("user_correction", A_NAME, 11, 20),
            ]


class TestNoOp:
    async def test_a_library_with_nothing_to_repair_writes_nothing(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Repair of correct rows changes no row, recounts no entity, and leaves the
        proximity scope CURRENT (a spurious invalidation would force a recompute of
        every repaired library).

        Mutation: invalidate the scope (or count the entity) before checking the plan
        has any change.
        """
        world = await seed_world(db_session, a_mentioned=False, a_segment_text="x")
        await mark_corrected(db_session, world.seg_a["en"], f"we saw {A_NAME} here")
        await place(
            db_session,
            entity_id=world.a,
            video_id=world.video_id,
            segment_id=world.seg_a["en"],
            start=7,
            mention_text=A_NAME,
            method="user_correction",
        )
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        before = await snapshot(db_session, world.video_id)

        report = await _repair(db_session, world.video_id)

        assert report["entities_changed"] == 0
        assert report["scopes_invalidated"] == 0
        assert await snapshot(db_session, world.video_id) == before
        assert is_current(await scope_state(db_session, world.video_id))


class TestRunningIt:
    async def test_a_dry_run_reports_and_writes_nothing(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg = await _corrected_world(db_session, f"we all saw {A_NAME} here")
        for start, method in ((7, "user_correction"), (11, "rule_match")):
            await place(
                db_session,
                entity_id=a,
                video_id=video,
                segment_id=seg,
                mention_text=A_NAME,
                start=start,
                method=method,
            )
        before = await _rows(db_session, a)

        report = await MentionRepairService().repair(
            db_session, video_ids=[video], dry_run=True
        )

        assert report.stale_removed == 1
        assert await _rows(db_session, a) == before

    async def test_a_second_run_changes_nothing(self, db_session: AsyncSession) -> None:
        a, video, seg = await _corrected_world(db_session, f"we all saw {A_NAME} here")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg,
            mention_text=A_NAME,
            start=7,
            method="user_correction",
        )
        service = MentionRepairService()
        await service.repair(db_session, video_ids=[video], dry_run=False)
        after_first = await _rows(db_session, a)

        second = await service.repair(db_session, video_ids=[video], dry_run=False)

        assert await _rows(db_session, a) == after_first
        assert (
            second.stale_moved,
            second.stale_removed,
            second.duplicates_removed,
        ) == (0, 0, 0)

    async def test_counters_are_recomputed_and_proximity_is_marked_stale(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = await seed_world(
            db_session,
            a_mentioned=False,
            a_segment_text="(original words)",
            b_segment_text=f"then {B_NAME} replied",
        )
        a, video, seg = world.a, world.video_id, world.seg_a["en"]
        await mark_corrected(db_session, seg, f"we all saw {A_NAME} here")
        for method, start in (("user_correction", 7), ("rule_match", 11)):
            await place(
                db_session,
                entity_id=a,
                video_id=video,
                segment_id=seg,
                mention_text=A_NAME,
                start=start,
                method=method,
            )
        entity = (
            await db_session.execute(select(NamedEntityDB).where(NamedEntityDB.id == a))
        ).scalar_one()
        entity.mention_count = 2
        await db_session.commit()
        await settle(db_session, monkeypatch, world)

        await MentionRepairService().repair(
            db_session, video_ids=[video], dry_run=False
        )

        count = (
            await db_session.execute(
                select(NamedEntityDB.mention_count)
                .where(NamedEntityDB.id == a)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert count == 1
        assert not is_current(await scope_state(db_session, video))

    async def _seed_every_kind_of_repair(self, session: AsyncSession) -> World:
        """One transcript, three entities, one of each repair the report counts.

        - A: a stale correction row with no twin: it MOVES (``stale_moved``);
        - B: a stale correction row beside a valid scan row of the same name: it is
          REMOVED (``stale_removed``);
        - C: the full name and, inside it, an alias row: the alias is a DUPLICATE
          (``duplicates_removed``).
        """
        world = await seed_world(session, a_mentioned=False, a_segment_text="x")
        a, b = world.a, world.b
        c = await make_entity(session, "Wexford Plinth")
        await add_alias(session, c, "Plinth")
        seg_a, seg_b = world.seg_a["en"], world.seg_b["en"]
        seg_c = await seed_segment(session, world.video_id, "en", 18.0, 2)
        await mark_corrected(session, seg_a, f"we all saw {A_NAME} here")
        await mark_corrected(session, seg_b, f"we saw {B_NAME} here")
        await mark_corrected(session, seg_c, "we saw Wexford Plinth here")
        video = world.video_id
        await place(
            session,
            entity_id=a,
            video_id=video,
            segment_id=seg_a,
            start=7,
            mention_text=A_NAME,
            method="user_correction",
        )
        await place(
            session,
            entity_id=b,
            video_id=video,
            segment_id=seg_b,
            start=7,
            mention_text=B_NAME,
        )
        await place(
            session,
            entity_id=b,
            video_id=video,
            segment_id=seg_b,
            start=0,
            mention_text=B_NAME,
            method="user_correction",
        )
        await place(
            session,
            entity_id=c,
            video_id=video,
            segment_id=seg_c,
            start=7,
            mention_text="Wexford Plinth",
        )
        await place(
            session,
            entity_id=c,
            video_id=video,
            segment_id=seg_c,
            start=15,
            mention_text="Plinth",
            method="user_correction",
        )
        return world

    async def test_a_dry_run_report_equals_the_real_runs_field_by_field(
        self, db_session: AsyncSession
    ) -> None:
        """The preview an operator reads before the real run must be what the real
        run then does, for each kind of repair at once. The seed is one transcript
        with a stale move, a stale removal and a duplicate, so no field is zero.

        Mutation: count a repair kind only on the real path (or skip the plan's
        counting under ``dry_run``), or let the real run's overlap step change a count
        the plan did not.
        """
        world = await self._seed_every_kind_of_repair(db_session)
        before = await snapshot(db_session, world.video_id)

        dry = await _repair(db_session, world.video_id, dry_run=True)

        assert await snapshot(db_session, world.video_id) == before, "dry run wrote"
        assert dry == {
            "transcripts_examined": 1,
            "stale_moved": 1,
            "stale_removed": 1,
            "duplicates_removed": 1,
            "entities_changed": 3,
            "scopes_invalidated": 1,
        }

        real = await _repair(db_session, world.video_id)

        assert real == dry
        assert await snapshot(db_session, world.video_id) != before, "real run wrote"
        await assert_mentions_ok(db_session, world.video_id)
        assert _changes(await _repair(db_session, world.video_id)) == (0, 0, 0)

    async def test_a_mixed_library_repairs_idempotently_and_a_full_scan_agrees(
        self, db_session: AsyncSession
    ) -> None:
        """Dry run equals real run, a second run is a no-op, and ``scan --full``,
        repair and ``scan --full`` again converge on one set of rows."""
        a, video, sa, sb = await seed_segments(db_session, "x", "Quux is here")
        await add_alias(db_session, a, "Quux")
        await mark_corrected(db_session, sa, f"so {A_NAME} and Zeta")
        # A stale single correction (twin of the scan row at 3).
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=0,
            end=9,
            mention_text=A_NAME,
            method="user_correction",
        )
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=3,
            end=12,
            mention_text=A_NAME,
        )
        # An alias fragment inside the scan row.
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=8,
            end=12,
            mention_text="Quux",
            method="user_correction",
        )
        # A stale split name (was at 13, the text now has 'Zeta' at 17).
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=13,
            end=4,
            mention_text=A_NAME,
            end_segment_id=sb,
        )
        # An alias in the end segment, inside the split name.
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sb,
            start=0,
            end=4,
            mention_text="Quux",
        )

        dry = await _repair(db_session, video, dry_run=True)
        real = await _repair(db_session, video)

        assert dry == real, (dry, real)
        desc = await assert_mentions_ok(db_session, video)
        settled = await snapshot(db_session, video)
        assert _changes(await _repair(db_session, video)) == (0, 0, 0), desc
        assert await snapshot(db_session, video) == settled

        await scan(db_session, video, [a], full=True)
        await assert_mentions_ok(db_session, video)
        after_full = await snapshot(db_session, video)
        await _repair(db_session, video)
        await scan(db_session, video, [a], full=True)
        assert await snapshot(db_session, video) == after_full

    async def test_full_scan_repair_full_scan_converges_after_corrections(
        self, db_session: AsyncSession
    ) -> None:
        a, video, sa, _sb = await seed_segments(
            db_session, f"{GARBLE} and {GARBLE}", "then Zeta"
        )
        s3 = await seed_segment(db_session, video, "en", 18.0, 2)
        await set_text(db_session, s3, "Quuks again")
        await add_alias(db_session, a, "Quux")
        await correct(db_session, sa, "Quuks", "Quux", entity_id=a)
        await correct(db_session, s3, GARBLE, A_NAME, entity_id=a, cross_segment=True)
        await assert_mentions_ok(db_session, video)
        await scan(db_session, video, [a], full=True)
        await assert_mentions_ok(db_session, video)
        first = await snapshot(db_session, video)

        await _repair(db_session, video)
        await scan(db_session, video, [a], full=True)

        assert await snapshot(db_session, video) == first

    async def test_a_repair_after_edits_through_the_write_paths_finds_nothing(
        self, db_session: AsyncSession
    ) -> None:
        """Rows written by the fixed write paths need no repair: the repair is for
        what was written before them."""
        a, video, seg, _ = await seed_segments(db_session, f"we saw {A_NAME} here")
        await scan(db_session, video, [a], full=False)
        await apply_text(db_session, video, seg, f"so we all saw {A_NAME} here")

        report = await _repair(db_session, video)

        assert _changes(report) == (0, 0, 0)


class TestRepairCommand:
    """``chronovista entities repair-mentions``, parsed by Typer, over the same
    session. The command rolls a dry run back itself, so the seed is committed first
    (a rollback would otherwise erase the seed and prove nothing)."""

    async def _seed_stale_row(
        self, session: AsyncSession
    ) -> tuple[uuid.UUID, str, int]:
        a, video, seg = await _corrected_world(session, f"we all saw {A_NAME} here")
        await place(
            session,
            entity_id=a,
            video_id=video,
            segment_id=seg,
            mention_text=A_NAME,
            start=7,
            method="user_correction",
        )
        await session.commit()
        return a, video, seg

    async def test_dry_run_writes_nothing_and_prints_the_counts(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Mutation: make the command pass ``dry_run=False`` regardless of the flag
        (the stale row would move), or drop the dry-run banner/the counts panel.
        """
        a, _video, _seg = await self._seed_stale_row(db_session)

        await invoke_cli(monkeypatch, db_session, ["repair-mentions", "--dry-run"])

        out = capsys.readouterr().out
        assert "dry run" in out.lower()
        assert re.search(r"Transcripts examined:\s*1\b", out), out
        assert re.search(r"Stale mentions moved to their words:\s*1\b", out), out
        assert await _rows(db_session, a) == [("user_correction", A_NAME, 7, 16)]

    async def test_a_real_run_repairs_and_prints_the_counts(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Mutation: make the command always run as a dry run."""
        a, _video, _seg = await self._seed_stale_row(db_session)

        await invoke_cli(monkeypatch, db_session, ["repair-mentions"])

        out = capsys.readouterr().out
        assert "dry run" not in out.lower()
        assert re.search(r"Stale mentions moved to their words:\s*1\b", out), out
        assert await _rows(db_session, a) == [("user_correction", A_NAME, 11, 20)]

    async def test_video_id_limits_the_repair_to_that_video(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Two videos each hold one stale row; ``--video-id`` names one.

        Mutation: drop ``video_ids=video_ids`` from the command's call to the
        service (both rows would move and the count would read 2).
        """
        first, second = await _two_videos_with_a_stale_row_each(db_session)
        await db_session.commit()

        await invoke_cli(
            monkeypatch, db_session, ["repair-mentions", "--video-id", first.video_id]
        )

        out = capsys.readouterr().out
        assert re.search(r"Transcripts examined:\s*1\b", out), out
        by_video = {
            m.video_id: m.match_start
            for m in await positioned(db_session, first.video_id)
            + await positioned(db_session, second.video_id)
        }
        assert by_video == {first.video_id: 11, second.video_id: 7}
