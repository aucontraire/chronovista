"""Read-only candidate-queue API tests (Feature 096, T021).

Exercises the three GET routes through the real app (ASGITransport) against the
integration DB: ranked+filtered list with pagination, detail + 404, the summary
counts, and the read-only boundary (no mutate routes). Name-free placeholders only.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from chronovista.db.models import CandidateSuggestion as CandidateSuggestionDB

pytestmark = pytest.mark.asyncio


def _candidate(
    *,
    qid: str,
    label: str,
    score: float,
    token_count: int = 2,
    triage: str = "worth_review",
    review_status: str = "pending",
) -> CandidateSuggestionDB:
    return CandidateSuggestionDB(
        id=uuid.uuid4(),
        source_channel="relation",
        wikidata_qid=qid,
        label=label,
        label_normalized=label.lower(),
        type_hint="person",
        token_count=token_count,
        corroboration_count=1,
        dangling_edge_count=1,
        salience=int(score),
        score=score,
        triage=triage,
        provenance={"seed_entity_ids": [str(uuid.uuid4())], "relations": ["spouse"]},
        review_status=review_status,
    )


@pytest.fixture
async def _seeded(integration_db_session: Callable[[], object]) -> list[str]:
    """Seed three pending candidates (+1 rejected) and return the pending QIDs by score desc."""
    async with integration_db_session() as session:  # type: ignore[attr-defined]
        # The integration DB is session-scoped and not reset between tests, so
        # start each test from a clean candidate table (fixed QIDs would otherwise
        # collide on uq_candidate_channel_qid).
        await session.execute(delete(CandidateSuggestionDB))
        session.add_all(
            [
                _candidate(qid="Q7001", label="High Score Name", score=90.0),
                _candidate(qid="Q7002", label="Mid Score Name", score=40.0),
                _candidate(
                    qid="Q7003",
                    label="Solo",
                    score=5.0,
                    token_count=1,
                    triage="likely_eliminable",
                ),
                _candidate(
                    qid="Q7004",
                    label="Rejected Name",
                    score=99.0,
                    review_status="rejected",
                ),
            ]
        )
        await session.commit()
    return ["Q7001", "Q7002", "Q7003"]


async def test_list_is_ranked_and_excludes_terminal(
    async_client: AsyncClient, _seeded: list[str]
) -> None:
    resp = await async_client.get("/api/v1/candidates?limit=10")
    assert resp.status_code == 200
    body = resp.json()
    qids = [row["wikidata_qid"] for row in body["data"]]
    # Pending only, ranked by score desc; the rejected candidate is absent.
    assert qids == ["Q7001", "Q7002", "Q7003"]
    assert "Q7004" not in qids
    assert body["pagination"]["total"] == 3


async def test_list_filters(async_client: AsyncClient, _seeded: list[str]) -> None:
    multi = await async_client.get("/api/v1/candidates?min_token_count=2")
    assert {r["wikidata_qid"] for r in multi.json()["data"]} == {"Q7001", "Q7002"}

    elim = await async_client.get("/api/v1/candidates?triage=likely_eliminable")
    data = elim.json()["data"]
    assert len(data) == 1 and data[0]["wikidata_qid"] == "Q7003"


async def test_pagination(async_client: AsyncClient, _seeded: list[str]) -> None:
    page = await async_client.get("/api/v1/candidates?limit=2&offset=0")
    body = page.json()
    assert len(body["data"]) == 2
    assert body["pagination"]["has_more"] is True
    assert body["pagination"]["total"] == 3


async def test_summary_counts(async_client: AsyncClient, _seeded: list[str]) -> None:
    resp = await async_client.get("/api/v1/candidates/summary")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["pending"] == 3
    assert data["rejected"] == 1
    assert data["worth_review"] == 2
    assert data["likely_eliminable"] == 1


async def test_detail_and_404(async_client: AsyncClient, _seeded: list[str]) -> None:
    listing = await async_client.get("/api/v1/candidates?limit=1")
    cid = listing.json()["data"][0]["id"]
    detail = await async_client.get(f"/api/v1/candidates/{cid}")
    assert detail.status_code == 200
    assert detail.json()["wikidata_qid"] == "Q7001"
    assert "provenance" in detail.json()

    missing = await async_client.get(f"/api/v1/candidates/{uuid.uuid4()}")
    assert missing.status_code == 404
    malformed = await async_client.get("/api/v1/candidates/not-a-uuid")
    assert malformed.status_code == 404


async def test_read_only_boundary(
    async_client: AsyncClient, _seeded: list[str]
) -> None:
    """No mutate routes exist on this surface (approve/reject are CLI-only, FR-016)."""
    cid = (await async_client.get("/api/v1/candidates?limit=1")).json()["data"][0]["id"]
    # POST/PATCH/DELETE are not defined → 405 Method Not Allowed.
    assert (await async_client.post("/api/v1/candidates")).status_code == 405
    assert (await async_client.patch(f"/api/v1/candidates/{cid}")).status_code == 405
    assert (await async_client.delete(f"/api/v1/candidates/{cid}")).status_code == 405
