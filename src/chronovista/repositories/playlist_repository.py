"""
Playlist repository implementation.

Provides data access layer for playlists with full CRUD operations,
content organization analytics, and playlist management.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, case, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.db.models import Playlist as PlaylistDB
from chronovista.db.models import PlaylistMembership as PlaylistMembershipDB
from chronovista.db.models import UserVideo as UserVideoDB
from chronovista.models.enums import PlaylistType
from chronovista.models.playlist import (
    PlaylistAnalytics,
    PlaylistCreate,
    PlaylistSearchFilters,
    PlaylistStatistics,
    PlaylistUpdate,
)
from chronovista.repositories.base import BaseSQLAlchemyRepository
from chronovista.repositories.user_video_repository import watched_video_ids


def saved_forgotten_video_ids() -> Any:
    """Return a subquery of every distinct "saved & forgotten" video id.

    Saved & Forgotten (Feature 061) means: the video sits in at least one
    *curated* playlist and has no watch-history record.

    **This is the single derivation of that concept.** Both the dashboard
    headline and the videos-list filter consume it, rather than each expressing
    it independently — FR-029b requires exactly one definition so the two
    consumers cannot drift, and FR-029c asserts their equality as a backstop
    rather than as the mechanism.

    Two details are load-bearing:

    - **"Curated" is tested positively** as ``playlist_type == 'regular'``, so
      every other type is excluded automatically — including ``liked`` and
      ``favorites``, which the upstream enum defines but this feature never
      names. A negative test against a list of known system types would leak a
      newly-introduced type into the count.
    - **``.not_in()`` against a non-correlated, DISTINCT subquery.** Safe here
      because ``user_videos.video_id`` and ``playlist_memberships.video_id`` are
      both NOT NULL — a NULL anywhere in a ``NOT IN`` subquery would make it
      return zero rows silently, reporting 0 forgotten videos as if that were a
      real answer.

    Returns
    -------
    Any
        A selectable of distinct video ids, usable as
        ``VideoDB.video_id.in_(saved_forgotten_video_ids())``.
    """
    return (
        select(PlaylistMembershipDB.video_id)
        .join(PlaylistDB, PlaylistDB.playlist_id == PlaylistMembershipDB.playlist_id)
        .where(
            PlaylistDB.playlist_type == PlaylistType.REGULAR.value,
            PlaylistMembershipDB.video_id.not_in(watched_video_ids()),
        )
        .distinct()
    )


async def get_library_overview(session: AsyncSession) -> dict[str, Any]:
    """Compute every Overview Dashboard figure.

    Query shape is the whole problem here (research R1). Measured against
    production data — 89,465 memberships, 51,271 watch rows:

    - ``LEFT JOIN LATERAL (SELECT 1 FROM user_videos ... LIMIT 1)`` per
      membership row: **50,893 ms**
    - the CTE form below: **131 ms**

    Both return identical numbers, so a test asserting only values cannot tell
    them apart. The CTE form expresses the watched set and the distinct
    (type, video) membership set once, then answers the depth figures with
    conditional aggregates over a single join — no per-row subquery anywhere.

    These CTEs are deliberately **not** ``MATERIALIZED``. Each is referenced once,
    so PostgreSQL 12+ inlines them and plans across the boundary. Forcing
    materialisation was measured against production and is *slower*: ~134 ms
    versus ~85 ms. The win over the LATERAL form came from removing the per-row
    correlation, not from an optimisation fence, so do not add the hint on the
    theory that it must help.

    Sequential queries, never ``asyncio.gather`` — ``AsyncSession`` raises
    ``IllegalStateChangeError`` under concurrent use (research R2, and see the
    note at ``api/routers/settings.py``). Keeping the figure count low matters
    precisely because the queries cannot overlap.

    Parameters
    ----------
    session : AsyncSession
        Database session.

    Returns
    -------
    dict[str, Any]
        Keys: ``saved_and_forgotten``, ``watch_later`` (None when absent),
        ``playlist_inventory``, ``rollup``.
    """
    watched = (
        select(UserVideoDB.video_id.label("video_id"))
        .where(UserVideoDB.watched_at.is_not(None))
        .distinct()
        .cte("watched")
    )
    membership = (
        select(
            PlaylistDB.playlist_type.label("playlist_type"),
            PlaylistMembershipDB.video_id.label("video_id"),
        )
        .join(PlaylistDB, PlaylistDB.playlist_id == PlaylistMembershipDB.playlist_id)
        .distinct()
        .cte("membership")
    )

    regular = PlaylistType.REGULAR.value
    watch_later_type = PlaylistType.WATCH_LATER.value
    unwatched = watched.c.video_id.is_(None)

    counts = (
        await session.execute(
            select(
                func.count()
                .filter(membership.c.playlist_type == regular)
                .label("saved_curated_videos"),
                func.count()
                .filter(membership.c.playlist_type == watch_later_type)
                .label("wl_total"),
                func.count()
                .filter(
                    and_(
                        membership.c.playlist_type == watch_later_type,
                        unwatched,
                    )
                )
                .label("wl_unwatched"),
            ).select_from(
                membership.outerjoin(
                    watched, watched.c.video_id == membership.c.video_id
                )
            )
        )
    ).one()

    # FR-021: group over whatever types exist. Never iterate a fixed list — this
    # is the tripwire that makes a newly-introduced playlist type visible.
    #
    # `min(playlist_id)` rides along so FR-025 can deep-link Watch Later without
    # a second round trip. It is only meaningful when the type has exactly one
    # playlist, which is enforced where it is consumed below.
    inventory_rows = (
        await session.execute(
            select(
                PlaylistDB.playlist_type,
                func.count(),
                func.min(PlaylistDB.playlist_id),
            )
            .group_by(PlaylistDB.playlist_type)
            .order_by(PlaylistDB.playlist_type)
        )
    ).all()

    # FR-029b: Saved & Forgotten has **one** derivation, and this is the
    # dashboard consuming it. Expressing it here a second time as a conditional
    # aggregate over the membership CTE would agree numerically today and make
    # the equality test (FR-029c) a coincidence rather than a consequence — the
    # backstop would be doing the job the mechanism is supposed to do. The extra
    # round trip costs ~30 ms against production, well inside the SC-010 budget.
    saved_and_forgotten = await session.scalar(
        select(func.count()).select_from(saved_forgotten_video_ids().subquery())
    )

    watched_videos = await session.scalar(
        select(func.count(func.distinct(UserVideoDB.video_id))).where(
            UserVideoDB.watched_at.is_not(None)
        )
    )
    liked_videos = await session.scalar(
        select(func.count(func.distinct(UserVideoDB.video_id))).where(
            UserVideoDB.liked.is_(True)
        )
    )

    # FR-020a: absence of a Watch Later playlist is distinct from an empty one.
    watch_later_row = next(
        (row for row in inventory_rows if row[0] == watch_later_type), None
    )

    # FR-025: the depth aggregates over every Watch Later playlist, but a link
    # can only target one. Offer an id only when the target is unambiguous —
    # with two such playlists the figure spans both and linking to either would
    # send the user somewhere whose count does not match what they clicked. The
    # frontend renders a non-interactive figure when this is null, which FR-025
    # explicitly permits.
    watch_later_playlist_id = (
        str(watch_later_row[2])
        if watch_later_row is not None and int(watch_later_row[1] or 0) == 1
        else None
    )

    return {
        "saved_and_forgotten": int(saved_and_forgotten or 0),
        "watch_later": (
            {
                "total": int(counts.wl_total or 0),
                "unwatched": int(counts.wl_unwatched or 0),
                "playlist_id": watch_later_playlist_id,
            }
            if watch_later_row is not None
            else None
        ),
        "playlist_inventory": [
            {
                "playlist_type": row[0],
                "playlist_count": int(row[1] or 0),
                # row[2] (min playlist_id) is deliberately not surfaced here;
                # it exists only for the Watch Later deep link above.
                # Derived, not enumerated (FR-022).
                "is_system": row[0] != regular,
            }
            for row in inventory_rows
        ],
        "rollup": {
            "watched_videos": int(watched_videos or 0),
            "saved_curated_videos": int(counts.saved_curated_videos or 0),
            "liked_videos": int(liked_videos or 0),
        },
    }


class PlaylistRepository(
    BaseSQLAlchemyRepository[PlaylistDB, PlaylistCreate, PlaylistUpdate, str]
):
    """Repository for playlist operations."""

    def __init__(self) -> None:
        super().__init__(PlaylistDB)

    async def get(self, session: AsyncSession, playlist_id: str) -> PlaylistDB | None:
        """Get playlist by playlist ID."""
        result = await session.execute(
            select(PlaylistDB).where(PlaylistDB.playlist_id == playlist_id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, playlist_id: str) -> bool:
        """Check if playlist exists by playlist ID."""
        result = await session.execute(
            select(PlaylistDB.playlist_id).where(PlaylistDB.playlist_id == playlist_id)
        )
        return result.first() is not None

    async def get_by_playlist_id(
        self, session: AsyncSession, playlist_id: str
    ) -> PlaylistDB | None:
        """Get playlist by playlist ID (alias for get method)."""
        return await self.get(session, playlist_id)

    async def exists_by_playlist_id(
        self, session: AsyncSession, playlist_id: str
    ) -> bool:
        """Check if playlist exists by playlist ID (alias for exists method)."""
        return await self.exists(session, playlist_id)

    async def get_playlists_by_type(
        self, session: AsyncSession, playlist_type: PlaylistType
    ) -> list[PlaylistDB]:
        """Return all playlists of a given ``playlist_type``, ordered by title.

        Used by the reclassify CLI (Feature 058) to load the ``regular``
        playlists that are candidates for promotion.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        playlist_type : PlaylistType
            The type to filter by.

        Returns
        -------
        list[PlaylistDB]
            Matching playlists.
        """
        result = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.playlist_type == playlist_type.value)
            .order_by(PlaylistDB.title)
        )
        return list(result.scalars().all())

    async def promote_playlist_type(
        self, session: AsyncSession, playlist_id: str, new_type: PlaylistType
    ) -> None:
        """Set a single playlist's ``playlist_type`` (reclassify promotion).

        Emits an independent single-row UPDATE, which makes the backfill
        interruption-safe (Feature 058, FR-009): each promoted row is a
        self-contained committed change.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        playlist_id : str
            The playlist to update.
        new_type : PlaylistType
            The type to set.
        """
        await session.execute(
            update(PlaylistDB)
            .where(PlaylistDB.playlist_id == playlist_id)
            .values(playlist_type=new_type.value)
        )

    async def get_with_channel(
        self, session: AsyncSession, playlist_id: str
    ) -> PlaylistDB | None:
        """Get playlist with channel information loaded."""
        result = await session.execute(
            select(PlaylistDB)
            .options(selectinload(PlaylistDB.channel))
            .where(PlaylistDB.playlist_id == playlist_id)
        )
        return result.scalar_one_or_none()

    async def create_or_update(
        self, session: AsyncSession, playlist_create: PlaylistCreate
    ) -> PlaylistDB:
        """Create new playlist or update existing one."""
        existing = await self.get_by_playlist_id(session, playlist_create.playlist_id)

        if existing:
            # Update existing playlist
            update_data = PlaylistUpdate(
                title=playlist_create.title,
                description=playlist_create.description,
                default_language=playlist_create.default_language,
                privacy_status=playlist_create.privacy_status,
                video_count=playlist_create.video_count,
            )
            return await self.update(session, db_obj=existing, obj_in=update_data)
        else:
            # Create new playlist
            return await self.create(session, obj_in=playlist_create)

    async def get_by_channel_id(
        self, session: AsyncSession, channel_id: str, skip: int = 0, limit: int = 100
    ) -> list[PlaylistDB]:
        """Get all playlists for a specific channel."""
        result = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.channel_id == channel_id)
            .order_by(PlaylistDB.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_privacy_status(
        self,
        session: AsyncSession,
        privacy_status: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[PlaylistDB]:
        """Get playlists by privacy status."""
        result = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.privacy_status == privacy_status)
            .order_by(PlaylistDB.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_language(
        self, session: AsyncSession, language_code: str, skip: int = 0, limit: int = 100
    ) -> list[PlaylistDB]:
        """Get playlists by default language."""
        result = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.default_language == language_code)
            .order_by(PlaylistDB.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def search_playlists(
        self, session: AsyncSession, filters: PlaylistSearchFilters
    ) -> list[PlaylistDB]:
        """Search playlists with advanced filters."""
        query = select(PlaylistDB)

        # Apply filters
        conditions: list[Any] = []

        if filters.playlist_ids:
            conditions.append(PlaylistDB.playlist_id.in_(filters.playlist_ids))

        if filters.channel_ids:
            conditions.append(PlaylistDB.channel_id.in_(filters.channel_ids))

        if filters.title_query:
            conditions.append(PlaylistDB.title.ilike(f"%{filters.title_query}%"))

        if filters.description_query:
            conditions.append(
                PlaylistDB.description.ilike(f"%{filters.description_query}%")
            )

        if filters.language_codes:
            conditions.append(PlaylistDB.default_language.in_(filters.language_codes))

        if filters.privacy_statuses:
            conditions.append(PlaylistDB.privacy_status.in_(filters.privacy_statuses))

        if filters.min_video_count is not None:
            conditions.append(PlaylistDB.video_count >= filters.min_video_count)

        if filters.max_video_count is not None:
            conditions.append(PlaylistDB.video_count <= filters.max_video_count)

        if filters.has_description is not None:
            if filters.has_description:
                conditions.append(PlaylistDB.description.is_not(None))
                conditions.append(PlaylistDB.description != "")
            else:
                conditions.append(
                    or_(
                        PlaylistDB.description.is_(None),
                        PlaylistDB.description == "",
                    )
                )

        if filters.created_after:
            conditions.append(PlaylistDB.created_at >= filters.created_after)

        if filters.created_before:
            conditions.append(PlaylistDB.created_at <= filters.created_before)

        if filters.updated_after:
            conditions.append(PlaylistDB.updated_at >= filters.updated_after)

        if filters.updated_before:
            conditions.append(PlaylistDB.updated_at <= filters.updated_before)

        # Apply linked_status filter (based on playlist_id prefix)
        # Linked = YouTube IDs (PL prefix or system: LL, WL, HL)
        # Unlinked = Internal IDs (int_ prefix)
        if filters.linked_status == "linked":
            conditions.append(
                or_(
                    PlaylistDB.playlist_id.startswith("PL"),
                    PlaylistDB.playlist_id.in_(["LL", "WL", "HL"]),
                )
            )
        elif filters.linked_status == "unlinked":
            conditions.append(PlaylistDB.playlist_id.startswith("int_"))
        # "all" (default) - no filter applied

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(PlaylistDB.created_at.desc())

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_popular_playlists(
        self, session: AsyncSession, limit: int = 50
    ) -> list[PlaylistDB]:
        """Get most popular playlists by video count."""
        result = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.privacy_status == "public")
            .order_by(desc(PlaylistDB.video_count))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_recent_playlists(
        self, session: AsyncSession, limit: int = 50
    ) -> list[PlaylistDB]:
        """Get most recently created playlists."""
        result = await session.execute(
            select(PlaylistDB).order_by(desc(PlaylistDB.created_at)).limit(limit)
        )
        return list(result.scalars().all())

    async def get_playlists_by_size_range(
        self, session: AsyncSession, min_videos: int, max_videos: int
    ) -> list[PlaylistDB]:
        """Get playlists within a specific video count range."""
        result = await session.execute(
            select(PlaylistDB)
            .where(
                and_(
                    PlaylistDB.video_count >= min_videos,
                    PlaylistDB.video_count <= max_videos,
                )
            )
            .order_by(desc(PlaylistDB.video_count))
        )
        return list(result.scalars().all())

    async def get_playlist_statistics(
        self, session: AsyncSession
    ) -> PlaylistStatistics:
        """Get comprehensive playlist statistics."""
        # Basic counts
        total_result = await session.execute(
            select(
                func.count(PlaylistDB.playlist_id).label("total_playlists"),
                func.sum(PlaylistDB.video_count).label("total_videos"),
                func.avg(PlaylistDB.video_count).label("avg_videos_per_playlist"),
                func.count(func.distinct(PlaylistDB.channel_id)).label(
                    "unique_channels"
                ),
                func.sum(
                    case(
                        (
                            and_(
                                PlaylistDB.description.is_not(None),
                                PlaylistDB.description != "",
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("playlists_with_descriptions"),
            )
        )

        stats = total_result.first()
        if not stats:
            return PlaylistStatistics(
                total_playlists=0,
                total_videos=0,
                avg_videos_per_playlist=0.0,
                unique_channels=0,
                playlists_with_descriptions=0,
            )

        # Privacy distribution
        privacy_result = await session.execute(
            select(
                PlaylistDB.privacy_status, func.count(PlaylistDB.playlist_id)
            ).group_by(PlaylistDB.privacy_status)
        )
        privacy_distribution = {row[0]: row[1] for row in privacy_result}

        # Language distribution
        language_result = await session.execute(
            select(PlaylistDB.default_language, func.count(PlaylistDB.playlist_id))
            .where(PlaylistDB.default_language.is_not(None))
            .group_by(PlaylistDB.default_language)
        )
        language_distribution = {str(row[0]): row[1] for row in language_result}

        # Top channels by playlist count
        channels_result = await session.execute(
            select(PlaylistDB.channel_id, func.count(PlaylistDB.playlist_id))
            .group_by(PlaylistDB.channel_id)
            .order_by(func.count(PlaylistDB.playlist_id).desc())
            .limit(10)
        )
        top_channels_by_playlists = [(row[0], row[1]) for row in channels_result]

        # Playlist size distribution
        size_distribution = {}
        size_ranges = [
            ("0-5", 0, 5),
            ("6-15", 6, 15),
            ("16-50", 16, 50),
            ("51-100", 51, 100),
            ("100+", 101, float("inf")),
        ]

        for range_name, min_size, max_size in size_ranges:
            if max_size == float("inf"):
                count_result = await session.execute(
                    select(func.count(PlaylistDB.playlist_id)).where(
                        PlaylistDB.video_count >= min_size
                    )
                )
            else:
                count_result = await session.execute(
                    select(func.count(PlaylistDB.playlist_id)).where(
                        and_(
                            PlaylistDB.video_count >= min_size,
                            PlaylistDB.video_count <= max_size,
                        )
                    )
                )
            size_distribution[range_name] = count_result.scalar() or 0

        return PlaylistStatistics(
            total_playlists=int(stats.total_playlists or 0),
            total_videos=int(stats.total_videos or 0),
            avg_videos_per_playlist=float(stats.avg_videos_per_playlist or 0.0),
            unique_channels=int(stats.unique_channels or 0),
            privacy_distribution=privacy_distribution,
            language_distribution=language_distribution,
            top_channels_by_playlists=top_channels_by_playlists,
            playlist_size_distribution=size_distribution,
            playlists_with_descriptions=int(stats.playlists_with_descriptions or 0),
        )

    async def get_channel_playlist_count(
        self, session: AsyncSession, channel_id: str
    ) -> int:
        """Get the number of playlists for a specific channel."""
        result = await session.execute(
            select(func.count(PlaylistDB.playlist_id)).where(
                PlaylistDB.channel_id == channel_id
            )
        )
        return result.scalar() or 0

    async def get_playlists_by_multiple_channels(
        self, session: AsyncSession, channel_ids: list[str]
    ) -> dict[str, list[PlaylistDB]]:
        """Get playlists for multiple channels efficiently."""
        if not channel_ids:
            return {}

        result = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.channel_id.in_(channel_ids))
            .order_by(PlaylistDB.channel_id, PlaylistDB.created_at.desc())
        )

        # Group playlists by channel_id
        # Note: All results have non-null channel_id due to the WHERE IN clause
        channel_playlists: dict[str, list[PlaylistDB]] = {}
        for playlist in result.scalars().all():
            if playlist.channel_id is None:
                continue  # Skip playlists without channel_id (shouldn't happen due to query)
            if playlist.channel_id not in channel_playlists:
                channel_playlists[playlist.channel_id] = []
            channel_playlists[playlist.channel_id].append(playlist)

        return channel_playlists

    async def bulk_create_playlists(
        self, session: AsyncSession, playlists: list[PlaylistCreate]
    ) -> list[PlaylistDB]:
        """Create multiple playlists efficiently."""
        created_playlists = []

        for playlist_create in playlists:
            # Check if playlist already exists
            existing = await self.get_by_playlist_id(
                session, playlist_create.playlist_id
            )
            if not existing:
                playlist = await self.create(session, obj_in=playlist_create)
                created_playlists.append(playlist)
            else:
                created_playlists.append(existing)

        return created_playlists

    async def bulk_update_video_counts(
        self, session: AsyncSession, playlist_counts: dict[str, int]
    ) -> int:
        """Bulk update video counts for multiple playlists."""
        updated_count = 0

        for playlist_id, new_count in playlist_counts.items():
            playlist = await self.get_by_playlist_id(session, playlist_id)
            if playlist and playlist.video_count != new_count:
                update_data = PlaylistUpdate(
                    title=None,
                    description=None,
                    default_language=None,
                    privacy_status=None,
                    video_count=new_count,
                )
                await self.update(session, db_obj=playlist, obj_in=update_data)
                updated_count += 1

        return updated_count

    async def delete_by_playlist_id(
        self, session: AsyncSession, playlist_id: str
    ) -> PlaylistDB | None:
        """Delete playlist by playlist ID."""
        playlist = await self.get_by_playlist_id(session, playlist_id)
        if playlist:
            await session.delete(playlist)
            await session.flush()
        return playlist

    async def delete_by_channel_id(self, session: AsyncSession, channel_id: str) -> int:
        """Delete all playlists for a specific channel."""
        # Get count first
        count_result = await session.execute(
            select(func.count(PlaylistDB.playlist_id)).where(
                PlaylistDB.channel_id == channel_id
            )
        )
        count = count_result.scalar() or 0

        # Delete playlists
        playlists = await self.get_by_channel_id(session, channel_id, limit=1000)
        for playlist in playlists:
            await session.delete(playlist)

        await session.flush()
        return count

    async def delete_by_null_channel_id(self, session: AsyncSession) -> int:
        """
        Delete all playlists with NULL channel_id (user playlists from Takeout).

        This is used during re-seeding to clear user playlists before importing
        fresh data. Playlist memberships are automatically deleted via CASCADE.

        Parameters
        ----------
        session : AsyncSession
            Database session.

        Returns
        -------
        int
            Number of playlists deleted.
        """
        # Get count first
        count_result = await session.execute(
            select(func.count(PlaylistDB.playlist_id)).where(
                PlaylistDB.channel_id.is_(None)
            )
        )
        count = count_result.scalar() or 0

        # Delete playlists with NULL channel_id
        result = await session.execute(
            select(PlaylistDB).where(PlaylistDB.channel_id.is_(None))
        )
        playlists = list(result.scalars().all())
        for playlist in playlists:
            await session.delete(playlist)

        await session.flush()
        return count

    async def get_unlinked_playlists(
        self, session: AsyncSession, skip: int = 0, limit: int = 100
    ) -> list[PlaylistDB]:
        """
        Get playlists with internal IDs (not linked to YouTube).

        Parameters
        ----------
        session : AsyncSession
            Database session.
        skip : int, optional
            Number of records to skip. Default 0.
        limit : int, optional
            Maximum records to return. Default 100.

        Returns
        -------
        List[PlaylistDB]
            Playlists with int_ prefix (internal IDs), ordered by title.
        """
        result = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.playlist_id.startswith("int_"))
            .order_by(PlaylistDB.title)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_linked_playlists(
        self, session: AsyncSession, skip: int = 0, limit: int = 100
    ) -> list[PlaylistDB]:
        """
        Get playlists with YouTube IDs (linked to YouTube).

        Parameters
        ----------
        session : AsyncSession
            Database session.
        skip : int, optional
            Number of records to skip. Default 0.
        limit : int, optional
            Maximum records to return. Default 100.

        Returns
        -------
        List[PlaylistDB]
            Playlists with PL prefix or system IDs (LL, WL, HL), ordered by title.
        """
        result = await session.execute(
            select(PlaylistDB)
            .where(
                or_(
                    PlaylistDB.playlist_id.startswith("PL"),
                    PlaylistDB.playlist_id.in_(["LL", "WL", "HL"]),
                )
            )
            .order_by(PlaylistDB.title)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_link_statistics(self, session: AsyncSession) -> dict[str, int]:
        """
        Get statistics about playlist linking.

        Parameters
        ----------
        session : AsyncSession
            Database session.

        Returns
        -------
        Dict[str, int]
            Statistics with keys:
            - total_playlists: Total number of playlists
            - linked_playlists: Playlists with YouTube IDs (PL, LL, WL, HL)
            - unlinked_playlists: Playlists with internal IDs (int_)
        """
        # Get total count
        total_result = await session.execute(select(func.count(PlaylistDB.playlist_id)))
        total_playlists = total_result.scalar() or 0

        # Get linked count (YouTube IDs)
        linked_result = await session.execute(
            select(func.count(PlaylistDB.playlist_id)).where(
                or_(
                    PlaylistDB.playlist_id.startswith("PL"),
                    PlaylistDB.playlist_id.in_(["LL", "WL", "HL"]),
                )
            )
        )
        linked_playlists = linked_result.scalar() or 0

        # Calculate unlinked
        unlinked_playlists = total_playlists - linked_playlists

        return {
            "total_playlists": total_playlists,
            "linked_playlists": linked_playlists,
            "unlinked_playlists": unlinked_playlists,
        }

    async def find_similar_playlists(
        self, session: AsyncSession, playlist_id: str, limit: int = 10
    ) -> list[tuple[PlaylistDB, float]]:
        """Find playlists similar to the given playlist based on title and description."""
        target_playlist = await self.get_by_playlist_id(session, playlist_id)
        if not target_playlist:
            return []

        # Simple similarity based on title words
        # In a real implementation, you'd use more sophisticated text similarity
        title_words = set(target_playlist.title.lower().split())

        if len(title_words) == 0:
            return []

        # Find playlists with similar titles
        all_playlists = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.playlist_id != playlist_id)
            .limit(100)  # Limit search space for performance
        )

        similar_playlists = []
        for playlist in all_playlists.scalars().all():
            other_title_words = set(playlist.title.lower().split())
            if other_title_words:
                # Simple Jaccard similarity
                intersection = len(title_words.intersection(other_title_words))
                union = len(title_words.union(other_title_words))
                similarity = intersection / union if union > 0 else 0.0

                if similarity > 0.1:  # Minimum similarity threshold
                    similar_playlists.append((playlist, similarity))

        # Sort by similarity score and return top results
        similar_playlists.sort(key=lambda x: x[1], reverse=True)
        return similar_playlists[:limit]

    async def get_playlist_analytics(self, session: AsyncSession) -> PlaylistAnalytics:
        """Get advanced playlist analytics."""
        # Creation trends by month
        creation_trends_result = await session.execute(
            select(
                func.to_char(PlaylistDB.created_at, "YYYY-MM").label("month"),
                func.count(PlaylistDB.playlist_id).label("count"),
            )
            .group_by(func.to_char(PlaylistDB.created_at, "YYYY-MM"))
            .order_by(func.to_char(PlaylistDB.created_at, "YYYY-MM"))
        )

        creation_trends = {"monthly_counts": [row[1] for row in creation_trends_result]}

        # Content analysis - basic statistics
        content_analysis = {
            "avg_title_length": 0.0,
            "playlists_with_descriptions": 0,
            "most_common_words": [],
        }

        # Get average title length
        avg_title_result = await session.execute(
            select(func.avg(func.length(PlaylistDB.title)))
        )
        avg_title_length = avg_title_result.scalar()
        if avg_title_length:
            content_analysis["avg_title_length"] = float(avg_title_length)

        # Count playlists with descriptions
        desc_count_result = await session.execute(
            select(func.count(PlaylistDB.playlist_id)).where(
                and_(
                    PlaylistDB.description.is_not(None),
                    PlaylistDB.description != "",
                )
            )
        )
        content_analysis["playlists_with_descriptions"] = (
            desc_count_result.scalar() or 0
        )

        # Engagement metrics (simplified - would need actual engagement data)
        engagement_metrics = {
            "avg_videos_per_playlist": 0.0,
            "playlist_creation_rate": 0.0,
        }

        # Get average videos per playlist
        avg_videos_result = await session.execute(
            select(func.avg(PlaylistDB.video_count))
        )
        avg_videos = avg_videos_result.scalar()
        if avg_videos:
            engagement_metrics["avg_videos_per_playlist"] = float(avg_videos)

        # Simple similarity clusters (placeholder)
        similarity_clusters = [
            {
                "cluster_id": "music",
                "playlists": [],
                "common_themes": ["music", "songs", "playlist"],
            },
            {
                "cluster_id": "educational",
                "playlists": [],
                "common_themes": ["tutorial", "learn", "course"],
            },
        ]

        return PlaylistAnalytics(
            creation_trends=creation_trends,
            content_analysis=content_analysis,
            engagement_metrics=engagement_metrics,
            similarity_clusters=similarity_clusters,
        )
