"""Fitness guards for the ASR-error-form admission gates (Feature 111).

`_asr_form_admissible` is the sole decision for whether a registered ASR-error
form may be used as a match pattern. Three conjunctive gates (FR-002 multiword,
FR-002a one-char token, FR-003 all-common) each guard a distinct precision
failure. These tests are mutation-verified: each "excluded" assertion flips to
admissible if its gate is removed, so a future edit that drops a gate turns a
test RED.

They are deliberately separate assertions, one per gate, so a single failing
gate cannot hide behind another (the recurring lesson of this feature: bundled
checks hide).
"""

from __future__ import annotations

from chronovista.services.entity_mention_scan_service import _asr_form_admissible


class TestMultiwordGate:
    """FR-002: a single-word form is never admissible (mutation-verifier)."""

    def test_single_word_form_excluded(self) -> None:
        # Remove the multiword gate and this becomes admissible.
        assert _asr_form_admissible("smithe") is False

    def test_multiword_form_admitted(self) -> None:
        assert _asr_form_admissible("john smithe") is True

    def test_leading_trailing_space_is_still_single_word(self) -> None:
        assert _asr_form_admissible("  smithe  ") is False


class TestOneCharTokenGate:
    """FR-002a: a form with a <=1-char token is junk (mutation-verifier)."""

    def test_one_char_token_excluded(self) -> None:
        # A multiword form carrying a stray one-char token ("q").
        # Remove the one-char gate and this becomes admissible.
        assert _asr_form_admissible("zelkov q") is False

    def test_no_one_char_token_admitted(self) -> None:
        assert _asr_form_admissible("john smithe") is True


class TestCommonWordGate:
    """FR-003: a form whose every token is common is excluded (mutation-verifier)."""

    def test_all_common_form_excluded(self) -> None:
        # Every token is a stopword -> no distinctive name token.
        # Remove the all-common gate and this becomes admissible.
        assert _asr_form_admissible("of the") is False

    def test_particle_plus_distinctive_token_is_NOT_collateral(self) -> None:
        # The particle-non-collateral guarantee: a 2-char particle ("de") must
        # survive (we gate on <=1-char and on all-common, never on <=2-char
        # length — a length rule would wrongly delete legitimate particle names).
        assert _asr_form_admissible("de zelkov") is True
        assert _asr_form_admissible("al qophine") is True

    def test_known_deferred_common_noun_case(self) -> None:
        # A form whose tokens are ordinary common NOUNS ("paper pencil") is NOT
        # yet excluded: common nouns are not in the function-word stopword seed,
        # so the all-common gate passes them. Catching this class is the
        # guard-sizing task (T029) that extends _COMMON_WORDS and gates the
        # backfill; documented here so the current scope is explicit.
        assert _asr_form_admissible("paper pencil") is True
