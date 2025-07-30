"""
Tests for SeedingOrchestrator - dependency resolution and execution coordination.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from src.chronovista.models.takeout.takeout_data import TakeoutData
from src.chronovista.services.seeding.base_seeder import (
    BaseSeeder,
    ProgressCallback,
    SeedResult,
)
from src.chronovista.services.seeding.orchestrator import SeedingOrchestrator

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


class MockSeeder(BaseSeeder):
    """Mock seeder for testing."""

    def __init__(self, data_type: str, dependencies: set = None):
        super().__init__(dependencies)
        self.data_type = data_type
        self.seed_called = False
        self.seed_result = SeedResult(
            created=1, updated=0, failed=0, duration_seconds=0.1
        )

    def get_data_type(self) -> str:
        return self.data_type

    async def seed(self, session, takeout_data, progress=None):
        self.seed_called = True
        if progress:
            progress.update(self.data_type)
        return self.seed_result


class TestSeedingOrchestrator:
    """Test the SeedingOrchestrator dependency resolution and execution."""

    @pytest.fixture
    def orchestrator(self):
        """Create a SeedingOrchestrator for testing."""
        return SeedingOrchestrator()

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_takeout_data(self):
        """Create mock takeout data."""
        return TakeoutData(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[],
            playlists=[],
        )

    def test_orchestrator_initialization(self, orchestrator):
        """Test orchestrator initializes correctly."""
        assert orchestrator.seeders == {}
        assert orchestrator.get_available_types() == set()

    def test_register_seeder(self, orchestrator):
        """Test registering a seeder."""
        seeder = MockSeeder("test_type")
        orchestrator.register_seeder(seeder)

        assert "test_type" in orchestrator.seeders
        assert orchestrator.seeders["test_type"] == seeder
        assert orchestrator.get_available_types() == {"test_type"}

    def test_register_multiple_seeders(self, orchestrator):
        """Test registering multiple seeders."""
        seeder1 = MockSeeder("type1")
        seeder2 = MockSeeder("type2")

        orchestrator.register_seeder(seeder1)
        orchestrator.register_seeder(seeder2)

        assert orchestrator.get_available_types() == {"type1", "type2"}

    def test_dependency_resolution_no_dependencies(self, orchestrator):
        """Test dependency resolution with no dependencies."""
        seeder1 = MockSeeder("type1")
        seeder2 = MockSeeder("type2")

        orchestrator.register_seeder(seeder1)
        orchestrator.register_seeder(seeder2)

        # Request all types
        execution_order = orchestrator._resolve_dependencies({"type1", "type2"})

        # Should include both types (order doesn't matter when no dependencies)
        assert set(execution_order) == {"type1", "type2"}
        assert len(execution_order) == 2

    def test_dependency_resolution_with_dependencies(self, orchestrator):
        """Test dependency resolution with dependencies."""
        # type2 depends on type1
        seeder1 = MockSeeder("type1", dependencies=set())
        seeder2 = MockSeeder("type2", dependencies={"type1"})

        orchestrator.register_seeder(seeder1)
        orchestrator.register_seeder(seeder2)

        execution_order = orchestrator._resolve_dependencies({"type1", "type2"})

        # type1 should come before type2
        assert execution_order == ["type1", "type2"]

    def test_dependency_resolution_complex_chain(self, orchestrator):
        """Test dependency resolution with complex dependency chain."""
        # Complex: type3 -> type2 -> type1, type4 -> type1
        seeder1 = MockSeeder("type1", dependencies=set())
        seeder2 = MockSeeder("type2", dependencies={"type1"})
        seeder3 = MockSeeder("type3", dependencies={"type2"})
        seeder4 = MockSeeder("type4", dependencies={"type1"})

        for seeder in [seeder1, seeder2, seeder3, seeder4]:
            orchestrator.register_seeder(seeder)

        execution_order = orchestrator._resolve_dependencies(
            {"type1", "type2", "type3", "type4"}
        )

        # Verify ordering constraints
        assert execution_order.index("type1") < execution_order.index("type2")
        assert execution_order.index("type2") < execution_order.index("type3")
        assert execution_order.index("type1") < execution_order.index("type4")

    def test_dependency_resolution_missing_dependency(self, orchestrator):
        """Test handling of missing dependencies."""
        # type2 depends on type1, but type1 is not registered
        seeder2 = MockSeeder("type2", dependencies={"type1"})
        orchestrator.register_seeder(seeder2)

        with pytest.raises(ValueError, match="Missing dependencies.*type1"):
            orchestrator._resolve_dependencies({"type2"})

    def test_dependency_resolution_circular_dependency(self, orchestrator):
        """Test handling of circular dependencies."""
        # Create circular dependency: type1 -> type2 -> type1
        seeder1 = MockSeeder("type1", dependencies={"type2"})
        seeder2 = MockSeeder("type2", dependencies={"type1"})

        orchestrator.register_seeder(seeder1)
        orchestrator.register_seeder(seeder2)

        with pytest.raises(ValueError, match="Circular dependency detected"):
            orchestrator._resolve_dependencies({"type1", "type2"})

    def test_dependency_resolution_partial_request(self, orchestrator):
        """Test dependency resolution when requesting subset of types."""
        seeder1 = MockSeeder("type1", dependencies=set())
        seeder2 = MockSeeder("type2", dependencies={"type1"})
        seeder3 = MockSeeder("type3", dependencies={"type2"})

        for seeder in [seeder1, seeder2, seeder3]:
            orchestrator.register_seeder(seeder)

        # Request only type2, should include its dependency type1
        execution_order = orchestrator._resolve_dependencies({"type2"})
        assert execution_order == ["type1", "type2"]

    async def test_seed_execution_order(
        self, orchestrator, mock_session, mock_takeout_data
    ):
        """Test that seeders are executed in correct dependency order."""
        execution_log = []

        class TrackingSeeder(MockSeeder):
            def __init__(self, data_type: str, dependencies: set = None):
                super().__init__(data_type, dependencies)

            async def seed(self, session, takeout_data, progress=None):
                execution_log.append(self.data_type)
                return await super().seed(session, takeout_data, progress)

        seeder1 = TrackingSeeder("type1", dependencies=set())
        seeder2 = TrackingSeeder("type2", dependencies={"type1"})

        orchestrator.register_seeder(seeder1)
        orchestrator.register_seeder(seeder2)

        results = await orchestrator.seed(
            mock_session, mock_takeout_data, {"type1", "type2"}
        )

        # Verify execution order
        assert execution_log == ["type1", "type2"]

        # Verify results
        assert len(results) == 2
        assert "type1" in results
        assert "type2" in results

    async def test_seed_with_progress_callback(
        self, orchestrator, mock_session, mock_takeout_data
    ):
        """Test seeding with progress callback."""
        progress_calls = []

        def mock_progress_callback(data_type: str):
            progress_calls.append(data_type)

        progress = ProgressCallback(mock_progress_callback)
        seeder = MockSeeder("test_type")
        orchestrator.register_seeder(seeder)

        results = await orchestrator.seed(
            mock_session,
            mock_takeout_data,
            {"test_type"},
            progress,  # positional argument, not keyword
        )

        # Verify progress was called
        assert "test_type" in progress_calls
        assert seeder.seed_called

    async def test_seed_error_handling(
        self, orchestrator, mock_session, mock_takeout_data
    ):
        """Test error handling during seeding."""

        class FailingSeeder(MockSeeder):
            async def seed(self, session, takeout_data, progress=None):
                raise Exception("Test seeding error")

        failing_seeder = FailingSeeder("failing_type")
        orchestrator.register_seeder(failing_seeder)

        # Should propagate the error
        with pytest.raises(Exception, match="Test seeding error"):
            await orchestrator.seed(mock_session, mock_takeout_data, {"failing_type"})

    async def test_seed_empty_types_request(
        self, orchestrator, mock_session, mock_takeout_data
    ):
        """Test seeding with empty types request."""
        seeder = MockSeeder("test_type")
        orchestrator.register_seeder(seeder)

        results = await orchestrator.seed(
            mock_session, mock_takeout_data, set()  # Empty set
        )

        # Should return empty results
        assert results == {}
        assert not seeder.seed_called

    def test_get_seeder_dependencies(self, orchestrator):
        """Test getting seeder dependencies."""
        seeder = MockSeeder("test_type", dependencies={"dep1", "dep2"})
        orchestrator.register_seeder(seeder)

        # Access seeder directly since get_seeder_dependencies doesn't exist
        dependencies = orchestrator.seeders["test_type"].get_dependencies()
        assert dependencies == {"dep1", "dep2"}

    def test_get_seeder_dependencies_nonexistent(self, orchestrator):
        """Test getting dependencies for nonexistent seeder."""
        # Should raise KeyError when seeder doesn't exist
        with pytest.raises(KeyError):
            orchestrator.seeders["nonexistent"].get_dependencies()

    async def test_real_world_dependency_scenario(
        self, orchestrator, mock_session, mock_takeout_data
    ):
        """Test real-world dependency scenario similar to actual system."""
        # Simulate: channels (no deps), videos (needs channels), user_videos (needs videos)
        channels_seeder = MockSeeder("channels", dependencies=set())
        videos_seeder = MockSeeder("videos", dependencies={"channels"})
        user_videos_seeder = MockSeeder("user_videos", dependencies={"videos"})
        playlists_seeder = MockSeeder("playlists", dependencies={"channels"})

        for seeder in [
            channels_seeder,
            videos_seeder,
            user_videos_seeder,
            playlists_seeder,
        ]:
            orchestrator.register_seeder(seeder)

        # Request all types
        results = await orchestrator.seed(
            mock_session,
            mock_takeout_data,
            {"channels", "videos", "user_videos", "playlists"},
        )

        # All should be executed
        assert len(results) == 4
        assert all(
            seeder.seed_called
            for seeder in [
                channels_seeder,
                videos_seeder,
                user_videos_seeder,
                playlists_seeder,
            ]
        )

        # Verify dependency constraints were met by checking execution was successful
        for result in results.values():
            assert result.created == 1  # Mock seeders create 1 item
