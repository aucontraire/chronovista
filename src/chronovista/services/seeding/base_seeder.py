"""
Base seeder interface for modular database seeding.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from ...models.takeout.takeout_data import TakeoutData


class SeedResult(BaseModel):
    """Result of a seeding operation."""
    
    created: int = 0
    updated: int = 0
    failed: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = Field(default_factory=list)
    
    @property
    def total_processed(self) -> int:
        """Total items processed."""
        return self.created + self.updated + self.failed
    
    @property
    def success_rate(self) -> float:
        """Success rate percentage."""
        if self.total_processed == 0:
            return 100.0
        return ((self.created + self.updated) / self.total_processed) * 100.0


class ProgressCallback:
    """Simple progress callback for visual-only progress bars."""
    
    def __init__(self, callback_fn: Optional[Callable[[str], None]] = None):
        self.callback_fn = callback_fn
    
    def update(self, data_type: str) -> None:
        """Update progress (visual pulse only, no numbers)."""
        if self.callback_fn:
            self.callback_fn(data_type)


class BaseSeeder(ABC):
    """Base class for all data type seeders."""
    
    def __init__(self, dependencies: Optional[Set[str]] = None):
        self.dependencies = dependencies or set()
    
    @abstractmethod
    async def seed(
        self, 
        session: AsyncSession, 
        takeout_data: TakeoutData,
        progress: Optional[ProgressCallback] = None
    ) -> SeedResult:
        """Seed data for this specific data type."""
        pass
    
    @abstractmethod
    def get_data_type(self) -> str:
        """Return the data type name."""
        pass
    
    def has_dependencies(self) -> bool:
        """Check if this seeder has dependencies."""
        return len(self.dependencies) > 0
    
    def get_dependencies(self) -> Set[str]:
        """Get list of dependencies."""
        return self.dependencies.copy()