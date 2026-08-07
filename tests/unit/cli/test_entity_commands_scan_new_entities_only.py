"""
Unit tests for ``entities scan --new-entities-only`` scope stability.

Regression coverage for a defect where the zero-mention set was re-evaluated
*per scan phase*. ``--sources transcript,title,description`` dispatches two
service calls; the transcript call runs first and writes mentions, so by the time
the metadata call loaded its patterns those entities no longer had zero mentions
and were filtered out.

Observed: of 32 newly created entities, **23 ended up with transcript mentions
only** and none from titles or descriptions — the surface with 100% coverage
rather than 2.4%, and the one that is not mangled by ASR.

The fix resolves the set once, before any phase runs, and passes it to both calls
as explicit ``entity_ids``. These tests assert on *what the service receives*,
because both the fixed and broken versions produce a successful-looking run.

All external dependencies are mocked; only CLI option handling is exercised.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.entity_commands import entity_app


def _make_scan_result(**kwargs: Any) -> MagicMock:
    """Mock ScanResult with the fields the CLI summary reads."""
    result = MagicMock()
    result.segments_scanned = kwargs.get("segments_scanned", 0)
    result.videos_scanned = kwargs.get("videos_scanned", 0)
    result.mentions_found = kwargs.get("mentions_found", 0)
    result.mentions_skipped = 0
    result.skipped_exclusion_pattern = 0
    result.skipped_longest_match = 0
    result.unique_entities = 0
    result.unique_videos = 0
    result.duration_seconds = 0.1
    result.dry_run = kwargs.get("dry_run", False)
    result.dry_run_matches = kwargs.get("dry_run_matches", [])
    result.failed_batches = 0
    return result


def _session_generator() -> AsyncGenerator[Any, None]:
    async def _gen() -> AsyncGenerator[Any, None]:
        yield AsyncMock()

    return _gen()


def _run_coro(coro: object) -> None:
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)  # type: ignore[arg-type]
    finally:
        loop.close()


class TestNewEntitiesOnlyScopeIsStable:
    """The zero-mention set must be pinned before any scan phase runs."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def _invoke(
        self, runner: CliRunner, zero_mention_ids: list[uuid.UUID], sources: str
    ) -> tuple[Any, Any]:
        """Run the command; return the kwargs each service call received."""
        service = MagicMock()
        service.scan = AsyncMock(return_value=_make_scan_result())
        service.scan_metadata = AsyncMock(return_value=_make_scan_result())

        repo = MagicMock()
        repo.get_entities_with_zero_mentions = AsyncMock(return_value=zero_mention_ids)

        with (
            patch(
                "chronovista.cli.entity_commands.db_manager.get_session",
                return_value=_session_generator(),
            ),
            patch(
                "chronovista.cli.entity_commands.EntityMentionScanService",
                return_value=service,
            ),
            patch(
                "chronovista.cli.entity_commands.EntityMentionRepository",
                return_value=repo,
            ),
            patch(
                "chronovista.cli.entity_commands.asyncio.run",
                side_effect=_run_coro,
            ),
        ):
            runner.invoke(
                entity_app,
                ["scan", "--new-entities-only", "--sources", sources, "--dry-run"],
            )

        scan_kwargs = service.scan.call_args.kwargs if service.scan.call_args else None
        meta_kwargs = (
            service.scan_metadata.call_args.kwargs
            if service.scan_metadata.call_args
            else None
        )
        return scan_kwargs, meta_kwargs

    def test_both_phases_receive_the_same_entity_ids(self, runner: CliRunner) -> None:
        """The regression: the metadata phase must not re-derive its own scope.

        Re-deriving it after the transcript phase has written means the second
        phase sees a smaller set — which is how 23 of 32 entities were left
        without title or description mentions.
        """
        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        scan_kwargs, meta_kwargs = self._invoke(
            runner, ids, "transcript,title,description"
        )

        assert scan_kwargs is not None, "transcript phase was not dispatched"
        assert meta_kwargs is not None, "metadata phase was not dispatched"
        assert scan_kwargs["entity_ids"] == ids
        assert meta_kwargs["entity_ids"] == ids

    def test_scope_is_resolved_once_not_per_phase(self, runner: CliRunner) -> None:
        """The zero-mention query must run a single time for the whole command."""
        service = MagicMock()
        service.scan = AsyncMock(return_value=_make_scan_result())
        service.scan_metadata = AsyncMock(return_value=_make_scan_result())
        repo = MagicMock()
        repo.get_entities_with_zero_mentions = AsyncMock(return_value=[uuid.uuid4()])

        with (
            patch(
                "chronovista.cli.entity_commands.db_manager.get_session",
                return_value=_session_generator(),
            ),
            patch(
                "chronovista.cli.entity_commands.EntityMentionScanService",
                return_value=service,
            ),
            patch(
                "chronovista.cli.entity_commands.EntityMentionRepository",
                return_value=repo,
            ),
            patch("chronovista.cli.entity_commands.asyncio.run", side_effect=_run_coro),
        ):
            runner.invoke(
                entity_app,
                [
                    "scan",
                    "--new-entities-only",
                    "--sources",
                    "transcript,title,description",
                    "--dry-run",
                ],
            )

        assert repo.get_entities_with_zero_mentions.await_count == 1

    def test_flag_is_converted_to_explicit_ids(self, runner: CliRunner) -> None:
        """Once the set is pinned, the flag itself must not be forwarded.

        Passing both would let the service re-filter and reintroduce the drift.
        """
        ids = [uuid.uuid4()]
        scan_kwargs, meta_kwargs = self._invoke(runner, ids, "transcript,title")

        assert scan_kwargs["new_entities_only"] is False
        assert meta_kwargs["new_entities_only"] is False
        assert scan_kwargs["entity_ids"] == ids
        assert meta_kwargs["entity_ids"] == ids

    def test_metadata_only_sources_still_scoped(self, runner: CliRunner) -> None:
        """Without a transcript phase the scope must still be applied."""
        ids = [uuid.uuid4(), uuid.uuid4()]
        scan_kwargs, meta_kwargs = self._invoke(runner, ids, "title,description")

        assert scan_kwargs is None, "no transcript phase should be dispatched"
        assert meta_kwargs is not None
        assert meta_kwargs["entity_ids"] == ids

    def test_no_zero_mention_entities_exits_without_scanning(
        self, runner: CliRunner
    ) -> None:
        """An empty set must stop, not fall through to scanning everything.

        Treating "nothing is new" as "no filter" is how the original bug
        expressed itself.
        """
        service = MagicMock()
        service.scan = AsyncMock(return_value=_make_scan_result())
        service.scan_metadata = AsyncMock(return_value=_make_scan_result())
        repo = MagicMock()
        repo.get_entities_with_zero_mentions = AsyncMock(return_value=[])

        with (
            patch(
                "chronovista.cli.entity_commands.db_manager.get_session",
                return_value=_session_generator(),
            ),
            patch(
                "chronovista.cli.entity_commands.EntityMentionScanService",
                return_value=service,
            ),
            patch(
                "chronovista.cli.entity_commands.EntityMentionRepository",
                return_value=repo,
            ),
            patch("chronovista.cli.entity_commands.asyncio.run", side_effect=_run_coro),
        ):
            result = runner.invoke(
                entity_app,
                ["scan", "--new-entities-only", "--sources", "title", "--dry-run"],
            )

        service.scan.assert_not_awaited()
        service.scan_metadata.assert_not_awaited()
        assert "No entities with zero mentions" in result.output
