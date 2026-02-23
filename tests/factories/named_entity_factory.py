"""
Factory for NamedEntity Pydantic models using factory_boy.

Provides reusable test data factories for all NamedEntity model variants
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

from chronovista.models.enums import DiscoveryMethod, EntityType, TagStatus
from chronovista.models.named_entity import (
    NamedEntity,
    NamedEntityBase,
    NamedEntityCreate,
    NamedEntityUpdate,
)


class NamedEntityBaseFactory(factory.Factory[NamedEntityBase]):
    """Factory for NamedEntityBase models."""

    class Meta:
        model = NamedEntityBase

    canonical_name: Any = Sequence(lambda n: f"Entity {n}")
    canonical_name_normalized: Any = Sequence(lambda n: f"entity {n}")
    entity_type: Any = LazyFunction(lambda: EntityType.PERSON)
    discovery_method: Any = LazyFunction(lambda: DiscoveryMethod.MANUAL)
    status: Any = LazyFunction(lambda: TagStatus.ACTIVE)


class NamedEntityCreateFactory(factory.Factory[NamedEntityCreate]):
    """Factory for NamedEntityCreate models."""

    class Meta:
        model = NamedEntityCreate

    canonical_name: Any = Sequence(lambda n: f"Entity {n}")
    canonical_name_normalized: Any = Sequence(lambda n: f"entity {n}")
    entity_type: Any = LazyFunction(lambda: EntityType.PERSON)
    discovery_method: Any = LazyFunction(lambda: DiscoveryMethod.MANUAL)
    status: Any = LazyFunction(lambda: TagStatus.ACTIVE)
    entity_subtype: Any = LazyFunction(lambda: None)
    description: Any = LazyFunction(lambda: None)
    external_ids: Any = LazyFunction(dict)
    confidence: Any = LazyFunction(lambda: 1.0)
    merged_into_id: Any = LazyFunction(lambda: None)


class NamedEntityUpdateFactory(factory.Factory[NamedEntityUpdate]):
    """Factory for NamedEntityUpdate models.

    Note: This factory respects the model's default values (None for all fields).
    For Update models, the default behavior should be an empty update (all None),
    with values only generated when explicitly requested.
    """

    class Meta:
        model = NamedEntityUpdate

    # No default values - respects model defaults (None for all fields)


class NamedEntityFactory(factory.Factory[NamedEntity]):
    """Factory for full NamedEntity models with all fields."""

    class Meta:
        model = NamedEntity

    id: Any = LazyFunction(_uuid7)
    canonical_name: Any = Sequence(lambda n: f"Entity {n}")
    canonical_name_normalized: Any = Sequence(lambda n: f"entity {n}")
    entity_type: Any = LazyFunction(lambda: EntityType.PERSON)
    discovery_method: Any = LazyFunction(lambda: DiscoveryMethod.MANUAL)
    status: Any = LazyFunction(lambda: TagStatus.ACTIVE)
    entity_subtype: Any = LazyFunction(lambda: None)
    description: Any = LazyFunction(lambda: None)
    external_ids: Any = LazyFunction(dict)
    mention_count: Any = LazyFunction(lambda: 0)
    video_count: Any = LazyFunction(lambda: 0)
    channel_count: Any = LazyFunction(lambda: 0)
    confidence: Any = LazyFunction(lambda: 1.0)
    merged_into_id: Any = LazyFunction(lambda: None)
    created_at: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )
    updated_at: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )


# Convenience factory methods
def create_named_entity(**kwargs: Any) -> NamedEntity:
    """Create a NamedEntity with keyword arguments."""
    result = NamedEntityFactory.build(**kwargs)
    assert isinstance(result, NamedEntity)
    return result


def create_named_entity_base(**kwargs: Any) -> NamedEntityBase:
    """Create a NamedEntityBase with keyword arguments."""
    result = NamedEntityBaseFactory.build(**kwargs)
    assert isinstance(result, NamedEntityBase)
    return result


def create_named_entity_create(**kwargs: Any) -> NamedEntityCreate:
    """Create a NamedEntityCreate with keyword arguments."""
    result = NamedEntityCreateFactory.build(**kwargs)
    assert isinstance(result, NamedEntityCreate)
    return result


def create_named_entity_update(**kwargs: Any) -> NamedEntityUpdate:
    """Create a NamedEntityUpdate with keyword arguments."""
    result = NamedEntityUpdateFactory.build(**kwargs)
    assert isinstance(result, NamedEntityUpdate)
    return result


# Common test data patterns
class NamedEntityTestData:
    """Common test data patterns for NamedEntity models."""

    VALID_CANONICAL_NAMES = [
        "Elon Musk",
        "Google",
        "New York City",
        "PyCon",
        "Python",
        "machine learning",
    ]

    VALID_CANONICAL_NAMES_NORMALIZED = [
        "elon musk",
        "google",
        "new york city",
        "pycon",
        "python",
        "machine learning",
    ]

    VALID_ENTITY_TYPES = [
        EntityType.PERSON,
        EntityType.ORGANIZATION,
        EntityType.PLACE,
        EntityType.EVENT,
        EntityType.WORK,
        EntityType.TECHNICAL_TERM,
    ]

    VALID_DISCOVERY_METHODS = [
        DiscoveryMethod.MANUAL,
        DiscoveryMethod.SPACY_NER,
        DiscoveryMethod.TAG_BOOTSTRAP,
        DiscoveryMethod.LLM_EXTRACTION,
        DiscoveryMethod.USER_CREATED,
    ]

    VALID_STATUSES = [
        TagStatus.ACTIVE,
        TagStatus.MERGED,
        TagStatus.DEPRECATED,
    ]

    INVALID_CANONICAL_NAMES = [
        "",  # Empty
        "x" * 501,  # Too long (max is 500)
    ]

    @classmethod
    def valid_named_entity_data(cls) -> dict[str, Any]:
        """Get valid named entity data."""
        return {
            "canonical_name": cls.VALID_CANONICAL_NAMES[0],
            "canonical_name_normalized": cls.VALID_CANONICAL_NAMES_NORMALIZED[0],
            "entity_type": EntityType.PERSON,
            "discovery_method": DiscoveryMethod.MANUAL,
            "status": TagStatus.ACTIVE,
        }

    @classmethod
    def minimal_named_entity_data(cls) -> dict[str, Any]:
        """Get minimal valid named entity data."""
        return {
            "canonical_name": "Elon Musk",
            "canonical_name_normalized": "elon musk",
            "entity_type": EntityType.PERSON,
        }
