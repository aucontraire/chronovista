"""Transcript endpoints for viewing, retrieving, and downloading transcript data."""

import logging
import re
from datetime import datetime
from typing import Optional, Union

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.routers.responses import (
    CONFLICT_RESPONSE,
    GET_ITEM_ERRORS,
    LIST_ERRORS,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
)
from chronovista.api.schemas.responses import ApiResponse, PaginationMeta
from chronovista.api.schemas.settings import (
    MultiTranscriptDownloadResponse,
    TranscriptDownloadResult,
)
from chronovista.api.schemas.transcripts import (
    SegmentListResponse,
    TranscriptDownloadResponse,
    TranscriptFull,
    TranscriptLanguage,
    TranscriptLanguagesResponse,
    TranscriptResponse,
    TranscriptSegment,
)
from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
from chronovista.db.models import TranscriptSegment as SegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as TranscriptDB
from chronovista.exceptions import (
    APIValidationError,
    ConflictError,
    NotFoundError,
    RateLimitError,
)
from chronovista.models.enums import AvailabilityStatus
from chronovista.models.user_language_preference import (
    UserLanguagePreference as UserLanguagePreferenceDomain,
)
from chronovista.models.video_transcript import VideoTranscriptCreate
from chronovista.repositories.user_language_preference_repository import (
    UserLanguagePreferenceRepository,
)
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
)
from chronovista.services.preference_aware_transcript_filter import (
    PreferenceAwareTranscriptFilter,
)
from chronovista.services.transcript_service import (
    TranscriptNotFoundError,
    TranscriptService,
    TranscriptServiceError,
    TranscriptServiceUnavailableError,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])

# Regex for YouTube video ID validation: exactly 11 chars, [A-Za-z0-9_-]
_VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")

# In-flight download guard: tracks video_ids currently being downloaded
_downloads_in_progress: set[str] = set()

# Module-level service/repository singletons
_transcript_service = TranscriptService()
_transcript_repo = VideoTranscriptRepository()
_pref_repo = UserLanguagePreferenceRepository()
_pref_filter = PreferenceAwareTranscriptFilter()

# Default user_id for single-user app
DEFAULT_USER_ID = "default_user"


def get_language_name(code: str) -> str:
    """
    Get human-readable language name from code.

    BCP-47 language codes are case-insensitive per RFC 5646.
    This function performs case-insensitive lookup to ensure robust matching.

    Parameters
    ----------
    code : str
        BCP-47 language code (case-insensitive).

    Returns
    -------
    str
        Human-readable language name, or the code itself if unknown.
    """
    # Lowercase lookup dictionary for case-insensitive matching
    names = {
        "en": "English",
        "en-us": "English (US)",
        "en-gb": "English (UK)",
        "es": "Spanish",
        "es-es": "Spanish (Spain)",
        "es-mx": "Spanish (Mexico)",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "pt": "Portuguese",
        "pt-br": "Portuguese (Brazil)",
        "zh-cn": "Chinese (Simplified)",
        "zh-tw": "Chinese (Traditional)",
        "ja": "Japanese",
        "ko": "Korean",
        "ru": "Russian",
        "ar": "Arabic",
        "hi": "Hindi",
    }
    return names.get(code.lower(), code)


@router.get(
    "/videos/{video_id}/transcript/languages",
    response_model=TranscriptLanguagesResponse,
    responses=GET_ITEM_ERRORS,
)
async def get_transcript_languages(
    video_id: str = Path(..., min_length=11, max_length=11),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    session: AsyncSession = Depends(get_db),
) -> TranscriptLanguagesResponse:
    """
    Get available transcript languages for a video.

    Parameters
    ----------
    video_id : str
        YouTube video ID (11 characters).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    TranscriptLanguagesResponse
        List of available transcript languages.

    Raises
    ------
    NotFoundError
        If video not found (404).
    """
    # Check video exists
    video_query = select(VideoDB).where(VideoDB.video_id == video_id)
    # Apply availability filter unless include_unavailable is True
    if not include_unavailable:
        video_query = video_query.where(VideoDB.availability_status == AvailabilityStatus.AVAILABLE)

    video_result = await session.execute(video_query)
    if not video_result.scalar_one_or_none():
        raise NotFoundError(
            resource_type="Video",
            identifier=video_id,
            hint="Verify the video ID or run: chronovista sync videos",
        )

    # Get transcripts
    result = await session.execute(
        select(TranscriptDB)
        .where(TranscriptDB.video_id == video_id)
        .order_by(TranscriptDB.is_cc.desc(), TranscriptDB.downloaded_at.desc())
    )
    transcripts = result.scalars().all()

    languages = [
        TranscriptLanguage(
            language_code=t.language_code,
            language_name=get_language_name(t.language_code),
            transcript_type=(
                "manual" if t.is_cc or t.transcript_type == "MANUAL" else "auto_generated"
            ),
            is_translatable=True,  # Default - could check from API
            downloaded_at=t.downloaded_at,
        )
        for t in transcripts
    ]

    return TranscriptLanguagesResponse(data=languages)


@router.get("/videos/{video_id}/transcript", response_model=TranscriptResponse, responses=GET_ITEM_ERRORS)
async def get_transcript(
    video_id: str = Path(..., min_length=11, max_length=11),
    language: Optional[str] = Query(
        None, description="Language code (default: first available)"
    ),
    session: AsyncSession = Depends(get_db),
) -> TranscriptResponse:
    """
    Get full transcript for a video.

    Parameters
    ----------
    video_id : str
        YouTube video ID (11 characters).
    language : Optional[str]
        Language code to retrieve (default: first available, preferring manual).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    TranscriptResponse
        Full transcript content with metadata.

    Raises
    ------
    NotFoundError
        If transcript not found (404).
    """
    # Build query
    query = select(TranscriptDB).where(TranscriptDB.video_id == video_id)

    if language:
        # Case-insensitive match for BCP-47 language codes (RFC 5646)
        query = query.where(func.lower(TranscriptDB.language_code) == language.lower())
    else:
        # Default selection: prefer manual/CC, then by download date
        query = query.order_by(
            TranscriptDB.is_cc.desc(), TranscriptDB.downloaded_at.desc()
        )

    result = await session.execute(query)
    transcript = result.scalars().first()

    if not transcript:
        if language:
            raise NotFoundError(
                resource_type="Transcript",
                identifier=f"{video_id}/{language}",
                hint=f"Check available languages at: GET /api/v1/videos/{video_id}/transcript/languages",
            )
        raise NotFoundError(
            resource_type="Transcript",
            identifier=video_id,
            hint=f"Run: chronovista sync transcripts --video-id {video_id}",
        )

    return TranscriptResponse(
        data=TranscriptFull(
            video_id=transcript.video_id,
            language_code=transcript.language_code,
            transcript_type="manual" if transcript.is_cc else "auto_generated",
            full_text=transcript.transcript_text,
            segment_count=transcript.segment_count or 0,
            downloaded_at=transcript.downloaded_at,
        )
    )


@router.get(
    "/videos/{video_id}/transcript/segments",
    response_model=SegmentListResponse,
    responses=LIST_ERRORS,
)
async def get_transcript_segments(
    video_id: str = Path(..., min_length=11, max_length=11),
    language: Optional[str] = Query(
        None, description="Language code (default: first available)"
    ),
    start_time: Optional[float] = Query(
        None, ge=0, description="Filter segments starting at or after (seconds)"
    ),
    end_time: Optional[float] = Query(
        None, ge=0, description="Filter segments ending before (seconds)"
    ),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
) -> SegmentListResponse:
    """
    Get paginated transcript segments for a video.

    Parameters
    ----------
    video_id : str
        YouTube video ID (11 characters).
    language : Optional[str]
        Language code to retrieve (default: first available, preferring manual).
    start_time : Optional[float]
        Filter segments starting at or after this time (seconds).
    end_time : Optional[float]
        Filter segments ending before this time (seconds).
    limit : int
        Items per page (1-200, default 50).
    offset : int
        Pagination offset (default 0).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    SegmentListResponse
        Paginated list of transcript segments.
    """
    # First, determine the language code to use
    if not language:
        # Get default transcript
        transcript_query = (
            select(TranscriptDB)
            .where(TranscriptDB.video_id == video_id)
            .order_by(TranscriptDB.is_cc.desc(), TranscriptDB.downloaded_at.desc())
        )
        result = await session.execute(transcript_query)
        transcript = result.scalars().first()
        if not transcript:
            return SegmentListResponse(
                data=[],
                pagination=PaginationMeta(
                    total=0, limit=limit, offset=offset, has_more=False
                ),
            )
        language = transcript.language_code

    # Build segments query - case-insensitive language match (RFC 5646)
    query = (
        select(SegmentDB)
        .where(SegmentDB.video_id == video_id)
        .where(func.lower(SegmentDB.language_code) == language.lower())
    )

    # Apply time filters
    if start_time is not None:
        query = query.where(SegmentDB.start_time >= start_time)
    if end_time is not None:
        query = query.where(SegmentDB.end_time <= end_time)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(SegmentDB.start_time.asc()).offset(offset).limit(limit)

    segment_result = await session.execute(query)
    segments: list[SegmentDB] = list(segment_result.scalars().all())

    # Derive correction metadata for all segments in a single query
    segment_ids = [seg.id for seg in segments]
    correction_meta: dict[int, tuple[datetime | None, int]] = {}
    if segment_ids:
        meta_query = (
            select(
                TranscriptCorrectionDB.segment_id,
                func.max(TranscriptCorrectionDB.corrected_at).label("latest_corrected_at"),
                func.count().label("correction_count"),
            )
            .where(TranscriptCorrectionDB.segment_id.in_(segment_ids))
            .group_by(TranscriptCorrectionDB.segment_id)
        )
        meta_result = await session.execute(meta_query)
        for row in meta_result.all():
            correction_meta[row.segment_id] = (row.latest_corrected_at, row.correction_count)

    items = [
        TranscriptSegment(
            id=seg.id,
            text=seg.corrected_text if seg.has_correction and seg.corrected_text else seg.text,
            start_time=seg.start_time,
            end_time=seg.end_time,
            duration=seg.duration,
            has_correction=seg.has_correction,
            corrected_at=correction_meta.get(seg.id, (None, 0))[0],
            correction_count=correction_meta.get(seg.id, (None, 0))[1],
        )
        for seg in segments
    ]

    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    return SegmentListResponse(data=items, pagination=pagination)


# OpenAPI error responses for the download endpoint
_DOWNLOAD_ERRORS = {
    **NOT_FOUND_RESPONSE,
    **VALIDATION_ERROR_RESPONSE,
    **UNAUTHORIZED_RESPONSE,
    **CONFLICT_RESPONSE,
    429: {
        "description": "Download already in progress for this video",
    },
    503: {
        "description": "YouTube transcript service unavailable or rate-limited",
    },
}


@router.post(
    "/videos/{video_id}/transcript/download",
    status_code=200,
    responses=_DOWNLOAD_ERRORS,
    summary="Download transcript from YouTube",
)
async def download_transcript(
    video_id: str = Path(..., description="YouTube video ID (11 characters)"),
    language: Optional[str] = Query(
        None, description="BCP-47 language code (default: user's preferred language)"
    ),
    session: AsyncSession = Depends(get_db),
) -> Union[ApiResponse[TranscriptDownloadResponse], ApiResponse[MultiTranscriptDownloadResponse]]:
    """Download a transcript from YouTube for the given video.

    Fetches the transcript from YouTube's transcript API and saves it
    to the local database. Returns metadata about the downloaded transcript.

    When ``language`` is provided, downloads that single language (backward
    compatible). When omitted, checks user language preferences and downloads
    all FLUENT + LEARNING languages automatically (CURIOUS excluded). If no
    preferences are configured, falls back to English (FR-013).

    Parameters
    ----------
    video_id : str
        YouTube video ID (exactly 11 characters, ``[A-Za-z0-9_-]``).
    language : Optional[str]
        BCP-47 language code to prefer. When omitted the user's preferred
        languages are used.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    ApiResponse[TranscriptDownloadResponse] | ApiResponse[MultiTranscriptDownloadResponse]
        Single-language metadata when ``language`` is provided, or
        multi-language result when preference-aware download is used.

    Raises
    ------
    APIValidationError
        If the video_id format is invalid (422).
    NotFoundError
        If no transcript is available on YouTube (404).
    ConflictError
        If the transcript already exists in the database (409).
    RateLimitError
        If a download is already in progress for this video (429).
    TranscriptServiceUnavailableError
        If YouTube is rate-limiting or the service is unavailable (503).
    """
    # 1. Validate video_id format before any service/DB call
    if not _VIDEO_ID_PATTERN.match(video_id):
        raise APIValidationError(
            message="Invalid video ID format. Must be exactly 11 characters matching [A-Za-z0-9_-].",
            details={"field": "video_id"},
        )

    # 2. In-flight download guard
    if video_id in _downloads_in_progress:
        raise RateLimitError(
            message=f"A download is already in progress for video '{video_id}'.",
            details={"video_id": video_id},
        )

    _downloads_in_progress.add(video_id)
    try:
        # 3. Get existing transcripts for this video
        existing_transcripts = await _transcript_repo.get_video_transcripts(
            session, video_id
        )
        existing_lang_codes = {
            t.language_code.lower() for t in existing_transcripts
        }

        # --- Path A: Explicit language override (FR-014) ---
        if language:
            # Per-language 409 check (FR-028)
            if language.lower() in existing_lang_codes:
                raise ConflictError(
                    message=(
                        f"Video '{video_id}' already has a transcript in "
                        f"'{language}'. Delete it first if you want to re-download."
                    ),
                    details={"video_id": video_id, "language": language},
                )

            # Download single language (existing behavior)
            return await _download_single_language(
                video_id=video_id,
                language=language,
                session=session,
            )

        # --- Check for user preferences ---
        user_prefs = await _pref_repo.get_user_preferences(
            session, DEFAULT_USER_ID
        )

        # --- Path C: No preferences → preserve existing default behavior (FR-013) ---
        if not user_prefs:
            # Original behavior: reject if ANY transcript exists
            if existing_transcripts:
                raise ConflictError(
                    message=f"Video '{video_id}' already has a transcript. "
                    "Delete it first if you want to re-download.",
                    details={"video_id": video_id},
                )
            return await _download_single_language(
                video_id=video_id,
                language=None,
                session=session,
            )

        # --- Path B: Preference-aware multi-language download (FR-011, FR-012) ---
        # Convert DB ORM models to Pydantic domain models for the filter service
        domain_prefs = [
            UserLanguagePreferenceDomain.model_validate(p) for p in user_prefs
        ]
        # Compute target languages from preferences (Fluent + Learning only)
        preferred_languages = _pref_filter.get_download_languages(
            # Pass preference language codes as "available" so the filter
            # returns Fluent + Learning codes. Actual YouTube availability
            # is checked per-language during download.
            available_languages=[
                str(p.language_code) for p in domain_prefs
            ],
            user_preferences=domain_prefs,
        )

        if not preferred_languages:
            # No Fluent/Learning preferences → fall back to default (English)
            if existing_transcripts:
                raise ConflictError(
                    message=f"Video '{video_id}' already has a transcript. "
                    "Delete it first if you want to re-download.",
                    details={"video_id": video_id},
                )
            return await _download_single_language(
                video_id=video_id,
                language=None,
                session=session,
            )

        # Filter out already-downloaded languages
        remaining_languages = [
            lang for lang in preferred_languages
            if lang.lower() not in existing_lang_codes
        ]

        # All preferred languages already downloaded → 409
        if not remaining_languages:
            already_names = [
                f"{get_language_name(lang)} ({lang})"
                for lang in preferred_languages
            ]
            raise ConflictError(
                message=(
                    "All preferred language transcripts already exist for "
                    f"video '{video_id}': {', '.join(already_names)}."
                ),
                details={
                    "video_id": video_id,
                    "existing_languages": preferred_languages,
                },
            )

        # Download each remaining language
        downloaded: list[TranscriptDownloadResult] = []
        skipped: list[str] = []
        failed: list[str] = []

        for lang_code in remaining_languages:
            try:
                enhanced_transcript = await _transcript_service.get_transcript(
                    video_id=video_id,
                    language_codes=[lang_code],
                )

                transcript_create = VideoTranscriptCreate(
                    video_id=enhanced_transcript.video_id,
                    language_code=enhanced_transcript.language_code,
                    transcript_text=enhanced_transcript.transcript_text,
                    transcript_type=enhanced_transcript.transcript_type,
                    download_reason=enhanced_transcript.download_reason,
                    confidence_score=enhanced_transcript.confidence_score,
                    is_cc=enhanced_transcript.is_cc,
                    is_auto_synced=enhanced_transcript.is_auto_synced,
                    track_kind=enhanced_transcript.track_kind,
                    caption_name=enhanced_transcript.caption_name,
                )

                db_transcript = await _transcript_repo.create_or_update(
                    session,
                    transcript_create,
                    raw_transcript_data=(
                        enhanced_transcript.raw_transcript_data
                        if enhanced_transcript.raw_transcript_data
                        else None
                    ),
                )

                transcript_type_display = (
                    "manual"
                    if db_transcript.is_cc
                    or db_transcript.transcript_type == "MANUAL"
                    else "auto_generated"
                )

                downloaded.append(
                    TranscriptDownloadResult(
                        language_code=db_transcript.language_code,
                        language_name=get_language_name(
                            db_transcript.language_code
                        ),
                        transcript_type=transcript_type_display,
                        segment_count=db_transcript.segment_count or 0,
                        downloaded_at=db_transcript.downloaded_at,
                    )
                )

            except TranscriptNotFoundError:
                skipped.append(lang_code)
                logger.info(
                    "No transcript available in '%s' for video %s — skipped",
                    lang_code,
                    video_id,
                )

            except (
                TranscriptServiceUnavailableError,
                TranscriptServiceError,
            ):
                failed.append(lang_code)
                logger.warning(
                    "Failed to download '%s' transcript for video %s",
                    lang_code,
                    video_id,
                    exc_info=True,
                )

        # Commit all successful downloads in one transaction
        if downloaded:
            await session.commit()

        # Build attempted languages list with display names (FR-015)
        attempted_languages = [
            f"{get_language_name(lang)} ({lang})"
            for lang in remaining_languages
        ]

        # If NOTHING was downloaded and everything was skipped/failed → 404
        if not downloaded:
            raise NotFoundError(
                resource_type="Transcript",
                identifier=video_id,
                hint=(
                    "No transcript available on YouTube for any of the "
                    f"preferred languages: {', '.join(attempted_languages)}."
                ),
            )

        response_data = MultiTranscriptDownloadResponse(
            video_id=video_id,
            downloaded=downloaded,
            skipped=skipped,
            failed=failed,
            attempted_languages=attempted_languages,
        )

        return ApiResponse[MultiTranscriptDownloadResponse](data=response_data)

    finally:
        _downloads_in_progress.discard(video_id)


async def _download_single_language(
    video_id: str,
    language: Optional[str],
    session: AsyncSession,
) -> ApiResponse[TranscriptDownloadResponse]:
    """Download a single language transcript and return the standard response.

    This is the original download path extracted into a helper so it can be
    reused by both the explicit-language and no-preferences code paths.

    Parameters
    ----------
    video_id : str
        YouTube video ID.
    language : Optional[str]
        BCP-47 language code, or None for default (English).
    session : AsyncSession
        Database session.

    Returns
    -------
    ApiResponse[TranscriptDownloadResponse]
        Metadata about the downloaded transcript.
    """
    language_codes: list[str] | None = None
    if language:
        language_codes = [language]

    try:
        enhanced_transcript = await _transcript_service.get_transcript(
            video_id=video_id,
            language_codes=language_codes,
        )
    except TranscriptNotFoundError as exc:
        raise NotFoundError(
            resource_type="Transcript",
            identifier=video_id,
            hint="No transcript is available on YouTube for this video.",
        ) from exc
    except TranscriptServiceUnavailableError as exc:
        from chronovista.api.schemas.responses import (
            ErrorCode,
            ProblemJSONResponse,
            get_error_type_uri,
            ERROR_TITLES,
        )
        import uuid

        return ProblemJSONResponse(  # type: ignore[return-value]
            status_code=503,
            content={
                "type": get_error_type_uri(ErrorCode.SERVICE_UNAVAILABLE),
                "title": ERROR_TITLES[ErrorCode.SERVICE_UNAVAILABLE],
                "status": 503,
                "detail": f"YouTube transcript service is unavailable: {exc}",
                "instance": f"/api/v1/videos/{video_id}/transcript/download",
                "code": ErrorCode.SERVICE_UNAVAILABLE.value,
                "request_id": str(uuid.uuid4()),
            },
        )
    except TranscriptServiceError as exc:
        error_msg = str(exc).lower()
        if any(kw in error_msg for kw in ["rate limit", "too many", "quota"]):
            from chronovista.api.schemas.responses import (
                ErrorCode,
                ProblemJSONResponse,
                get_error_type_uri,
                ERROR_TITLES,
            )
            import uuid

            return ProblemJSONResponse(  # type: ignore[return-value]
                status_code=503,
                content={
                    "type": get_error_type_uri(ErrorCode.SERVICE_UNAVAILABLE),
                    "title": ERROR_TITLES[ErrorCode.SERVICE_UNAVAILABLE],
                    "status": 503,
                    "detail": f"YouTube is rate-limiting transcript requests: {exc}",
                    "instance": f"/api/v1/videos/{video_id}/transcript/download",
                    "code": ErrorCode.SERVICE_UNAVAILABLE.value,
                    "request_id": str(uuid.uuid4()),
                },
            )
        raise

    transcript_create = VideoTranscriptCreate(
        video_id=enhanced_transcript.video_id,
        language_code=enhanced_transcript.language_code,
        transcript_text=enhanced_transcript.transcript_text,
        transcript_type=enhanced_transcript.transcript_type,
        download_reason=enhanced_transcript.download_reason,
        confidence_score=enhanced_transcript.confidence_score,
        is_cc=enhanced_transcript.is_cc,
        is_auto_synced=enhanced_transcript.is_auto_synced,
        track_kind=enhanced_transcript.track_kind,
        caption_name=enhanced_transcript.caption_name,
    )

    db_transcript = await _transcript_repo.create_or_update(
        session,
        transcript_create,
        raw_transcript_data=(
            enhanced_transcript.raw_transcript_data
            if enhanced_transcript.raw_transcript_data
            else None
        ),
    )
    await session.commit()

    transcript_type_display = (
        "manual"
        if db_transcript.is_cc or db_transcript.transcript_type == "MANUAL"
        else "auto_generated"
    )

    lang_code = db_transcript.language_code
    lang_name = get_language_name(lang_code)

    response_data = TranscriptDownloadResponse(
        video_id=db_transcript.video_id,
        language_code=lang_code,
        language_name=lang_name,
        transcript_type=transcript_type_display,
        segment_count=db_transcript.segment_count or 0,
        downloaded_at=db_transcript.downloaded_at,
    )

    return ApiResponse[TranscriptDownloadResponse](data=response_data)
