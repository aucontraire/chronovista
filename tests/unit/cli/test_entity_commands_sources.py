"""
Unit tests for the ``--sources`` flag on the ``entities scan`` CLI command.

Covers Feature 054 -- Multi-Source Entity Mention Detection, Phase 5 (US3).

All external dependencies (database session, scan service) are mocked so
that only CLI option-parsing, source validation, dispatch logic, and
output-formatting are exercised.

Covered tasks:
  T028 -- ``--sources title`` calls ``scan_metadata(sources=["title"])``
  T029 -- ``--sources transcript,title,description`` calls both ``scan()`` and
          ``scan_metadata()``
  T030 -- No ``--sources`` flag defaults to transcript-only (``scan()`` only)
  T031 -- ``--sources tag`` produces a validation error (exit code 1)
  T032 -- ``--sources title --dry-run`` output includes ``source`` column and
          uses em dash for segment_id / start_time per FR-030

Feature 054 -- Multi-Source Entity Mention Detection
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.entity_commands import entity_app
from tests.factories import id_factory

# ---------------------------------------------------------------------------
# Module-level asyncio marker -- ensures async tests run correctly with coverage
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_coro_via_fake_asyncio_run(coro: object) -> None:
    """Execute a coroutine synchronously (replaces asyncio.run in CLI tests)."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)  # type: ignore[arg-type]
    finally:
        loop.close()


def _make_scan_result(
    segments_scanned: int = 20,
    mentions_found: int = 3,
    mentions_skipped: int = 0,
    unique_entities: int = 1,
    unique_videos: int = 2,
    duration_seconds: float = 0.4,
    dry_run: bool = False,
    dry_run_matches: list[dict[str, Any]] | None = None,
    failed_batches: int = 0,
    skipped_longest_match: int = 0,
    skipped_exclusion_pattern: int = 0,
) -> MagicMock:
    """Build a mock ScanResult with sensible defaults."""
    result = MagicMock()
    result.segments_scanned = segments_scanned
    result.mentions_found = mentions_found
    result.mentions_skipped = mentions_skipped
    result.unique_entities = unique_entities
    result.unique_videos = unique_videos
    result.duration_seconds = duration_seconds
    result.dry_run = dry_run
    result.dry_run_matches = dry_run_matches
    result.failed_batches = failed_batches
    result.skipped_longest_match = skipped_longest_match
    result.skipped_exclusion_pattern = skipped_exclusion_pattern
    return result


def _make_dry_run_title_match(
    video_id: str | None = None,
    entity_name: str = "Test Entity",
    entity_type: str = "person",
    matched_text: str = "Test Entity",
    context: str = "Test Entity appears in this title",
) -> dict[str, Any]:
    """Build a dry-run match dict for a title-sourced mention (FR-030 shape)."""
    return {
        "video_id": video_id or id_factory.video_id("dry_run_title_vid"),
        "segment_id": None,
        "start_time": None,
        "entity_name": entity_name,
        "entity_type": entity_type,
        "matched_text": matched_text,
        "context": context,
        "source": "title",
    }


def _make_dry_run_transcript_match(
    video_id: str | None = None,
    segment_id: int = 101,
    start_time: float = 12.5,
    entity_name: str = "Test Entity",
    entity_type: str = "person",
    matched_text: str = "Test Entity",
    context: str = "...Test Entity was mentioned in this segment...",
) -> dict[str, Any]:
    """Build a dry-run match dict for a transcript-sourced mention."""
    return {
        "video_id": video_id or id_factory.video_id("dry_run_transcript_vid"),
        "segment_id": segment_id,
        "start_time": start_time,
        "entity_name": entity_name,
        "entity_type": entity_type,
        "matched_text": matched_text,
        "context": context,
        "source": "transcript",
    }


# ---------------------------------------------------------------------------
# T028 -- ``--sources title`` calls ``scan_metadata(sources=["title"])``
# ---------------------------------------------------------------------------


class TestSourcesTitleCallsScanMetadata:
    """T028: ``--sources title`` must dispatch only to scan_metadata(sources=['title'])."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Return a Typer CliRunner."""
        return CliRunner()

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_sources_title_calls_scan_metadata_only(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When ``--sources title`` is given, only scan_metadata() must be called."""
        mock_db_manager.get_session_factory.return_value = MagicMock()

        captured_scan_calls: list[dict[str, Any]] = []
        captured_metadata_calls: list[dict[str, Any]] = []

        mock_service = MagicMock()

        async def capture_scan(**kwargs: Any) -> Any:
            captured_scan_calls.append(kwargs)
            return _make_scan_result()

        async def capture_scan_metadata(**kwargs: Any) -> Any:
            captured_metadata_calls.append(kwargs)
            return _make_scan_result()

        mock_service.scan = capture_scan
        mock_service.scan_metadata = capture_scan_metadata
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(entity_app, ["scan", "--sources", "title"])

        assert result.exit_code == 0, f"Unexpected exit code; output: {result.stdout}"

        # scan() must NOT be called -- title-only means no transcript scan
        assert len(captured_scan_calls) == 0, (
            f"scan() should not be called for --sources title; "
            f"got {len(captured_scan_calls)} call(s)"
        )

        # scan_metadata() must be called once with sources=["title"]
        assert len(captured_metadata_calls) == 1, (
            f"Expected 1 scan_metadata() call; got {len(captured_metadata_calls)}"
        )
        assert captured_metadata_calls[0].get("sources") == ["title"], (
            f"Expected sources=['title']; got: {captured_metadata_calls[0].get('sources')}"
        )

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_sources_description_calls_scan_metadata_with_description(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """``--sources description`` dispatches to scan_metadata(sources=['description'])."""
        mock_db_manager.get_session_factory.return_value = MagicMock()

        captured_metadata_calls: list[dict[str, Any]] = []

        mock_service = MagicMock()

        async def capture_scan(**kwargs: Any) -> Any:
            return _make_scan_result()

        async def capture_scan_metadata(**kwargs: Any) -> Any:
            captured_metadata_calls.append(kwargs)
            return _make_scan_result()

        mock_service.scan = capture_scan
        mock_service.scan_metadata = capture_scan_metadata
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(entity_app, ["scan", "--sources", "description"])

        assert result.exit_code == 0
        assert len(captured_metadata_calls) == 1
        assert captured_metadata_calls[0].get("sources") == ["description"]


# ---------------------------------------------------------------------------
# T029 -- ``--sources transcript,title,description`` calls both services
# ---------------------------------------------------------------------------


class TestSourcesAllCallsBothServices:
    """T029: all three sources must dispatch to both scan() and scan_metadata()."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Return a Typer CliRunner."""
        return CliRunner()

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_all_sources_calls_scan_and_scan_metadata(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """``--sources transcript,title,description`` must call both service methods."""
        mock_db_manager.get_session_factory.return_value = MagicMock()

        captured_scan_calls: list[dict[str, Any]] = []
        captured_metadata_calls: list[dict[str, Any]] = []

        mock_service = MagicMock()

        async def capture_scan(**kwargs: Any) -> Any:
            captured_scan_calls.append(kwargs)
            return _make_scan_result()

        async def capture_scan_metadata(**kwargs: Any) -> Any:
            captured_metadata_calls.append(kwargs)
            return _make_scan_result()

        mock_service.scan = capture_scan
        mock_service.scan_metadata = capture_scan_metadata
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(
                entity_app,
                ["scan", "--sources", "transcript,title,description"],
            )

        assert result.exit_code == 0, f"Unexpected exit; output: {result.stdout}"

        # scan() called once for transcript
        assert len(captured_scan_calls) == 1, (
            f"Expected 1 scan() call; got {len(captured_scan_calls)}"
        )

        # scan_metadata() called once with both title and description
        assert len(captured_metadata_calls) == 1, (
            f"Expected 1 scan_metadata() call; got {len(captured_metadata_calls)}"
        )
        metadata_sources = captured_metadata_calls[0].get("sources", [])
        assert "title" in metadata_sources and "description" in metadata_sources, (
            f"Expected both 'title' and 'description' in metadata sources; "
            f"got: {metadata_sources}"
        )

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_transcript_title_calls_scan_and_scan_metadata(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """``--sources transcript,title`` calls scan() and scan_metadata(sources=['title'])."""
        mock_db_manager.get_session_factory.return_value = MagicMock()

        captured_metadata_calls: list[dict[str, Any]] = []
        captured_scan_calls: list[dict[str, Any]] = []

        mock_service = MagicMock()

        async def capture_scan(**kwargs: Any) -> Any:
            captured_scan_calls.append(kwargs)
            return _make_scan_result()

        async def capture_scan_metadata(**kwargs: Any) -> Any:
            captured_metadata_calls.append(kwargs)
            return _make_scan_result()

        mock_service.scan = capture_scan
        mock_service.scan_metadata = capture_scan_metadata
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(
                entity_app, ["scan", "--sources", "transcript,title"]
            )

        assert result.exit_code == 0
        assert len(captured_scan_calls) == 1
        assert len(captured_metadata_calls) == 1
        assert captured_metadata_calls[0].get("sources") == ["title"]


# ---------------------------------------------------------------------------
# T030 -- No ``--sources`` flag defaults to transcript-only
# ---------------------------------------------------------------------------


class TestDefaultSourcesTranscriptOnly:
    """T030: no ``--sources`` flag must default to transcript-only (backward compat)."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Return a Typer CliRunner."""
        return CliRunner()

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_no_sources_flag_calls_scan_only(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Without ``--sources``, only ``scan()`` is called; ``scan_metadata()`` is not."""
        mock_db_manager.get_session_factory.return_value = MagicMock()

        captured_scan_calls: list[dict[str, Any]] = []
        captured_metadata_calls: list[dict[str, Any]] = []

        mock_service = MagicMock()

        async def capture_scan(**kwargs: Any) -> Any:
            captured_scan_calls.append(kwargs)
            return _make_scan_result()

        async def capture_scan_metadata(**kwargs: Any) -> Any:
            captured_metadata_calls.append(kwargs)
            return _make_scan_result()

        mock_service.scan = capture_scan
        mock_service.scan_metadata = capture_scan_metadata
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(entity_app, ["scan"])

        assert result.exit_code == 0, f"Unexpected exit; output: {result.stdout}"
        assert len(captured_scan_calls) == 1, (
            f"Expected 1 scan() call; got {len(captured_scan_calls)}"
        )
        assert len(captured_metadata_calls) == 0, (
            f"scan_metadata() should NOT be called with default sources; "
            f"got {len(captured_metadata_calls)} call(s)"
        )

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_explicit_transcript_source_calls_scan_only(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """``--sources transcript`` behaves identically to the no-flag default."""
        mock_db_manager.get_session_factory.return_value = MagicMock()

        captured_scan_calls: list[dict[str, Any]] = []
        captured_metadata_calls: list[dict[str, Any]] = []

        mock_service = MagicMock()

        async def capture_scan(**kwargs: Any) -> Any:
            captured_scan_calls.append(kwargs)
            return _make_scan_result()

        async def capture_scan_metadata(**kwargs: Any) -> Any:
            captured_metadata_calls.append(kwargs)
            return _make_scan_result()

        mock_service.scan = capture_scan
        mock_service.scan_metadata = capture_scan_metadata
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(entity_app, ["scan", "--sources", "transcript"])

        assert result.exit_code == 0
        assert len(captured_scan_calls) == 1
        assert len(captured_metadata_calls) == 0


# ---------------------------------------------------------------------------
# T031 -- ``--sources tag`` produces a validation error
# ---------------------------------------------------------------------------


class TestSourcesInvalidValueRejected:
    """T031: invalid source values like 'tag' must produce a validation error."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Return a Typer CliRunner."""
        return CliRunner()

    def test_sources_tag_exits_with_code_1(self, runner: CliRunner) -> None:
        """``--sources tag`` must exit with code 1 (FR-025)."""
        result = runner.invoke(entity_app, ["scan", "--sources", "tag"])
        assert result.exit_code == 1

    def test_sources_tag_shows_error_panel(self, runner: CliRunner) -> None:
        """``--sources tag`` must display an error mentioning invalid sources."""
        result = runner.invoke(entity_app, ["scan", "--sources", "tag"])
        output = result.stdout or ""
        assert (
            "Invalid --sources" in output
            or "Invalid source" in output.lower()
            or "invalid" in output.lower()
        ), f"Expected invalid-sources error in output; got: {output[:400]}"

    def test_sources_tag_does_not_call_asyncio_run(self, runner: CliRunner) -> None:
        """Validation failure must exit before ``asyncio.run`` is called."""
        with patch(
            "chronovista.cli.entity_commands.asyncio.run"
        ) as mock_asyncio_run:
            runner.invoke(entity_app, ["scan", "--sources", "tag"])

        mock_asyncio_run.assert_not_called()

    def test_sources_unknown_value_exits_1(self, runner: CliRunner) -> None:
        """An unknown source value (e.g. ``foo``) must also exit with code 1."""
        result = runner.invoke(entity_app, ["scan", "--sources", "foo"])
        assert result.exit_code == 1

    def test_sources_tag_shows_valid_options(self, runner: CliRunner) -> None:
        """Error message for invalid sources must mention the valid options."""
        result = runner.invoke(entity_app, ["scan", "--sources", "tag"])
        output = result.stdout or ""
        # Valid values should appear in the error panel
        valid_shown = (
            "transcript" in output or "title" in output or "description" in output
        )
        assert valid_shown, (
            f"Expected valid source values in error output; got: {output[:400]}"
        )

    def test_sources_tag_among_valid_sources_exits_1(self, runner: CliRunner) -> None:
        """``--sources transcript,tag`` must still reject 'tag' and exit with code 1."""
        result = runner.invoke(entity_app, ["scan", "--sources", "transcript,tag"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# T032 -- ``--sources title --dry-run`` output: source column + em dash
# ---------------------------------------------------------------------------


class TestDryRunTitleOutputFormat:
    """T032: dry-run with metadata sources shows source column and em dashes (FR-030)."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Return a Typer CliRunner."""
        return CliRunner()

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_dry_run_title_shows_source_column(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """The dry-run preview table must include a ``source`` column for metadata sources."""
        mock_db_manager.get_session_factory.return_value = MagicMock()

        vid = id_factory.video_id("source_col_test")
        title_match = _make_dry_run_title_match(video_id=vid)

        mock_service = MagicMock()

        async def capture_scan(**kwargs: Any) -> Any:
            return _make_scan_result(dry_run_matches=[])

        async def capture_scan_metadata(**kwargs: Any) -> Any:
            return _make_scan_result(
                dry_run=True,
                dry_run_matches=[title_match],
                mentions_found=1,
                unique_videos=1,
                unique_entities=1,
            )

        mock_service.scan = capture_scan
        mock_service.scan_metadata = capture_scan_metadata
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(
                entity_app, ["scan", "--sources", "title", "--dry-run"]
            )

        output = result.stdout or ""
        assert result.exit_code == 0, f"Unexpected exit; output: {output[:600]}"
        # The source VALUE "title" must appear in the output.  Rich truncates
        # column *headers* on narrow terminals (CliRunner width = 80), so we
        # check for the data value rather than the header text.
        assert "title" in output.lower(), (
            f"Expected 'title' source value in dry-run output; got: {output[:600]}"
        )

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_dry_run_title_segment_id_is_em_dash(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Title mentions must show em dash (--) for segment_id per FR-030."""
        mock_db_manager.get_session_factory.return_value = MagicMock()

        vid = id_factory.video_id("em_dash_seg_test")
        title_match = _make_dry_run_title_match(video_id=vid)

        mock_service = MagicMock()

        async def capture_scan_metadata(**kwargs: Any) -> Any:
            return _make_scan_result(
                dry_run=True,
                dry_run_matches=[title_match],
                mentions_found=1,
                unique_videos=1,
                unique_entities=1,
            )

        async def capture_scan(**kwargs: Any) -> Any:
            return _make_scan_result(dry_run_matches=[])

        mock_service.scan = capture_scan
        mock_service.scan_metadata = capture_scan_metadata
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            # Use a wide terminal so Rich does not truncate cell values.
            # CliRunner defaults to 80 chars, which collapses narrow columns
            # (segment_id / start_time) to 2 chars -- too narrow for the em dash.
            result = runner.invoke(
                entity_app,
                ["scan", "--sources", "title", "--dry-run"],
                env={"COLUMNS": "200"},
            )

        output = result.stdout or ""
        assert result.exit_code == 0
        # Em dash character must appear in output for segment_id / start_time
        assert "\u2014" in output, (
            f"Expected em dash (\u2014) for segment_id/start_time in title dry-run; "
            f"output snippet: {output[:600]}"
        )

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_dry_run_title_shows_title_in_source_column(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """The source column value must show 'title' for title-sourced mentions."""
        mock_db_manager.get_session_factory.return_value = MagicMock()

        vid = id_factory.video_id("source_value_test")
        title_match = _make_dry_run_title_match(video_id=vid)

        mock_service = MagicMock()

        async def capture_scan_metadata(**kwargs: Any) -> Any:
            return _make_scan_result(
                dry_run=True,
                dry_run_matches=[title_match],
                mentions_found=1,
                unique_videos=1,
                unique_entities=1,
            )

        async def capture_scan(**kwargs: Any) -> Any:
            return _make_scan_result(dry_run_matches=[])

        mock_service.scan = capture_scan
        mock_service.scan_metadata = capture_scan_metadata
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(
                entity_app, ["scan", "--sources", "title", "--dry-run"]
            )

        output = result.stdout or ""
        assert result.exit_code == 0
        assert "title" in output.lower(), (
            f"Expected 'title' value in source column; got: {output[:600]}"
        )

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_dry_run_metadata_summary_says_videos_scanned(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Dry-run summary must say 'videos scanned' when metadata sources included (FR-030)."""
        mock_db_manager.get_session_factory.return_value = MagicMock()

        vid = id_factory.video_id("videos_scanned_test")
        title_match = _make_dry_run_title_match(video_id=vid)

        mock_service = MagicMock()

        async def capture_scan_metadata(**kwargs: Any) -> Any:
            return _make_scan_result(
                dry_run=True,
                dry_run_matches=[title_match],
                mentions_found=1,
                unique_videos=1,
                unique_entities=1,
                segments_scanned=5,
            )

        async def capture_scan(**kwargs: Any) -> Any:
            return _make_scan_result(dry_run_matches=[])

        mock_service.scan = capture_scan
        mock_service.scan_metadata = capture_scan_metadata
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(
                entity_app, ["scan", "--sources", "title", "--dry-run"]
            )

        output = result.stdout or ""
        assert result.exit_code == 0
        assert "videos scanned" in output.lower(), (
            f"Expected 'videos scanned' in dry-run summary; got: {output[:600]}"
        )

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_dry_run_transcript_only_no_source_column_in_summary(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Transcript-only dry-run summary must say 'segments scanned' (backward compat)."""
        mock_db_manager.get_session_factory.return_value = MagicMock()

        vid = id_factory.video_id("no_source_col_test")
        transcript_match = _make_dry_run_transcript_match(video_id=vid)

        mock_service = MagicMock()

        async def capture_scan(**kwargs: Any) -> Any:
            return _make_scan_result(
                dry_run=True,
                dry_run_matches=[transcript_match],
                mentions_found=1,
                unique_videos=1,
                unique_entities=1,
                segments_scanned=10,
            )

        mock_service.scan = capture_scan
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            # Use a wide terminal so Rich renders cell values without truncation.
            # The start_time column (width=10) collapses at 80-char CliRunner width.
            result = runner.invoke(
                entity_app, ["scan", "--dry-run"], env={"COLUMNS": "200"}
            )

        output = result.stdout or ""
        assert result.exit_code == 0
        # Summary must say "segments scanned", not "videos scanned"
        assert "segments scanned" in output.lower(), (
            f"Expected 'segments scanned' for transcript-only dry-run; got: {output[:600]}"
        )
        # Real start_time must be shown for transcript rows (visible at COLUMNS=200)
        assert "12.5" in output, (
            f"Expected real start_time '12.5' for transcript row; got: {output[:600]}"
        )
