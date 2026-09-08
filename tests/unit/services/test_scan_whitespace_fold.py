"""Entity-scan whitespace-aware match fold (Feature 076 / #293, US2).

_fold_diacritics is the match fold the scan runs before finditer. It must also
collapse whitespace (so a multi-word name split by a newline/nbsp matches an
alias with a normal space) and strip invisibles, while keeping the offset_map
so mention_text/match_start/match_end still slice the RAW text.

Accented inputs are built with chr() so the test does not depend on encoding.
"""

from __future__ import annotations

import re

from chronovista.services.entity_mention_scan_service import _fold_diacritics

NBSP = chr(0x00A0)
ZWSP = chr(0x200B)
COMBINING_ACUTE = chr(0x0301)


class TestWhitespaceFold:
    def test_newline_collapses_to_single_space(self) -> None:
        assert _fold_diacritics("Foo\nBar")[0] == "Foo Bar"

    def test_nbsp_collapses_to_space(self) -> None:
        assert _fold_diacritics("Foo" + NBSP + "Bar")[0] == "Foo Bar"

    def test_multiple_whitespace_collapses(self) -> None:
        assert _fold_diacritics("a  \n\t b")[0] == "a b"

    def test_zero_width_stripped(self) -> None:
        assert _fold_diacritics("Fo" + ZWSP + "o")[0] == "Foo"

    def test_diacritics_and_whitespace_together(self) -> None:
        # "Café\nBar" (decomposed é) -> "Cafe Bar"
        raw = "Cafe" + COMBINING_ACUTE + "\nBar"
        assert _fold_diacritics(raw)[0] == "Cafe Bar"

    def test_offset_map_length_matches_folded(self) -> None:
        folded, offset_map = _fold_diacritics("Foo\nBar")
        assert len(offset_map) == len(folded)


class TestOffsetMapBackToRaw:
    def test_match_across_newline_slices_raw_span(self) -> None:
        raw = "visited Foo\nBar today"
        folded, offset_map = _fold_diacritics(raw)
        assert folded == "visited Foo Bar today"
        # A folded regex with a literal space matches the split name.
        m = re.search(r"\bFoo Bar\b", folded)
        assert m is not None
        raw_start = offset_map[m.start()]
        raw_end = offset_map[m.end() - 1] + 1
        assert raw[raw_start:raw_end] == "Foo\nBar"

    def test_match_across_nbsp_slices_raw_span(self) -> None:
        raw = "Foo" + NBSP + "Bar"
        folded, offset_map = _fold_diacritics(raw)
        m = re.search(r"\bFoo Bar\b", folded)
        assert m is not None
        raw_start = offset_map[m.start()]
        raw_end = offset_map[m.end() - 1] + 1
        assert raw[raw_start:raw_end] == raw  # spans the whole "Foo Bar"


class TestRegressionSingleSpaced:
    def test_ordinary_single_spaced_text_unchanged(self) -> None:
        # The common case must be byte-identical to the diacritic-only fold.
        folded, offset_map = _fold_diacritics("hello world")
        assert folded == "hello world"
        assert len(offset_map) == len(folded)
