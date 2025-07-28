"""
TakeoutSeedingService

Service for seeding database with Google Takeout data.

Handles foreign key dependencies, data transformation, and incremental seeding
capabilities while preserving Takeout-specific historical data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..repositories.channel_repository import ChannelRepository
    from ..repositories.video_repository import VideoRepository
    from ..repositories.user_video_repository import UserVideoRepository
    from ..repositories.playlist_repository import PlaylistRepository

from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from ..models.takeout.takeout_data import (
    TakeoutData,
    TakeoutSubscription,
    TakeoutWatchEntry,
    TakeoutPlaylist,
)
from ..models.channel import ChannelCreate
from ..models.video import VideoCreate
from ..models.user_video import UserVideoCreate
from ..models.playlist import PlaylistCreate
from ..models.enums import LanguageCode
from ..repositories.channel_repository import ChannelRepository
from ..repositories.video_repository import VideoRepository
from ..repositories.user_video_repository import UserVideoRepository
from ..repositories.playlist_repository import PlaylistRepository


logger = logging.getLogger(__name__)


def generate_valid_channel_id(seed: str) -> str:
    """Generate a valid 24-character YouTube channel ID starting with 'UC'."""
    import hashlib
    hash_suffix = hashlib.md5(seed.encode()).hexdigest()[:22]
    return f"UC{hash_suffix}"


def generate_valid_video_id(seed: str) -> str:
    """Generate a valid 11-character YouTube video ID."""
    import hashlib
    hash_suffix = hashlib.md5(seed.encode()).hexdigest()[:11]
    return hash_suffix


def generate_valid_playlist_id(seed: str) -> str:
    """Generate a valid 30-34 character YouTube playlist ID starting with 'PL'."""
    import hashlib
    hash_suffix = hashlib.md5(seed.encode()).hexdigest()[:32]
    return f"PL{hash_suffix}"


class SeedingProgress(BaseModel):
    """Track seeding progress across all data types."""
    
    channels_processed: int = 0
    channels_total: int = 0
    videos_processed: int = 0
    videos_total: int = 0
    user_videos_processed: int = 0
    user_videos_total: int = 0
    playlists_processed: int = 0
    playlists_total: int = 0
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    
    @property
    def total_processed(self) -> int:
        """Total items processed."""
        return (
            self.channels_processed + self.videos_processed + 
            self.user_videos_processed + self.playlists_processed
        )
    
    @property
    def total_items(self) -> int:
        """Total items to process."""
        return (
            self.channels_total + self.videos_total + 
            self.user_videos_total + self.playlists_total
        )
    
    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage."""
        if self.total_items == 0:
            return 100.0
        return (self.total_processed / self.total_items) * 100.0


class SeedingResult(BaseModel):
    """Comprehensive seeding result with quality metrics."""
    
    channels_seeded: int = 0
    channels_updated: int = 0
    channels_failed: int = 0
    videos_seeded: int = 0
    videos_updated: int = 0
    videos_failed: int = 0
    user_videos_created: int = 0
    user_videos_failed: int = 0
    playlists_seeded: int = 0
    playlists_updated: int = 0
    playlists_failed: int = 0
    duration_seconds: float = 0.0
    data_quality_score: float = 0.0
    integrity_issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    
    @property
    def total_seeded(self) -> int:
        """Total items successfully seeded."""
        return (
            self.channels_seeded + self.videos_seeded + 
            self.user_videos_created + self.playlists_seeded
        )
    
    @property
    def total_failed(self) -> int:
        """Total items that failed."""
        return (
            self.channels_failed + self.videos_failed + 
            self.user_videos_failed + self.playlists_failed
        )
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        total_attempted = self.total_seeded + self.total_failed
        if total_attempted == 0:
            return 100.0
        return (self.total_seeded / total_attempted) * 100.0


class TakeoutDataTransformer:
    """Transforms Takeout data into database-ready Pydantic models."""
    
    def __init__(self, default_user_id: str = "takeout_user") -> None:
        """Initialize with default user ID."""
        self.default_user_id: str = default_user_id
    
    def transform_subscription_to_channel(
        self, subscription: TakeoutSubscription
    ) -> ChannelCreate:
        """Transform Takeout subscription into Channel create model."""
        # Generate valid 24-char channel ID if missing
        channel_id = subscription.channel_id
        if not channel_id:
            channel_id = generate_valid_channel_id(subscription.channel_title)
        
        return ChannelCreate(
            channel_id=channel_id,
            title=subscription.channel_title,
            description="",  # Not available in Takeout
            default_language=LanguageCode.ENGLISH,  # Default fallback
            country=None,  # Not available in Takeout
            subscriber_count=None,  # Will be enriched via API
            video_count=None,  # Will be enriched via API
            thumbnail_url=None,  # Will be enriched via API
        )
    
    def transform_watch_entry_to_channel(
        self, entry: TakeoutWatchEntry
    ) -> Optional[ChannelCreate]:
        """Transform watch history entry into Channel create model."""
        if not entry.channel_name:
            return None
        
        channel_id = entry.channel_id
        if not channel_id:
            channel_id = generate_valid_channel_id(entry.channel_name or "Unknown")
        
        return ChannelCreate(
            channel_id=channel_id,
            title=entry.channel_name,
            description="",  # Not available in Takeout
            default_language=LanguageCode.ENGLISH,  # Default fallback
            country=None,  # Not available in Takeout
            subscriber_count=None,  # Will be enriched via API
            video_count=None,  # Will be enriched via API
            thumbnail_url=None,  # Will be enriched via API
        )
    
    def transform_watch_entry_to_video(self, entry: TakeoutWatchEntry) -> VideoCreate:
        """Transform watch entry preserving historical data."""
        # Track if video ID was originally missing for deleted_flag logic
        originally_missing_video_id = not entry.video_id
        
        # Handle missing video ID
        video_id = entry.video_id
        if not video_id:
            video_id = generate_valid_video_id(entry.title_url or "unknown")
            originally_missing_video_id = True
        
        # Handle missing channel ID
        channel_id = entry.channel_id
        if not channel_id:
            channel_id = generate_valid_channel_id(entry.channel_name or "Unknown")
        
        # Check for indicators of deleted videos
        is_likely_deleted = (
            originally_missing_video_id or 
            "deleted" in (entry.title or "").lower() or
            not entry.video_id  # This should still work for truly missing IDs
        )
        
        return VideoCreate(
            video_id=video_id,
            channel_id=channel_id,
            title=entry.title or f"[Deleted Video] {video_id}",
            description="",  # Not available in Takeout
            upload_date=entry.watched_at or datetime.now(timezone.utc),
            duration=0,  # Will be enriched via API
            # Mark videos without proper IDs as potentially deleted
            deleted_flag=is_likely_deleted,
            made_for_kids=False,  # Will be enriched via API
            self_declared_made_for_kids=False,  # Will be enriched via API
            default_language=LanguageCode.ENGLISH,  # Default fallback
            default_audio_language=None,  # Will be enriched via API
            available_languages=None,  # Will be enriched via API
            region_restriction=None,  # Will be enriched via API
            content_rating=None,  # Will be enriched via API
            like_count=None,  # Will be enriched via API
            view_count=None,  # Will be enriched via API
            comment_count=None,  # Will be enriched via API
        )
    
    def transform_watch_entry_to_user_video(
        self, entry: TakeoutWatchEntry, user_id: Optional[str] = None
    ) -> Optional[UserVideoCreate]:
        """Transform watch entry into UserVideo relationship."""
        if not entry.watched_at:
            return None  # Skip entries without watch timestamps
        
        video_id = entry.video_id
        if not video_id:
            video_id = generate_valid_video_id(entry.title_url or "unknown")
        
        return UserVideoCreate(
            user_id=user_id or self.default_user_id,
            video_id=video_id,
            watched_at=entry.watched_at,
            watch_duration=None,  # Not available in Takeout
            completion_percentage=None,  # Not available in Takeout
            rewatch_count=0,  # Default value
            liked=False,  # Will be enriched via API
            disliked=False,  # Will be enriched via API
            saved_to_playlist=False,  # Will be determined from playlist data
        )
    
    def transform_playlist_to_playlist_create(
        self, takeout_playlist: TakeoutPlaylist, user_channel_id: Optional[str] = None
    ) -> PlaylistCreate:
        """Transform takeout playlist into Playlist create model."""
        # Generate valid 30-34 character playlist ID starting with PL
        playlist_id = generate_valid_playlist_id(takeout_playlist.name)
        
        # Generate valid user channel ID if not provided
        if not user_channel_id:
            user_channel_id = generate_valid_channel_id(self.default_user_id)
        
        return PlaylistCreate(
            playlist_id=playlist_id,
            title=takeout_playlist.name,
            description=f"Playlist imported from Google Takeout",
            channel_id=user_channel_id,
            video_count=len(takeout_playlist.videos),
            default_language=LanguageCode.ENGLISH,  # Default fallback
            privacy_status="private",  # Takeout playlists are typically private
        )


class DependencyResolver:
    """Ensures foreign key dependencies are met during seeding."""
    
    def __init__(
        self,
        channel_repo: ChannelRepository,
        video_repo: VideoRepository,
        transformer: TakeoutDataTransformer,
    ) -> None:
        """Initialize with repository dependencies."""
        self.channel_repo: ChannelRepository = channel_repo
        self.video_repo: VideoRepository = video_repo
        self.transformer: TakeoutDataTransformer = transformer
        
        # Cache for created entities to avoid duplicates
        self._channel_cache: Set[str] = set()
        self._video_cache: Set[str] = set()
    
    async def ensure_channel_exists(
        self, session: AsyncSession, channel_id: str, channel_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Ensure channel exists before creating dependent entities."""
        if channel_id in self._channel_cache:
            return channel_id
        
        # Check if channel already exists in database
        existing_channel = await self.channel_repo.get_by_channel_id(session, channel_id)
        if existing_channel:
            self._channel_cache.add(channel_id)
            return channel_id
        
        # Create placeholder channel if data not provided
        if not channel_data:
            channel_data = {
                "title": f"[Channel {channel_id}]",
                "description": "Placeholder channel created from Takeout data",
            }
        
        try:
            channel_create = ChannelCreate(
                channel_id=channel_id,
                title=channel_data.get("title", f"[Channel {channel_id}]"),
                description=channel_data.get("description", ""),
                default_language=LanguageCode.ENGLISH,
                country=None,
                subscriber_count=None,
                video_count=None,
                thumbnail_url=None,
            )
            
            await self.channel_repo.create(session, obj_in=channel_create)
            self._channel_cache.add(channel_id)
            logger.info(f"Created placeholder channel: {channel_id}")
            return channel_id
            
        except Exception as e:
            logger.error(f"Failed to create placeholder channel {channel_id}: {e}")
            raise
    
    async def ensure_video_exists(
        self, session: AsyncSession, video_id: str, video_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Ensure video exists before creating dependent entities."""
        if video_id in self._video_cache:
            return video_id
        
        # Check if video already exists in database
        existing_video = await self.video_repo.get_by_video_id(session, video_id)
        if existing_video:
            self._video_cache.add(video_id)
            return video_id
        
        # Video doesn't exist and we don't have data to create it
        if not video_data:
            raise ValueError(f"Video {video_id} not found and no data provided to create it")
        
        # Ensure channel exists first
        channel_id = video_data.get("channel_id")
        if channel_id:
            await self.ensure_channel_exists(session, channel_id)
        
        try:
            # Generate valid channel ID if not provided
            if not channel_id:
                channel_id = generate_valid_channel_id('unknown')
            
            video_create = VideoCreate(
                video_id=video_id,
                channel_id=channel_id,
                title=video_data.get("title", f"[Video {video_id}]"),
                description=video_data.get("description", ""),
                upload_date=video_data.get("upload_date", datetime.now(timezone.utc)),
                duration=video_data.get("duration", 0),
                deleted_flag=video_data.get("deleted_flag", True),
            )
            
            await self.video_repo.create(session, obj_in=video_create)
            self._video_cache.add(video_id)
            logger.info(f"Created placeholder video: {video_id}")
            return video_id
            
        except Exception as e:
            logger.error(f"Failed to create placeholder video {video_id}: {e}")
            raise


class TakeoutSeedingService:
    """
    Service for seeding database with Google Takeout data.
    
    Handles foreign key dependencies, data transformation,
    and incremental seeding capabilities.
    """
    
    def __init__(
        self,
        channel_repository: ChannelRepository,
        video_repository: VideoRepository,
        user_video_repository: UserVideoRepository,
        playlist_repository: PlaylistRepository,
        user_id: str = "takeout_user",
        batch_size: int = 100,
    ) -> None:
        """Initialize with repository dependencies."""
        self.channel_repo: ChannelRepository = channel_repository
        self.video_repo: VideoRepository = video_repository
        self.user_video_repo: UserVideoRepository = user_video_repository
        self.playlist_repo: PlaylistRepository = playlist_repository
        self.user_id: str = user_id
        self.batch_size: int = batch_size
        
        # Initialize transformer and dependency resolver
        self.transformer: TakeoutDataTransformer = TakeoutDataTransformer(user_id)
        self.dependency_resolver: DependencyResolver = DependencyResolver(
            self.channel_repo, self.video_repo, self.transformer
        )
        
        # Progress tracking
        self.progress: SeedingProgress = SeedingProgress()
    
    async def seed_database(
        self, 
        session: AsyncSession, 
        takeout_data: TakeoutData,
        data_types: Optional[set[str]] = None,
        skip_types: Optional[set[str]] = None
    ) -> SeedingResult:
        """
        Complete database seeding from Takeout data.
        
        Parameters
        ----------
        session : AsyncSession
            Database session
        takeout_data : TakeoutData
            Parsed takeout data
        data_types : Optional[set[str]]
            Data types to seed (if None, seeds all). Options: channels, videos, user_videos, playlists
        skip_types : Optional[set[str]]
            Data types to skip
        """
        start_time = datetime.now()
        result = SeedingResult()
        
        # Determine which data types to process
        all_types = {"channels", "videos", "user_videos", "playlists"}
        
        if data_types is not None:
            # Only process specified types
            types_to_process = data_types & all_types
        else:
            # Process all types unless specifically skipped
            types_to_process = all_types
        
        if skip_types:
            types_to_process = types_to_process - skip_types
        
        logger.info(f"🌱 Starting Takeout database seeding for types: {', '.join(sorted(types_to_process))}")
        
        try:
            # Initialize progress tracking
            await self._initialize_progress(takeout_data)
            
            # Phase 1: Foundation Data (Channels) - Required for other phases
            if "channels" in types_to_process:
                logger.info("📺 Phase 1: Seeding channels...")
                channels_result = await self._seed_channels(session, takeout_data)
                result.channels_seeded = channels_result["seeded"]
                result.channels_updated = channels_result["updated"]
                result.channels_failed = channels_result["failed"]
            else:
                logger.info("📺 Phase 1: Skipping channels (filtered out)")
            
            # Phase 2: Content Data (Videos) - Depends on channels
            if "videos" in types_to_process:
                # Ensure channels are available if we're seeding videos
                if "channels" not in types_to_process:
                    logger.warning("⚠️ Seeding videos without channels may cause foreign key violations")
                logger.info("🎬 Phase 2: Seeding videos...")
                videos_result = await self._seed_videos(session, takeout_data)
                result.videos_seeded = videos_result["seeded"]
                result.videos_updated = videos_result["updated"]
                result.videos_failed = videos_result["failed"]
            else:
                logger.info("🎬 Phase 2: Skipping videos (filtered out)")
            
            # Phase 3: Relationship Data (UserVideo) - Depends on videos
            if "user_videos" in types_to_process:
                # Ensure videos are available if we're seeding user_videos  
                if "videos" not in types_to_process:
                    logger.warning("⚠️ Seeding user_videos without videos may cause foreign key violations")
                logger.info("👤 Phase 3: Seeding user-video relationships...")
                user_videos_result = await self._seed_user_videos(session, takeout_data)
                result.user_videos_created = user_videos_result["created"]
                result.user_videos_failed = user_videos_result["failed"]
            else:
                logger.info("👤 Phase 3: Skipping user-video relationships (filtered out)")
            
            # Phase 4: Playlists - Depends on channels
            if "playlists" in types_to_process:
                # Ensure channels are available if we're seeding playlists
                if "channels" not in types_to_process:
                    logger.warning("⚠️ Seeding playlists without channels may cause foreign key violations")
                logger.info("📋 Phase 4: Seeding playlists...")
                playlists_result = await self._seed_playlists(session, takeout_data)
                result.playlists_seeded = playlists_result["seeded"]
                result.playlists_updated = playlists_result["updated"]
                result.playlists_failed = playlists_result["failed"]
            else:
                logger.info("📋 Phase 4: Skipping playlists (filtered out)")
            
            # Calculate final metrics
            end_time = datetime.now()
            result.duration_seconds = (end_time - start_time).total_seconds()
            result.data_quality_score = self._calculate_data_quality_score(result)
            
            logger.info(f"✅ Seeding completed in {result.duration_seconds:.2f}s")
            logger.info(f"📊 Success rate: {result.success_rate:.1f}%")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Seeding failed: {e}")
            result.integrity_issues.append(f"Seeding failed: {str(e)}")
            raise
    
    async def seed_incrementally(
        self, 
        session: AsyncSession, 
        takeout_data: TakeoutData,
        data_types: Optional[set[str]] = None,
        skip_types: Optional[set[str]] = None
    ) -> SeedingResult:
        """
        Incremental seeding that's safe to run multiple times.
        
        Strategy:
        1. Compare Takeout data against existing database records
        2. Only seed new or updated entities
        3. Preserve existing API-enriched data
        4. Update timestamps and metadata carefully
        
        Parameters
        ----------
        session : AsyncSession
            Database session
        takeout_data : TakeoutData
            Parsed takeout data
        data_types : Optional[set[str]]
            Data types to seed (if None, seeds all). Options: channels, videos, user_videos, playlists
        skip_types : Optional[set[str]]
            Data types to skip
        """
        logger.info("🔄 Starting incremental Takeout seeding...")
        
        # For now, implement incremental as full seeding with conflict resolution
        # TODO: Implement true incremental logic by checking existing records
        return await self.seed_database(session, takeout_data, data_types, skip_types)
    
    async def _initialize_progress(self, takeout_data: TakeoutData) -> None:
        """Initialize progress tracking with total counts."""
        # Calculate unique channels from all sources
        unique_channels = set()
        
        # From subscriptions
        for sub in takeout_data.subscriptions:
            if sub.channel_id:
                unique_channels.add(sub.channel_id)
            else:
                unique_channels.add(generate_valid_channel_id(sub.channel_title))
        
        # From watch history
        for entry in takeout_data.watch_history:
            if entry.channel_name:
                if entry.channel_id:
                    unique_channels.add(entry.channel_id)
                else:
                    unique_channels.add(generate_valid_channel_id(entry.channel_name))
        
        self.progress.channels_total = len(unique_channels)
        self.progress.videos_total = len(takeout_data.get_unique_video_ids())
        self.progress.user_videos_total = len([
            entry for entry in takeout_data.watch_history if entry.watched_at
        ])
        self.progress.playlists_total = len(takeout_data.playlists)
        
        logger.info(f"📊 Seeding totals: {self.progress.channels_total} channels, "
                   f"{self.progress.videos_total} videos, {self.progress.user_videos_total} user videos, "
                   f"{self.progress.playlists_total} playlists")
    
    async def _seed_channels(
        self, session: AsyncSession, takeout_data: TakeoutData
    ) -> Dict[str, int]:
        """Seed channels from subscriptions and watch history."""
        result = {"seeded": 0, "updated": 0, "failed": 0}
        
        # Collect unique channels from all sources
        channels_to_create: Dict[str, ChannelCreate] = {}
        
        # From subscriptions
        for subscription in takeout_data.subscriptions:
            try:
                channel_create = self.transformer.transform_subscription_to_channel(subscription)
                channels_to_create[channel_create.channel_id] = channel_create
            except Exception as e:
                logger.warning(f"Failed to transform subscription {subscription.channel_title}: {e}")
                result["failed"] += 1
        
        # From watch history
        for entry in takeout_data.watch_history:
            try:
                channel_create_optional = self.transformer.transform_watch_entry_to_channel(entry)
                if channel_create_optional and channel_create_optional.channel_id not in channels_to_create:
                    channels_to_create[channel_create_optional.channel_id] = channel_create_optional
            except Exception as e:
                logger.warning(f"Failed to transform watch entry channel {entry.channel_name}: {e}")
                result["failed"] += 1
        
        # Create channels in database
        for channel_id, channel_create in channels_to_create.items():
            try:
                # Check if channel already exists
                existing_channel = await self.channel_repo.get_by_channel_id(session, channel_id)
                
                if existing_channel:
                    # Could implement update logic here if needed
                    result["updated"] += 1
                else:
                    await self.channel_repo.create(session, obj_in=channel_create)
                    result["seeded"] += 1
                
                self.progress.channels_processed += 1
                
            except Exception as e:
                logger.error(f"Failed to seed channel {channel_id}: {e}")
                result["failed"] += 1
        
        return result
    
    async def _seed_videos(
        self, session: AsyncSession, takeout_data: TakeoutData
    ) -> Dict[str, int]:
        """Seed videos from watch history with individual session management."""
        from chronovista.config.database import db_manager
        
        result = {"seeded": 0, "updated": 0, "failed": 0}
        
        # Process videos in batches
        unique_videos: Dict[str, TakeoutWatchEntry] = {}
        for entry in takeout_data.watch_history:
            video_id = entry.video_id
            if not video_id:
                video_id = generate_valid_video_id(entry.title_url or "unknown")
            
            if video_id not in unique_videos:
                unique_videos[video_id] = entry
        
        # Process each video with its own session to avoid rollback cascade
        video_items = list(unique_videos.items())
        for i, (video_id, entry) in enumerate(video_items):
            try:
                # Use individual session for each video to prevent rollback cascade
                session_factory = db_manager.get_session_factory()
                async with session_factory() as individual_session:
                    # Ensure channel exists first
                    channel_id = entry.channel_id
                    if not channel_id:
                        hash_suffix = str(abs(hash(entry.channel_name or 'Unknown')))[:22]
                        channel_id = f"UC{hash_suffix.zfill(22)}"
                    
                    await self.dependency_resolver.ensure_channel_exists(
                        individual_session, channel_id, {"title": entry.channel_name or f"[Channel {channel_id}]"}
                    )
                    
                    # Transform and create video
                    video_create = self.transformer.transform_watch_entry_to_video(entry)
                    
                    # Check if video already exists
                    existing_video = await self.video_repo.get_by_video_id(individual_session, video_id)
                    
                    if existing_video:
                        result["updated"] += 1
                    else:
                        await self.video_repo.create(individual_session, obj_in=video_create)
                        result["seeded"] += 1
                    
                    # Commit the individual session
                    await individual_session.commit()
                    
                self.progress.videos_processed += 1
                
                # Log progress every 100 videos
                if (i + 1) % 100 == 0:
                    logger.info(f"Video seeding progress: {i + 1:,}/{len(video_items):,} ({result['seeded']:,} seeded, {result['failed']:,} failed)")
                
            except Exception as e:
                logger.error(f"Failed to seed video {video_id}: {e}")
                result["failed"] += 1
                # Individual session failure doesn't affect other videos
                continue
        
        return result
    
    async def _seed_user_videos(
        self, session: AsyncSession, takeout_data: TakeoutData
    ) -> Dict[str, int]:
        """Seed user-video relationships from watch history with individual session management."""
        from chronovista.config.database import db_manager
        
        result = {"created": 0, "failed": 0}
        
        # Process each user video with its own session to avoid rollback cascade
        watch_entries = [entry for entry in takeout_data.watch_history if entry.watched_at]
        
        for i, entry in enumerate(watch_entries):
            try:
                # Use individual session for each user video to prevent rollback cascade
                session_factory = db_manager.get_session_factory()
                async with session_factory() as individual_session:
                    # Transform to user video
                    user_video_create = self.transformer.transform_watch_entry_to_user_video(
                        entry, self.user_id
                    )
                    
                    if user_video_create:
                        # Ensure video exists first
                        video_id = user_video_create.video_id
                        # Generate valid channel ID if missing
                        channel_id = entry.channel_id
                        if not channel_id:
                            hash_suffix = str(abs(hash(entry.channel_name or 'Unknown')))[:22]
                            channel_id = f"UC{hash_suffix.zfill(22)}"
                        
                        video_data = {
                            "title": entry.title,
                            "channel_id": channel_id,
                            "upload_date": entry.watched_at or datetime.now(timezone.utc),
                            "duration": 0,
                            "deleted_flag": not entry.video_id,
                        }
                        
                        await self.dependency_resolver.ensure_video_exists(
                            individual_session, video_id, video_data
                        )
                        
                        # Check if user video relationship already exists
                        existing_user_video = await self.user_video_repo.get_by_composite_key(
                            individual_session, self.user_id, video_id
                        )
                        
                        if not existing_user_video:
                            await self.user_video_repo.create(individual_session, obj_in=user_video_create)
                            result["created"] += 1
                    
                    # Commit the individual session
                    await individual_session.commit()
                    
                self.progress.user_videos_processed += 1
                
                # Log progress every 100 user videos
                if (i + 1) % 100 == 0:
                    logger.info(f"User video seeding progress: {i + 1:,}/{len(watch_entries):,} ({result['created']:,} created, {result['failed']:,} failed)")
                
            except Exception as e:
                logger.error(f"Failed to seed user video for {entry.video_id}: {e}")
                result["failed"] += 1
                # Individual session failure doesn't affect other user videos
                continue
        
        return result
    
    async def _seed_playlists(
        self, session: AsyncSession, takeout_data: TakeoutData
    ) -> Dict[str, int]:
        """Seed playlists from takeout data."""
        result = {"seeded": 0, "updated": 0, "failed": 0}
        
        # Create user channel if needed for playlist ownership
        user_channel_id = generate_valid_channel_id(self.user_id)
        await self.dependency_resolver.ensure_channel_exists(
            session, user_channel_id, {"title": f"User Channel ({self.user_id})"}
        )
        
        for playlist in takeout_data.playlists:
            try:
                playlist_create = self.transformer.transform_playlist_to_playlist_create(
                    playlist, user_channel_id
                )
                
                # Check if playlist already exists (by name/ID)
                existing_playlist = await self.playlist_repo.get_by_playlist_id(
                    session, playlist_create.playlist_id
                )
                
                if existing_playlist:
                    result["updated"] += 1
                else:
                    await self.playlist_repo.create(session, obj_in=playlist_create)
                    result["seeded"] += 1
                
                self.progress.playlists_processed += 1
                
            except Exception as e:
                logger.error(f"Failed to seed playlist {playlist.name}: {e}")
                result["failed"] += 1
        
        return result
    
    def _calculate_data_quality_score(self, result: SeedingResult) -> float:
        """Calculate data quality score based on seeding results."""
        total_attempted = result.total_seeded + result.total_failed
        if total_attempted == 0:
            return 1.0
        
        # Base score on success rate
        success_rate = result.total_seeded / total_attempted
        
        # Penalize for integrity issues
        integrity_penalty = min(len(result.integrity_issues) * 0.1, 0.5)
        
        return max(0.0, success_rate - integrity_penalty)
    
    async def report_progress(self) -> None:
        """Report current progress."""
        print(
            f"📊 Progress: {self.progress.completion_percentage:.1f}% "
            f"({self.progress.total_processed}/{self.progress.total_items})"
        )
        logger.info(
            f"📊 Progress: {self.progress.completion_percentage:.1f}% "
            f"({self.progress.total_processed}/{self.progress.total_items})"
        )