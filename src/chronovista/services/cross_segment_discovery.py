"""
Cross-segment candidate discovery service.

Identifies transcript segments where ASR errors span the boundary between
consecutive segments. Uses recurring correction patterns to find adjacent
segment pairs where a known error form is split across segment N (suffix)
and segment N+1 (prefix), then scores candidates using phonetic similarity
and pattern confidence.

Feature 045 — Correction Intelligence Pipeline (US5, T033)
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.models.batch_correction_models import CorrectionPattern
from chronovista.services.batch_correction_service import BatchCorrectionService
from chronovista.services.phonetic_matcher import PhoneticMatcher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class CrossSegmentCandidate(BaseModel):
    """A candidate cross-segment ASR error discovered from correction patterns.

    Attributes
    ----------
    segment_n_id : int
        Primary key of the first segment (ending with the error prefix).
    segment_n_text : str
        Effective text of the first segment.
    segment_n1_id : int
        Primary key of the second segment (starting with the error suffix).
    segment_n1_text : str
        Effective text of the second segment.
    proposed_correction : str
        The corrected form derived from the source pattern.
    source_pattern : str
        The original ASR error text from the correction pattern.
    confidence : float
        Confidence score in [0.0, 1.0].
    is_partially_corrected : bool
        True if one of the two segments has already been corrected.
    video_id : str
        YouTube video ID where the candidate was found.
    """

    segment_n_id: int = Field(..., description="PK of the first segment")
    segment_n_text: str = Field(..., description="Effective text of the first segment")
    segment_n1_id: int = Field(..., description="PK of the second segment")
    segment_n1_text: str = Field(..., description="Effective text of the second segment")
    proposed_correction: str = Field(
        ..., description="Corrected form from the source pattern"
    )
    source_pattern: str = Field(
        ..., description="Original ASR error text from correction pattern"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    is_partially_corrected: bool = Field(
        default=False,
        description="True if one of the two segments already has a correction",
    )
    video_id: str = Field(..., description="YouTube video ID")

    model_config = ConfigDict(frozen=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WORD_BOUNDARY_RE = re.compile(r"\s+")


def _effective_text(segment: Any) -> str:
    """Return the effective text for a segment (corrected if available)."""
    if segment.has_correction and segment.corrected_text:
        return str(segment.corrected_text)
    return str(segment.text)


def _generate_splits(text: str) -> list[tuple[str, str, bool]]:
    """Generate all possible split points for *text*.

    Returns a list of ``(prefix, suffix, is_word_boundary)`` tuples.
    Word-boundary splits occur at whitespace positions; character-level
    splits occur at every other position.

    Parameters
    ----------
    text : str
        The text to split.

    Returns
    -------
    list[tuple[str, str, bool]]
        Each tuple contains (prefix, suffix, is_word_boundary).
    """
    splits: list[tuple[str, str, bool]] = []

    # Word-boundary splits (higher confidence)
    words = _WORD_BOUNDARY_RE.split(text)
    if len(words) >= 2:
        for i in range(1, len(words)):
            prefix = " ".join(words[:i])
            suffix = " ".join(words[i:])
            splits.append((prefix, suffix, True))

    # Character-level splits (lower confidence, only for short patterns)
    if len(text) <= 20:
        for i in range(1, len(text)):
            prefix = text[:i]
            suffix = text[i:]
            # Skip if this is already captured as a word-boundary split
            if text[i - 1] == " " or (i < len(text) and text[i] == " "):
                continue
            splits.append((prefix, suffix, False))

    return splits


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class CrossSegmentDiscovery:
    """Service for discovering cross-segment ASR error candidates.

    Uses recurring correction patterns from ``BatchCorrectionService`` to
    identify adjacent segment pairs where a known error form is split across
    the segment boundary.

    Parameters
    ----------
    batch_service : BatchCorrectionService
        Service providing recurring correction patterns.
    """

    def __init__(self, batch_service: BatchCorrectionService) -> None:
        self._batch_service = batch_service

    async def discover(
        self,
        session: AsyncSession,
        min_corrections: int = 3,
        entity_name: str | None = None,
    ) -> list[CrossSegmentCandidate]:
        """Discover cross-segment ASR error candidates.

        Analyses recurring correction patterns, generates split-point
        hypotheses for each error form, then searches for adjacent segment
        pairs matching prefix/suffix combinations.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        min_corrections : int, optional
            Minimum correction occurrences for a pattern to be considered
            (default 3).
        entity_name : str | None, optional
            If provided, only consider patterns whose original or corrected
            text contains this entity name (case-insensitive substring match).

        Returns
        -------
        list[CrossSegmentCandidate]
            Candidates sorted by confidence descending.
        """
        # 1. Get recurring patterns
        patterns = await self._batch_service.get_patterns(
            session,
            min_occurrences=min_corrections,
            limit=200,
            show_completed=True,
        )

        if not patterns:
            logger.info("No recurring patterns found (min_corrections=%d)", min_corrections)
            return []

        # 2. Optionally filter by entity name
        if entity_name is not None:
            entity_lower = entity_name.lower()
            patterns = [
                p
                for p in patterns
                if entity_lower in p.original_text.lower()
                or entity_lower in p.corrected_text.lower()
            ]
            if not patterns:
                logger.info(
                    "No patterns match entity filter '%s'", entity_name
                )
                return []

        logger.info(
            "Processing %d patterns for cross-segment discovery", len(patterns)
        )

        # 3. Collect corrected segment IDs to filter out fully corrected pairs
        corrected_segment_ids = await self._get_corrected_segment_ids(session)

        candidates: list[CrossSegmentCandidate] = []

        for pattern in patterns:
            pattern_candidates = await self._process_pattern(
                session, pattern, corrected_segment_ids
            )
            candidates.extend(pattern_candidates)

        # Sort by confidence descending
        candidates.sort(key=lambda c: c.confidence, reverse=True)

        logger.info(
            "Cross-segment discovery complete: %d candidates found",
            len(candidates),
        )
        return candidates

    async def _process_pattern(
        self,
        session: AsyncSession,
        pattern: CorrectionPattern,
        corrected_segment_ids: set[int],
    ) -> list[CrossSegmentCandidate]:
        """Process a single correction pattern for cross-segment splits.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        pattern : CorrectionPattern
            The correction pattern to process.
        corrected_segment_ids : set[int]
            Set of segment IDs that already have corrections applied.

        Returns
        -------
        list[CrossSegmentCandidate]
            Candidates found for this pattern.
        """
        original = pattern.original_text
        splits = _generate_splits(original)

        if not splits:
            return []

        candidates: list[CrossSegmentCandidate] = []

        for prefix, suffix, is_word_boundary in splits:
            if not prefix.strip() or not suffix.strip():
                continue

            # Search for segment pairs where segment N ends with prefix
            # and segment N+1 starts with suffix
            pairs = await self._find_adjacent_pairs(
                session, prefix, suffix
            )

            for seg_n, seg_n1 in pairs:
                # Determine correction status
                n_corrected = seg_n.id in corrected_segment_ids
                n1_corrected = seg_n1.id in corrected_segment_ids
                both_corrected = n_corrected and n1_corrected

                # Skip fully corrected pairs
                if both_corrected:
                    continue

                is_partial = n_corrected or n1_corrected

                # Score the candidate
                confidence = self._score_candidate(
                    prefix=prefix,
                    suffix=suffix,
                    seg_n_text=_effective_text(seg_n),
                    seg_n1_text=_effective_text(seg_n1),
                    is_word_boundary=is_word_boundary,
                    pattern_occurrences=pattern.occurrences,
                    is_partially_corrected=is_partial,
                )

                candidates.append(
                    CrossSegmentCandidate(
                        segment_n_id=seg_n.id,
                        segment_n_text=_effective_text(seg_n),
                        segment_n1_id=seg_n1.id,
                        segment_n1_text=_effective_text(seg_n1),
                        proposed_correction=pattern.corrected_text,
                        source_pattern=original,
                        confidence=round(confidence, 4),
                        is_partially_corrected=is_partial,
                        video_id=seg_n.video_id,
                    )
                )

        return candidates

    async def _find_adjacent_pairs(
        self,
        session: AsyncSession,
        prefix: str,
        suffix: str,
    ) -> list[tuple[Any, Any]]:
        """Find adjacent segment pairs where N ends with prefix and N+1 starts with suffix.

        Adjacency is defined as consecutive ``sequence_number`` values
        (N, N+1) within the same ``video_id`` and ``language_code``.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        prefix : str
            The text that segment N should end with.
        suffix : str
            The text that segment N+1 should start with.

        Returns
        -------
        list[tuple[Any, Any]]
            List of (segment_n, segment_n1) pairs.
        """
        # Alias tables for self-join
        seg_n = TranscriptSegmentDB.__table__.alias("seg_n")
        seg_n1 = TranscriptSegmentDB.__table__.alias("seg_n1")

        # Build effective text expressions for both segments
        from sqlalchemy import case, literal

        eff_text_n = case(
            (seg_n.c.has_correction, seg_n.c.corrected_text),
            else_=seg_n.c.text,
        )
        eff_text_n1 = case(
            (seg_n1.c.has_correction, seg_n1.c.corrected_text),
            else_=seg_n1.c.text,
        )

        # Use LIKE patterns for suffix/prefix matching
        prefix_like = f"%{prefix}"
        suffix_like = f"{suffix}%"

        stmt = (
            select(seg_n, seg_n1)
            .where(
                and_(
                    # Same video and language
                    seg_n.c.video_id == seg_n1.c.video_id,
                    seg_n.c.language_code == seg_n1.c.language_code,
                    # Adjacent segments
                    seg_n1.c.sequence_number == seg_n.c.sequence_number + 1,
                    # Segment N ends with prefix
                    eff_text_n.ilike(prefix_like),
                    # Segment N+1 starts with suffix
                    eff_text_n1.ilike(suffix_like),
                )
            )
            .limit(100)
        )

        result = await session.execute(stmt)
        rows = result.fetchall()

        # Convert raw rows to segment-like objects
        pairs: list[tuple[Any, Any]] = []
        n_cols = len(seg_n.c)
        for row in rows:
            # Row is a flat tuple: [seg_n columns...][seg_n1 columns...]
            # First column of each alias is the primary key (id)
            seg_n_obj = await session.get(TranscriptSegmentDB, row[0])
            seg_n1_obj = await session.get(TranscriptSegmentDB, row[n_cols])

            if seg_n_obj is not None and seg_n1_obj is not None:
                pairs.append((seg_n_obj, seg_n1_obj))

        return pairs

    def _score_candidate(
        self,
        *,
        prefix: str,
        suffix: str,
        seg_n_text: str,
        seg_n1_text: str,
        is_word_boundary: bool,
        pattern_occurrences: int,
        is_partially_corrected: bool,
    ) -> float:
        """Score a cross-segment candidate on a 0.0-1.0 scale.

        Scoring factors:
        - Split type: word-boundary splits score higher (0.4) than
          character-level splits (0.15)
        - Pattern frequency: more occurrences increase confidence
          (0.0-0.3 scaled)
        - Boundary precision: exact end/start match scores higher (0.0-0.2)
        - Partial correction flag: partially corrected pairs get a small
          boost (0.1) as evidence of a real error

        Parameters
        ----------
        prefix : str
            The prefix portion of the split.
        suffix : str
            The suffix portion of the split.
        seg_n_text : str
            Effective text of segment N.
        seg_n1_text : str
            Effective text of segment N+1.
        is_word_boundary : bool
            Whether the split occurs at a word boundary.
        pattern_occurrences : int
            Number of times the correction pattern has been observed.
        is_partially_corrected : bool
            Whether one segment already has a correction.

        Returns
        -------
        float
            Confidence score in [0.0, 1.0].
        """
        score = 0.0

        # Factor 1: Split type (word-boundary vs character-level)
        if is_word_boundary:
            score += 0.4
        else:
            score += 0.15

        # Factor 2: Pattern frequency (scaled 0.0-0.3)
        freq_score = min(pattern_occurrences / 20.0, 1.0) * 0.3
        score += freq_score

        # Factor 3: Boundary precision
        # Check if prefix is exactly at the end of segment N
        ends_exact = seg_n_text.rstrip().endswith(prefix.rstrip())
        starts_exact = seg_n1_text.lstrip().startswith(suffix.lstrip())
        if ends_exact and starts_exact:
            score += 0.2
        elif ends_exact or starts_exact:
            score += 0.1

        # Factor 4: Partial correction evidence
        if is_partially_corrected:
            score += 0.1

        return min(score, 1.0)

    async def _get_corrected_segment_ids(
        self, session: AsyncSession
    ) -> set[int]:
        """Get IDs of segments that have existing corrections.

        Parameters
        ----------
        session : AsyncSession
            Database session.

        Returns
        -------
        set[int]
            Set of segment IDs with at least one correction record.
        """
        stmt = (
            select(TranscriptCorrectionDB.segment_id)
            .where(TranscriptCorrectionDB.segment_id.is_not(None))
            .distinct()
        )
        result = await session.execute(stmt)
        return {row for row in result.scalars().all() if row is not None}
