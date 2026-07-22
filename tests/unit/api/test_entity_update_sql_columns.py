"""
Mock SQL-column (SET-clause) test for entity edits (Feature 057, T008; INV-1).

The constitution's Cross-Feature Data Contract Verification requires that an
entity name change writes BOTH ``canonical_name`` and
``canonical_name_normalized`` (never one without the other), and that a
description change writes ``description``.

``NamedEntityRepository.update`` applies the ``NamedEntityUpdate`` fields via
``model_dump(exclude_unset=True)`` and ``setattr`` — so the set of columns in
the resulting UPDATE's SET clause is exactly the set of explicitly-set fields
on the ``obj_in`` passed to it. This test captures that ``obj_in`` and asserts
its SET columns, which is the ORM-repository equivalent of inspecting the
SQL SET clause.
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
from chronovista.services.entity_curation_service import EntityCurationService
from tests.factories.named_entity_orm_factory import create_named_entity_db

pytestmark = pytest.mark.asyncio


def _uuid() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


def _entity() -> NamedEntityDB:
    return create_named_entity_db(
        canonical_name="Openai",
        canonical_name_normalized="openai",
        entity_type="organization",
        description="old",
    )


def _service_capturing_update(
    entity: NamedEntityDB,
) -> tuple[EntityCurationService, list[NamedEntityUpdate]]:
    captured: list[NamedEntityUpdate] = []

    entity_repo = MagicMock()
    entity_repo.get = AsyncMock(return_value=entity)

    async def _update(
        session: Any, *, db_obj: NamedEntityDB, obj_in: NamedEntityUpdate
    ) -> NamedEntityDB:
        captured.append(obj_in)
        for field, value in obj_in.model_dump(exclude_unset=True).items():
            setattr(db_obj, field, value)
        return db_obj

    entity_repo.update = AsyncMock(side_effect=_update)

    log_repo = MagicMock()
    log_repo.create = AsyncMock()

    service = EntityCurationService(
        named_entity_repo=entity_repo, operation_log_repo=log_repo
    )
    return service, captured


def _no_collision_session() -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    result = MagicMock()
    result.first.return_value = None
    session.execute = AsyncMock(return_value=result)
    return session


async def test_name_change_sets_both_name_columns() -> None:
    entity = _entity()
    service, captured = _service_capturing_update(entity)
    session = _no_collision_session()

    await service.update_entity(
        session, entity.id, canonical_name="OpenAI", actor="user:local"
    )

    assert len(captured) == 1
    set_columns = set(captured[0].model_dump(exclude_unset=True).keys())
    assert "canonical_name" in set_columns
    assert "canonical_name_normalized" in set_columns  # INV-1
    assert "description" not in set_columns


async def test_description_change_sets_description_only() -> None:
    entity = _entity()
    service, captured = _service_capturing_update(entity)
    session = _no_collision_session()

    await service.update_entity(
        session, entity.id, description="new text", actor="user:local"
    )

    assert len(captured) == 1
    set_columns = set(captured[0].model_dump(exclude_unset=True).keys())
    assert set_columns == {"description"}
