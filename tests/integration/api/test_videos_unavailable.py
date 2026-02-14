"""Integration tests for video detail endpoint with unavailable content (Feature 023).

Tests that the video detail endpoint returns unavailable records instead of 404,
per FR-007, FR-009, and FR-020. Verifies that all availability_status values
return 200 with full metadata, and only truly non-existent video IDs return 404.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel, Video, VideoTranscript
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
async def test_channel(test_data_session: AsyncSession) -> Channel:
    """Create a test channel for unavailable video tests."""
    # Check if channel exists first
    result = await test_data_session.execute(
        select(Channel).where(Channel.channel_id == "UC_unavail_test_ch_")
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    channel = Channel(
        channel_id="UC_unavail_test_ch_",
        title="Test Channel for Unavailable Videos",
        description="Channel for testing unavailable video scenarios",
    )
    test_data_session.add(channel)
    await test_data_session.commit()
    await test_data_session.refresh(channel)
    return channel


@pytest.fixture
async def cleanup_test_videos(
    test_data_session: AsyncSession,
) -> AsyncGenerator[None, None]:
    """Cleanup test videos after tests complete."""
    yield

    # Clean up test videos and transcripts
    test_video_ids = [
        "unavail_av1",  # available
        "unavail_del",  # deleted
        "unavail_prv",  # private
        "unavail_ter",  # terminated
        "unavail_unv",  # unavailable
        "unavail_cpy",  # copyright
        "unavail_tos",  # tos_violation
        "unavail_trn",  # deleted with transcript
    ]
    await test_data_session.execute(
        delete(VideoTranscript).where(VideoTranscript.video_id.in_(test_video_ids))
    )
    await test_data_session.execute(
        delete(Video).where(Video.video_id.in_(test_video_ids))
    )
    await test_data_session.commit()


async def create_test_video(
    session: AsyncSession,
    video_id: str,
    channel_id: str,
    availability_status: AvailabilityStatus,
    alternative_url: str | None = None,
) -> Video:
    """Create a test video with specified availability status.

    Parameters
    ----------
    session : AsyncSession
        Database session for creating the video.
    video_id : str
        11-character YouTube video ID.
    channel_id : str
        24-character channel ID.
    availability_status : AvailabilityStatus
        The availability status to set.
    alternative_url : str | None
        Optional alternative URL for deleted/unavailable content.

    Returns
    -------
    Video
        The created video database model.
    """
    # Check if video already exists
    result = await session.execute(select(Video).where(Video.video_id == video_id))
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    video = Video(
        video_id=video_id,
        channel_id=channel_id,
        title=f"Test Video - {availability_status.value}",
        description=f"Test video for availability status: {availability_status.value}",
        upload_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
        duration=300,
        availability_status=availability_status.value,
        alternative_url=alternative_url,
    )
    session.add(video)
    await session.flush()
    await session.refresh(video)
    return video


class TestVideoDetailAvailableStatus:
    """Tests for video detail endpoint with available status."""

    async def test_available_video_returns_200(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test that video with availability_status='available' returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create available video
            video = await create_test_video(
                test_data_session,
                "unavail_av1",
                test_channel.channel_id,
                AvailabilityStatus.AVAILABLE,
            )
            await test_data_session.commit()

            response = await async_client.get(f"/api/v1/videos/{video.video_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["video_id"] == video.video_id
            assert data["data"]["availability_status"] == "available"


class TestVideoDetailUnavailableStatuses:
    """Tests for video detail endpoint with various unavailable statuses."""

    async def test_deleted_video_returns_200(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test that video with availability_status='deleted' returns 200 (NOT 404)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create deleted video
            video = await create_test_video(
                test_data_session,
                "unavail_del",
                test_channel.channel_id,
                AvailabilityStatus.DELETED,
                alternative_url="https://web.archive.org/web/example",
            )
            await test_data_session.commit()

            response = await async_client.get(f"/api/v1/videos/{video.video_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["video_id"] == video.video_id
            assert data["data"]["availability_status"] == "deleted"

    async def test_private_video_returns_200(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test that video with availability_status='private' returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create private video
            video = await create_test_video(
                test_data_session,
                "unavail_prv",
                test_channel.channel_id,
                AvailabilityStatus.PRIVATE,
            )
            await test_data_session.commit()

            response = await async_client.get(f"/api/v1/videos/{video.video_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["video_id"] == video.video_id
            assert data["data"]["availability_status"] == "private"

    async def test_terminated_video_returns_200(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test that video with availability_status='terminated' returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create terminated video
            video = await create_test_video(
                test_data_session,
                "unavail_ter",
                test_channel.channel_id,
                AvailabilityStatus.TERMINATED,
            )
            await test_data_session.commit()

            response = await async_client.get(f"/api/v1/videos/{video.video_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["video_id"] == video.video_id
            assert data["data"]["availability_status"] == "terminated"

    async def test_unavailable_video_returns_200(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test that video with availability_status='unavailable' returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create unavailable video
            video = await create_test_video(
                test_data_session,
                "unavail_unv",
                test_channel.channel_id,
                AvailabilityStatus.UNAVAILABLE,
            )
            await test_data_session.commit()

            response = await async_client.get(f"/api/v1/videos/{video.video_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["video_id"] == video.video_id
            assert data["data"]["availability_status"] == "unavailable"

    async def test_copyright_video_returns_200(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test that video with availability_status='copyright' returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create copyright video
            video = await create_test_video(
                test_data_session,
                "unavail_cpy",
                test_channel.channel_id,
                AvailabilityStatus.COPYRIGHT,
            )
            await test_data_session.commit()

            response = await async_client.get(f"/api/v1/videos/{video.video_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["video_id"] == video.video_id
            assert data["data"]["availability_status"] == "copyright"

    async def test_tos_violation_video_returns_200(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test that video with availability_status='tos_violation' returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create tos_violation video
            video = await create_test_video(
                test_data_session,
                "unavail_tos",
                test_channel.channel_id,
                AvailabilityStatus.TOS_VIOLATION,
            )
            await test_data_session.commit()

            response = await async_client.get(f"/api/v1/videos/{video.video_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["video_id"] == video.video_id
            assert data["data"]["availability_status"] == "tos_violation"


class TestVideoDetailNonExistent:
    """Tests for video detail endpoint with non-existent videos."""

    async def test_nonexistent_video_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        """Test that non-existent video_id returns 404."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Use a valid 11-character video ID that doesn't exist in the database
            response = await async_client.get("/api/v1/videos/nonexist123")
            assert response.status_code == 404
            data = response.json()
            assert data["code"] == "NOT_FOUND"
            assert "Video" in data["detail"]
            assert "nonexist123" in data["detail"]


class TestVideoDetailResponseSchema:
    """Tests for video detail response schema with unavailable content."""

    async def test_unavailable_video_includes_availability_status(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test that response includes availability_status field for unavailable video."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create deleted video
            video = await create_test_video(
                test_data_session,
                "unavail_del",
                test_channel.channel_id,
                AvailabilityStatus.DELETED,
            )
            await test_data_session.commit()

            response = await async_client.get(f"/api/v1/videos/{video.video_id}")
            assert response.status_code == 200
            data = response.json()
            assert "availability_status" in data["data"]
            assert data["data"]["availability_status"] == "deleted"

    async def test_unavailable_video_includes_alternative_url(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test that response includes alternative_url field (null if not set)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create deleted video with alternative URL
            alt_url = "https://web.archive.org/web/20240101/video"
            video = await create_test_video(
                test_data_session,
                "unavail_del",
                test_channel.channel_id,
                AvailabilityStatus.DELETED,
                alternative_url=alt_url,
            )
            await test_data_session.commit()

            response = await async_client.get(f"/api/v1/videos/{video.video_id}")
            assert response.status_code == 200
            data = response.json()
            assert "alternative_url" in data["data"]
            assert data["data"]["alternative_url"] == alt_url

    async def test_unavailable_video_includes_all_metadata_fields(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test that response includes all standard metadata fields for unavailable video."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create unavailable video
            video = await create_test_video(
                test_data_session,
                "unavail_unv",
                test_channel.channel_id,
                AvailabilityStatus.UNAVAILABLE,
            )
            await test_data_session.commit()

            response = await async_client.get(f"/api/v1/videos/{video.video_id}")
            assert response.status_code == 200
            data = response.json()
            video_data = data["data"]

            # Verify all standard fields are present
            required_fields = [
                "video_id",
                "title",
                "description",
                "channel_id",
                "channel_title",
                "upload_date",
                "duration",
                "view_count",
                "like_count",
                "comment_count",
                "tags",
                "category_id",
                "category_name",
                "default_language",
                "made_for_kids",
                "transcript_summary",
                "topics",
                "availability_status",
                "alternative_url",
            ]
            for field in required_fields:
                assert field in video_data, f"Missing field: {field}"


class TestVideoDetailTranscriptAccessibility:
    """Tests for transcript accessibility with unavailable videos (FR-020)."""

    async def test_unavailable_video_with_transcripts_returns_transcript_data(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test that unavailable video with transcripts returns transcript summary."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create deleted video
            video = await create_test_video(
                test_data_session,
                "unavail_trn",
                test_channel.channel_id,
                AvailabilityStatus.DELETED,
            )

            # Add transcript to deleted video
            transcript = VideoTranscript(
                video_id=video.video_id,
                language_code="en",
                transcript_type="MANUAL",
                transcript_text="This is a test transcript for a deleted video.",
                download_reason="USER_REQUEST",
                is_cc=True,
                is_auto_synced=False,
            )
            test_data_session.add(transcript)
            await test_data_session.commit()

            response = await async_client.get(f"/api/v1/videos/{video.video_id}")
            assert response.status_code == 200
            data = response.json()

            # Verify transcript summary is included
            assert "transcript_summary" in data["data"]
            transcript_summary = data["data"]["transcript_summary"]
            assert transcript_summary["count"] == 1
            assert "en" in transcript_summary["languages"]
            assert transcript_summary["has_manual"] is True


class TestVideoAlternativeUrlUpdate:
    """Tests for PATCH /videos/{video_id}/alternative-url endpoint (T026)."""

    async def test_set_alternative_url_on_deleted_video(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test setting an alternative URL on a deleted video."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create deleted video without alternative URL
            video = await create_test_video(
                test_data_session,
                "unavail_del",
                test_channel.channel_id,
                AvailabilityStatus.DELETED,
            )
            await test_data_session.commit()

            # Set alternative URL
            alt_url = "https://odysee.com/@channel/deleted-video"
            response = await async_client.patch(
                f"/api/v1/videos/{video.video_id}/alternative-url",
                json={"alternative_url": alt_url},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["video_id"] == video.video_id
            assert data["data"]["alternative_url"] == alt_url

    async def test_clear_alternative_url_with_null(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test clearing an alternative URL by setting it to null."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create deleted video with alternative URL
            alt_url = "https://odysee.com/@channel/deleted-video"
            video = await create_test_video(
                test_data_session,
                "unavail_del",
                test_channel.channel_id,
                AvailabilityStatus.DELETED,
                alternative_url=alt_url,
            )
            await test_data_session.commit()

            # Clear alternative URL
            response = await async_client.patch(
                f"/api/v1/videos/{video.video_id}/alternative-url",
                json={"alternative_url": None},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["video_id"] == video.video_id
            assert data["data"]["alternative_url"] is None

    async def test_reject_alternative_url_on_available_video(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test that setting alternative URL on available video returns 409 (FR-027)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create available video
            video = await create_test_video(
                test_data_session,
                "unavail_av1",
                test_channel.channel_id,
                AvailabilityStatus.AVAILABLE,
            )
            await test_data_session.commit()

            # Attempt to set alternative URL on available video
            alt_url = "https://odysee.com/@channel/video"
            response = await async_client.patch(
                f"/api/v1/videos/{video.video_id}/alternative-url",
                json={"alternative_url": alt_url},
            )

            assert response.status_code == 409
            data = response.json()
            assert data["code"] == "CONFLICT"
            assert "unavailable" in data["detail"].lower()

    async def test_reject_url_exceeding_max_length(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test that URL exceeding 500 characters returns 422 (FR-029)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create deleted video
            video = await create_test_video(
                test_data_session,
                "unavail_del",
                test_channel.channel_id,
                AvailabilityStatus.DELETED,
            )
            await test_data_session.commit()

            # Attempt to set URL exceeding max length
            long_url = "https://example.com/" + "a" * 500
            response = await async_client.patch(
                f"/api/v1/videos/{video.video_id}/alternative-url",
                json={"alternative_url": long_url},
            )

            assert response.status_code == 422
            data = response.json()
            assert "detail" in data

    async def test_reject_invalid_url_format(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test that invalid URL format returns 422."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create deleted video
            video = await create_test_video(
                test_data_session,
                "unavail_del",
                test_channel.channel_id,
                AvailabilityStatus.DELETED,
            )
            await test_data_session.commit()

            # Attempt to set invalid URL
            invalid_url = "not-a-valid-url"
            response = await async_client.patch(
                f"/api/v1/videos/{video.video_id}/alternative-url",
                json={"alternative_url": invalid_url},
            )

            assert response.status_code == 422
            data = response.json()
            assert data["code"] == "VALIDATION_ERROR"

    async def test_return_404_for_nonexistent_video(
        self, async_client: AsyncClient
    ) -> None:
        """Test that PATCH on non-existent video returns 404."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Use a valid 11-character video ID that doesn't exist in the database
            response = await async_client.patch(
                "/api/v1/videos/nonexist123/alternative-url",
                json={"alternative_url": "https://example.com/video"},
            )

            assert response.status_code == 404
            data = response.json()
            assert data["code"] == "NOT_FOUND"
            assert "nonexist123" in data["detail"]

    async def test_set_alternative_url_on_private_video(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test setting alternative URL on private video."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create private video
            video = await create_test_video(
                test_data_session,
                "unavail_prv",
                test_channel.channel_id,
                AvailabilityStatus.PRIVATE,
            )
            await test_data_session.commit()

            # Set alternative URL
            alt_url = "https://vimeo.com/123456789"
            response = await async_client.patch(
                f"/api/v1/videos/{video.video_id}/alternative-url",
                json={"alternative_url": alt_url},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["alternative_url"] == alt_url

    async def test_set_alternative_url_on_unavailable_video(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test setting alternative URL on unavailable video."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create unavailable video
            video = await create_test_video(
                test_data_session,
                "unavail_unv",
                test_channel.channel_id,
                AvailabilityStatus.UNAVAILABLE,
            )
            await test_data_session.commit()

            # Set alternative URL
            alt_url = "https://web.archive.org/web/20240101/video"
            response = await async_client.patch(
                f"/api/v1/videos/{video.video_id}/alternative-url",
                json={"alternative_url": alt_url},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["alternative_url"] == alt_url

    async def test_update_existing_alternative_url(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test updating an existing alternative URL."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create deleted video with initial alternative URL
            old_url = "https://example.com/old-mirror"
            video = await create_test_video(
                test_data_session,
                "unavail_del",
                test_channel.channel_id,
                AvailabilityStatus.DELETED,
                alternative_url=old_url,
            )
            await test_data_session.commit()

            # Update alternative URL
            new_url = "https://example.com/new-mirror"
            response = await async_client.patch(
                f"/api/v1/videos/{video.video_id}/alternative-url",
                json={"alternative_url": new_url},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["alternative_url"] == new_url
            assert data["data"]["alternative_url"] != old_url

    async def test_clear_alternative_url_with_empty_string(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
        test_channel: Channel,
        cleanup_test_videos: None,
    ) -> None:
        """Test clearing an alternative URL by setting it to an empty string."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Create deleted video with alternative URL
            alt_url = "https://odysee.com/@channel/deleted-video"
            video = await create_test_video(
                test_data_session,
                "unavail_del",
                test_channel.channel_id,
                AvailabilityStatus.DELETED,
                alternative_url=alt_url,
            )
            await test_data_session.commit()

            # Clear alternative URL with empty string
            response = await async_client.patch(
                f"/api/v1/videos/{video.video_id}/alternative-url",
                json={"alternative_url": ""},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["video_id"] == video.video_id
            assert data["data"]["alternative_url"] is None
