"""
Base repository interface and implementation.

Provides common CRUD operations and patterns for all repositories.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, List, Optional, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from typing_extensions import TypeVar

# Type variables for generic repository
ModelType = TypeVar("ModelType", bound=DeclarativeBase)
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")
# IdType represents the primary key type for repository entities
# Default is Any for backward compatibility with existing code
IdType = TypeVar("IdType", default=Any)


class BaseRepository(ABC, Generic[ModelType, CreateSchemaType, UpdateSchemaType, IdType]):
    """
    Base repository interface defining common CRUD operations.

    This abstract base class provides a consistent interface for all repositories
    following the Repository pattern.

    Type Parameters
    ---------------
    ModelType : DeclarativeBase
        The SQLAlchemy model type for this repository.
    CreateSchemaType : Any
        The Pydantic schema type for creating entities.
    UpdateSchemaType : Any
        The Pydantic schema type for updating entities.
    IdType : Any
        The primary key type (e.g., VideoId, ChannelId, Tuple[str, str]).
        Defaults to Any for backward compatibility.
    """

    @abstractmethod
    async def create(
        self, session: AsyncSession, *, obj_in: CreateSchemaType
    ) -> ModelType:
        """Create a new entity."""
        pass

    @abstractmethod
    async def get(self, session: AsyncSession, id: IdType) -> Optional[ModelType]:
        """Get entity by ID."""
        pass

    @abstractmethod
    async def get_multi(
        self, session: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> List[ModelType]:
        """Get multiple entities with pagination."""
        pass

    @abstractmethod
    async def update(
        self,
        session: AsyncSession,
        *,
        db_obj: ModelType,
        obj_in: Union[UpdateSchemaType, dict[str, Any]],
    ) -> ModelType:
        """Update an existing entity."""
        pass

    @abstractmethod
    async def delete(self, session: AsyncSession, *, id: IdType) -> Optional[ModelType]:
        """Delete an entity by ID."""
        pass


class BaseSQLAlchemyRepository(
    BaseRepository[ModelType, CreateSchemaType, UpdateSchemaType, IdType]
):
    """
    Base SQLAlchemy repository implementation.

    Provides common SQLAlchemy-based implementations of CRUD operations
    that can be inherited by specific repository implementations.

    Type Parameters
    ---------------
    ModelType : DeclarativeBase
        The SQLAlchemy model type for this repository.
    CreateSchemaType : Any
        The Pydantic schema type for creating entities.
    UpdateSchemaType : Any
        The Pydantic schema type for updating entities.
    IdType : Any
        The primary key type (e.g., VideoId, ChannelId, Tuple[str, str]).
        Defaults to Any for backward compatibility.
    """

    def __init__(self, model: type[ModelType]):
        self.model = model

    async def create(
        self, session: AsyncSession, *, obj_in: CreateSchemaType
    ) -> ModelType:
        """Create a new entity in the database."""
        if hasattr(obj_in, "model_dump"):
            # Pydantic model
            obj_data = obj_in.model_dump()
        elif hasattr(obj_in, "dict"):
            # Pydantic v1 model
            obj_data = obj_in.dict()
        else:
            # Dictionary or other object
            obj_data = obj_in if isinstance(obj_in, dict) else obj_in.__dict__

        db_obj = self.model(**obj_data)
        session.add(db_obj)
        await session.flush()
        await session.refresh(db_obj)
        return db_obj

    async def get(self, session: AsyncSession, id: IdType) -> Optional[ModelType]:
        """Get entity by primary key."""
        # This method should be overridden by subclasses since different models
        # may use different primary key column names
        raise NotImplementedError("Subclasses must implement get() method")

    async def get_multi(
        self, session: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> List[ModelType]:
        """Get multiple entities with pagination."""
        result = await session.execute(select(self.model).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def update(
        self,
        session: AsyncSession,
        *,
        db_obj: ModelType,
        obj_in: Union[UpdateSchemaType, dict[str, Any]],
    ) -> ModelType:
        """Update an existing entity."""
        if hasattr(obj_in, "model_dump"):
            # Pydantic model
            update_data = obj_in.model_dump(exclude_unset=True)
        elif hasattr(obj_in, "dict"):
            # Pydantic v1 model
            update_data = obj_in.dict(exclude_unset=True)
        else:
            # Dictionary
            update_data = obj_in if isinstance(obj_in, dict) else obj_in.__dict__

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        session.add(db_obj)
        await session.flush()
        await session.refresh(db_obj)
        return db_obj

    async def delete(self, session: AsyncSession, *, id: IdType) -> Optional[ModelType]:
        """Delete an entity by ID."""
        db_obj = await self.get(session, id)
        if db_obj:
            await session.delete(db_obj)
            await session.flush()
        return db_obj

    async def exists(self, session: AsyncSession, id: IdType) -> bool:
        """Check if entity exists by ID."""
        # This method should be overridden by subclasses since different models
        # may use different primary key column names
        raise NotImplementedError("Subclasses must implement exists() method")

    async def count(self, session: AsyncSession) -> int:
        """Count total number of entities."""
        from sqlalchemy import func

        # Use count(*) instead of count(id) to avoid attribute issues
        result = await session.execute(select(func.count()).select_from(self.model))
        return result.scalar() or 0
