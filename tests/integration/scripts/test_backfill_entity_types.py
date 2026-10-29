"""Feature 099 (T007–T013): ``backfill_entity_types`` against the real integration DB.

Offline — the script reads each entity's already-stored ``properties.instance_of.qids``; no
Wikidata is involved. The script's own ``db_manager.session`` is pointed at the test session.
Placeholder names + universal class QIDs only (no library content).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import dialect as pg_dialect
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.config.database import db_manager
from chronovista.db.models import NamedEntity
from scripts.utilities import backfill_entity_types as bet

pytestmark = pytest.mark.asyncio


def _entity(label: str, entity_type: str, qids: list[str], **extra: Any) -> NamedEntity:
    return NamedEntity(
        id=uuid.uuid4(),
        canonical_name=label,
        canonical_name_normalized=label.lower(),
        entity_type=entity_type,
        properties={"instance_of": {"qids": qids, "source": "wikidata"}},
        **extra,
    )


@pytest.fixture
def wired(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    @asynccontextmanager
    async def _session(**_: Any) -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(db_manager, "session", _session)
    monkeypatch.chdir(tmp_path)  # the capture file lands under tmp_path/backups


@pytest.fixture
async def seeded(db_session: AsyncSession) -> dict[str, uuid.UUID]:
    # A: person but P31 = intelligence agency -> organization (ACTIONABLE, #351 class)
    # E: organization but P31 = political ideology -> concept (ACTIONABLE, other axis)
    # B: place with P31 = country -> place (agrees, no change)
    # C: person with P31 = human -> person (agrees)
    # D: person with P31 = unknown class -> OTHER (kept unchanged — FR-005)
    ents = {
        "A": _entity(
            "Placeholder A",
            "person",
            ["Q47913"],
            entity_subtype="politician",
            mention_count=7,
        ),
        "E": _entity("Placeholder E", "organization", ["Q12909644"]),
        "B": _entity("Placeholder B", "place", ["Q6256"]),
        "C": _entity("Placeholder C", "person", ["Q5"]),
        "D": _entity("Placeholder D", "person", ["Q999999999"]),
    }
    for e in ents.values():
        db_session.add(e)
    await db_session.commit()  # the script's _load rolls back after reading
    return {k: v.id for k, v in ents.items()}


async def _types(session: AsyncSession, ids: dict[str, uuid.UUID]) -> dict[str, str]:
    session.expire_all()
    result = await session.execute(
        select(NamedEntity.id, NamedEntity.entity_type).where(
            NamedEntity.id.in_(list(ids.values()))
        )
    )
    by_id = dict(result.tuples().all())
    return {k: str(by_id[v]) for k, v in ids.items()}


async def test_compute_changes_only_actionable_other_kept(
    wired: None, seeded: dict[str, uuid.UUID]
) -> None:
    rows = await bet._load()
    changes = {
        (c.old_type, c.new_type)
        for c in bet._compute_changes(rows)
        if c.entity_id in seeded.values()
    }
    # A person->organization and E organization->concept; B/C agree; D (OTHER) kept.
    assert changes == {("person", "organization"), ("organization", "concept")}


async def test_dry_run_writes_nothing(
    wired: None, seeded: dict[str, uuid.UUID], db_session: AsyncSession, tmp_path: Path
) -> None:
    before = await _types(db_session, seeded)
    assert await bet._run(apply=False, confirm_target=None) == 0
    assert await _types(db_session, seeded) == before
    assert not (tmp_path / "backups").exists()


async def test_apply_writes_entity_type_only_and_commits(
    wired: None, seeded: dict[str, uuid.UUID], db_session: AsyncSession, tmp_path: Path
) -> None:
    # Snapshot EVERY column of A before the correction (FR-013: only entity_type and the automatic
    # updated_at timestamp may change — no other data column).
    a_before = (
        await db_session.execute(
            select(NamedEntity).where(NamedEntity.id == seeded["A"])
        )
    ).scalar_one()
    before = {c.name: getattr(a_before, c.name) for c in NamedEntity.__table__.columns}

    dbname = (await db_session.execute(select(text("current_database()")))).scalar_one()
    assert await bet._run(apply=True, confirm_target=dbname) == 0
    assert await _types(db_session, seeded) == {
        "A": "organization",
        "E": "concept",
        "B": "place",
        "C": "person",
        "D": "person",  # OTHER classification kept (FR-005)
    }
    db_session.expire_all()
    a_after = (
        await db_session.execute(
            select(NamedEntity).where(NamedEntity.id == seeded["A"])
        )
    ).scalar_one()
    after = {c.name: getattr(a_after, c.name) for c in NamedEntity.__table__.columns}
    changed = {k for k in before if before[k] != after[k]}
    assert changed <= {
        "entity_type",
        "updated_at",
    }, f"FR-013 violated; also changed: {changed - {'entity_type', 'updated_at'}}"
    assert after["entity_type"] == "organization"
    # Committed, not merely flushed: survives a rollback of the shared session.
    await db_session.rollback()
    assert (await _types(db_session, seeded))["A"] == "organization"
    # Reversible capture written.
    captures = list((tmp_path / "backups").glob("entity_type_backfill_*.json"))
    assert len(captures) == 1


async def test_downstream_type_filter_consumer(
    wired: None, seeded: dict[str, uuid.UUID], db_session: AsyncSession
) -> None:
    """Cross-Feature Data Contract (US1 scenario 4): after correcting A person->organization,
    the type-filter predicate the entity-list consumer applies (`WHERE entity_type = :t`) returns
    A under 'organization' and not under 'person'; its counts are unchanged."""
    dbname = (await db_session.execute(select(text("current_database()")))).scalar_one()
    assert await bet._run(apply=True, confirm_target=dbname) == 0
    db_session.expire_all()

    async def _ids_of_type(t: str) -> set[uuid.UUID]:
        res = await db_session.execute(
            select(NamedEntity.id).where(
                NamedEntity.entity_type == t, NamedEntity.id.in_(list(seeded.values()))
            )
        )
        return {r[0] for r in res.all()}

    assert seeded["A"] in await _ids_of_type("organization")
    assert seeded["A"] not in await _ids_of_type("person")
    a = (
        await db_session.execute(
            select(NamedEntity).where(NamedEntity.id == seeded["A"])
        )
    ).scalar_one()
    assert a.mention_count == 7  # association/mention counts intact


async def test_apply_refuses_on_target_mismatch(
    wired: None, seeded: dict[str, uuid.UUID], db_session: AsyncSession
) -> None:
    before = await _types(db_session, seeded)
    assert await bet._run(apply=True, confirm_target="not_the_db") == 2
    assert await _types(db_session, seeded) == before


async def test_idempotent_second_run(
    wired: None, seeded: dict[str, uuid.UUID], db_session: AsyncSession
) -> None:
    dbname = (await db_session.execute(select(text("current_database()")))).scalar_one()
    assert await bet._run(apply=True, confirm_target=dbname) == 0
    # A second compute over the now-corrected data yields nothing actionable (SC-005).
    rows = await bet._load()
    remaining = [
        c for c in bet._compute_changes(rows) if c.entity_id in seeded.values()
    ]
    assert remaining == []


async def test_dry_run_report_lists_corrections(
    wired: None, seeded: dict[str, uuid.UUID], capsys: pytest.CaptureFixture[str]
) -> None:
    """T013: the dry-run output is the review surface — it lists each old -> new and a summary."""
    assert await bet._run(apply=False, confirm_target=None) == 0
    out = capsys.readouterr().out
    assert "person -> organization" in out
    assert "organization -> concept" in out
    assert "actionable corrections:" in out
    assert "DRY RUN" in out


async def test_update_statement_sets_entity_type_only() -> None:
    """Cross-Feature rule: inspect the emitted UPDATE's SET clause, not a mock's return value."""
    stmt = (
        update(NamedEntity)
        .where(NamedEntity.id == uuid.uuid4())
        .values(entity_type="organization")
    )
    compiled = stmt.compile(dialect=pg_dialect())  # type: ignore[no-untyped-call]
    set_clause = str(compiled).split(" SET ", 1)[1].split(" WHERE ", 1)[0]
    assert set_clause.startswith("entity_type=")
    # No other DATA column in the SET clause (updated_at, an audit timestamp, is allowed).
    for forbidden in (
        "entity_subtype",
        "canonical_name",
        "properties",
        "external_ids",
        "mention_count",
        "video_count",
    ):
        assert forbidden not in set_clause
    assert compiled.params["entity_type"] == "organization"


async def test_stale_plan_skips_changed_row_and_capture_excludes_it(
    wired: None, seeded: dict[str, uuid.UUID], db_session: AsyncSession, tmp_path: Path
) -> None:
    """Compare-and-set safety: a row changed between plan and apply is NOT clobbered, and the
    reversible capture records only rows actually applied (M2)."""
    changes = bet._compute_changes(await bet._load())
    assert any(
        c.entity_id == seeded["A"] for c in changes
    )  # A is in the plan (person->org)
    # A is re-typed out from under the plan.
    await db_session.execute(
        update(NamedEntity)
        .where(NamedEntity.id == seeded["A"])
        .values(entity_type="place")
    )
    await db_session.commit()
    dbname = (await db_session.execute(select(text("current_database()")))).scalar_one()
    assert await bet._apply(changes, dbname) == 0
    # old_type='person' no longer matches → A is left at the externally-set value, not clobbered.
    assert (await _types(db_session, seeded))["A"] == "place"
    # Capture lists only applied rows → the skipped A is absent.
    captures = list((tmp_path / "backups").glob("entity_type_backfill_*.json"))
    assert len(captures) == 1
    recorded = {r["entity_id"] for r in json.loads(captures[0].read_text())}
    assert str(seeded["A"]) not in recorded
    assert (
        str(seeded["E"]) in recorded
    )  # E (org->concept) still matched and was applied


async def test_merged_row_is_ignored(wired: None, db_session: AsyncSession) -> None:
    """A merged entity with a mismatched P31 is neither loaded nor corrected (status != 'merged')."""
    merged = _entity("Placeholder M", "person", ["Q47913"], status="merged")
    merged_id = merged.id  # capture before _load()'s rollback expires the ORM object
    db_session.add(merged)
    await db_session.commit()
    rows = await bet._load()
    assert merged_id not in {r[0] for r in rows}


async def test_only_applies_reviewed_subset(
    wired: None, seeded: dict[str, uuid.UUID], db_session: AsyncSession, tmp_path: Path
) -> None:
    """--only applies just the vetted subset; the other actionable rows are held at their stored
    type, and the capture records only what was applied."""
    dbname = (await db_session.execute(select(text("current_database()")))).scalar_one()
    assert (
        await bet._run(apply=True, confirm_target=dbname, only={str(seeded["A"])}) == 0
    )
    types = await _types(db_session, seeded)
    assert types["A"] == "organization"  # the one reviewed-in correction applied
    assert types["E"] == "organization"  # E (org->concept) held at its stored type
    capture = next((tmp_path / "backups").glob("entity_type_backfill_*.json"))
    recorded = {r["entity_id"] for r in json.loads(capture.read_text())}
    assert recorded == {str(seeded["A"])}


async def test_only_refuses_unknown_id(
    wired: None, seeded: dict[str, uuid.UUID], db_session: AsyncSession
) -> None:
    """--only with an id that is not an actionable correction refuses and writes nothing."""
    before = await _types(db_session, seeded)
    dbname = (await db_session.execute(select(text("current_database()")))).scalar_one()
    assert (
        await bet._run(apply=True, confirm_target=dbname, only={str(uuid.uuid4())}) == 2
    )
    assert await _types(db_session, seeded) == before
