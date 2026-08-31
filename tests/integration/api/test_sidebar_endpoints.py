"""Integration tests for the sidebar navigation endpoint.

Tests GET /api/v1/sidebar/categories on a real database. This endpoint's query
was moved into ``VideoCategoryRepository.get_with_video_counts`` and the
repository is now injected via FastAPI ``Depends`` through the DI container
(issue #256), so these tests exercise the full seam: dependency injection →
container factory → repository → the correlated-subquery aggregate on Postgres.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy import delete

from chronovista.db.models import Channel, Video, VideoCategory

# Test data scoped by unique ids so the shared integration DB's other rows do
# not interfere; we assert only over our own ids and clean up only our own rows.
_CHANNEL_ID = "UC" + "S" * 22
_CAT_TWO = "sb1"  # two available videos
_CAT_ONE = "sb2"  # one available video
_CAT_NONE = "sb3"  # no videos at all
_CAT_UNAVAIL = "sb4"  # one unavailable video only
_OUR_CATS = {_CAT_TWO, _CAT_ONE, _CAT_NONE, _CAT_UNAVAIL}


async def _seed(session_factory) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                VideoCategory(
                    category_id=_CAT_TWO, name="Sidebar Two", assignable=True
                ),
                VideoCategory(
                    category_id=_CAT_ONE, name="Sidebar One", assignable=True
                ),
                VideoCategory(
                    category_id=_CAT_NONE, name="Sidebar None", assignable=True
                ),
                VideoCategory(
                    category_id=_CAT_UNAVAIL, name="Sidebar Unavail", assignable=True
                ),
            ]
        )
        session.add(
            Channel(channel_id=_CHANNEL_ID, title="SB Channel", is_subscribed=False)
        )
        await session.flush()

        def _video(vid: str, category_id: str, status: str = "available") -> Video:
            return Video(
                video_id=vid,
                channel_id=_CHANNEL_ID,
                title=f"Video {vid}",
                upload_date=datetime.now(UTC),
                duration=300,
                category_id=category_id,
                availability_status=status,
            )

        session.add_all(
            [
                _video("sb_v0", _CAT_TWO),
                _video("sb_v1", _CAT_TWO),
                _video("sb_v2", _CAT_ONE),
                _video("sb_v3", _CAT_UNAVAIL, status="deleted"),
            ]
        )
        await session.commit()


async def _cleanup(session_factory) -> None:
    async with session_factory() as session:
        await session.execute(
            delete(Video).where(
                Video.video_id.in_(["sb_v0", "sb_v1", "sb_v2", "sb_v3"])
            )
        )
        await session.execute(delete(Channel).where(Channel.channel_id == _CHANNEL_ID))
        await session.execute(
            delete(VideoCategory).where(VideoCategory.category_id.in_(_OUR_CATS))
        )
        await session.commit()


class TestSidebarCategories:
    """Tests for GET /api/v1/sidebar/categories."""

    async def test_returns_only_categories_with_available_videos_ordered_desc(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Excludes empty/unavailable-only categories; orders by count desc."""
        await _seed(integration_session_factory)
        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.get("/api/v1/sidebar/categories")

            assert response.status_code == 200
            data = response.json()["data"]
            by_id = {c["category_id"]: c for c in data if c["category_id"] in _OUR_CATS}

            # Zero-video and unavailable-only categories are absent by default.
            assert _CAT_NONE not in by_id
            assert _CAT_UNAVAIL not in by_id

            # The two populated categories are present with correct counts + href.
            assert by_id[_CAT_TWO]["video_count"] == 2
            assert by_id[_CAT_ONE]["video_count"] == 1
            assert by_id[_CAT_TWO]["href"] == f"/videos?category={_CAT_TWO}"

            # Our categories appear in video_count-descending order.
            ours_in_order = [
                c["category_id"] for c in data if c["category_id"] in _OUR_CATS
            ]
            assert ours_in_order == [_CAT_TWO, _CAT_ONE]
        finally:
            await _cleanup(integration_session_factory)

    async def test_include_unavailable_counts_unavailable_videos(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """With include_unavailable=true the unavailable-only category appears."""
        await _seed(integration_session_factory)
        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.get(
                    "/api/v1/sidebar/categories?include_unavailable=true"
                )

            assert response.status_code == 200
            data = response.json()["data"]
            by_id = {c["category_id"]: c for c in data if c["category_id"] in _OUR_CATS}

            # The unavailable-only category is now counted and included.
            assert by_id[_CAT_UNAVAIL]["video_count"] == 1
            # The truly empty category is still absent.
            assert _CAT_NONE not in by_id
        finally:
            await _cleanup(integration_session_factory)
