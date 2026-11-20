"""Integration tests for ``GET /api/v1/graph/connect/evidence`` (Feature 114, T010).

Crosses the real HTTP boundary (ASGITransport) and the real database. 422/404 are unconditional;
data-dependent cases discover a co-occurring pair at runtime (no ids hard-coded) and skip with a
clear reason when the integration DB holds none.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import (
    Channel as ChannelDB,
)
from chronovista.db.models import (
    EntityAlias as EntityAliasDB,
)
from chronovista.db.models import (
    EntityMention as EntityMentionDB,
)
from chronovista.db.models import (
    EntityVideoExclusion as EntityVideoExclusionDB,
)
from chronovista.db.models import (
    NamedEntity as NamedEntityDB,
)
from chronovista.db.models import (
    TranscriptSegment as TranscriptSegmentDB,
)
from chronovista.db.models import (
    Video as VideoDB,
)
from chronovista.db.models import (
    VideoTranscript as VideoTranscriptDB,
)
from tests.factories.named_entity_orm_factory import create_named_entity_db

pytestmark = pytest.mark.asyncio

URL = "/api/v1/graph/connect/evidence"

_CANDIDATE_SQL = text(
    """
    SELECT a.entity_id AS a_id, b.entity_id AS b_id
    FROM entity_mentions a
    JOIN entity_mentions b
      ON a.video_id = b.video_id
     AND a.language_code = b.language_code
     AND a.entity_id < b.entity_id
    WHERE a.segment_id IS NOT NULL AND b.segment_id IS NOT NULL
      AND a.detection_method <> 'manual' AND b.detection_method <> 'manual'
    GROUP BY a.entity_id, b.entity_id
    ORDER BY COUNT(DISTINCT a.video_id) DESC
    LIMIT 40
    """
)


async def _discover_pair(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    *,
    min_items: int,
) -> tuple[uuid.UUID, uuid.UUID, dict[str, object]]:
    """Find a pair whose evidence response has at least ``min_items`` distinct contexts."""
    async with factory() as session:
        candidates = (await session.execute(_CANDIDATE_SQL)).all()
    for row in candidates:
        resp = await client.get(URL, params={"a": str(row.a_id), "b": str(row.b_id)})
        if resp.status_code != 200:
            continue
        body = resp.json()
        if body["total_available"] >= min_items:
            return row.a_id, row.b_id, body
    pytest.skip(
        f"integration DB has no entity pair with >= {min_items} transcript "
        "co-occurrence contexts passing the exclusion/qualification gate"
    )


# ---------------------------------------------------------------------------
# Seeded fixture: a committed, self-cleaning co-occurring pair (CI-safe).
# ---------------------------------------------------------------------------


async def _seed_video(
    session: AsyncSession,
    *,
    channel_id: str,
    video_id: str,
    entity_a: NamedEntityDB,
    entity_b: NamedEntityDB,
    name_a: str,
    name_b: str,
    language: str = "en",
    create_video: bool = True,
) -> None:
    """One video, one 'en' transcript, 7 segments; A and B mentioned in adjacent segments.

    The mention_text values are exactly the entities' visible names, so the repo's
    visible-name qualification rule accepts them.
    """
    if create_video:
        session.add(
            VideoDB(
                video_id=video_id,
                channel_id=channel_id,
                title="Fixture Video",
                upload_date=datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC),
                duration=70,
            )
        )
        await session.flush()
    session.add(
        VideoTranscriptDB(
            video_id=video_id,
            language_code=language,
            transcript_text="fixture transcript",
            transcript_type="MANUAL",
            download_reason="USER_REQUEST",
        )
    )
    await session.flush()
    segments: list[TranscriptSegmentDB] = []
    for seq in range(7):
        if seq == 2:
            text_ = f"Segment two mentions {name_a} here."
        elif seq == 3:
            text_ = f"Segment three mentions {name_b} here."
        else:
            text_ = f"Neutral filler segment {seq}."
        segments.append(
            TranscriptSegmentDB(
                video_id=video_id,
                language_code=language,
                text=text_,
                start_time=float(seq * 10),
                duration=10.0,
                end_time=float(seq * 10 + 10),
                sequence_number=seq,
            )
        )
    session.add_all(segments)
    await session.flush()
    for entity, name, seg in (
        (entity_a, name_a, segments[2]),
        (entity_b, name_b, segments[3]),
    ):
        start = seg.text.index(name)
        session.add(
            EntityMentionDB(
                id=uuid.uuid4(),
                entity_id=entity.id,
                segment_id=seg.id,
                video_id=video_id,
                language_code=language,
                mention_text=name,
                detection_method="rule_match",
                confidence=1.0,
                match_start=start,
                match_end=start + len(name),
                mention_source="transcript",
            )
        )
    await session.flush()


@pytest.fixture
async def seeded_pair(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[tuple[uuid.UUID, uuid.UUID], None]:
    """Seed and commit two entities co-occurring in two single-language videos.

    Two co-occurring videos → two video-grain items (``total_available == 2``, ``raw == 2``);
    there is no cross-video collapse. (Video 1 pairs the canonical names, video 2 the aliases —
    a leftover from when forms were collapsed; harmless now, both videos are their own row.)
    Torn down on exit.
    """
    token = uuid.uuid4().hex[:10]
    channel_id = f"UCfx{token}".ljust(24, "0")
    video_ids = [f"fxa{token[:8]}", f"fxb{token[:8]}"]
    canon_a, alias_a = f"Fixture Entity A {token}", f"Fixture Alias A {token}"
    canon_b, alias_b = f"Fixture Entity B {token}", f"Fixture Alias B {token}"

    entities: list[NamedEntityDB] = []
    async with integration_session_factory() as session:
        session.add(ChannelDB(channel_id=channel_id, title="Fixture Channel"))
        await session.flush()
        for canon, alias in ((canon_a, alias_a), (canon_b, alias_b)):
            entity = create_named_entity_db(
                canonical_name=canon,
                canonical_name_normalized=canon.lower(),
            )
            session.add(entity)
            await session.flush()
            session.add(
                EntityAliasDB(
                    id=uuid.uuid4(),
                    entity_id=entity.id,
                    alias_name=alias,
                    alias_name_normalized=alias.lower(),
                    alias_type="name_variant",
                )
            )
            entities.append(entity)
        await session.flush()
        a, b = entities
        await _seed_video(
            session,
            channel_id=channel_id,
            video_id=video_ids[0],
            entity_a=a,
            entity_b=b,
            name_a=canon_a,
            name_b=canon_b,
        )
        await _seed_video(
            session,
            channel_id=channel_id,
            video_id=video_ids[1],
            entity_a=a,
            entity_b=b,
            name_a=alias_a,
            name_b=alias_b,
        )
        await session.commit()
        ids = (a.id, b.id)

    try:
        yield ids
    finally:
        async with integration_session_factory() as session:
            # entities cascade to aliases + mentions; transcripts cascade to segments.
            await session.execute(
                delete(NamedEntityDB).where(NamedEntityDB.id.in_(ids))
            )
            await session.execute(
                delete(VideoTranscriptDB).where(
                    VideoTranscriptDB.video_id.in_(video_ids)
                )
            )
            await session.execute(
                delete(VideoDB).where(VideoDB.video_id.in_(video_ids))
            )
            await session.execute(
                delete(ChannelDB).where(ChannelDB.channel_id == channel_id)
            )
            await session.commit()


async def _seed_plan(
    factory: async_sessionmaker[AsyncSession],
    plan: list[tuple[int, str]],
    video_count: int,
) -> tuple[tuple[uuid.UUID, uuid.UUID], list[str], str]:
    """Commit entities A/B (canonical names only) and, per ``(video_index, language)`` in
    ``plan``, one transcript where A and B (canonical names) are adjacent. Returns
    ``((a_id, b_id), video_ids, channel_id)``; callers tear down via ``_teardown``."""
    token = uuid.uuid4().hex[:10]
    channel_id = f"UCfp{token}".ljust(24, "0")
    video_ids = [f"fxp{i}{token[:7]}" for i in range(video_count)]
    async with factory() as session:
        session.add(ChannelDB(channel_id=channel_id, title="Fixture Channel"))
        await session.flush()
        entities = []
        for label in ("A", "B"):
            name = f"Fixture Plan Entity {label} {token}"
            entity = create_named_entity_db(
                canonical_name=name, canonical_name_normalized=name.lower()
            )
            session.add(entity)
            entities.append(entity)
        await session.flush()
        a, b = entities
        created: set[str] = set()
        for idx, language in plan:
            await _seed_video(
                session,
                channel_id=channel_id,
                video_id=video_ids[idx],
                entity_a=a,
                entity_b=b,
                name_a=a.canonical_name,
                name_b=b.canonical_name,
                language=language,
                create_video=video_ids[idx] not in created,
            )
            created.add(video_ids[idx])
        await session.commit()
        return (a.id, b.id), video_ids, channel_id


async def _teardown(
    factory: async_sessionmaker[AsyncSession],
    ids: tuple[uuid.UUID, uuid.UUID],
    video_ids: list[str],
    channel_id: str,
) -> None:
    async with factory() as session:
        await session.execute(delete(NamedEntityDB).where(NamedEntityDB.id.in_(ids)))
        await session.execute(
            delete(VideoTranscriptDB).where(VideoTranscriptDB.video_id.in_(video_ids))
        )
        await session.execute(delete(VideoDB).where(VideoDB.video_id.in_(video_ids)))
        await session.execute(
            delete(ChannelDB).where(ChannelDB.channel_id == channel_id)
        )
        await session.commit()


@pytest.fixture
async def redundant_pair(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[tuple[uuid.UUID, uuid.UUID], None]:
    """Two videos whose pair uses the SAME surface forms — both must be KEPT (no cross-video
    collapse: identical forms in different videos are two distinct audit rows)."""
    ids, vids, chan = await _seed_plan(
        integration_session_factory, [(0, "en"), (1, "en")], 2
    )
    try:
        yield ids
    finally:
        await _teardown(integration_session_factory, ids, vids, chan)


@pytest.fixture
async def multilang_pair(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[tuple[uuid.UUID, uuid.UUID], None]:
    """ONE video whose pair co-occurs in two transcript languages (FR-009)."""
    ids, vids, chan = await _seed_plan(
        integration_session_factory, [(0, "en"), (0, "es")], 1
    )
    try:
        yield ids
    finally:
        await _teardown(integration_session_factory, ids, vids, chan)


@pytest.fixture
async def title_only_pair(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[tuple[uuid.UUID, uuid.UUID], None]:
    """Two entities co-occurring on one video ONLY via title-source mentions (no transcript)."""
    token = uuid.uuid4().hex[:10]
    channel_id = f"UCft{token}".ljust(24, "0")
    video_id = f"fxt{token[:8]}"
    async with integration_session_factory() as session:
        session.add(ChannelDB(channel_id=channel_id, title="Fixture Channel"))
        await session.flush()
        session.add(
            VideoDB(
                video_id=video_id,
                channel_id=channel_id,
                title="Fixture Video",
                upload_date=datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC),
                duration=70,
            )
        )
        entities = []
        for label in ("A", "B"):
            name = f"Fixture Title Entity {label} {token}"
            entity = create_named_entity_db(
                canonical_name=name, canonical_name_normalized=name.lower()
            )
            session.add(entity)
            entities.append(entity)
        await session.flush()
        for entity in entities:
            session.add(
                EntityMentionDB(
                    id=uuid.uuid4(),
                    entity_id=entity.id,
                    segment_id=None,
                    video_id=video_id,
                    language_code=None,
                    mention_text=entity.canonical_name,
                    detection_method="rule_match",
                    confidence=1.0,
                    mention_source="title",
                )
            )
        await session.commit()
        ids = (entities[0].id, entities[1].id)
    try:
        yield ids
    finally:
        async with integration_session_factory() as session:
            await session.execute(
                delete(NamedEntityDB).where(NamedEntityDB.id.in_(ids))
            )
            await session.execute(delete(VideoDB).where(VideoDB.video_id == video_id))
            await session.execute(
                delete(ChannelDB).where(ChannelDB.channel_id == channel_id)
            )
            await session.commit()


class TestValidation:
    async def test_same_entity_is_422(self, async_client: AsyncClient) -> None:
        eid = str(uuid.uuid4())
        resp = await async_client.get(URL, params={"a": eid, "b": eid})
        assert resp.status_code == 422

    async def test_absent_entity_is_404(self, async_client: AsyncClient) -> None:
        resp = await async_client.get(
            URL, params={"a": str(uuid.uuid4()), "b": str(uuid.uuid4())}
        )
        assert resp.status_code == 404

    async def test_malformed_id_is_422(self, async_client: AsyncClient) -> None:
        resp = await async_client.get(URL, params={"a": "nope", "b": str(uuid.uuid4())})
        assert resp.status_code == 422

    @pytest.mark.parametrize("limit", [0, 51])
    async def test_limit_out_of_range_is_422(
        self, async_client: AsyncClient, limit: int
    ) -> None:
        resp = await async_client.get(
            URL,
            params={"a": str(uuid.uuid4()), "b": str(uuid.uuid4()), "limit": limit},
        )
        assert resp.status_code == 422


class TestEvidenceShape:
    async def test_happy_path_shape_and_counts(
        self,
        async_client: AsyncClient,
        seeded_pair: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        a, b = seeded_pair
        body = (await async_client.get(URL, params={"a": str(a), "b": str(b)})).json()
        assert body["total_available"] >= 1
        assert body["entity_a_id"] == str(a)
        assert body["entity_b_id"] == str(b)
        items = body["items"]
        assert items, "discovery guaranteed total_available >= 1"
        for item in items:
            assert item[
                "video_title"
            ], "video title is populated, not the Untitled fallback"
            assert item["cooccurring_language_count"] == 1 + len(
                item["other_language_variants"]
            )
            # Every variant (the representative + each expander row) has the per-mention shape.
            for variant in [item["representative"], *item["other_language_variants"]]:
                assert variant["passages"], "every variant carries at least one passage"
                assert all(p["text"] for p in variant["passages"])
                # The client builds the per-passage deep link; assert the fields it needs.
                assert all(
                    isinstance(p["segment_id"], int) and p["start_time"] is not None
                    for p in variant["passages"]
                )
                assert variant["mention_a"] and variant["mention_b"]
                assert variant["separation_segments"] >= 0
        assert body["offset"] == 0
        assert body["returned"] == len(items)
        assert body["offset"] + body["returned"] <= body["total_available"]
        assert body["raw_cooccurrence_count"] >= body["total_available"]
        assert body["truncated"] == (
            body["offset"] + body["returned"] < body["total_available"]
        )
        assert body["basis_when_empty"] is None
        # Two single-language videos, no cross-video collapse -> two video items.
        assert body["total_available"] == 2
        assert body["raw_cooccurrence_count"] == 2
        assert all(i["cooccurring_language_count"] == 1 for i in items)
        assert all(i["representative"]["separation_segments"] == 1 for i in items)

    async def test_language_consistency_sc008(
        self,
        async_client: AsyncClient,
        seeded_pair: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        a, b = seeded_pair
        body = (await async_client.get(URL, params={"a": str(a), "b": str(b)})).json()
        assert body["items"]
        for item in body["items"]:
            for variant in [item["representative"], *item["other_language_variants"]]:
                assert (
                    variant["mention_a"]["language_code"]
                    == variant["mention_b"]["language_code"]
                    == variant["language_code"]
                )


class TestPagination:
    async def test_offset_limit_slice_and_last_page_not_truncated(
        self,
        async_client: AsyncClient,
        seeded_pair: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        a, b = seeded_pair
        full = (await async_client.get(URL, params={"a": str(a), "b": str(b)})).json()
        assert full["total_available"] == 2
        total = full["total_available"]
        params = {"a": str(a), "b": str(b)}

        all_resp = await async_client.get(URL, params={**params, "limit": 50})
        all_items = all_resp.json()["items"]
        vids = [i["video_id"] for i in all_items]
        assert len(vids) == len(set(vids)), "one item per video"

        first = (await async_client.get(URL, params={**params, "limit": 1})).json()
        assert first["returned"] == 1
        assert first["truncated"] is True
        assert first["total_available"] == total

        second = (
            await async_client.get(URL, params={**params, "limit": 1, "offset": 1})
        ).json()
        assert second["offset"] == 1
        assert second["items"][0]["video_id"] == all_items[1]["video_id"]

        last = (
            await async_client.get(
                URL, params={**params, "limit": 1, "offset": total - 1}
            )
        ).json()
        assert last["returned"] == 1
        assert last["truncated"] is False

    async def test_offset_past_end_is_empty_and_consistent(
        self,
        async_client: AsyncClient,
        seeded_pair: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        a, b = seeded_pair
        full = (await async_client.get(URL, params={"a": str(a), "b": str(b)})).json()
        assert full["total_available"] >= 1
        resp = await async_client.get(
            URL,
            params={"a": str(a), "b": str(b), "offset": full["total_available"] + 5},
        )
        # Past-end is a clean empty page (fixed): 200, no items, not truncated.
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["returned"] == 0
        assert body["items"] == []
        assert body["truncated"] is False


class TestEmptyBasisAndExclusions:
    async def test_empty_state_names_title_source_fr012(
        self,
        async_client: AsyncClient,
        title_only_pair: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        a, b = title_only_pair
        resp = await async_client.get(URL, params={"a": str(a), "b": str(b)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["items"] == []
        assert body["returned"] == 0
        assert body["basis_when_empty"] == "title"

    async def test_exclusion_removes_video_from_evidence_fr006(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        seeded_pair: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        a, b = seeded_pair
        params = {"a": str(a), "b": str(b)}
        before = (await async_client.get(URL, params=params)).json()
        assert before["total_available"] == 2
        assert before["raw_cooccurrence_count"] == 2
        excluded_video = before["items"][0]["video_id"]

        async with integration_session_factory() as session:
            session.add(
                EntityVideoExclusionDB(
                    entity_id=a,
                    video_id=excluded_video,
                    excluded_by="fixture",
                )
            )
            await session.commit()
        try:
            after = (await async_client.get(URL, params=params)).json()
        finally:
            async with integration_session_factory() as session:
                await session.execute(
                    delete(EntityVideoExclusionDB).where(
                        EntityVideoExclusionDB.entity_id == a,
                        EntityVideoExclusionDB.video_id == excluded_video,
                    )
                )
                await session.commit()

        assert excluded_video not in {i["video_id"] for i in after["items"]}
        assert after["total_available"] == before["total_available"] - 1
        assert after["raw_cooccurrence_count"] == before["raw_cooccurrence_count"] - 1


class TestVideoGrainAndExpander:
    async def test_distinct_videos_same_forms_are_both_kept(
        self,
        async_client: AsyncClient,
        redundant_pair: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        # The redesign: identical surface forms in DIFFERENT videos are two rows, never collapsed.
        a, b = redundant_pair
        body = (await async_client.get(URL, params={"a": str(a), "b": str(b)})).json()
        assert body["raw_cooccurrence_count"] == 2
        assert body["total_available"] == 2
        assert body["returned"] == 2
        assert len({i["video_id"] for i in body["items"]}) == 2
        assert all(i["cooccurring_language_count"] == 1 for i in body["items"])

    async def test_multilanguage_video_is_one_row_with_expander_sc005(
        self,
        async_client: AsyncClient,
        multilang_pair: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        # ONE video, pair co-occurs in two languages: one video row; the other language sits in the
        # expander (never a fabricated cross-language pair — FR-017).
        a, b = multilang_pair
        body = (await async_client.get(URL, params={"a": str(a), "b": str(b)})).json()
        assert body["raw_cooccurrence_count"] == 2
        assert body["total_available"] == 1
        assert body["returned"] == 1
        item = body["items"][0]
        assert item["cooccurring_language_count"] == 2
        assert len(item["other_language_variants"]) == 1
        langs = {item["representative"]["language_code"]} | {
            v["language_code"] for v in item["other_language_variants"]
        }
        assert langs == {"en", "es"}
        # The representative is the minimum-separation variant (the expander one is not closer).
        assert (
            item["other_language_variants"][0]["separation_segments"]
            >= item["representative"]["separation_segments"]
        )
        for variant in [item["representative"], *item["other_language_variants"]]:
            assert (
                variant["mention_a"]["language_code"]
                == variant["mention_b"]["language_code"]
                == variant["language_code"]
            )


class TestDiscoveredRealData:
    """Graceful-skip path: runs against whatever real pair the DB holds, skips when none."""

    async def test_language_grain_on_discovered_pair(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        _, _, body = await _discover_pair(
            async_client, integration_session_factory, min_items=1
        )
        for item in body["items"]:
            for variant in [item["representative"], *item["other_language_variants"]]:
                assert (
                    variant["mention_a"]["language_code"]
                    == variant["mention_b"]["language_code"]
                    == variant["language_code"]
                )
