"""Unit tests for normalize_segment_text (Feature 076 / bug #293).

The normalizer collapses whitespace + strips invisible formatting characters +
applies NFC, without altering content. Non-ASCII inputs are built from explicit
code points (chr()) so the tests never depend on how this file is encoded.
"""

from __future__ import annotations

import re

from chronovista.utils.text import normalize_segment_text

NBSP = chr(0x00A0)  # non-breaking space
EM_SPACE = chr(0x2003)
ZWSP = chr(0x200B)
ZWNJ = chr(0x200C)
ZWJ = chr(0x200D)
BOM = chr(0xFEFF)
SOFT_HYPHEN = chr(0x00AD)
COMBINING_ACUTE = chr(0x0301)

E_ACUTE_PRECOMPOSED = chr(0x00E9)  # "é" as one code point
E_ACUTE_DECOMPOSED = "e" + COMBINING_ACUTE  # "e" + combining accent
CAFE_PRECOMPOSED = "caf" + E_ACUTE_PRECOMPOSED
CAFE_DECOMPOSED = "caf" + E_ACUTE_DECOMPOSED


class TestWhitespaceCollapse:
    def test_newline_becomes_space(self) -> None:
        assert normalize_segment_text("foo\nbar") == "foo bar"

    def test_tab_and_cr_become_space(self) -> None:
        assert normalize_segment_text("foo\tbar\r\nbaz") == "foo bar baz"

    def test_runs_collapse_to_single_space(self) -> None:
        assert normalize_segment_text("foo   bar") == "foo bar"
        assert normalize_segment_text("foo \n\t bar") == "foo bar"

    def test_nbsp_becomes_space(self) -> None:
        assert normalize_segment_text("a" + NBSP + "b") == "a b"

    def test_other_unicode_space_becomes_space(self) -> None:
        assert normalize_segment_text("a" + EM_SPACE + "b") == "a b"

    def test_leading_and_trailing_trimmed(self) -> None:
        assert normalize_segment_text("  foo bar  ") == "foo bar"
        assert normalize_segment_text("\n\tfoo ") == "foo"


class TestInvisibleStripping:
    def test_zero_width_chars_removed(self) -> None:
        for zw in (ZWSP, ZWNJ, ZWJ, BOM):
            assert normalize_segment_text("a" + zw + "b") == "ab"

    def test_soft_hyphen_removed(self) -> None:
        assert normalize_segment_text("stra" + SOFT_HYPHEN + "sse") == "strasse"

    def test_invisible_between_words_does_not_leave_double_space(self) -> None:
        assert normalize_segment_text("foo " + ZWSP + " bar") == "foo bar"


class TestNFC:
    def test_decomposed_accent_is_composed(self) -> None:
        assert E_ACUTE_DECOMPOSED != E_ACUTE_PRECOMPOSED  # genuinely different input
        assert normalize_segment_text(CAFE_DECOMPOSED) == CAFE_PRECOMPOSED

    def test_precomposed_is_unchanged(self) -> None:
        assert normalize_segment_text(CAFE_PRECOMPOSED) == CAFE_PRECOMPOSED


class TestContentPreserved:
    def test_accents_kept(self) -> None:
        assert (
            normalize_segment_text(CAFE_PRECOMPOSED + " au lait")
            == CAFE_PRECOMPOSED + " au lait"
        )

    def test_emoji_kept(self) -> None:
        emoji = chr(0x1F600)
        assert (
            normalize_segment_text("hi " + emoji + " there") == "hi " + emoji + " there"
        )

    def test_currency_and_symbols_kept(self) -> None:
        euro = chr(0x20AC)
        assert (
            normalize_segment_text("price 5" + euro + " or 5$")
            == "price 5" + euro + " or 5$"
        )

    def test_non_latin_kept(self) -> None:
        cjk = chr(0x65E5) + chr(0x672C) + chr(0x8A9E)
        assert normalize_segment_text(cjk) == cjk

    def test_ordinary_punctuation_kept(self) -> None:
        assert normalize_segment_text("a-b, c.") == "a-b, c."


class TestEdgeCases:
    def test_whitespace_only_becomes_empty(self) -> None:
        assert normalize_segment_text("   ") == ""
        assert normalize_segment_text("\n\t " + ZWSP) == ""

    def test_empty_string(self) -> None:
        assert normalize_segment_text("") == ""

    def test_idempotent(self) -> None:
        raw = "  foo\n bar" + ZWSP + "  baz" + SOFT_HYPHEN + " "
        once = normalize_segment_text(raw)
        assert normalize_segment_text(once) == once


class TestAssumptions:
    def test_backslash_s_matches_nbsp(self) -> None:
        # The normalizer relies on \s matching U+00A0 in str mode; prove it.
        assert re.fullmatch(r"\s", NBSP) is not None


class TestNFCOrderRegression:
    """Regression for the NFC-order idempotency bug (#293 adversarial catch).

    A zero-width char between a base letter and its combining mark must be
    stripped BEFORE NFC, so NFC can compose the pair. If NFC ran first the pair
    would stay decomposed and a second pass would compose it — not idempotent,
    and it would re-write rows in the backfill.
    """

    def test_zero_width_between_base_and_combining_mark_composes(self) -> None:
        raw = "e" + ZWSP + COMBINING_ACUTE  # e + ZWSP + combining acute
        out = normalize_segment_text(raw)
        assert out == E_ACUTE_PRECOMPOSED  # composed "é" (U+00E9), NFC-correct
        assert normalize_segment_text(out) == out  # idempotent

    def test_output_is_nfc_normalized(self) -> None:
        import unicodedata

        raw = "cafe" + ZWSP + COMBINING_ACUTE
        out = normalize_segment_text(raw)
        assert unicodedata.is_normalized("NFC", out)
        assert normalize_segment_text(out) == out
