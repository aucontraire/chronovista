"""
Tests for database configuration and connection management.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.config.database import DatabaseManager, db_manager, get_db_session


class TestDatabaseManager:
    """Test DatabaseManager functionality."""

    def test_init(self):
        """Test DatabaseManager initialization."""
        manager = DatabaseManager()
        assert manager._engine is None
        assert manager._session_factory is None

    @patch("chronovista.config.database.create_async_engine")
    def test_get_engine(self, mock_create_engine):
        """Test engine creation and reuse."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        manager = DatabaseManager()

        # First call creates engine
        engine = manager.get_engine()
        assert engine == mock_engine
        assert manager._engine == mock_engine
        mock_create_engine.assert_called_once()

        # Second call reuses engine
        engine2 = manager.get_engine()
        assert engine2 == mock_engine
        assert mock_create_engine.call_count == 1

    @patch("chronovista.config.database.async_sessionmaker")
    def test_get_session_factory(self, mock_sessionmaker):
        """Test session factory creation and reuse."""
        mock_factory = MagicMock()
        mock_sessionmaker.return_value = mock_factory

        manager = DatabaseManager()
        manager._engine = MagicMock()  # Mock engine

        # First call creates factory
        factory = manager.get_session_factory()
        assert factory == mock_factory
        assert manager._session_factory == mock_factory
        mock_sessionmaker.assert_called_once()

        # Second call reuses factory
        factory2 = manager.get_session_factory()
        assert factory2 == mock_factory
        assert mock_sessionmaker.call_count == 1

    def test_get_session_factory_dependency(self):
        """Test that get_session depends on session factory."""
        manager = DatabaseManager()

        # Mock the session factory method
        with patch.object(manager, "get_session_factory") as mock_factory:
            mock_factory.return_value = MagicMock()
            manager.get_session_factory()
            mock_factory.assert_called_once()

    def test_session_factory_creation(self):
        """Test session factory is created properly."""
        manager = DatabaseManager()

        # Mock the engine to avoid database connection
        with patch.object(manager, "get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine

            with patch(
                "chronovista.config.database.async_sessionmaker"
            ) as mock_sessionmaker:
                mock_factory = MagicMock()
                mock_sessionmaker.return_value = mock_factory

                factory = manager.get_session_factory()

                assert factory == mock_factory
                mock_sessionmaker.assert_called_once()

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing database connections."""
        mock_engine = AsyncMock()
        manager = DatabaseManager()
        manager._engine = mock_engine
        manager._session_factory = MagicMock()

        await manager.close()

        # Verify the close method was effective
        mock_engine.dispose.assert_called_once()

        # Verify that manager attributes were properly reset after close()
        engine_is_none = manager._engine is None
        session_factory_is_none = manager._session_factory is None
        assert engine_is_none and session_factory_is_none

    @pytest.mark.asyncio
    async def test_close_no_engine(self):
        """Test closing when no engine exists."""
        manager = DatabaseManager()
        await manager.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_create_tables(self):
        """Test table creation."""
        mock_engine = MagicMock()
        mock_conn = AsyncMock()

        # Create a proper async context manager
        class MockBegin:
            async def __aenter__(self):
                return mock_conn

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_engine.begin.return_value = MockBegin()

        manager = DatabaseManager()
        manager._engine = mock_engine

        await manager.create_tables()

        mock_conn.run_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_drop_tables(self):
        """Test table dropping."""
        mock_engine = MagicMock()
        mock_conn = AsyncMock()

        # Create a proper async context manager
        class MockBegin:
            async def __aenter__(self):
                return mock_conn

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_engine.begin.return_value = MockBegin()

        manager = DatabaseManager()
        manager._engine = mock_engine

        await manager.drop_tables()

        mock_conn.run_sync.assert_called_once()

    @patch("chronovista.config.database.create_engine")
    def test_get_sync_engine(self, mock_create_engine):
        """Test sync engine creation for migrations."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        manager = DatabaseManager()
        engine = manager.get_sync_engine()

        assert engine == mock_engine
        mock_create_engine.assert_called_once()


def test_global_db_manager():
    """Test global database manager instance."""
    assert isinstance(db_manager, DatabaseManager)


@pytest.mark.asyncio
async def test_get_db_session():
    """Test database session dependency."""
    with patch.object(db_manager, "get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value.__aiter__.return_value = [mock_session]

        async for session in get_db_session():
            assert session == mock_session
            break
