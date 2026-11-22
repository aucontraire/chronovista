"""Dirty-scope round-trip for the proximity freshness queue (Feature 116, T017).

Crosses the real seam: ``mark_dirty`` writes ``proximity_dirty_scopes``, then
``drain_dirty_scopes`` recomputes through the real computor and clears the row.
Assertions are on persisted instance / queue rows, never on a mock's return.

Each test first asserts the stale state is still visible BEFORE the drain, so a
passing "after" assertion cannot be satisfied by the seed alone.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import EntityPairProximity as EntityPairProximityDB
from chronovista.db.models import ProximityDirtyScope as ProximityDirtyScopeDB
from chronovista.repositories.entity_pair_proximity_repository import (
    EntityPairProximityRepository,
)
from chronovista.services.proximity_service import (
    SUPPORT_MIN,
    drain_dirty_scopes,
    rebuild_proximity,
)
from tests.factories.proximity_seed import (
    canonical,
    route_proximity_service_to,
    seed_entity,
    seed_mention,
    seed_segment,
    seed_video,
)

pytestmark = pytest.mark.asyncio

_LANG = "en"


def _videos(prefix: str, count: int) -> list[str]:
    return [f"{prefix}{n:02d}" for n in range(count)]


async def _pair_instances(
    session: AsyncSession,
    pair: tuple[uuid.UUID, uuid.UUID],
    video_id: str | None = None,
) -> int:
    stmt = (
        select(func.count())
        .select_from(EntityPairProximityDB)
        .where(
            EntityPairProximityDB.entity_a_id == pair[0],
            EntityPairProximityDB.entity_b_id == pair[1],
        )
    )
    if video_id is not None:
        stmt = stmt.where(EntityPairProximityDB.video_id == video_id)
    return int((await session.execute(stmt)).scalar_one())


async def _dirty_count(session: AsyncSession, video_id: str) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(ProximityDirtyScopeDB)
                .where(ProximityDirtyScopeDB.video_id == video_id)
            )
        ).scalar_one()
    )


async def _seed_corpus(
    session: AsyncSession,
    videos: list[str],
    entities: list[tuple[uuid.UUID, float]],
    skip: set[tuple[uuid.UUID, str]] | None = None,
) -> None:
    """Every video gets one segment + mention per (entity, start_time)."""
    skip = skip or set()
    for video_id in videos:
        await seed_video(session, video_id, (_LANG,))
        for sequence, (entity_id, start) in enumerate(entities):
            if (entity_id, video_id) in skip:
                continue
            segment = await seed_segment(session, video_id, _LANG, start, sequence)
            await seed_mention(
                session,
                entity_id=entity_id,
                video_id=video_id,
                language_code=_LANG,
                segment_id=segment,
            )


class TestAdditiveCorrectionShape:
    async def test_new_close_pair_appears_after_dirty_drain(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A correction adds a mention that forms a NEW close pair.

        C is mentioned far from A in the first SUPPORT_MIN-1 videos (counts
        toward support, yields no instance: gap > window), so (A, C) is one
        shared video short of scope. Adding C next to A in the last video
        tips support to SUPPORT_MIN AND creates the close instance.
        """
        a = await seed_entity(db_session)
        b = await seed_entity(db_session)
        c = await seed_entity(db_session)
        videos = _videos("inv116add", SUPPORT_MIN)
        target = videos[-1]
        await _seed_corpus(
            db_session,
            videos,
            [(a, 10.0), (b, 20.0), (c, 500.0)],
            skip={(c, target)},
        )
        await db_session.commit()
        route_proximity_service_to(monkeypatch, db_session)
        await rebuild_proximity(video_ids=videos)

        ab, ac = canonical(a, b), canonical(a, c)
        assert await _pair_instances(db_session, ab) == SUPPORT_MIN
        assert await _pair_instances(db_session, ac) == 0, "precondition"

        # The correction: C now appears 5s from A in the target video.
        segment = await seed_segment(db_session, target, _LANG, 15.0, 9)
        await seed_mention(
            db_session,
            entity_id=c,
            video_id=target,
            language_code=_LANG,
            segment_id=segment,
        )
        await EntityPairProximityRepository().mark_dirty(
            db_session, video_id=target, language_code=_LANG, reason="correction"
        )
        await db_session.commit()

        assert await _dirty_count(db_session, target) == 1
        assert (
            await _pair_instances(db_session, ac) == 0
        ), "recompute happened before the drain - test proves nothing"

        summary = await drain_dirty_scopes()

        assert await _dirty_count(db_session, target) == 0, "dirty row not cleared"
        assert await _pair_instances(db_session, ac, target) == 1
        assert await _pair_instances(db_session, canonical(b, c), target) == 1
        assert await _pair_instances(db_session, ab) == SUPPORT_MIN
        assert summary["scopes_drained"] == 1
        # target video recomputed: AB + AC + BC, one instance each.
        assert summary["instances_written"] == 3


class TestAddAndRemoveScanShape:
    async def _seed_pair_corpus(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[uuid.UUID, uuid.UUID, list[str]]:
        a = await seed_entity(session)
        b = await seed_entity(session)
        # One spare video so removing A from one still leaves SUPPORT_MIN.
        videos = _videos("inv116scn", SUPPORT_MIN + 1)
        await _seed_corpus(session, videos, [(a, 10.0), (b, 20.0)])
        await session.commit()
        route_proximity_service_to(monkeypatch, session)
        await rebuild_proximity(video_ids=videos)
        assert await _pair_instances(session, canonical(a, b)) == SUPPORT_MIN + 1
        return a, b, videos

    async def test_removed_mention_drops_stale_instance(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b, videos = await self._seed_pair_corpus(db_session, monkeypatch)
        target = videos[-1]
        pair = canonical(a, b)

        await db_session.execute(
            delete(EntityMentionDB).where(
                EntityMentionDB.entity_id == a, EntityMentionDB.video_id == target
            )
        )
        await EntityPairProximityRepository().mark_dirty(
            db_session, video_id=target, language_code=_LANG, reason="scan"
        )
        await db_session.commit()

        assert (
            await _pair_instances(db_session, pair, target) == 1
        ), "stale instance should persist until the drain"

        summary = await drain_dirty_scopes()

        assert await _pair_instances(db_session, pair, target) == 0
        assert (
            await _pair_instances(db_session, pair) == SUPPORT_MIN
        ), "untouched videos must not be recomputed away"
        assert await _dirty_count(db_session, target) == 0
        assert summary == {"scopes_drained": 1, "instances_written": 0}

    async def test_relocated_mention_replaces_instance_with_nothing(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Scan removes A's close mention and adds one far away (add + remove).

        Delete-then-reinsert semantics: the old close instance goes, and the
        new far mention (gap > window) contributes no replacement.
        """
        a, b, videos = await self._seed_pair_corpus(db_session, monkeypatch)
        target = videos[-1]
        pair = canonical(a, b)

        await db_session.execute(
            delete(EntityMentionDB).where(
                EntityMentionDB.entity_id == a, EntityMentionDB.video_id == target
            )
        )
        far = await seed_segment(db_session, target, _LANG, 900.0, 9)
        await seed_mention(
            db_session,
            entity_id=a,
            video_id=target,
            language_code=_LANG,
            segment_id=far,
        )
        await EntityPairProximityRepository().mark_dirty(
            db_session, video_id=target, language_code=_LANG, reason="scan"
        )
        await db_session.commit()

        summary = await drain_dirty_scopes()

        assert await _pair_instances(db_session, pair, target) == 0
        assert await _pair_instances(db_session, pair) == SUPPORT_MIN
        assert summary == {"scopes_drained": 1, "instances_written": 0}
