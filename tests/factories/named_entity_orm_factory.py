"""
Factory for the NamedEntity ORM model using factory_boy.

Provides reusable in-memory ``NamedEntity`` ORM instances for tests that need a
persistable row (unit tests with mocked repos, integration tests via
``session.add``). Mirrors ``entity_operation_log_factory`` — the ORM model is
targeted directly (distinct from ``named_entity_factory`` which builds the
Pydantic models).

Unlike the Pydantic factories, ORM defaults (``mention_count``, ``confidence``,
``discovery_method`` …) are only applied at flush time, so this factory sets
them explicitly to yield a fully-populated in-memory object.
"""

from __future__ import annotations

import uuid
from typing import Any

import factory
from factory import LazyFunction, Sequence
from uuid_utils import uuid7

from chronovista.db.models import NamedEntity as NamedEntityDB


def _uuid7() -> uuid.UUID:
    """Generate a UUIDv7 as a standard uuid.UUID (ORM PGUUID compatible)."""
    return uuid.UUID(bytes=uuid7().bytes)


class NamedEntityDBFactory(factory.Factory[NamedEntityDB]):
    """Factory for NamedEntity ORM models."""

    class Meta:
        model = NamedEntityDB

    id: Any = LazyFunction(_uuid7)
    canonical_name: Any = Sequence(lambda n: f"Entity {n}")
    canonical_name_normalized: Any = Sequence(lambda n: f"entity {n}")
    entity_type: Any = LazyFunction(lambda: "organization")
    description: Any = LazyFunction(lambda: None)
    status: Any = LazyFunction(lambda: "active")
    mention_count: Any = LazyFunction(lambda: 0)
    video_count: Any = LazyFunction(lambda: 0)
    channel_count: Any = LazyFunction(lambda: 0)
    confidence: Any = LazyFunction(lambda: 1.0)
    discovery_method: Any = LazyFunction(lambda: "user_created")


def create_named_entity_db(**kwargs: Any) -> NamedEntityDB:
    """Build an in-memory NamedEntity ORM instance with keyword overrides."""
    result = NamedEntityDBFactory.build(**kwargs)
    assert isinstance(result, NamedEntityDB)
    return result
