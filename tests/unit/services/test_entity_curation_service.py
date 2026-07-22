"""
Tests for EntityCurationService (Feature 057, T007).

Covers name edits, description edits, casing-only vs identity-changing renames,
normalized recompute, same-type collision pre-check, audit-log writes, undo, and
already-undone handling. Uses in-memory ORM objects and mocked repositories —
no real database I/O.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.named_entity import NamedEntityUpdate
from chronovista.services.entity_curation_service import (
    EntityCurationService,
    EntityNameCollisionError,
    EntityNotFoundError,
    InvalidEntityEditError,
    OperationAlreadyUndoneError,
    OperationNotFoundError,
)
from tests.factories.entity_operation_log_factory import create_entity_operation_log
from tests.factories.named_entity_orm_factory import create_named_entity_db

pytestmark = pytest.mark.asyncio

_ACTOR = "user:local"


def _uuid() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


def _entity(
    *,
    canonical_name: str = "Openai",
    normalized: str = "openai",
    entity_type: str = "organization",
    description: str | None = "AI lab",
) -> NamedEntityDB:
    return create_named_entity_db(
        canonical_name=canonical_name,
        canonical_name_normalized=normalized,
        entity_type=entity_type,
        description=description,
    )


def _no_collision_session() -> MagicMock:
    """Session whose collision-check query returns no rows."""
    session = MagicMock(spec=AsyncSession)
    result = MagicMock()
    result.first.return_value = None
    session.execute = AsyncMock(return_value=result)
    return session


def _collision_session() -> MagicMock:
    """Session whose collision-check query returns a matching row."""
    session = MagicMock(spec=AsyncSession)
    result = MagicMock()
    result.first.return_value = (_uuid(),)
    session.execute = AsyncMock(return_value=result)
    return session


def _make_service(
    entity: NamedEntityDB | None,
) -> tuple[EntityCurationService, Any, Any]:
    """Build a service with mocked repos. Returns (service, entity_repo, log_repo)."""
    entity_repo = MagicMock()
    entity_repo.get = AsyncMock(return_value=entity)

    async def _update(
        session: Any, *, db_obj: NamedEntityDB, obj_in: NamedEntityUpdate
    ) -> NamedEntityDB:
        for field, value in obj_in.model_dump(exclude_unset=True).items():
            setattr(db_obj, field, value)
        return db_obj

    entity_repo.update = AsyncMock(side_effect=_update)

    log_repo = MagicMock()
    log_repo.create = AsyncMock(
        side_effect=lambda session, *, obj_in: create_entity_operation_log(
            entity_id=obj_in.entity_id,
            rollback_data=obj_in.rollback_data.model_dump(),
            performed_by=obj_in.performed_by,
        )
    )
    log_repo.get = AsyncMock(return_value=None)
    log_repo.mark_rolled_back = AsyncMock()

    service = EntityCurationService(
        named_entity_repo=entity_repo, operation_log_repo=log_repo
    )
    return service, entity_repo, log_repo


class TestUpdateEntity:
    async def test_casing_only_rename_succeeds(self) -> None:
        entity = _entity(canonical_name="Openai", normalized="openai")
        service, _repo, log_repo = _make_service(entity)
        session = _no_collision_session()

        updated = await service.update_entity(
            session, entity.id, canonical_name="OpenAI", actor=_ACTOR
        )
        assert updated.canonical_name == "OpenAI"
        # normalized unchanged (INV-1: still the folded form)
        assert updated.canonical_name_normalized == "openai"
        log_repo.create.assert_awaited_once()
        created_log = log_repo.create.await_args.kwargs["obj_in"]
        assert created_log.rollback_data.changed_fields == ["canonical_name"]
        assert created_log.rollback_data.before.canonical_name == "Openai"
        assert created_log.rollback_data.after.canonical_name == "OpenAI"
        assert created_log.performed_by == _ACTOR

    async def test_identity_changing_rename_recomputes_normalized(self) -> None:
        entity = _entity(canonical_name="Openai", normalized="openai")
        service, _repo, _log = _make_service(entity)
        session = _no_collision_session()

        updated = await service.update_entity(
            session, entity.id, canonical_name="Anthropic", actor=_ACTOR
        )
        assert updated.canonical_name == "Anthropic"
        assert updated.canonical_name_normalized == "anthropic"

    async def test_typo_fix_rename(self) -> None:
        entity = _entity(canonical_name="Anthropc", normalized="anthropc")
        service, _repo, _log = _make_service(entity)
        session = _no_collision_session()
        updated = await service.update_entity(
            session, entity.id, canonical_name="Anthropic", actor=_ACTOR
        )
        assert updated.canonical_name == "Anthropic"
        assert updated.canonical_name_normalized == "anthropic"

    async def test_description_only_edit(self) -> None:
        entity = _entity(description="old")
        service, _repo, log_repo = _make_service(entity)
        session = _no_collision_session()
        updated = await service.update_entity(
            session, entity.id, description="new description", actor=_ACTOR
        )
        assert updated.description == "new description"
        # name identity unchanged
        assert updated.canonical_name == "Openai"
        assert updated.canonical_name_normalized == "openai"
        log = log_repo.create.await_args.kwargs["obj_in"]
        assert log.rollback_data.changed_fields == ["description"]

    async def test_clear_description_is_valid(self) -> None:
        entity = _entity(description="something")
        service, _repo, _log = _make_service(entity)
        session = _no_collision_session()
        updated = await service.update_entity(
            session, entity.id, description="", actor=_ACTOR
        )
        assert updated.description == ""

    async def test_collision_rejected(self) -> None:
        entity = _entity(canonical_name="Openai", normalized="openai")
        service, _repo, log_repo = _make_service(entity)
        session = _collision_session()
        with pytest.raises(EntityNameCollisionError):
            await service.update_entity(
                session, entity.id, canonical_name="Anthropic", actor=_ACTOR
            )
        log_repo.create.assert_not_awaited()

    async def test_empty_name_rejected(self) -> None:
        entity = _entity()
        service, _repo, _log = _make_service(entity)
        session = _no_collision_session()
        with pytest.raises(InvalidEntityEditError):
            await service.update_entity(
                session, entity.id, canonical_name="   ", actor=_ACTOR
            )

    async def test_name_normalizes_to_empty_rejected(self) -> None:
        entity = _entity()
        service, _repo, _log = _make_service(entity)
        session = _no_collision_session()
        with pytest.raises(InvalidEntityEditError):
            await service.update_entity(
                session, entity.id, canonical_name="###", actor=_ACTOR
            )

    async def test_name_too_long_rejected(self) -> None:
        # Spec Edge Case: over-length name rejected by the service guard
        # (>500 chars — the ``NamedEntity.canonical_name`` bound). Reachable
        # directly here; the API layer additionally rejects it at the schema.
        entity = _entity()
        service, _repo, log_repo = _make_service(entity)
        session = _no_collision_session()
        with pytest.raises(InvalidEntityEditError):
            await service.update_entity(
                session, entity.id, canonical_name="x" * 501, actor=_ACTOR
            )
        log_repo.create.assert_not_awaited()

    async def test_no_fields_rejected(self) -> None:
        entity = _entity()
        service, _repo, _log = _make_service(entity)
        session = _no_collision_session()
        with pytest.raises(InvalidEntityEditError):
            await service.update_entity(session, entity.id, actor=_ACTOR)

    async def test_entity_not_found(self) -> None:
        service, _repo, _log = _make_service(None)
        session = _no_collision_session()
        with pytest.raises(EntityNotFoundError):
            await service.update_entity(
                session, _uuid(), canonical_name="X", actor=_ACTOR
            )

    async def test_noop_save_no_log(self) -> None:
        entity = _entity(canonical_name="Openai", description="AI lab")
        service, _repo, log_repo = _make_service(entity)
        session = _no_collision_session()
        updated = await service.update_entity(
            session,
            entity.id,
            canonical_name="Openai",
            description="AI lab",
            actor=_ACTOR,
        )
        assert updated is entity
        log_repo.create.assert_not_awaited()


class TestUndoOperation:
    async def test_undo_restores_name(self) -> None:
        entity = _entity(canonical_name="OpenAI", normalized="openai")
        service, _repo, log_repo = _make_service(entity)
        log = create_entity_operation_log(
            entity_id=entity.id,
            rollback_data={
                "before": {
                    "canonical_name": "Openai",
                    "canonical_name_normalized": "openai",
                },
                "after": {
                    "canonical_name": "OpenAI",
                    "canonical_name_normalized": "openai",
                },
                "changed_fields": ["canonical_name"],
            },
            rolled_back=False,
        )
        log_repo.get = AsyncMock(return_value=log)
        session = _no_collision_session()

        restored = await service.undo_operation(session, log.id, actor=_ACTOR)
        assert restored.canonical_name == "Openai"
        log_repo.mark_rolled_back.assert_awaited_once_with(session, log.id)

    async def test_undo_restores_description(self) -> None:
        entity = _entity(description="new")
        service, _repo, log_repo = _make_service(entity)
        log = create_entity_operation_log(
            entity_id=entity.id,
            rollback_data={
                "before": {"description": "old"},
                "after": {"description": "new"},
                "changed_fields": ["description"],
            },
            rolled_back=False,
        )
        log_repo.get = AsyncMock(return_value=log)
        session = _no_collision_session()

        restored = await service.undo_operation(session, log.id, actor=_ACTOR)
        assert restored.description == "old"

    async def test_undo_missing_operation(self) -> None:
        service, _repo, log_repo = _make_service(_entity())
        log_repo.get = AsyncMock(return_value=None)
        session = _no_collision_session()
        with pytest.raises(OperationNotFoundError):
            await service.undo_operation(session, _uuid(), actor=_ACTOR)

    async def test_undo_already_rolled_back(self) -> None:
        entity = _entity()
        service, _repo, log_repo = _make_service(entity)
        log = create_entity_operation_log(entity_id=entity.id, rolled_back=True)
        log_repo.get = AsyncMock(return_value=log)
        session = _no_collision_session()
        with pytest.raises(OperationAlreadyUndoneError):
            await service.undo_operation(session, log.id, actor=_ACTOR)

    async def test_undo_entity_deleted(self) -> None:
        # Defensive branch: the operation log exists, but its entity was
        # deleted before the undo → EntityNotFoundError (maps to 404).
        service, _repo, log_repo = _make_service(None)
        log = create_entity_operation_log(rolled_back=False)
        log_repo.get = AsyncMock(return_value=log)
        session = _no_collision_session()
        with pytest.raises(EntityNotFoundError):
            await service.undo_operation(session, log.id, actor=_ACTOR)

    async def test_undo_missing_previous_name(self) -> None:
        # Defensive branch: changed_fields records a name change but the
        # ``before`` snapshot lacks the previous name → InvalidEntityEditError
        # (maps to 400), guarding against a corrupt/partial rollback payload.
        entity = _entity(canonical_name="OpenAI", normalized="openai")
        service, _repo, log_repo = _make_service(entity)
        log = create_entity_operation_log(
            entity_id=entity.id,
            rollback_data={
                "before": {},
                "after": {
                    "canonical_name": "OpenAI",
                    "canonical_name_normalized": "openai",
                },
                "changed_fields": ["canonical_name"],
            },
            rolled_back=False,
        )
        log_repo.get = AsyncMock(return_value=log)
        session = _no_collision_session()
        with pytest.raises(InvalidEntityEditError):
            await service.undo_operation(session, log.id, actor=_ACTOR)

    async def test_undo_collision_rejected(self) -> None:
        entity = _entity(canonical_name="Anthropic", normalized="anthropic")
        service, _repo, log_repo = _make_service(entity)
        log = create_entity_operation_log(
            entity_id=entity.id,
            rollback_data={
                "before": {
                    "canonical_name": "Openai",
                    "canonical_name_normalized": "openai",
                },
                "after": {
                    "canonical_name": "Anthropic",
                    "canonical_name_normalized": "anthropic",
                },
                "changed_fields": ["canonical_name"],
            },
            rolled_back=False,
        )
        log_repo.get = AsyncMock(return_value=log)
        session = _collision_session()
        with pytest.raises(EntityNameCollisionError):
            await service.undo_operation(session, log.id, actor=_ACTOR)
