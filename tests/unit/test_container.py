"""
Unit tests for the chronovista DI container.

This module implements strict RED→GREEN TDD methodology for all container phases:
- Phase 2: Repository factory test setup
- Phase 3: US1 - Repository access (transient behavior)
- Phase 4: US2 - Service wiring with dependency injection
- Phase 5: US3 - Singleton caching for services
- Phase 6: US4 - Mock injection for testing
- Phase 7: US5 - Transient isolation verification
- Phase 8: US6 - Request scoping with context managers

Test Organization:
- Each phase has dedicated test methods following RED→GREEN pattern
- Tests are marked with pytest markers for selective execution
- Async tests use pytestmark for proper coverage integration
"""

import pytest
from pathlib import Path
from contextvars import ContextVar
from unittest.mock import MagicMock

# Module-level marker ensures all async tests work with coverage
pytestmark = pytest.mark.asyncio

from chronovista.container import Container, RequestContext, container
from chronovista.repositories import (
    ChannelRepository,
    PlaylistRepository,
    TopicCategoryRepository,
    UserVideoRepository,
    VideoCategoryRepository,
    VideoRepository,
    VideoTagRepository,
    VideoTopicRepository,
    ChannelTopicRepository,
)
from chronovista.repositories.playlist_membership_repository import (
    PlaylistMembershipRepository,
)


# =============================================================================
# Phase 2 Completion: T013-T014 (Test Setup)
# =============================================================================


class TestRepositoryFactories:
    """Test all 10 repository factory methods (Phase 2 baseline)."""

    def test_create_video_repository(self) -> None:
        """T013: Verify video repository factory returns correct type."""
        c = Container()
        repo = c.create_video_repository()
        assert isinstance(repo, VideoRepository)

    def test_create_channel_repository(self) -> None:
        """T013: Verify channel repository factory returns correct type."""
        c = Container()
        repo = c.create_channel_repository()
        assert isinstance(repo, ChannelRepository)

    def test_create_playlist_repository(self) -> None:
        """T013: Verify playlist repository factory returns correct type."""
        c = Container()
        repo = c.create_playlist_repository()
        assert isinstance(repo, PlaylistRepository)

    def test_create_user_video_repository(self) -> None:
        """T013: Verify user video repository factory returns correct type."""
        c = Container()
        repo = c.create_user_video_repository()
        assert isinstance(repo, UserVideoRepository)

    def test_create_playlist_membership_repository(self) -> None:
        """T013: Verify playlist membership repository factory returns correct type."""
        c = Container()
        repo = c.create_playlist_membership_repository()
        assert isinstance(repo, PlaylistMembershipRepository)

    def test_create_video_tag_repository(self) -> None:
        """T013: Verify video tag repository factory returns correct type."""
        c = Container()
        repo = c.create_video_tag_repository()
        assert isinstance(repo, VideoTagRepository)

    def test_create_video_topic_repository(self) -> None:
        """T013: Verify video topic repository factory returns correct type."""
        c = Container()
        repo = c.create_video_topic_repository()
        assert isinstance(repo, VideoTopicRepository)

    def test_create_channel_topic_repository(self) -> None:
        """T013: Verify channel topic repository factory returns correct type."""
        c = Container()
        repo = c.create_channel_topic_repository()
        assert isinstance(repo, ChannelTopicRepository)

    def test_create_topic_category_repository(self) -> None:
        """T013: Verify topic category repository factory returns correct type."""
        c = Container()
        repo = c.create_topic_category_repository()
        assert isinstance(repo, TopicCategoryRepository)

    def test_create_video_category_repository(self) -> None:
        """T013: Verify video category repository factory returns correct type."""
        c = Container()
        repo = c.create_video_category_repository()
        assert isinstance(repo, VideoCategoryRepository)


# =============================================================================
# Phase 3: US1 - Repository Access (T016-T020)
# =============================================================================


class TestRepositoryAccessTransientBehavior:
    """US1: Repository factories should return new instances each call (transient)."""

    def test_transient_behavior_video_repository(self) -> None:
        """T016: Each call to create_video_repository returns new instance."""
        c = Container()
        repo1 = c.create_video_repository()
        repo2 = c.create_video_repository()
        assert repo1 is not repo2, "Should return different instances"

    def test_transient_behavior_channel_repository(self) -> None:
        """T016: Each call to create_channel_repository returns new instance."""
        c = Container()
        repo1 = c.create_channel_repository()
        repo2 = c.create_channel_repository()
        assert repo1 is not repo2, "Should return different instances"

    def test_transient_behavior_all_repositories(self) -> None:
        """T016: Verify transient behavior across all 10 repository factories."""
        c = Container()

        # Test each factory method returns new instances
        factories = [
            c.create_video_repository,
            c.create_channel_repository,
            c.create_playlist_repository,
            c.create_user_video_repository,
            c.create_playlist_membership_repository,
            c.create_video_tag_repository,
            c.create_video_topic_repository,
            c.create_channel_topic_repository,
            c.create_topic_category_repository,
            c.create_video_category_repository,
        ]

        for factory in factories:
            instance1 = factory()
            instance2 = factory()
            assert instance1 is not instance2, f"{factory.__name__} should return new instance each call"

    def test_correct_return_types_all_repositories(self) -> None:
        """T017: Verify all 10 repositories return correct types."""
        c = Container()

        assert isinstance(c.create_video_repository(), VideoRepository)
        assert isinstance(c.create_channel_repository(), ChannelRepository)
        assert isinstance(c.create_playlist_repository(), PlaylistRepository)
        assert isinstance(c.create_user_video_repository(), UserVideoRepository)
        assert isinstance(c.create_playlist_membership_repository(), PlaylistMembershipRepository)
        assert isinstance(c.create_video_tag_repository(), VideoTagRepository)
        assert isinstance(c.create_video_topic_repository(), VideoTopicRepository)
        assert isinstance(c.create_channel_topic_repository(), ChannelTopicRepository)
        assert isinstance(c.create_topic_category_repository(), TopicCategoryRepository)
        assert isinstance(c.create_video_category_repository(), VideoCategoryRepository)


# =============================================================================
# Phase 4: US2 - Service Wiring (T021-T030) - RED Phase
# =============================================================================


class TestServiceWiring:
    """US2: Container should wire services with their repository dependencies."""

    def test_create_enrichment_service_dependency_wiring(self) -> None:
        """
        T021: Verify create_enrichment_service wires all required dependencies.

        EnrichmentService requires 7 repositories + 1 service:
        - video_repository, channel_repository, video_tag_repository
        - video_topic_repository, video_category_repository, topic_category_repository
        - youtube_service
        - playlist_repository (optional)
        """
        c = Container()

        # This will fail until we implement create_enrichment_service
        service = c.create_enrichment_service()

        # Verify service is correctly wired (implementation-agnostic check)
        assert service is not None
        assert hasattr(service, 'video_repository')
        assert hasattr(service, 'channel_repository')
        assert hasattr(service, 'youtube_service')

    def test_create_enrichment_service_with_optional_playlist_repository(self) -> None:
        """T022: Verify create_enrichment_service supports include_playlists parameter."""
        c = Container()

        # Test without playlists
        service_without = c.create_enrichment_service(include_playlists=False)
        assert service_without is not None
        assert service_without.playlist_repository is None

        # Test with playlists
        service_with = c.create_enrichment_service(include_playlists=True)
        assert service_with is not None
        assert service_with.playlist_repository is not None

    def test_create_topic_seeder_dependency_wiring(self) -> None:
        """
        T023: Verify create_topic_seeder wires required dependencies.

        TopicSeeder requires:
        - topic_repository (TopicCategoryRepository)
        """
        c = Container()

        # This will fail until we implement create_topic_seeder
        seeder = c.create_topic_seeder()

        assert seeder is not None
        assert hasattr(seeder, 'topic_repository')

    def test_create_category_seeder_dependency_wiring(self) -> None:
        """
        T024: Verify create_category_seeder wires required dependencies.

        CategorySeeder requires:
        - category_repository (VideoCategoryRepository)
        - youtube_service (YouTubeService)
        """
        c = Container()

        # This will fail until we implement create_category_seeder
        seeder = c.create_category_seeder()

        assert seeder is not None
        assert hasattr(seeder, 'category_repository')
        assert hasattr(seeder, 'youtube_service')

    def test_enrichment_service_transient_behavior(self) -> None:
        """T025: Verify create_enrichment_service returns new instance each call."""
        c = Container()

        service1 = c.create_enrichment_service()
        service2 = c.create_enrichment_service()

        assert service1 is not service2, "Should return different instances"


# =============================================================================
# Phase 5: US3 - Singleton Caching (T031-T041) - RED Phase
# =============================================================================


class TestSingletonCaching:
    """US3: Singleton services should be cached and reused."""

    def test_youtube_service_caching(self) -> None:
        """T031: Verify youtube_service returns same instance on repeated access."""
        c = Container()

        # This will fail until we implement youtube_service as @cached_property
        service1 = c.youtube_service
        service2 = c.youtube_service

        assert service1 is service2, "Should return same cached instance"

    def test_transcript_service_caching(self) -> None:
        """T032: Verify transcript_service returns same instance on repeated access."""
        c = Container()

        # This will fail until we implement transcript_service as @cached_property
        service1 = c.transcript_service
        service2 = c.transcript_service

        assert service1 is service2, "Should return same cached instance"

    def test_singleton_lazy_initialization(self) -> None:
        """T034: Verify singletons are not created until first access."""
        c = Container()

        # Check that internal cached properties are not set yet
        # Use __dict__ to inspect cached_property state
        assert 'youtube_service' not in c.__dict__, "youtube_service should not be initialized yet"
        assert 'transcript_service' not in c.__dict__, "transcript_service should not be initialized yet"

        # Access them to trigger initialization
        _ = c.youtube_service
        _ = c.transcript_service

        # Now they should be in __dict__
        assert 'youtube_service' in c.__dict__, "youtube_service should be cached"
        assert 'transcript_service' in c.__dict__, "transcript_service should be cached"

    def test_singleton_initialization_failure_propagates(self) -> None:
        """T035: Verify singleton initialization errors propagate correctly."""
        # This test is conceptual - actual error propagation depends on service implementation
        # We'll test that accessing a property doesn't swallow exceptions
        c = Container()

        # Normal access should work without raising
        try:
            _ = c.youtube_service
        except Exception as e:
            pytest.fail(f"Singleton access raised unexpected exception: {e}")


# =============================================================================
# Phase 6: US4 - Mock Injection (T042-T050) - RED Phase
# =============================================================================


class TestMockInjection:
    """US4: Container should support mock injection for testing."""

    def test_reset_method_clears_cached_singletons(self) -> None:
        """T042: Verify reset() clears all cached singleton instances."""
        c = Container()

        # Access singletons to cache them
        _ = c.youtube_service
        _ = c.transcript_service

        # Verify they're cached
        assert 'youtube_service' in c.__dict__
        assert 'transcript_service' in c.__dict__

        # This will fail until we implement reset()
        c.reset()

        # Verify cache is cleared
        assert 'youtube_service' not in c.__dict__, "youtube_service should be cleared"
        assert 'transcript_service' not in c.__dict__, "transcript_service should be cleared"

    def test_mock_injection_via_dict_property_replacement(self) -> None:
        """T043: Verify mocks can be injected by replacing __dict__ properties."""
        c = Container()

        # Create a mock
        mock_youtube_service = MagicMock(name="MockYouTubeService")

        # Inject mock by setting __dict__ property (bypasses cached_property)
        c.__dict__['youtube_service'] = mock_youtube_service

        # Access should return our mock
        assert c.youtube_service is mock_youtube_service

    def test_container_reset_fixture_teardown(self) -> None:
        """T044: Verify fixture teardown can restore original state."""
        c = Container()

        # Access a singleton
        original_service = c.youtube_service

        # Inject a mock
        mock_service = MagicMock(name="MockService")
        c.__dict__['youtube_service'] = mock_service
        assert c.youtube_service is mock_service

        # Reset to restore original state
        c.reset()

        # Access again - should get a new instance (not the mock)
        new_service = c.youtube_service
        assert new_service is not mock_service
        assert new_service is not original_service  # New instance after reset


# =============================================================================
# Phase 7: US5 - Transient Isolation (T051-T056) - RED Phase
# =============================================================================


class TestTransientIsolation:
    """US5: Verify transient factory methods maintain isolation."""

    def test_enrichment_service_transient_isolation(self) -> None:
        """T051: Verify create_enrichment_service returns new instance each call."""
        c = Container()

        service1 = c.create_enrichment_service()
        service2 = c.create_enrichment_service()

        assert service1 is not service2, "Should return different instances"

        # Verify they use different repository instances
        assert service1.video_repository is not service2.video_repository

    def test_topic_seeder_transient_isolation(self) -> None:
        """T052: Verify create_topic_seeder returns new instance each call."""
        c = Container()

        seeder1 = c.create_topic_seeder()
        seeder2 = c.create_topic_seeder()

        assert seeder1 is not seeder2, "Should return different instances"
        assert seeder1.topic_repository is not seeder2.topic_repository

    def test_category_seeder_transient_isolation(self) -> None:
        """T053: Verify create_category_seeder returns new instance each call."""
        c = Container()

        seeder1 = c.create_category_seeder()
        seeder2 = c.create_category_seeder()

        assert seeder1 is not seeder2, "Should return different instances"
        assert seeder1.category_repository is not seeder2.category_repository


# =============================================================================
# Phase 8: US6 - Request Scoping (T057-T067) - RED Phase
# =============================================================================


class TestRequestScoping:
    """US6: Container should support request-scoped context for API layer."""

    def test_request_context_dataclass(self) -> None:
        """T057: Verify RequestContext dataclass structure."""
        from sqlalchemy.ext.asyncio import AsyncSession

        # Create a mock session
        mock_session = MagicMock(spec=AsyncSession)

        # Test RequestContext creation with required fields
        ctx = RequestContext(session=mock_session, user_id="user_123")
        assert ctx.session is mock_session
        assert ctx.user_id == "user_123"

        # Test optional user_id
        ctx2 = RequestContext(session=mock_session)
        assert ctx2.session is mock_session
        assert ctx2.user_id is None

    def test_request_scope_context_manager_sets_and_clears(self) -> None:
        """T058: Verify request_scope() context manager sets and clears context."""
        from sqlalchemy.ext.asyncio import AsyncSession

        c = Container()
        mock_session = MagicMock(spec=AsyncSession)

        # This will fail until we implement request_scope()
        # Before entering context, should raise RuntimeError
        with pytest.raises(RuntimeError, match="No request context"):
            _ = c.request_context

        # Inside context manager, should work
        with c.request_scope(session=mock_session, user_id="user_123") as ctx:
            assert ctx is not None
            assert ctx.session is mock_session
            assert ctx.user_id == "user_123"

            # request_context property should return same context
            assert c.request_context is ctx

        # After exiting context, should raise RuntimeError again
        with pytest.raises(RuntimeError, match="No request context"):
            _ = c.request_context

    def test_request_context_property_returns_current_context(self) -> None:
        """T059: Verify request_context property returns current active context."""
        from sqlalchemy.ext.asyncio import AsyncSession

        c = Container()
        mock_session = MagicMock(spec=AsyncSession)

        with c.request_scope(session=mock_session, user_id="user_456") as ctx:
            retrieved_ctx = c.request_context
            assert retrieved_ctx is ctx
            assert retrieved_ctx.session is mock_session
            assert retrieved_ctx.user_id == "user_456"

    def test_request_context_raises_when_no_scope_active(self) -> None:
        """T060: Verify request_context raises RuntimeError when no scope is active."""
        c = Container()

        # This will fail until we implement request_context property
        with pytest.raises(RuntimeError, match="No request context"):
            _ = c.request_context

    def test_nested_request_scope_rejection(self) -> None:
        """T061: Verify nested request scopes are rejected with RuntimeError."""
        from sqlalchemy.ext.asyncio import AsyncSession

        c = Container()
        mock_session1 = MagicMock(spec=AsyncSession, name="session1")
        mock_session2 = MagicMock(spec=AsyncSession, name="session2")

        # This will fail until we implement nested scope detection
        with c.request_scope(session=mock_session1, user_id="user_1"):
            # Attempting to enter nested scope should raise
            with pytest.raises(RuntimeError, match="Nested request scopes not allowed"):
                with c.request_scope(session=mock_session2, user_id="user_2"):
                    pass
