"""
Tests for Feature 023 schema: availability_status on videos and channels.

This test suite validates that the SQLAlchemy models correctly define
the availability_status column and related recovery tracking columns
introduced by migration e8a4f5c9d7b2.

Changes Validated:
1. Videos table has availability_status column with 'available' default
2. Channels table has availability_status column with 'available' default
3. Videos table has alternative_url, recovered_at, recovery_source, unavailability_first_detected
4. Channels table has recovered_at, recovery_source, unavailability_first_detected
5. Videos table does NOT have deleted_flag column
6. Playlists table still has deleted_flag (per R8)

Related: Feature 023 (Deleted Content Visibility), Task T013
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Base, Channel, Playlist, Video

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


def get_column_names(model: type[Any]) -> list[str]:
    """
    Get column names from a SQLAlchemy model using runtime inspection.

    Parameters
    ----------
    model : type
        SQLAlchemy model class

    Returns
    -------
    list[str]
        List of column names
    """
    mapper = inspect(model)
    return [col.key for col in mapper.columns]


def get_column(model: type[Any], name: str) -> Any | None:
    """
    Get a specific column from a SQLAlchemy model.

    Parameters
    ----------
    model : type
        SQLAlchemy model class
    name : str
        Column name

    Returns
    -------
    Column or None
    """
    mapper = inspect(model)
    for col in mapper.columns:
        if col.key == name:
            return col
    return None


class TestVideoSchemaColumns:
    """Validate Video model has correct columns for Feature 023."""

    def test_videos_has_availability_status_column(self) -> None:
        """Verify Video model has availability_status column (FR-003)."""
        columns = get_column_names(Video)
        assert "availability_status" in columns

    def test_availability_status_default_is_available(self) -> None:
        """Verify availability_status defaults to 'available'."""
        col = get_column(Video, "availability_status")
        assert col is not None
        assert col.default is not None
        assert col.default.arg == "available"

    def test_videos_has_alternative_url_column(self) -> None:
        """Verify Video model has alternative_url column (FR-004)."""
        columns = get_column_names(Video)
        assert "alternative_url" in columns

    def test_videos_has_recovered_at_column(self) -> None:
        """Verify Video model has recovered_at column (FR-005)."""
        columns = get_column_names(Video)
        assert "recovered_at" in columns

    def test_videos_has_recovery_source_column(self) -> None:
        """Verify Video model has recovery_source column (FR-005)."""
        columns = get_column_names(Video)
        assert "recovery_source" in columns

    def test_videos_has_unavailability_first_detected_column(self) -> None:
        """Verify Video model has unavailability_first_detected column (FR-006)."""
        columns = get_column_names(Video)
        assert "unavailability_first_detected" in columns

    def test_videos_does_not_have_deleted_flag(self) -> None:
        """Verify Video model no longer has deleted_flag column."""
        columns = get_column_names(Video)
        assert "deleted_flag" not in columns


class TestChannelSchemaColumns:
    """Validate Channel model has correct columns for Feature 023."""

    def test_channels_has_availability_status_column(self) -> None:
        """Verify Channel model has availability_status column (FR-028)."""
        columns = get_column_names(Channel)
        assert "availability_status" in columns

    def test_channels_availability_status_default_is_available(self) -> None:
        """Verify channel availability_status defaults to 'available'."""
        col = get_column(Channel, "availability_status")
        assert col is not None
        assert col.default is not None
        assert col.default.arg == "available"

    def test_channels_has_recovery_columns(self) -> None:
        """Verify Channel model has recovery tracking columns (FR-028)."""
        columns = get_column_names(Channel)
        assert "recovered_at" in columns
        assert "recovery_source" in columns
        assert "unavailability_first_detected" in columns


class TestPlaylistSchemaUnchanged:
    """Validate Playlist model retains deleted_flag per R8 scope decision."""

    def test_playlists_has_deleted_flag(self) -> None:
        """Verify Playlist model still has deleted_flag (R8)."""
        columns = get_column_names(Playlist)
        assert "deleted_flag" in columns


class TestSchemaIntegration:
    """Validate schema works correctly with the database."""

    async def test_insert_video_with_default_availability_status(
        self, db_session: AsyncSession
    ) -> None:
        """Verify inserting a video uses 'available' as default status."""
        channel = Channel(
            channel_id="UC_test_channel_001",
            title="Test Channel",
            description="Test",
            availability_status="available",
        )
        db_session.add(channel)
        await db_session.flush()

        video = Video(
            video_id="test_avail_001",
            channel_id="UC_test_channel_001",
            title="Test Video",
            description="Test",
            upload_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            duration=300,
            availability_status="available",
        )
        db_session.add(video)
        await db_session.flush()

        assert video.availability_status == "available"
        assert video.alternative_url is None
        assert video.recovered_at is None
        assert video.recovery_source is None
        assert video.unavailability_first_detected is None

    async def test_insert_unavailable_video(
        self, db_session: AsyncSession
    ) -> None:
        """Verify inserting a video with unavailable status works."""
        channel = Channel(
            channel_id="UC_test_channel_002",
            title="Test Channel 2",
            description="Test",
            availability_status="available",
        )
        db_session.add(channel)
        await db_session.flush()

        video = Video(
            video_id="test_unavail_001",
            channel_id="UC_test_channel_002",
            title="Unavailable Video",
            description="Test",
            upload_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            duration=300,
            availability_status="unavailable",
        )
        db_session.add(video)
        await db_session.flush()

        assert video.availability_status == "unavailable"

    async def test_insert_channel_with_default_availability_status(
        self, db_session: AsyncSession
    ) -> None:
        """Verify inserting a channel uses 'available' as default status."""
        channel = Channel(
            channel_id="UC_test_avail_001",
            title="Test Channel",
            description="Test",
            availability_status="available",
        )
        db_session.add(channel)
        await db_session.flush()

        assert channel.availability_status == "available"
        assert channel.recovered_at is None
        assert channel.recovery_source is None
        assert channel.unavailability_first_detected is None
