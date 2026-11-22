"""Entity-delete cascade for the proximity tables (T016).

Both proximity tables declare ``entity_*_id ... ON DELETE CASCADE`` to
``named_entities``. Nothing in application code deletes through that path in
the proximity flow, so without this test "it's in the schema" is an unchecked
claim. This crosses the real FK: delete the entity row, assert BOTH the
instance rows and the rollup row are gone, and that an unrelated pair survives
(so the cascade is scoped rather than a table wipe).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityPairProximity as EntityPairProximityDB
from chronovista.db.models import EntityPairProximityRollup as RollupDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.entity_pair_proximity import EntityPairProximityCreate
from chronovista.repositories.entity_pair_proximity_repository import (
    EntityPairProximityRepository,
)
from tests.factories.proximity_seed import (
    canonical,
    seed_entity,
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
    """Two instances + one rollup row for ``pair`` on the shared video."""
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
    await repo.rebuild_rollup_for_pairs(session, pairs=[pair], windows=(15, 30, 60))


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
    rollups = await session.scalar(
        select(func.count())
        .select_from(RollupDB)
        .where(
            or_(RollupDB.entity_a_id == entity_id, RollupDB.entity_b_id == entity_id)
        )
    )
    return int(instances or 0), int(rollups or 0)


async def test_deleting_an_entity_cascades_instances_and_rollup(
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
