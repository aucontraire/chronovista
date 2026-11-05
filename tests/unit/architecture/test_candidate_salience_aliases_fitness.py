"""Salience alias-grounding fitness guard (bug fix: candidate salience dropped aliases).

The candidate grounder (``_CorpusIndex.salience``) shares ``_build_entity_pattern`` with the
scanner, but a shared function is not shared behaviour: the scanner feeds it canonical name +
alias rows, while the grounder once fed it ``names=[label]`` only. Entities whose corpus mentions
use a short form / acronym then grounded nowhere (measured 3.8% vs 17.5% salience>0 on an
institution sample).

Unlike the seam-equality test (``tests/unit/services/test_candidate_grounding_seam.py``), which
proves the index agrees with the direct rule and so stays green if BOTH sides drop aliases
together, this asserts an ABSOLUTE property: a candidate whose label is absent from the corpus but
whose ALIAS is present must score salience > 0. Reverting the fix — ``names=[name, *aliases]`` back
to ``names=[name]``, or the per-alternative token pre-filter back to the primary-name pre-filter —
drops this to 0 and fails. That is the mutation check Constitution v1.3.0 requires. Pure function:
no DB, no network, so it survives a fresh clone and runs in CI. Placeholder names only — no
library content.
"""

from __future__ import annotations

from chronovista.services.candidate_suggestion_service import _CorpusIndex

# The label's tokens appear nowhere in the corpus; only the acronym alias does.
_CORPUS = [
    ("v1", "The GSO annual report is out", "GSO featured in coverage"),
    ("v2", "unrelated content here", "nothing to match"),
]
_LABEL = "Giant Systems Organization"  # synthetic placeholder
_ALIAS = "GSO"


def test_salience_counts_alias_only_matches() -> None:
    index = _CorpusIndex(_CORPUS)

    label_only, _ = index.salience("Q1", _LABEL, "other", [])
    assert label_only == 0, (
        "the label's tokens are absent from the corpus — label-only salience must be 0, "
        "or this guard proves nothing"
    )

    with_alias, _ = index.salience("Q1", _LABEL, "other", [_ALIAS])
    assert with_alias >= 1, (
        "candidate salience must match the ALIAS set, not the label alone — reverting the "
        "aliases fix (names=[name], or a primary-name-only token pre-filter) makes this 0"
    )
