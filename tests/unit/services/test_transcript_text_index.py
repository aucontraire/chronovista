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


class TestMentionReads:
    """THE one rule for "does a stored mention still read as its text" (#426).

    Every reader of stored offsets (the correction rebase, the scanner's survivor
    check, the repair) asks this one method, so these cases pin what they all mean.
    """

    @staticmethod
    def _index() -> TranscriptTextIndex:
        return TranscriptTextIndex.of([(1, "we saw Zeta"), (2, "Quux is here")])

    def test_a_single_segment_mention_reads_when_its_slice_is_its_text(self) -> None:
        assert self._index().mention_reads(
            segment_id=2,
            end_segment_id=None,
            match_start=0,
            match_end=4,
            mention_text="Quux",
        )

    def test_the_comparison_ignores_case(self) -> None:
        assert self._index().mention_reads(
            segment_id=2,
            end_segment_id=None,
            match_start=0,
            match_end=4,
            mention_text="QUUX",
        )

    def test_the_comparison_is_by_casefold_not_lowercase(self) -> None:
        index = TranscriptTextIndex.of([(1, "we saw Zeta STRASSE")])
        assert index.mention_reads(
            segment_id=1,
            end_segment_id=None,
            match_start=7,
            match_end=19,
            mention_text="Zeta Straße",
        )

    def test_a_single_segment_mention_off_its_words_does_not_read(self) -> None:
        assert not self._index().mention_reads(
            segment_id=2,
            end_segment_id=None,
            match_start=1,
            match_end=5,
            mention_text="Quux",
        )

    def test_a_split_mention_reads_across_its_joined_halves(self) -> None:
        assert self._index().mention_reads(
            segment_id=1,
            end_segment_id=2,
            match_start=7,
            match_end=4,
            mention_text="Zeta Quux",
        )

    def test_a_split_mention_whose_halves_no_longer_join_does_not_read(self) -> None:
        """The end segment was edited so its head no longer continues the name: the
        same offsets now cover 'Zeta so Q'.

        Mutation: read each half on its own against its part of the name instead of
        the joined text.
        """
        index = TranscriptTextIndex.of([(1, "we saw Zeta"), (2, "so Quux is here")])
        assert not index.mention_reads(
            segment_id=1,
            end_segment_id=2,
            match_start=7,
            match_end=4,
            mention_text="Zeta Quux",
        )

    def test_a_split_mention_read_against_a_one_segment_text_does_not_read(
        self,
    ) -> None:
        assert not self._index().mention_reads(
            segment_id=1,
            end_segment_id=None,
            match_start=7,
            match_end=11,
            mention_text="Zeta Quux",
        )

    @pytest.mark.parametrize(
        ("start", "end"),
        [(-1, 4), (0, 13), (13, 13), (5, 3)],
        ids=["negative-start", "end-past-text", "start-past-text", "inverted"],
    )
    def test_offsets_outside_their_segment_do_not_read(
        self, start: int, end: int
    ) -> None:
        """Offsets that are not inside the segment's own text never read."""
        assert not self._index().mention_reads(
            segment_id=2,
            end_segment_id=None,
            match_start=start,
            match_end=end,
            mention_text="Quux",
        )

    def test_offsets_running_out_of_the_segment_into_the_next_do_not_read(self) -> None:
        """Offsets past a single segment's end land on the NEXT segment's words in the
        joined text, so a slice check alone would read 'Zeta Quux' here; the range
        check is what says this row is not on its words.

        Mutation: remove the range check from ``mention_reads``.
        """
        assert not self._index().mention_reads(
            segment_id=1,
            end_segment_id=None,
            match_start=7,
            match_end=16,
            mention_text="Zeta Quux",
        )

    def test_an_end_offset_past_the_end_segment_does_not_read(self) -> None:
        assert not self._index().mention_reads(
            segment_id=1,
            end_segment_id=2,
            match_start=7,
            match_end=40,
            mention_text="Zeta Quux",
        )

    def test_an_empty_span_does_not_read(self) -> None:
        assert not self._index().mention_reads(
            segment_id=2,
            end_segment_id=None,
            match_start=2,
            match_end=2,
            mention_text="",
        )

    @pytest.mark.parametrize(
        ("segment_id", "end_segment_id"),
        [(99, None), (1, 99), (99, 2)],
        ids=["unknown-start", "unknown-end", "unknown-start-known-end"],
    )
    def test_a_segment_outside_the_index_does_not_read(
        self, segment_id: int, end_segment_id: int | None
    ) -> None:
        assert not self._index().mention_reads(
            segment_id=segment_id,
            end_segment_id=end_segment_id,
            match_start=0,
            match_end=4,
            mention_text="Zeta",
        )


class TestLocate:
    def test_a_stored_mention_maps_to_its_assembled_text_range(self) -> None:
        index = TranscriptTextIndex.of([(1, "we saw Zeta"), (2, "Quux is here")])
        located = index.locate(
            segment_id=1, end_segment_id=2, match_start=7, match_end=4
        )
        assert located is not None
        assert index.text[located[0] : located[1]] == "Zeta Quux"

    def test_it_is_the_inverse_of_resolve_span(self) -> None:
        index = TranscriptTextIndex.of([(1, "we saw Zeta"), (2, "Quux is here")])
        anchor = index.resolve_span(7, 16)
        assert index.locate(
            segment_id=anchor.segment_id,
            end_segment_id=anchor.end_segment_id,
            match_start=anchor.match_start,
            match_end=anchor.match_end,
        ) == (7, 16)

    def test_a_segment_outside_the_index_has_no_location(self) -> None:
        index = TranscriptTextIndex.of([(1, "we saw Zeta")])
        assert (
            index.locate(segment_id=5, end_segment_id=None, match_start=0, match_end=1)
            is None
        )
