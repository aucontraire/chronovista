"""Integration tests for POST /api/v1/videos/{video_id}/recover endpoint.

This module tests the video recovery endpoint that uses the Wayback Machine
to recover metadata for unavailable YouTube videos.

Tests cover:
- Success case with recovered metadata
- 404 error when video doesn't exist
- 409 conflict when video is available
- 422 validation errors for invalid year ranges
- 503 error when CDX API is unavailable
- Zero-new-fields success case
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import Video as VideoDB
from chronovista.exceptions import CDXError
from chronovista.models.enums import AvailabilityStatus
from chronovista.services.recovery.models import RecoveryResult

pytestmark = pytest.mark.asyncio


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
async def test_channel(
    integration_session_factory,
) -> Dict[str, Any]:
    """
    Create a test channel for FK constraints.

    Returns channel data dict for use in tests.
    """
    async with integration_session_factory() as session:
        channel = ChannelDB(
            channel_id="UCrecovery12345678901234",
            title="Recovery Test Channel",
            description="Channel for recovery endpoint tests",
            subscriber_count=1000,
            video_count=50,
            availability_status=AvailabilityStatus.AVAILABLE.value,
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
        else:
            channel = existing_channel

        return {
            "channel_id": channel.channel_id,
            "title": channel.title,
        }


@pytest.fixture
async def deleted_video(
    integration_session_factory,
    test_channel: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a video with availability_status = 'deleted'.

    Returns video data dict for use in tests.
    """
    async with integration_session_factory() as session:
        video = VideoDB(
            video_id="delvid12345",  # 11 chars
            channel_id=test_channel["channel_id"],
            title="Deleted Video for Recovery",
            description="A deleted video that needs recovery",
            upload_date=datetime(2023, 1, 15, tzinfo=timezone.utc),
            duration=420,
            made_for_kids=False,
            availability_status=AvailabilityStatus.DELETED.value,
        )

        # Check if video already exists
        result = await session.execute(
            select(VideoDB).where(VideoDB.video_id == video.video_id)
        )
        existing_video = result.scalar_one_or_none()

        if existing_video:
            # Update to ensure deleted status
            existing_video.availability_status = AvailabilityStatus.DELETED.value
            existing_video.recovered_at = None
            existing_video.recovery_source = None
            await session.commit()
            return {
                "video_id": existing_video.video_id,
                "title": existing_video.title,
                "availability_status": existing_video.availability_status,
            }

        session.add(video)
        await session.commit()
        await session.refresh(video)

        return {
            "video_id": video.video_id,
            "title": video.title,
            "availability_status": video.availability_status,
        }


@pytest.fixture
async def available_video(
    integration_session_factory,
    test_channel: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a video with availability_status = 'available'.

    Returns video data dict for use in tests.
    """
    async with integration_session_factory() as session:
        video = VideoDB(
            video_id="avlvid12345",  # 11 chars
            channel_id=test_channel["channel_id"],
            title="Available Video",
            description="An available video that should not be recovered",
            upload_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            duration=300,
            made_for_kids=False,
            availability_status=AvailabilityStatus.AVAILABLE.value,
        )

        # Check if video already exists
        result = await session.execute(
            select(VideoDB).where(VideoDB.video_id == video.video_id)
        )
        existing_video = result.scalar_one_or_none()

        if existing_video:
            # Update to ensure available status
            existing_video.availability_status = AvailabilityStatus.AVAILABLE.value
            await session.commit()
            return {
                "video_id": existing_video.video_id,
                "title": existing_video.title,
                "availability_status": existing_video.availability_status,
            }

        session.add(video)
        await session.commit()
        await session.refresh(video)

        return {
            "video_id": video.video_id,
            "title": video.title,
            "availability_status": video.availability_status,
        }


# =============================================================================
# Success Tests
# =============================================================================


class TestVideoRecoverySuccess:
    """Tests for successful video recovery."""

    async def test_recover_video_success_with_metadata(
        self,
        async_client: AsyncClient,
        deleted_video: Dict[str, Any],
    ) -> None:
        """Test successful video recovery with populated RecoveryResult."""
        video_id = deleted_video["video_id"]

        # Mock the recover_video orchestrator to return success
        mock_result = RecoveryResult(
            video_id=video_id,
            success=True,
            snapshot_used="20220106075526",
            fields_recovered=["title", "description", "view_count", "like_count"],
            fields_skipped=["channel_id"],
            snapshots_available=15,
            snapshots_tried=3,
            duration_seconds=2.45,
            channel_recovery_candidates=["UCrecovery12345678901234"],
        )

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            with patch(
                "chronovista.services.recovery.orchestrator.recover_video",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                response = await async_client.post(f"/api/v1/videos/{video_id}/recover")

                assert response.status_code == 200
                data = response.json()

                # Verify response structure
                assert "data" in data
                result_data = data["data"]

                # Verify success fields
                assert result_data["video_id"] == video_id
                assert result_data["success"] is True
                assert result_data["snapshot_used"] == "20220106075526"
                assert result_data["fields_recovered"] == [
                    "title",
                    "description",
                    "view_count",
                    "like_count",
                ]
                assert result_data["fields_skipped"] == ["channel_id"]
                assert result_data["snapshots_available"] == 15
                assert result_data["snapshots_tried"] == 3
                assert result_data["failure_reason"] is None
                assert result_data["duration_seconds"] == 2.45
                assert result_data["channel_recovery_candidates"] == [
                    "UCrecovery12345678901234"
                ]

    async def test_recover_video_zero_new_fields(
        self,
        async_client: AsyncClient,
        deleted_video: Dict[str, Any],
    ) -> None:
        """Test successful recovery with empty fields_recovered list."""
        video_id = deleted_video["video_id"]

        # Mock the recover_video orchestrator to return success with no new fields
        mock_result = RecoveryResult(
            video_id=video_id,
            success=True,
            snapshot_used="20220106075526",
            fields_recovered=[],  # No new fields recovered
            fields_skipped=["title", "description", "channel_id"],
            snapshots_available=10,
            snapshots_tried=1,
            duration_seconds=1.2,
        )

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            with patch(
                "chronovista.services.recovery.orchestrator.recover_video",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                response = await async_client.post(f"/api/v1/videos/{video_id}/recover")

                assert response.status_code == 200
                data = response.json()

                # Verify response structure
                assert "data" in data
                result_data = data["data"]

                # Verify zero-new-fields scenario
                assert result_data["success"] is True
                assert result_data["fields_recovered"] == []
                assert len(result_data["fields_skipped"]) > 0
                assert result_data["snapshot_used"] == "20220106075526"


# =============================================================================
# Error Tests
# =============================================================================


class TestVideoRecoveryErrors:
    """Tests for video recovery error cases."""

    async def test_recover_nonexistent_video_404(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test 404 error when video doesn't exist in database."""
        video_id = "nonexistent"

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.post(f"/api/v1/videos/{video_id}/recover")

            assert response.status_code == 404
            data = response.json()

            # Verify error structure (RFC 7807)
            assert "detail" in data
            assert "Video" in data["detail"]
            assert video_id in data["detail"]

    async def test_recover_available_video_409(
        self,
        async_client: AsyncClient,
        available_video: Dict[str, Any],
    ) -> None:
        """Test 409 conflict when video is available."""
        video_id = available_video["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.post(f"/api/v1/videos/{video_id}/recover")

            assert response.status_code == 409
            data = response.json()

            # Verify conflict error
            assert "detail" in data
            assert "available" in data["detail"].lower()

    async def test_recover_invalid_year_range_422(
        self,
        async_client: AsyncClient,
        deleted_video: Dict[str, Any],
    ) -> None:
        """Test 422 validation error when end_year < start_year."""
        video_id = deleted_video["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.post(
                f"/api/v1/videos/{video_id}/recover?start_year=2020&end_year=2015"
            )

            assert response.status_code == 400  # BadRequestError maps to 400
            data = response.json()

            # Verify validation error
            assert "detail" in data
            assert "year" in data["detail"].lower()
            assert "2020" in data["detail"]
            assert "2015" in data["detail"]

    async def test_recover_year_out_of_range_422(
        self,
        async_client: AsyncClient,
        deleted_video: Dict[str, Any],
    ) -> None:
        """Test 422 validation error when year is out of range."""
        video_id = deleted_video["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Year too early (before 2005)
            response = await async_client.post(
                f"/api/v1/videos/{video_id}/recover?start_year=1990"
            )

            # FastAPI's Query validation will return 422
            assert response.status_code == 422
            data = response.json()

            # Verify validation error structure
            assert "detail" in data

    async def test_recover_cdx_error_503(
        self,
        async_client: AsyncClient,
        deleted_video: Dict[str, Any],
    ) -> None:
        """Test 503 error when CDX API is unavailable."""
        video_id = deleted_video["video_id"]

        # Mock the recover_video orchestrator to raise CDXError
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            with patch(
                "chronovista.services.recovery.orchestrator.recover_video",
                new_callable=AsyncMock,
                side_effect=CDXError(
                    message="CDX API connection timeout",
                    video_id=video_id,
                    status_code=503,
                ),
            ):
                response = await async_client.post(f"/api/v1/videos/{video_id}/recover")

                assert response.status_code == 503
                data = response.json()

                # Verify 503 error structure
                assert "detail" in data
                assert "Wayback Machine" in data["detail"]
                assert "CDX API" in data["detail"]

                # Verify Retry-After header
                assert "Retry-After" in response.headers
                assert response.headers["Retry-After"] == "60"


# =============================================================================
# Query Parameter Tests
# =============================================================================


class TestVideoRecoveryQueryParameters:
    """Tests for year filtering query parameters."""

    async def test_recover_with_start_year(
        self,
        async_client: AsyncClient,
        deleted_video: Dict[str, Any],
    ) -> None:
        """Test recovery with start_year parameter."""
        video_id = deleted_video["video_id"]

        mock_result = RecoveryResult(
            video_id=video_id,
            success=True,
            snapshot_used="20180101120000",
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
                    f"/api/v1/videos/{video_id}/recover?start_year=2018"
                )

                assert response.status_code == 200

                # Verify that recover_video was called with start_year
                mock_recover.assert_called_once()
                call_kwargs = mock_recover.call_args.kwargs
                assert call_kwargs["from_year"] == 2018
                assert call_kwargs["to_year"] is None

    async def test_recover_with_end_year(
        self,
        async_client: AsyncClient,
        deleted_video: Dict[str, Any],
    ) -> None:
        """Test recovery with end_year parameter."""
        video_id = deleted_video["video_id"]

        mock_result = RecoveryResult(
            video_id=video_id,
            success=True,
            snapshot_used="20200101120000",
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
                    f"/api/v1/videos/{video_id}/recover?end_year=2020"
                )

                assert response.status_code == 200

                # Verify that recover_video was called with end_year
                mock_recover.assert_called_once()
                call_kwargs = mock_recover.call_args.kwargs
                assert call_kwargs["from_year"] is None
                assert call_kwargs["to_year"] == 2020

    async def test_recover_with_year_range(
        self,
        async_client: AsyncClient,
        deleted_video: Dict[str, Any],
    ) -> None:
        """Test recovery with both start_year and end_year parameters."""
        video_id = deleted_video["video_id"]

        mock_result = RecoveryResult(
            video_id=video_id,
            success=True,
            snapshot_used="20190101120000",
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
                    f"/api/v1/videos/{video_id}/recover?start_year=2018&end_year=2020"
                )

                assert response.status_code == 200

                # Verify that recover_video was called with both parameters
                mock_recover.assert_called_once()
                call_kwargs = mock_recover.call_args.kwargs
                assert call_kwargs["from_year"] == 2018
                assert call_kwargs["to_year"] == 2020
