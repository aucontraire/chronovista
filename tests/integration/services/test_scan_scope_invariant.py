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
