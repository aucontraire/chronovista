"""
Entity alias repository for named entity resolution.

Handles CRUD operations for entity aliases that map alternative names
(variants, abbreviations, nicknames, etc.) to their canonical named entities.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.models.entity_alias import EntityAliasCreate, EntityAliasUpdate
from chronovista.repositories.base import BaseSQLAlchemyRepository


class EntityAliasRepository(
    BaseSQLAlchemyRepository[
        EntityAliasDB,
        EntityAliasCreate,
        EntityAliasUpdate,
        uuid.UUID,
    ]
):
    """Repository for entity alias CRUD operations."""

    def __init__(self) -> None:
        """Initialize repository with EntityAlias model."""
        super().__init__(EntityAliasDB)

    async def get(
        self, session: AsyncSession, id: uuid.UUID
    ) -> Optional[EntityAliasDB]:
        """Get entity alias by UUID primary key."""
        result = await session.execute(
            select(EntityAliasDB).where(EntityAliasDB.id == id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, id: uuid.UUID) -> bool:
        """Check if entity alias exists by UUID primary key."""
        result = await session.execute(
            select(EntityAliasDB.id).where(EntityAliasDB.id == id)
        )
        return result.first() is not None
