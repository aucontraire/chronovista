"""
Factory for EntityOperationLog ORM model using factory_boy.

Provides reusable in-memory test data for EntityOperationLog instances
(Feature 057). Mirrors ``tag_operation_log_factory`` — the ORM model is
targeted directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import factory
from factory import LazyFunction
from uuid_utils import uuid7

from chronovista.db.models import EntityOperationLog


def _default_rollback() -> dict[str, Any]:
    """Return a minimal valid rollback_data payload (rename Openai -> OpenAI)."""
    return {
        "before": {
            "canonical_name": "Openai",
            "canonical_name_normalized": "openai",
        },
        "after": {
            "canonical_name": "OpenAI",
            "canonical_name_normalized": "openai",
        },
        "changed_fields": ["canonical_name"],
    }


class EntityOperationLogFactory(factory.Factory[EntityOperationLog]):
    """Factory for EntityOperationLog ORM models."""

    class Meta:
        model = EntityOperationLog

    id: Any = LazyFunction(uuid7)
    entity_id: Any = LazyFunction(uuid7)
    operation_type: Any = LazyFunction(lambda: "update")
    rollback_data: Any = LazyFunction(_default_rollback)
    performed_by: Any = LazyFunction(lambda: "user:local")
    performed_at: Any = LazyFunction(
        lambda: datetime(2026, 7, 22, 10, 30, 0, tzinfo=UTC)
    )
    rolled_back: Any = LazyFunction(lambda: False)
    rolled_back_at: Any = LazyFunction(lambda: None)


def create_entity_operation_log(**kwargs: Any) -> EntityOperationLog:
    """Build an in-memory EntityOperationLog with keyword overrides."""
    result = EntityOperationLogFactory.build(**kwargs)
    assert isinstance(result, EntityOperationLog)
    return result
