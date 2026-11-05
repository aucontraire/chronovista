"""Grounding-seam equality test (Feature 096, T011, Constitution V).

Proves the candidate grounding uses the SAME detection rule as the scanner, not a
fork: the ``_CorpusIndex`` salience count must equal a direct, independent run of
the shared ``_build_entity_pattern`` + ``_compile_entity_regex`` + ``_fold_diacritics``
over the same corpus — for a candidate's FULL name set (canonical label + Wikidata
aliases), not the label alone. If the inverted-index pre-filter ever diverged from the
real rule — including by starving an alias whose tokens the label lacks — this test
fails. Pure functions — no DB.

The reference oracle intentionally takes aliases too: an earlier version built it from
``names=[name]``, so it agreed with the (then also alias-blind) index while BOTH silently
dropped aliases — a blind spot that let the institution 3.8%-vs-17.5% salience bug sit in a
file whose whole job is to guard this seam.
"""

from __future__ import annotations

import uuid

import pytest

from chronovista.services.candidate_suggestion_service import _PATTERN_NS, _CorpusIndex
from chronovista.services.entity_mention_scan_service import (
    _build_entity_pattern,
    _compile_entity_regex,
    _fold_diacritics,
)

# Name-free placeholder corpus (title, description); accents + case exercise the fold.
# v6 carries ONLY an acronym that appears in none of the full names — the alias-only case.
_CORPUS = [
    ("v1", "Acme Corporation launches a product", "more about Acme Corporation here"),
    ("v2", "A profile of Cafe Central", "the famous café central reviewed"),
    ("v3", "unrelated content", "nothing matching"),
    ("v4", "ACME everywhere", "acme acme acme"),
    ("v5", "Beta Theta news", None),
    ("v6", "The GSO annual report", "GSO is everywhere this year"),
]


def _reference_hits(name: str, aliases: list[str], qid: str) -> int:
    """Independently reproduce the shared detection rule over the full name set.

    No inverted-index pre-filter — scans every corpus video — so this is the oracle the
    index's token pre-filter must agree with, aliases included.
    """
    pattern = _build_entity_pattern(
        entity_id=uuid.uuid5(_PATTERN_NS, qid),
        canonical_name=name,
        entity_type="other",
        names=[name, *aliases],
        case_sensitive_names=set(),
        exclusion_patterns=[],
    )
    if not pattern.pg_pattern:
        return 0
    regex = _compile_entity_regex(pattern)
    hits = 0
    for _vid, title, description in _CORPUS:
        folded, _ = _fold_diacritics(f"{title} {description or ''}")
        if regex.search(folded):
            hits += 1
    return hits


@pytest.mark.parametrize(
    ("name", "aliases"),
    [
        ("Acme Corporation", []),
        ("Acme", []),
        ("Cafe Central", []),  # fold must match "café central"
        ("Beta Theta", []),
        ("Nonexistent Name", []),
        # Alias whose tokens the label lacks: the label grounds nowhere, the alias matches
        # v6. The per-alternative pre-filter must not starve it (the bug this guards).
        ("Giant Systems Organization", ["GSO"]),
        # Multiple aliases, mixed hits across v1/v4/v6.
        ("Acme Corporation", ["Acme", "GSO"]),
    ],
)
def test_index_salience_matches_direct_rule(name: str, aliases: list[str]) -> None:
    index = _CorpusIndex(_CORPUS)
    qid = "Q" + str(abs(hash((name, tuple(aliases)))) % 100000)
    index_hits, _specificity = index.salience(qid, name, "other", aliases)
    assert index_hits == _reference_hits(name, aliases, qid)


def test_accented_corpus_is_matched_by_unaccented_name() -> None:
    index = _CorpusIndex(_CORPUS)
    hits, _specificity = index.salience("Q1", "Cafe Central", "other", [])
    assert hits >= 1  # "café central" in v2 is matched by the folded "cafe central"
