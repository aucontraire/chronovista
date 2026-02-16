"""
Unit tests for the video recovery orchestrator.

Tests the recovery_video function which coordinates CDX API queries,
page parsing, database updates, and tag persistence for deleted YouTube videos.

Test Coverage
-------------
- T033: Three-tier overwrite policy (immutable vs mutable fields, NULL protection)
- T034: Eligibility checks (availability_status validation, video existence)
- T035: Snapshot iteration (newest-first, removal notice handling, limits)
- T036: Tag recovery (bulk_create_video_tags integration)
- T037: RecoveryResult construction (success/failure reasons, field tracking)
- T038: Idempotency (multiple recoveries with same/different snapshots)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Video as VideoDB
from chronovista.models.enums import AvailabilityStatus
from chronovista.repositories.video_repository import VideoRepository
from chronovista.repositories.video_tag_repository import VideoTagRepository
from chronovista.services.recovery.cdx_client import CDXClient, RateLimiter
from chronovista.services.recovery.models import CdxSnapshot, RecoveredVideoData
from chronovista.services.recovery.orchestrator import recover_video
from chronovista.services.recovery.page_parser import PageParser

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _mock_channel_repo():
    """Mock ChannelRepository for all orchestrator tests to prevent real DB access."""
    with patch(
        "chronovista.services.recovery.orchestrator.ChannelRepository"
    ) as mock_cls:
        mock_instance = AsyncMock()
        mock_cls.return_value = mock_instance
        mock_instance.get.return_value = None  # Default: no channel found
        mock_instance.exists.return_value = True  # Default: channel exists (skip stub creation)
        yield mock_instance


class TestOverwritePolicy:
    """
    T033: Three-tier overwrite policy tests.

    Validates that immutable fields are only filled when NULL, mutable fields
    are overwritten when the incoming snapshot is newer, and NULL values
    never blank existing data.
    """

    async def test_immutable_fields_fill_if_null_only(self) -> None:
        """Immutable fields (channel_id, category_id) fill-if-NULL only."""
        # GIVEN: A video with NULL immutable fields
        video = VideoDB(
            video_id="testVid0001",
            title="Existing Title",
            description="Existing Description",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id=None,  # NULL - should be filled
            category_id=None,  # NULL - should be filled
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data with immutable field values
        recovered_data = RecoveredVideoData(
            channel_id="UC1234567890123456789012",
            category_id="10",
            upload_date=datetime(2019, 6, 15, tzinfo=timezone.utc),
            snapshot_timestamp="20220106075526",
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        # Mock video repository to return our test video
        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            # Mock CDX client to return snapshots
            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0001",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]

            # Mock page parser to return recovered data
            page_parser.extract_metadata.return_value = recovered_data

            # Mock tag repository
            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0001",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Immutable NULL fields were filled
        assert result.success is True
        assert "channel_id" in result.fields_recovered
        assert "category_id" in result.fields_recovered

    async def test_immutable_fields_skip_when_existing_value(self) -> None:
        """Immutable fields with existing value are skipped (not overwritten)."""
        # GIVEN: A video with existing immutable fields
        video = VideoDB(
            video_id="testVid0002",
            title="Existing Title",
            description="Existing Description",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC_EXISTING_CHANNEL_ID",  # Has value - should NOT be overwritten
            category_id="20",  # Has value - should NOT be overwritten
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data attempting to overwrite immutable fields
        recovered_data = RecoveredVideoData(
            channel_id="UCSkipChannelId123456789",
            category_id="10",
            snapshot_timestamp="20220106075526",
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0002",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0002",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Immutable fields were skipped
        assert result.success is True
        assert "channel_id" in result.fields_skipped
        assert "category_id" in result.fields_skipped

    async def test_mutable_fields_fill_if_null_always(self) -> None:
        """Mutable fields (title, description, view_count, etc.) fill-if-NULL always."""
        # GIVEN: A video with NULL mutable fields
        video = VideoDB(
            video_id="testVid0003",
            title="Placeholder Title",
            description=None,  # NULL - should be filled
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            view_count=None,  # NULL - should be filled
            like_count=None,  # NULL - should be filled
            channel_name_hint=None,  # NULL - should be filled
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data with mutable field values
        recovered_data = RecoveredVideoData(
            title="Recovered Title",
            description="Recovered Description",
            view_count=100000,
            like_count=5000,
            channel_name_hint="Recovered Channel",
            snapshot_timestamp="20220106075526",
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0003",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0003",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Mutable NULL fields were filled
        assert result.success is True
        assert "description" in result.fields_recovered
        assert "view_count" in result.fields_recovered
        assert "like_count" in result.fields_recovered
        assert "channel_name_hint" in result.fields_recovered

    async def test_mutable_fields_overwrite_when_newer_snapshot(self) -> None:
        """Mutable fields overwrite when incoming snapshot is newer than existing recovery_source."""
        # GIVEN: A video previously recovered from an older snapshot
        video = VideoDB(
            video_id="testVid0004",
            title="Old Recovered Title",
            description="Old Recovered Description",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            view_count=50000,
            like_count=2000,
            recovery_source="wayback:20200106075526",  # Older snapshot
            recovered_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data from a newer snapshot
        recovered_data = RecoveredVideoData(
            title="Newer Recovered Title",
            description="Newer Recovered Description",
            view_count=100000,
            like_count=5000,
            snapshot_timestamp="20220106075526",  # Newer than existing recovery_source
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0004",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0004",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Mutable fields were overwritten with newer values
        assert result.success is True
        assert "title" in result.fields_recovered
        assert "description" in result.fields_recovered
        assert "view_count" in result.fields_recovered

    async def test_null_protection_never_blank_existing_values(self) -> None:
        """NULL values in recovered data never blank existing database values."""
        # GIVEN: A video with existing values
        video = VideoDB(
            video_id="testVid0005",
            title="Existing Title",
            description="Existing Description",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            view_count=50000,
            like_count=2000,
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data with NULL/missing fields but one valid field
        recovered_data = RecoveredVideoData(
            title=None,  # NULL - should NOT blank existing value
            description=None,  # NULL - should NOT blank existing value
            view_count=None,  # NULL - should NOT blank existing value
            thumbnail_url="https://i.ytimg.com/vi/test/hqdefault.jpg",  # Non-NULL so has_data=True
            snapshot_timestamp="20220106075526",
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0005",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0005",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: NULL values did not blank existing values
        assert result.success is True
        assert "title" in result.fields_skipped
        assert "description" in result.fields_skipped
        assert "view_count" in result.fields_skipped

    async def test_recovered_at_and_recovery_source_always_set_on_success(self) -> None:
        """recovered_at and recovery_source are always set on successful recovery."""
        # GIVEN: A video with no recovery metadata
        video = VideoDB(
            video_id="testVid0006",
            title="Test Video",
            description="Test Description",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            recovered_at=None,
            recovery_source=None,
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data
        recovered_data = RecoveredVideoData(
            title="Recovered Title",
            snapshot_timestamp="20220106075526",
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0006",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0006",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: recovery_source was set
        assert result.success is True
        assert result.snapshot_used == "20220106075526"

    async def test_upload_date_is_mutable_and_overwritten_when_newer(self) -> None:
        """upload_date is mutable and overwritten when newer snapshot is available."""
        # GIVEN: A video with existing upload_date from an older recovery
        video = VideoDB(
            video_id="testVid0007",
            title="Test Video",
            description="Test Description",
            upload_date=datetime(2026, 1, 25, tzinfo=timezone.utc),  # Bad date (future)
            duration=120,
            channel_id="UC1234567890123456789012",
            recovery_source="wayback:20180301000000",  # Older snapshot
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data with correct upload_date from newer snapshot
        recovered_data = RecoveredVideoData(
            title="Recovered Title",
            upload_date=datetime(2018, 2, 22, tzinfo=timezone.utc),  # Correct date
            snapshot_timestamp="20200101000000",  # Newer snapshot
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20200101000000",
                original="https://www.youtube.com/watch?v=testVid0007",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0007",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: upload_date was recovered (newer snapshot wins)
        assert result.success is True
        assert "upload_date" in result.fields_recovered

    async def test_upload_date_skipped_when_existing_recovery_is_newer(self) -> None:
        """upload_date is skipped when existing recovery is from a newer snapshot."""
        # GIVEN: A video with existing upload_date from a newer recovery
        video = VideoDB(
            video_id="testVid0008",
            title="Test Video",
            description="Test Description",
            upload_date=datetime(2018, 2, 22, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            recovery_source="wayback:20210101000000",  # Newer snapshot
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data from an older snapshot
        recovered_data = RecoveredVideoData(
            title="Recovered Title",
            upload_date=datetime(2018, 1, 15, tzinfo=timezone.utc),
            snapshot_timestamp="20200101000000",  # Older snapshot
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20200101000000",
                original="https://www.youtube.com/watch?v=testVid0008",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0008",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: upload_date was skipped (older snapshot loses)
        assert result.success is True
        assert "upload_date" in result.fields_skipped


class TestEligibilityChecks:
    """
    T034: Eligibility check tests.

    Validates that only unavailable videos are eligible for recovery,
    and that availability_status is never modified during recovery.
    """

    async def test_available_video_rejected(self) -> None:
        """Video with availability_status == AVAILABLE is rejected (video_available failure)."""
        # GIVEN: A video that is AVAILABLE (not deleted/unavailable)
        video = VideoDB(
            video_id="testVid0007",
            title="Available Video",
            description="This video is still available",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            availability_status=AvailabilityStatus.AVAILABLE.value,  # AVAILABLE
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            # WHEN: We attempt to recover the video
            result = await recover_video(
                session=session,
                video_id="testVid0007",
                cdx_client=cdx_client,
                page_parser=page_parser,
                rate_limiter=rate_limiter,
                dry_run=False,
            )

        # THEN: Recovery failed due to video being available
        assert result.success is False
        assert result.failure_reason == "video_available"

    async def test_unavailable_video_eligible(self) -> None:
        """Video with availability_status == DELETED/PRIVATE/etc. is eligible."""
        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        # Test each unavailable status with valid 11-char video IDs
        statuses_and_ids = [
            (AvailabilityStatus.DELETED, "tstDelVid01"),
            (AvailabilityStatus.PRIVATE, "tstPrvVid02"),
            (AvailabilityStatus.TERMINATED, "tstTrmVid03"),
            (AvailabilityStatus.COPYRIGHT, "tstCprVid04"),
            (AvailabilityStatus.TOS_VIOLATION, "tstTosVid05"),
            (AvailabilityStatus.UNAVAILABLE, "tstUnaVid06"),
        ]
        for status, vid_id in statuses_and_ids:
            video = VideoDB(
                video_id=vid_id,
                title=f"Video with status {status.value}",
                description="Test video",
                upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
                duration=120,
                channel_id="UC1234567890123456789012",
                availability_status=status.value,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            with patch(
                "chronovista.services.recovery.orchestrator.VideoRepository"
            ) as mock_repo_class:
                mock_repo = AsyncMock()
                mock_repo_class.return_value = mock_repo
                mock_repo.get_by_video_id.return_value = video

                snapshot = CdxSnapshot(
                    timestamp="20220106075526",
                    original=f"https://www.youtube.com/watch?v={vid_id}",
                    mimetype="text/html",
                    statuscode=200,
                    digest="ABCD1234567890",
                    length=50000,
                )
                cdx_client.fetch_snapshots.return_value = [snapshot]

                recovered_data = RecoveredVideoData(
                    title="Recovered Title",
                    snapshot_timestamp="20220106075526",
                )
                page_parser.extract_metadata.return_value = recovered_data

                with patch(
                    "chronovista.services.recovery.orchestrator.VideoTagRepository"
                ) as mock_tag_repo_class:
                    mock_tag_repo = AsyncMock()
                    mock_tag_repo_class.return_value = mock_tag_repo

                    result = await recover_video(
                        session=session,
                        video_id=vid_id,
                        cdx_client=cdx_client,
                        page_parser=page_parser,
                        rate_limiter=rate_limiter,
                        dry_run=False,
                    )

            assert result.success is True, f"Status {status.value} should be eligible"

    async def test_video_not_in_database_rejected(self) -> None:
        """Video ID not in database returns video_not_found failure."""
        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            # Return None (video not found)
            mock_repo.get_by_video_id.return_value = None

            # WHEN: We attempt to recover a non-existent video
            result = await recover_video(
                session=session,
                video_id="noVidExists",
                cdx_client=cdx_client,
                page_parser=page_parser,
                rate_limiter=rate_limiter,
                dry_run=False,
            )

        # THEN: Recovery failed due to video not found
        assert result.success is False
        assert result.failure_reason == "video_not_found"

    async def test_availability_status_never_modified(self) -> None:
        """availability_status is NEVER modified during recovery."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="testVid0008",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0008",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]

            recovered_data = RecoveredVideoData(
                title="Recovered Title",
                snapshot_timestamp="20220106075526",
            )
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0008",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Recovery succeeded and availability_status was NOT modified
        assert result.success is True
        assert "availability_status" not in result.fields_recovered


class TestSnapshotIteration:
    """
    T035: Snapshot iteration tests.

    Validates that snapshots are processed newest-first, removal notices
    are skipped, and iteration respects limits (20 snapshots max, 600s timeout).
    """

    async def test_iterates_newest_first(self) -> None:
        """Iterates snapshots newest-first (already sorted by CDXClient)."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="testVid0009",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Multiple snapshots (newest-first order from CDXClient)
        snapshots = [
            CdxSnapshot(
                timestamp="20220106075526",  # Newest
                original="https://www.youtube.com/watch?v=testVid0009",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            ),
            CdxSnapshot(
                timestamp="20210615102030",  # Middle
                original="https://www.youtube.com/watch?v=testVid0009",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567891",
                length=50000,
            ),
            CdxSnapshot(
                timestamp="20200101120000",  # Oldest
                original="https://www.youtube.com/watch?v=testVid0009",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567892",
                length=50000,
            ),
        ]

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        call_order = []

        async def track_parse_calls(snapshot: CdxSnapshot) -> RecoveredVideoData:
            """Track which snapshot was parsed first."""
            call_order.append(snapshot.timestamp)
            # First snapshot succeeds
            if snapshot.timestamp == "20220106075526":
                return RecoveredVideoData(
                    title="Recovered from newest",
                    snapshot_timestamp=snapshot.timestamp,
                )
            # Others would be skipped
            return RecoveredVideoData(snapshot_timestamp=snapshot.timestamp)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            cdx_client.fetch_snapshots.return_value = snapshots
            page_parser.extract_metadata.side_effect = track_parse_calls

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0009",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Newest snapshot was tried first
        assert len(call_order) >= 1
        assert call_order[0] == "20220106075526"  # Newest tried first

    async def test_skips_removal_notices_tries_next(self) -> None:
        """Skips removal notices and tries next snapshot."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="testVid0010",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Snapshots with removal notices
        snapshots = [
            CdxSnapshot(
                timestamp="20220106075526",  # First - removal notice
                original="https://www.youtube.com/watch?v=testVid0010",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            ),
            CdxSnapshot(
                timestamp="20210615102030",  # Second - has data
                original="https://www.youtube.com/watch?v=testVid0010",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567891",
                length=50000,
            ),
        ]

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        async def mock_parse(snapshot: CdxSnapshot) -> RecoveredVideoData | None:
            """First snapshot returns no data (removal notice), second succeeds."""
            if snapshot.timestamp == "20220106075526":
                # Removal notice - no data recovered
                return RecoveredVideoData(snapshot_timestamp=snapshot.timestamp)
            else:
                # Second snapshot has data
                return RecoveredVideoData(
                    title="Recovered Title",
                    snapshot_timestamp=snapshot.timestamp,
                )

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            cdx_client.fetch_snapshots.return_value = snapshots
            page_parser.extract_metadata.side_effect = mock_parse

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0010",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Second snapshot was used after first was skipped
        assert result.success is True
        assert result.snapshot_used == "20210615102030"
        assert result.snapshots_tried == 2

    async def test_stops_after_first_successful_extraction(self) -> None:
        """Stops after first successful metadata extraction."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="testVid0011",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Multiple snapshots (all could succeed)
        snapshots = [
            CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0011",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            ),
            CdxSnapshot(
                timestamp="20210615102030",
                original="https://www.youtube.com/watch?v=testVid0011",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567891",
                length=50000,
            ),
            CdxSnapshot(
                timestamp="20200101120000",
                original="https://www.youtube.com/watch?v=testVid0011",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567892",
                length=50000,
            ),
        ]

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            cdx_client.fetch_snapshots.return_value = snapshots

            # Mock page parser to always return data
            page_parser.extract_metadata.return_value = RecoveredVideoData(
                title="Recovered Title",
                snapshot_timestamp="20220106075526",
            )

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0011",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Only first snapshot was tried (stopped after success)
        assert result.success is True
        assert result.snapshots_tried == 1
        assert result.snapshot_used == "20220106075526"

    async def test_stops_after_20_snapshots_max(self) -> None:
        """Stops after trying 20 snapshots (max limit)."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="testVid0012",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: 30 snapshots (more than the 20 limit)
        snapshots = [
            CdxSnapshot(
                timestamp=f"2022010607552{i:02d}"[:14],  # Unique timestamps
                original="https://www.youtube.com/watch?v=testVid0012",
                mimetype="text/html",
                statuscode=200,
                digest=f"ABCD123456789{i:02d}",
                length=50000 + i,
            )
            for i in range(30)
        ]

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            cdx_client.fetch_snapshots.return_value = snapshots

            # All snapshots return no data (removal notices)
            page_parser.extract_metadata.return_value = RecoveredVideoData(
                snapshot_timestamp="20220106075526"
            )

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0012",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Only 20 snapshots were tried (max limit)
        assert result.snapshots_tried == 20
        assert result.snapshots_available == 30

    async def test_reports_snapshots_tried_and_available_counts(self) -> None:
        """Reports accurate snapshots_tried and snapshots_available counts."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="testVid0013",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: 5 snapshots
        snapshots = [
            CdxSnapshot(
                timestamp=f"202201060755{i:02d}",
                original="https://www.youtube.com/watch?v=testVid0013",
                mimetype="text/html",
                statuscode=200,
                digest=f"ABCD123456789{i}",
                length=50000 + i,
            )
            for i in range(5)
        ]

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        call_count = 0

        async def mock_parse(snapshot: CdxSnapshot) -> RecoveredVideoData:
            """Third snapshot succeeds."""
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                return RecoveredVideoData(
                    title="Recovered Title",
                    snapshot_timestamp=snapshot.timestamp,
                )
            return RecoveredVideoData(snapshot_timestamp=snapshot.timestamp)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            cdx_client.fetch_snapshots.return_value = snapshots
            page_parser.extract_metadata.side_effect = mock_parse

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0013",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Correct counts are reported
        assert result.snapshots_available == 5
        assert result.snapshots_tried == 3


class TestTagRecovery:
    """
    T036: Tag recovery tests.

    Validates that recovered tags are passed to bulk_create_video_tags,
    empty tag lists are handled correctly, and tag errors don't fail recovery.
    """

    async def test_recovered_tags_passed_to_bulk_create(self) -> None:
        """Recovered tags are passed to bulk_create_video_tags with tag_orders=None."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="testVid0014",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data with tags
        recovered_data = RecoveredVideoData(
            title="Recovered Title",
            tags=["music", "entertainment", "viral"],
            snapshot_timestamp="20220106075526",
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0014",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0014",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: bulk_create_video_tags was called with correct parameters
        mock_tag_repo.bulk_create_video_tags.assert_called_once()
        call_args = mock_tag_repo.bulk_create_video_tags.call_args
        assert call_args[1]["video_id"] == "testVid0014"
        assert call_args[1]["tags"] == ["music", "entertainment", "viral"]
        assert call_args[1]["tag_orders"] is None

    async def test_empty_tags_list_no_tag_operation(self) -> None:
        """Empty tags list results in no tag operation."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="testVid0015",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data with no tags
        recovered_data = RecoveredVideoData(
            title="Recovered Title",
            tags=[],  # Empty tags list
            snapshot_timestamp="20220106075526",
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0015",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0015",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: bulk_create_video_tags was NOT called
        mock_tag_repo.bulk_create_video_tags.assert_not_called()

    async def test_tag_errors_do_not_fail_recovery(self) -> None:
        """Tag persistence errors do not fail the recovery operation."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="testVid0016",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data with tags
        recovered_data = RecoveredVideoData(
            title="Recovered Title",
            tags=["music", "entertainment"],
            snapshot_timestamp="20220106075526",
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0016",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # Mock tag creation to raise an exception
                mock_tag_repo.bulk_create_video_tags.side_effect = Exception(
                    "Tag database error"
                )

                # WHEN: We recover the video (tag operation fails)
                result = await recover_video(
                    session=session,
                    video_id="testVid0016",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Recovery still succeeded despite tag error
        assert result.success is True


class TestRecoveryResultConstruction:
    """
    T037: RecoveryResult construction tests.

    Validates that RecoveryResult objects correctly track success/failure,
    fields recovered/skipped, duration, and channel recovery candidates.
    """

    async def test_success_result_includes_fields_recovered_and_skipped(self) -> None:
        """Success result includes fields_recovered and fields_skipped lists."""
        # GIVEN: A video with some existing and some NULL fields
        video = VideoDB(
            video_id="testVid0017",
            title="Existing Title",  # Existing
            description=None,  # NULL - will be filled
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",  # Existing - will be skipped
            view_count=None,  # NULL - will be filled
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data
        recovered_data = RecoveredVideoData(
            title="New Title",  # Should be skipped (existing newer than recovery_source)
            description="Recovered Description",  # Should be recovered (NULL)
            channel_id="UCNewChannelId1234567890",  # Should be skipped (immutable with existing value)
            view_count=100000,  # Should be recovered (NULL)
            snapshot_timestamp="20220106075526",
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0017",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0017",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Result includes fields_recovered and fields_skipped
        assert result.success is True
        assert "description" in result.fields_recovered
        assert "view_count" in result.fields_recovered
        assert "channel_id" in result.fields_skipped

    async def test_failure_results_use_standardized_failure_reasons(self) -> None:
        """Failure results use standardized failure_reason strings."""
        # Test video_not_found
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = None  # Video not found

            result = await recover_video(
                session=session,
                video_id="noVidExists",
                cdx_client=cdx_client,
                page_parser=page_parser,
                rate_limiter=rate_limiter,
                dry_run=False,
            )

        assert result.success is False
        assert result.failure_reason == "video_not_found"

    async def test_duration_seconds_is_tracked(self) -> None:
        """duration_seconds is tracked for the recovery operation."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="testVid0018",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data
        recovered_data = RecoveredVideoData(
            title="Recovered Title",
            snapshot_timestamp="20220106075526",
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0018",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="testVid0018",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: duration_seconds is set
        assert result.duration_seconds >= 0.0

    async def test_channel_recovery_candidates_populated_when_channel_unavailable(
        self,
    ) -> None:
        """channel_recovery_candidates populated when extracted channel has availability_status != AVAILABLE."""
        # GIVEN: A video with DELETED status and orphaned channel
        video = VideoDB(
            video_id="testVid0019",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id=None,  # Orphaned - no channel
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data with a channel ID
        recovered_channel_id = "UC1234567890123456789012"
        recovered_data = RecoveredVideoData(
            title="Recovered Title",
            channel_id=recovered_channel_id,
            snapshot_timestamp="20220106075526",
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0019",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            # Mock ChannelRepository to return an unavailable channel
            with patch(
                "chronovista.services.recovery.orchestrator.ChannelRepository"
            ) as mock_channel_repo_class:
                mock_channel_repo = AsyncMock()
                mock_channel_repo_class.return_value = mock_channel_repo

                # Mock channel lookup to return a DELETED channel
                from chronovista.db.models import Channel as ChannelDB

                unavailable_channel = ChannelDB(
                    channel_id=recovered_channel_id,
                    title="Deleted Channel",
                    availability_status=AvailabilityStatus.DELETED.value,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                mock_channel_repo.get.return_value = unavailable_channel

                with patch(
                    "chronovista.services.recovery.orchestrator.VideoTagRepository"
                ) as mock_tag_repo_class:
                    mock_tag_repo = AsyncMock()
                    mock_tag_repo_class.return_value = mock_tag_repo

                    # WHEN: We recover the video
                    result = await recover_video(
                        session=session,
                        video_id="testVid0019",
                        cdx_client=cdx_client,
                        page_parser=page_parser,
                        rate_limiter=rate_limiter,
                        dry_run=False,
                    )

        # THEN: channel_recovery_candidates includes the unavailable channel
        assert result.success is True
        assert recovered_channel_id in result.channel_recovery_candidates


class TestIdempotency:
    """
    T038: Idempotency tests.

    Validates that recovering the same video multiple times with the same
    or different snapshots produces expected behavior (idempotent updates).
    """

    async def test_recovering_same_video_twice_with_same_snapshot(self) -> None:
        """Recovering same video twice with same snapshot produces same DB state (except recovered_at)."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="testVid0020",
            title="Original Title",
            description=None,
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data from a snapshot
        recovered_data = RecoveredVideoData(
            title="Recovered Title",
            description="Recovered Description",
            snapshot_timestamp="20220106075526",
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        snapshot = CdxSnapshot(
            timestamp="20220106075526",
            original="https://www.youtube.com/watch?v=testVid0020",
            mimetype="text/html",
            statuscode=200,
            digest="ABCD1234567890",
            length=50000,
        )

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video first time
                result1 = await recover_video(
                    session=session,
                    video_id="testVid0020",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

                # Update video state to reflect first recovery
                video.title = "Recovered Title"
                video.description = "Recovered Description"
                video.recovery_source = "wayback:20220106075526"
                video.recovered_at = datetime.now(timezone.utc)

                # WHEN: We recover the video second time (same snapshot)
                result2 = await recover_video(
                    session=session,
                    video_id="testVid0020",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Both recoveries succeeded
        assert result1.success is True
        assert result2.success is True

        # Second recovery with same snapshot re-applies fields (idempotent)
        assert "title" in result2.fields_recovered
        assert "description" in result2.fields_recovered

    async def test_recovering_with_older_snapshot_only_fills_null_fields(self) -> None:
        """Recovering with older snapshot only fills NULL fields, doesn't overwrite."""
        # GIVEN: A video recovered from a newer snapshot
        video = VideoDB(
            video_id="testVid0021",
            title="Newer Recovered Title",
            description="Newer Recovered Description",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            view_count=100000,  # From newer snapshot
            like_count=None,  # Still NULL
            recovery_source="wayback:20220106075526",  # Newer snapshot
            recovered_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data from an older snapshot
        recovered_data = RecoveredVideoData(
            title="Older Title",  # Older - should be skipped
            description="Older Description",  # Older - should be skipped
            view_count=50000,  # Older - should be skipped
            like_count=2000,  # NULL - should be filled
            snapshot_timestamp="20200106075526",  # Older than existing
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20200106075526",
                original="https://www.youtube.com/watch?v=testVid0021",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover with older snapshot
                result = await recover_video(
                    session=session,
                    video_id="testVid0021",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Only NULL fields were filled
        assert result.success is True
        assert "like_count" in result.fields_recovered  # NULL - filled
        assert "title" in result.fields_skipped  # Older - skipped
        assert "description" in result.fields_skipped  # Older - skipped
        assert "view_count" in result.fields_skipped  # Older - skipped

    async def test_recovering_with_newer_snapshot_overwrites_mutable_fields(
        self,
    ) -> None:
        """Recovering with newer snapshot overwrites mutable fields."""
        # GIVEN: A video recovered from an older snapshot
        video = VideoDB(
            video_id="testVid0022",
            title="Older Recovered Title",
            description="Older Recovered Description",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UC1234567890123456789012",
            view_count=50000,  # From older snapshot
            recovery_source="wayback:20200106075526",  # Older snapshot
            recovered_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data from a newer snapshot
        recovered_data = RecoveredVideoData(
            title="Newer Recovered Title",
            description="Newer Recovered Description",
            view_count=100000,  # Newer value
            snapshot_timestamp="20220106075526",  # Newer than existing
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=testVid0022",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover with newer snapshot
                result = await recover_video(
                    session=session,
                    video_id="testVid0022",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Mutable fields were overwritten with newer values
        assert result.success is True
        assert "title" in result.fields_recovered
        assert "description" in result.fields_recovered
        assert "view_count" in result.fields_recovered


class TestEdgeCases:
    """
    Edge case tests for orchestrator coverage improvement.

    Tests scenarios not covered by existing test classes:
    - CDX query timeout
    - No snapshots found
    - Dry-run mode
    - Extraction timeout on individual snapshots
    - Extraction errors on individual snapshots
    - Unexpected errors during recovery
    """

    async def test_cdx_query_timeout(self) -> None:
        """CDX query timeout returns cdx_query_timeout failure."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="edgCdxTmt01",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UCEdgeChannelId12345678",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            # Mock CDX client to raise TimeoutError
            cdx_client.fetch_snapshots.side_effect = asyncio.TimeoutError()

            # WHEN: We attempt to recover the video
            result = await recover_video(
                session=session,
                video_id="edgCdxTmt01",
                cdx_client=cdx_client,
                page_parser=page_parser,
                rate_limiter=rate_limiter,
                dry_run=False,
            )

        # THEN: Recovery failed due to CDX timeout
        assert result.success is False
        assert result.failure_reason == "cdx_query_timeout"
        assert result.duration_seconds >= 0.0

    async def test_no_snapshots_found(self) -> None:
        """No snapshots found returns no_snapshots_found failure."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="edgNoSnap02",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UCEdgeChannelId12345678",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            # Mock CDX client to return empty list (no snapshots)
            cdx_client.fetch_snapshots.return_value = []

            # WHEN: We attempt to recover the video
            result = await recover_video(
                session=session,
                video_id="edgNoSnap02",
                cdx_client=cdx_client,
                page_parser=page_parser,
                rate_limiter=rate_limiter,
                dry_run=False,
            )

        # THEN: Recovery failed due to no snapshots
        assert result.success is False
        assert result.failure_reason == "no_snapshots_found"
        assert result.snapshots_available == 0
        assert result.snapshots_tried == 0
        assert result.duration_seconds >= 0.0

    async def test_dry_run_mode_skips_page_fetching(self) -> None:
        """Dry-run mode skips page fetching and creates minimal RecoveredVideoData."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="edgDryRun03",
            title="Deleted Video",
            description=None,
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UCEdgeChannelId12345678",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=edgDryRun03",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover in dry-run mode
                result = await recover_video(
                    session=session,
                    video_id="edgDryRun03",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=True,
                )

        # THEN: Page parser was NOT called (dry-run skips parsing)
        page_parser.extract_metadata.assert_not_called()

        # THEN: Recovery reports success because dry-run found snapshots
        assert result.success is True
        assert result.snapshots_available == 1
        assert result.snapshots_tried == 1

    async def test_extraction_timeout_continues_to_next_snapshot(self) -> None:
        """Extraction timeout on a snapshot continues to next snapshot."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="edgExtTmt04",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UCEdgeChannelId12345678",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Multiple snapshots
        snapshots = [
            CdxSnapshot(
                timestamp="20220106075526",  # First - times out
                original="https://www.youtube.com/watch?v=edgExtTmt04",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            ),
            CdxSnapshot(
                timestamp="20210615102030",  # Second - succeeds
                original="https://www.youtube.com/watch?v=edgExtTmt04",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567891",
                length=50000,
            ),
        ]

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        call_count = 0

        async def mock_extract(snapshot: CdxSnapshot) -> RecoveredVideoData:
            """First call times out, second succeeds."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError()
            else:
                return RecoveredVideoData(
                    title="Recovered Title",
                    snapshot_timestamp=snapshot.timestamp,
                )

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            cdx_client.fetch_snapshots.return_value = snapshots
            page_parser.extract_metadata.side_effect = mock_extract

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="edgExtTmt04",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Recovery succeeded using second snapshot
        assert result.success is True
        assert result.snapshot_used == "20210615102030"
        assert result.snapshots_tried == 2

    async def test_extraction_error_continues_to_next_snapshot(self) -> None:
        """Generic extraction error on a snapshot continues to next snapshot."""
        # GIVEN: A video with DELETED status
        video = VideoDB(
            video_id="edgExtErr05",
            title="Deleted Video",
            description="Test video",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            channel_id="UCEdgeChannelId12345678",
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Multiple snapshots
        snapshots = [
            CdxSnapshot(
                timestamp="20220106075526",  # First - raises error
                original="https://www.youtube.com/watch?v=edgExtErr05",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            ),
            CdxSnapshot(
                timestamp="20210615102030",  # Second - succeeds
                original="https://www.youtube.com/watch?v=edgExtErr05",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567891",
                length=50000,
            ),
        ]

        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        call_count = 0

        async def mock_extract(snapshot: CdxSnapshot) -> RecoveredVideoData:
            """First call raises exception, second succeeds."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Parsing error")
            else:
                return RecoveredVideoData(
                    title="Recovered Title",
                    snapshot_timestamp=snapshot.timestamp,
                )

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            cdx_client.fetch_snapshots.return_value = snapshots
            page_parser.extract_metadata.side_effect = mock_extract

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                # WHEN: We recover the video
                result = await recover_video(
                    session=session,
                    video_id="edgExtErr05",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Recovery succeeded using second snapshot
        assert result.success is True
        assert result.snapshot_used == "20210615102030"
        assert result.snapshots_tried == 2

    async def test_unexpected_error_during_recovery(self) -> None:
        """Unexpected error during recovery returns unexpected_error failure."""
        # GIVEN: Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo

            # Mock repository to raise an unexpected exception
            mock_repo.get_by_video_id.side_effect = Exception("Database connection error")

            # WHEN: We attempt to recover the video
            result = await recover_video(
                session=session,
                video_id="edgUnxErr06",
                cdx_client=cdx_client,
                page_parser=page_parser,
                rate_limiter=rate_limiter,
                dry_run=False,
            )

        # THEN: Recovery failed due to unexpected error
        assert result.success is False
        assert result.failure_reason == "unexpected_error"
        assert result.duration_seconds >= 0.0


class TestStubChannelCreation:
    """
    Tests for stub channel creation when recovered channel_id references
    a channel not present in the database (FK constraint protection).
    """

    async def test_stub_channel_created_when_channel_not_in_db(
        self, _mock_channel_repo: AsyncMock
    ) -> None:
        """Creates a stub channel record when recovered channel_id is missing from DB."""
        # GIVEN: A deleted video with no channel_id
        video = VideoDB(
            video_id="stubTest001",
            title="Deleted Video",
            description=None,
            upload_date=None,
            duration=120,
            channel_id=None,
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # GIVEN: Recovered data with channel_id and channel_name_hint
        recovered_data = RecoveredVideoData(
            title="Recovered Title",
            channel_id="UCStub123456789012345678",
            channel_name_hint="Some Channel Name",
            snapshot_timestamp="20220106075526",
        )

        # GIVEN: Channel does NOT exist in DB
        _mock_channel_repo.exists.return_value = False

        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=stubTest001",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                result = await recover_video(
                    session=session,
                    video_id="stubTest001",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Recovery succeeded and stub channel was created
        assert result.success is True
        assert "channel_id" in result.fields_recovered

        # Verify stub channel was created with correct data
        _mock_channel_repo.create.assert_called_once()
        call_args = _mock_channel_repo.create.call_args
        stub_channel = call_args.kwargs.get("obj_in") or call_args[1].get("obj_in")
        assert stub_channel.channel_id == "UCStub123456789012345678"
        assert stub_channel.title == "Some Channel Name"

    async def test_stub_channel_uses_channel_id_as_title_fallback(
        self, _mock_channel_repo: AsyncMock
    ) -> None:
        """Stub channel uses channel_id as title when channel_name_hint is None."""
        video = VideoDB(
            video_id="stubTest002",
            title="Deleted Video",
            description=None,
            upload_date=None,
            duration=120,
            channel_id=None,
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        recovered_data = RecoveredVideoData(
            title="Recovered Title",
            channel_id="UCFallback12345678901234",
            channel_name_hint=None,  # No hint - should use channel_id
            snapshot_timestamp="20220106075526",
        )

        _mock_channel_repo.exists.return_value = False

        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=stubTest002",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                result = await recover_video(
                    session=session,
                    video_id="stubTest002",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        assert result.success is True
        call_args = _mock_channel_repo.create.call_args
        stub_channel = call_args.kwargs.get("obj_in") or call_args[1].get("obj_in")
        assert stub_channel.title == "UCFallback12345678901234"

    async def test_channel_id_skipped_when_stub_creation_fails(
        self, _mock_channel_repo: AsyncMock
    ) -> None:
        """channel_id is removed from update and moved to skipped when stub creation fails."""
        video = VideoDB(
            video_id="stubTest003",
            title="Deleted Video",
            description=None,
            upload_date=None,
            duration=120,
            channel_id=None,
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        recovered_data = RecoveredVideoData(
            title="Recovered Title",
            channel_id="UCFailStub1234567890123_",
            channel_name_hint="Failed Channel",
            snapshot_timestamp="20220106075526",
        )

        _mock_channel_repo.exists.return_value = False
        _mock_channel_repo.create.side_effect = Exception("DB error creating channel")

        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=stubTest003",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                result = await recover_video(
                    session=session,
                    video_id="stubTest003",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Recovery still succeeded but channel_id was skipped
        assert result.success is True
        assert "channel_id" not in result.fields_recovered
        assert "channel_id" in result.fields_skipped

    async def test_no_stub_created_when_channel_already_exists(
        self, _mock_channel_repo: AsyncMock
    ) -> None:
        """No stub channel is created when channel already exists in DB."""
        video = VideoDB(
            video_id="stubTest004",
            title="Deleted Video",
            description=None,
            upload_date=None,
            duration=120,
            channel_id=None,
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        recovered_data = RecoveredVideoData(
            title="Recovered Title",
            channel_id="UCExisting12345678901234",
            snapshot_timestamp="20220106075526",
        )

        # Channel DOES exist
        _mock_channel_repo.exists.return_value = True

        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=stubTest004",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]
            page_parser.extract_metadata.return_value = recovered_data

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                result = await recover_video(
                    session=session,
                    video_id="stubTest004",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=False,
                )

        # THEN: Recovery succeeded, channel_id was set, no stub created
        assert result.success is True
        assert "channel_id" in result.fields_recovered
        _mock_channel_repo.create.assert_not_called()

    async def test_no_stub_created_in_dry_run(
        self, _mock_channel_repo: AsyncMock
    ) -> None:
        """No stub channel is created during dry-run mode."""
        video = VideoDB(
            video_id="stubTest005",
            title="Deleted Video",
            description=None,
            upload_date=None,
            duration=120,
            channel_id=None,
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            snapshot = CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=stubTest005",
                mimetype="text/html",
                statuscode=200,
                digest="ABCD1234567890",
                length=50000,
            )
            cdx_client.fetch_snapshots.return_value = [snapshot]

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ) as mock_tag_repo_class:
                mock_tag_repo = AsyncMock()
                mock_tag_repo_class.return_value = mock_tag_repo

                result = await recover_video(
                    session=session,
                    video_id="stubTest005",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=True,
                )

        # THEN: Dry-run succeeded, no channel operations
        assert result.success is True
        _mock_channel_repo.exists.assert_not_called()
        _mock_channel_repo.create.assert_not_called()


# =============================================================================
# TestYearFiltering - from_year / to_year parameter passthrough
# =============================================================================


class TestYearFiltering:
    """Test that recover_video passes from_year/to_year to cdx_client.fetch_snapshots."""

    async def test_recover_video_passes_from_year_to_fetch_snapshots(self) -> None:
        """recover_video passes from_year to cdx_client.fetch_snapshots."""
        video = VideoDB(
            video_id="yearTest001",
            title="Year Filter Test",
            description="Testing year filtering",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            # Return empty snapshots so we hit "no_snapshots_found"
            cdx_client.fetch_snapshots.return_value = []

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ):
                await recover_video(
                    session=session,
                    video_id="yearTest001",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    from_year=2018,
                )

        # THEN: fetch_snapshots was called with from_year
        cdx_client.fetch_snapshots.assert_called_once_with(
            "yearTest001", from_year=2018, to_year=None
        )

    async def test_recover_video_passes_to_year_to_fetch_snapshots(self) -> None:
        """recover_video passes to_year to cdx_client.fetch_snapshots."""
        video = VideoDB(
            video_id="yearTest002",
            title="Year Filter Test",
            description="Testing year filtering",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            cdx_client.fetch_snapshots.return_value = []

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ):
                await recover_video(
                    session=session,
                    video_id="yearTest002",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    to_year=2020,
                )

        cdx_client.fetch_snapshots.assert_called_once_with(
            "yearTest002", from_year=None, to_year=2020
        )

    async def test_recover_video_passes_both_years_to_fetch_snapshots(self) -> None:
        """recover_video passes both from_year and to_year to cdx_client.fetch_snapshots."""
        video = VideoDB(
            video_id="yearTest003",
            title="Year Filter Test",
            description="Testing year filtering",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            cdx_client.fetch_snapshots.return_value = []

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ):
                await recover_video(
                    session=session,
                    video_id="yearTest003",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    from_year=2018,
                    to_year=2020,
                )

        cdx_client.fetch_snapshots.assert_called_once_with(
            "yearTest003", from_year=2018, to_year=2020
        )

    async def test_recover_video_default_no_year_filter(self) -> None:
        """recover_video without year params passes None/None to fetch_snapshots."""
        video = VideoDB(
            video_id="yearTest004",
            title="Year Filter Test",
            description="Testing year filtering",
            upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            duration=120,
            availability_status=AvailabilityStatus.DELETED.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        session = AsyncMock(spec=AsyncSession)
        cdx_client = AsyncMock(spec=CDXClient)
        page_parser = AsyncMock(spec=PageParser)
        rate_limiter = AsyncMock(spec=RateLimiter)

        with patch(
            "chronovista.services.recovery.orchestrator.VideoRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_video_id.return_value = video

            cdx_client.fetch_snapshots.return_value = []

            with patch(
                "chronovista.services.recovery.orchestrator.VideoTagRepository"
            ):
                await recover_video(
                    session=session,
                    video_id="yearTest004",
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                )

        cdx_client.fetch_snapshots.assert_called_once_with(
            "yearTest004", from_year=None, to_year=None
        )
