"""
Factory definitions for video transcript models.

Provides factory-boy factories for creating test instances of video transcript models
with realistic and consistent test data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, cast

import factory
from factory import LazyFunction

from chronovista.models.enums import (
    DownloadReason,
    LanguageCode,
    TrackKind,
    TranscriptType,
)
from chronovista.models.video_transcript import (
    TranscriptSearchFilters,
    VideoTranscript,
    VideoTranscriptBase,
    VideoTranscriptCreate,
    VideoTranscriptUpdate,
    VideoTranscriptWithQuality,
)


class VideoTranscriptBaseFactory(factory.Factory[VideoTranscriptBase]):
    """Factory for VideoTranscriptBase models."""

    class Meta:
        model = VideoTranscriptBase

    video_id: Any = factory.LazyFunction(lambda: "dQw4w9WgXcQ")
    language_code: Any = factory.LazyFunction(lambda: LanguageCode.ENGLISH_US)
    transcript_text: Any = factory.LazyFunction(
        lambda: "Never gonna give you up, never gonna let you down, never gonna run around and desert you."
    )
    transcript_type: Any = factory.LazyFunction(lambda: TranscriptType.AUTO)
    download_reason: Any = factory.LazyFunction(lambda: DownloadReason.USER_REQUEST)
    confidence_score: Any = factory.LazyFunction(lambda: 0.87)
    is_cc: Any = factory.LazyFunction(lambda: False)
    is_auto_synced: Any = factory.LazyFunction(lambda: True)
    track_kind: Any = factory.LazyFunction(lambda: TrackKind.STANDARD)
    caption_name: Any = factory.LazyFunction(lambda: "English (auto-generated)")


class VideoTranscriptCreateFactory(factory.Factory[VideoTranscriptCreate]):
    """Factory for VideoTranscriptCreate models."""

    class Meta:
        model = VideoTranscriptCreate

    video_id: Any = factory.LazyFunction(lambda: "9bZkp7q19f0")
    language_code: Any = factory.LazyFunction(lambda: "en")
    transcript_text: Any = factory.LazyFunction(
        lambda: "Welcome to Google I/O 2023. Today we'll explore the latest developments in machine learning and artificial intelligence."
    )
    transcript_type: Any = factory.LazyFunction(lambda: TranscriptType.MANUAL)
    download_reason: Any = factory.LazyFunction(lambda: DownloadReason.API_ENRICHMENT)
    confidence_score: Any = factory.LazyFunction(lambda: 0.95)
    is_cc: Any = factory.LazyFunction(lambda: True)
    is_auto_synced: Any = factory.LazyFunction(lambda: False)
    track_kind: Any = factory.LazyFunction(lambda: TrackKind.STANDARD)
    caption_name: Any = factory.LazyFunction(lambda: "English (CC)")


class VideoTranscriptUpdateFactory(factory.Factory[VideoTranscriptUpdate]):
    """Factory for VideoTranscriptUpdate models."""

    class Meta:
        model = VideoTranscriptUpdate

    transcript_text: Any = factory.LazyFunction(
        lambda: "Updated transcript text with corrections and improvements."
    )
    transcript_type: Any = factory.LazyFunction(lambda: TranscriptType.TRANSLATED)
    download_reason: Any = factory.LazyFunction(lambda: DownloadReason.LEARNING_LANGUAGE)
    confidence_score: Any = factory.LazyFunction(lambda: 0.92)
    is_cc: Any = factory.LazyFunction(lambda: True)
    is_auto_synced: Any = factory.LazyFunction(lambda: False)
    track_kind: Any = factory.LazyFunction(lambda: TrackKind.STANDARD)
    caption_name: Any = factory.LazyFunction(lambda: "Updated Caption Track")


class VideoTranscriptFactory(factory.Factory[VideoTranscript]):
    """Factory for VideoTranscript models."""

    class Meta:
        model = VideoTranscript

    video_id: Any = factory.LazyFunction(lambda: "3tmd-ClpJxA")
    language_code: Any = factory.LazyFunction(lambda: "es")
    transcript_text: Any = factory.LazyFunction(
        lambda: "Hola y bienvenidos al Late Show con Stephen Colbert. Esta noche tenemos grandes momentos de comedia."
    )
    transcript_type: Any = factory.LazyFunction(lambda: TranscriptType.MANUAL)
    download_reason: Any = factory.LazyFunction(lambda: DownloadReason.AUTO_PREFERRED)
    confidence_score: Any = factory.LazyFunction(lambda: 0.89)
    is_cc: Any = factory.LazyFunction(lambda: True)
    is_auto_synced: Any = factory.LazyFunction(lambda: False)
    track_kind: Any = factory.LazyFunction(lambda: TrackKind.STANDARD)
    caption_name: Any = factory.LazyFunction(lambda: "Español (manual)")
    downloaded_at: Any = factory.LazyFunction(
        lambda: datetime(2023, 12, 15, 16, 30, 0, tzinfo=timezone.utc)
    )


class VideoTranscriptWithQualityFactory(factory.Factory[VideoTranscriptWithQuality]):
    """Factory for VideoTranscriptWithQuality models."""

    class Meta:
        model = VideoTranscriptWithQuality

    video_id: Any = factory.LazyFunction(lambda: "jNQXAC9IVRw")
    language_code: Any = factory.LazyFunction(lambda: LanguageCode.ENGLISH_US)
    transcript_text: Any = factory.LazyFunction(
        lambda: "The iPhone 15 Pro Max represents Apple's most advanced smartphone technology with titanium construction and advanced camera systems."
    )
    transcript_type: Any = factory.LazyFunction(lambda: TranscriptType.MANUAL)
    download_reason: Any = factory.LazyFunction(lambda: DownloadReason.USER_REQUEST)
    confidence_score: Any = factory.LazyFunction(lambda: 0.96)
    is_cc: Any = factory.LazyFunction(lambda: True)
    is_auto_synced: Any = factory.LazyFunction(lambda: False)
    track_kind: Any = factory.LazyFunction(lambda: TrackKind.STANDARD)
    caption_name: Any = factory.LazyFunction(lambda: "English (Professional)")
    downloaded_at: Any = factory.LazyFunction(
        lambda: datetime(2023, 9, 22, 14, 0, 0, tzinfo=timezone.utc)
    )
    quality_score: Any = factory.LazyFunction(lambda: 0.94)
    is_high_quality: Any = factory.LazyFunction(lambda: True)
    language_match_user_prefs: Any = factory.LazyFunction(lambda: True)


class TranscriptSearchFiltersFactory(factory.Factory[TranscriptSearchFilters]):
    """Factory for TranscriptSearchFilters models."""

    class Meta:
        model = TranscriptSearchFilters

    video_ids: Any = factory.LazyFunction(
        lambda: ["dQw4w9WgXcQ", "9bZkp7q19f0", "3tmd-ClpJxA"]
    )
    language_codes: Any = factory.LazyFunction(lambda: ["en-US", "es", "fr"])
    transcript_types: Any = factory.LazyFunction(
        lambda: [TranscriptType.MANUAL, TranscriptType.AUTO]
    )
    download_reasons: Any = factory.LazyFunction(
        lambda: [DownloadReason.USER_REQUEST, DownloadReason.AUTO_PREFERRED]
    )
    track_kinds: Any = factory.LazyFunction(lambda: [TrackKind.STANDARD, TrackKind.ASR])
    min_confidence: Any = factory.LazyFunction(lambda: 0.7)
    is_cc_only: Any = factory.LazyFunction(lambda: True)
    is_manual_only: Any = factory.LazyFunction(lambda: False)
    downloaded_after: Any = factory.LazyFunction(
        lambda: datetime(2023, 1, 1, tzinfo=timezone.utc)
    )
    downloaded_before: Any = factory.LazyFunction(
        lambda: datetime(2023, 12, 31, tzinfo=timezone.utc)
    )


# Test data constants for validation testing
class VideoTranscriptTestData:
    """Test data constants for video transcript models."""

    # Valid test data
    VALID_VIDEO_IDS = [
        "dQw4w9WgXcQ",  # Rick Astley - 11 chars
        "9bZkp7q19f0",  # Google I/O - 11 chars
        "3tmd-ClpJxA",  # Late Show - 11 chars
        "jNQXAC9IVRw",  # MKBHD - 11 chars
        "MejbOFk7H6c",  # Another video - 11 chars
        "abcdefghijk",  # Exactly 11 chars
        "AAAAAAAAAAA",  # Another 11-char ID
    ]

    VALID_LANGUAGE_CODES = [
        "en",  # Language only
        "en-US",  # Language-Country
        "zh-CN",  # Chinese Simplified
        "pt-BR",  # Portuguese Brazil
        "es-MX",  # Spanish Mexico
        "fr-CA",  # French Canada
        "de-AT",  # German Austria
        "it-IT",  # Italian Italy
        "ja",  # Japanese
        "ko",  # Korean
        "ru",  # Russian
        "ar",  # Arabic
    ]

    VALID_TRANSCRIPT_TYPES = [
        TranscriptType.AUTO,
        TranscriptType.MANUAL,
        TranscriptType.TRANSLATED,
    ]

    VALID_DOWNLOAD_REASONS = [
        DownloadReason.USER_REQUEST,
        DownloadReason.AUTO_PREFERRED,
        DownloadReason.LEARNING_LANGUAGE,
        DownloadReason.API_ENRICHMENT,
    ]

    VALID_TRACK_KINDS = [
        TrackKind.STANDARD,
        TrackKind.ASR,
        TrackKind.FORCED,
    ]

    VALID_CONFIDENCE_SCORES = [0.0, 0.1, 0.5, 0.8, 0.95, 1.0]

    VALID_TRANSCRIPT_TEXTS = [
        "Hello world!",
        "This is a test transcript with multiple sentences. It contains various punctuation marks!",
        "A" * 1000,  # Long transcript
        "Multilingual content: Hola, Bonjour, Guten Tag, こんにちは",
        "Technical content with numbers: The temperature is 23.5°C at 15:30 UTC.",
        "     Whitespace test content     ",  # Should be trimmed
    ]

    VALID_CAPTION_NAMES = [
        "English (auto-generated)",
        "English (CC)",
        "Español (manual)",
        "Français (traduit automatiquement)",
        "Deutsch (Untertitel)",
        None,  # Optional field
    ]

    # Invalid test data
    INVALID_VIDEO_IDS = [
        "",
        "   ",
        "\t\n",
        "short7",
        "a" * 21,
    ]  # Empty, whitespace, too short, too long
    INVALID_LANGUAGE_CODES = [
        "",
        "a",
        "a-b-c-d",
        "-US",
        "english",
    ]  # Empty, too short, too many parts, missing language, too long
    INVALID_TRANSCRIPT_TEXTS = ["", "   ", "\t\n"]  # Empty, whitespace
    INVALID_CONFIDENCE_SCORES = [-0.1, -1.0, 1.1, 2.0]  # Out of range
    INVALID_CAPTION_NAMES = ["a" * 256]  # Too long


# Convenience factory functions
def create_video_transcript_base(**kwargs: Any) -> VideoTranscriptBase:
    """Create a VideoTranscriptBase with optional overrides."""
    result = VideoTranscriptBaseFactory.build(**kwargs)
    assert isinstance(result, VideoTranscriptBase)
    return result


def create_video_transcript_create(**kwargs: Any) -> VideoTranscriptCreate:
    """Create a VideoTranscriptCreate with optional overrides."""
    result = VideoTranscriptCreateFactory.build(**kwargs)
    assert isinstance(result, VideoTranscriptCreate)
    return result


def create_video_transcript_update(**kwargs: Any) -> VideoTranscriptUpdate:
    """Create a VideoTranscriptUpdate with optional overrides."""
    result = VideoTranscriptUpdateFactory.build(**kwargs)
    assert isinstance(result, VideoTranscriptUpdate)
    return result


def create_video_transcript(**kwargs: Any) -> VideoTranscript:
    """Create a VideoTranscript with optional overrides."""
    result = VideoTranscriptFactory.build(**kwargs)
    assert isinstance(result, VideoTranscript)
    return result


def create_video_transcript_with_quality(**kwargs: Any) -> VideoTranscriptWithQuality:
    """Create a VideoTranscriptWithQuality with optional overrides."""
    result = VideoTranscriptWithQualityFactory.build(**kwargs)
    assert isinstance(result, VideoTranscriptWithQuality)
    return result


def create_transcript_search_filters(**kwargs: Any) -> TranscriptSearchFilters:
    """Create a TranscriptSearchFilters with optional overrides."""
    result = TranscriptSearchFiltersFactory.build(**kwargs)
    assert isinstance(result, TranscriptSearchFilters)
    return result


def create_batch_video_transcripts(count: int = 5) -> List[VideoTranscript]:
    """Create a batch of VideoTranscript instances for testing."""
    transcripts = []
    base_video_ids = [
        "dQw4w9WgXcQ",
        "9bZkp7q19f0",
        "3tmd-ClpJxA",
        "jNQXAC9IVRw",
        "MejbOFk7H6c",
    ]
    base_languages = ["en-US", "es", "fr-FR", "de", "ja"]
    base_types = [
        TranscriptType.AUTO,
        TranscriptType.MANUAL,
        TranscriptType.TRANSLATED,
        TranscriptType.AUTO,
        TranscriptType.MANUAL,
    ]
    base_reasons = [
        DownloadReason.USER_REQUEST,
        DownloadReason.AUTO_PREFERRED,
        DownloadReason.LEARNING_LANGUAGE,
        DownloadReason.API_ENRICHMENT,
        DownloadReason.USER_REQUEST,
    ]
    base_texts = [
        "Never gonna give you up, never gonna let you down.",
        "Welcome to Google I/O 2023, exploring AI and ML.",
        "Bienvenue au Late Show avec Stephen Colbert.",
        "Das iPhone 15 Pro Max ist Apples neuestes Smartphone.",
        "こんにちは、YouTubeへようこそ。",
    ]

    for i in range(count):
        video_id = base_video_ids[i % len(base_video_ids)]
        language_code = base_languages[i % len(base_languages)]
        transcript_type = base_types[i % len(base_types)]
        download_reason = base_reasons[i % len(base_reasons)]
        transcript_text = base_texts[i % len(base_texts)]

        transcript = VideoTranscriptFactory.build(
            video_id=video_id,
            language_code=language_code,
            transcript_type=transcript_type,
            download_reason=download_reason,
            transcript_text=transcript_text,
            confidence_score=0.7 + (i * 0.05),  # Varying confidence scores
            is_cc=(i % 2 == 0),  # Alternate CC status
            is_auto_synced=(transcript_type == TranscriptType.AUTO),
        )
        transcripts.append(transcript)

    return transcripts
