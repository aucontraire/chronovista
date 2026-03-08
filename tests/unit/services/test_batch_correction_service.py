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
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from chronovista.models.enums import EntityAliasType

# ---------------------------------------------------------------------------
# CRITICAL: Module-level asyncio marker ensures async tests run properly
# with coverage tools, avoiding silent test-skipping (see CLAUDE.md).
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.asyncio


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


def _make_segment(
    *,
    video_id: str = "vid1",
    segment_id: int = 1,
    language_code: str = "en",
    text: str = "hello world",
    corrected_text: str | None = None,
    has_correction: bool = False,
    start_time: float = 0.0,
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
    correction_type: str = "asr_error",
    original_text: str = "old",
    corrected_text: str = "new",
    correction_note: str | None = None,
    corrected_by_user_id: str | None = None,
    corrected_at: Any = None,
    version_number: int = 1,
) -> MagicMock:
    """Create a mock TranscriptCorrectionDB for testing."""
    from datetime import datetime, timezone

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
    c.corrected_at = corrected_at or datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    c.version_number = version_number
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
            "version_number",
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
        from datetime import datetime, timezone
        from chronovista.models.enums import CorrectionType

        mock_correction_repo.get_all_filtered.return_value = []
        since = datetime(2025, 1, 1, tzinfo=timezone.utc)
        until = datetime(2025, 12, 31, tzinfo=timezone.utc)

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
            "by_type": [TypeCount(correction_type="asr_error", count=3)],
            "top_videos": [],
        }

        result = await service.get_statistics(mock_session)
        assert len(result.by_type) == 1
        assert result.by_type[0].correction_type == "asr_error"

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
        from chronovista.models.batch_correction_models import CorrectionPattern

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
    ) -> None:
        """Dry-run returns list of (video_id, segment_id, start_time, corrected_text)."""
        seg = _make_segment(
            video_id="v1", segment_id=10, text="original",
            corrected_text="fixed text", has_correction=True, start_time=5.5,
        )

        mock_segment_repo.count_filtered.return_value = 100
        mock_segment_repo.find_by_text_pattern.return_value = [seg]

        result = await service.batch_revert(
            mock_session, pattern="fixed", dry_run=True,
        )

        assert isinstance(result, list)
        assert len(result) == 1
        video_id, segment_id, start_time, corrected_text = result[0]
        assert video_id == "v1"
        assert segment_id == 10
        assert start_time == 5.5
        assert corrected_text == "fixed text"

    async def test_dry_run_filters_has_correction(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
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
    ) -> None:
        """Live mode calls revert_correction for each matched segment."""
        seg = _make_segment(
            video_id="v1", segment_id=42, text="orig",
            corrected_text="fixed", has_correction=True,
        )

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg]
        mock_correction_service.revert_correction.return_value = MagicMock()

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

        result = await service.batch_revert(mock_session, pattern="fix")

        assert result.unique_videos == 2

    async def test_progress_callback_called(
        self,
        service: Any,
        mock_session: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_correction_service: AsyncMock,
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
    ) -> None:
        """Dry-run mode does not call revert_correction."""
        seg = _make_segment(
            video_id="v1", segment_id=1, text="a",
            corrected_text="fix", has_correction=True,
        )

        mock_segment_repo.count_filtered.return_value = 10
        mock_segment_repo.find_by_text_pattern.return_value = [seg]

        await service.batch_revert(mock_session, pattern="fix", dry_run=True)

        mock_correction_service.revert_correction.assert_not_called()


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
            "chronovista.services.batch_correction_service.EntityAliasRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            MockRepo.return_value = mock_repo_instance

            with patch(
                "chronovista.services.tag_normalization.TagNormalizationService"
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
            "chronovista.services.batch_correction_service.EntityAliasRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            MockRepo.return_value = mock_repo_instance

            with patch(
                "chronovista.services.tag_normalization.TagNormalizationService"
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
            "chronovista.services.batch_correction_service.EntityAliasRepository"
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
            "chronovista.services.batch_correction_service.EntityAliasRepository"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            MockRepo.return_value = mock_repo_instance

            with patch(
                "chronovista.services.tag_normalization.TagNormalizationService"
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
