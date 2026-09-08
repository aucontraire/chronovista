"""Batch-correction whitespace normalization (Feature 076 / #293, US1).

The correction search pattern is normalized (collapse whitespace / strip
invisibles / NFC) before the DB find, so a phrase written or pasted with a
line break or non-breaking space still locates and replaces the target once
stored text is normalized. Regex patterns are left untouched. The stored
column is queried raw (no whitespace-folding SQL wrapper — index-safe); the
dirty-stored-row window is closed by the US3 backfill.

Non-ASCII inputs use chr() so the test does not depend on file encoding.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.services.batch_correction_service import BatchCorrectionService

pytestmark = pytest.mark.asyncio

NBSP = chr(0x00A0)


def _service() -> BatchCorrectionService:
    return BatchCorrectionService(
        correction_service=AsyncMock(),
        segment_repo=AsyncMock(),
        correction_repo=AsyncMock(),
    )


def _empty_execute_result(*args: Any, **kwargs: Any) -> MagicMock:
    result = MagicMock()
    result.all.return_value = []
    result.scalars.return_value.all.return_value = []
    return result


def _segment(text: str, *, segment_id: int = 1) -> MagicMock:
    seg = MagicMock()
    seg.video_id = "vid1"
    seg.id = segment_id
    seg.language_code = "en"
    seg.text = text
    seg.corrected_text = None
    seg.has_correction = False
    seg.start_time = 0.0
    seg.sequence_number = 1
    return seg


class TestSearchPatternNormalized:
    async def test_literal_newline_pattern_normalized_before_find(self) -> None:
        svc = _service()
        svc._segment_repo.find_by_text_pattern.return_value = []
        await svc.find_matching_segments(
            AsyncMock(), pattern="foo\nbar", replacement="X"
        )
        assert (
            svc._segment_repo.find_by_text_pattern.call_args.kwargs["pattern"]
            == "foo bar"
        )

    async def test_nbsp_pattern_normalized_before_find(self) -> None:
        svc = _service()
        svc._segment_repo.find_by_text_pattern.return_value = []
        await svc.find_matching_segments(
            AsyncMock(), pattern="foo" + NBSP + "bar", replacement="X"
        )
        assert (
            svc._segment_repo.find_by_text_pattern.call_args.kwargs["pattern"]
            == "foo bar"
        )

    async def test_regex_pattern_not_normalized(self) -> None:
        svc = _service()
        svc._segment_repo.find_by_text_pattern.return_value = []
        await svc.find_matching_segments(
            AsyncMock(), pattern=r"foo\s+bar", replacement="X", regex=True
        )
        assert (
            svc._segment_repo.find_by_text_pattern.call_args.kwargs["pattern"]
            == r"foo\s+bar"
        )

    async def test_ordinary_pattern_unchanged(self) -> None:
        svc = _service()
        svc._segment_repo.find_by_text_pattern.return_value = []
        await svc.find_matching_segments(
            AsyncMock(), pattern="foo bar", replacement="X"
        )
        assert (
            svc._segment_repo.find_by_text_pattern.call_args.kwargs["pattern"]
            == "foo bar"
        )

    async def test_whitespace_only_pattern_not_emptied(self) -> None:
        # A whitespace/invisible-only phrase must NOT normalize to "" (which a
        # substring search reads as match-everything). The raw pattern is kept.
        svc = _service()
        svc._segment_repo.find_by_text_pattern.return_value = []
        raw = "  " + NBSP + "\n"
        await svc.find_matching_segments(AsyncMock(), pattern=raw, replacement="X")
        passed = svc._segment_repo.find_by_text_pattern.call_args.kwargs["pattern"]
        assert passed == raw
        assert passed != ""


class TestReplaceUsesNormalizedPattern:
    async def test_replacement_applies_with_whitespace_pattern(self) -> None:
        # Without pattern normalization, "foo\nbar" would not match the
        # normalized stored text "foo bar", the replace would be a no-op, and
        # the match would be skipped (0 results). With normalization it applies.
        svc = _service()
        svc._segment_repo.find_by_text_pattern.return_value = [_segment("foo bar")]
        session = AsyncMock()
        session.execute.side_effect = _empty_execute_result
        matches, total = await svc.find_matching_segments(
            session, pattern="foo\nbar", replacement="X"
        )
        assert total == 1
        assert matches[0].current_text == "foo bar"
        assert matches[0].proposed_text == "X"
