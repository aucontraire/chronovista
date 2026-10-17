"""Unit tests for the cross-segment correction token split (Feature 081, T023/T026).

Exercises ``BatchCorrectionService._find_cross_segment_matches`` directly with mocked
segment fetches. A boundary-spanning correction whose replacement has two or more whole
tokens must distribute WHOLE tokens across both segments (never splitting a token
mid-word, both sides non-empty); a single-token replacement keeps the absorb-into-A
behavior and fires the FR-008 empty-B warning. All names are synthetic placeholders — no
library content (Constitution VI).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.services.batch_correction_service import BatchCorrectionService

pytestmark = pytest.mark.asyncio

_LOGGER_NAME = "chronovista.services.batch_correction_service"


def _seg(seg_id: int, seq: int, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=seg_id,
        video_id="testvideo01",
        language_code="en",
        sequence_number=seq,
        text=text,
        corrected_text=None,
        has_correction=False,
    )


def _service(segments: list[SimpleNamespace]) -> BatchCorrectionService:
    svc = BatchCorrectionService(
        correction_service=MagicMock(),
        segment_repo=MagicMock(),
        correction_repo=MagicMock(),
    )
    svc._segment_repo.find_segments_in_scope = AsyncMock(return_value=segments)
    return svc


async def _match(
    svc: BatchCorrectionService, *, pattern: str, replacement: str
) -> list[Any]:
    return await svc._find_cross_segment_matches(
        AsyncMock(),
        pattern=pattern,
        replacement=replacement,
        regex=False,
        case_insensitive=False,
        re_flags=0,
        language=None,
        channel=None,
        video_ids=["testvideo01"],  # non-None -> skip candidate pre-filter
        single_segment_ids=set(),
    )


class TestCrossSegmentCorrectionSplit:
    async def test_multi_token_distributes_whole_tokens_across_boundary(self) -> None:
        # Garbled "Alpha"|"Bravo" spans the boundary; corrected name is "Alfa Bravo".
        svc = _service([_seg(1, 0, "the guest is Alpha"), _seg(2, 1, "Bravo speaks")])
        matches = await _match(svc, pattern="Alpha Bravo", replacement="Alfa Bravo")

        assert len(matches) == 1
        a, b = matches[0].text_for_seg_a, matches[0].text_for_seg_b

        # Whole tokens, one per side — neither segment holds the entire name.
        assert "Alfa" in a.split() and "Bravo" not in a.split()
        assert "Bravo" in b.split() and "Alfa" not in b.split()
        # Both sides stay non-empty, so FR-008 does not apply to the multi-token case.
        assert a.strip() and b.strip()
        # No token was split mid-word; the full name reconstructs across the boundary.
        assert "Alfa Bravo" in f"{a} {b}"

    async def test_single_token_absorbs_into_a_and_warns_on_empty_b(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Single-token replacement with seg B fully consumed -> B emptied (FR-008).
        svc = _service([_seg(3, 0, "intro Charlie"), _seg(4, 1, "Delta")])
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            matches = await _match(
                svc, pattern="Charlie Delta", replacement="Charliedelta"
            )

        assert len(matches) == 1
        a, b = matches[0].text_for_seg_a, matches[0].text_for_seg_b

        # The whole single-token name is absorbed into segment A.
        assert "Charliedelta" in a.split()
        # Segment B is left empty and the FR-008 warning fired.
        assert b.strip() == ""
        assert "FR-008" in caplog.text

    async def test_single_token_with_trailing_context_keeps_b_nonempty(self) -> None:
        # A single-token replacement does not empty B when B has trailing context.
        svc = _service([_seg(5, 0, "say Echo"), _seg(6, 1, "Foxtrot and more")])
        matches = await _match(svc, pattern="Echo Foxtrot", replacement="Echofoxtrot")

        assert len(matches) == 1
        a, b = matches[0].text_for_seg_a, matches[0].text_for_seg_b
        assert "Echofoxtrot" in a.split()
        assert b.strip() == "and more"
