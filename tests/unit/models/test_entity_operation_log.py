"""
Tests for entity operation log Pydantic models (Feature 057, T005).

Covers the snapshot / rollback value objects and the Base/Create/Update/Full
model family, including ``from_attributes`` construction from an ORM instance.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from uuid_utils import uuid7

from chronovista.db.models import EntityOperationLog as EntityOperationLogDB
from chronovista.models.entity_operation_log import (
    EntityEditRollback,
    EntityEditSnapshot,
    EntityOperationLog,
    EntityOperationLogCreate,
    EntityOperationLogUpdate,
)


def _uuid() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


class TestEntityEditSnapshot:
    def test_all_fields_optional_default_none(self) -> None:
        snap = EntityEditSnapshot()
        assert snap.canonical_name is None
        assert snap.canonical_name_normalized is None
        assert snap.description is None

    def test_populates_provided_fields(self) -> None:
        snap = EntityEditSnapshot(
            canonical_name="OpenAI", canonical_name_normalized="openai"
        )
        assert snap.canonical_name == "OpenAI"
        assert snap.canonical_name_normalized == "openai"
        assert snap.description is None


class TestEntityEditRollback:
    def test_requires_before_and_after(self) -> None:
        rb = EntityEditRollback(
            before=EntityEditSnapshot(canonical_name="Openai"),
            after=EntityEditSnapshot(canonical_name="OpenAI"),
            changed_fields=["canonical_name"],
        )
        assert rb.before.canonical_name == "Openai"
        assert rb.after.canonical_name == "OpenAI"
        assert rb.changed_fields == ["canonical_name"]

    def test_validates_nested_dict(self) -> None:
        rb = EntityEditRollback.model_validate(
            {
                "before": {"description": "old"},
                "after": {"description": "new"},
                "changed_fields": ["description"],
            }
        )
        assert rb.before.description == "old"
        assert rb.after.description == "new"

    def test_changed_fields_defaults_empty(self) -> None:
        rb = EntityEditRollback(before=EntityEditSnapshot(), after=EntityEditSnapshot())
        assert rb.changed_fields == []


class TestEntityOperationLogModels:
    def test_base_defaults(self) -> None:
        base = EntityOperationLogCreate(
            entity_id=_uuid(),
            rollback_data=EntityEditRollback(
                before=EntityEditSnapshot(), after=EntityEditSnapshot()
            ),
        )
        assert base.operation_type == "update"
        assert base.performed_by == "system"

    def test_rejects_invalid_operation_type(self) -> None:
        with pytest.raises(ValidationError):
            EntityOperationLogCreate(
                entity_id=_uuid(),
                operation_type="merge",
                rollback_data=EntityEditRollback(
                    before=EntityEditSnapshot(), after=EntityEditSnapshot()
                ),
            )

    def test_update_model_optional(self) -> None:
        upd = EntityOperationLogUpdate()
        assert upd.rolled_back is None
        assert upd.rolled_back_at is None
        upd2 = EntityOperationLogUpdate(rolled_back=True)
        assert upd2.rolled_back is True

    def test_full_model_from_orm_attributes(self) -> None:
        db_obj = EntityOperationLogDB(
            id=_uuid(),
            entity_id=_uuid(),
            operation_type="update",
            rollback_data={
                "before": {"canonical_name": "Openai"},
                "after": {"canonical_name": "OpenAI"},
                "changed_fields": ["canonical_name"],
            },
            performed_by="user:local",
            performed_at=datetime.now(UTC),
            rolled_back=False,
            rolled_back_at=None,
        )
        full = EntityOperationLog.model_validate(db_obj)
        assert full.performed_by == "user:local"
        assert full.rolled_back is False
        assert full.rollback_data.before.canonical_name == "Openai"
        assert full.rollback_data.changed_fields == ["canonical_name"]
