"""
Canonical tag repository for tag normalization management.

Handles CRUD operations for canonical tags that represent the normalized,
deduplicated form of video tags with lifecycle management and merge tracking.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.models.canonical_tag import CanonicalTagCreate, CanonicalTagUpdate
from chronovista.repositories.base import BaseSQLAlchemyRepository


class CanonicalTagRepository(
    BaseSQLAlchemyRepository[
        CanonicalTagDB,
        CanonicalTagCreate,
        CanonicalTagUpdate,
        uuid.UUID,
    ]
):
    """Repository for canonical tag CRUD operations."""

    def __init__(self) -> None:
        """Initialize repository with CanonicalTag model."""
        super().__init__(CanonicalTagDB)

    async def get(
        self, session: AsyncSession, id: uuid.UUID
    ) -> Optional[CanonicalTagDB]:
        """Get canonical tag by UUID primary key."""
        result = await session.execute(
            select(CanonicalTagDB).where(CanonicalTagDB.id == id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, id: uuid.UUID) -> bool:
        """Check if canonical tag exists by UUID primary key."""
        result = await session.execute(
            select(CanonicalTagDB.id).where(CanonicalTagDB.id == id)
        )
        return result.first() is not None
