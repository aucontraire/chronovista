"""Candidate approve/reject write API, crossed from outside (Feature 097, T015).

Real JSON through the app (``ASGITransport``) against the real integration DB: the
service-level tests cannot see the HTTP schema, the identity gate, or the commit
boundary. The integration DB is shared and never reset, so every row uses a per-run
random QID and label, and is removed on teardown.
"""

from __future__ import annotations

import random
import string
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.api.deps import require_local_identity
from chronovista.api.main import app
from chronovista.db.models import CandidateSuggestion as CandidateDB
from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.enums import TagStatus
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from tests.factories.canonical_tag_factory import CanonicalTagCreateFactory

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_IDENTITY = "UCtest_identity_00000000"


def _letters(n: int) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=n))


def _unique_qid() -> str:
    return "Q97015" + "".join(random.choices(string.digits, k=9))


class _Seeder:
    """Seeds pending candidates and records what to delete on teardown."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory
        self.candidate_ids: list[uuid.UUID] = []
        self.tag_ids: list[uuid.UUID] = []
        self.qids: list[str] = []

    async def candidate(self, *, label: str, type_hint: str = "person") -> CandidateDB:
        qid = _unique_qid()
        self.qids.append(qid)
        row = CandidateDB(
            source_channel="relation",
            wikidata_qid=qid,
            label=label,
            label_normalized=label.lower(),
            type_hint=type_hint,
            token_count=len(label.split()),
            corroboration_count=1,
            dangling_edge_count=1,
            salience=0,
            score=0.0,
            triage="grounds_nowhere",
            provenance={
                "seed_entity_ids": [str(uuid.uuid4())],
                "relations": ["spouse"],
            },
            review_status="pending",
        )
        async with self.factory() as session:
            session.add(row)
            await session.commit()
        self.candidate_ids.append(row.id)
        return row

    async def unlinked_tag(self, *, normalized: str, entity_type: str) -> uuid.UUID:
        create = CanonicalTagCreateFactory.build(
            canonical_form=normalized,
            normalized_form=normalized,
            status=TagStatus.ACTIVE,
        )
        data = create.model_dump(mode="json")
        data["entity_type"] = entity_type
        data["entity_id"] = None
        async with self.factory() as session:
            tag = CanonicalTagDB(**data)
            session.add(tag)
            await session.commit()
            self.tag_ids.append(tag.id)
            return tag.id


@pytest.fixture
async def seeder(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[_Seeder, None]:
    seeder = _Seeder(integration_session_factory)
    yield seeder
    async with integration_session_factory() as session:
        await session.execute(
            delete(CandidateDB).where(CandidateDB.id.in_(seeder.candidate_ids))
        )
        await session.execute(
            delete(CanonicalTagDB).where(CanonicalTagDB.id.in_(seeder.tag_ids))
        )
        await session.execute(
            delete(NamedEntityDB).where(
                NamedEntityDB.external_ids["wikidata"]["id"].astext.in_(seeder.qids)
            )
        )
        await session.commit()


@pytest.fixture(autouse=True)
def no_detached_enrichment() -> Any:
    """Enrichment is best-effort and detached; it opens its own app-level session and
    would reach the network, so it is not part of what this test exercises."""
    with patch("chronovista.api.routers.candidates._schedule_enrichment") as sched:
        yield sched


async def _entity_count(factory: async_sessionmaker[AsyncSession], qid: str) -> int:
    async with factory() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(NamedEntityDB)
                .where(NamedEntityDB.external_ids["wikidata"]["id"].astext == qid)
            )
            or 0
        )


class TestApproveReject:
    async def test_approve_creates_grounded_entity_once_and_never_links_a_tag(
        self,
        async_client: AsyncClient,
        seeder: _Seeder,
        integration_session_factory: async_sessionmaker[AsyncSession],
        no_detached_enrichment: Any,
    ) -> None:
        label = f"Zq {_letters(10)} {_letters(8)}"
        cand = await seeder.candidate(label=label)
        # FR-052: a tag matching the candidate's name+type, deliberately unlinked.
        tag_id = await seeder.unlinked_tag(
            normalized=label.lower(), entity_type="person"
        )

        first = await async_client.post(f"/api/v1/candidates/{cand.id}/approve")
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["outcome"] == "approved"
        assert body["candidate_id"] == str(cand.id)
        created_id = uuid.UUID(body["created_entity_id"])
        no_detached_enrichment.assert_called_once()

        # Read back through the entity read path, not the write path.
        detail = await async_client.get(f"/api/v1/entities/{created_id}")
        assert detail.status_code == 200, detail.text
        async with integration_session_factory() as session:
            grounded = await NamedEntityRepository().get_by_wikidata_qids(
                session, [cand.wikidata_qid]
            )
            entity = await NamedEntityRepository().get(session, created_id)
            persisted = await session.get(CandidateDB, cand.id)
            tag = await session.get(CanonicalTagDB, tag_id)
        assert grounded[cand.wikidata_qid][0] == created_id
        assert entity is not None
        assert entity.status == "active"
        assert entity.external_ids["wikidata"]["id"] == cand.wikidata_qid
        assert persisted is not None
        assert persisted.review_status == "approved"
        assert persisted.reviewed_by == _IDENTITY
        assert persisted.created_entity_id == created_id

        # FR-052 negative guarantee: approval must never auto-link a tag.
        assert tag is not None
        assert tag.entity_id is None, "approve auto-linked a canonical tag"

        # Second approval: compare-and-set refuses, and nothing is duplicated.
        second = await async_client.post(f"/api/v1/candidates/{cand.id}/approve")
        assert second.status_code == 200, second.text
        assert second.json()["outcome"] == "failed"
        assert second.json()["created_entity_id"] is None
        assert await _entity_count(integration_session_factory, cand.wikidata_qid) == 1
        async with integration_session_factory() as session:
            tag = await session.get(CanonicalTagDB, tag_id)
        assert tag is not None and tag.entity_id is None

    async def test_reject_records_verdict_and_creates_no_entity(
        self,
        async_client: AsyncClient,
        seeder: _Seeder,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        cand = await seeder.candidate(label=f"Zr {_letters(10)} {_letters(8)}")

        resp = await async_client.post(f"/api/v1/candidates/{cand.id}/reject")
        assert resp.status_code == 200, resp.text
        assert resp.json()["outcome"] == "rejected"
        assert resp.json()["created_entity_id"] is None

        async with integration_session_factory() as session:
            persisted = await session.get(CandidateDB, cand.id)
        assert persisted is not None
        assert persisted.review_status == "rejected"
        assert persisted.reviewed_by == _IDENTITY
        assert await _entity_count(integration_session_factory, cand.wikidata_qid) == 0

        # A decided candidate cannot be approved afterwards.
        again = await async_client.post(f"/api/v1/candidates/{cand.id}/approve")
        assert again.json()["outcome"] == "failed"
        assert await _entity_count(integration_session_factory, cand.wikidata_qid) == 0

    async def test_approve_unknown_candidate_is_404(
        self, async_client: AsyncClient
    ) -> None:
        resp = await async_client.post(f"/api/v1/candidates/{uuid.uuid4()}/approve")
        assert resp.status_code == 404, resp.text

    async def test_reject_unknown_candidate_is_404(
        self, async_client: AsyncClient
    ) -> None:
        resp = await async_client.post(f"/api/v1/candidates/{uuid.uuid4()}/reject")
        assert resp.status_code == 404, resp.text

    async def test_no_established_identity_is_409_and_mutates_nothing(
        self,
        async_client: AsyncClient,
        seeder: _Seeder,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        cand = await seeder.candidate(label=f"Zi {_letters(10)} {_letters(8)}")

        def _no_identity() -> str:
            raise HTTPException(status_code=409, detail="no identity")

        app.dependency_overrides[require_local_identity] = _no_identity
        for verb in ("approve", "reject"):
            resp = await async_client.post(f"/api/v1/candidates/{cand.id}/{verb}")
            assert resp.status_code == 409, (verb, resp.text)

        async with integration_session_factory() as session:
            persisted = await session.get(CandidateDB, cand.id)
        assert persisted is not None and persisted.review_status == "pending"
        assert await _entity_count(integration_session_factory, cand.wikidata_qid) == 0
