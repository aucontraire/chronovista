"""Real-DB ranking math for ``get_channel_entity_rankings`` (Feature 070 / #171, T004).

A mock cannot exercise this method — its channel count comes from the shared
``_tag_inclusive_association_arms`` (a ``UNION ALL`` + ``unnest``) and its
denominator from ``get_association_counts``, both of which only mean anything
against real rows. So this lives in the integration suite on an isolated
``db_session`` (create_all + drop_all per test), not among the mock SQL-shape
guards in ``tests/unit``.

Covers (data-model / spec): distinctiveness ordering (high share above high raw
count, SC-001), the ≥2 floor putting a 1-video entity in "also appears" (FR-008),
the tie-break order (channel desc → corpus asc → name), ``share = channel /
corpus``, the ``corpus ≥ channel`` invariant, and the all-videos basis (an
unavailable channel video is counted, FR-003).

Neutral placeholder data only (this repository is public).
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from tests.factories.entity_association_orm_factory import (
    seed_alias_tag_association,
    seed_channel_with_videos,
    seed_mention_association,
    seed_tag_only_association,
)

pytestmark = pytest.mark.asyncio

_CH = "UCr070RankChannel000000"[:24]
_OTHER = "UCr070OtherChannel00000"[:24]


async def _seed(session: AsyncSession) -> None:
    """Seed one channel + a corpus-padding channel with a spread of entities.

    Channel videos cv1..cv4 (available) + cvU (unavailable); ov1..ov9 pad the
    corpus on another channel so ``corpus > channel`` and shares differ.
    """
    await seed_channel_with_videos(
        session,
        channel_id=_CH,
        available=[f"r070cv{i}" for i in range(1, 5)],
        unavailable=["r070cvU"],
        channel_title="R070 Rank Channel",
    )
    await seed_channel_with_videos(
        session,
        channel_id=_OTHER,
        available=[f"r070ov{i}" for i in range(1, 10)],
        channel_title="R070 Other Channel",
    )

    # HIGH: 2 channel videos, no others -> channel=2, corpus=2, share=1.0 (ranked).
    await seed_mention_association(
        session, video_ids=["r070cv1", "r070cv2"], entity_name="R070 High"
    )
    # FREQ: 3 channel videos + 3 other -> channel=3, corpus=6, share=0.5 (ranked).
    #       Higher raw channel count than HIGH but lower share.
    await seed_mention_association(
        session,
        video_ids=["r070cv1", "r070cv2", "r070cv3", "r070ov1", "r070ov2", "r070ov3"],
        entity_name="R070 Freq",
    )
    # Tie pair, both share 1/3: TA channel=2 corpus=6, TB channel=3 corpus=9.
    # Equal share -> channel desc means TB precedes TA.
    await seed_mention_association(
        session,
        video_ids=[
            "r070cv1",
            "r070cv2",
            "r070ov1",
            "r070ov2",
            "r070ov3",
            "r070ov4",
        ],
        entity_name="R070 TieA",  # channel=2, corpus=6, share=1/3
    )
    await seed_mention_association(
        session,
        video_ids=[
            "r070cv1",
            "r070cv2",
            "r070cv3",
            "r070ov1",
            "r070ov2",
            "r070ov3",
            "r070ov4",
            "r070ov5",
            "r070ov6",
        ],
        entity_name="R070 TieB",  # channel=3, corpus=9, share=1/3
    )
    # ALIAS: reached ONLY through the alias-tag path (canonical_tag.entity_id
    # NULL) -> exercises discovery step 2c AND the alias arm in
    # _tag_inclusive_association_arms (the path that regressed #260). channel=2
    # (cv1,cv2) + 2 other -> corpus=4, share=0.5 (ties Freq on share, loses the
    # tie on channel count: Freq ch=3 precedes Alias ch=2).
    await seed_alias_tag_association(
        session,
        video_ids=["r070cv1", "r070cv2", "r070ov7", "r070ov8"],
        entity_name="R070 Alias",
    )
    # ONE: exactly 1 channel video (tag-only) -> also-appears (is_ranked False).
    await seed_tag_only_association(
        session, video_ids=["r070cv4"], entity_name="R070 Also One"
    )
    # UNAVAIL: associated ONLY on the unavailable channel video -> channel=1,
    # also-appears; proves the all-videos basis counts unavailable (FR-003).
    await seed_mention_association(
        session, video_ids=["r070cvU"], entity_name="R070 Also Unavail"
    )


class TestChannelEntityRankings:
    async def test_ranking_math_and_grouping(self, db_session: AsyncSession) -> None:
        await _seed(db_session)
        repo = EntityMentionRepository()

        rows = await repo.get_channel_entity_rankings(db_session, _CH)
        by_name = {r.display_name: r for r in rows}

        # Every seeded entity surfaced (7 total, incl. the alias-tag-only one).
        assert set(by_name) == {
            "R070 High",
            "R070 Freq",
            "R070 Alias",
            "R070 TieA",
            "R070 TieB",
            "R070 Also One",
            "R070 Also Unavail",
        }

        # share == channel / corpus, and the corpus >= channel invariant, per row.
        for r in rows:
            assert r.corpus_video_count >= r.channel_video_count >= 1
            assert r.share == pytest.approx(
                r.channel_video_count / r.corpus_video_count
            )

        # Concrete counts.
        assert (
            by_name["R070 High"].channel_video_count,
            by_name["R070 High"].corpus_video_count,
        ) == (2, 2)
        assert (
            by_name["R070 Freq"].channel_video_count,
            by_name["R070 Freq"].corpus_video_count,
        ) == (3, 6)
        assert (
            by_name["R070 TieA"].channel_video_count,
            by_name["R070 TieA"].corpus_video_count,
        ) == (2, 6)
        assert (
            by_name["R070 TieB"].channel_video_count,
            by_name["R070 TieB"].corpus_video_count,
        ) == (3, 9)
        # ALIAS proves the alias-tag discovery (2c) + arm both executed on a real
        # DB: an entity reachable ONLY via the alias-tag path still surfaces with
        # the right counts (the #260 regression class).
        assert (
            by_name["R070 Alias"].channel_video_count,
            by_name["R070 Alias"].corpus_video_count,
        ) == (2, 4)
        assert by_name["R070 Alias"].is_ranked is True

        # The ≥2 floor: 1-channel-video entities are NOT share-ranked.
        assert by_name["R070 Also One"].is_ranked is False
        assert by_name["R070 Also Unavail"].is_ranked is False
        assert by_name["R070 High"].is_ranked is True

        # All-videos basis: the entity associated only via the UNAVAILABLE channel
        # video is still counted (FR-003).
        assert by_name["R070 Also Unavail"].channel_video_count == 1

        ranked = [r.display_name for r in rows if r.is_ranked]
        also = [r.display_name for r in rows if not r.is_ranked]

        # SC-001: HIGH (share 1.0, channel 2) outranks FREQ (share 0.5, channel 3)
        # despite FREQ's higher raw count. Share-tie break by channel desc:
        # FREQ (0.5, ch 3) before ALIAS (0.5, ch 2); TB (1/3, ch 3) before TA
        # (1/3, ch 2).
        assert ranked == [
            "R070 High",
            "R070 Freq",
            "R070 Alias",
            "R070 TieB",
            "R070 TieA",
        ]

        # Ranked group precedes the "also appears" group; the latter is ordered by
        # display name.
        assert also == ["R070 Also One", "R070 Also Unavail"]
        assert [r.display_name for r in rows] == ranked + also

    async def test_channel_with_no_videos_returns_empty(
        self, db_session: AsyncSession
    ) -> None:
        repo = EntityMentionRepository()
        assert await repo.get_channel_entity_rankings(db_session, _CH) == []

    async def test_channel_with_videos_but_no_entities_returns_empty(
        self, db_session: AsyncSession
    ) -> None:
        await seed_channel_with_videos(
            db_session, channel_id=_CH, available=["r070cv1"]
        )

        repo = EntityMentionRepository()
        assert await repo.get_channel_entity_rankings(db_session, _CH) == []
