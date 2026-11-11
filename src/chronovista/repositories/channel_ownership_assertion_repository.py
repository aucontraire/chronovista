"""Async repository for ``channel_ownership_assertions`` (Feature 109).

User-asserted "entity operates channel" links — the DECIDED-space store, kept separate
from the imported Wikidata ``youtube_channel_id`` property. Plain CRUD: the redundancy
checks (already imported vs already asserted) and the read-time union with imported values
live in ``NamedEntityRepository`` / the routes, which hold both sides. Nothing here ever
writes to ``named_entities.properties``.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    ChannelOwnershipAssertion as ChannelOwnershipAssertionDB,
)
from chronovista.models.channel_ownership_assertion import ChannelOwnershipAssertion


class ChannelOwnershipAssertionRepository:
    """Data access for user-asserted channel-ownership links."""

    async def add(
        self,
        session: AsyncSession,
        *,
        entity_id: uuid.UUID,
        channel_id: str,
        note: str | None = None,
        asserted_at: datetime.datetime | None = None,
    ) -> ChannelOwnershipAssertion:
        """Insert one assertion and return it. Caller owns the transaction (no commit).

        Assumes the caller has already rejected redundant adds (imported or existing
        manual); the ``uq_channel_ownership_assertions`` constraint is the DB backstop.
        """
        row = ChannelOwnershipAssertionDB(
            entity_id=entity_id,
            channel_id=channel_id,
            note=note,
        )
        if asserted_at is not None:
            row.asserted_at = asserted_at
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return ChannelOwnershipAssertion.model_validate(row)

    async def get(
        self, session: AsyncSession, entity_id: uuid.UUID, channel_id: str
    ) -> ChannelOwnershipAssertion | None:
        """Return the stored assertion for ``(entity_id, channel_id)``, or ``None``."""
        row = (
            await session.execute(
                select(ChannelOwnershipAssertionDB).where(
                    ChannelOwnershipAssertionDB.entity_id == entity_id,
                    ChannelOwnershipAssertionDB.channel_id == channel_id,
                )
            )
        ).scalar_one_or_none()
        return (
            ChannelOwnershipAssertion.model_validate(row) if row is not None else None
        )

    async def list_by_entity(
        self, session: AsyncSession, entity_id: uuid.UUID
    ) -> list[ChannelOwnershipAssertion]:
        """All manual assertions for one entity, oldest first."""
        rows = (
            (
                await session.execute(
                    select(ChannelOwnershipAssertionDB)
                    .where(ChannelOwnershipAssertionDB.entity_id == entity_id)
                    .order_by(
                        ChannelOwnershipAssertionDB.asserted_at,
                        ChannelOwnershipAssertionDB.channel_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        return [ChannelOwnershipAssertion.model_validate(r) for r in rows]

    async def list_by_channel(
        self, session: AsyncSession, channel_id: str
    ) -> list[ChannelOwnershipAssertion]:
        """All manual assertions naming one channel, oldest first."""
        rows = (
            (
                await session.execute(
                    select(ChannelOwnershipAssertionDB)
                    .where(ChannelOwnershipAssertionDB.channel_id == channel_id)
                    .order_by(
                        ChannelOwnershipAssertionDB.asserted_at,
                        ChannelOwnershipAssertionDB.entity_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        return [ChannelOwnershipAssertion.model_validate(r) for r in rows]

    async def delete(
        self, session: AsyncSession, entity_id: uuid.UUID, channel_id: str
    ) -> bool:
        """Delete the manual link for ``(entity_id, channel_id)``; True if a row was removed."""
        result = await session.execute(
            sql_delete(ChannelOwnershipAssertionDB).where(
                ChannelOwnershipAssertionDB.entity_id == entity_id,
                ChannelOwnershipAssertionDB.channel_id == channel_id,
            )
        )
        return (result.rowcount or 0) > 0
