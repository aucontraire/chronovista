"""Integration tests for ``GET /api/v1/graph/connect/passages`` (Feature 118).

Every case crosses the real HTTP boundary (ASGITransport) and the real database: the
co-mentions are measured through the production ``replace_scope_records`` path (so the
shared qualification rule and exclusions apply), then read and grouped exactly as the
panel reads them. The passage rule's own properties are unit-tested in
``tests/unit/services/test_passage_rule.py``; these test it end to end.
All data is synthetic (placeholder entities, generated video ids) and removed afterwards.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import EntityPairProximity as EntityPairProximityDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import ProximityScopeState as ProximityScopeStateDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import UserLanguagePreference as UserLanguagePreferenceDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from tests.factories.proximity_seed import (
    measure_scope,
    seed_entity,
    seed_exclusion,
    seed_mention,
    seed_preference,
    seed_scope_state,
    seed_segment,
    seed_timed_comentions,
    seed_title_mention,
    seed_video,
)

pytestmark = pytest.mark.asyncio

URL = "/api/v1/graph/connect/passages"
_RUN = uuid.uuid4().hex[:6]


class World:
    """Seeds committed, self-cleaning data and remembers what to remove."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory
        self.entities: list[uuid.UUID] = []
        self.videos: list[str] = []
        self.user_id = f"test-{_RUN}"
        self._n = 0

    def video_id(self) -> str:
        self._n += 1
        video_id = f"p{_RUN}{self._n:03d}"
        self.videos.append(video_id)
        return video_id

    async def pair(self, *, a_is_lo: bool | None = None) -> tuple[uuid.UUID, uuid.UUID]:
        """Two fresh entities. ``a_is_lo`` fixes which one the records store first
        (canonical order); by default it is whatever the ids happen to sort to."""
        async with self.factory() as session:
            a = await seed_entity(session, unique=True)
            b = await seed_entity(session, unique=True)
            await session.commit()
        self.entities += [a, b]
        if a_is_lo is not None and (a < b) != a_is_lo:
            a, b = b, a
        return a, b

    async def entity(self) -> uuid.UUID:
        async with self.factory() as session:
            entity_id = await seed_entity(session, unique=True)
            await session.commit()
        self.entities.append(entity_id)
        return entity_id

    async def comentions(
        self,
        a: uuid.UUID,
        b: uuid.UUID,
        moments: Sequence[tuple[float, float]],
        *,
        video_id: str | None = None,
        language_code: str = "en",
        create_video: bool = True,
    ) -> str:
        video_id = video_id or self.video_id()
        async with self.factory() as session:
            await seed_timed_comentions(
                session,
                entity_a=a,
                entity_b=b,
                video_id=video_id,
                moments=moments,
                language_code=language_code,
                create_video=create_video,
            )
            await session.commit()
        return video_id

    async def prefer(self, *preferences: tuple[str, str, int]) -> str:
        """Seed this test user's language preferences: (language, type, priority)."""
        async with self.factory() as session:
            for language_code, preference_type, priority in preferences:
                await seed_preference(
                    session,
                    user_id=self.user_id,
                    language_code=language_code,
                    preference_type=preference_type,
                    priority=priority,
                )
            await session.commit()
        return self.user_id

    async def cleanup(self) -> None:
        async with self.factory() as session:
            await session.execute(
                delete(UserLanguagePreferenceDB).where(
                    UserLanguagePreferenceDB.user_id == self.user_id
                )
            )
            await session.execute(
                delete(ProximityScopeStateDB).where(
                    ProximityScopeStateDB.video_id.in_(self.videos)
                )
            )
            # Entity delete cascades mentions, exclusions and proximity rows.
            await session.execute(
                delete(NamedEntityDB).where(NamedEntityDB.id.in_(self.entities))
            )
            await session.execute(
                delete(TranscriptSegmentDB).where(
                    TranscriptSegmentDB.video_id.in_(self.videos)
                )
            )
            await session.execute(
                delete(VideoTranscriptDB).where(
                    VideoTranscriptDB.video_id.in_(self.videos)
                )
            )
            await session.execute(
                delete(VideoDB).where(VideoDB.video_id.in_(self.videos))
            )
            await session.commit()


@pytest.fixture
async def world(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[World]:
    w = World(integration_session_factory)
    try:
        yield w
    finally:
        await w.cleanup()


async def _get(
    client: AsyncClient, a: uuid.UUID, b: uuid.UUID, **params: Any
) -> dict[str, Any]:
    resp = await client.get(URL, params={"a": str(a), "b": str(b), **params})
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


def _only_video(body: dict[str, Any]) -> dict[str, Any]:
    assert body["video_count"] == 1, body
    item: dict[str, Any] = body["items"][0]
    return item


class TestPassages:
    async def test_two_separate_discussions_are_two_passages(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await world.comentions(a, b, [(10, 12), (700, 702)])
        body = await _get(async_client, a, b)
        video = _only_video(body)
        assert body["passage_count"] == 2
        assert [p["start_time"] for p in video["passages"]] == [10.0, 700.0]

    async def test_dense_repetition_is_one_passage(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        video_id = await world.comentions(
            a, b, [(2.0 * i, 2.0 * i + 1) for i in range(20)]
        )
        video = _only_video(await _get(async_client, a, b))
        (passage,) = video["passages"]
        (variant,) = passage["variants"]
        # A co-mention is one proximity record: every A/B mention pair within the window,
        # so dense repetition holds far more co-mentions than moments, in ONE passage.
        async with world.factory() as session:
            records = (
                await session.execute(
                    select(func.count()).where(
                        EntityPairProximityDB.video_id == video_id,
                        EntityPairProximityDB.gap_seconds <= 30,
                    )
                )
            ).scalar_one()
        assert records > 20
        assert variant["co_mention_count"] == records
        assert len(variant["other_moments"]) == min(
            records - 1, 50
        )  # listed up to a cap

    async def test_a_sustained_discussion_chains_into_one_long_passage(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await world.comentions(a, b, [(float(t), t + 1.0) for t in range(0, 601, 25)])
        video = _only_video(await _get(async_client, a, b, window=30))
        (passage,) = video["passages"]
        assert passage["start_time"] == 0.0
        assert passage["end_time"] >= 600.0

    async def test_chaining_joins_at_exactly_the_window_after_the_end(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        # One-segment co-mentions: the first ends at 2.0 (segments last 2 s). A start
        # at 2.0 + 30 joins; a start just past it opens a new passage (FR-001).
        joined = await world.comentions(a, b, [(0, 0), (32.0, 32.0)])
        split = await world.comentions(a, b, [(0, 0), (32.001, 32.001)])
        body = await _get(async_client, a, b, window=30)
        by_video = {v["video_id"]: v for v in body["items"]}
        assert len(by_video[joined]["passages"]) == 1
        assert len(by_video[split]["passages"]) == 2

    async def test_seconds_decide_order_when_segment_order_disagrees(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        # The later moment is seeded first, so it holds the lower sequence numbers.
        await world.comentions(a, b, [(100, 101), (10, 11)])
        video = _only_video(await _get(async_client, a, b))
        assert [p["start_time"] for p in video["passages"]] == [10.0, 100.0]

    @pytest.mark.parametrize("a_is_lo", [True, False])
    async def test_cross_segment_mention_extends_the_interval_and_shows_context(
        self, async_client: AsyncClient, world: World, a_is_lo: bool
    ) -> None:
        a, b = await world.pair(a_is_lo=a_is_lo)
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id)
            a_start = await seed_segment(session, video_id, "en", 10.0, 0)
            b_seg = await seed_segment(session, video_id, "en", 14.0, 1)
            a_end = await seed_segment(
                session, video_id, "en", 30.0, 2, text="end of A"
            )
            await seed_segment(session, video_id, "en", 40.0, 3, text="context after")
            await seed_mention(
                session,
                entity_id=a,
                video_id=video_id,
                language_code="en",
                segment_id=a_start,
                end_segment_id=a_end,
            )
            await seed_mention(
                session,
                entity_id=b,
                video_id=video_id,
                language_code="en",
                segment_id=b_seg,
            )
            await measure_scope(session, video_id=video_id, language_code="en")
            await session.commit()
        video = _only_video(await _get(async_client, a, b))
        (passage,) = video["passages"]
        variant = passage["variants"][0]
        assert variant["end_time"] == 32.0  # A's end segment ends at 30 + 2
        segments = variant["closest"]["segments"]
        # Each segment's position in its transcript, so the panel can mark omitted text.
        assert [s["sequence_number"] for s in segments] == [0, 1, 2, 3]
        assert [s["text"] for s in segments if s["is_context"]] == ["context after"]
        assert "end of A" in [s["text"] for s in segments if not s["is_context"]]
        # The player link's target: the earlier mention's start segment and time (FR-003).
        closest = variant["closest"]
        assert closest["segment_id"] == a_start and closest["start_time"] == 10.0
        assert closest["gap_seconds"] == 4.0
        assert closest["mention_a"]["segment_id"] == a_start
        assert video["video_title"] == f"Placeholder {video_id}"

    @pytest.mark.parametrize("a_is_lo", [True, False])
    async def test_a_rejected_mention_never_stretches_or_highlights(
        self, async_client: AsyncClient, world: World, a_is_lo: bool
    ) -> None:
        a, b = await world.pair(a_is_lo=a_is_lo)
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id)
            a_seg = await seed_segment(session, video_id, "en", 10.0, 0)
            b_seg = await seed_segment(session, video_id, "en", 12.0, 1)
            far = await seed_segment(session, video_id, "en", 90.0, 2)
            await seed_mention(
                session,
                entity_id=a,
                video_id=video_id,
                language_code="en",
                segment_id=a_seg,
            )
            # Same entity, same segment, text that is not a visible name: the shared rule
            # rejects it. It "ends" far away; it must not stretch the passage.
            await seed_mention(
                session,
                entity_id=a,
                video_id=video_id,
                language_code="en",
                segment_id=a_seg,
                end_segment_id=far,
                mention_text="not a name",
            )
            await seed_mention(
                session,
                entity_id=b,
                video_id=video_id,
                language_code="en",
                segment_id=b_seg,
            )
            await measure_scope(session, video_id=video_id, language_code="en")
            await session.commit()
        video = _only_video(await _get(async_client, a, b))
        variant = video["passages"][0]["variants"][0]
        assert variant["end_time"] == 14.0
        assert variant["closest"]["mention_a"]["mention_text"] != "not a name"

    async def test_corrected_text_is_shown(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        video_id = await world.comentions(a, b, [(10, 12)])
        async with world.factory() as session:
            await session.execute(
                update(TranscriptSegmentDB)
                .where(
                    TranscriptSegmentDB.video_id == video_id,
                    TranscriptSegmentDB.start_time == 12.0,
                )
                .values(has_correction=True, corrected_text="corrected wording")
            )
            await session.commit()
        video = _only_video(await _get(async_client, a, b))
        texts = [
            s["text"]
            for s in video["passages"][0]["variants"][0]["closest"]["segments"]
        ]
        assert "corrected wording" in texts

    async def test_an_exclusion_hides_the_video_even_before_recompute(
        self, async_client: AsyncClient, world: World
    ) -> None:
        # Measured first, excluded afterwards: the records still exist until the scope is
        # recomputed, so it is the panel's own read that must leave the video out (FR-009).
        a, b = await world.pair()
        await world.comentions(a, b, [(10, 12)])
        excluded = await world.comentions(a, b, [(10, 13)])
        far = await world.comentions(a, b, [(10, 400)])
        async with world.factory() as session:
            await seed_exclusion(session, entity_id=a, video_id=excluded)
            await seed_exclusion(session, entity_id=a, video_id=far)
            await session.commit()
        body = await _get(async_client, a, b)
        assert excluded not in {v["video_id"] for v in body["items"]}
        assert body["video_count"] == 1
        assert body["farther_video_count"] == 0
        farther = (
            await async_client.get(FARTHER, params={"a": str(a), "b": str(b)})
        ).json()
        assert farther["total"] == 0

    async def test_a_deleted_mention_drops_its_video_before_recompute(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        kept = await world.comentions(a, b, [(10, 12)])
        gone = await world.comentions(a, b, [(10, 13)])
        async with world.factory() as session:
            await session.execute(
                delete(EntityMentionDB).where(
                    EntityMentionDB.video_id == gone, EntityMentionDB.entity_id == a
                )
            )
            await session.commit()
        await _set_scope(world, gone, "stale")
        body = await _get(async_client, a, b)
        assert [v["video_id"] for v in body["items"]] == [kept]
        assert (
            body["pending_scopes"] == 1
        )  # disclosed as updating, never silently final

    async def test_every_passage_of_a_video_is_returned(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await world.comentions(a, b, [(100.0 * i, 100.0 * i + 1) for i in range(8)])
        video = _only_video(await _get(async_client, a, b))
        assert len(video["passages"]) == 8

    async def test_videos_are_ordered_closest_first_then_by_id(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        far = await world.comentions(a, b, [(10, 15)])
        near = await world.comentions(a, b, [(10, 11)])
        tied = await world.comentions(a, b, [(10, 11)])
        body = await _get(async_client, a, b)
        assert [v["video_id"] for v in body["items"]] == [near, tied, far]
        assert body["closest_gap_seconds"] == 1.0

    async def test_swapping_the_pair_swaps_only_the_mentions(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await world.comentions(a, b, [(10, 12), (500, 503)])
        forward = await _get(async_client, a, b)
        backward = await _get(async_client, b, a)
        for key in (
            "video_count",
            "passage_count",
            "channel_count",
            "closest_gap_seconds",
        ):
            assert forward[key] == backward[key]
        f_moment = forward["items"][0]["passages"][0]["variants"][0]["closest"]
        b_moment = backward["items"][0]["passages"][0]["variants"][0]["closest"]
        assert f_moment["mention_a"] == b_moment["mention_b"]
        assert f_moment["mention_a"]["start_time"] == 10.0

    async def test_the_old_evidence_endpoint_still_answers(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await world.comentions(a, b, [(10, 12)])
        resp = await async_client.get(
            "/api/v1/graph/connect/evidence", params={"a": str(a), "b": str(b)}
        )
        assert resp.status_code == 200
        assert resp.json()["total_available"] == 1


class TestWindow:
    async def test_each_window_admits_exactly_the_gaps_within_it(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        for gap in (10.0, 25.0, 50.0, 100.0):
            await world.comentions(a, b, [(100.0, 100.0 + gap)])
        counts = {
            window: (await _get(async_client, a, b, window=window))["video_count"]
            for window in (15, 30, 60, 120)
        }
        assert counts == {15: 1, 30: 2, 60: 3, 120: 4}

    async def test_a_gap_equal_to_the_window_qualifies(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await world.comentions(a, b, [(10.0, 40.0)])
        assert (await _get(async_client, a, b, window=30))["video_count"] == 1
        assert (await _get(async_client, a, b, window=15))["video_count"] == 0

    async def test_a_wider_window_merges_passages(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        # Two discussions 50 s apart: separate at 15 s, chained at 60 s.
        await world.comentions(a, b, [(10.0, 11.0), (63.0, 64.0)])
        narrow = _only_video(await _get(async_client, a, b, window=15))
        wide = _only_video(await _get(async_client, a, b, window=60))
        assert len(narrow["passages"]) == 2
        assert len(wide["passages"]) == 1

    async def test_the_default_window_is_30_seconds(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await world.comentions(a, b, [(10.0, 11.0)])
        assert (await _get(async_client, a, b))["window_seconds"] == 30


class TestValidation:
    async def test_same_entity_twice_is_422(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, _ = await world.pair()
        resp = await async_client.get(URL, params={"a": str(a), "b": str(a)})
        assert resp.status_code == 422

    async def test_unknown_entity_is_404(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, _ = await world.pair()
        resp = await async_client.get(URL, params={"a": str(a), "b": str(uuid.uuid4())})
        assert resp.status_code == 404

    @pytest.mark.parametrize("window", ["45", "0", "abc"])
    async def test_unsupported_window_is_422(
        self, async_client: AsyncClient, world: World, window: str
    ) -> None:
        a, b = await world.pair()
        resp = await async_client.get(
            URL, params={"a": str(a), "b": str(b), "window": window}
        )
        assert resp.status_code == 422
        # Every bad window fails request validation the same way, naming the parameter.
        locations = [e["loc"] for e in resp.json()["errors"]]
        assert ["query", "window"] in locations


def _as_user(monkeypatch: pytest.MonkeyPatch, user_id: str | None) -> None:
    """Resolve the request's identity to ``user_id`` (``None``: no identity established).

    The identity table is a singleton on the shared integration DB, so tests substitute
    only this lookup; the preferences themselves are seeded and read for real.
    """

    async def resolve(session: AsyncSession) -> str | None:
        return user_id

    monkeypatch.setattr(
        "chronovista.api.routers.connection_evidence.optional_local_identity", resolve
    )


class TestLanguages:
    async def test_parallel_languages_are_one_grouped_passage(
        self, async_client: AsyncClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _as_user(monkeypatch, None)
        a, b = await world.pair()
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id, ("en", "es"))
            await session.commit()
        await world.comentions(a, b, [(10, 12)], video_id=video_id, create_video=False)
        await world.comentions(
            a, b, [(11, 13)], video_id=video_id, language_code="es", create_video=False
        )
        body = await _get(async_client, a, b)
        video = _only_video(body)
        (passage,) = video["passages"]
        assert sorted(v["language_code"] for v in passage["variants"]) == ["en", "es"]
        assert body["passage_count"] == 1

    async def test_unequal_boundaries_group_transitively(
        self, async_client: AsyncClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _as_user(monkeypatch, None)
        a, b = await world.pair()
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id, ("en", "es"))
            await session.commit()
        # English splits into two passages (60 s apart at 15 s); Spanish spans both.
        await world.comentions(
            a, b, [(10, 11), (70, 71)], video_id=video_id, create_video=False
        )
        await world.comentions(
            a,
            b,
            [(float(t), t + 1.0) for t in range(12, 80, 10)],
            video_id=video_id,
            language_code="es",
            create_video=False,
        )
        body = await _get(async_client, a, b, window=15)
        (passage,) = _only_video(body)["passages"]
        assert sorted(v["language_code"] for v in passage["variants"]) == [
            "en",
            "en",
            "es",
        ]
        assert body["passage_count"] == 1

    async def test_a_covered_translation_changes_no_count(
        self, async_client: AsyncClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _as_user(monkeypatch, None)
        a, b = await world.pair()
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id, ("en", "es"))
            await session.commit()
        await world.comentions(
            a, b, [(10, 12), (500, 502)], video_id=video_id, create_video=False
        )
        before = await _get(async_client, a, b)
        await world.comentions(
            a,
            b,
            [(11, 13), (501, 503)],
            video_id=video_id,
            language_code="es",
            create_video=False,
        )
        after = await _get(async_client, a, b)
        for key in ("video_count", "passage_count", "channel_count"):
            assert before[key] == after[key]

    async def test_the_preferred_language_leads_even_when_farther(
        self, async_client: AsyncClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b = await world.pair()
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id, ("en", "es-MX"))
            await session.commit()
        await world.comentions(a, b, [(10, 11)], video_id=video_id, create_video=False)
        await world.comentions(
            a,
            b,
            [(10, 15)],
            video_id=video_id,
            language_code="es-MX",
            create_video=False,
        )
        _as_user(monkeypatch, None)
        unpreferred = _only_video(await _get(async_client, a, b))
        _as_user(monkeypatch, await world.prefer(("es", "fluent", 1)))
        preferred = _only_video(await _get(async_client, a, b))
        lead = lambda v: v["passages"][0]["variants"][0]["language_code"]  # noqa: E731
        assert lead(unpreferred) == "en"  # closest wins without preferences
        assert lead(preferred) == "es-MX"  # base-language match, even though farther
        # The leading variant never changes the counts or the closest gap.
        assert (
            unpreferred["closest_gap_seconds"]
            == preferred["closest_gap_seconds"]
            == 1.0
        )
        assert unpreferred["passages"][0]["closest_gap_seconds"] == 1.0
        assert preferred["passages"][0]["closest_gap_seconds"] == 1.0

    async def test_fluent_outranks_learning_and_curious_never_promotes(
        self, async_client: AsyncClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b = await world.pair()
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id, ("en", "fr", "de"))
            await session.commit()
        await world.comentions(a, b, [(10, 11)], video_id=video_id, create_video=False)
        await world.comentions(
            a, b, [(10, 13)], video_id=video_id, language_code="fr", create_video=False
        )
        await world.comentions(
            a, b, [(10, 17)], video_id=video_id, language_code="de", create_video=False
        )
        _as_user(
            monkeypatch,
            await world.prefer(
                ("en", "curious", 1), ("fr", "learning", 2), ("de", "fluent", 3)
            ),
        )
        video = _only_video(await _get(async_client, a, b))
        order = [v["language_code"] for v in video["passages"][0]["variants"]]
        assert order == ["de", "fr", "en"]

    async def test_no_identity_answers_200_in_closest_order(
        self, async_client: AsyncClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _as_user(monkeypatch, None)
        a, b = await world.pair()
        await world.comentions(a, b, [(10, 12)])
        resp = await async_client.get(URL, params={"a": str(a), "b": str(b)})
        assert resp.status_code == 200


async def _set_scope(
    world: World,
    video_id: str,
    state: str,
    *,
    attempts: int = 0,
    language_code: str = "en",
) -> None:
    async with world.factory() as session:
        await session.execute(
            delete(ProximityScopeStateDB).where(
                ProximityScopeStateDB.video_id == video_id,
                ProximityScopeStateDB.language_code == language_code,
            )
        )
        await seed_scope_state(
            session,
            video_id=video_id,
            language_code=language_code,
            state=state,
            attempts=attempts,
        )
        await session.commit()


async def _spoken_only(world: World, a: uuid.UUID, b: uuid.UUID, gap: float) -> str:
    """Both entities spoken in one video, ``gap`` seconds apart, measured."""
    return await world.comentions(a, b, [(10.0, 10.0 + gap)])


class TestSummaryAndState:
    async def test_counts_cover_every_page(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        for _ in range(3):
            await world.comentions(a, b, [(10, 12), (500, 503)])
        first = await _get(async_client, a, b, limit=1, offset=0)
        last = await _get(async_client, a, b, limit=1, offset=2)
        for key in (
            "video_count",
            "passage_count",
            "channel_count",
            "closest_gap_seconds",
        ):
            assert first[key] == last[key]
        assert first["video_count"] == 3 and first["passage_count"] == 6
        assert first["truncated"] is True and last["truncated"] is False

    async def test_videos_without_a_channel_count_as_one_unknown_channel(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await world.comentions(a, b, [(10, 12)])
        await world.comentions(a, b, [(10, 13)])
        assert (await _get(async_client, a, b))["channel_count"] == 1

    async def test_pending_transcripts_never_read_as_zero(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        video_id = await world.comentions(a, b, [(10, 12)])
        await _set_scope(world, video_id, "stale")
        body = await _get(async_client, a, b)
        assert body["state"] == "passages" and body["pending_scopes"] == 1

    async def test_no_qualifying_mention_and_pending_is_not_computed(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id)
            segment = await seed_segment(session, video_id, "en", 10.0, 0)
            await seed_mention(
                session,
                entity_id=a,
                video_id=video_id,
                language_code="en",
                segment_id=segment,
            )
            await seed_mention(
                session,
                entity_id=b,
                video_id=video_id,
                language_code="en",
                segment_id=segment,
                mention_text="not a name",
            )
            await seed_scope_state(
                session, video_id=video_id, language_code="en", state="not_computed"
            )
            await session.commit()
        body = await _get(async_client, a, b)
        assert body["state"] == "not_computed"
        assert body["video_count"] == 0

    async def test_never_spoken_together_names_the_other_basis(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        body = await _get(async_client, a, b)
        assert body["state"] == "no_transcript"
        assert body["pending_scopes"] == 0

    async def test_spoken_but_never_close_is_no_passage_in_window(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await _spoken_only(world, a, b, 300.0)
        body = await _get(async_client, a, b)
        assert body["state"] == "no_passage_in_window"
        assert body["farther_video_count"] == 1
        assert body["video_count"] == 0

    async def test_spoken_but_pending_is_not_computed(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        video_id = await _spoken_only(world, a, b, 300.0)
        await _set_scope(world, video_id, "not_computed")
        assert (await _get(async_client, a, b))["state"] == "not_computed"

    async def test_failed_is_reported_apart_from_pending(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        failed = await _spoken_only(world, a, b, 300.0)
        retrying = await _spoken_only(world, a, b, 400.0)
        await _set_scope(world, failed, "failing", attempts=3)
        await _set_scope(world, retrying, "failing", attempts=2)
        body = await _get(async_client, a, b)
        assert [f["video_id"] for f in body["failed_scopes"]] == [failed]
        assert body["failed_scopes"][0]["language_code"] == "en"
        assert body["pending_scopes"] == 1  # two attempts is still retrying, so pending
        assert body["state"] == "not_computed"

    async def test_only_failed_transcripts_never_read_as_updating(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        failed = await _spoken_only(world, a, b, 300.0)
        await _set_scope(world, failed, "failing", attempts=3)
        body = await _get(async_client, a, b)
        assert body["pending_scopes"] == 0
        assert len(body["failed_scopes"]) == 1
        assert body["state"] == "no_passage_in_window"

    async def test_a_recovered_scope_leaves_the_failed_list(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        video_id = await world.comentions(a, b, [(10, 12)])
        await _set_scope(world, video_id, "failing", attempts=3)
        assert len((await _get(async_client, a, b))["failed_scopes"]) == 1
        async with world.factory() as session:
            await measure_scope(session, video_id=video_id, language_code="en")
            await session.commit()
        body = await _get(async_client, a, b)
        assert body["failed_scopes"] == [] and body["pending_scopes"] == 0
        assert body["video_count"] == 1


FARTHER = "/api/v1/graph/connect/passages/farther"


class TestFarther:
    async def test_lists_far_videos_nearest_first_and_matches_the_count(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await world.comentions(a, b, [(10, 12)])  # within the window: not listed
        far = await _spoken_only(world, a, b, 300.0)
        nearer = await _spoken_only(world, a, b, 80.0)  # recorded at 120 s, not at 30 s
        resp = await async_client.get(FARTHER, params={"a": str(a), "b": str(b)})
        assert resp.status_code == 200
        body = resp.json()
        assert [v["video_id"] for v in body["items"]] == [nearer, far]
        assert [v["nearest_gap_seconds"] for v in body["items"]] == [80.0, 300.0]
        assert body["items"][0]["nearest_start_time"] == 10.0
        assert body["total"] == (await _get(async_client, a, b))["farther_video_count"]

    async def test_a_wider_window_moves_a_video_into_the_passages(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await _spoken_only(world, a, b, 80.0)
        resp = await async_client.get(
            FARTHER, params={"a": str(a), "b": str(b), "window": 120}
        )
        assert resp.json()["total"] == 0
        assert (await _get(async_client, a, b, window=120))["video_count"] == 1

    async def test_both_spoken_only_in_different_languages_is_not_farther(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id, ("en", "es"))
            sa = await seed_segment(session, video_id, "en", 10.0, 0)
            sb = await seed_segment(session, video_id, "es", 500.0, 0)
            await seed_mention(
                session,
                entity_id=a,
                video_id=video_id,
                language_code="en",
                segment_id=sa,
            )
            await seed_mention(
                session,
                entity_id=b,
                video_id=video_id,
                language_code="es",
                segment_id=sb,
            )
            await session.commit()
        resp = await async_client.get(FARTHER, params={"a": str(a), "b": str(b)})
        assert resp.json()["total"] == 0

    async def test_validates_like_the_passages_endpoint(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        assert (
            await async_client.get(FARTHER, params={"a": str(a), "b": str(a)})
        ).status_code == 422
        assert (
            await async_client.get(
                FARTHER, params={"a": str(a), "b": str(b), "window": 45}
            )
        ).status_code == 422


class TestNameLists:
    async def _segment_naming(
        self, world: World, a: uuid.UUID, b: uuid.UUID, others: int
    ) -> str:
        """One segment naming A, B and ``others`` more entities, measured."""
        extra = []
        async with world.factory() as session:
            for _ in range(others):
                extra.append(await seed_entity(session, unique=True))
            await session.commit()
        world.entities += extra
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id)
            segment = await seed_segment(session, video_id, "en", 10.0, 0)
            for entity_id in (a, b, *extra):
                await seed_mention(
                    session,
                    entity_id=entity_id,
                    video_id=video_id,
                    language_code="en",
                    segment_id=segment,
                )
            await measure_scope(session, video_id=video_id, language_code="en")
            await session.commit()
        return video_id

    async def test_four_names_in_one_segment_are_marked_and_still_count(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await self._segment_naming(world, a, b, others=2)
        body = await _get(async_client, a, b)
        assert body["video_count"] == 1 and body["passage_count"] == 1
        assert _only_video(body)["passages"][0]["variants"][0]["name_list"] is True

    async def test_the_pair_alone_is_not_a_name_list(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await self._segment_naming(world, a, b, others=0)
        variant = _only_video(await _get(async_client, a, b))["passages"][0][
            "variants"
        ][0]
        assert variant["name_list"] is False

    async def test_exactly_three_names_are_a_name_list(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await self._segment_naming(world, a, b, others=1)
        variant = _first_variant(await _get(async_client, a, b))
        assert variant["name_list"] is True

    async def test_a_closest_moment_across_two_segments_is_never_marked(
        self, async_client: AsyncClient, world: World
    ) -> None:
        # A and two more entities share segment X and B is in segment Y: X is a name list
        # in the measurement, but the closest co-mention spans two segments.
        a, b = await world.pair()
        c, d = await world.entity(), await world.entity()
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id)
            x = await seed_segment(session, video_id, "en", 10.0, 0)
            y = await seed_segment(session, video_id, "en", 12.0, 1)
            for entity_id, segment in ((a, x), (c, x), (d, x), (b, y)):
                await seed_mention(
                    session,
                    entity_id=entity_id,
                    video_id=video_id,
                    language_code="en",
                    segment_id=segment,
                )
            await measure_scope(session, video_id=video_id, language_code="en")
            await session.commit()
        assert _first_variant(await _get(async_client, a, b))["name_list"] is False

    async def test_a_rejected_third_name_does_not_make_a_name_list(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        c = await world.entity()
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id)
            segment = await seed_segment(session, video_id, "en", 10.0, 0)
            for entity_id, mention_text in ((a, None), (b, None), (c, "not a name")):
                await seed_mention(
                    session,
                    entity_id=entity_id,
                    video_id=video_id,
                    language_code="en",
                    segment_id=segment,
                    mention_text=mention_text,
                )
            await measure_scope(session, video_id=video_id, language_code="en")
            await session.commit()
        assert _first_variant(await _get(async_client, a, b))["name_list"] is False


def _first_variant(body: dict[str, Any]) -> dict[str, Any]:
    variant: dict[str, Any] = _only_video(body)["passages"][0]["variants"][0]
    return variant


class TestPagingAndChannels:
    async def test_pages_are_disjoint_and_cover_the_ordering(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        for gap in (5.0, 1.0, 3.0, 2.0, 4.0):
            await world.comentions(a, b, [(10.0, 10.0 + gap)])
        whole = [v["video_id"] for v in (await _get(async_client, a, b))["items"]]
        paged: list[str] = []
        for offset in (0, 2, 4):
            page = await _get(async_client, a, b, limit=2, offset=offset)
            paged += [v["video_id"] for v in page["items"]]
        assert paged == whole and len(set(whole)) == 5

    async def test_an_offset_past_the_end_is_an_empty_page_with_the_same_counts(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await world.comentions(a, b, [(10, 12)])
        body = await _get(async_client, a, b, offset=10)
        assert body["items"] == [] and body["state"] == "passages"
        assert body["video_count"] == 1 and body["truncated"] is False

    @pytest.mark.parametrize("limit", ["0", "51"])
    async def test_limit_out_of_range_is_422(
        self, async_client: AsyncClient, world: World, limit: str
    ) -> None:
        a, b = await world.pair()
        resp = await async_client.get(
            URL, params={"a": str(a), "b": str(b), "limit": limit}
        )
        assert resp.status_code == 422

    async def test_channels_count_distinct_with_unknown_once(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        channels = [f"c{_RUN}one", f"c{_RUN}two"]
        async with world.factory() as session:
            for channel_id in channels:
                session.add(
                    ChannelDB(channel_id=channel_id, title=f"Channel {channel_id}")
                )
            await session.commit()
        videos = [
            await world.comentions(a, b, [(10.0, 10.0 + g)]) for g in (1, 2, 3, 4)
        ]
        owners = [channels[0], channels[0], channels[1], None]
        try:
            async with world.factory() as session:
                for video_id, channel_id in zip(videos, owners, strict=False):
                    await session.execute(
                        update(VideoDB)
                        .where(VideoDB.video_id == video_id)
                        .values(channel_id=channel_id)
                    )
                await session.commit()
            body = await _get(async_client, a, b)
            assert body["channel_count"] == 3  # two channels and one "unknown"
            assert body["items"][0]["channel_title"] == f"Channel {channels[0]}"
        finally:
            async with world.factory() as session:
                await session.execute(
                    update(VideoDB)
                    .where(VideoDB.video_id.in_(videos))
                    .values(channel_id=None)
                )
                await session.execute(
                    delete(ChannelDB).where(ChannelDB.channel_id.in_(channels))
                )
                await session.commit()


class TestSeams:
    async def test_each_request_reads_one_read_only_snapshot(
        self, async_client: AsyncClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from chronovista.services import proximity_service

        a, b = await world.pair()
        await world.comentions(a, b, [(10, 12)])
        seen: list[tuple[str, str]] = []

        def observing(
            real: Callable[..., Awaitable[Any]],
        ) -> Callable[..., Awaitable[Any]]:
            async def wrapper(session: AsyncSession, **kwargs: Any) -> Any:
                isolation = await session.execute(text("SHOW transaction_isolation"))
                read_only = await session.execute(text("SHOW transaction_read_only"))
                seen.append((isolation.scalar_one(), read_only.scalar_one()))
                return await real(session, **kwargs)

            return wrapper

        for name in ("pair_passages", "farther_videos"):
            monkeypatch.setattr(
                proximity_service, name, observing(getattr(proximity_service, name))
            )
        await _get(async_client, a, b)
        await async_client.get(FARTHER, params={"a": str(a), "b": str(b)})
        assert seen == [("repeatable read", "on"), ("repeatable read", "on")]

    @pytest.mark.parametrize("established", [False, True])
    async def test_the_real_identity_helper_drives_the_leading_language(
        self,
        async_client: AsyncClient,
        world: World,
        monkeypatch: pytest.MonkeyPatch,
        established: bool,
    ) -> None:
        from chronovista.services.identity_service import (
            IdentityNotEstablishedError,
            IdentityService,
        )

        a, b = await world.pair()
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id, ("en", "es"))
            await session.commit()
        await world.comentions(a, b, [(10, 11)], video_id=video_id, create_video=False)
        await world.comentions(
            a, b, [(10, 15)], video_id=video_id, language_code="es", create_video=False
        )
        user_id = await world.prefer(("es", "fluent", 1))

        async def identity(self: IdentityService, session: AsyncSession) -> str:
            if not established:
                raise IdentityNotEstablishedError("none")
            return user_id

        # Only the identity row is substituted (a singleton on the shared DB); the real
        # optional_local_identity, preference read and ranking run.
        monkeypatch.setattr(IdentityService, "get_established_identity", identity)
        lead = _first_variant(await _get(async_client, a, b))["language_code"]
        assert lead == ("es" if established else "en")


class TestMoreFarther:
    async def test_a_video_close_in_another_language_is_not_farther(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id, ("en", "es"))
            await session.commit()
        await world.comentions(a, b, [(10, 12)], video_id=video_id, create_video=False)
        await world.comentions(
            a, b, [(10, 400)], video_id=video_id, language_code="es", create_video=False
        )
        body = await _get(async_client, a, b)
        assert body["video_count"] == 1 and body["farther_video_count"] == 0

    async def test_the_nearest_start_is_the_earlier_of_the_two(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await world.comentions(a, b, [(400.0, 100.0)])  # B is spoken first
        resp = await async_client.get(FARTHER, params={"a": str(a), "b": str(b)})
        (item,) = resp.json()["items"]
        assert item["nearest_start_time"] == 100.0
        assert item["nearest_gap_seconds"] == 300.0

    async def test_the_list_pages_nearest_first_with_ties_by_video(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        ids = [await _spoken_only(world, a, b, gap) for gap in (300.0, 200.0, 200.0)]
        params = {"a": str(a), "b": str(b), "limit": 2}
        first = (await async_client.get(FARTHER, params=params)).json()
        rest = (await async_client.get(FARTHER, params={**params, "offset": 2})).json()
        assert [v["video_id"] for v in first["items"] + rest["items"]] == [
            ids[1],
            ids[2],
            ids[0],
        ]
        assert first["truncated"] is True and rest["truncated"] is False
        assert first["total"] == rest["total"] == 3


class TestBasis:
    async def test_a_title_only_link_is_named_as_the_basis(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        video_id = world.video_id()
        async with world.factory() as session:
            await seed_video(session, video_id)
            await seed_title_mention(session, entity_id=a, video_id=video_id)
            await seed_title_mention(session, entity_id=b, video_id=video_id)
            await session.commit()
        body = await _get(async_client, a, b)
        assert body["state"] == "no_transcript"
        assert body["basis_when_empty"] == "title"

    async def test_no_basis_when_spoken_but_far(
        self, async_client: AsyncClient, world: World
    ) -> None:
        a, b = await world.pair()
        await _spoken_only(world, a, b, 300.0)
        body = await _get(async_client, a, b)
        assert body["state"] == "no_passage_in_window"
        assert body["basis_when_empty"] is None
