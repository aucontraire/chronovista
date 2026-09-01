"""
Entity alias repository for named entity resolution.

Handles CRUD operations for entity aliases that map alternative names
(variants, abbreviations, nicknames, etc.) to their canonical named entities.
"""

from __future__ import annotations

import uuid

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

    async def get(self, session: AsyncSession, id: uuid.UUID) -> EntityAliasDB | None:
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

    async def get_by_entity_and_normalized(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        alias_name_normalized: str,
    ) -> EntityAliasDB | None:
        """Return an entity's alias whose normalized name matches (#256).

        The duplicate check for alias creation: accents and case are folded into
        ``alias_name_normalized``, so two variants that normalize to the same
        string are treated as the same alias.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        entity_id : uuid.UUID
            The entity that would own the alias.
        alias_name_normalized : str
            The normalized alias name to match.

        Returns
        -------
        EntityAliasDB | None
            The existing alias, or ``None`` if the entity has no alias with that
            normalized name.
        """
        result = await session.execute(
            select(EntityAliasDB).where(
                EntityAliasDB.entity_id == entity_id,
                EntityAliasDB.alias_name_normalized == alias_name_normalized,
            )
        )
        return result.scalar_one_or_none()
