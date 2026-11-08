"""Read-only relationship-candidate queue API tests (Feature 107, T017).

Exercises GET /api/v1/relationship-candidates through the real app (ASGITransport)
against the integration DB: lift-ranked order, pagination, the eligible-only filter,
the empty state (200, not error), the response shape (entity summaries + provenance +
status), and the read-only boundary (no mutate routes). Name-free placeholders only.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

import chronovista.repositories.relationship_candidate_repository as rc_repo
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import RelationshipCandidate as RelationshipCandidateDB

pytestmark = pytest.mark.asyncio


def _entity(name: str) -> NamedEntityDB:
    return NamedEntityDB(
        id=uuid.uuid4(),
        canonical_name=name,
        canonical_name_normalized=name.lower(),
        entity_type="person",
    )


def _cand(
    a: uuid.UUID, b: uuid.UUID, *, lift: float, eligible: bool = True, support: int = 7
) -> RelationshipCandidateDB:
    lo, hi = (a, b) if a < b else (b, a)
    return RelationshipCandidateDB(
        id=uuid.uuid4(),
        entity_a_id=lo,
        entity_b_id=hi,
        channel="title_description",
        shared_video_count=support,
        lift=lift,
        entity_a_video_count=10,
        entity_b_video_count=12,
        channel_video_universe=40000,
        both_typed_eligible=eligible,
        kb_corroboration_count=0,
        kb_corroboration_detail={"fields": []},
        provenance={"channel": "title_description", "N": 40000},
    )


async def _seed(
    integration_db_session: Callable[[], object],
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Clean the table, insert 3 entities + 3 candidates (lifts 500/80/10)."""
    async with integration_db_session() as session:  # type: ignore[attr-defined]
        await session.execute(delete(RelationshipCandidateDB))
        # The integration DB is session-scoped (not reset per test) and
        # named_entities has a unique (name_normalized, type); use unique names.
        tag = uuid.uuid4().hex[:10]
        e1, e2, e3 = (
            _entity(f"RC {tag} A"),
            _entity(f"RC {tag} B"),
            _entity(f"RC {tag} C"),
        )
        session.add_all([e1, e2, e3])
        await session.flush()
        session.add_all(
            [
                _cand(e1.id, e2.id, lift=10.0, eligible=False),
                _cand(e1.id, e3.id, lift=500.0, eligible=True),
                _cand(e2.id, e3.id, lift=80.0, eligible=True),
            ]
        )
        await session.commit()
        return e1.id, e2.id, e3.id


class TestList:
    async def test_ranked_by_lift_desc(
        self, async_client: AsyncClient, integration_db_session: Callable[[], object]
    ) -> None:
        await _seed(integration_db_session)
        r = await async_client.get("/api/v1/relationship-candidates")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        lifts = [item["lift"] for item in body["items"]]
        assert lifts == sorted(lifts, reverse=True)
        assert lifts[0] == 500.0

    async def test_item_shape_and_status(
        self, async_client: AsyncClient, integration_db_session: Callable[[], object]
    ) -> None:
        await _seed(integration_db_session)
        r = await async_client.get("/api/v1/relationship-candidates?limit=1")
        item = r.json()["items"][0]
        assert item["status"] == "candidate"
        assert set(item["entity_a"]) >= {"id", "canonical_name", "entity_type"}
        assert set(item["entity_b"]) >= {"id", "canonical_name", "entity_type"}
        assert item["channel"] == "title_description"
        assert item["channel_video_universe"] == 40000  # provenance N is present
        assert r.json()["generated_at"] is not None

    async def test_pagination(
        self, async_client: AsyncClient, integration_db_session: Callable[[], object]
    ) -> None:
        await _seed(integration_db_session)
        r = await async_client.get("/api/v1/relationship-candidates?limit=1&offset=1")
        body = r.json()
        assert body["total"] == 3 and len(body["items"]) == 1
        assert body["items"][0]["lift"] == 80.0  # second by lift

    async def test_eligible_only_filter(
        self, async_client: AsyncClient, integration_db_session: Callable[[], object]
    ) -> None:
        await _seed(integration_db_session)
        r = await async_client.get("/api/v1/relationship-candidates?eligible_only=true")
        body = r.json()
        assert body["total"] == 2
        assert all(item["both_typed_eligible"] for item in body["items"])

    async def test_empty_state_is_200(
        self, async_client: AsyncClient, integration_db_session: Callable[[], object]
    ) -> None:
        async with integration_db_session() as session:  # type: ignore[attr-defined]
            await session.execute(delete(RelationshipCandidateDB))
            await session.commit()
        r = await async_client.get("/api/v1/relationship-candidates")
        assert r.status_code == 200
        assert r.json() == {
            "items": [],
            "total": 0,
            "total_before_scoping": 0,
            "head_cutoff": 500,
            "limit": 50,
            "offset": 0,
            "generated_at": None,
        }

    async def test_min_support_cannot_go_below_5(
        self, async_client: AsyncClient
    ) -> None:
        # The qualifying floor is 5; the API rejects a lower min_support (ge=5).
        r = await async_client.get("/api/v1/relationship-candidates?min_support=1")
        assert r.status_code == 422


class TestHeadScope:
    """Feature 108: head-scoping + provenance through the real endpoint."""

    async def test_provenance_fields_present(
        self, async_client: AsyncClient, integration_db_session: Callable[[], object]
    ) -> None:
        # SC-005: the scoped total, the pre-scoping total, and the cutoff are all exposed.
        await _seed(integration_db_session)  # 3 rows, under the cutoff
        body = (await async_client.get("/api/v1/relationship-candidates")).json()
        assert body["total"] == 3  # scoped
        assert body["total_before_scoping"] == 3  # == scoped when under the cutoff
        assert body["head_cutoff"] == 500

    async def test_hard_cap_not_bypassable_at_api(
        self,
        async_client: AsyncClient,
        integration_db_session: Callable[[], object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # FR-004 / SC-001/SC-002 end-to-end: a large limit cannot exceed the cap, and the
        # provenance reports both totals. One patch of the module constant drives both the
        # repository cap and the response's head_cutoff (single runtime source).
        monkeypatch.setattr(rc_repo, "HEAD_CUTOFF", 3)
        async with integration_db_session() as session:  # type: ignore[attr-defined]
            await session.execute(delete(RelationshipCandidateDB))
            tag = uuid.uuid4().hex[:10]
            hub = _entity(f"HS {tag} hub")
            partners = [_entity(f"HS {tag} p{i}") for i in range(5)]
            session.add_all([hub, *partners])
            await session.flush()
            session.add_all(
                [
                    _cand(hub.id, p.id, lift=float(100 - i))
                    for i, p in enumerate(partners)
                ]
            )
            await session.commit()

        body = (
            await async_client.get("/api/v1/relationship-candidates?limit=100")
        ).json()
        assert len(body["items"]) == 3  # capped despite limit=100
        assert body["total"] == 3  # scoped
        assert body["total_before_scoping"] == 5  # full qualifying count
        assert body["head_cutoff"] == 3
        # Cannot page into the tail past the cutoff.
        empty = (
            await async_client.get("/api/v1/relationship-candidates?offset=3&limit=100")
        ).json()
        assert empty["items"] == []


class TestReadOnlyBoundary:
    async def test_no_mutation_routes(self, async_client: AsyncClient) -> None:
        for method in ("post", "patch", "delete", "put"):
            resp = await getattr(async_client, method)(
                "/api/v1/relationship-candidates"
            )
            # No write verb is defined -> 405 Method Not Allowed (not 2xx).
            assert resp.status_code == 405
