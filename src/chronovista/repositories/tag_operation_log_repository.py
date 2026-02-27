"""
Tag operation log repository for audit trail management.

Handles CRUD operations for tag operation logs that record normalization
and management operations with rollback support.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TagOperationLog as TagOperationLogDB
from chronovista.models.tag_operation_log import TagOperationLogCreate, TagOperationLogUpdate
from chronovista.repositories.base import BaseSQLAlchemyRepository


class TagOperationLogRepository(
    BaseSQLAlchemyRepository[
        TagOperationLogDB,
        TagOperationLogCreate,
        TagOperationLogUpdate,
        uuid.UUID,
    ]
):
    """Repository for tag operation log CRUD operations."""

    def __init__(self) -> None:
        """Initialize repository with TagOperationLog model."""
        super().__init__(TagOperationLogDB)

    async def get(
        self, session: AsyncSession, id: uuid.UUID
    ) -> Optional[TagOperationLogDB]:
        """
        Get tag operation log entry by UUID primary key.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        id : uuid.UUID
            Primary key of the operation log entry.

        Returns
        -------
        Optional[TagOperationLogDB]
            The matching log entry, or ``None`` if not found.
        """
        result = await session.execute(
            select(TagOperationLogDB).where(TagOperationLogDB.id == id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, id: uuid.UUID) -> bool:
        """
        Check if a tag operation log entry exists by UUID primary key.

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
            select(TagOperationLogDB.id).where(TagOperationLogDB.id == id)
        )
        return result.first() is not None

    async def get_recent(
        self,
        session: AsyncSession,
        *,
        limit: int = 20,
    ) -> list[TagOperationLogDB]:
        """
        Get recent tag operation log entries ordered by performed_at descending.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        limit : int, optional
            Maximum number of entries to return (default 20).

        Returns
        -------
        list[TagOperationLogDB]
            Operation log entries ordered by ``performed_at DESC``.
        """
        result = await session.execute(
            select(TagOperationLogDB)
            .order_by(desc(TagOperationLogDB.performed_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_operation_id(
        self, session: AsyncSession, operation_id: uuid.UUID
    ) -> Optional[TagOperationLogDB]:
        """
        Get tag operation log entry by operation UUID.

        Semantically equivalent to ``get()`` but uses a more descriptive name
        intended for undo/rollback command contexts.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        operation_id : uuid.UUID
            Primary key of the operation log entry.

        Returns
        -------
        Optional[TagOperationLogDB]
            The matching log entry, or ``None`` if not found.
        """
        return await self.get(session, operation_id)
