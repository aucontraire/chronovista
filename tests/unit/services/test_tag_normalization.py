"""
Tests for Tag Normalization Service.

Covers the 9-step normalization pipeline (``TagNormalizationService.normalize``)
and the standalone ``selective_strip_diacritics`` utility.  Edge-case and
idempotency tests are included; hypothesis / multilang tests live in
separate task files (T024, T025).

References
----------
- T004: Unit test task for tag normalization
- FR-002: Empty / whitespace-only input returns ``None``
- FR-006: ``selective_strip_diacritics`` standalone utility
- FR-007: Idempotency guarantee
- FR-008: Pure function — no I/O, no database
"""

from __future__ import annotations

import unicodedata

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from chronovista.services.tag_normalization import (
    SAFE_TO_STRIP,
    TagNormalizationService,
    selective_strip_diacritics,
)


@pytest.fixture()
def svc() -> TagNormalizationService:
    """Provide a fresh ``TagNormalizationService`` instance."""
    return TagNormalizationService()


# =========================================================================
# TestNormalize — 9-step pipeline
# =========================================================================


class TestNormalize:
    """Tests for ``TagNormalizationService.normalize``."""

    # ----- basic transformations ------------------------------------------

    def test_case_folding(self, svc: TagNormalizationService) -> None:
        """Upper-case input is case-folded to lower case."""
        assert svc.normalize("MEXICO") == "mexico"

    def test_hashtag_stripping(self, svc: TagNormalizationService) -> None:
        """A single leading '#' is removed (accent on 'e' is Tier 1)."""
        assert svc.normalize("#Mexico") == "mexico"

    def test_tilde_preserved(self, svc: TagNormalizationService) -> None:
        """Spanish tilde (Tier 2) survives normalization."""
        assert svc.normalize("año") == "año"

    def test_cedilla_preserved(self, svc: TagNormalizationService) -> None:
        """French cedilla (Tier 2) survives normalization."""
        assert svc.normalize("façade") == "façade"

    def test_umlaut_stripped(self, svc: TagNormalizationService) -> None:
        """German umlaut / diaeresis (Tier 1) is stripped."""
        assert svc.normalize("München") == "munchen"

    def test_empty_string_returns_none(self, svc: TagNormalizationService) -> None:
        """Empty string yields ``None``."""
        assert svc.normalize("") is None

    def test_whitespace_only_returns_none(self, svc: TagNormalizationService) -> None:
        """Whitespace-only input yields ``None``."""
        assert svc.normalize("  ") is None

    def test_composed_transformations(self, svc: TagNormalizationService) -> None:
        """Hashtag + accent + case fold: '#MEXICO' -> 'mexico'."""
        assert svc.normalize("#MÉXICO") == "mexico"

    # ----- idempotency (FR-007) ------------------------------------------

    @pytest.mark.parametrize(
        "raw",
        [
            "MEXICO",
            "#Mexico",
            "año",
            "façade",
            "München",
            "#MÉXICO",
            "mex\u200bico",
            "hello\u00A0world",
        ],
        ids=[
            "upper",
            "hashtag",
            "tilde",
            "cedilla",
            "umlaut",
            "composed",
            "zero-width",
            "nbsp",
        ],
    )
    def test_idempotency(self, svc: TagNormalizationService, raw: str) -> None:
        """normalize(normalize(x)) == normalize(x) for various inputs."""
        first = svc.normalize(raw)
        if first is None:
            # If the first pass is None, a second pass on "" should also be None,
            # but the contract says we pass a str — so treat None sentinel consistently.
            assert first is None
        else:
            assert svc.normalize(first) == first

    def test_idempotency_double_hash_converges(
        self, svc: TagNormalizationService
    ) -> None:
        """'##double' converges after two passes (output with leading '#' is not stable)."""
        first = svc.normalize("##double")
        assert first == "#double"
        second = svc.normalize(first)
        assert second == "double"
        # Third pass is stable
        assert svc.normalize(second) == second

    # ----- edge cases: hashtag stripping ---------------------------------

    def test_triple_hash_strips_one(self, svc: TagNormalizationService) -> None:
        """'###' strips one '#' leaving '##'."""
        assert svc.normalize("###") == "##"

    def test_double_hash_tag(self, svc: TagNormalizationService) -> None:
        """'##double' strips one '#' leaving '#double'."""
        assert svc.normalize("##double") == "#double"

    # ----- edge cases: zero-width characters -----------------------------

    def test_zero_width_space_removal(self, svc: TagNormalizationService) -> None:
        """Zero-width space (U+200B) inside a word is removed."""
        assert svc.normalize("mex\u200bico") == "mexico"

    def test_zero_width_non_joiner_removal(
        self, svc: TagNormalizationService
    ) -> None:
        """Zero-width non-joiner (U+200C) is removed."""
        assert svc.normalize("test\u200cvalue") == "testvalue"

    def test_zero_width_joiner_removal(self, svc: TagNormalizationService) -> None:
        """Zero-width joiner (U+200D) is removed."""
        assert svc.normalize("test\u200dvalue") == "testvalue"

    def test_bom_removal(self, svc: TagNormalizationService) -> None:
        """BOM / zero-width no-break space (U+FEFF) is removed."""
        assert svc.normalize("\uFEFFhello") == "hello"

    # ----- edge cases: whitespace normalization --------------------------

    def test_non_breaking_space_normalization(
        self, svc: TagNormalizationService
    ) -> None:
        """Non-breaking space (U+00A0) is replaced with regular space."""
        assert svc.normalize("hello\u00A0world") == "hello world"

    def test_tab_normalization(self, svc: TagNormalizationService) -> None:
        """Tab character is replaced with regular space."""
        assert svc.normalize("hello\tworld") == "hello world"

    def test_multiple_spaces_collapse(self, svc: TagNormalizationService) -> None:
        """Multiple spaces collapse to a single space."""
        assert svc.normalize("hello   world") == "hello world"

    # ----- edge case: single Tier 1 mark only ----------------------------

    def test_single_tier1_mark_returns_none(
        self, svc: TagNormalizationService
    ) -> None:
        """A string consisting only of a Tier 1 combining mark yields None."""
        # Compose a string that is just the combining acute accent
        assert svc.normalize("\u0301") is None


# =========================================================================
# TestSelectiveStripDiacritics — standalone utility (FR-006)
# =========================================================================


class TestSelectiveStripDiacritics:
    """Tests for the ``selective_strip_diacritics`` standalone utility."""

    # ----- Tier 1 marks removed ------------------------------------------

    def test_acute_accent_removed(self) -> None:
        """Acute accent (Tier 1) is stripped: 'é' -> 'e'."""
        assert selective_strip_diacritics("é") == "e"

    def test_grave_accent_removed(self) -> None:
        """Grave accent (Tier 1) is stripped: 'è' -> 'e'."""
        assert selective_strip_diacritics("è") == "e"

    def test_circumflex_removed(self) -> None:
        """Circumflex (Tier 1) is stripped: 'ê' -> 'e'."""
        assert selective_strip_diacritics("ê") == "e"

    def test_diaeresis_removed(self) -> None:
        """Diaeresis (Tier 1) is stripped: 'ü' -> 'u'."""
        assert selective_strip_diacritics("ü") == "u"

    def test_macron_removed(self) -> None:
        """Macron (Tier 1) is stripped: 'ā' -> 'a'."""
        assert selective_strip_diacritics("ā") == "a"

    def test_breve_removed(self) -> None:
        """Breve (Tier 1) is stripped: 'ă' -> 'a'."""
        assert selective_strip_diacritics("ă") == "a"

    def test_double_acute_removed(self) -> None:
        """Double acute (Tier 1) is stripped: 'ő' -> 'o'."""
        assert selective_strip_diacritics("ő") == "o"

    def test_double_grave_removed(self) -> None:
        """Double grave (Tier 1) is stripped."""
        # U+0200 = A with double grave -> 'A' after stripping
        assert selective_strip_diacritics("\u0200") == "A"

    # ----- Tier 2 combining marks preserved ------------------------------

    def test_tilde_preserved(self) -> None:
        """Combining tilde (Tier 2) is preserved: 'ñ' stays 'ñ'."""
        assert selective_strip_diacritics("ñ") == "ñ"

    def test_cedilla_preserved(self) -> None:
        """Combining cedilla (Tier 2) is preserved: 'ç' stays 'ç'."""
        assert selective_strip_diacritics("ç") == "ç"

    def test_ogonek_preserved(self) -> None:
        """Combining ogonek (Tier 2) is preserved: 'ą' stays 'ą'."""
        assert selective_strip_diacritics("ą") == "ą"

    def test_caron_preserved(self) -> None:
        """Combining caron (Tier 2) is preserved: 'č' stays 'č'."""
        assert selective_strip_diacritics("č") == "č"

    def test_dot_above_preserved(self) -> None:
        """Combining dot above (Tier 2) is preserved: 'ż' stays 'ż'."""
        assert selective_strip_diacritics("ż") == "ż"

    def test_ring_above_preserved(self) -> None:
        """Combining ring above (Tier 2) is preserved: 'å' stays 'å'."""
        assert selective_strip_diacritics("å") == "å"

    # ----- Tier 2 base characters preserved ------------------------------

    def test_o_stroke_preserved(self) -> None:
        """ø (U+00F8) is a base character and survives: 'ø' stays 'ø'."""
        assert selective_strip_diacritics("ø") == "ø"

    def test_a_ring_preserved(self) -> None:
        """å (U+00E5) survives (ring above is Tier 2)."""
        assert selective_strip_diacritics("å") == "å"

    def test_ae_ligature_preserved(self) -> None:
        """æ (U+00E6) is a base character and survives."""
        assert selective_strip_diacritics("æ") == "æ"

    def test_l_stroke_preserved(self) -> None:
        """ł (U+0142) is a base character and survives."""
        assert selective_strip_diacritics("ł") == "ł"

    # ----- Tier 3 marks preserved ----------------------------------------

    def test_tier3_combining_marks_preserved(self) -> None:
        """Arbitrary Tier 3 combining marks (not in Tier 1 or Tier 2) survive."""
        # U+0325 = COMBINING RING BELOW (Tier 3)
        text_with_ring_below = "a\u0325"
        nfc = unicodedata.normalize("NFC", text_with_ring_below)
        result = selective_strip_diacritics(nfc)
        # The ring below should still be present
        decomposed = unicodedata.normalize("NFKD", result)
        assert "\u0325" in decomposed

    # ----- mixed input ---------------------------------------------------

    def test_mixed_tier1_and_tier2(self) -> None:
        """Tier 1 is removed while Tier 2 is preserved in the same word."""
        # 'Müñchen' has diaeresis (Tier 1) on u and tilde (Tier 2) on n
        result = selective_strip_diacritics("Müñchen")
        assert result == "Muñchen"


# =========================================================================
# TestSelectCanonicalForm — canonical form selection algorithm (FR-009)
# =========================================================================


class TestSelectCanonicalForm:
    """Tests for ``TagNormalizationService.select_canonical_form``."""

    # ----- US4 acceptance scenarios --------------------------------------

    def test_title_case_preferred(self, svc: TagNormalizationService) -> None:
        """Title case form is preferred when it exists."""
        forms = [("MEXICO", 203), ("Mexico", 412), ("mexico", 156)]
        assert svc.select_canonical_form(forms) == "Mexico"

    def test_alphabetical_tiebreaker_title_case(
        self, svc: TagNormalizationService
    ) -> None:
        """When title case forms have equal count, use alphabetical min."""
        forms = [("Mexico", 200), ("México", 200)]
        assert svc.select_canonical_form(forms) == "Mexico"

    def test_most_frequent_when_no_title_case(
        self, svc: TagNormalizationService
    ) -> None:
        """When no title case forms exist, pick most frequent."""
        forms = [("MEXICO", 500), ("mexico", 300)]
        assert svc.select_canonical_form(forms) == "MEXICO"

    def test_low_count_tag_frequency_applies(
        self, svc: TagNormalizationService
    ) -> None:
        """Frequency rule applies regardless of absolute count."""
        forms = [("TOPIC", 2), ("topic", 1)]
        assert svc.select_canonical_form(forms) == "TOPIC"

    def test_single_form(self, svc: TagNormalizationService) -> None:
        """Single form is returned as-is."""
        forms = [("hello", 1)]
        assert svc.select_canonical_form(forms) == "hello"

    # ----- edge cases ----------------------------------------------------

    def test_empty_list_raises_error(self, svc: TagNormalizationService) -> None:
        """Empty list raises ValueError."""
        with pytest.raises(ValueError, match="Cannot select canonical form from empty list"):
            svc.select_canonical_form([])

    def test_all_equal_counts_no_title_case(
        self, svc: TagNormalizationService
    ) -> None:
        """When all forms have equal count and none are title case, use alphabetical min."""
        forms = [("zebra", 10), ("apple", 10), ("banana", 10)]
        assert svc.select_canonical_form(forms) == "apple"

    def test_all_equal_counts_all_title_case(
        self, svc: TagNormalizationService
    ) -> None:
        """When all forms are title case with equal count, use alphabetical min."""
        forms = [("Zebra", 10), ("Apple", 10), ("Banana", 10)]
        assert svc.select_canonical_form(forms) == "Apple"

    def test_mixed_case_prefers_title_even_if_lower_count(
        self, svc: TagNormalizationService
    ) -> None:
        """Title case is preferred even if it has lower count than non-title forms."""
        forms = [("TOPIC", 1000), ("topic", 500), ("Topic", 50)]
        assert svc.select_canonical_form(forms) == "Topic"

    def test_multiple_title_case_picks_highest_count(
        self, svc: TagNormalizationService
    ) -> None:
        """Among multiple title case forms, pick the one with highest count."""
        forms = [("Mexico", 100), ("México", 200), ("mexico", 500)]
        assert svc.select_canonical_form(forms) == "México"


# =========================================================================
# TestMultilang* — multi-language diacritic preservation tests (T024)
# =========================================================================


class TestMultilangSpanish:
    """Spanish diacritic handling tests."""

    def test_tilde_preserved(self, svc: TagNormalizationService) -> None:
        """Spanish tilde is preserved in normalization."""
        assert svc.normalize("año") == "año"

    def test_acute_stripped_tilde_preserved(
        self, svc: TagNormalizationService
    ) -> None:
        """Acute accent (Tier 1) is stripped, tilde (Tier 2) preserved, casefolded."""
        assert svc.normalize("España") == "españa"


class TestMultilangPortuguese:
    """Portuguese diacritic handling tests."""

    def test_cedilla_preserved(self, svc: TagNormalizationService) -> None:
        """Portuguese cedilla is preserved in normalization."""
        assert svc.normalize("façade") == "façade"

    def test_circumflex_stripped(self, svc: TagNormalizationService) -> None:
        """Circumflex (Tier 1) is stripped from Portuguese text."""
        assert svc.normalize("avô") == "avo"


class TestMultilangGerman:
    """German diacritic handling tests."""

    def test_umlaut_u_stripped(self, svc: TagNormalizationService) -> None:
        """German diaeresis/umlaut on 'ü' (Tier 1) is stripped."""
        assert svc.normalize("München") == "munchen"

    def test_umlaut_u_lowercase_stripped(self, svc: TagNormalizationService) -> None:
        """German diaeresis on lowercase 'ü' (Tier 1) is stripped."""
        assert svc.normalize("über") == "uber"


class TestMultilangNordic:
    """Nordic language diacritic handling tests."""

    def test_o_stroke_preserved(self, svc: TagNormalizationService) -> None:
        """Norwegian/Danish ø (o-stroke) is preserved as a base character."""
        assert svc.normalize("ø") == "ø"

    def test_a_ring_preserved(self, svc: TagNormalizationService) -> None:
        """Nordic å (a-ring) is preserved (ring above is Tier 2)."""
        assert svc.normalize("å") == "å"

    def test_ae_ligature_preserved(self, svc: TagNormalizationService) -> None:
        """Nordic æ (ae-ligature) is preserved as a base character."""
        assert svc.normalize("æ") == "æ"


class TestMultilangPolish:
    """Polish diacritic handling tests."""

    def test_l_stroke_preserved(self, svc: TagNormalizationService) -> None:
        """Polish ł (l-stroke) is preserved as a base character."""
        assert svc.normalize("ł") == "ł"


class TestZeroFalseMerges:
    """SC-002: Verify that semantically distinct tags remain distinct."""

    def test_ano_vs_ano_different(self, svc: TagNormalizationService) -> None:
        """Spanish 'año' and 'ano' must NOT produce the same normalized output."""
        result_with_tilde = svc.normalize("año")
        result_without_tilde = svc.normalize("ano")
        assert result_with_tilde != result_without_tilde
        assert result_with_tilde == "año"
        assert result_without_tilde == "ano"

    def test_facade_vs_facade_different(self, svc: TagNormalizationService) -> None:
        """French 'façade' and 'facade' must remain distinct."""
        result_with_cedilla = svc.normalize("façade")
        result_without_cedilla = svc.normalize("facade")
        assert result_with_cedilla != result_without_cedilla
        assert result_with_cedilla == "façade"
        assert result_without_cedilla == "facade"


# =========================================================================
# TestHypothesisProperties — property-based tests (T025)
# =========================================================================


class TestHypothesisProperties:
    """Property-based tests using Hypothesis for normalization invariants."""

    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=500)
    def test_idempotency(self, text: str) -> None:
        """SC-003: normalize(normalize(x)) == normalize(x) for all non-empty inputs."""
        svc = TagNormalizationService()
        result = svc.normalize(text)
        if result is not None:
            assert svc.normalize(result) == result

    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=500)
    def test_no_tier1_marks_in_output(self, text: str) -> None:
        """US5 AS-6: Normalized output must not contain any Tier 1 combining marks."""
        svc = TagNormalizationService()
        result = svc.normalize(text)
        if result is not None:
            decomposed = unicodedata.normalize("NFD", result)
            for char in decomposed:
                assert char not in SAFE_TO_STRIP
