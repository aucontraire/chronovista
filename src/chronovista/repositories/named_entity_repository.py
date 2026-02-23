"""
Named entity repository for entity extraction and management.

Handles CRUD operations for named entities discovered from tags and transcripts,
supporting entity resolution, merge tracking, and confidence scoring.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
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

    async def get(
        self, session: AsyncSession, id: uuid.UUID
    ) -> Optional[NamedEntityDB]:
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
