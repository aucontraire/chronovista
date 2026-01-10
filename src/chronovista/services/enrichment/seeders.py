"""
Seeders for pre-populating reference data in the database.

This module provides seeder classes for YouTube reference data:
- TopicSeeder: Seeds the ~55 official YouTube topic categories (hardcoded hierarchy)
- CategorySeeder: Seeds YouTube video categories from API across multiple regions

These seeders support idempotent operations with optional force flag for re-seeding.

Reference:
- Topics: https://developers.google.com/youtube/v3/docs/videos#topicDetails.topicCategories[0]
- Categories: https://developers.google.com/youtube/v3/docs/videoCategories/list
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TopicCategory as TopicCategoryDB
from chronovista.exceptions import YouTubeAPIError
from chronovista.models.api_responses import YouTubeVideoCategoryResponse
from chronovista.models.enums import TopicType
from chronovista.models.topic_category import TopicCategoryCreate
from chronovista.models.video_category import VideoCategoryCreate
from chronovista.repositories.topic_category_repository import TopicCategoryRepository
from chronovista.repositories.video_category_repository import VideoCategoryRepository
from chronovista.services.youtube_service import YouTubeService

logger = logging.getLogger(__name__)


class TopicSeedResult(BaseModel):
    """Result of a topic seeding operation."""

    created: int = Field(default=0, description="Number of topics created")
    skipped: int = Field(
        default=0, description="Number of topics skipped (already exist)"
    )
    deleted: int = Field(default=0, description="Number of topics deleted (force mode)")
    failed: int = Field(default=0, description="Number of topics that failed to seed")
    duration_seconds: float = Field(
        default=0.0, description="Duration of seeding operation"
    )
    errors: list[str] = Field(
        default_factory=list, description="List of error messages"
    )

    @property
    def total_processed(self) -> int:
        """Total items processed."""
        return self.created + self.skipped + self.failed

    @property
    def success_rate(self) -> float:
        """Success rate percentage."""
        if self.total_processed == 0:
            return 100.0
        return ((self.created + self.skipped) / self.total_processed) * 100.0


class CategorySeedResult(BaseModel):
    """Result of a category seeding operation with quota tracking."""

    created: int = Field(default=0, description="Number of categories created")
    skipped: int = Field(
        default=0, description="Number of categories skipped (already exist)"
    )
    deleted: int = Field(
        default=0, description="Number of categories deleted (force mode)"
    )
    failed: int = Field(
        default=0, description="Number of categories that failed to seed"
    )
    duration_seconds: float = Field(
        default=0.0, description="Duration of seeding operation"
    )
    quota_used: int = Field(default=0, description="YouTube API quota units consumed")
    errors: list[str] = Field(
        default_factory=list, description="List of error messages"
    )

    @property
    def total_processed(self) -> int:
        """Total items processed."""
        return self.created + self.skipped + self.failed

    @property
    def success_rate(self) -> float:
        """Success rate percentage."""
        if self.total_processed == 0:
            return 100.0
        return ((self.created + self.skipped) / self.total_processed) * 100.0


class TopicSeeder:
    """
    Seeds YouTube topic categories into the database.

    This seeder populates the topic_categories table with the official YouTube
    topic taxonomy. The hierarchy consists of 7 parent categories and their
    child categories, totaling approximately 55 topics.

    All seeded topics use topic_type = TopicType.YOUTUBE to distinguish them
    from user-defined custom topics.

    Attributes
    ----------
    topic_repository : TopicCategoryRepository
        Repository for topic category database operations.

    Examples
    --------
    >>> seeder = TopicSeeder(TopicCategoryRepository())
    >>> async with session_maker() as session:
    ...     result = await seeder.seed(session)
    ...     print(f"Created {result.created} topics")
    """

    # YouTube Topic Hierarchy
    # Format: topic_id -> (category_name, parent_topic_id)
    # Parent topics have None as parent_topic_id
    YOUTUBE_TOPICS: dict[str, tuple[str, Optional[str]]] = {
        # =================================================================
        # PARENT TOPICS (7 root categories)
        # =================================================================
        "/m/04rlf": ("Music", None),
        "/m/0bzvm2": ("Gaming", None),
        "/m/06ntj": ("Sports", None),
        "/m/02jjt": ("Entertainment", None),
        "/m/019_rr": ("Lifestyle", None),
        "/m/01k8wb": ("Knowledge", None),
        "/m/098wr": ("Society", None),
        # =================================================================
        # MUSIC CHILDREN (14 subcategories)
        # =================================================================
        "/m/02lkt": ("Christian music", "/m/04rlf"),
        "/m/0ggq0m": ("Classical music", "/m/04rlf"),
        "/m/01lyv": ("Country music", "/m/04rlf"),
        "/m/02mscn": ("Electronic music", "/m/04rlf"),
        "/m/0glt670": ("Hip hop music", "/m/04rlf"),
        "/m/05rwpb": ("Independent music", "/m/04rlf"),
        "/m/03_d0": ("Jazz", "/m/04rlf"),
        "/m/028sqc": ("Music of Asia", "/m/04rlf"),
        "/m/0g293": ("Music of Latin America", "/m/04rlf"),
        "/m/064t9": ("Pop music", "/m/04rlf"),
        "/m/06cqb": ("Reggae", "/m/04rlf"),
        "/m/06j6l": ("Rhythm and blues", "/m/04rlf"),
        "/m/06by7": ("Rock music", "/m/04rlf"),
        "/m/0dl5d": ("Soul music", "/m/04rlf"),
        # =================================================================
        # GAMING CHILDREN (10 subcategories)
        # =================================================================
        "/m/0403l3g": ("Action game", "/m/0bzvm2"),
        "/m/021bp2": ("Action-adventure game", "/m/0bzvm2"),
        "/m/022dc6": ("Casual game", "/m/0bzvm2"),
        "/m/03hf_rm": ("Music video game", "/m/0bzvm2"),
        "/m/04q1x3q": ("Puzzle video game", "/m/0bzvm2"),
        "/m/01sjng": ("Racing video game", "/m/0bzvm2"),
        "/m/0403zg": ("Role-playing video game", "/m/0bzvm2"),
        "/m/021bms": ("Simulation video game", "/m/0bzvm2"),
        "/m/022lj": ("Strategy video game", "/m/0bzvm2"),
        "/m/03npn": ("Sports game", "/m/0bzvm2"),
        # =================================================================
        # SPORTS CHILDREN (13 subcategories)
        # =================================================================
        "/m/0jm_": ("American football", "/m/06ntj"),
        "/m/018jz": ("Baseball", "/m/06ntj"),
        "/m/018w8": ("Basketball", "/m/06ntj"),
        "/m/01cgz": ("Boxing", "/m/06ntj"),
        "/m/09xp_": ("Cricket", "/m/06ntj"),
        "/m/02vx4": ("Football", "/m/06ntj"),  # Soccer
        "/m/037hz": ("Golf", "/m/06ntj"),
        "/m/03tmr": ("Ice hockey", "/m/06ntj"),
        "/m/01h7lh": ("Mixed martial arts", "/m/06ntj"),
        "/m/0410tth": ("Motorsport", "/m/06ntj"),
        "/m/07bs0": ("Tennis", "/m/06ntj"),
        "/m/07_53": ("Volleyball", "/m/06ntj"),
        "/m/09_bl": ("Wrestling", "/m/06ntj"),
        # =================================================================
        # ENTERTAINMENT CHILDREN (5 subcategories)
        # =================================================================
        "/m/09kqc": ("Humor", "/m/02jjt"),
        "/m/02vxn": ("Movies", "/m/02jjt"),
        "/m/05qjc": ("Performing arts", "/m/02jjt"),
        "/m/066wd": ("Professional wrestling", "/m/02jjt"),
        "/m/0f2f9": ("TV shows", "/m/02jjt"),
        # =================================================================
        # LIFESTYLE CHILDREN (9 subcategories)
        # =================================================================
        "/m/032tl": ("Fashion", "/m/019_rr"),
        "/m/027x7n": ("Fitness", "/m/019_rr"),
        "/m/02wbm": ("Food", "/m/019_rr"),
        "/m/03glg": ("Hobby", "/m/019_rr"),
        "/m/068hy": ("Pets", "/m/019_rr"),
        "/m/041xxh": ("Physical attractiveness [Beauty]", "/m/019_rr"),
        "/m/07c1v": ("Technology", "/m/019_rr"),
        "/m/07bxq": ("Tourism", "/m/019_rr"),
        "/m/0kt51": ("Vehicles", "/m/019_rr"),
        # =================================================================
        # KNOWLEDGE CHILDREN - None (leaf category)
        # =================================================================
        # SOCIETY CHILDREN - None (leaf category)
        # =================================================================
    }

    # Topic IDs for parent categories (for easy reference)
    PARENT_TOPIC_IDS: frozenset[str] = frozenset(
        [
            "/m/04rlf",  # Music
            "/m/0bzvm2",  # Gaming
            "/m/06ntj",  # Sports
            "/m/02jjt",  # Entertainment
            "/m/019_rr",  # Lifestyle
            "/m/01k8wb",  # Knowledge
            "/m/098wr",  # Society
        ]
    )

    def __init__(self, topic_repository: TopicCategoryRepository) -> None:
        """
        Initialize the TopicSeeder.

        Parameters
        ----------
        topic_repository : TopicCategoryRepository
            Repository for topic category database operations.
        """
        self.topic_repository = topic_repository

    async def seed(
        self,
        session: AsyncSession,
        force: bool = False,
    ) -> TopicSeedResult:
        """
        Seed YouTube topics into the database.

        This method seeds the official YouTube topic hierarchy. By default, it
        performs idempotent seeding (skips existing topics). When force=True,
        it deletes all existing YouTube topics and re-seeds them.

        Parameters
        ----------
        session : AsyncSession
            SQLAlchemy async session for database operations.
        force : bool, optional
            If True, delete all existing YouTube topics and re-seed.
            Default is False (idempotent seeding).

        Returns
        -------
        TopicSeedResult
            Result containing counts of created, skipped, deleted, and failed topics.

        Examples
        --------
        >>> result = await seeder.seed(session)
        >>> print(f"Created: {result.created}, Skipped: {result.skipped}")

        >>> result = await seeder.seed(session, force=True)
        >>> print(f"Deleted: {result.deleted}, Created: {result.created}")
        """
        start_time = time.time()
        result = TopicSeedResult()

        logger.info("Starting YouTube topic seeding...")

        try:
            # Handle force mode: delete all existing YouTube topics
            if force:
                deleted_count = await self._delete_all_youtube_topics(session)
                result.deleted = deleted_count
                logger.info(
                    f"Force mode: Deleted {deleted_count} existing YouTube topics"
                )

            # Seed topics in dependency order (parents first, then children)
            await self._seed_parent_topics(session, result)
            await self._seed_child_topics(session, result)

            # Commit all changes
            await session.commit()

            result.duration_seconds = time.time() - start_time

            logger.info(
                f"YouTube topic seeding complete: "
                f"{result.created} created, {result.skipped} skipped, "
                f"{result.deleted} deleted, {result.failed} failed "
                f"in {result.duration_seconds:.2f}s"
            )

        except Exception as e:
            logger.error(f"Topic seeding failed: {e}")
            result.errors.append(f"Seeding failed: {str(e)}")
            result.failed += 1
            await session.rollback()

        return result

    async def _delete_all_youtube_topics(self, session: AsyncSession) -> int:
        """
        Delete all YouTube topics from the database.

        This is used in force mode to clear existing topics before re-seeding.
        Child topics are deleted first due to foreign key constraints.

        Parameters
        ----------
        session : AsyncSession
            SQLAlchemy async session.

        Returns
        -------
        int
            Number of topics deleted.
        """
        # Delete child topics first (foreign key constraint)
        child_delete = delete(TopicCategoryDB).where(
            TopicCategoryDB.topic_type == TopicType.YOUTUBE.value,
            TopicCategoryDB.parent_topic_id.is_not(None),
        )
        child_result = await session.execute(child_delete)
        child_count = child_result.rowcount

        # Delete parent topics
        parent_delete = delete(TopicCategoryDB).where(
            TopicCategoryDB.topic_type == TopicType.YOUTUBE.value,
            TopicCategoryDB.parent_topic_id.is_(None),
        )
        parent_result = await session.execute(parent_delete)
        parent_count = parent_result.rowcount

        await session.flush()

        return child_count + parent_count

    async def _seed_parent_topics(
        self,
        session: AsyncSession,
        result: TopicSeedResult,
    ) -> None:
        """
        Seed parent (root) topics first.

        Parameters
        ----------
        session : AsyncSession
            SQLAlchemy async session.
        result : TopicSeedResult
            Result object to update with counts.
        """
        parent_topics = [
            (topic_id, name, parent_id)
            for topic_id, (name, parent_id) in self.YOUTUBE_TOPICS.items()
            if parent_id is None
        ]

        logger.info(f"Seeding {len(parent_topics)} parent topics...")

        for topic_id, category_name, _ in parent_topics:
            await self._seed_single_topic(
                session, topic_id, category_name, None, result
            )

        await session.flush()

    async def _seed_child_topics(
        self,
        session: AsyncSession,
        result: TopicSeedResult,
    ) -> None:
        """
        Seed child topics after parents exist.

        Parameters
        ----------
        session : AsyncSession
            SQLAlchemy async session.
        result : TopicSeedResult
            Result object to update with counts.
        """
        child_topics = [
            (topic_id, name, parent_id)
            for topic_id, (name, parent_id) in self.YOUTUBE_TOPICS.items()
            if parent_id is not None
        ]

        logger.info(f"Seeding {len(child_topics)} child topics...")

        for topic_id, category_name, parent_topic_id in child_topics:
            await self._seed_single_topic(
                session, topic_id, category_name, parent_topic_id, result
            )

        await session.flush()

    async def _seed_single_topic(
        self,
        session: AsyncSession,
        topic_id: str,
        category_name: str,
        parent_topic_id: Optional[str],
        result: TopicSeedResult,
    ) -> None:
        """
        Seed a single topic, handling idempotency.

        Parameters
        ----------
        session : AsyncSession
            SQLAlchemy async session.
        topic_id : str
            The Freebase topic ID (e.g., "/m/04rlf").
        category_name : str
            Human-readable category name.
        parent_topic_id : Optional[str]
            Parent topic ID or None for root topics.
        result : TopicSeedResult
            Result object to update with counts.
        """
        try:
            # Check if topic already exists (idempotent seeding)
            existing = await self.topic_repository.exists(session, topic_id)

            if existing:
                result.skipped += 1
                logger.debug(
                    f"Topic already exists, skipping: {topic_id} ({category_name})"
                )
                return

            # Create the topic
            topic_create = TopicCategoryCreate(
                topic_id=topic_id,
                category_name=category_name,
                parent_topic_id=parent_topic_id,
                topic_type=TopicType.YOUTUBE,
            )

            await self.topic_repository.create(session, obj_in=topic_create)
            result.created += 1
            logger.debug(f"Created topic: {topic_id} ({category_name})")

        except Exception as e:
            result.failed += 1
            error_msg = f"Failed to seed topic {topic_id} ({category_name}): {str(e)}"
            result.errors.append(error_msg)
            logger.error(error_msg)

    async def get_topic_count(self, session: AsyncSession) -> int:
        """
        Get the current count of YouTube topics in the database.

        Parameters
        ----------
        session : AsyncSession
            SQLAlchemy async session.

        Returns
        -------
        int
            Number of YouTube topics currently in the database.
        """
        from sqlalchemy import func

        query = select(func.count(TopicCategoryDB.topic_id)).where(
            TopicCategoryDB.topic_type == TopicType.YOUTUBE.value
        )
        result = await session.execute(query)
        return result.scalar() or 0

    @classmethod
    def get_expected_topic_count(cls) -> int:
        """
        Get the expected number of YouTube topics.

        Returns
        -------
        int
            Total number of topics in the YOUTUBE_TOPICS dictionary.
        """
        return len(cls.YOUTUBE_TOPICS)

    @classmethod
    def get_parent_count(cls) -> int:
        """
        Get the number of parent (root) topics.

        Returns
        -------
        int
            Number of parent topics.
        """
        return len(cls.PARENT_TOPIC_IDS)

    @classmethod
    def get_child_count(cls) -> int:
        """
        Get the number of child topics.

        Returns
        -------
        int
            Number of child topics.
        """
        return cls.get_expected_topic_count() - cls.get_parent_count()

    @classmethod
    def get_topic_by_id(cls, topic_id: str) -> Optional[tuple[str, Optional[str]]]:
        """
        Get topic information by ID.

        Parameters
        ----------
        topic_id : str
            The Freebase topic ID.

        Returns
        -------
        Optional[tuple[str, Optional[str]]]
            Tuple of (category_name, parent_topic_id) or None if not found.
        """
        return cls.YOUTUBE_TOPICS.get(topic_id)

    @classmethod
    def get_topics_by_parent(cls, parent_topic_id: str) -> list[tuple[str, str]]:
        """
        Get all child topics for a given parent.

        Parameters
        ----------
        parent_topic_id : str
            The parent topic ID.

        Returns
        -------
        list[tuple[str, str]]
            List of (topic_id, category_name) tuples for children.
        """
        return [
            (topic_id, name)
            for topic_id, (name, parent_id) in cls.YOUTUBE_TOPICS.items()
            if parent_id == parent_topic_id
        ]


class CategorySeeder:
    """
    Seeds YouTube video categories from API across multiple regions.

    This seeder fetches video categories from the YouTube Data API for multiple
    regions and merges them to create a superset of all available categories.
    Category IDs are globally unique, so the same ID returns the same category
    regardless of region.

    The default regions (US, GB, JP, DE, BR, IN, MX) provide comprehensive
    coverage of categories available worldwide. The seeding operation costs
    1 API quota unit per region (7 units total for default regions).

    Attributes
    ----------
    DEFAULT_REGIONS : list[str]
        Default regions to fetch categories from: US, GB, JP, DE, BR, IN, MX
    category_repository : VideoCategoryRepository
        Repository for video category CRUD operations
    youtube_service : YouTubeService
        Service for YouTube API calls

    Examples
    --------
    >>> seeder = CategorySeeder(category_repository, youtube_service)
    >>> async with session_maker() as session:
    ...     result = await seeder.seed(session)
    ...     print(f"Created {result.created} categories, used {result.quota_used} quota")

    >>> # Force re-seeding (delete all and re-seed)
    >>> result = await seeder.seed(session, force=True)
    >>> print(f"Deleted {result.deleted}, Created {result.created}")
    """

    DEFAULT_REGIONS: list[str] = ["US", "GB", "JP", "DE", "BR", "IN", "MX"]

    def __init__(
        self,
        category_repository: VideoCategoryRepository,
        youtube_service: YouTubeService,
    ) -> None:
        """
        Initialize CategorySeeder.

        Parameters
        ----------
        category_repository : VideoCategoryRepository
            Repository for video category CRUD operations.
        youtube_service : YouTubeService
            Service for YouTube API calls.
        """
        self.category_repository = category_repository
        self.youtube_service = youtube_service

    async def seed(
        self,
        session: AsyncSession,
        regions: list[str] | None = None,
        force: bool = False,
    ) -> CategorySeedResult:
        """
        Seed video categories from YouTube API.

        Fetches categories from multiple regions and merges them to create
        a superset. Supports idempotent operation (skip existing) or
        force re-seeding (delete all and re-seed).

        Parameters
        ----------
        session : AsyncSession
            Database session for transactions.
        regions : list[str] | None, optional
            List of region codes to fetch from (defaults to DEFAULT_REGIONS).
        force : bool, optional
            If True, delete all existing categories and re-seed (default False).

        Returns
        -------
        CategorySeedResult
            Result containing created/skipped counts and quota used.

        Examples
        --------
        >>> result = await seeder.seed(session)
        >>> print(f"Created: {result.created}, Skipped: {result.skipped}")

        >>> result = await seeder.seed(session, regions=["US", "GB"])
        >>> print(f"Quota used: {result.quota_used}")

        >>> result = await seeder.seed(session, force=True)
        >>> print(f"Deleted: {result.deleted}, Created: {result.created}")
        """
        start_time = time.time()
        result = CategorySeedResult()

        regions_to_fetch = regions or self.DEFAULT_REGIONS
        logger.info(
            f"Starting category seeding for {len(regions_to_fetch)} regions: "
            f"{', '.join(regions_to_fetch)}"
        )

        try:
            # Handle force flag: delete all existing categories
            if force:
                deleted_count = await self._delete_all_categories(session)
                result.deleted = deleted_count
                logger.info(f"Force mode: Deleted {deleted_count} existing categories")

            # Fetch categories from all regions and merge
            all_categories: dict[str, VideoCategoryCreate] = {}
            for region in regions_to_fetch:
                try:
                    region_categories = await self._fetch_categories_for_region(region)
                    result.quota_used += 1  # 1 quota unit per region

                    # Merge categories (category IDs are globally unique)
                    for category in region_categories:
                        if category.category_id not in all_categories:
                            all_categories[category.category_id] = category

                    logger.info(
                        f"Fetched {len(region_categories)} categories from region {region}"
                    )

                except (ValueError, YouTubeAPIError) as e:
                    error_msg = f"Failed to fetch categories for region {region}: {e}"
                    logger.warning(error_msg)
                    result.errors.append(error_msg)
                    # Continue with other regions per FR-052 (graceful degradation)

            logger.info(
                f"Total unique categories across all regions: {len(all_categories)}"
            )

            # Seed categories to database
            for category_id, category_create in all_categories.items():
                try:
                    # Check if category already exists
                    exists = await self.category_repository.exists(session, category_id)

                    if exists and not force:
                        result.skipped += 1
                        logger.debug(f"Skipping existing category: {category_id}")
                    else:
                        # Create or update the category
                        await self.category_repository.create_or_update(
                            session, category_create
                        )
                        result.created += 1
                        logger.debug(
                            f"Created category: {category_id} - {category_create.name}"
                        )

                except Exception as e:
                    error_msg = f"Failed to seed category {category_id}: {e}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)
                    result.failed += 1

            # Commit the transaction
            await session.commit()

        except Exception as e:
            logger.error(f"Category seeding failed: {e}")
            result.errors.append(f"Seeding failed: {str(e)}")
            result.failed += 1
            await session.rollback()

        result.duration_seconds = time.time() - start_time

        logger.info(
            f"Category seeding complete: {result.created} created, "
            f"{result.skipped} skipped, {result.deleted} deleted, "
            f"{result.failed} failed, {result.quota_used} quota units used "
            f"in {result.duration_seconds:.2f}s"
        )

        return result

    async def _fetch_categories_for_region(
        self, region: str
    ) -> list[VideoCategoryCreate]:
        """
        Fetch categories from API for a single region.

        Parameters
        ----------
        region : str
            Two-character ISO 3166-1 country code (e.g., "US", "GB").

        Returns
        -------
        list[VideoCategoryCreate]
            List of video category creation objects.

        Raises
        ------
        YouTubeAPIError
            If the API call fails or returns invalid data.
        """
        try:
            # Fetch categories from YouTube API
            api_response = await self.youtube_service.get_video_categories(
                region_code=region
            )

            categories: list[VideoCategoryCreate] = []
            for item in api_response:
                category = self._transform_api_response_to_category(item)
                if category:
                    categories.append(category)

            return categories

        except YouTubeAPIError:
            raise
        except Exception as e:
            raise YouTubeAPIError(
                message=f"API call failed for region {region}: {e}",
                error_reason="categoryFetchFailed",
            ) from e

    def _transform_api_response_to_category(
        self, item: YouTubeVideoCategoryResponse | dict[str, Any]
    ) -> VideoCategoryCreate | None:
        """
        Transform API response item to VideoCategoryCreate.

        Parameters
        ----------
        item : YouTubeVideoCategoryResponse | dict[str, Any]
            API response item (Pydantic model or dict) with structure:
            {
                "id": "1",
                "snippet": {
                    "title": "Film & Animation",
                    "assignable": true
                }
            }

        Returns
        -------
        VideoCategoryCreate | None
            Video category creation object, or None if transformation fails.
        """
        try:
            # Handle both Pydantic model and dict formats
            if isinstance(item, dict):
                category_id = item.get("id")
                snippet = item.get("snippet", {})
                name = snippet.get("title") if isinstance(snippet, dict) else None
                assignable = snippet.get("assignable", True) if isinstance(snippet, dict) else True
            else:
                # Pydantic model
                category_id = item.id
                snippet = item.snippet
                name = snippet.title if snippet else None
                assignable = snippet.assignable if snippet else True

            if not category_id or not name:
                logger.warning(f"Skipping invalid category item: {item}")
                return None

            return VideoCategoryCreate(
                category_id=str(category_id),
                name=name,
                assignable=bool(assignable),
            )

        except Exception as e:
            logger.warning(f"Failed to transform category item {item}: {e}")
            return None

    async def _delete_all_categories(self, session: AsyncSession) -> int:
        """
        Delete all existing video categories.

        Parameters
        ----------
        session : AsyncSession
            Database session.

        Returns
        -------
        int
            Number of categories deleted.
        """
        # Get all categories and delete them one by one
        all_categories = await self.category_repository.get_all(session)
        deleted_count = 0

        for category in all_categories:
            await self.category_repository.delete_by_category_id(
                session, category.category_id
            )
            deleted_count += 1

        await session.flush()
        logger.info(f"Deleted {deleted_count} existing categories")
        return deleted_count

    async def get_category_count(self, session: AsyncSession) -> int:
        """
        Get the current count of video categories in the database.

        Parameters
        ----------
        session : AsyncSession
            SQLAlchemy async session.

        Returns
        -------
        int
            Number of video categories currently in the database.
        """
        categories = await self.category_repository.get_all(session)
        return len(categories)

    @classmethod
    def get_default_region_count(cls) -> int:
        """
        Get the number of default regions.

        Returns
        -------
        int
            Number of default regions for seeding.
        """
        return len(cls.DEFAULT_REGIONS)

    @classmethod
    def get_expected_quota_cost(cls, regions: list[str] | None = None) -> int:
        """
        Get the expected API quota cost for seeding.

        Parameters
        ----------
        regions : list[str] | None, optional
            List of regions to seed from (defaults to DEFAULT_REGIONS).

        Returns
        -------
        int
            Expected quota cost (1 unit per region).
        """
        return len(regions) if regions else len(cls.DEFAULT_REGIONS)
