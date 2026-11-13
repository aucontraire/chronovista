"""Factory for EntityAsrError Pydantic models using factory_boy (Feature 110).

Reusable test data for the dedicated ASR-error store models. Uses invented names
only — never library content (Constitution VI).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import factory
from factory import LazyFunction, Sequence
from uuid_utils import uuid7


def _uuid7() -> uuid.UUID:
    """Generate a UUIDv7 as a standard uuid.UUID for Pydantic compatibility."""
    return uuid.UUID(bytes=uuid7().bytes)


from chronovista.models.entity_asr_error import (
    EntityAsrError,
    EntityAsrErrorBase,
    EntityAsrErrorCreate,
    EntityAsrErrorUpdate,
)


class EntityAsrErrorBaseFactory(factory.Factory[EntityAsrErrorBase]):
    """Factory for EntityAsrErrorBase models."""

    class Meta:
        model = EntityAsrErrorBase

    alias_name: Any = Sequence(lambda n: f"Garbled Form {n}")
    alias_name_normalized: Any = Sequence(lambda n: f"garbled form {n}")


class EntityAsrErrorCreateFactory(factory.Factory[EntityAsrErrorCreate]):
    """Factory for EntityAsrErrorCreate models."""

    class Meta:
        model = EntityAsrErrorCreate

    alias_name: Any = Sequence(lambda n: f"Garbled Form {n}")
    alias_name_normalized: Any = Sequence(lambda n: f"garbled form {n}")
    entity_id: Any = LazyFunction(_uuid7)


class EntityAsrErrorUpdateFactory(factory.Factory[EntityAsrErrorUpdate]):
    """Factory for EntityAsrErrorUpdate models (respects None defaults)."""

    class Meta:
        model = EntityAsrErrorUpdate

    # No default values - respects model defaults (None for all fields)


class EntityAsrErrorFactory(factory.Factory[EntityAsrError]):
    """Factory for full EntityAsrError models with all fields."""

    class Meta:
        model = EntityAsrError

    id: Any = LazyFunction(_uuid7)
    alias_name: Any = Sequence(lambda n: f"Garbled Form {n}")
    alias_name_normalized: Any = Sequence(lambda n: f"garbled form {n}")
    entity_id: Any = LazyFunction(_uuid7)
    first_seen_at: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
    )
    last_seen_at: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
    )


def create_entity_asr_error(**kwargs: Any) -> EntityAsrError:
    """Create a full EntityAsrError with keyword arguments."""
    result = EntityAsrErrorFactory.build(**kwargs)
    assert isinstance(result, EntityAsrError)
    return result


def create_entity_asr_error_create(**kwargs: Any) -> EntityAsrErrorCreate:
    """Create an EntityAsrErrorCreate with keyword arguments."""
    result = EntityAsrErrorCreateFactory.build(**kwargs)
    assert isinstance(result, EntityAsrErrorCreate)
    return result
