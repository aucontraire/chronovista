"""The single write path for recovery provenance — ADR-011.

Every recovery adapter records what it contributed through this repository.
Nothing else writes ``videos.recovery_source`` or ``channels.recovery_source``.

WHY A SINGLE WRITE PATH

Before ADR-011, provenance was a single ``varchar`` that each pass overwrote. On
2026-08-09 a Filmot import silently destroyed the attribution of 92 rows that
Wayback and sync had recovered earlier, taking the Wayback snapshot timestamps
with it because those were encoded inside the source string. The data itself
survived; the record of where it came from did not.

Concentrating the write in one place is what makes "append, never overwrite"
enforceable rather than a convention each adapter has to remember.

WHY THIS DOES NOT INHERIT BaseSQLAlchemyRepository

Every other repository in this package does, and the deviation is deliberate:

* the base is generic over exactly one model, and this coordinates two tables
  plus a denormalised column on a third and fourth;
* its ``update`` and ``delete`` have no meaning on an append-only table, so
  inheriting would ship two methods that must never be called.

``get``-style reads are provided explicitly below instead.
"""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from chronovista.db.models import ChannelRecoverySource as ChannelRecoverySourceDB
from chronovista.db.models import VideoRecoverySource as VideoRecoverySourceDB
from chronovista.models.recovery_provenance import RecoverySourceRecord


def _cumulative_fields(table_name: str) -> TextClause:
    """The stored and incoming field lists unioned, de-duplicated and sorted.

    ``fields_written`` names everything a source has contributed to a row, so a
    later pass that fills a *different* field must add to the list rather than
    replace it.

    Replacing it was the behaviour until #228, and the path to losing data was
    ordinary rather than rare: a run fills a video's title while its owning
    channel is not yet in the library, the channel is synced later, and a second
    run fills ``channel_id``. The row then recorded only ``{channel_id}`` — the
    same shape of loss ADR-011 exists to prevent, one column further in. It
    reached 23 rows in the production library before it was noticed.

    Sorted so the column is order-independent: the value now depends on the set
    of fields a source has written, never on the order of the runs that wrote
    them.

    Parameters
    ----------
    table_name : str
        The provenance table being upserted into. Supplied from the mapped
        model's ``__tablename__``, never from user input.

    Returns
    -------
    TextClause
        A scalar subquery for the ``DO UPDATE`` SET clause.
    """
    empty = "ARRAY[]::varchar[]"
    return text(
        f"(SELECT coalesce(array_agg(DISTINCT f ORDER BY f), {empty}) "
        f"FROM unnest("
        f"coalesce({table_name}.fields_written, {empty}) || "
        f"coalesce(excluded.fields_written, {empty})"
        f") AS f)"
    )


class RecoveryProvenanceRepository:
    """Append provenance, and keep the denormalised columns in step."""

    # ── writes ───────────────────────────────────────────────────────────────

    async def record_video(
        self,
        session: AsyncSession,
        video_id: str,
        record: RecoverySourceRecord,
    ) -> None:
        """Record that *record.source* contributed to *video_id*.

        Idempotent per (video_id, source). A repeat pass by the same source
        refreshes its own row's timestamp and *adds to* its field list, and
        leaves every other source's row untouched — which is the whole point.

        The field list accumulates rather than being replaced (#228): a source
        that fills a title on one run and a channel on the next has written
        both, and the row must say so.
        """
        values: dict[str, object] = {
            "video_id": video_id,
            "source": record.source,
            "source_detail": record.source_detail,
            "fields_written": record.fields_written,
        }
        if record.recovered_at is not None:
            values["recovered_at"] = record.recovered_at

        stmt = insert(VideoRecoverySourceDB).values(values)
        # A source may legitimately run twice (a retry, or a second pass filling
        # a gap it could not fill before). Updating its own row is correct;
        # DO NOTHING would silently keep a stale timestamp.
        update_cols: dict[str, object] = {
            "source_detail": stmt.excluded.source_detail,
            "fields_written": _cumulative_fields(VideoRecoverySourceDB.__tablename__),
        }
        if record.recovered_at is not None:
            update_cols["recovered_at"] = stmt.excluded.recovered_at
        stmt = stmt.on_conflict_do_update(
            index_elements=["video_id", "source"], set_=update_cols
        )
        await session.execute(stmt)

        await self._refresh_video_denormalised(session, video_id)

    async def record_channel(
        self,
        session: AsyncSession,
        channel_id: str,
        record: RecoverySourceRecord,
    ) -> None:
        """Record that *record.source* contributed to *channel_id*.

        Same accumulation rule as ``record_video`` (#228) — the two paths must
        not disagree about what ``fields_written`` means.
        """
        values: dict[str, object] = {
            "channel_id": channel_id,
            "source": record.source,
            "source_detail": record.source_detail,
            "fields_written": record.fields_written,
        }
        if record.recovered_at is not None:
            values["recovered_at"] = record.recovered_at

        stmt = insert(ChannelRecoverySourceDB).values(values)
        update_cols: dict[str, object] = {
            "source_detail": stmt.excluded.source_detail,
            "fields_written": _cumulative_fields(ChannelRecoverySourceDB.__tablename__),
        }
        if record.recovered_at is not None:
            update_cols["recovered_at"] = stmt.excluded.recovered_at
        stmt = stmt.on_conflict_do_update(
            index_elements=["channel_id", "source"], set_=update_cols
        )
        await session.execute(stmt)

        await self._refresh_channel_denormalised(session, channel_id)

    # ── reads ────────────────────────────────────────────────────────────────

    async def get_video_sources(
        self, session: AsyncSession, video_id: str
    ) -> list[VideoRecoverySourceDB]:
        """Every source that contributed to *video_id*, newest first."""
        result = await session.execute(
            select(VideoRecoverySourceDB)
            .where(VideoRecoverySourceDB.video_id == video_id)
            .order_by(VideoRecoverySourceDB.recovered_at.desc())
        )
        return list(result.scalars().all())

    async def get_channel_sources(
        self, session: AsyncSession, channel_id: str
    ) -> list[ChannelRecoverySourceDB]:
        """Every source that contributed to *channel_id*, newest first."""
        result = await session.execute(
            select(ChannelRecoverySourceDB)
            .where(ChannelRecoverySourceDB.channel_id == channel_id)
            .order_by(ChannelRecoverySourceDB.recovered_at.desc())
        )
        return list(result.scalars().all())

    # ── prior-contribution lookups ───────────────────────────────────────────
    #
    # A recovery pass deciding whether its capture supersedes what is already
    # stored must compare against *its own* previous contribution, not against
    # whichever source wrote most recently. Reading that from the denormalised
    # column answers the wrong question — and answers it silently, because a
    # failed parse is indistinguishable from no prior contribution.

    async def get_video_source_detail(
        self, session: AsyncSession, video_id: str, source: str
    ) -> str | None:
        """This source's own ``source_detail`` for *video_id*, if it has one.

        Returns ``None`` when the source has never written to this row, which
        callers must treat as "no prior contribution" rather than as an error.
        """
        result = await session.execute(
            select(VideoRecoverySourceDB.source_detail).where(
                VideoRecoverySourceDB.video_id == video_id,
                VideoRecoverySourceDB.source == source,
            )
        )
        return result.scalar_one_or_none()

    async def get_channel_source_detail(
        self, session: AsyncSession, channel_id: str, source: str
    ) -> str | None:
        """This source's own ``source_detail`` for *channel_id*, if it has one."""
        result = await session.execute(
            select(ChannelRecoverySourceDB.source_detail).where(
                ChannelRecoverySourceDB.channel_id == channel_id,
                ChannelRecoverySourceDB.source == source,
            )
        )
        return result.scalar_one_or_none()

    # ── denormalised projection ──────────────────────────────────────────────
    #
    # ADR-011 keeps `videos.recovery_source` / `recovered_at` as a cheap "most
    # recent" so the detail endpoint need not join per row. They are DERIVED:
    # this is the only code permitted to write them, and it always recomputes
    # from the join table rather than from whatever the caller happened to pass.
    #
    # The packed `source:detail` form is reconstructed here for backward
    # compatibility with existing readers (the API schemas and frontend types
    # already expose the column). New readers should use the join table.

    async def _refresh_video_denormalised(
        self, session: AsyncSession, video_id: str
    ) -> None:
        await session.execute(_VIDEO_REFRESH, {"video_id": video_id})

    async def _refresh_channel_denormalised(
        self, session: AsyncSession, channel_id: str
    ) -> None:
        await session.execute(_CHANNEL_REFRESH, {"channel_id": channel_id})


def _refresh_sql(table: str, join_table: str, key: str) -> TextClause:
    """Project the most recent provenance row onto the denormalised columns.

    The packed ``source:detail`` string is rebuilt here — not because packing is
    good, but because the existing readers (API schemas, frontend types) already
    consume that shape. The join table remains the record of truth; this is a
    compatibility projection with a single writer, and it can be dropped once no
    reader depends on it.
    """
    return text(
        f"""
        UPDATE {table} AS t
        SET recovery_source = s.packed,
            recovered_at    = s.recovered_at
        FROM (
            SELECT source || COALESCE(':' || source_detail, '') AS packed,
                   recovered_at
            FROM {join_table}
            WHERE {key} = :{key}
            ORDER BY recovered_at DESC, source ASC
            LIMIT 1
        ) AS s
        WHERE t.{key} = :{key}
        """  # noqa: S608 - table names are literals from this module, never input
    )


# Built once at import: the statements are fixed, only the bound key varies.
_VIDEO_REFRESH = _refresh_sql("videos", "video_recovery_sources", "video_id")
_CHANNEL_REFRESH = _refresh_sql("channels", "channel_recovery_sources", "channel_id")
