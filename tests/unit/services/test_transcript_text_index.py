"""Unit tests for the shared span-resolution primitive (Feature 081, T008).

The primitive is the single source of truth for (a) the effective-text rule and (b) mapping a
match's offsets in the assembled transcript text back to its segment(s). These tests pin the
span semantics both mention-writers depend on. All names are synthetic placeholders — no
library content (Constitution VI).
"""

from __future__ import annotations

import pytest

from chronovista.services.transcript_text_index import (
    SEGMENT_SEPARATOR,
    SegmentInput,
    TranscriptTextIndex,
    effective_text,
)


class TestEffectiveText:
    def test_uses_corrected_when_corrected(self) -> None:
        assert effective_text("orig", "fixed", True) == "fixed"

    def test_uses_original_when_not_corrected(self) -> None:
        assert effective_text("orig", "fixed", False) == "orig"

    def test_null_corrected_falls_back_to_original_even_if_flagged(self) -> None:
        assert effective_text("orig", None, True) == "orig"

    def test_segment_input_effective_property(self) -> None:
        assert (
            SegmentInput(
                segment_id=1, text="a", corrected_text="b", has_correction=True
            ).effective
            == "b"
        )
        assert SegmentInput(segment_id=1, text="a").effective == "a"


class TestAssembly:
    def test_single_space_separator_between_segments(self) -> None:
        idx = TranscriptTextIndex.from_segments(
            [
                SegmentInput(segment_id=1, text="Alfa"),
                SegmentInput(segment_id=2, text="Bravo"),
            ]
        )
        assert idx.text == f"Alfa{SEGMENT_SEPARATOR}Bravo" == "Alfa Bravo"


class TestResolveSpan:
    def test_single_segment_match_has_no_end_segment(self) -> None:
        # one segment that already contains the whole name
        idx = TranscriptTextIndex.from_segments(
            [SegmentInput(segment_id=5, text="Alfa Bravo")]
        )
        anchor = idx.resolve_span(0, len("Alfa Bravo"))
        assert anchor.segment_id == 5
        assert anchor.end_segment_id is None
        assert anchor.crossed_segment_ids == (5,)
        assert (anchor.match_start, anchor.match_end) == (0, len("Alfa Bravo"))

    def test_two_segment_span_anchors_first_ends_last(self) -> None:
        # "Alfa" | "Bravo" -> assembled "Alfa Bravo", a match spans the separator
        idx = TranscriptTextIndex.from_segments(
            [
                SegmentInput(segment_id=1, text="Alfa"),
                SegmentInput(segment_id=2, text="Bravo"),
            ]
        )
        anchor = idx.resolve_span(0, len("Alfa Bravo"))
        assert anchor.segment_id == 1
        assert anchor.end_segment_id == 2
        assert anchor.crossed_segment_ids == (1, 2)
        assert anchor.match_start == 0  # offset into segment 1 ("Alfa")
        assert anchor.match_end == len("Bravo")  # offset into segment 2

    def test_three_segment_span_lists_all_crossed(self) -> None:
        idx = TranscriptTextIndex.from_segments(
            [
                SegmentInput(segment_id=1, text="Doc"),
                SegmentInput(segment_id=2, text="Alfa"),
                SegmentInput(segment_id=3, text="Bravo"),
            ]
        )  # assembled "Doc Alfa Bravo"
        anchor = idx.resolve_span(0, len("Doc Alfa Bravo"))
        assert anchor.segment_id == 1
        assert anchor.end_segment_id == 3
        assert anchor.crossed_segment_ids == (1, 2, 3)
        assert anchor.match_start == 0
        assert anchor.match_end == len("Bravo")

    def test_match_inside_second_segment_only(self) -> None:
        idx = TranscriptTextIndex.from_segments(
            [
                SegmentInput(segment_id=1, text="hello"),
                SegmentInput(segment_id=2, text="Alfa Bravo here"),
            ]
        )
        start = idx.text.index("Alfa Bravo")
        anchor = idx.resolve_span(start, start + len("Alfa Bravo"))
        assert anchor.segment_id == 2
        assert anchor.end_segment_id is None
        assert anchor.match_start == 0
        assert anchor.match_end == len("Alfa Bravo")

    def test_uses_effective_text_for_corrected_segment(self) -> None:
        idx = TranscriptTextIndex.from_segments(
            [
                SegmentInput(
                    segment_id=1,
                    text="Wrong",
                    corrected_text="Right",
                    has_correction=True,
                ),
                SegmentInput(segment_id=2, text="word"),
            ]
        )
        assert idx.text == "Right word"

    def test_inverted_or_empty_span_raises(self) -> None:
        idx = TranscriptTextIndex.from_segments(
            [SegmentInput(segment_id=1, text="abc")]
        )
        with pytest.raises(ValueError):
            idx.resolve_span(2, 2)
        with pytest.raises(ValueError):
            idx.resolve_span(3, 1)
