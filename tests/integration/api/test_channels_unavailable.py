"""Integration tests for channel detail endpoint with unavailable content (Feature 023).

Tests that the channel detail endpoint returns unavailable records instead of 404,
per FR-007, FR-009, and FR-020. Verifies that all availability_status values
return 200 with full metadata, and only truly non-existent channel IDs return 404.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel
from chronovista.models.enums import AvailabilityStatus

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def test_data_session(
    integration_session_factory,
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a session for test data setup and cleanup."""
    async with integration_session_factory() as session:
        yield session


@pytest.fixture
async def cleanup_test_channels(
    test_data_session: AsyncSession,
) -> AsyncGenerator[None, None]:
    """Cleanup test channels after tests complete."""
    yield

    # Clean up test channels
    test_channel_ids = [
        "UCunavail_av123456789012",  # available
        "UCunavail_del12345678901",  # deleted
        "UCunavail_ter12345678901",  # terminated
        "UCunavail_unv12345678901",  # unavailable
    ]
    await test_data_session.execute(
        delete(Channel).where(Channel.channel_id.in_(test_channel_ids))
    )
    await test_data_session.commit()


async def create_test_channel(
    session: AsyncSession,
    channel_id: str,
    availability_status: AvailabilityStatus,
) -> Channel:
    """Create a test channel with specified availability status.

    Parameters
    ----------
    session : AsyncSession
        Database session for creating the channel.
    channel_id : str
        24-character YouTube channel ID.
    availability_status : AvailabilityStatus
        The availability status to set.

    Returns
    -------
    Channel
        The created channel database model.
    """
    # Check if channel already exists
    result = await session.execute(
        select(Channel).where(Channel.channel_id == channel_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    channel = Channel(
        channel_id=channel_id,
        title=f"Test Channel - {availability_status.value}",
        description=f"Test channel for availability status: {availability_status.value}",
        subscriber_count=1000,
        video_count=50,
        availability_status=availability_status.value,
    )
    session.add(channel)
    await session.flush()
    await session.refresh(channel)
    return channel


class TestChannelDetailAvailableStatus:
    """Tests for channel detail endpoint with available status."""

    async def test_available_channel_returns_200(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        cleanup_test_channels: None,
    ) -> None:
        """Test that channel with availability_status='available' returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create available channel
            channel = await create_test_channel(
                test_data_session,
                "UCunavail_av123456789012",
                AvailabilityStatus.AVAILABLE,
            )
            await test_data_session.commit()

            response = await async_client.get(
                f"/api/v1/channels/{channel.channel_id}"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["channel_id"] == channel.channel_id
            assert data["data"]["availability_status"] == "available"


class TestChannelDetailUnavailableStatuses:
    """Tests for channel detail endpoint with various unavailable statuses."""

    async def test_deleted_channel_returns_200(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        cleanup_test_channels: None,
    ) -> None:
        """Test that channel with availability_status='deleted' returns 200 (NOT 404)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create deleted channel
            channel = await create_test_channel(
                test_data_session,
                "UCunavail_del12345678901",
                AvailabilityStatus.DELETED,
            )
            await test_data_session.commit()

            response = await async_client.get(
                f"/api/v1/channels/{channel.channel_id}"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["channel_id"] == channel.channel_id
            assert data["data"]["availability_status"] == "deleted"

    async def test_terminated_channel_returns_200(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        cleanup_test_channels: None,
    ) -> None:
        """Test that channel with availability_status='terminated' returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create terminated channel
            channel = await create_test_channel(
                test_data_session,
                "UCunavail_ter12345678901",
                AvailabilityStatus.TERMINATED,
            )
            await test_data_session.commit()

            response = await async_client.get(
                f"/api/v1/channels/{channel.channel_id}"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["channel_id"] == channel.channel_id
            assert data["data"]["availability_status"] == "terminated"

    async def test_unavailable_channel_returns_200(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        cleanup_test_channels: None,
    ) -> None:
        """Test that channel with availability_status='unavailable' returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create unavailable channel
            channel = await create_test_channel(
                test_data_session,
                "UCunavail_unv12345678901",
                AvailabilityStatus.UNAVAILABLE,
            )
            await test_data_session.commit()

            response = await async_client.get(
                f"/api/v1/channels/{channel.channel_id}"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["channel_id"] == channel.channel_id
            assert data["data"]["availability_status"] == "unavailable"


class TestChannelDetailNonExistent:
    """Tests for channel detail endpoint with non-existent channels."""

    async def test_nonexistent_channel_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        """Test that non-existent channel_id returns 404."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Use a valid 24-character channel ID that doesn't exist in the database
            response = await async_client.get(
                "/api/v1/channels/UC0000000000000000000000"
            )
            assert response.status_code == 404
            data = response.json()
            assert data["code"] == "NOT_FOUND"
            assert "Channel" in data["detail"]
            assert "UC0000000000000000000000" in data["detail"]


class TestChannelDetailResponseSchema:
    """Tests for channel detail response schema with unavailable content."""

    async def test_unavailable_channel_includes_availability_status(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        cleanup_test_channels: None,
    ) -> None:
        """Test that response includes availability_status field for unavailable channel."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create deleted channel
            channel = await create_test_channel(
                test_data_session,
                "UCunavail_del12345678901",
                AvailabilityStatus.DELETED,
            )
            await test_data_session.commit()

            response = await async_client.get(
                f"/api/v1/channels/{channel.channel_id}"
            )
            assert response.status_code == 200
            data = response.json()
            assert "availability_status" in data["data"]
            assert data["data"]["availability_status"] == "deleted"

    async def test_available_channel_has_no_banner_data_issues(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        cleanup_test_channels: None,
    ) -> None:
        """Test that available channel response doesn't have data integrity issues."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create available channel
            channel = await create_test_channel(
                test_data_session,
                "UCunavail_av123456789012",
                AvailabilityStatus.AVAILABLE,
            )
            await test_data_session.commit()

            response = await async_client.get(
                f"/api/v1/channels/{channel.channel_id}"
            )
            assert response.status_code == 200
            data = response.json()
            channel_data = data["data"]

            # Verify all standard fields are present
            required_fields = [
                "channel_id",
                "title",
                "description",
                "subscriber_count",
                "video_count",
                "thumbnail_url",
                "custom_url",
                "default_language",
                "country",
                "is_subscribed",
                "availability_status",
                "created_at",
                "updated_at",
            ]
            for field in required_fields:
                assert field in channel_data, f"Missing field: {field}"

            # Verify availability_status is correct
            assert channel_data["availability_status"] == "available"

    async def test_unavailable_channel_includes_all_metadata_fields(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        cleanup_test_channels: None,
    ) -> None:
        """Test that response includes all standard metadata fields for unavailable channel."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create unavailable channel
            channel = await create_test_channel(
                test_data_session,
                "UCunavail_unv12345678901",
                AvailabilityStatus.UNAVAILABLE,
            )
            await test_data_session.commit()

            response = await async_client.get(
                f"/api/v1/channels/{channel.channel_id}"
            )
            assert response.status_code == 200
            data = response.json()
            channel_data = data["data"]

            # Verify all standard fields are present
            required_fields = [
                "channel_id",
                "title",
                "description",
                "subscriber_count",
                "video_count",
                "thumbnail_url",
                "custom_url",
                "default_language",
                "country",
                "is_subscribed",
                "availability_status",
                "created_at",
                "updated_at",
            ]
            for field in required_fields:
                assert field in channel_data, f"Missing field: {field}"


class TestChannelListAvailabilityFilter:
    """Tests for channel list endpoint with include_unavailable parameter."""

    async def test_channel_list_with_include_unavailable_true(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        cleanup_test_channels: None,
    ) -> None:
        """Test that channel list with include_unavailable=true includes unavailable channels."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create both available and unavailable channels
            available_channel = await create_test_channel(
                test_data_session,
                "UCunavail_av123456789012",
                AvailabilityStatus.AVAILABLE,
            )
            unavailable_channel = await create_test_channel(
                test_data_session,
                "UCunavail_del12345678901",
                AvailabilityStatus.DELETED,
            )
            await test_data_session.commit()

            response = await async_client.get(
                "/api/v1/channels?include_unavailable=true"
            )
            assert response.status_code == 200
            data = response.json()

            # Get all channel IDs from response
            channel_ids = [ch["channel_id"] for ch in data["data"]]

            # Both channels should be in the results
            assert available_channel.channel_id in channel_ids
            assert unavailable_channel.channel_id in channel_ids

    async def test_channel_list_without_include_unavailable_excludes_unavailable(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        cleanup_test_channels: None,
    ) -> None:
        """Test that channel list without include_unavailable excludes unavailable channels."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create both available and unavailable channels
            available_channel = await create_test_channel(
                test_data_session,
                "UCunavail_av123456789012",
                AvailabilityStatus.AVAILABLE,
            )
            unavailable_channel = await create_test_channel(
                test_data_session,
                "UCunavail_del12345678901",
                AvailabilityStatus.DELETED,
            )
            await test_data_session.commit()

            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 200
            data = response.json()

            # Get all channel IDs from response
            channel_ids = [ch["channel_id"] for ch in data["data"]]

            # Only available channel should be in results
            assert available_channel.channel_id in channel_ids
            assert unavailable_channel.channel_id not in channel_ids

    async def test_channel_list_default_excludes_unavailable(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        cleanup_test_channels: None,
    ) -> None:
        """Test that channel list defaults to excluding unavailable channels."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create both available and unavailable channels
            available_channel = await create_test_channel(
                test_data_session,
                "UCunavail_av123456789012",
                AvailabilityStatus.AVAILABLE,
            )
            unavailable_channel = await create_test_channel(
                test_data_session,
                "UCunavail_del12345678901",
                AvailabilityStatus.DELETED,
            )
            await test_data_session.commit()

            # Don't pass include_unavailable parameter (defaults to False)
            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 200
            data = response.json()

            # Get all channel IDs from response
            channel_ids = [ch["channel_id"] for ch in data["data"]]

            # Only available channel should be in results
            assert available_channel.channel_id in channel_ids
            assert unavailable_channel.channel_id not in channel_ids

    async def test_channel_list_includes_availability_status_in_items(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        cleanup_test_channels: None,
    ) -> None:
        """Test that channel list items include availability_status field."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create channels with different statuses
            await create_test_channel(
                test_data_session,
                "UCunavail_av123456789012",
                AvailabilityStatus.AVAILABLE,
            )
            await create_test_channel(
                test_data_session,
                "UCunavail_del12345678901",
                AvailabilityStatus.DELETED,
            )
            await test_data_session.commit()

            # Request with include_unavailable=true to get both
            response = await async_client.get(
                "/api/v1/channels?include_unavailable=true"
            )
            assert response.status_code == 200
            data = response.json()

            # All items should have availability_status field
            for channel in data["data"]:
                assert "availability_status" in channel
                assert channel["availability_status"] in [
                    "available",
                    "deleted",
                    "terminated",
                    "unavailable",
                    "private",
                    "copyright",
                    "tos_violation",
                ]
