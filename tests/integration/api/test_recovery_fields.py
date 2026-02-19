"""Integration tests for recovered_at and recovery_source fields in API responses.

This module tests that the recovery metadata fields (recovered_at, recovery_source)
appear correctly in video and channel detail API responses.

Tests cover:
- Video detail endpoint - fields are null when not recovered
- Video detail endpoint - fields populated when recovered
- Channel detail endpoint - fields are null when not recovered
- Channel detail endpoint - fields populated when recovered
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
async def video_not_recovered(
    integration_session_factory,
) -> Dict[str, Any]:
    """
    Create a video with recovered_at=NULL and recovery_source=NULL.

    Returns video data dict for use in tests.
    """
    async with integration_session_factory() as session:
        # First create a channel for FK constraint
        channel = ChannelDB(
            channel_id="UCrec123456789012345678",
            title="Recovery Test Channel",
            description="Channel for recovery field tests",
            subscriber_count=500,
            video_count=10,
            availability_status="available",
        )

        # Check if channel already exists
        result = await session.execute(
            select(ChannelDB).where(ChannelDB.channel_id == channel.channel_id)
        )
        existing_channel = result.scalar_one_or_none()

        if not existing_channel:
            session.add(channel)
            await session.commit()
            await session.refresh(channel)

        # Create video without recovery fields (NULL)
        video = VideoDB(
            video_id="notrecovr01",  # 11 chars
            channel_id="UCrec123456789012345678",
            title="Not Recovered Video",
            description="A video that was never recovered",
            upload_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            duration=300,
            made_for_kids=False,
            availability_status="available",
            recovered_at=None,  # Explicitly NULL
            recovery_source=None,  # Explicitly NULL
        )

        # Check if video already exists
        result = await session.execute(
            select(VideoDB).where(VideoDB.video_id == video.video_id)
        )
        existing_video = result.scalar_one_or_none()

        if existing_video:
            # Update to ensure NULL values
            existing_video.recovered_at = None
            existing_video.recovery_source = None
            await session.commit()
            return {
                "video_id": existing_video.video_id,
                "title": existing_video.title,
                "recovered_at": existing_video.recovered_at,
                "recovery_source": existing_video.recovery_source,
            }

        session.add(video)
        await session.commit()
        await session.refresh(video)

        return {
            "video_id": video.video_id,
            "title": video.title,
            "recovered_at": video.recovered_at,
            "recovery_source": video.recovery_source,
        }


@pytest.fixture
async def video_recovered(
    integration_session_factory,
) -> Dict[str, Any]:
    """
    Create a video with recovered_at and recovery_source populated.

    Returns video data dict for use in tests.
    """
    async with integration_session_factory() as session:
        # First create a channel for FK constraint
        channel = ChannelDB(
            channel_id="UCrec123456789012345678",
            title="Recovery Test Channel",
            description="Channel for recovery field tests",
            subscriber_count=500,
            video_count=10,
            availability_status="available",
        )

        # Check if channel already exists
        result = await session.execute(
            select(ChannelDB).where(ChannelDB.channel_id == channel.channel_id)
        )
        existing_channel = result.scalar_one_or_none()

        if not existing_channel:
            session.add(channel)
            await session.commit()
            await session.refresh(channel)

        # Create video with recovery fields populated
        recovery_timestamp = datetime(2024, 2, 10, 14, 30, 0, tzinfo=timezone.utc)
        video = VideoDB(
            video_id="yesrecovr01",  # 11 chars
            channel_id="UCrec123456789012345678",
            title="Recovered Video",
            description="A video that was recovered from Wayback Machine",
            upload_date=datetime(2023, 5, 20, tzinfo=timezone.utc),
            duration=420,
            made_for_kids=False,
            availability_status="deleted",
            recovered_at=recovery_timestamp,
            recovery_source="wayback_machine",
        )

        # Check if video already exists
        result = await session.execute(
            select(VideoDB).where(VideoDB.video_id == video.video_id)
        )
        existing_video = result.scalar_one_or_none()

        if existing_video:
            # Update with recovery values
            existing_video.recovered_at = recovery_timestamp
            existing_video.recovery_source = "wayback_machine"
            await session.commit()
            return {
                "video_id": existing_video.video_id,
                "title": existing_video.title,
                "recovered_at": existing_video.recovered_at,
                "recovery_source": existing_video.recovery_source,
            }

        session.add(video)
        await session.commit()
        await session.refresh(video)

        return {
            "video_id": video.video_id,
            "title": video.title,
            "recovered_at": video.recovered_at,
            "recovery_source": video.recovery_source,
        }


@pytest.fixture
async def channel_not_recovered(
    integration_session_factory,
) -> Dict[str, Any]:
    """
    Create a channel with recovered_at=NULL and recovery_source=NULL.

    Returns channel data dict for use in tests.
    """
    async with integration_session_factory() as session:
        channel = ChannelDB(
            channel_id="UCnotrec1234567890123456",
            title="Not Recovered Channel",
            description="A channel that was never recovered",
            subscriber_count=1000,
            video_count=50,
            availability_status="available",
            recovered_at=None,  # Explicitly NULL
            recovery_source=None,  # Explicitly NULL
        )

        # Check if channel already exists
        result = await session.execute(
            select(ChannelDB).where(ChannelDB.channel_id == channel.channel_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update to ensure NULL values
            existing.recovered_at = None
            existing.recovery_source = None
            await session.commit()
            return {
                "channel_id": existing.channel_id,
                "title": existing.title,
                "recovered_at": existing.recovered_at,
                "recovery_source": existing.recovery_source,
            }

        session.add(channel)
        await session.commit()
        await session.refresh(channel)

        return {
            "channel_id": channel.channel_id,
            "title": channel.title,
            "recovered_at": channel.recovered_at,
            "recovery_source": channel.recovery_source,
        }


@pytest.fixture
async def channel_recovered(
    integration_session_factory,
) -> Dict[str, Any]:
    """
    Create a channel with recovered_at and recovery_source populated.

    Returns channel data dict for use in tests.
    """
    async with integration_session_factory() as session:
        recovery_timestamp = datetime(2024, 3, 5, 10, 15, 0, tzinfo=timezone.utc)
        channel = ChannelDB(
            channel_id="UCyesrec1234567890123456",
            title="Recovered Channel",
            description="A channel that was recovered from Wayback Machine",
            subscriber_count=5000,
            video_count=100,
            availability_status="terminated",
            recovered_at=recovery_timestamp,
            recovery_source="wayback_machine",
        )

        # Check if channel already exists
        result = await session.execute(
            select(ChannelDB).where(ChannelDB.channel_id == channel.channel_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update with recovery values
            existing.recovered_at = recovery_timestamp
            existing.recovery_source = "wayback_machine"
            await session.commit()
            return {
                "channel_id": existing.channel_id,
                "title": existing.title,
                "recovered_at": existing.recovered_at,
                "recovery_source": existing.recovery_source,
            }

        session.add(channel)
        await session.commit()
        await session.refresh(channel)

        return {
            "channel_id": channel.channel_id,
            "title": channel.title,
            "recovered_at": channel.recovered_at,
            "recovery_source": channel.recovery_source,
        }


# =============================================================================
# Video Detail Recovery Fields Tests
# =============================================================================


class TestVideoRecoveryFields:
    """Tests for recovered_at and recovery_source in video detail endpoint."""

    async def test_video_detail_fields_null_when_not_recovered(
        self,
        async_client: AsyncClient,
        video_not_recovered: Dict[str, Any],
    ) -> None:
        """Test that recovered_at and recovery_source are null for non-recovered video."""
        video_id = video_not_recovered["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(f"/api/v1/videos/{video_id}")

            assert response.status_code == 200
            data = response.json()

            # Check response structure
            assert "data" in data
            video_data = data["data"]

            # Verify recovery fields exist and are null
            assert "recovered_at" in video_data
            assert "recovery_source" in video_data
            assert video_data["recovered_at"] is None
            assert video_data["recovery_source"] is None

            # Verify other fields are present
            assert video_data["video_id"] == video_id
            assert video_data["title"] == video_not_recovered["title"]

    async def test_video_detail_fields_populated_when_recovered(
        self,
        async_client: AsyncClient,
        video_recovered: Dict[str, Any],
    ) -> None:
        """Test that recovered_at and recovery_source are populated for recovered video."""
        video_id = video_recovered["video_id"]
        expected_timestamp = video_recovered["recovered_at"]
        expected_source = video_recovered["recovery_source"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(f"/api/v1/videos/{video_id}")

            assert response.status_code == 200
            data = response.json()

            # Check response structure
            assert "data" in data
            video_data = data["data"]

            # Verify recovery fields exist and have correct values
            assert "recovered_at" in video_data
            assert "recovery_source" in video_data
            assert video_data["recovered_at"] is not None
            assert video_data["recovery_source"] == expected_source

            # Parse the timestamp and compare
            recovered_timestamp = datetime.fromisoformat(
                video_data["recovered_at"].replace("Z", "+00:00")
            )
            assert recovered_timestamp == expected_timestamp

            # Verify other fields are present
            assert video_data["video_id"] == video_id
            assert video_data["title"] == video_recovered["title"]


# =============================================================================
# Channel Detail Recovery Fields Tests
# =============================================================================


class TestChannelRecoveryFields:
    """Tests for recovered_at and recovery_source in channel detail endpoint."""

    async def test_channel_detail_fields_null_when_not_recovered(
        self,
        async_client: AsyncClient,
        channel_not_recovered: Dict[str, Any],
    ) -> None:
        """Test that recovered_at and recovery_source are null for non-recovered channel."""
        channel_id = channel_not_recovered["channel_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(f"/api/v1/channels/{channel_id}")

            assert response.status_code == 200
            data = response.json()

            # Check response structure
            assert "data" in data
            channel_data = data["data"]

            # Verify recovery fields exist and are null
            assert "recovered_at" in channel_data
            assert "recovery_source" in channel_data
            assert channel_data["recovered_at"] is None
            assert channel_data["recovery_source"] is None

            # Verify other fields are present
            assert channel_data["channel_id"] == channel_id
            assert channel_data["title"] == channel_not_recovered["title"]

    async def test_channel_detail_fields_populated_when_recovered(
        self,
        async_client: AsyncClient,
        channel_recovered: Dict[str, Any],
    ) -> None:
        """Test that recovered_at and recovery_source are populated for recovered channel."""
        channel_id = channel_recovered["channel_id"]
        expected_timestamp = channel_recovered["recovered_at"]
        expected_source = channel_recovered["recovery_source"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(f"/api/v1/channels/{channel_id}")

            assert response.status_code == 200
            data = response.json()

            # Check response structure
            assert "data" in data
            channel_data = data["data"]

            # Verify recovery fields exist and have correct values
            assert "recovered_at" in channel_data
            assert "recovery_source" in channel_data
            assert channel_data["recovered_at"] is not None
            assert channel_data["recovery_source"] == expected_source

            # Parse the timestamp and compare
            recovered_timestamp = datetime.fromisoformat(
                channel_data["recovered_at"].replace("Z", "+00:00")
            )
            assert recovered_timestamp == expected_timestamp

            # Verify other fields are present
            assert channel_data["channel_id"] == channel_id
            assert channel_data["title"] == channel_recovered["title"]
