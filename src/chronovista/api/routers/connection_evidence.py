"""Connection-evidence API: transcript passages behind a pair's co-occurrence (Feature 114).

Read-only and **SQL-backed** (Postgres `entity_mentions` / `transcript_segments`), deliberately
distinct from the Neo4j-backed ``graph`` router (which has no AsyncSession): this follows the
SQL-router pattern (``get_db`` + repository ``Depends``) while matching the graph router's RFC-7807
conventions. Mounted under the same ``/graph`` path space so it is discoverable with the explorer.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, get_entity_mention_repository, require_auth
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.exceptions import APIValidationError, NotFoundError
from chronovista.models.connection_evidence import ConnectionEvidence
from chronovista.repositories.entity_mention_repository import EntityMentionRepository

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get(
    "/graph/connect/evidence",
    response_model=ConnectionEvidence,
    summary="Transcript passages where two entities co-occur (evidence behind CO_OCCURS_*)",
)
async def connection_evidence(
    a: uuid.UUID = Query(..., description="first entity id"),
    b: uuid.UUID = Query(..., description="second entity id"),
    limit: int = Query(12, ge=1, le=50, description="max evidence items per page"),
    offset: int = Query(
        0, ge=0, description="pagination offset over the ordered items"
    ),
    session: AsyncSession = Depends(get_db),
    mention_repo: EntityMentionRepository = Depends(get_entity_mention_repository),
) -> ConnectionEvidence:
    """Return the transcript evidence for a co-occurring pair (read-only).

    Evidence is framed as co-mention, never a factual relationship. **422** for two equal ids;
    **404** for an entity id absent from ``named_entities``. No **503** — this reads Postgres
    (always available), unlike the snapshot-backed ``/graph/connect``; a brief live-vs-snapshot gap
    against the graph's edges is the FR-014 staleness, not an error.
    """
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
    return await mention_repo.co_occurrence_evidence(
        session, a, b, limit=limit, offset=offset
    )
