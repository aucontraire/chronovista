"""
Factory for EntityAlias Pydantic models using factory_boy.

Provides reusable test data factories for all EntityAlias model variants
with sensible defaults and easy customization.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import factory
from factory import LazyFunction, Sequence
from uuid_utils import uuid7


def _uuid7() -> uuid.UUID:
    """Generate a UUIDv7 as a standard uuid.UUID for Pydantic compatibility."""
    return uuid.UUID(bytes=uuid7().bytes)

from chronovista.models.entity_alias import (
    EntityAlias,
    EntityAliasBase,
    EntityAliasCreate,
    EntityAliasUpdate,
)
from chronovista.models.enums import EntityAliasType


class EntityAliasBaseFactory(factory.Factory[EntityAliasBase]):
    """Factory for EntityAliasBase models."""

    class Meta:
        model = EntityAliasBase

    alias_name: Any = Sequence(lambda n: f"Alias {n}")
    alias_name_normalized: Any = Sequence(lambda n: f"alias {n}")
    alias_type: Any = LazyFunction(lambda: EntityAliasType.NAME_VARIANT)


class EntityAliasCreateFactory(factory.Factory[EntityAliasCreate]):
    """Factory for EntityAliasCreate models."""

    class Meta:
        model = EntityAliasCreate

    alias_name: Any = Sequence(lambda n: f"Alias {n}")
    alias_name_normalized: Any = Sequence(lambda n: f"alias {n}")
    alias_type: Any = LazyFunction(lambda: EntityAliasType.NAME_VARIANT)
    entity_id: Any = LazyFunction(_uuid7)
    occurrence_count: Any = LazyFunction(lambda: 0)


class EntityAliasUpdateFactory(factory.Factory[EntityAliasUpdate]):
    """Factory for EntityAliasUpdate models.

    Note: This factory respects the model's default values (None for all fields).
    For Update models, the default behavior should be an empty update (all None),
    with values only generated when explicitly requested.
    """

    class Meta:
        model = EntityAliasUpdate

    # No default values - respects model defaults (None for all fields)


class EntityAliasFactory(factory.Factory[EntityAlias]):
    """Factory for full EntityAlias models with all fields."""

    class Meta:
        model = EntityAlias

    id: Any = LazyFunction(_uuid7)
    alias_name: Any = Sequence(lambda n: f"Alias {n}")
    alias_name_normalized: Any = Sequence(lambda n: f"alias {n}")
    alias_type: Any = LazyFunction(lambda: EntityAliasType.NAME_VARIANT)
    entity_id: Any = LazyFunction(_uuid7)
    occurrence_count: Any = LazyFunction(lambda: 0)
    first_seen_at: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )
    last_seen_at: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )


# Convenience factory methods
def create_entity_alias(**kwargs: Any) -> EntityAlias:
    """Create an EntityAlias with keyword arguments."""
    result = EntityAliasFactory.build(**kwargs)
    assert isinstance(result, EntityAlias)
    return result


def create_entity_alias_base(**kwargs: Any) -> EntityAliasBase:
    """Create an EntityAliasBase with keyword arguments."""
    result = EntityAliasBaseFactory.build(**kwargs)
    assert isinstance(result, EntityAliasBase)
    return result


def create_entity_alias_create(**kwargs: Any) -> EntityAliasCreate:
    """Create an EntityAliasCreate with keyword arguments."""
    result = EntityAliasCreateFactory.build(**kwargs)
    assert isinstance(result, EntityAliasCreate)
    return result


def create_entity_alias_update(**kwargs: Any) -> EntityAliasUpdate:
    """Create an EntityAliasUpdate with keyword arguments."""
    result = EntityAliasUpdateFactory.build(**kwargs)
    assert isinstance(result, EntityAliasUpdate)
    return result


# Common test data patterns
class EntityAliasTestData:
    """Common test data patterns for EntityAlias models."""

    VALID_ALIAS_NAMES = [
        "Elon",
        "E. Musk",
        "SpaceX CEO",
        "Tesla CEO",
        "Mr. Musk",
    ]

    VALID_ALIAS_NAMES_NORMALIZED = [
        "elon",
        "e. musk",
        "spacex ceo",
        "tesla ceo",
        "mr. musk",
    ]

    VALID_ALIAS_TYPES = [
        EntityAliasType.NAME_VARIANT,
        EntityAliasType.ABBREVIATION,
        EntityAliasType.NICKNAME,
        EntityAliasType.ASR_ERROR,
        EntityAliasType.TRANSLATED_NAME,
        EntityAliasType.FORMER_NAME,
    ]

    INVALID_ALIAS_NAMES = [
        "",  # Empty
        "x" * 501,  # Too long (max is 500)
    ]

    @classmethod
    def valid_entity_alias_data(cls) -> dict[str, Any]:
        """Get valid entity alias data."""
        return {
            "alias_name": cls.VALID_ALIAS_NAMES[0],
            "alias_name_normalized": cls.VALID_ALIAS_NAMES_NORMALIZED[0],
            "alias_type": EntityAliasType.NAME_VARIANT,
        }

    @classmethod
    def minimal_entity_alias_data(cls) -> dict[str, Any]:
        """Get minimal valid entity alias data."""
        return {
            "alias_name": "Elon",
            "alias_name_normalized": "elon",
        }
