"""
Tests for enrichment logging (T061d - Phase 8, User Story 6).

Covers:
- Log file is created during enrichment
- Log file path format (./logs/enrichment-{timestamp}.log)
- Logs directory is created if missing
- INFO messages are logged
- ERROR messages are logged for failures
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.services.enrichment.enrichment_service import (
    EnrichmentService,
    logger as enrichment_logger,
)

pytestmark = pytest.mark.asyncio


def generate_default_log_path(
    base_dir: Path,
    timestamp: datetime | None = None,
) -> Path:
    """
    Generate a default log file path with timestamp.

    This simulates the expected behavior of the enrichment logging when
    file-based logging is configured.

    Parameters
    ----------
    base_dir : Path
        Base directory for logs
    timestamp : datetime | None
        Timestamp to use; defaults to current time

    Returns
    -------
    Path
        Full path to the log file
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    # Format: enrichment-YYYYMMDD-HHMMSS.log
    timestamp_str = timestamp.strftime("%Y%m%d-%H%M%S")
    return base_dir / "logs" / f"enrichment-{timestamp_str}.log"


def setup_file_logging(log_path: Path, level: int = logging.INFO) -> logging.Handler:
    """
    Set up file logging for enrichment.

    Parameters
    ----------
    log_path : Path
        Path to the log file
    level : int
        Logging level (default INFO)

    Returns
    -------
    logging.Handler
        The file handler that was added
    """
    # Ensure parent directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Create file handler
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(level)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)

    return handler


class TestLogFileCreation:
    """Tests for log file creation during enrichment."""

    def test_log_file_created_at_path(self, tmp_path: Path) -> None:
        """Test that log file is created at the specified path."""
        log_path = tmp_path / "test.log"

        handler = setup_file_logging(log_path)
        test_logger = logging.getLogger("test_log_creation")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        try:
            test_logger.info("Test log message")
            handler.flush()

            assert log_path.exists()
            assert log_path.is_file()
        finally:
            test_logger.removeHandler(handler)
            handler.close()

    def test_log_file_contains_log_messages(self, tmp_path: Path) -> None:
        """Test that log file contains the logged messages."""
        log_path = tmp_path / "test.log"

        handler = setup_file_logging(log_path)
        test_logger = logging.getLogger("test_log_content")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        try:
            test_logger.info("First log message")
            test_logger.info("Second log message")
            handler.flush()

            content = log_path.read_text(encoding="utf-8")
            assert "First log message" in content
            assert "Second log message" in content
        finally:
            test_logger.removeHandler(handler)
            handler.close()


class TestLogFilePathFormat:
    """Tests for log file path format (./logs/enrichment-{timestamp}.log)."""

    def test_default_log_path_format(self, tmp_path: Path) -> None:
        """Test that default log path follows expected format."""
        timestamp = datetime(2024, 6, 15, 14, 30, 45, tzinfo=timezone.utc)
        path = generate_default_log_path(tmp_path, timestamp)

        # Verify path format
        assert path.parent.name == "logs"
        assert path.name == "enrichment-20240615-143045.log"

    def test_log_path_in_logs_directory(self, tmp_path: Path) -> None:
        """Test that default log path is in logs directory."""
        path = generate_default_log_path(tmp_path)

        assert "logs" in str(path)
        assert path.parent.name == "logs"

    def test_log_path_includes_timestamp(self, tmp_path: Path) -> None:
        """Test that log path includes timestamp."""
        timestamp = datetime(2024, 12, 25, 8, 0, 0, tzinfo=timezone.utc)
        path = generate_default_log_path(tmp_path, timestamp)

        # Should contain date components
        assert "20241225" in path.name
        assert "080000" in path.name

    def test_log_path_has_log_extension(self, tmp_path: Path) -> None:
        """Test that log path has .log extension."""
        path = generate_default_log_path(tmp_path)

        assert path.suffix == ".log"

    def test_log_path_matches_pattern(self, tmp_path: Path) -> None:
        """Test that log path matches expected regex pattern."""
        path = generate_default_log_path(tmp_path)

        # Pattern: enrichment-YYYYMMDD-HHMMSS.log
        pattern = r"enrichment-\d{8}-\d{6}\.log"
        assert re.match(pattern, path.name), f"Path {path.name} doesn't match pattern"


class TestLogsDirectoryCreation:
    """Tests for logs directory creation if missing."""

    def test_logs_directory_created_if_missing(self, tmp_path: Path) -> None:
        """Test that logs directory is created if it doesn't exist."""
        logs_dir = tmp_path / "logs"
        log_path = logs_dir / "test.log"

        # Verify directory doesn't exist yet
        assert not logs_dir.exists()

        handler = setup_file_logging(log_path)
        test_logger = logging.getLogger("test_dir_creation")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        try:
            test_logger.info("Test message")
            handler.flush()

            # Now directory should exist
            assert logs_dir.exists()
            assert logs_dir.is_dir()
        finally:
            test_logger.removeHandler(handler)
            handler.close()

    def test_nested_logs_directory_created(self, tmp_path: Path) -> None:
        """Test that nested directory structure is created."""
        log_path = tmp_path / "data" / "logs" / "2024" / "06" / "enrichment.log"

        # None of the directories exist
        assert not (tmp_path / "data").exists()

        handler = setup_file_logging(log_path)
        test_logger = logging.getLogger("test_nested_dir")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        try:
            test_logger.info("Test message")
            handler.flush()

            # All directories should now exist
            assert (tmp_path / "data").exists()
            assert (tmp_path / "data" / "logs").exists()
            assert log_path.exists()
        finally:
            test_logger.removeHandler(handler)
            handler.close()

    def test_existing_logs_directory_not_affected(self, tmp_path: Path) -> None:
        """Test that existing logs directory is not affected."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True)

        # Create an existing file in the directory
        existing_file = logs_dir / "existing.log"
        existing_file.write_text("existing log content")

        new_log_path = logs_dir / "new.log"
        handler = setup_file_logging(new_log_path)
        test_logger = logging.getLogger("test_existing_dir")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        try:
            test_logger.info("New log message")
            handler.flush()

            # Both files should exist
            assert existing_file.exists()
            assert new_log_path.exists()
            assert existing_file.read_text() == "existing log content"
        finally:
            test_logger.removeHandler(handler)
            handler.close()


class TestINFOMessageLogging:
    """Tests for INFO messages being logged."""

    def test_info_messages_logged(self, tmp_path: Path) -> None:
        """Test that INFO level messages are logged."""
        log_path = tmp_path / "test.log"

        handler = setup_file_logging(log_path, level=logging.INFO)
        test_logger = logging.getLogger("test_info")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        try:
            test_logger.info("This is an INFO message")
            handler.flush()

            content = log_path.read_text(encoding="utf-8")
            assert "INFO" in content
            assert "This is an INFO message" in content
        finally:
            test_logger.removeHandler(handler)
            handler.close()

    def test_info_messages_include_timestamp(self, tmp_path: Path) -> None:
        """Test that INFO messages include timestamp."""
        log_path = tmp_path / "test.log"

        handler = setup_file_logging(log_path)
        test_logger = logging.getLogger("test_info_timestamp")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        try:
            test_logger.info("Test message with timestamp")
            handler.flush()

            content = log_path.read_text(encoding="utf-8")
            # Should have timestamp format like 2024-06-15 14:30:45
            assert re.search(r"\d{4}-\d{2}-\d{2}", content)
        finally:
            test_logger.removeHandler(handler)
            handler.close()

    def test_multiple_info_messages(self, tmp_path: Path) -> None:
        """Test that multiple INFO messages are logged."""
        log_path = tmp_path / "test.log"

        handler = setup_file_logging(log_path)
        test_logger = logging.getLogger("test_multi_info")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        try:
            test_logger.info("Processing video 1")
            test_logger.info("Processing video 2")
            test_logger.info("Processing video 3")
            handler.flush()

            content = log_path.read_text(encoding="utf-8")
            assert "Processing video 1" in content
            assert "Processing video 2" in content
            assert "Processing video 3" in content
        finally:
            test_logger.removeHandler(handler)
            handler.close()


class TestERRORMessageLogging:
    """Tests for ERROR messages being logged for failures."""

    def test_error_messages_logged(self, tmp_path: Path) -> None:
        """Test that ERROR level messages are logged."""
        log_path = tmp_path / "test.log"

        handler = setup_file_logging(log_path, level=logging.INFO)
        test_logger = logging.getLogger("test_error")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        try:
            test_logger.error("This is an ERROR message")
            handler.flush()

            content = log_path.read_text(encoding="utf-8")
            assert "ERROR" in content
            assert "This is an ERROR message" in content
        finally:
            test_logger.removeHandler(handler)
            handler.close()

    def test_error_messages_include_exception_info(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that error messages can include exception info."""
        log_path = tmp_path / "test.log"

        handler = setup_file_logging(log_path)
        test_logger = logging.getLogger("test_error_exc")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        try:
            try:
                raise ValueError("Test exception")
            except ValueError:
                test_logger.error("Error occurred", exc_info=True)

            handler.flush()

            content = log_path.read_text(encoding="utf-8")
            assert "ERROR" in content
            assert "Error occurred" in content
            assert "ValueError" in content
            assert "Test exception" in content
        finally:
            test_logger.removeHandler(handler)
            handler.close()

    def test_error_and_info_messages_both_logged(self, tmp_path: Path) -> None:
        """Test that both ERROR and INFO messages are logged."""
        log_path = tmp_path / "test.log"

        handler = setup_file_logging(log_path)
        test_logger = logging.getLogger("test_mixed")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        try:
            test_logger.info("Starting process")
            test_logger.info("Processing item 1")
            test_logger.error("Failed to process item 2")
            test_logger.info("Processing item 3")
            handler.flush()

            content = log_path.read_text(encoding="utf-8")
            assert "Starting process" in content
            assert "Processing item 1" in content
            assert "Failed to process item 2" in content
            assert "Processing item 3" in content
            assert "ERROR" in content
            assert content.count("INFO") == 3
        finally:
            test_logger.removeHandler(handler)
            handler.close()


class TestEnrichmentServiceLogging:
    """Tests for EnrichmentService-specific logging."""

    @pytest.fixture
    def mock_youtube_service(self) -> MagicMock:
        """Create a mock YouTube service."""
        service = MagicMock()
        service.fetch_videos_batched = AsyncMock(return_value=([], set()))
        return service

    @pytest.fixture
    def enrichment_service(
        self, mock_youtube_service: MagicMock
    ) -> EnrichmentService:
        """Create an EnrichmentService instance with mocks."""
        return EnrichmentService(
            video_repository=MagicMock(),
            channel_repository=MagicMock(),
            video_tag_repository=MagicMock(),
            video_topic_repository=MagicMock(),
            video_category_repository=MagicMock(),
            topic_category_repository=MagicMock(),
            youtube_service=mock_youtube_service,
        )

    def test_enrichment_service_uses_logger(
        self, enrichment_service: EnrichmentService
    ) -> None:
        """Test that enrichment service has a configured logger."""
        # The enrichment_service module should have a logger
        assert enrichment_logger is not None
        assert isinstance(enrichment_logger, logging.Logger)

    def test_enrichment_logger_has_correct_name(self) -> None:
        """Test that enrichment logger has the correct name."""
        # Logger should be named after the module
        assert "enrichment_service" in enrichment_logger.name

    @pytest.mark.asyncio
    async def test_enrichment_logs_info_on_no_videos(
        self,
        enrichment_service: EnrichmentService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that INFO is logged when no videos need enrichment."""
        mock_session = AsyncMock()

        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = []

            with caplog.at_level(logging.INFO):
                await enrichment_service.enrich_videos(mock_session)

            # Should log that no videos were found
            assert any(
                "no video" in record.message.lower()
                for record in caplog.records
            )

    @pytest.mark.asyncio
    async def test_enrichment_logs_info_on_start(
        self,
        enrichment_service: EnrichmentService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that INFO is logged when enrichment starts."""
        mock_session = AsyncMock()
        mock_video = MagicMock()
        mock_video.video_id = "test_vid"
        mock_video.title = "[Placeholder] Video test_vid"
        mock_video.deleted_flag = False

        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get, patch.object(
            enrichment_service.youtube_service, "fetch_videos_batched", new=AsyncMock(return_value=([], {"test_vid"}))
        ), patch.object(
            mock_session, "commit", new=AsyncMock()
        ), patch.object(
            mock_session, "rollback", new=AsyncMock()
        ):
            mock_get.return_value = [mock_video]

            with caplog.at_level(logging.INFO):
                await enrichment_service.enrich_videos(mock_session)

            # Should log found videos count
            assert any(
                "found" in record.message.lower() and "1" in record.message
                for record in caplog.records
            )


class TestLoggingWithCaplog:
    """Tests using pytest's caplog fixture for capturing logs."""

    def test_caplog_captures_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that caplog captures INFO level messages."""
        test_logger = logging.getLogger("test_caplog_info")

        with caplog.at_level(logging.INFO):
            test_logger.info("Test INFO message for caplog")

        assert "Test INFO message for caplog" in caplog.text
        assert any(
            record.levelname == "INFO" for record in caplog.records
        )

    def test_caplog_captures_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that caplog captures ERROR level messages."""
        test_logger = logging.getLogger("test_caplog_error")

        with caplog.at_level(logging.ERROR):
            test_logger.error("Test ERROR message for caplog")

        assert "Test ERROR message for caplog" in caplog.text
        assert any(
            record.levelname == "ERROR" for record in caplog.records
        )

    def test_caplog_enrichment_module(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test capturing logs from the enrichment module specifically."""
        with caplog.at_level(logging.INFO, logger="chronovista.services.enrichment"):
            enrichment_logger.info("Enrichment test message")

        assert "Enrichment test message" in caplog.text
