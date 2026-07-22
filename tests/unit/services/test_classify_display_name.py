"""
Unit tests for ``TagManagementService.classify(display_name=...)`` (Feature 057, T024).

Verifies US2: an explicit ``display_name`` is stored verbatim as the entity
``canonical_name`` (the ``str.title()`` auto-casing is skipped and the tag's own
``canonical_form`` is left untouched), the normalized form is still derived for
the link, the chosen name is captured in rollback_data, the actor is recorded,
and omitting ``display_name`` preserves today's auto-derived behavior.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid_utils import uuid7

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.models.enums import EntityType
from chronovista.services.tag_management import TagManagementService

pytestmark = pytest.mark.asyncio


def _uuid() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


def _make_tag(*, normalized_form: str, canonical_form: str) -> MagicMock:
    tag = MagicMock(spec=CanonicalTagDB)
    tag.id = _uuid()
    tag.normalized_form = normalized_form
    tag.canonical_form = canonical_form
    tag.status = "active"
    tag.entity_type = None
    tag.entity_id = None
    return tag


def _build_service(tag: MagicMock) -> tuple[TagManagementService, AsyncMock, AsyncMock]:
    canonical_repo = AsyncMock()
    canonical_repo.get_by_normalized_form.return_value = tag

    named_entity_repo = AsyncMock()
    created_entity = MagicMock()
    created_entity.id = _uuid()
    named_entity_repo.create.return_value = created_entity

    entity_alias_repo = AsyncMock()
    created_alias = MagicMock()
    created_alias.id = _uuid()
    entity_alias_repo.create.return_value = created_alias

    operation_log_repo = AsyncMock()
    log_entry = MagicMock()
    log_entry.id = _uuid()
    operation_log_repo.create.return_value = log_entry

    service = TagManagementService(
        canonical_tag_repo=canonical_repo,
        tag_alias_repo=AsyncMock(),
        named_entity_repo=named_entity_repo,
        entity_alias_repo=entity_alias_repo,
        operation_log_repo=operation_log_repo,
    )
    return service, named_entity_repo, operation_log_repo


def _session_no_existing() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(**{"scalar_one_or_none.return_value": None}),  # existing entity
            MagicMock(**{"scalar_one_or_none.return_value": None}),  # self-alias check
        ]
    )
    session.add = MagicMock()
    return session


async def test_display_name_used_verbatim() -> None:
    tag = _make_tag(normalized_form="openai", canonical_form="openai")
    service, named_entity_repo, operation_log_repo = _build_service(tag)
    session = _session_no_existing()

    await service.classify(
        session,
        "openai",
        EntityType.ORGANIZATION,
        display_name="OpenAI",
        actor="user:local",
    )

    entity_create = named_entity_repo.create.call_args.kwargs["obj_in"]
    assert entity_create.canonical_name == "OpenAI"  # verbatim, not "Openai"
    assert entity_create.canonical_name_normalized == "openai"  # derived
    # Tag's own display form must not be title-cased when display_name is set.
    assert tag.canonical_form == "openai"

    log_create = operation_log_repo.create.call_args.kwargs["obj_in"]
    assert log_create.rollback_data["display_name"] == "OpenAI"
    assert log_create.performed_by == "user:local"


async def test_absent_display_name_auto_cases() -> None:
    tag = _make_tag(normalized_form="openai", canonical_form="openai")
    service, named_entity_repo, _log = _build_service(tag)
    session = _session_no_existing()

    await service.classify(
        session,
        "openai",
        EntityType.ORGANIZATION,
    )

    entity_create = named_entity_repo.create.call_args.kwargs["obj_in"]
    # Backward-compatible: auto-title-cased from the tag canonical form.
    assert entity_create.canonical_name == "Openai"
    assert tag.canonical_form == "Openai"


async def test_default_actor_is_cli_when_absent() -> None:
    tag = _make_tag(normalized_form="openai", canonical_form="openai")
    service, _entity, operation_log_repo = _build_service(tag)
    session = _session_no_existing()

    await service.classify(session, "openai", EntityType.ORGANIZATION)

    log_create = operation_log_repo.create.call_args.kwargs["obj_in"]
    assert log_create.performed_by == "cli"
