"""Delete cascades for the proximity records: entity, video, segment (Features 116, 117).

The record table declares ``entity_*_id ... ON DELETE CASCADE`` to
``named_entities``. Nothing in application code deletes through that path in
the proximity flow, so without this test "it's in the schema" is an unchecked
claim. This crosses the real FK: delete the entity row, assert the record rows
are gone AND the derived pair summary (``read_rollup``) no longer reports the
pair, and that an unrelated pair survives (so the cascade is scoped rather than
a table wipe). Since Feature 117 the summary is derived on read, so it cannot
lag a cascade the way the old stored rollup could.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityPairProximity as EntityPairProximityDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import ProximityScopeState as ProximityScopeStateDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.entity_pair_proximity import EntityPairProximityCreate
from chronovista.repositories.entity_pair_proximity_repository import (
    EntityPairProximityRepository,
)
from tests.factories.proximity_seed import (
    canonical,
    seed_entity,
    seed_scope_state,
    seed_segment,
    seed_video,
)

pytestmark = pytest.mark.asyncio

_VIDEO = "casc116vid0"


async def _seed_pair(
    session: AsyncSession,
    repo: EntityPairProximityRepository,
    pair: tuple[uuid.UUID, uuid.UUID],
    first_sequence: int,
) -> None:
    """Two instances for ``pair`` on the shared video."""
    seg_a = await seed_segment(session, _VIDEO, "en", 10.0, first_sequence)
    seg_b = await seed_segment(session, _VIDEO, "en", 20.0, first_sequence + 1)
    written = await repo.insert_instances(
        session,
        instances=[
            EntityPairProximityCreate(
                entity_a_id=pair[0],
                entity_b_id=pair[1],
                video_id=_VIDEO,
                language_code="en",
                segment_a_id=seg_a,
                segment_b_id=seg_b,
                gap_seconds=10.0,
            ),
            EntityPairProximityCreate(
                entity_a_id=pair[0],
                entity_b_id=pair[1],
                video_id=_VIDEO,
                language_code="en",
                segment_a_id=seg_b,
                segment_b_id=seg_a,
                gap_seconds=10.0,
            ),
        ],
    )
    assert written == 2


async def _counts(session: AsyncSession, entity_id: uuid.UUID) -> tuple[int, int]:
    instances = await session.scalar(
        select(func.count())
        .select_from(EntityPairProximityDB)
        .where(
            or_(
                EntityPairProximityDB.entity_a_id == entity_id,
                EntityPairProximityDB.entity_b_id == entity_id,
            )
        )
    )
    derived = await EntityPairProximityRepository().read_rollup(
        session, min_shared_videos=1
    )
    pairs = sum(1 for a, b, _, _ in derived if entity_id in (a, b))
    return int(instances or 0), pairs


async def test_deleting_an_entity_cascades_records_and_derived_summary(
    db_session: AsyncSession,
) -> None:
    repo = EntityPairProximityRepository()
    doomed, partner, bystander_a, bystander_b = [
        await seed_entity(db_session) for _ in range(4)
    ]
    await seed_video(db_session, _VIDEO)
    doomed_pair = canonical(doomed, partner)
    bystander_pair = canonical(bystander_a, bystander_b)
    await _seed_pair(db_session, repo, doomed_pair, first_sequence=0)
    await _seed_pair(db_session, repo, bystander_pair, first_sequence=2)
    await db_session.commit()

    # Precondition: rows exist, so the post-delete zero is a real change.
    assert await _counts(db_session, doomed) == (2, 1)
    assert await _counts(db_session, bystander_a) == (2, 1)

    # Core DELETE (not session.delete) so the DATABASE FK does the cascading.
    await db_session.execute(delete(NamedEntityDB).where(NamedEntityDB.id == doomed))
    await db_session.commit()

    assert await _counts(db_session, doomed) == (0, 0), "cascade left proximity rows"
    assert await _counts(db_session, partner) == (0, 0), "partner kept orphan rows"
    assert await _counts(db_session, bystander_a) == (2, 1), "cascade over-deleted"


async def _video_records(session: AsyncSession, video_id: str) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(EntityPairProximityDB)
            .where(EntityPairProximityDB.video_id == video_id)
        )
        or 0
    )


async def test_deleting_a_transcript_then_its_video_cascades_records_and_state(
    db_session: AsyncSession,
) -> None:
    """FR-011 deletion clause, along the schema's real path.

    ``video_transcripts -> videos`` does not cascade, so a video with transcripts is
    removed transcript-first: the transcript's segments cascade, taking their
    mentions and proximity records; deleting the video then removes its scope state.
    """
    repo = EntityPairProximityRepository()
    a, b = await seed_entity(db_session), await seed_entity(db_session)
    doomed, kept = f"casc117d{uuid.uuid4().hex[:6]}", f"casc117k{uuid.uuid4().hex[:6]}"
    for video_id in (doomed, kept):
        await seed_video(db_session, video_id)
        seg_a = await seed_segment(db_session, video_id, "en", 10.0, 0)
        seg_b = await seed_segment(db_session, video_id, "en", 20.0, 1)
        lo, hi = canonical(a, b)
        await repo.insert_instances(
            db_session,
            instances=[
                EntityPairProximityCreate(
                    entity_a_id=lo,
                    entity_b_id=hi,
                    video_id=video_id,
                    language_code="en",
                    segment_a_id=seg_a,
                    segment_b_id=seg_b,
                    gap_seconds=10.0,
                )
            ],
        )
        await seed_scope_state(
            db_session, video_id=video_id, language_code="en", state="current"
        )
    await db_session.commit()

    await db_session.execute(
        delete(VideoTranscriptDB).where(VideoTranscriptDB.video_id == doomed)
    )
    await db_session.commit()
    assert await _video_records(db_session, doomed) == 0
    assert await _video_records(db_session, kept) == 1, "cascade over-deleted"

    await db_session.execute(delete(VideoDB).where(VideoDB.video_id == doomed))
    await db_session.commit()
    states = await db_session.scalar(
        select(func.count())
        .select_from(ProximityScopeStateDB)
        .where(ProximityScopeStateDB.video_id == doomed)
    )
    assert states == 0, "the video's scope state outlived it"
    # the derived read now counts only the surviving video for the pair
    derived = await repo.read_rollup(db_session, min_shared_videos=1)
    assert [shared for _a, _b, shared, _gap in derived] == [1]


async def test_deleting_a_segment_cascades_the_records_that_cite_it(
    db_session: AsyncSession,
) -> None:
    """FR-011: a record citing a deleted segment cannot survive (both FKs cascade)."""
    repo = EntityPairProximityRepository()
    a, b = await seed_entity(db_session), await seed_entity(db_session)
    video_id = f"casc117s{uuid.uuid4().hex[:6]}"
    await seed_video(db_session, video_id)
    seg_a = await seed_segment(db_session, video_id, "en", 10.0, 0)
    seg_b = await seed_segment(db_session, video_id, "en", 20.0, 1)
    seg_c = await seed_segment(db_session, video_id, "en", 30.0, 2)
    lo, hi = canonical(a, b)
    await repo.insert_instances(
        db_session,
        instances=[
            EntityPairProximityCreate(
                entity_a_id=lo,
                entity_b_id=hi,
                video_id=video_id,
                language_code="en",
                segment_a_id=seg_a,
                segment_b_id=seg_b,
                gap_seconds=10.0,
            ),
            EntityPairProximityCreate(
                entity_a_id=lo,
                entity_b_id=hi,
                video_id=video_id,
                language_code="en",
                segment_a_id=seg_c,
                segment_b_id=seg_b,
                gap_seconds=10.0,
            ),
        ],
    )
    await db_session.commit()

    await db_session.execute(
        delete(TranscriptSegmentDB).where(TranscriptSegmentDB.id == seg_a)
    )
    await db_session.commit()

    assert await _video_records(db_session, video_id) == 1
