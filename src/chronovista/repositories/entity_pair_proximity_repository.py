"""
Entity-pair proximity repository (Feature 116).

Backs the transcript proximity primitive: the instance table
(``entity_pair_proximity``) is populated by a single in-database INSERT…SELECT
self-join of ``entity_mentions`` (the compute lives in SQL, never pulled into
Python — the join is large), and the per-pair aggregate
(``entity_pair_proximity_rollup``) is rebuilt from those instances. Run tracking
mirrors ``relationship_candidate_repository`` (a global single-active lock).

All data access for the computor lives here rather than in the service so the
repository pattern (Principle III) is not bypassed. The FR-016 language-scoping
invariant is expressed as :func:`language_scope_predicate` — a single, isolatable
clause the mutation-verified guard (T015) removes to prove the join fabricates
cross-language instances without it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Select,
    delete,
    func,
    literal,
    or_,
    select,
    tuple_,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from uuid_utils import uuid7

from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import EntityPairProximity as EntityPairProximityDB
from chronovista.db.models import (
    EntityPairProximityRollup as EntityPairProximityRollupDB,
)
from chronovista.db.models import EntityVideoExclusion as EntityVideoExclusionDB
from chronovista.db.models import ProximityDirtyScope as ProximityDirtyScopeDB
from chronovista.db.models import ProximityGenerationRun as ProximityGenerationRunDB
from chronovista.db.models import RelationshipCandidate as RelationshipCandidateDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.entity_pair_proximity import EntityPairProximityCreate
from chronovista.repositories.base import BaseSQLAlchemyRepository

# asyncpg rejects a statement with > 32,767 bind parameters. The Python-object
# insert binds ~8 params/row and the pair-IN rollup binds 2/pair, so chunk well
# under the ceiling. (The main compute path is INSERT…SELECT and binds nothing
# per row — only the scoped Python helpers need chunking.)
_CHUNK_SIZE = 1000


def language_scope_predicate(
    segment_a: type[TranscriptSegmentDB], segment_b: type[TranscriptSegmentDB]
) -> ColumnElement[bool]:
    """FR-016 invariant: the two mentions must share the SAME transcript language.

    This is the single, isolatable join clause the mutation-verified guard (T015)
    removes. One video can carry N transcripts of the same audio on an aligned
    timeline; without this predicate the self-join pairs a mention in one language
    with its translation in another and fabricates a near-zero gap (the artifact
    that *inverts* ``min_gap_seconds`` into a false strong signal). A pair-keyed
    aggregate has nowhere to store language, so the invariant is enforced here in
    the computor rather than by a table constraint.
    """
    return segment_a.language_code == segment_b.language_code


def _exclusion_exists(mention: type[EntityMentionDB]) -> ColumnElement[bool]:
    """F091 anti-join: True when ``(entity_id, video_id)`` is manually excluded.

    ``entity_video_exclusions`` is keyed ``(entity_id, video_id)`` with no language
    column, so one exclusion suppresses the entity across all of a video's
    transcripts. Applied to BOTH endpoints of the pair in :func:`_instance_select`.
    """
    return (
        select(literal(1))
        .select_from(EntityVideoExclusionDB)
        .where(
            EntityVideoExclusionDB.entity_id == mention.entity_id,
            EntityVideoExclusionDB.video_id == mention.video_id,
        )
        .exists()
    )


def _scope_pairs_cte(support_min: int) -> Any:
    """Canonically-ordered pairs eligible for proximity: support-only ∪ reviewed.

    The self-join is bounded to pairs that either clear transcript co-occurrence
    SUPPORT (shared videos >= ``support_min``) OR already carry a verdict in
    ``relationship_candidates`` (``review_status IS NOT NULL``, FR-019). NOT bounded
    by lift — a lift gate would exclude the hub-anchored orphans the feature exists
    to rescue (D5).
    """
    transcript_mentions = (
        select(
            EntityMentionDB.entity_id.label("entity_id"),
            EntityMentionDB.video_id.label("video_id"),
        )
        .where(
            EntityMentionDB.mention_source == "transcript",
            EntityMentionDB.segment_id.is_not(None),
        )
        .distinct()
        .cte("proximity_transcript_mentions")
    )
    tv_a = aliased(transcript_mentions, name="tv_a")
    tv_b = aliased(transcript_mentions, name="tv_b")
    support_pairs = (
        select(
            tv_a.c.entity_id.label("entity_a_id"),
            tv_b.c.entity_id.label("entity_b_id"),
        )
        .select_from(tv_a)
        .join(tv_b, tv_a.c.video_id == tv_b.c.video_id)
        .where(tv_a.c.entity_id < tv_b.c.entity_id)
        .group_by(tv_a.c.entity_id, tv_b.c.entity_id)
        .having(func.count() >= support_min)
    )
    reviewed_pairs = select(
        RelationshipCandidateDB.entity_a_id.label("entity_a_id"),
        RelationshipCandidateDB.entity_b_id.label("entity_b_id"),
    ).where(RelationshipCandidateDB.review_status.is_not(None))
    return support_pairs.union(reviewed_pairs).cte("proximity_scope_pairs")


def _instance_select(
    *,
    support_min: int,
    outer_window: float,
    video_ids: Sequence[str] | None,
    entity_ids: Sequence[uuid.UUID] | None,
) -> Select[Any]:
    """The mention×mention proximity self-join (D3/D8), scoped and language-safe.

    One output row per close co-mention ``(pair, video, segment_a, segment_b)`` whose
    start times are within ``outer_window`` seconds, restricted to in-scope pairs,
    with both F091-excluded endpoints removed. The segment ``start_time`` is the
    position anchor for cross-segment mentions (FR-021 — ``segment_id`` is the start
    segment). ``gap_seconds = abs(start_a - start_b)``.
    """
    ma = aliased(EntityMentionDB, name="ma")
    mb = aliased(EntityMentionDB, name="mb")
    sa = aliased(TranscriptSegmentDB, name="sa")
    sb = aliased(TranscriptSegmentDB, name="sb")
    scope = _scope_pairs_cte(support_min)

    gap = func.abs(sa.start_time - sb.start_time)

    stmt = (
        select(
            func.gen_random_uuid().label("id"),
            ma.entity_id.label("entity_a_id"),
            mb.entity_id.label("entity_b_id"),
            ma.video_id.label("video_id"),
            sa.language_code.label("language_code"),
            ma.segment_id.label("segment_a_id"),
            mb.segment_id.label("segment_b_id"),
            gap.label("gap_seconds"),
        )
        .select_from(ma)
        .join(sa, sa.id == ma.segment_id)
        .join(
            mb,
            (mb.video_id == ma.video_id) & (ma.entity_id < mb.entity_id),
        )
        .join(sb, sb.id == mb.segment_id)
        .join(
            scope,
            (scope.c.entity_a_id == ma.entity_id)
            & (scope.c.entity_b_id == mb.entity_id),
        )
        .where(
            ma.mention_source == "transcript",
            ma.segment_id.is_not(None),
            mb.mention_source == "transcript",
            mb.segment_id.is_not(None),
            language_scope_predicate(sa, sb),  # FR-016 — the isolatable invariant
            gap <= outer_window,
            ~_exclusion_exists(ma),
            ~_exclusion_exists(mb),
        )
    )
    if video_ids:
        stmt = stmt.where(ma.video_id.in_(list(video_ids)))
    if entity_ids:
        ids = list(entity_ids)
        stmt = stmt.where(or_(ma.entity_id.in_(ids), mb.entity_id.in_(ids)))
    return stmt


_INSTANCE_INSERT_COLUMNS = [
    "id",
    "entity_a_id",
    "entity_b_id",
    "video_id",
    "language_code",
    "segment_a_id",
    "segment_b_id",
    "gap_seconds",
]
_ROLLUP_INSERT_COLUMNS = [
    "entity_a_id",
    "entity_b_id",
    "close_co_mentions_15",
    "close_co_mentions_30",
    "close_co_mentions_60",
    "min_gap_seconds",
    "shared_videos",
]


def _rollup_select(
    windows: tuple[int, int, int],
    *,
    pair_filter: ColumnElement[bool] | None = None,
) -> Select[Any]:
    """Per-pair aggregate over the instance rows (optionally scoped to ``pair_filter``).

    The three ``close_co_mentions_{15,30,60}`` counts are read-time predicates over
    ``gap_seconds`` (every stored instance already has ``gap <= OUTER_WINDOW``), so a
    pair's rollup is derivable entirely from its instances. ``min_gap_seconds`` is the
    smallest gap over all the pair's instances (language-scoped by construction, since
    every instance is); ``shared_videos`` is the distinct video count.
    """
    close15, close30, close60 = windows
    gap = EntityPairProximityDB.gap_seconds
    stmt = select(
        EntityPairProximityDB.entity_a_id.label("entity_a_id"),
        EntityPairProximityDB.entity_b_id.label("entity_b_id"),
        func.count().filter(gap <= close15).label("close_co_mentions_15"),
        func.count().filter(gap <= close30).label("close_co_mentions_30"),
        func.count().filter(gap <= close60).label("close_co_mentions_60"),
        func.min(gap).label("min_gap_seconds"),
        func.count(func.distinct(EntityPairProximityDB.video_id)).label(
            "shared_videos"
        ),
    ).group_by(EntityPairProximityDB.entity_a_id, EntityPairProximityDB.entity_b_id)
    if pair_filter is not None:
        stmt = stmt.where(pair_filter)
    return stmt


def _chunked(
    pairs: Sequence[tuple[uuid.UUID, uuid.UUID]], size: int
) -> Iterable[Sequence[tuple[uuid.UUID, uuid.UUID]]]:
    for start in range(0, len(pairs), size):
        yield pairs[start : start + size]


class EntityPairProximityRepository(
    BaseSQLAlchemyRepository[
        EntityPairProximityDB,
        EntityPairProximityCreate,
        EntityPairProximityCreate,
        uuid.UUID,
    ]
):
    """Instance + rollup writes/reads, scoped recompute, and run tracking."""

    def __init__(self) -> None:
        super().__init__(EntityPairProximityDB)

    async def get(
        self, session: AsyncSession, id: uuid.UUID
    ) -> EntityPairProximityDB | None:
        """Get one proximity instance by UUID primary key."""
        result = await session.execute(
            select(EntityPairProximityDB).where(EntityPairProximityDB.id == id)
        )
        return result.scalar_one_or_none()

    # ----- instance writes -------------------------------------------------

    async def insert_instances_for_scope(
        self,
        session: AsyncSession,
        *,
        support_min: int,
        outer_window: float,
        video_ids: Sequence[str] | None = None,
        entity_ids: Sequence[uuid.UUID] | None = None,
    ) -> int:
        """Compute + insert proximity instances in one INSERT…SELECT (the main path).

        The self-join (:func:`_instance_select`) runs entirely in the database;
        ``ON CONFLICT (instance key) DO NOTHING`` absorbs the duplicate rows that two
        mentions of one entity in the same segment would otherwise produce. Returns the
        number of instances inserted.
        """
        select_stmt = _instance_select(
            support_min=support_min,
            outer_window=outer_window,
            video_ids=video_ids,
            entity_ids=entity_ids,
        )
        insert_stmt = (
            pg_insert(EntityPairProximityDB)
            .from_select(_INSTANCE_INSERT_COLUMNS, select_stmt)
            .on_conflict_do_nothing(constraint="uq_entity_pair_proximity_instance")
        )
        result = await session.execute(insert_stmt)
        await session.flush()
        return result.rowcount or 0

    async def insert_instances(
        self,
        session: AsyncSession,
        *,
        instances: list[EntityPairProximityCreate],
    ) -> int:
        """Bulk-insert already-computed instances — the test/seed path, NOT production.

        The production computor path is :meth:`insert_instances_for_scope`
        (INSERT…SELECT, so the heavy join runs entirely in the database). This
        Python-object path exists only for tests and seeds that already hold
        :class:`EntityPairProximityCreate` rows (T016); ``ON CONFLICT (instance key)
        DO NOTHING`` absorbs duplicates.
        """
        if not instances:
            return 0
        total = 0
        for start in range(0, len(instances), _CHUNK_SIZE):
            chunk = instances[start : start + _CHUNK_SIZE]
            values = [{"id": uuid7(), **c.model_dump()} for c in chunk]
            stmt = pg_insert(EntityPairProximityDB).values(values)
            stmt = stmt.on_conflict_do_nothing(
                constraint="uq_entity_pair_proximity_instance"
            )
            result = await session.execute(stmt)
            total += result.rowcount or 0
        await session.flush()
        return total

    async def delete_all_instances(self, session: AsyncSession) -> int:
        """Delete every instance (full rebuild). Returns rows removed."""
        result = await session.execute(delete(EntityPairProximityDB))
        await session.flush()
        return result.rowcount or 0

    async def delete_instances_matching(
        self,
        session: AsyncSession,
        *,
        video_ids: Sequence[str] | None = None,
        entity_ids: Sequence[uuid.UUID] | None = None,
    ) -> int:
        """Delete instances matching the same scope the insert reinserts.

        Mirrors :func:`_instance_select`'s scope filters (``video_ids`` AND an
        endpoint in ``entity_ids``) so a scoped delete-then-reinsert leaves no stale
        rows and removes none it will not re-create. With neither filter it is a no-op
        (callers wanting a full wipe use :meth:`delete_all_instances`).
        """
        conds: list[ColumnElement[bool]] = []
        if video_ids:
            conds.append(EntityPairProximityDB.video_id.in_(list(video_ids)))
        if entity_ids:
            ids = list(entity_ids)
            conds.append(
                or_(
                    EntityPairProximityDB.entity_a_id.in_(ids),
                    EntityPairProximityDB.entity_b_id.in_(ids),
                )
            )
        if not conds:
            return 0
        result = await session.execute(delete(EntityPairProximityDB).where(*conds))
        await session.flush()
        return result.rowcount or 0

    async def read_rollup(
        self, session: AsyncSession, *, min_shared_videos: int = 5
    ) -> list[tuple[uuid.UUID, uuid.UUID, int, float]]:
        """Rollup pairs qualifying for transcript-candidate generation (Feature 116).

        Returns ``(entity_a_id, entity_b_id, shared_videos, min_gap_seconds)`` for every
        pair whose transcript shared-video count clears ``min_shared_videos`` (the FR-019
        support bound). ``shared_videos`` is the support quantity — the SAME unit the
        title/description channel uses, so cross-signal calibration (FR-011) is definable.
        ``close_co_mentions_*`` are NOT returned: they are display-time evidence (FR-022a),
        joined from the rollup at render, never the ranking key.
        """
        result = await session.execute(
            select(
                EntityPairProximityRollupDB.entity_a_id,
                EntityPairProximityRollupDB.entity_b_id,
                EntityPairProximityRollupDB.shared_videos,
                EntityPairProximityRollupDB.min_gap_seconds,
            ).where(EntityPairProximityRollupDB.shared_videos >= min_shared_videos)
        )
        return [(r[0], r[1], r[2], r[3]) for r in result.all()]

    async def pairs_in_scope(
        self,
        session: AsyncSession,
        *,
        video_ids: Sequence[str] | None = None,
        entity_ids: Sequence[uuid.UUID] | None = None,
    ) -> set[tuple[uuid.UUID, uuid.UUID]]:
        """Distinct pairs with at least one instance in the given scope.

        Used to capture a scoped recompute's affected pairs (before delete ∪ after
        insert) so their rollup is rebuilt even when the recompute drops a pair's last
        instance.
        """
        stmt = select(
            EntityPairProximityDB.entity_a_id, EntityPairProximityDB.entity_b_id
        ).distinct()
        conds: list[ColumnElement[bool]] = []
        if video_ids:
            conds.append(EntityPairProximityDB.video_id.in_(list(video_ids)))
        if entity_ids:
            ids = list(entity_ids)
            conds.append(
                or_(
                    EntityPairProximityDB.entity_a_id.in_(ids),
                    EntityPairProximityDB.entity_b_id.in_(ids),
                )
            )
        if conds:
            stmt = stmt.where(*conds)
        result = await session.execute(stmt)
        return {(row[0], row[1]) for row in result.all()}

    # ----- rollup (T008) ---------------------------------------------------

    async def rebuild_all_rollup(
        self, session: AsyncSession, *, windows: tuple[int, int, int]
    ) -> int:
        """Recompute the entire rollup table from the instances. Returns rows written."""
        await session.execute(delete(EntityPairProximityRollupDB))
        insert_stmt = pg_insert(EntityPairProximityRollupDB).from_select(
            _ROLLUP_INSERT_COLUMNS, _rollup_select(windows)
        )
        result = await session.execute(insert_stmt)
        await session.flush()
        return result.rowcount or 0

    async def rebuild_rollup_for_pairs(
        self,
        session: AsyncSession,
        *,
        pairs: Iterable[tuple[uuid.UUID, uuid.UUID]],
        windows: tuple[int, int, int],
    ) -> int:
        """Recompute the rollup for ``pairs`` only (scoped recompute).

        Delete-then-reinsert per pair chunk: a pair whose instances all disappeared is
        dropped from the rollup (its grouped select yields no row), never left stale.
        Returns the number of rollup rows written.
        """
        pair_list = sorted(set(pairs))
        if not pair_list:
            return 0
        total = 0
        for chunk in _chunked(pair_list, _CHUNK_SIZE):
            chunk_values = list(chunk)
            await session.execute(
                delete(EntityPairProximityRollupDB).where(
                    tuple_(
                        EntityPairProximityRollupDB.entity_a_id,
                        EntityPairProximityRollupDB.entity_b_id,
                    ).in_(chunk_values)
                )
            )
            pair_filter = tuple_(
                EntityPairProximityDB.entity_a_id,
                EntityPairProximityDB.entity_b_id,
            ).in_(chunk_values)
            insert_stmt = pg_insert(EntityPairProximityRollupDB).from_select(
                _ROLLUP_INSERT_COLUMNS,
                _rollup_select(windows, pair_filter=pair_filter),
            )
            result = await session.execute(insert_stmt)
            total += result.rowcount or 0
        await session.flush()
        return total

    # ----- run tracking ----------------------------------------------------

    async def start_run(
        self, session: AsyncSession, *, generator_version: str
    ) -> ProximityGenerationRunDB | None:
        """Insert a 'running' run, or None if one is already active (global lock).

        The partial unique index on ``status WHERE status='running'`` is the real
        guard; the insert is wrapped in a SAVEPOINT so a concurrent-run IntegrityError
        rolls back only this insert, leaving the transaction usable.
        """
        run = ProximityGenerationRunDB(
            status="running", generator_version=generator_version
        )
        try:
            async with session.begin_nested():
                session.add(run)
                await session.flush()
        except IntegrityError:
            return None
        await session.refresh(run)
        return run

    async def finish_run(
        self,
        session: AsyncSession,
        *,
        run_id: uuid.UUID,
        status: str,
        scopes_processed: int,
        instances_written: int,
        pairs_rolled_up: int,
    ) -> None:
        """Transition a run to a terminal status with its counts.

        Guarded by ``status='running'`` so a run already reaped is not resurrected.
        """
        await session.execute(
            update(ProximityGenerationRunDB)
            .where(
                ProximityGenerationRunDB.id == run_id,
                ProximityGenerationRunDB.status == "running",
            )
            .values(
                status=status,
                scopes_processed=scopes_processed,
                instances_written=instances_written,
                pairs_rolled_up=pairs_rolled_up,
                completed_at=datetime.now(UTC),
            )
        )
        await session.flush()

    # ----- dirty-scope queue (T009) ----------------------------------------

    async def mark_dirty(
        self,
        session: AsyncSession,
        *,
        video_id: str,
        language_code: str,
        reason: str | None = None,
    ) -> None:
        """Enqueue one ``(video, language)`` scope for recompute (dedupes).

        Upsert on the ``(video_id, language_code)`` primary key: a second mark of the
        same scope before it drains refreshes ``marked_at``/``reason`` rather than
        inserting a duplicate, so the queue holds at most one row per scope.
        """
        stmt = (
            pg_insert(ProximityDirtyScopeDB)
            .values(video_id=video_id, language_code=language_code, reason=reason)
            .on_conflict_do_update(
                index_elements=["video_id", "language_code"],
                set_={"marked_at": func.now(), "reason": reason},
            )
        )
        await session.execute(stmt)

    async def mark_dirty_all_languages(
        self,
        session: AsyncSession,
        *,
        video_id: str,
        reason: str | None = None,
    ) -> int:
        """Mark every transcript language of ``video_id`` dirty. Returns the count.

        Used by producers whose mutation is language-agnostic (e.g. an F091
        ``(entity, video)`` exclusion, which has no language column): one dirty row
        per ``video_transcripts.language_code`` the video carries. Reads
        ``video_transcripts`` (one row per video+language), NOT ``transcript_segments``
        (millions of rows) — the languages are the same set either way.
        """
        result = await session.execute(
            select(VideoTranscriptDB.language_code).where(
                VideoTranscriptDB.video_id == video_id
            )
        )
        languages = [row[0] for row in result.all()]
        for language_code in languages:
            await self.mark_dirty(
                session,
                video_id=video_id,
                language_code=language_code,
                reason=reason,
            )
        return len(languages)

    async def list_dirty_scopes(
        self, session: AsyncSession, *, limit: int | None = None
    ) -> list[ProximityDirtyScopeDB]:
        """The queued dirty scopes, oldest-marked first (optionally capped)."""
        stmt = select(ProximityDirtyScopeDB).order_by(ProximityDirtyScopeDB.marked_at)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def delete_dirty_scope(
        self,
        session: AsyncSession,
        *,
        video_id: str,
        language_code: str,
        before_marked_at: datetime | None = None,
    ) -> int:
        """Remove one drained scope from the queue. Returns rows removed.

        When ``before_marked_at`` is given the delete is conditional: the row is
        removed only if its ``marked_at`` is still ``<=`` that snapshot. A
        ``mark_dirty`` that re-queued the scope after the snapshot (e.g. during a
        drain's rebuild) bumps ``marked_at`` past it and is left in place rather than
        silently cleared.
        """
        conds: list[ColumnElement[bool]] = [
            ProximityDirtyScopeDB.video_id == video_id,
            ProximityDirtyScopeDB.language_code == language_code,
        ]
        if before_marked_at is not None:
            conds.append(ProximityDirtyScopeDB.marked_at <= before_marked_at)
        result = await session.execute(delete(ProximityDirtyScopeDB).where(*conds))
        await session.flush()
        return result.rowcount or 0
