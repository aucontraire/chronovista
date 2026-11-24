"""Connection-evidence API: discussion passages behind a pair's proximity (Features 114, 118).

Read-only and **SQL-backed** (Postgres `entity_mentions` / `transcript_segments`), deliberately
distinct from the Neo4j-backed ``graph`` router (which has no AsyncSession): this follows the
SQL-router pattern (``get_db`` + repository ``Depends``) while matching the graph router's RFC-7807
conventions. Mounted under the same ``/graph`` path space so it is discoverable with the explorer.

``/graph/connect/passages`` serves the panel's discussion passages, built from the proximity
measurement; it replaced Feature 114's ``/graph/connect/evidence``, which was retired.
"""

from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from pydantic import AfterValidator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import (
    get_db,
    optional_local_identity,
    require_auth,
)
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.exceptions import APIValidationError, NotFoundError
from chronovista.models.connection_evidence import (
    PROXIMITY_WINDOWS,
    FartherVideos,
    PairPassages,
    ProximityWindow,
)
from chronovista.services import proximity_service

router = APIRouter(dependencies=[Depends(require_auth)])


def _check_window(window: int) -> int:
    """Accept only the four measured windows, inside request validation (one 422 shape).

    A ``Literal`` query parameter would reject the string ``"30"`` (literal validation is exact),
    so the value is parsed as an int and checked here; a bad value then fails like any other
    malformed parameter, with its location, before the request touches the database.
    """
    if window not in PROXIMITY_WINDOWS:
        raise ValueError(
            f"window must be one of {', '.join(map(str, PROXIMITY_WINDOWS))} seconds"
        )
    return window


_WindowParam = Annotated[
    int,
    Query(
        description="seconds between the two mentions' starts: 15, 30, 60 or 120",
        json_schema_extra={"enum": list(PROXIMITY_WINDOWS)},
    ),
    AfterValidator(_check_window),
]


@router.get(
    "/graph/connect/passages",
    response_model=PairPassages,
    summary="Discussion passages where two entities are mentioned within a time window",
)
async def pair_passages(
    a: uuid.UUID = Query(..., description="first entity id"),
    b: uuid.UUID = Query(..., description="second entity id"),
    window: _WindowParam = 30,
    limit: int = Query(12, ge=1, le=50, description="max videos per page"),
    offset: int = Query(
        0, ge=0, description="pagination offset over the ordered videos"
    ),
    session: AsyncSession = Depends(get_db),
) -> PairPassages:
    """Return a pair's discussion passages for one window (read-only, Feature 118).

    Built from the transcript proximity measurement, so the videos listed are exactly the
    videos it reports for this pair and window. Framed as co-mention, never a relationship.
    **422** for two equal ids
    or a window other than 15, 30, 60 or 120; **404** for an entity id absent from
    ``named_entities``.
    """
    await proximity_service.begin_read_snapshot(session)
    await _validate_pair(session, a, b)
    return await proximity_service.pair_passages(
        session,
        entity_a=a,
        entity_b=b,
        window=cast(ProximityWindow, window),
        limit=limit,
        offset=offset,
        user_id=await optional_local_identity(session),
    )


@router.get(
    "/graph/connect/passages/farther",
    response_model=FartherVideos,
    summary="Videos where two entities are both spoken, but never within the window",
)
async def pair_farther_videos(
    a: uuid.UUID = Query(..., description="first entity id"),
    b: uuid.UUID = Query(..., description="second entity id"),
    window: _WindowParam = 30,
    limit: int = Query(20, ge=1, le=100, description="max videos per page"),
    offset: int = Query(
        0, ge=0, description="pagination offset over the ordered videos"
    ),
    session: AsyncSession = Depends(get_db),
) -> FartherVideos:
    """List the videos behind a passages response's ``farther_video_count`` (read-only, FR-010).

    Nearest-first by the smallest start-to-start gap in any shared transcript language, so a
    reviewer can audit a match that sits far from the other entity. Same validation as
    ``/graph/connect/passages``.
    """
    await proximity_service.begin_read_snapshot(session)
    await _validate_pair(session, a, b)
    return await proximity_service.farther_videos(
        session,
        entity_a=a,
        entity_b=b,
        window=cast(ProximityWindow, window),
        limit=limit,
        offset=offset,
    )


async def _validate_pair(session: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> None:
    """422 for two equal ids; 404 for an id absent from ``named_entities``."""
    if a == b:
        raise APIValidationError(
            message="The two entities must be different (a and b are the same id)."
        )
    present = {
        row.id
        for row in (
            await session.execute(
                select(NamedEntityDB.id).where(NamedEntityDB.id.in_([a, b]))
            )
        ).all()
    }
    missing = [str(x) for x in (a, b) if x not in present]
    if missing:
        raise NotFoundError(
            resource_type="Entity",
            identifier=", ".join(missing),
            hint="The entity id is well-formed but not present in named_entities.",
        )
