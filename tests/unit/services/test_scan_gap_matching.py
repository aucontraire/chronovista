"""
Unit tests for disfluency-tolerant gap matching in the entity mention scan.

Feature 111 US3 (Deliverable B, R3, FR-010): a name interrupted by a BOUNDED gap
(a single filler token, a false-start prefix, a repeat of the preceding token, or
an enumerated multi-word filler phrase) is detected and a mention spanning the gap
is recorded -- additively, without altering any contiguous match and without
creating any stored name/alias/ASR form that contains the filler.

All data here is invented (placeholder names, garbles, fillers); no library
content is used.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.services.entity_mention_scan_service import (
    EntityMentionScanService,
    _build_entity_pattern,
    _EntityPattern,
    _filler_tokens_for_language,
    _find_gap_spans,
)

# Module-level asyncio marker so async tests run under coverage (see CLAUDE.md).
pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _noop_cross_segment_pass() -> Any:
    """No-op the additive cross-segment pass; these tests drive _scan_batch only."""
    with patch(
        "chronovista.services.entity_mention_scan_service."
        "EntityMentionScanService._scan_cross_segment",
        new=AsyncMock(),
    ):
        yield


def _make_pattern(
    canonical_name: str = "Ada Quorne",
    *,
    aliases: list[str] | None = None,
    asr_forms: list[str] | None = None,
) -> _EntityPattern:
    """Build a real _EntityPattern via the shared builder (invented names)."""
    names = [canonical_name, *(aliases or [])]
    return _build_entity_pattern(
        entity_id=uuid.uuid4(),
        canonical_name=canonical_name,
        entity_type="person",
        names=names,
        case_sensitive_names=set(),
        exclusion_patterns=[],
        asr_forms=asr_forms,
    )


def _make_segment_row(
    seg_id: int = 1,
    effective_text: str = "",
    language_code: str = "en",
) -> MagicMock:
    """Create a mock transcript segment row matching service column access."""
    row = MagicMock()
    row.id = seg_id
    row.video_id = "vid0000000A"
    row.language_code = language_code
    row.start_time = 0.0
    row.effective_text = effective_text
    return row


async def _run_scan_batch(
    pattern: _EntityPattern,
    text: str,
    *,
    language_code: str = "en",
) -> list[Any]:
    """Drive _scan_batch (dry_run + full_rescan: no DB access) and return mentions."""
    svc = EntityMentionScanService(session_factory=MagicMock())
    row = _make_segment_row(effective_text=text, language_code=language_code)
    mentions, _skipped, _preview, _lmw, _excl = await svc._scan_batch(
        AsyncMock(),
        batch_rows=[row],
        patterns=[pattern],
        full_rescan=True,
        dry_run=True,
        limit=None,
        current_preview_count=0,
    )
    return mentions


# ---------------------------------------------------------------------------
# _find_gap_spans (pure matching rule)
# ---------------------------------------------------------------------------


class TestFindGapSpans:
    """Direct tests of the token-stream gap rule."""

    def test_single_filler_token_matches(self) -> None:
        en = _filler_tokens_for_language("en")
        spans = _find_gap_spans(["ada", "uh", "quorne"], ("ada", "quorne"), en, 1)
        assert spans == [(0, 2)]

    def test_false_start_prefix_matches(self) -> None:
        # "varic smi smithe" -> gap token "smi" is a >=2-char prefix of "smithe".
        spans = _find_gap_spans(
            ["varic", "smi", "smithe"], ("varic", "smithe"), frozenset(), 1
        )
        assert spans == [(0, 2)]

    def test_repeat_of_preceding_token_matches(self) -> None:
        spans = _find_gap_spans(
            ["ada", "ada", "quorne"], ("ada", "quorne"), frozenset(), 1
        )
        assert spans == [(0, 2)]

    def test_two_token_gap_not_matched(self) -> None:
        en = _filler_tokens_for_language("en")
        spans = _find_gap_spans(["ada", "uh", "um", "quorne"], ("ada", "quorne"), en, 1)
        assert spans == []

    def test_contiguous_occurrence_not_emitted(self) -> None:
        # Purely contiguous -> owned by the regex, so the gap pass emits nothing.
        spans = _find_gap_spans(["ada", "quorne"], ("ada", "quorne"), frozenset(), 1)
        assert spans == []

    def test_single_char_prefix_does_not_qualify(self) -> None:
        # Prefix tolerance requires length >= 2; "s" is too short.
        spans = _find_gap_spans(
            ["varic", "s", "smithe"], ("varic", "smithe"), frozenset(), 1
        )
        assert spans == []

    def test_non_qualifying_token_not_matched(self) -> None:
        spans = _find_gap_spans(
            ["ada", "zzz", "quorne"], ("ada", "quorne"), frozenset(), 1
        )
        assert spans == []

    def test_multiword_filler_phrase_matches(self) -> None:
        es = _filler_tokens_for_language("es")
        # Spanish "o sea" is the only enumerated >1-token gap exception.
        spans = _find_gap_spans(["ada", "o", "sea", "quorne"], ("ada", "quorne"), es, 2)
        assert spans == [(0, 3)]


# ---------------------------------------------------------------------------
# _filler_tokens_for_language
# ---------------------------------------------------------------------------


class TestFillerTokensForLanguage:
    def test_primary_subtag_resolved(self) -> None:
        assert _filler_tokens_for_language("en-US") == _filler_tokens_for_language("en")

    def test_unknown_language_is_empty(self) -> None:
        assert _filler_tokens_for_language("zz") == frozenset()

    def test_none_language_is_empty(self) -> None:
        assert _filler_tokens_for_language(None) == frozenset()

    def test_multiword_filler_stored_as_tuple(self) -> None:
        assert ("o", "sea") in _filler_tokens_for_language("es")


# ---------------------------------------------------------------------------
# End-to-end via _scan_batch (mention rows, span, transcript unchanged)
# ---------------------------------------------------------------------------


class TestScanBatchGapMentions:
    async def test_filler_split_name_recorded_with_spanning_text(self) -> None:
        pattern = _make_pattern("Ada Quorne")
        text = "we saw ada uh quorne speak"
        mentions = await _run_scan_batch(pattern, text)

        assert len(mentions) == 1
        m = mentions[0]
        # The span covers the filler: mention_text is the raw slice including "uh".
        assert m.mention_text == "ada uh quorne"
        assert text[m.match_start : m.match_end] == "ada uh quorne"
        # Transcript row is never mutated by the match.
        assert text == "we saw ada uh quorne speak"

    async def test_no_stored_form_contains_the_filler(self) -> None:
        pattern = _make_pattern("Ada Quorne")
        await _run_scan_batch(pattern, "ada uh quorne")
        # The match-time tolerance never injects the filler into a stored form.
        assert "uh" not in pattern.alias_names
        assert all("uh" not in name.split() for name in pattern.alias_names)
        assert pattern.canonical_name == "Ada Quorne"
        assert all("uh" not in fold.split() for fold in pattern.asr_folds)

    async def test_false_start_prefix_recorded(self) -> None:
        pattern = _make_pattern("Varic Smithe")
        mentions = await _run_scan_batch(pattern, "then varic smi smithe arrived")
        assert len(mentions) == 1
        assert mentions[0].mention_text == "varic smi smithe"

    async def test_repeat_recorded(self) -> None:
        pattern = _make_pattern("Ada Quorne")
        mentions = await _run_scan_batch(pattern, "ada ada quorne")
        assert len(mentions) == 1
        assert mentions[0].mention_text == "ada ada quorne"

    async def test_two_token_gap_not_recorded(self) -> None:
        pattern = _make_pattern("Ada Quorne")
        mentions = await _run_scan_batch(pattern, "ada uh um quorne")
        assert mentions == []

    async def test_contiguous_match_unchanged(self) -> None:
        pattern = _make_pattern("Ada Quorne")
        text = "here is ada quorne today"
        mentions = await _run_scan_batch(pattern, text)
        assert len(mentions) == 1
        m = mentions[0]
        assert m.mention_text == "ada quorne"
        assert text[m.match_start : m.match_end] == "ada quorne"

    async def test_contiguous_and_gap_prefers_longest(self) -> None:
        # "ada ada quorne": the gap span ("ada ada quorne") overlaps the
        # contiguous "ada quorne"; longest-match-wins keeps the longer span.
        pattern = _make_pattern("Ada Quorne")
        mentions = await _run_scan_batch(pattern, "ada ada quorne")
        assert len(mentions) == 1
        assert mentions[0].mention_text == "ada ada quorne"

    async def test_spanish_multiword_filler(self) -> None:
        pattern = _make_pattern("Ada Quorne")
        mentions = await _run_scan_batch(
            pattern, "vimos a ada o sea quorne hoy", language_code="es"
        )
        assert len(mentions) == 1
        assert mentions[0].mention_text == "ada o sea quorne"


# ---------------------------------------------------------------------------
# Performance scoping
# ---------------------------------------------------------------------------


class TestGapPassScoping:
    def test_empty_candidate_set_does_no_work(self) -> None:
        # No candidate patterns -> no gap matches, no iteration over entities.
        result = EntityMentionScanService._collect_gap_matches(
            "ada uh quorne",
            list(range(len("ada uh quorne"))),
            "ada uh quorne",
            [],
            "en",
        )
        assert result == []

    def test_only_passed_patterns_are_scanned(self) -> None:
        # A pattern that is NOT a candidate (not passed in) yields no gap match,
        # proving the pass is scoped to the candidate list it receives.
        candidate = _make_pattern("Ada Quorne")
        non_candidate = _make_pattern("Varic Smithe")
        text = "ada uh quorne and varic smi smithe"
        from chronovista.services.entity_mention_scan_service import _fold_diacritics

        folded, offset_map = _fold_diacritics(text)
        result = EntityMentionScanService._collect_gap_matches(
            folded, offset_map, text, [candidate], "en"
        )
        entity_ids = {r[0] for r in result}
        assert candidate.entity_id in entity_ids
        assert non_candidate.entity_id not in entity_ids
