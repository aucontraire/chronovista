"""Real-DB tests for VideoCategoryRepository's video-count aggregates (#256).

These pin the two behaviors that the category/sidebar endpoint tests cannot
catch: (1) the availability filter is a FILTERed aggregate over a LEFT JOIN, so
categories whose videos are all unavailable (or absent) are *kept* with count 0
rather than dropped — a WHERE would drop them; and (2) the ``(count DESC,
category_id)`` tiebreak makes pagination stable when counts are equal. The
endpoints' sort assertion (``sorted(reverse=True)``) is order-robust and would
miss a regression in either. A mock cannot exercise a correlated/JOINed
aggregate, so these live in the integration suite on an isolated ``db_session``.

Neutral placeholder data only (this repository is public).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel, Video, VideoCategory
from chronovista.repositories.video_category_repository import VideoCategoryRepository

pytestmark = pytest.mark.asyncio

_CHANNEL = "UC" + "V" * 22


async def _add_category(session: AsyncSession, category_id: str, name: str) -> None:
    session.add(VideoCategory(category_id=category_id, name=name, assignable=True))


async def _add_videos(
    session: AsyncSession, category_id: str, *, available: int, unavailable: int
) -> None:
    for i in range(available):
        session.add(
            Video(
                video_id=f"{category_id}_av{i}",
                channel_id=_CHANNEL,
                title=f"vid {category_id} av{i}",
                upload_date=datetime.now(UTC),
                duration=300,
                category_id=category_id,
                availability_status="available",
            )
        )
    for i in range(unavailable):
        session.add(
            Video(
                video_id=f"{category_id}_un{i}",
                channel_id=_CHANNEL,
                title=f"vid {category_id} un{i}",
                upload_date=datetime.now(UTC),
                duration=300,
                category_id=category_id,
                availability_status="deleted",
            )
        )


class TestGetWithVideoCounts:
    async def test_filter_keeps_zero_and_unavailable_categories(
        self, db_session: AsyncSession
    ) -> None:
        """LEFT JOIN + FILTER keeps empty/unavailable-only categories at count 0."""
        await _add_category(db_session, "1", "Has Available")
        await _add_category(db_session, "2", "Only Unavailable")
        await _add_category(db_session, "3", "Empty")
        db_session.add(Channel(channel_id=_CHANNEL, title="C", is_subscribed=False))
        await db_session.flush()
        await _add_videos(db_session, "1", available=2, unavailable=0)
        await _add_videos(db_session, "2", available=0, unavailable=1)
        await db_session.commit()

        repo = VideoCategoryRepository()

        # only_with_videos=False keeps all three; the unavailable-only and empty
        # categories are present with count 0 (default availability basis).
        rows = await repo.get_with_video_counts(db_session)
        counts = {r.category_id: r.video_count for r in rows}
        assert counts == {"1": 2, "2": 0, "3": 0}

        # include_unavailable=True now counts the deleted video in category "2".
        rows_all = await repo.get_with_video_counts(
            db_session, include_unavailable=True
        )
        assert {r.category_id: r.video_count for r in rows_all} == {
            "1": 2,
            "2": 1,
            "3": 0,
        }

        # only_with_videos=True drops the zero-count categories.
        only = await repo.get_with_video_counts(db_session, only_with_videos=True)
        assert {r.category_id for r in only} == {"1"}

        only_all = await repo.get_with_video_counts(
            db_session, only_with_videos=True, include_unavailable=True
        )
        assert {r.category_id for r in only_all} == {"1", "2"}

    async def test_tiebreak_and_pagination_are_stable(
        self, db_session: AsyncSession
    ) -> None:
        """Ties resolve by category_id asc; limit/offset paginate without overlap."""
        # "5" has the most videos (sorts first); "4","1","3" tie at one video each
        # in insertion order that differs from sorted order, so a missing tiebreak
        # would show. "9" has none.
        for cid, name in [
            ("5", "Two"),
            ("4", "One-d"),
            ("1", "One-a"),
            ("3", "One-c"),
            ("9", "Zero"),
        ]:
            await _add_category(db_session, cid, name)
        db_session.add(Channel(channel_id=_CHANNEL, title="C", is_subscribed=False))
        await db_session.flush()
        await _add_videos(db_session, "5", available=2, unavailable=0)
        for cid in ("4", "1", "3"):
            await _add_videos(db_session, cid, available=1, unavailable=0)
        await db_session.commit()

        repo = VideoCategoryRepository()

        ordered = [
            r.category_id
            for r in await repo.get_with_video_counts(db_session, only_with_videos=True)
        ]
        # count DESC then category_id ASC: "5"(2), then the ties "1","3","4"(1).
        assert ordered == ["5", "1", "3", "4"]

        # Paginating that same ordering must partition it with no overlap or gap.
        page1 = await repo.get_with_video_counts(
            db_session, only_with_videos=True, limit=2, offset=0
        )
        page2 = await repo.get_with_video_counts(
            db_session, only_with_videos=True, limit=2, offset=2
        )
        assert [r.category_id for r in page1] == ["5", "1"]
        assert [r.category_id for r in page2] == ["3", "4"]


class TestGetVideoCount:
    async def test_single_category_count_respects_availability(
        self, db_session: AsyncSession
    ) -> None:
        await _add_category(db_session, "1", "Cat")
        db_session.add(Channel(channel_id=_CHANNEL, title="C", is_subscribed=False))
        await db_session.flush()
        await _add_videos(db_session, "1", available=2, unavailable=1)
        await db_session.commit()

        repo = VideoCategoryRepository()

        assert await repo.get_video_count(db_session, "1") == 2
        assert (
            await repo.get_video_count(db_session, "1", include_unavailable=True) == 3
        )
        # A category with no videos (or an unknown id) counts as 0, never raises.
        assert await repo.get_video_count(db_session, "404") == 0
