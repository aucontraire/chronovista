"""
Actor-attribution regression test for TagManagementService (Feature 057, T004).

FR-018 parameterizes the shared ``_log_operation`` actor. This test protects
the tag-operation logging path: the default actor stays ``"cli"`` (so existing
CLI behavior is unchanged), and an explicit actor (e.g. the web ``"user:local"``)
is recorded verbatim in the ``tag_operation_logs`` entry.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.services.tag_management import TagManagementService

pytestmark = pytest.mark.asyncio


def _uuid() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


def _service() -> tuple[TagManagementService, AsyncMock]:
    log_repo = MagicMock()
    created = MagicMock()
    created.id = _uuid()
    log_repo.create = AsyncMock(return_value=created)

    service = TagManagementService(
        canonical_tag_repo=MagicMock(),
        tag_alias_repo=MagicMock(),
        named_entity_repo=MagicMock(),
        entity_alias_repo=MagicMock(),
        operation_log_repo=log_repo,
    )
    return service, log_repo.create


async def test_default_actor_is_cli() -> None:
    service, create = _service()
    session = MagicMock(spec=AsyncSession)

    await service._log_operation(
        session,
        operation_type="merge",
        source_ids=[_uuid()],
        target_id=_uuid(),
        alias_ids=[],
        reason=None,
        rollback_data={},
    )
    obj_in = create.await_args.kwargs["obj_in"]
    assert obj_in.performed_by == "cli"


async def test_explicit_web_actor_recorded() -> None:
    service, create = _service()
    session = MagicMock(spec=AsyncSession)

    await service._log_operation(
        session,
        operation_type="rename",
        source_ids=[_uuid()],
        target_id=None,
        alias_ids=[],
        reason=None,
        rollback_data={},
        actor="user:local",
    )
    obj_in = create.await_args.kwargs["obj_in"]
    assert obj_in.performed_by == "user:local"
