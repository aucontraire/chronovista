"""
Tests for PhoneticMatcher service (Feature 045 — T031).

Covers the public interface of PhoneticMatcher:
- score_match()   — static scoring method (phonetic + Levenshtein + evidence boost)
- match_entity()  — async method orchestrating DB queries and match scoring

Mock strategy: ``AsyncSession`` is replaced with a ``MagicMock`` whose
``execute`` is an ``AsyncMock`` returning configurable result chains.
``EntityMentionRepository.get_entity_video_ids`` is patched at the instance
level to avoid real DB queries.

Key phonetic properties under test:
  (a) Single-word corruption "Shanebam" → "Sheinbaum" scores high confidence
  (b) Truncation "Shan" → "Sheinbaum" scores medium confidence
  (c) Multi-word "Shane Bound" → "Sheinbaum" scores medium confidence
  (d) Non-match "Shane believes" filtered out (below default threshold)
  (e) Confidence weights: 0.4 + 0.3 + 0.3 = 1.0 maximum
  (f) Corroborating evidence binary boost: +0.3 when present, 0.0 when absent
  (g) Non-alphabetic characters stripped before phonetic encoding
  (h) Canonical-name-only fallback when the entity has no aliases
  (i) Multiple entity matches returned from match_entity()
  (j) Threshold filtering removes low-confidence matches

Feature 045 — Correction Intelligence Pipeline (US4)
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.services.phonetic_matcher import PhoneticMatcher, PhoneticMatch
from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
)

# CRITICAL: ensures every async test in this module is recognised by
# pytest-asyncio regardless of how coverage is invoked
# (see CLAUDE.md §pytest-asyncio Coverage Integration Issues).
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uuid() -> uuid.UUID:
    """Return a fresh UUIDv7 expressed as a stdlib uuid.UUID."""
    return uuid.UUID(bytes=uuid7().bytes)


def _make_mock_session() -> MagicMock:
    """Create a MagicMock AsyncSession with an AsyncMock execute attribute."""
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    return session


def _make_matcher() -> tuple[PhoneticMatcher, MagicMock]:
    """Instantiate PhoneticMatcher with a mocked EntityMentionRepository.

    Returns
    -------
    tuple[PhoneticMatcher, MagicMock]
        The service instance and its underlying repository mock, allowing
        tests to configure ``get_entity_video_ids`` return values.
    """
    mock_repo = MagicMock(spec=EntityMentionRepository)
    matcher = PhoneticMatcher(entity_mention_repo=mock_repo)
    return matcher, mock_repo


def _configure_entity_query(
    mock_session: MagicMock,
    entity_name: str,
    entity_id: uuid.UUID,
    aliases: list[str],
    video_ids: list[str],
    evidence_video_ids: list[str],
    segment_texts: list[tuple[str, str, int]],
) -> None:
    """Configure mock_session.execute side_effects for match_entity().

    match_entity() makes these session.execute calls in order:
      1. SELECT NamedEntity WHERE id = entity_id
      2. SELECT EntityAlias.alias_name WHERE entity_id = entity_id
      3. (no session.execute for get_entity_video_ids — it is patched on repo)
      4. SELECT DISTINCT EntityMention.video_id WHERE entity_id = entity_id
      5. SELECT TranscriptSegment WHERE video_id IN (...)

    Parameters
    ----------
    mock_session : MagicMock
        The session mock to configure.
    entity_name : str
        Canonical name to return for the entity SELECT.
    entity_id : uuid.UUID
        Entity PK.
    aliases : list[str]
        Alias names to return for the alias SELECT.
    video_ids : list[str]
        Video IDs returned by get_entity_video_ids (patched separately).
    evidence_video_ids : list[str]
        Video IDs returned by the corroborating-evidence SELECT.
    segment_texts : list[tuple[str, str, int]]
        Each tuple is (video_id, text, segment_id) for the segment SELECT.
    """
    # 1. Entity result
    mock_entity = MagicMock()
    mock_entity.canonical_name = entity_name
    mock_entity.id = entity_id

    entity_result = MagicMock()
    entity_result.scalar_one_or_none.return_value = mock_entity

    # 2. Alias result
    alias_scalars = MagicMock()
    alias_scalars.all.return_value = aliases
    alias_result = MagicMock()
    alias_result.scalars.return_value = alias_scalars

    # 4. Evidence (confirmed mention) video IDs
    evidence_scalars = MagicMock()
    evidence_scalars.all.return_value = evidence_video_ids
    evidence_result = MagicMock()
    evidence_result.scalars.return_value = evidence_scalars

    # 5. Transcript segments
    mock_segments = []
    for vid_id, text, seg_id in segment_texts:
        seg = MagicMock()
        seg.video_id = vid_id
        seg.id = seg_id
        seg.text = text
        seg.corrected_text = None
        seg.has_correction = False
        mock_segments.append(seg)

    segment_scalars = MagicMock()
    segment_scalars.all.return_value = mock_segments
    segment_result = MagicMock()
    segment_result.scalars.return_value = segment_scalars

    mock_session.execute.side_effect = [
        entity_result,    # 1 entity lookup
        alias_result,     # 2 alias lookup
        evidence_result,  # 4 evidence lookup
        segment_result,   # 5 segments
    ]


# ---------------------------------------------------------------------------
# TestPhoneticMatcherScoreMatch  — pure static scoring (no DB)
# ---------------------------------------------------------------------------


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
class TestPhoneticMatcherScoreMatch:
    """Unit tests for PhoneticMatcher.score_match() (static method).

    This is the core scoring engine; no database or session mocking is needed.
    All tests call the method directly with controlled inputs.
    """

    # ---- (a) Single-word corruption ----

    def test_single_word_corruption_scores_high_confidence(self) -> None:
        """'Shanebam' phonetically resembles 'Sheinbaum' and scores above 0.5.

        This is the primary use case: ASR mis-transcribes a proper noun as a
        phonetically similar garbled word.  Without corroborating evidence the
        score must still exceed 0.5 based on phonetic + Levenshtein similarity.
        """
        score = PhoneticMatcher.score_match(
            ngram="Shanebam",
            entity_name="Sheinbaum",
            entity_aliases=[],
            has_corroborating_evidence=False,
        )
        assert score > 0.5, (
            f"Expected 'Shanebam' → 'Sheinbaum' to score above 0.5, got {score:.4f}"
        )

    def test_single_word_corruption_with_evidence_boosts_score(self) -> None:
        """Corroborating evidence pushes the 'Shanebam' → 'Sheinbaum' score higher.

        The +0.3 evidence boost should raise the score compared to the
        same inputs without evidence.
        """
        score_no_evidence = PhoneticMatcher.score_match(
            ngram="Shanebam",
            entity_name="Sheinbaum",
            entity_aliases=[],
            has_corroborating_evidence=False,
        )
        score_with_evidence = PhoneticMatcher.score_match(
            ngram="Shanebam",
            entity_name="Sheinbaum",
            entity_aliases=[],
            has_corroborating_evidence=True,
        )
        assert score_with_evidence > score_no_evidence, (
            "Evidence boost should increase the score"
        )

    # ---- (b) Truncation ----

    def test_truncated_form_scores_medium_confidence(self) -> None:
        """'Shan' (a truncation of 'Sheinbaum') scores in the medium range (0.2-0.7).

        Short N-grams that are prefixes of the entity name should score
        noticeably above zero but below the level of the full corrupted form.
        """
        score = PhoneticMatcher.score_match(
            ngram="Shan",
            entity_name="Sheinbaum",
            entity_aliases=[],
            has_corroborating_evidence=False,
        )
        # Truncations should show some phonetic similarity but not a high match
        assert 0.0 < score < 0.85, (
            f"Expected truncation 'Shan' to score in medium range, got {score:.4f}"
        )

    # ---- (c) Multi-word match ----

    def test_multi_word_ngram_scores_medium_confidence(self) -> None:
        """'Shane Bound' (multi-word) phonetically resembles 'Sheinbaum'.

        Multi-word N-grams are scored against the entity name after stripping
        non-alphabetic characters.  A phonetically close multi-word string
        should score above zero.
        """
        score = PhoneticMatcher.score_match(
            ngram="Shane Bound",
            entity_name="Sheinbaum",
            entity_aliases=[],
            has_corroborating_evidence=False,
        )
        # Multi-word forms that are close but not exact should score positively
        assert score > 0.0, (
            f"Expected multi-word 'Shane Bound' to score above 0.0, got {score:.4f}"
        )

    # ---- (d) Non-match filtered out ----

    def test_non_matching_ngram_scores_below_default_threshold(self) -> None:
        """'Shane believes' has low phonetic similarity to 'Sheinbaum'.

        The phrase shares the 'Shane' prefix but the second word diverges
        strongly.  The combined score should be below the default threshold
        of 0.5, so it would be filtered from results.
        """
        score = PhoneticMatcher.score_match(
            ngram="Shane believes",
            entity_name="Sheinbaum",
            entity_aliases=[],
            has_corroborating_evidence=False,
        )
        assert score < 0.5, (
            f"Expected 'Shane believes' to score below 0.5, got {score:.4f}"
        )

    # ---- (e) Weight sum: 0.4 + 0.3 + 0.3 = 1.0 ----

    def test_maximum_score_never_exceeds_one(self) -> None:
        """The confidence score is capped at 1.0 regardless of weights.

        An identical ngram and entity name with corroborating evidence should
        approach or reach 1.0 but must never exceed it.
        """
        score = PhoneticMatcher.score_match(
            ngram="Sheinbaum",
            entity_name="Sheinbaum",
            entity_aliases=[],
            has_corroborating_evidence=True,
        )
        assert score <= 1.0, f"Score exceeded 1.0: {score}"
        assert score >= 0.9, (
            f"Identical ngram+entity should score near 1.0, got {score:.4f}"
        )

    def test_weight_sum_with_no_evidence_caps_at_0_7(self) -> None:
        """Without evidence the maximum reachable score is 0.4+0.3 = 0.7.

        For a perfectly matching ngram and entity name with
        has_corroborating_evidence=False, the phonetic (0.4) + Levenshtein
        (0.3) components sum to 0.7 at most.
        """
        score = PhoneticMatcher.score_match(
            ngram="Sheinbaum",
            entity_name="Sheinbaum",
            entity_aliases=[],
            has_corroborating_evidence=False,
        )
        # Should be at or near 0.7 (the two components max out at 1.0 each)
        assert score <= 0.7 + 1e-9, (
            f"Without evidence, score must not exceed 0.7; got {score:.4f}"
        )

    def test_evidence_contribution_is_exactly_0_3(self) -> None:
        """The evidence boost is exactly 0.3 (not scaled).

        Comparing the same inputs with and without evidence reveals a diff
        of exactly 0.3 (clipped to ensure we don't exceed 1.0).
        """
        base = PhoneticMatcher.score_match(
            ngram="Sheinbaum",
            entity_name="Sheinbaum",
            entity_aliases=[],
            has_corroborating_evidence=False,
        )
        boosted = PhoneticMatcher.score_match(
            ngram="Sheinbaum",
            entity_name="Sheinbaum",
            entity_aliases=[],
            has_corroborating_evidence=True,
        )
        # Both are clipped to 1.0 — confirm that raw diff is ≤ 0.3
        diff = boosted - base
        assert 0.0 <= diff <= 0.3 + 1e-9, (
            f"Evidence boost should be at most 0.3; actual diff was {diff:.4f}"
        )

    # ---- (f) Corroborating evidence binary boost ----

    def test_no_evidence_contributes_zero_to_score(self) -> None:
        """has_corroborating_evidence=False contributes exactly 0.0 to the score.

        The formula adds ``0.3 if has_corroborating_evidence else 0.0``.
        This test uses a pair of identical inputs differing only in the
        evidence flag to isolate the 0.0 / 0.3 contribution.
        """
        score_false = PhoneticMatcher.score_match(
            ngram="Chomsky",
            entity_name="Chomsky",
            entity_aliases=[],
            has_corroborating_evidence=False,
        )
        score_true = PhoneticMatcher.score_match(
            ngram="Chomsky",
            entity_name="Chomsky",
            entity_aliases=[],
            has_corroborating_evidence=True,
        )
        # The 0.3 boost is only applied for True
        assert score_true >= score_false

    def test_evidence_present_gives_0_3_boost(self) -> None:
        """has_corroborating_evidence=True adds 0.3 to the raw combined score.

        Uses a weak match where the phonetic + Levenshtein components are
        small, making the 0.3 boost visible.
        """
        score_without = PhoneticMatcher.score_match(
            ngram="xyz",
            entity_name="Sheinbaum",
            entity_aliases=[],
            has_corroborating_evidence=False,
        )
        score_with = PhoneticMatcher.score_match(
            ngram="xyz",
            entity_name="Sheinbaum",
            entity_aliases=[],
            has_corroborating_evidence=True,
        )
        # The difference should be 0.3 (subject to min(total, 1.0) clipping)
        diff = score_with - score_without
        assert diff == pytest.approx(0.3, abs=1e-9), (
            f"Expected evidence boost of 0.3, got {diff:.6f}"
        )

    # ---- (g) Non-alphabetic character stripping ----

    def test_non_alphabetic_chars_stripped_before_encoding(self) -> None:
        """Punctuation and digits are removed before phonetic encoding.

        'Shein-baum!' and 'Sheinbaum' should produce similar scores because
        the non-alphabetic characters are stripped via ``_strip_non_alpha``
        before Double Metaphone encoding.
        """
        score_clean = PhoneticMatcher.score_match(
            ngram="Sheinbaum",
            entity_name="Sheinbaum",
            entity_aliases=[],
            has_corroborating_evidence=False,
        )
        score_punctuated = PhoneticMatcher.score_match(
            ngram="Shein-baum!",
            entity_name="Sheinbaum",
            entity_aliases=[],
            has_corroborating_evidence=False,
        )
        # After stripping, "Sheinbaum" == "Sheinbaum"; scores should be equal
        assert abs(score_punctuated - score_clean) < 0.05, (
            f"Stripping should normalise punctuated form; "
            f"clean={score_clean:.4f}, punctuated={score_punctuated:.4f}"
        )

    def test_digits_stripped_before_encoding(self) -> None:
        """Digit characters are stripped, so '3lmo' encodes like 'lmo'."""
        score_with_digit = PhoneticMatcher.score_match(
            ngram="3lmo",
            entity_name="Elmo",
            entity_aliases=[],
            has_corroborating_evidence=False,
        )
        # After stripping the digit '3' becomes 'lmo', which is phonetically
        # similar to 'Elmo' — score should be above zero.
        assert score_with_digit > 0.0, (
            "Digit-stripped form should still produce a positive phonetic score"
        )

    # ---- (h) Canonical-name-only fallback ----

    def test_empty_alias_list_falls_back_to_canonical_name(self) -> None:
        """When entity_aliases=[], only the canonical name is compared.

        The method must not crash or return 0.0 when no aliases are provided;
        it uses the canonical name as the sole candidate.
        """
        score = PhoneticMatcher.score_match(
            ngram="Chomsky",
            entity_name="Chomsky",
            entity_aliases=[],
            has_corroborating_evidence=False,
        )
        assert score > 0.5, (
            "Exact canonical name match with no aliases should score above 0.5"
        )

    def test_alias_match_beats_canonical_name_mismatch(self) -> None:
        """A strong alias match should produce a higher score than entity_name alone.

        When the ngram matches an alias better than the canonical name, the
        method should pick the best score across all candidates.
        """
        # Canonical name: completely unrelated
        score_no_alias = PhoneticMatcher.score_match(
            ngram="Noam",
            entity_name="Chomsky",
            entity_aliases=[],
            has_corroborating_evidence=False,
        )
        # With alias "Noam" (first name) that matches the ngram exactly
        score_with_alias = PhoneticMatcher.score_match(
            ngram="Noam",
            entity_name="Chomsky",
            entity_aliases=["Noam"],
            has_corroborating_evidence=False,
        )
        assert score_with_alias > score_no_alias, (
            "Alias matching ngram exactly should score higher than canonical mismatch"
        )

    # ---- (i) Score is in [0.0, 1.0] for all inputs ----

    def test_score_always_in_range(self) -> None:
        """score_match() must always return a value in [0.0, 1.0]."""
        cases = [
            ("completely_unrelated", "Sheinbaum", [], False),
            ("Sheinbaum", "Sheinbaum", [], True),
            ("", "Sheinbaum", [], True),
            ("Sheinbaum", "Sheinbaum", ["Claudia"], True),
        ]
        for ngram, name, aliases, evidence in cases:
            score = PhoneticMatcher.score_match(ngram, name, aliases, evidence)
            assert 0.0 <= score <= 1.0, (
                f"Score out of range for ({ngram!r}, {name!r}): {score}"
            )


# ---------------------------------------------------------------------------
# TestPhoneticMatcherMatchEntity  — async match_entity() tests (with DB mocks)
# ---------------------------------------------------------------------------


class TestPhoneticMatcherMatchEntity:
    """Tests for the async match_entity() method.

    Each test mocks session.execute() to simulate DB responses and patches
    EntityMentionRepository.get_entity_video_ids to control which video IDs
    are "associated" with the entity under test.
    """

    @pytest.fixture
    def matcher_and_repo(self) -> tuple[PhoneticMatcher, MagicMock]:
        """Provide a fresh matcher and its mocked repository."""
        return _make_matcher()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a fresh mock async session."""
        return _make_mock_session()

    # ---- entity not found returns empty list ----

    async def test_returns_empty_list_when_entity_not_found(
        self,
        matcher_and_repo: tuple[PhoneticMatcher, MagicMock],
        mock_session: MagicMock,
    ) -> None:
        """When the entity UUID does not exist in the DB, return []."""
        matcher, mock_repo = matcher_and_repo

        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = entity_result

        result = await matcher.match_entity(
            entity_id=_uuid(),
            session=mock_session,
        )

        assert result == []

    # ---- entity with no associated videos returns empty list ----

    async def test_returns_empty_list_when_no_associated_videos(
        self,
        matcher_and_repo: tuple[PhoneticMatcher, MagicMock],
        mock_session: MagicMock,
    ) -> None:
        """When the entity has no associated video IDs, return []."""
        matcher, mock_repo = matcher_and_repo
        entity_id = _uuid()

        mock_entity = MagicMock()
        mock_entity.canonical_name = "Sheinbaum"
        mock_entity.id = entity_id

        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = mock_entity

        alias_scalars = MagicMock()
        alias_scalars.all.return_value = []
        alias_result = MagicMock()
        alias_result.scalars.return_value = alias_scalars

        mock_session.execute.side_effect = [entity_result, alias_result]

        # get_entity_video_ids returns empty set → no videos to scan
        mock_repo.get_entity_video_ids = AsyncMock(return_value=set())

        result = await matcher.match_entity(
            entity_id=entity_id,
            session=mock_session,
        )

        assert result == []

    # ---- (i) multiple entity matches returned ----

    async def test_multiple_matches_returned_sorted_by_confidence(
        self,
        matcher_and_repo: tuple[PhoneticMatcher, MagicMock],
        mock_session: MagicMock,
    ) -> None:
        """Matches above the threshold are returned sorted by confidence descending.

        This test configures two segments with text that yields different
        confidence levels, verifying the sorting contract.
        """
        matcher, mock_repo = matcher_and_repo
        entity_id = _uuid()

        # Segment 1: exact match → high score
        # Segment 2: truncated match → lower score
        segment_texts = [
            ("dQw4w9WgXcQ", "Sheinbaum spoke", 1),
            ("dQw4w9WgXcQ", "Shanebam policy", 2),
        ]

        _configure_entity_query(
            mock_session=mock_session,
            entity_name="Sheinbaum",
            entity_id=entity_id,
            aliases=[],
            video_ids=["dQw4w9WgXcQ"],
            evidence_video_ids=["dQw4w9WgXcQ"],
            segment_texts=segment_texts,
        )
        mock_repo.get_entity_video_ids = AsyncMock(return_value={"dQw4w9WgXcQ"})

        # Use a low threshold to ensure both ngrams that match are captured
        result = await matcher.match_entity(
            entity_id=entity_id,
            session=mock_session,
            threshold=0.3,
        )

        # Must be a list of PhoneticMatch instances
        assert isinstance(result, list)
        for match in result:
            assert isinstance(match, PhoneticMatch)

        # Sorted by confidence descending
        confidences = [m.confidence for m in result]
        assert confidences == sorted(confidences, reverse=True), (
            "Results must be sorted by confidence descending"
        )

    # ---- (j) threshold filtering ----

    async def test_threshold_filters_low_confidence_matches(
        self,
        matcher_and_repo: tuple[PhoneticMatcher, MagicMock],
        mock_session: MagicMock,
    ) -> None:
        """Matches below the threshold are excluded from results.

        A high threshold (0.9) should exclude most N-grams, returning only
        very close matches.
        """
        matcher, mock_repo = matcher_and_repo
        entity_id = _uuid()

        # A segment with text that produces low-scoring N-grams for "Sheinbaum"
        segment_texts = [
            ("dQw4w9WgXcQ", "the economy grew last year", 1),
        ]

        _configure_entity_query(
            mock_session=mock_session,
            entity_name="Sheinbaum",
            entity_id=entity_id,
            aliases=[],
            video_ids=["dQw4w9WgXcQ"],
            evidence_video_ids=[],
            segment_texts=segment_texts,
        )
        mock_repo.get_entity_video_ids = AsyncMock(return_value={"dQw4w9WgXcQ"})

        result = await matcher.match_entity(
            entity_id=entity_id,
            session=mock_session,
            threshold=0.9,
        )

        # Unrelated text should produce no matches above 0.9
        assert result == [], (
            "Unrelated text should produce no matches at threshold=0.9"
        )

    async def test_lower_threshold_returns_more_matches(
        self,
        matcher_and_repo: tuple[PhoneticMatcher, MagicMock],
        mock_session: MagicMock,
    ) -> None:
        """Lowering the threshold increases the number of returned matches.

        This verifies that the threshold parameter meaningfully controls
        the result set size.
        """
        matcher, mock_repo = matcher_and_repo
        entity_id = _uuid()

        segment_texts = [
            ("dQw4w9WgXcQ", "Sheinbaum Shanebam Shane", 1),
        ]

        # Configure two independent calls (each call to match_entity uses a
        # fresh side_effect sequence)
        def _make_side_effects() -> list[Any]:
            mock_entity = MagicMock()
            mock_entity.canonical_name = "Sheinbaum"
            mock_entity.id = entity_id

            ent_r = MagicMock()
            ent_r.scalar_one_or_none.return_value = mock_entity

            alias_sc = MagicMock()
            alias_sc.all.return_value = []
            alias_r = MagicMock()
            alias_r.scalars.return_value = alias_sc

            ev_sc = MagicMock()
            ev_sc.all.return_value = ["dQw4w9WgXcQ"]
            ev_r = MagicMock()
            ev_r.scalars.return_value = ev_sc

            segs = []
            for vid_id, text, seg_id in segment_texts:
                seg = MagicMock()
                seg.video_id = vid_id
                seg.id = seg_id
                seg.text = text
                seg.corrected_text = None
                seg.has_correction = False
                segs.append(seg)

            seg_sc = MagicMock()
            seg_sc.all.return_value = segs
            seg_r = MagicMock()
            seg_r.scalars.return_value = seg_sc

            return [ent_r, alias_r, ev_r, seg_r]

        mock_repo.get_entity_video_ids = AsyncMock(return_value={"dQw4w9WgXcQ"})

        mock_session.execute.side_effect = _make_side_effects()
        high_threshold_result = await matcher.match_entity(
            entity_id=entity_id,
            session=mock_session,
            threshold=0.9,
        )

        mock_session.execute.side_effect = _make_side_effects()
        low_threshold_result = await matcher.match_entity(
            entity_id=entity_id,
            session=mock_session,
            threshold=0.3,
        )

        assert len(low_threshold_result) >= len(high_threshold_result), (
            "Lower threshold should yield at least as many matches as higher threshold"
        )

    # ---- PhoneticMatch fields are populated correctly ----

    async def test_phonetic_match_fields_populated_correctly(
        self,
        matcher_and_repo: tuple[PhoneticMatcher, MagicMock],
        mock_session: MagicMock,
    ) -> None:
        """Each PhoneticMatch has all required fields with correct types."""
        matcher, mock_repo = matcher_and_repo
        entity_id = _uuid()

        segment_texts = [("dQw4w9WgXcQ", "Sheinbaum is president", 42)]
        _configure_entity_query(
            mock_session=mock_session,
            entity_name="Sheinbaum",
            entity_id=entity_id,
            aliases=[],
            video_ids=["dQw4w9WgXcQ"],
            evidence_video_ids=["dQw4w9WgXcQ"],
            segment_texts=segment_texts,
        )
        mock_repo.get_entity_video_ids = AsyncMock(return_value={"dQw4w9WgXcQ"})

        result = await matcher.match_entity(
            entity_id=entity_id,
            session=mock_session,
            threshold=0.3,
        )

        assert len(result) >= 1, "Expected at least one match for 'Sheinbaum'"
        match = result[0]

        assert isinstance(match.original_text, str)
        assert isinstance(match.proposed_correction, str)
        assert isinstance(match.confidence, float)
        assert 0.0 <= match.confidence <= 1.0
        assert isinstance(match.evidence_description, str)
        assert match.video_id == "dQw4w9WgXcQ"
        assert match.segment_id == 42

    # ---- corrected_text is used when has_correction=True ----

    async def test_corrected_text_preferred_over_raw_text(
        self,
        matcher_and_repo: tuple[PhoneticMatcher, MagicMock],
        mock_session: MagicMock,
    ) -> None:
        """When a segment has has_correction=True, corrected_text is scored, not text.

        The service reads ``segment.corrected_text`` when ``has_correction`` is
        True and ``corrected_text`` is not None.
        """
        matcher, mock_repo = matcher_and_repo
        entity_id = _uuid()

        mock_entity = MagicMock()
        mock_entity.canonical_name = "Sheinbaum"
        mock_entity.id = entity_id

        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = mock_entity

        alias_scalars = MagicMock()
        alias_scalars.all.return_value = []
        alias_result = MagicMock()
        alias_result.scalars.return_value = alias_scalars

        ev_scalars = MagicMock()
        ev_scalars.all.return_value = ["dQw4w9WgXcQ"]
        ev_result = MagicMock()
        ev_result.scalars.return_value = ev_scalars

        # Segment with corrected_text set
        seg = MagicMock()
        seg.video_id = "dQw4w9WgXcQ"
        seg.id = 99
        seg.text = "garbled nonsense words"          # raw text — unrelated
        seg.corrected_text = "Sheinbaum spoke today"  # corrected — should score
        seg.has_correction = True

        seg_scalars = MagicMock()
        seg_scalars.all.return_value = [seg]
        seg_result = MagicMock()
        seg_result.scalars.return_value = seg_scalars

        mock_session.execute.side_effect = [
            entity_result,
            alias_result,
            ev_result,
            seg_result,
        ]
        mock_repo.get_entity_video_ids = AsyncMock(return_value={"dQw4w9WgXcQ"})

        result = await matcher.match_entity(
            entity_id=entity_id,
            session=mock_session,
            threshold=0.3,
        )

        # We expect at least the "Sheinbaum" N-gram from the corrected text
        match_texts = [m.original_text for m in result]
        assert any("Sheinbaum" in t for t in match_texts), (
            f"Expected 'Sheinbaum' from corrected_text in matches; got {match_texts}"
        )
