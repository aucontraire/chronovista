"""Async repository for `channel_principals` (DESIGN-CHANNEL-PRINCIPALS).

Channel-level cast links. A row's provenance lives in three independent slots and
``decision`` is the human verdict category (``cast`` | ``recurring_guest`` |
``credited_subject`` | ``stuffing`` | ``retired``). Reads expose the cast (current or
all-time); the loader upserts reviewed verdicts. No per-video materialisation happens
here or anywhere — a principal link never mints a mention (design §6).
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from chronovista.db.models import ChannelPrincipal as ChannelPrincipalDB
from chronovista.models.channel_principal import ChannelPrincipal


class ChannelPrincipalRepository:
    """Data access for channel cast links."""

    async def upsert_review(
        self,
        session: AsyncSession,
        *,
        channel_id: str,
        entity_id: uuid.UUID,
        decision: str,
        decided_at: datetime.datetime,
        decided_reason: str | None = None,
        through: datetime.date | None = None,
        generator_version: str | None = None,
        tag_credited_count: int | None = None,
        text_credited_count: int | None = None,
        checkable_video_count: int | None = None,
        spoken_video_count: int | None = None,
        wikidata_linked_at: datetime.datetime | None = None,
    ) -> None:
        """Insert or update the reviewed verdict for ``(channel_id, entity_id)``.

        Writes the human-decision slot (``decision`` = versioned category, ``decided_at``,
        ``decided_reason``), the tenure ``through`` (``None`` = current), and the observed /
        imported slots when supplied. Idempotent on the ``(channel_id, entity_id)`` unique
        constraint, so re-loading the verdict corpus is safe. Does not commit — the caller
        owns the transaction.
        """
        stmt = pg_insert(ChannelPrincipalDB).values(
            channel_id=channel_id,
            entity_id=entity_id,
            decision=decision,
            decided_at=decided_at,
            decided_reason=decided_reason,
            through=through,
            derived_generator_version=generator_version,
            tag_credited_count=tag_credited_count,
            text_credited_count=text_credited_count,
            checkable_video_count=checkable_video_count,
            spoken_video_count=spoken_video_count,
            wikidata_linked_at=wikidata_linked_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["channel_id", "entity_id"],
            set_={
                "decision": stmt.excluded.decision,
                "decided_at": stmt.excluded.decided_at,
                "decided_reason": stmt.excluded.decided_reason,
                "through": stmt.excluded.through,
                "derived_generator_version": stmt.excluded.derived_generator_version,
                "tag_credited_count": stmt.excluded.tag_credited_count,
                "text_credited_count": stmt.excluded.text_credited_count,
                "checkable_video_count": stmt.excluded.checkable_video_count,
                "spoken_video_count": stmt.excluded.spoken_video_count,
                "wikidata_linked_at": stmt.excluded.wikidata_linked_at,
                "updated_at": func.now(),
            },
        )
        await session.execute(stmt)

    async def get(
        self, session: AsyncSession, channel_id: str, entity_id: uuid.UUID
    ) -> ChannelPrincipal | None:
        """Return the stored row for ``(channel_id, entity_id)``, or ``None``."""
        row = (
            await session.execute(
                select(ChannelPrincipalDB).where(
                    ChannelPrincipalDB.channel_id == channel_id,
                    ChannelPrincipalDB.entity_id == entity_id,
                )
            )
        ).scalar_one_or_none()
        return ChannelPrincipal.model_validate(row) if row is not None else None

    async def list_cast_for_channel(
        self, session: AsyncSession, channel_id: str, *, current_only: bool = True
    ) -> list[ChannelPrincipal]:
        """The channel's cast (``decision = 'cast'``).

        ``current_only`` (default) restricts to current principals (``through IS NULL``),
        matching the ``idx_channel_principals_current`` partial index; pass ``False`` for
        the all-time roster (former cast included, each carrying its ``through`` date).
        Non-cast rows (guest / subject / stuffing tombstones) are never returned here.
        """
        stmt = select(ChannelPrincipalDB).where(
            ChannelPrincipalDB.channel_id == channel_id,
            ChannelPrincipalDB.decision == "cast",
        )
        if current_only:
            stmt = stmt.where(ChannelPrincipalDB.through.is_(None))
        stmt = stmt.order_by(
            ChannelPrincipalDB.first_seen, ChannelPrincipalDB.entity_id
        )
        rows = (await session.execute(stmt)).scalars().all()
        return [ChannelPrincipal.model_validate(r) for r in rows]
