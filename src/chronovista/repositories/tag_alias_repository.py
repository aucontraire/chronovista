"""
Tag alias repository for tag normalization management.

Handles CRUD operations for tag aliases that map raw tag forms (as they appear
in YouTube data) to their canonical normalized representations.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.models.tag_alias import TagAliasCreate, TagAliasUpdate
from chronovista.repositories.base import BaseSQLAlchemyRepository


class TagAliasRepository(
    BaseSQLAlchemyRepository[
        TagAliasDB,
        TagAliasCreate,
        TagAliasUpdate,
        uuid.UUID,
    ]
):
    """Repository for tag alias CRUD operations."""

    def __init__(self) -> None:
        """Initialize repository with TagAlias model."""
        super().__init__(TagAliasDB)

    async def get(
        self, session: AsyncSession, id: uuid.UUID
    ) -> Optional[TagAliasDB]:
        """Get tag alias by UUID primary key."""
        result = await session.execute(
            select(TagAliasDB).where(TagAliasDB.id == id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, id: uuid.UUID) -> bool:
        """Check if tag alias exists by UUID primary key."""
        result = await session.execute(
            select(TagAliasDB.id).where(TagAliasDB.id == id)
        )
        return result.first() is not None
