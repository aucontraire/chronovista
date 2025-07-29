"""
Modular takeout seeding service - new architecture with same familiar interface.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession

from .seeding.base_seeder import SeedResult, ProgressCallback
from .seeding.channel_seeder import ChannelSeeder
from .seeding.video_seeder import VideoSeeder
from .seeding.user_video_seeder import UserVideoSeeder
from .seeding.playlist_seeder import PlaylistSeeder
from .seeding.orchestrator import SeedingOrchestrator
from ..models.takeout.takeout_data import TakeoutData
from ..repositories.channel_repository import ChannelRepository
from ..repositories.video_repository import VideoRepository
from ..repositories.user_video_repository import UserVideoRepository
from ..repositories.playlist_repository import PlaylistRepository


logger = logging.getLogger(__name__)


class TakeoutSeedingService:
    """
    Modular takeout seeding service.
    
    New architecture with improved dependency resolution and progress tracking.
    """
    
    def __init__(self, user_id: str = "takeout_user"):
        self.user_id = user_id
        self.orchestrator = SeedingOrchestrator()
        self._setup_seeders()
    
    def _setup_seeders(self) -> None:
        """Setup all seeders with proper dependencies."""
        # Create repositories
        channel_repo = ChannelRepository()
        video_repo = VideoRepository()
        user_video_repo = UserVideoRepository()
        playlist_repo = PlaylistRepository()
        
        # Register all seeders
        self.orchestrator.register_seeder(ChannelSeeder(channel_repo))
        self.orchestrator.register_seeder(VideoSeeder(video_repo))
        self.orchestrator.register_seeder(UserVideoSeeder(user_video_repo, self.user_id))
        self.orchestrator.register_seeder(PlaylistSeeder(playlist_repo, self.user_id))
        
        logger.info("✅ Registered all seeders: channels, videos, user_videos, playlists")
    
    async def seed_database(
        self,
        session: AsyncSession,
        takeout_data: TakeoutData,
        data_types: Optional[Set[str]] = None,
        skip_types: Optional[Set[str]] = None,
        progress_callback: Optional[ProgressCallback] = None
    ) -> Dict[str, SeedResult]:
        """
        Seed database with takeout data.
        
        Parameters
        ----------
        session : AsyncSession
            Database session
        takeout_data : TakeoutData
            Parsed takeout data
        data_types : Optional[Set[str]]
            Data types to seed (if None, seeds all). Options: channels, videos, user_videos, playlists
        skip_types : Optional[Set[str]]
            Data types to skip
        progress_callback : Optional[ProgressCallback]
            Progress callback for visual updates
        
        Returns
        -------
        Dict[str, SeedResult]
            Results for each data type processed
        """
        start_time = datetime.now()
        
        # Determine which types to process
        available_types = self.orchestrator.get_available_types()
        
        if data_types is not None:
            types_to_process = data_types & available_types
        else:
            types_to_process = available_types
        
        if skip_types:
            types_to_process = types_to_process - skip_types
        
        if not types_to_process:
            logger.warning("No data types to process")
            return {}
        
        logger.info(f"🌱 Starting modular seeding for: {', '.join(sorted(types_to_process))}")
        
        # Execute seeding with dependency resolution
        results = await self.orchestrator.seed(
            session, takeout_data, types_to_process, progress_callback
        )
        
        # Log summary
        total_duration = (datetime.now() - start_time).total_seconds()
        total_created = sum(r.created for r in results.values())
        total_updated = sum(r.updated for r in results.values())
        total_failed = sum(r.failed for r in results.values())
        
        logger.info(f"🎉 Modular seeding completed in {total_duration:.1f}s")
        logger.info(f"📊 Summary: {total_created} created, {total_updated} updated, {total_failed} failed")
        
        return results
    
    def get_available_types(self) -> Set[str]:
        """Get all available data types."""
        return self.orchestrator.get_available_types()
    
    async def seed_incrementally(
        self,
        session: AsyncSession,
        takeout_data: TakeoutData,
        data_types: Optional[Set[str]] = None,
        skip_types: Optional[Set[str]] = None,
        progress_callback: Optional[ProgressCallback] = None
    ) -> Dict[str, SeedResult]:
        """
        Incremental seeding (same as full seeding for now).
        
        Individual seeders handle existence checks, making this naturally incremental.
        """
        logger.info("🔄 Starting incremental seeding (using existence checks)...")
        return await self.seed_database(
            session, takeout_data, data_types, skip_types, progress_callback
        )