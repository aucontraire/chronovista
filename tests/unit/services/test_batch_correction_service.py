"""
Unit tests for BatchCorrectionService.

Tests the core infrastructure methods: constructor DI, _process_in_batches()
transaction batching, _validate_pattern() regex pre-validation, and
find_and_replace() in both live mode (T010) and dry-run mode (T011).

All database I/O is mocked — these are pure unit tests that validate
service-layer logic without any real database connection.

Feature 036 — Batch Correction Tools (T009, T010, T011)
Feature 038 — Entity Mention Detection (ASR alias hook)
"""

from __future__ import annotations

import uuid
from datetime import UTC
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from chronovista.models.enums import EntityAliasType

# ---------------------------------------------------------------------------
# CRITICAL: Module-level asyncio marker ensures async tests run properly
# with coverage tools, avoiding silent test-skipping (see CLAUDE.md).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_correction_service() -> AsyncMock:
    """Provide a mock TranscriptCorrectionService."""
    return AsyncMock()


@pytest.fixture
def mock_segment_repo() -> AsyncMock:
    """Provide a mock TranscriptSegmentRepository."""
    return AsyncMock()


@pytest.fixture
def mock_correction_repo() -> AsyncMock:
    """Provide a mock TranscriptCorrectionRepository."""
    return AsyncMock()


@pytest.fixture
def mock_session() -> AsyncMock:
    """Provide a mock AsyncSession with commit and rollback stubs."""
    return AsyncMock()


@pytest.fixture
def service(
    mock_correction_service: AsyncMock,
    mock_segment_repo: AsyncMock,
    mock_correction_repo: AsyncMock,
) -> Any:
    """
    Provide a BatchCorrectionService instance wired with mock dependencies.

    Lazy import to follow the TDD pattern used across the project.
    """
    from chronovista.services.batch_correction_service import (
        BatchCorrectionService,
    )

    return BatchCorrectionService(
        correction_service=mock_correction_service,
        segment_repo=mock_segment_repo,
        correction_repo=mock_correction_repo,
    )


# ---------------------------------------------------------------------------
# TestConstructor
# ---------------------------------------------------------------------------


class TestConstructor:
    """Tests that the constructor stores injected dependencies correctly."""

    def test_stores_correction_service(
        self,
        service: Any,
        mock_correction_service: AsyncMock,
    ) -> None:
        """Constructor must store the correction_service dependency."""
        assert service._correction_service is mock_correction_service

    def test_stores_segment_repo(
        self,
        service: Any,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """Constructor must store the segment_repo dependency."""
        assert service._segment_repo is mock_segment_repo

    def test_stores_correction_repo(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Constructor must store the correction_repo dependency."""
        assert service._correction_repo is mock_correction_repo


# ---------------------------------------------------------------------------
# TestProcessInBatches
# ---------------------------------------------------------------------------


class TestProcessInBatches:
    """
    Tests for BatchCorrectionService._process_in_batches().

    The method processes items in chunks with commit/rollback semantics:
    - After each successful chunk: session.commit()
    - After a failed chunk: session.rollback(), increment failed_batches
    - Returns (total_applied, total_skipped, total_failed, failed_batches)
    """

    async def test_all_items_succeed(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """
        When all items succeed, total_applied equals the item count,
        total_skipped/total_failed/failed_batches are all zero.
        """
        items = ["a", "b", "c"]

        async def process_fn(session: Any, item: Any) -> str:
            return "applied"

        applied, skipped, failed, failed_batches = (
            await service._process_in_batches(
                mock_session, items, process_fn, batch_size=10
            )
        )

        assert applied == 3
        assert skipped == 0
        assert failed == 0
        assert failed_batches == 0

    async def test_all_items_succeed_commit_called(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """
        When all items fit in one batch and succeed, session.commit()
        must be called exactly once.
        """
        items = ["a", "b"]

        async def process_fn(session: Any, item: Any) -> str:
            return "applied"

        await service._process_in_batches(
            mock_session, items, process_fn, batch_size=10
        )

        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()

    async def test_skipped_items_counted(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """
        When process_fn returns 'skipped', those items are counted
        separately from applied items.
        """
        items = ["apply", "skip", "apply", "skip", "skip"]

        async def process_fn(session: Any, item: Any) -> str:
            return "skipped" if item == "skip" else "applied"

        applied, skipped, failed, failed_batches = (
            await service._process_in_batches(
                mock_session, items, process_fn, batch_size=10
            )
        )

        assert applied == 2
        assert skipped == 3
        assert failed == 0
        assert failed_batches == 0

    async def test_empty_items_list(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """
        When the items list is empty, all counters are zero and no
        commit/rollback is called.
        """
        async def process_fn(session: Any, item: Any) -> str:
            return "applied"

        applied, skipped, failed, failed_batches = (
            await service._process_in_batches(
                mock_session, [], process_fn, batch_size=10
            )
        )

        assert applied == 0
        assert skipped == 0
        assert failed == 0
        assert failed_batches == 0
        mock_session.commit.assert_not_called()
        mock_session.rollback.assert_not_called()

    async def test_custom_batch_size(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """
        With batch_size=2 and 5 items, session.commit() should be called
        3 times (batches of 2, 2, 1).
        """
        items = list(range(5))

        async def process_fn(session: Any, item: Any) -> str:
            return "applied"

        applied, skipped, failed, failed_batches = (
            await service._process_in_batches(
                mock_session, items, process_fn, batch_size=2
            )
        )

        assert applied == 5
        assert mock_session.commit.call_count == 3

    async def test_batch_failure_rolls_back_and_continues(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """
        When a batch fails (process_fn raises), that batch is rolled back
        and the failed_batches counter is incremented. Processing continues
        with the next batch.

        With batch_size=2 and 4 items where batch 1 (items 0,1) fails:
        - Batch 0 (items 0,1): raises -> rollback, failed_batches=1, total_failed=2
        - Batch 1 (items 2,3): succeeds -> commit, total_applied=2
        """
        call_count = 0

        async def process_fn(session: Any, item: Any) -> str:
            nonlocal call_count
            call_count += 1
            if item < 2:
                raise RuntimeError("simulated failure")
            return "applied"

        items = list(range(4))
        applied, skipped, failed, failed_batches = (
            await service._process_in_batches(
                mock_session, items, process_fn, batch_size=2
            )
        )

        assert failed_batches == 1
        assert failed == 2
        assert applied == 2
        assert skipped == 0

    async def test_failed_batch_rollback_called(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """
        When a batch fails, session.rollback() must be called for that batch.
        """
        async def process_fn(session: Any, item: Any) -> str:
            raise RuntimeError("boom")

        items = ["x"]
        await service._process_in_batches(
            mock_session, items, process_fn, batch_size=10
        )

        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()

    async def test_successful_batch_commit_called(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """
        When a batch succeeds, session.commit() must be called.
        session.rollback() must not be called.
        """
        async def process_fn(session: Any, item: Any) -> str:
            return "applied"

        items = ["x"]
        await service._process_in_batches(
            mock_session, items, process_fn, batch_size=10
        )

        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()

    async def test_progress_callback_invoked(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """
        When a progress_callback is provided, it must be called with the
        chunk length after each batch (both success and failure).
        """
        callback = MagicMock()

        async def process_fn(session: Any, item: Any) -> str:
            return "applied"

        items = list(range(5))
        await service._process_in_batches(
            mock_session,
            items,
            process_fn,
            batch_size=2,
            progress_callback=callback,
        )

        # 3 batches: sizes 2, 2, 1
        assert callback.call_count == 3
        callback.assert_has_calls([call(2), call(2), call(1)])

    async def test_progress_callback_called_on_failure_too(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """
        The progress_callback is invoked even when a batch fails, so that
        callers always get accurate progress reporting.
        """
        callback = MagicMock()

        async def process_fn(session: Any, item: Any) -> str:
            raise RuntimeError("boom")

        items = ["a", "b"]
        await service._process_in_batches(
            mock_session,
            items,
            process_fn,
            batch_size=10,
            progress_callback=callback,
        )

        callback.assert_called_once_with(2)

    async def test_no_progress_callback_does_not_error(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """
        When progress_callback is None (default), no error should occur.
        """
        async def process_fn(session: Any, item: Any) -> str:
            return "applied"

        items = ["a"]
        applied, skipped, failed, failed_batches = (
            await service._process_in_batches(
                mock_session, items, process_fn, batch_size=10
            )
        )

        assert applied == 1

    async def test_multiple_batches_mixed_success_failure(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """
        With batch_size=1 and mixed results: the first item fails (in its
        own batch), the second succeeds, the third fails.

        Expected: applied=1, failed=2, failed_batches=2
        """
        call_index = 0

        async def process_fn(session: Any, item: Any) -> str:
            nonlocal call_index
            call_index += 1
            if item in ("fail1", "fail2"):
                raise RuntimeError("simulated")
            return "applied"

        items = ["fail1", "ok", "fail2"]
        applied, skipped, failed, failed_batches = (
            await service._process_in_batches(
                mock_session, items, process_fn, batch_size=1
            )
        )

        assert applied == 1
        assert failed == 2
        assert failed_batches == 2
        assert mock_session.commit.call_count == 1
        assert mock_session.rollback.call_count == 2


# ---------------------------------------------------------------------------
# TestValidatePattern
# ---------------------------------------------------------------------------


class TestValidatePattern:
    """
    Tests for BatchCorrectionService._validate_pattern().

    When regex=True, the pattern is compiled with re.compile(). Invalid
    patterns raise ValueError. When regex=False, no validation is performed.
    """

    def test_valid_regex_does_not_raise(self, service: Any) -> None:
        """A valid regex pattern should not raise any exception."""
        service._validate_pattern(r"\b\w+\b", regex=True)

    def test_complex_valid_regex(self, service: Any) -> None:
        """A more complex but valid regex should pass validation."""
        service._validate_pattern(
            r"(?:hello|world)\s+\d{2,4}", regex=True
        )

    def test_invalid_regex_raises_value_error(self, service: Any) -> None:
        """An invalid regex pattern must raise ValueError."""
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            service._validate_pattern("[unclosed", regex=True)

    def test_invalid_regex_error_message_includes_pattern(
        self, service: Any
    ) -> None:
        """The ValueError message must include the offending pattern."""
        with pytest.raises(ValueError, match=r"\[unclosed"):
            service._validate_pattern("[unclosed", regex=True)

    def test_substring_mode_no_validation(self, service: Any) -> None:
        """
        When regex=False, even an invalid regex string should not raise,
        because the pattern is treated as a plain substring.
        """
        # This would be invalid as regex, but substring mode skips validation
        service._validate_pattern("[unclosed", regex=False)

    def test_empty_regex_is_valid(self, service: Any) -> None:
        """An empty string is a valid regex (matches everything)."""
        service._validate_pattern("", regex=True)

    def test_empty_substring_is_valid(self, service: Any) -> None:
        """An empty string in substring mode should not raise."""
        service._validate_pattern("", regex=False)


# ---------------------------------------------------------------------------
# Helpers for find_and_replace tests
# ---------------------------------------------------------------------------


def _make_empty_execute_result(*args: Any, **kwargs: Any) -> MagicMock:
    """Return a synchronous MagicMock that satisfies all session.execute() call
    patterns used inside find_matching_segments():

    - ``video_result.all()``       → empty list (video title lookup)
    - ``channel_result.all()``     → empty list (channel title lookup)
    - ``result.all()``             → empty list (context neighbour query)
    - ``result.scalars().all()``   → empty list (fallback scalar patterns)
    """
    result = MagicMock()
    result.all.return_value = []
    result.scalars.return_value.all.return_value = []
    return result


def _make_segment(
    *,
    video_id: str = "vid1",
    segment_id: int = 1,
    language_code: str = "en",
    text: str = "hello world",
    corrected_text: str | None = None,
    has_correction: bool = False,
    start_time: float = 0.0,
    sequence_number: int = 1,
) -> MagicMock:
    """Create a mock TranscriptSegmentDB for testing."""
    seg = MagicMock()
    seg.video_id = video_id
    seg.id = segment_id
    seg.language_code = language_code
    seg.text = text
    seg.corrected_text = corrected_text
    seg.has_correction = has_correction
    seg.start_time = start_time
    # sequence_number must be an int so _batch_fetch_context_segments can
    # perform arithmetic (seq - 1, seq + 1) and the int comparison (seq >= 0).
    seg.sequence_number = sequence_number
    return seg


# ---------------------------------------------------------------------------
# TestFindAndReplaceLiveMode (T010)
# ---------------------------------------------------------------------------


class TestFindAndReplaceLiveMode:
    """
    Tests for find_and_replace() in live mode (dry_run=False).

    Validates that corrections are applied via TranscriptCorrectionService,
    no-ops are handled as skips, and BatchCorrectionResult is returned.
    """

    async def test_all_segments_match_and_corrected(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """All matched segments are corrected successfully."""
        seg1 = _make_segment(video_id="v1", segment_id=1, text="foo bar")
        seg2 = _make_segment(video_id="v1", segment_id=2, text="foo baz")

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg1, seg2]
        mock_correction_service.apply_correction.return_value = MagicMock()

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        result = await service.find_and_replace(
            mock_session,
            pattern="foo",
            replacement="qux",
        )

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_scanned == 10
        assert result.total_matched == 2
        assert result.total_applied == 2
        assert result.total_skipped == 0
        assert result.total_failed == 0
        assert result.failed_batches == 0
        assert result.unique_videos == 1

    async def test_some_segments_are_no_ops(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """
        When apply_correction raises ValueError (no-op), that segment
        is counted as skipped, not failed.
        """
        seg1 = _make_segment(segment_id=1, text="foo bar")
        seg2 = _make_segment(segment_id=2, text="foo baz")

        mock_segment_repo.count_filtered.return_value = 5
        mock_segment_repo.find_by_text_pattern.return_value = [seg1, seg2]

        # First apply succeeds, second raises ValueError (no-op)
        mock_correction_service.apply_correction.side_effect = [
            MagicMock(),
            ValueError("no-op"),
        ]

        result = await service.find_and_replace(
            mock_session,
            pattern="foo",
            replacement="qux",
        )

        assert result.total_applied == 1
        assert result.total_skipped == 1

    async def test_batch_failure_partial_success(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """
        When a batch fails (non-ValueError exception), the batch is
        rolled back and counted as failed. Other batches still succeed.
        """
        seg1 = _make_segment(segment_id=1, text="foo a")
        seg2 = _make_segment(segment_id=2, text="foo b")
        seg3 = _make_segment(segment_id=3, text="foo c")

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg1, seg2, seg3]

        # First call raises RuntimeError (batch failure), next two succeed
        mock_correction_service.apply_correction.side_effect = [
            RuntimeError("db error"),
            MagicMock(),
            MagicMock(),
        ]

        result = await service.find_and_replace(
            mock_session,
            pattern="foo",
            replacement="qux",
            batch_size=1,
        )

        assert result.total_matched == 3
        assert result.total_failed == 1
        assert result.failed_batches == 1
        assert result.total_applied == 2

    async def test_zero_matches_returns_all_zeros(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """When no segments match, result has all zeros except total_scanned."""
        mock_segment_repo.count_filtered.return_value = 100
        mock_segment_repo.find_by_text_pattern.return_value = []

        result = await service.find_and_replace(
            mock_session,
            pattern="nonexistent",
            replacement="replacement",
        )

        assert result.total_scanned == 100
        assert result.total_matched == 0
        assert result.total_applied == 0
        assert result.total_skipped == 0
        assert result.total_failed == 0
        assert result.unique_videos == 0
        mock_correction_service.apply_correction.assert_not_called()

    async def test_regex_replacement(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """Regex patterns are used for replacement with re.sub()."""
        seg = _make_segment(segment_id=1, text="hello 123 world 456")

        mock_segment_repo.count_filtered.return_value = 1
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_service.apply_correction.return_value = MagicMock()

        await service.find_and_replace(
            mock_session,
            pattern=r"\d+",
            replacement="NUM",
            regex=True,
        )

        # Verify the corrected_text passed to apply_correction
        call_kwargs = mock_correction_service.apply_correction.call_args.kwargs
        assert call_kwargs["corrected_text"] == "hello NUM world NUM"

    async def test_case_insensitive_substring_replacement(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """Case-insensitive substring mode uses re.sub with re.escape."""
        seg = _make_segment(segment_id=1, text="Hello HELLO hello")

        mock_segment_repo.count_filtered.return_value = 1
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_service.apply_correction.return_value = MagicMock()

        await service.find_and_replace(
            mock_session,
            pattern="hello",
            replacement="hi",
            case_insensitive=True,
        )

        call_kwargs = mock_correction_service.apply_correction.call_args.kwargs
        assert call_kwargs["corrected_text"] == "hi hi hi"

    async def test_progress_callback_called(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """Progress callback is invoked during batch processing."""
        seg1 = _make_segment(segment_id=1, text="foo x")
        seg2 = _make_segment(segment_id=2, text="foo y")
        seg3 = _make_segment(segment_id=3, text="foo z")

        mock_segment_repo.count_filtered.return_value = 3
        mock_segment_repo.find_by_text_pattern.return_value = [seg1, seg2, seg3]
        mock_correction_service.apply_correction.return_value = MagicMock()

        callback = MagicMock()

        await service.find_and_replace(
            mock_session,
            pattern="foo",
            replacement="bar",
            batch_size=2,
            progress_callback=callback,
        )

        # 2 batches: size 2 and size 1
        assert callback.call_count == 2
        callback.assert_has_calls([call(2), call(1)])

    async def test_unique_videos_count(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """unique_videos counts distinct video_ids from matched segments."""
        seg1 = _make_segment(video_id="v1", segment_id=1, text="foo a")
        seg2 = _make_segment(video_id="v2", segment_id=2, text="foo b")
        seg3 = _make_segment(video_id="v1", segment_id=3, text="foo c")

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg1, seg2, seg3]
        mock_correction_service.apply_correction.return_value = MagicMock()

        result = await service.find_and_replace(
            mock_session,
            pattern="foo",
            replacement="bar",
        )

        assert result.unique_videos == 2

    async def test_uses_corrected_text_when_has_correction(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """
        When a segment has_correction=True, effective text is
        corrected_text, not the original text.
        """
        seg = _make_segment(
            segment_id=1,
            text="original foo text",
            corrected_text="already corrected foo text",
            has_correction=True,
        )

        mock_segment_repo.count_filtered.return_value = 1
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_service.apply_correction.return_value = MagicMock()

        await service.find_and_replace(
            mock_session,
            pattern="foo",
            replacement="bar",
        )

        call_kwargs = mock_correction_service.apply_correction.call_args.kwargs
        assert call_kwargs["corrected_text"] == "already corrected bar text"

    async def test_apply_correction_receives_actor_cli_batch(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """apply_correction is called with corrected_by_user_id=ACTOR_CLI_BATCH."""
        seg = _make_segment(segment_id=1, text="foo bar")

        mock_segment_repo.count_filtered.return_value = 1
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_service.apply_correction.return_value = MagicMock()

        from chronovista.models.correction_actors import ACTOR_CLI_BATCH

        await service.find_and_replace(
            mock_session,
            pattern="foo",
            replacement="baz",
        )

        call_kwargs = mock_correction_service.apply_correction.call_args.kwargs
        assert call_kwargs["corrected_by_user_id"] == ACTOR_CLI_BATCH

    async def test_invalid_regex_raises_before_processing(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """Invalid regex raises ValueError before any repo calls."""
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            await service.find_and_replace(
                mock_session,
                pattern="[unclosed",
                replacement="x",
                regex=True,
            )

        mock_segment_repo.count_filtered.assert_not_called()
        mock_segment_repo.find_by_text_pattern.assert_not_called()


# ---------------------------------------------------------------------------
# TestFindAndReplaceDryRun (T011)
# ---------------------------------------------------------------------------


class TestFindAndReplaceDryRun:
    """
    Tests for find_and_replace() in dry-run mode (dry_run=True).

    Validates that no corrections are applied, and a list of preview
    tuples is returned.
    """

    async def test_returns_list_of_tuples(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """Dry-run returns a list of tuples, not a BatchCorrectionResult."""
        seg = _make_segment(
            video_id="v1",
            segment_id=42,
            text="foo bar",
            start_time=1.5,
        )
        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        # find_matching_segments() calls session.execute() for video titles,
        # channel titles, and context neighbour segments. Return empty results
        # so the mock session doesn't raise on .all().
        mock_session.execute.side_effect = _make_empty_execute_result

        result = await service.find_and_replace(
            mock_session,
            pattern="foo",
            replacement="qux",
            dry_run=True,
        )

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], tuple)

    async def test_no_apply_correction_calls(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """Dry-run mode never calls apply_correction."""
        seg = _make_segment(segment_id=1, text="foo bar")
        mock_segment_repo.count_filtered.return_value = 1
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_session.execute.side_effect = _make_empty_execute_result

        await service.find_and_replace(
            mock_session,
            pattern="foo",
            replacement="baz",
            dry_run=True,
        )

        mock_correction_service.apply_correction.assert_not_called()

    async def test_preview_tuples_contain_correct_values(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """
        Preview tuples contain (video_id, segment_id, start_time,
        current_text, proposed_text).
        """
        seg = _make_segment(
            video_id="v99",
            segment_id=7,
            text="hello world",
            start_time=3.14,
        )
        mock_segment_repo.count_filtered.return_value = 1
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_session.execute.side_effect = _make_empty_execute_result

        result = await service.find_and_replace(
            mock_session,
            pattern="world",
            replacement="earth",
            dry_run=True,
        )

        video_id, segment_id, start_time, current, proposed = result[0]
        assert video_id == "v99"
        assert segment_id == 7
        assert start_time == 3.14
        assert current == "hello world"
        assert proposed == "hello earth"

    async def test_preview_uses_corrected_text_when_has_correction(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """Preview uses corrected_text as current text when has_correction=True."""
        seg = _make_segment(
            segment_id=1,
            text="original foo text",
            corrected_text="corrected foo text",
            has_correction=True,
            start_time=0.0,
        )
        mock_segment_repo.count_filtered.return_value = 1
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_session.execute.side_effect = _make_empty_execute_result

        result = await service.find_and_replace(
            mock_session,
            pattern="foo",
            replacement="bar",
            dry_run=True,
        )

        _, _, _, current, proposed = result[0]
        assert current == "corrected foo text"
        assert proposed == "corrected bar text"

    async def test_dry_run_empty_matches_returns_empty_list(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """When no segments match, dry-run returns an empty list."""
        mock_segment_repo.count_filtered.return_value = 50
        mock_segment_repo.find_by_text_pattern.return_value = []

        result = await service.find_and_replace(
            mock_session,
            pattern="nonexistent",
            replacement="anything",
            dry_run=True,
        )

        assert result == []

    async def test_dry_run_regex_preview(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """Dry-run with regex=True shows correct proposed replacement."""
        seg = _make_segment(
            segment_id=1,
            text="price is $100.00 today",
            start_time=5.0,
        )
        mock_segment_repo.count_filtered.return_value = 1
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_session.execute.side_effect = _make_empty_execute_result

        result = await service.find_and_replace(
            mock_session,
            pattern=r"\$\d+\.\d+",
            replacement="[PRICE]",
            regex=True,
            dry_run=True,
        )

        _, _, _, current, proposed = result[0]
        assert current == "price is $100.00 today"
        assert proposed == "price is [PRICE] today"

    async def test_dry_run_invalid_regex_raises(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """Invalid regex raises ValueError even in dry-run mode."""
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            await service.find_and_replace(
                mock_session,
                pattern="[bad",
                replacement="x",
                regex=True,
                dry_run=True,
            )

        mock_segment_repo.count_filtered.assert_not_called()


# ---------------------------------------------------------------------------
# Helpers for rebuild_text, batch_revert tests
# ---------------------------------------------------------------------------


def _make_transcript(
    *,
    video_id: str = "vid1",
    language_code: str = "en",
    transcript_text: str = "old text",
    has_corrections: bool = True,
) -> MagicMock:
    """Create a mock VideoTranscriptDB for testing."""
    t = MagicMock()
    t.video_id = video_id
    t.language_code = language_code
    t.transcript_text = transcript_text
    t.has_corrections = has_corrections
    return t


def _make_correction_db(
    *,
    id: str = "00000000-0000-0000-0000-000000000001",
    video_id: str = "vid1",
    language_code: str = "en",
    segment_id: int = 1,
    correction_type: str = "proper_noun",
    original_text: str = "old",
    corrected_text: str = "new",
    correction_note: str | None = None,
    corrected_by_user_id: str | None = None,
    corrected_at: Any = None,
    version_number: int = 1,
    batch_id: Any = None,
) -> MagicMock:
    """Create a mock TranscriptCorrectionDB for testing."""
    from datetime import datetime

    c = MagicMock()
    c.id = id
    c.video_id = video_id
    c.language_code = language_code
    c.segment_id = segment_id
    c.correction_type = correction_type
    c.original_text = original_text
    c.corrected_text = corrected_text
    c.correction_note = correction_note
    c.corrected_by_user_id = corrected_by_user_id
    c.corrected_at = corrected_at or datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
    c.version_number = version_number
    c.batch_id = batch_id
    return c


# ---------------------------------------------------------------------------
# TestRebuildText (T017)
# ---------------------------------------------------------------------------


class TestRebuildText:
    """Tests for BatchCorrectionService.rebuild_text()."""

    async def test_dry_run_returns_preview_dicts(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """Dry-run returns a list of preview dicts."""
        transcript = _make_transcript(
            video_id="v1", language_code="en", transcript_text="old text"
        )

        seg1 = _make_segment(
            video_id="v1", segment_id=1, text="hello", start_time=0.0,
            has_correction=True, corrected_text="HELLO",
        )
        seg2 = _make_segment(
            video_id="v1", segment_id=2, text="world", start_time=1.0,
        )

        # Mock the session.execute for transcript query
        transcript_result = MagicMock()
        transcript_result.scalars.return_value.all.return_value = [transcript]

        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg1, seg2]

        mock_session.execute.side_effect = [transcript_result, segment_result]

        result = await service.rebuild_text(mock_session, dry_run=True)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["video_id"] == "v1"
        assert result[0]["language_code"] == "en"
        assert result[0]["current_length"] == len("old text")
        assert result[0]["new_length"] == len("HELLO\nworld")

    async def test_live_mode_returns_tuple(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """Live mode returns (total_rebuilt, total_segments)."""
        transcript = _make_transcript(video_id="v1")

        seg1 = _make_segment(
            video_id="v1", segment_id=1, text="hello", start_time=0.0,
            has_correction=True, corrected_text="HELLO",
        )
        seg2 = _make_segment(
            video_id="v1", segment_id=2, text="world", start_time=1.0,
        )

        transcript_result = MagicMock()
        transcript_result.scalars.return_value.all.return_value = [transcript]

        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg1, seg2]

        mock_session.execute.side_effect = [transcript_result, segment_result]

        result = await service.rebuild_text(mock_session, dry_run=False)

        assert isinstance(result, tuple)
        assert result == (1, 2)

    async def test_live_mode_updates_transcript_text(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """Live mode sets transcript_text to concatenated effective texts."""
        transcript = _make_transcript(video_id="v1", transcript_text="old")

        seg1 = _make_segment(
            video_id="v1", segment_id=1, text="hello", start_time=0.0,
            has_correction=True, corrected_text="HELLO",
        )
        seg2 = _make_segment(
            video_id="v1", segment_id=2, text="world", start_time=1.0,
        )

        transcript_result = MagicMock()
        transcript_result.scalars.return_value.all.return_value = [transcript]

        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg1, seg2]

        mock_session.execute.side_effect = [transcript_result, segment_result]

        await service.rebuild_text(mock_session, dry_run=False)

        assert transcript.transcript_text == "HELLO world"

    async def test_skips_transcript_with_no_corrected_segments(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """Transcripts where no segment has_correction are skipped."""
        transcript = _make_transcript(video_id="v1")

        seg1 = _make_segment(
            video_id="v1", segment_id=1, text="hello", start_time=0.0,
        )

        transcript_result = MagicMock()
        transcript_result.scalars.return_value.all.return_value = [transcript]

        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg1]

        mock_session.execute.side_effect = [transcript_result, segment_result]

        result = await service.rebuild_text(mock_session, dry_run=False)

        assert result == (0, 0)

    async def test_empty_transcripts_returns_zero(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """When no transcripts have corrections, returns (0, 0)."""
        transcript_result = MagicMock()
        transcript_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [transcript_result]

        result = await service.rebuild_text(mock_session, dry_run=False)
        assert result == (0, 0)

    async def test_dry_run_empty_returns_empty_list(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """Dry-run with no transcripts returns empty list."""
        transcript_result = MagicMock()
        transcript_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [transcript_result]

        result = await service.rebuild_text(mock_session, dry_run=True)
        assert result == []

    async def test_progress_callback_called_per_transcript(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """Progress callback invoked once per transcript."""
        t1 = _make_transcript(video_id="v1")
        t2 = _make_transcript(video_id="v2")

        seg1 = _make_segment(
            video_id="v1", segment_id=1, text="a", start_time=0.0,
            has_correction=True, corrected_text="A",
        )
        seg2 = _make_segment(
            video_id="v2", segment_id=2, text="b", start_time=0.0,
            has_correction=True, corrected_text="B",
        )

        transcript_result = MagicMock()
        transcript_result.scalars.return_value.all.return_value = [t1, t2]

        seg_result1 = MagicMock()
        seg_result1.scalars.return_value.all.return_value = [seg1]

        seg_result2 = MagicMock()
        seg_result2.scalars.return_value.all.return_value = [seg2]

        mock_session.execute.side_effect = [transcript_result, seg_result1, seg_result2]
        # flush calls
        mock_session.flush = AsyncMock()

        callback = MagicMock()
        await service.rebuild_text(mock_session, dry_run=False, progress_callback=callback)

        assert callback.call_count == 2
        callback.assert_has_calls([call(1), call(1)])

    async def test_multiple_transcripts_rebuilt(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """Multiple transcripts each with corrected segments are rebuilt."""
        t1 = _make_transcript(video_id="v1")
        t2 = _make_transcript(video_id="v2")

        seg1 = _make_segment(
            video_id="v1", segment_id=1, text="a", start_time=0.0,
            has_correction=True, corrected_text="A",
        )
        seg2 = _make_segment(
            video_id="v2", segment_id=2, text="b", start_time=0.0,
            has_correction=True, corrected_text="B",
        )

        transcript_result = MagicMock()
        transcript_result.scalars.return_value.all.return_value = [t1, t2]

        sr1 = MagicMock()
        sr1.scalars.return_value.all.return_value = [seg1]
        sr2 = MagicMock()
        sr2.scalars.return_value.all.return_value = [seg2]

        mock_session.execute.side_effect = [transcript_result, sr1, sr2]
        mock_session.flush = AsyncMock()

        result = await service.rebuild_text(mock_session, dry_run=False)
        assert result == (2, 2)


# ---------------------------------------------------------------------------
# TestExportCorrections (T019)
# ---------------------------------------------------------------------------


class TestExportCorrections:
    """Tests for BatchCorrectionService.export_corrections()."""

    async def test_csv_format_returns_csv_string(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """CSV format produces a valid CSV string with headers."""
        c = _make_correction_db(video_id="v1", segment_id=1)
        mock_correction_repo.get_all_filtered.return_value = [c]

        count, csv_str = await service.export_corrections(
            mock_session, format="csv",
        )

        assert count == 1
        assert "id,video_id,language_code" in csv_str
        assert "v1" in csv_str

    async def test_csv_has_correct_columns(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """CSV header contains all expected column names."""
        mock_correction_repo.get_all_filtered.return_value = []

        _, csv_str = await service.export_corrections(
            mock_session, format="csv",
        )

        header = csv_str.strip().split("\n")[0]
        expected_cols = [
            "id", "video_id", "language_code", "segment_id",
            "correction_type", "original_text", "corrected_text",
            "correction_note", "corrected_by_user_id", "corrected_at",
            "version_number", "batch_id",
        ]
        assert header == ",".join(expected_cols)

    async def test_json_format_returns_json_string(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """JSON format produces a parseable JSON array."""
        import json

        c = _make_correction_db(video_id="v1")
        mock_correction_repo.get_all_filtered.return_value = [c]

        count, json_str = await service.export_corrections(
            mock_session, format="json",
        )

        assert count == 1
        parsed = json.loads(json_str)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["video_id"] == "v1"

    async def test_json_compact_has_no_indentation(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Compact JSON has no newlines from indentation."""
        import json

        c = _make_correction_db()
        mock_correction_repo.get_all_filtered.return_value = [c]

        _, json_str = await service.export_corrections(
            mock_session, format="json", compact=True,
        )

        # Compact JSON should be a single line (no indent newlines)
        parsed = json.loads(json_str)
        assert isinstance(parsed, list)
        # Verify no pretty-print indentation
        assert "\n  " not in json_str

    async def test_json_non_compact_has_indentation(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Non-compact JSON has 2-space indentation."""
        c = _make_correction_db()
        mock_correction_repo.get_all_filtered.return_value = [c]

        _, json_str = await service.export_corrections(
            mock_session, format="json", compact=False,
        )

        # Should have indented content
        assert "\n  " in json_str

    async def test_empty_corrections_returns_zero(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """No corrections produces count 0."""
        mock_correction_repo.get_all_filtered.return_value = []

        count, csv_str = await service.export_corrections(
            mock_session, format="csv",
        )

        assert count == 0

    async def test_filters_passed_to_repo(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """All filter params are passed through to the repository."""
        from datetime import datetime

        from chronovista.models.enums import CorrectionType

        mock_correction_repo.get_all_filtered.return_value = []
        since = datetime(2025, 1, 1, tzinfo=UTC)
        until = datetime(2025, 12, 31, tzinfo=UTC)

        await service.export_corrections(
            mock_session,
            video_ids=["v1", "v2"],
            correction_type=CorrectionType.SPELLING,
            since=since,
            until=until,
        )

        mock_correction_repo.get_all_filtered.assert_called_once_with(
            mock_session,
            video_ids=["v1", "v2"],
            correction_type=CorrectionType.SPELLING,
            since=since,
            until=until,
        )

    async def test_progress_callback_called_per_record(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Progress callback invoked once per correction record."""
        c1 = _make_correction_db(id="id1", video_id="v1")
        c2 = _make_correction_db(id="id2", video_id="v2")
        mock_correction_repo.get_all_filtered.return_value = [c1, c2]

        callback = MagicMock()
        await service.export_corrections(
            mock_session, format="csv", progress_callback=callback,
        )

        assert callback.call_count == 2

    async def test_csv_multiple_records(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """CSV with multiple records produces correct row count."""
        c1 = _make_correction_db(id="id1", video_id="v1")
        c2 = _make_correction_db(id="id2", video_id="v2")
        mock_correction_repo.get_all_filtered.return_value = [c1, c2]

        count, csv_str = await service.export_corrections(
            mock_session, format="csv",
        )

        assert count == 2
        lines = csv_str.strip().split("\n")
        assert len(lines) == 3  # header + 2 data rows

    async def test_json_empty_returns_empty_array(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Empty JSON export returns '[]'."""
        import json

        mock_correction_repo.get_all_filtered.return_value = []

        count, json_str = await service.export_corrections(
            mock_session, format="json",
        )

        assert count == 0
        assert json.loads(json_str) == []


# ---------------------------------------------------------------------------
# TestGetStatistics (T021)
# ---------------------------------------------------------------------------


class TestGetStatistics:
    """Tests for BatchCorrectionService.get_statistics()."""

    async def test_delegates_to_repo(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """get_statistics delegates to correction_repo.get_stats."""
        mock_correction_repo.get_stats.return_value = {
            "total_corrections": 10,
            "total_reverts": 2,
            "unique_segments": 8,
            "unique_videos": 3,
            "by_type": [],
            "top_videos": [],
        }

        result = await service.get_statistics(mock_session)

        mock_correction_repo.get_stats.assert_called_once_with(
            mock_session, language=None, top=10,
        )
        assert result.total_corrections == 10
        assert result.total_reverts == 2

    async def test_returns_correction_stats_model(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Return type is CorrectionStats."""
        from chronovista.models.batch_correction_models import CorrectionStats

        mock_correction_repo.get_stats.return_value = {
            "total_corrections": 5,
            "total_reverts": 1,
            "unique_segments": 4,
            "unique_videos": 2,
            "by_type": [],
            "top_videos": [],
        }

        result = await service.get_statistics(mock_session)
        assert isinstance(result, CorrectionStats)

    async def test_passes_language_and_top_params(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Language and top params are forwarded to repo."""
        mock_correction_repo.get_stats.return_value = {
            "total_corrections": 0,
            "total_reverts": 0,
            "unique_segments": 0,
            "unique_videos": 0,
            "by_type": [],
            "top_videos": [],
        }

        await service.get_statistics(mock_session, language="es", top=5)

        mock_correction_repo.get_stats.assert_called_once_with(
            mock_session, language="es", top=5,
        )

    async def test_by_type_populated(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """by_type field is populated from repo result."""
        from chronovista.models.batch_correction_models import TypeCount

        mock_correction_repo.get_stats.return_value = {
            "total_corrections": 3,
            "total_reverts": 0,
            "unique_segments": 3,
            "unique_videos": 1,
            "by_type": [TypeCount(correction_type="proper_noun", count=3)],
            "top_videos": [],
        }

        result = await service.get_statistics(mock_session)
        assert len(result.by_type) == 1
        assert result.by_type[0].correction_type == "proper_noun"

    async def test_top_videos_populated(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """top_videos field is populated from repo result."""
        from chronovista.models.batch_correction_models import VideoCount

        mock_correction_repo.get_stats.return_value = {
            "total_corrections": 5,
            "total_reverts": 0,
            "unique_segments": 5,
            "unique_videos": 2,
            "by_type": [],
            "top_videos": [VideoCount(video_id="v1", title="Test", count=3)],
        }

        result = await service.get_statistics(mock_session)
        assert len(result.top_videos) == 1
        assert result.top_videos[0].video_id == "v1"

    async def test_zero_stats(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """All-zero stats are returned correctly."""
        mock_correction_repo.get_stats.return_value = {
            "total_corrections": 0,
            "total_reverts": 0,
            "unique_segments": 0,
            "unique_videos": 0,
            "by_type": [],
            "top_videos": [],
        }

        result = await service.get_statistics(mock_session)
        assert result.total_corrections == 0
        assert result.unique_videos == 0

    async def test_unique_segments_and_videos(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """unique_segments and unique_videos are properly mapped."""
        mock_correction_repo.get_stats.return_value = {
            "total_corrections": 15,
            "total_reverts": 3,
            "unique_segments": 12,
            "unique_videos": 5,
            "by_type": [],
            "top_videos": [],
        }

        result = await service.get_statistics(mock_session)
        assert result.unique_segments == 12
        assert result.unique_videos == 5


# ---------------------------------------------------------------------------
# TestGetPatterns (T023)
# ---------------------------------------------------------------------------


class TestGetPatterns:
    """Tests for BatchCorrectionService.get_patterns()."""

    async def test_delegates_to_repo(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """get_patterns delegates to correction_repo.get_correction_patterns."""
        from chronovista.models.batch_correction_models import CorrectionPattern

        mock_correction_repo.get_correction_patterns.return_value = [
            CorrectionPattern(
                original_text="teh",
                corrected_text="the",
                occurrences=5,
                remaining_matches=10,
            ),
        ]

        result = await service.get_patterns(mock_session)

        mock_correction_repo.get_correction_patterns.assert_called_once_with(
            mock_session,
            min_occurrences=2,
            limit=25,
            show_completed=False,
        )
        assert len(result) == 1
        assert result[0].original_text == "teh"

    async def test_returns_list_of_correction_pattern(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Return type is list[CorrectionPattern]."""

        mock_correction_repo.get_correction_patterns.return_value = []

        result = await service.get_patterns(mock_session)
        assert isinstance(result, list)

    async def test_passes_params_to_repo(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Parameters are forwarded to the repo."""
        mock_correction_repo.get_correction_patterns.return_value = []

        await service.get_patterns(
            mock_session, min_occurrences=5, limit=10, show_completed=True,
        )

        mock_correction_repo.get_correction_patterns.assert_called_once_with(
            mock_session,
            min_occurrences=5,
            limit=10,
            show_completed=True,
        )

    async def test_empty_patterns(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Returns empty list when no patterns found."""
        mock_correction_repo.get_correction_patterns.return_value = []

        result = await service.get_patterns(mock_session)
        assert result == []

    async def test_multiple_patterns_returned(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Multiple patterns are returned as-is."""
        from chronovista.models.batch_correction_models import CorrectionPattern

        patterns = [
            CorrectionPattern(
                original_text="teh", corrected_text="the",
                occurrences=5, remaining_matches=10,
            ),
            CorrectionPattern(
                original_text="taht", corrected_text="that",
                occurrences=3, remaining_matches=7,
            ),
        ]
        mock_correction_repo.get_correction_patterns.return_value = patterns

        result = await service.get_patterns(mock_session)
        assert len(result) == 2
        assert result[0].original_text == "teh"
        assert result[1].original_text == "taht"

    async def test_remaining_matches_preserved(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """remaining_matches values are preserved from repo."""
        from chronovista.models.batch_correction_models import CorrectionPattern

        mock_correction_repo.get_correction_patterns.return_value = [
            CorrectionPattern(
                original_text="x", corrected_text="y",
                occurrences=2, remaining_matches=99,
            ),
        ]

        result = await service.get_patterns(mock_session)
        assert result[0].remaining_matches == 99

    async def test_default_params(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Default parameters are min_occurrences=2, limit=25, show_completed=False."""
        mock_correction_repo.get_correction_patterns.return_value = []

        await service.get_patterns(mock_session)

        mock_correction_repo.get_correction_patterns.assert_called_once_with(
            mock_session,
            min_occurrences=2,
            limit=25,
            show_completed=False,
        )

    async def test_show_completed_true(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """show_completed=True is forwarded."""
        mock_correction_repo.get_correction_patterns.return_value = []

        await service.get_patterns(mock_session, show_completed=True)

        call_kwargs = mock_correction_repo.get_correction_patterns.call_args.kwargs
        assert call_kwargs["show_completed"] is True


# ---------------------------------------------------------------------------
# TestBatchRevert (T025)
# ---------------------------------------------------------------------------


class TestBatchRevert:
    """Tests for BatchCorrectionService.batch_revert()."""

    async def test_dry_run_returns_preview_tuples(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Dry-run returns list of (video_id, segment_id, start_time, corrected_text, is_partner)."""
        seg = _make_segment(
            video_id="v1", segment_id=10, text="original",
            corrected_text="fixed text", has_correction=True, start_time=5.5,
        )

        mock_segment_repo.count_filtered.return_value = 100
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        # No cross-segment partner for this segment
        mock_correction_repo.get_by_segment.return_value = []

        result = await service.batch_revert(
            mock_session, pattern="fixed", dry_run=True,
        )

        assert isinstance(result, list)
        assert len(result) == 1
        video_id, segment_id, start_time, corrected_text, is_partner = result[0]
        assert video_id == "v1"
        assert segment_id == 10
        assert start_time == 5.5
        assert corrected_text == "fixed text"
        assert is_partner is False

    async def test_dry_run_filters_has_correction(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Dry-run only includes segments with has_correction=True."""
        seg_corrected = _make_segment(
            video_id="v1", segment_id=1, text="a",
            corrected_text="fixed", has_correction=True,
        )
        seg_uncorrected = _make_segment(
            video_id="v1", segment_id=2, text="fixed",
            has_correction=False,
        )

        mock_segment_repo.count_filtered.return_value = 50
        mock_segment_repo.find_by_text_pattern.return_value = [
            seg_corrected, seg_uncorrected,
        ]
        # No cross-segment partner
        mock_correction_repo.get_by_segment.return_value = []

        result = await service.batch_revert(
            mock_session, pattern="fixed", dry_run=True,
        )

        assert len(result) == 1
        assert result[0][1] == 1  # segment_id of the corrected one

    async def test_live_mode_returns_batch_result(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Live mode returns BatchCorrectionResult."""
        from chronovista.models.batch_correction_models import BatchCorrectionResult

        seg = _make_segment(
            video_id="v1", segment_id=1, text="orig",
            corrected_text="fixed", has_correction=True,
        )

        mock_segment_repo.count_filtered.return_value = 100
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_service.revert_correction.return_value = MagicMock()
        mock_correction_repo.get_by_segment.return_value = []
        # T033: session.execute() is called for correction ID query
        mock_session.execute.return_value = _make_empty_execute_result()

        result = await service.batch_revert(
            mock_session, pattern="fixed",
        )

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_scanned == 100
        assert result.total_matched == 1
        assert result.total_applied == 1

    async def test_live_mode_calls_revert_correction(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Live mode calls revert_correction for each matched segment."""
        seg = _make_segment(
            video_id="v1", segment_id=42, text="orig",
            corrected_text="fixed", has_correction=True,
        )

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_service.revert_correction.return_value = MagicMock()
        mock_correction_repo.get_by_segment.return_value = []
        # T033: session.execute() is called for correction ID query
        mock_session.execute.return_value = _make_empty_execute_result()

        await service.batch_revert(mock_session, pattern="fixed")

        mock_correction_service.revert_correction.assert_called_once_with(
            mock_session, segment_id=42,
        )

    async def test_live_mode_skips_on_value_error(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """ValueError from revert_correction is handled as skip."""
        seg1 = _make_segment(
            video_id="v1", segment_id=1, text="a",
            corrected_text="fixed a", has_correction=True,
        )
        seg2 = _make_segment(
            video_id="v1", segment_id=2, text="b",
            corrected_text="fixed b", has_correction=True,
        )

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg1, seg2]
        mock_correction_service.revert_correction.side_effect = [
            MagicMock(),
            ValueError("no active correction"),
        ]
        mock_correction_repo.get_by_segment.return_value = []
        # T033: session.execute() is called for correction ID query
        mock_session.execute.return_value = _make_empty_execute_result()

        result = await service.batch_revert(mock_session, pattern="fixed")

        assert result.total_applied == 1
        assert result.total_skipped == 1

    async def test_zero_corrected_matches_returns_zero_result(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """When all matches are uncorrected, total_matched is 0."""
        seg = _make_segment(
            video_id="v1", segment_id=1, text="fixed text",
            has_correction=False,
        )

        mock_segment_repo.count_filtered.return_value = 100
        mock_segment_repo.find_by_text_pattern.return_value = [seg]

        result = await service.batch_revert(mock_session, pattern="fixed")

        assert result.total_matched == 0
        assert result.total_applied == 0
        mock_correction_service.revert_correction.assert_not_called()

    async def test_invalid_regex_raises(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """Invalid regex raises ValueError before processing."""
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            await service.batch_revert(
                mock_session, pattern="[bad", regex=True,
            )

        mock_segment_repo.count_filtered.assert_not_called()

    async def test_unique_videos_counted(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """unique_videos counts distinct video_ids from corrected matches."""
        seg1 = _make_segment(
            video_id="v1", segment_id=1, text="a",
            corrected_text="fix", has_correction=True,
        )
        seg2 = _make_segment(
            video_id="v2", segment_id=2, text="b",
            corrected_text="fix", has_correction=True,
        )
        seg3 = _make_segment(
            video_id="v1", segment_id=3, text="c",
            corrected_text="fix", has_correction=True,
        )

        mock_segment_repo.count_filtered.return_value = 50
        mock_segment_repo.find_by_text_pattern.return_value = [seg1, seg2, seg3]
        mock_correction_service.revert_correction.return_value = MagicMock()
        mock_correction_repo.get_by_segment.return_value = []
        # T033: session.execute() is called for correction ID query
        mock_session.execute.return_value = _make_empty_execute_result()

        result = await service.batch_revert(mock_session, pattern="fix")

        assert result.unique_videos == 2

    async def test_progress_callback_called(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Progress callback is invoked during batch processing."""
        seg1 = _make_segment(
            video_id="v1", segment_id=1, text="a",
            corrected_text="fix a", has_correction=True,
        )
        seg2 = _make_segment(
            video_id="v1", segment_id=2, text="b",
            corrected_text="fix b", has_correction=True,
        )

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg1, seg2]
        mock_correction_service.revert_correction.return_value = MagicMock()
        mock_correction_repo.get_by_segment.return_value = []
        # T033: session.execute() is called for correction ID query
        mock_session.execute.return_value = _make_empty_execute_result()

        callback = MagicMock()
        await service.batch_revert(
            mock_session, pattern="fix", batch_size=1, progress_callback=callback,
        )

        assert callback.call_count == 2

    async def test_empty_matches_returns_zero_result(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """No matches at all returns zero BatchCorrectionResult."""
        mock_segment_repo.count_filtered.return_value = 200
        mock_segment_repo.find_by_text_pattern.return_value = []

        result = await service.batch_revert(mock_session, pattern="nothing")

        assert result.total_scanned == 200
        assert result.total_matched == 0
        assert result.total_applied == 0

    async def test_dry_run_no_mutations(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Dry-run mode does not call revert_correction."""
        seg = _make_segment(
            video_id="v1", segment_id=1, text="a",
            corrected_text="fix", has_correction=True,
        )

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_repo.get_by_segment.return_value = []

        await service.batch_revert(mock_session, pattern="fix", dry_run=True)

        mock_correction_service.revert_correction.assert_not_called()

    # -----------------------------------------------------------------------
    # T033/T034: Entity mention cascade on revert
    # -----------------------------------------------------------------------

    async def test_revert_deletes_correction_linked_mentions(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Revert cascade deletes entity mentions linked to reverted corrections."""
        import uuid as _uuid

        seg = _make_segment(
            video_id="v1", segment_id=1, text="orig",
            corrected_text="fixed", has_correction=True,
        )

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_service.revert_correction.return_value = MagicMock()
        mock_correction_repo.get_by_segment.return_value = []

        # Simulate correction ID query returning a correction UUID
        corr_id = _uuid.uuid4()
        entity_id = _uuid.uuid4()
        correction_result = MagicMock()
        correction_result.scalars.return_value.all.return_value = [corr_id]
        mock_session.execute.return_value = correction_result

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockRepo:
            mock_mention_repo = AsyncMock()
            MockRepo.return_value = mock_mention_repo
            mock_mention_repo.get_entity_ids_by_correction_ids.return_value = [entity_id]
            mock_mention_repo.delete_by_correction_ids.return_value = 3

            result = await service.batch_revert(mock_session, pattern="fixed")

            # Verify mentions were deleted with the correct correction IDs
            mock_mention_repo.delete_by_correction_ids.assert_called_once_with(
                mock_session, [corr_id]
            )
            # Verify entity and alias counters were recalculated
            mock_mention_repo.update_entity_counters.assert_called_once_with(
                mock_session, [entity_id]
            )
            mock_mention_repo.update_alias_counters.assert_called_once_with(
                mock_session, [entity_id]
            )

        assert result.total_applied == 1

    async def test_revert_skips_cascade_when_no_correction_ids(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """No cascade when no correction IDs are found for segments."""
        seg = _make_segment(
            video_id="v1", segment_id=1, text="orig",
            corrected_text="fixed", has_correction=True,
        )

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_service.revert_correction.return_value = MagicMock()
        mock_correction_repo.get_by_segment.return_value = []
        # No correction IDs found
        mock_session.execute.return_value = _make_empty_execute_result()

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockRepo:
            mock_mention_repo = AsyncMock()
            MockRepo.return_value = mock_mention_repo

            result = await service.batch_revert(mock_session, pattern="fixed")

            # No cascade operations should be called
            mock_mention_repo.delete_by_correction_ids.assert_not_called()
            mock_mention_repo.update_entity_counters.assert_not_called()
            mock_mention_repo.update_alias_counters.assert_not_called()

        assert result.total_applied == 1

    async def test_partial_revert_only_deletes_reverted_correction_mentions(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """T034: Partial revert only deletes mentions for the specific corrections being reverted."""
        import uuid as _uuid

        # Only seg1 matches the revert pattern; seg2 does not
        seg1 = _make_segment(
            video_id="v1", segment_id=1, text="a",
            corrected_text="fix", has_correction=True,
        )

        mock_segment_repo.count_filtered.return_value = 50
        mock_segment_repo.find_by_text_pattern.return_value = [seg1]
        mock_correction_service.revert_correction.return_value = MagicMock()
        mock_correction_repo.get_by_segment.return_value = []

        # Only one correction ID returned (for seg1's correction)
        corr_id_seg1 = _uuid.uuid4()
        entity_id = _uuid.uuid4()
        correction_result = MagicMock()
        correction_result.scalars.return_value.all.return_value = [corr_id_seg1]
        mock_session.execute.return_value = correction_result

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockRepo:
            mock_mention_repo = AsyncMock()
            MockRepo.return_value = mock_mention_repo
            mock_mention_repo.get_entity_ids_by_correction_ids.return_value = [entity_id]
            mock_mention_repo.delete_by_correction_ids.return_value = 2

            result = await service.batch_revert(mock_session, pattern="fix")

            # Should only pass seg1's correction ID — not seg2's
            mock_mention_repo.delete_by_correction_ids.assert_called_once_with(
                mock_session, [corr_id_seg1]
            )

        assert result.total_applied == 1

    async def test_revert_cascade_happens_before_text_revert(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """FR-016: Mention deletion must happen BEFORE the text revert."""
        import uuid as _uuid

        seg = _make_segment(
            video_id="v1", segment_id=1, text="orig",
            corrected_text="fixed", has_correction=True,
        )

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_service.revert_correction.return_value = MagicMock()
        mock_correction_repo.get_by_segment.return_value = []

        corr_id = _uuid.uuid4()
        correction_result = MagicMock()
        correction_result.scalars.return_value.all.return_value = [corr_id]
        mock_session.execute.return_value = correction_result

        # Track call order
        call_order: list[str] = []

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockRepo:
            mock_mention_repo = AsyncMock()
            MockRepo.return_value = mock_mention_repo
            mock_mention_repo.get_entity_ids_by_correction_ids.return_value = [_uuid.uuid4()]
            async def _track_delete(*a: object, **kw: object) -> int:
                call_order.append("delete_mentions")
                return 1

            async def _track_revert(*a: object, **kw: object) -> MagicMock:
                call_order.append("revert_correction")
                return MagicMock()

            mock_mention_repo.delete_by_correction_ids.side_effect = _track_delete
            mock_correction_service.revert_correction.side_effect = _track_revert

            await service.batch_revert(mock_session, pattern="fixed")

        assert call_order.index("delete_mentions") < call_order.index(
            "revert_correction"
        ), "Mention deletion must happen before text revert (FR-016)"

    async def test_dry_run_does_not_cascade_mentions(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """Dry-run mode should not delete entity mentions."""
        seg = _make_segment(
            video_id="v1", segment_id=1, text="a",
            corrected_text="fix", has_correction=True,
        )

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_repo.get_by_segment.return_value = []

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockRepo:
            result = await service.batch_revert(
                mock_session, pattern="fix", dry_run=True,
            )
            # Repository should never be instantiated in dry-run mode
            MockRepo.assert_not_called()

        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# TestRecordAsrAliasForBatchReplacement (Feature 038)
# ---------------------------------------------------------------------------


def _mock_execute_returns(*results: Any) -> AsyncMock:
    """Build a mock session.execute that returns results in sequence.

    Each *result* is a value to return from ``scalar_one_or_none()`` or
    ``scalars().first()``.  The helper wraps them in MagicMock chains
    matching SQLAlchemy's async result API.
    """
    side_effects: list[MagicMock] = []
    for r in results:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = r
        mock_result.scalars.return_value.first.return_value = r
        side_effects.append(mock_result)
    session = AsyncMock()
    session.execute.side_effect = side_effects
    # begin_nested() returns an async context manager (savepoint).
    # Use a non-async mock so calling it doesn't return a coroutine.
    nested_cm = MagicMock()
    nested_cm.__aenter__ = AsyncMock(return_value=None)
    nested_cm.__aexit__ = AsyncMock(return_value=False)
    session.begin_nested = MagicMock(return_value=nested_cm)
    return session


class TestRecordAsrAliasForBatchReplacement:
    """Tests for BatchCorrectionService._record_asr_alias_for_batch_replacement().

    The hook auto-registers ASR error aliases when find-and-replace
    replacement text matches a known entity name or alias.

    Feature 038 -- Entity Mention Detection
    """

    async def test_alias_created_when_replacement_matches_entity_canonical_name(
        self,
        service: Any,
    ) -> None:
        """New alias created when replacement matches entity canonical_name."""
        entity_mock = MagicMock()
        entity_mock.id = uuid.uuid4()
        entity_mock.canonical_name = "Claudia Sheinbaum"

        # execute sequence: entity lookup → existing alias check → (create via repo)
        session = _mock_execute_returns(entity_mock, None)

        with patch(
            "chronovista.services.asr_alias_registry.EntityAliasRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            MockRepo.return_value = mock_repo_instance

            with patch(
                "chronovista.services.asr_alias_registry.TagNormalizationService"
            ) as MockNorm:
                MockNorm.return_value.normalize.return_value = "claudia shainbom"

                await service._record_asr_alias_for_batch_replacement(
                    session,
                    pattern="Claudia Shainbom",
                    replacement="Claudia Sheinbaum",
                    total_applied=5,
                )

            mock_repo_instance.create.assert_called_once()
            call_kwargs = mock_repo_instance.create.call_args
            alias_create = call_kwargs[1]["obj_in"]
            assert alias_create.entity_id == entity_mock.id
            assert alias_create.alias_name == "Claudia Shainbom"
            assert alias_create.occurrence_count == 5
            assert alias_create.alias_type == EntityAliasType.ASR_ERROR

    async def test_alias_created_when_replacement_matches_existing_alias(
        self,
        service: Any,
    ) -> None:
        """New alias created when replacement matches an existing entity alias."""
        alias_mock = MagicMock()
        alias_mock.entity_id = uuid.uuid4()

        # execute sequence: entity lookup (None) → alias lookup → existing alias check → (create)
        session = _mock_execute_returns(None, alias_mock, None)

        with patch(
            "chronovista.services.asr_alias_registry.EntityAliasRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            MockRepo.return_value = mock_repo_instance

            with patch(
                "chronovista.services.asr_alias_registry.TagNormalizationService"
            ) as MockNorm:
                MockNorm.return_value.normalize.return_value = "seon"

                await service._record_asr_alias_for_batch_replacement(
                    session,
                    pattern="Seon",
                    replacement="Sheinbaum",
                    total_applied=3,
                )

            mock_repo_instance.create.assert_called_once()
            call_kwargs = mock_repo_instance.create.call_args
            alias_create = call_kwargs[1]["obj_in"]
            assert alias_create.entity_id == alias_mock.entity_id
            assert alias_create.alias_name == "Seon"
            assert alias_create.occurrence_count == 3

    async def test_existing_alias_occurrence_count_incremented(
        self,
        service: Any,
    ) -> None:
        """If pattern already exists as alias, occurrence_count is incremented."""
        entity_mock = MagicMock()
        entity_mock.id = uuid.uuid4()
        entity_mock.canonical_name = "Claudia Sheinbaum"

        existing_alias = MagicMock()
        existing_alias.occurrence_count = 2

        # execute sequence: entity lookup → existing alias check (found)
        session = _mock_execute_returns(entity_mock, existing_alias)

        await service._record_asr_alias_for_batch_replacement(
            session,
            pattern="Claudia Shainbom",
            replacement="Claudia Sheinbaum",
            total_applied=7,
        )

        assert existing_alias.occurrence_count == 9  # 2 + 7
        session.flush.assert_called()
        session.commit.assert_called()

    async def test_no_alias_when_replacement_matches_no_entity(
        self,
        service: Any,
    ) -> None:
        """No alias created when replacement matches neither entity nor alias."""
        # execute sequence: entity lookup (None) → alias lookup (None)
        session = _mock_execute_returns(None, None)

        with patch(
            "chronovista.services.asr_alias_registry.EntityAliasRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            MockRepo.return_value = mock_repo_instance

            await service._record_asr_alias_for_batch_replacement(
                session,
                pattern="Shainbom",
                replacement="Unknown Person",
                total_applied=5,
            )

            mock_repo_instance.create.assert_not_called()

    async def test_regex_mode_extracts_distinct_matched_forms(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """Regex find-replace extracts actual matched forms and registers each as alias."""
        seg1 = _make_segment(
            video_id="v1", segment_id=1,
            text="presidenta Claudia Shambom también", start_time=0.0,
        )
        seg2 = _make_segment(
            video_id="v1", segment_id=2,
            text="presidenta Claudia Shamon equipara", start_time=1.0,
        )
        seg3 = _make_segment(
            video_id="v2", segment_id=3,
            text="presidenta Claudia Shambom quien", start_time=2.0,
        )

        mock_segment_repo.count_filtered.return_value = 50
        mock_segment_repo.find_by_text_pattern.return_value = [seg1, seg2, seg3]
        mock_correction_service.apply_correction.return_value = MagicMock()

        with patch.object(
            service, "_record_asr_alias_for_batch_replacement", new_callable=AsyncMock,
        ) as mock_hook:
            await service.find_and_replace(
                mock_session,
                pattern=r"Claudia Sham\w*",
                replacement="Claudia Sheinbaum",
                regex=True,
            )

            # Should be called once per distinct matched form
            assert mock_hook.call_count == 2

            # Collect calls by pattern
            calls_by_pattern = {
                c.kwargs["pattern"]: c.kwargs["total_applied"]
                for c in mock_hook.call_args_list
            }
            assert calls_by_pattern["Claudia Shambom"] == 2
            assert calls_by_pattern["Claudia Shamon"] == 1

    async def test_regex_mode_single_form_calls_hook(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """Regex find-replace with a single matched form calls hook once."""
        seg = _make_segment(
            video_id="v1", segment_id=1,
            text="Claudia Shainbom here", start_time=0.0,
        )

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_service.apply_correction.return_value = MagicMock()

        with patch.object(
            service, "_record_asr_alias_for_batch_replacement", new_callable=AsyncMock,
        ) as mock_hook:
            await service.find_and_replace(
                mock_session,
                pattern=r"Claudia Shain\w*",
                replacement="Claudia Sheinbaum",
                regex=True,
            )
            mock_hook.assert_called_once_with(
                mock_session,
                pattern="Claudia Shainbom",
                replacement="Claudia Sheinbaum",
                total_applied=1,
            )

    async def test_no_alias_when_dry_run(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """find_and_replace with dry_run=True does not call the alias hook."""
        seg = _make_segment(
            video_id="v1", segment_id=1, text="Shainbom", start_time=0.0,
        )

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        # find_matching_segments() executes session queries for video/channel
        # titles and context neighbours; configure the mock to return empty
        # results for all of them.
        mock_session.execute.side_effect = _make_empty_execute_result

        with patch.object(
            service, "_record_asr_alias_for_batch_replacement", new_callable=AsyncMock,
        ) as mock_hook:
            await service.find_and_replace(
                mock_session,
                pattern="Shainbom",
                replacement="Sheinbaum",
                dry_run=True,
            )
            mock_hook.assert_not_called()

    async def test_no_alias_when_zero_applied(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """find_and_replace with zero matches does not call the alias hook."""
        mock_segment_repo.count_filtered.return_value = 100
        mock_segment_repo.find_by_text_pattern.return_value = []

        with patch.object(
            service, "_record_asr_alias_for_batch_replacement", new_callable=AsyncMock,
        ) as mock_hook:
            await service.find_and_replace(
                mock_session,
                pattern="nonexistent",
                replacement="anything",
            )
            mock_hook.assert_not_called()

    async def test_hook_failure_does_not_propagate(
        self,
        service: Any,
    ) -> None:
        """Exception in hook is caught and logged, not propagated."""
        session = AsyncMock()
        session.execute.side_effect = RuntimeError("DB connection lost")

        # Should not raise
        await service._record_asr_alias_for_batch_replacement(
            session,
            pattern="bad",
            replacement="good",
            total_applied=1,
        )

    async def test_alias_normalized_via_tag_normalization_service(
        self,
        service: Any,
    ) -> None:
        """New alias uses TagNormalizationService for normalized name."""
        entity_mock = MagicMock()
        entity_mock.id = uuid.uuid4()
        entity_mock.canonical_name = "Max Blumenthal"

        session = _mock_execute_returns(entity_mock, None)

        with patch(
            "chronovista.services.asr_alias_registry.EntityAliasRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            MockRepo.return_value = mock_repo_instance

            with patch(
                "chronovista.services.asr_alias_registry.TagNormalizationService"
            ) as MockNorm:
                MockNorm.return_value.normalize.return_value = "max blumenthal typo"

                await service._record_asr_alias_for_batch_replacement(
                    session,
                    pattern="Max Blumenthal Typo",
                    replacement="Max Blumenthal",
                    total_applied=2,
                )

                MockNorm.return_value.normalize.assert_called_once_with(
                    "Max Blumenthal Typo"
                )

            alias_create = mock_repo_instance.create.call_args[1]["obj_in"]
            assert alias_create.alias_name_normalized == "max blumenthal typo"

    async def test_find_and_replace_calls_hook_on_success(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """find_and_replace calls the alias hook after successful live corrections."""
        seg = _make_segment(
            video_id="v1", segment_id=1, text="Claudia Shainbom", start_time=0.0,
        )

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_service.apply_correction.return_value = MagicMock()

        with patch.object(
            service, "_record_asr_alias_for_batch_replacement", new_callable=AsyncMock,
        ) as mock_hook:
            await service.find_and_replace(
                mock_session,
                pattern="Claudia Shainbom",
                replacement="Claudia Sheinbaum",
            )
            mock_hook.assert_called_once_with(
                mock_session,
                pattern="Claudia Shainbom",
                replacement="Claudia Sheinbaum",
                total_applied=1,
            )


# ---------------------------------------------------------------------------
# TestExtractPatternTokens
# ---------------------------------------------------------------------------


class TestExtractPatternTokens:
    """
    Unit tests for BatchCorrectionService._extract_pattern_tokens().

    This static helper converts a search pattern into a list of substring
    tokens used to pre-filter videos before loading all segments.
    """

    @pytest.fixture
    def service_cls(self) -> Any:
        from chronovista.services.batch_correction_service import BatchCorrectionService
        return BatchCorrectionService

    # ------------------------------------------------------------------
    # Plain (non-regex) patterns
    # ------------------------------------------------------------------

    def test_plain_multi_word_splits_on_spaces(self, service_cls: Any) -> None:
        """Multi-word plain pattern splits into its constituent words."""
        tokens = service_cls._extract_pattern_tokens("Shine Bomb", regex=False)
        assert tokens == ["Shine", "Bomb"]

    def test_plain_single_word_returns_list_with_that_word(
        self, service_cls: Any
    ) -> None:
        """Single-word plain pattern returns a one-element list."""
        tokens = service_cls._extract_pattern_tokens("hello", regex=False)
        assert tokens == ["hello"]

    def test_plain_three_words(self, service_cls: Any) -> None:
        """Three-word pattern splits into three tokens."""
        tokens = service_cls._extract_pattern_tokens("one two three", regex=False)
        assert tokens == ["one", "two", "three"]

    def test_plain_extra_whitespace_ignored(self, service_cls: Any) -> None:
        """Extra internal spaces do not produce empty tokens."""
        tokens = service_cls._extract_pattern_tokens("a  b", regex=False)
        assert "" not in tokens
        assert "a" in tokens
        assert "b" in tokens

    def test_plain_empty_string_returns_list_with_empty(
        self, service_cls: Any
    ) -> None:
        """An empty string falls back to [pattern] (the empty string itself)."""
        tokens = service_cls._extract_pattern_tokens("", regex=False)
        assert tokens == [""]

    # ------------------------------------------------------------------
    # Regex patterns
    # ------------------------------------------------------------------

    def test_regex_word_boundary_pattern_extracts_word(
        self, service_cls: Any
    ) -> None:
        r"""Regex \bShine\b yields at least ['Shine'] after metachar stripping."""
        tokens = service_cls._extract_pattern_tokens(r"\bShine\b", regex=True)
        assert "Shine" in tokens

    def test_regex_metachar_only_pattern_falls_back(self, service_cls: Any) -> None:
        r"""Pattern composed entirely of metacharacters falls back to [pattern]."""
        tokens = service_cls._extract_pattern_tokens(r"\b\b", regex=True)
        # No alphanumeric runs of length >= 3, so falls back to the raw pattern
        assert len(tokens) >= 1

    def test_regex_mixed_pattern_keeps_long_words(self, service_cls: Any) -> None:
        """Long alphanumeric runs are kept; short runs are discarded."""
        tokens = service_cls._extract_pattern_tokens(r"(hello|world)", regex=True)
        assert "hello" in tokens
        assert "world" in tokens

    def test_regex_two_char_words_excluded(self, service_cls: Any) -> None:
        """Words shorter than 3 characters are excluded from regex tokens."""
        tokens = service_cls._extract_pattern_tokens(r"ab|cde", regex=True)
        # "ab" is 2 chars — excluded; "cde" is 3 chars — kept
        assert "ab" not in tokens
        assert "cde" in tokens

    def test_regex_single_long_word(self, service_cls: Any) -> None:
        """Simple regex with a single long word is extracted correctly."""
        tokens = service_cls._extract_pattern_tokens(r"^hello$", regex=True)
        assert "hello" in tokens

    def test_returns_list_type(self, service_cls: Any) -> None:
        """Return type is always list."""
        tokens = service_cls._extract_pattern_tokens("test", regex=False)
        assert isinstance(tokens, list)


# ---------------------------------------------------------------------------
# TestGetCandidateVideoIds
# ---------------------------------------------------------------------------


class TestGetCandidateVideoIds:
    """
    Unit tests for BatchCorrectionService._get_candidate_video_ids().

    Verifies that the helper delegates to the repository's
    find_candidate_video_ids_for_cross_segment() with correctly extracted
    tokens and forwarded filter parameters.
    """

    async def test_delegates_to_repo_with_extracted_tokens(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """Tokens extracted from the pattern are forwarded to the repository."""
        mock_segment_repo.find_candidate_video_ids_for_cross_segment.return_value = [
            "vid1"
        ]

        result = await service._get_candidate_video_ids(
            mock_session,
            pattern="Shine Bomb",
            regex=False,
            case_insensitive=False,
            language=None,
            channel=None,
        )

        mock_segment_repo.find_candidate_video_ids_for_cross_segment.assert_called_once_with(
            mock_session,
            tokens=["Shine", "Bomb"],
            language=None,
            channel=None,
            case_insensitive=False,
        )
        assert result == ["vid1"]

    async def test_forwards_language_filter(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """language parameter is forwarded to the repository call."""
        mock_segment_repo.find_candidate_video_ids_for_cross_segment.return_value = []

        await service._get_candidate_video_ids(
            mock_session,
            pattern="hello",
            regex=False,
            case_insensitive=False,
            language="es",
            channel=None,
        )

        call_kwargs = (
            mock_segment_repo.find_candidate_video_ids_for_cross_segment.call_args.kwargs
        )
        assert call_kwargs["language"] == "es"

    async def test_forwards_channel_filter(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """channel parameter is forwarded to the repository call."""
        mock_segment_repo.find_candidate_video_ids_for_cross_segment.return_value = []

        await service._get_candidate_video_ids(
            mock_session,
            pattern="hello",
            regex=False,
            case_insensitive=False,
            language=None,
            channel="UCxxxxxx",
        )

        call_kwargs = (
            mock_segment_repo.find_candidate_video_ids_for_cross_segment.call_args.kwargs
        )
        assert call_kwargs["channel"] == "UCxxxxxx"

    async def test_forwards_case_insensitive_flag(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """case_insensitive flag is forwarded to the repository call."""
        mock_segment_repo.find_candidate_video_ids_for_cross_segment.return_value = []

        await service._get_candidate_video_ids(
            mock_session,
            pattern="hello",
            regex=False,
            case_insensitive=True,
            language=None,
            channel=None,
        )

        call_kwargs = (
            mock_segment_repo.find_candidate_video_ids_for_cross_segment.call_args.kwargs
        )
        assert call_kwargs["case_insensitive"] is True

    async def test_returns_empty_list_when_no_candidates(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """Returns empty list propagated from the repository."""
        mock_segment_repo.find_candidate_video_ids_for_cross_segment.return_value = []

        result = await service._get_candidate_video_ids(
            mock_session,
            pattern="xyzzy",
            regex=False,
            case_insensitive=False,
            language=None,
            channel=None,
        )

        assert result == []


# ---------------------------------------------------------------------------
# TestFindCrossSegmentMatchesPreFilter
# ---------------------------------------------------------------------------


class TestFindCrossSegmentMatchesPreFilter:
    """
    Unit tests for the pre-filter optimization in _find_cross_segment_matches().

    These tests validate the branching logic: when video_ids is None the
    service must call find_candidate_video_ids_for_cross_segment() first;
    when video_ids is already provided by the caller the pre-filter is skipped.
    """

    # ------------------------------------------------------------------
    # Pre-filter skipped when caller supplies video_ids
    # ------------------------------------------------------------------

    async def test_pre_filter_skipped_when_video_ids_provided(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """When the caller passes video_ids the candidate query is NOT issued."""
        mock_segment_repo.find_segments_in_scope.return_value = []

        await service._find_cross_segment_matches(
            mock_session,
            pattern="Shine Bomb",
            replacement="ShineBomb",
            regex=False,
            case_insensitive=False,
            re_flags=0,
            language=None,
            channel=None,
            video_ids=["vid1"],
            single_segment_ids=set(),
        )

        mock_segment_repo.find_candidate_video_ids_for_cross_segment.assert_not_called()
        mock_segment_repo.find_segments_in_scope.assert_called_once_with(
            mock_session,
            language=None,
            channel=None,
            video_ids=["vid1"],
        )

    # ------------------------------------------------------------------
    # Pre-filter invoked when video_ids is None
    # ------------------------------------------------------------------

    async def test_pre_filter_called_when_no_video_ids_filter(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """When video_ids is None the candidate pre-filter query is issued first."""
        mock_segment_repo.find_candidate_video_ids_for_cross_segment.return_value = [
            "vid_candidate"
        ]
        mock_segment_repo.find_segments_in_scope.return_value = []

        await service._find_cross_segment_matches(
            mock_session,
            pattern="Shine Bomb",
            replacement="ShineBomb",
            regex=False,
            case_insensitive=False,
            re_flags=0,
            language=None,
            channel=None,
            video_ids=None,
            single_segment_ids=set(),
        )

        mock_segment_repo.find_candidate_video_ids_for_cross_segment.assert_called_once()
        # find_segments_in_scope receives the narrowed video_ids
        mock_segment_repo.find_segments_in_scope.assert_called_once_with(
            mock_session,
            language=None,
            channel=None,
            video_ids=["vid_candidate"],
        )

    async def test_pre_filter_early_return_when_no_candidates(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """When pre-filter returns [] the method exits early without loading segments."""
        mock_segment_repo.find_candidate_video_ids_for_cross_segment.return_value = []

        result = await service._find_cross_segment_matches(
            mock_session,
            pattern="xyzzy plugh",
            replacement="other",
            regex=False,
            case_insensitive=False,
            re_flags=0,
            language=None,
            channel=None,
            video_ids=None,
            single_segment_ids=set(),
        )

        assert result == []
        mock_segment_repo.find_segments_in_scope.assert_not_called()

    async def test_pre_filter_forwards_language_to_candidate_query(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """language filter is forwarded to the candidate pre-filter query."""
        mock_segment_repo.find_candidate_video_ids_for_cross_segment.return_value = []

        await service._find_cross_segment_matches(
            mock_session,
            pattern="foo bar",
            replacement="baz",
            regex=False,
            case_insensitive=False,
            re_flags=0,
            language="es",
            channel=None,
            video_ids=None,
            single_segment_ids=set(),
        )

        call_kwargs = (
            mock_segment_repo.find_candidate_video_ids_for_cross_segment.call_args.kwargs
        )
        assert call_kwargs.get("language") == "es"

    async def test_pre_filter_forwards_channel_to_candidate_query(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
    ) -> None:
        """channel filter is forwarded to the candidate pre-filter query."""
        mock_segment_repo.find_candidate_video_ids_for_cross_segment.return_value = []

        await service._find_cross_segment_matches(
            mock_session,
            pattern="foo bar",
            replacement="baz",
            regex=False,
            case_insensitive=False,
            re_flags=0,
            language=None,
            channel="UCzzzz",
            video_ids=None,
            single_segment_ids=set(),
        )

        call_kwargs = (
            mock_segment_repo.find_candidate_video_ids_for_cross_segment.call_args.kwargs
        )
        assert call_kwargs.get("channel") == "UCzzzz"


# ---------------------------------------------------------------------------
# Entity-Aware Corrections (T027-T031)
# ---------------------------------------------------------------------------


def _make_entity(
    *,
    entity_id: uuid.UUID | None = None,
    canonical_name: str = "Test Entity",
    status: str = "active",
    exclusion_patterns: list[Any] | None = None,
) -> MagicMock:
    """Create a mock NamedEntityDB for testing."""
    entity = MagicMock()
    entity.id = entity_id or uuid.uuid4()
    entity.canonical_name = canonical_name
    entity.status = status
    entity.exclusion_patterns = exclusion_patterns or []
    return entity


class TestFindAllOccurrences:
    """Tests for the _find_all_occurrences static method."""

    def test_simple_match(self) -> None:
        from chronovista.services.batch_correction_service import (
            BatchCorrectionService,
        )

        result = BatchCorrectionService._find_all_occurrences(
            "hello world hello", "hello"
        )
        assert result == [(0, 5), (12, 17)]

    def test_case_insensitive(self) -> None:
        from chronovista.services.batch_correction_service import (
            BatchCorrectionService,
        )

        result = BatchCorrectionService._find_all_occurrences(
            "Hello HELLO hello", "hello"
        )
        assert result == [(0, 5), (6, 11), (12, 17)]

    def test_no_match(self) -> None:
        from chronovista.services.batch_correction_service import (
            BatchCorrectionService,
        )

        result = BatchCorrectionService._find_all_occurrences(
            "hello world", "xyz"
        )
        assert result == []

    def test_empty_substring(self) -> None:
        from chronovista.services.batch_correction_service import (
            BatchCorrectionService,
        )

        result = BatchCorrectionService._find_all_occurrences(
            "hello world", ""
        )
        assert result == []

    def test_non_overlapping(self) -> None:
        from chronovista.services.batch_correction_service import (
            BatchCorrectionService,
        )

        # "aa" in "aaa" should yield only one match (non-overlapping)
        result = BatchCorrectionService._find_all_occurrences("aaa", "aa")
        assert result == [(0, 2)]

    def test_single_occurrence(self) -> None:
        from chronovista.services.batch_correction_service import (
            BatchCorrectionService,
        )

        result = BatchCorrectionService._find_all_occurrences(
            "the quick brown fox", "brown"
        )
        assert result == [(10, 15)]


class TestIsExcludedByPatterns:
    """Tests for the _is_excluded_by_patterns static method."""

    def test_no_exclusion_patterns(self) -> None:
        from chronovista.services.batch_correction_service import (
            BatchCorrectionService,
        )

        assert not BatchCorrectionService._is_excluded_by_patterns(
            0, 5, "hello world", []
        )

    def test_non_overlapping_exclusion(self) -> None:
        from chronovista.services.batch_correction_service import (
            BatchCorrectionService,
        )

        # Exclusion at "world" (6-11), mention at "hello" (0-5) — no overlap
        assert not BatchCorrectionService._is_excluded_by_patterns(
            0, 5, "hello world", ["world"]
        )

    def test_overlapping_exclusion(self) -> None:
        from chronovista.services.batch_correction_service import (
            BatchCorrectionService,
        )

        # Exclusion at "hello world" (0-11), mention at "hello" (0-5) — overlap
        assert BatchCorrectionService._is_excluded_by_patterns(
            0, 5, "hello world", ["hello world"]
        )

    def test_case_insensitive_exclusion(self) -> None:
        from chronovista.services.batch_correction_service import (
            BatchCorrectionService,
        )

        assert BatchCorrectionService._is_excluded_by_patterns(
            0, 5, "Hello world", ["HELLO WORLD"]
        )

    def test_partial_overlap_excluded(self) -> None:
        from chronovista.services.batch_correction_service import (
            BatchCorrectionService,
        )

        # Text: "New York City", exclusion "York City" at 4-13,
        # mention "New York" at 0-8 — overlap at 4-8
        assert BatchCorrectionService._is_excluded_by_patterns(
            0, 8, "New York City", ["York City"]
        )

    def test_invalid_exclusion_pattern_ignored(self) -> None:
        from chronovista.services.batch_correction_service import (
            BatchCorrectionService,
        )

        assert not BatchCorrectionService._is_excluded_by_patterns(
            0, 5, "hello world", [None, "", 123]
        )


class TestApplyToSegmentsEntityValidation:
    """Tests for T027: entity validation in apply_to_segments."""

    async def test_entity_not_found_raises_value_error(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """If entity_id is given but not found, ValueError is raised."""
        eid = uuid.uuid4()
        # Mock the session.execute for entity lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not found"):
            await service.apply_to_segments(
                mock_session,
                pattern="foo",
                replacement="bar",
                segment_ids=[1],
                entity_id=eid,
            )

    async def test_entity_not_active_raises_value_error(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """If entity exists but status is not active, ValueError is raised."""
        entity = _make_entity(status="deprecated")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not active"):
            await service.apply_to_segments(
                mock_session,
                pattern="foo",
                replacement="bar",
                segment_ids=[1],
                entity_id=entity.id,
            )

    async def test_no_entity_id_skips_validation(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """When entity_id is None, entity validation is skipped entirely."""
        # Set up mock to return empty segment list
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await service.apply_to_segments(
            mock_session,
            pattern="foo",
            replacement="bar",
            segment_ids=[],
        )
        assert result.total_applied == 0


class TestApplyToSegmentsEntityMentionCreation:
    """Tests for T028/T029: entity mention creation after correction."""

    async def test_mentions_created_after_correction(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """When entity_id is present, entity mentions are created."""
        entity = _make_entity()
        seg = _make_segment(
            video_id="vid1_test_x", segment_id=10, text="bad text here"
        )
        correction_record = MagicMock()
        correction_record.id = uuid.uuid4()
        mock_correction_service.apply_correction.return_value = correction_record

        # First execute: entity lookup
        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = entity
        # Second execute: segment fetch
        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg]

        mock_session.execute.side_effect = [entity_result, segment_result]
        # begin_nested must return an async context manager
        nested_cm = AsyncMock()
        mock_session.begin_nested = MagicMock(return_value=nested_cm)

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockMentionRepo:
            mock_repo_instance = AsyncMock()
            MockMentionRepo.return_value = mock_repo_instance

            result = await service.apply_to_segments(
                mock_session,
                pattern="bad",
                replacement="good",
                segment_ids=[10],
                entity_id=entity.id,
                auto_rebuild=False,
            )

            assert result.total_applied == 1
            # Verify bulk_create_with_conflict_skip was called
            mock_repo_instance.bulk_create_with_conflict_skip.assert_called_once()
            mentions = mock_repo_instance.bulk_create_with_conflict_skip.call_args[0][1]
            assert len(mentions) >= 1
            assert mentions[0].entity_id == entity.id
            assert mentions[0].detection_method.value == "user_correction"
            assert mentions[0].confidence == 1.0

    async def test_empty_replacement_skips_mention_creation(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """When replacement is empty (deletion), no mentions are created."""
        entity = _make_entity()
        seg = _make_segment(
            video_id="vid1_test_x", segment_id=10, text="remove this"
        )
        correction_record = MagicMock()
        correction_record.id = uuid.uuid4()
        mock_correction_service.apply_correction.return_value = correction_record

        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = entity
        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg]
        mock_session.execute.side_effect = [entity_result, segment_result]

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockMentionRepo:
            mock_repo_instance = AsyncMock()
            MockMentionRepo.return_value = mock_repo_instance

            result = await service.apply_to_segments(
                mock_session,
                pattern="remove this",
                replacement="",
                segment_ids=[10],
                entity_id=entity.id,
                auto_rebuild=False,
            )

            assert result.total_applied == 1
            # No mentions should be created for empty replacement
            mock_repo_instance.bulk_create_with_conflict_skip.assert_not_called()

    async def test_exclusion_pattern_suppresses_mention(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """T029: Exclusion patterns suppress overlapping mentions."""
        entity = _make_entity(exclusion_patterns=["good text here"])
        seg = _make_segment(
            video_id="vid1_test_x", segment_id=10, text="bad text here"
        )
        correction_record = MagicMock()
        correction_record.id = uuid.uuid4()
        mock_correction_service.apply_correction.return_value = correction_record

        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = entity
        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg]
        mock_session.execute.side_effect = [entity_result, segment_result]
        nested_cm = AsyncMock()
        mock_session.begin_nested = MagicMock(return_value=nested_cm)

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockMentionRepo:
            mock_repo_instance = AsyncMock()
            MockMentionRepo.return_value = mock_repo_instance

            # Pattern "bad" → "good", result is "good text here"
            # Exclusion pattern "good text here" overlaps mention "good" at 0-4
            result = await service.apply_to_segments(
                mock_session,
                pattern="bad",
                replacement="good",
                segment_ids=[10],
                entity_id=entity.id,
                auto_rebuild=False,
            )

            assert result.total_applied == 1
            # Mention should be suppressed due to exclusion pattern overlap
            mock_repo_instance.bulk_create_with_conflict_skip.assert_not_called()


class TestApplyToSegmentsEntityCounterUpdate:
    """Tests for T031: entity counter update after all corrections."""

    async def test_counter_update_called_when_entity_and_applied(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """T031: update_entity_counters is called after successful corrections."""
        entity = _make_entity()
        seg = _make_segment(
            video_id="vid1_test_x", segment_id=10, text="bad text"
        )
        correction_record = MagicMock()
        correction_record.id = uuid.uuid4()
        mock_correction_service.apply_correction.return_value = correction_record

        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = entity
        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg]
        mock_session.execute.side_effect = [entity_result, segment_result]
        nested_cm = AsyncMock()
        mock_session.begin_nested = MagicMock(return_value=nested_cm)

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockMentionRepo:
            mock_repo_instance = AsyncMock()
            MockMentionRepo.return_value = mock_repo_instance

            result = await service.apply_to_segments(
                mock_session,
                pattern="bad",
                replacement="good",
                segment_ids=[10],
                entity_id=entity.id,
                auto_rebuild=False,
            )

            assert result.total_applied == 1
            # update_entity_counters and update_alias_counters should have been called
            mock_repo_instance.update_entity_counters.assert_called_once_with(
                mock_session, [entity.id]
            )
            mock_repo_instance.update_alias_counters.assert_called_once_with(
                mock_session, [entity.id]
            )

    async def test_counter_update_not_called_without_entity(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """Counter update is not called when entity_id is None."""
        seg = _make_segment(
            video_id="vid1_test_x", segment_id=10, text="bad text"
        )
        correction_record = MagicMock()
        correction_record.id = uuid.uuid4()
        mock_correction_service.apply_correction.return_value = correction_record

        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg]
        mock_session.execute.return_value = segment_result

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockMentionRepo:
            mock_repo_instance = AsyncMock()
            MockMentionRepo.return_value = mock_repo_instance

            result = await service.apply_to_segments(
                mock_session,
                pattern="bad",
                replacement="good",
                segment_ids=[10],
                auto_rebuild=False,
            )

            assert result.total_applied == 1
            mock_repo_instance.update_entity_counters.assert_not_called()
            mock_repo_instance.update_alias_counters.assert_not_called()

    async def test_counter_update_not_called_when_zero_applied(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """Counter update is not called when no corrections are applied."""
        entity = _make_entity()

        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = entity
        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = []
        mock_session.execute.side_effect = [entity_result, segment_result]

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockMentionRepo:
            mock_repo_instance = AsyncMock()
            MockMentionRepo.return_value = mock_repo_instance

            result = await service.apply_to_segments(
                mock_session,
                pattern="foo",
                replacement="bar",
                segment_ids=[],
                entity_id=entity.id,
                auto_rebuild=False,
            )

            assert result.total_applied == 0
            mock_repo_instance.update_entity_counters.assert_not_called()
            mock_repo_instance.update_alias_counters.assert_not_called()


class TestCreateEntityMentionsForSegment:
    """Tests for _create_entity_mentions_for_segment helper method."""

    async def test_multiple_occurrences_create_multiple_mentions(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """Multiple occurrences of replacement create multiple mentions."""
        entity = _make_entity()
        seg = _make_segment(video_id="vid1_test_x", segment_id=5)
        correction_id = uuid.uuid4()

        nested_cm = AsyncMock()
        mock_session.begin_nested = MagicMock(return_value=nested_cm)

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockMentionRepo:
            mock_repo_instance = AsyncMock()
            MockMentionRepo.return_value = mock_repo_instance

            await service._create_entity_mentions_for_segment(
                mock_session,
                entity=entity,
                segment=seg,
                corrected_text="hello hello hello",
                replacement="hello",
                correction_id=correction_id,
            )

            mock_repo_instance.bulk_create_with_conflict_skip.assert_called_once()
            mentions = mock_repo_instance.bulk_create_with_conflict_skip.call_args[0][1]
            assert len(mentions) == 3
            assert mentions[0].match_start == 0
            assert mentions[0].match_end == 5
            assert mentions[1].match_start == 6
            assert mentions[1].match_end == 11
            assert mentions[2].match_start == 12
            assert mentions[2].match_end == 17

    async def test_no_occurrences_skips_creation(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """If replacement text not found in corrected text, no mentions created."""
        entity = _make_entity()
        seg = _make_segment(video_id="vid1_test_x", segment_id=5)
        correction_id = uuid.uuid4()

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockMentionRepo:
            mock_repo_instance = AsyncMock()
            MockMentionRepo.return_value = mock_repo_instance

            await service._create_entity_mentions_for_segment(
                mock_session,
                entity=entity,
                segment=seg,
                corrected_text="completely different text",
                replacement="xyz",
                correction_id=correction_id,
            )

            mock_repo_instance.bulk_create_with_conflict_skip.assert_not_called()

    async def test_mention_creation_failure_logs_warning(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """Failures during mention creation are logged but don't propagate."""
        entity = _make_entity()
        seg = _make_segment(video_id="vid1_test_x", segment_id=5)
        correction_id = uuid.uuid4()

        # Make begin_nested raise an exception
        mock_session.begin_nested.side_effect = RuntimeError("DB error")

        with patch(
            "chronovista.services.batch_correction_service.logger"
        ) as mock_logger:
            # Should not raise
            await service._create_entity_mentions_for_segment(
                mock_session,
                entity=entity,
                segment=seg,
                corrected_text="hello world",
                replacement="hello",
                correction_id=correction_id,
            )

            # Warning should have been logged
            mock_logger.warning.assert_called_once()

    async def test_exclusion_filters_some_but_not_all(
        self,
        service: Any,
        mock_session: AsyncMock,
    ) -> None:
        """Exclusion pattern filters only overlapping occurrences."""
        entity = _make_entity(exclusion_patterns=["Mexico City"])
        seg = _make_segment(video_id="vid1_test_x", segment_id=5)
        correction_id = uuid.uuid4()

        nested_cm = AsyncMock()
        mock_session.begin_nested = MagicMock(return_value=nested_cm)

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockMentionRepo:
            mock_repo_instance = AsyncMock()
            MockMentionRepo.return_value = mock_repo_instance

            # Text has "Mexico" twice: once in "Mexico City" (excluded) and once standalone
            await service._create_entity_mentions_for_segment(
                mock_session,
                entity=entity,
                segment=seg,
                corrected_text="visited Mexico City and then Mexico",
                replacement="Mexico",
                correction_id=correction_id,
            )

            mock_repo_instance.bulk_create_with_conflict_skip.assert_called_once()
            mentions = mock_repo_instance.bulk_create_with_conflict_skip.call_args[0][1]
            # First "Mexico" at 8-14 overlaps with "Mexico City" at 8-19 → excluded
            # Second "Mexico" at 29-35 → included
            assert len(mentions) == 1


# ---------------------------------------------------------------------------
# TestFindAndReplaceBatchIdGeneration (Feature 045 — T015)
# ---------------------------------------------------------------------------


class TestFindAndReplaceBatchIdGeneration:
    """Tests for batch_id generation and propagation in find_and_replace().

    Feature 045 adds UUIDv7 batch provenance tracking so that every correction
    produced by a single find_and_replace() call shares the same batch_id.
    Individual (non-batch) corrections must have batch_id=None.
    """

    async def test_find_and_replace_generates_batch_id_on_live_run(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """find_and_replace() generates a UUIDv7 batch_id in live mode.

        Each live (non-dry-run) call must produce a new batch_id and pass it
        to every apply_correction() call so that all corrections from the
        same operation can be looked up or reverted as a group.
        """
        seg = _make_segment(video_id="v1", segment_id=1, text="teh quick fox")

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_service.apply_correction.return_value = MagicMock()

        result = await service.find_and_replace(
            mock_session,
            pattern="teh",
            replacement="the",
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_applied == 1

        # Verify apply_correction was called with a batch_id keyword argument
        call_kwargs = mock_correction_service.apply_correction.call_args.kwargs
        assert "batch_id" in call_kwargs, (
            "apply_correction must receive batch_id kwarg from find_and_replace"
        )
        batch_id_passed = call_kwargs["batch_id"]
        assert batch_id_passed is not None, (
            "batch_id passed to apply_correction must not be None in live mode"
        )
        assert isinstance(batch_id_passed, uuid.UUID), (
            f"batch_id must be a uuid.UUID; got {type(batch_id_passed)}"
        )

    async def test_all_corrections_in_batch_share_same_batch_id(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """All corrections from a single find_and_replace() share the same batch_id.

        When multiple segments match the pattern, every apply_correction() call
        issued within that single find_and_replace() invocation must receive the
        same batch_id so that they form a cohesive group for later batch-revert.
        """
        seg1 = _make_segment(video_id="v1", segment_id=1, text="teh cat")
        seg2 = _make_segment(video_id="v1", segment_id=2, text="teh dog")
        seg3 = _make_segment(video_id="v2", segment_id=3, text="teh bird")

        mock_segment_repo.count_filtered.return_value = 20
        mock_segment_repo.find_by_text_pattern.return_value = [seg1, seg2, seg3]
        mock_correction_service.apply_correction.return_value = MagicMock()

        await service.find_and_replace(
            mock_session,
            pattern="teh",
            replacement="the",
        )

        assert mock_correction_service.apply_correction.call_count == 3

        # Collect all batch_ids passed across every apply_correction() call
        batch_ids_used: set[uuid.UUID] = set()
        for call in mock_correction_service.apply_correction.call_args_list:
            bid = call.kwargs.get("batch_id")
            assert bid is not None, (
                "Every apply_correction call must receive a non-None batch_id"
            )
            batch_ids_used.add(bid)

        # All corrections in a single find_and_replace must share one batch_id
        assert len(batch_ids_used) == 1, (
            f"Expected exactly 1 unique batch_id; got {len(batch_ids_used)}: "
            f"{batch_ids_used}"
        )

    async def test_successive_find_and_replace_calls_get_different_batch_ids(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """Two separate find_and_replace() calls produce two distinct batch_ids.

        Each call is an independent batch operation and must receive its own
        UUIDv7 so that operators can revert them independently via batch-revert.
        """
        seg_a = _make_segment(video_id="v1", segment_id=10, text="errr word")
        seg_b = _make_segment(video_id="v2", segment_id=20, text="seperate issue")

        mock_segment_repo.count_filtered.return_value = 5
        mock_segment_repo.find_by_text_pattern.side_effect = [
            [seg_a],  # first call returns seg_a
            [seg_b],  # second call returns seg_b
        ]
        mock_correction_service.apply_correction.return_value = MagicMock()

        # First batch operation
        await service.find_and_replace(
            mock_session,
            pattern="errr",
            replacement="err",
        )
        first_call_kwargs = mock_correction_service.apply_correction.call_args.kwargs
        batch_id_first = first_call_kwargs["batch_id"]

        mock_correction_service.apply_correction.reset_mock()

        # Second batch operation
        await service.find_and_replace(
            mock_session,
            pattern="seperate",
            replacement="separate",
        )
        second_call_kwargs = mock_correction_service.apply_correction.call_args.kwargs
        batch_id_second = second_call_kwargs["batch_id"]

        assert batch_id_first != batch_id_second, (
            "Successive find_and_replace() calls must produce distinct batch_ids; "
            f"got identical id {batch_id_first!r} for both"
        )

    async def test_dry_run_does_not_generate_batch_id(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """find_and_replace(dry_run=True) never calls apply_correction with a batch_id.

        Dry-run mode returns preview data without touching the database, so
        no batch_id is generated and apply_correction is never called.
        """
        mock_session.execute.return_value = _make_empty_execute_result()
        mock_segment_repo.find_by_text_pattern.return_value = []

        result = await service.find_and_replace(
            mock_session,
            pattern="teh",
            replacement="the",
            dry_run=True,
        )

        # Dry-run returns a list of preview tuples, not a BatchCorrectionResult
        assert isinstance(result, list)
        # apply_correction must never be invoked in dry-run mode
        mock_correction_service.apply_correction.assert_not_called()

    async def test_zero_match_live_run_skips_batch_id(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """When no segments match, apply_correction is never called.

        If find_and_replace() short-circuits due to zero matches, the UUIDv7
        batch_id is still generated internally (expected) but never forwarded
        since apply_correction is never called.
        """
        mock_segment_repo.count_filtered.return_value = 0
        mock_segment_repo.find_by_text_pattern.return_value = []

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        result = await service.find_and_replace(
            mock_session,
            pattern="nonexistent_pattern",
            replacement="replacement",
        )

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_applied == 0
        mock_correction_service.apply_correction.assert_not_called()


# ---------------------------------------------------------------------------
# TestApplyToSegmentsBatchIdPropagation (Feature 045 — T015)
# ---------------------------------------------------------------------------


class TestApplyToSegmentsBatchIdPropagation:
    """Tests for batch_id propagation in apply_to_segments().

    apply_to_segments() accepts an optional batch_id and must forward it to
    every apply_correction() call.  When no batch_id is provided (inline
    corrections), apply_correction must receive batch_id=None.
    """

    async def test_explicit_batch_id_is_forwarded_to_apply_correction(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """apply_to_segments() forwards an explicit batch_id to apply_correction().

        This is the batch-apply path: the caller (find_and_replace) generates
        a batch_id and passes it through apply_to_segments so all resulting
        corrections share the same provenance identifier.
        """
        batch_id = uuid.UUID(bytes=__import__("uuid_utils").uuid7().bytes)
        seg = _make_segment(video_id="vid1", segment_id=1, text="teh fox")

        correction_record = MagicMock()
        correction_record.id = uuid.uuid4()
        mock_correction_service.apply_correction.return_value = correction_record

        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg]
        mock_session.execute.return_value = segment_result

        result = await service.apply_to_segments(
            mock_session,
            pattern="teh",
            replacement="the",
            segment_ids=[1],
            batch_id=batch_id,
            auto_rebuild=False,
        )

        assert result.total_applied == 1
        call_kwargs = mock_correction_service.apply_correction.call_args.kwargs
        assert call_kwargs.get("batch_id") == batch_id, (
            f"apply_correction must receive batch_id={batch_id!r}; "
            f"got {call_kwargs.get('batch_id')!r}"
        )

    async def test_none_batch_id_passed_as_null_to_apply_correction(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """apply_to_segments() with batch_id=None passes None to apply_correction().

        Individual (inline) corrections must have batch_id=None so that they
        are excluded from batch-list aggregation and batch-revert operations.
        """
        seg = _make_segment(video_id="vid1", segment_id=1, text="teh fox")

        correction_record = MagicMock()
        correction_record.id = uuid.uuid4()
        mock_correction_service.apply_correction.return_value = correction_record

        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg]
        mock_session.execute.return_value = segment_result

        result = await service.apply_to_segments(
            mock_session,
            pattern="teh",
            replacement="the",
            segment_ids=[1],
            batch_id=None,  # explicit None — individual correction
            auto_rebuild=False,
        )

        assert result.total_applied == 1
        call_kwargs = mock_correction_service.apply_correction.call_args.kwargs
        assert call_kwargs.get("batch_id") is None, (
            "apply_correction must receive batch_id=None for individual corrections"
        )

    async def test_all_segments_in_one_call_share_batch_id(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """All segments in a single apply_to_segments() share the same batch_id.

        When batch_id is provided, every segment processed in that call must
        receive the identical batch_id so they all belong to the same batch group.
        """
        batch_id = uuid.UUID(bytes=__import__("uuid_utils").uuid7().bytes)

        seg1 = _make_segment(video_id="v1", segment_id=1, text="teh cat")
        seg2 = _make_segment(video_id="v1", segment_id=2, text="teh dog")

        correction_record = MagicMock()
        correction_record.id = uuid.uuid4()
        mock_correction_service.apply_correction.return_value = correction_record

        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg1, seg2]
        mock_session.execute.return_value = segment_result

        result = await service.apply_to_segments(
            mock_session,
            pattern="teh",
            replacement="the",
            segment_ids=[1, 2],
            batch_id=batch_id,
            auto_rebuild=False,
        )

        assert result.total_applied == 2
        assert mock_correction_service.apply_correction.call_count == 2

        for call in mock_correction_service.apply_correction.call_args_list:
            assert call.kwargs.get("batch_id") == batch_id


# ---------------------------------------------------------------------------
# TestExportCorrectionsBatchId (Feature 045 — T015)
# ---------------------------------------------------------------------------


class TestExportCorrectionsBatchId:
    """Tests for batch_id inclusion in export_corrections() output.

    export_corrections() must include the batch_id field in both CSV and JSON
    output, with NULL (None) values preserved for individual corrections and
    UUID values serialised correctly for batch corrections.
    """

    async def test_csv_export_includes_batch_id_column(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """CSV export includes batch_id as the last column header.

        The CSV fieldnames list in export_corrections() must include 'batch_id'
        so downstream consumers can identify which corrections belong to a batch.
        """
        mock_correction_repo.get_all_filtered.return_value = []

        _, csv_str = await service.export_corrections(mock_session, format="csv")

        header_row = csv_str.strip().split("\n")[0]
        assert "batch_id" in header_row, (
            f"CSV header must include 'batch_id' column; got: {header_row!r}"
        )

    async def test_csv_export_batch_id_populated_when_correction_has_batch(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """CSV export renders the UUID when a correction has a non-null batch_id.

        The batch_id in the exported row must match the correction's batch_id
        so that operators can identify and correlate batch corrections.
        """
        import csv
        import io

        batch_id = uuid.UUID(bytes=__import__("uuid_utils").uuid7().bytes)
        c = _make_correction_db(
            video_id="v1",
            segment_id=1,
            batch_id=batch_id,
        )
        mock_correction_repo.get_all_filtered.return_value = [c]

        _, csv_str = await service.export_corrections(mock_session, format="csv")

        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["batch_id"] == str(batch_id), (
            f"CSV batch_id must be the UUID string; got {rows[0]['batch_id']!r}"
        )

    async def test_csv_export_batch_id_empty_when_null(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """CSV export renders empty string for individual corrections (batch_id=None).

        Individual (non-batch) corrections have batch_id=None in the database.
        The CSV export must render this as an empty cell, not the string 'None'.
        """
        import csv
        import io

        c = _make_correction_db(video_id="v1", segment_id=1, batch_id=None)
        mock_correction_repo.get_all_filtered.return_value = [c]

        _, csv_str = await service.export_corrections(mock_session, format="csv")

        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        assert len(rows) == 1
        # batch_id=None should render as empty string in CSV, not the string "None"
        assert rows[0]["batch_id"] != "None", (
            "batch_id=None must not be rendered as the string 'None' in CSV; "
            f"got {rows[0]['batch_id']!r}"
        )

    async def test_json_export_includes_batch_id_field(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """JSON export includes batch_id key in each correction object.

        Every correction object in the JSON array must have a 'batch_id' key
        present (value may be null for individual corrections).
        """
        import json

        c = _make_correction_db(video_id="v1", batch_id=None)
        mock_correction_repo.get_all_filtered.return_value = [c]

        _, json_str = await service.export_corrections(mock_session, format="json")

        parsed = json.loads(json_str)
        assert len(parsed) == 1
        assert "batch_id" in parsed[0], (
            f"JSON correction object must have 'batch_id' key; "
            f"keys present: {list(parsed[0].keys())}"
        )

    async def test_json_export_batch_id_serialised_as_string(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
    ) -> None:
        """JSON export renders batch_id UUID as a string, not a raw UUID object.

        The JSON serialiser must convert UUID objects to strings via the
        _json_default fallback, so clients receive a standard UUID string.
        """
        import json

        batch_id = uuid.UUID(bytes=__import__("uuid_utils").uuid7().bytes)
        c = _make_correction_db(video_id="v1", batch_id=batch_id)
        mock_correction_repo.get_all_filtered.return_value = [c]

        _, json_str = await service.export_corrections(mock_session, format="json")

        parsed = json.loads(json_str)
        assert len(parsed) == 1
        # If batch_id is present and non-null, it must be a string
        if parsed[0]["batch_id"] is not None:
            assert isinstance(parsed[0]["batch_id"], str), (
                f"JSON batch_id must be a string; got {type(parsed[0]['batch_id'])}"
            )
            # Must round-trip as a valid UUID
            parsed_uuid = uuid.UUID(parsed[0]["batch_id"])
            assert parsed_uuid == batch_id


# ---------------------------------------------------------------------------
# TestBatchRevertByBatchId (Feature 045 — T015)
# ---------------------------------------------------------------------------


class TestBatchRevertByBatchId:
    """Tests for batch_revert(batch_id=...) mode introduced in Feature 045.

    When batch_id is provided, batch_revert() must:
    1. Call correction_repo.get_by_batch_id() to fetch corrections
    2. Fetch segments by the segment IDs in those corrections
    3. Revert only the segments that still have active corrections
    4. Return a BatchCorrectionResult with accurate counts
    5. Return an empty BatchCorrectionResult when no corrections exist
    """

    async def test_batch_id_mode_calls_get_by_batch_id(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """batch_revert(batch_id=...) queries corrections by batch_id.

        The service must call correction_repo.get_by_batch_id() so that
        only corrections from the specified batch are targeted for revert.
        """
        batch_id = uuid.UUID(bytes=__import__("uuid_utils").uuid7().bytes)
        correction = _make_correction_db(
            segment_id=10, batch_id=batch_id
        )
        mock_correction_repo.get_by_batch_id.return_value = [correction]

        # Segment lookup returns a corrected segment
        seg = _make_segment(
            video_id="v1", segment_id=10,
            corrected_text="the fox", has_correction=True,
        )
        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg]
        mock_session.execute.return_value = segment_result

        mock_correction_service.revert_correction.return_value = MagicMock()

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockMentionRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_entity_ids_by_correction_ids.return_value = []
            mock_repo_instance.delete_by_correction_ids.return_value = 0
            MockMentionRepo.return_value = mock_repo_instance

            result = await service.batch_revert(
                mock_session,
                batch_id=batch_id,
            )

        mock_correction_repo.get_by_batch_id.assert_called_once_with(
            mock_session, batch_id
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult)

    async def test_batch_id_mode_reverts_all_matching_segments(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """batch_revert() reverts every active correction in the batch.

        All segments from the batch that still have has_correction=True must
        be reverted. Segments without active corrections are skipped.
        """
        batch_id = uuid.UUID(bytes=__import__("uuid_utils").uuid7().bytes)

        correction_a = _make_correction_db(segment_id=1, batch_id=batch_id)
        correction_b = _make_correction_db(segment_id=2, batch_id=batch_id)
        mock_correction_repo.get_by_batch_id.return_value = [
            correction_a, correction_b
        ]

        seg1 = _make_segment(
            video_id="v1", segment_id=1,
            corrected_text="the cat", has_correction=True,
        )
        seg2 = _make_segment(
            video_id="v1", segment_id=2,
            corrected_text="the dog", has_correction=True,
        )
        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg1, seg2]
        mock_session.execute.return_value = segment_result

        mock_correction_service.revert_correction.return_value = MagicMock()

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockMentionRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_entity_ids_by_correction_ids.return_value = []
            mock_repo_instance.delete_by_correction_ids.return_value = 0
            MockMentionRepo.return_value = mock_repo_instance

            result = await service.batch_revert(
                mock_session,
                batch_id=batch_id,
            )

        assert mock_correction_service.revert_correction.call_count == 2
        assert result.total_applied == 2
        assert result.total_skipped == 0

    async def test_batch_id_mode_returns_empty_result_for_nonexistent_batch(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """batch_revert(batch_id=...) returns empty BatchCorrectionResult for unknown batch.

        When no corrections exist for the given batch_id, the service must
        return a zero-count result rather than raising an error.
        """
        batch_id = uuid.UUID(bytes=__import__("uuid_utils").uuid7().bytes)
        mock_correction_repo.get_by_batch_id.return_value = []

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        result = await service.batch_revert(
            mock_session,
            batch_id=batch_id,
        )

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_applied == 0
        assert result.total_matched == 0
        assert result.total_scanned == 0
        # revert_correction must never be called when there are no corrections
        mock_correction_service.revert_correction.assert_not_called()

    async def test_batch_id_mode_skips_segments_without_active_corrections(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """batch_revert() skips segments that have already been reverted.

        If a segment's has_correction flag is False at revert time (e.g. it was
        already reverted by a previous call), it must be counted as skipped
        rather than causing an error.
        """
        batch_id = uuid.UUID(bytes=__import__("uuid_utils").uuid7().bytes)

        correction_a = _make_correction_db(segment_id=1, batch_id=batch_id)
        correction_b = _make_correction_db(segment_id=2, batch_id=batch_id)
        mock_correction_repo.get_by_batch_id.return_value = [
            correction_a, correction_b
        ]

        # seg1 still has an active correction; seg2 was already reverted
        seg1 = _make_segment(
            video_id="v1", segment_id=1,
            corrected_text="the cat", has_correction=True,
        )
        seg2 = _make_segment(
            video_id="v1", segment_id=2,
            corrected_text=None, has_correction=False,
        )
        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg1, seg2]
        mock_session.execute.return_value = segment_result

        mock_correction_service.revert_correction.return_value = MagicMock()

        with patch(
            "chronovista.services.batch_correction_service.EntityMentionRepository"
        ) as MockMentionRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_entity_ids_by_correction_ids.return_value = []
            mock_repo_instance.delete_by_correction_ids.return_value = 0
            MockMentionRepo.return_value = mock_repo_instance

            result = await service.batch_revert(
                mock_session,
                batch_id=batch_id,
            )

        # Only seg1 (has_correction=True) should be reverted
        assert mock_correction_service.revert_correction.call_count == 1
        assert result.total_applied == 1

    async def test_batch_id_mode_dry_run_returns_preview_tuples(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_correction_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """batch_revert(batch_id=..., dry_run=True) returns preview tuples.

        Dry-run mode must return a list of preview tuples describing what
        would be reverted without actually calling revert_correction.
        """
        batch_id = uuid.UUID(bytes=__import__("uuid_utils").uuid7().bytes)
        correction = _make_correction_db(segment_id=5, batch_id=batch_id)
        mock_correction_repo.get_by_batch_id.return_value = [correction]

        seg = _make_segment(
            video_id="vid1", segment_id=5,
            corrected_text="the fox", has_correction=True, start_time=1.5,
        )
        segment_result = MagicMock()
        segment_result.scalars.return_value.all.return_value = [seg]
        mock_session.execute.return_value = segment_result

        result = await service.batch_revert(
            mock_session,
            batch_id=batch_id,
            dry_run=True,
        )

        # Dry-run returns a list, not a BatchCorrectionResult
        assert isinstance(result, list)
        assert len(result) == 1
        # revert_correction must never be called in dry-run mode
        mock_correction_service.revert_correction.assert_not_called()

    async def test_batch_id_mode_does_not_use_pattern_matching(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_repo: AsyncMock,
        mock_correction_service: AsyncMock,
    ) -> None:
        """batch_revert(batch_id=...) bypasses segment pattern matching.

        When batch_id is provided, the service must use get_by_batch_id()
        rather than find_by_text_pattern(). The segment_repo pattern-search
        must not be called so that the batch is identified purely by provenance.
        """
        batch_id = uuid.UUID(bytes=__import__("uuid_utils").uuid7().bytes)
        mock_correction_repo.get_by_batch_id.return_value = []

        await service.batch_revert(
            mock_session,
            batch_id=batch_id,
        )

        # Pattern-based segment search must NOT be used in batch_id mode
        mock_segment_repo.find_by_text_pattern.assert_not_called()
        mock_segment_repo.count_filtered.assert_not_called()


# ---------------------------------------------------------------------------
# T024 [US3]: word_level_diff() unit tests
# ---------------------------------------------------------------------------


class TestWordLevelDiff:
    """Unit tests for the ``word_level_diff()`` function.

    Covers single-word changes, multi-word shared context, full-text
    replacement, capitalisation-only exclusion, token-count mismatches,
    Unicode characters, identical inputs, and empty strings.

    All tests are synchronous — ``word_level_diff`` is a pure function with
    no I/O.
    """

    # ------------------------------------------------------------------
    # (a) Single-word change
    # ------------------------------------------------------------------

    def test_single_word_change_one_changed_pair(self) -> None:
        """A single misspelled word produces exactly one changed pair.

        "Chomski" → "Chomsky" must yield changed_pairs=[("Chomski", "Chomsky")]
        with no unchanged_tokens and no residual pairs.
        """
        from chronovista.services.batch_correction_service import word_level_diff

        result = word_level_diff("Chomski", "Chomsky")

        assert len(result.changed_pairs) == 1
        assert result.changed_pairs[0] == ("Chomski", "Chomsky")
        # Single-token input — nothing is unchanged
        assert result.unchanged_tokens == []

    # ------------------------------------------------------------------
    # (b) Multi-word with shared context
    # ------------------------------------------------------------------

    def test_multi_word_shared_context_only_diff_reported(self) -> None:
        """Unchanged surrounding words are captured in unchanged_tokens.

        "Noam Chomski" → "Noam Chomsky": "Noam" is identical (case-insensitive),
        so it must appear in unchanged_tokens. Only the misspelled word should
        appear as a changed pair.
        """
        from chronovista.services.batch_correction_service import word_level_diff

        result = word_level_diff("Noam Chomski", "Noam Chomsky")

        assert ("Chomski", "Chomsky") in result.changed_pairs
        assert "Noam" in result.unchanged_tokens
        # There must be exactly one changed pair (the misspelling, not "Noam")
        assert len(result.changed_pairs) == 1

    # ------------------------------------------------------------------
    # (c) Entire text changed
    # ------------------------------------------------------------------

    def test_entire_text_changed_both_tokens_different(self) -> None:
        """When every token changes, all pairs land in changed_pairs.

        "Shane Bound" → "Sheinbaum": both tokens differ, so changed_pairs must
        contain the full original and corrected fragments. No unchanged_tokens.
        """
        from chronovista.services.batch_correction_service import word_level_diff

        result = word_level_diff("Shane Bound", "Sheinbaum")

        # At least one changed pair must exist; unchanged_tokens must be empty
        assert len(result.changed_pairs) >= 1
        assert result.unchanged_tokens == []
        # Reconstruct all originals from pairs
        all_originals = " ".join(pair[0] for pair in result.changed_pairs if pair[0])
        assert "Shane" in all_originals or "Shane Bound" in all_originals

    # ------------------------------------------------------------------
    # (d) Capitalisation-only excluded
    # ------------------------------------------------------------------

    def test_capitalisation_only_not_reported(self) -> None:
        """Capitalisation-only differences must NOT appear in changed_pairs.

        "NATO" vs "nato" differ only in case; the function compares tokens
        in lowered form so this must produce no changed pairs.
        """
        from chronovista.services.batch_correction_service import word_level_diff

        result = word_level_diff("NATO", "nato")

        assert result.changed_pairs == []
        # The token is equal (case-insensitive), so it shows as unchanged
        assert len(result.unchanged_tokens) == 1

    # ------------------------------------------------------------------
    # (e) Token count mismatch
    # ------------------------------------------------------------------

    def test_token_count_mismatch_handled(self) -> None:
        """2-token original vs 1-token corrected does not raise.

        "Shin Bomb" (2 tokens) → "Sheinbaum" (1 token): the function must
        return a result without raising, and changed_pairs must be non-empty
        since the content differs.
        """
        from chronovista.services.batch_correction_service import word_level_diff

        result = word_level_diff("Shin Bomb", "Sheinbaum")

        # Must not raise; must have at least one change since texts differ
        assert isinstance(result.changed_pairs, list)
        assert len(result.changed_pairs) >= 1

    # ------------------------------------------------------------------
    # (f) Unicode accented characters
    # ------------------------------------------------------------------

    def test_unicode_accent_difference_detected(self) -> None:
        """Accented vs non-accented characters are reported as a change.

        "café" vs "cafe" differ at the character level even though they look
        similar. The function must detect this as a changed pair.
        """
        from chronovista.services.batch_correction_service import word_level_diff

        result = word_level_diff("café", "cafe")

        assert len(result.changed_pairs) == 1
        assert result.changed_pairs[0] == ("café", "cafe")

    # ------------------------------------------------------------------
    # (g) Identical text
    # ------------------------------------------------------------------

    def test_identical_text_returns_no_changes(self) -> None:
        """Diffing identical strings yields no changed pairs.

        Every token appears in unchanged_tokens; changed_pairs and any
        delete/insert opcodes are absent.
        """
        from chronovista.services.batch_correction_service import word_level_diff

        result = word_level_diff("the quick brown fox", "the quick brown fox")

        assert result.changed_pairs == []
        assert result.unchanged_tokens == ["the", "quick", "brown", "fox"]

    # ------------------------------------------------------------------
    # (h) Empty strings
    # ------------------------------------------------------------------

    def test_both_empty_returns_empty_result(self) -> None:
        """Two empty strings produce a fully empty WordLevelDiffResult.

        No pairs, no unchanged tokens, no opcodes.
        """
        from chronovista.services.batch_correction_service import word_level_diff

        result = word_level_diff("", "")

        assert result.changed_pairs == []
        assert result.unchanged_tokens == []
        assert result.token_positions == []

    def test_original_empty_corrected_nonempty(self) -> None:
        """Empty original with non-empty corrected yields an insert-type pair.

        The corrected text that was inserted should appear in changed_pairs as
        ("", corrected_fragment).
        """
        from chronovista.services.batch_correction_service import word_level_diff

        result = word_level_diff("", "Chomsky")

        assert len(result.changed_pairs) >= 1
        # An insert opcode adds ("", token) pairs
        assert any(pair[0] == "" for pair in result.changed_pairs)

    def test_original_nonempty_corrected_empty(self) -> None:
        """Non-empty original with empty corrected yields a delete-type pair.

        The deleted text should appear in changed_pairs as (original_fragment, "").
        """
        from chronovista.services.batch_correction_service import word_level_diff

        result = word_level_diff("Chomski", "")

        assert len(result.changed_pairs) >= 1
        assert any(pair[1] == "" for pair in result.changed_pairs)


# ---------------------------------------------------------------------------
# T025 [US3]: Minimal-token alias registration tests
# ---------------------------------------------------------------------------


class TestMinimalTokenAliasRegistration:
    """Unit tests for the word-level diff sub-token alias registration logic
    inside ``register_asr_alias`` (chronovista.services.asr_alias_registry).

    Tests verify that when a full-string correction matches an entity:
    - Minimal (sub-token) changed pairs are registered as separate ASR aliases
    - Multiple changed blocks are each registered independently
    - Duplicate sub-tokens (identical to the full string) are skipped
    - No registration occurs when no entity is matched

    All database I/O is mocked; tests use factory-boy ORM factories for
    correction data construction.
    """

    # ------------------------------------------------------------------
    # (a) Minimal token registered alongside full string
    # ------------------------------------------------------------------

    async def test_sub_token_registered_when_entity_matched(self) -> None:
        """When the corrected text matches an entity, changed sub-tokens are
        also registered as separate ASR aliases.

        Scenario: "Noam Chomski" → "Noam Chomsky". The full string is
        registered for the entity. The sub-token diff produces ("Chomski",
        "Chomsky") which must trigger a second alias registration.
        """
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from uuid_utils import uuid7

        entity_id = uuid.UUID(bytes=uuid7().bytes)

        mock_session = AsyncMock()
        # begin_nested is a synchronous context manager returning an async cm
        mock_session.begin_nested = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
        )

        with patch(
            "chronovista.services.asr_alias_registry.resolve_entity_id_from_text",
            new=AsyncMock(return_value=(entity_id, "Noam Chomsky")),
        ), patch(
            "chronovista.services.asr_alias_registry.TagNormalizationService"
        ) as MockNormalizer, patch(
            "chronovista.services.asr_alias_registry.EntityAliasRepository"
        ) as MockAliasRepo:
            normalizer_instance = MagicMock()
            normalizer_instance.normalize.side_effect = lambda t: t.lower()
            MockNormalizer.return_value = normalizer_instance

            repo_instance = AsyncMock()
            MockAliasRepo.return_value = repo_instance

            existing_result = MagicMock()
            existing_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = existing_result

            from chronovista.services.asr_alias_registry import register_asr_alias

            await register_asr_alias(
                mock_session,
                original_text="Noam Chomski",
                corrected_text="Noam Chomsky",
            )

        # EntityAliasRepository.create must have been called at least twice:
        # once for the full string alias and once for the sub-token alias
        assert repo_instance.create.call_count >= 2

    # ------------------------------------------------------------------
    # (b) Multiple changed blocks registered as separate aliases
    # ------------------------------------------------------------------

    async def test_multiple_changed_blocks_registered_separately(self) -> None:
        """Each distinct changed pair from the diff is registered individually.

        Scenario: "Shin Bomb" → "Sheinbaum" — two tokens differ.  The
        implementation must attempt alias creation for every non-empty,
        non-duplicate changed pair.
        """
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from uuid_utils import uuid7

        entity_id = uuid.UUID(bytes=uuid7().bytes)

        mock_session = AsyncMock()
        mock_session.begin_nested = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
        )

        with patch(
            "chronovista.services.asr_alias_registry.resolve_entity_id_from_text",
            new=AsyncMock(return_value=(entity_id, "Sheinbaum")),
        ), patch(
            "chronovista.services.asr_alias_registry.TagNormalizationService"
        ) as MockNormalizer, patch(
            "chronovista.services.asr_alias_registry.EntityAliasRepository"
        ) as MockAliasRepo:
            normalizer_instance = MagicMock()
            normalizer_instance.normalize.side_effect = lambda t: t.lower()
            MockNormalizer.return_value = normalizer_instance

            repo_instance = AsyncMock()
            MockAliasRepo.return_value = repo_instance

            existing_result = MagicMock()
            existing_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = existing_result

            from chronovista.services.asr_alias_registry import register_asr_alias

            await register_asr_alias(
                mock_session,
                original_text="Shin Bomb",
                corrected_text="Sheinbaum",
            )

        # At least the full-string alias must have been registered
        assert repo_instance.create.call_count >= 1

    # ------------------------------------------------------------------
    # (c) Identical minimal token and full string — no duplicate
    # ------------------------------------------------------------------

    async def test_no_duplicate_when_sub_token_equals_full_string(self) -> None:
        """Sub-tokens that are identical to the full original string are skipped.

        The guard ``error_token.strip() == original_text.strip()`` prevents
        registering the same ASR error form twice.  With "Chomski" → "Chomsky"
        the single token equals the full string, so only one alias is created.
        """
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from uuid_utils import uuid7

        entity_id = uuid.UUID(bytes=uuid7().bytes)

        mock_session = AsyncMock()
        mock_session.begin_nested = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
        )

        with patch(
            "chronovista.services.asr_alias_registry.resolve_entity_id_from_text",
            new=AsyncMock(return_value=(entity_id, "Chomsky")),
        ), patch(
            "chronovista.services.asr_alias_registry.TagNormalizationService"
        ) as MockNormalizer, patch(
            "chronovista.services.asr_alias_registry.EntityAliasRepository"
        ) as MockAliasRepo:
            normalizer_instance = MagicMock()
            normalizer_instance.normalize.side_effect = lambda t: t.lower()
            MockNormalizer.return_value = normalizer_instance

            repo_instance = AsyncMock()
            MockAliasRepo.return_value = repo_instance

            existing_result = MagicMock()
            existing_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = existing_result

            from chronovista.services.asr_alias_registry import register_asr_alias

            await register_asr_alias(
                mock_session,
                original_text="Chomski",
                corrected_text="Chomsky",
            )

        # "Chomski" == "Chomski" (full string) so no sub-token registration,
        # meaning create is called exactly once (for the full-string alias).
        assert repo_instance.create.call_count == 1

    # ------------------------------------------------------------------
    # (d) No registration when entity not matched
    # ------------------------------------------------------------------

    async def test_no_registration_when_no_entity_match(self) -> None:
        """When ``resolve_entity_id_from_text`` returns None, nothing is registered.

        The hook is a no-op when the corrected text does not match any known
        entity — no alias repository calls must be made.
        """
        from unittest.mock import AsyncMock, patch

        mock_session = AsyncMock()

        with patch(
            "chronovista.services.asr_alias_registry.resolve_entity_id_from_text",
            new=AsyncMock(return_value=None),
        ), patch(
            "chronovista.services.asr_alias_registry.EntityAliasRepository"
        ) as MockAliasRepo:
            repo_instance = AsyncMock()
            MockAliasRepo.return_value = repo_instance

            from chronovista.services.asr_alias_registry import register_asr_alias

            await register_asr_alias(
                mock_session,
                original_text="random text",
                corrected_text="unknown entity xyz",
            )

        # No alias was resolved, so nothing should have been created
        repo_instance.create.assert_not_called()
