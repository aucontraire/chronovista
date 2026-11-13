"""
Scoped-scan invariant fitness guard for entity-mention shadowing.

Invariant (NOTE 020 section 3)
------------------------------
A scoped scan must produce the same surviving mentions for the scoped entity
as an unscoped scan, restricted to that entity.

Known violation
---------------
``EntityMentionScanService.scan`` derives the set of entities it writes for
from the set of patterns it matches with (``scoped_entity_ids = [p.entity_id
for p in patterns]``).  A scan scoped to one entity therefore loads only that
entity's pattern, and cross-entity longest-match-wins has no competing span to
arbitrate against, so it writes a "shadow" mention that an unscoped scan
would have suppressed.

The shared-token match/write-set split (NOTE 020 §2/§5) makes these pass; the
guard stays to keep the invariant from regressing.

Each test seeds its entities and one segment, runs the unscoped scan to
capture ground truth, clears the mention rows, then runs
``scan(entity_ids=[E])`` per entity and compares surviving mention spans.
All names are invented placeholders.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.services.entity_mention_scan_service import (
    EntityMentionScanService,
)
from tests.factories.id_factory import video_id
from tests.integration.services.test_entity_mention_scan_integration import (
    _make_session_factory_from_session,
    _seed_channel,
    _seed_entity,
    _seed_segment,
    _seed_transcript,
    _seed_video,
)

# CRITICAL: ensures async tests are not silently skipped under coverage.
pytestmark = pytest.mark.asyncio

SpanKey = tuple[uuid.UUID, int, int, int]


async def _surviving_spans(session: AsyncSession, entity_id: uuid.UUID) -> set[SpanKey]:
    """Return ``(entity_id, segment_id, match_start, match_end)`` per mention."""
    rows = (
        await session.execute(
            select(
                EntityMentionDB.entity_id,
                EntityMentionDB.segment_id,
                EntityMentionDB.match_start,
                EntityMentionDB.match_end,
            ).where(EntityMentionDB.entity_id == entity_id)
        )
    ).all()
    return {(r.entity_id, r.segment_id, r.match_start, r.match_end) for r in rows}


async def _assert_scoped_equals_unscoped(
    session: AsyncSession,
    entities: list[NamedEntityDB],
    sources: list[str] | None = None,
) -> None:
    """Assert the scoped-scan invariant for every entity in ``entities``.

    ``sources`` ``None`` drives the transcript-segment path (:meth:`scan`);
    a list such as ``["description"]`` drives the metadata path
    (:meth:`scan_metadata`), which has the identical write-set=match-set
    collapse at ``entity_mention_scan_service.py:1074``.
    """
    service = EntityMentionScanService(
        session_factory=_make_session_factory_from_session(session)
    )

    async def _run(entity_ids: list[uuid.UUID] | None = None) -> None:
        kwargs = {} if entity_ids is None else {"entity_ids": entity_ids}
        if sources is None:
            await service.scan(**kwargs)
        else:
            await service.scan_metadata(sources=sources, **kwargs)

    await _run()
    unscoped = {
        e.canonical_name: await _surviving_spans(session, e.id) for e in entities
    }

    differences: list[str] = []
    for entity in entities:
        await session.execute(delete(EntityMentionDB))
        await session.commit()
        await _run(entity_ids=[entity.id])
        scoped = await _surviving_spans(session, entity.id)
        expected = unscoped[entity.canonical_name]
        if scoped != expected:
            differences.append(
                f"{entity.canonical_name!r}: scoped scan produced "
                f"{sorted(s[2:] for s in scoped)} but unscoped scan produced "
                f"{sorted(s[2:] for s in expected)} (match_start, match_end)"
            )

    assert not differences, "scoped != unscoped: " + "; ".join(differences)


class TestScopedScanInvariant:
    """NOTE 020 section 3: scoped scan == unscoped scan, per scoped entity."""

    async def test_scoped_scan_matches_unscoped__containment(
        self, db_session: AsyncSession
    ) -> None:
        """
        Containment arm: "Marla" is a token-prefix of "Marla Quenneville".

        Unscoped, the longer match wins and the shorter entity gets zero
        mentions.  Scoped to the shorter entity, its pattern is alone, so a
        shadow mention is written.
        """
        vid = video_id(seed="scope_contain")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid)
        await _seed_segment(db_session, vid, text="Marla Quenneville spoke at length.")
        short = await _seed_entity(db_session, "Marla", entity_type="person")
        long_ = await _seed_entity(
            db_session, "Marla Quenneville", entity_type="person"
        )
        await db_session.commit()

        await _assert_scoped_equals_unscoped(db_session, [short, long_])

    async def test_scoped_scan_matches_unscoped__partial_overlap(
        self, db_session: AsyncSession
    ) -> None:
        """
        Partial-overlap arm: the two names share only the token "Oberlin".

        MUTATION SENTINEL.  Neither name contains the other, so a fix that
        widens the scoped match set by *containment* would leave this test
        failing; only widening by *shared whole token* fixes it.  Do not
        weaken this arm into a containment case.
        """
        vid = video_id(seed="scope_overlap")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid)
        await _seed_segment(
            db_session, vid, text="Danforth Oberlin Pashby arrived today."
        )
        left = await _seed_entity(db_session, "Danforth Oberlin", entity_type="person")
        right = await _seed_entity(db_session, "Oberlin Pashby", entity_type="person")
        await db_session.commit()

        await _assert_scoped_equals_unscoped(db_session, [left, right])

    async def test_scoped_metadata_scan_matches_unscoped__containment(
        self, db_session: AsyncSession
    ) -> None:
        """
        Description-path containment arm: "Marla" is a token-prefix of
        "Marla Quenneville", seeded in the VIDEO'S DESCRIPTION.

        Unscoped, the longer match wins and the shorter entity gets zero
        mentions.  Scoped to the shorter entity via ``scan_metadata``, its
        pattern is alone, so a shadow description mention is written —
        the same collapse as the transcript path, at line 1074.
        """
        vid = video_id(seed="scope_meta_contain")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await db_session.execute(
            update(VideoDB)
            .where(VideoDB.video_id == vid)
            .values(description="Marla Quenneville spoke at length.")
        )
        short = await _seed_entity(db_session, "Marla", entity_type="person")
        long_ = await _seed_entity(
            db_session, "Marla Quenneville", entity_type="person"
        )
        await db_session.commit()

        await _assert_scoped_equals_unscoped(
            db_session, [short, long_], sources=["description"]
        )

    async def test_scoped_metadata_scan_matches_unscoped__partial_overlap(
        self, db_session: AsyncSession
    ) -> None:
        """
        Description-path partial-overlap arm (MUTATION SENTINEL): the two
        names share only the token "Oberlin", seeded in the VIDEO'S
        DESCRIPTION.

        Neither name contains the other, so a fix that widens the scoped
        metadata match set by *containment* would leave this failing; only
        widening by *shared whole token* fixes it.  Do not weaken this arm
        into a containment case.
        """
        vid = video_id(seed="scope_meta_overlap")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await db_session.execute(
            update(VideoDB)
            .where(VideoDB.video_id == vid)
            .values(description="Danforth Oberlin Pashby arrived today.")
        )
        left = await _seed_entity(db_session, "Danforth Oberlin", entity_type="person")
        right = await _seed_entity(db_session, "Oberlin Pashby", entity_type="person")
        await db_session.commit()

        await _assert_scoped_equals_unscoped(
            db_session, [left, right], sources=["description"]
        )


class TestCrossPoolCompeteInvariant:
    """Q3 / issue #279: spanning and in-segment matches must COMPETE in one pool.

    The transcript (:meth:`scan`) runs two passes with SEPARATE longest-match-wins
    pools: a per-segment pass, and an additive cross-segment pass
    (``_scan_cross_segment``) that detects names split across a segment boundary
    and *discards every single-segment survivor*
    (``entity_mention_scan_service.py:855`` — ``if anchor.end_segment_id is None:
    continue``).  Because the two pools never meet, a spanning match and an
    overlapping in-segment match of a *different* entity are both written today
    (additive by construction) — the ~434-pair / 31-entity cross-segment
    arbitration gap (``measurements/01_design_gate_overlap_relation.sql`` §C).

    User product decision (2026-11-12): they should **COMPETE** — the longer
    spanning match SUPPRESSES the overlapping shorter in-segment match (one pool,
    uniform longest-match-wins across the boundary), consistent with the shipped
    shadowing fixes (#280 / v0.120.1-.2).

    Written first and FAILING (``xfail(strict=True)``): CI stays green now and
    turns red (XPASS) the moment the single-pool compete fix lands, forcing
    removal of the marker.  All names are invented placeholders.
    """

    async def test_cross_segment_span_is_detected(
        self, db_session: AsyncSession
    ) -> None:
        """
        UNMARKED precondition guard for the compete arm below.

        Hoisted out of the ``xfail`` test on purpose.  ``xfail(strict=True)``
        collapses *every* failure cause to a green ``xfailed``: a precondition
        assert living inside that marker would let a regression in cross-segment
        detection pass silently while the compete guard quietly measures
        nothing.  This test is UNMARKED, so it goes red the instant the spanning
        match stops being detected — which is exactly when the compete fixture
        would stop meaning anything.
        """
        vid = video_id(seed="scope_xpool_detect")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid)
        await _seed_segment(
            db_session,
            vid,
            text="The guest tonight is Quade",
            sequence_number=0,
            start_time=0.0,
        )
        await _seed_segment(
            db_session,
            vid,
            text="Marlowe joined the panel.",
            sequence_number=1,
            start_time=5.0,
        )
        long_ = await _seed_entity(db_session, "Quade Marlowe", entity_type="person")
        await db_session.commit()

        service = EntityMentionScanService(
            session_factory=_make_session_factory_from_session(db_session)
        )
        await service.scan()

        long_spans = await _surviving_spans(db_session, long_.id)
        assert long_spans, (
            "cross-segment pass must detect 'Quade Marlowe' spanning the segment "
            "boundary; if this regresses, the compete arm below silently measures "
            "nothing"
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Q3/#279: cross-segment and per-segment passes arbitrate in separate "
            "pools, so a spanning match does not suppress an overlapping in-segment "
            "match. Compete (user 2026-11-12) is unimplemented; this fails today "
            "and XPASSes when the single-pool fix lands."
        ),
    )
    async def test_spanning_match_suppresses_overlapping_in_segment(
        self, db_session: AsyncSession
    ) -> None:
        """
        Cross-pool arm, EXACT-SET form (distinguishes the correct fix from an
        over-suppressing one).

        Three segments on one video::

            seg 0  "The guest tonight is Quade"
            seg 1  "Marlowe joined the panel."   <- boundary-adjacent "Marlowe"
            seg 2  "Marlowe returned later."     <- FAR, non-overlapping "Marlowe"

        Concatenated, "Quade Marlowe" (LONG) straddles the 0/1 boundary — a
        spanning match owned by the cross-segment pass.  "Marlowe" (SHORT)
        matches in-segment in BOTH seg 1 and seg 2; only the seg-1 occurrence
        overlaps the spanning match, the seg-2 occurrence is far from any
        "Quade".

        Under COMPETE, SHORT must keep EXACTLY its far occurrence (seg 2) and
        lose only the boundary-adjacent one (seg 1).  The exact set is what lets
        the guard reject an over-suppressing "fix"::

            today (additive, two pools):   {seg1, seg2}  != {seg2}  -> xfails (gap present, correct)
            correct cross-boundary LMW:    {seg2}        == {seg2}  -> XPASSes (strict red; remove marker)
            blanket token suppression:     {}            != {seg2}  -> still fails (guard REJECTS the wrong fix)

        A weaker ``assert not short_spans`` would be *satisfied* by blanket
        suppression and could not tell the real fix from the broken one.
        """
        vid = video_id(seed="scope_xpool")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid)
        await _seed_segment(
            db_session,
            vid,
            text="The guest tonight is Quade",
            sequence_number=0,
            start_time=0.0,
        )
        await _seed_segment(
            db_session,
            vid,
            text="Marlowe joined the panel.",
            sequence_number=1,
            start_time=5.0,
        )
        far_seg = await _seed_segment(
            db_session,
            vid,
            text="Marlowe returned later.",
            sequence_number=2,
            start_time=10.0,
        )
        short = await _seed_entity(db_session, "Marlowe", entity_type="person")
        long_ = await _seed_entity(db_session, "Quade Marlowe", entity_type="person")
        await db_session.commit()

        service = EntityMentionScanService(
            session_factory=_make_session_factory_from_session(db_session)
        )
        await service.scan()

        long_spans = await _surviving_spans(db_session, long_.id)
        short_spans = await _surviving_spans(db_session, short.id)

        # Fixture tripwire. The loud, unmarked guarantee is
        # test_cross_segment_span_is_detected above; this line only protects
        # against a silently-broken fixture inside the marker.
        assert (
            long_spans
        ), "spanning 'Quade Marlowe' should be detected across the boundary"

        # Exact-set invariant: SHORT retains precisely its far, non-overlapping
        # occurrence and loses the boundary-adjacent one. See the outcome table
        # in the docstring for why an exact set (not `not short_spans`) is
        # required to reject an over-suppressing fix.
        short_segments = {s[1] for s in short_spans}
        assert short_segments == {far_seg.id}, (
            "under compete, 'Marlowe' must retain exactly its far occurrence "
            f"(segment {far_seg.id}) and lose the boundary-adjacent one, but got "
            f"segments {sorted(short_segments)}"
        )

    async def test_far_non_overlapping_match_is_never_suppressed(
        self, db_session: AsyncSession
    ) -> None:
        """
        UNMARKED companion to the compete arm: the far, non-overlapping match
        must survive, so an over-suppressing "fix" fails LOUDLY here instead of
        hiding behind an unchanged ``xfailed``.

        The exact-set arm above *declines to certify* an over-suppressing fix
        (no XPASS), but its suite output is byte-identical to the gap state —
        same ``xfailed``, same counts.  A developer who implements blanket
        suppression therefore sees no change and misreads it as "not done yet."
        This test converts that silent miss into a red.

        "A non-overlapping in-segment match is never suppressed" is a permanent
        invariant of *any* correct compete fix: the far occurrence (seg 2)
        overlaps no spanning match, so it is present in both correct states and
        absent only when a fix over-suppresses::

            today (additive):     SHORT superset-of {seg2}  -> PASS
            correct compete LMW:  SHORT == {seg2}           -> PASS
            over-suppression:     SHORT == {}               -> RED

        Both SHORT and LONG are seeded: the over-suppression failure mode keys
        on the token-subset relation ("Marlowe" within "Quade Marlowe"), so LONG
        must be loaded for that mutation to fire and for this guard to catch it.
        """
        vid = video_id(seed="scope_xpool_far")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid)
        await _seed_segment(
            db_session,
            vid,
            text="The guest tonight is Quade",
            sequence_number=0,
            start_time=0.0,
        )
        await _seed_segment(
            db_session,
            vid,
            text="Marlowe joined the panel.",
            sequence_number=1,
            start_time=5.0,
        )
        far_seg = await _seed_segment(
            db_session,
            vid,
            text="Marlowe returned later.",
            sequence_number=2,
            start_time=10.0,
        )
        short = await _seed_entity(db_session, "Marlowe", entity_type="person")
        await _seed_entity(db_session, "Quade Marlowe", entity_type="person")
        await db_session.commit()

        service = EntityMentionScanService(
            session_factory=_make_session_factory_from_session(db_session)
        )
        await service.scan()

        short_segments = {s[1] for s in await _surviving_spans(db_session, short.id)}
        assert far_seg.id in short_segments, (
            f"the far, non-overlapping 'Marlowe' (segment {far_seg.id}) must never "
            "be suppressed — it overlaps no spanning match; its absence signals an "
            f"over-suppressing fix. Got segments {sorted(short_segments)}"
        )
