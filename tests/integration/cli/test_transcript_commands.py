"""
Integration tests for transcript segment CLI commands.

Tests the transcript segment/context/range commands with various inputs.
Requires database setup with actual transcript and segment data.

NOTE: These tests use synchronous fixtures and runner.invoke() to avoid
asyncio.run() conflicts. The CLI commands themselves handle async operations
internally via run_sync_operation().
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from chronovista.cli.main import app
from chronovista.db.models import (
    Channel as ChannelDB,
    TranscriptSegment as TranscriptSegmentDB,
    VideoTranscript as VideoTranscriptDB,
    Video as VideoDB,
)
from chronovista.models.enums import DownloadReason, TranscriptType

# Test runner with environment that matches the integration test database
TEST_DATABASE_URL = os.getenv(
    "DATABASE_INTEGRATION_URL",
    "postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test"
)
runner = CliRunner()


@pytest.fixture(autouse=True)
def patch_settings_for_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Patch settings to use integration test database.

    The settings singleton is loaded at module import time with values from .env.
    This fixture patches the effective_database_url property to return the
    integration test database URL.
    """
    from chronovista.config import settings as settings_module
    from chronovista.config import database as database_module

    # Patch the settings object to return the test database URL
    monkeypatch.setattr(
        settings_module.settings,
        "database_url",
        TEST_DATABASE_URL,
    )
    monkeypatch.setattr(
        settings_module.settings,
        "database_dev_url",
        TEST_DATABASE_URL,
    )
    monkeypatch.setattr(
        settings_module.settings,
        "development_mode",
        False,
    )

    # Reset the db_manager singleton to use new settings
    database_module.db_manager._engine = None
    database_module.db_manager._session_factory = None


@pytest.fixture
async def db_with_segments(db_session: AsyncSession) -> AsyncSession:
    """
    Create test database with video, transcript, and segments.

    Creates a video with a transcript and segments for testing
    the CLI commands.
    """
    # Create channel first (foreign key requirement)
    channel = ChannelDB(
        channel_id="test_channel",
        title="Test Channel",
        description="Test channel description",
    )
    db_session.add(channel)
    await db_session.flush()

    # Create video
    video = VideoDB(
        video_id="dQw4w9WgXcQ",
        channel_id="test_channel",
        title="Test Video",
        description="Test Description",
        upload_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
        duration=300,  # 5 minutes
        made_for_kids=False,
        self_declared_made_for_kids=False,
        deleted_flag=False,
    )
    db_session.add(video)
    await db_session.flush()

    # Create transcript
    transcript = VideoTranscriptDB(
        video_id="dQw4w9WgXcQ",
        language_code="en",
        transcript_text="Full transcript text here",
        transcript_type=TranscriptType.MANUAL,
        download_reason=DownloadReason.USER_REQUEST,
        is_cc=True,
        is_auto_synced=False,
        raw_transcript_data={
            "snippets": [
                {"text": "Hello world", "start": 0.0, "duration": 2.5},
                {"text": "This is a test", "start": 2.5, "duration": 3.0},
                {"text": "Testing segments", "start": 60.0, "duration": 2.0},
                {"text": "More content", "start": 90.0, "duration": 1.5},
            ]
        },
    )
    db_session.add(transcript)
    await db_session.flush()

    # Create segments
    segments = [
        TranscriptSegmentDB(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="Hello world",
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=0,
        ),
        TranscriptSegmentDB(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="This is a test",
            start_time=2.5,
            duration=3.0,
            end_time=5.5,
            sequence_number=1,
        ),
        TranscriptSegmentDB(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="Testing segments",
            start_time=60.0,
            duration=2.0,
            end_time=62.0,
            sequence_number=2,
        ),
        TranscriptSegmentDB(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="More content",
            start_time=90.0,
            duration=1.5,
            end_time=91.5,
            sequence_number=3,
        ),
    ]

    for segment in segments:
        db_session.add(segment)

    await db_session.commit()
    return db_session


class TestTranscriptSegmentCommand:
    """Tests for transcript segment command."""

    @pytest.mark.asyncio
    async def test_segment_with_valid_timestamp(self, db_with_segments: AsyncSession) -> None:
        """Test segment command returns segment at timestamp."""
        result = runner.invoke(app, [
            "transcript", "segment", "dQw4w9WgXcQ", "1:00"
        ])

        # Should succeed
        assert result.exit_code == 0, f"Unexpected output: {result.stdout}"
        # Human format shows segment ID with # prefix
        assert "#" in result.stdout
        # Should contain segment text
        assert "Testing segments" in result.stdout

    @pytest.mark.asyncio
    async def test_segment_with_json_format(self, db_with_segments: AsyncSession) -> None:
        """Test segment command with --format json."""
        result = runner.invoke(app, [
            "transcript", "segment", "dQw4w9WgXcQ", "1:00",
            "--format", "json"
        ])

        assert result.exit_code == 0, f"Unexpected output: {result.stdout}"
        # JSON format should be parseable
        import json
        data = json.loads(result.stdout)
        assert "segment_id" in data
        assert "text" in data
        assert data["text"] == "Testing segments"

    @pytest.mark.asyncio
    async def test_segment_missing_transcript(self, db_session: AsyncSession) -> None:
        """Test segment command with missing transcript shows error."""
        result = runner.invoke(app, [
            "transcript", "segment", "nonexistent", "00:01:30"
        ])

        assert result.exit_code == 1
        # Should mention missing transcript (error goes to stderr, use result.output)
        output = result.output.lower() if result.output else ""
        assert "transcript" in output or "not found" in output

    @pytest.mark.asyncio
    async def test_segment_invalid_timestamp_format(self, db_with_segments: AsyncSession) -> None:
        """Test segment command with invalid timestamp shows error."""
        result = runner.invoke(app, [
            "transcript", "segment", "dQw4w9WgXcQ", "invalid"
        ])

        assert result.exit_code == 2

    @pytest.mark.asyncio
    async def test_segment_language_flag(self, db_with_segments: AsyncSession) -> None:
        """Test segment command with --language flag."""
        result = runner.invoke(app, [
            "transcript", "segment", "dQw4w9WgXcQ", "1:00",
            "--language", "es"
        ])

        # Should fail since no Spanish transcript exists
        assert result.exit_code == 1


class TestTranscriptContextCommand:
    """Tests for transcript context command."""

    @pytest.mark.asyncio
    async def test_context_default_window(self, db_with_segments: AsyncSession) -> None:
        """Test context command with default 30s window."""
        result = runner.invoke(app, [
            "transcript", "context", "dQw4w9WgXcQ", "1:00"
        ])

        assert result.exit_code == 0, f"Unexpected output: {result.stdout}"
        # Should show context title
        assert "Context around" in result.stdout

    @pytest.mark.asyncio
    async def test_context_custom_window(self, db_with_segments: AsyncSession) -> None:
        """Test context command with custom --window."""
        result = runner.invoke(app, [
            "transcript", "context", "dQw4w9WgXcQ", "1:00",
            "--window", "60"
        ])

        assert result.exit_code == 0, f"Unexpected output: {result.stdout}"
        assert "60s" in result.stdout

    @pytest.mark.asyncio
    async def test_context_window_clamped(self, db_with_segments: AsyncSession) -> None:
        """Test context command clamps window to 3600s max."""
        result = runner.invoke(app, [
            "transcript", "context", "dQw4w9WgXcQ", "1:00",
            "--window", "9999"
        ])

        assert result.exit_code == 0, f"Unexpected output: {result.stdout}"
        # Should show warning about clamping
        assert "clamped" in result.stdout.lower() or "3600" in result.stdout


class TestTranscriptRangeCommand:
    """Tests for transcript range command."""

    @pytest.mark.asyncio
    async def test_range_valid(self, db_with_segments: AsyncSession) -> None:
        """Test range command with valid range."""
        result = runner.invoke(app, [
            "transcript", "range", "dQw4w9WgXcQ", "0:00", "2:00"
        ])

        assert result.exit_code == 0, f"Unexpected output: {result.stdout}"
        # Should show multiple segments
        assert "segments" in result.stdout.lower()

    @pytest.mark.asyncio
    async def test_range_srt_format(self, db_with_segments: AsyncSession) -> None:
        """Test range command with --format srt."""
        result = runner.invoke(app, [
            "transcript", "range", "dQw4w9WgXcQ", "0:00", "1:00",
            "--format", "srt"
        ])

        assert result.exit_code == 0, f"Unexpected output: {result.stdout}"
        # SRT format uses --> for timestamps
        assert "-->" in result.stdout

    @pytest.mark.asyncio
    async def test_range_invalid_end_before_start(self, db_with_segments: AsyncSession) -> None:
        """Test range command rejects end < start."""
        result = runner.invoke(app, [
            "transcript", "range", "dQw4w9WgXcQ", "2:00", "1:00"
        ])

        assert result.exit_code == 4
        # Should show error about invalid range (error goes to stderr)
        output = result.output if result.output else ""
        assert "Error" in output or "end" in output.lower()

    @pytest.mark.asyncio
    async def test_range_no_segments_in_range(self, db_with_segments: AsyncSession) -> None:
        """Test range command with no segments in range."""
        result = runner.invoke(app, [
            "transcript", "range", "dQw4w9WgXcQ", "3:00", "4:00"
        ])

        # Should succeed but show no segments found (message goes to stderr)
        assert result.exit_code == 0, f"Unexpected output: {result.output}"
        output = result.output if result.output else ""
        assert "No segments found" in output or "0 segment" in output
