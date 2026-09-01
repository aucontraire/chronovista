"""FastAPI dependencies for API endpoints."""

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, NamedTuple

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from chronovista.services.batch_correction_service import BatchCorrectionService
    from chronovista.services.entity_curation_service import EntityCurationService
    from chronovista.services.tag_management import TagManagementService
    from chronovista.services.transcript_correction_service import (
        TranscriptCorrectionService,
    )
    from chronovista.services.transcript_service import TranscriptService

from chronovista.auth import youtube_oauth
from chronovista.config.database import db_manager
from chronovista.config.settings import settings
from chronovista.repositories import (
    CanonicalTagRepository,
    ChannelRepository,
    EntityAliasRepository,
    EntityMentionRepository,
    NamedEntityRepository,
    PlaylistRepository,
    TranscriptSegmentRepository,
    UserVideoRepository,
    VideoRepository,
    VideoTranscriptRepository,
)
from chronovista.repositories.playlist_membership_repository import (
    PlaylistMembershipRepository,
)
from chronovista.repositories.topic_category_repository import TopicCategoryRepository
from chronovista.repositories.transcript_correction_repository import (
    TranscriptCorrectionRepository,
)
from chronovista.repositories.user_language_preference_repository import (
    UserLanguagePreferenceRepository,
)
from chronovista.repositories.video_category_repository import VideoCategoryRepository
from chronovista.repositories.video_tag_repository import VideoTagRepository
from chronovista.services.recovery.cdx_client import CDXClient, RateLimiter
from chronovista.services.recovery.page_parser import PageParser

# Module-level singleton: shared across all recovery API calls
_recovery_rate_limiter = RateLimiter(rate=40.0)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for database session.

    Yields an async SQLAlchemy session that auto-commits on success
    and rolls back on exception.

    Yields
    ------
    AsyncSession
        An async SQLAlchemy session for database operations.
    """
    async for session in db_manager.get_session():
        yield session


async def require_auth() -> None:
    """
    Dependency to require OAuth authentication.

    Raises HTTPException 401 if user is not authenticated via CLI.
    Health endpoint should NOT use this dependency.

    Raises
    ------
    HTTPException
        401 Unauthorized if user is not authenticated.
    """
    if not youtube_oauth.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "NOT_AUTHENTICATED",
                "message": "Not authenticated. Run: chronovista auth login",
            },
        )


async def require_local_identity(
    session: AsyncSession = Depends(get_db),
) -> str:
    """Return the canonical local-user identity, or 409 if none established.

    Feature 060 (FR-020a): read/write endpoints resolve the persisted identity
    instead of hardcoding a placeholder. A read request MUST NOT establish an
    identity as a side effect — that belongs to the CLI/onboarding path — so
    this raises 409 when none exists rather than minting one.

    Raises
    ------
    HTTPException
        409 Conflict if no canonical identity has been established.
    """
    from chronovista.services.identity_service import (
        IdentityNotEstablishedError,
        IdentityService,
    )

    try:
        return await IdentityService().get_established_identity(session)
    except IdentityNotEstablishedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "IDENTITY_NOT_ESTABLISHED",
                "message": str(exc),
            },
        ) from exc


def get_tag_management_service() -> "TagManagementService":
    """
    Dependency for the tag management service (merge/undo/preview).

    Constructs a ``TagManagementService`` from the five repositories it
    depends on, mirroring the inline construction used by the CLI. The
    repositories are stateless, so a fresh instance per request is cheap.

    Returns
    -------
    TagManagementService
        A service instance wired with all required repositories.
    """
    from chronovista.repositories.canonical_tag_repository import (
        CanonicalTagRepository,
    )
    from chronovista.repositories.entity_alias_repository import (
        EntityAliasRepository,
    )
    from chronovista.repositories.named_entity_repository import (
        NamedEntityRepository,
    )
    from chronovista.repositories.tag_alias_repository import TagAliasRepository
    from chronovista.repositories.tag_operation_log_repository import (
        TagOperationLogRepository,
    )
    from chronovista.services.tag_management import TagManagementService

    return TagManagementService(
        canonical_tag_repo=CanonicalTagRepository(),
        tag_alias_repo=TagAliasRepository(),
        named_entity_repo=NamedEntityRepository(),
        entity_alias_repo=EntityAliasRepository(),
        operation_log_repo=TagOperationLogRepository(),
    )


def get_video_category_repository() -> VideoCategoryRepository:
    """
    Dependency providing a VideoCategoryRepository via the DI container.

    Wires the container's repository factory into FastAPI's ``Depends()``
    (issue #256), so endpoints inject the repository instead of constructing
    queries inline. The repository is session-agnostic — the session flows in
    per method call — so a fresh per-request instance is cheap, and tests can
    override this dependency to substitute a fake.

    Returns
    -------
    VideoCategoryRepository
        A repository instance for video category operations.
    """
    from chronovista.container import container

    return container.create_video_category_repository()


def get_video_tag_repository() -> VideoTagRepository:
    """Dependency providing a VideoTagRepository via the DI container (#256)."""
    from chronovista.container import container

    return container.create_video_tag_repository()


class StatsRepositories(NamedTuple):
    """The repositories whose row counts make up the app-info database stats.

    Bundled so the app-info endpoint injects one dependency instead of six
    (issue #256); each is a fresh, session-agnostic repository from the DI
    container. Named access (``repos.video``) keeps the call sites readable.

    Notes
    -----
    Always inject this by passing the factory explicitly —
    ``Depends(get_stats_repositories)`` — never the bare ``Depends()`` idiom:
    FastAPI would try to treat this NamedTuple's repository-typed fields as
    request-model fields and crash at startup.

    This bundle is 1:1 with ``DatabaseStats``. For an endpoint needing a
    different subset of counts, add a second bundle rather than stretching this
    one to cover an unrelated shape.
    """

    video: VideoRepository
    channel: ChannelRepository
    playlist: PlaylistRepository
    transcript: VideoTranscriptRepository
    correction: TranscriptCorrectionRepository
    canonical_tag: CanonicalTagRepository


def get_stats_repositories() -> StatsRepositories:
    """
    Dependency bundling the repositories the app-info endpoint counts.

    Wires the container's repository factories into FastAPI's ``Depends()``
    (issue #256) so the endpoint reads row counts via ``repo.count(session)``
    instead of building ``select(func.count())`` inline. The repositories are
    session-agnostic, so fresh per-request instances are cheap.

    Returns
    -------
    StatsRepositories
        The six repositories whose counts populate ``DatabaseStats``.
    """
    from chronovista.container import container

    return StatsRepositories(
        video=container.create_video_repository(),
        channel=container.create_channel_repository(),
        playlist=container.create_playlist_repository(),
        transcript=container.create_video_transcript_repository(),
        correction=container.create_transcript_correction_repository(),
        canonical_tag=container.create_canonical_tag_repository(),
    )


def get_canonical_tag_repository() -> CanonicalTagRepository:
    """Dependency providing a CanonicalTagRepository via the container (#256)."""
    from chronovista.container import container

    return container.create_canonical_tag_repository()


def get_video_repository() -> VideoRepository:
    """Dependency providing a VideoRepository via the DI container (issue #256)."""
    from chronovista.container import container

    return container.create_video_repository()


def get_channel_repository() -> ChannelRepository:
    """Dependency providing a ChannelRepository via the DI container (#256)."""
    from chronovista.container import container

    return container.create_channel_repository()


def get_entity_mention_repository() -> EntityMentionRepository:
    """Dependency providing an EntityMentionRepository via the container (#256)."""
    from chronovista.container import container

    return container.create_entity_mention_repository()


def get_entity_alias_repository() -> EntityAliasRepository:
    """Dependency providing an EntityAliasRepository via the container (#256)."""
    from chronovista.container import container

    return container.create_entity_alias_repository()


def get_named_entity_repository() -> NamedEntityRepository:
    """Dependency providing a NamedEntityRepository via the container (#256)."""
    from chronovista.container import container

    return container.create_named_entity_repository()


def get_batch_correction_service() -> "BatchCorrectionService":
    """
    Dependency providing a BatchCorrectionService via the DI container.

    Replaces the batch-corrections router's module-level service singleton
    (issue #256) with a per-request, container-wired instance. The batch service
    wraps a TranscriptCorrectionService; all three repositories are stateless, so
    per-request construction is cheap. The correction and segment repositories are
    shared between the two services, mirroring the original singleton wiring.

    Returns
    -------
    BatchCorrectionService
        A service wired with a correction service and the segment/correction repos.
    """
    from chronovista.container import container
    from chronovista.services.batch_correction_service import BatchCorrectionService
    from chronovista.services.transcript_correction_service import (
        TranscriptCorrectionService,
    )

    correction_repo = container.create_transcript_correction_repository()
    segment_repo = container.create_transcript_segment_repository()
    correction_service = TranscriptCorrectionService(
        correction_repo=correction_repo,
        segment_repo=segment_repo,
        transcript_repo=container.create_video_transcript_repository(),
    )
    return BatchCorrectionService(
        correction_service=correction_service,
        segment_repo=segment_repo,
        correction_repo=correction_repo,
    )


def get_transcript_segment_repository() -> TranscriptSegmentRepository:
    """Dependency providing a TranscriptSegmentRepository via the container (#256)."""
    from chronovista.container import container

    return container.create_transcript_segment_repository()


def get_video_transcript_repository() -> VideoTranscriptRepository:
    """Dependency providing a VideoTranscriptRepository via the container (#256)."""
    from chronovista.container import container

    return container.create_video_transcript_repository()


def get_user_language_preference_repository() -> UserLanguagePreferenceRepository:
    """Dependency providing a UserLanguagePreferenceRepository via the container (#256)."""
    from chronovista.container import container

    return container.create_user_language_preference_repository()


def get_transcript_service() -> "TranscriptService":
    """Dependency providing the shared TranscriptService via the container (#256).

    Replaces the transcripts router's module-level _transcript_service singleton.
    The container caches this service (``@cached_property``), so this returns the
    same instance across requests, preserving the prior singleton semantics.
    """
    from chronovista.container import container

    return container.transcript_service


def get_topic_category_repository() -> TopicCategoryRepository:
    """Dependency providing a TopicCategoryRepository via the container (#256)."""
    from chronovista.container import container

    return container.create_topic_category_repository()


def get_playlist_membership_repository() -> PlaylistMembershipRepository:
    """Dependency providing a PlaylistMembershipRepository via the container (#256)."""
    from chronovista.container import container

    return container.create_playlist_membership_repository()


def get_transcript_correction_repository() -> TranscriptCorrectionRepository:
    """Dependency providing a TranscriptCorrectionRepository via the container (#256)."""
    from chronovista.container import container

    return container.create_transcript_correction_repository()


def get_playlist_repository() -> PlaylistRepository:
    """Dependency providing a PlaylistRepository via the container (#256)."""
    from chronovista.container import container

    return container.create_playlist_repository()


def get_user_video_repository() -> UserVideoRepository:
    """Dependency providing a UserVideoRepository via the container (#256)."""
    from chronovista.container import container

    return container.create_user_video_repository()


def get_transcript_correction_service() -> "TranscriptCorrectionService":
    """
    Dependency providing a TranscriptCorrectionService via the DI container.

    Replaces the router's module-level service singleton (issue #256) with a
    per-request, container-wired instance. The service is stateless (it holds
    only its three repositories), so per-request construction is cheap.

    Returns
    -------
    TranscriptCorrectionService
        A service wired with the correction, segment, and transcript repos.
    """
    from chronovista.container import container
    from chronovista.services.transcript_correction_service import (
        TranscriptCorrectionService,
    )

    return TranscriptCorrectionService(
        correction_repo=container.create_transcript_correction_repository(),
        segment_repo=container.create_transcript_segment_repository(),
        transcript_repo=container.create_video_transcript_repository(),
    )


def get_entity_curation_service() -> "EntityCurationService":
    """
    Dependency providing an EntityCurationService via the DI container (#256).

    Replaces the router's module-level _entity_curation_service singleton with a
    per-request, container-wired instance. The service is stateless (it holds
    only its two repositories plus a normalizer it constructs), so per-request
    construction is cheap.

    Returns
    -------
    EntityCurationService
        A service wired with the named-entity and entity-operation-log repos.
    """
    from chronovista.container import container
    from chronovista.services.entity_curation_service import EntityCurationService

    return EntityCurationService(
        named_entity_repo=container.create_named_entity_repository(),
        operation_log_repo=container.create_entity_operation_log_repository(),
    )


def get_recovery_deps() -> tuple[CDXClient, PageParser, RateLimiter]:
    """
    Dependency for recovery service components.

    Creates a CDXClient and PageParser per-call (they hold no
    request-scoped state) and returns the module-level RateLimiter
    singleton so that all recovery API calls share one token bucket.

    Returns
    -------
    tuple[CDXClient, PageParser, RateLimiter]
        A 3-tuple of (cdx_client, page_parser, rate_limiter) that
        recovery endpoints can unpack for use with the orchestrator.
    """
    cache_dir = settings.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    cdx_client = CDXClient(cache_dir=cache_dir)
    page_parser = PageParser(rate_limiter=_recovery_rate_limiter)

    return cdx_client, page_parser, _recovery_rate_limiter
