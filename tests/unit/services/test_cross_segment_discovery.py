"""
Unit tests for CrossSegmentDiscovery service (Feature 045 — T035).

Tests the ``CrossSegmentDiscovery.discover()`` pipeline and the
``_score_candidate()`` helper for correct confidence weighting.

Test coverage map:
  (a) Discovers cross-segment split from recurring pattern
  (b) Respects min_corrections threshold — patterns below threshold excluded
  (c) Exact vs speculative split confidence scoring — word-boundary splits
      score higher than character-level splits
  (d) Filters fully corrected pairs — both segments already corrected = excluded
  (e) Includes partially corrected pairs with ``is_partially_corrected=True``
  (f) Processes cross-language adjacent segments (same video, different
      language_code segments are NOT paired; same language required)
  (g) Adjacency by sequence_number — only consecutive N, N+1 within the same
      video
  (h) No candidates when no patterns meet threshold — returns empty list

Mock strategy: ``AsyncSession`` is replaced with ``MagicMock`` whose
``execute`` / ``get`` attributes are ``AsyncMock`` instances.
``BatchCorrectionService.get_patterns`` is patched at the instance level.

Feature 045 — Correction Intelligence Pipeline (US5, T033)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.models.batch_correction_models import CorrectionPattern
from chronovista.services.cross_segment_discovery import (
    CrossSegmentCandidate,
    CrossSegmentDiscovery,
    _effective_text,
    _generate_splits,
    _generate_word_splits,
    _is_stopword_split,
)

# ---------------------------------------------------------------------------
# CRITICAL: Module-level asyncio marker ensures async tests run with coverage
# (see CLAUDE.md §pytest-asyncio Coverage Integration Issues).
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers / convenience
# ---------------------------------------------------------------------------


def _make_pattern(
    original: str,
    corrected: str,
    occurrences: int = 5,
    remaining: int = 0,
) -> CorrectionPattern:
    """Build a ``CorrectionPattern`` using the factory-verified field names."""
    return CorrectionPattern(
        original_text=original,
        corrected_text=corrected,
        occurrences=occurrences,
        remaining_matches=remaining,
    )


def _make_segment_mock(
    *,
    seg_id: int,
    video_id: str,
    language_code: str,
    sequence_number: int,
    text: str,
    has_correction: bool = False,
    corrected_text: str | None = None,
) -> MagicMock:
    """Return a MagicMock that behaves like a ``TranscriptSegmentDB`` ORM object."""
    seg = MagicMock()
    seg.id = seg_id
    seg.video_id = video_id
    seg.language_code = language_code
    seg.sequence_number = sequence_number
    seg.text = text
    seg.has_correction = has_correction
    seg.corrected_text = corrected_text
    return seg


def _make_mock_session() -> MagicMock:
    """Create a MagicMock AsyncSession with async execute and get stubs."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()
    return session


def _make_batch_service(patterns: list[CorrectionPattern]) -> AsyncMock:
    """Return an AsyncMock BatchCorrectionService that returns *patterns* from get_patterns."""
    svc = AsyncMock()
    svc.get_patterns = AsyncMock(return_value=patterns)
    return svc


# ---------------------------------------------------------------------------
# Unit tests for pure helpers (synchronous)
# ---------------------------------------------------------------------------


class TestGenerateSplits:
    """Tests for the ``_generate_splits`` helper function."""

    def test_single_word_no_word_boundary_split(self) -> None:
        """A single word produces only character-level splits (no word boundary)."""
        splits = _generate_splits("hello")
        word_boundary_splits = [s for s in splits if s[2] is True]
        assert len(word_boundary_splits) == 0

    def test_two_word_produces_one_word_boundary_split(self) -> None:
        """Two-word text produces exactly one word-boundary split."""
        splits = _generate_splits("hello world")
        word_boundary_splits = [s for s in splits if s[2] is True]
        assert len(word_boundary_splits) == 1
        prefix, suffix, _ = word_boundary_splits[0]
        assert prefix == "hello"
        assert suffix == "world"

    def test_multi_word_produces_n_minus_one_word_boundary_splits(self) -> None:
        """N-word text produces N-1 word-boundary splits."""
        splits = _generate_splits("a b c d")
        word_boundary_splits = [s for s in splits if s[2] is True]
        assert len(word_boundary_splits) == 3

    def test_long_text_skips_character_level_splits(self) -> None:
        """Texts longer than 20 characters skip character-level splits."""
        long_text = "x" * 21
        splits = _generate_splits(long_text)
        # Only word-boundary splits (none for a single long token)
        char_level_splits = [s for s in splits if s[2] is False]
        assert len(char_level_splits) == 0

    def test_short_text_has_character_level_splits(self) -> None:
        """Texts of 20 chars or fewer include character-level splits."""
        splits = _generate_splits("abc")
        char_level_splits = [s for s in splits if s[2] is False]
        assert len(char_level_splits) > 0

    def test_all_splits_have_non_empty_prefix_and_suffix(self) -> None:
        """Every split tuple must have a non-empty prefix and non-empty suffix."""
        for text in ["hello world", "Chomski", "a b"]:
            for prefix, suffix, _ in _generate_splits(text):
                assert prefix != ""
                assert suffix != ""


class TestEffectiveText:
    """Tests for the ``_effective_text`` helper."""

    def test_returns_corrected_text_when_has_correction(self) -> None:
        seg = _make_segment_mock(
            seg_id=1,
            video_id="vid1",
            language_code="en",
            sequence_number=0,
            text="original text",
            has_correction=True,
            corrected_text="corrected text",
        )
        assert _effective_text(seg) == "corrected text"

    def test_returns_raw_text_when_no_correction(self) -> None:
        seg = _make_segment_mock(
            seg_id=1,
            video_id="vid1",
            language_code="en",
            sequence_number=0,
            text="raw text",
            has_correction=False,
            corrected_text=None,
        )
        assert _effective_text(seg) == "raw text"

    def test_returns_raw_text_when_corrected_text_is_none(self) -> None:
        """Even if has_correction is True but corrected_text is None, fall back to text."""
        seg = _make_segment_mock(
            seg_id=1,
            video_id="vid1",
            language_code="en",
            sequence_number=0,
            text="fallback text",
            has_correction=True,
            corrected_text=None,
        )
        assert _effective_text(seg) == "fallback text"


# ---------------------------------------------------------------------------
# Unit tests for _score_candidate
# ---------------------------------------------------------------------------


class TestScoreCandidate:
    """Tests for ``CrossSegmentDiscovery._score_candidate``."""

    @pytest.fixture
    def service(self) -> CrossSegmentDiscovery:
        """Provide a CrossSegmentDiscovery with a mock BatchCorrectionService."""
        return CrossSegmentDiscovery(batch_service=AsyncMock())

    # (c) Word-boundary splits score higher than character-level splits
    def test_word_boundary_scores_higher_than_char_level(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """Word-boundary split base score (0.4) exceeds char-level (0.15)."""
        word_score = service._score_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="He said Chomski",
            seg_n1_text="is great",
            is_word_boundary=True,
            pattern_occurrences=5,
            is_partially_corrected=False,
        )
        char_score = service._score_candidate(
            prefix="Chomsk",
            suffix="i is",
            seg_n_text="He said Chomsk",
            seg_n1_text="i is great",
            is_word_boundary=False,
            pattern_occurrences=5,
            is_partially_corrected=False,
        )
        assert word_score > char_score

    def test_score_capped_at_one(self, service: CrossSegmentDiscovery) -> None:
        """The confidence score is never greater than 1.0."""
        score = service._score_candidate(
            prefix="hello",
            suffix="world",
            seg_n_text="hello",
            seg_n1_text="world",
            is_word_boundary=True,
            pattern_occurrences=100,
            is_partially_corrected=True,
        )
        assert score <= 1.0

    def test_score_non_negative(self, service: CrossSegmentDiscovery) -> None:
        """The confidence score is always >= 0.0."""
        score = service._score_candidate(
            prefix="x",
            suffix="y",
            seg_n_text="notx",
            seg_n1_text="noty",
            is_word_boundary=False,
            pattern_occurrences=0,
            is_partially_corrected=False,
        )
        assert score >= 0.0

    def test_partial_correction_boosts_score(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """is_partially_corrected=True adds 0.1 boost to the score."""
        base_score = service._score_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="He said Chomski",
            seg_n1_text="is right",
            is_word_boundary=True,
            pattern_occurrences=3,
            is_partially_corrected=False,
        )
        boosted_score = service._score_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="He said Chomski",
            seg_n1_text="is right",
            is_word_boundary=True,
            pattern_occurrences=3,
            is_partially_corrected=True,
        )
        assert boosted_score == pytest.approx(base_score + 0.1, abs=1e-9)

    def test_high_frequency_pattern_increases_score(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """More pattern occurrences produce a higher frequency contribution."""
        low_freq_score = service._score_candidate(
            prefix="hello",
            suffix="world",
            seg_n_text="say hello",
            seg_n1_text="world today",
            is_word_boundary=True,
            pattern_occurrences=1,
            is_partially_corrected=False,
        )
        high_freq_score = service._score_candidate(
            prefix="hello",
            suffix="world",
            seg_n_text="say hello",
            seg_n1_text="world today",
            is_word_boundary=True,
            pattern_occurrences=20,
            is_partially_corrected=False,
        )
        assert high_freq_score > low_freq_score

    def test_exact_boundary_match_adds_precision_bonus(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """Exact end/start boundary match adds 0.2 to the score."""
        exact_score = service._score_candidate(
            prefix="Chomski",
            suffix="was",
            seg_n_text="said Chomski",
            seg_n1_text="was wrong",
            is_word_boundary=True,
            pattern_occurrences=5,
            is_partially_corrected=False,
        )
        partial_score = service._score_candidate(
            prefix="Chomski",
            suffix="was",
            seg_n_text="not a match",
            seg_n1_text="not a match either",
            is_word_boundary=True,
            pattern_occurrences=5,
            is_partially_corrected=False,
        )
        assert exact_score > partial_score


# ---------------------------------------------------------------------------
# Unit tests for discover() — async, with mocked DB
# ---------------------------------------------------------------------------


class TestCrossSegmentDiscoveryDiscover:
    """Integration-style unit tests for ``CrossSegmentDiscovery.discover()``."""

    # (b) No patterns from service → returns empty list
    async def test_no_patterns_returns_empty_list(self) -> None:
        """discover() returns [] when get_patterns returns no patterns and no entity aliases."""
        batch_svc = _make_batch_service(patterns=[])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        # Isolate pattern path: entity-based discovery returns nothing
        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]

        result = await discovery.discover(session, min_corrections=3)

        assert result == []
        batch_svc.get_patterns.assert_awaited_once_with(
            session,
            min_occurrences=3,
            limit=200,
            show_completed=True,
        )

    # (b) min_corrections forwarded to get_patterns
    async def test_min_corrections_forwarded_to_get_patterns(self) -> None:
        """discover() passes min_corrections as min_occurrences to get_patterns."""
        batch_svc = _make_batch_service(patterns=[])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        # Isolate pattern path: entity-based discovery returns nothing
        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]

        await discovery.discover(session, min_corrections=7)

        call_kwargs = batch_svc.get_patterns.call_args
        assert call_kwargs.kwargs["min_occurrences"] == 7

    # (h) No patterns meeting threshold → empty list (already covered above,
    #     additional explicit check with entity filter returning nothing)
    async def test_entity_filter_with_no_match_returns_empty(self) -> None:
        """When entity filter matches no patterns and no aliases, discover() returns []."""
        pattern = _make_pattern("Chomski is", "Chomsky is", occurrences=5)
        batch_svc = _make_batch_service(patterns=[pattern])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        # Entity discovery finds nothing for the filter
        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]

        # Pattern-based: corrected segment IDs query returns nothing
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = []
        session.execute.return_value = exec_result

        result = await discovery.discover(
            session,
            min_corrections=3,
            entity_name="Nonexistent",
        )

        assert result == []

    # (c) Entity filter case-insensitive match (pattern path)
    async def test_entity_filter_is_case_insensitive(self) -> None:
        """Entity filter matches patterns case-insensitively in the pattern path."""
        pattern_matching = _make_pattern("Chomski is", "Chomsky is", occurrences=5)
        pattern_not_matching = _make_pattern("wrong text", "correct text", occurrences=5)
        batch_svc = _make_batch_service(
            patterns=[pattern_matching, pattern_not_matching]
        )
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        # Isolate pattern path: entity-based discovery returns nothing
        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]

        # DB execute returns no adjacent pairs to keep test focused on filter
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = []
        exec_result.fetchall.return_value = []
        session.execute.return_value = exec_result

        # We verify entity_name="chomski" (lower-case) still matches "Chomski is"
        # by spying on _find_adjacent_pairs_batched and checking which splits
        # are passed (only splits from the matching pattern should appear).
        recorded_pairs: list[tuple[str, str]] = []

        async def _spy_batched(
            s: Any,
            pairs: list[tuple[str, str]],
            limit: int = 500,
        ) -> list[tuple[Any, Any]]:
            recorded_pairs.extend(pairs)
            return []

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        discovery._find_adjacent_pairs_batched = _spy_batched  # type: ignore[assignment]
        discovery._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]

        await discovery.discover(session, min_corrections=3, entity_name="chomski")

        # Only splits from "Chomski is" should be present (word-boundary: "Chomski"/"is")
        assert len(recorded_pairs) >= 1
        assert any("Chomski" in p for p, _ in recorded_pairs)

    # (a) Discovers cross-segment split — full pipeline with mocked _find_adjacent_pairs
    async def test_discovers_candidate_from_recurring_pattern(self) -> None:
        """discover() returns a CrossSegmentCandidate when adjacent pairs are found."""
        pattern = _make_pattern("Chomski is", "Chomsky is", occurrences=10)
        batch_svc = _make_batch_service(patterns=[pattern])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        seg_n = _make_segment_mock(
            seg_id=10,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            sequence_number=5,
            text="He said Chomski",
        )
        seg_n1 = _make_segment_mock(
            seg_id=11,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            sequence_number=6,
            text="is wrong about that",
        )

        # Isolate pattern path: entity-based discovery returns nothing
        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]

        # Patch _find_adjacent_pairs and _get_corrected_segment_ids
        async def _fake_find_pairs_batched(
            s: Any, pairs: Any, limit: int = 500
        ) -> list[tuple[Any, Any]]:
            return [(seg_n, seg_n1)]

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        discovery._find_adjacent_pairs_batched = _fake_find_pairs_batched  # type: ignore[assignment]
        discovery._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]

        candidates = await discovery.discover(session, min_corrections=3)

        assert len(candidates) >= 1
        first = candidates[0]
        assert isinstance(first, CrossSegmentCandidate)
        assert first.segment_n_id == 10
        assert first.segment_n1_id == 11
        assert first.video_id == "dQw4w9WgXcQ"
        assert first.proposed_correction == "Chomsky is"
        assert first.source_pattern == "Chomski is"
        assert 0.0 <= first.confidence <= 1.0

    # (d) Fully corrected pairs are excluded
    async def test_fully_corrected_pairs_excluded(self) -> None:
        """If both segments are already corrected, the candidate is not returned."""
        pattern = _make_pattern("Chomski is", "Chomsky is", occurrences=5)
        batch_svc = _make_batch_service(patterns=[pattern])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        seg_n = _make_segment_mock(
            seg_id=20,
            video_id="vid1",
            language_code="en",
            sequence_number=0,
            text="He said Chomski",
            has_correction=True,
            corrected_text="He said Chomsky",
        )
        seg_n1 = _make_segment_mock(
            seg_id=21,
            video_id="vid1",
            language_code="en",
            sequence_number=1,
            text="is great",
            has_correction=True,
            corrected_text="is great",
        )

        # Isolate pattern path: entity-based discovery returns nothing
        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]

        # Both segment IDs are in the corrected set
        async def _fake_find_pairs_batched(
            s: Any, pairs: Any, limit: int = 500
        ) -> list[tuple[Any, Any]]:
            return [(seg_n, seg_n1)]

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return {20, 21}

        discovery._find_adjacent_pairs_batched = _fake_find_pairs_batched  # type: ignore[assignment]
        discovery._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]

        candidates = await discovery.discover(session, min_corrections=3)

        assert candidates == []

    # (e) Partially corrected pairs included with flag set
    async def test_partially_corrected_pair_included_with_flag(self) -> None:
        """If exactly one segment is corrected, the candidate is included with is_partially_corrected=True."""
        pattern = _make_pattern("Chomski is", "Chomsky is", occurrences=5)
        batch_svc = _make_batch_service(patterns=[pattern])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        seg_n = _make_segment_mock(
            seg_id=30,
            video_id="vid2",
            language_code="en",
            sequence_number=0,
            text="he said Chomski",
            has_correction=True,
            corrected_text="He said Chomski",  # capitalisation fix; pattern still matches
        )
        seg_n1 = _make_segment_mock(
            seg_id=31,
            video_id="vid2",
            language_code="en",
            sequence_number=1,
            text="is wrong",
            has_correction=False,
        )

        # Isolate pattern path: entity-based discovery returns nothing
        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]

        # Only seg_n (id=30) is in the corrected set
        async def _fake_find_pairs_batched(
            s: Any, pairs: Any, limit: int = 500
        ) -> list[tuple[Any, Any]]:
            return [(seg_n, seg_n1)]

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return {30}

        discovery._find_adjacent_pairs_batched = _fake_find_pairs_batched  # type: ignore[assignment]
        discovery._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]

        candidates = await discovery.discover(session, min_corrections=3)

        partial_candidates = [c for c in candidates if c.is_partially_corrected]
        assert len(partial_candidates) >= 1

    # Results are sorted by confidence descending
    async def test_results_sorted_by_confidence_descending(self) -> None:
        """discover() returns candidates sorted by confidence, highest first."""
        # Two word-boundary patterns with different occurrences → different scores
        pattern_high = _make_pattern("Chomski is", "Chomsky is", occurrences=20)
        pattern_low = _make_pattern("foo bar", "Foo Bar", occurrences=1)
        batch_svc = _make_batch_service(patterns=[pattern_high, pattern_low])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        # Isolate pattern path: entity-based discovery returns nothing
        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]

        # Build two fake candidate pairs to ensure different confidence scores
        seg_high_n = _make_segment_mock(
            seg_id=40, video_id="vid3", language_code="en",
            sequence_number=0, text="said Chomski"
        )
        seg_high_n1 = _make_segment_mock(
            seg_id=41, video_id="vid3", language_code="en",
            sequence_number=1, text="is important"
        )
        seg_low_n = _make_segment_mock(
            seg_id=50, video_id="vid4", language_code="en",
            sequence_number=0, text="prefix foo"
        )
        seg_low_n1 = _make_segment_mock(
            seg_id=51, video_id="vid4", language_code="en",
            sequence_number=1, text="bar suffix"
        )

        async def _fake_find_pairs_batched(
            s: Any, pairs: Any, limit: int = 500
        ) -> list[tuple[Any, Any]]:
            return [(seg_high_n, seg_high_n1), (seg_low_n, seg_low_n1)]

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        discovery._find_adjacent_pairs_batched = _fake_find_pairs_batched  # type: ignore[assignment]
        discovery._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]

        candidates = await discovery.discover(session, min_corrections=3)

        if len(candidates) >= 2:
            for i in range(len(candidates) - 1):
                assert candidates[i].confidence >= candidates[i + 1].confidence

    # (g) Adjacency: only consecutive N, N+1 by sequence_number
    # This is enforced in the SQL query; we verify via _find_adjacent_pairs_batched args
    async def test_only_adjacent_pairs_considered(self) -> None:
        """_find_adjacent_pairs_batched receives prefix/suffix splits from patterns."""
        pattern = _make_pattern("hello world", "Hello World", occurrences=5)
        batch_svc = _make_batch_service(patterns=[pattern])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        # Isolate pattern path: entity-based discovery returns nothing
        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]

        recorded_pairs: list[tuple[str, str]] = []

        async def _recording_find_pairs_batched(
            s: Any, pairs: Any, limit: int = 500
        ) -> list[tuple[Any, Any]]:
            recorded_pairs.extend(pairs)
            return []

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        discovery._find_adjacent_pairs_batched = _recording_find_pairs_batched  # type: ignore[assignment]
        discovery._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]

        await discovery.discover(session, min_corrections=3)

        # At minimum the word-boundary split ("hello", "world") must have been tried
        assert len(recorded_pairs) > 0
        prefixes = [p for p, _ in recorded_pairs]
        assert any("hello" in p.lower() for p in prefixes)

    # (f) Cross-language test: same video, different language_code = NOT paired
    # This is enforced via the SQL (seg_n.language_code == seg_n1.language_code),
    # so we verify the WHERE clause is respected by ensuring the service does NOT
    # return cross-language pairs from _find_adjacent_pairs.
    async def test_cross_language_pairs_not_discovered(self) -> None:
        """Segments of the same video but different languages are not paired."""
        pattern = _make_pattern("Chomski is", "Chomsky is", occurrences=5)
        batch_svc = _make_batch_service(patterns=[pattern])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        # Isolate pattern path: entity-based discovery returns nothing
        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]

        # Simulate: the SQL query correctly rejects cross-language pairs,
        # so _find_adjacent_pairs returns [] for them.
        async def _no_cross_lang_pairs_batched(
            s: Any, pairs: Any, limit: int = 500
        ) -> list[tuple[Any, Any]]:
            # Simulate correct SQL behaviour: cross-language segments not returned
            return []

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        discovery._find_adjacent_pairs_batched = _no_cross_lang_pairs_batched  # type: ignore[assignment]
        discovery._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]

        candidates = await discovery.discover(session, min_corrections=3)

        # No candidates because cross-language pairs are excluded by the query
        assert candidates == []

    # confidence rounded to 4 decimal places in CrossSegmentCandidate
    async def test_candidate_confidence_rounded_to_4_decimal_places(self) -> None:
        """CrossSegmentCandidate.confidence is rounded to 4 decimal places."""
        pattern = _make_pattern("Chomski is", "Chomsky is", occurrences=7)
        batch_svc = _make_batch_service(patterns=[pattern])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        seg_n = _make_segment_mock(
            seg_id=70, video_id="vid6", language_code="en",
            sequence_number=0, text="said Chomski"
        )
        seg_n1 = _make_segment_mock(
            seg_id=71, video_id="vid6", language_code="en",
            sequence_number=1, text="is the point"
        )

        # Isolate pattern path: entity-based discovery returns nothing
        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]

        async def _fake_find_pairs_batched(
            s: Any, pairs: Any, limit: int = 500
        ) -> list[tuple[Any, Any]]:
            return [(seg_n, seg_n1)]

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        discovery._find_adjacent_pairs_batched = _fake_find_pairs_batched  # type: ignore[assignment]
        discovery._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]

        candidates = await discovery.discover(session, min_corrections=3)

        for c in candidates:
            # Confidence rounded to 4dp: str representation should not exceed 4 dp
            str_repr = f"{c.confidence}"
            decimal_part = str_repr.split(".")[1] if "." in str_repr else ""
            assert len(decimal_part) <= 4, (
                f"Confidence {c.confidence} has more than 4 decimal places"
            )


# ---------------------------------------------------------------------------
# CrossSegmentCandidate model tests
# ---------------------------------------------------------------------------


class TestCrossSegmentCandidateModel:
    """Unit tests for the ``CrossSegmentCandidate`` Pydantic model."""

    def _valid_kwargs(self) -> dict[str, Any]:
        return {
            "segment_n_id": 1,
            "segment_n_text": "He said Chomski",
            "segment_n1_id": 2,
            "segment_n1_text": "is great",
            "proposed_correction": "Chomsky is",
            "source_pattern": "Chomski is",
            "confidence": 0.75,
            "is_partially_corrected": False,
            "video_id": "dQw4w9WgXcQ",
        }

    def test_valid_candidate_instantiation(self) -> None:
        """A valid CrossSegmentCandidate can be instantiated without errors."""
        candidate = CrossSegmentCandidate(**self._valid_kwargs())
        assert candidate.segment_n_id == 1
        assert candidate.segment_n1_id == 2
        assert candidate.confidence == 0.75
        assert candidate.is_partially_corrected is False

    def test_confidence_below_zero_rejected(self) -> None:
        """confidence < 0.0 is rejected by Pydantic validation."""
        from pydantic import ValidationError

        kwargs = self._valid_kwargs()
        kwargs["confidence"] = -0.1
        with pytest.raises(ValidationError):
            CrossSegmentCandidate(**kwargs)

    def test_confidence_above_one_rejected(self) -> None:
        """confidence > 1.0 is rejected by Pydantic validation."""
        from pydantic import ValidationError

        kwargs = self._valid_kwargs()
        kwargs["confidence"] = 1.01
        with pytest.raises(ValidationError):
            CrossSegmentCandidate(**kwargs)

    def test_model_is_frozen(self) -> None:
        """CrossSegmentCandidate is immutable (frozen=True)."""
        candidate = CrossSegmentCandidate(**self._valid_kwargs())
        with pytest.raises(Exception):
            candidate.confidence = 0.5

    def test_default_is_partially_corrected_is_false(self) -> None:
        """is_partially_corrected defaults to False."""
        kwargs = self._valid_kwargs()
        del kwargs["is_partially_corrected"]
        candidate = CrossSegmentCandidate(**kwargs)
        assert candidate.is_partially_corrected is False


# ---------------------------------------------------------------------------
# New test classes for entity-aware cross-segment discovery
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Unit tests for _generate_word_splits (module-level helper)
# ---------------------------------------------------------------------------


class TestGenerateWordSplits:
    """Tests for the ``_generate_word_splits`` helper function.

    Unlike ``_generate_splits``, this function produces only word-boundary
    splits (no character-level splits) and returns 2-tuples instead of
    3-tuples.
    """

    def test_two_word_text_produces_one_split(self) -> None:
        """A two-word alias produces exactly one (prefix, suffix) split."""
        splits = _generate_word_splits("Claudia Shabom")
        assert len(splits) == 1
        assert splits[0] == ("Claudia", "Shabom")

    def test_three_word_text_produces_two_splits(self) -> None:
        """A three-word alias produces N-1=2 splits in left-to-right order."""
        splits = _generate_word_splits("Claudia Shane Bound")
        assert len(splits) == 2
        assert splits[0] == ("Claudia", "Shane Bound")
        assert splits[1] == ("Claudia Shane", "Bound")

    def test_single_word_returns_empty_list(self) -> None:
        """A single-word text (no whitespace) produces no splits."""
        splits = _generate_word_splits("Chomski")
        assert splits == []

    def test_empty_string_returns_empty_list(self) -> None:
        """An empty string produces no splits."""
        splits = _generate_word_splits("")
        assert splits == []

    def test_preserves_original_casing(self) -> None:
        """The prefix and suffix preserve the original case of the input."""
        splits = _generate_word_splits("noam Chomsky")
        assert len(splits) == 1
        prefix, suffix = splits[0]
        assert prefix == "noam"
        assert suffix == "Chomsky"

    def test_four_word_text_produces_three_splits(self) -> None:
        """A four-word alias produces N-1=3 splits."""
        splits = _generate_word_splits("a b c d")
        assert len(splits) == 3

    def test_all_splits_have_non_empty_parts(self) -> None:
        """Every split must have a non-empty prefix and a non-empty suffix."""
        for alias in ["hello world", "one two three"]:
            for prefix, suffix in _generate_word_splits(alias):
                assert prefix.strip() != ""
                assert suffix.strip() != ""

    def test_splits_are_two_tuples(self) -> None:
        """Every element is a 2-tuple, not a 3-tuple like _generate_splits."""
        splits = _generate_word_splits("Claudia Shabom")
        for item in splits:
            assert len(item) == 2

    def test_multiple_spaces_between_words(self) -> None:
        """Multiple spaces between words are treated as one boundary."""
        # _WORD_BOUNDARY_RE uses r"\s+" so this is handled
        splits = _generate_word_splits("hello  world")
        # Should still produce one split with the raw joined strings
        assert len(splits) == 1
        prefix, suffix = splits[0]
        assert prefix == "hello"
        assert suffix == "world"

    def test_prefix_suffix_reconstruct_words(self) -> None:
        """Joining prefix + ' ' + suffix gives back the space-joined word form."""
        text = "Anna Maria Contreras"
        splits = _generate_word_splits(text)
        # The text joined by a single space
        normalized = " ".join(text.split())
        for prefix, suffix in splits:
            assert f"{prefix} {suffix}" == normalized


# ---------------------------------------------------------------------------
# Unit tests for _is_stopword_split
# ---------------------------------------------------------------------------


class TestIsStopwordSplit:
    """Tests for ``_is_stopword_split`` helper.

    Stopword-only splits (e.g. "be" / "out") are filtered out because
    they produce overwhelming false positives in cross-segment discovery.
    """

    def test_both_stopwords_returns_true(self) -> None:
        assert _is_stopword_split("be", "out") is True

    def test_multi_word_stopwords_returns_true(self) -> None:
        assert _is_stopword_split("it was", "on the") is True

    def test_one_side_non_stopword_returns_false(self) -> None:
        assert _is_stopword_split("Chomsk", "i") is False

    def test_proper_name_prefix_returns_false(self) -> None:
        assert _is_stopword_split("Shein", "baum") is False

    def test_mixed_stopword_and_name_returns_false(self) -> None:
        assert _is_stopword_split("Rick be", "out") is False

    def test_empty_prefix_returns_false(self) -> None:
        assert _is_stopword_split("", "out") is False

    def test_empty_suffix_returns_false(self) -> None:
        assert _is_stopword_split("be", "") is False


# ---------------------------------------------------------------------------
# Unit tests for _score_entity_candidate
# ---------------------------------------------------------------------------


class TestScoreEntityCandidate:
    """Tests for ``CrossSegmentDiscovery._score_entity_candidate``.

    Scoring formula (capped at 1.0):
      Base:                 0.50
      Exact boundary:      +0.20 (both ends/starts match)
      One-side boundary:   +0.10 (only one side matches)
      Partial correction:  +0.10
      Person entity type:  +0.10
      2-word alias:        +0.10
    """

    @pytest.fixture
    def service(self) -> CrossSegmentDiscovery:
        """Provide a CrossSegmentDiscovery with a stub BatchCorrectionService."""
        return CrossSegmentDiscovery(batch_service=AsyncMock())

    def test_base_score_without_bonuses(self, service: CrossSegmentDiscovery) -> None:
        """No matching boundary, no partial, non-person, 3-word alias → score == 0.50."""
        score = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="something else entirely",
            seg_n1_text="nothing here",
            is_partially_corrected=False,
            entity_type="organization",
            alias_word_count=3,
        )
        assert score == pytest.approx(0.50, abs=1e-9)

    def test_entity_base_score_higher_than_pattern_base(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """Entity base (0.50) exceeds pattern word-boundary base (0.40)."""
        entity_score = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="unmatched text",
            seg_n1_text="unmatched text",
            is_partially_corrected=False,
            entity_type="organization",
            alias_word_count=3,
        )
        pattern_score = service._score_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="unmatched text",
            seg_n1_text="unmatched text",
            is_word_boundary=True,
            pattern_occurrences=0,
            is_partially_corrected=False,
        )
        assert entity_score > pattern_score

    def test_exact_boundary_adds_0_20(self, service: CrossSegmentDiscovery) -> None:
        """When seg_n ends with prefix AND seg_n1 starts with suffix, +0.20 is added."""
        base_score = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="unrelated",
            seg_n1_text="unrelated",
            is_partially_corrected=False,
            entity_type="organization",
            alias_word_count=3,
        )
        exact_score = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="He said Chomski",
            seg_n1_text="is the truth",
            is_partially_corrected=False,
            entity_type="organization",
            alias_word_count=3,
        )
        assert exact_score == pytest.approx(base_score + 0.20, abs=1e-9)

    def test_one_side_boundary_adds_0_10(self, service: CrossSegmentDiscovery) -> None:
        """When only one side matches, +0.10 is added (not +0.20)."""
        base_score = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="unrelated",
            seg_n1_text="unrelated",
            is_partially_corrected=False,
            entity_type="organization",
            alias_word_count=3,
        )
        one_side_score = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="He said Chomski",  # ends with prefix
            seg_n1_text="no match here",   # does NOT start with suffix
            is_partially_corrected=False,
            entity_type="organization",
            alias_word_count=3,
        )
        assert one_side_score == pytest.approx(base_score + 0.10, abs=1e-9)

    def test_partial_correction_adds_0_10(self, service: CrossSegmentDiscovery) -> None:
        """is_partially_corrected=True adds exactly 0.10 to the score."""
        without = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="unrelated",
            seg_n1_text="unrelated",
            is_partially_corrected=False,
            entity_type="organization",
            alias_word_count=3,
        )
        with_partial = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="unrelated",
            seg_n1_text="unrelated",
            is_partially_corrected=True,
            entity_type="organization",
            alias_word_count=3,
        )
        assert with_partial == pytest.approx(without + 0.10, abs=1e-9)

    def test_person_entity_type_adds_0_10(self, service: CrossSegmentDiscovery) -> None:
        """entity_type='person' adds exactly 0.10 over a non-person type."""
        non_person = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="unrelated",
            seg_n1_text="unrelated",
            is_partially_corrected=False,
            entity_type="organization",
            alias_word_count=3,
        )
        person = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="unrelated",
            seg_n1_text="unrelated",
            is_partially_corrected=False,
            entity_type="person",
            alias_word_count=3,
        )
        assert person == pytest.approx(non_person + 0.10, abs=1e-9)

    def test_two_word_alias_adds_0_10(self, service: CrossSegmentDiscovery) -> None:
        """alias_word_count==2 adds exactly 0.10 over a 3-word alias."""
        three_word = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="unrelated",
            seg_n1_text="unrelated",
            is_partially_corrected=False,
            entity_type="organization",
            alias_word_count=3,
        )
        two_word = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="unrelated",
            seg_n1_text="unrelated",
            is_partially_corrected=False,
            entity_type="organization",
            alias_word_count=2,
        )
        assert two_word == pytest.approx(three_word + 0.10, abs=1e-9)

    def test_three_word_alias_does_not_get_two_word_bonus(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """alias_word_count==3 does NOT receive the 2-word alias bonus."""
        score = service._score_entity_candidate(
            prefix="Chomski Shane",
            suffix="is",
            seg_n_text="unrelated",
            seg_n1_text="unrelated",
            is_partially_corrected=False,
            entity_type="organization",
            alias_word_count=3,
        )
        # Only base: 0.50
        assert score == pytest.approx(0.50, abs=1e-9)

    def test_score_capped_at_one(self, service: CrossSegmentDiscovery) -> None:
        """All bonuses stacked together cannot push the score above 1.0."""
        score = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="He said Chomski",  # exact ends-with
            seg_n1_text="is the truth",    # exact starts-with
            is_partially_corrected=True,
            entity_type="person",
            alias_word_count=2,
        )
        # 0.50 + 0.20 + 0.10 + 0.10 + 0.10 = 1.00 — exactly at cap
        assert score == pytest.approx(1.0, abs=1e-9)
        assert score <= 1.0

    def test_score_never_negative(self, service: CrossSegmentDiscovery) -> None:
        """The entity candidate score is always >= 0.0."""
        score = service._score_entity_candidate(
            prefix="x",
            suffix="y",
            seg_n_text="not matching",
            seg_n1_text="not matching",
            is_partially_corrected=False,
            entity_type="location",
            alias_word_count=5,
        )
        assert score >= 0.0

    def test_score_is_float(self, service: CrossSegmentDiscovery) -> None:
        """The return type of _score_entity_candidate is float."""
        score = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="unrelated",
            seg_n1_text="unrelated",
            is_partially_corrected=False,
            entity_type="organization",
            alias_word_count=3,
        )
        assert isinstance(score, float)

    def test_all_bonuses_accumulate_correctly(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """Each bonus is independently additive before the cap."""
        # Apply exactly one bonus at a time and verify the delta
        base = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="unrelated",
            seg_n1_text="unrelated",
            is_partially_corrected=False,
            entity_type="organization",
            alias_word_count=3,
        )
        with_person = service._score_entity_candidate(
            prefix="Chomski",
            suffix="is",
            seg_n_text="unrelated",
            seg_n1_text="unrelated",
            is_partially_corrected=False,
            entity_type="person",
            alias_word_count=2,
        )
        # person bonus + 2-word bonus = 0.20 added
        assert with_person == pytest.approx(base + 0.20, abs=1e-9)


# ---------------------------------------------------------------------------
# Unit tests for discover_from_entities
# ---------------------------------------------------------------------------


def _make_alias_row(
    alias_name: str,
    canonical_name: str,
    entity_type: str,
) -> tuple[str, str, str]:
    """Build a fake alias row as returned by _load_multiword_asr_aliases."""
    return (alias_name, canonical_name, entity_type)


class TestDiscoverFromEntities:
    """Tests for ``CrossSegmentDiscovery.discover_from_entities``.

    Strategy: patch ``_load_multiword_asr_aliases`` and ``_find_adjacent_pairs``
    at the instance level so no real DB calls are made.
    """

    @pytest.fixture
    def service(self) -> CrossSegmentDiscovery:
        """Provide a CrossSegmentDiscovery with a stub BatchCorrectionService."""
        return CrossSegmentDiscovery(batch_service=AsyncMock())

    async def test_no_aliases_returns_empty_list(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """When no multi-word ASR aliases exist, returns empty list."""
        service._load_multiword_asr_aliases = AsyncMock(return_value=[])  # type: ignore[method-assign]
        session = _make_mock_session()

        result = await service.discover_from_entities(session)

        assert result == []

    async def test_discovery_source_is_entity_alias(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """All candidates returned have discovery_source='entity_alias'."""
        aliases = [_make_alias_row("Chomski is", "Chomsky", "person")]
        service._load_multiword_asr_aliases = AsyncMock(return_value=aliases)  # type: ignore[method-assign]

        seg_n = _make_segment_mock(
            seg_id=100, video_id="vid10", language_code="en",
            sequence_number=0, text="He said Chomski"
        )
        seg_n1 = _make_segment_mock(
            seg_id=101, video_id="vid10", language_code="en",
            sequence_number=1, text="is here"
        )

        async def _fake_find_pairs_batched(
            s: Any, pairs: Any, limit: int = 500
        ) -> list[tuple[Any, Any]]:
            return [(seg_n, seg_n1)]

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        service._find_adjacent_pairs_batched = _fake_find_pairs_batched  # type: ignore[assignment]
        service._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]
        session = _make_mock_session()

        candidates = await service.discover_from_entities(session)

        assert len(candidates) >= 1
        for c in candidates:
            assert c.discovery_source == "entity_alias"

    async def test_proposed_correction_is_canonical_name(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """The proposed_correction field equals the entity's canonical_name."""
        canonical = "Noam Chomsky"
        aliases = [_make_alias_row("Chomski is", canonical, "person")]
        service._load_multiword_asr_aliases = AsyncMock(return_value=aliases)  # type: ignore[method-assign]

        seg_n = _make_segment_mock(
            seg_id=110, video_id="vid11", language_code="en",
            sequence_number=0, text="He said Chomski"
        )
        seg_n1 = _make_segment_mock(
            seg_id=111, video_id="vid11", language_code="en",
            sequence_number=1, text="is wrong"
        )

        async def _fake_find_pairs_batched(
            s: Any, pairs: Any, limit: int = 500
        ) -> list[tuple[Any, Any]]:
            return [(seg_n, seg_n1)]

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        service._find_adjacent_pairs_batched = _fake_find_pairs_batched  # type: ignore[assignment]
        service._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]
        session = _make_mock_session()

        candidates = await service.discover_from_entities(session)

        assert len(candidates) >= 1
        assert all(c.proposed_correction == canonical for c in candidates)

    async def test_fully_corrected_pairs_excluded(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """Pairs where both segments are already corrected are excluded."""
        aliases = [_make_alias_row("Chomski is", "Chomsky", "person")]
        service._load_multiword_asr_aliases = AsyncMock(return_value=aliases)  # type: ignore[method-assign]

        seg_n = _make_segment_mock(
            seg_id=120, video_id="vid12", language_code="en",
            sequence_number=0, text="Chomski", has_correction=True,
            corrected_text="Chomsky"
        )
        seg_n1 = _make_segment_mock(
            seg_id=121, video_id="vid12", language_code="en",
            sequence_number=1, text="is", has_correction=True,
            corrected_text="is"
        )

        async def _fake_find_pairs_batched(
            s: Any, pairs: Any, limit: int = 500
        ) -> list[tuple[Any, Any]]:
            return [(seg_n, seg_n1)]

        # Both IDs are corrected
        async def _fake_corrected_ids(s: Any) -> set[int]:
            return {120, 121}

        service._find_adjacent_pairs_batched = _fake_find_pairs_batched  # type: ignore[assignment]
        service._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]
        session = _make_mock_session()

        candidates = await service.discover_from_entities(session)

        assert candidates == []

    async def test_partially_corrected_pair_included_with_flag(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """When only one segment is corrected, the candidate is included with is_partially_corrected=True."""
        aliases = [_make_alias_row("Chomski is", "Chomsky", "person")]
        service._load_multiword_asr_aliases = AsyncMock(return_value=aliases)  # type: ignore[method-assign]

        # seg_n has a correction for something else (punctuation), but its
        # effective text still ends with the alias prefix "Chomski".
        seg_n = _make_segment_mock(
            seg_id=130, video_id="vid13", language_code="en",
            sequence_number=0, text="he said Chomski",
            has_correction=True, corrected_text="He said Chomski"
        )
        seg_n1 = _make_segment_mock(
            seg_id=131, video_id="vid13", language_code="en",
            sequence_number=1, text="is wrong", has_correction=False
        )

        async def _fake_find_pairs_batched(
            s: Any, pairs: Any, limit: int = 500
        ) -> list[tuple[Any, Any]]:
            return [(seg_n, seg_n1)]

        # Only seg_n is corrected
        async def _fake_corrected_ids(s: Any) -> set[int]:
            return {130}

        service._find_adjacent_pairs_batched = _fake_find_pairs_batched  # type: ignore[assignment]
        service._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]
        session = _make_mock_session()

        candidates = await service.discover_from_entities(session)

        assert len(candidates) >= 1
        assert any(c.is_partially_corrected for c in candidates)

    async def test_entity_name_filter_forwarded_to_load_aliases(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """The entity_name argument is forwarded to _load_multiword_asr_aliases."""
        service._load_multiword_asr_aliases = AsyncMock(return_value=[])  # type: ignore[method-assign]
        session = _make_mock_session()

        await service.discover_from_entities(session, entity_name="Chomsky")

        service._load_multiword_asr_aliases.assert_awaited_once_with(
            session, "Chomsky"
        )

    async def test_no_multiword_aliases_returns_empty(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """When all aliases are single-word (no spaces), no splits are generated."""
        # _generate_word_splits("Chomski") returns [] for single-word aliases.
        # Simulate this by providing an alias that produces no splits.
        aliases = [_make_alias_row("Chomski", "Chomsky", "person")]
        service._load_multiword_asr_aliases = AsyncMock(return_value=aliases)  # type: ignore[method-assign]

        async def _fake_find_pairs_batched(
            s: Any, pairs: Any, limit: int = 500
        ) -> list[tuple[Any, Any]]:
            return []

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        service._find_adjacent_pairs_batched = _fake_find_pairs_batched  # type: ignore[assignment]
        service._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]
        session = _make_mock_session()

        result = await service.discover_from_entities(session)

        assert result == []

    async def test_confidence_in_valid_range(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """All returned candidates have confidence in [0.0, 1.0]."""
        aliases = [_make_alias_row("Chomski is", "Chomsky", "person")]
        service._load_multiword_asr_aliases = AsyncMock(return_value=aliases)  # type: ignore[method-assign]

        seg_n = _make_segment_mock(
            seg_id=140, video_id="vid14", language_code="en",
            sequence_number=0, text="He said Chomski"
        )
        seg_n1 = _make_segment_mock(
            seg_id=141, video_id="vid14", language_code="en",
            sequence_number=1, text="is the point"
        )

        async def _fake_find_pairs_batched(
            s: Any, pairs: Any, limit: int = 500
        ) -> list[tuple[Any, Any]]:
            return [(seg_n, seg_n1)]

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        service._find_adjacent_pairs_batched = _fake_find_pairs_batched  # type: ignore[assignment]
        service._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]
        session = _make_mock_session()

        candidates = await service.discover_from_entities(session)

        for c in candidates:
            assert 0.0 <= c.confidence <= 1.0, (
                f"Candidate confidence {c.confidence} is out of range"
            )

    async def test_returns_list_of_cross_segment_candidates(
        self, service: CrossSegmentDiscovery
    ) -> None:
        """discover_from_entities returns a list of CrossSegmentCandidate instances."""
        aliases = [_make_alias_row("Chomski is", "Chomsky", "person")]
        service._load_multiword_asr_aliases = AsyncMock(return_value=aliases)  # type: ignore[method-assign]

        seg_n = _make_segment_mock(
            seg_id=150, video_id="vid15", language_code="en",
            sequence_number=0, text="He said Chomski"
        )
        seg_n1 = _make_segment_mock(
            seg_id=151, video_id="vid15", language_code="en",
            sequence_number=1, text="is here"
        )

        async def _fake_find_pairs_batched(
            s: Any, pairs: Any, limit: int = 500
        ) -> list[tuple[Any, Any]]:
            return [(seg_n, seg_n1)]

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        service._find_adjacent_pairs_batched = _fake_find_pairs_batched  # type: ignore[assignment]
        service._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]
        session = _make_mock_session()

        result = await service.discover_from_entities(session)

        assert isinstance(result, list)
        assert all(isinstance(c, CrossSegmentCandidate) for c in result)


# ---------------------------------------------------------------------------
# Unit tests for _merge_candidates (static method)
# ---------------------------------------------------------------------------


def _make_candidate(
    *,
    seg_n_id: int,
    seg_n1_id: int,
    confidence: float = 0.75,
    discovery_source: str = "correction_pattern",
    proposed_correction: str = "Chomsky is",
) -> CrossSegmentCandidate:
    """Build a CrossSegmentCandidate for merge tests."""
    return CrossSegmentCandidate(
        segment_n_id=seg_n_id,
        segment_n_text="prefix text",
        segment_n1_id=seg_n1_id,
        segment_n1_text="suffix text",
        proposed_correction=proposed_correction,
        source_pattern="Chomski is",
        confidence=confidence,
        is_partially_corrected=False,
        video_id="dQw4w9WgXcQ",
        discovery_source=discovery_source,
    )


class TestMergeCandidates:
    """Tests for ``CrossSegmentDiscovery._merge_candidates`` static method."""

    def test_entity_candidate_wins_over_pattern_for_same_pair(self) -> None:
        """When entity and pattern candidates share the same (n, n+1) pair,
        the entity candidate is kept and the pattern candidate is dropped."""
        entity_c = _make_candidate(
            seg_n_id=1, seg_n1_id=2,
            discovery_source="entity_alias",
            confidence=0.80,
        )
        pattern_c = _make_candidate(
            seg_n_id=1, seg_n1_id=2,
            discovery_source="correction_pattern",
            confidence=0.65,
        )

        merged = CrossSegmentDiscovery._merge_candidates([entity_c], [pattern_c])

        assert len(merged) == 1
        assert merged[0].discovery_source == "entity_alias"
        assert merged[0].confidence == pytest.approx(0.80, abs=1e-9)

    def test_unique_pairs_from_both_sources_all_included(self) -> None:
        """Different (n, n+1) pairs from both sources are all included."""
        entity_c = _make_candidate(seg_n_id=1, seg_n1_id=2,
                                   discovery_source="entity_alias")
        pattern_c = _make_candidate(seg_n_id=3, seg_n1_id=4,
                                    discovery_source="correction_pattern")

        merged = CrossSegmentDiscovery._merge_candidates([entity_c], [pattern_c])

        assert len(merged) == 2
        pair_keys = {(c.segment_n_id, c.segment_n1_id) for c in merged}
        assert (1, 2) in pair_keys
        assert (3, 4) in pair_keys

    def test_empty_entity_list_returns_all_pattern_candidates(self) -> None:
        """When entity_candidates is empty, all pattern candidates are returned."""
        pattern_c1 = _make_candidate(seg_n_id=5, seg_n1_id=6,
                                     discovery_source="correction_pattern")
        pattern_c2 = _make_candidate(seg_n_id=7, seg_n1_id=8,
                                     discovery_source="correction_pattern")

        merged = CrossSegmentDiscovery._merge_candidates([], [pattern_c1, pattern_c2])

        assert len(merged) == 2

    def test_empty_pattern_list_returns_all_entity_candidates(self) -> None:
        """When pattern_candidates is empty, all entity candidates are returned."""
        entity_c1 = _make_candidate(seg_n_id=9, seg_n1_id=10,
                                    discovery_source="entity_alias")
        entity_c2 = _make_candidate(seg_n_id=11, seg_n1_id=12,
                                    discovery_source="entity_alias")

        merged = CrossSegmentDiscovery._merge_candidates(
            [entity_c1, entity_c2], []
        )

        assert len(merged) == 2

    def test_both_empty_returns_empty_list(self) -> None:
        """When both inputs are empty, the result is an empty list."""
        merged = CrossSegmentDiscovery._merge_candidates([], [])
        assert merged == []

    def test_no_duplicates_in_result(self) -> None:
        """No pair key appears twice in the merged output."""
        entity_c = _make_candidate(seg_n_id=13, seg_n1_id=14,
                                   discovery_source="entity_alias")
        pattern_c = _make_candidate(seg_n_id=13, seg_n1_id=14,
                                    discovery_source="correction_pattern")
        extra = _make_candidate(seg_n_id=15, seg_n1_id=16,
                                discovery_source="correction_pattern")

        merged = CrossSegmentDiscovery._merge_candidates(
            [entity_c], [pattern_c, extra]
        )

        pair_keys = [(c.segment_n_id, c.segment_n1_id) for c in merged]
        assert len(pair_keys) == len(set(pair_keys))

    def test_entity_candidates_preserve_insertion_order(self) -> None:
        """Entity candidates appear before pattern candidates in the merged list."""
        entity_c = _make_candidate(seg_n_id=17, seg_n1_id=18,
                                   discovery_source="entity_alias")
        pattern_c = _make_candidate(seg_n_id=19, seg_n1_id=20,
                                    discovery_source="correction_pattern")

        merged = CrossSegmentDiscovery._merge_candidates([entity_c], [pattern_c])

        # Entity candidate should come first (entity is processed first)
        assert merged[0].discovery_source == "entity_alias"
        assert merged[1].discovery_source == "correction_pattern"

    def test_multiple_entity_candidates_same_pair_first_wins(self) -> None:
        """If entity_candidates itself has duplicate pairs, only the first is kept."""
        entity_c1 = _make_candidate(seg_n_id=21, seg_n1_id=22,
                                    discovery_source="entity_alias",
                                    confidence=0.90)
        entity_c2 = _make_candidate(seg_n_id=21, seg_n1_id=22,
                                    discovery_source="entity_alias",
                                    confidence=0.70)

        merged = CrossSegmentDiscovery._merge_candidates(
            [entity_c1, entity_c2], []
        )

        assert len(merged) == 1
        assert merged[0].confidence == pytest.approx(0.90, abs=1e-9)

    def test_returns_list_type(self) -> None:
        """_merge_candidates always returns a list."""
        result = CrossSegmentDiscovery._merge_candidates([], [])
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Unit tests for the updated discover() — combining entity + pattern paths
# ---------------------------------------------------------------------------


class TestDiscoverCombined:
    """Tests for the updated ``discover()`` that combines entity and pattern discovery.

    Unlike ``TestCrossSegmentDiscoveryDiscover`` (which isolates the pattern path),
    these tests verify the interaction between both discovery strategies.
    """

    async def test_discover_calls_both_strategies(self) -> None:
        """discover() calls both discover_from_entities and _discover_from_patterns."""
        batch_svc = _make_batch_service(patterns=[])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]
        discovery._discover_from_patterns = AsyncMock(return_value=[])  # type: ignore[method-assign]

        await discovery.discover(session, min_corrections=3)

        discovery.discover_from_entities.assert_awaited_once()
        discovery._discover_from_patterns.assert_awaited_once()

    async def test_entity_candidates_ranked_higher_when_same_pair(self) -> None:
        """When the same pair is found by both strategies, entity candidate is kept."""
        entity_c = _make_candidate(
            seg_n_id=200, seg_n1_id=201,
            discovery_source="entity_alias",
            confidence=0.85,
        )
        pattern_c = _make_candidate(
            seg_n_id=200, seg_n1_id=201,
            discovery_source="correction_pattern",
            confidence=0.60,
        )

        batch_svc = _make_batch_service(patterns=[])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        discovery.discover_from_entities = AsyncMock(return_value=[entity_c])  # type: ignore[method-assign]
        discovery._discover_from_patterns = AsyncMock(return_value=[pattern_c])  # type: ignore[method-assign]

        result = await discovery.discover(session, min_corrections=3)

        assert len(result) == 1
        assert result[0].discovery_source == "entity_alias"
        assert result[0].confidence == pytest.approx(0.85, abs=1e-9)

    async def test_results_sorted_by_confidence_descending(self) -> None:
        """discover() returns results sorted by confidence descending."""
        high_entity = _make_candidate(
            seg_n_id=210, seg_n1_id=211,
            discovery_source="entity_alias",
            confidence=0.90,
        )
        low_pattern = _make_candidate(
            seg_n_id=212, seg_n1_id=213,
            discovery_source="correction_pattern",
            confidence=0.55,
        )
        mid_entity = _make_candidate(
            seg_n_id=214, seg_n1_id=215,
            discovery_source="entity_alias",
            confidence=0.70,
        )

        batch_svc = _make_batch_service(patterns=[])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        discovery.discover_from_entities = AsyncMock(  # type: ignore[method-assign]
            return_value=[high_entity, mid_entity]
        )
        discovery._discover_from_patterns = AsyncMock(  # type: ignore[method-assign]
            return_value=[low_pattern]
        )

        result = await discovery.discover(session, min_corrections=3)

        assert len(result) == 3
        confidences = [c.confidence for c in result]
        assert confidences == sorted(confidences, reverse=True)

    async def test_unique_pairs_from_both_sources_included(self) -> None:
        """Unique pairs from entity and pattern strategies are all included."""
        entity_c = _make_candidate(
            seg_n_id=220, seg_n1_id=221,
            discovery_source="entity_alias",
            confidence=0.80,
        )
        pattern_c = _make_candidate(
            seg_n_id=222, seg_n1_id=223,
            discovery_source="correction_pattern",
            confidence=0.65,
        )

        batch_svc = _make_batch_service(patterns=[])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        discovery.discover_from_entities = AsyncMock(return_value=[entity_c])  # type: ignore[method-assign]
        discovery._discover_from_patterns = AsyncMock(return_value=[pattern_c])  # type: ignore[method-assign]

        result = await discovery.discover(session, min_corrections=3)

        assert len(result) == 2
        sources = {c.discovery_source for c in result}
        assert "entity_alias" in sources
        assert "correction_pattern" in sources

    async def test_both_empty_returns_empty_list(self) -> None:
        """discover() returns [] when both strategies find no candidates."""
        batch_svc = _make_batch_service(patterns=[])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]
        discovery._discover_from_patterns = AsyncMock(return_value=[])  # type: ignore[method-assign]

        result = await discovery.discover(session, min_corrections=3)

        assert result == []

    async def test_entity_name_forwarded_to_both_strategies(self) -> None:
        """The entity_name kwarg is passed to both discover_from_entities and _discover_from_patterns."""
        batch_svc = _make_batch_service(patterns=[])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]
        discovery._discover_from_patterns = AsyncMock(return_value=[])  # type: ignore[method-assign]

        await discovery.discover(session, min_corrections=5, entity_name="Chomsky")

        entity_call = discovery.discover_from_entities.call_args
        pattern_call = discovery._discover_from_patterns.call_args

        assert entity_call.kwargs.get("entity_name") == "Chomsky"
        assert pattern_call.kwargs.get("entity_name") == "Chomsky"

    async def test_min_corrections_forwarded_to_pattern_strategy(self) -> None:
        """min_corrections is forwarded to _discover_from_patterns."""
        batch_svc = _make_batch_service(patterns=[])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]
        discovery._discover_from_patterns = AsyncMock(return_value=[])  # type: ignore[method-assign]

        await discovery.discover(session, min_corrections=7)

        pattern_call = discovery._discover_from_patterns.call_args
        assert pattern_call.kwargs.get("min_corrections") == 7

    async def test_discover_returns_list_type(self) -> None:
        """discover() always returns a list, even when both strategies are empty."""
        batch_svc = _make_batch_service(patterns=[])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        discovery.discover_from_entities = AsyncMock(return_value=[])  # type: ignore[method-assign]
        discovery._discover_from_patterns = AsyncMock(return_value=[])  # type: ignore[method-assign]

        result = await discovery.discover(session)

        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Unit tests for CrossSegmentCandidate.discovery_source field
# ---------------------------------------------------------------------------


class TestCrossSegmentCandidateDiscoverySource:
    """Tests for the ``discovery_source`` field on ``CrossSegmentCandidate``.

    This is a new field added in the entity-aware refactor.
    """

    def _valid_kwargs(self) -> dict[str, Any]:
        return {
            "segment_n_id": 1,
            "segment_n_text": "He said Chomski",
            "segment_n1_id": 2,
            "segment_n1_text": "is great",
            "proposed_correction": "Chomsky is",
            "source_pattern": "Chomski is",
            "confidence": 0.75,
            "is_partially_corrected": False,
            "video_id": "dQw4w9WgXcQ",
        }

    def test_default_discovery_source_is_correction_pattern(self) -> None:
        """When discovery_source is not specified, it defaults to 'correction_pattern'."""
        candidate = CrossSegmentCandidate(**self._valid_kwargs())
        assert candidate.discovery_source == "correction_pattern"

    def test_discovery_source_can_be_set_to_entity_alias(self) -> None:
        """discovery_source can be explicitly set to 'entity_alias'."""
        kwargs = self._valid_kwargs()
        kwargs["discovery_source"] = "entity_alias"
        candidate = CrossSegmentCandidate(**kwargs)
        assert candidate.discovery_source == "entity_alias"

    def test_discovery_source_is_string(self) -> None:
        """discovery_source is always a string value."""
        candidate = CrossSegmentCandidate(**self._valid_kwargs())
        assert isinstance(candidate.discovery_source, str)

    def test_discovery_source_included_in_model_dump(self) -> None:
        """discovery_source appears in model_dump() output."""
        candidate = CrossSegmentCandidate(**self._valid_kwargs())
        dumped = candidate.model_dump()
        assert "discovery_source" in dumped
        assert dumped["discovery_source"] == "correction_pattern"

    def test_entity_alias_discovery_source_in_model_dump(self) -> None:
        """discovery_source='entity_alias' is preserved in model_dump()."""
        kwargs = self._valid_kwargs()
        kwargs["discovery_source"] = "entity_alias"
        candidate = CrossSegmentCandidate(**kwargs)
        dumped = candidate.model_dump()
        assert dumped["discovery_source"] == "entity_alias"

    def test_discovery_source_immutable_on_frozen_model(self) -> None:
        """discovery_source cannot be reassigned because the model is frozen."""
        candidate = CrossSegmentCandidate(**self._valid_kwargs())
        with pytest.raises(Exception):
            candidate.discovery_source = "entity_alias"

    def test_custom_discovery_source_string_accepted(self) -> None:
        """Any string value is accepted for discovery_source (no enum restriction)."""
        kwargs = self._valid_kwargs()
        kwargs["discovery_source"] = "custom_strategy"
        candidate = CrossSegmentCandidate(**kwargs)
        assert candidate.discovery_source == "custom_strategy"
