"""
Entity-pair proximity repository (Features 116, 117).

Backs the transcript proximity primitive: the instance table
(``entity_pair_proximity``) is populated by an in-database INSERT…SELECT
self-join of ``entity_mentions`` (the compute lives in SQL, never pulled into
Python). Per-pair summaries are derived on read from those instances (Feature 117
dropped the stored rollup, which could drift after cascade deletes). Freshness is
tracked per ``(video_id, language_code)`` scope in ``proximity_scope_states``.

All data access for the computor lives here rather than in the service so the
repository pattern (Principle III) is not bypassed. The FR-016 language-scoping
invariant is expressed as :func:`language_scope_predicate` — a single, isolatable
clause the mutation-verified guard (T015) removes to prove the join fabricates
cross-language instances without it.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from typing import Any, NamedTuple, TypeVar

from sqlalchemy import (
    ColumnElement,
    Select,
    Update,
    Uuid,
    and_,
    case,
    column,
    delete,
    func,
    literal,
    or_,
    select,
    text,
    tuple_,
    union,
    update,
    values,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from sqlalchemy.orm import aliased
from uuid_utils import uuid7

from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import EntityPairProximity as EntityPairProximityDB
from chronovista.db.models import EntityVideoExclusion as EntityVideoExclusionDB
from chronovista.db.models import ProximityGenerationRun as ProximityGenerationRunDB
from chronovista.db.models import ProximityScopeState as ProximityScopeStateDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.entity_pair_proximity import (
    EntityPairProximityBase,
    EntityPairProximityCreate,
    PairProximitySummary,
    ProximityScopeState,
    ProximityScopeStatus,
    ScopeFilter,
)
from chronovista.repositories.base import BaseSQLAlchemyRepository
from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
    _folded,
    _visible_names_subquery,
    co_positioned_scopes,
    positioned_transcript_mention_qualifies,
)

# asyncpg rejects a statement with > 32,767 bind parameters. The Python-object
# insert (``insert_instances``, a test/seed path) binds ~8 params/row, so it chunks
# well under the ceiling. The compute path is INSERT...SELECT and binds nothing per row.
_CHUNK_SIZE = 1000

# Clearing a scope's failure bookkeeping, on publish, invalidation, retry and force.
_FAILURE_RESET: dict[str, Any] = {
    "attempts": 0,
    "failed_rule_version": None,
    "next_attempt_at": None,
    "last_error": None,
}

# Session-level advisory lock owned by a running ``proximity rebuild``. Held on a
# dedicated connection, so it is released by Postgres if the process dies.
PROXIMITY_REBUILD_LOCK_KEY = 1_170_001

# Each requested pair binds two parameters; asyncpg caps a statement at 32,767.
_PAIRS_PER_STATEMENT = 5_000


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


def _instance_select(
    *, outer_window: float, video_id: str, language_code: str
) -> Select[Any]:
    """The mention x mention proximity self-join for ONE ``(video, language)`` scope.

    One output row per close co-mention ``(pair, video, segment_a, segment_b)`` whose
    start times are within ``outer_window`` seconds (inclusive), with both
    F091-excluded endpoints removed. Each endpoint is qualified independently by the
    rule the evidence panel uses (``positioned_transcript_mention_qualifies``, with
    its own visible-names join), so proximity counts exactly the mentions a reviewer
    can open (FR-001..FR-003). There is NO eligibility gate (Feature 117, FR-006):
    every close pair in the scope is recorded, so a pair co-mentioned in a single
    video is measured. The segment ``start_time`` anchors cross-segment
    mentions (``segment_id`` is the start segment). ``gap_seconds`` is
    ``abs(start_a - start_b)``.
    """
    ma = aliased(EntityMentionDB, name="ma")
    mb = aliased(EntityMentionDB, name="mb")
    sa = aliased(TranscriptSegmentDB, name="sa")
    sb = aliased(TranscriptSegmentDB, name="sb")
    # Bound the visible names to the entities positioned in this scope. The join is
    # per entity, so this cannot change a match; unbounded, the whole name library
    # was folded and hashed twice per scope (measured: median 8 -> 58 ms).
    scope_entities = (
        select(EntityMentionDB.entity_id)
        .where(
            EntityMentionDB.video_id == video_id,
            EntityMentionDB.language_code == language_code,
            EntityMentionDB.mention_source == "transcript",
            EntityMentionDB.segment_id.is_not(None),
        )
        .distinct()
    )
    vna = _visible_names_subquery(scope_entities)
    vnb = _visible_names_subquery(scope_entities)

    gap = func.abs(sa.start_time - sb.start_time)

    return (
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
        # Segment joins match on id AND language, as the panel's do.
        .join(sa, and_(sa.id == ma.segment_id, sa.language_code == ma.language_code))
        .join(
            mb,
            (mb.video_id == ma.video_id) & (ma.entity_id < mb.entity_id),
        )
        .join(sb, and_(sb.id == mb.segment_id, sb.language_code == mb.language_code))
        .outerjoin(
            vna,
            and_(
                vna.c.entity_id == ma.entity_id,
                _folded(ma.mention_text) == vna.c.name_lower,
            ),
        )
        .outerjoin(
            vnb,
            and_(
                vnb.c.entity_id == mb.entity_id,
                _folded(mb.mention_text) == vnb.c.name_lower,
            ),
        )
        .where(
            ma.video_id == video_id,
            sa.language_code == language_code,
            positioned_transcript_mention_qualifies(ma, vna),
            positioned_transcript_mention_qualifies(mb, vnb),
            language_scope_predicate(sa, sb),  # FR-005: the isolatable invariant
            gap <= outer_window,
            ~_exclusion_exists(ma),
            ~_exclusion_exists(mb),
        )
    )


def _entity_scope_select(entity_id: uuid.UUID) -> Select[Any]:
    """Every ``(video_id, language_code)`` scope an entity touches.

    The union of scopes holding the entity's positioned transcript mentions and
    scopes whose stored records reference it, so a scope whose last mention of the
    entity was removed is still reachable (research R8). One SELECT per record
    endpoint, not an OR, so each side can use its own index.
    """
    mention_scopes = select(
        EntityMentionDB.video_id.label("video_id"),
        EntityMentionDB.language_code.label("language_code"),
    ).where(
        EntityMentionDB.entity_id == entity_id,
        EntityMentionDB.mention_source == "transcript",
        EntityMentionDB.segment_id.is_not(None),
        EntityMentionDB.language_code.is_not(None),
    )
    record_scopes_a = select(
        EntityPairProximityDB.video_id.label("video_id"),
        EntityPairProximityDB.language_code.label("language_code"),
    ).where(EntityPairProximityDB.entity_a_id == entity_id)
    record_scopes_b = select(
        EntityPairProximityDB.video_id.label("video_id"),
        EntityPairProximityDB.language_code.label("language_code"),
    ).where(EntityPairProximityDB.entity_b_id == entity_id)
    both = union(mention_scopes, record_scopes_a, record_scopes_b).subquery()
    return select(both.c.video_id, both.c.language_code)


def _is_current(rule_version: str) -> ColumnElement[bool]:
    """THE "this scope is current" predicate (data-model section 2); one home.

    Current: computed from the latest revision under ``rule_version``. Null-safe
    (``IS NOT DISTINCT FROM``), so a never-computed row (both computed columns NULL)
    is definitely NOT current; a plain equality would evaluate to unknown for it. Every
    freshness read (claim, counts, status, pair completeness) uses this, so they can
    never disagree about the same row; a fitness test pins it.
    """
    state = ProximityScopeStateDB
    return and_(
        state.computed_revision.is_not_distinct_from(state.revision),
        state.computed_rule_version.is_not_distinct_from(rule_version),
    )


def _is_failing(rule_version: str, threshold: int) -> ColumnElement[bool]:
    """THE "this scope is failing" predicate; one home (Features 117, 118).

    Not current, and failed under ``rule_version`` at least ``threshold`` times. What
    ``proximity status`` lists as failing and what the evidence panel reports as "could not be
    computed" are the same scopes because both read this; a fitness test pins its call sites.
    """
    state = ProximityScopeStateDB
    return and_(
        _not_current(rule_version),
        state.failed_rule_version == rule_version,
        state.attempts >= threshold,
    )


def _not_current(rule_version: str) -> ColumnElement[bool]:
    """Negation of :func:`_is_current` (both operands are null-safe, so NOT is too)."""
    return ~_is_current(rule_version)


_Stmt = TypeVar("_Stmt", Select[Any], Update)


def _apply_scope_filter(stmt: _Stmt, scope_filter: ScopeFilter | None) -> _Stmt:
    """Restrict a scope-state SELECT or UPDATE to a :class:`ScopeFilter` (None: all).

    The one interpretation of a filter against the state table, so a rebuild's
    lock pass and its update can never select different scopes.
    """
    if scope_filter is None:
        return stmt
    state = ProximityScopeStateDB
    if scope_filter.video_ids is not None:
        return stmt.where(state.video_id.in_(list(scope_filter.video_ids)))
    if scope_filter.entity_id is not None:
        scopes = _entity_scope_select(scope_filter.entity_id).subquery()
        return stmt.where(
            tuple_(state.video_id, state.language_code).in_(
                select(scopes.c.video_id, scopes.c.language_code)
            )
        )
    return stmt


class CoMentionRow(NamedTuple):
    """One co-mention of a pair within a window, with its time interval (Feature 118).

    In the canonical (lo, hi) orientation the records are stored in. ``end_time`` is the
    later of the two mentions' ends (FR-002).
    """

    video_id: str
    channel_id: str | None
    language_code: str
    segment_lo_id: int
    segment_hi_id: int
    gap_seconds: float
    start_time: float
    end_time: float


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


class EntityPairProximityRepository(
    BaseSQLAlchemyRepository[
        EntityPairProximityDB,
        EntityPairProximityCreate,
        EntityPairProximityCreate,
        uuid.UUID,
    ]
):
    """Per-scope record writes, derived reads, scope state, and run tracking."""

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

    # ----- per-scope records (Feature 117) ----------------------------------

    async def replace_scope_records(
        self,
        session: AsyncSession,
        *,
        video_id: str,
        language_code: str,
        outer_window: float,
    ) -> int:
        """Replace one scope's records wholesale, inside the caller's transaction.

        Deletes the scope's existing records, then recomputes them with one
        INSERT...SELECT (the self-join runs entirely in the database).
        ``ON CONFLICT (instance key) DO NOTHING`` absorbs the duplicate rows that two
        mentions of one entity in the same segment would otherwise produce. The caller
        publishes the scope state in the same transaction, so readers never see a
        partly replaced scope (FR-017). Returns the number of records written.
        """
        await session.execute(
            delete(EntityPairProximityDB).where(
                EntityPairProximityDB.video_id == video_id,
                EntityPairProximityDB.language_code == language_code,
            )
        )
        insert_stmt = (
            pg_insert(EntityPairProximityDB)
            .from_select(
                _INSTANCE_INSERT_COLUMNS,
                _instance_select(
                    outer_window=outer_window,
                    video_id=video_id,
                    language_code=language_code,
                ),
            )
            .on_conflict_do_nothing(constraint="uq_entity_pair_proximity_instance")
        )
        result = await session.execute(insert_stmt)
        return result.rowcount or 0

    async def count_scope_records(
        self,
        session: AsyncSession,
        *,
        video_id: str,
        language_code: str,
        outer_window: float,
    ) -> int:
        """How many records :meth:`replace_scope_records` WOULD write (no writes).

        Counts distinct record keys, matching the insert's ON CONFLICT de-duplication.
        Used by the non-publishing dry run.
        """
        computed = _instance_select(
            outer_window=outer_window, video_id=video_id, language_code=language_code
        ).subquery()
        keys = (
            select(
                computed.c.entity_a_id,
                computed.c.entity_b_id,
                computed.c.video_id,
                computed.c.segment_a_id,
                computed.c.segment_b_id,
            )
            .distinct()
            .subquery()
        )
        result = await session.execute(select(func.count()).select_from(keys))
        return int(result.scalar_one())

    async def insert_instances(
        self,
        session: AsyncSession,
        *,
        instances: list[EntityPairProximityCreate],
    ) -> int:
        """Bulk-insert already-computed instances — the test/seed path, NOT production.

        The production computor path is :meth:`replace_scope_records`
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

    async def scope_states(
        self,
        session: AsyncSession,
        *,
        video_ids: Collection[str],
        rule_version: str,
        failing_threshold: int,
    ) -> list[ProximityScopeState]:
        """Freshness of every transcript scope of ``video_ids`` (FR-019/FR-020).

        A transcript scope with no state row, or a row never computed, is
        ``not_computed``. ``current`` means computed from the latest revision under
        ``rule_version`` (possibly with zero records); otherwise ``stale``.
        """
        state = ProximityScopeStateDB
        rows = (
            await session.execute(
                select(
                    VideoTranscriptDB.video_id,
                    VideoTranscriptDB.language_code,
                    state,
                )
                .outerjoin(
                    state,
                    and_(
                        state.video_id == VideoTranscriptDB.video_id,
                        state.language_code == VideoTranscriptDB.language_code,
                    ),
                )
                .where(VideoTranscriptDB.video_id.in_(list(video_ids)))
                .order_by(VideoTranscriptDB.video_id, VideoTranscriptDB.language_code)
            )
        ).all()
        result: list[ProximityScopeState] = []
        for video_id, language_code, row in rows:
            if row is None:
                result.append(
                    ProximityScopeState(
                        video_id=video_id,
                        language_code=language_code,
                        state=ProximityScopeStatus.NOT_COMPUTED,
                        failing=False,
                        revision=None,
                    )
                )
                continue
            if row.computed_revision is None:
                status = ProximityScopeStatus.NOT_COMPUTED
            elif (
                row.computed_revision == row.revision
                and row.computed_rule_version == rule_version
            ):
                status = ProximityScopeStatus.CURRENT
            else:
                status = ProximityScopeStatus.STALE
            result.append(
                ProximityScopeState(
                    video_id=video_id,
                    language_code=language_code,
                    state=status,
                    failing=(
                        status is not ProximityScopeStatus.CURRENT
                        and row.failed_rule_version == rule_version
                        and row.attempts >= failing_threshold
                    ),
                    revision=row.revision,
                    computed_revision=row.computed_revision,
                    computed_rule_version=row.computed_rule_version,
                    computed_at=row.computed_at,
                    attempts=row.attempts,
                    next_attempt_at=row.next_attempt_at,
                    last_error=row.last_error,
                )
            )
        return result

    async def pair_summaries(
        self,
        session: AsyncSession,
        *,
        rule_version: str,
        pairs: Sequence[tuple[uuid.UUID, uuid.UUID]] | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> list[PairProximitySummary]:
        """Per-pair counts and completeness, from ONE statement (one snapshot).

        Either ``pairs`` (each returned even with zero records) or ``entity_id``
        (every pair with records involving it). ``videos_within_w`` counts distinct
        videos with a record at ``gap <= w``; ``segment_pairs_within_w`` counts the
        records themselves (mention density, not separate discussions, and parallel
        language transcripts add to it). ``complete`` is True only if every scope in
        the pair's contributing set is current: the scopes holding its records UNION
        the scopes where both entities have positioned transcript mentions. A scope
        with no state row is not current (research R12, data-model INV-5).

        The contributing set is deliberately a SUPERSET of the scopes that can
        produce records (it ignores qualification and exclusions), so the flag can
        only err toward False, never True. Such a scope is stale, so processing
        settles it; and it always has a state row, because positioned mentions and
        records hang off segments, which require a transcript row (bootstrap). Calls
        with more than ``_PAIRS_PER_STATEMENT`` pairs run one statement per chunk:
        each pair's counts and flag still come from a single snapshot.
        """
        if (pairs is None) == (entity_id is None):
            raise ValueError("pass exactly one of pairs or entity_id")
        if pairs is not None and len(pairs) > _PAIRS_PER_STATEMENT:
            ordered = sorted({(a, b) if a < b else (b, a) for a, b in pairs})
            chunks: list[PairProximitySummary] = []
            for start in range(0, len(ordered), _PAIRS_PER_STATEMENT):
                chunks += await self.pair_summaries(
                    session,
                    rule_version=rule_version,
                    pairs=ordered[start : start + _PAIRS_PER_STATEMENT],
                )
            return chunks
        rec = EntityPairProximityDB
        state = ProximityScopeStateDB
        if pairs is not None:
            canonical = sorted({(a, b) if a < b else (b, a) for a, b in pairs})
            if not canonical:
                return []
            given = values(
                column("entity_a_id", Uuid),
                column("entity_b_id", Uuid),
                name="given",
            ).data(canonical)
            requested = select(given.c.entity_a_id, given.c.entity_b_id).cte(
                "requested"
            )
        else:
            requested = (
                select(rec.entity_a_id, rec.entity_b_id)
                .where(or_(rec.entity_a_id == entity_id, rec.entity_b_id == entity_id))
                .distinct()
                .cte("requested")
            )
        req_a, req_b = requested.c.entity_a_id, requested.c.entity_b_id
        windows = (15, 30, 60, 120)
        not_settled = or_(state.video_id.is_(None), _not_current(rule_version))

        # Two-level aggregation, never row-per-record. Level 1 folds each
        # (pair, video): its closest gap, its windowed segment-pair counts, and
        # whether any of its record scopes is not current. Level 2 folds each pair:
        # a video is within w when its closest co-mention is, so videos_within_w is
        # count(*) FILTER (min_gap <= w), with no DISTINCT aggregate. Measured at
        # production scale, the single-level shape (four count(DISTINCT) aggregates
        # plus a per-record UNION) spilled past temp_file_limit for a hub entity in
        # about a quarter of all records.
        per_video = (
            select(
                rec.entity_a_id.label("a"),
                rec.entity_b_id.label("b"),
                func.min(rec.gap_seconds).label("min_gap"),
                *(
                    func.count().filter(rec.gap_seconds <= w).label(f"s{w}")
                    for w in windows
                ),
                func.bool_or(not_settled).label("unsettled"),
            )
            .join(requested, and_(rec.entity_a_id == req_a, rec.entity_b_id == req_b))
            .outerjoin(
                state,
                and_(
                    state.video_id == rec.video_id,
                    state.language_code == rec.language_code,
                ),
            )
            .group_by(rec.entity_a_id, rec.entity_b_id, rec.video_id)
            .cte("per_video")
        )
        counts = (
            select(
                per_video.c.a,
                per_video.c.b,
                *(
                    func.count().filter(per_video.c.min_gap <= w).label(f"v{w}")
                    for w in windows
                ),
                *(func.sum(per_video.c[f"s{w}"]).label(f"s{w}") for w in windows),
                func.min(per_video.c.min_gap).label("min_gap"),
                func.bool_or(per_video.c.unsettled).label("unsettled"),
            )
            .group_by(per_video.c.a, per_video.c.b)
            .cte("counts")
        )

        # Scopes where both entities have positioned mentions, even with no record:
        # only an UNSETTLED one can change the flag. Measured at production scale,
        # joining both entities' mentions first produced every co-present entity
        # combination among the requested entities (3.2M rows, sorted to disk) to keep
        # 62K. So each pair is driven from its side with FEWER scopes, its unsettled
        # scopes are taken first (materialized, so the planner cannot reorder it into
        # that product), and only then is the other entity probed on all three keys.
        present = (
            select(
                EntityMentionDB.entity_id.label("entity_id"),
                EntityMentionDB.video_id.label("video_id"),
                EntityMentionDB.language_code.label("language_code"),
                func.bool_or(not_settled).label("unsettled"),
            )
            .outerjoin(
                state,
                and_(
                    state.video_id == EntityMentionDB.video_id,
                    state.language_code == EntityMentionDB.language_code,
                ),
            )
            .where(
                EntityMentionDB.entity_id.in_(
                    select(req_a).union(select(req_b)).scalar_subquery()
                ),
                EntityMentionDB.mention_source == "transcript",
                EntityMentionDB.segment_id.is_not(None),
                EntityMentionDB.language_code.is_not(None),
            )
            .group_by(
                EntityMentionDB.entity_id,
                EntityMentionDB.video_id,
                EntityMentionDB.language_code,
            )
            .cte("present")
        )
        sizes = (
            select(present.c.entity_id, func.count().label("n"))
            .group_by(present.c.entity_id)
            .cte("sizes")
        )
        size_a, size_b = aliased(sizes, name="size_a"), aliased(sizes, name="size_b")
        a_drives = size_a.c.n <= size_b.c.n
        driven = (
            select(
                req_a.label("a"),
                req_b.label("b"),
                case((a_drives, req_a), else_=req_b).label("drive"),
                case((a_drives, req_b), else_=req_a).label("other"),
            )
            .select_from(requested)
            .join(size_a, size_a.c.entity_id == req_a)
            .join(size_b, size_b.c.entity_id == req_b)
            .cte("driven")
        )
        own = aliased(present, name="own")
        driving_unsettled = (
            select(
                driven.c.a,
                driven.c.b,
                driven.c.other,
                own.c.video_id,
                own.c.language_code,
            )
            .join(own, and_(own.c.entity_id == driven.c.drive, own.c.unsettled))
            .cte("driving_unsettled")
            .prefix_with("MATERIALIZED")
        )
        partner = aliased(present, name="partner")
        shared_scopes = (
            select(
                driving_unsettled.c.a,
                driving_unsettled.c.b,
                literal(True).label("unsettled"),
            )
            .join(
                partner,
                and_(
                    partner.c.entity_id == driving_unsettled.c.other,
                    partner.c.video_id == driving_unsettled.c.video_id,
                    partner.c.language_code == driving_unsettled.c.language_code,
                ),
            )
            .distinct()
            .cte("shared_scopes")
        )

        stmt = (
            select(
                req_a,
                req_b,
                *(func.coalesce(counts.c[f"v{w}"], 0) for w in windows),
                *(func.coalesce(counts.c[f"s{w}"], 0) for w in windows),
                counts.c.min_gap,
                or_(
                    func.coalesce(counts.c.unsettled, False),
                    func.coalesce(shared_scopes.c.unsettled, False),
                ),
            )
            .select_from(requested)
            .outerjoin(counts, and_(counts.c.a == req_a, counts.c.b == req_b))
            .outerjoin(
                shared_scopes,
                and_(shared_scopes.c.a == req_a, shared_scopes.c.b == req_b),
            )
            .order_by(req_a, req_b)
        )
        return [
            PairProximitySummary(
                entity_a_id=row[0],
                entity_b_id=row[1],
                videos_within_15=row[2],
                videos_within_30=row[3],
                videos_within_60=row[4],
                videos_within_120=row[5],
                segment_pairs_within_15=row[6],
                segment_pairs_within_30=row[7],
                segment_pairs_within_60=row[8],
                segment_pairs_within_120=row[9],
                min_gap_seconds=row[10],
                complete=not row[11],
            )
            for row in (await session.execute(stmt)).all()
        ]

    async def records_for_pair(
        self,
        session: AsyncSession,
        entity_a_id: uuid.UUID,
        entity_b_id: uuid.UUID,
        *,
        window_s: float,
    ) -> list[EntityPairProximityBase]:
        """The pair's traceable records within ``window_s`` (inclusive), closest first.

        Each names the video, the transcript language, both segments, and the gap, so
        a reviewer can open the exact passages.
        """
        a, b = sorted((entity_a_id, entity_b_id))
        rec = EntityPairProximityDB
        rows = (
            await session.execute(
                select(rec)
                .where(
                    rec.entity_a_id == a,
                    rec.entity_b_id == b,
                    rec.gap_seconds <= window_s,
                )
                .order_by(
                    rec.gap_seconds,
                    rec.video_id,
                    rec.language_code,
                    rec.segment_a_id,
                    rec.segment_b_id,
                )
            )
        ).scalars()
        return [
            EntityPairProximityBase.model_validate(row, from_attributes=True)
            for row in rows
        ]

    # ----- discussion passages (Feature 118) -------------------------------

    @staticmethod
    async def begin_read_snapshot(session: AsyncSession) -> None:
        """Make the session's transaction a read-only snapshot (REPEATABLE READ).

        MUST be the transaction's first statement. The passage panel reads in several statements
        while the proximity worker commits scope replacements; under the default READ COMMITTED a
        count from one statement could disagree with the rows of the next.
        """
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )

    async def name_list_segments(
        self, session: AsyncSession, *, segment_ids: Collection[int]
    ) -> set[int]:
        """The ``segment_ids`` that name three or more distinct qualifying entities (FR-018).

        Read from the measurement itself: every pair of entities with qualifying mentions in one
        segment has a record with ``segment_a_id = segment_b_id`` there, so the distinct entities
        across those records are exactly the segment's qualifying entities (the pair included).
        A reading aid only: it never filters or discounts anything.
        """
        if not segment_ids:
            return set()
        rec = EntityPairProximityDB
        same_segment = (
            rec.segment_a_id == rec.segment_b_id,
            rec.segment_a_id.in_(list(segment_ids)),
        )
        entities = union(
            select(
                rec.segment_a_id.label("segment_id"), rec.entity_a_id.label("entity_id")
            ).where(*same_segment),
            select(
                rec.segment_a_id.label("segment_id"), rec.entity_b_id.label("entity_id")
            ).where(*same_segment),
        ).subquery("segment_entities")
        rows = await session.execute(
            select(entities.c.segment_id)
            .group_by(entities.c.segment_id)
            .having(func.count() >= 3)
        )
        return {int(r.segment_id) for r in rows.all()}

    async def pair_scope_health(
        self,
        session: AsyncSession,
        *,
        entity_a: uuid.UUID,
        entity_b: uuid.UUID,
        rule_version: str,
        failing_threshold: int,
    ) -> tuple[int, list[tuple[str, str]]]:
        """``(pending, failed)`` among the transcripts a pair's evidence depends on (Feature 118).

        The contributing set is the one :meth:`pair_summaries` judges completeness by: the scopes
        holding the pair's records UNION the scopes where both entities have positioned transcript
        mentions (a deliberate superset, so the panel can only err toward "updating"). A scope is
        **failed** exactly when ``proximity status`` calls it failing: not current, failed under
        ``rule_version`` at least ``failing_threshold`` times. Every other scope that is not current,
        including one with no state row, is **pending**. Returns the pending count and the failed
        ``(video_id, language_code)`` scopes, ordered.
        """
        lo, hi = sorted((entity_a, entity_b))
        rec = EntityPairProximityDB
        state = ProximityScopeStateDB

        contributing = union(
            select(rec.video_id, rec.language_code).where(
                rec.entity_a_id == lo, rec.entity_b_id == hi
            ),
            co_positioned_scopes(lo, hi),
        ).subquery("contributing")
        failing = _is_failing(rule_version, failing_threshold)
        rows = (
            await session.execute(
                select(
                    contributing.c.video_id,
                    contributing.c.language_code,
                    func.coalesce(failing, False).label("failed"),
                )
                .outerjoin(
                    state,
                    and_(
                        state.video_id == contributing.c.video_id,
                        state.language_code == contributing.c.language_code,
                    ),
                )
                .where(or_(state.video_id.is_(None), _not_current(rule_version)))
                .order_by(contributing.c.video_id, contributing.c.language_code)
            )
        ).all()
        failed = [(r.video_id, r.language_code) for r in rows if r.failed]
        return len(rows) - len(failed), failed

    async def pair_comentions(
        self,
        session: AsyncSession,
        *,
        entity_a: uuid.UUID,
        entity_b: uuid.UUID,
        window_s: float,
    ) -> list[CoMentionRow]:
        """Every co-mention of a pair within ``window_s``, each with its interval (FR-002).

        One row per record ``gap_seconds <= window_s`` (inclusive) of the canonical pair, so the
        videos here are exactly the videos the measurement reports for this window (FR-008). The
        interval is ``[earlier start segment's start, later mention's end]``; a mention's end is its
        end segment's end when it spans segments. Ends come ONLY from
        :meth:`EntityMentionRepository._pair_qualifying_mentions`, so a mention the shared rule
        rejects cannot stretch an interval; a record whose segment has no qualifying mention (the
        library changed since the scope was measured, and the scope is now pending) is left out.

        Two set-based statements, joined in Python. Measured on production's densest pair (~58k
        records at 120 s): a single statement joining records to the qualifying mentions was planned
        against a one-row estimate of the visible-name join and ran up to 39 s; per-record
        correlated lookups took ~3.6 s; these two statements take ~0.9 s together.
        """
        lo, hi = sorted((entity_a, entity_b))
        rec = EntityPairProximityDB
        sa = aliased(TranscriptSegmentDB, name="sa")
        sb = aliased(TranscriptSegmentDB, name="sb")
        in_window = (
            rec.entity_a_id == lo,
            rec.entity_b_id == hi,
            rec.gap_seconds <= window_s,
        )
        records = (
            await session.execute(
                select(
                    rec.video_id,
                    VideoDB.channel_id,
                    rec.language_code,
                    rec.segment_a_id,
                    rec.segment_b_id,
                    rec.gap_seconds,
                    func.least(sa.start_time, sb.start_time).label("start_time"),
                )
                .join(sa, sa.id == rec.segment_a_id)
                .join(sb, sb.id == rec.segment_b_id)
                .join(VideoDB, VideoDB.video_id == rec.video_id)
                .where(*in_window)
            )
        ).all()
        if not records:
            return []
        segments = union(
            select(rec.segment_a_id).where(*in_window),
            select(rec.segment_b_id).where(*in_window),
        )
        qualifying = (
            EntityMentionRepository._pair_qualifying_mentions([lo, hi])
            .where(EntityMentionDB.segment_id.in_(segments))
            .subquery("pair_qualifying_mentions")
        )
        # A segment can hold several qualifying mentions of one entity: its end is the latest.
        ends: dict[tuple[uuid.UUID, int], float] = {
            (row.entity_id, row.segment_id): float(row.end_time)
            for row in (
                await session.execute(
                    select(
                        qualifying.c.entity_id,
                        qualifying.c.segment_id,
                        func.max(qualifying.c.end_time).label("end_time"),
                    ).group_by(qualifying.c.entity_id, qualifying.c.segment_id)
                )
            ).all()
        }
        rows: list[CoMentionRow] = []
        for r in records:
            end_lo = ends.get((lo, r.segment_a_id))
            end_hi = ends.get((hi, r.segment_b_id))
            if end_lo is None or end_hi is None:
                continue
            rows.append(
                CoMentionRow(
                    video_id=r.video_id,
                    channel_id=r.channel_id,
                    language_code=r.language_code,
                    segment_lo_id=int(r.segment_a_id),
                    segment_hi_id=int(r.segment_b_id),
                    gap_seconds=float(r.gap_seconds),
                    start_time=float(r.start_time),
                    end_time=max(end_lo, end_hi),
                )
            )
        return rows

    async def read_rollup(
        self, session: AsyncSession, *, min_shared_videos: int = 5
    ) -> list[tuple[uuid.UUID, uuid.UUID, int, float]]:
        """Pairs qualifying for transcript-candidate generation (Feature 116 queue).

        Returns ``(entity_a_id, entity_b_id, shared_videos, min_gap_seconds)`` for every
        pair whose transcript shared-video count clears ``min_shared_videos``.
        ``shared_videos`` is the number of distinct videos with at least one co-mention
        record (within the 120 s outer window) — the same meaning the Feature 116
        stored rollup had. Since Feature 117 it is derived on read from the records, so
        it can never drift from them (e.g. after a cascade delete).
        """
        shared = func.count(func.distinct(EntityPairProximityDB.video_id))
        result = await session.execute(
            select(
                EntityPairProximityDB.entity_a_id,
                EntityPairProximityDB.entity_b_id,
                shared,
                func.min(EntityPairProximityDB.gap_seconds),
            )
            .group_by(
                EntityPairProximityDB.entity_a_id, EntityPairProximityDB.entity_b_id
            )
            .having(shared >= min_shared_videos)
        )
        return [(r[0], r[1], r[2], r[3]) for r in result.all()]

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

    async def mark_abandoned_runs(self, session: AsyncSession) -> int:
        """Mark leftover ``running`` runs ``abandoned``.

        Call only while holding the rebuild lock: holding it proves no live rebuild
        exists, so any ``running`` row belongs to a process that died.
        """
        result = await session.execute(
            update(ProximityGenerationRunDB)
            .where(ProximityGenerationRunDB.status == "running")
            .values(status="abandoned", completed_at=datetime.now(UTC))
        )
        return result.rowcount or 0

    async def finish_run(
        self,
        session: AsyncSession,
        *,
        run_id: uuid.UUID,
        status: str,
        scopes_processed: int,
        instances_written: int,
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
                completed_at=datetime.now(UTC),
            )
        )
        await session.flush()

    # ----- rebuild ownership (Feature 117) -----------------------------------

    async def try_acquire_rebuild_lock(self, connection: AsyncConnection) -> bool:
        """Take the rebuild advisory lock on ``connection``; False if already held.

        Session-level: it outlives transactions on that connection and ends when the
        connection closes, including when the owning process is killed.
        """
        result = await connection.execute(
            select(func.pg_try_advisory_lock(PROXIMITY_REBUILD_LOCK_KEY))
        )
        await connection.commit()
        return bool(result.scalar_one())

    async def release_rebuild_lock(self, connection: AsyncConnection) -> bool:
        """Release the rebuild lock; False if this connection did not hold it."""
        result = await connection.execute(
            select(func.pg_advisory_unlock(PROXIMITY_REBUILD_LOCK_KEY))
        )
        await connection.commit()
        return bool(result.scalar_one())

    async def rebuild_lock_holder(self, session: AsyncSession) -> int | None:
        """Backend pid of the process holding the rebuild lock, if any."""
        result = await session.execute(
            text(
                "SELECT pid FROM pg_locks WHERE locktype = 'advisory' AND granted "
                "AND classid = 0 AND objid = :key AND objsubid = 1 "
                # pg_locks spans every database in the cluster (dev, integration,
                # demo share one server); only this database's rebuild counts.
                "AND database = (SELECT oid FROM pg_database "
                "WHERE datname = current_database())"
            ),
            {"key": PROXIMITY_REBUILD_LOCK_KEY},
        )
        pid: int | None = result.scalars().first()
        return pid

    async def force_invalidate_scopes(
        self, session: AsyncSession, *, scope_filter: ScopeFilter | None = None
    ) -> int:
        """Bump the revision of every state row in the filter and reset its failures.

        ``rebuild --force``: a deliberate full recompute. Locks rows in a sorted order
        so a concurrent producer cannot deadlock against it.
        """
        state = ProximityScopeStateDB
        keys = (
            _apply_scope_filter(
                select(state.video_id, state.language_code), scope_filter
            )
            .order_by(state.video_id, state.language_code)
            .with_for_update()
        )
        # Lock first, in sorted order, then update by the SAME predicate: binding the
        # locked keys would cost two bind parameters per scope and exceed the driver's
        # 32,767-parameter cap at about 16k scopes.
        if not (await session.execute(keys)).first():
            return 0
        result = await session.execute(
            _apply_scope_filter(update(state), scope_filter).values(
                revision=state.revision + 1,
                invalidated_at=func.now(),
                reason="force",
                **_FAILURE_RESET,
            )
        )
        return result.rowcount or 0

    async def reset_failures(
        self, session: AsyncSession, *, video_ids: Collection[str] | None = None
    ) -> int:
        """Clear failure state so failing scopes are claimable now (no revision bump)."""
        state = ProximityScopeStateDB
        stmt = (
            update(state)
            .where(or_(state.attempts > 0, state.failed_rule_version.is_not(None)))
            .values(**_FAILURE_RESET)
        )
        if video_ids is not None:
            stmt = stmt.where(state.video_id.in_(list(video_ids)))
        result = await session.execute(stmt)
        return result.rowcount or 0

    async def list_transcript_scopes(
        self,
        session: AsyncSession,
        *,
        scope_filter: ScopeFilter | None = None,
        limit: int | None = None,
    ) -> list[tuple[str, str]]:
        """``(video_id, language_code)`` scopes, from transcripts (videos) or from an
        entity's mention and record scopes, sorted; ``limit`` bounds a sample."""
        if scope_filter is not None and scope_filter.entity_id is not None:
            scopes = _entity_scope_select(scope_filter.entity_id).subquery()
            stmt = select(scopes.c.video_id, scopes.c.language_code).order_by(
                scopes.c.video_id, scopes.c.language_code
            )
        else:
            stmt = select(
                VideoTranscriptDB.video_id, VideoTranscriptDB.language_code
            ).order_by(VideoTranscriptDB.video_id, VideoTranscriptDB.language_code)
            if scope_filter is not None and scope_filter.video_ids is not None:
                stmt = stmt.where(
                    VideoTranscriptDB.video_id.in_(list(scope_filter.video_ids))
                )
        if limit is not None:
            stmt = stmt.limit(limit)
        return [(row[0], row[1]) for row in (await session.execute(stmt)).all()]

    async def state_counts(
        self, session: AsyncSession, *, rule_version: str
    ) -> tuple[int, int, int, datetime | None]:
        """``(not_computed, current, stale, oldest_not_current_at)`` over all scopes.

        A transcript scope with no state row yet counts as not computed.
        """
        state = ProximityScopeStateDB
        current = _is_current(rule_version)
        row = (
            await session.execute(
                select(
                    func.count().filter(state.computed_revision.is_(None)),
                    func.count().filter(current),
                    func.count().filter(
                        and_(state.computed_revision.is_not(None), ~current)
                    ),
                    func.min(state.invalidated_at).filter(~current),
                )
            )
        ).one()
        missing = (
            await session.execute(
                select(func.count())
                .select_from(VideoTranscriptDB)
                .outerjoin(
                    state,
                    and_(
                        state.video_id == VideoTranscriptDB.video_id,
                        state.language_code == VideoTranscriptDB.language_code,
                    ),
                )
                .where(state.video_id.is_(None))
            )
        ).scalar_one()
        return int(row[0]) + int(missing), int(row[1]), int(row[2]), row[3]

    async def list_failing(
        self,
        session: AsyncSession,
        *,
        rule_version: str,
        threshold: int,
        limit: int,
    ) -> list[ProximityScopeStateDB]:
        """Failing scopes, most attempts first."""
        state = ProximityScopeStateDB
        stmt = (
            select(state)
            .where(_is_failing(rule_version, threshold))
            .order_by(state.attempts.desc(), state.video_id, state.language_code)
            .limit(limit)
        )
        return list((await session.execute(stmt)).scalars().all())

    # ----- scope processing (Feature 117) -----------------------------------

    async def claim_next_scope(
        self,
        session: AsyncSession,
        *,
        rule_version: str,
        scope_filter: ScopeFilter | None = None,
        exclude: Collection[tuple[str, str]] = (),
        key: tuple[str, str] | None = None,
    ) -> ProximityScopeStateDB | None:
        """Lock and return one claimable scope, or None if none is claimable now.

        Claimable: not current (null-safe), and either never failed, past its
        retry time, or failed only under an older rule version. The row lock
        (``FOR UPDATE SKIP LOCKED``) is held until the caller's transaction ends, so
        concurrent processors never claim the same scope, a producer's invalidation of
        a claimed scope waits for the publish, and a scope still locked by an
        in-flight producer is skipped rather than computed from uncommitted data.
        ``exclude`` lists scopes this caller already attempted, so one call never
        re-claims a scope that just failed. ``key`` restricts the claim to one scope
        (a prompt retry after lock contention re-claims the same scope).
        """
        state = ProximityScopeStateDB
        due = or_(
            state.next_attempt_at.is_(None),
            state.next_attempt_at <= func.now(),
            and_(
                state.failed_rule_version.is_not(None),
                state.failed_rule_version != rule_version,
            ),
        )
        stmt = select(state).where(_not_current(rule_version), due)
        stmt = _apply_scope_filter(stmt, scope_filter)
        if key is not None:
            stmt = stmt.where(state.video_id == key[0], state.language_code == key[1])
        if exclude:
            stmt = stmt.where(
                tuple_(state.video_id, state.language_code).not_in(list(exclude))
            )
        stmt = (
            stmt.order_by(
                state.attempts,
                state.invalidated_at,
                state.video_id,
                state.language_code,
            )
            .limit(1)
            .with_for_update(skip_locked=True)
            # FOR UPDATE does not refresh an object already in the identity map;
            # the caller must see the LOCKED row's revision, not a cached one.
            .execution_options(populate_existing=True)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def publish_scope(
        self,
        session: AsyncSession,
        *,
        video_id: str,
        language_code: str,
        revision: int,
        rule_version: str,
    ) -> bool:
        """Mark a scope current as of ``revision`` and clear its failure bookkeeping.

        Called in the same transaction as :meth:`replace_scope_records`. Guarded by
        ``revision`` so a publish can never apply to a revision other than the one
        that was computed. Returns False when the guard matched nothing (the scope
        then stays stale and is recomputed later).
        """
        state = ProximityScopeStateDB
        result = await session.execute(
            update(state)
            .where(
                state.video_id == video_id,
                state.language_code == language_code,
                state.revision == revision,
            )
            .values(
                computed_revision=revision,
                computed_rule_version=rule_version,
                computed_at=func.now(),
                **_FAILURE_RESET,
            )
        )
        return bool(result.rowcount)

    async def record_scope_failure(
        self,
        session: AsyncSession,
        *,
        video_id: str,
        language_code: str,
        attempted_revision: int,
        rule_version: str,
        error: str,
    ) -> bool:
        """Record a failed computation of ``attempted_revision`` (data-model section 2).

        Runs in its own transaction after the scope's transaction rolled back. The
        new attempt number ``n`` restarts at 1 when the earlier failures were under
        another rule version; the retry waits ``30 s * 2^(n-1)``, capped at 1 h. The
        update is guarded by revision and is null-safe: it no-ops if the scope was
        invalidated again or recomputed successfully meanwhile, and it does apply to a
        never-computed scope. Returns whether it applied.
        """
        state = ProximityScopeStateDB
        attempt = case(
            (
                state.failed_rule_version.is_not_distinct_from(rule_version),
                state.attempts + 1,
            ),
            else_=1,
        )
        backoff = func.least(
            text("interval '30 seconds'") * func.power(2, attempt - 1),
            text("interval '1 hour'"),
        )
        result = await session.execute(
            update(state)
            .where(
                state.video_id == video_id,
                state.language_code == language_code,
                state.revision == attempted_revision,
                _not_current(rule_version),
            )
            .values(
                attempts=attempt,
                failed_rule_version=rule_version,
                next_attempt_at=func.now() + backoff,
                last_error=error[:500],
            )
        )
        return bool(result.rowcount)

    async def defer_scope(
        self,
        session: AsyncSession,
        *,
        video_id: str,
        language_code: str,
        attempted_revision: int,
        seconds: float,
    ) -> bool:
        """Skip a contended scope for ``seconds`` without counting an attempt.

        Lock contention is not a computation failure, so ``attempts`` is unchanged.
        Revision-guarded like :meth:`record_scope_failure`.
        """
        state = ProximityScopeStateDB
        result = await session.execute(
            update(state)
            .where(
                state.video_id == video_id,
                state.language_code == language_code,
                state.revision == attempted_revision,
            )
            .values(
                next_attempt_at=func.now()
                + func.make_interval(0, 0, 0, 0, 0, 0, seconds)
            )
        )
        return bool(result.rowcount)

    async def count_failing(
        self,
        session: AsyncSession,
        *,
        rule_version: str,
        threshold: int,
        scope_filter: ScopeFilter | None = None,
    ) -> int:
        """Not-current scopes with at least ``threshold`` failures under ``rule_version``."""
        state = ProximityScopeStateDB
        stmt = (
            select(func.count())
            .select_from(state)
            .where(_is_failing(rule_version, threshold))
        )
        result = await session.execute(_apply_scope_filter(stmt, scope_filter))
        return int(result.scalar_one())

    async def count_waiting_to_retry(
        self,
        session: AsyncSession,
        *,
        rule_version: str,
        scope_filter: ScopeFilter | None = None,
    ) -> int:
        """Not-current scopes in a backoff or deferral window (retried automatically)."""
        state = ProximityScopeStateDB
        stmt = (
            select(func.count())
            .select_from(state)
            .where(_not_current(rule_version), state.next_attempt_at > func.now())
        )
        result = await session.execute(_apply_scope_filter(stmt, scope_filter))
        return int(result.scalar_one())

    async def count_lockable_unsettled(
        self,
        session: AsyncSession,
        *,
        rule_version: str,
        scope_filter: ScopeFilter | None = None,
    ) -> int:
        """Not-current scopes NOT row-locked by another transaction right now.

        ``count_unsettled`` minus this is the number held by another processor or
        producer. The locks taken here are released when the caller's transaction
        ends; keep that transaction short.
        """
        state = ProximityScopeStateDB
        stmt = _apply_scope_filter(
            select(state.video_id).where(_not_current(rule_version)), scope_filter
        ).with_for_update(skip_locked=True)
        result = await session.execute(stmt)
        return len(result.all())

    async def bootstrap_scope_states(self, session: AsyncSession) -> int:
        """Insert a not-computed state row for every transcript scope that lacks one.

        Scopes are ``video_transcripts`` ``(video_id, language_code)`` pairs.
        Existing rows are left untouched (``ON CONFLICT DO NOTHING``), so this is safe
        to run on every worker start and periodically. Returns the rows inserted.
        """
        stmt = (
            pg_insert(ProximityScopeStateDB)
            .from_select(
                ["video_id", "language_code", "reason"],
                select(
                    VideoTranscriptDB.video_id,
                    VideoTranscriptDB.language_code,
                    literal("bootstrap"),
                ),
            )
            .on_conflict_do_nothing(index_elements=["video_id", "language_code"])
        )
        result = await session.execute(stmt)
        return result.rowcount or 0

    async def count_unsettled(
        self,
        session: AsyncSession,
        *,
        rule_version: str,
        scope_filter: ScopeFilter | None = None,
    ) -> int:
        """Number of scope-state rows in the filtered set that are not current."""
        stmt = (
            select(func.count())
            .select_from(ProximityScopeStateDB)
            .where(_not_current(rule_version))
        )
        stmt = _apply_scope_filter(stmt, scope_filter)
        result = await session.execute(stmt)
        return int(result.scalar_one())

    # ----- scope invalidation (Feature 117) --------------------------------

    async def invalidate_proximity_scopes(
        self,
        session: AsyncSession,
        *,
        reason: str,
        video_id: str | None = None,
        language_code: str | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> int:
        """Mark proximity scopes stale inside the caller's transaction (FR-010).

        The ONE invalidation operation. Every producer that changes which positioned
        transcript mentions qualify calls it in the SAME transaction as its change, so
        a committed change can never lack its invalidation. It never commits.

        Scope selection (exactly one of ``video_id`` / ``entity_id``):

        - ``video_id`` + ``language_code``: that one scope.
        - ``video_id`` alone: every ``video_transcripts`` language of the video.
        - ``entity_id``: every scope where the entity has positioned transcript
          mentions, UNION every scope whose stored records reference it, so removing
          an entity's last mention still reaches the stale evidence it left.

        Each affected row is upserted (``revision = 1`` when new, else ``revision + 1``)
        with its failure bookkeeping reset, in ``(video_id, language_code)`` order so
        concurrent multi-scope invalidations acquire row locks consistently.

        Forward contract (FR-014): any future operation that alters qualifying
        mentions (including the fix for issue #420 and any future entity merge) MUST
        call this.

        Returns the number of scopes affected.
        """
        if (video_id is None) == (entity_id is None):
            raise ValueError("pass exactly one of video_id or entity_id")
        if language_code is not None and video_id is None:
            raise ValueError("language_code requires video_id")

        scopes: Select[Any]
        if video_id is not None and language_code is not None:
            scopes = select(
                literal(video_id).label("video_id"),
                literal(language_code).label("language_code"),
            )
        elif video_id is not None:
            scopes = select(
                VideoTranscriptDB.video_id.label("video_id"),
                VideoTranscriptDB.language_code.label("language_code"),
            ).where(VideoTranscriptDB.video_id == video_id)
        else:
            assert entity_id is not None
            scopes = _entity_scope_select(entity_id)

        ordered = scopes.subquery()
        source = select(
            ordered.c.video_id, ordered.c.language_code, literal(reason)
        ).order_by(ordered.c.video_id, ordered.c.language_code)
        stmt = pg_insert(ProximityScopeStateDB).from_select(
            ["video_id", "language_code", "reason"], source
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["video_id", "language_code"],
            set_={
                "revision": ProximityScopeStateDB.revision + 1,
                "invalidated_at": func.now(),
                "reason": stmt.excluded.reason,
                **_FAILURE_RESET,
            },
        )
        # A Core statement executes immediately; no flush is needed (and none is
        # done, so producers keep the exact session behavior they had before).
        result = await session.execute(stmt)
        return result.rowcount or 0
