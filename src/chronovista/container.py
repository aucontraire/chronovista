"""
Dependency Injection Container for chronovista.

This module provides a centralized container for managing dependencies across
the application. It implements a lightweight dependency injection pattern that:

- Provides factory methods for creating repository instances (transient)
- Manages singleton service instances via cached properties (future phases)
- Supports request-scoped context for API layer (future phases)
- Enables easy mock injection for testing

Usage
-----
Basic repository access:

    >>> from chronovista.container import container
    >>> video_repo = container.create_video_repository()
    >>> channel_repo = container.create_channel_repository()

Future: Wired service factories (Phase 4):

    >>> enrichment_service = container.create_enrichment_service()

Future: Singleton services (Phase 5):

    >>> youtube_service = container.youtube_service  # Cached
    >>> same_service = container.youtube_service  # Same instance

Design Principles
-----------------
- Repository factories return new instances each call (transient)
- Service singletons are cached via @cached_property (lazy initialization)
- Request context uses ContextVar for async-safe scoping
- Container can be reset for testing isolation
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Generator, Optional

from chronovista.repositories import (
    ChannelRepository,
    ChannelTopicRepository,
    PlaylistRepository,
    TopicCategoryRepository,
    UserVideoRepository,
    VideoCategoryRepository,
    VideoRepository,
    VideoTagRepository,
    VideoTopicRepository,
    VideoTranscriptRepository,
)
from chronovista.repositories.playlist_membership_repository import (
    PlaylistMembershipRepository,
)
from chronovista.services import YouTubeService
from chronovista.services.enrichment.enrichment_service import EnrichmentService
from chronovista.services.enrichment.seeders import CategorySeeder, TopicSeeder
from chronovista.services.transcript_service import TranscriptService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# Request context storage using ContextVar for async-safe scoping
_request_context: ContextVar[RequestContext | None] = ContextVar(
    "_request_context", default=None
)


@dataclass
class RequestContext:
    """
    Per-request context for API layer.

    This class holds request-scoped data that needs to be accessible
    throughout the request lifecycle, such as the database session
    and authenticated user ID.

    Attributes
    ----------
    session : AsyncSession
        The database session for the current request.
    user_id : Optional[str]
        The authenticated user ID, if available.

    Examples
    --------
    >>> context = RequestContext(session=db_session, user_id="user_123")
    >>> context.session
    <AsyncSession ...>
    >>> context.user_id
    'user_123'
    """

    session: "AsyncSession"
    user_id: Optional[str] = None


class Container:
    """
    Dependency injection container for chronovista.

    The Container provides centralized access to all repositories and services
    in the application. It manages the lifecycle of dependencies:

    - **Transient**: Repository factories create new instances each call
    - **Singleton**: Service properties return cached instances (future phases)
    - **Scoped**: Request context available during API requests (future phases)

    Examples
    --------
    Creating repositories (transient - new instance each call):

        >>> container = Container()
        >>> repo1 = container.create_video_repository()
        >>> repo2 = container.create_video_repository()
        >>> repo1 is repo2
        False

    Notes
    -----
    All repository factory methods follow the naming convention
    ``create_<entity>_repository()`` and return a new instance each call.
    This ensures no state leakage between operations.
    """

    # -------------------------------------------------------------------------
    # Repository Factory Methods (Transient - new instance per call)
    # -------------------------------------------------------------------------

    def create_video_repository(self) -> VideoRepository:
        """
        Create a new VideoRepository instance.

        Returns a fresh repository instance for video operations.
        Each call creates a new instance (transient lifecycle).

        Returns
        -------
        VideoRepository
            A new VideoRepository instance for video CRUD operations.

        Examples
        --------
        >>> repo = container.create_video_repository()
        >>> isinstance(repo, VideoRepository)
        True
        """
        return VideoRepository()

    def create_channel_repository(self) -> ChannelRepository:
        """
        Create a new ChannelRepository instance.

        Returns a fresh repository instance for channel operations.
        Each call creates a new instance (transient lifecycle).

        Returns
        -------
        ChannelRepository
            A new ChannelRepository instance for channel CRUD operations.

        Examples
        --------
        >>> repo = container.create_channel_repository()
        >>> isinstance(repo, ChannelRepository)
        True
        """
        return ChannelRepository()

    def create_playlist_repository(self) -> PlaylistRepository:
        """
        Create a new PlaylistRepository instance.

        Returns a fresh repository instance for playlist operations.
        Each call creates a new instance (transient lifecycle).

        Returns
        -------
        PlaylistRepository
            A new PlaylistRepository instance for playlist CRUD operations.

        Examples
        --------
        >>> repo = container.create_playlist_repository()
        >>> isinstance(repo, PlaylistRepository)
        True
        """
        return PlaylistRepository()

    def create_user_video_repository(self) -> UserVideoRepository:
        """
        Create a new UserVideoRepository instance.

        Returns a fresh repository instance for user-video interaction operations.
        Each call creates a new instance (transient lifecycle).

        Returns
        -------
        UserVideoRepository
            A new UserVideoRepository instance for user video CRUD operations.

        Examples
        --------
        >>> repo = container.create_user_video_repository()
        >>> isinstance(repo, UserVideoRepository)
        True
        """
        return UserVideoRepository()

    def create_playlist_membership_repository(self) -> PlaylistMembershipRepository:
        """
        Create a new PlaylistMembershipRepository instance.

        Returns a fresh repository instance for playlist membership operations.
        Each call creates a new instance (transient lifecycle).

        Returns
        -------
        PlaylistMembershipRepository
            A new PlaylistMembershipRepository instance for playlist membership
            CRUD operations.

        Examples
        --------
        >>> repo = container.create_playlist_membership_repository()
        >>> isinstance(repo, PlaylistMembershipRepository)
        True
        """
        return PlaylistMembershipRepository()

    def create_video_tag_repository(self) -> VideoTagRepository:
        """
        Create a new VideoTagRepository instance.

        Returns a fresh repository instance for video tag operations.
        Each call creates a new instance (transient lifecycle).

        Returns
        -------
        VideoTagRepository
            A new VideoTagRepository instance for video tag CRUD operations.

        Examples
        --------
        >>> repo = container.create_video_tag_repository()
        >>> isinstance(repo, VideoTagRepository)
        True
        """
        return VideoTagRepository()

    def create_video_topic_repository(self) -> VideoTopicRepository:
        """
        Create a new VideoTopicRepository instance.

        Returns a fresh repository instance for video topic operations.
        Each call creates a new instance (transient lifecycle).

        Returns
        -------
        VideoTopicRepository
            A new VideoTopicRepository instance for video topic CRUD operations.

        Examples
        --------
        >>> repo = container.create_video_topic_repository()
        >>> isinstance(repo, VideoTopicRepository)
        True
        """
        return VideoTopicRepository()

    def create_channel_topic_repository(self) -> ChannelTopicRepository:
        """
        Create a new ChannelTopicRepository instance.

        Returns a fresh repository instance for channel topic operations.
        Each call creates a new instance (transient lifecycle).

        Returns
        -------
        ChannelTopicRepository
            A new ChannelTopicRepository instance for channel topic CRUD operations.

        Examples
        --------
        >>> repo = container.create_channel_topic_repository()
        >>> isinstance(repo, ChannelTopicRepository)
        True
        """
        return ChannelTopicRepository()

    def create_topic_category_repository(self) -> TopicCategoryRepository:
        """
        Create a new TopicCategoryRepository instance.

        Returns a fresh repository instance for topic category operations.
        Each call creates a new instance (transient lifecycle).

        Returns
        -------
        TopicCategoryRepository
            A new TopicCategoryRepository instance for topic category
            CRUD operations.

        Examples
        --------
        >>> repo = container.create_topic_category_repository()
        >>> isinstance(repo, TopicCategoryRepository)
        True
        """
        return TopicCategoryRepository()

    def create_video_category_repository(self) -> VideoCategoryRepository:
        """
        Create a new VideoCategoryRepository instance.

        Returns a fresh repository instance for video category operations.
        Each call creates a new instance (transient lifecycle).

        Returns
        -------
        VideoCategoryRepository
            A new VideoCategoryRepository instance for video category
            CRUD operations.

        Examples
        --------
        >>> repo = container.create_video_category_repository()
        >>> isinstance(repo, VideoCategoryRepository)
        True
        """
        return VideoCategoryRepository()

    def create_video_transcript_repository(self) -> VideoTranscriptRepository:
        """
        Create a new VideoTranscriptRepository instance.

        Returns a fresh repository instance for video transcript operations.
        Each call creates a new instance (transient lifecycle).

        Returns
        -------
        VideoTranscriptRepository
            A new VideoTranscriptRepository instance for video transcript
            CRUD operations.

        Examples
        --------
        >>> repo = container.create_video_transcript_repository()
        >>> isinstance(repo, VideoTranscriptRepository)
        True
        """
        return VideoTranscriptRepository()

    # -------------------------------------------------------------------------
    # Service Factory Methods (Transient - new instance per call)
    # -------------------------------------------------------------------------

    def create_enrichment_service(
        self, include_playlists: bool = False
    ) -> EnrichmentService:
        """
        Create a new EnrichmentService instance with wired dependencies.

        This factory method creates a new EnrichmentService instance with all
        required repository dependencies automatically wired. The service is
        transient (new instance per call) to ensure clean state.

        Parameters
        ----------
        include_playlists : bool, optional
            If True, wire the optional PlaylistRepository dependency.
            Default is False.

        Returns
        -------
        EnrichmentService
            A new EnrichmentService instance with all dependencies wired.

        Examples
        --------
        >>> service = container.create_enrichment_service()
        >>> service.playlist_repository is None
        True

        >>> service_with_playlists = container.create_enrichment_service(include_playlists=True)
        >>> service_with_playlists.playlist_repository is not None
        True
        """
        return EnrichmentService(
            video_repository=self.create_video_repository(),
            channel_repository=self.create_channel_repository(),
            video_tag_repository=self.create_video_tag_repository(),
            video_topic_repository=self.create_video_topic_repository(),
            video_category_repository=self.create_video_category_repository(),
            topic_category_repository=self.create_topic_category_repository(),
            youtube_service=self.youtube_service,
            playlist_repository=(
                self.create_playlist_repository() if include_playlists else None
            ),
        )

    def create_topic_seeder(self) -> TopicSeeder:
        """
        Create a new TopicSeeder instance with wired dependencies.

        This factory method creates a new TopicSeeder instance for seeding
        YouTube topic categories into the database. The seeder is transient
        (new instance per call).

        Returns
        -------
        TopicSeeder
            A new TopicSeeder instance with topic_repository dependency wired.

        Examples
        --------
        >>> seeder = container.create_topic_seeder()
        >>> isinstance(seeder.topic_repository, TopicCategoryRepository)
        True
        """
        return TopicSeeder(topic_repository=self.create_topic_category_repository())

    def create_category_seeder(self) -> CategorySeeder:
        """
        Create a new CategorySeeder instance with wired dependencies.

        This factory method creates a new CategorySeeder instance for seeding
        YouTube video categories from the API. The seeder is transient
        (new instance per call).

        Returns
        -------
        CategorySeeder
            A new CategorySeeder instance with category_repository and
            youtube_service dependencies wired.

        Examples
        --------
        >>> seeder = container.create_category_seeder()
        >>> isinstance(seeder.category_repository, VideoCategoryRepository)
        True
        >>> isinstance(seeder.youtube_service, YouTubeService)
        True
        """
        return CategorySeeder(
            category_repository=self.create_video_category_repository(),
            youtube_service=self.youtube_service,
        )

    # -------------------------------------------------------------------------
    # Singleton Service Properties (Cached - same instance on repeated access)
    # -------------------------------------------------------------------------

    @cached_property
    def youtube_service(self) -> YouTubeService:
        """
        Get the singleton YouTubeService instance.

        This service is cached using @cached_property, so repeated access
        returns the same instance. The service is lazily initialized on
        first access.

        Returns
        -------
        YouTubeService
            The singleton YouTubeService instance.

        Examples
        --------
        >>> service1 = container.youtube_service
        >>> service2 = container.youtube_service
        >>> service1 is service2
        True
        """
        return YouTubeService()

    @cached_property
    def transcript_service(self) -> TranscriptService:
        """
        Get the singleton TranscriptService instance.

        This service is cached using @cached_property, so repeated access
        returns the same instance. The service is lazily initialized on
        first access.

        Returns
        -------
        TranscriptService
            The singleton TranscriptService instance.

        Examples
        --------
        >>> service1 = container.transcript_service
        >>> service2 = container.transcript_service
        >>> service1 is service2
        True
        """
        return TranscriptService()

    # -------------------------------------------------------------------------
    # Testing Support
    # -------------------------------------------------------------------------

    def reset(self) -> None:
        """
        Reset the container by clearing all cached singleton instances.

        This method is primarily for testing purposes, allowing tests to
        inject mocks and then restore the container to a clean state.
        It clears all @cached_property values from the instance __dict__.

        Examples
        --------
        >>> container.reset()
        >>> # All cached singletons are cleared
        """
        # Clear all cached_property values
        properties_to_clear = ["youtube_service", "transcript_service"]
        for prop in properties_to_clear:
            self.__dict__.pop(prop, None)

    # -------------------------------------------------------------------------
    # Request Scoping (Phase 8)
    # -------------------------------------------------------------------------

    @contextmanager
    def request_scope(
        self,
        session: "AsyncSession",
        user_id: str | None = None,
    ) -> Generator[RequestContext, None, None]:
        """
        Create a request-scoped context for API layer operations.

        This context manager sets up request-scoped state (database session
        and optional user ID) that can be accessed throughout the request
        lifecycle. Nested scopes are not allowed and will raise RuntimeError.

        Parameters
        ----------
        session : AsyncSession
            The database session for the current request.
        user_id : str | None, optional
            The authenticated user ID, if available.

        Yields
        ------
        RequestContext
            The request context containing session and user_id.

        Raises
        ------
        RuntimeError
            If a request scope is already active (nested scopes not allowed).

        Examples
        --------
        >>> async with session_maker() as session:
        ...     with container.request_scope(session=session, user_id="user_123") as ctx:
        ...         # Inside request scope
        ...         assert ctx.session is session
        ...         assert ctx.user_id == "user_123"
        ...         # Access via property
        ...         assert container.request_context is ctx
        """
        # Check for nested scope
        if _request_context.get() is not None:
            raise RuntimeError("Nested request scopes not allowed")

        # Create and set context
        ctx = RequestContext(session=session, user_id=user_id)
        token = _request_context.set(ctx)

        try:
            yield ctx
        finally:
            # Clean up context
            _request_context.reset(token)

    @property
    def request_context(self) -> RequestContext:
        """
        Get the current request context.

        This property provides access to the current request-scoped context.
        It must be called within an active request_scope() context manager,
        otherwise it raises RuntimeError.

        Returns
        -------
        RequestContext
            The current request context containing session and user_id.

        Raises
        ------
        RuntimeError
            If no request scope is currently active.

        Examples
        --------
        >>> with container.request_scope(session=session, user_id="user_123"):
        ...     ctx = container.request_context
        ...     assert ctx.user_id == "user_123"

        >>> # Outside request scope
        >>> container.request_context  # Raises RuntimeError
        """
        ctx = _request_context.get()
        if ctx is None:
            raise RuntimeError("No request context - call from API route with request_scope")
        return ctx


# Global container instance
# This is the single entry point for dependency access throughout the application
container = Container()
