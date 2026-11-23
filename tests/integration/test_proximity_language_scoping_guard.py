"""Mutation-verified guard for the FR-005 language-scoping invariant (Features 116, 117).

Proximity instances must never pair two mentions from different transcript
languages. One video can carry several transcripts of the SAME audio on an
aligned timeline, so without the scoping clause the self-join pairs a mention
with its own translation at a near-zero gap — a fabricated strong signal.

A structural assertion ("the predicate exists") would not notice if the clause
stopped being applied. This test crosses the real seam instead: it seeds a
multilingual video, runs the real per-scope computor against real tables, and proves the
guard is load-bearing by monkeypatching ``language_scope_predicate`` to
``true()`` and requiring cross-language instances to APPEAR. If the clause were
removed from the join, the "intact" half would fail; if the patch target ever
stopped being the symbol the join uses, the "mutated" half would fail.

Since Feature 117 the join is bound to one ``(video, language)`` scope, but the scope
filter constrains only side A. ``language_scope_predicate`` is still the only clause
that keeps side B in the same language, which is exactly what the mutation proves.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from chronovista.db.models import EntityPairProximity as EntityPairProximityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.repositories.entity_pair_proximity_repository import (
    EntityPairProximityRepository,
)
from chronovista.services.proximity_service import process_stale_scopes
from tests.factories.proximity_seed import (
    route_proximity_service_to,
    seed_entity,
    seed_mention,
    seed_segment,
    seed_video,
)

pytestmark = pytest.mark.asyncio

_LANGUAGES = ("en", "es")


async def _seed_multilingual_video(session: AsyncSession) -> str:
    """One video with two aligned transcripts (no support gate since Feature 117).

    In every language the two entities sit 60s apart, and the language tracks
    are offset by only 1s, so every cross-language combination is ALSO inside
    the 120s window — the cross-language trap.
    """
    entity_a = await seed_entity(session)
    entity_b = await seed_entity(session)
    video_id = f"lang117v{uuid.uuid4().hex[:8]}"
    await seed_video(session, video_id, _LANGUAGES)
    for offset, language in enumerate(_LANGUAGES):
        seg_a = await seed_segment(session, video_id, language, 10.0 + offset, 0)
        seg_b = await seed_segment(session, video_id, language, 70.0 + offset, 1)
        for entity_id, segment_id in ((entity_a, seg_a), (entity_b, seg_b)):
            await seed_mention(
                session,
                entity_id=entity_id,
                video_id=video_id,
                language_code=language,
                segment_id=segment_id,
            )
    await session.commit()
    return video_id


async def _recompute(session: AsyncSession, video_id: str) -> None:
    """Invalidate every language of the video, then process its stale scopes."""
    await EntityPairProximityRepository().invalidate_proximity_scopes(
        session, video_id=video_id, reason="test"
    )
    await process_stale_scopes(limit=100)


async def _instance_counts(session: AsyncSession, video_id: str) -> tuple[int, int]:
    """Return ``(total_instances, cross_language_instances)``.

    Joins each instance back to BOTH of its segments and compares their
    languages, rather than trusting the instance's own ``language_code`` column
    (which is copied from one side and would hide a mismatch).
    """
    seg_a = aliased(TranscriptSegmentDB)
    seg_b = aliased(TranscriptSegmentDB)
    row = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(seg_a.language_code != seg_b.language_code),
            )
            .select_from(EntityPairProximityDB)
            .join(seg_a, seg_a.id == EntityPairProximityDB.segment_a_id)
            .join(seg_b, seg_b.id == EntityPairProximityDB.segment_b_id)
            .where(EntityPairProximityDB.video_id == video_id)
        )
    ).one()
    return int(row[0]), int(row[1])


async def test_proximity_never_spans_two_transcript_languages(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_id = await _seed_multilingual_video(db_session)
    route_proximity_service_to(monkeypatch, db_session)

    # --- intact: the invariant holds, and the run is not vacuously empty -----
    await _recompute(db_session, video_id)
    intact_total, intact_cross = await _instance_counts(db_session, video_id)
    assert intact_total > 0, "no instances at all - the seed is vacuous"
    assert intact_cross == 0, f"{intact_cross} cross-language instances (FR-005)"
    per_language = (
        await db_session.execute(
            select(EntityPairProximityDB.language_code, func.count())
            .where(EntityPairProximityDB.video_id == video_id)
            .group_by(EntityPairProximityDB.language_code)
        )
    ).all()
    assert dict(per_language) == {"en": 1, "es": 1}, "a language scope was skipped"

    # --- mutated: remove the clause; the guard must now see the violation ----
    monkeypatch.setattr(
        "chronovista.repositories.entity_pair_proximity_repository"
        ".language_scope_predicate",
        lambda segment_a, segment_b: true(),
    )
    await _recompute(db_session, video_id)
    mutated_total, mutated_cross = await _instance_counts(db_session, video_id)
    assert mutated_cross > 0, (
        "removing language_scope_predicate did not produce cross-language "
        "instances - this guard would pass against broken code"
    )
    assert mutated_total > intact_total
