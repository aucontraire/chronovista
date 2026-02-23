"""
Factory for TagAlias Pydantic models using factory_boy.

Provides reusable test data factories for all TagAlias model variants
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

from chronovista.models.enums import CreationMethod
from chronovista.models.tag_alias import (
    TagAlias,
    TagAliasBase,
    TagAliasCreate,
    TagAliasUpdate,
)


class TagAliasBaseFactory(factory.Factory[TagAliasBase]):
    """Factory for TagAliasBase models."""

    class Meta:
        model = TagAliasBase

    raw_form: Any = Sequence(lambda n: f"raw_tag_{n}")
    normalized_form: Any = Sequence(lambda n: f"raw_tag_{n}")
    creation_method: Any = LazyFunction(lambda: CreationMethod.AUTO_NORMALIZE)


class TagAliasCreateFactory(factory.Factory[TagAliasCreate]):
    """Factory for TagAliasCreate models."""

    class Meta:
        model = TagAliasCreate

    raw_form: Any = Sequence(lambda n: f"raw_tag_{n}")
    normalized_form: Any = Sequence(lambda n: f"raw_tag_{n}")
    creation_method: Any = LazyFunction(lambda: CreationMethod.AUTO_NORMALIZE)
    canonical_tag_id: Any = LazyFunction(_uuid7)
    normalization_version: Any = LazyFunction(lambda: 1)
    occurrence_count: Any = LazyFunction(lambda: 1)


class TagAliasUpdateFactory(factory.Factory[TagAliasUpdate]):
    """Factory for TagAliasUpdate models.

    Note: This factory respects the model's default values (None for all fields).
    For Update models, the default behavior should be an empty update (all None),
    with values only generated when explicitly requested.
    """

    class Meta:
        model = TagAliasUpdate

    # No default values - respects model defaults (None for all fields)


class TagAliasFactory(factory.Factory[TagAlias]):
    """Factory for full TagAlias models with all fields."""

    class Meta:
        model = TagAlias

    id: Any = LazyFunction(_uuid7)
    raw_form: Any = Sequence(lambda n: f"raw_tag_{n}")
    normalized_form: Any = Sequence(lambda n: f"raw_tag_{n}")
    creation_method: Any = LazyFunction(lambda: CreationMethod.AUTO_NORMALIZE)
    canonical_tag_id: Any = LazyFunction(_uuid7)
    normalization_version: Any = LazyFunction(lambda: 1)
    occurrence_count: Any = LazyFunction(lambda: 1)
    first_seen_at: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )
    last_seen_at: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )
    created_at: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )


# Convenience factory methods
def create_tag_alias(**kwargs: Any) -> TagAlias:
    """Create a TagAlias with keyword arguments."""
    result = TagAliasFactory.build(**kwargs)
    assert isinstance(result, TagAlias)
    return result


def create_tag_alias_base(**kwargs: Any) -> TagAliasBase:
    """Create a TagAliasBase with keyword arguments."""
    result = TagAliasBaseFactory.build(**kwargs)
    assert isinstance(result, TagAliasBase)
    return result


def create_tag_alias_create(**kwargs: Any) -> TagAliasCreate:
    """Create a TagAliasCreate with keyword arguments."""
    result = TagAliasCreateFactory.build(**kwargs)
    assert isinstance(result, TagAliasCreate)
    return result


def create_tag_alias_update(**kwargs: Any) -> TagAliasUpdate:
    """Create a TagAliasUpdate with keyword arguments."""
    result = TagAliasUpdateFactory.build(**kwargs)
    assert isinstance(result, TagAliasUpdate)
    return result


# Common test data patterns
class TagAliasTestData:
    """Common test data patterns for TagAlias models."""

    VALID_RAW_FORMS = [
        "Python",
        "#python",
        "PYTHON",
        "python3",
        "Machine Learning",
        "#MachineLearning",
    ]

    VALID_NORMALIZED_FORMS = [
        "python",
        "python",
        "python",
        "python3",
        "machine learning",
        "machinelearning",
    ]

    VALID_CREATION_METHODS = [
        CreationMethod.AUTO_NORMALIZE,
        CreationMethod.MANUAL_MERGE,
        CreationMethod.BACKFILL,
        CreationMethod.API_CREATE,
    ]

    INVALID_RAW_FORMS = [
        "",  # Empty
        "x" * 501,  # Too long (max is 500)
    ]

    @classmethod
    def valid_tag_alias_data(cls) -> dict[str, Any]:
        """Get valid tag alias data."""
        return {
            "raw_form": cls.VALID_RAW_FORMS[0],
            "normalized_form": cls.VALID_NORMALIZED_FORMS[0],
            "creation_method": CreationMethod.AUTO_NORMALIZE,
        }

    @classmethod
    def minimal_tag_alias_data(cls) -> dict[str, Any]:
        """Get minimal valid tag alias data."""
        return {
            "raw_form": "Python",
            "normalized_form": "python",
        }
