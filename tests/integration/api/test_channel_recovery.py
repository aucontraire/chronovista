"""Integration tests for POST /api/v1/channels/{channel_id}/recover endpoint.

This module tests the channel recovery endpoint that uses the Wayback Machine
to recover metadata for unavailable YouTube channels.

Tests cover:
- Success case with recovered metadata
- 404 error when channel doesn't exist
- 409 conflict when channel is available
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
from chronovista.exceptions import CDXError
from chronovista.models.enums import AvailabilityStatus
from chronovista.services.recovery.models import ChannelRecoveryResult

pytestmark = pytest.mark.asyncio


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
async def unavailable_channel(
    integration_session_factory,
) -> Dict[str, Any]:
    """
    Create a channel with availability_status = 'deleted'.

    Returns channel data dict for use in tests.
    """
    async with integration_session_factory() as session:
        channel = ChannelDB(
            channel_id="UCdeleted123456789012345",
            title="Deleted Channel for Recovery",
            description="A deleted channel that needs recovery",
            subscriber_count=500,
            video_count=20,
            availability_status=AvailabilityStatus.DELETED.value,
        )

        # Check if channel already exists
        result = await session.execute(
            select(ChannelDB).where(ChannelDB.channel_id == channel.channel_id)
        )
        existing_channel = result.scalar_one_or_none()

        if existing_channel:
            # Update to ensure deleted status
            existing_channel.availability_status = AvailabilityStatus.DELETED.value
            existing_channel.recovered_at = None
            existing_channel.recovery_source = None
            await session.commit()
            return {
                "channel_id": existing_channel.channel_id,
                "title": existing_channel.title,
                "availability_status": existing_channel.availability_status,
            }

        session.add(channel)
        await session.commit()
        await session.refresh(channel)

        return {
            "channel_id": channel.channel_id,
            "title": channel.title,
            "availability_status": channel.availability_status,
        }


@pytest.fixture
async def available_channel(
    integration_session_factory,
) -> Dict[str, Any]:
    """
    Create a channel with availability_status = 'available'.

    Returns channel data dict for use in tests.
    """
    async with integration_session_factory() as session:
        channel = ChannelDB(
            channel_id="UCavailable3456789012345",
            title="Available Channel",
            description="An available channel that should not be recovered",
            subscriber_count=10000,
            video_count=200,
            availability_status=AvailabilityStatus.AVAILABLE.value,
        )

        # Check if channel already exists
        result = await session.execute(
            select(ChannelDB).where(ChannelDB.channel_id == channel.channel_id)
        )
        existing_channel = result.scalar_one_or_none()

        if existing_channel:
            # Update to ensure available status
            existing_channel.availability_status = AvailabilityStatus.AVAILABLE.value
            await session.commit()
            return {
                "channel_id": existing_channel.channel_id,
                "title": existing_channel.title,
                "availability_status": existing_channel.availability_status,
            }

        session.add(channel)
        await session.commit()
        await session.refresh(channel)

        return {
            "channel_id": channel.channel_id,
            "title": channel.title,
            "availability_status": channel.availability_status,
        }


# =============================================================================
# Success Tests
# =============================================================================


class TestChannelRecoverySuccess:
    """Tests for successful channel recovery."""

    async def test_recover_channel_success_with_metadata(
        self,
        async_client: AsyncClient,
        unavailable_channel: Dict[str, Any],
    ) -> None:
        """Test successful channel recovery with populated ChannelRecoveryResult."""
        channel_id = unavailable_channel["channel_id"]

        # Mock the recover_channel orchestrator to return success
        mock_result = ChannelRecoveryResult(
            channel_id=channel_id,
            success=True,
            snapshot_used="20220106075526",
            fields_recovered=["title", "description", "subscriber_count"],
            fields_skipped=["video_count"],
            snapshots_available=15,
            snapshots_tried=3,
            duration_seconds=2.45,
        )

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            with patch(
                "chronovista.services.recovery.orchestrator.recover_channel",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                response = await async_client.post(
                    f"/api/v1/channels/{channel_id}/recover"
                )

                assert response.status_code == 200
                data = response.json()

                # Verify response structure
                assert "data" in data
                result_data = data["data"]

                # Verify success fields
                assert result_data["channel_id"] == channel_id
                assert result_data["success"] is True
                assert result_data["snapshot_used"] == "20220106075526"
                assert result_data["fields_recovered"] == [
                    "title",
                    "description",
                    "subscriber_count",
                ]
                assert result_data["fields_skipped"] == ["video_count"]
                assert result_data["snapshots_available"] == 15
                assert result_data["snapshots_tried"] == 3
                assert result_data["failure_reason"] is None
                assert result_data["duration_seconds"] == 2.45

    async def test_recover_channel_zero_new_fields(
        self,
        async_client: AsyncClient,
        unavailable_channel: Dict[str, Any],
    ) -> None:
        """Test successful recovery with empty fields_recovered list."""
        channel_id = unavailable_channel["channel_id"]

        # Mock the recover_channel orchestrator to return success with no new fields
        mock_result = ChannelRecoveryResult(
            channel_id=channel_id,
            success=True,
            snapshot_used="20220106075526",
            fields_recovered=[],  # No new fields recovered
            fields_skipped=["title", "description", "subscriber_count"],
            snapshots_available=10,
            snapshots_tried=1,
            duration_seconds=1.2,
        )

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            with patch(
                "chronovista.services.recovery.orchestrator.recover_channel",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                response = await async_client.post(
                    f"/api/v1/channels/{channel_id}/recover"
                )

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


class TestChannelRecoveryErrors:
    """Tests for channel recovery error cases."""

    async def test_recover_nonexistent_channel_404(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test 404 error when channel doesn't exist in database."""
        channel_id = "UCnonexistent12345678901"

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.post(
                f"/api/v1/channels/{channel_id}/recover"
            )

            assert response.status_code == 404
            data = response.json()

            # Verify error structure (RFC 7807)
            assert "detail" in data
            assert "Channel" in data["detail"]
            assert channel_id in data["detail"]

    async def test_recover_available_channel_409(
        self,
        async_client: AsyncClient,
        available_channel: Dict[str, Any],
    ) -> None:
        """Test 409 conflict when channel is available."""
        channel_id = available_channel["channel_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.post(
                f"/api/v1/channels/{channel_id}/recover"
            )

            assert response.status_code == 409
            data = response.json()

            # Verify conflict error
            assert "detail" in data
            assert "available" in data["detail"].lower()

    async def test_recover_invalid_year_range_422(
        self,
        async_client: AsyncClient,
        unavailable_channel: Dict[str, Any],
    ) -> None:
        """Test 422 validation error when end_year < start_year."""
        channel_id = unavailable_channel["channel_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.post(
                f"/api/v1/channels/{channel_id}/recover?start_year=2020&end_year=2015"
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
        unavailable_channel: Dict[str, Any],
    ) -> None:
        """Test 422 validation error when year is out of range."""
        channel_id = unavailable_channel["channel_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Year too early (before 2005)
            response = await async_client.post(
                f"/api/v1/channels/{channel_id}/recover?start_year=1990"
            )

            # FastAPI's Query validation will return 422
            assert response.status_code == 422
            data = response.json()

            # Verify validation error structure
            assert "detail" in data

    async def test_recover_cdx_error_503(
        self,
        async_client: AsyncClient,
        unavailable_channel: Dict[str, Any],
    ) -> None:
        """Test 503 error when CDX API is unavailable."""
        channel_id = unavailable_channel["channel_id"]

        # Mock the recover_channel orchestrator to raise CDXError
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            with patch(
                "chronovista.services.recovery.orchestrator.recover_channel",
                new_callable=AsyncMock,
                side_effect=CDXError(
                    message="CDX API connection timeout",
                    video_id=channel_id,
                    status_code=503,
                ),
            ):
                response = await async_client.post(
                    f"/api/v1/channels/{channel_id}/recover"
                )

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


class TestChannelRecoveryQueryParameters:
    """Tests for year filtering query parameters."""

    async def test_recover_with_start_year(
        self,
        async_client: AsyncClient,
        unavailable_channel: Dict[str, Any],
    ) -> None:
        """Test recovery with start_year parameter."""
        channel_id = unavailable_channel["channel_id"]

        mock_result = ChannelRecoveryResult(
            channel_id=channel_id,
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
                "chronovista.services.recovery.orchestrator.recover_channel",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_recover:
                response = await async_client.post(
                    f"/api/v1/channels/{channel_id}/recover?start_year=2018"
                )

                assert response.status_code == 200

                # Verify that recover_channel was called with start_year
                mock_recover.assert_called_once()
                call_kwargs = mock_recover.call_args.kwargs
                assert call_kwargs["from_year"] == 2018
                assert call_kwargs["to_year"] is None

    async def test_recover_with_end_year(
        self,
        async_client: AsyncClient,
        unavailable_channel: Dict[str, Any],
    ) -> None:
        """Test recovery with end_year parameter."""
        channel_id = unavailable_channel["channel_id"]

        mock_result = ChannelRecoveryResult(
            channel_id=channel_id,
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
                "chronovista.services.recovery.orchestrator.recover_channel",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_recover:
                response = await async_client.post(
                    f"/api/v1/channels/{channel_id}/recover?end_year=2020"
                )

                assert response.status_code == 200

                # Verify that recover_channel was called with end_year
                mock_recover.assert_called_once()
                call_kwargs = mock_recover.call_args.kwargs
                assert call_kwargs["from_year"] is None
                assert call_kwargs["to_year"] == 2020

    async def test_recover_with_year_range(
        self,
        async_client: AsyncClient,
        unavailable_channel: Dict[str, Any],
    ) -> None:
        """Test recovery with both start_year and end_year parameters."""
        channel_id = unavailable_channel["channel_id"]

        mock_result = ChannelRecoveryResult(
            channel_id=channel_id,
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
                "chronovista.services.recovery.orchestrator.recover_channel",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_recover:
                response = await async_client.post(
                    f"/api/v1/channels/{channel_id}/recover?start_year=2018&end_year=2020"
                )

                assert response.status_code == 200

                # Verify that recover_channel was called with both parameters
                mock_recover.assert_called_once()
                call_kwargs = mock_recover.call_args.kwargs
                assert call_kwargs["from_year"] == 2018
                assert call_kwargs["to_year"] == 2020
