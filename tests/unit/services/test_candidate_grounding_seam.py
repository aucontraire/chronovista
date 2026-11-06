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

Feature 106 adds transcript as a third per-source fold. The corpus tuples are now
``(video_id, title, description, transcript)`` and the oracle scans all three sources
SEPARATELY (no cross-source concatenation), mirroring ``_CorpusIndex``.
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

# Name-free placeholder corpus (title, description, transcript); accents + case exercise the fold.
# v6 carries ONLY an acronym (alias-only case). v7 carries a name ONLY in its transcript.
_CORPUS = [
    (
        "v1",
        "Acme Corporation launches a product",
        "more about Acme Corporation here",
        None,
    ),
    ("v2", "A profile of Cafe Central", "the famous café central reviewed", None),
    ("v3", "unrelated content", "nothing matching", "idle transcript chatter"),
    ("v4", "ACME everywhere", "acme acme acme", None),
    ("v5", "Beta Theta news", None, None),
    ("v6", "The GSO annual report", "GSO is everywhere this year", None),
    ("v7", "a plain title", "a plain description", "we talk about Delta Umbra today"),
]


def _reference_hits(name: str, aliases: list[str], qid: str) -> int:
    """Independently reproduce the shared detection rule over the full name set.

    No inverted-index pre-filter — scans every corpus video — so this is the oracle the
    index's token pre-filter must agree with, aliases included. Title, description, and
    transcript are scanned SEPARATELY (as the index does); a video counts once if the name
    matches in ANY source (the pooled union).
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
    for _vid, title, description, transcript in _CORPUS:
        # Match each source SEPARATELY (as the index now does); concatenating them would allow a
        # false match spanning a cross-source seam.
        folded_title, _ = _fold_diacritics(title)
        folded_desc, _ = _fold_diacritics(description or "")
        folded_transcript, _ = _fold_diacritics(transcript or "")
        if (
            regex.search(folded_title)
            or regex.search(folded_desc)
            or regex.search(folded_transcript)
        ):
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
        # Transcript-only name: present in v7's transcript, absent from every title/description.
        ("Delta Umbra", []),
    ],
)
def test_index_salience_matches_direct_rule(name: str, aliases: list[str]) -> None:
    index = _CorpusIndex(_CORPUS)
    qid = "Q" + str(abs(hash((name, tuple(aliases)))) % 100000)
    s = index.salience(qid, name, "other", aliases)
    assert s.pooled == _reference_hits(name, aliases, qid)
    # transcript is now a measured corpus source (Feature 106): always an int, never None.
    assert s.transcript is not None
    # Per-source parts overlap, so they never sum below the pooled total (D1).
    assert s.title + s.description + s.transcript >= s.pooled


def test_transcript_only_name_grounds_via_transcript() -> None:
    """A name only in a transcript scores a transcript hit and a positive pooled total."""
    index = _CorpusIndex(_CORPUS)
    s = index.salience("Q1", "Delta Umbra", "other", [])
    assert s.title == 0 and s.description == 0
    assert s.transcript == 1
    assert s.pooled == 1


def test_accented_corpus_is_matched_by_unaccented_name() -> None:
    index = _CorpusIndex(_CORPUS)
    # "café central" in v2's title is matched by the folded "cafe central".
    assert index.salience("Q1", "Cafe Central", "other", []).pooled >= 1
