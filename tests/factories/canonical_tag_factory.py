"""
Factory for CanonicalTag Pydantic models using factory_boy.

Provides reusable test data factories for all CanonicalTag model variants
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

from chronovista.models.canonical_tag import (
    CanonicalTag,
    CanonicalTagBase,
    CanonicalTagCreate,
    CanonicalTagUpdate,
)
from chronovista.models.enums import TagStatus


class CanonicalTagBaseFactory(factory.Factory[CanonicalTagBase]):
    """Factory for CanonicalTagBase models."""

    class Meta:
        model = CanonicalTagBase

    canonical_form: Any = Sequence(lambda n: f"Tag {n}")
    normalized_form: Any = Sequence(lambda n: f"tag {n}")
    entity_type: Any = LazyFunction(lambda: None)
    status: Any = LazyFunction(lambda: TagStatus.ACTIVE)


class CanonicalTagCreateFactory(factory.Factory[CanonicalTagCreate]):
    """Factory for CanonicalTagCreate models."""

    class Meta:
        model = CanonicalTagCreate

    canonical_form: Any = Sequence(lambda n: f"Tag {n}")
    normalized_form: Any = Sequence(lambda n: f"tag {n}")
    entity_type: Any = LazyFunction(lambda: None)
    status: Any = LazyFunction(lambda: TagStatus.ACTIVE)
    alias_count: Any = LazyFunction(lambda: 1)
    video_count: Any = LazyFunction(lambda: 0)
    entity_id: Any = LazyFunction(lambda: None)
    merged_into_id: Any = LazyFunction(lambda: None)


class CanonicalTagUpdateFactory(factory.Factory[CanonicalTagUpdate]):
    """Factory for CanonicalTagUpdate models.

    Note: This factory respects the model's default values (None for all fields).
    For Update models, the default behavior should be an empty update (all None),
    with values only generated when explicitly requested.
    """

    class Meta:
        model = CanonicalTagUpdate

    # No default values - respects model defaults (None for all fields)


class CanonicalTagFactory(factory.Factory[CanonicalTag]):
    """Factory for full CanonicalTag models with all fields."""

    class Meta:
        model = CanonicalTag

    id: Any = LazyFunction(_uuid7)
    canonical_form: Any = Sequence(lambda n: f"Tag {n}")
    normalized_form: Any = Sequence(lambda n: f"tag {n}")
    entity_type: Any = LazyFunction(lambda: None)
    status: Any = LazyFunction(lambda: TagStatus.ACTIVE)
    alias_count: Any = LazyFunction(lambda: 1)
    video_count: Any = LazyFunction(lambda: 0)
    entity_id: Any = LazyFunction(lambda: None)
    merged_into_id: Any = LazyFunction(lambda: None)
    created_at: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )
    updated_at: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )


# Convenience factory methods
def create_canonical_tag(**kwargs: Any) -> CanonicalTag:
    """Create a CanonicalTag with keyword arguments."""
    result = CanonicalTagFactory.build(**kwargs)
    assert isinstance(result, CanonicalTag)
    return result


def create_canonical_tag_base(**kwargs: Any) -> CanonicalTagBase:
    """Create a CanonicalTagBase with keyword arguments."""
    result = CanonicalTagBaseFactory.build(**kwargs)
    assert isinstance(result, CanonicalTagBase)
    return result


def create_canonical_tag_create(**kwargs: Any) -> CanonicalTagCreate:
    """Create a CanonicalTagCreate with keyword arguments."""
    result = CanonicalTagCreateFactory.build(**kwargs)
    assert isinstance(result, CanonicalTagCreate)
    return result


def create_canonical_tag_update(**kwargs: Any) -> CanonicalTagUpdate:
    """Create a CanonicalTagUpdate with keyword arguments."""
    result = CanonicalTagUpdateFactory.build(**kwargs)
    assert isinstance(result, CanonicalTagUpdate)
    return result


# Common test data patterns
class CanonicalTagTestData:
    """Common test data patterns for CanonicalTag models."""

    VALID_CANONICAL_FORMS = [
        "Python",
        "Machine Learning",
        "New York City",
        "Google",
        "Tutorial",
        "A",  # Minimum length
    ]

    VALID_NORMALIZED_FORMS = [
        "python",
        "machine learning",
        "new york city",
        "google",
        "tutorial",
        "a",
    ]

    VALID_STATUSES = [
        TagStatus.ACTIVE,
        TagStatus.MERGED,
        TagStatus.DEPRECATED,
    ]

    INVALID_CANONICAL_FORMS = [
        "",  # Empty
        "x" * 501,  # Too long (max is 500)
    ]

    @classmethod
    def valid_canonical_tag_data(cls) -> dict[str, Any]:
        """Get valid canonical tag data."""
        return {
            "canonical_form": cls.VALID_CANONICAL_FORMS[0],
            "normalized_form": cls.VALID_NORMALIZED_FORMS[0],
            "entity_type": None,
            "status": TagStatus.ACTIVE,
        }

    @classmethod
    def minimal_canonical_tag_data(cls) -> dict[str, Any]:
        """Get minimal valid canonical tag data."""
        return {
            "canonical_form": "Python",
            "normalized_form": "python",
        }
