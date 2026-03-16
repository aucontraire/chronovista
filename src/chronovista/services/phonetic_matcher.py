"""
Phonetic matcher service for ASR error boundary detection.

Uses Double Metaphone phonetic encoding and Levenshtein distance to identify
transcript segments where ASR has likely mis-transcribed entity names. Scores
candidate N-grams against entity names and aliases with a weighted formula
combining phonetic similarity, string similarity, and corroborating evidence.

Feature 045 — Correction Intelligence Pipeline (US4)
"""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from metaphone import doublemetaphone  # type: ignore[import-untyped]
import Levenshtein

from chronovista.db.models import (
    EntityAlias as EntityAliasDB,
    EntityMention as EntityMentionDB,
    NamedEntity as NamedEntityDB,
    TranscriptSegment as TranscriptSegmentDB,
)
from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class PhoneticMatch(BaseModel):
    """A candidate ASR error boundary match for an entity.

    Attributes
    ----------
    original_text : str
        The N-gram text from the transcript segment.
    proposed_correction : str
        The entity name (or alias) that the N-gram likely represents.
    confidence : float
        Weighted confidence score in [0.0, 1.0].
    evidence_description : str
        Human-readable description of the evidence supporting this match.
    video_id : str
        YouTube video ID where the match was found.
    segment_id : int
        Transcript segment primary key.
    """

    original_text: str
    proposed_correction: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_description: str
    video_id: str
    segment_id: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NON_ALPHA_RE = re.compile(r"[^a-zA-Z]")


def _strip_non_alpha(text: str) -> str:
    """Remove all non-alphabetic characters from *text*."""
    return _NON_ALPHA_RE.sub("", text)


def _metaphone_similarity(code_a: tuple[str, str], code_b: tuple[str, str]) -> float:
    """Compute similarity between two Double Metaphone code pairs.

    Compares primary and alternate codes and returns the best match ratio.
    Empty codes are treated as non-matching.

    Parameters
    ----------
    code_a : tuple[str, str]
        Primary and alternate Metaphone codes for the first term.
    code_b : tuple[str, str]
        Primary and alternate Metaphone codes for the second term.

    Returns
    -------
    float
        Similarity score in [0.0, 1.0].
    """
    best = 0.0
    for ca in code_a:
        if not ca:
            continue
        for cb in code_b:
            if not cb:
                continue
            ratio = Levenshtein.ratio(ca, cb)
            if ratio > best:
                best = ratio
    return best


def _extract_ngrams(text: str, min_n: int = 1, max_n: int = 3) -> list[str]:
    """Extract word-level N-grams from *text*.

    Parameters
    ----------
    text : str
        Source text to extract N-grams from.
    min_n : int
        Minimum N-gram size in words (default 1).
    max_n : int
        Maximum N-gram size in words (default 3).

    Returns
    -------
    list[str]
        List of N-gram strings.
    """
    words = text.split()
    ngrams: list[str] = []
    for n in range(min_n, max_n + 1):
        for i in range(len(words) - n + 1):
            ngrams.append(" ".join(words[i : i + n]))
    return ngrams


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PhoneticMatcher:
    """Service for detecting ASR error boundaries using phonetic matching.

    Parameters
    ----------
    entity_mention_repo : EntityMentionRepository
        Repository for entity mention queries.
    """

    def __init__(
        self,
        entity_mention_repo: EntityMentionRepository,
    ) -> None:
        self._entity_mention_repo = entity_mention_repo

    # ---- public scoring method ----

    @staticmethod
    def score_match(
        ngram: str,
        entity_name: str,
        entity_aliases: list[str],
        has_corroborating_evidence: bool,
    ) -> float:
        """Score an N-gram against an entity name and its aliases.

        Weighted formula:
          0.4 * Double Metaphone similarity
        + 0.3 * Levenshtein similarity
        + 0.3 * corroborating evidence (binary: 0.3 if True, 0.0 if False)

        Compares against the canonical name **and** all aliases, returning
        the best combined score.

        Parameters
        ----------
        ngram : str
            Candidate N-gram text from a transcript segment.
        entity_name : str
            Canonical entity name.
        entity_aliases : list[str]
            List of alias names for the entity.
        has_corroborating_evidence : bool
            Whether the entity has a confirmed mention in the same video.

        Returns
        -------
        float
            Confidence score in [0.0, 1.0].
        """
        candidates = [entity_name] + entity_aliases

        ngram_stripped = _strip_non_alpha(ngram).lower()
        ngram_codes = doublemetaphone(ngram_stripped)

        best_score = 0.0
        for candidate in candidates:
            candidate_stripped = _strip_non_alpha(candidate).lower()
            if not candidate_stripped or not ngram_stripped:
                continue

            candidate_codes = doublemetaphone(candidate_stripped)

            phonetic_sim = _metaphone_similarity(ngram_codes, candidate_codes)
            levenshtein_sim = Levenshtein.ratio(
                ngram_stripped, candidate_stripped
            )

            score = (
                0.4 * phonetic_sim
                + 0.3 * levenshtein_sim
                + (0.3 if has_corroborating_evidence else 0.0)
            )
            if score > best_score:
                best_score = score

        return min(best_score, 1.0)

    # ---- main matching method ----

    async def match_entity(
        self,
        entity_id: uuid.UUID,
        session: AsyncSession,
        threshold: float = 0.5,
    ) -> list[PhoneticMatch]:
        """Find candidate ASR error boundaries for a single entity.

        Loads the entity's associated video IDs (via mention and tag paths),
        retrieves transcript segments from those videos, extracts 1-3 word
        N-grams, and scores each against the entity name and aliases.

        Parameters
        ----------
        entity_id : uuid.UUID
            The named entity UUID.
        session : AsyncSession
            The database session.
        threshold : float
            Minimum confidence score to include a match (default 0.5).

        Returns
        -------
        list[PhoneticMatch]
            All matches above the threshold, sorted by confidence descending.
        """
        # 1. Get entity details
        entity_result = await session.execute(
            select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
        )
        entity = entity_result.scalar_one_or_none()
        if entity is None:
            return []

        entity_name: str = entity.canonical_name

        # 2. Get entity aliases
        alias_result = await session.execute(
            select(EntityAliasDB.alias_name).where(
                EntityAliasDB.entity_id == entity_id
            )
        )
        entity_aliases: list[str] = list(alias_result.scalars().all())

        # 3. Get associated video IDs
        video_ids = await self._entity_mention_repo.get_entity_video_ids(
            session, entity_id
        )
        if not video_ids:
            return []

        # 4. Get videos that have confirmed entity mentions (for evidence)
        evidence_result = await session.execute(
            select(EntityMentionDB.video_id)
            .where(EntityMentionDB.entity_id == entity_id)
            .distinct()
        )
        videos_with_mentions: set[str] = set(evidence_result.scalars().all())

        # 5. Load segments from associated videos
        segment_result = await session.execute(
            select(TranscriptSegmentDB)
            .where(TranscriptSegmentDB.video_id.in_(video_ids))
            .order_by(
                TranscriptSegmentDB.video_id,
                TranscriptSegmentDB.sequence_number,
            )
        )
        segments = segment_result.scalars().all()

        # 6. Extract N-grams and score
        matches: list[PhoneticMatch] = []
        for segment in segments:
            effective_text: str = (
                segment.corrected_text
                if segment.has_correction and segment.corrected_text
                else segment.text
            )
            ngrams = _extract_ngrams(effective_text, min_n=1, max_n=3)

            has_evidence = segment.video_id in videos_with_mentions

            for ngram in ngrams:
                confidence = self.score_match(
                    ngram, entity_name, entity_aliases, has_evidence
                )
                if confidence >= threshold:
                    # Determine which candidate scored best for
                    # proposed_correction
                    best_candidate = entity_name
                    best_candidate_score = 0.0
                    for candidate in [entity_name] + entity_aliases:
                        cand_stripped = _strip_non_alpha(candidate).lower()
                        ngram_stripped = _strip_non_alpha(ngram).lower()
                        if not cand_stripped or not ngram_stripped:
                            continue
                        sim = Levenshtein.ratio(ngram_stripped, cand_stripped)
                        if sim > best_candidate_score:
                            best_candidate_score = sim
                            best_candidate = candidate

                    evidence_parts: list[str] = []
                    evidence_parts.append(
                        f"phonetic+levenshtein match (conf={confidence:.2f})"
                    )
                    if has_evidence:
                        evidence_parts.append(
                            "entity confirmed in same video"
                        )

                    matches.append(
                        PhoneticMatch(
                            original_text=ngram,
                            proposed_correction=best_candidate,
                            confidence=round(confidence, 4),
                            evidence_description="; ".join(evidence_parts),
                            video_id=segment.video_id,
                            segment_id=segment.id,
                        )
                    )

        # Sort by confidence descending
        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches
