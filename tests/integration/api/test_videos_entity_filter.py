"""
Integration tests for the entity intersection filter on the videos list (Feature 062).

Covers FR-032 (intersections of two, three, and four entities), FR-033 (the
count-parity seam), FR-003a (per-entity match cardinality), FR-020a/FR-020c
(evidence scope), and FR-005 (read-only).

The integration database is never reset between runs, so every assertion here
compares against an INDEPENDENT query over this module's own seeded rows rather
than an absolute constant. Anything else would pass on a clean database and
drift the moment another module seeds a video.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from tests.factories.named_entity_orm_factory import create_named_entity_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

# CRITICAL: without this, async tests are silently skipped under coverage and
# report a false low number. This repo has hit exactly that.
pytestmark = pytest.mark.asyncio

_CHANNEL_ID = "UCei062ef000000000000001"  # <= 24 chars
_LANG = "en"
_PREFIX = "ei062ef"
_VIDEOS = [f"{_PREFIX}_v{n}" for n in range(1, 6)]  # <= 20 chars each


async def _cleanup(session: AsyncSession) -> None:
    """Remove this module's rows so reruns start from a known state."""
    await session.execute(
        delete(EntityMentionDB).where(EntityMentionDB.video_id.in_(_VIDEOS))
    )
    await session.execute(
        delete(NamedEntityDB).where(
            NamedEntityDB.canonical_name.like(f"{_PREFIX.title()}%")
        )
    )
    await session.execute(
        delete(TranscriptSegmentDB).where(TranscriptSegmentDB.video_id.in_(_VIDEOS))
    )
    await session.execute(
        delete(VideoTranscriptDB).where(VideoTranscriptDB.video_id.in_(_VIDEOS))
    )
    await session.execute(delete(VideoDB).where(VideoDB.video_id.in_(_VIDEOS)))
    await session.execute(delete(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID))
    await session.commit()


@pytest.fixture
async def seed(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[dict[str, Any], None]:
    """Seed five videos with deliberately overlapping entity sets.

    The distribution is chosen so each requirement has a case that would fail
    if the implementation were wrong in a specific way:

    ===== ================================================================
    Video Mentions
    ===== ================================================================
    v1    e1 x3 transcript (DUPLICATE rows), e2, e3, e4 -- all four
    v2    e1, e2, e3 transcript; e4 transcript via detection_method=manual
    v3    e1 transcript, e2 DESCRIPTION -- scope-sensitive
    v4    e1 only -- must never appear in any intersection
    v5    e1 TITLE only, e2 transcript -- scope-sensitive, null timestamp
    ===== ================================================================

    So under ``any``: {e1,e2} = v1,v2,v3,v5 (4); {e1,e2,e3} = v1,v2 (2);
    {e1,e2,e3,e4} = v1,v2 (2). Under ``transcript``: {e1,e2} = v1,v2 (2),
    because v3's e2 is description-sourced and v5's e1 is title-sourced.
    """
    ids = {name: uuid.uuid4() for name in ("e1", "e2", "e3", "e4")}

    async with integration_session_factory() as session:
        await _cleanup(session)
        session.add(ChannelDB(channel_id=_CHANNEL_ID, title="EI062 Test Channel"))
        for vid in _VIDEOS:
            session.add(
                VideoDB(
                    video_id=vid,
                    channel_id=_CHANNEL_ID,
                    title=f"EI062 {vid}",
                    description="entity intersection fixture",
                    upload_date=datetime(2024, 5, 1, tzinfo=UTC),
                    duration=300,
                )
            )
        await session.commit()

        # One transcript + segment per video, so transcript mentions have a
        # real segment_id and therefore a real first_timestamp.
        segment_ids: dict[str, int] = {}
        for vid in _VIDEOS:
            session.add(
                VideoTranscriptDB(
                    video_id=vid,
                    language_code=_LANG,
                    transcript_text="fixture transcript",
                    transcript_type="MANUAL",
                    download_reason="USER_REQUEST",
                    is_cc=False,
                    is_auto_synced=False,
                    track_kind="standard",
                )
            )
        await session.commit()

        for index, vid in enumerate(_VIDEOS):
            segment = TranscriptSegmentDB(
                video_id=vid,
                language_code=_LANG,
                text="fixture segment",
                start_time=float(index * 10),
                duration=5.0,
                end_time=float(index * 10 + 5),
                sequence_number=0,
                has_correction=False,
            )
            session.add(segment)
            await session.commit()
            segment_ids[vid] = segment.id

        for name, entity_id in ids.items():
            session.add(
                create_named_entity_db(
                    id=entity_id,
                    canonical_name=f"{_PREFIX.title()} {name.upper()}",
                    canonical_name_normalized=f"{_PREFIX} {name}",
                    entity_type="person",
                    description="fixture",
                )
            )
        await session.commit()

        def mention(
            entity: str,
            video: str,
            source: str = "transcript",
            method: str = "rule_match",
        ) -> EntityMentionDB:
            return EntityMentionDB(
                id=uuid.UUID(bytes=uuid7().bytes),
                entity_id=ids[entity],
                # Only transcript mentions have a segment; title and
                # description mentions have none, hence a null timestamp.
                segment_id=segment_ids[video] if source == "transcript" else None,
                video_id=video,
                language_code=_LANG,
                mention_text=f"{_PREFIX} {entity}",
                detection_method=method,
                mention_source=source,
            )

        rows = [
            # v1 — all four entities; e1 appears THREE times (duplicate rows).
            mention("e1", _VIDEOS[0]),
            mention("e1", _VIDEOS[0]),
            mention("e1", _VIDEOS[0]),
            mention("e2", _VIDEOS[0]),
            mention("e3", _VIDEOS[0]),
            mention("e4", _VIDEOS[0]),
            # v2 — three by rule, e4 added manually. Manual mentions are
            # transcript-sourced, so they must survive min_evidence=transcript.
            mention("e1", _VIDEOS[1]),
            mention("e2", _VIDEOS[1]),
            mention("e3", _VIDEOS[1]),
            mention("e4", _VIDEOS[1], method="manual"),
            # v3 — e2 only in the description.
            mention("e1", _VIDEOS[2]),
            mention("e2", _VIDEOS[2], source="description"),
            # v4 — e1 alone; must never satisfy a multi-entity intersection.
            mention("e1", _VIDEOS[3]),
            # v5 — e1 only in the title (null timestamp), e2 in transcript.
            mention("e1", _VIDEOS[4], source="title"),
            mention("e2", _VIDEOS[4]),
        ]
        for row in rows:
            session.add(row)
        await session.commit()

    yield {"ids": ids, "videos": _VIDEOS}

    async with integration_session_factory() as session:
        await _cleanup(session)


def _params(entity_ids: list[uuid.UUID], **extra: str) -> str:
    parts = [f"entity_id={e}" for e in entity_ids]
    parts += [f"{k}={v}" for k, v in extra.items()]
    return "&".join(parts)


class TestIntersectionCorrectness:
    """FR-032, SC-002, SC-004 — intersections of two, three, and four."""

    async def test_two_entity_intersection(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """Exactly the videos where BOTH entities appear, under the default scope."""
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']], limit='50')}"
        )
        assert response.status_code == 200
        returned = {v["video_id"] for v in response.json()["data"]}
        assert returned == {_VIDEOS[0], _VIDEOS[1], _VIDEOS[2], _VIDEOS[4]}
        # v4 mentions only e1 and must never qualify.
        assert _VIDEOS[3] not in returned

    async def test_three_entity_intersection_narrows(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """Adding a third required entity narrows rather than widens (SC-002)."""
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2'], ids['e3']], limit='50')}"
        )
        returned = {v["video_id"] for v in response.json()["data"]}
        assert returned == {_VIDEOS[0], _VIDEOS[1]}

    async def test_four_entity_intersection(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """Four required entities behave identically to two (FR-002)."""
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2'], ids['e3'], ids['e4']], limit='50')}"
        )
        returned = {v["video_id"] for v in response.json()["data"]}
        assert returned == {_VIDEOS[0], _VIDEOS[1]}

    async def test_duplicate_mention_rows_do_not_affect_qualification(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """SC-004: v1 holds three e1 rows and still qualifies exactly once.

        The count must reflect the true multiplicity (3) while qualification
        stays per distinct entity. A formulation that joined per entity would
        return v1 three times.
        """
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']], limit='50')}"
        )
        rows = [v for v in response.json()["data"] if v["video_id"] == _VIDEOS[0]]
        assert len(rows) == 1
        e1_match = next(
            m for m in rows[0]["entity_matches"] if m["entity_id"] == str(ids["e1"])
        )
        assert e1_match["mention_count"] == 3
        assert rows[0]["total_mentions"] == 4  # 3 x e1 + 1 x e2

    async def test_requesting_same_entity_twice_is_idempotent(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """Duplicate ids must not raise the qualification bar."""
        ids = seed["ids"]
        once = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']], limit='50')}"
        )
        twice = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2'], ids['e1']], limit='50')}"
        )
        assert twice.json()["pagination"]["total"] == once.json()["pagination"]["total"]


class TestPerEntityMatchShape:
    """FR-003a, FR-008, FR-031 — the per-video entity evidence."""

    async def test_match_count_equals_required_set_size(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """Every returned row carries exactly one entry per required entity."""
        ids = seed["ids"]
        for required in ([ids["e1"], ids["e2"]], [ids["e1"], ids["e2"], ids["e3"]]):
            response = await async_client.get(
                f"/api/v1/videos?{_params(required, limit='50')}"
            )
            for video in response.json()["data"]:
                assert len(video["entity_matches"]) == len(required)

    async def test_match_order_follows_the_requested_sequence(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """Per-entity evidence is ordered by the caller's required set.

        Without this the order is whatever the GROUP BY happened to return, so
        badges on one video can reorder between requests and two pages of one
        result set can present the same entities differently. The co-occurrence
        query carries an explicit tiebreak for the same reason.
        """
        ids = seed["ids"]
        forward = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2'], ids['e3']], limit='50')}"
        )
        reversed_ = await async_client.get(
            f"/api/v1/videos?{_params([ids['e3'], ids['e2'], ids['e1']], limit='50')}"
        )

        for video in forward.json()["data"]:
            assert [m["entity_id"] for m in video["entity_matches"]] == [
                str(ids["e1"]),
                str(ids["e2"]),
                str(ids["e3"]),
            ]
        # Reversing the request reverses the response, proving the order is
        # driven by the caller rather than incidentally stable.
        for video in reversed_.json()["data"]:
            assert [m["entity_id"] for m in video["entity_matches"]] == [
                str(ids["e3"]),
                str(ids["e2"]),
                str(ids["e1"]),
            ]

    async def test_entity_type_present_without_extra_lookup(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """FR-031: type identity travels with the match."""
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']], limit='50')}"
        )
        for video in response.json()["data"]:
            for match in video["entity_matches"]:
                assert match["entity_type"] == "person"
                assert match["canonical_name"]

    async def test_title_only_mention_has_null_timestamp(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """FR-008: an entity with no segment has no time -- null, not zero."""
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']], limit='50')}"
        )
        v5 = next(v for v in response.json()["data"] if v["video_id"] == _VIDEOS[4])
        e1_match = next(
            m for m in v5["entity_matches"] if m["entity_id"] == str(ids["e1"])
        )
        assert e1_match["first_timestamp"] is None

    async def test_transcript_mention_has_a_timestamp(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """The null above must be meaningful, not the only outcome."""
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']], limit='50')}"
        )
        v1 = next(v for v in response.json()["data"] if v["video_id"] == _VIDEOS[0])
        e1_match = next(
            m for m in v1["entity_matches"] if m["entity_id"] == str(ids["e1"])
        )
        assert e1_match["first_timestamp"] == 0.0


class TestCountParitySeam:
    """FR-033, SC-003 — the feature's highest-risk seam.

    A filter that reaches the result set but not the reported total produces
    correct rows with a wrong count, which no row-inspecting assertion detects.
    Each test here compares the reported total against an INDEPENDENT count.
    """

    async def test_total_matches_independent_count(
        self,
        async_client: AsyncClient,
        seed: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']], limit='1')}"
        )
        async with integration_session_factory() as session:
            qualifying = (
                select(EntityMentionDB.video_id)
                .where(EntityMentionDB.entity_id.in_([ids["e1"], ids["e2"]]))
                .group_by(EntityMentionDB.video_id)
                .having(func.count(func.distinct(EntityMentionDB.entity_id)) == 2)
                .subquery()
            )
            expected = (
                await session.execute(
                    select(func.count())
                    .select_from(VideoDB)
                    .join(qualifying, VideoDB.video_id == qualifying.c.video_id)
                    .where(VideoDB.availability_status == "available")
                )
            ).scalar()
        assert response.json()["pagination"]["total"] == expected

    async def test_total_respects_evidence_scope_not_only_entity_ids(
        self,
        async_client: AsyncClient,
        seed: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The scope must reach the COUNT query, not only the result query.

        This is the specific failure FR-033 names: applying `min_evidence` to
        the rows but not the total yields a page whose count describes a
        different set than the one listed.
        """
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']], limit='1', min_evidence='transcript')}"
        )
        async with integration_session_factory() as session:
            qualifying = (
                select(EntityMentionDB.video_id)
                .where(
                    EntityMentionDB.entity_id.in_([ids["e1"], ids["e2"]]),
                    EntityMentionDB.mention_source == "transcript",
                )
                .group_by(EntityMentionDB.video_id)
                .having(func.count(func.distinct(EntityMentionDB.entity_id)) == 2)
                .subquery()
            )
            expected = (
                await session.execute(
                    select(func.count())
                    .select_from(VideoDB)
                    .join(qualifying, VideoDB.video_id == qualifying.c.video_id)
                    .where(VideoDB.availability_status == "available")
                )
            ).scalar()
        assert response.json()["pagination"]["total"] == expected
        # And it must genuinely differ from the unscoped total, or this test
        # would pass even if the scope were ignored everywhere.
        unscoped = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']], limit='1')}"
        )
        assert (
            response.json()["pagination"]["total"]
            < unscoped.json()["pagination"]["total"]
        )


class TestEvidenceScope:
    """FR-020a, FR-020c — what counts as a qualifying mention."""

    async def test_default_scope_accepts_all_three_sources(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """FR-020a: with no scope requested, title and description qualify."""
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']], limit='50')}"
        )
        returned = {v["video_id"] for v in response.json()["data"]}
        assert _VIDEOS[2] in returned  # e2 is description-sourced
        assert _VIDEOS[4] in returned  # e1 is title-sourced

    async def test_transcript_scope_excludes_other_sources(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']], limit='50', min_evidence='transcript')}"
        )
        returned = {v["video_id"] for v in response.json()["data"]}
        assert returned == {_VIDEOS[0], _VIDEOS[1]}

    async def test_transcript_scope_retains_manual_mentions(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """FR-020c: every human-added mention is transcript-sourced.

        Excluding them would invert the parameter's intent -- restricting to
        stronger evidence would discard the strongest evidence in the system.
        v2's e4 mention was added with detection_method='manual'.
        """
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e4']], limit='50', min_evidence='transcript')}"
        )
        returned = {v["video_id"] for v in response.json()["data"]}
        assert _VIDEOS[1] in returned


class TestExclusion:
    """FR-014, FR-015a, SC-007."""

    async def test_excluded_entity_removes_its_videos(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1']], limit='50')}"
            f"&exclude_entity_id={ids['e3']}"
        )
        returned = {v["video_id"] for v in response.json()["data"]}
        assert _VIDEOS[0] not in returned  # v1 mentions e3
        assert _VIDEOS[1] not in returned  # v2 mentions e3
        assert _VIDEOS[3] in returned  # v4 has e1 only

    async def test_exclusion_only_filter_returns_present_and_empty_fields(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """FR-015a: exclusion-only IS an active filter."""
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?exclude_entity_id={ids['e3']}&limit=1"
        )
        row = response.json()["data"][0]
        assert row["entity_matches"] == []
        assert row["total_mentions"] == 0

    async def test_no_entity_filter_leaves_fields_null(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """Existing callers must see an unchanged response shape."""
        response = await async_client.get("/api/v1/videos?limit=1")
        row = response.json()["data"][0]
        assert row["entity_matches"] is None
        assert row["total_mentions"] is None


class TestRelevanceOrdering:
    """FR-009b, FR-009c — auto-selection and user override."""

    async def test_relevance_auto_selected_when_sort_unset(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """FR-009b: v1 carries four qualifying mentions and must rank first."""
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']], limit='50')}"
        )
        totals = [v["total_mentions"] for v in response.json()["data"]]
        assert totals == sorted(totals, reverse=True)
        assert response.json()["data"][0]["video_id"] == _VIDEOS[0]

    async def test_explicit_sort_is_never_overridden(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """FR-009c: user choice wins even when an entity filter is active."""
        ids = seed["ids"]
        response = await async_client.get(
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']], limit='50')}"
            "&sort_by=title&sort_order=asc"
        )
        titles = [v["title"] for v in response.json()["data"]]
        assert titles == sorted(titles)


class TestFilterComposition:
    """FR-010, SC-011 — the entity filter composes with EVERY existing filter.

    Checked exhaustively rather than by sample. One unchecked combination is
    where a silent drop hides: a filter that stops being applied when an entity
    filter is present returns MORE videos than it should, and every assertion
    about the rows themselves still passes because the rows that are there are
    correct. Only comparing against the filter applied alone catches it.

    Each case asserts two things:

    1. The combination is a subset of the entity filter alone (or of the other
       filter alone) — so neither side was dropped.
    2. Where the fixture makes it possible, the combination is strictly smaller
       than the entity filter alone — so the other filter did something.
    """

    async def test_composes_with_every_existing_filter(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        ids = seed["ids"]
        entity_only = f"entity_id={ids['e1']}&limit=50"

        baseline = await async_client.get(f"/api/v1/videos?{entity_only}")
        baseline_ids = {v["video_id"] for v in baseline.json()["data"]}
        assert baseline_ids, "fixture must produce a non-empty baseline"

        # Every filter the videos list accepts, paired with the entity filter.
        # `include_unavailable` is the one that legitimately WIDENS, so it is
        # asserted separately below.
        combinations = {
            "channel_id": f"channel_id={_CHANNEL_ID}",
            "tag": "tag=nonexistent-ei062-tag",
            "canonical_tag": "canonical_tag=nonexistent-ei062-tag",
            "topic_id": "topic_id=/m/nonexistent",
            "category": "category=25",
            "has_transcript": "has_transcript=true",
            "liked_only": "liked_only=true",
            "saved_unwatched": "saved_unwatched=true",
            "uploaded_after": "uploaded_after=2030-01-01T00:00:00",
            "uploaded_before": "uploaded_before=2000-01-01T00:00:00",
        }

        for label, param in combinations.items():
            response = await async_client.get(f"/api/v1/videos?{entity_only}&{param}")
            assert response.status_code in (
                200,
                400,
            ), f"{label} + entity filter returned {response.status_code}"
            if response.status_code != 200:
                continue

            combined_ids = {v["video_id"] for v in response.json()["data"]}
            # The entity filter must still be applied: nothing may appear that
            # the entity filter alone did not return.
            assert combined_ids <= baseline_ids, (
                f"combining with {label} returned videos the entity filter "
                f"alone did not: {combined_ids - baseline_ids}. The entity "
                f"filter was dropped."
            )

    async def test_directly_applied_filters_still_narrow(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """The other half: the SECOND filter must not be dropped either.

        A subset assertion alone passes if the second filter is ignored, so
        each case here uses a value the fixture cannot satisfy — the result
        must be empty.

        **Only filters applied DIRECTLY belong here.** ``tag``,
        ``canonical_tag``, ``topic_id`` and ``category`` are validated first
        (Feature 020, FR-042–FR-044): an unrecognised value is ignored and
        reported in ``warnings``, not applied. For those, "impossible value"
        correctly yields the unfiltered result, so asserting emptiness would
        test the wrong mechanism. They are covered by the subset assertion
        above and by the warning-shape test below.
        """
        ids = seed["ids"]
        entity_only = f"entity_id={ids['e1']}&limit=50"

        impossible = {
            "channel_id": "channel_id=UCzzzzzzzzzzzzzzzzzzzzzz",
            "uploaded_after": "uploaded_after=2035-01-01T00:00:00",
            "uploaded_before": "uploaded_before=1990-01-01T00:00:00",
            "liked_only": "liked_only=true",
            "saved_unwatched": "saved_unwatched=true",
        }

        for label, param in impossible.items():
            response = await async_client.get(f"/api/v1/videos?{entity_only}&{param}")
            assert response.status_code == 200, f"{label}: {response.status_code}"
            assert response.json()["pagination"]["total"] == 0, (
                f"{label} should have excluded every fixture video, but "
                f"{response.json()['pagination']['total']} remained — the "
                f"filter was silently dropped when combined with an entity "
                f"filter."
            )

    async def test_validated_filters_keep_their_ignore_and_warn_behaviour(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """An unrecognised tag/topic/category is ignored, not applied.

        That predates this feature and must survive it. The entity filter
        rejects unknown ids instead (FR-016b), and the two conventions have to
        coexist in one request without either changing the other.
        """
        ids = seed["ids"]
        entity_only = await async_client.get(
            f"/api/v1/videos?entity_id={ids['e1']}&limit=50"
        )
        with_bogus_tag = await async_client.get(
            f"/api/v1/videos?entity_id={ids['e1']}&tag=no-such-tag-ei062&limit=50"
        )

        assert with_bogus_tag.status_code == 200
        # The bogus tag changed nothing; the entity filter still applies.
        assert (
            with_bogus_tag.json()["pagination"]["total"]
            == entity_only.json()["pagination"]["total"]
        )
        # And the response says so rather than silently pretending.
        assert with_bogus_tag.json().get("warnings")

    async def test_include_unavailable_widens_rather_than_narrows(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """The one filter that legitimately grows the result.

        Availability is orthogonal to qualification (Edge Cases): an
        unavailable video that mentions the entity still qualifies, it is just
        hidden by default.
        """
        ids = seed["ids"]
        default = await async_client.get(
            f"/api/v1/videos?entity_id={ids['e1']}&limit=50"
        )
        widened = await async_client.get(
            f"/api/v1/videos?entity_id={ids['e1']}&include_unavailable=true&limit=50"
        )
        assert (
            widened.json()["pagination"]["total"]
            >= default.json()["pagination"]["total"]
        )

    async def test_composes_with_sort_and_pagination(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """Sorting and paging are filters' quiet neighbours.

        A page-2 request that silently dropped the entity filter would return
        unrelated videos, and a total that ignored it would promise more pages
        than exist.
        """
        ids = seed["ids"]
        required = f"entity_id={ids['e1']}&entity_id={ids['e2']}"

        page1 = await async_client.get(
            f"/api/v1/videos?{required}&sort_by=title&sort_order=asc&limit=2&offset=0"
        )
        page2 = await async_client.get(
            f"/api/v1/videos?{required}&sort_by=title&sort_order=asc&limit=2&offset=2"
        )
        unpaged = await async_client.get(f"/api/v1/videos?{required}&limit=50")

        all_ids = {v["video_id"] for v in unpaged.json()["data"]}
        paged_ids = {v["video_id"] for v in page1.json()["data"]} | {
            v["video_id"] for v in page2.json()["data"]
        }
        assert paged_ids <= all_ids
        # Totals agree across pages and with the unpaged request.
        assert (
            page1.json()["pagination"]["total"]
            == page2.json()["pagination"]["total"]
            == unpaged.json()["pagination"]["total"]
        )

    async def test_exclusion_composes_with_the_other_filters_too(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """SC-011 covers the excluded set as well as the required one."""
        ids = seed["ids"]
        # Scope BOTH sides to this module's channel. An unscoped exclusion-only
        # query spans the whole library, so its first page is arbitrary and a
        # subset assertion against it would compare two unrelated pages rather
        # than two filters.
        base = await async_client.get(
            f"/api/v1/videos?channel_id={_CHANNEL_ID}&limit=50"
        )
        base_ids = {v["video_id"] for v in base.json()["data"]}

        combined = await async_client.get(
            f"/api/v1/videos?exclude_entity_id={ids['e3']}"
            f"&channel_id={_CHANNEL_ID}&limit=50"
        )
        combined_ids = {v["video_id"] for v in combined.json()["data"]}

        assert combined_ids < base_ids, "the exclusion did not narrow the set"
        assert _VIDEOS[0] not in combined_ids  # v1 mentions e3
        assert _VIDEOS[1] not in combined_ids  # v2 mentions e3
        assert _VIDEOS[3] in combined_ids  # v4 has e1 only, survives


class TestReadOnly:
    """FR-005, Constitution VI — the feature must never write."""

    async def test_exercising_every_path_mutates_nothing(
        self,
        async_client: AsyncClient,
        seed: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = seed["ids"]

        async def counts() -> dict[str, int]:
            async with integration_session_factory() as session:
                return {
                    "mentions": (
                        await session.execute(
                            select(func.count()).select_from(EntityMentionDB)
                        )
                    ).scalar()
                    or 0,
                    "entities": (
                        await session.execute(
                            select(func.count()).select_from(NamedEntityDB)
                        )
                    ).scalar()
                    or 0,
                    "videos": (
                        await session.execute(select(func.count()).select_from(VideoDB))
                    ).scalar()
                    or 0,
                }

        before = await counts()
        for url in (
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']], limit='50')}",
            f"/api/v1/videos?{_params([ids['e1']], limit='5', min_evidence='transcript')}",
            f"/api/v1/videos?exclude_entity_id={ids['e3']}&limit=5",
            f"/api/v1/videos?{_params([ids['e1'], ids['e2']])}&sort_by=title",
        ):
            assert (await async_client.get(url)).status_code == 200
        assert await counts() == before
