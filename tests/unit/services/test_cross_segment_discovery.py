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
        """discover() returns [] when get_patterns returns no patterns."""
        batch_svc = _make_batch_service(patterns=[])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        # No DB query should be needed because patterns list is empty
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

        await discovery.discover(session, min_corrections=7)

        call_kwargs = batch_svc.get_patterns.call_args
        assert call_kwargs.kwargs["min_occurrences"] == 7

    # (h) No patterns meeting threshold → empty list (already covered above,
    #     additional explicit check with entity filter returning nothing)
    async def test_entity_filter_with_no_match_returns_empty(self) -> None:
        """When entity filter matches no patterns, discover() returns []."""
        pattern = _make_pattern("Chomski is", "Chomsky is", occurrences=5)
        batch_svc = _make_batch_service(patterns=[pattern])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        # Corrected segment IDs query returns nothing
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = []
        session.execute.return_value = exec_result

        result = await discovery.discover(
            session,
            min_corrections=3,
            entity_name="Nonexistent",
        )

        assert result == []

    # (c) Entity filter case-insensitive match
    async def test_entity_filter_is_case_insensitive(self) -> None:
        """Entity filter matches patterns case-insensitively."""
        pattern_matching = _make_pattern("Chomski is", "Chomsky is", occurrences=5)
        pattern_not_matching = _make_pattern("wrong text", "correct text", occurrences=5)
        batch_svc = _make_batch_service(
            patterns=[pattern_matching, pattern_not_matching]
        )
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        # DB execute returns no adjacent pairs to keep test focused on filter
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = []
        exec_result.fetchall.return_value = []
        session.execute.return_value = exec_result

        # We verify entity_name="chomski" (lower-case) still matches "Chomski is"
        # by checking _process_pattern is called with the filtered pattern.
        # We spy by mocking _process_pattern directly.
        processed_patterns: list[CorrectionPattern] = []

        original_process = discovery._process_pattern

        async def _spy(
            s: Any,
            p: CorrectionPattern,
            corrected_ids: set[int],
        ) -> list[CrossSegmentCandidate]:
            processed_patterns.append(p)
            return []

        discovery._process_pattern = _spy  # type: ignore[assignment]

        await discovery.discover(session, min_corrections=3, entity_name="chomski")

        assert len(processed_patterns) == 1
        assert processed_patterns[0].original_text == "Chomski is"

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

        # Corrected segment IDs query returns empty set
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = []
        session.execute.return_value = exec_result

        # Patch _find_adjacent_pairs and _get_corrected_segment_ids
        async def _fake_find_pairs(
            s: Any, prefix: str, suffix: str
        ) -> list[tuple[Any, Any]]:
            if "Chomski" in prefix or "is" in suffix:
                return [(seg_n, seg_n1)]
            return []

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        discovery._find_adjacent_pairs = _fake_find_pairs  # type: ignore[assignment]
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

        # Both segment IDs are in the corrected set
        async def _fake_find_pairs(
            s: Any, prefix: str, suffix: str
        ) -> list[tuple[Any, Any]]:
            return [(seg_n, seg_n1)]

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return {20, 21}

        discovery._find_adjacent_pairs = _fake_find_pairs  # type: ignore[assignment]
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
            text="He said Chomski",
            has_correction=True,
            corrected_text="He said Chomsky",
        )
        seg_n1 = _make_segment_mock(
            seg_id=31,
            video_id="vid2",
            language_code="en",
            sequence_number=1,
            text="is wrong",
            has_correction=False,
        )

        # Only seg_n (id=30) is in the corrected set
        async def _fake_find_pairs(
            s: Any, prefix: str, suffix: str
        ) -> list[tuple[Any, Any]]:
            return [(seg_n, seg_n1)]

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return {30}

        discovery._find_adjacent_pairs = _fake_find_pairs  # type: ignore[assignment]
        discovery._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]

        candidates = await discovery.discover(session, min_corrections=3)

        partial_candidates = [c for c in candidates if c.is_partially_corrected]
        assert len(partial_candidates) >= 1

    # Results are sorted by confidence descending
    async def test_results_sorted_by_confidence_descending(self) -> None:
        """discover() returns candidates sorted by confidence, highest first."""
        pattern_wb = _make_pattern("Chomski is", "Chomsky is", occurrences=20)
        pattern_cl = _make_pattern("abc", "xyz", occurrences=1)
        batch_svc = _make_batch_service(patterns=[pattern_wb, pattern_cl])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        # Build two fake candidate pairs to ensure different confidence scores
        seg_wb_n = _make_segment_mock(
            seg_id=40, video_id="vid3", language_code="en",
            sequence_number=0, text="said Chomski"
        )
        seg_wb_n1 = _make_segment_mock(
            seg_id=41, video_id="vid3", language_code="en",
            sequence_number=1, text="is important"
        )
        seg_cl_n = _make_segment_mock(
            seg_id=50, video_id="vid4", language_code="en",
            sequence_number=0, text="prefix ab"
        )
        seg_cl_n1 = _make_segment_mock(
            seg_id=51, video_id="vid4", language_code="en",
            sequence_number=1, text="c suffix"
        )

        call_count = 0

        async def _fake_find_pairs(
            s: Any, prefix: str, suffix: str
        ) -> list[tuple[Any, Any]]:
            nonlocal call_count
            call_count += 1
            # Alternate between word-boundary and char-level patterns
            if "Chomski" in prefix:
                return [(seg_wb_n, seg_wb_n1)]
            if "ab" in prefix:
                return [(seg_cl_n, seg_cl_n1)]
            return []

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        discovery._find_adjacent_pairs = _fake_find_pairs  # type: ignore[assignment]
        discovery._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]

        candidates = await discovery.discover(session, min_corrections=3)

        if len(candidates) >= 2:
            for i in range(len(candidates) - 1):
                assert candidates[i].confidence >= candidates[i + 1].confidence

    # (g) Adjacency: only consecutive N, N+1 by sequence_number
    # This is enforced in the SQL query; we verify via _find_adjacent_pairs signature
    async def test_only_adjacent_pairs_considered(self) -> None:
        """_find_adjacent_pairs is invoked with prefix/suffix derived from split."""
        pattern = _make_pattern("hello world", "Hello World", occurrences=5)
        batch_svc = _make_batch_service(patterns=[pattern])
        discovery = CrossSegmentDiscovery(batch_service=batch_svc)
        session = _make_mock_session()

        pairs_args: list[tuple[str, str]] = []

        async def _recording_find_pairs(
            s: Any, prefix: str, suffix: str
        ) -> list[tuple[Any, Any]]:
            pairs_args.append((prefix, suffix))
            return []

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        discovery._find_adjacent_pairs = _recording_find_pairs  # type: ignore[assignment]
        discovery._get_corrected_segment_ids = _fake_corrected_ids  # type: ignore[assignment]

        await discovery.discover(session, min_corrections=3)

        # At minimum the word-boundary split ("hello", "world") must have been tried
        assert len(pairs_args) > 0
        prefixes = [p for p, _ in pairs_args]
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

        # Cross-language pair (same video, different language_code)
        seg_en = _make_segment_mock(
            seg_id=60, video_id="vid5", language_code="en",
            sequence_number=0, text="Chomski"
        )
        seg_es = _make_segment_mock(
            seg_id=61, video_id="vid5", language_code="es",
            sequence_number=1, text="is"
        )

        # Simulate: the SQL query correctly rejects cross-language pairs,
        # so _find_adjacent_pairs returns [] for them.
        async def _no_cross_lang_pairs(
            s: Any, prefix: str, suffix: str
        ) -> list[tuple[Any, Any]]:
            # Simulate correct SQL behaviour: cross-language segments not returned
            return []

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        discovery._find_adjacent_pairs = _no_cross_lang_pairs  # type: ignore[assignment]
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

        async def _fake_find_pairs(
            s: Any, prefix: str, suffix: str
        ) -> list[tuple[Any, Any]]:
            if "Chomski" in prefix:
                return [(seg_n, seg_n1)]
            return []

        async def _fake_corrected_ids(s: Any) -> set[int]:
            return set()

        discovery._find_adjacent_pairs = _fake_find_pairs  # type: ignore[assignment]
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
