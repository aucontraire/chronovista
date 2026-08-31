"""Search endpoints for transcript segment search."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import (
    get_db,
    get_transcript_segment_repository,
    get_video_repository,
    require_auth,
)
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
from chronovista.db.models import TranscriptSegment as SegmentDB
from chronovista.exceptions import BadRequestError
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.repositories.video_repository import VideoRepository

router = APIRouter(dependencies=[Depends(require_auth)])

SEARCH_ERRORS = {
    **BAD_REQUEST_RESPONSE,
    **UNAUTHORIZED_RESPONSE,
    **INTERNAL_ERROR_RESPONSE,
}


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
    segment_repo: TranscriptSegmentRepository = Depends(
        get_transcript_segment_repository
    ),
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

    # Available-language facet: every language the phrase matches (no language
    # filter), so a caller can switch. Computed independently of the selected
    # language, matching the response contract.
    available_languages = await segment_repo.get_matching_languages(
        session,
        query_text=query_text,
        video_id=video_id,
        include_unavailable=include_unavailable,
    )

    # Paginated matching segments (with the selected language filter applied to
    # both the page and the total count).
    rows, total = await segment_repo.search_segments(
        session,
        query_text=query_text,
        video_id=video_id,
        language=language,
        include_unavailable=include_unavailable,
        skip=offset,
        limit=limit,
    )

    # Batch-fetch adjacent-segment context for the page (eliminates N+1), bounded
    # to the (video_id, language_code) partitions the results live in.
    segment_ids = [segment.id for segment, _t, _v, _c in rows]
    context_map = await segment_repo.get_adjacent_segment_text(
        session,
        segment_ids=segment_ids,
        video_ids=list({s.video_id for s, _t, _v, _c in rows}),
        language_codes=list({s.language_code for s, _t, _v, _c in rows}),
    )

    # Build response items using the pre-fetched context (truncated for display)
    items: list[SearchResultSegment] = []
    for segment, _transcript, video, channel in rows:
        prev_text, next_text = context_map.get(segment.id, (None, None))
        ctx_before = (
            prev_text[:200] if prev_text and len(prev_text) > 200 else prev_text
        )
        ctx_after = next_text[:200] if next_text and len(next_text) > 200 else next_text
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


@router.get(
    "/search/titles", response_model=TitleSearchResponse, responses=SEARCH_ERRORS
)
async def search_titles(
    q: str = Query(
        ..., min_length=2, max_length=500, description="Search query (2-500 characters)"
    ),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    limit: int = Query(
        50, ge=1, le=50, description="Maximum results (1-50, default 50)"
    ),
    video_repo: VideoRepository = Depends(get_video_repository),
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

    rows, total_count = await video_repo.search_titles(
        session,
        query_text=query_text,
        include_unavailable=include_unavailable,
        limit=limit,
    )

    items = [
        TitleSearchResult(
            video_id=video.video_id,
            title=video.title,
            channel_title=channel.title if channel else None,
            upload_date=video.upload_date,
            availability_status=video.availability_status,
        )
        for video, channel in rows
    ]

    return TitleSearchResponse(data=items, total_count=total_count)


def _generate_snippet(
    description: str, query_terms: list[str], target_length: int = 200
) -> str:
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


@router.get(
    "/search/descriptions",
    response_model=DescriptionSearchResponse,
    responses=SEARCH_ERRORS,
)
async def search_descriptions(
    q: str = Query(
        ..., min_length=2, max_length=500, description="Search query (2-500 characters)"
    ),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    limit: int = Query(
        50, ge=1, le=50, description="Maximum results (1-50, default 50)"
    ),
    video_repo: VideoRepository = Depends(get_video_repository),
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

    rows, total_count = await video_repo.search_descriptions(
        session,
        query_text=query_text,
        include_unavailable=include_unavailable,
        limit=limit,
    )

    items = [
        DescriptionSearchResult(
            video_id=video.video_id,
            title=video.title,
            channel_title=channel.title if channel else None,
            upload_date=video.upload_date,
            # description is non-null here (the repo filters it out); `or ""`
            # only satisfies the type-checker for the nullable ORM column.
            snippet=_generate_snippet(video.description or "", [query_text]),
            availability_status=video.availability_status,
        )
        for video, channel in rows
    ]

    return DescriptionSearchResponse(data=items, total_count=total_count)
