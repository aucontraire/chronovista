"""
Named entity repository for entity extraction and management.

Handles CRUD operations for named entities discovered from tags and transcripts,
supporting entity resolution, merge tracking, and confidence scoring.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.named_entity import NamedEntityCreate, NamedEntityUpdate
from chronovista.repositories.base import BaseSQLAlchemyRepository


class NamedEntityRepository(
    BaseSQLAlchemyRepository[
        NamedEntityDB,
        NamedEntityCreate,
        NamedEntityUpdate,
        uuid.UUID,
    ]
):
    """Repository for named entity CRUD operations."""

    def __init__(self) -> None:
        """Initialize repository with NamedEntity model."""
        super().__init__(NamedEntityDB)

    async def get(self, session: AsyncSession, id: uuid.UUID) -> NamedEntityDB | None:
        """Get named entity by UUID primary key."""
        result = await session.execute(
            select(NamedEntityDB).where(NamedEntityDB.id == id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, id: uuid.UUID) -> bool:
        """Check if named entity exists by UUID primary key."""
        result = await session.execute(
            select(NamedEntityDB.id).where(NamedEntityDB.id == id)
        )
        return result.first() is not None

    async def replace_enrichment(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        *,
        properties: dict[str, Any],
        external_ids: dict[str, Any],
    ) -> int:
        """Full-replacement write of knowledge-base enrichment for one entity (Feature 067).

        Sets exactly ``properties`` and ``external_ids`` — never a JSONB merge — so a value
        removed upstream does not survive (FR-005). The SET clause contains only these two
        columns and never the human-authored display fields (FR-006); this is asserted by the
        SET-clause guard test (ST-001). UPDATE-only: if no row matches ``entity_id`` the
        entity is absent and the caller skips it (FR-005b) — nothing is inserted.

        Parameters
        ----------
        session : AsyncSession
            The active database session.
        entity_id : uuid.UUID
            Target entity's primary key.
        properties : dict[str, Any]
            The property bag, mirrored verbatim into ``named_entities.properties``.
        external_ids : dict[str, Any]
            The structured identifier map for ``named_entities.external_ids``.

        Returns
        -------
        int
            Number of rows updated: 1 if the entity existed, 0 if it was absent.
        """
        stmt = (
            update(NamedEntityDB)
            .where(NamedEntityDB.id == entity_id)
            .values(properties=properties, external_ids=external_ids)
        )
        result = await session.execute(stmt)
        return result.rowcount
