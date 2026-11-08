"""Read-only novel-relationship candidate queue endpoint (Feature 107).

Exposes a single lift-ranked, paginated GET. The queue is a measurement surface:
there is NO write verb here — no create/confirm/reject/delete — and the row's
``status`` is always ``"candidate"`` (the verdict columns exist in storage but are
never surfaced). Generation is an operator CLI (see the service), not an endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.schemas.relationship_candidate import (
    EntitySummary,
    RelationshipCandidateItem,
    RelationshipCandidateListResponse,
)
from chronovista.repositories import relationship_candidate_repository as rc_repo
from chronovista.repositories.relationship_candidate_repository import (
    RelationshipCandidateRepository,
)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get(
    "/relationship-candidates",
    response_model=RelationshipCandidateListResponse,
    summary="List novel-relationship candidates, ranked by lift",
)
async def list_relationship_candidates(
    *,
    session: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    eligible_only: bool = Query(
        False,
        description="Only the measured-precision population (both endpoints typed-eligible)",
    ),
    min_support: int = Query(
        5,
        ge=5,
        description="Filter rows by shared-video count; never below the qualifying floor of 5",
    ),
) -> RelationshipCandidateListResponse:
    """Return a lift-ranked page of candidates (strongest first). Read-only.

    ``min_support`` only filters rows (bounded at >= 5); it never re-floors the
    ranking, which is always by lift. The empty set returns 200 with ``items: []``.
    """
    repo = RelationshipCandidateRepository()
    # The API always reads head-scoped (head_only defaults True); there is no request
    # parameter to disable the cap or reach the tail (FR-003/FR-004).
    rows, total, total_before_scoping = await repo.list_ranked(
        session,
        eligible_only=eligible_only,
        min_support=min_support,
        skip=offset,
        limit=limit,
    )
    entity_ids = [r.entity_a_id for r in rows] + [r.entity_b_id for r in rows]
    summaries = await repo.fetch_entity_summaries(session, ids=entity_ids)
    generated_at = await repo.latest_generated_at(session)

    items: list[RelationshipCandidateItem] = []
    for row in rows:
        a = summaries.get(row.entity_a_id)
        b = summaries.get(row.entity_b_id)
        if a is None or b is None:
            # Both FKs are ON DELETE CASCADE, so a deleted entity atomically removes
            # its candidate row — steady-state orphans cannot exist. This branch only
            # fires in a rare TOCTOU race (an entity deleted between list_ranked and
            # fetch_entity_summaries); skip the row rather than 500. A consequence is
            # that a page may return fewer than `limit` rows and `total` can
            # transiently exceed the rows returned.
            continue
        detail = (row.kb_corroboration_detail or {}).get("fields", [])
        items.append(
            RelationshipCandidateItem(
                id=row.id,
                entity_a=EntitySummary(
                    id=row.entity_a_id, canonical_name=a[0], entity_type=a[1]
                ),
                entity_b=EntitySummary(
                    id=row.entity_b_id, canonical_name=b[0], entity_type=b[1]
                ),
                shared_video_count=row.shared_video_count,
                lift=row.lift,
                both_typed_eligible=row.both_typed_eligible,
                kb_corroboration_count=row.kb_corroboration_count,
                kb_corroboration_detail=detail,
                channel=row.channel,
                channel_video_universe=row.channel_video_universe,
            )
        )

    return RelationshipCandidateListResponse(
        items=items,
        total=total,
        total_before_scoping=total_before_scoping,
        # Read through the module so the cutoff has a single runtime source (list_ranked
        # and this provenance field can never disagree).
        head_cutoff=rc_repo.HEAD_CUTOFF,
        limit=limit,
        offset=offset,
        generated_at=generated_at,
    )
