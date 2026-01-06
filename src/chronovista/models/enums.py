"""
Enums for chronovista models.

Defines enumeration types used across the application for consistent
type safety and validation.
"""

from __future__ import annotations

from enum import Enum


class LanguagePreferenceType(str, Enum):
    """Language preference types for user content consumption."""

    FLUENT = "fluent"
    LEARNING = "learning"
    CURIOUS = "curious"
    EXCLUDE = "exclude"


class TranscriptType(str, Enum):
    """Types of video transcripts available."""

    AUTO = "auto"
    MANUAL = "manual"
    TRANSLATED = "translated"


class DownloadReason(str, Enum):
    """Reasons for transcript download."""

    USER_REQUEST = "user_request"
    AUTO_PREFERRED = "auto_preferred"
    LEARNING_LANGUAGE = "learning_language"
    API_ENRICHMENT = "api_enrichment"
    SCHEMA_VALIDATION = "schema_validation"


class TrackKind(str, Enum):
    """Types of caption tracks."""

    STANDARD = "standard"
    ASR = "asr"  # Automatic Speech Recognition
    FORCED = "forced"


class PrivacyStatus(str, Enum):
    """Playlist privacy settings."""

    PRIVATE = "private"
    PUBLIC = "public"
    UNLISTED = "unlisted"


class TopicType(str, Enum):
    """Topic classification types."""

    YOUTUBE = "youtube"
    CUSTOM = "custom"


class LanguageCode(str, Enum):
    """BCP-47 language codes for international content.

    Covers the most common language codes used by YouTube and other
    international platforms. Follows BCP-47 standard for language tags.
    """

    # Major English variants
    ENGLISH = "en"
    ENGLISH_US = "en-US"
    ENGLISH_GB = "en-GB"
    ENGLISH_AU = "en-AU"
    ENGLISH_CA = "en-CA"

    # Spanish variants
    SPANISH = "es"
    SPANISH_ES = "es-ES"
    SPANISH_MX = "es-MX"
    SPANISH_AR = "es-AR"
    SPANISH_CO = "es-CO"
    SPANISH_419 = "es-419"  # Latin American Spanish

    # French variants
    FRENCH = "fr"
    FRENCH_FR = "fr-FR"
    FRENCH_CA = "fr-CA"

    # German variants
    GERMAN = "de"
    GERMAN_DE = "de-DE"
    GERMAN_AT = "de-AT"
    GERMAN_CH = "de-CH"

    # Italian
    ITALIAN = "it"
    ITALIAN_IT = "it-IT"

    # Portuguese variants
    PORTUGUESE = "pt"
    PORTUGUESE_PT = "pt-PT"
    PORTUGUESE_BR = "pt-BR"

    # Chinese variants
    CHINESE_SIMPLIFIED = "zh-CN"
    CHINESE_TRADITIONAL = "zh-TW"
    CHINESE_HK = "zh-HK"

    # Japanese
    JAPANESE = "ja"
    JAPANESE_JP = "ja-JP"

    # Korean
    KOREAN = "ko"
    KOREAN_KR = "ko-KR"

    # Russian
    RUSSIAN = "ru"
    RUSSIAN_RU = "ru-RU"

    # Arabic
    ARABIC = "ar"
    ARABIC_SA = "ar-SA"
    ARABIC_EG = "ar-EG"

    # Hindi
    HINDI = "hi"
    HINDI_IN = "hi-IN"

    # Other major languages
    DUTCH = "nl"
    DUTCH_NL = "nl-NL"
    SWEDISH = "sv"
    NORWEGIAN = "no"
    DANISH = "da"
    FINNISH = "fi"
    POLISH = "pl"
    CZECH = "cs"
    HUNGARIAN = "hu"
    ROMANIAN = "ro"
    GREEK = "el"
    HEBREW = "he"
    TURKISH = "tr"
    UKRAINIAN = "uk"
    THAI = "th"
    VIETNAMESE = "vi"
    INDONESIAN = "id"
    MALAY = "ms"
    TAGALOG = "tl"

    # Additional common YouTube language codes
    BENGALI = "bn"
    GUJARATI = "gu"
    KANNADA = "kn"
    MALAYALAM = "ml"
    MARATHI = "mr"
    PUNJABI = "pa"
    TAMIL = "ta"
    TELUGU = "te"
    URDU = "ur"

    @classmethod
    def get_base_language(cls, language_code: str) -> str:
        """Extract base language from BCP-47 code.

        Args:
            language_code: BCP-47 language code (e.g., 'en-US', 'zh-CN')

        Returns:
            Base language code (e.g., 'en', 'zh')
        """
        return language_code.split("-")[0] if "-" in language_code else language_code

    @classmethod
    def get_common_variants(cls, base_language: str) -> list[str]:
        """Get common variants for a base language.

        Args:
            base_language: Base language code (e.g., 'en', 'es')

        Returns:
            List of common variants for that language
        """
        variants_map = {
            "en": ["en", "en-US", "en-GB", "en-AU", "en-CA"],
            "es": ["es", "es-ES", "es-MX", "es-AR", "es-CO"],
            "fr": ["fr", "fr-FR", "fr-CA"],
            "de": ["de", "de-DE", "de-AT", "de-CH"],
            "pt": ["pt", "pt-PT", "pt-BR"],
            "zh": ["zh-CN", "zh-TW", "zh-HK"],
            "ar": ["ar", "ar-SA", "ar-EG"],
        }
        return variants_map.get(base_language, [base_language])
