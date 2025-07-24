"""
Channel repository for YouTube channel management.

Handles CRUD operations and queries for YouTube channels with subscription tracking.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.db.models import Channel as ChannelDB
from chronovista.models.channel import (
    ChannelCreate,
    ChannelSearchFilters,
    ChannelStatistics,
    ChannelUpdate,
)
from chronovista.models.youtube_types import ChannelId
from chronovista.repositories.base import BaseSQLAlchemyRepository


class ChannelRepository(
    BaseSQLAlchemyRepository[
        ChannelDB,
        ChannelCreate,
        ChannelUpdate,
    ]
):
    """Repository for YouTube channel management with subscription tracking."""

    def __init__(self) -> None:
        """Initialize repository with Channel model."""
        super().__init__(ChannelDB)

    async def get(self, session: AsyncSession, id: ChannelId) -> Optional[ChannelDB]:
        """Get channel by channel_id (primary key)."""
        return await self.get_by_channel_id(session, id)

    async def exists(self, session: AsyncSession, id: ChannelId) -> bool:
        """Check if channel exists by channel_id."""
        return await self.exists_by_channel_id(session, id)

    async def get_by_channel_id(
        self, session: AsyncSession, channel_id: ChannelId
    ) -> Optional[ChannelDB]:
        """
        Get channel by YouTube channel ID.

        Parameters
        ----------
        session : AsyncSession
            Database session
        channel_id : str
            YouTube channel identifier

        Returns
        -------
        Optional[ChannelDB]
            Channel if found, None otherwise
        """
        result = await session.execute(
            select(ChannelDB).where(ChannelDB.channel_id == channel_id)
        )
        return result.scalar_one_or_none()

    async def exists_by_channel_id(
        self, session: AsyncSession, channel_id: ChannelId
    ) -> bool:
        """
        Check if channel exists by channel ID.

        Parameters
        ----------
        session : AsyncSession
            Database session
        channel_id : str
            YouTube channel identifier

        Returns
        -------
        bool
            True if channel exists, False otherwise
        """
        result = await session.execute(
            select(ChannelDB.channel_id).where(ChannelDB.channel_id == channel_id)
        )
        return result.first() is not None

    async def find_by_title(self, session: AsyncSession, title: str) -> List[ChannelDB]:
        """
        Find channels by title (case-insensitive search).

        Parameters
        ----------
        session : AsyncSession
            Database session
        title : str
            Title search term

        Returns
        -------
        List[ChannelDB]
            List of matching channels ordered by title
        """
        result = await session.execute(
            select(ChannelDB)
            .where(ChannelDB.title.ilike(f"%{title}%"))
            .order_by(ChannelDB.title)
        )
        return list(result.scalars().all())

    async def find_by_language(
        self, session: AsyncSession, language: str
    ) -> List[ChannelDB]:
        """
        Find channels by default language.

        Parameters
        ----------
        session : AsyncSession
            Database session
        language : str
            Language code (BCP-47)

        Returns
        -------
        List[ChannelDB]
            List of channels ordered by subscriber count
        """
        result = await session.execute(
            select(ChannelDB)
            .where(ChannelDB.default_language == language.lower())
            .order_by(ChannelDB.subscriber_count.desc().nulls_last())
        )
        return list(result.scalars().all())

    async def find_by_country(
        self, session: AsyncSession, country: str
    ) -> List[ChannelDB]:
        """
        Find channels by country.

        Parameters
        ----------
        session : AsyncSession
            Database session
        country : str
            Country code (ISO 3166-1)

        Returns
        -------
        List[ChannelDB]
            List of channels ordered by subscriber count
        """
        result = await session.execute(
            select(ChannelDB)
            .where(ChannelDB.country == country.upper())
            .order_by(ChannelDB.subscriber_count.desc().nulls_last())
        )
        return list(result.scalars().all())

    async def get_with_videos(
        self, session: AsyncSession, channel_id: ChannelId
    ) -> Optional[ChannelDB]:
        """
        Get channel with all associated videos loaded.

        Parameters
        ----------
        session : AsyncSession
            Database session
        channel_id : str
            YouTube channel identifier

        Returns
        -------
        Optional[ChannelDB]
            Channel with videos loaded if found
        """
        result = await session.execute(
            select(ChannelDB)
            .options(selectinload(ChannelDB.videos))
            .where(ChannelDB.channel_id == channel_id)
        )
        return result.scalar_one_or_none()

    async def get_with_keywords(
        self, session: AsyncSession, channel_id: ChannelId
    ) -> Optional[ChannelDB]:
        """
        Get channel with all keywords loaded.

        Parameters
        ----------
        session : AsyncSession
            Database session
        channel_id : str
            YouTube channel identifier

        Returns
        -------
        Optional[ChannelDB]
            Channel with keywords loaded if found
        """
        result = await session.execute(
            select(ChannelDB)
            .options(selectinload(ChannelDB.keywords))
            .where(ChannelDB.channel_id == channel_id)
        )
        return result.scalar_one_or_none()

    async def search_channels(
        self, session: AsyncSession, filters: ChannelSearchFilters
    ) -> List[ChannelDB]:
        """
        Search channels with advanced filtering.

        Parameters
        ----------
        session : AsyncSession
            Database session
        filters : ChannelSearchFilters
            Search filters to apply

        Returns
        -------
        List[ChannelDB]
            List of matching channels
        """
        query = select(ChannelDB)
        conditions: List[Any] = []

        # Text search in title
        if filters.title_query:
            conditions.append(ChannelDB.title.ilike(f"%{filters.title_query}%"))

        # Text search in description
        if filters.description_query:
            conditions.append(
                ChannelDB.description.ilike(f"%{filters.description_query}%")
            )

        # Language filters
        if filters.language_codes:
            language_conditions = [
                ChannelDB.default_language == lang.lower()
                for lang in filters.language_codes
            ]
            conditions.append(or_(*language_conditions))

        # Country filters
        if filters.countries:
            country_conditions = [
                ChannelDB.country == country.upper() for country in filters.countries
            ]
            conditions.append(or_(*country_conditions))

        # Subscriber count filters
        if filters.min_subscriber_count is not None:
            conditions.append(
                ChannelDB.subscriber_count >= filters.min_subscriber_count
            )

        if filters.max_subscriber_count is not None:
            conditions.append(
                ChannelDB.subscriber_count <= filters.max_subscriber_count
            )

        # Video count filters
        if filters.min_video_count is not None:
            conditions.append(ChannelDB.video_count >= filters.min_video_count)

        if filters.max_video_count is not None:
            conditions.append(ChannelDB.video_count <= filters.max_video_count)

        # Keywords filter
        if filters.has_keywords is not None:
            if filters.has_keywords:
                # Has keywords - use exists subquery
                from chronovista.db.models import ChannelKeyword

                keyword_exists = (
                    select(ChannelKeyword.channel_id)
                    .where(ChannelKeyword.channel_id == ChannelDB.channel_id)
                    .exists()
                )
                conditions.append(keyword_exists)
            else:
                # No keywords - use not exists
                from chronovista.db.models import ChannelKeyword

                keyword_exists = (
                    select(ChannelKeyword.channel_id)
                    .where(ChannelKeyword.channel_id == ChannelDB.channel_id)
                    .exists()
                )
                conditions.append(~keyword_exists)

        # Apply all conditions
        if conditions:
            query = query.where(and_(*conditions))

        # Default ordering by subscriber count
        query = query.order_by(ChannelDB.subscriber_count.desc().nulls_last())

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_top_channels_by_subscribers(
        self, session: AsyncSession, limit: int = 10
    ) -> List[ChannelDB]:
        """
        Get top channels by subscriber count.

        Parameters
        ----------
        session : AsyncSession
            Database session
        limit : int
            Maximum number of results to return

        Returns
        -------
        List[ChannelDB]
            List of top channels by subscriber count
        """
        result = await session.execute(
            select(ChannelDB)
            .where(ChannelDB.subscriber_count.is_not(None))
            .order_by(ChannelDB.subscriber_count.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_or_update(
        self, session: AsyncSession, channel_data: ChannelCreate
    ) -> ChannelDB:
        """
        Create a new channel or update existing one.

        Parameters
        ----------
        session : AsyncSession
            Database session
        channel_data : ChannelCreate
            Channel data to create or update

        Returns
        -------
        ChannelDB
            Created or updated channel
        """
        existing = await self.get_by_channel_id(session, channel_data.channel_id)

        if existing:
            # Update existing channel
            update_data = ChannelUpdate(
                title=channel_data.title,
                description=channel_data.description,
                subscriber_count=channel_data.subscriber_count,
                video_count=channel_data.video_count,
                default_language=channel_data.default_language,
                country=channel_data.country,
                thumbnail_url=channel_data.thumbnail_url,
            )
            return await self.update(session, db_obj=existing, obj_in=update_data)
        else:
            # Create new channel
            return await self.create(session, obj_in=channel_data)

    async def get_channel_statistics(self, session: AsyncSession) -> ChannelStatistics:
        """
        Get comprehensive channel statistics.

        Parameters
        ----------
        session : AsyncSession
            Database session

        Returns
        -------
        ChannelStatistics
            Channel statistics summary
        """
        # Get basic counts and aggregates
        result = await session.execute(
            select(
                func.count(ChannelDB.channel_id).label("total_channels"),
                func.sum(ChannelDB.subscriber_count).label("total_subscribers"),
                func.sum(ChannelDB.video_count).label("total_videos"),
                func.avg(ChannelDB.subscriber_count).label("avg_subscribers"),
                func.avg(ChannelDB.video_count).label("avg_videos"),
            )
        )

        stats_row = result.first()
        if not stats_row:
            return ChannelStatistics(
                total_channels=0,
                total_subscribers=0,
                total_videos=0,
                avg_subscribers_per_channel=0.0,
                avg_videos_per_channel=0.0,
                top_countries=[],
                top_languages=[],
            )

        # Get top countries
        country_result = await session.execute(
            select(ChannelDB.country, func.count().label("count"))
            .where(ChannelDB.country.is_not(None))
            .group_by(ChannelDB.country)
            .order_by(func.count().desc())
            .limit(10)
        )
        top_countries = [(str(row[0]), int(row[1])) for row in country_result]

        # Get top languages
        language_result = await session.execute(
            select(ChannelDB.default_language, func.count().label("count"))
            .where(ChannelDB.default_language.is_not(None))
            .group_by(ChannelDB.default_language)
            .order_by(func.count().desc())
            .limit(10)
        )
        top_languages = [(str(row[0]), int(row[1])) for row in language_result]

        return ChannelStatistics(
            total_channels=int(stats_row.total_channels or 0),
            total_subscribers=int(stats_row.total_subscribers or 0),
            total_videos=int(stats_row.total_videos or 0),
            avg_subscribers_per_channel=float(stats_row.avg_subscribers or 0.0),
            avg_videos_per_channel=float(stats_row.avg_videos or 0.0),
            top_countries=top_countries,
            top_languages=top_languages,
        )
