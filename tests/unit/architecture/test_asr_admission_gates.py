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

    def test_common_nouns_remain_admitted_by_design(self) -> None:
        # A form whose tokens are ordinary common NOUNS ("paper pencil") stays
        # admitted BY DESIGN. The T029 dictionary-wide noun extension was REJECTED:
        # a /usr/share/dict/words proxy excludes genuine recoveries (a real first
        # name beside an ordinary-word surname), so the gate uses a curated
        # closed-class function-word set, never a dictionary. A false admission of
        # this shape is caught downstream by the SC-001 precision audit, not here.
        assert _asr_form_admissible("paper pencil") is True


class TestSpanishCommonWordGate:
    """FR-003 over the Spanish function-word set (mutation-verifier).

    English-only _COMMON_WORDS left this gate inert on the bilingual corpus. The
    Spanish set makes it do work: a two-word all-common Spanish form (a function
    word beside the ubiquitous "fe"/"faith") carries no name anchor and is excluded.
    Remove _ES_COMMON_WORDS from _COMMON_WORDS and ``test_spanish_all_common_excluded``
    flips to admissible.
    """

    def test_spanish_all_common_excluded(self) -> None:
        # Every token is a Spanish high-frequency word -> no distinctive name token.
        # ("fe de" = "faith of"; "de la" = "of the".) Admitting such a form would
        # tag ordinary Spanish prose as a person. Remove the Spanish set -> admitted.
        assert _asr_form_admissible("fe de") is False
        assert _asr_form_admissible("de la") is False

    def test_spanish_distinctive_token_still_admitted(self) -> None:
        # A Spanish particle beside a distinctive (invented) token survives, so a
        # real recovery is not over-excluded (the Spanish set is not over-broad).
        assert _asr_form_admissible("fe de zelkov") is True
        assert _asr_form_admissible("de la marlowe") is True
