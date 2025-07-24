"""
Factory definitions for user language preference models.

Provides factory-boy factories for creating test instances of user language preference models
with realistic and consistent test data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import factory
from factory import LazyFunction

from chronovista.models.enums import LanguageCode, LanguagePreferenceType
from chronovista.models.user_language_preference import (
    UserLanguagePreference,
    UserLanguagePreferenceBase,
    UserLanguagePreferenceCreate,
    UserLanguagePreferenceUpdate,
)


class UserLanguagePreferenceBaseFactory(factory.Factory):
    """Factory for UserLanguagePreferenceBase models."""

    class Meta:
        model = UserLanguagePreferenceBase

    user_id = factory.LazyFunction(lambda: "user_12345")
    language_code = factory.LazyFunction(lambda: LanguageCode.ENGLISH_US)
    preference_type = factory.LazyFunction(lambda: LanguagePreferenceType.FLUENT)
    priority = factory.LazyFunction(lambda: 1)
    auto_download_transcripts = factory.LazyFunction(lambda: True)
    learning_goal = factory.LazyFunction(
        lambda: "Improve professional English communication skills"
    )


class UserLanguagePreferenceCreateFactory(factory.Factory):
    """Factory for UserLanguagePreferenceCreate models."""

    class Meta:
        model = UserLanguagePreferenceCreate

    user_id = factory.LazyFunction(lambda: "user_create_67890")
    language_code = factory.LazyFunction(lambda: LanguageCode.SPANISH)
    preference_type = factory.LazyFunction(lambda: LanguagePreferenceType.LEARNING)
    priority = factory.LazyFunction(lambda: 2)
    auto_download_transcripts = factory.LazyFunction(lambda: True)
    learning_goal = factory.LazyFunction(
        lambda: "Learn Spanish for travel and cultural understanding"
    )


class UserLanguagePreferenceUpdateFactory(factory.Factory):
    """Factory for UserLanguagePreferenceUpdate models."""

    class Meta:
        model = UserLanguagePreferenceUpdate

    preference_type = factory.LazyFunction(lambda: LanguagePreferenceType.CURIOUS)
    priority = factory.LazyFunction(lambda: 3)
    auto_download_transcripts = factory.LazyFunction(lambda: False)
    learning_goal = factory.LazyFunction(
        lambda: "Updated: Exploring French literature and philosophy"
    )


class UserLanguagePreferenceFactory(factory.Factory):
    """Factory for UserLanguagePreference models."""

    class Meta:
        model = UserLanguagePreference

    user_id = factory.LazyFunction(lambda: "user_full_11111")
    language_code = factory.LazyFunction(lambda: LanguageCode.FRENCH_FR)
    preference_type = factory.LazyFunction(lambda: LanguagePreferenceType.CURIOUS)
    priority = factory.LazyFunction(lambda: 4)
    auto_download_transcripts = factory.LazyFunction(lambda: False)
    learning_goal = factory.LazyFunction(
        lambda: "Cultural interest in French media and cinema"
    )
    created_at = factory.LazyFunction(
        lambda: datetime(2023, 10, 15, 14, 30, 0, tzinfo=timezone.utc)
    )


# Test data constants for validation testing
class UserLanguagePreferenceTestData:
    """Test data constants for user language preference models."""

    # Valid test data
    VALID_USER_IDS = [
        "user_12345",
        "test_user_001",
        "admin_user",
        "language_learner_999",
        "u",  # Min length (1 char)
        "a" * 100,  # Long user ID
    ]

    VALID_LANGUAGE_CODES = [
        LanguageCode.ENGLISH,  # Language only
        LanguageCode.ENGLISH_US,  # Language-Country
        LanguageCode.CHINESE_SIMPLIFIED,  # Chinese Simplified
        LanguageCode.PORTUGUESE_BR,  # Portuguese Brazil
        LanguageCode.SPANISH_MX,  # Spanish Mexico
        LanguageCode.FRENCH_CA,  # French Canada
        LanguageCode.GERMAN_AT,  # German Austria
        LanguageCode.ITALIAN_IT,  # Italian Italy
        LanguageCode.JAPANESE,  # Japanese
        LanguageCode.KOREAN,  # Korean
        LanguageCode.RUSSIAN,  # Russian
        LanguageCode.ARABIC,  # Arabic
    ]

    VALID_PREFERENCE_TYPES = [
        LanguagePreferenceType.FLUENT,
        LanguagePreferenceType.LEARNING,
        LanguagePreferenceType.CURIOUS,
        LanguagePreferenceType.EXCLUDE,
    ]

    VALID_PRIORITIES = [1, 2, 3, 4, 5, 10, 100]

    VALID_LEARNING_GOALS = [
        "Improve business communication",
        "Learn for travel purposes",
        "Cultural interest and media consumption",
        "Academic research and study",
        "Connect with family heritage",
        "Professional development",
        None,  # Optional field
    ]

    # Invalid test data
    INVALID_USER_IDS = ["", "   ", "\t\n"]  # Empty, whitespace
    INVALID_LANGUAGE_CODES = [
        "",  # Empty
        "a",  # Too short (language part must be 2-3 chars)
        "a-b-c-d",  # Too many parts (max 3 parts)
        "-US",  # Missing language (first part empty)
        "english",  # Too long (language part > 3 chars)
    ]
    INVALID_PRIORITIES = [0, -1, -100]  # Must be >= 1


# Convenience factory functions
def create_user_language_preference_base(**kwargs) -> UserLanguagePreferenceBase:
    """Create a UserLanguagePreferenceBase with optional overrides."""
    return UserLanguagePreferenceBaseFactory(**kwargs)


def create_user_language_preference_create(**kwargs) -> UserLanguagePreferenceCreate:
    """Create a UserLanguagePreferenceCreate with optional overrides."""
    return UserLanguagePreferenceCreateFactory(**kwargs)


def create_user_language_preference_update(**kwargs) -> UserLanguagePreferenceUpdate:
    """Create a UserLanguagePreferenceUpdate with optional overrides."""
    return UserLanguagePreferenceUpdateFactory(**kwargs)


def create_user_language_preference(**kwargs) -> UserLanguagePreference:
    """Create a UserLanguagePreference with optional overrides."""
    return UserLanguagePreferenceFactory(**kwargs)


def create_batch_user_language_preferences(
    count: int = 5,
) -> List[UserLanguagePreference]:
    """Create a batch of UserLanguagePreference instances for testing."""
    preferences = []
    base_user_ids = ["user_001", "user_002", "user_003", "user_004", "user_005"]
    base_languages = [
        LanguageCode.ENGLISH_US,
        LanguageCode.SPANISH,
        LanguageCode.FRENCH_FR,
        LanguageCode.GERMAN,
        LanguageCode.JAPANESE,
    ]
    base_types = [
        LanguagePreferenceType.FLUENT,
        LanguagePreferenceType.LEARNING,
        LanguagePreferenceType.CURIOUS,
        LanguagePreferenceType.EXCLUDE,
        LanguagePreferenceType.FLUENT,
    ]
    base_goals = [
        "Professional communication",
        "Language learning practice",
        "Cultural exploration",
        "Exclude unwanted content",
        "Native language preference",
    ]

    for i in range(count):
        user_id = base_user_ids[i % len(base_user_ids)]
        language_code = base_languages[i % len(base_languages)]
        preference_type = base_types[i % len(base_types)]
        learning_goal = base_goals[i % len(base_goals)]

        preference = UserLanguagePreferenceFactory(
            user_id=user_id,
            language_code=language_code,
            preference_type=preference_type,
            priority=i + 1,
            auto_download_transcripts=(i % 2 == 0),  # Alternate true/false
            learning_goal=(
                learning_goal
                if preference_type != LanguagePreferenceType.EXCLUDE
                else None
            ),
        )
        preferences.append(preference)

    return preferences
