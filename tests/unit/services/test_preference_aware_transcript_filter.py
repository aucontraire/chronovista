"""
Tests for PreferenceAwareTranscriptFilter service.

Comprehensive test coverage for preference-aware transcript filtering
that implements the FLUENT/LEARNING/CURIOUS/EXCLUDE hierarchy.
"""

from datetime import datetime, timezone
from typing import List

import pytest

from chronovista.models.enums import LanguageCode, LanguagePreferenceType
from chronovista.models.user_language_preference import UserLanguagePreference
from chronovista.services.preference_aware_transcript_filter import (
    DownloadPlan,
    PreferenceAwareTranscriptFilter,
)


class TestDownloadPlan:
    """Tests for DownloadPlan dataclass."""

    def test_download_plan_creation(self):
        """Test DownloadPlan can be created with all fields."""
        plan = DownloadPlan(
            fluent_downloads=["en", "es"],
            learning_pairs=[("ja", "en")],
            skipped_curious=["fr"],
            blocked_excluded=["de"],
        )

        assert plan.fluent_downloads == ["en", "es"]
        assert plan.learning_pairs == [("ja", "en")]
        assert plan.skipped_curious == ["fr"]
        assert plan.blocked_excluded == ["de"]

    def test_download_plan_empty_lists(self):
        """Test DownloadPlan with empty lists."""
        plan = DownloadPlan(
            fluent_downloads=[],
            learning_pairs=[],
            skipped_curious=[],
            blocked_excluded=[],
        )

        assert plan.fluent_downloads == []
        assert plan.learning_pairs == []
        assert plan.skipped_curious == []
        assert plan.blocked_excluded == []


class TestPreferenceAwareTranscriptFilterInit:
    """Tests for PreferenceAwareTranscriptFilter initialization."""

    def test_init_creates_filter(self):
        """Test filter can be initialized."""
        filter_service = PreferenceAwareTranscriptFilter()
        assert filter_service is not None


class TestPreferenceAwareTranscriptFilterFluentDownloads:
    """Tests for FLUENT preference behavior (T091)."""

    @pytest.fixture
    def filter_service(self) -> PreferenceAwareTranscriptFilter:
        """Create filter service for testing."""
        return PreferenceAwareTranscriptFilter()

    @pytest.fixture
    def fluent_en_es_preferences(self) -> List[UserLanguagePreference]:
        """Create fluent preferences for English and Spanish."""
        now = datetime.now(timezone.utc)
        return [
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                created_at=now,
            ),
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.SPANISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=2,
                auto_download_transcripts=True,
                created_at=now,
            ),
        ]

    def test_fluent_downloads_all_matching(
        self, filter_service: PreferenceAwareTranscriptFilter, fluent_en_es_preferences
    ):
        """T091: FLUENT preferences download ALL matching transcripts."""
        available = ["en", "es", "fr", "de"]

        plan = filter_service.create_download_plan(available, fluent_en_es_preferences)

        # Both en and es should be in fluent downloads
        assert "en" in plan.fluent_downloads
        assert "es" in plan.fluent_downloads
        # Non-matching languages should not be downloaded
        assert "fr" not in plan.fluent_downloads
        assert "de" not in plan.fluent_downloads

    def test_fluent_downloads_variant_matching(
        self, filter_service: PreferenceAwareTranscriptFilter, fluent_en_es_preferences
    ):
        """T091: FLUENT matches language variants (en-US matches en)."""
        available = ["en-US", "en-GB", "es-MX", "fr"]

        plan = filter_service.create_download_plan(available, fluent_en_es_preferences)

        # Variants should match base language preferences
        assert "en-US" in plan.fluent_downloads
        assert "en-GB" in plan.fluent_downloads
        assert "es-MX" in plan.fluent_downloads
        assert "fr" not in plan.fluent_downloads

    def test_fluent_downloads_no_duplicates(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """T091: FLUENT downloads should not have duplicates."""
        now = datetime.now(timezone.utc)
        prefs = [
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                created_at=now,
            ),
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.ENGLISH_US,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=2,
                auto_download_transcripts=True,
                created_at=now,
            ),
        ]

        available = ["en", "en-US"]
        plan = filter_service.create_download_plan(available, prefs)

        # Both should be downloaded since they're both available
        assert "en" in plan.fluent_downloads
        assert "en-US" in plan.fluent_downloads
        # No duplicates
        assert len(plan.fluent_downloads) == 2


class TestPreferenceAwareTranscriptFilterExcluded:
    """Tests for EXCLUDE preference behavior (T092)."""

    @pytest.fixture
    def filter_service(self) -> PreferenceAwareTranscriptFilter:
        """Create filter service for testing."""
        return PreferenceAwareTranscriptFilter()

    @pytest.fixture
    def excluded_preferences(self) -> List[UserLanguagePreference]:
        """Create excluded preferences for German and Russian."""
        now = datetime.now(timezone.utc)
        return [
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.GERMAN,
                preference_type=LanguagePreferenceType.EXCLUDE,
                priority=1,
                auto_download_transcripts=False,
                created_at=now,
            ),
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.RUSSIAN,
                preference_type=LanguagePreferenceType.EXCLUDE,
                priority=2,
                auto_download_transcripts=False,
                created_at=now,
            ),
        ]

    def test_excluded_languages_blocked(
        self, filter_service: PreferenceAwareTranscriptFilter, excluded_preferences
    ):
        """T092: EXCLUDE preferences block all matching transcripts."""
        available = ["en", "de", "ru", "fr"]

        plan = filter_service.create_download_plan(available, excluded_preferences)

        # Excluded languages should be blocked
        assert "de" in plan.blocked_excluded
        assert "ru" in plan.blocked_excluded
        # Non-excluded languages should not be blocked
        assert "en" not in plan.blocked_excluded
        assert "fr" not in plan.blocked_excluded

    def test_excluded_variant_matching(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """T092: EXCLUDE matches language variants."""
        now = datetime.now(timezone.utc)
        prefs = [
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.GERMAN,
                preference_type=LanguagePreferenceType.EXCLUDE,
                priority=1,
                auto_download_transcripts=False,
                created_at=now,
            ),
        ]

        available = ["de", "de-DE", "de-AT", "en"]
        plan = filter_service.create_download_plan(available, prefs)

        # All German variants should be blocked
        assert "de" in plan.blocked_excluded
        assert "de-DE" in plan.blocked_excluded
        assert "de-AT" in plan.blocked_excluded
        assert "en" not in plan.blocked_excluded


class TestPreferenceAwareTranscriptFilterCurious:
    """Tests for CURIOUS preference behavior (T093)."""

    @pytest.fixture
    def filter_service(self) -> PreferenceAwareTranscriptFilter:
        """Create filter service for testing."""
        return PreferenceAwareTranscriptFilter()

    @pytest.fixture
    def curious_preferences(self) -> List[UserLanguagePreference]:
        """Create curious preferences for Japanese and Korean."""
        now = datetime.now(timezone.utc)
        return [
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.JAPANESE,
                preference_type=LanguagePreferenceType.CURIOUS,
                priority=1,
                auto_download_transcripts=False,
                created_at=now,
            ),
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.KOREAN,
                preference_type=LanguagePreferenceType.CURIOUS,
                priority=2,
                auto_download_transcripts=False,
                created_at=now,
            ),
        ]

    def test_curious_languages_skipped(
        self, filter_service: PreferenceAwareTranscriptFilter, curious_preferences
    ):
        """T093: CURIOUS preferences skip transcripts (on-demand only)."""
        available = ["en", "ja", "ko", "fr"]

        plan = filter_service.create_download_plan(available, curious_preferences)

        # Curious languages should be skipped (not auto-downloaded)
        assert "ja" in plan.skipped_curious
        assert "ko" in plan.skipped_curious
        # They should NOT be in fluent downloads
        assert "ja" not in plan.fluent_downloads
        assert "ko" not in plan.fluent_downloads

    def test_curious_not_in_download_languages(
        self, filter_service: PreferenceAwareTranscriptFilter, curious_preferences
    ):
        """T093: CURIOUS languages are NOT included in get_download_languages()."""
        available = ["en", "ja", "ko", "fr"]

        result = filter_service.get_download_languages(available, curious_preferences)

        # Curious languages should not be downloaded automatically
        assert "ja" not in result
        assert "ko" not in result


class TestPreferenceAwareTranscriptFilterNoPreferences:
    """Tests for behavior with no preferences (T094)."""

    @pytest.fixture
    def filter_service(self) -> PreferenceAwareTranscriptFilter:
        """Create filter service for testing."""
        return PreferenceAwareTranscriptFilter()

    def test_no_preferences_returns_empty_plan(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """T094: No preferences returns empty download lists."""
        available = ["en", "es", "fr", "de"]

        plan = filter_service.create_download_plan(available, [])

        # All lists should be empty with no preferences
        assert plan.fluent_downloads == []
        assert plan.learning_pairs == []
        assert plan.skipped_curious == []
        assert plan.blocked_excluded == []

    def test_no_preferences_get_download_languages_empty(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """T094: get_download_languages returns empty with no preferences."""
        available = ["en", "es", "fr"]

        result = filter_service.get_download_languages(available, [])

        assert result == []


class TestPreferenceAwareTranscriptFilterDownloadSummary:
    """Tests for download summary structure (T095)."""

    @pytest.fixture
    def filter_service(self) -> PreferenceAwareTranscriptFilter:
        """Create filter service for testing."""
        return PreferenceAwareTranscriptFilter()

    @pytest.fixture
    def mixed_preferences(self) -> List[UserLanguagePreference]:
        """Create mixed preferences covering all types."""
        now = datetime.now(timezone.utc)
        return [
            # Fluent: English (priority 1)
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                created_at=now,
            ),
            # Fluent: Spanish (priority 2)
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.SPANISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=2,
                auto_download_transcripts=True,
                created_at=now,
            ),
            # Learning: Japanese
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.JAPANESE,
                preference_type=LanguagePreferenceType.LEARNING,
                priority=1,
                auto_download_transcripts=True,
                learning_goal="JLPT N3 by 2025",
                created_at=now,
            ),
            # Curious: Korean
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.KOREAN,
                preference_type=LanguagePreferenceType.CURIOUS,
                priority=1,
                auto_download_transcripts=False,
                created_at=now,
            ),
            # Exclude: Russian
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.RUSSIAN,
                preference_type=LanguagePreferenceType.EXCLUDE,
                priority=1,
                auto_download_transcripts=False,
                created_at=now,
            ),
        ]

    def test_download_summary_structure(
        self, filter_service: PreferenceAwareTranscriptFilter, mixed_preferences
    ):
        """T095: Download plan contains proper summary breakdown."""
        available = ["en", "es", "ja", "ko", "ru", "fr"]

        plan = filter_service.create_download_plan(available, mixed_preferences)

        # Verify structure contains expected categories
        assert hasattr(plan, "fluent_downloads")
        assert hasattr(plan, "learning_pairs")
        assert hasattr(plan, "skipped_curious")
        assert hasattr(plan, "blocked_excluded")

        # Verify proper categorization
        assert "en" in plan.fluent_downloads
        assert "es" in plan.fluent_downloads
        assert ("ja", "en") in plan.learning_pairs  # Learning with translation target
        assert "ko" in plan.skipped_curious
        assert "ru" in plan.blocked_excluded

        # Uncategorized language (fr) should not appear anywhere
        assert "fr" not in plan.fluent_downloads
        assert "fr" not in plan.skipped_curious
        assert "fr" not in plan.blocked_excluded

    def test_download_summary_counts(
        self, filter_service: PreferenceAwareTranscriptFilter, mixed_preferences
    ):
        """T095: Summary provides accurate counts for each category."""
        available = ["en", "es", "ja", "ko", "ru"]

        plan = filter_service.create_download_plan(available, mixed_preferences)

        assert len(plan.fluent_downloads) == 2  # en, es
        assert len(plan.learning_pairs) == 1  # ja
        assert len(plan.skipped_curious) == 1  # ko
        assert len(plan.blocked_excluded) == 1  # ru


class TestPreferenceAwareTranscriptFilterLearning:
    """Tests for LEARNING preference behavior."""

    @pytest.fixture
    def filter_service(self) -> PreferenceAwareTranscriptFilter:
        """Create filter service for testing."""
        return PreferenceAwareTranscriptFilter()

    @pytest.fixture
    def learning_with_fluent(self) -> List[UserLanguagePreference]:
        """Create learning preferences with fluent target language."""
        now = datetime.now(timezone.utc)
        return [
            # Fluent: English (translation target)
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                created_at=now,
            ),
            # Learning: Japanese
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.JAPANESE,
                preference_type=LanguagePreferenceType.LEARNING,
                priority=1,
                auto_download_transcripts=True,
                learning_goal="Learn Japanese",
                created_at=now,
            ),
        ]

    def test_learning_creates_translation_pair(
        self, filter_service: PreferenceAwareTranscriptFilter, learning_with_fluent
    ):
        """LEARNING creates a pair with the top fluent language."""
        available = ["ja", "en", "fr"]

        plan = filter_service.create_download_plan(available, learning_with_fluent)

        # Learning language should create pair with top fluent
        assert ("ja", "en") in plan.learning_pairs
        # Fluent language should still be in fluent downloads
        assert "en" in plan.fluent_downloads

    def test_learning_included_in_download_languages(
        self, filter_service: PreferenceAwareTranscriptFilter, learning_with_fluent
    ):
        """LEARNING languages ARE included in get_download_languages()."""
        available = ["ja", "en", "fr"]

        result = filter_service.get_download_languages(available, learning_with_fluent)

        # Both fluent and learning should be included
        assert "en" in result
        assert "ja" in result

    def test_learning_without_fluent_no_translation_target(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """LEARNING without any fluent preference has no translation target."""
        now = datetime.now(timezone.utc)
        prefs = [
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.JAPANESE,
                preference_type=LanguagePreferenceType.LEARNING,
                priority=1,
                auto_download_transcripts=True,
                created_at=now,
            ),
        ]

        available = ["ja", "en", "fr"]
        plan = filter_service.create_download_plan(available, prefs)

        # Learning pair is created but with None translation target (no fluent language)
        assert len(plan.learning_pairs) == 1
        assert plan.learning_pairs[0] == ("ja", None)


class TestPreferenceAwareTranscriptFilterGetTopFluent:
    """Tests for get_top_fluent_language method."""

    @pytest.fixture
    def filter_service(self) -> PreferenceAwareTranscriptFilter:
        """Create filter service for testing."""
        return PreferenceAwareTranscriptFilter()

    def test_get_top_fluent_respects_priority(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """Top fluent language respects priority ordering."""
        now = datetime.now(timezone.utc)
        prefs = [
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.SPANISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=2,  # Lower priority
                auto_download_transcripts=True,
                created_at=now,
            ),
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,  # Higher priority
                auto_download_transcripts=True,
                created_at=now,
            ),
        ]

        result = filter_service.get_top_fluent_language(prefs)

        # Should return English (priority 1)
        assert result == "en"

    def test_get_top_fluent_empty_list(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """Empty fluent list returns None."""
        result = filter_service.get_top_fluent_language([])
        assert result is None


class TestPreferenceAwareTranscriptFilterGetDownloadLanguages:
    """Tests for get_download_languages method."""

    @pytest.fixture
    def filter_service(self) -> PreferenceAwareTranscriptFilter:
        """Create filter service for testing."""
        return PreferenceAwareTranscriptFilter()

    def test_get_download_languages_fluent_only(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """get_download_languages includes only fluent and learning."""
        now = datetime.now(timezone.utc)
        prefs = [
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                created_at=now,
            ),
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.JAPANESE,
                preference_type=LanguagePreferenceType.LEARNING,
                priority=1,
                auto_download_transcripts=True,
                created_at=now,
            ),
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.KOREAN,
                preference_type=LanguagePreferenceType.CURIOUS,
                priority=1,
                auto_download_transcripts=False,
                created_at=now,
            ),
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.RUSSIAN,
                preference_type=LanguagePreferenceType.EXCLUDE,
                priority=1,
                auto_download_transcripts=False,
                created_at=now,
            ),
        ]

        available = ["en", "ja", "ko", "ru"]
        result = filter_service.get_download_languages(available, prefs)

        # Only fluent and learning should be included
        assert "en" in result
        assert "ja" in result
        # Curious and exclude should NOT be included
        assert "ko" not in result
        assert "ru" not in result


class TestPreferenceAwareTranscriptFilterEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.fixture
    def filter_service(self) -> PreferenceAwareTranscriptFilter:
        """Create filter service for testing."""
        return PreferenceAwareTranscriptFilter()

    def test_language_in_multiple_categories_not_possible(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """A language can only be in one preference category per user."""
        now = datetime.now(timezone.utc)
        # In real usage, the same language wouldn't be in multiple categories
        # This test verifies the filter handles a single language preference correctly
        prefs = [
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                created_at=now,
            ),
        ]

        available = ["en"]
        plan = filter_service.create_download_plan(available, prefs)

        # English should only be in fluent
        assert "en" in plan.fluent_downloads
        assert "en" not in plan.blocked_excluded
        assert "en" not in plan.skipped_curious

    def test_unavailable_language_not_in_plan(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """Languages not in available list are not in the plan."""
        now = datetime.now(timezone.utc)
        prefs = [
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                created_at=now,
            ),
        ]

        # English is NOT available
        available = ["es", "fr", "de"]
        plan = filter_service.create_download_plan(available, prefs)

        # English should not be in fluent downloads since it's not available
        assert "en" not in plan.fluent_downloads
        assert plan.fluent_downloads == []

    def test_base_language_preference_matches_variant(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """Base language preference (e.g., 'en') matches variants (e.g., 'en-US')."""
        now = datetime.now(timezone.utc)
        prefs = [
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.ENGLISH,  # Base 'en'
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                created_at=now,
            ),
        ]

        available = ["en-US", "en-GB", "en-AU"]
        plan = filter_service.create_download_plan(available, prefs)

        # All English variants should match the base 'en' preference
        assert "en-US" in plan.fluent_downloads
        assert "en-GB" in plan.fluent_downloads
        assert "en-AU" in plan.fluent_downloads

    def test_variant_preference_matches_base_and_variants(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """Variant preference (e.g., 'en-US') matches base and other variants."""
        now = datetime.now(timezone.utc)
        prefs = [
            UserLanguagePreference(
                user_id="test_user_001",
                language_code=LanguageCode.ENGLISH_US,  # Variant 'en-US'
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                created_at=now,
            ),
        ]

        available = ["en", "en-US", "en-GB"]
        plan = filter_service.create_download_plan(available, prefs)

        # Base and variants should match since they share the same base
        assert "en" in plan.fluent_downloads
        assert "en-US" in plan.fluent_downloads
        assert "en-GB" in plan.fluent_downloads


class TestPreferenceAwareTranscriptFilterLearningTranslationPairing:
    """Tests for LEARNING preference translation pairing behavior (US10: T101-T104)."""

    @pytest.fixture
    def filter_service(self) -> PreferenceAwareTranscriptFilter:
        """Create filter service for testing."""
        return PreferenceAwareTranscriptFilter()

    def _create_pref(
        self,
        lang_code: LanguageCode,
        pref_type: LanguagePreferenceType,
        priority: int = 1,
    ) -> UserLanguagePreference:
        """Helper to create a language preference."""
        now = datetime.now(timezone.utc)
        return UserLanguagePreference(
            user_id="test_user_001",
            language_code=lang_code,
            preference_type=pref_type,
            priority=priority,
            auto_download_transcripts=(pref_type != LanguagePreferenceType.EXCLUDE),
            created_at=now,
        )

    def test_learning_downloads_original(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """T101: Learning language downloads original transcript."""
        prefs = [
            self._create_pref(LanguageCode.ENGLISH, LanguagePreferenceType.FLUENT, 1),
            self._create_pref(LanguageCode.ITALIAN, LanguagePreferenceType.LEARNING, 1),
        ]
        available = ["it", "en", "fr"]

        plan = filter_service.create_download_plan(available, prefs)

        # Learning pair includes Italian original
        assert any(pair[0] == "it" for pair in plan.learning_pairs)

    def test_learning_downloads_translation_when_available(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """T102: Learning downloads translation to top fluent when available."""
        prefs = [
            self._create_pref(LanguageCode.ENGLISH, LanguagePreferenceType.FLUENT, 1),
            self._create_pref(LanguageCode.ITALIAN, LanguagePreferenceType.LEARNING, 1),
        ]
        available = ["it", "en", "fr"]

        plan = filter_service.create_download_plan(available, prefs)

        # Should pair Italian with English translation
        assert ("it", "en") in plan.learning_pairs

    def test_graceful_handling_missing_translation(
        self, filter_service: PreferenceAwareTranscriptFilter, caplog: pytest.LogCaptureFixture
    ):
        """T103: Graceful handling when translation unavailable (INFO log per FR-016)."""
        import logging

        caplog.set_level(logging.INFO)

        prefs = [
            self._create_pref(LanguageCode.ENGLISH, LanguagePreferenceType.FLUENT, 1),
            self._create_pref(LanguageCode.ITALIAN, LanguagePreferenceType.LEARNING, 1),
        ]
        # English NOT in available languages
        available = ["it", "fr", "de"]

        plan = filter_service.create_download_plan(available, prefs)

        # Should still have Italian in plan (original only, no translation)
        assert any(pair[0] == "it" for pair in plan.learning_pairs)
        # Translation target should be None
        it_pair = next(pair for pair in plan.learning_pairs if pair[0] == "it")
        assert it_pair[1] is None
        # Should have logged at INFO level
        assert "Translation to en not available" in caplog.text

    def test_translation_uses_top_priority_fluent(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """T104: Translation target is highest priority fluent language."""
        prefs = [
            self._create_pref(LanguageCode.SPANISH, LanguagePreferenceType.FLUENT, 2),
            self._create_pref(
                LanguageCode.ENGLISH, LanguagePreferenceType.FLUENT, 1
            ),  # Top priority
            self._create_pref(LanguageCode.ITALIAN, LanguagePreferenceType.LEARNING, 1),
        ]
        available = ["it", "en", "es", "fr"]

        plan = filter_service.create_download_plan(available, prefs)

        # Should pair Italian with English (priority 1), not Spanish (priority 2)
        assert ("it", "en") in plan.learning_pairs


class TestPreferenceAwareTranscriptFilterGetTranslationPair:
    """Tests for get_translation_pair method (US10)."""

    @pytest.fixture
    def filter_service(self) -> PreferenceAwareTranscriptFilter:
        """Create filter service for testing."""
        return PreferenceAwareTranscriptFilter()

    def _create_fluent_pref(
        self, lang_code: LanguageCode, priority: int = 1
    ) -> UserLanguagePreference:
        """Helper to create a fluent language preference."""
        now = datetime.now(timezone.utc)
        return UserLanguagePreference(
            user_id="test_user_001",
            language_code=lang_code,
            preference_type=LanguagePreferenceType.FLUENT,
            priority=priority,
            auto_download_transcripts=True,
            created_at=now,
        )

    def test_get_translation_pair_with_available_translation(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """Translation pair includes target when translation is available."""
        fluent_prefs = [
            self._create_fluent_pref(LanguageCode.ENGLISH, 1),
        ]
        available = ["it", "en", "fr"]

        result = filter_service.get_translation_pair("it", available, fluent_prefs)

        assert result == ("it", "en")

    def test_get_translation_pair_without_available_translation(
        self, filter_service: PreferenceAwareTranscriptFilter, caplog: pytest.LogCaptureFixture
    ):
        """Translation pair has None target when translation unavailable."""
        import logging

        caplog.set_level(logging.INFO)

        fluent_prefs = [
            self._create_fluent_pref(LanguageCode.ENGLISH, 1),
        ]
        available = ["it", "fr", "de"]  # No English

        result = filter_service.get_translation_pair("it", available, fluent_prefs)

        assert result == ("it", None)
        assert "Translation to en not available" in caplog.text

    def test_get_translation_pair_no_fluent_prefs(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """Translation pair has None target when no fluent preferences exist."""
        fluent_prefs: List[UserLanguagePreference] = []
        available = ["it", "en", "fr"]

        result = filter_service.get_translation_pair("it", available, fluent_prefs)

        assert result == ("it", None)

    def test_get_translation_pair_uses_top_priority_fluent(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """Translation pair uses highest priority fluent language."""
        fluent_prefs = [
            self._create_fluent_pref(LanguageCode.SPANISH, 2),
            self._create_fluent_pref(LanguageCode.ENGLISH, 1),  # Top priority
        ]
        available = ["it", "en", "es"]

        result = filter_service.get_translation_pair("it", available, fluent_prefs)

        # Should use English (priority 1), not Spanish (priority 2)
        assert result == ("it", "en")

    def test_get_translation_pair_with_language_variant(
        self, filter_service: PreferenceAwareTranscriptFilter
    ):
        """Translation pair matches language variants correctly."""
        fluent_prefs = [
            self._create_fluent_pref(LanguageCode.ENGLISH, 1),
        ]
        # Only en-US available, not base "en"
        available = ["it", "en-US", "fr"]

        result = filter_service.get_translation_pair("it", available, fluent_prefs)

        # Should match en-US as a variant of en
        assert result[0] == "it"
        assert result[1] is not None  # Should find a match
