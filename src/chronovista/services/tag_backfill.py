"""
Tag normalization backfill pipeline service.

This module provides the ``TagBackfillService`` that orchestrates the tag
normalization backfill process — scanning existing ``video_tags`` rows,
normalizing each raw tag, and populating the ``canonical_tags`` and
``tag_aliases`` tables.

References
----------
- FR-019: Known false-merge patterns for Tier 1 diacritic stripping
- FR-022: Table existence check before backfill
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress
from rich.table import Table
from sqlalchemy import distinct, func, inspect as sa_inspect, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import VideoTag as VideoTagDB
from chronovista.repositories.video_tag_repository import VideoTagRepository
from chronovista.services.tag_normalization import TagNormalizationService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known Tier 1 false-merge patterns (FR-019)
# These normalized forms merge semantically distinct words due to diacritic
# stripping.  Reported as "known false-merge" in collision detection output.
# ---------------------------------------------------------------------------
KNOWN_FALSE_MERGE_PATTERNS: frozenset[str] = frozenset(
    {
        "cafe",  # café (French loanword) / cafe (English)
        "resume",  # résumé (French loanword) / resume (English verb)
        "cliche",  # cliché (French loanword) / cliche (anglicized)
        "naive",  # naïve (French loanword) / naive (anglicized)
        "rape",  # Rapé (cartoonist) / rape (unrelated English word)
    }
)


class TagBackfillService:
    """Orchestrates tag normalization backfill, analysis, and recount operations.

    Parameters
    ----------
    normalization_service : TagNormalizationService
        The service that provides the 9-step normalization pipeline and
        canonical form selection logic.
    """

    def __init__(self, normalization_service: TagNormalizationService) -> None:
        self._normalization_service = normalization_service

    async def _check_tables_exist(self, session: AsyncSession) -> None:
        """Check that ``canonical_tags`` and ``tag_aliases`` tables exist.

        Raises ``SystemExit`` with a user-friendly message directing the user
        to run ``alembic upgrade head`` if either table is missing (FR-022).

        Parameters
        ----------
        session : AsyncSession
            An active SQLAlchemy async session used to inspect the database.

        Raises
        ------
        SystemExit
            If one or both required tables are missing from the database.
        """

        def _sync_check(connection) -> list[str]:  # type: ignore[no-untyped-def]
            inspector = sa_inspect(connection)
            tables = inspector.get_table_names()
            missing: list[str] = []
            if "canonical_tags" not in tables:
                missing.append("canonical_tags")
            if "tag_aliases" not in tables:
                missing.append("tag_aliases")
            return missing

        conn = await session.connection()
        missing = await conn.run_sync(_sync_check)
        if missing:
            table_list = ", ".join(missing)
            raise SystemExit(
                f"Required table(s) missing: {table_list}. "
                f"Run 'alembic upgrade head' to create them."
            )

    # ------------------------------------------------------------------
    # T004: Normalization and grouping
    # ------------------------------------------------------------------

    def _normalize_and_group_core(
        self,
        distinct_tags: dict[str, int],
    ) -> tuple[
        dict[str, list[tuple[str, int]]],  # groups: normalized_form -> [(raw_form, count), ...]
        list[tuple[str, int]],  # skip_list: [(raw_form, count), ...]
    ]:
        """Normalize tags and group aliases by normalized form.

        This is the shared helper used by both ``_normalize_and_group`` (backfill)
        and ``run_analysis`` (Phase 3).  It performs normalization and grouping
        but does **not** generate UUIDs or batch records.

        Parameters
        ----------
        distinct_tags : dict[str, int]
            Mapping of raw tag strings to their occurrence counts.

        Returns
        -------
        tuple[dict[str, list[tuple[str, int]]], list[tuple[str, int]]]
            A 2-tuple of:
            - ``groups``: normalized_form -> list of (raw_form, count) tuples
            - ``skip_list``: list of (raw_form, count) tuples that could not
              be normalized (normalize returned ``None``)
        """
        groups: dict[str, list[tuple[str, int]]] = defaultdict(list)
        skip_list: list[tuple[str, int]] = []

        for raw_tag, count in distinct_tags.items():
            normalized = self._normalization_service.normalize(raw_tag)
            if normalized is None:
                skip_list.append((raw_tag, count))
                logger.debug("Skipping tag (normalizes to empty): %r", raw_tag)
            else:
                groups[normalized].append((raw_tag, count))

        logger.info(
            "Normalization complete: %d groups, %d skipped",
            len(groups),
            len(skip_list),
        )
        return dict(groups), skip_list

    def _normalize_and_group(
        self,
        distinct_tags: dict[str, int],
        execution_timestamp: datetime,
    ) -> tuple[
        list[dict[str, Any]],  # canonical_tags batch records
        list[dict[str, Any]],  # tag_aliases batch records
        list[tuple[str, int]],  # skip_list
    ]:
        """Normalize, group, and build batch insert records for the backfill.

        Delegates to ``_normalize_and_group_core`` for the normalization step,
        then generates UUIDv7 primary keys and assembles the batch dictionaries
        required by ``_batch_insert_canonical_tags`` and ``_batch_insert_tag_aliases``.

        Parameters
        ----------
        distinct_tags : dict[str, int]
            Mapping of raw tag strings to their occurrence counts.
        execution_timestamp : datetime
            The timestamp to use for ``first_seen_at`` and ``last_seen_at``
            on all tag alias records.

        Returns
        -------
        tuple[list[dict[str, Any]], list[dict[str, Any]], list[tuple[str, int]]]
            A 3-tuple of:
            - ``canonical_tags_batch``: dicts ready for bulk insert into
              ``canonical_tags``
            - ``tag_aliases_batch``: dicts ready for bulk insert into
              ``tag_aliases``
            - ``skip_list``: raw tags that could not be normalized
        """
        groups, skip_list = self._normalize_and_group_core(distinct_tags)

        canonical_tags_batch: list[dict[str, Any]] = []
        tag_aliases_batch: list[dict[str, Any]] = []

        for normalized_form, aliases in groups.items():
            # Pre-generate a UUIDv7 for the canonical tag (convert for Pydantic compat)
            ct_id = uuid.UUID(bytes=uuid7().bytes)

            canonical_form = self._normalization_service.select_canonical_form(aliases)

            canonical_tags_batch.append(
                {
                    "id": ct_id,
                    "canonical_form": canonical_form,
                    "normalized_form": normalized_form,
                    "alias_count": len(aliases),
                    "video_count": 0,
                    "status": "active",
                }
            )

            for raw_form, occ_count in aliases:
                alias_id = uuid.UUID(bytes=uuid7().bytes)
                tag_aliases_batch.append(
                    {
                        "id": alias_id,
                        "raw_form": raw_form,
                        "normalized_form": normalized_form,
                        "canonical_tag_id": ct_id,
                        "creation_method": "backfill",
                        "normalization_version": 1,
                        "occurrence_count": occ_count,
                        "first_seen_at": execution_timestamp,
                        "last_seen_at": execution_timestamp,
                    }
                )

        logger.info(
            "Prepared %d canonical tag records and %d tag alias records",
            len(canonical_tags_batch),
            len(tag_aliases_batch),
        )
        return canonical_tags_batch, tag_aliases_batch, skip_list

    # ------------------------------------------------------------------
    # T005: Batch insert helpers
    # ------------------------------------------------------------------

    async def _batch_insert_canonical_tags(
        self,
        session: AsyncSession,
        records: list[dict[str, Any]],
        batch_size: int,
    ) -> tuple[int, int]:
        """Insert canonical tag records in batches, skipping conflicts.

        Parameters
        ----------
        session : AsyncSession
            An active SQLAlchemy async session.
        records : list[dict[str, Any]]
            List of dicts to insert into ``canonical_tags``.
        batch_size : int
            Number of records per batch.

        Returns
        -------
        tuple[int, int]
            ``(inserted, skipped)`` — the number of rows actually inserted
            and the number skipped due to ``ON CONFLICT DO NOTHING``.
        """
        inserted = 0
        skipped = 0

        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            stmt = pg_insert(CanonicalTagDB).values(batch).on_conflict_do_nothing()
            result = await session.execute(stmt)
            await session.commit()
            batch_inserted = result.rowcount
            inserted += batch_inserted
            skipped += len(batch) - batch_inserted

        logger.info(
            "Canonical tags: %d inserted, %d skipped (already exist)",
            inserted,
            skipped,
        )
        return inserted, skipped

    async def _batch_insert_tag_aliases(
        self,
        session: AsyncSession,
        records: list[dict[str, Any]],
        batch_size: int,
    ) -> tuple[int, int]:
        """Insert tag alias records in batches, skipping conflicts.

        Parameters
        ----------
        session : AsyncSession
            An active SQLAlchemy async session.
        records : list[dict[str, Any]]
            List of dicts to insert into ``tag_aliases``.
        batch_size : int
            Number of records per batch.

        Returns
        -------
        tuple[int, int]
            ``(inserted, skipped)`` — the number of rows actually inserted
            and the number skipped due to ``ON CONFLICT DO NOTHING``.
        """
        inserted = 0
        skipped = 0

        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            stmt = pg_insert(TagAliasDB).values(batch).on_conflict_do_nothing()
            result = await session.execute(stmt)
            await session.commit()
            batch_inserted = result.rowcount
            inserted += batch_inserted
            skipped += len(batch) - batch_inserted

        logger.info(
            "Tag aliases: %d inserted, %d skipped (already exist)",
            inserted,
            skipped,
        )
        return inserted, skipped

    # ------------------------------------------------------------------
    # T006: Video count update
    # ------------------------------------------------------------------

    async def _update_video_counts(self, session: AsyncSession) -> int:
        """Update ``video_count`` on every canonical tag using a correlated subquery.

        Joins ``tag_aliases.raw_form`` to ``video_tags.tag`` to count distinct
        videos per canonical tag, then writes the result back.

        Parameters
        ----------
        session : AsyncSession
            An active SQLAlchemy async session.

        Returns
        -------
        int
            The number of canonical tag rows updated.
        """
        subq = (
            select(
                TagAliasDB.canonical_tag_id,
                func.count(distinct(VideoTagDB.video_id)).label("cnt"),
            )
            .join(VideoTagDB, VideoTagDB.tag == TagAliasDB.raw_form)
            .group_by(TagAliasDB.canonical_tag_id)
            .subquery()
        )

        stmt = (
            update(CanonicalTagDB)
            .where(CanonicalTagDB.id == subq.c.canonical_tag_id)
            .values(video_count=subq.c.cnt)
        )
        result = await session.execute(stmt)
        await session.commit()

        logger.info("Updated video_count on %d canonical tags", result.rowcount)
        return result.rowcount

    # ------------------------------------------------------------------
    # T007: Orchestrator
    # ------------------------------------------------------------------

    async def run_backfill(
        self,
        session: AsyncSession,
        batch_size: int = 1000,
        console: Console | None = None,
    ) -> None:
        """Run the full tag normalization backfill pipeline.

        Scans all distinct tags in ``video_tags``, normalizes each one,
        groups aliases under canonical forms, batch-inserts into
        ``canonical_tags`` and ``tag_aliases``, and updates video counts.

        The operation is idempotent: re-running skips rows that already
        exist (``ON CONFLICT DO NOTHING``).

        Parameters
        ----------
        session : AsyncSession
            An active SQLAlchemy async session.
        batch_size : int, optional
            Number of records per INSERT batch (default ``1000``).
            Must be >= 1.
        console : Console | None, optional
            Rich console for output.  A default console is created if
            ``None``.

        Raises
        ------
        SystemExit
            If ``batch_size < 1`` (exit code 2) or if required tables
            are missing from the database.
        """
        if batch_size < 1:
            raise SystemExit(2)

        start_time = time.time()
        _console = console or Console()

        # Step 1: Verify required tables exist (FR-022)
        await self._check_tables_exist(session)

        # Step 2: Query distinct tags from video_tags
        repo = VideoTagRepository()
        raw_tags = await repo.get_distinct_tags_with_counts(session)
        distinct_tags: dict[str, int] = {tag: count for tag, count in raw_tags}

        logger.info("Found %d distinct tags in video_tags", len(distinct_tags))

        # Step 3: Normalize, group, and prepare batch records
        execution_timestamp = datetime.now(UTC)
        ct_records, ta_records, skip_list = self._normalize_and_group(
            distinct_tags, execution_timestamp
        )

        # Step 4: Batch insert with Rich progress bar
        with Progress(console=_console) as progress:
            task = progress.add_task(
                "Processing distinct tags...",
                total=len(ct_records) + len(ta_records),
            )

            ct_inserted, ct_skipped = await self._batch_insert_canonical_tags(
                session, ct_records, batch_size
            )
            progress.update(task, advance=len(ct_records))

            ta_inserted, ta_skipped = await self._batch_insert_tag_aliases(
                session, ta_records, batch_size
            )
            progress.update(task, advance=len(ta_records))

        # Step 5: Update video counts
        updated = await self._update_video_counts(session)
        logger.info("Updated video_count on %d canonical tags", updated)

        # Step 6: Print completion summary
        elapsed = time.time() - start_time

        _console.print()
        _console.print("[bold]── Backfill Complete ──[/bold]")
        _console.print()

        ct_line = f"Canonical tags created:    {ct_inserted:>7,}"
        if ct_skipped > 0:
            ct_line += f"  ({ct_skipped:,} already exist)"
        _console.print(ct_line)

        ta_line = f"Tag aliases created:      {ta_inserted:>7,}"
        if ta_skipped > 0:
            ta_line += f"  ({ta_skipped:,} already exist)"
        _console.print(ta_line)

        _console.print(f"Tags skipped:             {len(skip_list):>7,}")

        minutes, seconds = divmod(int(elapsed), 60)
        if minutes > 0:
            _console.print(f"Elapsed time:            {minutes}m {seconds:02d}s")
        else:
            _console.print(f"Elapsed time:              {seconds}s")

        # Step 7: Display skipped tags table if any
        if skip_list:
            skip_table = Table(title="Skipped Tags")
            skip_table.add_column("Raw Form")
            skip_table.add_column("Occurrences", justify="right")
            for raw_form, count in skip_list:
                skip_table.add_row(repr(raw_form), str(count))
            _console.print(skip_table)

    # ------------------------------------------------------------------
    # T012: Collision detection
    # ------------------------------------------------------------------

    def _detect_collisions(
        self,
        groups: dict[str, list[tuple[str, int]]],
    ) -> list[dict[str, Any]]:
        """Detect collision candidates among normalized tag groups.

        A collision occurs when a single normalized form merges raw tags
        whose *casefolded* forms (after stripping leading ``#`` and
        whitespace) are distinct.  This indicates the normalization
        pipeline merged semantically different words — typically due to
        diacritic stripping.

        Parameters
        ----------
        groups : dict[str, list[tuple[str, int]]]
            Mapping of normalized form to list of ``(raw_form, count)``
            tuples, as returned by ``_normalize_and_group_core``.

        Returns
        -------
        list[dict[str, Any]]
            Collision candidates sorted by total occurrence count
            descending.  Each entry has keys ``normalized_form``,
            ``aliases`` (list of dicts with ``raw_form`` and
            ``occurrence_count``), and ``is_known_false_merge``.
        """
        collisions: list[dict[str, Any]] = []

        for normalized_form, aliases in groups.items():
            if len(aliases) < 2:
                continue

            # For each raw form: strip leading #, strip whitespace, casefold
            # (do NOT strip diacritics)
            casefolded_set: set[str] = set()
            for raw_form, _count in aliases:
                cleaned = raw_form.strip()
                if cleaned.startswith("#"):
                    cleaned = cleaned[1:]
                cleaned = cleaned.strip().casefold()
                casefolded_set.add(cleaned)

            # Collision only if 2+ distinct casefolded values remain
            if len(casefolded_set) < 2:
                continue

            total_count = sum(count for _, count in aliases)
            is_known = normalized_form in KNOWN_FALSE_MERGE_PATTERNS

            collisions.append(
                {
                    "normalized_form": normalized_form,
                    "aliases": [
                        {"raw_form": rf, "occurrence_count": c}
                        for rf, c in aliases
                    ],
                    "is_known_false_merge": is_known,
                }
            )

        # Sort by total occurrence count descending
        collisions.sort(
            key=lambda c: sum(a["occurrence_count"] for a in c["aliases"]),
            reverse=True,
        )

        return collisions

    # ------------------------------------------------------------------
    # T013: Analysis (read-only)
    # ------------------------------------------------------------------

    async def run_analysis(
        self,
        session: AsyncSession,
        output_format: str = "table",
        console: Console | None = None,
    ) -> dict[str, Any] | None:
        """Run read-only tag normalization analysis.

        Queries all distinct tags, normalizes them in-memory, computes
        summary statistics, detects collision candidates, and outputs
        results in either Rich table or JSON format.

        This method **never writes** to the database.

        Parameters
        ----------
        session : AsyncSession
            An active SQLAlchemy async session (read-only usage).
        output_format : str, optional
            ``"table"`` for Rich console output, ``"json"`` for machine-
            readable JSON (default ``"table"``).
        console : Console | None, optional
            Rich console for output.  A default console is created if
            ``None``.

        Returns
        -------
        dict[str, Any] | None
            The analysis result dict when ``output_format="json"``,
            ``None`` when ``output_format="table"``.

        Raises
        ------
        SystemExit
            If required tables are missing from the database.
        """
        _console = console or Console()

        # Step 1: Verify required tables exist (FR-022)
        await self._check_tables_exist(session)

        # Step 2: Query distinct tags from video_tags
        repo = VideoTagRepository()
        raw_tags = await repo.get_distinct_tags_with_counts(session)
        distinct_tags: dict[str, int] = {tag: count for tag, count in raw_tags}

        # Step 3: Normalize and group
        groups, skip_list = self._normalize_and_group_core(distinct_tags)

        # Step 4: Compute summary stats
        total_distinct_tags = len(distinct_tags)
        estimated_canonical_tags = len(groups)
        skip_count = len(skip_list)

        # Step 5: Select canonical forms and build top 20
        canonical_entries: list[dict[str, Any]] = []
        for normalized_form, aliases in groups.items():
            canonical_form = self._normalization_service.select_canonical_form(aliases)
            canonical_entries.append(
                {
                    "canonical_form": canonical_form,
                    "normalized_form": normalized_form,
                    "alias_count": len(aliases),
                    "aliases": [rf for rf, _c in aliases],
                }
            )

        # Sort by alias count descending and take top 20
        canonical_entries.sort(key=lambda e: e["alias_count"], reverse=True)
        top_canonical_tags = canonical_entries[:20]

        # Step 6: Detect collision candidates
        collision_candidates = self._detect_collisions(groups)

        # Step 7: Build skip list
        skipped_tags = [
            {"raw_form": rf, "occurrence_count": c} for rf, c in skip_list
        ]

        # ---- Output ----

        if output_format == "json":
            result: dict[str, Any] = {
                "total_distinct_tags": total_distinct_tags,
                "estimated_canonical_tags": estimated_canonical_tags,
                "skip_count": skip_count,
                "top_canonical_tags": top_canonical_tags,
                "collision_candidates": collision_candidates,
                "skipped_tags": skipped_tags,
            }
            _console.print(json.dumps(result, indent=2, default=str))
            return result

        # --- Table format ---

        # Summary panel
        summary_text = (
            f"[bold]Total distinct tags:[/bold]      {total_distinct_tags:>10,}\n"
            f"[bold]Estimated canonical tags:[/bold]  {estimated_canonical_tags:>10,}\n"
            f"[bold]Tags skipped:[/bold]              {skip_count:>10,}"
        )
        _console.print(Panel(summary_text, title="Analysis Summary", border_style="blue"))

        # Top 20 canonical tags table
        top_table = Table(title="Top 20 Canonical Tags by Alias Count")
        top_table.add_column("Rank", style="dim", width=6)
        top_table.add_column("Canonical Form", style="cyan", width=30)
        top_table.add_column("Normalized Form", style="white", width=30)
        top_table.add_column("Aliases", justify="right", width=10)
        top_table.add_column("Alias List", style="dim", width=50)
        for rank, entry in enumerate(top_canonical_tags, 1):
            alias_str = ", ".join(entry["aliases"][:5])
            if len(entry["aliases"]) > 5:
                alias_str += f" (+{len(entry['aliases']) - 5} more)"
            top_table.add_row(
                str(rank),
                entry["canonical_form"],
                entry["normalized_form"],
                str(entry["alias_count"]),
                alias_str,
            )
        _console.print(top_table)

        # Collision candidates
        if collision_candidates:
            collision_table = Table(title="Collision Candidates")
            collision_table.add_column("Normalized Form", style="cyan", width=25)
            collision_table.add_column("Aliases", style="white", width=50)
            collision_table.add_column("Total Count", justify="right", width=12)
            collision_table.add_column("Status", width=25)
            for candidate in collision_candidates:
                alias_parts = [
                    f"{a['raw_form']} ({a['occurrence_count']:,})"
                    for a in candidate["aliases"]
                ]
                alias_display = ", ".join(alias_parts)
                total = sum(a["occurrence_count"] for a in candidate["aliases"])
                status = (
                    "[yellow]Known false-merge[/yellow]"
                    if candidate["is_known_false_merge"]
                    else ""
                )
                collision_table.add_row(
                    candidate["normalized_form"],
                    alias_display,
                    f"{total:,}",
                    status,
                )
            _console.print(collision_table)
        else:
            _console.print(
                Panel(
                    "[green]No collision candidates detected.[/green]",
                    title="Collision Candidates",
                    border_style="green",
                )
            )

        # Skip list
        if skipped_tags:
            skip_table = Table(title="Skipped Tags")
            skip_table.add_column("Raw Form", width=40)
            skip_table.add_column("Occurrences", justify="right", width=12)
            for entry in skipped_tags:
                skip_table.add_row(repr(entry["raw_form"]), str(entry["occurrence_count"]))
            _console.print(skip_table)
        else:
            _console.print(
                Panel(
                    "[green]No tags were skipped.[/green]",
                    title="Skipped Tags",
                    border_style="green",
                )
            )

        return None

    # ------------------------------------------------------------------
    # T017: Recount utility
    # ------------------------------------------------------------------

    async def run_recount(
        self,
        session: AsyncSession,
        dry_run: bool = False,
        console: Console | None = None,
    ) -> None:
        """Recalculate ``alias_count`` and ``video_count`` on all canonical tags.

        Computes the true counts from ``tag_aliases`` and ``video_tags`` and
        either previews the deltas (``dry_run=True``) or writes the corrected
        values (``dry_run=False``).

        Parameters
        ----------
        session : AsyncSession
            An active SQLAlchemy async session.
        dry_run : bool, optional
            If ``True``, show a Rich table of count deltas without writing to
            the database.  Default is ``False``.
        console : Console | None, optional
            Rich console for output.  A default console is created if
            ``None``.

        Raises
        ------
        SystemExit
            If required tables are missing from the database (FR-022).
        """
        start_time = time.time()
        _console = console or Console()

        # Step 1: Verify required tables exist (FR-022)
        await self._check_tables_exist(session)

        # Step 2: Compute new alias_count for all canonical tags
        alias_query = select(
            TagAliasDB.canonical_tag_id,
            func.count().label("new_alias_count"),
        ).group_by(TagAliasDB.canonical_tag_id)
        alias_rows = (await session.execute(alias_query)).all()
        new_alias_counts: dict[uuid.UUID, int] = {
            row.canonical_tag_id: row.new_alias_count for row in alias_rows
        }

        # Step 3: Compute new video_count for all canonical tags
        video_query = (
            select(
                TagAliasDB.canonical_tag_id,
                func.count(distinct(VideoTagDB.video_id)).label("new_video_count"),
            )
            .join(VideoTagDB, VideoTagDB.tag == TagAliasDB.raw_form)
            .group_by(TagAliasDB.canonical_tag_id)
        )
        video_rows = (await session.execute(video_query)).all()
        new_video_counts: dict[uuid.UUID, int] = {
            row.canonical_tag_id: row.new_video_count for row in video_rows
        }

        # Step 4: Fetch current counts from canonical_tags
        current_stmt = select(
            CanonicalTagDB.id,
            CanonicalTagDB.alias_count,
            CanonicalTagDB.video_count,
        )
        current_rows = (await session.execute(current_stmt)).all()

        # Step 5: Compare current vs recalculated
        deltas: list[tuple[uuid.UUID, int, int, int, int]] = []
        for row in current_rows:
            ct_id = row.id
            current_alias = row.alias_count
            current_video = row.video_count
            new_alias = new_alias_counts.get(ct_id, 0)
            new_video = new_video_counts.get(ct_id, 0)
            if current_alias != new_alias or current_video != new_video:
                deltas.append(
                    (ct_id, current_alias, new_alias, current_video, new_video)
                )

        if dry_run:
            # Show Rich table with deltas only
            if not deltas:
                _console.print("All counts are correct.")
            else:
                delta_table = Table(title="Count Deltas (Dry Run)")
                delta_table.add_column("Canonical Tag ID", style="dim")
                delta_table.add_column("Current Alias", justify="right")
                delta_table.add_column("New Alias", justify="right")
                delta_table.add_column("Current Video", justify="right")
                delta_table.add_column("New Video", justify="right")
                for ct_id, cur_alias, new_alias, cur_video, new_video in deltas:
                    delta_table.add_row(
                        str(ct_id),
                        str(cur_alias),
                        str(new_alias),
                        str(cur_video),
                        str(new_video),
                    )
                _console.print(delta_table)
                _console.print(f"Total with deltas: {len(deltas)}")
            return

        # Step 6: Write corrected counts (non-dry-run mode)
        # Update alias_count via correlated subquery
        alias_count_subq = (
            select(
                TagAliasDB.canonical_tag_id,
                func.count().label("cnt"),
            )
            .group_by(TagAliasDB.canonical_tag_id)
            .subquery()
        )
        alias_update_stmt = (
            update(CanonicalTagDB)
            .where(CanonicalTagDB.id == alias_count_subq.c.canonical_tag_id)
            .values(alias_count=alias_count_subq.c.cnt)
        )
        await session.execute(alias_update_stmt)

        # Update video_count via correlated subquery
        video_count_subq = (
            select(
                TagAliasDB.canonical_tag_id,
                func.count(distinct(VideoTagDB.video_id)).label("cnt"),
            )
            .join(VideoTagDB, VideoTagDB.tag == TagAliasDB.raw_form)
            .group_by(TagAliasDB.canonical_tag_id)
            .subquery()
        )
        video_update_stmt = (
            update(CanonicalTagDB)
            .where(CanonicalTagDB.id == video_count_subq.c.canonical_tag_id)
            .values(video_count=video_count_subq.c.cnt)
        )
        await session.execute(video_update_stmt)
        await session.commit()

        # Step 7: Print summary
        elapsed = time.time() - start_time
        total_updated = len(deltas)
        _console.print(f"Total updated: {total_updated}")

        minutes, seconds = divmod(int(elapsed), 60)
        if minutes > 0:
            _console.print(f"Elapsed time: {minutes}m {seconds:02d}s")
        else:
            _console.print(f"Elapsed time: {seconds}s")
