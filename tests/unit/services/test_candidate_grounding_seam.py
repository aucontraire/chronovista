"""Grounding-seam equality test (Feature 096, T011, Constitution V).

Proves the candidate grounding uses the SAME detection rule as the scanner, not a
fork: the ``_CorpusIndex`` salience count must equal a direct, independent run of
the shared ``_build_entity_pattern`` + ``_compile_entity_regex`` + ``_fold_diacritics``
over the same corpus. If the inverted-index pre-filter ever diverged from the real
rule, this test fails. Pure functions — no DB.
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
_CORPUS = [
    ("v1", "Acme Corporation launches a product", "more about Acme Corporation here"),
    ("v2", "A profile of Cafe Central", "the famous café central reviewed"),
    ("v3", "unrelated content", "nothing matching"),
    ("v4", "ACME everywhere", "acme acme acme"),
    ("v5", "Beta Theta news", None),
]


def _reference_hits(name: str, qid: str) -> int:
    """Independently reproduce the shared detection rule and count distinct videos."""
    pattern = _build_entity_pattern(
        entity_id=uuid.uuid5(_PATTERN_NS, qid),
        canonical_name=name,
        entity_type="other",
        names=[name],
        case_sensitive_names=set(),
        exclusion_patterns=[],
    )
    regex = _compile_entity_regex(pattern)
    hits = 0
    for _vid, title, description in _CORPUS:
        folded, _ = _fold_diacritics(f"{title} {description or ''}")
        if regex.search(folded):
            hits += 1
    return hits


@pytest.mark.parametrize(
    "name",
    [
        "Acme Corporation",
        "Acme",
        "Cafe Central",  # fold must match "café central"
        "Beta Theta",
        "Nonexistent Name",
    ],
)
def test_index_salience_matches_direct_rule(name: str) -> None:
    index = _CorpusIndex(_CORPUS)
    qid = "Q" + str(abs(hash(name)) % 100000)
    index_hits, _specificity = index.salience(qid, name, "other")
    assert index_hits == _reference_hits(name, qid)


def test_accented_corpus_is_matched_by_unaccented_name() -> None:
    index = _CorpusIndex(_CORPUS)
    hits, _specificity = index.salience("Q1", "Cafe Central", "other")
    assert hits >= 1  # "café central" in v2 is matched by the folded "cafe central"
