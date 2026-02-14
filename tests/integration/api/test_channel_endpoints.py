"""Integration tests for channel API endpoints (Feature 011 - US1).

This module provides integration tests for the channel endpoints:
- GET /api/v1/channels - List channels with pagination
- GET /api/v1/channels/{channel_id} - Get channel details
- GET /api/v1/channels/{channel_id}/videos - Get channel videos

Tests cover:
- Authentication requirements (T018)
- List/pagination functionality (T016)
- Detail and not_found handling (T017)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import Video as VideoDB

pytestmark = pytest.mark.asyncio


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
async def sample_channel(
    integration_session_factory,
) -> Dict[str, Any]:
    """
    Create a sample channel in the database for testing.

    Returns channel data dict with channel_id for use in tests.
    """
    async with integration_session_factory() as session:
        # Create a test channel (channel_id must be exactly 24 chars starting with UC)
        channel = ChannelDB(
            channel_id="UCtest123456789012345678",
            title="Test Channel",
            description="A test channel for integration tests",
            subscriber_count=1000,
            video_count=50,
            thumbnail_url="https://example.com/thumbnail.jpg",
            is_subscribed=True,
            default_language="en",
            country="US",
        )

        # Check if channel already exists
        result = await session.execute(
            select(ChannelDB).where(ChannelDB.channel_id == channel.channel_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Return existing channel data
            return {
                "channel_id": existing.channel_id,
                "title": existing.title,
                "description": existing.description,
                "subscriber_count": existing.subscriber_count,
                "video_count": existing.video_count,
            }

        session.add(channel)
        await session.commit()
        await session.refresh(channel)

        return {
            "channel_id": channel.channel_id,
            "title": channel.title,
            "description": channel.description,
            "subscriber_count": channel.subscriber_count,
            "video_count": channel.video_count,
        }


@pytest.fixture
async def sample_channel_with_videos(
    integration_session_factory,
    sample_channel: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a sample channel with associated videos.

    Returns channel data dict including video_ids for testing.
    """
    async with integration_session_factory() as session:
        channel_id = sample_channel["channel_id"]
        video_ids = []

        # Create sample videos for the channel
        for i in range(3):
            video_id = f"testvid{i:04d}"
            video = VideoDB(
                video_id=video_id,
                channel_id=channel_id,
                title=f"Test Video {i + 1}",
                description=f"Description for test video {i + 1}",
                upload_date=datetime(2024, 1, 15 + i, tzinfo=timezone.utc),
                duration=300 + (i * 60),
                view_count=1000 * (i + 1),
                made_for_kids=False,
                availability_status="available",
            )

            # Check if video already exists
            result = await session.execute(
                select(VideoDB).where(VideoDB.video_id == video.video_id)
            )
            existing = result.scalar_one_or_none()

            if not existing:
                session.add(video)

            video_ids.append(video_id)

        await session.commit()

        return {
            **sample_channel,
            "video_ids": video_ids,
        }


@pytest.fixture
async def channel_without_videos(
    integration_session_factory,
) -> Dict[str, Any]:
    """
    Create a channel with no videos for testing has_videos filter.

    Returns channel data dict.
    """
    async with integration_session_factory() as session:
        # Channel ID must be exactly 24 chars starting with UC
        channel = ChannelDB(
            channel_id="UCempty12345678901234567",
            title="Empty Channel",
            description="A channel with no videos",
            subscriber_count=100,
            video_count=0,
            is_subscribed=False,
        )

        # Check if channel already exists
        result = await session.execute(
            select(ChannelDB).where(ChannelDB.channel_id == channel.channel_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            return {
                "channel_id": existing.channel_id,
                "title": existing.title,
                "video_count": existing.video_count,
            }

        session.add(channel)
        await session.commit()
        await session.refresh(channel)

        return {
            "channel_id": channel.channel_id,
            "title": channel.title,
            "video_count": channel.video_count,
        }


# =============================================================================
# T018: Authentication Tests
# =============================================================================


class TestChannelAuth:
    """Tests for channel endpoint authentication requirements (T018)."""

    async def test_list_channels_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test that channel list requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 401

    async def test_get_channel_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test that channel detail requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get(
                "/api/v1/channels/UCtest123456789012345678"
            )
            assert response.status_code == 401

    async def test_get_channel_videos_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test that channel videos endpoint requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get(
                "/api/v1/channels/UCtest123456789012345678/videos"
            )
            assert response.status_code == 401


# =============================================================================
# T016: List and Pagination Tests
# =============================================================================


class TestListChannels:
    """Tests for GET /api/v1/channels endpoint (T016)."""

    async def test_list_channels_returns_paginated_response(
        self,
        async_client: AsyncClient,
        sample_channel: Dict[str, Any],
    ) -> None:
        """Test channel list returns paginated response structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data
            assert isinstance(data["data"], list)

    async def test_list_channels_pagination_metadata(
        self,
        async_client: AsyncClient,
        sample_channel: Dict[str, Any],
    ) -> None:
        """Test pagination metadata contains required fields."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/channels?limit=10&offset=0")
            assert response.status_code == 200
            data = response.json()

            pagination = data["pagination"]
            assert "total" in pagination
            assert "limit" in pagination
            assert "offset" in pagination
            assert "has_more" in pagination
            assert pagination["limit"] == 10
            assert pagination["offset"] == 0

    async def test_list_channels_default_pagination(
        self,
        async_client: AsyncClient,
        sample_channel: Dict[str, Any],
    ) -> None:
        """Test default pagination values (limit=20, offset=0)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 200
            data = response.json()

            assert data["pagination"]["limit"] == 20
            assert data["pagination"]["offset"] == 0

    async def test_list_channels_limit_validation_max(
        self, async_client: AsyncClient
    ) -> None:
        """Test limit validation (max 100)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/channels?limit=200")
            assert response.status_code == 422

    async def test_list_channels_limit_validation_min(
        self, async_client: AsyncClient
    ) -> None:
        """Test limit validation (min 1)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/channels?limit=0")
            assert response.status_code == 422

    async def test_list_channels_offset_validation(
        self, async_client: AsyncClient
    ) -> None:
        """Test offset validation (must be >= 0)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/channels?offset=-1")
            assert response.status_code == 422

    async def test_list_channels_item_structure(
        self,
        async_client: AsyncClient,
        sample_channel: Dict[str, Any],
    ) -> None:
        """Test channel list items have correct structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 200
            data = response.json()

            if data["data"]:
                channel = data["data"][0]
                assert "channel_id" in channel
                assert "title" in channel
                assert "description" in channel
                assert "subscriber_count" in channel
                assert "video_count" in channel
                assert "thumbnail_url" in channel
                assert "custom_url" in channel

    async def test_list_channels_has_videos_filter_true(
        self,
        async_client: AsyncClient,
        sample_channel: Dict[str, Any],
        channel_without_videos: Dict[str, Any],
    ) -> None:
        """Test has_videos=true filter returns only channels with videos."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/channels?has_videos=true")
            assert response.status_code == 200
            data = response.json()

            # All returned channels should have video_count > 0
            for channel in data["data"]:
                assert channel["video_count"] is not None
                assert channel["video_count"] > 0

    async def test_list_channels_has_videos_filter_false(
        self,
        async_client: AsyncClient,
        channel_without_videos: Dict[str, Any],
    ) -> None:
        """Test has_videos=false filter returns only channels without videos."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/channels?has_videos=false")
            assert response.status_code == 200
            data = response.json()

            # All returned channels should have video_count == 0 or None
            for channel in data["data"]:
                assert channel["video_count"] is None or channel["video_count"] == 0

    async def test_list_channels_ordered_by_video_count(
        self,
        async_client: AsyncClient,
        sample_channel: Dict[str, Any],
        channel_without_videos: Dict[str, Any],
    ) -> None:
        """Test channels are ordered by video_count descending."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 200
            data = response.json()

            if len(data["data"]) >= 2:
                # Verify descending order (accounting for nulls)
                video_counts = [
                    c.get("video_count") or 0 for c in data["data"]
                ]
                for i in range(len(video_counts) - 1):
                    assert video_counts[i] >= video_counts[i + 1]


# =============================================================================
# T017: Detail and Not Found Tests
# =============================================================================


class TestChannelDetail:
    """Tests for GET /api/v1/channels/{channel_id} endpoint (T017)."""

    async def test_get_channel_detail(
        self,
        async_client: AsyncClient,
        sample_channel: Dict[str, Any],
    ) -> None:
        """Test getting channel details by ID."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/channels/{sample_channel['channel_id']}"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["channel_id"] == sample_channel["channel_id"]
            assert data["data"]["title"] == sample_channel["title"]

    async def test_get_channel_detail_structure(
        self,
        async_client: AsyncClient,
        sample_channel: Dict[str, Any],
    ) -> None:
        """Test channel detail response has all expected fields."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/channels/{sample_channel['channel_id']}"
            )
            assert response.status_code == 200
            data = response.json()

            channel = data["data"]
            # ChannelListItem fields
            assert "channel_id" in channel
            assert "title" in channel
            assert "description" in channel
            assert "subscriber_count" in channel
            assert "video_count" in channel
            assert "thumbnail_url" in channel
            assert "custom_url" in channel
            # ChannelDetail additional fields
            assert "default_language" in channel
            assert "country" in channel
            assert "is_subscribed" in channel
            assert "created_at" in channel
            assert "updated_at" in channel

    async def test_get_channel_not_found(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 response for non-existent channel."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/channels/UC0000000000000000000000"
            )
            assert response.status_code == 404
            data = response.json()
            # RFC 7807 format: code is at top level
            assert data["code"] == "NOT_FOUND"
            assert "Channel" in data["detail"]

    async def test_get_channel_actionable_error_message(
        self, async_client: AsyncClient
    ) -> None:
        """Test that 404 error has actionable hint."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/channels/UC0000000000000000000000"
            )
            data = response.json()
            # RFC 7807 format: Check for actionable guidance in detail field
            assert "Verify the channel ID or run a sync" in data["detail"]

    async def test_get_channel_id_validation_too_short(
        self, async_client: AsyncClient
    ) -> None:
        """Test channel_id must be exactly 24 characters (too short)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/channels/short")
            assert response.status_code == 422

    async def test_get_channel_id_validation_too_long(
        self, async_client: AsyncClient
    ) -> None:
        """Test channel_id must be exactly 24 characters (too long)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/channels/UC0000000000000000000000000000000000"
            )
            assert response.status_code == 422


# =============================================================================
# Channel Videos Tests (T014)
# =============================================================================


class TestChannelVideos:
    """Tests for GET /api/v1/channels/{channel_id}/videos endpoint."""

    async def test_get_channel_videos_returns_videos(
        self,
        async_client: AsyncClient,
        sample_channel_with_videos: Dict[str, Any],
    ) -> None:
        """Test getting videos for a channel returns video list."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/channels/{sample_channel_with_videos['channel_id']}/videos"
            )
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data
            assert isinstance(data["data"], list)

    async def test_get_channel_videos_empty_channel(
        self,
        async_client: AsyncClient,
        channel_without_videos: Dict[str, Any],
    ) -> None:
        """Test getting videos for channel with no videos returns empty list."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/channels/{channel_without_videos['channel_id']}/videos"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["data"] == []
            assert data["pagination"]["total"] == 0

    async def test_get_channel_videos_not_found_channel(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 when channel does not exist."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/channels/UC0000000000000000000000/videos"
            )
            assert response.status_code == 404
            data = response.json()
            # RFC 7807 format: code is at top level
            assert data["code"] == "NOT_FOUND"

    async def test_get_channel_videos_pagination(
        self,
        async_client: AsyncClient,
        sample_channel_with_videos: Dict[str, Any],
    ) -> None:
        """Test pagination works for channel videos."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/channels/{sample_channel_with_videos['channel_id']}/videos"
                "?limit=2&offset=0"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["pagination"]["limit"] == 2
            assert data["pagination"]["offset"] == 0

    async def test_get_channel_videos_item_structure(
        self,
        async_client: AsyncClient,
        sample_channel_with_videos: Dict[str, Any],
    ) -> None:
        """Test video list items have correct structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/channels/{sample_channel_with_videos['channel_id']}/videos"
            )
            assert response.status_code == 200
            data = response.json()

            if data["data"]:
                video = data["data"][0]
                assert "video_id" in video
                assert "title" in video
                assert "channel_id" in video
                assert "upload_date" in video
                assert "duration" in video
                assert "transcript_summary" in video

    async def test_get_channel_videos_ordered_by_upload_date(
        self,
        async_client: AsyncClient,
        sample_channel_with_videos: Dict[str, Any],
    ) -> None:
        """Test videos are ordered by upload_date descending."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/channels/{sample_channel_with_videos['channel_id']}/videos"
            )
            assert response.status_code == 200
            data = response.json()

            if len(data["data"]) >= 2:
                dates = [v["upload_date"] for v in data["data"]]
                # Verify descending order
                for i in range(len(dates) - 1):
                    assert dates[i] >= dates[i + 1]
