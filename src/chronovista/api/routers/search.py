"""Search endpoints for transcript segment search."""


from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from chronovista.api.deps import get_db, require_auth
from chronovista.api.routers.responses import (
    BAD_REQUEST_RESPONSE,
    INTERNAL_ERROR_RESPONSE,
    LIST_ERRORS,
    UNAUTHORIZED_RESPONSE,
)
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.search import (
    DescriptionSearchResponse,
    DescriptionSearchResult,
    SearchResponse,
    SearchResultSegment,
    TitleSearchResponse,
    TitleSearchResult,
)
from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import TranscriptSegment as SegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as TranscriptDB
from chronovista.exceptions import BadRequestError
from chronovista.models.enums import AvailabilityStatus
from chronovista.repositories.transcript_segment_repository import _escape_like_pattern

router = APIRouter(dependencies=[Depends(require_auth)])

SEARCH_ERRORS = {**BAD_REQUEST_RESPONSE, **UNAUTHORIZED_RESPONSE, **INTERNAL_ERROR_RESPONSE}


def _display_text(seg: "SegmentDB") -> str:
    """Return corrected text if available, otherwise original."""
    if seg.has_correction and seg.corrected_text:
        return seg.corrected_text
    return seg.text


def count_query_matches(text: str, query_terms: list[str]) -> int:
    """
    Count how many query terms appear in the text.

    Parameters
    ----------
    text : str
        The text to search in.
    query_terms : List[str]
        List of query terms to search for.

    Returns
    -------
    int
        Number of query terms found in the text.
    """
    text_lower = text.lower()
    return sum(1 for term in query_terms if term.lower() in text_lower)


@router.get("/search/segments", response_model=SearchResponse, responses=LIST_ERRORS)
async def search_segments(
    q: str = Query(
        ..., min_length=2, max_length=500, description="Search query (2-500 characters)"
    ),
    video_id: str | None = Query(
        None, min_length=11, max_length=11, description="Limit to specific video"
    ),
    language: str | None = Query(None, description="Limit to specific language"),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    limit: int = Query(20, ge=1, le=100, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """
    Search transcript segments by text query.

    Uses case-insensitive substring matching (ILIKE).
    Results ordered by video upload date (desc), then segment start time (asc).

    Parameters
    ----------
    q : str
        Search query string (2-500 characters).
    video_id : Optional[str]
        Limit search to specific video ID (11 characters).
    language : Optional[str]
        Limit search to specific language code.
    limit : int
        Results per page (1-100, default 20).
    offset : int
        Pagination offset (default 0).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    SearchResponse
        Search results with pagination metadata.

    Raises
    ------
    BadRequestError
        If search query is empty after stripping whitespace (400).
    """
    # Validate and clean query
    query_text = q.strip()
    if not query_text:
        raise BadRequestError(
            message="Search query cannot be empty",
            details={"field": "q", "constraint": "non_empty"},
        )

    # Reject NULL bytes
    if "\x00" in query_text:
        raise BadRequestError(
            message="Search query contains invalid characters",
            details={"field": "q", "constraint": "no_null_bytes"},
        )

    # Escape special LIKE characters for literal phrase matching
    escaped_query = _escape_like_pattern(query_text)

    # Build base query with joins (including Channel for eager loading)
    query = (
        select(SegmentDB, TranscriptDB, VideoDB, ChannelDB)
        .join(
            TranscriptDB,
            and_(
                SegmentDB.video_id == TranscriptDB.video_id,
                SegmentDB.language_code == TranscriptDB.language_code,
            ),
        )
        .join(VideoDB, SegmentDB.video_id == VideoDB.video_id)
        .outerjoin(ChannelDB, VideoDB.channel_id == ChannelDB.channel_id)
    )

    # Apply availability filter unless include_unavailable is True
    if not include_unavailable:
        query = query.where(VideoDB.availability_status == AvailabilityStatus.AVAILABLE)

    # Apply ILIKE filter for the entire query as a single phrase
    # Search both original text and corrected text so corrections are findable
    query = query.where(
        or_(
            SegmentDB.text.ilike(f"%{escaped_query}%"),
            SegmentDB.corrected_text.ilike(f"%{escaped_query}%"),
        )
    )

    # Apply optional video filter (affects both available_languages and results)
    if video_id:
        query = query.where(SegmentDB.video_id == video_id)

    # Build a FRESH query specifically for extracting available languages
    # This avoids any potential issues from the complex joined base query
    # Only query transcript_segments directly to get ACTUAL language codes in results
    lang_base_query = (
        select(SegmentDB.language_code)
        .join(VideoDB, SegmentDB.video_id == VideoDB.video_id)
    )

    # Apply availability filter unless include_unavailable is True
    if not include_unavailable:
        lang_base_query = lang_base_query.where(VideoDB.availability_status == AvailabilityStatus.AVAILABLE)

    # Apply the same text search filter (single phrase, both original and corrected text)
    lang_base_query = lang_base_query.where(
        or_(
            SegmentDB.text.ilike(f"%{escaped_query}%"),
            SegmentDB.corrected_text.ilike(f"%{escaped_query}%"),
        )
    )

    # Apply optional video filter
    if video_id:
        lang_base_query = lang_base_query.where(SegmentDB.video_id == video_id)

    # Get distinct languages from matching segments
    languages_query = lang_base_query.distinct()
    languages_result = await session.execute(languages_query)
    available_languages = sorted([lang for (lang,) in languages_result.all()])

    # Apply language filter AFTER computing available_languages
    if language:
        # Case-insensitive comparison to handle BCP-47 casing variations
        # (e.g., "en-US" vs "en-us" vs "EN-US")
        query = query.where(func.lower(SegmentDB.language_code) == func.lower(language))

    # Get total count from filtered result set
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Apply ordering and pagination
    query = (
        query.order_by(VideoDB.upload_date.desc(), SegmentDB.start_time.asc())
        .offset(offset)
        .limit(limit)
    )

    result = await session.execute(query)
    rows = result.all()

    # Batch-fetch adjacent segments for context (eliminates N+1 queries).
    # Collect the segment IDs from the result set, then use LAG/LEAD window
    # functions in a single query to get prev/next text for all results.
    segment_ids = [segment.id for segment, _t, _v, _c in rows]
    context_map: dict[int, tuple[str | None, str | None]] = {}

    if segment_ids:
        # Use a CTE with window functions over each (video_id, language_code)
        # partition to get the previous and next segment text.
        partition = [SegmentDB.video_id, SegmentDB.language_code]
        order = SegmentDB.start_time.asc()
        # corrected_text takes precedence over text (matching _display_text)
        display_text_col = func.coalesce(SegmentDB.corrected_text, SegmentDB.text)

        context_cte = (
            select(
                SegmentDB.id.label("seg_id"),
                func.lag(display_text_col, 1)
                .over(partition_by=partition, order_by=order)
                .label("prev_text"),
                func.lead(display_text_col, 1)
                .over(partition_by=partition, order_by=order)
                .label("next_text"),
            )
            .where(
                # Only compute windows for segments in the same
                # (video_id, language_code) groups as our results.
                # This keeps the window computation bounded.
                and_(
                    SegmentDB.video_id.in_(
                        [s.video_id for s, _t, _v, _c in rows]
                    ),
                    SegmentDB.language_code.in_(
                        [s.language_code for s, _t, _v, _c in rows]
                    ),
                )
            )
            .cte("context_cte")
        )

        context_query = (
            select(
                context_cte.c.seg_id,
                context_cte.c.prev_text,
                context_cte.c.next_text,
            )
            .where(context_cte.c.seg_id.in_(segment_ids))
        )
        context_result = await session.execute(context_query)
        for seg_id, prev_text, next_text in context_result.all():
            ctx_before = prev_text[:200] if prev_text and len(prev_text) > 200 else prev_text
            ctx_after = next_text[:200] if next_text and len(next_text) > 200 else next_text
            context_map[seg_id] = (ctx_before, ctx_after)

    # Build response items using the pre-fetched context
    items: list[SearchResultSegment] = []
    for segment, _transcript, video, channel in rows:
        ctx_before, ctx_after = context_map.get(segment.id, (None, None))
        items.append(
            SearchResultSegment(
                segment_id=segment.id,
                video_id=segment.video_id,
                video_title=video.title,
                channel_title=channel.title if channel else None,
                language_code=segment.language_code,
                text=_display_text(segment),
                start_time=segment.start_time,
                end_time=segment.end_time,
                context_before=ctx_before,
                context_after=ctx_after,
                match_count=count_query_matches(_display_text(segment), [query_text]),
                video_upload_date=video.upload_date,
                availability_status=video.availability_status,
            )
        )

    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    return SearchResponse(
        data=items,
        pagination=pagination,
        available_languages=available_languages,
    )


@router.get("/search/titles", response_model=TitleSearchResponse, responses=SEARCH_ERRORS)
async def search_titles(
    q: str = Query(
        ..., min_length=2, max_length=500, description="Search query (2-500 characters)"
    ),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    limit: int = Query(50, ge=1, le=50, description="Maximum results (1-50, default 50)"),
    session: AsyncSession = Depends(get_db),
) -> TitleSearchResponse:
    """
    Search video titles.

    Uses case-insensitive substring matching (ILIKE) with implicit AND
    for multi-word queries. Returns results ordered by upload date (newest first),
    capped at the specified limit. Excludes deleted videos.

    Parameters
    ----------
    q : str
        Search query string (2-500 characters).
    limit : int
        Maximum number of results to return (1-50, default 50).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    TitleSearchResponse
        Title search results with total count.

    Raises
    ------
    BadRequestError
        If search query is empty after stripping whitespace (400).
    """
    query_text = q.strip()
    if not query_text:
        raise BadRequestError(
            message="Search query cannot be empty",
            details={"field": "q", "constraint": "non_empty"},
        )

    # Reject NULL bytes
    if "\x00" in query_text:
        raise BadRequestError(
            message="Search query contains invalid characters",
            details={"field": "q", "constraint": "no_null_bytes"},
        )

    # Escape special LIKE characters for literal phrase matching
    escaped_query = _escape_like_pattern(query_text)

    # Build conditions for reuse (count + results)
    conditions = []
    # Apply availability filter unless include_unavailable is True
    if not include_unavailable:
        conditions.append(VideoDB.availability_status == AvailabilityStatus.AVAILABLE)
    conditions.append(VideoDB.title.ilike(f"%{escaped_query}%"))

    # Get total count
    count_query = select(func.count()).select_from(
        select(VideoDB.video_id).where(*conditions).subquery()
    )
    total_result = await session.execute(count_query)
    total_count = total_result.scalar() or 0

    # Build results query with channel join, ordering, and limit
    results_query = (
        select(VideoDB.video_id, VideoDB.title, ChannelDB.title.label("channel_title"), VideoDB.upload_date, VideoDB.availability_status)
        .outerjoin(ChannelDB, VideoDB.channel_id == ChannelDB.channel_id)
        .where(*conditions)
        .order_by(VideoDB.upload_date.desc())
        .limit(limit)
    )
    result = await session.execute(results_query)
    rows = result.all()

    items = [
        TitleSearchResult(
            video_id=row.video_id,
            title=row.title,
            channel_title=row.channel_title,
            upload_date=row.upload_date,
            availability_status=row.availability_status,
        )
        for row in rows
    ]

    return TitleSearchResponse(data=items, total_count=total_count)


def _generate_snippet(description: str, query_terms: list[str], target_length: int = 200) -> str:
    """
    Generate a snippet from a description centered around the first match.

    Parameters
    ----------
    description : str
        The full description text.
    query_terms : list[str]
        Query terms to find in the description.
    target_length : int
        Approximate target snippet length (default 200).

    Returns
    -------
    str
        Snippet with ellipsis indicators if truncated.
    """
    if len(description) <= target_length:
        return description

    # Find the position of the first matching term (case-insensitive)
    desc_lower = description.lower()
    first_pos = len(description)  # Default to end if no match found
    for term in query_terms:
        pos = desc_lower.find(term.lower())
        if pos != -1 and pos < first_pos:
            first_pos = pos

    # Calculate window centered around the match
    half_window = target_length // 2
    start = max(0, first_pos - half_window)
    end = min(len(description), first_pos + len(query_terms[0]) + half_window)

    # Adjust to word boundaries
    if start > 0:
        # Find next space after start
        space_pos = description.find(" ", start)
        if space_pos != -1 and space_pos < first_pos:
            start = space_pos + 1

    if end < len(description):
        # Find previous space before end
        space_pos = description.rfind(" ", start, end)
        if space_pos != -1 and space_pos > first_pos:
            end = space_pos

    snippet = description[start:end]

    # Add ellipsis
    if start > 0:
        snippet = "..." + snippet
    if end < len(description):
        snippet = snippet + "..."

    return snippet


@router.get("/search/descriptions", response_model=DescriptionSearchResponse, responses=SEARCH_ERRORS)
async def search_descriptions(
    q: str = Query(
        ..., min_length=2, max_length=500, description="Search query (2-500 characters)"
    ),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    limit: int = Query(50, ge=1, le=50, description="Maximum results (1-50, default 50)"),
    session: AsyncSession = Depends(get_db),
) -> DescriptionSearchResponse:
    """
    Search video descriptions.

    Uses case-insensitive substring matching (ILIKE) with implicit AND
    for multi-word queries. Returns results with a ~200 character snippet
    centered around the first match location. Results ordered by upload date
    (newest first), capped at the specified limit. Excludes deleted videos
    and videos with null descriptions.

    Parameters
    ----------
    q : str
        Search query string (2-500 characters).
    limit : int
        Maximum number of results to return (1-50, default 50).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    DescriptionSearchResponse
        Description search results with snippets and total count.

    Raises
    ------
    BadRequestError
        If search query is empty after stripping whitespace (400).
    """
    query_text = q.strip()
    if not query_text:
        raise BadRequestError(
            message="Search query cannot be empty",
            details={"field": "q", "constraint": "non_empty"},
        )

    # Reject NULL bytes
    if "\x00" in query_text:
        raise BadRequestError(
            message="Search query contains invalid characters",
            details={"field": "q", "constraint": "no_null_bytes"},
        )

    # Escape special LIKE characters for literal phrase matching
    escaped_query = _escape_like_pattern(query_text)

    # Build conditions for reuse
    conditions: list[ColumnElement[bool]] = [VideoDB.description.isnot(None)]
    # Apply availability filter unless include_unavailable is True
    if not include_unavailable:
        conditions.append(VideoDB.availability_status == AvailabilityStatus.AVAILABLE)
    conditions.append(VideoDB.description.ilike(f"%{escaped_query}%"))

    # Get total count
    count_query = select(func.count()).select_from(
        select(VideoDB.video_id).where(*conditions).subquery()
    )
    total_result = await session.execute(count_query)
    total_count = total_result.scalar() or 0

    # Build results query with channel join
    results_query = (
        select(
            VideoDB.video_id,
            VideoDB.title,
            VideoDB.description,
            ChannelDB.title.label("channel_title"),
            VideoDB.upload_date,
            VideoDB.availability_status,
        )
        .outerjoin(ChannelDB, VideoDB.channel_id == ChannelDB.channel_id)
        .where(*conditions)
        .order_by(VideoDB.upload_date.desc())
        .limit(limit)
    )
    result = await session.execute(results_query)
    rows = result.all()

    items = [
        DescriptionSearchResult(
            video_id=row.video_id,
            title=row.title,
            channel_title=row.channel_title,
            upload_date=row.upload_date,
            snippet=_generate_snippet(row.description, [query_text]),
            availability_status=row.availability_status,
        )
        for row in rows
    ]

    return DescriptionSearchResponse(data=items, total_count=total_count)
