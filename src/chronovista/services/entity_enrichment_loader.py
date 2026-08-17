"""
Entity enrichment loader (Feature 067, US1).

Lands the entity-resolution ledger's captured knowledge-base enrichment into the database,
making the database the authoritative store. Reads a ledger export (produced by the untracked
``scripts/entity_resolution/`` pipeline), validates each record against the tracked
``EntityEnrichmentRecord`` contract, and for every entity **present** in the database writes
its ``properties`` (verbatim) and its transformed ``external_ids`` via
``NamedEntityRepository.replace_enrichment``.

Semantics (spec):
- **Mirror-what's-present** (FR-005a): an entity present in the export is written to match the
  export exactly; entities absent from the export are never touched (this loader only writes
  entities named in the input).
- **UPDATE-only** (FR-005b): a record whose ``entity_id`` is not in the database is skipped and
  reported, never inserted.
- **Display-safe** (FR-006): only ``properties`` and ``external_ids`` are written.
- **Idempotent** (FR-004): a re-run with unchanged input produces no change.
- **Coverage** (FR-007/FR-007a): reports whether the export covers every active entity
  (``status='active'`` AND ``merged_into_id IS NULL``) — guarding the stale-partial-snapshot
  hazard (ST-006).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.entity_enrichment import EntityEnrichmentRecord
from chronovista.repositories.named_entity_repository import NamedEntityRepository


class EnrichmentLoadReport(BaseModel):
    """Outcome of a load run (dry-run or applied)."""

    applied: bool = Field(
        description="True if changes were written; False for a dry run"
    )
    total_records: int = Field(description="Records parsed from the export")
    written: int = Field(default=0, description="Entities whose enrichment was written")
    skipped_absent: list[str] = Field(
        default_factory=list,
        description="Record entity_ids not present in the database (FR-005b)",
    )
    active_entity_count: int = Field(
        default=0, description="Active entities in the database (FR-007a)"
    )
    active_covered: int = Field(
        default=0, description="Active entities that the export covers"
    )
    missing_active: list[str] = Field(
        default_factory=list,
        description="Active entity_ids NOT in the export — the coverage gap (ST-006)",
    )

    @property
    def coverage_complete(self) -> bool:
        """True when the export covers every active entity (no stale-partial gap)."""
        return not self.missing_active


def should_requery_source(external_ids: dict[str, Any], source: str) -> bool:
    """Whether a subsequent resolution pass should query ``source`` for this entity (FR-017).

    Returns False when the source is recorded as searched-and-absent (``status='absent'``) —
    re-querying would waste time and re-disclose the same name to the knowledge base (US4).
    The untracked resolution pipeline calls this so both it and any tracked pass share one
    definition of "already searched, found nothing".
    """
    entry = external_ids.get(source)
    return not (isinstance(entry, dict) and entry.get("status") == "absent")


def is_verified_locked(external_ids: dict[str, Any], source: str) -> bool:
    """Whether ``source``'s identifier is human-verified and must not be overturned (FR-017).

    An automated pass must not overwrite a ``verified`` identifier — a human decided it, and a
    wrong overwrite propagates silently (ADR-010 Decision 3 / US4).
    """
    entry = external_ids.get(source)
    return isinstance(entry, dict) and bool(entry.get("verified"))


def parse_ledger(path: Path) -> list[EntityEnrichmentRecord]:
    """Parse a ledger export file into validated enrichment records.

    The export is ``{... , "entities": [ {entity_id, canonical_name, properties, wikidata,
    dbpedia, ...}, ... ]}``. Unknown fields on each record are ignored (``extra="ignore"``),
    so a richer ledger does not break the load.
    """
    data = json.loads(path.read_text())
    entities = data.get("entities", data if isinstance(data, list) else [])
    return [EntityEnrichmentRecord.model_validate(e) for e in entities]


async def _active_entity_ids(session: AsyncSession) -> set[str]:
    """IDs of active entities: status='active' AND not merged into another (FR-007a)."""
    result = await session.execute(
        select(NamedEntityDB.id).where(
            and_(
                NamedEntityDB.status == "active",
                NamedEntityDB.merged_into_id.is_(None),
            )
        )
    )
    return {str(row[0]) for row in result.all()}


async def _existing_entity_ids(session: AsyncSession, ids: list[uuid.UUID]) -> set[str]:
    """The subset of ``ids`` that exist in ``named_entities`` (any status), in one query."""
    if not ids:
        return set()
    result = await session.execute(
        select(NamedEntityDB.id).where(NamedEntityDB.id.in_(ids))
    )
    return {str(row[0]) for row in result.all()}


async def load_enrichment(
    session: AsyncSession,
    records: list[EntityEnrichmentRecord],
    *,
    apply: bool,
) -> EnrichmentLoadReport:
    """Load enrichment records into the database (or dry-run) and report coverage.

    Parameters
    ----------
    session : AsyncSession
        Active database session. In ``apply`` mode the caller is responsible for committing.
    records : list[EntityEnrichmentRecord]
        The parsed, validated export records.
    apply : bool
        When False (dry run), no writes occur; coverage and skip analysis still run.

    Returns
    -------
    EnrichmentLoadReport
    """
    repo = NamedEntityRepository()

    active_ids = await _active_entity_ids(session)
    record_ids = {str(rec.entity_id) for rec in records}

    written = 0
    skipped_absent: list[str] = []

    # Dry run resolves "absent" from one IN-query rather than a per-record exists() (N+1).
    existing_ids: set[str] = (
        set()
        if apply
        else await _existing_entity_ids(session, [rec.entity_id for rec in records])
    )

    for rec in records:
        external_ids = {
            source: identifier.model_dump()
            for source, identifier in rec.to_external_ids().items()
        }
        if apply:
            rowcount = await repo.replace_enrichment(
                session,
                rec.entity_id,
                properties=rec.properties,
                external_ids=external_ids,
            )
            if rowcount == 0:
                skipped_absent.append(str(rec.entity_id))
            else:
                written += rowcount
        elif str(rec.entity_id) not in existing_ids:
            skipped_absent.append(str(rec.entity_id))

    missing_active = sorted(active_ids - record_ids)

    return EnrichmentLoadReport(
        applied=apply,
        total_records=len(records),
        written=written,
        skipped_absent=skipped_absent,
        active_entity_count=len(active_ids),
        active_covered=len(active_ids & record_ids),
        missing_active=missing_active,
    )
