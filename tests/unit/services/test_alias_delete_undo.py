"""Unit tests for EntityCurationService alias delete/undo guards (#298).

The full delete→undo behaviour (restore, collision-reject, missing-segment
skip, undo-again) is covered end-to-end against the real DB in
``tests/integration/api/test_alias_undo.py``. Here we lock the pure control-flow
branch that integration can't reach: the service constructed WITHOUT the alias /
mention repositories (they are optional, needed only by the #298 paths) must
fail loudly rather than silently no-op.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.services.entity_curation_service import EntityCurationService

pytestmark = pytest.mark.asyncio

_ACTOR = "user:local"


def _service_without_alias_repos() -> EntityCurationService:
    """A service wired only for entity edits — no alias/mention repos (#298)."""
    return EntityCurationService(
        named_entity_repo=MagicMock(),
        operation_log_repo=MagicMock(),
    )


async def test_delete_alias_without_repos_raises_runtime_error() -> None:
    service = _service_without_alias_repos()
    session = MagicMock(spec=AsyncSession)
    entity = MagicMock(spec=NamedEntityDB)
    entity.id = uuid.uuid4()
    alias = MagicMock(spec=EntityAliasDB)
    alias.id = uuid.uuid4()
    alias.alias_name = "Test"

    with pytest.raises(RuntimeError, match="alias/mention repositories"):
        await service.delete_alias(session, entity=entity, alias=alias, actor=_ACTOR)


async def test_undo_dispatches_alias_delete_and_guards_missing_repos() -> None:
    # A log entry typed 'alias_delete' routes to the alias-restore path, which
    # (without the repos) raises rather than falling through to the edit path.
    service = _service_without_alias_repos()
    log_entry = MagicMock()
    log_entry.rolled_back = False
    log_entry.operation_type = "alias_delete"
    log_entry.entity_id = uuid.uuid4()
    service._operation_log_repo.get = AsyncMock(return_value=log_entry)
    session = MagicMock(spec=AsyncSession)

    with pytest.raises(RuntimeError, match="alias/mention repositories"):
        await service.undo_operation(session, uuid.uuid4(), actor=_ACTOR)
