"""
Entity operation log repository for the entity-curation audit trail.

Handles CRUD operations for ``entity_operation_logs`` rows that record
named-entity name/description edits with rollback support (Feature 057).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityOperationLog as EntityOperationLogDB
from chronovista.models.entity_operation_log import (
    EntityOperationLogCreate,
    EntityOperationLogUpdate,
)
from chronovista.repositories.base import BaseSQLAlchemyRepository


class EntityOperationLogRepository(
    BaseSQLAlchemyRepository[
        EntityOperationLogDB,
        EntityOperationLogCreate,
        EntityOperationLogUpdate,
        uuid.UUID,
    ]
):
    """Repository for entity operation log CRUD operations."""

    def __init__(self) -> None:
        """Initialize repository with EntityOperationLog model."""
        super().__init__(EntityOperationLogDB)

    async def get(
        self, session: AsyncSession, id: uuid.UUID
    ) -> EntityOperationLogDB | None:
        """
        Get an entity operation log entry by UUID primary key.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        id : uuid.UUID
            Primary key of the operation log entry.

        Returns
        -------
        Optional[EntityOperationLogDB]
            The matching log entry, or ``None`` if not found.
        """
        result = await session.execute(
            select(EntityOperationLogDB).where(EntityOperationLogDB.id == id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, id: uuid.UUID) -> bool:
        """
        Check if an entity operation log entry exists by UUID primary key.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        id : uuid.UUID
            Primary key of the operation log entry.

        Returns
        -------
        bool
            ``True`` if the entry exists, ``False`` otherwise.
        """
        result = await session.execute(
            select(EntityOperationLogDB.id).where(EntityOperationLogDB.id == id)
        )
        return result.first() is not None

    async def get_by_entity(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        *,
        limit: int = 50,
    ) -> list[EntityOperationLogDB]:
        """
        Get operation log entries for an entity, newest first.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        entity_id : uuid.UUID
            The named entity whose edits to fetch.
        limit : int, optional
            Maximum number of entries to return (default 50).

        Returns
        -------
        list[EntityOperationLogDB]
            Operation log entries ordered by ``performed_at DESC``.
        """
        result = await session.execute(
            select(EntityOperationLogDB)
            .where(EntityOperationLogDB.entity_id == entity_id)
            .order_by(desc(EntityOperationLogDB.performed_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_rolled_back(
        self, session: AsyncSession, id: uuid.UUID
    ) -> EntityOperationLogDB | None:
        """
        Mark an operation log entry as rolled back.

        Sets ``rolled_back = True`` and ``rolled_back_at = now()``.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        id : uuid.UUID
            Primary key of the operation log entry to mark.

        Returns
        -------
        Optional[EntityOperationLogDB]
            The updated entry, or ``None`` if it does not exist.
        """
        db_obj = await self.get(session, id)
        if db_obj is None:
            return None
        db_obj.rolled_back = True
        db_obj.rolled_back_at = datetime.now(UTC)
        session.add(db_obj)
        await session.flush()
        await session.refresh(db_obj)
        return db_obj
