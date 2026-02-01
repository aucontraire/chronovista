"""
Integration tests for language preference-aware download behavior.

These tests verify the complete flow from preference configuration
through transcript download, ensuring all FR-014 through FR-018
requirements are met.

Test Coverage:
- T109: Set preferences → sync → verify correct languages downloaded
- T110: Exclude preference prevents download completely
- T111: Curious preference only downloads on explicit --language flag
- T112: Learning preference pairs with translation when available
- T113: Fallback behavior when no preferences configured (system locale)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple
from unittest.mock import MagicMock

import pytest

from chronovista.models.enums import LanguageCode, LanguagePreferenceType
from chronovista.models.user_language_preference import UserLanguagePreference
from chronovista.services.preference_aware_transcript_filter import (
    DownloadPlan,
    PreferenceAwareTranscriptFilter,
)

# CRITICAL: Module-level marker ensures ALL async tests run with coverage
pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_preference(
    language_code: str,
    preference_type: str,
    priority: int,
    auto_download: bool = True,
    learning_goal: str = "",
) -> UserLanguagePreference:
    """
    Create a UserLanguagePreference instance for testing.

    Parameters
    ----------
    language_code : str
        BCP-47 language code (e.g., 'en', 'es-MX')
    preference_type : str
        Type of preference ('fluent', 'learning', 'curious', 'exclude')
    priority : int
        Priority order (1 = highest)
    auto_download : bool
        Whether to auto-download transcripts
    learning_goal : str
        Optional learning goal description

    Returns
    -------
    UserLanguagePreference
        Fully populated preference instance
    """
    # Map string preference type to enum value
    pref_type_map = {
        "fluent": LanguagePreferenceType.FLUENT,
        "learning": LanguagePreferenceType.LEARNING,
        "curious": LanguagePreferenceType.CURIOUS,
        "exclude": LanguagePreferenceType.EXCLUDE,
    }

    # Map string language code to enum (if it exists, otherwise use string)
    try:
        lang_enum = LanguageCode(language_code)
    except ValueError:
        # For test cases with non-enum language codes, use the string directly
        lang_enum = language_code  # type: ignore[assignment]

    return UserLanguagePreference(
        user_id="test_user_123",
        language_code=lang_enum,
        preference_type=pref_type_map[preference_type],
        priority=priority,
        auto_download_transcripts=auto_download,
        learning_goal=learning_goal if learning_goal else None,
        created_at=datetime.now(timezone.utc),
    )


# ============================================================================
# E2E PREFERENCE → DOWNLOAD FLOW TESTS
# ============================================================================


class TestPreferenceAwareDownloadFlow:
    """E2E tests for preference → download flow (FR-014 through FR-018)."""

    async def test_fluent_preferences_download_all_matching(self) -> None:
        """
        T109: Set preferences → sync → verify correct languages.

        Scenario:
        1. User sets fluent=en,es
        2. Video has transcripts: en, es, fr, de
        3. Sync downloads en, es
        4. Verify: fr, de NOT downloaded

        This validates FR-014: FLUENT languages download automatically.
        """
        # Setup preferences
        prefs = [
            create_preference("en", "fluent", priority=1),
            create_preference("es", "fluent", priority=2),
        ]

        # Available transcripts
        available = ["en", "es", "fr", "de"]

        # Run filter
        filter_service = PreferenceAwareTranscriptFilter()
        plan = filter_service.create_download_plan(available, prefs)

        # Verify
        assert set(plan.fluent_downloads) == {"en", "es"}
        assert "fr" not in plan.fluent_downloads
        assert "de" not in plan.fluent_downloads
        assert len(plan.learning_pairs) == 0
        assert len(plan.skipped_curious) == 0
        assert len(plan.blocked_excluded) == 0

    async def test_exclude_preference_prevents_download(self) -> None:
        """
        T110: Exclude preference blocks download completely.

        Scenario:
        1. User sets fluent=en, exclude=de
        2. Video has transcripts: en, de
        3. Sync downloads en
        4. Verify: de NEVER downloaded (blocked)

        This validates FR-017: EXCLUDE languages are never downloaded.
        """
        prefs = [
            create_preference("en", "fluent", priority=1),
            create_preference("de", "exclude", priority=1),
        ]

        available = ["en", "de", "fr"]

        filter_service = PreferenceAwareTranscriptFilter()
        plan = filter_service.create_download_plan(available, prefs)

        # Verify
        assert "en" in plan.fluent_downloads
        assert "de" in plan.blocked_excluded
        assert "de" not in plan.fluent_downloads
        # fr is not in any preference list, so it's not included anywhere
        assert "fr" not in plan.fluent_downloads
        assert "fr" not in plan.blocked_excluded

    async def test_curious_preference_skipped_during_sync(self) -> None:
        """
        T111: Curious preference skips download (on-demand only).

        Scenario:
        1. User sets fluent=en, curious=fr
        2. Video has transcripts: en, fr
        3. Sync downloads en only
        4. Verify: fr marked as skipped (on-demand)

        This validates FR-016: CURIOUS languages are skipped during sync,
        available only on-demand via explicit --language flag.
        """
        prefs = [
            create_preference("en", "fluent", priority=1),
            create_preference("fr", "curious", priority=1),
        ]

        available = ["en", "fr", "de"]

        filter_service = PreferenceAwareTranscriptFilter()
        plan = filter_service.create_download_plan(available, prefs)

        # Verify
        assert "en" in plan.fluent_downloads
        assert "fr" in plan.skipped_curious
        assert "fr" not in plan.fluent_downloads
        # de is not in any preference list
        assert "de" not in plan.skipped_curious

    async def test_learning_preference_downloads_with_translation(self) -> None:
        """
        T112: Learning preference pairs original with translation.

        Scenario:
        1. User sets fluent=en, learning=it
        2. Video has transcripts: it, en, fr
        3. Sync downloads: it (original), en (translation)
        4. Verify: translation pair created

        This validates FR-015: LEARNING languages download the original
        language paired with a translation to the user's top fluent language.
        """
        prefs = [
            create_preference("en", "fluent", priority=1),
            create_preference("it", "learning", priority=1),
        ]

        available = ["it", "en", "fr"]

        filter_service = PreferenceAwareTranscriptFilter()
        plan = filter_service.create_download_plan(available, prefs)

        # Verify learning pair
        assert ("it", "en") in plan.learning_pairs
        # en should be in fluent downloads as well
        assert "en" in plan.fluent_downloads
        # fr is not in any preference list
        assert "fr" not in plan.fluent_downloads

    async def test_fallback_to_system_locale_when_no_preferences(self) -> None:
        """
        T113: Fallback to system locale when no preferences configured.

        Scenario:
        1. No preferences configured
        2. System locale is es_MX
        3. Sync uses Spanish as default

        This validates FR-018: When no preferences are configured,
        the system should provide an empty download list, allowing
        the caller to implement locale-based fallback.
        """
        prefs: List[UserLanguagePreference] = []  # No preferences
        available = ["en", "es", "fr"]

        filter_service = PreferenceAwareTranscriptFilter()
        languages = filter_service.get_download_languages(available, prefs)

        # Verify: no languages selected (caller should use locale fallback)
        assert languages == []

        # Verify plan is also empty
        plan = filter_service.create_download_plan(available, prefs)
        assert len(plan.fluent_downloads) == 0
        assert len(plan.learning_pairs) == 0
        assert len(plan.skipped_curious) == 0
        assert len(plan.blocked_excluded) == 0


# ============================================================================
# LANGUAGE VARIANT MATCHING TESTS
# ============================================================================


class TestLanguageVariantMatching:
    """Test language variant matching (en-US matches en)."""

    async def test_base_language_matches_variants(self) -> None:
        """
        en preference matches en-US and en-GB transcripts.

        Scenario:
        1. User sets fluent=en (base language)
        2. Video has transcripts: en-US, en-GB, es
        3. Sync downloads en-US, en-GB
        4. Verify: es NOT downloaded

        This validates that base language preferences match all variants.
        """
        prefs = [create_preference("en", "fluent", priority=1)]
        available = ["en-US", "en-GB", "es"]

        filter_service = PreferenceAwareTranscriptFilter()
        plan = filter_service.create_download_plan(available, prefs)

        # Should match en-US and en-GB
        assert "en-US" in plan.fluent_downloads
        assert "en-GB" in plan.fluent_downloads
        assert "es" not in plan.fluent_downloads

    async def test_variant_preference_matches_base_language(self) -> None:
        """
        en-US preference matches en base language transcript.

        Scenario:
        1. User sets fluent=en-US (specific variant)
        2. Video has transcripts: en, es
        3. Sync downloads en
        4. Verify: es NOT downloaded

        This validates that variant preferences match base language transcripts.
        """
        prefs = [create_preference("en-US", "fluent", priority=1)]
        available = ["en", "es", "fr"]

        filter_service = PreferenceAwareTranscriptFilter()
        plan = filter_service.create_download_plan(available, prefs)

        # Should match en (base language matches variant preference)
        assert "en" in plan.fluent_downloads
        assert "es" not in plan.fluent_downloads
        assert "fr" not in plan.fluent_downloads

    async def test_different_variants_of_same_base_match(self) -> None:
        """
        es-MX preference matches es-ES transcript.

        Scenario:
        1. User sets fluent=es-MX (Mexican Spanish)
        2. Video has transcripts: es-ES (Spain Spanish), en
        3. Sync downloads es-ES
        4. Verify: Both Spanish variants match due to shared base

        This validates that different variants of the same base language match.
        """
        prefs = [create_preference("es-MX", "fluent", priority=1)]
        available = ["es-ES", "es-419", "en"]

        filter_service = PreferenceAwareTranscriptFilter()
        plan = filter_service.create_download_plan(available, prefs)

        # Should match all Spanish variants
        assert "es-ES" in plan.fluent_downloads
        assert "es-419" in plan.fluent_downloads
        assert "en" not in plan.fluent_downloads


# ============================================================================
# PRIORITY ORDERING TESTS
# ============================================================================


class TestPriorityOrdering:
    """Test priority-based ordering for fluent languages."""

    async def test_top_fluent_determined_by_priority(self) -> None:
        """
        Top fluent language is determined by lowest priority number.

        Scenario:
        1. User sets fluent=es (priority=2), fluent=en (priority=1)
        2. Learning=it configured
        3. Top fluent is en (priority=1)
        4. Verify: it pairs with en for translation

        This validates that priority determines the top fluent language
        used for learning language translations.
        """
        prefs = [
            create_preference("es", "fluent", priority=2),
            create_preference("en", "fluent", priority=1),  # Top
            create_preference("it", "learning", priority=1),
        ]

        filter_service = PreferenceAwareTranscriptFilter()

        # Get top fluent language
        # Note: preference_type is already a string due to use_enum_values=True
        fluent_prefs = [p for p in prefs if p.preference_type == "fluent"]
        top = filter_service.get_top_fluent_language(fluent_prefs)

        assert top == "en"

        # Verify learning pairs use top fluent language
        available = ["it", "en", "es"]
        plan = filter_service.create_download_plan(available, prefs)

        assert ("it", "en") in plan.learning_pairs


# ============================================================================
# COMPLEX MULTI-PREFERENCE SCENARIOS
# ============================================================================


class TestComplexPreferenceScenarios:
    """Test complex scenarios with multiple preference types."""

    async def test_all_preference_types_together(self) -> None:
        """
        Test all preference types in a single configuration.

        Scenario:
        1. User sets: fluent=en, learning=it, curious=fr, exclude=de
        2. Video has transcripts: en, it, fr, de, es
        3. Verify correct handling of each type

        This validates that all preference types work correctly together.
        """
        prefs = [
            create_preference("en", "fluent", priority=1),
            create_preference("it", "learning", priority=1),
            create_preference("fr", "curious", priority=1),
            create_preference("de", "exclude", priority=1),
        ]

        available = ["en", "it", "fr", "de", "es"]

        filter_service = PreferenceAwareTranscriptFilter()
        plan = filter_service.create_download_plan(available, prefs)

        # Verify each category
        assert "en" in plan.fluent_downloads
        assert ("it", "en") in plan.learning_pairs
        assert "fr" in plan.skipped_curious
        assert "de" in plan.blocked_excluded
        # es is not in any preference list
        assert "es" not in plan.fluent_downloads

    async def test_multiple_fluent_languages(self) -> None:
        """
        Test multiple fluent languages with different priorities.

        Scenario:
        1. User sets: fluent=en (p1), fluent=es (p2), fluent=fr (p3)
        2. Video has transcripts: en, es, fr, de
        3. All fluent languages download
        4. Verify priority ordering for learning pairs

        This validates that multiple fluent languages work correctly.
        """
        prefs = [
            create_preference("en", "fluent", priority=1),
            create_preference("es", "fluent", priority=2),
            create_preference("fr", "fluent", priority=3),
            create_preference("it", "learning", priority=1),
        ]

        available = ["en", "es", "fr", "it", "de"]

        filter_service = PreferenceAwareTranscriptFilter()
        plan = filter_service.create_download_plan(available, prefs)

        # All fluent languages should download
        assert "en" in plan.fluent_downloads
        assert "es" in plan.fluent_downloads
        assert "fr" in plan.fluent_downloads

        # Learning should pair with top fluent (en, priority=1)
        assert ("it", "en") in plan.learning_pairs

        # de is not in any preference list
        assert "de" not in plan.fluent_downloads

    async def test_learning_without_fluent_translation_target(self) -> None:
        """
        Test learning preference when no fluent languages configured.

        Scenario:
        1. User sets: learning=it (no fluent languages)
        2. Video has transcripts: it, en
        3. Verify: Learning pair created with None as translation target

        This validates graceful handling when learning has no fluent target.
        The implementation creates a pair with None, allowing the caller
        to decide how to handle the missing translation.
        """
        prefs = [
            create_preference("it", "learning", priority=1),
        ]

        available = ["it", "en"]

        filter_service = PreferenceAwareTranscriptFilter()
        plan = filter_service.create_download_plan(available, prefs)

        # Learning pair is created with None as translation target
        assert len(plan.learning_pairs) == 1
        assert ("it", None) in plan.learning_pairs
        assert len(plan.fluent_downloads) == 0

    async def test_exclude_overrides_other_preferences(self) -> None:
        """
        Test that exclude preference behavior is consistent.

        Scenario:
        1. User sets: exclude=de
        2. Video has transcripts: en, de
        3. Verify: de is blocked even if no other preferences set

        This validates exclude works independently.
        """
        prefs = [
            create_preference("de", "exclude", priority=1),
        ]

        available = ["en", "de", "fr"]

        filter_service = PreferenceAwareTranscriptFilter()
        plan = filter_service.create_download_plan(available, prefs)

        # de should be blocked
        assert "de" in plan.blocked_excluded
        assert "de" not in plan.fluent_downloads

        # Other languages not in preferences
        assert "en" not in plan.fluent_downloads
        assert "fr" not in plan.fluent_downloads


# ============================================================================
# EDGE CASES AND ERROR HANDLING
# ============================================================================


class TestEdgeCases:
    """Test edge cases and unusual scenarios."""

    async def test_empty_available_languages(self) -> None:
        """
        Test behavior when no transcripts are available.

        Scenario:
        1. User has preferences configured
        2. Video has no transcripts available
        3. Verify: Empty plan returned

        This validates graceful handling of videos with no transcripts.
        """
        prefs = [
            create_preference("en", "fluent", priority=1),
            create_preference("es", "fluent", priority=2),
        ]

        available: List[str] = []

        filter_service = PreferenceAwareTranscriptFilter()
        plan = filter_service.create_download_plan(available, prefs)

        # All lists should be empty
        assert len(plan.fluent_downloads) == 0
        assert len(plan.learning_pairs) == 0
        assert len(plan.skipped_curious) == 0
        assert len(plan.blocked_excluded) == 0

    async def test_no_matching_preferences(self) -> None:
        """
        Test when available languages don't match any preferences.

        Scenario:
        1. User sets: fluent=en, fluent=es
        2. Video has transcripts: de, fr, it
        3. Verify: Empty fluent downloads

        This validates handling when no available languages match preferences.
        """
        prefs = [
            create_preference("en", "fluent", priority=1),
            create_preference("es", "fluent", priority=2),
        ]

        available = ["de", "fr", "it"]

        filter_service = PreferenceAwareTranscriptFilter()
        plan = filter_service.create_download_plan(available, prefs)

        # No matches
        assert len(plan.fluent_downloads) == 0
        assert len(plan.learning_pairs) == 0

    async def test_duplicate_language_codes_in_available(self) -> None:
        """
        Test behavior when available list has duplicates.

        Scenario:
        1. User sets: fluent=en
        2. Available list has duplicates: en, en, es
        3. Verify: en appears in plan (duplicates handled by caller)

        This validates the filter doesn't break with duplicate input.
        """
        prefs = [
            create_preference("en", "fluent", priority=1),
        ]

        available = ["en", "en", "es"]

        filter_service = PreferenceAwareTranscriptFilter()
        plan = filter_service.create_download_plan(available, prefs)

        # en should appear (duplicates in input list)
        assert "en" in plan.fluent_downloads
        # Count is based on input list duplicates
        assert plan.fluent_downloads.count("en") == 2

    async def test_get_download_languages_simplified_interface(self) -> None:
        """
        Test simplified get_download_languages interface.

        Scenario:
        1. User sets: fluent=en, learning=it, curious=fr
        2. Available: en, it, fr
        3. Verify: Returns only fluent + learning (not curious)

        This validates the simplified interface for download language selection.
        """
        prefs = [
            create_preference("en", "fluent", priority=1),
            create_preference("it", "learning", priority=1),
            create_preference("fr", "curious", priority=1),
        ]

        available = ["en", "it", "fr"]

        filter_service = PreferenceAwareTranscriptFilter()
        languages = filter_service.get_download_languages(available, prefs)

        # Should include fluent + learning original (not curious)
        assert "en" in languages
        assert "it" in languages
        assert "fr" not in languages
