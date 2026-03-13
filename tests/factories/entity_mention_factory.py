"""
Factory for EntityMention Pydantic models using factory_boy.

Provides reusable test data factories for all EntityMention model variants
with sensible defaults and easy customization.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import factory
from factory import LazyFunction, Sequence
from uuid_utils import uuid7

from chronovista.models.entity_mention import (
    EntityMention,
    EntityMentionBase,
    EntityMentionCreate,
)
from chronovista.models.enums import DetectionMethod


def _uuid7() -> uuid.UUID:
    """Generate a UUIDv7 as a standard uuid.UUID for Pydantic compatibility."""
    return uuid.UUID(bytes=uuid7().bytes)


class EntityMentionBaseFactory(factory.Factory[EntityMentionBase]):
    """Factory for EntityMentionBase models."""

    class Meta:
        model = EntityMentionBase

    entity_id: Any = LazyFunction(_uuid7)
    segment_id: Any = Sequence(lambda n: n + 1)
    video_id: Any = LazyFunction(lambda: "dQw4w9WgXcQ")  # 11-char valid video ID
    language_code: Any = LazyFunction(lambda: "en")
    mention_text: Any = Sequence(lambda n: f"Entity mention {n}")
    detection_method: Any = LazyFunction(lambda: DetectionMethod.RULE_MATCH)
    confidence: Any = LazyFunction(lambda: 1.0)
    match_start: Any = None
    match_end: Any = None
    correction_id: Any = None


class EntityMentionCreateFactory(factory.Factory[EntityMentionCreate]):
    """Factory for EntityMentionCreate models."""

    class Meta:
        model = EntityMentionCreate

    entity_id: Any = LazyFunction(_uuid7)
    segment_id: Any = Sequence(lambda n: n + 1)
    video_id: Any = LazyFunction(lambda: "dQw4w9WgXcQ")  # 11-char valid video ID
    language_code: Any = LazyFunction(lambda: "en")
    mention_text: Any = Sequence(lambda n: f"Entity mention {n}")
    detection_method: Any = LazyFunction(lambda: DetectionMethod.RULE_MATCH)
    confidence: Any = LazyFunction(lambda: 1.0)
    match_start: Any = None
    match_end: Any = None
    correction_id: Any = None


class EntityMentionFactory(factory.Factory[EntityMention]):
    """Factory for full EntityMention models with database-assigned fields."""

    class Meta:
        model = EntityMention

    id: Any = LazyFunction(_uuid7)
    entity_id: Any = LazyFunction(_uuid7)
    segment_id: Any = Sequence(lambda n: n + 1)
    video_id: Any = LazyFunction(lambda: "dQw4w9WgXcQ")  # 11-char valid video ID
    language_code: Any = LazyFunction(lambda: "en")
    mention_text: Any = Sequence(lambda n: f"Entity mention {n}")
    detection_method: Any = LazyFunction(lambda: DetectionMethod.RULE_MATCH)
    confidence: Any = LazyFunction(lambda: 1.0)
    match_start: Any = None
    match_end: Any = None
    correction_id: Any = None
    created_at: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )


# ---------------------------------------------------------------------------
# Convenience factory functions
# ---------------------------------------------------------------------------


def create_entity_mention(**kwargs: Any) -> EntityMention:
    """Create an EntityMention with keyword arguments.

    Parameters
    ----------
    **kwargs : Any
        Any field overrides to apply on top of factory defaults.

    Returns
    -------
    EntityMention
        A built EntityMention Pydantic model.
    """
    result = EntityMentionFactory.build(**kwargs)
    assert isinstance(result, EntityMention)
    return result


def create_entity_mention_base(**kwargs: Any) -> EntityMentionBase:
    """Create an EntityMentionBase with keyword arguments.

    Parameters
    ----------
    **kwargs : Any
        Any field overrides to apply on top of factory defaults.

    Returns
    -------
    EntityMentionBase
        A built EntityMentionBase Pydantic model.
    """
    result = EntityMentionBaseFactory.build(**kwargs)
    assert isinstance(result, EntityMentionBase)
    return result


def create_entity_mention_create(**kwargs: Any) -> EntityMentionCreate:
    """Create an EntityMentionCreate with keyword arguments.

    Parameters
    ----------
    **kwargs : Any
        Any field overrides to apply on top of factory defaults.

    Returns
    -------
    EntityMentionCreate
        A built EntityMentionCreate Pydantic model.
    """
    result = EntityMentionCreateFactory.build(**kwargs)
    assert isinstance(result, EntityMentionCreate)
    return result


# ---------------------------------------------------------------------------
# Common test data patterns
# ---------------------------------------------------------------------------


class EntityMentionTestData:
    """Common test data patterns for EntityMention models."""

    VALID_VIDEO_IDS = [
        "dQw4w9WgXcQ",  # Rick Astley (11 chars)
        "9bZkp7q19f0",  # Google I/O (11 chars)
        "3tmd-ClpJxA",  # Late Show (11 chars)
        "jNQXAC9IVRw",  # MKBHD (11 chars)
        "MejbOFk7H6c",  # Another video (11 chars)
    ]

    VALID_LANGUAGE_CODES = [
        "en",
        "en-US",
        "es",
        "fr",
        "de",
        "ja",
        "ko",
        "zh-CN",
        "pt-BR",
    ]

    VALID_MENTION_TEXTS = [
        "Elon Musk",
        "Google",
        "New York City",
        "Python",
        "A",  # Minimum length (1 char)
        "x" * 500,  # Maximum length (500 chars)
    ]

    INVALID_MENTION_TEXTS = [
        "",  # Empty — below min_length=1
        "x" * 501,  # Too long — above max_length=500
    ]

    INVALID_LANGUAGE_CODES = [
        "",  # Empty — below min_length=2
        "a",  # Too short — below min_length=2
        "x" * 11,  # Too long — above max_length=10
    ]

    INVALID_VIDEO_IDS = [
        "",  # Empty
        "   ",  # Whitespace
        "short",  # Too short (< 11 chars)
        "x" * 25,  # Too long (> 11 chars)
    ]

    VALID_DETECTION_METHODS = [
        DetectionMethod.RULE_MATCH,
        DetectionMethod.SPACY_NER,
        DetectionMethod.LLM_EXTRACTION,
        DetectionMethod.MANUAL,
    ]

    VALID_CONFIDENCE_VALUES = [0.0, 0.5, 1.0, 0.99, 0.01]

    INVALID_CONFIDENCE_VALUES = [-0.001, 1.001, -1.0, 2.0]

    @classmethod
    def valid_base_data(cls) -> dict[str, Any]:
        """Get valid EntityMentionBase data.

        Returns
        -------
        dict[str, Any]
            A fresh dictionary of valid field values for EntityMentionBase.
        """
        return {
            "entity_id": _uuid7(),
            "segment_id": 1,
            "video_id": cls.VALID_VIDEO_IDS[0],
            "language_code": cls.VALID_LANGUAGE_CODES[0],
            "mention_text": cls.VALID_MENTION_TEXTS[0],
            "detection_method": DetectionMethod.RULE_MATCH,
            "confidence": 1.0,
        }

    @classmethod
    def valid_full_data(cls) -> dict[str, Any]:
        """Get valid full EntityMention data including database-assigned fields.

        Returns
        -------
        dict[str, Any]
            A fresh dictionary of valid field values for EntityMention.
        """
        data = cls.valid_base_data()
        data.update(
            {
                "id": _uuid7(),
                "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            }
        )
        return data
