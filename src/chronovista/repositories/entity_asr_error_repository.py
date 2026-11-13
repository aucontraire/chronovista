"""Entity ASR-error repository (Feature 110).

CRUD and lookup for the dedicated ``entity_asr_errors`` store — confirmed ASR
mis-transcriptions of entity names, lifted out of ``entity_aliases``. Provides the
registration-hook upsert (keyed on the entity + normalized form) and the
corrections-discovery query the ``/corrections/batch`` flow consumes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityAsrError as EntityAsrErrorDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.entity_asr_error import (
    EntityAsrErrorCreate,
    EntityAsrErrorUpdate,
)
from chronovista.repositories.base import BaseSQLAlchemyRepository


class EntityAsrErrorRepository(
    BaseSQLAlchemyRepository[
        EntityAsrErrorDB,
        EntityAsrErrorCreate,
        EntityAsrErrorUpdate,
        uuid.UUID,
    ]
):
    """Repository for entity ASR-error CRUD and discovery lookups."""

    def __init__(self) -> None:
        """Initialize repository with the EntityAsrError model."""
        super().__init__(EntityAsrErrorDB)

    async def get(
        self, session: AsyncSession, id: uuid.UUID
    ) -> EntityAsrErrorDB | None:
        """Get an ASR-error row by UUID primary key."""
        result = await session.execute(
            select(EntityAsrErrorDB).where(EntityAsrErrorDB.id == id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, id: uuid.UUID) -> bool:
        """Check whether an ASR-error row exists by UUID primary key."""
        result = await session.execute(
            select(EntityAsrErrorDB.id).where(EntityAsrErrorDB.id == id)
        )
        return result.first() is not None

    async def get_by_entity_and_normalized(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        alias_name_normalized: str,
    ) -> EntityAsrErrorDB | None:
        """Return an entity's ASR-error row whose normalized form matches.

        The duplicate key — the same ``(alias_name_normalized, entity_id)`` the
        unique constraint enforces — used by the registration-hook upsert.
        """
        result = await session.execute(
            select(EntityAsrErrorDB).where(
                EntityAsrErrorDB.entity_id == entity_id,
                EntityAsrErrorDB.alias_name_normalized == alias_name_normalized,
            )
        )
        return result.scalar_one_or_none()

    async def create_or_update(
        self, session: AsyncSession, *, obj_in: EntityAsrErrorCreate
    ) -> EntityAsrErrorDB:
        """Register an ASR-error form idempotently (keyed on entity + normalized).

        If the entity already has a row with this normalized form, bump its
        ``last_seen_at`` and return it; otherwise create it. Mirrors the old
        name-store registration intent without an occurrence counter (dropped for
        this store — see Feature 110).
        """
        existing = await self.get_by_entity_and_normalized(
            session, obj_in.entity_id, obj_in.alias_name_normalized
        )
        if existing is not None:
            existing.last_seen_at = datetime.now(UTC)
            await session.flush()
            await session.refresh(existing)
            return existing
        return await self.create(session, obj_in=obj_in)

    async def get_multiword_candidates(
        self,
        session: AsyncSession,
        entity_name: str | None = None,
    ) -> list[tuple[str, str, str]]:
        """Return multi-word ASR-error candidates for corrections discovery.

        Mirrors the shape the ``/corrections/batch`` flow consumed from the name
        store: each tuple is ``(alias_name, canonical_name, entity_type)``, limited
        to multi-word forms (the cross-segment discovery relation needs a space to
        split on), optionally filtered to entities whose canonical name contains
        ``entity_name`` (case-insensitive).
        """
        stmt = (
            select(
                EntityAsrErrorDB.alias_name,
                NamedEntityDB.canonical_name,
                NamedEntityDB.entity_type,
            )
            .join(NamedEntityDB, EntityAsrErrorDB.entity_id == NamedEntityDB.id)
            .where(EntityAsrErrorDB.alias_name.contains(" "))
        )
        if entity_name is not None:
            stmt = stmt.where(
                func.lower(NamedEntityDB.canonical_name).contains(entity_name.lower())
            )

        result = await session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]
