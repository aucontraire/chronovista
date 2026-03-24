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


class AvailabilityStatus(str, Enum):
    """Content availability status."""

    AVAILABLE = "available"
    PRIVATE = "private"
    DELETED = "deleted"
    TERMINATED = "terminated"
    COPYRIGHT = "copyright"
    TOS_VIOLATION = "tos_violation"
    UNAVAILABLE = "unavailable"


class TopicType(str, Enum):
    """Topic classification types."""

    YOUTUBE = "youtube"
    CUSTOM = "custom"


class PlaylistType(str, Enum):
    """Types of YouTube playlists.

    Distinguishes between regular user-created playlists and special
    system playlists with unique API behavior.
    """

    REGULAR = "regular"
    LIKED = "liked"  # Liked Videos playlist (LL prefix)
    WATCH_LATER = "watch_later"  # Watch Later playlist (WL prefix)
    HISTORY = "history"  # Watch History playlist (HL prefix)
    FAVORITES = "favorites"  # Legacy Favorites playlist


class ImageQuality(str, Enum):
    """YouTube thumbnail image quality levels.

    Maps to standard YouTube thumbnail URL suffixes for different
    resolution variants.
    """

    DEFAULT = "default"
    MEDIUM = "mqdefault"
    HIGH = "hqdefault"
    STANDARD = "sddefault"
    MAX = "maxresdefault"


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


class EntityType(str, Enum):
    """Types of named entities extracted from tags."""

    PERSON = "person"
    ORGANIZATION = "organization"
    PLACE = "place"
    EVENT = "event"
    WORK = "work"
    TECHNICAL_TERM = "technical_term"
    TOPIC = "topic"
    DESCRIPTOR = "descriptor"
    CONCEPT = "concept"
    OTHER = "other"


class EntityAliasType(str, Enum):
    """Types of alias relationships between entity names."""

    NAME_VARIANT = "name_variant"
    ABBREVIATION = "abbreviation"
    NICKNAME = "nickname"
    ASR_ERROR = "asr_error"
    TRANSLATED_NAME = "translated_name"
    FORMER_NAME = "former_name"


class TagStatus(str, Enum):
    """Lifecycle status of a canonical tag."""

    ACTIVE = "active"
    MERGED = "merged"
    DEPRECATED = "deprecated"


class CreationMethod(str, Enum):
    """Methods by which a canonical tag was created."""

    AUTO_NORMALIZE = "auto_normalize"
    MANUAL_MERGE = "manual_merge"
    BACKFILL = "backfill"
    API_CREATE = "api_create"


class DiscoveryMethod(str, Enum):
    """Methods by which a tag was originally discovered."""

    MANUAL = "manual"
    SPACY_NER = "spacy_ner"
    TAG_BOOTSTRAP = "tag_bootstrap"
    LLM_EXTRACTION = "llm_extraction"
    USER_CREATED = "user_created"


class TagOperationType(str, Enum):
    """Types of operations recorded in the tag operation log."""

    MERGE = "merge"
    SPLIT = "split"
    RENAME = "rename"
    DELETE = "delete"
    CREATE = "create"


class CorrectionType(str, Enum):
    """Types of corrections that can be applied to a transcript.

    Each value represents a category of transcription error being fixed.
    """

    SPELLING = "spelling"
    """Non-name orthographic errors (typos, misspellings of common words)."""

    PROPER_NOUN = "proper_noun"
    """Names of people, places, or organizations that ASR misrecognized."""

    CONTEXT_CORRECTION = "context_correction"
    """Right sound, wrong word — ASR picked a valid word that doesn't fit the context."""

    WORD_BOUNDARY = "word_boundary"
    """Run-together words or wrongly split compounds (e.g., 'alotof' → 'a lot of')."""

    FORMATTING = "formatting"
    """Punctuation, capitalization, or spacing corrections."""

    PROFANITY_FIX = "profanity_fix"
    """ASR garbled or censored profanity that needs restoration."""

    OTHER = "other"
    """Corrections that don't fit other categories."""

    REVERT = "revert"
    """System-only: marks a revert of a previous correction."""


class DetectionMethod(str, Enum):
    """Methods by which an entity mention was detected in transcript text."""

    RULE_MATCH = "rule_match"
    SPACY_NER = "spacy_ner"
    LLM_EXTRACTION = "llm_extraction"
    MANUAL = "manual"
    USER_CORRECTION = "user_correction"


class TaskStatus(str, Enum):
    """Status of a background task."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStepStatus(str, Enum):
    """Status of a pipeline step in the onboarding flow."""

    NOT_STARTED = "not_started"
    AVAILABLE = "available"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class OperationType(str, Enum):
    """Types of pipeline operations that can be triggered."""

    SEED_REFERENCE = "seed_reference"
    LOAD_DATA = "load_data"
    ENRICH_METADATA = "enrich_metadata"
    SYNC_TRANSCRIPTS = "sync_transcripts"
    NORMALIZE_TAGS = "normalize_tags"
