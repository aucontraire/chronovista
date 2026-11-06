"""Transcript corpus assembly for candidate grounding (Feature 106).

Two layers, both testable without a database:

* ``_assemble_one_video`` — the pure per-video unit. Three requirements converge on it:
  - FR-001 effective text: a corrected segment contributes ``corrected_text``, not raw ``text``,
    through the single ``effective_text`` rule, joined by the single ``SEGMENT_SEPARATOR`` (so the
    assembled string is byte-identical to what the scanner reads).
  - FR-002 no quality gate: every segment of a non-excluded language contributes.
  - FR-003 language exclusion: a segment whose language the user excluded contributes nothing.
    This is the DISCRIMINATING test — on real data the owner excludes no language, so the
    restrictive branch never runs and only a synthetic excluded-language fixture can prove it.

* ``CandidateSuggestionService._stream_transcript_corpus`` — groups the streamed segment rows by
  video and assembles each via ``_assemble_one_video``. Tested with a fake streaming repo (an async
  generator) so the grouping + finalize-last-video logic is covered without a DB.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import Mock

import pytest

from chronovista.services.candidate_suggestion_service import (
    CandidateSuggestionService,
    _assemble_one_video,
)
from chronovista.services.transcript_text_index import SEGMENT_SEPARATOR

# Per-video segment tuples are (language_code, text, corrected_text, has_correction), in order.


def test_effective_text_prefers_correction() -> None:
    """FR-001: a corrected segment contributes its correction, not the raw text."""
    text = _assemble_one_video(
        [
            ("en", "Mangled Nayme speaking", "Corrected Name speaking", True),
            ("en", "and more raw text", None, False),
        ],
        frozenset(),
    )
    assert text == f"Corrected Name speaking{SEGMENT_SEPARATOR}and more raw text"
    assert text is not None and "Mangled Nayme" not in text


def test_segments_joined_by_single_separator_in_order() -> None:
    text = _assemble_one_video(
        [
            ("en", "first", None, False),
            ("en", "second", None, False),
            ("en", "third", None, False),
        ],
        frozenset(),
    )
    assert text == SEGMENT_SEPARATOR.join(["first", "second", "third"])


def test_excluded_language_contributes_nothing() -> None:
    """FR-003 discriminating test: an excluded-language segment is dropped.

    PROD excludes no language, so the filter is a pass-through on real data (output == input) and a
    correct filter is indistinguishable from a broken one without this synthetic fixture. An
    inverted filter would empty the corpus (loud); a pass-through is silent and wrong only once an
    exclude exists.
    """
    text = _assemble_one_video(
        [
            ("en", "included english content", None, False),
            ("de", "ausgeschlossener deutscher Inhalt", None, False),
        ],
        frozenset({"de"}),
    )
    assert text == "included english content"
    assert text is not None and "deutscher" not in text


def test_only_excluded_language_returns_none() -> None:
    text = _assemble_one_video(
        [("de", "nur deutscher Inhalt", None, False)], frozenset({"de"})
    )
    assert text is None  # no surviving segment → no transcript evidence


def test_no_quality_gate_all_segments_contribute() -> None:
    """FR-002: every non-excluded segment contributes regardless of origin (ASR or manual)."""
    text = _assemble_one_video(
        [
            ("en", "auto generated line", None, False),
            ("en", "manually written line", None, False),
        ],
        frozenset(),
    )
    assert text is not None
    assert "auto generated line" in text and "manually written line" in text


def test_empty_correction_falls_back_to_raw_text() -> None:
    """A segment flagged corrected but with no correction text falls back to raw (effective rule)."""
    text = _assemble_one_video([("en", "raw fallback text", None, True)], frozenset())
    assert text == "raw fallback text"


# --- streaming consumer (grouping) -------------------------------------------------


class _FakeTranscriptRepo:
    """A transcript repo whose stream yields pre-canned rows (no DB)."""

    def __init__(self, rows: list[tuple[str, str, int, str, str | None, bool]]) -> None:
        self._rows = rows

    async def stream_segments_for_grounding(
        self, session: object, *, batch_size: int = 10_000
    ) -> AsyncIterator[tuple[str, str, int, str, str | None, bool]]:
        for row in self._rows:
            yield row


def _service_with(
    rows: list[tuple[str, str, int, str, str | None, bool]],
) -> CandidateSuggestionService:
    return CandidateSuggestionService(
        candidate_repo=Mock(),
        entity_repo=Mock(),
        video_repo=Mock(),
        alias_repo=Mock(),
        transcript_repo=_FakeTranscriptRepo(rows),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_stream_groups_videos_and_finalizes_last() -> None:
    """Streamed rows are grouped per video; the last video is finalized (not dropped)."""
    rows = [
        ("v1", "en", 0, "video one part a", None, False),
        ("v1", "en", 1, "part b", None, False),
        ("v2", "en", 0, "video two content", None, False),  # last video
    ]
    service = _service_with(rows)
    corpus = await service._stream_transcript_corpus(
        session=object(), excluded_languages=frozenset()
    )
    assert corpus == {
        "v1": SEGMENT_SEPARATOR.join(["video one part a", "part b"]),
        "v2": "video two content",
    }


@pytest.mark.asyncio
async def test_stream_drops_excluded_language_video() -> None:
    rows = [
        ("v1", "en", 0, "kept english", None, False),
        ("v2", "de", 0, "nur deutsch", None, False),  # excluded → absent
    ]
    service = _service_with(rows)
    corpus = await service._stream_transcript_corpus(
        session=object(), excluded_languages=frozenset({"de"})
    )
    assert corpus == {"v1": "kept english"}
