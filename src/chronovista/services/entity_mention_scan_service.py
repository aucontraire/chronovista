"""
Entity mention scan service for detecting named entity occurrences in transcripts.

Scans transcript segments for mentions of named entities using PostgreSQL regex
matching with word-boundary support. Supports incremental and full-rescan modes,
batch processing, dry-run previews, and progress reporting.

Feature 038 -- Entity Mention Detection
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import Select, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.models.entity_mention import EntityMentionCreate
from chronovista.models.enums import DetectionMethod
from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
)

logger = logging.getLogger(__name__)

# Minimum alias length before a warning is emitted.
_MIN_ALIAS_LENGTH = 3


@dataclass
class ScanResult:
    """Aggregate statistics returned after a scan completes.

    Parameters
    ----------
    segments_scanned : int
        Total number of transcript segments examined.
    mentions_found : int
        Number of new entity mention rows inserted (or previewed).
    mentions_skipped : int
        Number of mention matches that were already present (incremental mode).
    unique_entities : int
        Count of distinct entities that produced at least one mention.
    unique_videos : int
        Count of distinct videos that contained at least one mention.
    duration_seconds : float
        Wall-clock time spent on the scan.
    dry_run : bool
        Whether this was a dry-run (no writes).
    failed_batches : int
        Number of segment batches that raised an exception.
    dry_run_matches : list[dict] | None
        Preview match data when ``dry_run=True``, else ``None``.
    skipped_longest_match : int
        Number of matches suppressed by longest-match-wins disambiguation.
    skipped_exclusion_pattern : int
        Number of matches suppressed by exclusion pattern overlap.
    """

    segments_scanned: int = 0
    mentions_found: int = 0
    mentions_skipped: int = 0
    unique_entities: int = 0
    unique_videos: int = 0
    duration_seconds: float = 0.0
    dry_run: bool = False
    failed_batches: int = 0
    dry_run_matches: list[dict[str, Any]] | None = None
    skipped_longest_match: int = 0
    skipped_exclusion_pattern: int = 0


@dataclass
class _EntityPattern:
    """Pre-compiled pattern data for a single named entity."""

    entity_id: uuid.UUID
    canonical_name: str
    entity_type: str
    pg_pattern: str  # PostgreSQL regex (unescaped \m / \M boundaries)
    alias_names: list[str]  # all raw names contributing to pattern
    exclusion_patterns: list[str] = field(default_factory=list)


class EntityMentionScanService:
    """Service for scanning transcript segments for named entity mentions.

    Uses PostgreSQL ``~*`` (case-insensitive regex) with ``\\m`` / ``\\M``
    word-boundary markers for accurate detection.  Supports incremental
    scanning (skip segments already matched for a given entity) and full
    rescan (delete + re-detect).

    Parameters
    ----------
    session_factory : async_sessionmaker[AsyncSession]
        Factory for creating database sessions.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._mention_repo = EntityMentionRepository()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scan(
        self,
        entity_type: str | None = None,
        video_ids: list[str] | None = None,
        language_code: str | None = None,
        batch_size: int = 500,
        dry_run: bool = False,
        full_rescan: bool = False,
        new_entities_only: bool = False,
        limit: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ScanResult:
        """Scan transcript segments for entity mentions.

        Parameters
        ----------
        entity_type : str | None
            Restrict scanning to entities of this type.
        video_ids : list[str] | None
            Restrict scanning to segments from these videos.
        language_code : str | None
            Restrict scanning to segments in this language.
        batch_size : int
            Number of segments fetched per batch (default 500).
        dry_run : bool
            If ``True``, collect preview data without writing.
        full_rescan : bool
            If ``True``, delete existing ``rule_match`` mentions in scope
            before scanning.
        new_entities_only : bool
            If ``True``, only scan entities that have zero existing mentions.
        limit : int | None
            Cap the number of dry-run preview rows collected.
        progress_callback : Callable[[int, int], None] | None
            Called after each batch with ``(segments_scanned, mentions_found)``.

        Returns
        -------
        ScanResult
            Aggregate statistics about the scan.
        """
        t0 = time.monotonic()

        async with self._session_factory() as session:
            # 1. Load entity patterns
            patterns = await self._load_entity_patterns(
                session,
                entity_type=entity_type,
                new_entities_only=new_entities_only,
            )

            if not patterns:
                logger.info("No active entities matched the filter criteria")
                return ScanResult(dry_run=dry_run, duration_seconds=time.monotonic() - t0)

            entity_ids = [p.entity_id for p in patterns]

            # 2. Handle --full rescan: delete existing mentions in scope
            if full_rescan and not dry_run:
                deleted = await self._mention_repo.delete_by_scope(
                    session,
                    entity_ids=entity_ids,
                    video_ids=video_ids,
                    language_code=language_code,
                    detection_method="rule_match",
                )
                logger.info(
                    "Full rescan: deleted %d existing rule_match mentions", deleted
                )
                await session.flush()

            # 3. Process segments in batches
            result = ScanResult(dry_run=dry_run)
            if dry_run:
                result.dry_run_matches = []

            matched_entity_ids: set[uuid.UUID] = set()
            matched_video_ids: set[str] = set()

            offset = 0
            while True:
                try:
                    batch_rows = await self._fetch_segment_batch(
                        session,
                        video_ids=video_ids,
                        language_code=language_code,
                        batch_size=batch_size,
                        offset=offset,
                    )
                except Exception:
                    logger.warning(
                        "Failed to fetch segment batch at offset=%d", offset, exc_info=True
                    )
                    result.failed_batches += 1
                    offset += batch_size
                    continue

                if not batch_rows:
                    break

                result.segments_scanned += len(batch_rows)

                try:
                    (
                        batch_mentions,
                        batch_skipped,
                        batch_previews,
                        batch_lmw_skips,
                        batch_ep_skips,
                    ) = await self._scan_batch(
                        session,
                        batch_rows=batch_rows,
                        patterns=patterns,
                        full_rescan=full_rescan,
                        dry_run=dry_run,
                        limit=limit,
                        current_preview_count=(
                            len(result.dry_run_matches) if result.dry_run_matches is not None else 0
                        ),
                    )
                except Exception:
                    logger.warning(
                        "Failed to process segment batch at offset=%d",
                        offset,
                        exc_info=True,
                    )
                    result.failed_batches += 1
                    offset += batch_size
                    if progress_callback:
                        progress_callback(result.segments_scanned, result.mentions_found)
                    continue

                # Accumulate results
                for m in batch_mentions:
                    matched_entity_ids.add(m.entity_id)
                    matched_video_ids.add(m.video_id)

                if not dry_run and batch_mentions:
                    inserted = await self._mention_repo.bulk_create_with_conflict_skip(
                        session, batch_mentions
                    )
                    result.mentions_found += inserted
                    result.mentions_skipped += len(batch_mentions) - inserted
                    await session.flush()
                elif dry_run:
                    result.mentions_found += len(batch_mentions)
                    if result.dry_run_matches is not None and batch_previews:
                        result.dry_run_matches.extend(batch_previews)

                result.mentions_skipped += batch_skipped
                result.skipped_longest_match += batch_lmw_skips
                result.skipped_exclusion_pattern += batch_ep_skips

                if progress_callback:
                    progress_callback(result.segments_scanned, result.mentions_found)

                offset += batch_size

                # If dry-run and we have reached the limit, stop early
                if (
                    dry_run
                    and limit is not None
                    and result.dry_run_matches is not None
                    and len(result.dry_run_matches) >= limit
                ):
                    # Trim to limit
                    result.dry_run_matches = result.dry_run_matches[:limit]
                    break

            result.unique_entities = len(matched_entity_ids)
            result.unique_videos = len(matched_video_ids)

            # 4. Update entity counters (live mode only)
            if not dry_run and matched_entity_ids:
                await self._mention_repo.update_entity_counters(
                    session, list(matched_entity_ids)
                )
                await session.flush()

            # 5. Commit all work
            if not dry_run:
                await session.commit()

            result.duration_seconds = time.monotonic() - t0

            logger.info(
                "Scan complete: segments_scanned=%d, mentions_found=%d, "
                "mentions_skipped=%d, unique_entities=%d, unique_videos=%d, "
                "duration=%.2fs, dry_run=%s, failed_batches=%d, "
                "skipped_longest_match=%d, skipped_exclusion_pattern=%d",
                result.segments_scanned,
                result.mentions_found,
                result.mentions_skipped,
                result.unique_entities,
                result.unique_videos,
                result.duration_seconds,
                result.dry_run,
                result.failed_batches,
                result.skipped_longest_match,
                result.skipped_exclusion_pattern,
            )

            return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _load_entity_patterns(
        self,
        session: AsyncSession,
        entity_type: str | None,
        new_entities_only: bool,
    ) -> list[_EntityPattern]:
        """Load active entities and their aliases, build regex patterns.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        entity_type : str | None
            Optional entity type filter.
        new_entities_only : bool
            If True, only include entities with zero existing mentions.

        Returns
        -------
        list[_EntityPattern]
            List of entity pattern objects ready for matching.
        """
        # Determine which entity IDs to scan
        if new_entities_only:
            zero_mention_ids = await self._mention_repo.get_entities_with_zero_mentions(
                session, entity_type=entity_type
            )
            if not zero_mention_ids:
                return []
            entity_stmt = select(NamedEntityDB).where(
                NamedEntityDB.id.in_(zero_mention_ids)
            )
        else:
            entity_stmt = select(NamedEntityDB).where(
                NamedEntityDB.status == "active"
            )
            if entity_type is not None:
                entity_stmt = entity_stmt.where(
                    NamedEntityDB.entity_type == entity_type
                )

        entity_result = await session.execute(entity_stmt)
        entities = list(entity_result.scalars().all())

        if not entities:
            return []

        # Load all aliases for these entities in a single query
        entity_id_list = [e.id for e in entities]
        alias_stmt = select(EntityAliasDB).where(
            EntityAliasDB.entity_id.in_(entity_id_list)
        )
        alias_result = await session.execute(alias_stmt)
        all_aliases = list(alias_result.scalars().all())

        # Group aliases by entity_id
        alias_map: dict[uuid.UUID, list[str]] = {}
        for alias in all_aliases:
            alias_map.setdefault(alias.entity_id, []).append(alias.alias_name)

        patterns: list[_EntityPattern] = []
        for entity in entities:
            names: list[str] = []

            # Add canonical name
            names.append(entity.canonical_name)

            # Add aliases (may include canonical name again, dedup below)
            entity_aliases = alias_map.get(entity.id, [])
            for alias_name in entity_aliases:
                if alias_name not in names:
                    names.append(alias_name)

            # Warn about short aliases
            for name in names:
                if len(name) < _MIN_ALIAS_LENGTH:
                    logger.warning(
                        "Entity %s (%s) has alias shorter than %d chars: '%s'",
                        entity.canonical_name,
                        entity.id,
                        _MIN_ALIAS_LENGTH,
                        name,
                    )

            # Build PostgreSQL regex pattern: \m(alias1|alias2|...)\M
            escaped_names = [re.escape(n) for n in names]
            pg_pattern = "|".join(escaped_names)

            patterns.append(
                _EntityPattern(
                    entity_id=entity.id,
                    canonical_name=entity.canonical_name,
                    entity_type=entity.entity_type,
                    pg_pattern=pg_pattern,
                    alias_names=names,
                    exclusion_patterns=list(entity.exclusion_patterns or []),
                )
            )

        logger.info(
            "Loaded %d entity patterns (%d total aliases)",
            len(patterns),
            sum(len(p.alias_names) for p in patterns),
        )
        return patterns

    async def _fetch_segment_batch(
        self,
        session: AsyncSession,
        video_ids: list[str] | None,
        language_code: str | None,
        batch_size: int,
        offset: int,
    ) -> list[Any]:
        """Fetch a batch of transcript segments with effective text.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_ids : list[str] | None
            Optional video ID filter.
        language_code : str | None
            Optional language filter.
        batch_size : int
            Maximum segments per batch.
        offset : int
            Pagination offset.

        Returns
        -------
        list[Any]
            List of Row objects with id, video_id, language_code, start_time,
            effective_text.
        """
        stmt: Select[tuple[Any, ...]] = select(
            TranscriptSegmentDB.id,
            TranscriptSegmentDB.video_id,
            TranscriptSegmentDB.language_code,
            TranscriptSegmentDB.start_time,
            literal_column(
                "CASE WHEN transcript_segments.has_correction "
                "THEN transcript_segments.corrected_text "
                "ELSE transcript_segments.text END"
            ).label("effective_text"),
        ).where(
            # Exclude segments with empty corrected text
            text(
                "NOT (transcript_segments.has_correction = TRUE "
                "AND (transcript_segments.corrected_text IS NULL "
                "OR transcript_segments.corrected_text = ''))"
            )
        )

        if video_ids is not None:
            stmt = stmt.where(TranscriptSegmentDB.video_id.in_(video_ids))
        if language_code is not None:
            stmt = stmt.where(TranscriptSegmentDB.language_code == language_code)

        stmt = stmt.order_by(TranscriptSegmentDB.id.asc())
        stmt = stmt.limit(batch_size).offset(offset)

        result = await session.execute(stmt)
        return list(result.all())

    async def _scan_batch(
        self,
        session: AsyncSession,
        batch_rows: list[Any],
        patterns: list[_EntityPattern],
        full_rescan: bool,
        dry_run: bool,
        limit: int | None,
        current_preview_count: int,
    ) -> tuple[list[EntityMentionCreate], int, list[dict[str, Any]], int, int]:
        """Scan a batch of segments against all entity patterns.

        For each segment, all entity patterns are matched via ``finditer()``
        to collect every occurrence.  Matches are then disambiguated with
        longest-match-wins and filtered through exclusion patterns before
        mention rows are created.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        batch_rows : list[Any]
            Segment rows from ``_fetch_segment_batch``.
        patterns : list[_EntityPattern]
            Entity patterns to match against.
        full_rescan : bool
            Whether this is a full rescan (skip dedup check).
        dry_run : bool
            Whether this is a dry-run.
        limit : int | None
            Dry-run preview limit.
        current_preview_count : int
            Number of preview rows already collected.

        Returns
        -------
        tuple[list[EntityMentionCreate], int, list[dict], int, int]
            (new_mentions, skipped_count, preview_data,
             longest_match_skips, exclusion_pattern_skips)
        """
        new_mentions: list[EntityMentionCreate] = []
        skipped = 0
        preview_data: list[dict[str, Any]] = []
        longest_match_skips = 0
        exclusion_pattern_skips = 0

        # Pre-compile all Python regexes
        compiled_patterns: list[tuple[_EntityPattern, re.Pattern[str]]] = []
        for pattern in patterns:
            try:
                py_regex = re.compile(
                    r"\b(" + pattern.pg_pattern + r")\b",
                    re.IGNORECASE,
                )
                compiled_patterns.append((pattern, py_regex))
            except re.error:
                logger.warning(
                    "Failed to compile regex for entity %s (%s), skipping",
                    pattern.canonical_name,
                    pattern.entity_id,
                )

        # Build a lookup from entity_id to pattern (for exclusion patterns)
        pattern_by_entity: dict[uuid.UUID, _EntityPattern] = {
            p.entity_id: p for p in patterns
        }

        for row in batch_rows:
            effective_text = row.effective_text
            if not effective_text:
                continue

            # ----------------------------------------------------------
            # Step 1: Collect ALL (entity_id, start, end, text) via finditer
            # ----------------------------------------------------------
            raw_matches: list[tuple[uuid.UUID, int, int, str, _EntityPattern]] = []
            for pattern, py_regex in compiled_patterns:
                for match in py_regex.finditer(effective_text):
                    raw_matches.append(
                        (
                            pattern.entity_id,
                            match.start(),
                            match.end(),
                            match.group(0),
                            pattern,
                        )
                    )

            if not raw_matches:
                continue

            # ----------------------------------------------------------
            # Step 2: Longest-match-wins disambiguation
            # ----------------------------------------------------------
            surviving_matches, lmw_skips = self._apply_longest_match_wins(
                raw_matches, row, dry_run
            )
            longest_match_skips += lmw_skips

            # ----------------------------------------------------------
            # Step 3: Exclusion pattern filtering
            # ----------------------------------------------------------
            final_matches, ep_skips = self._apply_exclusion_patterns(
                surviving_matches, effective_text, pattern_by_entity, row, dry_run
            )
            exclusion_pattern_skips += ep_skips

            if not final_matches:
                continue

            # ----------------------------------------------------------
            # Step 4: Incremental dedup check
            # ----------------------------------------------------------
            if not full_rescan:
                entity_ids_in_segment = list(
                    {entity_id for entity_id, _, _, _, _ in final_matches}
                )
                existing_stmt = select(
                    EntityMentionDB.segment_id,
                    EntityMentionDB.entity_id,
                ).where(
                    EntityMentionDB.segment_id == row.id,
                    EntityMentionDB.entity_id.in_(entity_ids_in_segment),
                )
                existing_result = await session.execute(existing_stmt)
                existing_pairs = {
                    (r.segment_id, r.entity_id) for r in existing_result.all()
                }
            else:
                existing_pairs = set()

            # ----------------------------------------------------------
            # Step 5: Create mentions from surviving matches
            # ----------------------------------------------------------
            for entity_id, m_start, m_end, matched_text, pat in final_matches:
                if (row.id, entity_id) in existing_pairs:
                    skipped += 1
                    continue

                mention = EntityMentionCreate(
                    entity_id=entity_id,
                    segment_id=row.id,
                    video_id=row.video_id,
                    language_code=row.language_code,
                    mention_text=matched_text,
                    detection_method=DetectionMethod.RULE_MATCH,
                    confidence=1.0,
                    match_start=m_start,
                    match_end=m_end,
                )
                new_mentions.append(mention)

                if dry_run:
                    if limit is None or (current_preview_count + len(preview_data)) < limit:
                        context = (
                            effective_text[:120]
                            if len(effective_text) > 120
                            else effective_text
                        )
                        preview_data.append(
                            {
                                "video_id": row.video_id,
                                "segment_id": row.id,
                                "start_time": row.start_time,
                                "entity_name": pat.canonical_name,
                                "entity_type": pat.entity_type,
                                "matched_text": matched_text,
                                "match_start": m_start,
                                "match_end": m_end,
                                "context": context,
                            }
                        )

                logger.debug(
                    "Match: entity=%s, segment_id=%d, video_id=%s, "
                    "text='%s', pos=%d-%d",
                    pat.canonical_name,
                    row.id,
                    row.video_id,
                    matched_text,
                    m_start,
                    m_end,
                )

        return new_mentions, skipped, preview_data, longest_match_skips, exclusion_pattern_skips

    # ------------------------------------------------------------------
    # Disambiguation & filtering helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_longest_match_wins(
        raw_matches: list[tuple[uuid.UUID, int, int, str, _EntityPattern]],
        row: Any,
        dry_run: bool,
    ) -> tuple[list[tuple[uuid.UUID, int, int, str, _EntityPattern]], int]:
        """Disambiguate overlapping matches using longest-match-wins.

        Parameters
        ----------
        raw_matches : list[tuple]
            All ``(entity_id, start, end, text, pattern)`` tuples for one segment.
        row : Any
            The segment row (used for logging).
        dry_run : bool
            Whether this is a dry-run.

        Returns
        -------
        tuple[list[tuple], int]
            (surviving_matches, skip_count)
        """
        # Sort by length descending, then start ascending for stability
        sorted_matches = sorted(
            raw_matches,
            key=lambda m: (-(m[2] - m[1]), m[1]),
        )

        # Store claimed intervals as (start, end) tuples for O(k) overlap checks
        # where k = number of claimed intervals, avoiding O(n) set operations on
        # character positions.
        claimed_intervals: list[tuple[int, int]] = []
        surviving: list[tuple[uuid.UUID, int, int, str, _EntityPattern]] = []
        skip_count = 0

        for entity_id, m_start, m_end, matched_text, pattern in sorted_matches:
            # Check overlap against all claimed intervals
            overlaps = any(
                c_start < m_end and c_end > m_start
                for c_start, c_end in claimed_intervals
            )
            if overlaps:
                skip_count += 1
                if dry_run:
                    logger.info(
                        "[DRY RUN] Segment %d: \"%s\" → SKIPPED "
                        "(longest-match-wins: overlapping longer match preferred)",
                        row.id,
                        matched_text,
                    )
                else:
                    logger.debug(
                        "Segment %d: \"%s\" skipped (longest-match-wins)",
                        row.id,
                        matched_text,
                    )
                continue

            claimed_intervals.append((m_start, m_end))
            surviving.append((entity_id, m_start, m_end, matched_text, pattern))

        return surviving, skip_count

    @staticmethod
    def _apply_exclusion_patterns(
        matches: list[tuple[uuid.UUID, int, int, str, _EntityPattern]],
        segment_text: str,
        pattern_by_entity: dict[uuid.UUID, _EntityPattern],
        row: Any,
        dry_run: bool,
    ) -> tuple[list[tuple[uuid.UUID, int, int, str, _EntityPattern]], int]:
        """Filter matches against entity exclusion patterns.

        For each surviving match, check if any of the entity's exclusion
        patterns overlap the match position in the segment text.

        Parameters
        ----------
        matches : list[tuple]
            Surviving matches after longest-match-wins.
        segment_text : str
            The full effective text of the segment.
        pattern_by_entity : dict
            Lookup from entity_id to ``_EntityPattern``.
        row : Any
            The segment row (used for logging).
        dry_run : bool
            Whether this is a dry-run.

        Returns
        -------
        tuple[list[tuple], int]
            (final_matches, skip_count)
        """
        final: list[tuple[uuid.UUID, int, int, str, _EntityPattern]] = []
        skip_count = 0

        for entity_id, m_start, m_end, matched_text, pattern in matches:
            ep = pattern_by_entity.get(entity_id)
            exclusions = ep.exclusion_patterns if ep else []

            suppressed = False
            for excl_pattern_text in exclusions:
                # Find all case-insensitive occurrences of the exclusion pattern
                try:
                    excl_regex = re.compile(re.escape(excl_pattern_text), re.IGNORECASE)
                except re.error:
                    logger.warning(
                        "Invalid exclusion pattern '%s' for entity %s, skipping",
                        excl_pattern_text,
                        entity_id,
                    )
                    continue

                for excl_match in excl_regex.finditer(segment_text):
                    pattern_start = excl_match.start()
                    pattern_end = excl_match.end()
                    # Overlap check: pattern_start < match_end AND pattern_end > match_start
                    if pattern_start < m_end and pattern_end > m_start:
                        suppressed = True
                        skip_count += 1
                        if dry_run:
                            logger.info(
                                "[DRY RUN] Segment %d: \"%s\" at %d-%d → SKIPPED "
                                "(exclusion pattern: \"%s\")",
                                row.id,
                                matched_text,
                                m_start,
                                m_end,
                                excl_pattern_text,
                            )
                        else:
                            logger.debug(
                                "Segment %d: \"%s\" at %d-%d suppressed by "
                                "exclusion pattern \"%s\"",
                                row.id,
                                matched_text,
                                m_start,
                                m_end,
                                excl_pattern_text,
                            )
                        break  # One overlap is enough to suppress
                if suppressed:
                    break

            if not suppressed:
                final.append((entity_id, m_start, m_end, matched_text, pattern))

        return final, skip_count


__all__ = ["EntityMentionScanService", "ScanResult"]