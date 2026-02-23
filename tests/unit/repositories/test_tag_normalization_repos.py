"""
Tests for tag normalization repository functionality.

Tests repository CRUD operations and initialization for canonical tags,
tag aliases, named entities, and entity aliases.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import (
    CanonicalTag as CanonicalTagDB,
    EntityAlias as EntityAliasDB,
    NamedEntity as NamedEntityDB,
    TagAlias as TagAliasDB,
)
from chronovista.models.canonical_tag import CanonicalTagCreate
from chronovista.models.entity_alias import EntityAliasCreate
from chronovista.models.enums import (
    CreationMethod,
    DiscoveryMethod,
    EntityAliasType,
    EntityType,
    TagStatus,
)
from chronovista.models.named_entity import NamedEntityCreate
from chronovista.models.tag_alias import TagAliasCreate
from chronovista.repositories.canonical_tag_repository import CanonicalTagRepository
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.repositories.tag_alias_repository import TagAliasRepository


class TestCanonicalTagRepository:
    """Test CanonicalTagRepository functionality."""

    @pytest.fixture
    def repository(self) -> CanonicalTagRepository:
        """Create repository instance for testing."""
        return CanonicalTagRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock async session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def sample_canonical_tag_db(self) -> CanonicalTagDB:
        """Create sample database canonical tag object."""
        return CanonicalTagDB(
            canonical_form="Python",
            normalized_form="python",
            entity_type="technical_term",
            status="active",
            alias_count=5,
            video_count=100,
        )

    def test_repository_initialization(self, repository: CanonicalTagRepository) -> None:
        """Test repository initialization."""
        assert repository.model == CanonicalTagDB

    def test_repository_has_crud_methods(self, repository: CanonicalTagRepository) -> None:
        """Test that repository has standard CRUD methods."""
        # Verify repository has expected methods from BaseSQLAlchemyRepository
        assert hasattr(repository, "get")
        assert hasattr(repository, "exists")
        assert hasattr(repository, "create")
        assert hasattr(repository, "update")
        assert hasattr(repository, "delete")
        assert hasattr(repository, "get_multi")

    @pytest.mark.asyncio
    async def test_get_existing_tag(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
        sample_canonical_tag_db: CanonicalTagDB,
    ) -> None:
        """Test getting canonical tag by UUID when it exists."""
        tag_id = sample_canonical_tag_db.id
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_canonical_tag_db
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, tag_id)

        assert result == sample_canonical_tag_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_nonexistent_tag(
        self, repository: CanonicalTagRepository, mock_session: MagicMock
    ) -> None:
        """Test getting canonical tag when it doesn't exist."""
        tag_id = uuid.UUID(bytes=uuid7().bytes)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, tag_id)

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_true(
        self, repository: CanonicalTagRepository, mock_session: MagicMock
    ) -> None:
        """Test exists returns True when tag exists."""
        tag_id = uuid.UUID(bytes=uuid7().bytes)
        mock_result = MagicMock()
        mock_result.first.return_value = (tag_id,)
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, tag_id)

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_false(
        self, repository: CanonicalTagRepository, mock_session: MagicMock
    ) -> None:
        """Test exists returns False when tag doesn't exist."""
        tag_id = uuid.UUID(bytes=uuid7().bytes)
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, tag_id)

        assert result is False
        mock_session.execute.assert_called_once()


class TestTagAliasRepository:
    """Test TagAliasRepository functionality."""

    @pytest.fixture
    def repository(self) -> TagAliasRepository:
        """Create repository instance for testing."""
        return TagAliasRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock async session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def sample_tag_alias_db(self) -> TagAliasDB:
        """Create sample database tag alias object."""
        canonical_tag_id = uuid.UUID(bytes=uuid7().bytes)
        return TagAliasDB(
            raw_form="Python",
            normalized_form="python",
            canonical_tag_id=canonical_tag_id,
            creation_method="auto_normalize",
            normalization_version=1,
            occurrence_count=10,
        )

    def test_repository_initialization(self, repository: TagAliasRepository) -> None:
        """Test repository initialization."""
        assert repository.model == TagAliasDB

    def test_repository_has_crud_methods(self, repository: TagAliasRepository) -> None:
        """Test that repository has standard CRUD methods."""
        assert hasattr(repository, "get")
        assert hasattr(repository, "exists")
        assert hasattr(repository, "create")
        assert hasattr(repository, "update")
        assert hasattr(repository, "delete")
        assert hasattr(repository, "get_multi")

    @pytest.mark.asyncio
    async def test_get_existing_alias(
        self,
        repository: TagAliasRepository,
        mock_session: MagicMock,
        sample_tag_alias_db: TagAliasDB,
    ) -> None:
        """Test getting tag alias by UUID when it exists."""
        alias_id = sample_tag_alias_db.id
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_tag_alias_db
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, alias_id)

        assert result == sample_tag_alias_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_nonexistent_alias(
        self, repository: TagAliasRepository, mock_session: MagicMock
    ) -> None:
        """Test getting tag alias when it doesn't exist."""
        alias_id = uuid.UUID(bytes=uuid7().bytes)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, alias_id)

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_true(
        self, repository: TagAliasRepository, mock_session: MagicMock
    ) -> None:
        """Test exists returns True when alias exists."""
        alias_id = uuid.UUID(bytes=uuid7().bytes)
        mock_result = MagicMock()
        mock_result.first.return_value = (alias_id,)
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, alias_id)

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_false(
        self, repository: TagAliasRepository, mock_session: MagicMock
    ) -> None:
        """Test exists returns False when alias doesn't exist."""
        alias_id = uuid.UUID(bytes=uuid7().bytes)
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, alias_id)

        assert result is False
        mock_session.execute.assert_called_once()


class TestNamedEntityRepository:
    """Test NamedEntityRepository functionality."""

    @pytest.fixture
    def repository(self) -> NamedEntityRepository:
        """Create repository instance for testing."""
        return NamedEntityRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock async session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def sample_named_entity_db(self) -> NamedEntityDB:
        """Create sample database named entity object."""
        return NamedEntityDB(
            canonical_name="Elon Musk",
            canonical_name_normalized="elon musk",
            entity_type="person",
            discovery_method="manual",
            status="active",
            mention_count=50,
            video_count=10,
            channel_count=3,
            confidence=0.95,
        )

    def test_repository_initialization(self, repository: NamedEntityRepository) -> None:
        """Test repository initialization."""
        assert repository.model == NamedEntityDB

    def test_repository_has_crud_methods(self, repository: NamedEntityRepository) -> None:
        """Test that repository has standard CRUD methods."""
        assert hasattr(repository, "get")
        assert hasattr(repository, "exists")
        assert hasattr(repository, "create")
        assert hasattr(repository, "update")
        assert hasattr(repository, "delete")
        assert hasattr(repository, "get_multi")

    @pytest.mark.asyncio
    async def test_get_existing_entity(
        self,
        repository: NamedEntityRepository,
        mock_session: MagicMock,
        sample_named_entity_db: NamedEntityDB,
    ) -> None:
        """Test getting named entity by UUID when it exists."""
        entity_id = sample_named_entity_db.id
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_named_entity_db
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, entity_id)

        assert result == sample_named_entity_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_nonexistent_entity(
        self, repository: NamedEntityRepository, mock_session: MagicMock
    ) -> None:
        """Test getting named entity when it doesn't exist."""
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, entity_id)

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_true(
        self, repository: NamedEntityRepository, mock_session: MagicMock
    ) -> None:
        """Test exists returns True when entity exists."""
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        mock_result = MagicMock()
        mock_result.first.return_value = (entity_id,)
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, entity_id)

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_false(
        self, repository: NamedEntityRepository, mock_session: MagicMock
    ) -> None:
        """Test exists returns False when entity doesn't exist."""
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, entity_id)

        assert result is False
        mock_session.execute.assert_called_once()


class TestEntityAliasRepository:
    """Test EntityAliasRepository functionality."""

    @pytest.fixture
    def repository(self) -> EntityAliasRepository:
        """Create repository instance for testing."""
        return EntityAliasRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock async session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def sample_entity_alias_db(self) -> EntityAliasDB:
        """Create sample database entity alias object."""
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        return EntityAliasDB(
            alias_name="Elon",
            alias_name_normalized="elon",
            alias_type="nickname",
            entity_id=entity_id,
            occurrence_count=25,
        )

    def test_repository_initialization(self, repository: EntityAliasRepository) -> None:
        """Test repository initialization."""
        assert repository.model == EntityAliasDB

    def test_repository_has_crud_methods(self, repository: EntityAliasRepository) -> None:
        """Test that repository has standard CRUD methods."""
        assert hasattr(repository, "get")
        assert hasattr(repository, "exists")
        assert hasattr(repository, "create")
        assert hasattr(repository, "update")
        assert hasattr(repository, "delete")
        assert hasattr(repository, "get_multi")

    @pytest.mark.asyncio
    async def test_get_existing_alias(
        self,
        repository: EntityAliasRepository,
        mock_session: MagicMock,
        sample_entity_alias_db: EntityAliasDB,
    ) -> None:
        """Test getting entity alias by UUID when it exists."""
        alias_id = sample_entity_alias_db.id
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_entity_alias_db
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, alias_id)

        assert result == sample_entity_alias_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_nonexistent_alias(
        self, repository: EntityAliasRepository, mock_session: MagicMock
    ) -> None:
        """Test getting entity alias when it doesn't exist."""
        alias_id = uuid.UUID(bytes=uuid7().bytes)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, alias_id)

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_true(
        self, repository: EntityAliasRepository, mock_session: MagicMock
    ) -> None:
        """Test exists returns True when alias exists."""
        alias_id = uuid.UUID(bytes=uuid7().bytes)
        mock_result = MagicMock()
        mock_result.first.return_value = (alias_id,)
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, alias_id)

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_false(
        self, repository: EntityAliasRepository, mock_session: MagicMock
    ) -> None:
        """Test exists returns False when alias doesn't exist."""
        alias_id = uuid.UUID(bytes=uuid7().bytes)
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, alias_id)

        assert result is False
        mock_session.execute.assert_called_once()
