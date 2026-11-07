"""
Relationship-candidate repository (Feature 107).

Backs the novel-relationship queue: an idempotent bulk upsert on the canonical
pair key that refreshes metric fields on re-generation and never touches a verdict
(mirroring the candidate-suggestion queue), the lift-ranked read, a stale-row
reconciliation for pairs that no longer qualify, and the two bulk read-helpers the
generator needs (channel co-occurrence inputs + entity property rows).

All reads are async; data access for the generator lives here rather than in a
service so the repository pattern (Principle III) is not bypassed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity
from chronovista.db.models import RelationshipCandidate as RelationshipCandidateDB
from chronovista.db.models import (
    RelationshipCandidateGenerationRun as RelationshipCandidateGenerationRunDB,
)
from chronovista.models.relationship_candidate import (
    RelationshipCandidateCreate,
    RelationshipCandidateUpdate,
)
from chronovista.repositories.base import BaseSQLAlchemyRepository

# Metric fields refreshed in place when a generation re-run re-emits a pair.
# Identity (entity ids), verdict fields, and created_at are deliberately excluded.
_REFRESHABLE_FIELDS = (
    "channel",
    "shared_video_count",
    "lift",
    "entity_a_video_count",
    "entity_b_video_count",
    "channel_video_universe",
    "both_typed_eligible",
    "kb_corroboration_count",
    "kb_corroboration_detail",
    "provenance",
)

# asyncpg rejects a statement with > 32,767 bind parameters. Each candidate row
# binds ~14 params (12 create fields + last_generated_at + the uuid7 id default),
# so a single multi-row INSERT breaks at ~2,340 rows — and the generator emits
# thousands. Chunk well under that ceiling.
_UPSERT_CHUNK_SIZE = 1000


class RelationshipCandidateRepository(
    BaseSQLAlchemyRepository[
        RelationshipCandidateDB,
        RelationshipCandidateCreate,
        RelationshipCandidateUpdate,
        uuid.UUID,
    ]
):
    """CRUD + lift-ranked read + idempotent reconciliation for relationship candidates."""

    def __init__(self) -> None:
        super().__init__(RelationshipCandidateDB)

    async def get(
        self, session: AsyncSession, id: uuid.UUID
    ) -> RelationshipCandidateDB | None:
        """Get a relationship candidate by UUID primary key."""
        result = await session.execute(
            select(RelationshipCandidateDB).where(RelationshipCandidateDB.id == id)
        )
        return result.scalar_one_or_none()

    async def upsert_many(
        self,
        session: AsyncSession,
        *,
        candidates: list[RelationshipCandidateCreate],
    ) -> int:
        """Bulk insert/refresh candidates on the canonical pair key.

        ``INSERT ... ON CONFLICT (entity_a_id, entity_b_id) DO UPDATE ... WHERE
        review_status IS NULL`` — a re-run refreshes an unverdicted pair's metrics
        in place (preserving its row identity, so a future verdict survives
        regeneration) and never overwrites a verdicted row. Returns the number of
        distinct pairs upserted.

        The input is deduplicated by canonical pair (last wins) before insert, so
        ON CONFLICT never tries to affect the same row twice in one statement, and
        the insert is chunked under asyncpg's bind-parameter ceiling
        (``_UPSERT_CHUNK_SIZE``) so a multi-thousand-row generation does not exceed it.
        """
        if not candidates:
            return 0

        # Dedupe by canonical pair: a repeated (a, b) in one statement raises
        # "ON CONFLICT DO UPDATE command cannot affect row a second time".
        by_pair: dict[tuple[uuid.UUID, uuid.UUID], RelationshipCandidateCreate] = {
            (c.entity_a_id, c.entity_b_id): c for c in candidates
        }
        deduped = list(by_pair.values())

        now = datetime.now(UTC)
        for start in range(0, len(deduped), _UPSERT_CHUNK_SIZE):
            chunk = deduped[start : start + _UPSERT_CHUNK_SIZE]
            values = [{**c.model_dump(), "last_generated_at": now} for c in chunk]
            insert_stmt = pg_insert(RelationshipCandidateDB).values(values)
            refresh_set: dict[str, Any] = {
                field: insert_stmt.excluded[field] for field in _REFRESHABLE_FIELDS
            }
            refresh_set["last_generated_at"] = insert_stmt.excluded.last_generated_at
            refresh_set["updated_at"] = now
            stmt = insert_stmt.on_conflict_do_update(
                index_elements=["entity_a_id", "entity_b_id"],
                set_=refresh_set,
                where=RelationshipCandidateDB.review_status.is_(None),
            )
            await session.execute(stmt)
        await session.flush()
        return len(deduped)

    async def list_ranked(
        self,
        session: AsyncSession,
        *,
        eligible_only: bool = False,
        min_support: int = 5,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[RelationshipCandidateDB], int]:
        """Return a page of candidates ranked by lift (strongest first) + total count.

        ``min_support`` only filters rows (never below the qualifying floor of 5); it
        is never used to re-floor the ranking, which is always ``lift DESC`` (then a
        stable tiebreak). ``eligible_only`` restricts to the measured-precision
        population without changing the ordering.
        """
        filters = [RelationshipCandidateDB.shared_video_count >= max(min_support, 5)]
        if eligible_only:
            filters.append(RelationshipCandidateDB.both_typed_eligible.is_(True))

        total_result = await session.execute(
            select(func.count()).select_from(RelationshipCandidateDB).where(*filters)
        )
        total = total_result.scalar() or 0

        stmt = (
            select(RelationshipCandidateDB)
            .where(*filters)
            .order_by(
                RelationshipCandidateDB.lift.desc(),
                RelationshipCandidateDB.shared_video_count.desc(),
                RelationshipCandidateDB.id,
            )
            .offset(skip)
            .limit(limit)
            # A bulk Core upsert does not sync cached ORM instances; force the read
            # to reflect committed DB state so a same-session read-after-upsert
            # (and the generator's own re-reads) never return stale metrics.
            .execution_options(populate_existing=True)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    async def delete_stale(
        self, session: AsyncSession, *, run_started_at: datetime
    ) -> int:
        """Delete unverdicted pairs not re-emitted by the current run (delete-if-absent).

        A pair re-emitted this run has ``last_generated_at >= run_started_at``; one
        that no longer qualifies keeps its older timestamp and is removed. Verdicted
        rows (``review_status`` set) are never deleted here — the MVP writes no
        verdicts, so this deletes unverdicted stale pairs only. (A future
        mark-no-longer-qualifying transition for verdicted rows is NOT implemented
        yet; it would be added when confirm/reject ships.) Returns rows removed.

        Caller contract: capture ``run_started_at`` BEFORE the first upsert, and
        only call this after a non-empty generation — on an empty/degraded read the
        caller must skip reconciliation or it would wipe every unverdicted row.
        """
        stmt = delete(RelationshipCandidateDB).where(
            RelationshipCandidateDB.last_generated_at < run_started_at,
            RelationshipCandidateDB.review_status.is_(None),
        )
        result = await session.execute(stmt)
        await session.flush()
        return result.rowcount or 0

    async def fetch_cooccurrence_inputs(
        self, session: AsyncSession, *, sources: tuple[str, ...]
    ) -> list[tuple[uuid.UUID, str]]:
        """All ``(entity_id, video_id)`` mention rows on the given channel sources.

        The generator builds the all-pairs co-occurrence graph from these. Scoped to
        ``mention_source IN sources`` (e.g. ``("title", "description")``) and
        ``DISTINCT`` so multiple hits of one entity in one video's title/description
        collapse to a single ``(entity_id, video_id)`` pair — the co-occurrence
        metric is over distinct videos, and distinct also shrinks the result.

        Note: no ``entity_video_exclusion`` (Feature 091 manual unlink) filter is
        applied — the precision calibration was measured on unexcluded title/
        description mentions, so excluding here would diverge the queue from the
        calibrated set. Revisit if confirm/reject later wants exclusions honoured.
        """
        result = await session.execute(
            select(EntityMentionDB.entity_id, EntityMentionDB.video_id)
            .where(EntityMentionDB.mention_source.in_(sources))
            .distinct()
        )
        return [(row[0], row[1]) for row in result.all()]

    async def fetch_entity_property_rows(
        self, session: AsyncSession
    ) -> list[tuple[uuid.UUID, dict[str, Any], dict[str, Any]]]:
        """All entities as ``(id, external_ids, properties)`` for the novelty filter.

        The generator derives each entity's QID (``external_ids['wikidata']['id']``)
        and its captured relation/attribute targets (``properties[field]['qids']``)
        from these rows to build the direct-edge, co-membership, and attribute arms.
        """
        result = await session.execute(
            select(NamedEntity.id, NamedEntity.external_ids, NamedEntity.properties)
        )
        return [(row[0], row[1] or {}, row[2] or {}) for row in result.all()]

    async def fetch_entity_summaries(
        self, session: AsyncSession, *, ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[str, str]]:
        """Map ``entity_id -> (canonical_name, entity_type)`` for display/navigation.

        Batched for the ids on one page of the queue, so the read-only list endpoint
        resolves both ends of each pair in a single query (no N+1).
        """
        if not ids:
            return {}
        result = await session.execute(
            select(
                NamedEntity.id, NamedEntity.canonical_name, NamedEntity.entity_type
            ).where(NamedEntity.id.in_(ids))
        )
        return {row[0]: (row[1], row[2]) for row in result.all()}

    async def latest_generated_at(self, session: AsyncSession) -> datetime | None:
        """The most recent generation time across candidates, or None if empty.

        Lets the read endpoint report how current the queue is.
        """
        result = await session.execute(
            select(func.max(RelationshipCandidateDB.last_generated_at))
        )
        return result.scalar_one_or_none()

    async def start_run(
        self, session: AsyncSession, *, channel: str, generator_version: str
    ) -> RelationshipCandidateGenerationRunDB | None:
        """Insert a 'running' generation run, or return None if one is already active.

        The partial unique index on ``channel WHERE status='running'`` is the real
        concurrency guard; the insert is wrapped in a SAVEPOINT so a concurrent-run
        IntegrityError rolls back only this insert, leaving the transaction usable.
        """
        run = RelationshipCandidateGenerationRunDB(
            channel=channel, status="running", generator_version=generator_version
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
        channel_video_universe: int,
        corpus_size: int,
        candidates_written: int,
        candidates_removed: int,
    ) -> None:
        """Transition a run to a terminal status with its result counts.

        Guarded by ``status='running'`` so a run already reaped is not resurrected.
        """
        await session.execute(
            update(RelationshipCandidateGenerationRunDB)
            .where(
                RelationshipCandidateGenerationRunDB.id == run_id,
                RelationshipCandidateGenerationRunDB.status == "running",
            )
            .values(
                status=status,
                channel_video_universe=channel_video_universe,
                corpus_size=corpus_size,
                candidates_written=candidates_written,
                candidates_removed=candidates_removed,
                completed_at=datetime.now(UTC),
            )
        )
        await session.flush()
