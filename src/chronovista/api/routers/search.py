"""Search endpoints for transcript segment search."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.routers.responses import LIST_ERRORS
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.search import SearchResponse, SearchResultSegment
from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import TranscriptSegment as SegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as TranscriptDB
from chronovista.exceptions import BadRequestError


router = APIRouter(dependencies=[Depends(require_auth)])


def count_query_matches(text: str, query_terms: List[str]) -> int:
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
    video_id: Optional[str] = Query(
        None, min_length=11, max_length=11, description="Limit to specific video"
    ),
    language: Optional[str] = Query(None, description="Limit to specific language"),
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

    # Split query into terms for multi-word search (implicit AND)
    query_terms = query_text.split()

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
        .where(VideoDB.deleted_flag.is_(False))
    )

    # Apply ILIKE filter for each term (implicit AND)
    for term in query_terms:
        escaped_term = term.replace("%", r"\%").replace("_", r"\_")
        query = query.where(SegmentDB.text.ilike(f"%{escaped_term}%"))

    # Apply optional filters
    if video_id:
        query = query.where(SegmentDB.video_id == video_id)
    if language:
        query = query.where(SegmentDB.language_code == language)

    # Get total count
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

    # Build response items with context
    items: List[SearchResultSegment] = []
    for segment, transcript, video, channel in rows:
        # Get adjacent segments for context
        context_before: Optional[str] = None
        context_after: Optional[str] = None

        # Previous segment
        prev_query = (
            select(SegmentDB)
            .where(SegmentDB.video_id == segment.video_id)
            .where(SegmentDB.language_code == segment.language_code)
            .where(SegmentDB.start_time < segment.start_time)
            .order_by(SegmentDB.start_time.desc())
            .limit(1)
        )
        prev_result = await session.execute(prev_query)
        prev_segment = prev_result.scalar_one_or_none()
        if prev_segment:
            context_before = (
                prev_segment.text[:200]
                if len(prev_segment.text) > 200
                else prev_segment.text
            )

        # Next segment
        next_query = (
            select(SegmentDB)
            .where(SegmentDB.video_id == segment.video_id)
            .where(SegmentDB.language_code == segment.language_code)
            .where(SegmentDB.start_time > segment.start_time)
            .order_by(SegmentDB.start_time.asc())
            .limit(1)
        )
        next_result = await session.execute(next_query)
        next_segment = next_result.scalar_one_or_none()
        if next_segment:
            context_after = (
                next_segment.text[:200]
                if len(next_segment.text) > 200
                else next_segment.text
            )

        items.append(
            SearchResultSegment(
                segment_id=segment.id,
                video_id=segment.video_id,
                video_title=video.title,
                channel_title=channel.title if channel else None,
                language_code=segment.language_code,
                text=segment.text,
                start_time=segment.start_time,
                end_time=segment.end_time,
                context_before=context_before,
                context_after=context_after,
                match_count=count_query_matches(segment.text, query_terms),
                video_upload_date=video.upload_date,
            )
        )

    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    return SearchResponse(data=items, pagination=pagination)
