"""Unit tests for EntityCurationService.reground_entity (Feature 073, #292).

In-memory ORM objects + mocked repositories, no real DB I/O. Verifies the
re-link path: a verified link is set, facts are cleared atomically (no stale
facts — FR-012), the old DBpedia link is dropped (FR-003), the confirmed
description is applied (FR-011), and a 'reground' audit row records before/after.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.entity_operation_log import GroundingRollback
from chronovista.models.named_entity import NamedEntityUpdate
from chronovista.services.entity_curation_service import (
    EntityCurationService,
    EntityNotFoundError,
    InvalidEntityEditError,
)
from tests.factories.named_entity_orm_factory import create_named_entity_db

pytestmark = pytest.mark.asyncio

_ACTOR = "user:local"


def _make_service(
    entity: NamedEntityDB | None,
) -> tuple[EntityCurationService, Any, Any]:
    """Service with mocked repos. Returns (service, entity_repo, log_repo)."""
    entity_repo = MagicMock()
    entity_repo.get = AsyncMock(return_value=entity)
    entity_repo.replace_enrichment = AsyncMock(return_value=1)

    async def _update(
        session: Any, *, db_obj: NamedEntityDB, obj_in: NamedEntityUpdate
    ) -> NamedEntityDB:
        for field, value in obj_in.model_dump(exclude_unset=True).items():
            setattr(db_obj, field, value)
        return db_obj

    entity_repo.update = AsyncMock(side_effect=_update)

    log_repo = MagicMock()
    log_repo.create = AsyncMock(return_value=MagicMock())

    service = EntityCurationService(
        named_entity_repo=entity_repo, operation_log_repo=log_repo
    )
    return service, entity_repo, log_repo


async def test_relink_sets_verified_link_and_clears_facts_atomically() -> None:
    entity = create_named_entity_db(
        canonical_name="Trevor",
        canonical_name_normalized="trevor",
        entity_type="person",
        description="old desc",
    )
    entity.external_ids = {
        "wikidata": {"id": "Q_WRONG", "verified": True, "status": "verified"},
        "dbpedia": {"id": "http://dbpedia.org/resource/Wrong"},
    }
    service, repo, log_repo = _make_service(entity)
    session = MagicMock(spec=AsyncSession)

    await service.reground_entity(
        session, entity.id, qid="Q_RIGHT", description="new desc", actor=_ACTOR
    )

    # Facts cleared + new verified link, all in one full-replace; old dbpedia gone.
    repo.replace_enrichment.assert_awaited_once()
    kwargs = repo.replace_enrichment.await_args.kwargs
    assert kwargs["properties"] == {}
    assert kwargs["external_ids"]["wikidata"]["id"] == "Q_RIGHT"
    assert kwargs["external_ids"]["wikidata"]["verified"] is True
    assert "dbpedia" not in kwargs["external_ids"]

    # Confirmed description applied.
    assert entity.description == "new desc"

    # 'reground' audit with before/after + changed fields.
    created = log_repo.create.await_args.kwargs["obj_in"]
    assert created.operation_type == "reground"
    assert isinstance(created.rollback_data, GroundingRollback)
    assert created.rollback_data.before.wikidata_id == "Q_WRONG"
    assert (
        created.rollback_data.before.dbpedia_id == "http://dbpedia.org/resource/Wrong"
    )
    assert created.rollback_data.after.wikidata_id == "Q_RIGHT"
    assert created.rollback_data.after.dbpedia_id is None
    for f in ("wikidata", "properties", "dbpedia", "description"):
        assert f in created.rollback_data.changed_fields
    assert created.performed_by == _ACTOR


async def test_relink_ungrounded_entity_records_null_before() -> None:
    entity = create_named_entity_db(
        canonical_name="Trevor",
        canonical_name_normalized="trevor",
        entity_type="person",
        description=None,
    )
    entity.external_ids = {}
    service, _repo, log_repo = _make_service(entity)
    session = MagicMock(spec=AsyncSession)

    await service.reground_entity(session, entity.id, qid="Q_RIGHT", actor=_ACTOR)

    created = log_repo.create.await_args.kwargs["obj_in"]
    assert created.rollback_data.before.wikidata_id is None
    # No prior dbpedia link and no description provided → neither in changed_fields.
    assert "dbpedia" not in created.rollback_data.changed_fields
    assert "description" not in created.rollback_data.changed_fields


async def test_reground_missing_entity_raises_not_found() -> None:
    service, repo, log_repo = _make_service(None)
    session = MagicMock(spec=AsyncSession)

    with pytest.raises(EntityNotFoundError):
        await service.reground_entity(
            session, uuid.UUID(bytes=uuid7().bytes), qid="Q1", actor=_ACTOR
        )
    repo.replace_enrichment.assert_not_awaited()
    log_repo.create.assert_not_awaited()


# ---------------------------------------------------------------------------
# refresh_grounding (US2) — re-fetch facts for the CURRENT link.
# Design: facts stay visible synchronously; the background fetch (scheduled by
# the caller) fully replaces them. The service only validates the link and
# writes a 'refetch' audit row — it never touches link/description/facts here.
# ---------------------------------------------------------------------------


async def test_refresh_audits_refetch_and_leaves_link_and_facts_untouched() -> None:
    entity = create_named_entity_db(
        canonical_name="Trevor",
        canonical_name_normalized="trevor",
        entity_type="person",
        description="keep me",
    )
    entity.external_ids = {
        "wikidata": {"id": "Q_CURRENT", "verified": True, "status": "verified"},
        "dbpedia": {"id": "http://dbpedia.org/resource/Current"},
    }
    service, repo, log_repo = _make_service(entity)
    session = MagicMock(spec=AsyncSession)

    returned_entity, qid = await service.refresh_grounding(
        session, entity.id, actor=_ACTOR
    )

    assert returned_entity is entity
    assert qid == "Q_CURRENT"

    # Nothing mutated synchronously: link, description, facts untouched.
    repo.replace_enrichment.assert_not_awaited()
    repo.update.assert_not_awaited()

    # A 'refetch' audit row with before == after link + description.
    created = log_repo.create.await_args.kwargs["obj_in"]
    assert created.operation_type == "refetch"
    assert isinstance(created.rollback_data, GroundingRollback)
    assert created.rollback_data.before.wikidata_id == "Q_CURRENT"
    assert created.rollback_data.after.wikidata_id == "Q_CURRENT"
    assert created.rollback_data.before.description == "keep me"
    assert created.rollback_data.after.description == "keep me"
    assert created.rollback_data.changed_fields == ["properties"]
    assert created.performed_by == _ACTOR


async def test_refresh_without_current_link_raises_invalid() -> None:
    entity = create_named_entity_db(
        canonical_name="Trevor",
        canonical_name_normalized="trevor",
        entity_type="person",
        description=None,
    )
    entity.external_ids = {}
    service, repo, log_repo = _make_service(entity)
    session = MagicMock(spec=AsyncSession)

    with pytest.raises(InvalidEntityEditError):
        await service.refresh_grounding(session, entity.id, actor=_ACTOR)

    # No audit and no mutation when there is nothing to refresh.
    log_repo.create.assert_not_awaited()
    repo.replace_enrichment.assert_not_awaited()


async def test_refresh_is_idempotent_across_repeat_calls() -> None:
    entity = create_named_entity_db(
        canonical_name="Trevor",
        canonical_name_normalized="trevor",
        entity_type="person",
        description="keep me",
    )
    entity.external_ids = {
        "wikidata": {"id": "Q_CURRENT", "verified": True, "status": "verified"}
    }
    service, repo, _log_repo = _make_service(entity)
    session = MagicMock(spec=AsyncSession)

    _, qid_first = await service.refresh_grounding(session, entity.id, actor=_ACTOR)
    _, qid_second = await service.refresh_grounding(session, entity.id, actor=_ACTOR)

    # Repeated refreshes converge: same link, no synchronous fact/link mutation.
    assert qid_first == qid_second == "Q_CURRENT"
    repo.replace_enrichment.assert_not_awaited()
    repo.update.assert_not_awaited()
    assert entity.external_ids["wikidata"]["id"] == "Q_CURRENT"


async def test_refresh_missing_entity_raises_not_found() -> None:
    service, _repo, log_repo = _make_service(None)
    session = MagicMock(spec=AsyncSession)

    with pytest.raises(EntityNotFoundError):
        await service.refresh_grounding(
            session, uuid.UUID(bytes=uuid7().bytes), actor=_ACTOR
        )
    log_repo.create.assert_not_awaited()


# ---------------------------------------------------------------------------
# Graceful degradation (T023, FR-007): the re-link commit path takes NO
# knowledge-base collaborator, so the link + description persist and facts are
# left pending ({}) even when the KB is unreachable. The background fetch that
# fills facts is scheduled by the endpoint AFTER commit and cannot fail this
# path — here we prove the service itself never depends on the KB.
# ---------------------------------------------------------------------------


async def test_relink_commits_link_and_description_without_kb_dependency() -> None:
    entity = create_named_entity_db(
        canonical_name="Trevor",
        canonical_name_normalized="trevor",
        entity_type="person",
        description="old desc",
    )
    entity.external_ids = {}
    service, repo, log_repo = _make_service(entity)
    session = MagicMock(spec=AsyncSession)

    # No enrichment/KB service is injected into EntityCurationService at all;
    # the call must complete and persist without one (no exception raised).
    returned = await service.reground_entity(
        session, entity.id, qid="Q_NEW", description="new desc", actor=_ACTOR
    )

    assert returned is entity
    # Link + description committed; facts left EMPTY (pending), not fetched here.
    kwargs = repo.replace_enrichment.await_args.kwargs
    assert kwargs["properties"] == {}
    assert kwargs["external_ids"]["wikidata"]["id"] == "Q_NEW"
    assert entity.description == "new desc"
    # The audit row is still written even though no facts were fetched.
    log_repo.create.assert_awaited_once()
