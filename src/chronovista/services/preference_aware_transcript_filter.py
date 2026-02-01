"""
Preference-aware transcript filtering service.

Filters available transcripts based on user language preferences,
implementing the FLUENT/LEARNING/CURIOUS/EXCLUDE hierarchy.

This service is a core component of US9 (Multi-Fluent Download) that
ensures transcripts are downloaded according to the user's preference
configuration:
- FLUENT: Download ALL matching transcripts automatically
- LEARNING: Download original + pair with translation target
- CURIOUS: Skip automatic download (on-demand only)
- EXCLUDE: Never download
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from ..models.enums import LanguageCode, LanguagePreferenceType
from ..models.user_language_preference import UserLanguagePreference

logger = logging.getLogger(__name__)


@dataclass
class DownloadPlan:
    """
    Plan for which transcripts to download.

    This dataclass captures the result of filtering available transcripts
    against user preferences, providing a clear breakdown of what will
    be downloaded and what will be skipped.

    Attributes
    ----------
    fluent_downloads : List[str]
        Language codes to download directly (FLUENT preferences)
    learning_pairs : List[Tuple[str, Optional[str]]]
        Tuples of (original_lang, translation_target) for LEARNING preferences.
        translation_target is None if translation to top fluent language is
        not available.
    skipped_curious : List[str]
        Languages skipped because they're CURIOUS (on-demand only)
    blocked_excluded : List[str]
        Languages blocked because they're EXCLUDE (never download)
    """

    fluent_downloads: List[str]
    learning_pairs: List[Tuple[str, Optional[str]]]
    skipped_curious: List[str]
    blocked_excluded: List[str]


class PreferenceAwareTranscriptFilter:
    """
    Filters available transcripts based on user language preferences.

    Implements FR-014 through FR-018 from the feature specification:
    - FLUENT: Download ALL matching transcripts
    - LEARNING: Download original + translation to top fluent language
    - CURIOUS: Skip (on-demand only)
    - EXCLUDE: Never download

    Examples
    --------
    >>> filter_service = PreferenceAwareTranscriptFilter()
    >>> # Create some preferences (normally from database)
    >>> from datetime import datetime, timezone
    >>> from chronovista.models.enums import LanguageCode, LanguagePreferenceType
    >>> from chronovista.models.user_language_preference import UserLanguagePreference
    >>> prefs = [
    ...     UserLanguagePreference(
    ...         user_id="user_123",
    ...         language_code=LanguageCode.ENGLISH,
    ...         preference_type=LanguagePreferenceType.FLUENT,
    ...         priority=1,
    ...         auto_download_transcripts=True,
    ...         created_at=datetime.now(timezone.utc),
    ...     )
    ... ]
    >>> plan = filter_service.create_download_plan(["en", "es", "fr"], prefs)
    >>> plan.fluent_downloads
    ['en']
    """

    def __init__(self) -> None:
        """Initialize the filter."""
        pass

    def create_download_plan(
        self,
        available_languages: List[str],
        user_preferences: List[UserLanguagePreference],
    ) -> DownloadPlan:
        """
        Create a download plan based on available languages and preferences.

        Parameters
        ----------
        available_languages : List[str]
            Languages available for download from YouTube
        user_preferences : List[UserLanguagePreference]
            User's configured language preferences

        Returns
        -------
        DownloadPlan
            Plan specifying which transcripts to download
        """
        # Group preferences by type
        fluent = [
            p
            for p in user_preferences
            if p.preference_type == LanguagePreferenceType.FLUENT.value
        ]
        learning = [
            p
            for p in user_preferences
            if p.preference_type == LanguagePreferenceType.LEARNING.value
        ]
        curious = [
            p
            for p in user_preferences
            if p.preference_type == LanguagePreferenceType.CURIOUS.value
        ]
        excluded = [
            p
            for p in user_preferences
            if p.preference_type == LanguagePreferenceType.EXCLUDE.value
        ]

        # Get language codes from preferences
        fluent_codes = self._get_language_codes(fluent)
        learning_codes = self._get_language_codes(learning)
        curious_codes = self._get_language_codes(curious)
        excluded_codes = self._get_language_codes(excluded)

        # Build plan
        plan = DownloadPlan(
            fluent_downloads=[],
            learning_pairs=[],
            skipped_curious=[],
            blocked_excluded=[],
        )

        # FLUENT: Download all matching
        for lang in available_languages:
            if self._matches_preference(lang, fluent_codes):
                plan.fluent_downloads.append(lang)

        # LEARNING: Original + translation (get top fluent as translation target)
        for lang in available_languages:
            if self._matches_preference(lang, learning_codes):
                # Get translation pair (original, translation_target)
                # translation_target may be None if not available
                pair = self.get_translation_pair(lang, available_languages, fluent)
                plan.learning_pairs.append(pair)

        # CURIOUS: Skip
        for lang in available_languages:
            if self._matches_preference(lang, curious_codes):
                plan.skipped_curious.append(lang)

        # EXCLUDE: Block
        for lang in available_languages:
            if self._matches_preference(lang, excluded_codes):
                plan.blocked_excluded.append(lang)

        return plan

    def _get_language_codes(
        self, preferences: List[UserLanguagePreference]
    ) -> Set[str]:
        """
        Extract language codes from preferences.

        Parameters
        ----------
        preferences : List[UserLanguagePreference]
            List of user preferences

        Returns
        -------
        Set[str]
            Set of language code strings
        """
        codes: Set[str] = set()
        for pref in preferences:
            # language_code is already a string due to use_enum_values=True
            # in the Pydantic model configuration
            lang_code = str(pref.language_code)
            codes.add(lang_code)
        return codes

    def _matches_preference(self, lang: str, pref_codes: Set[str]) -> bool:
        """
        Check if a language matches any preference (including base matching).

        This implements variant matching where:
        - A preference for 'en' matches 'en', 'en-US', 'en-GB', etc.
        - A preference for 'en-US' matches 'en', 'en-US', 'en-GB', etc.
          (because they share the same base language)

        Parameters
        ----------
        lang : str
            The available language code to check
        pref_codes : Set[str]
            Set of preference language codes

        Returns
        -------
        bool
            True if the language matches any preference
        """
        if not pref_codes:
            return False

        # Direct match
        if lang in pref_codes:
            return True

        # Get base language of the available language
        base_lang = LanguageCode.get_base_language(lang)

        # Check if base language matches any preference
        if base_lang in pref_codes:
            return True

        # Check if any preference's base language matches the available language's base
        pref_bases = {LanguageCode.get_base_language(code) for code in pref_codes}
        return base_lang in pref_bases

    def get_top_fluent_language(
        self, fluent_prefs: List[UserLanguagePreference]
    ) -> Optional[str]:
        """
        Get highest priority fluent language.

        Parameters
        ----------
        fluent_prefs : List[UserLanguagePreference]
            List of fluent language preferences

        Returns
        -------
        Optional[str]
            The language code of the highest priority fluent language,
            or None if no fluent preferences exist
        """
        if not fluent_prefs:
            return None

        # Sort by priority (lower number = higher priority)
        sorted_prefs = sorted(fluent_prefs, key=lambda p: p.priority)

        # language_code is already a string due to use_enum_values=True
        # in the Pydantic model configuration
        return str(sorted_prefs[0].language_code)

    def get_translation_pair(
        self,
        learning_lang: str,
        available_languages: List[str],
        fluent_prefs: List[UserLanguagePreference],
    ) -> Tuple[str, Optional[str]]:
        """
        Get translation pair for a learning language.

        For LEARNING languages, we want to download both the original transcript
        and a translation to the user's top fluent language (if available).

        Parameters
        ----------
        learning_lang : str
            The learning language code (original transcript)
        available_languages : List[str]
            Languages available for download from YouTube
        fluent_prefs : List[UserLanguagePreference]
            List of fluent language preferences (to determine translation target)

        Returns
        -------
        Tuple[str, Optional[str]]
            Tuple of (original_lang, translation_target) where translation_target
            is None if translation is not available or no fluent preferences exist.
        """
        top_fluent = self.get_top_fluent_language(fluent_prefs)
        if not top_fluent:
            return (learning_lang, None)

        # Check if translation to top fluent language is available
        # Translation is available if the top fluent language (or a variant) is
        # in the available languages
        if self._matches_any_variant(top_fluent, available_languages):
            return (learning_lang, top_fluent)

        # Translation not available - log at INFO level per FR-016
        logger.info(
            f"Translation to {top_fluent} not available for {learning_lang}, "
            "downloading original only"
        )
        return (learning_lang, None)

    def _matches_any_variant(
        self, target_lang: str, available_languages: List[str]
    ) -> bool:
        """
        Check if target language (or any variant) is in available languages.

        Parameters
        ----------
        target_lang : str
            The target language code to find
        available_languages : List[str]
            List of available language codes

        Returns
        -------
        bool
            True if target language or any variant is available
        """
        if not available_languages:
            return False

        # Direct match
        if target_lang in available_languages:
            return True

        # Get base language of target
        target_base = LanguageCode.get_base_language(target_lang)

        # Check if any available language shares the same base
        for avail_lang in available_languages:
            avail_base = LanguageCode.get_base_language(avail_lang)
            if avail_base == target_base:
                return True

        return False

    def get_download_languages(
        self,
        available_languages: List[str],
        user_preferences: List[UserLanguagePreference],
    ) -> List[str]:
        """
        Get list of languages to download (simplified interface).

        Returns languages from FLUENT and LEARNING preferences only.
        Excludes CURIOUS and EXCLUDE languages.

        Parameters
        ----------
        available_languages : List[str]
            Languages available for download from YouTube
        user_preferences : List[UserLanguagePreference]
            User's configured language preferences

        Returns
        -------
        List[str]
            List of language codes to download
        """
        plan = self.create_download_plan(available_languages, user_preferences)

        # Start with fluent downloads
        result = list(plan.fluent_downloads)

        # Add learning language originals (not already included)
        for original, _ in plan.learning_pairs:
            if original not in result:
                result.append(original)

        return result
