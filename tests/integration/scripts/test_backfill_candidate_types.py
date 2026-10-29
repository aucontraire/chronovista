"""Feature 098 (T010): ``backfill_candidate_types`` against the real integration DB.

Wikidata is faked at the HTTP-response boundary (``httpx.MockTransport``); the script's own
``db_manager.session`` is pointed at the test session. Placeholder QIDs only.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import dialect as pg_dialect
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.config.database import db_manager
from chronovista.db.models import CandidateSuggestion
from chronovista.models.candidate_suggestion import CandidateSuggestionCreate
from chronovista.models.enums import EntityType, SourceChannel, TriageCategory
from chronovista.repositories.candidate_suggestion_repository import (
    CandidateSuggestionRepository,
)
from chronovista.services.wikidata_client import WikidataClient
from scripts.utilities import backfill_candidate_types as bct

pytestmark = pytest.mark.asyncio

P31_BY_QID: dict[str, str] = {
    "Q8001": "Q6256",  # country -> place
    "Q8002": "Q5",  # human -> person
    "Q8003": "Q5",  # human -> person (stored person: no change)
    "Q8005": "Q88888888",  # unrecognized class -> OTHER (Direction A: keep stored type)
}


def _candidate(qid: str, type_hint: EntityType) -> CandidateSuggestionCreate:
    return CandidateSuggestionCreate(
        source_channel=SourceChannel.RELATION,
        wikidata_qid=qid,
        label="Placeholder Label",
        label_normalized="placeholder label",
        type_hint=type_hint,
        token_count=2,
        corroboration_count=1,
        dangling_edge_count=1,
        salience=0,
        score=1.0,
        triage=TriageCategory.WORTH_REVIEW,
        provenance={"seed_entity_ids": [str(uuid.uuid4())], "relations": ["founder"]},
    )


def _handler(request: httpx.Request) -> httpx.Response:
    ids = request.url.params["ids"].split("|")
    entities: dict[str, Any] = {}
    for qid in ids:
        if qid in P31_BY_QID:
            entities[qid] = {
                "claims": {
                    "P31": [
                        {"mainsnak": {"datavalue": {"value": {"id": P31_BY_QID[qid]}}}}
                    ]
                },
                "sitelinks": {},
                "labels": {},
                "descriptions": {},
            }
        else:
            entities[qid] = {"id": qid, "missing": ""}
    return httpx.Response(200, json={"entities": entities})


@pytest.fixture
def wired(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    @asynccontextmanager
    async def _session(**_: Any) -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(db_manager, "session", _session)
    monkeypatch.setattr(
        bct,
        "WikidataClient",
        lambda: WikidataClient(
            http=httpx.AsyncClient(transport=httpx.MockTransport(_handler))
        ),
    )
    monkeypatch.chdir(tmp_path)  # the capture file lands under tmp_path/backups


@pytest.fixture
async def seeded(db_session: AsyncSession) -> dict[str, uuid.UUID]:
    repo = CandidateSuggestionRepository()
    # Q8001 stored 'person' (wrong: it is a country); Q8002 stored 'place' (wrong);
    # Q8003 already right; Q8004 unknown to Wikidata -> must stay untouched.
    rows = {
        "Q8001": EntityType.PERSON,
        "Q8002": EntityType.PLACE,
        "Q8003": EntityType.PERSON,
        "Q8004": EntityType.ORGANIZATION,
        "Q8005": EntityType.PERSON,  # P31 -> OTHER; Direction A keeps 'person'
    }
    ids: dict[str, uuid.UUID] = {}
    for qid, t in rows.items():
        ids[qid] = (
            await repo.upsert_generated(db_session, candidate=_candidate(qid, t))
        ).id
    await db_session.commit()  # the script's _load_pending rolls back after reading
    return ids


async def _types(session: AsyncSession) -> dict[str, str]:
    session.expire_all()
    result = await session.execute(
        select(CandidateSuggestion.wikidata_qid, CandidateSuggestion.type_hint)
    )
    return {str(q): str(t) for q, t in result.tuples().all()}


async def test_compute_changes_returns_only_disagreeing_rows(
    wired: None, seeded: dict[str, uuid.UUID]
) -> None:
    pending = await bct._load_pending()
    changes = await bct._compute_changes(pending)
    assert sorted(changes, key=lambda c: c[1]) == [
        (seeded["Q8001"], "Q8001", "person", "place"),
        (seeded["Q8002"], "Q8002", "place", "person"),
    ]


async def test_dry_run_writes_nothing(
    wired: None, seeded: dict[str, uuid.UUID], db_session: AsyncSession, tmp_path: Path
) -> None:
    before = await _types(db_session)
    assert await bct._run(apply=False, confirm_target=None) == 0
    assert await _types(db_session) == before
    assert not (tmp_path / "backups").exists()


async def test_apply_updates_changed_rows_and_commits(
    wired: None, seeded: dict[str, uuid.UUID], db_session: AsyncSession
) -> None:
    dbname = (await db_session.execute(select(text("current_database()")))).scalar_one()
    assert await bct._run(apply=True, confirm_target=dbname) == 0
    assert await _types(db_session) == {
        "Q8001": "place",
        "Q8002": "person",
        "Q8003": "person",
        "Q8004": "organization",
        "Q8005": "person",  # P31 classified OTHER -> stored type kept (Direction A)
    }
    # Committed, not merely flushed: survives a rollback of the shared session.
    await db_session.rollback()
    assert (await _types(db_session))["Q8001"] == "place"


async def test_apply_refuses_on_target_mismatch(
    wired: None, seeded: dict[str, uuid.UUID], db_session: AsyncSession
) -> None:
    before = await _types(db_session)
    assert await bct._run(apply=True, confirm_target="not_the_db") == 2
    assert await _types(db_session) == before


async def test_update_statement_sets_type_hint_column() -> None:
    """Cross-Feature rule: inspect the emitted UPDATE, not a mock's return value."""
    stmt = (
        update(CandidateSuggestion)
        .where(CandidateSuggestion.id == uuid.uuid4())
        .values(type_hint="place")
    )
    compiled = stmt.compile(dialect=pg_dialect())  # type: ignore[no-untyped-call]
    set_clause = str(compiled).split(" SET ", 1)[1].split(" WHERE ", 1)[0]
    assert set_clause.startswith("type_hint=")
    assert "review_status" not in set_clause
    assert compiled.params["type_hint"] == "place"


async def test_other_classification_keeps_stored_type(
    wired: None, seeded: dict[str, uuid.UUID]
) -> None:
    """Direction A: a candidate whose P31 classifies to OTHER (an unrecognized class, Q8005) keeps
    its stored type rather than being flipped to 'other'."""
    pending = await bct._load_pending()
    changes = await bct._compute_changes(pending)
    changed_qids = {qid for _, qid, _, _ in changes}
    assert "Q8005" not in changed_qids
