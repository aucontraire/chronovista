"""
Candidate suggestion repository for seed-and-grow entity discovery (Feature 096).

Backs the durable candidate queue: idempotent upsert on re-generation (refresh
pending rows only, never terminal ones), the ranked pending read, verdict
transitions, status/triage counts, and reconciliation of candidates whose
identity became a library entity by other means.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ARRAY, String, bindparam, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import CandidateSuggestion as CandidateSuggestionDB
from chronovista.models.candidate_suggestion import (
    CandidateSuggestionCreate,
    CandidateSuggestionUpdate,
    RelationCandidateRow,
)
from chronovista.models.enums import ReviewStatus, TriageCategory
from chronovista.repositories.base import BaseSQLAlchemyRepository

# Signals a generation re-run refreshes on a still-pending candidate (FR-014).
# Verdict fields and identity keys are deliberately excluded.
_REFRESHABLE_FIELDS = (
    "label",
    "label_normalized",
    "type_hint",
    "token_count",
    "corroboration_count",
    "dangling_edge_count",
    "salience",
    "score",
    "triage",
    "provenance",
    "possible_duplicate_of_id",
)

_SORT_COLUMNS = {
    "score": CandidateSuggestionDB.score,
    "corroboration": CandidateSuggestionDB.corroboration_count,
    "salience": CandidateSuggestionDB.salience,
}

# (str, Enum) fields are written as their ``.value`` string rather than relying on
# the str-subclass identity (which ``repr``s as ``'SourceChannel.RELATION'`` on
# Python 3.11+), so the raw-SQL upsert path is driver-independent.
_ENUM_FIELDS = ("source_channel", "type_hint", "triage", "review_status")


def _candidate_row_values(candidate: CandidateSuggestionCreate) -> dict[str, Any]:
    """Serialize a create model to column values, enums as their ``.value`` strings."""
    data = candidate.model_dump()
    for field in _ENUM_FIELDS:
        value = data[field]
        data[field] = value.value if hasattr(value, "value") else value
    return data


class CandidateSuggestionRepository(
    BaseSQLAlchemyRepository[
        CandidateSuggestionDB,
        CandidateSuggestionCreate,
        CandidateSuggestionUpdate,
        uuid.UUID,
    ]
):
    """Repository for candidate suggestion CRUD and the review lifecycle."""

    def __init__(self) -> None:
        """Initialize repository with the CandidateSuggestion model."""
        super().__init__(CandidateSuggestionDB)

    async def get(
        self, session: AsyncSession, id: uuid.UUID
    ) -> CandidateSuggestionDB | None:
        """Get a candidate suggestion by UUID primary key."""
        result = await session.execute(
            select(CandidateSuggestionDB).where(CandidateSuggestionDB.id == id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, id: uuid.UUID) -> bool:
        """Check whether a candidate suggestion exists by UUID primary key."""
        result = await session.execute(
            select(CandidateSuggestionDB.id).where(CandidateSuggestionDB.id == id)
        )
        return result.first() is not None

    async def get_by_channel_qid(
        self, session: AsyncSession, *, source_channel: str, wikidata_qid: str
    ) -> CandidateSuggestionDB | None:
        """Return the candidate for ``(source_channel, wikidata_qid)`` or ``None``.

        The pair is unique (``uq_candidate_channel_qid``), so this yields zero or
        one row — ``scalar_one_or_none`` is safe.
        """
        result = await session.execute(
            select(CandidateSuggestionDB).where(
                CandidateSuggestionDB.source_channel == source_channel,
                CandidateSuggestionDB.wikidata_qid == wikidata_qid,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_generated(
        self, session: AsyncSession, *, candidate: CandidateSuggestionCreate
    ) -> CandidateSuggestionDB:
        """Insert a new candidate, or refresh an existing **pending** one (FR-014).

        - Absent ``(source_channel, wikidata_qid)`` → insert a new pending row.
        - Present and ``review_status == 'pending'`` → refresh the generation
          signals (``_REFRESHABLE_FIELDS``) and bump ``last_generated_at`` /
          ``updated_at``; verdict fields are never touched.
        - Present and terminal (approved/rejected/superseded) → left untouched
          so a re-run never overwrites a human verdict.

        Implemented as a single ``INSERT ... ON CONFLICT (source_channel,
        wikidata_qid) DO UPDATE ... WHERE review_status = 'pending'`` so it is
        race-safe: concurrent generations cannot double-insert (the unique
        constraint + ``DO UPDATE`` collapse to one row), and the ``WHERE`` clause
        means a conflicting **terminal** row is never updated — closing the
        SELECT-then-write races. The raw upsert bypasses the ORM ``onupdate``, so
        ``updated_at`` and ``last_generated_at`` are set explicitly.

        Parameters
        ----------
        session : AsyncSession
            The active database session.
        candidate : CandidateSuggestionCreate
            The freshly generated candidate (validated pending-on-create).

        Returns
        -------
        CandidateSuggestionDB
            The inserted or current row (a conflicting terminal row is returned
            unchanged).
        """
        now = datetime.now(UTC)
        values = _candidate_row_values(candidate)
        values["last_generated_at"] = now

        insert_stmt = pg_insert(CandidateSuggestionDB).values(**values)
        refresh_set: dict[str, Any] = {
            field: insert_stmt.excluded[field] for field in _REFRESHABLE_FIELDS
        }
        refresh_set["last_generated_at"] = insert_stmt.excluded.last_generated_at
        refresh_set["updated_at"] = now
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["source_channel", "wikidata_qid"],
            set_=refresh_set,
            where=CandidateSuggestionDB.review_status == ReviewStatus.PENDING.value,
        )
        await session.execute(stmt)
        await session.flush()

        # populate_existing forces the identity-map object to take the fresh DB
        # values — a Core upsert does not auto-sync a cached ORM instance, so a
        # refreshed row (score/triage/…) would otherwise read stale.
        result = await session.execute(
            select(CandidateSuggestionDB)
            .where(
                CandidateSuggestionDB.source_channel == values["source_channel"],
                CandidateSuggestionDB.wikidata_qid == values["wikidata_qid"],
            )
            .execution_options(populate_existing=True)
        )
        # Row exists: it was either just inserted or already present on conflict.
        return result.scalar_one()

    async def list_pending(
        self,
        session: AsyncSession,
        *,
        source_channel: str = "relation",
        triage: str | None = None,
        type_hint: str | None = None,
        min_token_count: int | None = None,
        possible_duplicate: bool | None = None,
        sort: str = "score",
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[CandidateSuggestionDB], int]:
        """Return a page of pending candidates plus the total matching count.

        Ordered by ``sort`` (``score`` | ``corroboration`` | ``salience``),
        descending — most plausible first (FR-007).
        """
        filters = [
            CandidateSuggestionDB.review_status == ReviewStatus.PENDING.value,
            CandidateSuggestionDB.source_channel == source_channel,
        ]
        if triage is not None:
            filters.append(CandidateSuggestionDB.triage == triage)
        if type_hint is not None:
            filters.append(CandidateSuggestionDB.type_hint == type_hint)
        if min_token_count is not None:
            filters.append(CandidateSuggestionDB.token_count >= min_token_count)
        if possible_duplicate is not None:
            if possible_duplicate:
                filters.append(
                    CandidateSuggestionDB.possible_duplicate_of_id.isnot(None)
                )
            else:
                filters.append(CandidateSuggestionDB.possible_duplicate_of_id.is_(None))

        total_result = await session.execute(
            select(func.count()).select_from(CandidateSuggestionDB).where(*filters)
        )
        total = total_result.scalar() or 0

        sort_column = _SORT_COLUMNS.get(sort, CandidateSuggestionDB.score)
        stmt = (
            select(CandidateSuggestionDB)
            .where(*filters)
            .order_by(sort_column.desc(), CandidateSuggestionDB.id)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    async def counts_by_status(
        self, session: AsyncSession, *, source_channel: str = "relation"
    ) -> dict[str, int]:
        """Return review-status counts plus the pending triage distribution (FR-016).

        Keys: every ``ReviewStatus`` value (0 when absent) and every
        ``TriageCategory`` value counted over **pending** rows only.
        """
        status_rows = await session.execute(
            select(
                CandidateSuggestionDB.review_status,
                func.count(),
            )
            .where(CandidateSuggestionDB.source_channel == source_channel)
            .group_by(CandidateSuggestionDB.review_status)
        )
        counts: dict[str, int] = {status.value: 0 for status in ReviewStatus}
        counts.update({triage.value: 0 for triage in TriageCategory})
        for status_value, count in status_rows.all():
            counts[status_value] = count

        triage_rows = await session.execute(
            select(
                CandidateSuggestionDB.triage,
                func.count(),
            )
            .where(
                CandidateSuggestionDB.source_channel == source_channel,
                CandidateSuggestionDB.review_status == ReviewStatus.PENDING.value,
            )
            .group_by(CandidateSuggestionDB.triage)
        )
        for triage_value, count in triage_rows.all():
            counts[triage_value] = count
        return counts

    async def set_verdict(
        self,
        session: AsyncSession,
        *,
        candidate_id: uuid.UUID,
        review_status: ReviewStatus,
        reviewed_by: str,
        reviewed_at: datetime,
        created_entity_id: uuid.UUID | None = None,
    ) -> CandidateSuggestionDB | None:
        """Transition a **pending** candidate to a terminal review state.

        Compare-and-set: the UPDATE is guarded by ``review_status = 'pending'`` so a
        stale review or a concurrent second verdict cannot flip an already-terminal
        row (e.g. re-approve a rejected one, or overwrite ``created_entity_id``).
        Returns the updated row, or ``None`` if the candidate is absent or is no
        longer pending (the caller treats ``None`` as "already decided").

        ``created_entity_id`` is set only for an approval; passing ``None`` leaves it
        unset (correct for reject/supersede).
        """
        values: dict[str, Any] = {
            "review_status": review_status.value,
            "reviewed_by": reviewed_by,
            "reviewed_at": reviewed_at,
            "updated_at": datetime.now(UTC),
        }
        if created_entity_id is not None:
            values["created_entity_id"] = created_entity_id
        result = await session.execute(
            update(CandidateSuggestionDB)
            .where(
                CandidateSuggestionDB.id == candidate_id,
                CandidateSuggestionDB.review_status == ReviewStatus.PENDING.value,
            )
            .values(**values)
        )
        await session.flush()
        if (result.rowcount or 0) == 0:
            return None
        return await self.get(session, candidate_id)

    async def supersede_grounded(
        self,
        session: AsyncSession,
        *,
        source_channel: str,
        grounded_qids: set[str],
    ) -> int:
        """Mark pending candidates whose QID is now a library entity as superseded.

        Reconciliation for FR-011b: a candidate whose identity became an entity by
        other means is retired, never left pending or duplicated. Returns the
        number of rows updated; a no-op (0) when ``grounded_qids`` is empty.

        ``grounded_qids`` is the set of library-grounded QIDs (~2k today); the
        ``IN`` list stays well under asyncpg's 32767 bind-parameter cap. If the
        library ever approaches that, chunk this call.
        """
        if not grounded_qids:
            return 0
        result = await session.execute(
            update(CandidateSuggestionDB)
            .where(
                CandidateSuggestionDB.source_channel == source_channel,
                CandidateSuggestionDB.review_status == ReviewStatus.PENDING.value,
                CandidateSuggestionDB.wikidata_qid.in_(grounded_qids),
            )
            .values(
                review_status=ReviewStatus.SUPERSEDED.value,
                updated_at=datetime.now(UTC),
            )
        )
        await session.flush()
        return result.rowcount or 0

    async def emit_relation_candidates(
        self, session: AsyncSession, *, relation_fields: list[str]
    ) -> list[RelationCandidateRow]:
        """Emit relation-channel candidates from grounded entities' stored relations (FR-001).

        Reads each active, grounded entity's ``properties[<relation>]`` blocks
        (``{qids: [...], values: [...]}``) for the given relation field names,
        pairs each target QID with its label, and aggregates per distinct target:
        corroboration (distinct seeds), dangling edges (total edges), and the set
        of relation field names. Targets whose QID is already a library entity are
        excluded. Offline — reads stored JSONB only, no external call.

        Whole-statement ``text()`` (not a narrow fragment composed into Core) because
        this is a standalone read whose substance is a correlated ``LATERAL …
        WITH ORDINALITY`` pairing of two parallel JSONB arrays. A Core rewrite is
        *possible* but would be a longer transcription of the same SQL with no
        composability, readability, or safety gain — nothing else composes into it,
        and the real-DB integration tests already exercise the query. This matches the
        whole-statement ``text()`` precedent in ``recovery_provenance_repository`` and
        is safer than it (no string interpolation; ``relation_fields`` is a typed array
        bind). A ``CASE … '[]'::jsonb`` coercion inside each lateral keeps a malformed
        ``qids``/``values`` value (a scalar rather than an array) from aborting the run.

        Parameters
        ----------
        session : AsyncSession
            The active database session.
        relation_fields : list[str]
            Relation field names to follow (``wikidata_properties.RELATIONS`` values).

        Returns
        -------
        list[RelationCandidateRow]
            One row per distinct not-yet-library target with provenance.
        """
        stmt = text(
            """
            WITH flds(field) AS (SELECT unnest(cast(:fields AS text[]))),
            lib AS (
                SELECT external_ids->'wikidata'->>'id' AS qid
                FROM named_entities
                WHERE status = 'active' AND merged_into_id IS NULL
                  AND external_ids->'wikidata'->>'id' IS NOT NULL
            ),
            edges AS (
                SELECT ne.id AS seed_id, f.field AS rel, q.qid AS tgt, v.val AS label
                FROM named_entities ne
                JOIN flds f ON jsonb_exists(ne.properties, f.field)
                -- Guard with CASE INSIDE the set-returning function, not a join
                -- qual: a join qual is not guaranteed to run before the SRF, so a
                -- malformed non-array `qids`/`values` would still raise "cannot
                -- extract elements from a scalar". Coercing a non-array to '[]'
                -- yields zero rows and is bulletproof regardless of plan order.
                CROSS JOIN LATERAL jsonb_array_elements_text(
                    CASE
                        WHEN jsonb_typeof(ne.properties->f.field->'qids') = 'array'
                        THEN ne.properties->f.field->'qids'
                        ELSE '[]'::jsonb
                    END
                ) WITH ORDINALITY q(qid, ord)
                LEFT JOIN LATERAL jsonb_array_elements_text(
                    CASE
                        WHEN jsonb_typeof(ne.properties->f.field->'values') = 'array'
                        THEN ne.properties->f.field->'values'
                        ELSE '[]'::jsonb
                    END
                ) WITH ORDINALITY v(val, ord2) ON v.ord2 = q.ord
                WHERE ne.status = 'active' AND ne.merged_into_id IS NULL
                  AND coalesce(q.qid, '') <> ''
                  AND q.qid NOT IN (SELECT qid FROM lib WHERE qid IS NOT NULL)
            )
            SELECT tgt AS wikidata_qid,
                   max(label) AS label,
                   count(DISTINCT seed_id) AS corroboration_count,
                   count(*) AS dangling_edge_count,
                   array_agg(DISTINCT rel) AS relations,
                   array_agg(DISTINCT seed_id) AS seed_ids
            FROM edges
            WHERE coalesce(label, '') <> ''
            GROUP BY tgt
            """
        ).bindparams(bindparam("fields", type_=ARRAY(String())))
        result = await session.execute(stmt, {"fields": relation_fields})
        return [
            RelationCandidateRow(
                wikidata_qid=row.wikidata_qid,
                label=row.label,
                corroboration_count=row.corroboration_count,
                dangling_edge_count=row.dangling_edge_count,
                relations=list(row.relations),
                seed_entity_ids=list(row.seed_ids),
            )
            for row in result.all()
        ]
