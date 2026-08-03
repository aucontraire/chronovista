"""Overview dashboard endpoint (Feature 061).

A single read-only aggregation serving every figure the dashboard displays
(FR-026), so the cards are computed together and cannot disagree.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.routers.responses import LIST_ERRORS
from chronovista.api.schemas.overview import OverviewResponse
from chronovista.api.schemas.responses import ApiResponse
from chronovista.repositories.playlist_repository import get_library_overview

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get(
    "/overview",
    response_model=ApiResponse[OverviewResponse],
    responses=LIST_ERRORS,
    summary="Library overview aggregates",
)
async def get_overview(
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[OverviewResponse]:
    """Return the library overview figures.

    Read-only. Takes no parameters and returns aggregates rather than rows, so
    its cost does not grow with the number of videos in the library (SC-011).

    Parameters
    ----------
    session : AsyncSession
        Database session injected via FastAPI dependency.

    Returns
    -------
    ApiResponse[OverviewResponse]
        Saved & Forgotten headline, Watch Later depth (null when no such
        playlist exists), the playlist inventory, and library rollups.
    """
    data = await get_library_overview(session)
    return ApiResponse[OverviewResponse](data=OverviewResponse.model_validate(data))
