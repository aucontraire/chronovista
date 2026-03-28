"""
Cross-segment candidate discovery service.

Identifies transcript segments where ASR errors span the boundary between
consecutive segments. Two discovery strategies are combined:

1. **Correction-pattern based** (original): Uses recurring correction patterns
   from ``BatchCorrectionService`` to find adjacent segment pairs where a
   known error form is split across the segment boundary.

2. **Entity-alias based** (new): Uses multi-word ASR error aliases from
   ``entity_aliases`` to find segment boundary splits. This leverages
   curated entity knowledge and does not require prior corrections.

Feature 045 — Correction Intelligence Pipeline (US5, T033)
"""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.models.batch_correction_models import CorrectionPattern
from chronovista.services.batch_correction_service import BatchCorrectionService
from chronovista.utils.text import strip_boundary_punctuation

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
    discovery_source: str = Field(
        default="correction_pattern",
        description="How this candidate was discovered: 'entity_alias' or 'correction_pattern'",
    )

    model_config = ConfigDict(frozen=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WORD_BOUNDARY_RE = re.compile(r"\s+")

# Common English function words.  When BOTH halves of a 2-word alias
# split consist entirely of stopwords the split is too noisy for
# cross-segment discovery (e.g. "be out" from "Rick Beato").
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "not", "no", "so",
    "is", "am", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did",
    "will", "would", "shall", "should", "may", "might", "can", "could",
    "i", "me", "my", "we", "us", "our", "you", "your",
    "he", "him", "his", "she", "her", "it", "its", "they", "them", "their",
    "this", "that", "these", "those",
    "in", "on", "at", "to", "of", "for", "by", "with", "from",
    "up", "out", "off", "over", "into", "onto", "upon",
    "if", "then", "than", "as", "while", "when", "where", "how", "what",
    "who", "whom", "which", "why",
    "all", "each", "every", "both", "few", "more", "most", "some", "any",
    "much", "many", "such", "own", "other",
    "just", "also", "very", "too", "quite", "about", "still",
    "here", "there", "now", "well", "back",
    "get", "got", "go", "going", "gone", "come", "came",
    "make", "made", "take", "took", "put", "let", "say", "said",
    "know", "think", "see", "look", "want", "give", "use",
})


def _is_stopword_split(prefix: str, suffix: str) -> bool:
    """Return True if both sides of the split are common stopwords.

    A split is considered "stopword-only" when every word in both the
    prefix and suffix appears in ``_STOPWORDS``.  Such splits produce
    overwhelming false-positive matches in cross-segment discovery.
    """
    prefix_words = prefix.lower().split()
    suffix_words = suffix.lower().split()
    return (
        bool(prefix_words)
        and bool(suffix_words)
        and all(w in _STOPWORDS for w in prefix_words)
        and all(w in _STOPWORDS for w in suffix_words)
    )


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


def _generate_word_splits(text: str) -> list[tuple[str, str]]:
    """Generate word-boundary split points for a multi-word text.

    For text with N words, returns N-1 splits. Only word-boundary splits
    are generated (no character-level splits) since entity aliases are
    clean multi-word strings.

    Parameters
    ----------
    text : str
        The text to split (e.g. an entity alias name).

    Returns
    -------
    list[tuple[str, str]]
        Each tuple contains (prefix, suffix).
    """
    words = _WORD_BOUNDARY_RE.split(text)
    if len(words) < 2:
        return []
    splits: list[tuple[str, str]] = []
    for i in range(1, len(words)):
        prefix = " ".join(words[:i])
        suffix = " ".join(words[i:])
        if prefix.strip() and suffix.strip():
            splits.append((prefix, suffix))
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

        Combines two discovery strategies:
        1. Entity-alias based — uses curated ASR error aliases from
           ``entity_aliases`` (no prior corrections required).
        2. Correction-pattern based — uses recurring correction patterns
           from ``BatchCorrectionService``.

        Entity-based candidates are prioritised when both strategies find
        the same segment pair.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        min_corrections : int, optional
            Minimum correction occurrences for pattern-based discovery
            (default 3).
        entity_name : str | None, optional
            If provided, only consider patterns/aliases matching this
            entity name (case-insensitive substring match).

        Returns
        -------
        list[CrossSegmentCandidate]
            Candidates sorted by confidence descending.
        """
        # 1. Entity-based discovery
        entity_candidates = await self.discover_from_entities(
            session, entity_name=entity_name
        )

        # 2. Pattern-based discovery
        pattern_candidates = await self._discover_from_patterns(
            session,
            min_corrections=min_corrections,
            entity_name=entity_name,
        )

        # 3. Merge and deduplicate (entity candidates take priority)
        merged = self._merge_candidates(entity_candidates, pattern_candidates)

        # 4. Sort by confidence descending
        merged.sort(key=lambda c: c.confidence, reverse=True)

        logger.info(
            "Cross-segment discovery complete: %d candidates "
            "(%d entity-based, %d pattern-based)",
            len(merged),
            len(entity_candidates),
            len(pattern_candidates),
        )
        return merged

    # ------------------------------------------------------------------
    # Entity-alias based discovery
    # ------------------------------------------------------------------

    async def discover_from_entities(
        self,
        session: AsyncSession,
        entity_name: str | None = None,
    ) -> list[CrossSegmentCandidate]:
        """Discover cross-segment candidates using entity ASR aliases.

        Loads multi-word ASR error aliases, generates word-boundary splits,
        and searches for adjacent segment pairs matching any split in a
        single batched SQL query (avoiding per-split round-trips).

        Parameters
        ----------
        session : AsyncSession
            Database session.
        entity_name : str | None
            Optional filter by entity canonical name.

        Returns
        -------
        list[CrossSegmentCandidate]
            Candidates with ``discovery_source='entity_alias'``.
        """
        aliases = await self._load_multiword_asr_aliases(session, entity_name)
        if not aliases:
            logger.debug("No multi-word ASR aliases found for entity discovery")
            return []

        # Prioritize aliases: 2-word aliases first (more precise), then
        # shorter names.  Limit to 30 to keep query cost reasonable on
        # large segment tables (~1M rows → sequential ILIKE scan).
        aliases.sort(
            key=lambda a: (len(a[0].split()), len(a[0]))
        )
        max_aliases = 30
        if len(aliases) > max_aliases:
            logger.info(
                "Limiting entity aliases from %d to %d for performance",
                len(aliases),
                max_aliases,
            )
            aliases = aliases[:max_aliases]

        # Collect all (prefix, suffix) splits with their alias metadata,
        # filtering out splits where both halves are common stopwords.
        split_entries: list[tuple[str, str, str, str, str]] = []
        skipped_stopword = 0
        for alias_name, canonical_name, entity_type in aliases:
            for prefix, suffix in _generate_word_splits(alias_name):
                if _is_stopword_split(prefix, suffix):
                    skipped_stopword += 1
                    continue
                split_entries.append(
                    (prefix, suffix, alias_name, canonical_name, entity_type)
                )
        if skipped_stopword:
            logger.info(
                "Skipped %d stopword-only splits from entity aliases",
                skipped_stopword,
            )

        if not split_entries:
            logger.debug("No word-boundary splits generated from aliases")
            return []

        corrected_segment_ids = await self._get_corrected_segment_ids(session)

        # Single batched query for ALL alias splits
        pairs = await self._find_adjacent_pairs_batched(
            session,
            [(p, s) for p, s, _, _, _ in split_entries],
        )

        candidates: list[CrossSegmentCandidate] = []
        for seg_n, seg_n1 in pairs:
            n_corrected = seg_n.id in corrected_segment_ids
            n1_corrected = seg_n1.id in corrected_segment_ids
            if n_corrected and n1_corrected:
                continue
            is_partial = n_corrected or n1_corrected

            seg_n_text = _effective_text(seg_n)
            seg_n1_text = _effective_text(seg_n1)

            # Match this pair to the best-scoring alias
            best_alias: tuple[str, str] | None = None
            best_score = -1.0
            for prefix, suffix, a_name, c_name, e_type in split_entries:
                if seg_n_text.lower().rstrip().endswith(
                    prefix.lower().rstrip()
                ) and seg_n1_text.lower().lstrip().startswith(
                    suffix.lower().lstrip()
                ):
                    score = self._score_entity_candidate(
                        prefix=prefix,
                        suffix=suffix,
                        seg_n_text=seg_n_text,
                        seg_n1_text=seg_n1_text,
                        is_partially_corrected=is_partial,
                        entity_type=e_type,
                        alias_word_count=len(
                            _WORD_BOUNDARY_RE.split(a_name)
                        ),
                    )
                    if score > best_score:
                        best_score = score
                        best_alias = (a_name, c_name)

            if best_alias:
                alias_name, canonical_name = best_alias
                candidates.append(
                    CrossSegmentCandidate(
                        segment_n_id=seg_n.id,
                        segment_n_text=seg_n_text,
                        segment_n1_id=seg_n1.id,
                        segment_n1_text=seg_n1_text,
                        proposed_correction=canonical_name,
                        source_pattern=alias_name,
                        confidence=round(best_score, 4),
                        is_partially_corrected=is_partial,
                        video_id=seg_n.video_id,
                        discovery_source="entity_alias",
                    )
                )

        logger.info(
            "Entity-alias discovery: %d candidates from %d aliases "
            "(%d splits, %d pairs found)",
            len(candidates),
            len(aliases),
            len(split_entries),
            len(pairs),
        )
        return candidates

    async def _load_multiword_asr_aliases(
        self,
        session: AsyncSession,
        entity_name: str | None = None,
    ) -> list[tuple[str, str, str]]:
        """Load multi-word ASR error aliases with their entity canonical names.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        entity_name : str | None
            Optional case-insensitive filter on canonical_name.

        Returns
        -------
        list[tuple[str, str, str]]
            Each tuple is (alias_name, canonical_name, entity_type).
        """
        stmt = (
            select(
                EntityAliasDB.alias_name,
                NamedEntityDB.canonical_name,
                NamedEntityDB.entity_type,
            )
            .join(NamedEntityDB, EntityAliasDB.entity_id == NamedEntityDB.id)
            .where(
                EntityAliasDB.alias_type == "asr_error",
                EntityAliasDB.alias_name.contains(" "),
            )
        )
        if entity_name is not None:
            stmt = stmt.where(
                func.lower(NamedEntityDB.canonical_name).contains(
                    entity_name.lower()
                )
            )

        result = await session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def _find_adjacent_pairs_batched(
        self,
        session: AsyncSession,
        prefix_suffix_pairs: list[tuple[str, str]],
        limit: int = 500,
    ) -> list[tuple[Any, Any]]:
        """Find adjacent segment pairs matching any of the given splits.

        Batches all ``(prefix, suffix)`` pairs into a single SQL query
        with OR conditions, avoiding one round-trip per split.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        prefix_suffix_pairs : list[tuple[str, str]]
            Each tuple is ``(prefix, suffix)`` where segment N should
            end with *prefix* and segment N+1 should start with *suffix*.
        limit : int
            Maximum number of rows to return (default 500).

        Returns
        -------
        list[tuple[Any, Any]]
            List of ``(seg_n, seg_n1)`` lightweight namespace objects
            with ``id``, ``text``, ``corrected_text``, ``has_correction``,
            and ``video_id`` attributes.
        """
        if not prefix_suffix_pairs:
            return []

        seg_n = TranscriptSegmentDB.__table__.alias("seg_n")
        seg_n1 = TranscriptSegmentDB.__table__.alias("seg_n1")

        eff_text_n = case(
            (seg_n.c.has_correction, seg_n.c.corrected_text),
            else_=seg_n.c.text,
        )
        eff_text_n1 = case(
            (seg_n1.c.has_correction, seg_n1.c.corrected_text),
            else_=seg_n1.c.text,
        )

        or_conditions = [
            and_(
                eff_text_n.ilike(f"%{prefix}"),
                eff_text_n1.ilike(f"{suffix}%"),
            )
            for prefix, suffix in prefix_suffix_pairs
        ]

        stmt = (
            select(
                seg_n.c.id.label("n_id"),
                seg_n.c.text.label("n_text"),
                seg_n.c.corrected_text.label("n_corrected_text"),
                seg_n.c.has_correction.label("n_has_correction"),
                seg_n.c.video_id.label("n_video_id"),
                seg_n1.c.id.label("n1_id"),
                seg_n1.c.text.label("n1_text"),
                seg_n1.c.corrected_text.label("n1_corrected_text"),
                seg_n1.c.has_correction.label("n1_has_correction"),
            )
            .where(
                and_(
                    seg_n.c.video_id == seg_n1.c.video_id,
                    seg_n.c.language_code == seg_n1.c.language_code,
                    seg_n1.c.sequence_number == seg_n.c.sequence_number + 1,
                    or_(*or_conditions),
                )
            )
            .limit(limit)
        )

        result = await session.execute(stmt)
        rows = result.fetchall()

        seen: set[tuple[int, int]] = set()
        pairs: list[tuple[Any, Any]] = []
        for row in rows:
            key = (row.n_id, row.n1_id)
            if key in seen:
                continue
            seen.add(key)

            seg_n_obj = SimpleNamespace(
                id=row.n_id,
                text=row.n_text,
                corrected_text=row.n_corrected_text,
                has_correction=row.n_has_correction,
                video_id=row.n_video_id,
            )
            seg_n1_obj = SimpleNamespace(
                id=row.n1_id,
                text=row.n1_text,
                corrected_text=row.n1_corrected_text,
                has_correction=row.n1_has_correction,
            )
            pairs.append((seg_n_obj, seg_n1_obj))

        logger.debug(
            "Batched adjacent-pair query: %d OR conditions → %d unique pairs",
            len(prefix_suffix_pairs),
            len(pairs),
        )
        return pairs

    def _score_entity_candidate(
        self,
        *,
        prefix: str,
        suffix: str,
        seg_n_text: str,
        seg_n1_text: str,
        is_partially_corrected: bool,
        entity_type: str,
        alias_word_count: int,
    ) -> float:
        """Score an entity-based cross-segment candidate.

        Entity candidates use a higher base score than pattern-based
        candidates because they are derived from curated ASR aliases
        with known canonical corrections.

        Scoring factors (0.0-1.0):
        - Entity source base: 0.50
        - Boundary precision: 0.0-0.20
        - Partial correction evidence: 0.10
        - Person entity type boost: 0.10
        - 2-word alias boost: 0.10

        Parameters
        ----------
        prefix : str
            The prefix portion of the alias split.
        suffix : str
            The suffix portion of the alias split.
        seg_n_text : str
            Effective text of segment N.
        seg_n1_text : str
            Effective text of segment N+1.
        is_partially_corrected : bool
            Whether one segment already has a correction.
        entity_type : str
            The entity type (e.g. 'person', 'organization').
        alias_word_count : int
            Number of words in the alias.

        Returns
        -------
        float
            Confidence score in [0.0, 1.0].
        """
        score = 0.50  # Entity source base

        # Boundary precision
        ends_exact = seg_n_text.rstrip().endswith(prefix.rstrip())
        starts_exact = seg_n1_text.lstrip().startswith(suffix.lstrip())
        if ends_exact and starts_exact:
            score += 0.20
        elif ends_exact or starts_exact:
            score += 0.10

        # Partial correction evidence
        if is_partially_corrected:
            score += 0.10

        # Person entity type boost (ASR most commonly mangles names)
        if entity_type == "person":
            score += 0.10

        # 2-word aliases are more precise than 3+ word aliases
        if alias_word_count == 2:
            score += 0.10

        return min(score, 1.0)

    @staticmethod
    def _merge_candidates(
        entity_candidates: list[CrossSegmentCandidate],
        pattern_candidates: list[CrossSegmentCandidate],
    ) -> list[CrossSegmentCandidate]:
        """Merge entity-based and pattern-based candidates, deduplicating by segment pair.

        Entity-based candidates take priority when both approaches find
        the same ``(segment_n_id, segment_n1_id)`` pair.

        Parameters
        ----------
        entity_candidates : list[CrossSegmentCandidate]
            Candidates from entity-alias discovery.
        pattern_candidates : list[CrossSegmentCandidate]
            Candidates from correction-pattern discovery.

        Returns
        -------
        list[CrossSegmentCandidate]
            Merged, deduplicated candidates.
        """
        seen: set[tuple[int, int]] = set()
        merged: list[CrossSegmentCandidate] = []

        for c in entity_candidates:
            key = (c.segment_n_id, c.segment_n1_id)
            if key not in seen:
                seen.add(key)
                merged.append(c)

        for c in pattern_candidates:
            key = (c.segment_n_id, c.segment_n1_id)
            if key not in seen:
                seen.add(key)
                merged.append(c)

        return merged

    # ------------------------------------------------------------------
    # Correction-pattern based discovery (original approach)
    # ------------------------------------------------------------------

    async def _discover_from_patterns(
        self,
        session: AsyncSession,
        min_corrections: int = 3,
        entity_name: str | None = None,
    ) -> list[CrossSegmentCandidate]:
        """Discover cross-segment candidates from recurring correction patterns.

        Collects word-boundary splits across all qualifying patterns and
        runs a single batched SQL query (same optimisation as entity
        discovery).  Character-level splits are skipped — they generate
        hundreds of noisy, low-confidence queries.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        min_corrections : int
            Minimum correction occurrences for a pattern to be considered.
        entity_name : str | None
            Optional entity name filter.

        Returns
        -------
        list[CrossSegmentCandidate]
            Candidates with ``discovery_source='correction_pattern'``.
        """
        patterns = await self._batch_service.get_patterns(
            session,
            min_occurrences=min_corrections,
            limit=200,
            show_completed=True,
        )

        if not patterns:
            logger.info(
                "No recurring patterns found (min_corrections=%d)",
                min_corrections,
            )
            return []

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

        # Collect word-boundary splits across all patterns
        # (prefix, suffix, pattern) — skip character-level splits
        split_entries: list[tuple[str, str, CorrectionPattern]] = []
        for pattern in patterns:
            for prefix, suffix, is_word_boundary in _generate_splits(
                pattern.original_text
            ):
                if not is_word_boundary:
                    continue
                if not prefix.strip() or not suffix.strip():
                    continue
                if _is_stopword_split(prefix, suffix):
                    continue
                split_entries.append((prefix, suffix, pattern))

        if not split_entries:
            logger.info(
                "No word-boundary splits from %d patterns", len(patterns)
            )
            return []

        logger.info(
            "Pattern discovery: %d word-boundary splits from %d patterns",
            len(split_entries),
            len(patterns),
        )

        corrected_segment_ids = await self._get_corrected_segment_ids(session)

        # Single batched query for ALL pattern splits
        pairs = await self._find_adjacent_pairs_batched(
            session,
            [(p, s) for p, s, _ in split_entries],
        )

        candidates: list[CrossSegmentCandidate] = []
        for seg_n, seg_n1 in pairs:
            n_corrected = seg_n.id in corrected_segment_ids
            n1_corrected = seg_n1.id in corrected_segment_ids
            if n_corrected and n1_corrected:
                continue
            is_partial = n_corrected or n1_corrected

            seg_n_text = _effective_text(seg_n)
            seg_n1_text = _effective_text(seg_n1)

            # Find best-scoring pattern match for this pair
            best_pattern: CorrectionPattern | None = None
            best_score = -1.0
            for prefix, suffix, pat in split_entries:
                if seg_n_text.lower().rstrip().endswith(
                    prefix.lower().rstrip()
                ) and seg_n1_text.lower().lstrip().startswith(
                    suffix.lower().lstrip()
                ):
                    score = self._score_candidate(
                        prefix=prefix,
                        suffix=suffix,
                        seg_n_text=seg_n_text,
                        seg_n1_text=seg_n1_text,
                        is_word_boundary=True,
                        pattern_occurrences=pat.occurrences,
                        is_partially_corrected=is_partial,
                    )
                    if score > best_score:
                        best_score = score
                        best_pattern = pat

            if best_pattern:
                candidates.append(
                    CrossSegmentCandidate(
                        segment_n_id=seg_n.id,
                        segment_n_text=seg_n_text,
                        segment_n1_id=seg_n1.id,
                        segment_n1_text=seg_n1_text,
                        proposed_correction=strip_boundary_punctuation(
                            best_pattern.corrected_text
                        ),
                        source_pattern=strip_boundary_punctuation(
                            best_pattern.original_text
                        ),
                        confidence=round(best_score, 4),
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
