"""
Repository for the canonical local-user identity (Feature 060).

``app_identities`` is a singleton table (one row, ``id = 1``). This repository
exposes read/establish/update operations for that single row.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AppIdentity as AppIdentityDB
from ..models.app_identity import AppIdentityCreate, AppIdentityUpdate
from .base import BaseSQLAlchemyRepository

_SINGLETON_ID = 1


class AppIdentityRepository(
    BaseSQLAlchemyRepository[AppIdentityDB, AppIdentityCreate, AppIdentityUpdate, int]
):
    """Data access for the singleton canonical identity row."""

    def __init__(self) -> None:
        super().__init__(AppIdentityDB)

    async def get(self, session: AsyncSession, id: int) -> AppIdentityDB | None:
        """Get the identity row by primary key."""
        result = await session.execute(
            select(AppIdentityDB).where(AppIdentityDB.id == id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, id: int) -> bool:
        """Check whether the identity row exists."""
        result = await session.execute(
            select(AppIdentityDB.id).where(AppIdentityDB.id == id)
        )
        return result.scalar_one_or_none() is not None

    async def get_identity(self, session: AsyncSession) -> AppIdentityDB | None:
        """Return the singleton canonical identity, or ``None`` if unestablished."""
        return await self.get(session, _SINGLETON_ID)

    async def set_identity(
        self, session: AsyncSession, *, obj_in: AppIdentityCreate
    ) -> AppIdentityDB:
        """Establish the singleton canonical identity (``id = 1``).

        Raises an integrity error if an identity already exists — callers MUST
        check ``get_identity`` first (the resolver does).
        """
        db_obj = AppIdentityDB(
            id=_SINGLETON_ID,
            user_id=obj_in.user_id,
            source=obj_in.source.value,
        )
        session.add(db_obj)
        await session.flush()
        await session.refresh(db_obj)
        return db_obj

    async def update_identity(
        self, session: AsyncSession, *, obj_in: AppIdentityUpdate
    ) -> AppIdentityDB | None:
        """Update the singleton identity (used only by ``identity reset``).

        Returns the updated row, or ``None`` if no identity is established.
        """
        existing = await self.get_identity(session)
        if existing is None:
            return None

        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is None or not hasattr(existing, field):
                continue
            if field == "source" and hasattr(value, "value"):
                value = value.value
            setattr(existing, field, value)

        session.add(existing)
        await session.flush()
        await session.refresh(existing)
        return existing
