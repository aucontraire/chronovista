"""
Tests for user language preference models using factory pattern.

Comprehensive tests for UserLanguagePreference Pydantic models with validation,
serialization, and business logic testing using factory-boy for DRY principles.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from chronovista.models.enums import LanguagePreferenceType
from chronovista.models.user_language_preference import (
    UserLanguagePreference,
    UserLanguagePreferenceBase,
    UserLanguagePreferenceCreate,
    UserLanguagePreferenceUpdate,
)
from tests.factories.user_language_preference_factory import (
    UserLanguagePreferenceBaseFactory,
    UserLanguagePreferenceCreateFactory,
    UserLanguagePreferenceFactory,
    UserLanguagePreferenceTestData,
    UserLanguagePreferenceUpdateFactory,
    create_batch_user_language_preferences,
    create_user_language_preference,
    create_user_language_preference_base,
    create_user_language_preference_create,
    create_user_language_preference_update,
)


class TestUserLanguagePreferenceBaseFactory:
    """Test UserLanguagePreferenceBase model with factory pattern."""

    def test_user_language_preference_base_creation(self):
        """Test basic UserLanguagePreferenceBase creation from factory."""
        preference = UserLanguagePreferenceBaseFactory.build()

        assert isinstance(preference, UserLanguagePreferenceBase)
        assert preference.user_id == "user_12345"
        assert preference.language_code == "en-US"
        assert preference.preference_type == LanguagePreferenceType.FLUENT
        assert preference.priority == 1
        assert preference.auto_download_transcripts is True
        assert (
            preference.learning_goal
            == "Improve professional English communication skills"
        )

    def test_user_language_preference_base_custom_values(self):
        """Test UserLanguagePreferenceBase with custom values."""
        custom_preference = UserLanguagePreferenceBaseFactory.build(
            user_id="custom_user_123",
            language_code="es-MX",
            preference_type=LanguagePreferenceType.LEARNING,
            priority=5,
            auto_download_transcripts=False,
            learning_goal="Learn Mexican Spanish for business",
        )

        assert custom_preference.user_id == "custom_user_123"
        assert custom_preference.language_code == "es-MX"
        assert custom_preference.preference_type == LanguagePreferenceType.LEARNING
        assert custom_preference.priority == 5
        assert custom_preference.auto_download_transcripts is False
        assert custom_preference.learning_goal == "Learn Mexican Spanish for business"

    @pytest.mark.parametrize(
        "valid_user_id", UserLanguagePreferenceTestData.VALID_USER_IDS
    )
    def test_user_language_preference_base_valid_user_ids(self, valid_user_id):
        """Test UserLanguagePreferenceBase with valid user IDs."""
        preference = UserLanguagePreferenceBaseFactory.build(user_id=valid_user_id)
        assert preference.user_id == valid_user_id.strip()

    @pytest.mark.parametrize(
        "invalid_user_id", UserLanguagePreferenceTestData.INVALID_USER_IDS
    )
    def test_user_language_preference_base_invalid_user_ids(self, invalid_user_id):
        """Test UserLanguagePreferenceBase validation with invalid user IDs."""
        with pytest.raises(ValidationError):
            UserLanguagePreferenceBaseFactory.build(user_id=invalid_user_id)

    @pytest.mark.parametrize(
        "valid_language_code", UserLanguagePreferenceTestData.VALID_LANGUAGE_CODES
    )
    def test_user_language_preference_base_valid_language_codes(
        self, valid_language_code
    ):
        """Test UserLanguagePreferenceBase with valid language codes."""
        preference = UserLanguagePreferenceBaseFactory.build(
            language_code=valid_language_code
        )
        assert preference.language_code == valid_language_code

    @pytest.mark.parametrize(
        "invalid_language_code", UserLanguagePreferenceTestData.INVALID_LANGUAGE_CODES
    )
    def test_user_language_preference_base_invalid_language_codes(
        self, invalid_language_code
    ):
        """Test UserLanguagePreferenceBase validation with invalid language codes."""
        with pytest.raises(ValidationError):
            UserLanguagePreferenceBaseFactory.build(language_code=invalid_language_code)

    @pytest.mark.parametrize(
        "valid_preference_type", UserLanguagePreferenceTestData.VALID_PREFERENCE_TYPES
    )
    def test_user_language_preference_base_valid_preference_types(
        self, valid_preference_type
    ):
        """Test UserLanguagePreferenceBase with valid preference types."""
        preference = UserLanguagePreferenceBaseFactory.build(
            preference_type=valid_preference_type
        )
        assert preference.preference_type == valid_preference_type

    @pytest.mark.parametrize(
        "valid_priority", UserLanguagePreferenceTestData.VALID_PRIORITIES
    )
    def test_user_language_preference_base_valid_priorities(self, valid_priority):
        """Test UserLanguagePreferenceBase with valid priorities."""
        preference = UserLanguagePreferenceBaseFactory.build(priority=valid_priority)
        assert preference.priority == valid_priority

    @pytest.mark.parametrize(
        "invalid_priority", UserLanguagePreferenceTestData.INVALID_PRIORITIES
    )
    def test_user_language_preference_base_invalid_priorities(self, invalid_priority):
        """Test UserLanguagePreferenceBase validation with invalid priorities."""
        with pytest.raises(ValidationError):
            UserLanguagePreferenceBaseFactory.build(priority=invalid_priority)

    @pytest.mark.parametrize(
        "valid_learning_goal", UserLanguagePreferenceTestData.VALID_LEARNING_GOALS
    )
    def test_user_language_preference_base_valid_learning_goals(
        self, valid_learning_goal
    ):
        """Test UserLanguagePreferenceBase with valid learning goals."""
        preference = UserLanguagePreferenceBaseFactory.build(
            learning_goal=valid_learning_goal
        )
        assert preference.learning_goal == valid_learning_goal

    def test_user_language_preference_base_model_dump(self):
        """Test UserLanguagePreferenceBase model_dump functionality."""
        preference = UserLanguagePreferenceBaseFactory.build()
        data = preference.model_dump()

        assert isinstance(data, dict)
        assert data["user_id"] == "user_12345"
        assert data["language_code"] == "en-US"
        assert data["preference_type"] == "fluent"  # Enum value
        assert data["priority"] == 1

    def test_user_language_preference_base_model_validate(self):
        """Test UserLanguagePreferenceBase model_validate functionality."""
        data = {
            "user_id": "validate_user_123",
            "language_code": "pt-BR",
            "preference_type": "learning",
            "priority": 2,
            "auto_download_transcripts": True,
            "learning_goal": "Learn Portuguese for Brazil travel",
        }

        preference = UserLanguagePreferenceBase.model_validate(data)
        assert preference.user_id == "validate_user_123"
        assert preference.language_code == "pt-BR"
        assert preference.preference_type == LanguagePreferenceType.LEARNING
        assert preference.priority == 2

    def test_user_language_preference_base_convenience_function(self):
        """Test convenience function for UserLanguagePreferenceBase."""
        preference = create_user_language_preference_base(
            user_id="convenience_user", language_code="de-AT", priority=3
        )

        assert preference.user_id == "convenience_user"
        assert preference.language_code == "de-AT"
        assert preference.priority == 3


class TestUserLanguagePreferenceCreateFactory:
    """Test UserLanguagePreferenceCreate model with factory pattern."""

    def test_user_language_preference_create_creation(self):
        """Test basic UserLanguagePreferenceCreate creation from factory."""
        preference = UserLanguagePreferenceCreateFactory.build()

        assert isinstance(preference, UserLanguagePreferenceCreate)
        assert preference.user_id == "user_create_67890"
        assert preference.language_code == "es"
        assert preference.preference_type == LanguagePreferenceType.LEARNING
        assert preference.priority == 2

    def test_user_language_preference_create_convenience_function(self):
        """Test convenience function for UserLanguagePreferenceCreate."""
        preference = create_user_language_preference_create(
            user_id="create_test_user",
            language_code="ja",
            preference_type=LanguagePreferenceType.CURIOUS,
        )

        assert preference.user_id == "create_test_user"
        assert preference.language_code == "ja"
        assert preference.preference_type == LanguagePreferenceType.CURIOUS


class TestUserLanguagePreferenceUpdateFactory:
    """Test UserLanguagePreferenceUpdate model with factory pattern."""

    def test_user_language_preference_update_creation(self):
        """Test basic UserLanguagePreferenceUpdate creation from factory."""
        update = UserLanguagePreferenceUpdateFactory.build()

        assert isinstance(update, UserLanguagePreferenceUpdate)
        assert update.preference_type == LanguagePreferenceType.CURIOUS
        assert update.priority == 3
        assert update.auto_download_transcripts is False
        assert update.learning_goal is not None
        assert update.learning_goal and "Updated:" in update.learning_goal

    def test_user_language_preference_update_partial_data(self):
        """Test UserLanguagePreferenceUpdate with partial data."""
        update = UserLanguagePreferenceUpdateFactory.build(
            preference_type=LanguagePreferenceType.EXCLUDE,
            priority=None,  # Only update some fields
            auto_download_transcripts=None,
            learning_goal=None,
        )

        assert update.preference_type == LanguagePreferenceType.EXCLUDE
        assert update.priority is None
        assert update.auto_download_transcripts is None
        assert update.learning_goal is None

    def test_user_language_preference_update_none_values(self):
        """Test UserLanguagePreferenceUpdate with all None values."""
        update = UserLanguagePreferenceUpdate(
            preference_type=None,
            priority=None,
            auto_download_transcripts=None,
            learning_goal=None,
        )

        assert update.preference_type is None
        assert update.priority is None
        assert update.auto_download_transcripts is None
        assert update.learning_goal is None

    def test_user_language_preference_update_convenience_function(self):
        """Test convenience function for UserLanguagePreferenceUpdate."""
        update = create_user_language_preference_update(
            preference_type=LanguagePreferenceType.FLUENT, priority=1
        )

        assert update.preference_type == LanguagePreferenceType.FLUENT
        assert update.priority == 1


class TestUserLanguagePreferenceFactory:
    """Test UserLanguagePreference model with factory pattern."""

    def test_user_language_preference_creation(self):
        """Test basic UserLanguagePreference creation from factory."""
        preference = UserLanguagePreferenceFactory.build()

        assert isinstance(preference, UserLanguagePreference)
        assert preference.user_id == "user_full_11111"
        assert preference.language_code == "fr-FR"
        assert preference.preference_type == LanguagePreferenceType.CURIOUS
        assert hasattr(preference, "created_at")

    def test_user_language_preference_timestamps(self):
        """Test UserLanguagePreference with custom timestamps."""
        created_time = datetime(2023, 1, 1, tzinfo=timezone.utc)

        preference = UserLanguagePreferenceFactory.build(created_at=created_time)

        assert preference.created_at == created_time

    def test_user_language_preference_from_attributes_config(self):
        """Test UserLanguagePreference from_attributes configuration for ORM compatibility."""
        preference_data = {
            "user_id": "orm_test_user",
            "language_code": "it-IT",
            "preference_type": "fluent",
            "priority": 1,
            "auto_download_transcripts": True,
            "learning_goal": "Native Italian speaker",
            "created_at": datetime(2023, 6, 15, 10, 30, tzinfo=timezone.utc),
        }

        preference = UserLanguagePreference.model_validate(preference_data)
        assert preference.user_id == "orm_test_user"
        assert preference.language_code == "it-IT"
        assert preference.preference_type == LanguagePreferenceType.FLUENT
        assert preference.created_at is not None

    def test_user_language_preference_convenience_function(self):
        """Test convenience function for UserLanguagePreference."""
        preference = create_user_language_preference(
            user_id="convenience_full_user",
            language_code="ko",
            preference_type=LanguagePreferenceType.LEARNING,
        )

        assert preference.user_id == "convenience_full_user"
        assert preference.language_code == "ko"
        assert preference.preference_type == LanguagePreferenceType.LEARNING


class TestBatchOperations:
    """Test batch operations and advanced factory usage."""

    def test_create_batch_user_language_preferences(self):
        """Test creating multiple UserLanguagePreference instances."""
        preferences = create_batch_user_language_preferences(count=3)

        assert len(preferences) == 3
        assert all(isinstance(pref, UserLanguagePreference) for pref in preferences)

        # Check that different values are generated
        user_ids = [pref.user_id for pref in preferences]
        language_codes = [pref.language_code for pref in preferences]
        priorities = [pref.priority for pref in preferences]

        assert len(set(user_ids)) > 1  # Should have different user IDs
        assert len(set(language_codes)) > 1  # Should have different language codes
        assert priorities == [1, 2, 3]  # Should have sequential priorities

    def test_model_serialization_round_trip(self):
        """Test model serialization and deserialization."""
        original = UserLanguagePreferenceFactory.build(
            user_id="serialize_test_user",
            language_code="zh-CN",
            preference_type=LanguagePreferenceType.LEARNING,
            priority=2,
        )

        # Serialize to dict
        data = original.model_dump()

        # Deserialize back to model
        restored = UserLanguagePreference.model_validate(data)

        assert original.user_id == restored.user_id
        assert original.language_code == restored.language_code
        assert original.preference_type == restored.preference_type
        assert original.priority == restored.priority
        assert original.created_at == restored.created_at

    def test_factory_inheritance_behavior(self):
        """Test that factories properly handle model inheritance."""
        base_preference = UserLanguagePreferenceBaseFactory.build()
        create_preference = UserLanguagePreferenceCreateFactory.build()
        full_preference = UserLanguagePreferenceFactory.build()

        # All should have the core attributes
        for pref in [base_preference, create_preference, full_preference]:
            assert hasattr(pref, "user_id")
            assert hasattr(pref, "language_code")
            assert hasattr(pref, "preference_type")
            assert hasattr(pref, "priority")

        # Only full preference should have timestamps
        assert hasattr(full_preference, "created_at")
        assert not hasattr(base_preference, "created_at")
        assert not hasattr(create_preference, "created_at")


class TestValidationEdgeCases:
    """Test edge cases and validation scenarios."""

    def test_none_values_handling(self):
        """Test handling of None values in optional fields."""
        preference = UserLanguagePreferenceBaseFactory.build(learning_goal=None)

        assert preference.learning_goal is None

    def test_boundary_values(self):
        """Test boundary values for validation."""
        # Test minimum valid values
        min_preference = UserLanguagePreferenceBaseFactory.build(
            user_id="u",  # Min length (1 char)
            language_code="en",  # Min valid language code
            priority=1,  # Min priority
        )
        assert len(min_preference.user_id) == 1
        assert len(min_preference.language_code) == 2
        assert min_preference.priority == 1

        # Test maximum valid values
        max_preference = UserLanguagePreferenceBaseFactory.build(
            user_id="a" * 100,  # Long user ID
            language_code="zh-CN",  # Valid complex language code
            priority=100,  # High priority
        )
        assert len(max_preference.user_id) == 100
        assert max_preference.language_code == "zh-CN"
        assert max_preference.priority == 100

    def test_model_config_validation(self):
        """Test model configuration validation behaviors."""
        preference = UserLanguagePreferenceFactory.build()

        # Test validate_assignment works
        preference.priority = 5
        assert preference.priority == 5

        # Test that invalid assignment raises validation error
        with pytest.raises(ValidationError):
            preference.priority = -1  # Invalid negative priority

    def test_field_validator_edge_cases(self):
        """Test field validator edge cases."""
        # Test user_id validator with whitespace
        preference1 = UserLanguagePreferenceBaseFactory.build(user_id="  test_user  ")
        assert preference1.user_id == "test_user"  # Should be trimmed

        # Test language_code validator case normalization
        preference2 = UserLanguagePreferenceBaseFactory.build(language_code="en-US")
        assert preference2.language_code == "en-US"

    def test_enum_validation(self):
        """Test enum validation for preference types."""
        # Test with string values
        preference1 = UserLanguagePreferenceBaseFactory.build(preference_type="fluent")
        assert preference1.preference_type == LanguagePreferenceType.FLUENT

        preference2 = UserLanguagePreferenceBaseFactory.build(
            preference_type="learning"
        )
        assert preference2.preference_type == LanguagePreferenceType.LEARNING

        preference3 = UserLanguagePreferenceBaseFactory.build(preference_type="curious")
        assert preference3.preference_type == LanguagePreferenceType.CURIOUS

        preference4 = UserLanguagePreferenceBaseFactory.build(preference_type="exclude")
        assert preference4.preference_type == LanguagePreferenceType.EXCLUDE

        # Test with enum values
        preference5 = UserLanguagePreferenceBaseFactory.build(
            preference_type=LanguagePreferenceType.FLUENT
        )
        assert preference5.preference_type == LanguagePreferenceType.FLUENT

    def test_language_code_validation_specifics(self):
        """Test specific language code validation scenarios."""
        # Test various valid formats
        test_cases = [
            ("en", "en"),
            ("en-US", "en-US"),
            ("zh-CN", "zh-CN"),
            ("pt-BR", "pt-BR"),
        ]

        for input_code, expected_code in test_cases:
            preference = UserLanguagePreferenceBaseFactory.build(
                language_code=input_code
            )
            assert preference.language_code == expected_code

    def test_learning_scenarios(self):
        """Test different learning scenarios and use cases."""
        # Fluent speaker - native language
        fluent_pref = UserLanguagePreferenceBaseFactory.build(
            language_code="en-US",
            preference_type=LanguagePreferenceType.FLUENT,
            priority=1,
            auto_download_transcripts=False,
            learning_goal=None,
        )
        assert fluent_pref.preference_type == LanguagePreferenceType.FLUENT
        assert fluent_pref.priority == 1

        # Learning language - high priority
        learning_pref = UserLanguagePreferenceBaseFactory.build(
            language_code="es",
            preference_type=LanguagePreferenceType.LEARNING,
            priority=2,
            auto_download_transcripts=True,
            learning_goal="Achieve conversational fluency in Spanish",
        )
        assert learning_pref.preference_type == LanguagePreferenceType.LEARNING
        assert learning_pref.auto_download_transcripts is True

        # Curious about language - lower priority
        curious_pref = UserLanguagePreferenceBaseFactory.build(
            language_code="ja",
            preference_type=LanguagePreferenceType.CURIOUS,
            priority=5,
            auto_download_transcripts=False,
            learning_goal="Explore Japanese culture through media",
        )
        assert curious_pref.preference_type == LanguagePreferenceType.CURIOUS
        assert curious_pref.priority == 5

        # Exclude language - no transcripts
        exclude_pref = UserLanguagePreferenceBaseFactory.build(
            language_code="ar",  # Arabic language code
            preference_type=LanguagePreferenceType.EXCLUDE,
            priority=999,
            auto_download_transcripts=False,
            learning_goal=None,
        )
        assert exclude_pref.preference_type == LanguagePreferenceType.EXCLUDE
        assert exclude_pref.auto_download_transcripts is False

    def test_priority_ordering_logic(self):
        """Test priority-based ordering scenarios."""
        # Create preferences with different priorities
        prefs = [
            UserLanguagePreferenceBaseFactory.build(priority=3, language_code="fr"),
            UserLanguagePreferenceBaseFactory.build(priority=1, language_code="en"),
            UserLanguagePreferenceBaseFactory.build(priority=2, language_code="es"),
        ]

        # Sort by priority (ascending = higher priority first)
        sorted_prefs = sorted(prefs, key=lambda p: p.priority)

        assert sorted_prefs[0].priority == 1  # Highest priority
        assert sorted_prefs[1].priority == 2
        assert sorted_prefs[2].priority == 3  # Lowest priority

        assert sorted_prefs[0].language_code == "en"
        assert sorted_prefs[1].language_code == "es"
        assert sorted_prefs[2].language_code == "fr"
