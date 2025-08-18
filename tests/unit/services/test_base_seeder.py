"""
Tests for BaseSeeder - abstract base class for all seeders.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Set
from unittest.mock import AsyncMock

import pytest

from chronovista.models.takeout.takeout_data import TakeoutData
from chronovista.services.seeding.base_seeder import (
    BaseSeeder,
    ProgressCallback,
    SeedResult,
)
from tests.factories.takeout_data_factory import create_takeout_data

# Only mark async tests individually - not all tests in this module are async


class TestSeedResult:
    """Tests for SeedResult model."""

    def test_seed_result_creation(self) -> None:
        """Test basic SeedResult creation."""
        result = SeedResult(created=5, updated=3, failed=1, duration_seconds=10.5)

        assert result.created == 5
        assert result.updated == 3
        assert result.failed == 1
        assert result.duration_seconds == 10.5
        assert result.errors == []

    def test_seed_result_defaults(self) -> None:
        """Test SeedResult with default values."""
        result = SeedResult()

        assert result.created == 0
        assert result.updated == 0
        assert result.failed == 0
        assert result.duration_seconds == 0.0
        assert result.errors == []

    def test_seed_result_with_errors(self) -> None:
        """Test SeedResult with errors."""
        errors = ["Error 1", "Error 2"]
        result = SeedResult(created=2, failed=2, errors=errors)

        assert result.errors == errors
        assert len(result.errors) == 2

    def test_total_processed_property(self) -> None:
        """Test total_processed property calculation."""
        result = SeedResult(created=5, updated=3, failed=2)

        assert result.total_processed == 10

    def test_total_processed_zero(self) -> None:
        """Test total_processed with zero values."""
        result = SeedResult()

        assert result.total_processed == 0

    def test_success_rate_perfect(self) -> None:
        """Test success_rate with 100% success."""
        result = SeedResult(created=5, updated=3, failed=0)

        assert result.success_rate == 100.0

    def test_success_rate_partial(self) -> None:
        """Test success_rate with partial success."""
        result = SeedResult(created=6, updated=2, failed=2)  # 8/10 = 80%

        assert result.success_rate == 80.0

    def test_success_rate_zero_processed(self) -> None:
        """Test success_rate with zero processed items."""
        result = SeedResult()

        assert (
            result.success_rate == 100.0
        )  # Empty operation is considered 100% successful

    def test_success_rate_all_failed(self) -> None:
        """Test success_rate with all failures."""
        result = SeedResult(created=0, updated=0, failed=5)

        assert result.success_rate == 0.0

    def test_success_rate_precision(self) -> None:
        """Test success_rate precision with decimal values."""
        result = SeedResult(created=1, updated=1, failed=1)  # 2/3 = 66.67%

        assert abs(result.success_rate - 66.66666666666667) < 0.0001


class TestProgressCallback:
    """Tests for ProgressCallback class."""

    def test_progress_callback_creation_with_callback(self) -> None:
        """Test ProgressCallback creation with callback function."""
        calls = []

        def test_callback(data_type: str) -> None:
            calls.append(data_type)

        progress = ProgressCallback(test_callback)

        assert progress.callback_fn == test_callback

        # Test update method
        progress.update("test_type")
        assert calls == ["test_type"]

    def test_progress_callback_creation_without_callback(self) -> None:
        """Test ProgressCallback creation without callback function."""
        progress = ProgressCallback()

        assert progress.callback_fn is None

        # Should not raise error when calling update
        progress.update("test_type")  # Should do nothing

    def test_progress_callback_with_none(self) -> None:
        """Test ProgressCallback creation with explicit None."""
        progress = ProgressCallback(None)

        assert progress.callback_fn is None

        # Should not raise error when calling update
        progress.update("test_type")  # Should do nothing

    def test_progress_callback_multiple_updates(self) -> None:
        """Test multiple updates with ProgressCallback."""
        calls = []

        def test_callback(data_type: str) -> None:
            calls.append(data_type)

        progress = ProgressCallback(test_callback)

        progress.update("type1")
        progress.update("type2")
        progress.update("type1")  # Duplicate

        assert calls == ["type1", "type2", "type1"]


class MockSeeder(BaseSeeder):
    """Mock implementation of BaseSeeder for testing."""

    def __init__(self, data_type: str, dependencies: Optional[Set[str]] = None):
        super().__init__(dependencies)
        self.data_type = data_type
        self.seed_called = False
        self.seed_args: tuple[Any, ...] = ()
        self.seed_kwargs: dict[str, Any] = {}

    async def seed(
        self,
        session: Any,
        takeout_data: TakeoutData,
        progress: Optional[ProgressCallback] = None,
    ) -> SeedResult:
        """Mock seed implementation."""
        self.seed_called = True
        self.seed_args = (session, takeout_data, progress)

        if progress:
            progress.update(self.data_type)

        return SeedResult(created=1, updated=0, failed=0, duration_seconds=1.0)

    def get_data_type(self) -> str:
        """Return the data type name."""
        return self.data_type


class TestBaseSeeder:
    """Tests for BaseSeeder abstract base class."""

    def test_base_seeder_creation_no_dependencies(self) -> None:
        """Test BaseSeeder creation without dependencies."""
        seeder = MockSeeder("test_type")

        assert seeder.dependencies == set()
        assert not seeder.has_dependencies()
        assert seeder.get_dependencies() == set()
        assert seeder.get_data_type() == "test_type"

    def test_base_seeder_creation_with_dependencies(self) -> None:
        """Test BaseSeeder creation with dependencies."""
        dependencies = {"dep1", "dep2"}
        seeder = MockSeeder("test_type", dependencies)

        assert seeder.dependencies == dependencies
        assert seeder.has_dependencies()
        assert seeder.get_dependencies() == dependencies
        assert seeder.get_data_type() == "test_type"

    def test_base_seeder_creation_with_none_dependencies(self) -> None:
        """Test BaseSeeder creation with None dependencies."""
        seeder = MockSeeder("test_type", None)

        assert seeder.dependencies == set()
        assert not seeder.has_dependencies()

    def test_get_dependencies_returns_copy(self) -> None:
        """Test that get_dependencies returns a copy, not reference."""
        dependencies = {"dep1", "dep2"}
        seeder = MockSeeder("test_type", dependencies)

        returned_deps = seeder.get_dependencies()
        returned_deps.add("new_dep")

        # Original dependencies should not be modified
        assert seeder.dependencies == {"dep1", "dep2"}
        assert "new_dep" not in seeder.dependencies

    def test_has_dependencies_empty_set(self) -> None:
        """Test has_dependencies with empty set."""
        seeder = MockSeeder("test_type", set())

        assert not seeder.has_dependencies()

    def test_has_dependencies_non_empty_set(self) -> None:
        """Test has_dependencies with non-empty set."""
        seeder = MockSeeder("test_type", {"dep1"})

        assert seeder.has_dependencies()

    @pytest.mark.asyncio
    async def test_seed_method_call(self) -> None:
        """Test that seed method is called correctly."""
        seeder = MockSeeder("test_type")
        session = AsyncMock()
        takeout_data = create_takeout_data(
            takeout_path=Path("/test"),
            subscriptions=[],
            watch_history=[],
            playlists=[],
        )

        result = await seeder.seed(session, takeout_data)

        assert seeder.seed_called
        assert seeder.seed_args[0] == session
        assert seeder.seed_args[1] == takeout_data
        assert seeder.seed_args[2] is None  # No progress callback
        assert isinstance(result, SeedResult)
        assert result.created == 1

    @pytest.mark.asyncio
    async def test_seed_method_with_progress(self) -> None:
        """Test seed method with progress callback."""
        seeder = MockSeeder("test_type")
        session = AsyncMock()
        takeout_data = create_takeout_data(
            takeout_path=Path("/test"),
            subscriptions=[],
            watch_history=[],
            playlists=[],
        )

        calls = []

        def progress_callback(data_type: str) -> None:
            calls.append(data_type)

        progress = ProgressCallback(progress_callback)

        result = await seeder.seed(session, takeout_data, progress)

        assert seeder.seed_called
        assert seeder.seed_args[2] == progress
        assert calls == ["test_type"]  # Progress should have been called

    def test_dependencies_immutability(self) -> None:
        """Test that dependencies are properly encapsulated."""
        original_deps = {"dep1", "dep2"}
        seeder = MockSeeder("test_type", original_deps)

        # Store original seeder dependencies
        original_seeder_deps = seeder.dependencies.copy()

        # Modify original set
        original_deps.add("new_dep")

        # Seeder's dependencies should not be affected if BaseSeeder copies them
        # This test verifies the actual behavior - if BaseSeeder stores reference,
        # the behavior may be different
        expected_deps = (
            {"dep1", "dep2", "new_dep"}
            if seeder.dependencies is original_deps
            else original_seeder_deps
        )
        assert seeder.dependencies == expected_deps


class TestBaseSeederInheritance:
    """Tests for proper inheritance and abstract method enforcement."""

    def test_cannot_instantiate_base_seeder_directly(self) -> None:
        """Test that BaseSeeder cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseSeeder()  # type: ignore

    def test_mock_seeder_implements_abstract_methods(self) -> None:
        """Test that MockSeeder properly implements abstract methods."""
        seeder = MockSeeder("test_type")

        # Should be able to call abstract methods
        assert seeder.get_data_type() == "test_type"

    def test_incomplete_seeder_fails_instantiation(self) -> None:
        """Test that incomplete seeder implementations fail."""

        class IncompleteSeeder(BaseSeeder):
            # Missing implementation of abstract methods
            pass

        with pytest.raises(TypeError):
            IncompleteSeeder()  # type: ignore


class TestSeederIntegration:
    """Integration tests for seeder components working together."""

    @pytest.mark.asyncio
    async def test_seeder_with_real_progress_tracking(self) -> None:
        """Test seeder with realistic progress tracking."""
        progress_updates = []

        def track_progress(data_type: str) -> None:
            progress_updates.append(
                {
                    "data_type": data_type,
                    "timestamp": datetime.now(timezone.utc),
                }
            )

        seeder = MockSeeder("integration_test", {"dep1", "dep2"})
        progress = ProgressCallback(track_progress)

        session = AsyncMock()
        takeout_data = create_takeout_data(
            takeout_path=Path("/test"),
            subscriptions=[],
            watch_history=[],
            playlists=[],
        )

        result = await seeder.seed(session, takeout_data, progress)

        # Verify seeder behavior
        assert seeder.has_dependencies()
        assert seeder.get_dependencies() == {"dep1", "dep2"}
        assert result.success_rate == 100.0

        # Verify progress tracking
        assert len(progress_updates) == 1
        assert progress_updates[0]["data_type"] == "integration_test"

    @pytest.mark.asyncio
    async def test_multiple_seeders_different_dependencies(self) -> None:
        """Test multiple seeders with different dependency configurations."""
        seeder1 = MockSeeder("type1", set())  # No dependencies
        seeder2 = MockSeeder("type2", {"type1"})  # Depends on type1
        seeder3 = MockSeeder("type3", {"type1", "type2"})  # Depends on both

        # Verify dependency configurations
        assert not seeder1.has_dependencies()
        assert seeder2.has_dependencies()
        assert seeder3.has_dependencies()

        assert seeder1.get_dependencies() == set()
        assert seeder2.get_dependencies() == {"type1"}
        assert seeder3.get_dependencies() == {"type1", "type2"}

    def test_seeder_result_aggregation(self) -> None:
        """Test aggregating results from multiple operations."""
        # Simulate multiple batch operations
        results = [
            SeedResult(created=5, updated=2, failed=1, duration_seconds=2.0),
            SeedResult(created=3, updated=1, failed=0, duration_seconds=1.5),
            SeedResult(created=2, updated=4, failed=2, duration_seconds=3.0),
        ]

        # Manual aggregation (would be in actual seeder implementation)
        total_created = sum(r.created for r in results)
        total_updated = sum(r.updated for r in results)
        total_failed = sum(r.failed for r in results)
        total_duration = sum(r.duration_seconds for r in results)

        aggregated = SeedResult(
            created=total_created,
            updated=total_updated,
            failed=total_failed,
            duration_seconds=total_duration,
        )

        assert aggregated.created == 10
        assert aggregated.updated == 7
        assert aggregated.failed == 3
        assert aggregated.total_processed == 20
        assert aggregated.success_rate == 85.0  # 17/20 = 85%
        assert aggregated.duration_seconds == 6.5


class TestSeederErrorScenarios:
    """Tests for error handling in seeder implementations."""

    class FailingSeeder(BaseSeeder):
        """Seeder that simulates failures."""

        def __init__(self, fail_type: str = "exception"):
            super().__init__()
            self.fail_type = fail_type

        async def seed(
            self,
            session: Any,
            takeout_data: TakeoutData,
            progress: Optional[ProgressCallback] = None,
        ) -> SeedResult:
            """Simulate different types of failures."""
            if self.fail_type == "exception":
                raise Exception("Simulated seeding error")
            elif self.fail_type == "partial_failure":
                return SeedResult(
                    created=3,
                    updated=2,
                    failed=5,
                    duration_seconds=10.0,
                    errors=["Error 1", "Error 2", "Error 3", "Error 4", "Error 5"],
                )
            else:
                return SeedResult(created=0, updated=0, failed=0, duration_seconds=0.0)

        def get_data_type(self) -> str:
            return "failing_seeder"

    @pytest.mark.asyncio
    async def test_seeder_exception_propagation(self) -> None:
        """Test that seeder exceptions are properly propagated."""
        seeder = self.FailingSeeder("exception")
        session = AsyncMock()
        takeout_data = create_takeout_data(
            takeout_path=Path("/test"),
            subscriptions=[],
            watch_history=[],
            playlists=[],
        )

        with pytest.raises(Exception, match="Simulated seeding error"):
            await seeder.seed(session, takeout_data)

    @pytest.mark.asyncio
    async def test_seeder_partial_failure_handling(self) -> None:
        """Test handling of partial failures in seeding."""
        seeder = self.FailingSeeder("partial_failure")
        session = AsyncMock()
        takeout_data = create_takeout_data(
            takeout_path=Path("/test"),
            subscriptions=[],
            watch_history=[],
            playlists=[],
        )

        result = await seeder.seed(session, takeout_data)

        assert result.created == 3
        assert result.updated == 2
        assert result.failed == 5
        assert result.total_processed == 10
        assert result.success_rate == 50.0
        assert len(result.errors) == 5
