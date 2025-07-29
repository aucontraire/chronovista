"""
Seeding orchestrator - manages dependencies and execution order.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession

from .base_seeder import BaseSeeder, SeedResult, ProgressCallback
from ...models.takeout.takeout_data import TakeoutData


logger = logging.getLogger(__name__)


class SeedingOrchestrator:
    """Orchestrates seeding operations with dependency resolution."""
    
    def __init__(self):
        self.seeders: Dict[str, BaseSeeder] = {}
    
    def register_seeder(self, seeder: BaseSeeder) -> None:
        """Register a seeder for a specific data type."""
        data_type = seeder.get_data_type()
        self.seeders[data_type] = seeder
        logger.debug(f"Registered seeder for {data_type}")
    
    def get_available_types(self) -> Set[str]:
        """Get all available data types."""
        return set(self.seeders.keys())
    
    async def seed(
        self,
        session: AsyncSession,
        takeout_data: TakeoutData,
        types_to_process: Optional[Set[str]] = None,
        progress: Optional[ProgressCallback] = None
    ) -> Dict[str, SeedResult]:
        """Execute seeding for specified types in dependency order."""
        start_time = datetime.now()
        
        # Determine which types to process
        if types_to_process is None:
            types_to_process = self.get_available_types()
        else:
            # Validate requested types
            invalid_types = types_to_process - self.get_available_types()
            if invalid_types:
                raise ValueError(f"Unknown data types: {invalid_types}")
        
        # Resolve execution order based on dependencies
        execution_order = self._resolve_dependencies(types_to_process)
        
        logger.info(f"🌱 Starting seeding for: {', '.join(execution_order)}")
        
        results = {}
        
        for data_type in execution_order:
            logger.info(f"📊 Processing {data_type}...")
            
            seeder = self.seeders[data_type]
            result = await seeder.seed(session, takeout_data, progress)
            results[data_type] = result
            
            logger.info(f"✅ {data_type}: {result.created} created, "
                       f"{result.updated} updated, {result.failed} failed "
                       f"({result.success_rate:.1f}% success)")
        
        total_duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"🎉 Seeding completed in {total_duration:.1f}s")
        
        return results
    
    def _resolve_dependencies(self, requested_types: Set[str]) -> List[str]:
        """
        Resolve execution order based on dependencies.
        
        Automatically includes required dependencies even if not explicitly requested.
        Returns types in dependency order (dependencies first).
        """
        # First, expand requested types to include all dependencies
        all_needed_types = self._expand_with_dependencies(requested_types)
        
        resolved = []
        remaining = all_needed_types.copy()
        
        # Keep resolving until all types are processed
        while remaining:
            # Find types with no unresolved dependencies
            ready = []
            for data_type in remaining:
                seeder = self.seeders[data_type]
                dependencies = seeder.get_dependencies()
                
                # Check if all dependencies are already resolved
                unresolved_deps = dependencies & remaining
                if not unresolved_deps:
                    ready.append(data_type)
            
            if not ready:
                # Circular dependency or missing dependency
                raise ValueError(f"Circular dependency detected for: {remaining}")
            
            # Add ready types to execution order
            for data_type in ready:
                resolved.append(data_type)
                remaining.remove(data_type)
        
        return resolved
    
    def _expand_with_dependencies(self, requested_types: Set[str]) -> Set[str]:
        """
        Expand requested types to include all required dependencies.
        """
        all_types = set()
        to_process = list(requested_types)
        
        while to_process:
            data_type = to_process.pop()
            if data_type in all_types:
                continue
                
            if data_type not in self.seeders:
                raise ValueError(f"Missing dependencies: {data_type} seeder not registered")
                
            all_types.add(data_type)
            
            # Add dependencies to be processed
            seeder = self.seeders[data_type]
            dependencies = seeder.get_dependencies()
            for dep in dependencies:
                if dep not in all_types:
                    to_process.append(dep)
        
        return all_types