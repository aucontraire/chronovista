"""Integration tests for T033 — Recovery Idempotency Guard.

This module tests the idempotency guard added to both video and channel
recovery endpoints. When an entity was recovered within the last 5 minutes,
the endpoint should return a 200 with success=True and empty fields_recovered
instead of calling the Wayback Machine orchestrator again.

Tests cover:
- Entity recovered < 5 min ago -> returns 200 with empty fields_recovered
- Entity recovered > 5 min ago -> proceeds normally to orchestrator
- Entity never recovered (recovered_at is None) -> proceeds normally
- Edge case: recovered_at exactly 5 min ago -> proceeds normally
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import Video as VideoDB
from chronovista.models.enums import AvailabilityStatus
from chronovista.services.recovery.models import ChannelRecoveryResult, RecoveryResult

pytestmark = pytest.mark.asyncio


# =============================================================================
# Video Recovery Idempotency Fixtures
# =============================================================================


@pytest.fixture
async def idempotency_channel(
    integration_session_factory,
) -> Dict[str, Any]:
    """
    Create a test channel for FK constraints in idempotency tests.

    Returns channel data dict for use in tests.
    """
    async with integration_session_factory() as session:
        channel = ChannelDB(
            channel_id="UCidempotency_test012345",
            title="Idempotency Test Channel",
            description="Channel for idempotency guard tests",
            subscriber_count=1000,
            video_count=50,
            availability_status=AvailabilityStatus.AVAILABLE.value,
        )

        result = await session.execute(
            select(ChannelDB).where(ChannelDB.channel_id == channel.channel_id)
        )
        existing = result.scalar_one_or_none()

        if not existing:
            session.add(channel)
            await session.commit()
            await session.refresh(channel)
        else:
            channel = existing

        return {
            "channel_id": channel.channel_id,
            "title": channel.title,
        }


@pytest.fixture
async def recently_recovered_video(
    integration_session_factory,
    idempotency_channel: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a deleted video that was recovered 2 minutes ago.

    This should trigger the idempotency guard (< 5 min).
    """
    async with integration_session_factory() as session:
        recovered_time = datetime.now(timezone.utc) - timedelta(minutes=2)

        video = VideoDB(
            video_id="recvid00001",  # 11 chars
            channel_id=idempotency_channel["channel_id"],
            title="Recently Recovered Video",
            description="Recovered 2 minutes ago",
            upload_date=datetime(2023, 1, 15, tzinfo=timezone.utc),
            duration=300,
            made_for_kids=False,
            availability_status=AvailabilityStatus.DELETED.value,
            recovered_at=recovered_time,
            recovery_source="wayback:20220106075526",
        )

        result = await session.execute(
            select(VideoDB).where(VideoDB.video_id == video.video_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.availability_status = AvailabilityStatus.DELETED.value
            existing.recovered_at = recovered_time
            existing.recovery_source = "wayback:20220106075526"
            await session.commit()
            return {
                "video_id": existing.video_id,
                "recovered_at": recovered_time,
            }

        session.add(video)
        await session.commit()
        await session.refresh(video)

        return {
            "video_id": video.video_id,
            "recovered_at": recovered_time,
        }


@pytest.fixture
async def stale_recovered_video(
    integration_session_factory,
    idempotency_channel: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a deleted video that was recovered 10 minutes ago.

    This should NOT trigger the idempotency guard (> 5 min).
    """
    async with integration_session_factory() as session:
        recovered_time = datetime.now(timezone.utc) - timedelta(minutes=10)

        video = VideoDB(
            video_id="oldvid00001",  # 11 chars
            channel_id=idempotency_channel["channel_id"],
            title="Stale Recovered Video",
            description="Recovered 10 minutes ago",
            upload_date=datetime(2023, 1, 15, tzinfo=timezone.utc),
            duration=300,
            made_for_kids=False,
            availability_status=AvailabilityStatus.DELETED.value,
            recovered_at=recovered_time,
            recovery_source="wayback:20220106075526",
        )

        result = await session.execute(
            select(VideoDB).where(VideoDB.video_id == video.video_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.availability_status = AvailabilityStatus.DELETED.value
            existing.recovered_at = recovered_time
            existing.recovery_source = "wayback:20220106075526"
            await session.commit()
            return {
                "video_id": existing.video_id,
                "recovered_at": recovered_time,
            }

        session.add(video)
        await session.commit()
        await session.refresh(video)

        return {
            "video_id": video.video_id,
            "recovered_at": recovered_time,
        }


@pytest.fixture
async def never_recovered_video(
    integration_session_factory,
    idempotency_channel: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a deleted video that has never been recovered (recovered_at is None).

    This should NOT trigger the idempotency guard.
    """
    async with integration_session_factory() as session:
        video = VideoDB(
            video_id="nevvid00001",  # 11 chars
            channel_id=idempotency_channel["channel_id"],
            title="Never Recovered Video",
            description="Has never been recovered",
            upload_date=datetime(2023, 1, 15, tzinfo=timezone.utc),
            duration=300,
            made_for_kids=False,
            availability_status=AvailabilityStatus.DELETED.value,
            recovered_at=None,
            recovery_source=None,
        )

        result = await session.execute(
            select(VideoDB).where(VideoDB.video_id == video.video_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.availability_status = AvailabilityStatus.DELETED.value
            existing.recovered_at = None
            existing.recovery_source = None
            await session.commit()
            return {"video_id": existing.video_id}

        session.add(video)
        await session.commit()
        await session.refresh(video)

        return {"video_id": video.video_id}


@pytest.fixture
async def edge_case_video(
    integration_session_factory,
    idempotency_channel: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a deleted video recovered exactly 5 minutes ago.

    At exactly 5 minutes, timedelta(minutes=5) is NOT less than
    timedelta(minutes=5), so the guard should NOT trigger.
    """
    async with integration_session_factory() as session:
        recovered_time = datetime.now(timezone.utc) - timedelta(minutes=5)

        video = VideoDB(
            video_id="edgvid00001",  # 11 chars
            channel_id=idempotency_channel["channel_id"],
            title="Edge Case Video",
            description="Recovered exactly 5 minutes ago",
            upload_date=datetime(2023, 1, 15, tzinfo=timezone.utc),
            duration=300,
            made_for_kids=False,
            availability_status=AvailabilityStatus.DELETED.value,
            recovered_at=recovered_time,
            recovery_source="wayback:20220106075526",
        )

        result = await session.execute(
            select(VideoDB).where(VideoDB.video_id == video.video_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.availability_status = AvailabilityStatus.DELETED.value
            existing.recovered_at = recovered_time
            existing.recovery_source = "wayback:20220106075526"
            await session.commit()
            return {
                "video_id": existing.video_id,
                "recovered_at": recovered_time,
            }

        session.add(video)
        await session.commit()
        await session.refresh(video)

        return {
            "video_id": video.video_id,
            "recovered_at": recovered_time,
        }


# =============================================================================
# Channel Recovery Idempotency Fixtures
# =============================================================================


@pytest.fixture
async def recently_recovered_channel(
    integration_session_factory,
) -> Dict[str, Any]:
    """
    Create a deleted channel that was recovered 2 minutes ago.

    This should trigger the idempotency guard (< 5 min).
    """
    async with integration_session_factory() as session:
        recovered_time = datetime.now(timezone.utc) - timedelta(minutes=2)

        channel = ChannelDB(
            channel_id="UCrecent_recovery_test01",
            title="Recently Recovered Channel",
            description="Recovered 2 minutes ago",
            subscriber_count=500,
            video_count=20,
            availability_status=AvailabilityStatus.DELETED.value,
            recovered_at=recovered_time,
            recovery_source="wayback:20220106075526",
        )

        result = await session.execute(
            select(ChannelDB).where(ChannelDB.channel_id == channel.channel_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.availability_status = AvailabilityStatus.DELETED.value
            existing.recovered_at = recovered_time
            existing.recovery_source = "wayback:20220106075526"
            await session.commit()
            return {
                "channel_id": existing.channel_id,
                "recovered_at": recovered_time,
            }

        session.add(channel)
        await session.commit()
        await session.refresh(channel)

        return {
            "channel_id": channel.channel_id,
            "recovered_at": recovered_time,
        }


@pytest.fixture
async def stale_recovered_channel(
    integration_session_factory,
) -> Dict[str, Any]:
    """
    Create a deleted channel that was recovered 10 minutes ago.

    This should NOT trigger the idempotency guard (> 5 min).
    """
    async with integration_session_factory() as session:
        recovered_time = datetime.now(timezone.utc) - timedelta(minutes=10)

        channel = ChannelDB(
            channel_id="UCstale_recovery_test001",
            title="Stale Recovered Channel",
            description="Recovered 10 minutes ago",
            subscriber_count=500,
            video_count=20,
            availability_status=AvailabilityStatus.DELETED.value,
            recovered_at=recovered_time,
            recovery_source="wayback:20220106075526",
        )

        result = await session.execute(
            select(ChannelDB).where(ChannelDB.channel_id == channel.channel_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.availability_status = AvailabilityStatus.DELETED.value
            existing.recovered_at = recovered_time
            existing.recovery_source = "wayback:20220106075526"
            await session.commit()
            return {
                "channel_id": existing.channel_id,
                "recovered_at": recovered_time,
            }

        session.add(channel)
        await session.commit()
        await session.refresh(channel)

        return {
            "channel_id": channel.channel_id,
            "recovered_at": recovered_time,
        }


@pytest.fixture
async def never_recovered_channel(
    integration_session_factory,
) -> Dict[str, Any]:
    """
    Create a deleted channel that has never been recovered.

    This should NOT trigger the idempotency guard.
    """
    async with integration_session_factory() as session:
        channel = ChannelDB(
            channel_id="UCnever_recovery_test001",
            title="Never Recovered Channel",
            description="Has never been recovered",
            subscriber_count=500,
            video_count=20,
            availability_status=AvailabilityStatus.DELETED.value,
            recovered_at=None,
            recovery_source=None,
        )

        result = await session.execute(
            select(ChannelDB).where(ChannelDB.channel_id == channel.channel_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.availability_status = AvailabilityStatus.DELETED.value
            existing.recovered_at = None
            existing.recovery_source = None
            await session.commit()
            return {"channel_id": existing.channel_id}

        session.add(channel)
        await session.commit()
        await session.refresh(channel)

        return {"channel_id": channel.channel_id}


@pytest.fixture
async def edge_case_channel(
    integration_session_factory,
) -> Dict[str, Any]:
    """
    Create a deleted channel recovered exactly 5 minutes ago.

    At exactly 5 minutes, the guard should NOT trigger.
    """
    async with integration_session_factory() as session:
        recovered_time = datetime.now(timezone.utc) - timedelta(minutes=5)

        channel = ChannelDB(
            channel_id="UCedge_recovery_test0001",
            title="Edge Case Channel",
            description="Recovered exactly 5 minutes ago",
            subscriber_count=500,
            video_count=20,
            availability_status=AvailabilityStatus.DELETED.value,
            recovered_at=recovered_time,
            recovery_source="wayback:20220106075526",
        )

        result = await session.execute(
            select(ChannelDB).where(ChannelDB.channel_id == channel.channel_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.availability_status = AvailabilityStatus.DELETED.value
            existing.recovered_at = recovered_time
            existing.recovery_source = "wayback:20220106075526"
            await session.commit()
            return {
                "channel_id": existing.channel_id,
                "recovered_at": recovered_time,
            }

        session.add(channel)
        await session.commit()
        await session.refresh(channel)

        return {
            "channel_id": channel.channel_id,
            "recovered_at": recovered_time,
        }


# =============================================================================
# Video Recovery Idempotency Tests
# =============================================================================


class TestVideoRecoveryIdempotency:
    """Tests for video recovery idempotency guard (T033)."""

    async def test_recently_recovered_video_returns_cached(
        self,
        async_client: AsyncClient,
        recently_recovered_video: Dict[str, Any],
    ) -> None:
        """
        Video recovered < 5 min ago should return 200 with empty fields_recovered.

        The orchestrator should NOT be called, protecting the Wayback Machine
        rate budget.
        """
        video_id = recently_recovered_video["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            with patch(
                "chronovista.services.recovery.orchestrator.recover_video",
                new_callable=AsyncMock,
            ) as mock_recover:
                response = await async_client.post(
                    f"/api/v1/videos/{video_id}/recover"
                )

                assert response.status_code == 200
                data = response.json()

                # Verify response structure
                assert "data" in data
                result_data = data["data"]

                # Verify idempotency guard response
                assert result_data["video_id"] == video_id
                assert result_data["success"] is True
                assert result_data["fields_recovered"] == []
                assert result_data["failure_reason"] is None
                assert result_data["duration_seconds"] == 0.0

                # Orchestrator should NOT have been called
                mock_recover.assert_not_called()

    async def test_stale_recovered_video_proceeds_to_orchestrator(
        self,
        async_client: AsyncClient,
        stale_recovered_video: Dict[str, Any],
    ) -> None:
        """
        Video recovered > 5 min ago should proceed normally to orchestrator.

        The idempotency guard should not block the request.
        """
        video_id = stale_recovered_video["video_id"]

        mock_result = RecoveryResult(
            video_id=video_id,
            success=True,
            snapshot_used="20220106075526",
            fields_recovered=["title", "description"],
            snapshots_available=10,
            snapshots_tried=2,
            duration_seconds=1.5,
        )

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            with patch(
                "chronovista.services.recovery.orchestrator.recover_video",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_recover:
                response = await async_client.post(
                    f"/api/v1/videos/{video_id}/recover"
                )

                assert response.status_code == 200
                data = response.json()

                result_data = data["data"]
                assert result_data["fields_recovered"] == ["title", "description"]
                assert result_data["snapshot_used"] == "20220106075526"

                # Orchestrator SHOULD have been called
                mock_recover.assert_called_once()

    async def test_never_recovered_video_proceeds_to_orchestrator(
        self,
        async_client: AsyncClient,
        never_recovered_video: Dict[str, Any],
    ) -> None:
        """
        Video with recovered_at=None should proceed normally to orchestrator.

        The idempotency guard should not block the request.
        """
        video_id = never_recovered_video["video_id"]

        mock_result = RecoveryResult(
            video_id=video_id,
            success=True,
            snapshot_used="20220106075526",
            fields_recovered=["title"],
            snapshots_available=5,
            snapshots_tried=1,
            duration_seconds=1.0,
        )

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            with patch(
                "chronovista.services.recovery.orchestrator.recover_video",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_recover:
                response = await async_client.post(
                    f"/api/v1/videos/{video_id}/recover"
                )

                assert response.status_code == 200
                data = response.json()

                result_data = data["data"]
                assert result_data["fields_recovered"] == ["title"]

                # Orchestrator SHOULD have been called
                mock_recover.assert_called_once()

    async def test_edge_case_exactly_5_min_proceeds(
        self,
        async_client: AsyncClient,
        edge_case_video: Dict[str, Any],
    ) -> None:
        """
        Video recovered exactly 5 min ago should proceed to orchestrator.

        The guard uses strict less-than: elapsed < 5 min. At exactly 5 min
        (or slightly over due to test execution time), the guard should
        NOT trigger.
        """
        video_id = edge_case_video["video_id"]

        mock_result = RecoveryResult(
            video_id=video_id,
            success=True,
            snapshot_used="20220106075526",
            fields_recovered=["title"],
            snapshots_available=5,
            snapshots_tried=1,
            duration_seconds=1.0,
        )

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            with patch(
                "chronovista.services.recovery.orchestrator.recover_video",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_recover:
                response = await async_client.post(
                    f"/api/v1/videos/{video_id}/recover"
                )

                assert response.status_code == 200

                # Orchestrator SHOULD have been called (exactly 5 min is not < 5 min)
                mock_recover.assert_called_once()


# =============================================================================
# Channel Recovery Idempotency Tests
# =============================================================================


class TestChannelRecoveryIdempotency:
    """Tests for channel recovery idempotency guard (T033)."""

    async def test_recently_recovered_channel_returns_cached(
        self,
        async_client: AsyncClient,
        recently_recovered_channel: Dict[str, Any],
    ) -> None:
        """
        Channel recovered < 5 min ago should return 200 with empty fields_recovered.

        The orchestrator should NOT be called, protecting the Wayback Machine
        rate budget.
        """
        channel_id = recently_recovered_channel["channel_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            with patch(
                "chronovista.services.recovery.orchestrator.recover_channel",
                new_callable=AsyncMock,
            ) as mock_recover:
                response = await async_client.post(
                    f"/api/v1/channels/{channel_id}/recover"
                )

                assert response.status_code == 200
                data = response.json()

                # Verify response structure
                assert "data" in data
                result_data = data["data"]

                # Verify idempotency guard response
                assert result_data["channel_id"] == channel_id
                assert result_data["success"] is True
                assert result_data["fields_recovered"] == []
                assert result_data["failure_reason"] is None
                assert result_data["duration_seconds"] == 0.0

                # Orchestrator should NOT have been called
                mock_recover.assert_not_called()

    async def test_stale_recovered_channel_proceeds_to_orchestrator(
        self,
        async_client: AsyncClient,
        stale_recovered_channel: Dict[str, Any],
    ) -> None:
        """
        Channel recovered > 5 min ago should proceed normally to orchestrator.

        The idempotency guard should not block the request.
        """
        channel_id = stale_recovered_channel["channel_id"]

        mock_result = ChannelRecoveryResult(
            channel_id=channel_id,
            success=True,
            snapshot_used="20220106075526",
            fields_recovered=["title", "description"],
            snapshots_available=10,
            snapshots_tried=2,
            duration_seconds=1.5,
        )

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            with patch(
                "chronovista.services.recovery.orchestrator.recover_channel",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_recover:
                response = await async_client.post(
                    f"/api/v1/channels/{channel_id}/recover"
                )

                assert response.status_code == 200
                data = response.json()

                result_data = data["data"]
                assert result_data["fields_recovered"] == ["title", "description"]
                assert result_data["snapshot_used"] == "20220106075526"

                # Orchestrator SHOULD have been called
                mock_recover.assert_called_once()

    async def test_never_recovered_channel_proceeds_to_orchestrator(
        self,
        async_client: AsyncClient,
        never_recovered_channel: Dict[str, Any],
    ) -> None:
        """
        Channel with recovered_at=None should proceed normally to orchestrator.

        The idempotency guard should not block the request.
        """
        channel_id = never_recovered_channel["channel_id"]

        mock_result = ChannelRecoveryResult(
            channel_id=channel_id,
            success=True,
            snapshot_used="20220106075526",
            fields_recovered=["title"],
            snapshots_available=5,
            snapshots_tried=1,
            duration_seconds=1.0,
        )

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            with patch(
                "chronovista.services.recovery.orchestrator.recover_channel",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_recover:
                response = await async_client.post(
                    f"/api/v1/channels/{channel_id}/recover"
                )

                assert response.status_code == 200
                data = response.json()

                result_data = data["data"]
                assert result_data["fields_recovered"] == ["title"]

                # Orchestrator SHOULD have been called
                mock_recover.assert_called_once()

    async def test_edge_case_exactly_5_min_proceeds(
        self,
        async_client: AsyncClient,
        edge_case_channel: Dict[str, Any],
    ) -> None:
        """
        Channel recovered exactly 5 min ago should proceed to orchestrator.

        The guard uses strict less-than: elapsed < 5 min. At exactly 5 min
        (or slightly over due to test execution time), the guard should
        NOT trigger.
        """
        channel_id = edge_case_channel["channel_id"]

        mock_result = ChannelRecoveryResult(
            channel_id=channel_id,
            success=True,
            snapshot_used="20220106075526",
            fields_recovered=["title"],
            snapshots_available=5,
            snapshots_tried=1,
            duration_seconds=1.0,
        )

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            with patch(
                "chronovista.services.recovery.orchestrator.recover_channel",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_recover:
                response = await async_client.post(
                    f"/api/v1/channels/{channel_id}/recover"
                )

                assert response.status_code == 200

                # Orchestrator SHOULD have been called (exactly 5 min is not < 5 min)
                mock_recover.assert_called_once()
