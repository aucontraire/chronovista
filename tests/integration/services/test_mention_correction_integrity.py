"""Corrections keep mention offsets true and never duplicate a mention (#426).

Drives the real entry points (``BatchCorrectionService.apply_to_segments``,
``TranscriptCorrectionService.apply_correction`` / ``revert_correction`` and
``EntityMentionScanService.scan``) against the integration database. Before the fix,
every scenario here except the plain-scan controls failed:

- corrections never moved existing mentions with the text (stale offsets);
- a correction recorded only the replaced fragment of a name;
- duplicates were caught only when two rows started on the same character, so
  ``scan --full`` (and the correction writer) wrote a second mention of one
  occurrence whenever the first had stale offsets or a fragment span.

Invariants checked on every scenario: every positioned mention's offsets read as its
``mention_text``, no entity has two overlapping mentions, and one spoken occurrence of
an entity's name is one mention. Placeholder names only.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.enums import CorrectionType
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from chronovista.services.entity_mention_scan_service import EntityMentionScanService
from tests.factories.mention_world import (
    A_NAME,
    B_NAME,
    GARBLE,
    GARBLED_SURNAME,
    SURNAME,
    add_alias,
    add_asr_form,
    apply_text,
    assert_mentions_ok,
    batch_service,
    correct,
    correction_service,
    count_of,
    describe,
    effective_text,
    make_entity,
    mention_report,
    mentions,
    new_batch_id,
    place,
    positioned,
    scan,
    seed_segments,
    seed_three_segment_world,
    seed_world,
    set_text,
    snapshot,
    text_index,
)
from tests.factories.proximity_seed import seed_mention, seed_segment

pytestmark = pytest.mark.asyncio


def _all_read_true(text: str, rows: list[EntityMentionDB]) -> bool:
    return all(
        m.match_start is not None
        and m.match_end is not None
        and text[m.match_start : m.match_end].casefold() == m.mention_text.casefold()
        for m in rows
    )


# ---------------------------------------------------------------------------
# 1. A correction moves mentions with the text
# ---------------------------------------------------------------------------


class TestOffsetsFollowTheText:
    async def test_a_correction_mention_moves_with_a_later_edit_before_it(
        self, db_session: AsyncSession
    ) -> None:
        a, _video, seg, _ = await seed_segments(db_session, f"we saw {GARBLE} here")
        await correct(db_session, seg, GARBLE, A_NAME, entity_id=a)
        await correct(db_session, seg, "we saw", "we all saw")  # +4 chars, no entity

        text = await effective_text(db_session, seg)
        rows = await mentions(db_session, a, seg)
        assert len(rows) == 1 and _all_read_true(text, rows), describe(text, rows)

    async def test_a_scan_mention_moves_with_an_edit_before_it(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(db_session, f"we saw {A_NAME} here")
        await scan(db_session, video, [a], full=False)
        await correct(db_session, seg, "we saw", "we all saw")

        text = await effective_text(db_session, seg)
        rows = await mentions(db_session, a, seg)
        assert len(rows) == 1 and _all_read_true(text, rows), describe(text, rows)

    async def test_a_revert_moves_the_mention_back(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(db_session, f"we saw {A_NAME} here")
        await scan(db_session, video, [a], full=False)
        await correct(db_session, seg, "we saw", "we all saw")

        await correction_service().revert_correction(db_session, segment_id=seg)

        text = await effective_text(db_session, seg)
        rows = await mentions(db_session, a, seg)
        assert text == f"we saw {A_NAME} here"
        assert [(m.match_start, m.match_end) for m in rows] == [(7, 16)], describe(
            text, rows
        )

    async def test_an_already_stale_mention_is_left_for_a_deliberate_repair(
        self, db_session: AsyncSession
    ) -> None:
        """A correction never silently deletes a row that was wrong before it."""
        a, video, seg, _ = await seed_segments(db_session, f"we saw {A_NAME} here")
        await seed_mention(
            db_session,
            entity_id=a,
            video_id=video,
            language_code="en",
            segment_id=seg,
            match_start=0,
            match_end=9,  # reads "we saw Ze", not the name
        )
        await correct(db_session, seg, "here", "there")

        rows = await mentions(db_session, a, seg)
        assert [(m.match_start, m.match_end) for m in rows] == [(0, 9)]


# ---------------------------------------------------------------------------
# 2. One occurrence, one mention
# ---------------------------------------------------------------------------


class TestOneOccurrenceOneMention:
    @pytest.mark.parametrize("full", [False, True], ids=["scan", "full-rescan"])
    async def test_a_scan_after_a_shifted_correction_adds_no_second_mention(
        self, db_session: AsyncSession, full: bool
    ) -> None:
        """The 165-row production shape: a stale correction mention plus a scan twin."""
        a, video, seg, _ = await seed_segments(db_session, f"we saw {GARBLE} here")
        await correct(db_session, seg, GARBLE, A_NAME, entity_id=a)
        await correct(db_session, seg, "we saw", "we all saw")
        await scan(db_session, video, [a], full=full)

        text = await effective_text(db_session, seg)
        rows = await mentions(db_session, a, seg)
        assert len(rows) == 1 and _all_read_true(text, rows), describe(text, rows)

    @pytest.mark.parametrize("full", [False, True], ids=["scan", "full-rescan"])
    async def test_a_surname_correction_records_the_whole_name_once(
        self, db_session: AsyncSession, full: bool
    ) -> None:
        """The 160-row production shape: a fragment correction, then a full-name scan."""
        a, video, seg, _ = await seed_segments(db_session, f"we saw {GARBLE} here")
        await add_alias(db_session, a, SURNAME)  # the fragment is a visible name
        await correct(db_session, seg, GARBLED_SURNAME, SURNAME, entity_id=a)

        text = await effective_text(db_session, seg)
        rows = await mentions(db_session, a, seg)
        assert [m.mention_text for m in rows] == [A_NAME], describe(text, rows)

        await scan(db_session, video, [a], full=full)
        rows = await mentions(db_session, a, seg)
        assert len(rows) == 1 and _all_read_true(text, rows), describe(text, rows)

    async def test_a_correction_over_a_scanned_name_shifts_it_and_tags_only_new_ones(
        self, db_session: AsyncSession
    ) -> None:
        """The issue's own order: a scan, then an entity-tagged correction that both
        shifts the scanned mention and re-tags the same name."""
        a, video, seg, _ = await seed_segments(
            db_session, f"{GARBLE} met {A_NAME} today"
        )
        await add_alias(db_session, a, SURNAME)
        await scan(db_session, video, [a], full=False)
        assert len(await mentions(db_session, a, seg)) == 1

        # Fixing the first (garbled) surname shortens the text before the scanned
        # mention, and its replacement also occurs inside that mention.
        await correct(db_session, seg, GARBLED_SURNAME, SURNAME, entity_id=a)

        text = await effective_text(db_session, seg)
        rows = await mentions(db_session, a, seg)
        assert text == f"{A_NAME} met {A_NAME} today"
        assert len(rows) == 2 and _all_read_true(text, rows), describe(text, rows)
        assert [m.match_start for m in rows] == [0, text.rindex(A_NAME)]

    async def test_a_full_rescan_does_not_duplicate_a_fragment_across_segments(
        self, db_session: AsyncSession
    ) -> None:
        """The cross-segment pass: the name runs across a boundary and only its second
        half was corrected, so the correction mention sits in the second segment."""
        world = await seed_world(
            db_session,
            a_mentioned=False,
            a_segment_text="we saw Zeta",
            b_segment_text=f"{GARBLED_SURNAME} is here",
        )
        a, seg_b = world.a, world.seg_b["en"]
        b_far = await seed_segment(db_session, world.video_id, "en", 18.0, 2)
        await set_text(db_session, b_far, f"then {B_NAME} replied")
        await db_session.execute(
            update(EntityMentionDB)
            .where(EntityMentionDB.entity_id == world.b)
            .values(segment_id=b_far)
        )
        await add_alias(db_session, a, SURNAME)
        await correct(db_session, seg_b, GARBLED_SURNAME, SURNAME, entity_id=a)

        await scan(db_session, world.video_id, [a], full=True)

        all_a = list(
            (
                await db_session.execute(
                    select(EntityMentionDB).where(EntityMentionDB.entity_id == a)
                )
            )
            .scalars()
            .all()
        )
        assert len(all_a) == 1, [
            (m.detection_method, m.mention_text, m.segment_id, m.end_segment_id)
            for m in all_a
        ]


class TestRowsWrittenBeforeTheFix:
    """Rows that do not line up with a scan match (fragments, stale offsets) exist in
    production. A new writer must not duplicate them either."""

    async def _seed_legacy_fragment(
        self, session: AsyncSession, entity_id: uuid.UUID, video_id: str, segment: int
    ) -> None:
        """A ``user_correction`` written before #426: only the corrected surname,
        inside a whole name that a scan matches from an earlier character."""
        text = await effective_text(session, segment)
        await seed_mention(
            session,
            entity_id=entity_id,
            video_id=video_id,
            language_code="en",
            segment_id=segment,
            mention_text=SURNAME,
            detection_method="user_correction",
            match_start=text.index(A_NAME) + len(A_NAME) - len(SURNAME),
        )

    async def test_a_full_rescan_does_not_duplicate_a_legacy_fragment(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(db_session, f"we saw {A_NAME} here")
        await add_alias(db_session, a, SURNAME)
        await self._seed_legacy_fragment(db_session, a, video, seg)

        await scan(db_session, video, [a], full=True)

        text = await effective_text(db_session, seg)
        rows = await mentions(db_session, a, seg)
        assert len(rows) == 1, describe(text, rows)

    async def test_a_correction_does_not_duplicate_a_legacy_fragment(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(
            db_session, f"we saw {A_NAME} and {GARBLE}"
        )
        await add_alias(db_session, a, SURNAME)
        await self._seed_legacy_fragment(db_session, a, video, seg)

        # The replacement also occurs inside the already-recorded name.
        await correct(db_session, seg, GARBLED_SURNAME, SURNAME, entity_id=a)

        text = await effective_text(db_session, seg)
        rows = await mentions(db_session, a, seg)
        assert text == f"we saw {A_NAME} and {A_NAME}"
        assert len(rows) == 2, describe(text, rows)
        assert [m.match_start for m in rows] == [
            text.index(A_NAME) + len(A_NAME) - len(SURNAME),
            text.rindex(A_NAME),
        ], describe(text, rows)


class TestRemovalAndMoveInOneEdit:
    async def test_a_mention_can_move_onto_the_start_of_one_the_edit_removed(
        self, db_session: AsyncSession
    ) -> None:
        """Deleting the first of two mentions shifts the second onto its old start.
        The removed row must be gone before the move, or the unique index on
        ``(entity_id, segment_id, match_start)`` rejects the moved row."""
        first, second = A_NAME.split(" ")
        a, video, seg, _ = await seed_segments(db_session, A_NAME)
        await add_alias(db_session, a, first)
        await add_alias(db_session, a, second)
        for text, start in ((first, 0), (second, len(first) + 1)):
            await seed_mention(
                db_session,
                entity_id=a,
                video_id=video,
                language_code="en",
                segment_id=seg,
                mention_text=text,
                match_start=start,
            )

        await correction_service().apply_correction(
            db_session,
            video_id=video,
            language_code="en",
            segment_id=seg,
            corrected_text=second,
            correction_type=CorrectionType.PROPER_NOUN,
        )

        rows = await mentions(db_session, a, seg)
        assert [(m.mention_text, m.match_start, m.match_end) for m in rows] == [
            (second, 0, len(second))
        ]


# ---------------------------------------------------------------------------
# 3. Fixing a misheard name keeps the mention
# ---------------------------------------------------------------------------


class TestFixingAMisheardName:
    async def test_the_misheard_forms_mention_is_kept_as_the_name(
        self, db_session: AsyncSession
    ) -> None:
        """The most common correction replaces exactly the words a recovered
        ``asr_match`` recorded. The entity is still said there, now correctly, so
        the mention stays: re-pointed to the name, as a scan would record it."""
        start = len("we saw ")
        world = await seed_world(
            db_session,
            a_mention_text=GARBLE,
            a_detection="asr_match",
            a_segment_text=f"we saw {GARBLE} here",
            b_segment_text=f"then {B_NAME} replied",
            a_match_start=start,
        )
        a, seg = world.a, world.seg_a["en"]

        await correct(db_session, seg, GARBLE, A_NAME)  # no entity tagged

        text = await effective_text(db_session, seg)
        rows = await mentions(db_session, a, seg)
        assert [(m.detection_method, m.mention_text, m.match_start) for m in rows] == [
            ("rule_match", A_NAME, start)
        ], describe(text, rows)

    async def test_fixing_the_misheard_half_of_a_split_name_keeps_a_mention(
        self, db_session: AsyncSession
    ) -> None:
        """Regression (#426 review): the misheard name is split over two segments and
        the fix rewrites only the second. The span still reads as the name once
        re-pointed, so the entity keeps one mention, now as the name.

        Mutation: in ``_rebase_spanning``, return ``("kept", None, None)`` (remove)
        for a scan-owned split name whose words were rewritten, instead of re-pointing
        it to what the scan finds.
        """
        a, video, _sa, sb = await seed_segments(
            db_session, "we saw Zeta", "Quuks is here"
        )
        await add_asr_form(db_session, a, GARBLE)
        await scan(db_session, video, [a], full=False)
        rows = [m for m in await positioned(db_session, video) if m.entity_id == a]
        assert [(r.detection_method, r.end_segment_id) for r in rows] == [
            ("asr_match", sb)
        ]

        await apply_text(db_session, video, sb, "Quux is here")

        desc = await assert_mentions_ok(db_session, video)
        rows = [m for m in await positioned(db_session, video) if m.entity_id == a]
        assert [(r.detection_method, r.mention_text) for r in rows] == [
            ("rule_match", A_NAME)
        ], desc

    async def test_a_plain_scan_after_fixing_a_misheard_split_name_changes_nothing(
        self, db_session: AsyncSession
    ) -> None:
        a, video, _sa, sb = await seed_segments(
            db_session, "we saw Zeta", "Quuks is here"
        )
        await add_asr_form(db_session, a, GARBLE)
        await scan(db_session, video, [a], full=False)
        await apply_text(db_session, video, sb, "Quux is here")
        before = await snapshot(db_session, video)

        await scan(db_session, video, [a], full=False)

        await assert_mentions_ok(db_session, video)
        assert await snapshot(db_session, video) == before
        rows = [m for m in await positioned(db_session, video) if m.entity_id == a]
        assert [(r.detection_method, r.mention_text) for r in rows] == [
            ("rule_match", A_NAME)
        ]

    async def test_an_asr_form_round_trips_through_correction_and_revert(
        self, db_session: AsyncSession
    ) -> None:
        """Fixing the registered mishearing re-points the mention to the name; the
        revert puts the misheard form back, at its own offsets."""
        a, video, seg, _ = await seed_segments(db_session, f"we saw {GARBLE} here")
        await add_asr_form(db_session, a, GARBLE)
        await scan(db_session, video, [a], full=False)
        rows = [m for m in await positioned(db_session, video) if m.entity_id == a]
        assert [(r.detection_method, r.mention_text) for r in rows] == [
            ("asr_match", GARBLE)
        ]

        await apply_text(db_session, video, seg, f"we saw {A_NAME} here")
        rows = [m for m in await positioned(db_session, video) if m.entity_id == a]
        assert [(r.detection_method, r.mention_text) for r in rows] == [
            ("rule_match", A_NAME)
        ]

        await correction_service().revert_correction(db_session, segment_id=seg)
        await assert_mentions_ok(db_session, video)
        rows = [m for m in await positioned(db_session, video) if m.entity_id == a]
        assert [(r.detection_method, r.mention_text, r.match_start) for r in rows] == [
            ("asr_match", GARBLE, 7)
        ]


# ---------------------------------------------------------------------------
# 4. Edits that extend a recorded name into a longer word
# ---------------------------------------------------------------------------


class TestWordExtension:
    @pytest.mark.parametrize(
        ("pattern", "replacement"),
        [("Quux", "Quuxley"), ("Zeta", "BZeta")],
        ids=["suffix", "prefix"],
    )
    async def test_a_name_glued_to_a_longer_word_is_not_kept_and_rescan_agrees(
        self, db_session: AsyncSession, pattern: str, replacement: str
    ) -> None:
        """'Zeta Quux' corrected to 'Zeta Quuxley' (a different, longer name): the
        rebase must not keep the row, and after it ``--full`` must be a no-op, so the
        rebase and the scanner agree on what a mention is."""
        a, video, seg, _ = await seed_segments(db_session, f"we saw {A_NAME} here")
        await scan(db_session, video, [a], full=False)
        assert await count_of(db_session, a, video) == 1

        await correct(db_session, seg, pattern, replacement)

        await assert_mentions_ok(db_session, video)
        before = await snapshot(db_session, video)
        await scan(db_session, video, [a], full=True)
        assert await snapshot(db_session, video) == before


# ---------------------------------------------------------------------------
# 5. Cross-segment mentions
# ---------------------------------------------------------------------------


async def _spanning_world(
    session: AsyncSession, a_text: str = "we saw Zeta", b_text: str = "Quux is here"
) -> tuple[uuid.UUID, str, int, int]:
    return await seed_segments(session, a_text, b_text)


class TestCrossSegment:
    async def test_scan_creates_one_spanning_mention(
        self, db_session: AsyncSession
    ) -> None:
        a, video, _sa, _sb = await _spanning_world(db_session)
        await scan(db_session, video, [a], full=False)
        desc = await assert_mentions_ok(db_session, video)
        rows = await positioned(db_session, video)
        assert len([m for m in rows if m.entity_id == a]) == 1, desc
        assert rows[0].end_segment_id is not None, desc

    @pytest.mark.parametrize(
        ("edited", "new_text"),
        [
            ("start", "we saw Z"),
            ("end", "ux is here"),
            ("end", "Quuxley is here"),
            ("end", f"{A_NAME} is here"),
        ],
        ids=[
            "start-truncated",
            "end-head-truncated",
            "end-head-extended",
            "end-gets-the-whole-name",
        ],
    )
    async def test_an_edit_that_changes_a_half_leaves_no_row_off_its_words(
        self, db_session: AsyncSession, edited: str, new_text: str
    ) -> None:
        """Whatever the edit does to one half of a split name, no row may be left
        reading the wrong words (the last case would read 'Zeta Zeta Quux')."""
        a, video, sa, sb = await _spanning_world(db_session)
        await scan(db_session, video, [a], full=False)
        await apply_text(db_session, video, sa if edited == "start" else sb, new_text)
        await assert_mentions_ok(db_session, video)

    @pytest.mark.parametrize(
        ("edited", "new_text"),
        [("start", "we all saw Zeta"), ("end", "Quux is right here")],
        ids=["before-the-name", "after-the-name"],
    )
    async def test_an_edit_that_leaves_the_name_alone_keeps_the_span(
        self, db_session: AsyncSession, edited: str, new_text: str
    ) -> None:
        a, video, sa, sb = await _spanning_world(db_session)
        await scan(db_session, video, [a], full=False)
        await apply_text(db_session, video, sa if edited == "start" else sb, new_text)
        await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 1

    async def test_both_sides_edited_then_reverted(
        self, db_session: AsyncSession
    ) -> None:
        a, video, sa, sb = await _spanning_world(db_session)
        await scan(db_session, video, [a], full=False)
        before = await snapshot(db_session, video)
        await apply_text(db_session, video, sa, "so we saw Zeta")
        await apply_text(db_session, video, sb, "Quux is here now")
        await assert_mentions_ok(db_session, video)
        await correction_service().revert_correction(db_session, segment_id=sa)
        await correction_service().revert_correction(db_session, segment_id=sb)
        await assert_mentions_ok(db_session, video)
        assert await snapshot(db_session, video) == before

    async def test_revert_end_segment_of_spanning_correction(
        self, db_session: AsyncSession
    ) -> None:
        a, video, sa, sb = await _spanning_world(
            db_session, "we saw Zeta", "Quuks is here"
        )
        await correct(db_session, sa, GARBLE, A_NAME, entity_id=a, cross_segment=True)
        await correction_service().revert_correction(db_session, segment_id=sb)
        await assert_mentions_ok(db_session, video)

    @pytest.mark.parametrize("full", [False, True], ids=["plain-scan", "full-rescan"])
    @pytest.mark.parametrize("fragment_alias", [False, True], ids=["name", "+alias"])
    @pytest.mark.parametrize(
        ("a_text", "pattern"),
        [("we saw Zeta", GARBLE), ("we saw Zeda", "Zeda Quuks")],
        ids=["end-half-only", "both-halves"],
    )
    async def test_a_scan_after_a_tagged_cross_segment_correction_keeps_one_span(
        self,
        db_session: AsyncSession,
        a_text: str,
        pattern: str,
        fragment_alias: bool,
        full: bool,
    ) -> None:
        """The split name the correction recorded is the one mention of that
        occurrence, whether or not the second half is also an alias, and a scan of
        either kind neither adds a row nor moves one, twice over."""
        a, video, sa, sb = await _spanning_world(db_session, a_text, "Quuks is here")
        if fragment_alias:
            await add_alias(db_session, a, SURNAME)
        await correct(db_session, sa, pattern, A_NAME, entity_id=a, cross_segment=True)
        desc = await assert_mentions_ok(db_session, video)
        rows = [m for m in await positioned(db_session, video) if m.entity_id == a]
        assert len(rows) == 1 and rows[0].end_segment_id == sb, desc
        recorded = await snapshot(db_session, video)

        await scan(db_session, video, [a], full=full)
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 1, desc
        assert await snapshot(db_session, video) == recorded, desc
        await scan(db_session, video, [a], full=full)
        assert await snapshot(db_session, video) == recorded

    async def test_a_correction_over_a_name_with_its_first_half_as_an_alias_row(
        self, db_session: AsyncSession
    ) -> None:
        """DELIBERATE CHOICE, not a defect. A correct alias row for the first half
        ('Zeta') already exists when a tagged cross-segment correction fixes the
        second half. The row reads correctly and holds the entity's unique key at that
        start, so the correction writer leaves it standing rather than also writing the
        split name over it (two rows of one entity may not overlap). The split name
        is what ``scan --full`` records, so it replaces the alias row on the next
        full scan. Every row reads correctly at every step.
        """
        a, video, sa, sb = await _spanning_world(
            db_session, "we saw Zeta", "Quuks is here"
        )
        await add_alias(db_session, a, "Zeta")
        await scan(db_session, video, [a], full=False)
        assert await snapshot(db_session, video) == [
            (str(a), sa, -1, 7, 11, "Zeta", "rule_match")
        ]

        await correct(db_session, sa, GARBLE, A_NAME, entity_id=a, cross_segment=True)

        await assert_mentions_ok(db_session, video)
        assert await snapshot(db_session, video) == [
            (str(a), sa, -1, 7, 11, "Zeta", "rule_match")
        ], "the correct alias row stands after the tagged correction"

        await scan(db_session, video, [a], full=True)

        await assert_mentions_ok(db_session, video)
        assert await snapshot(db_session, video) == [
            (str(a), sa, sb, 7, 4, A_NAME, "rule_match")
        ], "scan --full replaces the alias row with the split name"

    async def test_a_plain_scan_adds_no_second_half_mention_when_a_span_ends_here(
        self, db_session: AsyncSession
    ) -> None:
        """A person's correction recorded a split name as one span anchored in its
        START segment. Its second half is also an alias in the END segment; a plain
        scan of that segment must see the span ends there and not record the alias
        again. (A scan-owned span would be caught by the cross-segment pass's own
        suppression; a correction's is not, so this arm is the only guard.)

        Mutation: drop the ``end_segment_id == row.id`` arm of the incremental dedup
        query in ``EntityMentionScanService`` (the per-segment existing-mentions
        lookup), so only mentions STARTING in the segment count.
        """
        a, video, sa, sb = await _spanning_world(db_session)
        await add_alias(db_session, a, SURNAME)
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=sa,
            start=7,
            end=4,
            mention_text=A_NAME,
            end_segment_id=sb,
            method="user_correction",
        )

        await scan(db_session, video, [a], full=False)

        desc = await assert_mentions_ok(db_session, video)
        rows = [m for m in await positioned(db_session, video) if m.entity_id == a]
        assert [(r.segment_id, r.end_segment_id, r.mention_text) for r in rows] == [
            (sa, sb, A_NAME)
        ], desc


class TestSpanOverThreeSegments:
    async def test_the_middle_segment_replaced(self, db_session: AsyncSession) -> None:
        """The rebase reads mentions starting or ending in the edited segment, so a
        middle segment needs its own lookup (``spans_crossing_segment``)."""
        entity, video, _first, middle, last = await seed_three_segment_world(db_session)
        await scan(db_session, video, [entity], full=False)
        rows = [m for m in await positioned(db_session, video) if m.entity_id == entity]
        assert len(rows) == 1 and rows[0].end_segment_id == last, (
            await mention_report(db_session, video)
        )[3]

        await apply_text(db_session, video, middle, "Blah")

        await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, entity, video) == 0

    async def test_spans_crossing_segment_finds_the_span_only_for_its_middle(
        self, db_session: AsyncSession
    ) -> None:
        """``spans_crossing_segment`` returns the three-segment span for its middle
        segment, and nothing for an end of it or for a segment past it.

        Mutation: relax the ordering conditions (``start.sequence_number <
        middle.sequence_number`` / ``end.sequence_number > middle.sequence_number``)
        to ``<=`` / ``>=``, or drop either; the end segments or the unrelated one
        would then match.
        """
        entity, video, first, middle, last = await seed_three_segment_world(db_session)
        past = await seed_segment(db_session, video, "en", 22.0, 3)
        await set_text(db_session, past, "unrelated words")
        await scan(db_session, video, [entity], full=False)
        repo = EntityMentionRepository()

        crossing = await repo.spans_crossing_segment(db_session, segment_id=middle)

        assert [(s.entity_id, s.segment_id, s.end_segment_id) for s in crossing] == [
            (entity, first, last)
        ]
        for other in (first, last, past):
            assert (
                await repo.spans_crossing_segment(db_session, segment_id=other) == []
            ), f"segment {other} is not inside the span"

    async def test_a_scan_with_the_alias_in_the_middle_converges(
        self, db_session: AsyncSession
    ) -> None:
        entity, video, _first, _middle, _last = await seed_three_segment_world(
            db_session
        )
        await add_alias(db_session, entity, "Quux")
        await scan(db_session, video, [entity], full=False)
        desc = await assert_mentions_ok(db_session, video)
        plain = await snapshot(db_session, video)
        assert len([s for s in plain if s[0] == str(entity)]) == 1, desc
        await scan(db_session, video, [entity], full=True)
        assert await snapshot(db_session, video) == plain
        await scan(db_session, video, [entity], full=False)
        assert await snapshot(db_session, video) == plain

    async def test_a_scan_with_the_alias_in_the_end_segment_converges(
        self, db_session: AsyncSession
    ) -> None:
        entity, video, _first, _middle, _last = await seed_three_segment_world(
            db_session
        )
        await add_alias(db_session, entity, "Nine")
        await scan(db_session, video, [entity], full=False)
        desc = await assert_mentions_ok(db_session, video)
        plain = await snapshot(db_session, video)
        assert len([s for s in plain if s[0] == str(entity)]) == 1, desc
        await scan(db_session, video, [entity], full=True)
        assert await snapshot(db_session, video) == plain


# ---------------------------------------------------------------------------
# 6. Stale rows interacting with valid ones
# ---------------------------------------------------------------------------


async def _valid_rows(
    session: AsyncSession, entity_id: uuid.UUID, video: str
) -> list[EntityMentionDB]:
    index = await text_index(session, video)
    return [
        m
        for m in await positioned(session, video)
        if m.entity_id == entity_id
        and index.text[m.match_start : m.match_end].casefold()
        == m.mention_text.casefold()
    ]


class TestStaleRows:
    async def test_valid_move_onto_a_stale_rows_start_deletes_the_valid_row(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(db_session, f"we saw {A_NAME} here")
        await scan(db_session, video, [a], full=False)  # valid at 7
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg,
            start=0,
            end=5,  # stale: reads "we sa"
            mention_text=A_NAME,
            method="user_correction",
        )
        await apply_text(db_session, video, seg, f"{A_NAME} here")
        assert await _valid_rows(db_session, a, video), (
            await mention_report(db_session, video)
        )[3]

    async def test_stale_overlapping_row_suppresses_a_correction_mention(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(db_session, f"we saw {GARBLE} here")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg,
            start=5,
            end=14,  # stale: reads "w Zeta Qu"
            mention_text=A_NAME,
        )
        await correct(db_session, seg, GARBLE, A_NAME, entity_id=a)
        assert await _valid_rows(db_session, a, video), (
            await mention_report(db_session, video)
        )[3]

    async def test_stale_user_correction_suppresses_full_rescan(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(db_session, f"we saw {A_NAME} here")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg,
            start=0,
            end=9,  # stale: reads "we saw Ze", overlapping the real name
            mention_text=A_NAME,
            method="user_correction",
        )
        await scan(db_session, video, [a], full=True)
        assert await _valid_rows(db_session, a, video), (
            await mention_report(db_session, video)
        )[3]


# ---------------------------------------------------------------------------
# 7. Repeated names, alignment, unique-index churn
# ---------------------------------------------------------------------------


class TestRepeatedNames:
    async def test_both_mentions_shift_past_each_others_starts(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(db_session, f"ab {A_NAME} {A_NAME}")
        await scan(db_session, video, [a], full=False)
        assert await count_of(db_session, a, video) == 2
        await apply_text(db_session, video, seg, f"0123456789ab {A_NAME} {A_NAME}")
        desc = await assert_mentions_ok(db_session, video)
        assert [m.match_start for m in await positioned(db_session, video)] == [
            13,
            23,
        ], desc

    async def test_delete_one_of_two_identical_names(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(db_session, f"{A_NAME}, {A_NAME}")
        await scan(db_session, video, [a], full=False)
        assert await count_of(db_session, a, video) == 2
        await apply_text(db_session, video, seg, A_NAME)
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 1, desc

    async def test_an_ambiguous_deletion_is_attributed_to_the_later_name(
        self, db_session: AsyncSession
    ) -> None:
        """Documented limitation. Two identical names, only the SECOND carrying a
        correction mention, and the edit deletes one of them: the diff cannot tell
        which, and attributes the deletion to the later one, so that mention goes.
        The surviving name reads correctly and a scan records it again; nothing is
        left pointing at the wrong words."""
        a, video, seg, _ = await seed_segments(db_session, f"{A_NAME}, {A_NAME}")
        await place(
            db_session,
            entity_id=a,
            video_id=video,
            segment_id=seg,
            start=11,
            end=20,
            mention_text=A_NAME,
            method="user_correction",
        )
        await apply_text(db_session, video, seg, A_NAME)
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 0, desc
        await scan(db_session, video, [a], full=False)
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 1, desc

    async def test_insert_same_name_before_existing(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(db_session, f"we saw {A_NAME}")
        await scan(db_session, video, [a], full=False)
        await apply_text(db_session, video, seg, f"{A_NAME} said we saw {A_NAME}")
        desc = await assert_mentions_ok(db_session, video)
        assert [m.match_start for m in await positioned(db_session, video)] == [
            22
        ], desc
        await scan(db_session, video, [a], full=True)
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 2, desc

    async def test_multiple_replacements_around_a_scanned_name(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(
            db_session, f"{GARBLE} met {A_NAME} and {GARBLE}"
        )
        await scan(db_session, video, [a], full=False)
        assert await count_of(db_session, a, video) == 1
        await correct(db_session, seg, GARBLE, A_NAME, entity_id=a)
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 3, desc
        await scan(db_session, video, [a], full=True)
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 3, desc
        settled = await snapshot(db_session, video)
        await scan(db_session, video, [a], full=True)
        assert await snapshot(db_session, video) == settled


# ---------------------------------------------------------------------------
# 8. Small edits: case, punctuation, whitespace, emptying
# ---------------------------------------------------------------------------


class TestSmallEdits:
    async def test_case_only_edit(self, db_session: AsyncSession) -> None:
        a, video, seg, _ = await seed_segments(db_session, "we saw zeta quux here")
        await scan(db_session, video, [a], full=False)
        assert await count_of(db_session, a, video) == 1
        await apply_text(db_session, video, seg, f"we saw {A_NAME} here")
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 1, desc
        await scan(db_session, video, [a], full=True)
        assert await count_of(db_session, a, video) == 1

    async def test_punctuation_adjacent(self, db_session: AsyncSession) -> None:
        a, video, seg, _ = await seed_segments(db_session, f"we saw {A_NAME} here")
        await scan(db_session, video, [a], full=False)
        await apply_text(db_session, video, seg, f"we saw, {A_NAME}, here.")
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 1, desc

    async def test_whitespace_inside_name(self, db_session: AsyncSession) -> None:
        a, video, seg, _ = await seed_segments(db_session, f"we saw {A_NAME} here")
        await scan(db_session, video, [a], full=False)
        await apply_text(db_session, video, seg, "we saw Zeta  Quux here")
        await assert_mentions_ok(db_session, video)

    async def test_empty_the_segment(self, db_session: AsyncSession) -> None:
        a, video, seg, _ = await seed_segments(db_session, f"we saw {A_NAME} here")
        await scan(db_session, video, [a], full=False)
        await apply_text(db_session, video, seg, " ")
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 0, desc
        entity = (
            await db_session.execute(
                select(NamedEntityDB)
                .where(NamedEntityDB.id == a)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert entity.mention_count == 0


# ---------------------------------------------------------------------------
# 9. Unicode
# ---------------------------------------------------------------------------


class TestUnicode:
    async def test_accented_name_moves(self, db_session: AsyncSession) -> None:
        c = await make_entity(db_session, "Zéta Vörn")
        _a, video, seg, _ = await seed_segments(db_session, "we saw Zéta Vörn here")
        await scan(db_session, video, [c], full=False)
        assert await count_of(db_session, c, video) == 1
        await apply_text(db_session, video, seg, "and so we saw Zéta Vörn here")
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, c, video) == 1, desc

    async def test_sharp_s_name_moves(self, db_session: AsyncSession) -> None:
        c = await make_entity(db_session, "Zeta Straße")
        _a, video, seg, _ = await seed_segments(db_session, "we saw Zeta Straße here")
        await scan(db_session, video, [c], full=False)
        assert await count_of(db_session, c, video) == 1
        await apply_text(db_session, video, seg, "ß we saw Zeta Straße here")
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, c, video) == 1, desc

    async def test_emoji_before_mention(self, db_session: AsyncSession) -> None:
        a, video, seg, _ = await seed_segments(
            db_session, f"\U0001f600 we saw {A_NAME}"
        )
        await scan(db_session, video, [a], full=False)
        await apply_text(
            db_session, video, seg, f"\U0001f600\U0001f600 we all saw {A_NAME}"
        )
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 1, desc

    async def test_dotted_capital_i_before_entity_tagged_correction(
        self, db_session: AsyncSession
    ) -> None:
        """'İ'.lower() is two code points, so the correction writer's
        lower()-based finder is off by one per 'İ' before the hit. The
        replacement is not a visible name, so widening cannot rescue it."""
        a, video, seg, _ = await seed_segments(db_session, "İİ Quuks here")
        await correct(db_session, seg, "Quuks", "Quuxian", entity_id=a)
        rows = await positioned(db_session, video)
        desc = (await mention_report(db_session, video))[3]
        assert [m.mention_text for m in rows] == ["Quuxian"], desc

    async def test_dotted_capital_i_rescued_by_widening(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(db_session, f"İ saw {GARBLE} here")
        await correct(db_session, seg, GARBLE, A_NAME, entity_id=a)
        desc = await assert_mentions_ok(db_session, video)
        rows = await positioned(db_session, video)
        assert [m.mention_text for m in rows] == [A_NAME], desc


# ---------------------------------------------------------------------------
# 10. Revert chains
# ---------------------------------------------------------------------------


class TestReverts:
    async def test_apply_apply_revert_revert(self, db_session: AsyncSession) -> None:
        original = f"we saw {A_NAME} here"
        a, video, seg, _ = await seed_segments(db_session, original)
        await scan(db_session, video, [a], full=False)
        await apply_text(db_session, video, seg, f"so we saw {A_NAME} here")
        await apply_text(db_session, video, seg, f"so we saw {A_NAME} there")
        await assert_mentions_ok(db_session, video)
        await correction_service().revert_correction(db_session, segment_id=seg)
        await assert_mentions_ok(db_session, video)
        await correction_service().revert_correction(db_session, segment_id=seg)
        desc = await assert_mentions_ok(db_session, video)
        index = await text_index(db_session, video)
        if index.text.startswith(original):
            assert [
                (m.match_start, m.match_end)
                for m in await positioned(db_session, video)
            ] == [(7, 16)], desc
        assert await count_of(db_session, a, video) == 1, desc

    async def test_batch_revert_by_batch_id_moves_back(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(db_session, f"we saw {GARBLE} here")
        first = new_batch_id()
        await correct(db_session, seg, GARBLE, A_NAME, entity_id=a, batch_id=first)
        second = new_batch_id()
        await correct(db_session, seg, "we saw", "we all saw", batch_id=second)
        await assert_mentions_ok(db_session, video)
        await batch_service().batch_revert(db_session, batch_id=second)
        desc = await assert_mentions_ok(db_session, video)
        rows = await positioned(db_session, video)
        assert [(m.match_start, m.match_end) for m in rows] == [(7, 16)], desc
        await batch_service().batch_revert(db_session, batch_id=first)
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 0, desc

    async def test_revert_of_entity_correction_removes_scan_twin_too(
        self, db_session: AsyncSession
    ) -> None:
        """Correction -> full scan (no twin) -> revert via revert_correction (not
        the batch path): the user_correction row's words revert to the garble."""
        a, video, seg, _ = await seed_segments(db_session, f"we saw {GARBLE} here")
        await correct(db_session, seg, GARBLE, A_NAME, entity_id=a)
        await scan(db_session, video, [a], full=True)
        await correction_service().revert_correction(db_session, segment_id=seg)
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 0, desc

    async def test_a_cross_segment_correction_survives_an_edit_and_its_revert(
        self, db_session: AsyncSession
    ) -> None:
        """Tagged cross-segment correction, two full scans, a plain scan, then an
        edit before the name in the start segment and its revert: the snapshot is the
        one the correction recorded."""
        a, video, sa, sb = await _spanning_world(
            db_session, "we saw Zeda", "Quuks is here"
        )
        await correct(
            db_session, sa, "Zeda Quuks", A_NAME, entity_id=a, cross_segment=True
        )
        rows = [m for m in await positioned(db_session, video) if m.entity_id == a]
        assert len(rows) == 1 and rows[0].end_segment_id == sb
        for full in (True, True, False):
            await scan(db_session, video, [a], full=full)
        recorded = await snapshot(db_session, video)
        assert await count_of(db_session, a, video) == 1

        await apply_text(db_session, video, sa, "so we saw Zeta")
        await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 1
        await correction_service().revert_correction(db_session, segment_id=sa)

        await assert_mentions_ok(db_session, video)
        assert await snapshot(db_session, video) == recorded


# ---------------------------------------------------------------------------
# 11. Aliases, two entities, exclusion patterns
# ---------------------------------------------------------------------------


class TestEntitiesAndAliases:
    async def test_alias_substring_then_name_completed(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(db_session, "we saw Quuks")
        await add_alias(db_session, a, "Quux")
        await correct(db_session, seg, "Quuks", "Quux", entity_id=a)
        await correct(db_session, seg, "saw Quux", "saw Zeta Quux", entity_id=a)
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 1, desc
        await scan(db_session, video, [a], full=True)
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 1, desc

    async def test_two_entities_overlapping_names(
        self, db_session: AsyncSession
    ) -> None:
        c = await make_entity(db_session, "Quux Nine")
        a, video, seg, _ = await seed_segments(db_session, "we saw Zeta Quuks Nine")
        await correct(db_session, seg, "Quuks", "Quux", entity_id=c)
        rows = await positioned(db_session, video)
        desc = await assert_mentions_ok(db_session, video)
        assert [(m.entity_id, m.mention_text) for m in rows] == [(c, "Quux Nine")], desc
        await scan(db_session, video, [a, c], full=True)
        desc = await assert_mentions_ok(db_session, video)
        settled = await snapshot(db_session, video)
        await scan(db_session, video, [a, c], full=True)
        assert await snapshot(db_session, video) == settled, desc

    async def test_other_entity_mention_survives_correction(
        self, db_session: AsyncSession
    ) -> None:
        """Entity A scanned; an entity-C-tagged correction elsewhere in the segment
        must not touch A's mention."""
        c = await make_entity(db_session, "Quux Nine")
        a, video, seg, _ = await seed_segments(db_session, f"{A_NAME} and Quuks Nine")
        await scan(db_session, video, [a], full=False)
        await correct(db_session, seg, "Quuks", "Quux", entity_id=c)
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 1, desc
        assert await count_of(db_session, c, video) == 1, desc

    async def test_exclusion_pattern_on_widened_span(
        self, db_session: AsyncSession
    ) -> None:
        a, video, seg, _ = await seed_segments(db_session, "on Zeta Quuks Street")
        await db_session.execute(
            update(NamedEntityDB)
            .where(NamedEntityDB.id == a)
            .values(exclusion_patterns=["Zeta Quux Street"])
        )
        await db_session.flush()
        await correct(db_session, seg, "Quuks", "Quux", entity_id=a)
        desc = await assert_mentions_ok(db_session, video)
        assert await count_of(db_session, a, video) == 0, desc
        await scan(db_session, video, [a], full=True)
        assert await count_of(db_session, a, video) == 0

    async def test_alias_equal_to_common_word_widening(
        self, db_session: AsyncSession
    ) -> None:
        """Alias 'the'; a correction that writes 'Quux' next to 'the' must not be
        widened into an unrelated span or produce overlapping rows."""
        a, video, seg, _ = await seed_segments(
            db_session, "the Quuks and the Zeta Quuks"
        )
        await add_alias(db_session, a, "the")
        await correct(db_session, seg, "Quuks", "Quux", entity_id=a)
        desc = await assert_mentions_ok(db_session, video)
        rows = await positioned(db_session, video)
        assert all(m.mention_text.casefold() != "the" for m in rows), desc


# ---------------------------------------------------------------------------
# 12. detect_in_text: the scan's rule, with or without its neighbours' arbitration
# ---------------------------------------------------------------------------


class TestDetectInTextArbitration:
    async def test_a_longer_neighbour_shadows_the_name_only_when_arbitrating(
        self, db_session: AsyncSession
    ) -> None:
        """Entity X is 'Zeta Quux'; entity Y is 'Zeta Quux Nine' and shares its tokens.
        In 'we saw Zeta Quux Nine here' a scan gives that span to the longer Y, so
        X is not found. A correction a person tagged with X must still find X's name
        there (``arbitrate_with_neighbours=False``): another name must not override
        their choice. Y's own match is never returned, in either mode.

        Mutation: ignore ``arbitrate_with_neighbours`` (always arbitrate, or never):
        one of the two assertions below turns red.
        """
        x = await make_entity(db_session, A_NAME)
        await make_entity(db_session, "Zeta Quux Nine")
        text = "we saw Zeta Quux Nine here"
        detector = EntityMentionScanService()

        arbitrated = await detector.detect_in_text(
            db_session, text=text, language_code="en", entity_ids=[x]
        )
        unarbitrated = await EntityMentionScanService().detect_in_text(
            db_session,
            text=text,
            language_code="en",
            entity_ids=[x],
            arbitrate_with_neighbours=False,
        )

        assert arbitrated == [], "the longer neighbour owns the span in a scan"
        assert [(m.entity_id, m.match_start, m.match_end) for m in unarbitrated] == [
            (x, 7, 16)
        ]

    async def test_without_a_longer_neighbour_both_modes_find_the_name(
        self, db_session: AsyncSession
    ) -> None:
        """Control: where nothing longer overlaps, arbitration changes nothing, so the
        test above is about the neighbour and not about the flag removing matches."""
        x = await make_entity(db_session, A_NAME)
        await make_entity(db_session, "Zeta Quux Nine")
        text = "we saw Zeta Quux here"
        for arbitrate in (True, False):
            found = await EntityMentionScanService().detect_in_text(
                db_session,
                text=text,
                language_code="en",
                entity_ids=[x],
                arbitrate_with_neighbours=arbitrate,
            )
            assert [(m.match_start, m.match_end) for m in found] == [(7, 16)]
