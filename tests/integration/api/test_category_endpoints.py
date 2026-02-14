"""Integration tests for category API endpoints (US1).

Tests for GET /api/v1/categories, GET /api/v1/categories/{category_id}, and
GET /api/v1/categories/{category_id}/videos endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    Channel,
    Video,
    VideoCategory,
    VideoTag,
    VideoTopic,
)


pytestmark = pytest.mark.asyncio


class TestListCategories:
    """Tests for GET /api/v1/categories endpoint (T012-T014, T021-T022)."""

    async def test_list_categories_returns_paginated_list(
        self, async_client: AsyncClient
    ) -> None:
        """Test category list returns paginated response structure (T012)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/categories")
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data
            assert isinstance(data["data"], list)

            # Check pagination metadata
            pagination = data["pagination"]
            assert "total" in pagination
            assert "limit" in pagination
            assert "offset" in pagination
            assert "has_more" in pagination
            assert pagination["limit"] == 20  # Default limit
            assert pagination["offset"] == 0  # Default offset

    async def test_list_categories_sorted_by_video_count_desc(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test category list sorted by video_count in descending order (T013)."""
        # Create test data with different video counts
        async with integration_session_factory() as session:
            # Clean up any existing test data
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.execute(delete(VideoCategory))
            await session.commit()

            # Create categories
            cat1 = VideoCategory(
                category_id="1",
                name="Category 1",
                assignable=True,
            )
            cat2 = VideoCategory(
                category_id="2",
                name="Category 2",
                assignable=True,
            )
            cat3 = VideoCategory(
                category_id="3",
                name="Category 3",
                assignable=True,
            )
            session.add_all([cat1, cat2, cat3])
            await session.flush()

            # Create channel for videos
            channel = Channel(
                channel_id="UC" + "T" * 22,
                title="Test Channel",
                is_subscribed=False,
            )
            session.add(channel)
            await session.flush()

            # Create videos with different category assignments
            # cat2 should have 3 videos, cat1 should have 2, cat3 should have 1
            videos = [
                Video(
                    video_id=f"vid_{i:03d}",
                    channel_id=channel.channel_id,
                    title=f"Video {i}",
                    upload_date=datetime.now(timezone.utc),
                    duration=300,
                    category_id="2" if i < 3 else ("1" if i < 5 else "3"),
                )
                for i in range(6)
            ]
            session.add_all(videos)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/categories")
            assert response.status_code == 200
            data = response.json()

            # Find our test categories
            test_cats = [c for c in data["data"] if c["category_id"] in ["1", "2", "3"]]

            if len(test_cats) >= 3:
                # Verify they are sorted by video_count DESC
                video_counts = [c["video_count"] for c in test_cats]
                assert video_counts == sorted(video_counts, reverse=True)

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.execute(delete(VideoCategory))
            await session.commit()

    async def test_list_categories_pagination_params(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test category list pagination parameters work correctly (T014)."""
        # Create test data with multiple categories
        async with integration_session_factory() as session:
            await session.execute(delete(VideoCategory))
            await session.commit()

            # Create 5 categories
            categories = [
                VideoCategory(
                    category_id=f"cat_{i}",
                    name=f"Category {i}",
                    assignable=True,
                )
                for i in range(5)
            ]
            session.add_all(categories)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Test with limit
            response = await async_client.get("/api/v1/categories?limit=2&offset=0")
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) <= 2
            assert data["pagination"]["limit"] == 2
            assert data["pagination"]["offset"] == 0

            # Test with offset
            response = await async_client.get("/api/v1/categories?limit=2&offset=2")
            assert response.status_code == 200
            data = response.json()
            assert data["pagination"]["offset"] == 2

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoCategory))
            await session.commit()

    async def test_list_categories_invalid_pagination(
        self, async_client: AsyncClient
    ) -> None:
        """Test category list validates pagination parameters (T021)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Test limit < 1
            response = await async_client.get("/api/v1/categories?limit=0")
            assert response.status_code == 422

            # Test limit > 100
            response = await async_client.get("/api/v1/categories?limit=101")
            assert response.status_code == 422

            # Test offset < 0
            response = await async_client.get("/api/v1/categories?offset=-1")
            assert response.status_code == 422

    async def test_list_categories_offset_exceeds_total(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test category list returns empty data when offset exceeds total (T022)."""
        # Ensure we have at least one category (max 10 chars for category_id)
        async with integration_session_factory() as session:
            await session.execute(delete(VideoCategory))
            await session.commit()

            cat = VideoCategory(
                category_id="95",
                name="Test Category",
                assignable=True,
            )
            session.add(cat)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Request with offset way beyond total
            response = await async_client.get("/api/v1/categories?limit=20&offset=1000")
            assert response.status_code == 200
            data = response.json()
            assert data["data"] == []
            assert data["pagination"]["has_more"] is False

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoCategory))
            await session.commit()


class TestGetCategory:
    """Tests for GET /api/v1/categories/{category_id} endpoint (T015-T016)."""

    async def test_get_category_returns_detail(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test category detail returns correct structure (T015)."""
        # Create test category (max 10 chars for category_id)
        async with integration_session_factory() as session:
            await session.execute(delete(VideoCategory).where(
                VideoCategory.category_id == "99"
            ))
            await session.commit()

            category = VideoCategory(
                category_id="99",
                name="Test Detail Category",
                assignable=True,
            )
            session.add(category)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/categories/99")
            assert response.status_code == 200
            data = response.json()

            assert "data" in data
            category_data = data["data"]
            assert category_data["category_id"] == "99"
            assert category_data["name"] == "Test Detail Category"
            assert category_data["assignable"] is True
            assert "video_count" in category_data
            assert "created_at" in category_data

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoCategory).where(
                VideoCategory.category_id == "99"
            ))
            await session.commit()

    async def test_get_category_not_found(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 response for non-existent category (T016)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/categories/nonexistent_category_xyz")
            assert response.status_code == 404
            data = response.json()
            # RFC 7807 format: code is at top level
            assert data["code"] == "NOT_FOUND"
            assert "Category" in data["detail"]
            # Check for actionable hint
            assert "Verify the category ID" in data["detail"]


class TestGetCategoryVideos:
    """Tests for GET /api/v1/categories/{category_id}/videos endpoint (T017-T019)."""

    async def test_get_category_videos_returns_paginated_list(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test category videos returns paginated response structure (T017)."""
        # Create test data (max 10 chars for category_id)
        async with integration_session_factory() as session:
            # Clean up (respect foreign key constraints)
            await session.execute(delete(VideoTag))
            await session.execute(delete(VideoTopic))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.execute(delete(VideoCategory).where(
                VideoCategory.category_id == "98"
            ))
            await session.commit()

            # Create category
            category = VideoCategory(
                category_id="98",
                name="Videos Test Category",
                assignable=True,
            )
            session.add(category)

            # Create channel
            channel = Channel(
                channel_id="UC" + "V" * 22,
                title="Videos Test Channel",
                is_subscribed=False,
            )
            session.add(channel)
            await session.flush()

            # Create video
            video = Video(
                video_id="vid_test_00",
                channel_id=channel.channel_id,
                title="Test Video",
                upload_date=datetime.now(timezone.utc),
                duration=300,
                category_id=category.category_id,
            )
            session.add(video)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/categories/98/videos"
            )
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data
            assert isinstance(data["data"], list)
            assert len(data["data"]) >= 1

            # Check video structure
            video = data["data"][0]
            assert "video_id" in video
            assert "title" in video
            assert "upload_date" in video
            assert "transcript_summary" in video

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag))
            await session.execute(delete(VideoTopic))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.execute(delete(VideoCategory).where(
                VideoCategory.category_id == "98"
            ))
            await session.commit()

    async def test_get_category_videos_excludes_deleted(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test category videos excludes deleted videos (T018)."""
        # Create test data with deleted video (max 10 chars for category_id)
        async with integration_session_factory() as session:
            # Clean up (respect foreign key constraints)
            await session.execute(delete(VideoTag))
            await session.execute(delete(VideoTopic))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.execute(delete(VideoCategory).where(
                VideoCategory.category_id == "97"
            ))
            await session.commit()

            # Create category
            category = VideoCategory(
                category_id="97",
                name="Deleted Test Category",
                assignable=True,
            )
            session.add(category)

            # Create channel
            channel = Channel(
                channel_id="UC" + "D" * 22,
                title="Deleted Test Channel",
                is_subscribed=False,
            )
            session.add(channel)
            await session.flush()

            # Create active and deleted videos
            video_active = Video(
                video_id="vid_active",
                channel_id=channel.channel_id,
                title="Active Video",
                upload_date=datetime.now(timezone.utc),
                duration=300,
                category_id=category.category_id,
                availability_status="available",
            )
            video_deleted = Video(
                video_id="vid_deleted",
                channel_id=channel.channel_id,
                title="Deleted Video",
                upload_date=datetime.now(timezone.utc),
                duration=300,
                category_id=category.category_id,
                availability_status="unavailable",
            )
            session.add_all([video_active, video_deleted])
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/categories/97/videos"
            )
            assert response.status_code == 200
            data = response.json()

            # Should only have 1 video (the active one)
            video_ids = [v["video_id"] for v in data["data"]]
            assert "vid_active" in video_ids
            assert "vid_deleted" not in video_ids

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag))
            await session.execute(delete(VideoTopic))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.execute(delete(VideoCategory).where(
                VideoCategory.category_id == "97"
            ))
            await session.commit()

    async def test_get_category_videos_sorted_by_upload_date_desc(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test category videos sorted by upload_date descending (T019)."""
        # Create test data with multiple videos (max 10 chars for category_id)
        async with integration_session_factory() as session:
            # Clean up (respect foreign key constraints)
            await session.execute(delete(VideoTag))
            await session.execute(delete(VideoTopic))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.execute(delete(VideoCategory).where(
                VideoCategory.category_id == "96"
            ))
            await session.commit()

            # Create category
            category = VideoCategory(
                category_id="96",
                name="Sort Test Category",
                assignable=True,
            )
            session.add(category)

            # Create channel
            channel = Channel(
                channel_id="UC" + "S" * 22,
                title="Sort Test Channel",
                is_subscribed=False,
            )
            session.add(channel)
            await session.flush()

            # Create videos with different upload dates
            from datetime import timedelta
            base_date = datetime.now(timezone.utc)
            videos = [
                Video(
                    video_id=f"vid_sort_{i}",
                    channel_id=channel.channel_id,
                    title=f"Sort Video {i}",
                    upload_date=base_date - timedelta(days=i),
                    duration=300,
                    category_id=category.category_id,
                )
                for i in range(3)
            ]
            session.add_all(videos)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/categories/96/videos"
            )
            assert response.status_code == 200
            data = response.json()

            # Verify sort order (newest first)
            if len(data["data"]) >= 2:
                upload_dates = [v["upload_date"] for v in data["data"]]
                # Convert to datetime for comparison
                from datetime import datetime as dt
                dates = [dt.fromisoformat(d.replace("Z", "+00:00")) for d in upload_dates]
                # Verify descending order
                for i in range(len(dates) - 1):
                    assert dates[i] >= dates[i + 1]

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag))
            await session.execute(delete(VideoTopic))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.execute(delete(VideoCategory).where(
                VideoCategory.category_id == "96"
            ))
            await session.commit()


class TestCategoryAuthRequirements:
    """Tests for authentication requirements on all category endpoints (T020)."""

    async def test_list_categories_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test GET /categories requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/categories")
            assert response.status_code == 401
            data = response.json()
            # Auth errors still use old format (HTTPException detail dict)
            assert data["detail"]["code"] == "NOT_AUTHENTICATED"

    async def test_get_category_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test GET /categories/{category_id} requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/categories/10")
            assert response.status_code == 401
            data = response.json()
            # Auth errors still use old format (HTTPException detail dict)
            assert data["detail"]["code"] == "NOT_AUTHENTICATED"

    async def test_get_category_videos_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test GET /categories/{category_id}/videos requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/categories/10/videos")
            assert response.status_code == 401
            data = response.json()
            # Auth errors still use old format (HTTPException detail dict)
            assert data["detail"]["code"] == "NOT_AUTHENTICATED"
