"""Unit tests for the shared entity-creation core (Feature 101).

Covers the orchestration logic of ``create_and_ground_entity`` and the ``build_grounding``
helper. The core's job *is* orchestration, so the repositories are faked here to assert the
sequence and policy routing deterministically; the real DB seam (actual persistence + the
canonical self-alias row) is covered by the integration consistency tests. The core is proven to
perform no transaction control by asserting the session is never committed or rolled back.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.models.entity_alias import EntityAliasCreate
from chronovista.models.enums import EntityAliasType, EntityType
from chronovista.models.named_entity import NamedEntityCreate
from chronovista.services.entity_creation import (
    build_grounding,
    create_and_ground_entity,
)

pytestmark = pytest.mark.asyncio


class TestBuildGrounding:
    """The sole sanctioned constructor of an external_ids grounding entry (FR-003)."""

    async def test_verified_identifier_shape(self) -> None:
        grounding = build_grounding("wikidata", "Q42", verified=True, status="verified")
        assert grounding == {
            "wikidata": {
                "id": "Q42",
                "verified": True,
                "status": "verified",
                "link_provenance": None,
            }
        }

    async def test_absent_identifier_carries_no_id(self) -> None:
        grounding = build_grounding("wikidata", None, verified=False, status="absent")
        assert grounding["wikidata"]["id"] is None
        assert grounding["wikidata"]["status"] == "absent"


def _obj_in() -> NamedEntityCreate:
    return NamedEntityCreate(
        canonical_name="Acme Corp",
        canonical_name_normalized="acme corp",
        entity_type=EntityType.OTHER,
    )


class TestCreateAndGroundEntity:
    """Orchestration + policy routing of the shared core."""

    @pytest.fixture
    def session(self) -> MagicMock:
        return MagicMock(spec=AsyncSession)

    async def test_no_conflict_inserts_and_wires_canonical_alias(
        self, session: MagicMock
    ) -> None:
        """No collision → insert via the uniquely-named primitive + canonical NAME_VARIANT alias."""
        created = SimpleNamespace(id=uuid.uuid4())
        entity_repo = MagicMock()
        entity_repo.find_by_normalized_and_type = AsyncMock(return_value=None)
        entity_repo.insert_new_entity = AsyncMock(return_value=created)
        alias_repo = MagicMock()
        alias_repo.create = AsyncMock()
        on_conflict = AsyncMock()

        result = await create_and_ground_entity(
            session,
            _obj_in(),
            on_conflict=on_conflict,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
        )

        assert result is created
        on_conflict.assert_not_awaited()
        entity_repo.insert_new_entity.assert_awaited_once()
        # Exactly one alias: the canonical self-alias, NAME_VARIANT, occurrence_count 0.
        alias_repo.create.assert_awaited_once()
        alias_obj: EntityAliasCreate = alias_repo.create.await_args.kwargs["obj_in"]
        assert alias_obj.alias_type == EntityAliasType.NAME_VARIANT
        assert alias_obj.occurrence_count == 0
        assert alias_obj.alias_name == "Acme Corp"
        assert alias_obj.alias_name_normalized == "acme corp"
        assert alias_obj.entity_id == created.id

    async def test_extra_aliases_deduped_by_normalized_form(
        self, session: MagicMock
    ) -> None:
        """Two extras that normalize identically yield one extra alias (canonical + 1 = 2)."""
        created = SimpleNamespace(id=uuid.uuid4())
        entity_repo = MagicMock()
        entity_repo.find_by_normalized_and_type = AsyncMock(return_value=None)
        entity_repo.insert_new_entity = AsyncMock(return_value=created)
        alias_repo = MagicMock()
        alias_repo.create = AsyncMock()

        await create_and_ground_entity(
            session,
            _obj_in(),
            extra_aliases=["Globex", "globex"],
            on_conflict=AsyncMock(),
            entity_repo=entity_repo,
            alias_repo=alias_repo,
        )

        # canonical + exactly one deduped extra
        assert alias_repo.create.await_count == 2

    async def test_conflict_routes_to_policy_and_skips_insert(
        self, session: MagicMock
    ) -> None:
        """A collision invokes on_conflict and returns its result; the core never inserts."""
        existing = SimpleNamespace(id=uuid.uuid4())
        entity_repo = MagicMock()
        entity_repo.find_by_normalized_and_type = AsyncMock(return_value=existing)
        entity_repo.insert_new_entity = AsyncMock()
        alias_repo = MagicMock()
        alias_repo.create = AsyncMock()
        on_conflict = AsyncMock(return_value=existing)

        result = await create_and_ground_entity(
            session,
            _obj_in(),
            on_conflict=on_conflict,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
        )

        assert result is existing
        on_conflict.assert_awaited_once_with(existing)
        entity_repo.insert_new_entity.assert_not_awaited()
        alias_repo.create.assert_not_awaited()

    async def test_core_performs_no_transaction_control(
        self, session: MagicMock
    ) -> None:
        """FR-011: the core never commits or rolls back — the caller owns the boundary."""
        entity_repo = MagicMock()
        entity_repo.find_by_normalized_and_type = AsyncMock(return_value=None)
        entity_repo.insert_new_entity = AsyncMock(
            return_value=SimpleNamespace(id=uuid.uuid4())
        )
        alias_repo = MagicMock()
        alias_repo.create = AsyncMock()

        await create_and_ground_entity(
            session,
            _obj_in(),
            on_conflict=AsyncMock(),
            entity_repo=entity_repo,
            alias_repo=alias_repo,
        )

        session.commit.assert_not_called()
        session.rollback.assert_not_called()
