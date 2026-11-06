"""Corpus-sources contract guard (Feature 106, Constitution v1.4.0 committed contract).

``CORPUS_SOURCES`` is the single committed home for "which text the grounding corpus searches."
The zero-salience triage bucket means "no match in ANY of these," and the user-facing label is
derived from this list (exposed on the candidate summary API) rather than hand-written — the fix
for a label that drifted from the corpus twice (v0.113.2, and again when transcripts were added).

This guard ties ``CORPUS_SOURCES`` to the per-source fields of ``_Salience`` — the fields
``_CorpusIndex.salience`` actually populates. Adding a fourth fold (a new ``_Salience`` per-source
field) without naming it in ``CORPUS_SOURCES``, or renaming a source, makes ``CORPUS_SOURCES`` and
the derived expectation diverge and fails this test. That is the mutation check: the label can no
longer silently fall out of step with the corpus. Pure data; no DB, no network.
"""

from __future__ import annotations

from chronovista.services.candidate_suggestion_service import (
    _SALIENCE_NON_SOURCE_FIELDS,
    CORPUS_SOURCES,
    _Salience,
)


def test_corpus_sources_match_salience_per_source_fields() -> None:
    expected = tuple(
        field for field in _Salience._fields if field not in _SALIENCE_NON_SOURCE_FIELDS
    )
    assert expected == CORPUS_SOURCES, (
        "CORPUS_SOURCES must name exactly the per-source folds _CorpusIndex.salience populates "
        "(the _Salience per-source fields). A new fold added to _Salience without updating "
        "CORPUS_SOURCES — or a renamed/removed source — makes the user-facing label drift from "
        "the actual corpus, which is exactly what this contract guards."
    )


def test_transcript_is_a_corpus_source() -> None:
    """The specific drift this release fixes: transcripts are now searched, so the label must
    name them. Removing 'transcript' from the corpus (reverting Feature 106) fails this.
    """
    assert "transcript" in CORPUS_SOURCES
