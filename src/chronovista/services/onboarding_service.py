"""Onboarding pipeline service for first-time data setup.

Queries existing repositories for record counts, checks filesystem and
auth state, computes pipeline step statuses, and dispatches pipeline
operations to existing services via the TaskManager.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Coroutine, cast

from sqlalchemy import CursorResult, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.api.schemas.onboarding import (
    OnboardingCounts,
    OnboardingStatus,
    PipelineStep,
)
from chronovista.api.schemas.tasks import BackgroundTask
from chronovista.api.services.task_manager import TaskManager
from chronovista.db.models import (
    CanonicalTag,
    Channel,
    Playlist,
    Video,
    VideoCategory,
    VideoTranscript,
)
from chronovista.models.enums import OperationType, PipelineStepStatus

logger = logging.getLogger(__name__)

# Type alias for the coroutine factory accepted by TaskManager.submit
CoroFactory = Callable[
    [Callable[[float], None]], Coroutine[Any, Any, dict[str, Any]]
]


class _StepDefinition:
    """Internal definition of a pipeline step.

    Parameters
    ----------
    order : int
        Display / execution order (1-based).
    name : str
        Human-readable step name.
    operation_type : OperationType
        Enum value for the pipeline operation.
    description : str
        Short explanation shown in the UI.
    dependencies : list[OperationType]
        Steps that must be completed before this one is available.
    requires_auth : bool
        Whether OAuth authentication is required.
    count_key : str
        Key in ``OnboardingCounts`` used to decide completion.
    """

    __slots__ = (
        "order",
        "name",
        "operation_type",
        "description",
        "dependencies",
        "requires_auth",
        "count_key",
    )

    def __init__(
        self,
        *,
        order: int,
        name: str,
        operation_type: OperationType,
        description: str,
        dependencies: list[OperationType],
        requires_auth: bool,
        count_key: str,
    ) -> None:
        self.order = order
        self.name = name
        self.operation_type = operation_type
        self.description = description
        self.dependencies = dependencies
        self.requires_auth = requires_auth
        self.count_key = count_key


_PIPELINE_STEPS: list[_StepDefinition] = [
    _StepDefinition(
        order=1,
        name="Seed Reference Data",
        operation_type=OperationType.SEED_REFERENCE,
        description="Populate YouTube topic and video category reference tables.",
        dependencies=[],
        requires_auth=False,
        count_key="categories",
    ),
    _StepDefinition(
        order=2,
        name="Load Data Export",
        operation_type=OperationType.LOAD_DATA,
        description="Import channels, videos, and playlists from a Google Takeout export.",
        dependencies=[],
        requires_auth=False,
        count_key="videos",
    ),
    _StepDefinition(
        order=3,
        name="Enrich Metadata",
        operation_type=OperationType.ENRICH_METADATA,
        description="Fetch additional metadata from the YouTube Data API.",
        dependencies=[OperationType.LOAD_DATA],
        requires_auth=True,
        count_key="enriched_videos",
    ),
    _StepDefinition(
        order=4,
        name="Normalize Tags",
        operation_type=OperationType.NORMALIZE_TAGS,
        description="Deduplicate and normalize video tags into canonical form.",
        dependencies=[OperationType.LOAD_DATA],
        requires_auth=False,
        count_key="canonical_tags",
    ),
]


class OnboardingService:
    """Orchestrates the first-time data onboarding pipeline.

    Responsibilities:

    * Query the database for aggregate record counts.
    * Detect whether a Google Takeout data export is present on disk.
    * Check OAuth token existence.
    * Compute the status of each pipeline step based on counts, running
      tasks, dependencies, and authentication state.
    * Dispatch pipeline operations to existing services via coroutine
      factories that the ``TaskManager`` can execute in the background.

    Parameters
    ----------
    task_manager : TaskManager
        The in-memory task manager singleton for submitting and querying
        background tasks.
    session_factory : async_sessionmaker[AsyncSession]
        SQLAlchemy async session factory for database queries.
    """

    def __init__(
        self,
        task_manager: TaskManager,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._task_manager = task_manager
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_status(self) -> OnboardingStatus:
        """Build the complete onboarding status payload.

        Returns
        -------
        OnboardingStatus
            Full pipeline state including step statuses, counts, auth
            state, and any currently active task.
        """
        counts = await self._get_counts()
        is_authenticated = self._check_auth()
        data_export_path = self._get_data_export_path()
        data_export_detected = self._detect_data_export(data_export_path)
        export_mtime = self._get_export_mtime(data_export_path)
        last_loaded_at = await self._get_last_loaded_at()
        new_data_available = self._detect_new_data(
            data_export_detected=data_export_detected,
            export_mtime=export_mtime,
            videos_loaded=counts.videos,
            last_loaded_at=last_loaded_at,
        )
        active_task = self._get_active_task()

        steps = self._compute_steps(
            counts=counts,
            is_authenticated=is_authenticated,
            new_data_available=new_data_available,
        )

        return OnboardingStatus(
            steps=steps,
            is_authenticated=is_authenticated,
            data_export_path=str(data_export_path),
            data_export_detected=data_export_detected,
            new_data_available=new_data_available,
            active_task=active_task,
            counts=counts,
        )

    async def dispatch(self, operation_type: OperationType) -> str:
        """Start a pipeline operation in the background.

        Validates that the operation's prerequisites are met, then
        delegates to the ``TaskManager``.

        Parameters
        ----------
        operation_type : OperationType
            Which pipeline operation to start.

        Returns
        -------
        str
            The task ID assigned by the ``TaskManager``.

        Raises
        ------
        ValueError
            If the operation type is unknown, prerequisites are unmet,
            or the ``TaskManager`` rejects the submission (e.g. duplicate).
        """
        step_def = self._find_step(operation_type)
        if step_def is None:
            raise ValueError(f"Unknown operation type: {operation_type.value}")

        # Pre-flight: verify dependencies
        counts = await self._get_counts()
        for dep in step_def.dependencies:
            dep_def = self._find_step(dep)
            if dep_def is not None:
                dep_count = getattr(counts, dep_def.count_key, 0)
                if dep_count == 0:
                    raise ValueError(
                        f"Dependency '{dep.value}' not satisfied for "
                        f"'{operation_type.value}'"
                    )

        if step_def.requires_auth and not self._check_auth():
            raise ValueError(
                f"Operation '{operation_type.value}' requires OAuth "
                f"authentication. Run: chronovista auth login"
            )

        factory = self._make_coro_factory(operation_type)
        return await self._task_manager.submit(operation_type, factory)

    # ------------------------------------------------------------------
    # Count queries
    # ------------------------------------------------------------------

    async def _get_counts(self) -> OnboardingCounts:
        """Query aggregate record counts from the database.

        Returns
        -------
        OnboardingCounts
            Counts for channels, videos, playlists, transcripts,
            categories, and canonical_tags.
        """
        async with self._session_factory() as session:
            channels = await self._count(session, Channel)
            videos = await self._count(session, Video)
            available_videos = await self._count_available_videos(session)
            enriched_videos = await self._count_enriched_videos(session)
            playlists = await self._count(session, Playlist)
            transcripts = await self._count(session, VideoTranscript)
            categories = await self._count(session, VideoCategory)
            canonical_tags = await self._count(session, CanonicalTag)

        return OnboardingCounts(
            channels=channels,
            videos=videos,
            available_videos=available_videos,
            enriched_videos=enriched_videos,
            playlists=playlists,
            transcripts=transcripts,
            categories=categories,
            canonical_tags=canonical_tags,
        )

    @staticmethod
    async def _count(session: AsyncSession, model: type) -> int:
        """Return the row count for a given SQLAlchemy model.

        Parameters
        ----------
        session : AsyncSession
            Active database session.
        model : type
            The SQLAlchemy ORM model class.

        Returns
        -------
        int
            Total number of rows in the model's table.
        """
        result = await session.execute(select(func.count()).select_from(model))
        return result.scalar_one()

    @staticmethod
    async def _count_enriched_videos(session: AsyncSession) -> int:
        """Count videos that have been enriched via the YouTube API.

        Enriched videos have a non-NULL ``view_count`` — a field that is
        never populated by Takeout import, only by API enrichment.

        Parameters
        ----------
        session : AsyncSession
            Active database session.

        Returns
        -------
        int
            Number of enriched video rows.
        """
        result = await session.execute(
            select(func.count())
            .select_from(Video)
            .where(Video.view_count.is_not(None))
        )
        return result.scalar_one()

    @staticmethod
    async def _count_available_videos(session: AsyncSession) -> int:
        """Count videos with availability_status = 'available'."""
        result = await session.execute(
            select(func.count())
            .select_from(Video)
            .where(Video.availability_status == "available")
        )
        return result.scalar_one()

    async def _get_last_loaded_at(self) -> float | None:
        """Return the epoch timestamp of the most recently created video.

        Used to compare against the takeout directory mtime to decide
        whether new export data has appeared since the last load.

        Returns
        -------
        float | None
            Epoch timestamp, or ``None`` if no videos exist.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.max(Video.created_at))
            )
            latest = result.scalar_one_or_none()
            if latest is None:
                return None
            return latest.timestamp()

    # ------------------------------------------------------------------
    # Filesystem / auth checks
    # ------------------------------------------------------------------

    @staticmethod
    def _get_data_export_path() -> Path:
        """Resolve the path where Takeout exports should be placed.

        Reads ``TAKEOUT_DIR`` environment variable, falling back to
        ``./data/takeout``.

        Returns
        -------
        Path
            Absolute path to the takeout directory.
        """
        raw = os.environ.get("TAKEOUT_DIR", "./data/takeout")
        return Path(raw).resolve()

    @staticmethod
    def _detect_data_export(export_path: Path) -> bool:
        """Check whether the takeout directory exists and has files.

        Parameters
        ----------
        export_path : Path
            Directory to inspect.

        Returns
        -------
        bool
            ``True`` if the directory contains at least one file or
            subdirectory.
        """
        if not export_path.is_dir():
            return False
        try:
            return any(export_path.iterdir())
        except PermissionError:
            logger.warning(
                "Cannot read data export directory: %s", export_path
            )
            return False

    @staticmethod
    def _get_export_mtime(export_path: Path) -> float | None:
        """Return the latest modification time among files in the export dir.

        Scans the top-level entries in *export_path* and returns the most
        recent ``st_mtime`` value.  Returns ``None`` if the directory does
        not exist, is empty, or cannot be read.

        Parameters
        ----------
        export_path : Path
            Directory to inspect.

        Returns
        -------
        float | None
            Epoch timestamp of the most recently modified entry, or
            ``None`` if unavailable.
        """
        if not export_path.is_dir():
            return None
        try:
            entries = list(export_path.iterdir())
            if not entries:
                return None
            return max(entry.stat().st_mtime for entry in entries)
        except (PermissionError, OSError):
            logger.warning(
                "Cannot stat data export directory entries: %s", export_path
            )
            return None

    @staticmethod
    def _detect_new_data(
        *,
        data_export_detected: bool,
        export_mtime: float | None,
        videos_loaded: int,
        last_loaded_at: float | None = None,
    ) -> bool:
        """Determine whether new export data is available for import.

        A returning user scenario: the database already contains videos
        (``videos_loaded > 0``), and the export directory has been modified
        **after** the most recent video was loaded into the database —
        hinting that the user placed a fresh Takeout archive.

        Parameters
        ----------
        data_export_detected : bool
            Whether the export directory has any files.
        export_mtime : float | None
            Latest modification time of export entries, or ``None``.
        videos_loaded : int
            Current video count in the database.
        last_loaded_at : float | None
            Epoch timestamp of the most recently created video record in
            the database, or ``None`` if no videos exist.

        Returns
        -------
        bool
            ``True`` if there is evidence of new data to import.
        """
        if not data_export_detected:
            return False
        if videos_loaded == 0:
            return False
        if export_mtime is None:
            return False
        # Only signal new data if export dir was modified after last load
        if last_loaded_at is not None and export_mtime <= last_loaded_at:
            return False
        return True

    @staticmethod
    def _check_auth() -> bool:
        """Check whether a YouTube OAuth token file exists.

        Uses the ``settings.data_dir / 'youtube_token.json'`` path
        consistent with ``YouTubeOAuthService``.

        Returns
        -------
        bool
            ``True`` if the token file is present on disk.
        """
        from chronovista.config.settings import settings

        token_path = settings.data_dir / "youtube_token.json"
        return token_path.is_file()

    # ------------------------------------------------------------------
    # Step status computation
    # ------------------------------------------------------------------

    def _compute_steps(
        self,
        *,
        counts: OnboardingCounts,
        is_authenticated: bool,
        new_data_available: bool = False,
    ) -> list[PipelineStep]:
        """Derive the status of every pipeline step.

        Parameters
        ----------
        counts : OnboardingCounts
            Current database record counts.
        is_authenticated : bool
            Whether the user has a valid OAuth token.
        new_data_available : bool
            Whether new export data has been detected for a returning
            user.  When ``True``, the ``load_data`` step is shown as
            ``AVAILABLE`` even if videos already exist.

        Returns
        -------
        list[PipelineStep]
            Ordered list of pipeline steps with computed statuses.
        """
        # Build a set of completed operation types for dependency checks
        completed_ops: set[OperationType] = set()
        for step_def in _PIPELINE_STEPS:
            count_value = getattr(counts, step_def.count_key, 0)
            if count_value > 0:
                completed_ops.add(step_def.operation_type)

        steps: list[PipelineStep] = []
        for step_def in _PIPELINE_STEPS:
            status = self._resolve_status(
                step_def=step_def,
                counts=counts,
                completed_ops=completed_ops,
                is_authenticated=is_authenticated,
                new_data_available=new_data_available,
            )
            metrics = self._build_metrics(step_def, counts)
            running_task = self._task_manager.get_running_task_for_operation(
                step_def.operation_type
            )
            error: str | None = None
            if running_task is not None and running_task.error is not None:
                error = running_task.error

            steps.append(
                PipelineStep(
                    name=step_def.name,
                    operation_type=step_def.operation_type,
                    description=step_def.description,
                    status=status,
                    dependencies=step_def.dependencies,
                    requires_auth=step_def.requires_auth,
                    metrics=metrics,
                    error=error,
                )
            )
        return steps

    def _resolve_status(
        self,
        *,
        step_def: _StepDefinition,
        counts: OnboardingCounts,
        completed_ops: set[OperationType],
        is_authenticated: bool,
        new_data_available: bool = False,
    ) -> PipelineStepStatus:
        """Determine the status of a single pipeline step.

        Parameters
        ----------
        step_def : _StepDefinition
            The step's static definition.
        counts : OnboardingCounts
            Current record counts.
        completed_ops : set[OperationType]
            Set of operation types that are considered completed.
        is_authenticated : bool
            Whether OAuth is available.
        new_data_available : bool
            When ``True`` and this step is ``load_data``, the step is
            shown as ``AVAILABLE`` instead of ``COMPLETED`` even when
            the video count is positive — signalling that re-import is
            possible.

        Returns
        -------
        PipelineStepStatus
            The computed status enum value.
        """
        # Check if a task is currently running for this operation
        running_task = self._task_manager.get_running_task_for_operation(
            step_def.operation_type
        )
        if running_task is not None:
            return PipelineStepStatus.RUNNING

        # Check if already completed (relevant count > 0)
        count_value = getattr(counts, step_def.count_key, 0)
        if count_value > 0:
            # Special case: load_data can be re-run when new exports exist
            if (
                new_data_available
                and step_def.operation_type == OperationType.LOAD_DATA
            ):
                return PipelineStepStatus.AVAILABLE
            # Special case: enrich_metadata can be re-run when there are
            # un-enriched *available* videos.  Unavailable/deleted videos
            # can never be enriched, so we compare enriched count against
            # available videos only.
            if (
                step_def.operation_type == OperationType.ENRICH_METADATA
                and counts.enriched_videos < counts.available_videos
            ):
                return PipelineStepStatus.AVAILABLE
            return PipelineStepStatus.COMPLETED

        # Check for blocked conditions
        if step_def.requires_auth and not is_authenticated:
            return PipelineStepStatus.BLOCKED

        for dep in step_def.dependencies:
            if dep not in completed_ops:
                return PipelineStepStatus.BLOCKED

        # Dependencies met, not completed, not running
        return PipelineStepStatus.AVAILABLE

    @staticmethod
    def _build_metrics(
        step_def: _StepDefinition,
        counts: OnboardingCounts,
    ) -> dict[str, int | str]:
        """Build the metrics dict for a step.

        Parameters
        ----------
        step_def : _StepDefinition
            The step's static definition.
        counts : OnboardingCounts
            Current record counts.

        Returns
        -------
        dict[str, int | str]
            Relevant metrics for frontend display.
        """
        metrics: dict[str, int | str] = {}
        count_value = getattr(counts, step_def.count_key, 0)
        metrics[step_def.count_key] = count_value

        # Add extra contextual metrics per step
        if step_def.operation_type == OperationType.LOAD_DATA:
            metrics["channels"] = counts.channels
            metrics["playlists"] = counts.playlists
        elif step_def.operation_type == OperationType.ENRICH_METADATA:
            metrics["videos"] = counts.videos
            metrics["channels"] = counts.channels

        return metrics

    # ------------------------------------------------------------------
    # Active task helpers
    # ------------------------------------------------------------------

    def _get_active_task(self) -> BackgroundTask | None:
        """Return any currently running or queued task.

        Returns
        -------
        BackgroundTask | None
            The first active task found, or ``None``.
        """
        for step_def in _PIPELINE_STEPS:
            task = self._task_manager.get_running_task_for_operation(
                step_def.operation_type
            )
            if task is not None:
                return task
        return None

    # ------------------------------------------------------------------
    # Coroutine factories for dispatching to real services
    # ------------------------------------------------------------------

    def _make_coro_factory(
        self,
        operation_type: OperationType,
    ) -> CoroFactory:
        """Create a coroutine factory for the given operation type.

        The returned callable accepts a progress callback and produces a
        coroutine suitable for ``TaskManager.submit``.

        Parameters
        ----------
        operation_type : OperationType
            The pipeline operation to create a factory for.

        Returns
        -------
        CoroFactory
            A callable ``(progress_cb) -> Coroutine[..., dict]``.

        Raises
        ------
        ValueError
            If the operation type has no factory mapping.
        """
        factories: dict[OperationType, Callable[[], CoroFactory]] = {
            OperationType.SEED_REFERENCE: self._factory_seed_reference,
            OperationType.LOAD_DATA: self._factory_load_data,
            OperationType.ENRICH_METADATA: self._factory_enrich_metadata,
            OperationType.NORMALIZE_TAGS: self._factory_normalize_tags,
        }
        builder = factories.get(operation_type)
        if builder is None:
            raise ValueError(
                f"No coroutine factory for operation: {operation_type.value}"
            )
        return builder()

    def _factory_seed_reference(self) -> CoroFactory:
        """Factory for the seed_reference operation.

        Returns
        -------
        CoroFactory
            Coroutine factory that seeds topic and category reference data.
        """
        session_factory = self._session_factory

        def factory(
            progress_cb: Callable[[float], None],
        ) -> Coroutine[Any, Any, dict[str, Any]]:
            async def _run() -> dict[str, Any]:
                from chronovista.container import container

                logger.info("Starting seed_reference pipeline step")
                progress_cb(0.0)

                topic_seeder = container.create_topic_seeder()
                category_seeder = container.create_category_seeder()

                async with session_factory() as session:
                    topic_result = await topic_seeder.seed(session)
                    progress_cb(40.0)

                    category_result = await category_seeder.seed(session)
                    progress_cb(90.0)

                progress_cb(100.0)
                return {
                    "topics_created": topic_result.created,
                    "topics_skipped": topic_result.skipped,
                    "aliases_seeded": topic_result.aliases_seeded,
                    "categories_created": category_result.created,
                    "categories_skipped": category_result.skipped,
                    "quota_used": category_result.quota_used,
                }

            return _run()

        return factory

    def _factory_load_data(self) -> CoroFactory:
        """Factory for the load_data operation.

        Returns
        -------
        CoroFactory
            Coroutine factory that parses a Takeout export and seeds the DB.
        """
        session_factory = self._session_factory

        def factory(
            progress_cb: Callable[[float], None],
        ) -> Coroutine[Any, Any, dict[str, Any]]:
            async def _run() -> dict[str, Any]:
                from chronovista.services.takeout_recovery_service import (
                    TakeoutRecoveryService,
                )
                from chronovista.services.takeout_seeding_service import (
                    TakeoutSeedingService,
                )
                from chronovista.services.takeout_service import TakeoutService

                logger.info("Starting load_data pipeline step")
                progress_cb(0.0)

                takeout_path = OnboardingService._get_data_export_path()

                # Discover all takeout directories (dated + undated)
                # and seed from each to capture the full watch history.
                takeout_dirs: list[Path] = []
                for entry in sorted(takeout_path.iterdir()):
                    if entry.is_dir() and entry.name.startswith(
                        "YouTube and YouTube Music"
                    ):
                        # TakeoutService expects the *parent* of
                        # "YouTube and YouTube Music", so if the entry
                        # IS that folder, its parent is the takeout_path.
                        # But dated dirs are siblings — each is a
                        # "YouTube and YouTube Music YYYY-MM-DD" folder
                        # containing the same structure as the undated one.
                        takeout_dirs.append(entry)

                if not takeout_dirs:
                    # Fallback: single undated directory
                    takeout_dirs = [
                        takeout_path / "YouTube and YouTube Music"
                    ]

                logger.info(
                    "Found %d takeout directories to process",
                    len(takeout_dirs),
                )

                # Resolve the real user ID when authenticated, so
                # user_videos rows are stored under the actual channel
                # ID instead of the "takeout_user" placeholder.
                user_id = "takeout_user"
                if OnboardingService._check_auth():
                    try:
                        from chronovista.container import container

                        yt = container.youtube_service
                        my_ch = await yt.get_my_channel()
                        if my_ch:
                            user_id = my_ch.id
                            logger.info(
                                "Load data: using authenticated channel ID %s",
                                user_id,
                            )
                    except Exception as exc:
                        logger.warning(
                            "Load data: could not resolve channel ID, "
                            "falling back to 'takeout_user': %s",
                            exc,
                        )

                # Parse and seed from each takeout directory
                seeding_svc = TakeoutSeedingService(user_id=user_id)
                all_results: dict[str, Any] = {}
                total_dirs = len(takeout_dirs)

                for idx, tdir in enumerate(takeout_dirs):
                    try:
                        # TakeoutService expects the parent dir; it
                        # appends "YouTube and YouTube Music" internally.
                        # For dated dirs like "YouTube and YouTube Music
                        # 2025-08-13", the dir name doesn't match the
                        # hardcoded suffix — so we point TakeoutService
                        # at a temp parent and override youtube_path.
                        svc = object.__new__(TakeoutService)
                        svc.takeout_path = tdir.parent
                        svc.youtube_path = tdir

                        takeout_data = await svc.parse_all()

                        async with session_factory() as session:
                            results = await seeding_svc.seed_database(
                                session, takeout_data
                            )

                        # Merge results (sum created counts)
                        for key, val in results.items():
                            if key not in all_results:
                                all_results[key] = val.created
                            else:
                                all_results[key] += val.created

                    except Exception as exc:
                        logger.warning(
                            "Failed to process takeout dir %s: %s",
                            tdir.name,
                            exc,
                        )

                    progress_cb(
                        5.0 + (idx + 1) / total_dirs * 50.0
                    )

                progress_cb(60.0)

                # Recover metadata from historical takeout exports
                # (fills placeholder titles/channels for deleted/private videos)
                recovery_svc = TakeoutRecoveryService()
                recovery_result_data: dict[str, Any] = {}
                async with session_factory() as session:
                    try:
                        recovery_result = (
                            await recovery_svc.recover_from_historical_takeouts(
                                session, takeout_path
                            )
                        )
                        recovery_result_data = {
                            "videos_recovered": recovery_result.videos_recovered,
                            "channels_created": recovery_result.channels_created,
                            "channels_updated": recovery_result.channels_updated,
                        }
                        logger.info(
                            "Takeout recovery: %d videos recovered, "
                            "%d channels created",
                            recovery_result.videos_recovered,
                            recovery_result.channels_created,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Takeout recovery failed (non-fatal): %s", exc
                        )
                        recovery_result_data = {"recovery_error": str(exc)}
                progress_cb(90.0)

                progress_cb(100.0)
                all_results.update(recovery_result_data)
                return all_results

            return _run()

        return factory

    def _factory_enrich_metadata(self) -> CoroFactory:
        """Factory for the enrich_metadata operation.

        Returns
        -------
        CoroFactory
            Coroutine factory that enriches video metadata via YouTube API.
        """
        session_factory = self._session_factory

        def factory(
            progress_cb: Callable[[float], None],
        ) -> Coroutine[Any, Any, dict[str, Any]]:
            async def _run() -> dict[str, Any]:
                from chronovista.container import container
                from chronovista.repositories.user_video_repository import (
                    UserVideoRepository,
                )
                from chronovista.repositories.video_repository import (
                    VideoRepository as VR,
                )

                logger.info("Starting enrich_metadata pipeline step")
                progress_cb(0.0)

                # include_playlists=True for maximum enrichment
                enrichment_service = container.create_enrichment_service(
                    include_playlists=True
                )

                # Step 1: Enrich videos (--priority all --include-deleted)
                # Map video enrichment progress (0.0-1.0) into the 0%-30% range.
                def _video_progress(fraction: float) -> None:
                    progress_cb(fraction * 30.0)

                async with session_factory() as session:
                    report = await enrichment_service.enrich_videos(
                        session,
                        priority="all",
                        include_deleted=True,
                        check_prerequisites=False,
                        progress_cb=_video_progress,
                    )
                progress_cb(30.0)

                summary = report.summary

                # Step 2: Enrich playlists (--include-playlists)
                playlists_processed = 0
                playlists_updated = 0
                async with session_factory() as session:
                    try:
                        p_processed, p_updated, _p_deleted = (
                            await enrichment_service.enrich_playlists(session)
                        )
                        playlists_processed = p_processed
                        playlists_updated = p_updated
                    except Exception as exc:
                        logger.warning(
                            "Playlist enrichment failed (non-fatal): %s", exc
                        )
                progress_cb(50.0)

                # Step 2.5: Migrate any "takeout_user" rows to the real
                # channel ID so likes sync and filters work correctly.
                youtube_service = container.youtube_service
                real_user_id: str | None = None
                async with session_factory() as session:
                    try:
                        my_channel = await youtube_service.get_my_channel()
                        if my_channel:
                            real_user_id = my_channel.id
                            from chronovista.db.models import UserVideo as UserVideoDB
                            from sqlalchemy import text

                            # Migrate takeout_user → real channel ID,
                            # skipping rows that already exist under
                            # the real ID (avoids PK conflict).
                            result = await session.execute(
                                text("""
                                    UPDATE user_videos
                                    SET user_id = :real_id
                                    WHERE user_id = 'takeout_user'
                                    AND video_id NOT IN (
                                        SELECT video_id FROM user_videos
                                        WHERE user_id = :real_id
                                    )
                                """),
                                {"real_id": real_user_id},
                            )
                            cursor = cast(CursorResult[Any], result)
                            migrated = cursor.rowcount
                            await session.commit()
                            if migrated > 0:
                                logger.info(
                                    "Migrated %d user_videos rows from "
                                    "'takeout_user' to '%s'",
                                    migrated,
                                    real_user_id,
                                )
                    except Exception as exc:
                        logger.warning(
                            "User ID migration failed (non-fatal): %s", exc
                        )
                progress_cb(55.0)

                # Step 3: Sync liked videos (--sync-likes)
                likes_synced = 0
                async with session_factory() as session:
                    try:
                        # Reuse channel ID from migration step if available,
                        # otherwise fetch it now.
                        if real_user_id is None:
                            logger.info("Likes sync: fetching authenticated channel...")
                            ch = await youtube_service.get_my_channel()
                            real_user_id = ch.id if ch else None

                        if real_user_id:
                            logger.info(
                                "Likes sync: channel=%s, fetching liked videos...",
                                real_user_id,
                            )
                            liked_videos = (
                                await youtube_service.get_liked_videos()
                            )
                            logger.info(
                                "Likes sync: got %d liked videos from API",
                                len(liked_videos) if liked_videos else 0,
                            )
                            if liked_videos:
                                user_video_repo = UserVideoRepository()
                                video_repo = VR()
                                existing_ids = [
                                    v.id
                                    for v in liked_videos
                                    if await video_repo.exists(session, v.id)
                                ]
                                logger.info(
                                    "Likes sync: %d/%d liked videos exist in DB",
                                    len(existing_ids),
                                    len(liked_videos),
                                )
                                if existing_ids:
                                    likes_synced = await user_video_repo.update_like_status_batch(
                                        session,
                                        real_user_id,
                                        existing_ids,
                                        liked=True,
                                    )
                                    await session.commit()
                                    logger.info(
                                        "Likes sync: %d records updated",
                                        likes_synced,
                                    )
                        else:
                            logger.warning(
                                "Likes sync: no channel found for authenticated user"
                            )
                    except Exception as exc:
                        logger.error(
                            "Likes sync failed (non-fatal): %s", exc,
                            exc_info=True,
                        )
                progress_cb(70.0)

                # Step 4: Enrich channels
                channels_enriched = 0
                async with session_factory() as session:
                    try:
                        channel_result = (
                            await enrichment_service.enrich_channels(session)
                        )
                        channels_enriched = channel_result.channels_enriched
                    except Exception as exc:
                        logger.warning(
                            "Channel enrichment failed (non-fatal): %s", exc
                        )
                progress_cb(95.0)

                progress_cb(100.0)
                return {
                    "videos_processed": summary.videos_processed,
                    "videos_updated": summary.videos_updated,
                    "videos_deleted": summary.videos_deleted,
                    "channels_created": summary.channels_created,
                    "channels_enriched": channels_enriched,
                    "playlists_processed": playlists_processed,
                    "playlists_updated": playlists_updated,
                    "likes_synced": likes_synced,
                    "tags_created": summary.tags_created,
                    "errors": summary.errors,
                    "quota_used": summary.quota_used,
                }

            return _run()

        return factory

    def _factory_normalize_tags(self) -> CoroFactory:
        """Factory for the normalize_tags operation.

        Returns
        -------
        CoroFactory
            Coroutine factory that runs the tag normalization backfill.
        """
        session_factory = self._session_factory

        def factory(
            progress_cb: Callable[[float], None],
        ) -> Coroutine[Any, Any, dict[str, Any]]:
            async def _run() -> dict[str, Any]:
                from chronovista.services.tag_backfill import (
                    TagBackfillService,
                )
                from chronovista.services.tag_normalization import (
                    TagNormalizationService,
                )

                logger.info("Starting normalize_tags pipeline step")
                progress_cb(0.0)

                norm_svc = TagNormalizationService()
                backfill_svc = TagBackfillService(norm_svc)

                async with session_factory() as session:
                    await backfill_svc.run_backfill(session)
                progress_cb(90.0)

                progress_cb(100.0)
                return {"status": "completed"}

            return _run()

        return factory

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_step(operation_type: OperationType) -> _StepDefinition | None:
        """Look up a step definition by operation type.

        Parameters
        ----------
        operation_type : OperationType
            The enum value to search for.

        Returns
        -------
        _StepDefinition | None
            The matching definition, or ``None`` if not found.
        """
        for step_def in _PIPELINE_STEPS:
            if step_def.operation_type == operation_type:
                return step_def
        return None
