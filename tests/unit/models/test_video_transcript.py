"""
Tests for video transcript models using factory pattern.

Comprehensive tests for VideoTranscript Pydantic models with validation,
serialization, and business logic testing using factory-boy for DRY principles.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from chronovista.models.enums import DownloadReason, TrackKind, TranscriptType
from chronovista.models.video_transcript import (
    TranscriptSearchFilters,
    VideoTranscript,
    VideoTranscriptBase,
    VideoTranscriptCreate,
    VideoTranscriptUpdate,
    VideoTranscriptWithQuality,
)
from tests.factories.video_transcript_factory import (
    TranscriptSearchFiltersFactory,
    VideoTranscriptBaseFactory,
    VideoTranscriptCreateFactory,
    VideoTranscriptFactory,
    VideoTranscriptTestData,
    VideoTranscriptUpdateFactory,
    VideoTranscriptWithQualityFactory,
    create_batch_video_transcripts,
    create_transcript_search_filters,
    create_video_transcript,
    create_video_transcript_base,
    create_video_transcript_create,
    create_video_transcript_update,
    create_video_transcript_with_quality,
)


class TestVideoTranscriptBaseFactory:
    """Test VideoTranscriptBase model with factory pattern."""

    def test_video_transcript_base_creation(self):
        """Test basic VideoTranscriptBase creation from factory."""
        transcript = VideoTranscriptBaseFactory.build()

        assert isinstance(transcript, VideoTranscriptBase)
        assert transcript.video_id == "dQw4w9WgXcQ"
        assert transcript.language_code == "en-us"  # Should be lowercase
        assert "Never gonna give you up" in transcript.transcript_text
        assert transcript.transcript_type == TranscriptType.AUTO
        assert transcript.download_reason == DownloadReason.USER_REQUEST
        assert transcript.confidence_score == 0.87
        assert transcript.is_cc is False
        assert transcript.is_auto_synced is True
        assert transcript.track_kind == TrackKind.STANDARD

    def test_video_transcript_base_custom_values(self):
        """Test VideoTranscriptBase with custom values."""
        custom_transcript = VideoTranscriptBaseFactory.build(
            video_id="dQw4w9WgXcQ",
            language_code="es-MX",
            transcript_text="Hola mundo, este es un texto personalizado.",
            transcript_type=TranscriptType.MANUAL,
            download_reason=DownloadReason.LEARNING_LANGUAGE,
            confidence_score=0.95,
            is_cc=True,
            is_auto_synced=False,
            track_kind=TrackKind.ASR,
        )

        assert custom_transcript.video_id == "dQw4w9WgXcQ"
        assert custom_transcript.language_code == "es-mx"  # Should be lowercase
        assert (
            custom_transcript.transcript_text
            == "Hola mundo, este es un texto personalizado."
        )
        assert custom_transcript.transcript_type == TranscriptType.MANUAL
        assert custom_transcript.confidence_score == 0.95

    @pytest.mark.parametrize("valid_video_id", VideoTranscriptTestData.VALID_VIDEO_IDS)
    def test_video_transcript_base_valid_video_ids(self, valid_video_id):
        """Test VideoTranscriptBase with valid video IDs."""
        transcript = VideoTranscriptBaseFactory.build(video_id=valid_video_id)
        assert transcript.video_id == valid_video_id.strip()

    @pytest.mark.parametrize(
        "invalid_video_id", VideoTranscriptTestData.INVALID_VIDEO_IDS
    )
    def test_video_transcript_base_invalid_video_ids(self, invalid_video_id):
        """Test VideoTranscriptBase validation with invalid video IDs."""
        with pytest.raises(ValidationError):
            VideoTranscriptBaseFactory.build(video_id=invalid_video_id)

    @pytest.mark.parametrize(
        "valid_language_code", VideoTranscriptTestData.VALID_LANGUAGE_CODES
    )
    def test_video_transcript_base_valid_language_codes(self, valid_language_code):
        """Test VideoTranscriptBase with valid language codes."""
        transcript = VideoTranscriptBaseFactory.build(language_code=valid_language_code)
        assert transcript.language_code == valid_language_code.lower()

    @pytest.mark.parametrize(
        "invalid_language_code", VideoTranscriptTestData.INVALID_LANGUAGE_CODES
    )
    def test_video_transcript_base_invalid_language_codes(self, invalid_language_code):
        """Test VideoTranscriptBase validation with invalid language codes."""
        with pytest.raises(ValidationError):
            VideoTranscriptBaseFactory.build(language_code=invalid_language_code)

    @pytest.mark.parametrize(
        "valid_transcript_type", VideoTranscriptTestData.VALID_TRANSCRIPT_TYPES
    )
    def test_video_transcript_base_valid_transcript_types(self, valid_transcript_type):
        """Test VideoTranscriptBase with valid transcript types."""
        transcript = VideoTranscriptBaseFactory.build(
            transcript_type=valid_transcript_type
        )
        assert transcript.transcript_type == valid_transcript_type

    @pytest.mark.parametrize(
        "valid_download_reason", VideoTranscriptTestData.VALID_DOWNLOAD_REASONS
    )
    def test_video_transcript_base_valid_download_reasons(self, valid_download_reason):
        """Test VideoTranscriptBase with valid download reasons."""
        transcript = VideoTranscriptBaseFactory.build(
            download_reason=valid_download_reason
        )
        assert transcript.download_reason == valid_download_reason

    @pytest.mark.parametrize(
        "valid_track_kind", VideoTranscriptTestData.VALID_TRACK_KINDS
    )
    def test_video_transcript_base_valid_track_kinds(self, valid_track_kind):
        """Test VideoTranscriptBase with valid track kinds."""
        transcript = VideoTranscriptBaseFactory.build(track_kind=valid_track_kind)
        assert transcript.track_kind == valid_track_kind

    @pytest.mark.parametrize(
        "valid_confidence_score", VideoTranscriptTestData.VALID_CONFIDENCE_SCORES
    )
    def test_video_transcript_base_valid_confidence_scores(
        self, valid_confidence_score
    ):
        """Test VideoTranscriptBase with valid confidence scores."""
        transcript = VideoTranscriptBaseFactory.build(
            confidence_score=valid_confidence_score
        )
        assert transcript.confidence_score == valid_confidence_score

    @pytest.mark.parametrize(
        "invalid_confidence_score", VideoTranscriptTestData.INVALID_CONFIDENCE_SCORES
    )
    def test_video_transcript_base_invalid_confidence_scores(
        self, invalid_confidence_score
    ):
        """Test VideoTranscriptBase validation with invalid confidence scores."""
        with pytest.raises(ValidationError):
            VideoTranscriptBaseFactory.build(confidence_score=invalid_confidence_score)

    @pytest.mark.parametrize(
        "valid_transcript_text", VideoTranscriptTestData.VALID_TRANSCRIPT_TEXTS
    )
    def test_video_transcript_base_valid_transcript_texts(self, valid_transcript_text):
        """Test VideoTranscriptBase with valid transcript texts."""
        transcript = VideoTranscriptBaseFactory.build(
            transcript_text=valid_transcript_text
        )
        assert transcript.transcript_text == valid_transcript_text.strip()

    @pytest.mark.parametrize(
        "invalid_transcript_text", VideoTranscriptTestData.INVALID_TRANSCRIPT_TEXTS
    )
    def test_video_transcript_base_invalid_transcript_texts(
        self, invalid_transcript_text
    ):
        """Test VideoTranscriptBase validation with invalid transcript texts."""
        with pytest.raises(ValidationError):
            VideoTranscriptBaseFactory.build(transcript_text=invalid_transcript_text)

    @pytest.mark.parametrize(
        "valid_caption_name", VideoTranscriptTestData.VALID_CAPTION_NAMES
    )
    def test_video_transcript_base_valid_caption_names(self, valid_caption_name):
        """Test VideoTranscriptBase with valid caption names."""
        transcript = VideoTranscriptBaseFactory.build(caption_name=valid_caption_name)
        assert transcript.caption_name == valid_caption_name

    @pytest.mark.parametrize(
        "invalid_caption_name", VideoTranscriptTestData.INVALID_CAPTION_NAMES
    )
    def test_video_transcript_base_invalid_caption_names(self, invalid_caption_name):
        """Test VideoTranscriptBase validation with invalid caption names."""
        with pytest.raises(ValidationError):
            VideoTranscriptBaseFactory.build(caption_name=invalid_caption_name)

    def test_video_transcript_base_model_dump(self):
        """Test VideoTranscriptBase model_dump functionality."""
        transcript = VideoTranscriptBaseFactory.build()
        data = transcript.model_dump()

        assert isinstance(data, dict)
        assert data["video_id"] == "dQw4w9WgXcQ"
        assert data["language_code"] == "en-us"
        assert data["transcript_type"] == "auto"  # Enum value
        assert data["download_reason"] == "user_request"  # Enum value

    def test_video_transcript_base_model_validate(self):
        """Test VideoTranscriptBase model_validate functionality."""
        data = {
            "video_id": "dQw4w9WgXcQ",
            "language_code": "fr-CA",  # Valid enum value
            "transcript_text": "Bonjour le monde! Comment allez-vous?",
            "transcript_type": "manual",
            "download_reason": "learning_language",
            "confidence_score": 0.88,
            "is_cc": True,
            "is_auto_synced": False,
            "track_kind": "standard",
            "caption_name": "Français (Canada)",
        }

        transcript = VideoTranscriptBase.model_validate(data)
        assert transcript.video_id == "dQw4w9WgXcQ"
        assert transcript.language_code == "fr-ca"  # Should be lowercase
        assert transcript.transcript_type == TranscriptType.MANUAL
        assert transcript.confidence_score == 0.88

    def test_video_transcript_base_convenience_function(self):
        """Test convenience function for VideoTranscriptBase."""
        transcript = create_video_transcript_base(
            video_id="dQw4w9WgXcQ",
            language_code="de-AT",
            transcript_text="Guten Tag! Das ist ein Test.",
        )

        assert transcript.video_id == "dQw4w9WgXcQ"
        assert transcript.language_code == "de-at"
        assert transcript.transcript_text == "Guten Tag! Das ist ein Test."


class TestVideoTranscriptCreateFactory:
    """Test VideoTranscriptCreate model with factory pattern."""

    def test_video_transcript_create_creation(self):
        """Test basic VideoTranscriptCreate creation from factory."""
        transcript = VideoTranscriptCreateFactory.build()

        assert isinstance(transcript, VideoTranscriptCreate)
        assert transcript.video_id == "9bZkp7q19f0"
        assert transcript.language_code == "en"
        assert "Google I/O" in transcript.transcript_text
        assert transcript.transcript_type == TranscriptType.MANUAL

    def test_video_transcript_create_convenience_function(self):
        """Test convenience function for VideoTranscriptCreate."""
        transcript = create_video_transcript_create(
            video_id="dQw4w9WgXcQ",
            transcript_text="This is a test transcript for creation.",
        )

        assert transcript.video_id == "dQw4w9WgXcQ"
        assert transcript.transcript_text == "This is a test transcript for creation."


class TestVideoTranscriptUpdateFactory:
    """Test VideoTranscriptUpdate model with factory pattern."""

    def test_video_transcript_update_creation(self):
        """Test basic VideoTranscriptUpdate creation from factory."""
        update = VideoTranscriptUpdateFactory.build()

        assert isinstance(update, VideoTranscriptUpdate)
        assert update.transcript_text is not None
        assert "Updated transcript text" in update.transcript_text
        assert update.transcript_type == TranscriptType.TRANSLATED
        assert update.confidence_score == 0.92

    def test_video_transcript_update_partial_data(self):
        """Test VideoTranscriptUpdate with partial data."""
        update = VideoTranscriptUpdateFactory.build(
            transcript_text="Only transcript text update",
            transcript_type=None,  # Only update some fields
            confidence_score=None,
        )

        assert update.transcript_text == "Only transcript text update"
        assert update.transcript_type is None
        assert update.confidence_score is None

    def test_video_transcript_update_none_values(self):
        """Test VideoTranscriptUpdate with all None values."""
        update = VideoTranscriptUpdate(
            transcript_text=None,
            transcript_type=None,
            download_reason=None,
            confidence_score=None,
            is_cc=None,
            is_auto_synced=None,
            track_kind=None,
            caption_name=None,
        )

        assert update.transcript_text is None
        assert update.transcript_type is None
        assert update.download_reason is None

    def test_video_transcript_update_convenience_function(self):
        """Test convenience function for VideoTranscriptUpdate."""
        update = create_video_transcript_update(
            transcript_text="Convenience update text", confidence_score=0.91
        )

        assert update.transcript_text == "Convenience update text"
        assert update.confidence_score == 0.91


class TestVideoTranscriptFactory:
    """Test VideoTranscript model with factory pattern."""

    def test_video_transcript_creation(self):
        """Test basic VideoTranscript creation from factory."""
        transcript = VideoTranscriptFactory.build()

        assert isinstance(transcript, VideoTranscript)
        assert transcript.video_id == "3tmd-ClpJxA"
        assert transcript.language_code == "es"
        assert "Stephen Colbert" in transcript.transcript_text
        assert hasattr(transcript, "downloaded_at")

    def test_video_transcript_timestamps(self):
        """Test VideoTranscript with custom timestamps."""
        downloaded_time = datetime(2023, 1, 1, tzinfo=timezone.utc)

        transcript = VideoTranscriptFactory.build(downloaded_at=downloaded_time)

        assert transcript.downloaded_at == downloaded_time

    def test_video_transcript_from_attributes_config(self):
        """Test VideoTranscript from_attributes configuration for ORM compatibility."""
        transcript_data = {
            "video_id": "dQw4w9WgXcQ",
            "language_code": "it-IT",
            "transcript_text": "Benvenuti al nostro canale YouTube italiano!",
            "transcript_type": "manual",
            "download_reason": "user_request",
            "confidence_score": 0.93,
            "is_cc": True,
            "is_auto_synced": False,
            "track_kind": "standard",
            "caption_name": "Italiano (manuale)",
            "downloaded_at": datetime(2023, 6, 15, 10, 30, tzinfo=timezone.utc),
        }

        transcript = VideoTranscript.model_validate(transcript_data)
        assert transcript.video_id == "dQw4w9WgXcQ"
        assert (
            transcript.language_code == "it-it"
        )  # Language code normalized to lowercase
        assert transcript.transcript_type == TranscriptType.MANUAL
        assert transcript.downloaded_at is not None

    def test_video_transcript_convenience_function(self):
        """Test convenience function for VideoTranscript."""
        transcript = create_video_transcript(
            video_id="dQw4w9WgXcQ",
            transcript_text="Convenience test transcript content.",
        )

        assert transcript.video_id == "dQw4w9WgXcQ"
        assert transcript.transcript_text == "Convenience test transcript content."


class TestVideoTranscriptWithQualityFactory:
    """Test VideoTranscriptWithQuality model with factory pattern."""

    def test_video_transcript_with_quality_creation(self):
        """Test basic VideoTranscriptWithQuality creation from factory."""
        transcript = VideoTranscriptWithQualityFactory.build()

        assert isinstance(transcript, VideoTranscriptWithQuality)
        assert transcript.video_id == "jNQXAC9IVRw"
        assert "iPhone 15 Pro Max" in transcript.transcript_text
        assert transcript.quality_score == 0.94
        assert transcript.is_high_quality is True
        assert transcript.language_match_user_prefs is True

    def test_video_transcript_with_quality_custom_values(self):
        """Test VideoTranscriptWithQuality with custom values."""
        transcript = VideoTranscriptWithQualityFactory.build(
            quality_score=0.75, is_high_quality=False, language_match_user_prefs=False
        )

        assert transcript.quality_score == 0.75
        assert transcript.is_high_quality is False
        assert transcript.language_match_user_prefs is False

    def test_video_transcript_with_quality_validation(self):
        """Test VideoTranscriptWithQuality quality score validation."""
        # Valid quality score
        transcript = VideoTranscriptWithQualityFactory.build(quality_score=0.85)
        assert transcript.quality_score == 0.85

        # Invalid quality score - too high
        with pytest.raises(ValidationError):
            VideoTranscriptWithQualityFactory.build(quality_score=1.5)

        # Invalid quality score - too low
        with pytest.raises(ValidationError):
            VideoTranscriptWithQualityFactory.build(quality_score=-0.1)

    def test_video_transcript_with_quality_convenience_function(self):
        """Test convenience function for VideoTranscriptWithQuality."""
        transcript = create_video_transcript_with_quality(
            quality_score=0.88, is_high_quality=True
        )

        assert transcript.quality_score == 0.88
        assert transcript.is_high_quality is True


class TestTranscriptSearchFiltersFactory:
    """Test TranscriptSearchFilters model with factory pattern."""

    def test_transcript_search_filters_creation(self):
        """Test basic TranscriptSearchFilters creation from factory."""
        filters = TranscriptSearchFiltersFactory.build()

        assert isinstance(filters, TranscriptSearchFilters)
        assert filters.video_ids is not None
        assert len(filters.video_ids) == 3
        assert filters.language_codes is not None
        assert len(filters.language_codes) == 3
        assert filters.transcript_types is not None
        assert len(filters.transcript_types) == 2
        assert filters.min_confidence == 0.7
        assert filters.is_cc_only is True

    def test_transcript_search_filters_partial(self):
        """Test TranscriptSearchFilters with partial data."""
        filters = TranscriptSearchFiltersFactory.build(
            video_ids=["dQw4w9WgXcQ"], language_codes=None, min_confidence=None
        )

        assert filters.video_ids == ["dQw4w9WgXcQ"]
        assert filters.language_codes is None
        assert filters.min_confidence is None

    def test_transcript_search_filters_comprehensive(self):
        """Test TranscriptSearchFilters with all fields."""
        download_after = datetime(2023, 1, 1, tzinfo=timezone.utc)
        download_before = datetime(2023, 12, 31, tzinfo=timezone.utc)

        filters = TranscriptSearchFiltersFactory.build(
            video_ids=["dQw4w9WgXcQ", "9bZkp7q19f0", "3tmd-ClpJxA"],
            language_codes=["en", "es", "fr", "de"],
            transcript_types=[TranscriptType.MANUAL],
            download_reasons=[DownloadReason.USER_REQUEST],
            track_kinds=[TrackKind.STANDARD, TrackKind.ASR],
            min_confidence=0.85,
            is_cc_only=True,
            is_manual_only=True,
            downloaded_after=download_after,
            downloaded_before=download_before,
        )

        assert filters.video_ids is not None
        assert len(filters.video_ids) == 3
        assert filters.language_codes is not None
        assert len(filters.language_codes) == 4
        assert filters.transcript_types == [TranscriptType.MANUAL]
        assert filters.min_confidence == 0.85
        assert filters.downloaded_after == download_after

    def test_transcript_search_filters_convenience_function(self):
        """Test convenience function for TranscriptSearchFilters."""
        filters = create_transcript_search_filters(
            video_ids=["dQw4w9WgXcQ"], min_confidence=0.9
        )

        assert filters.video_ids == ["dQw4w9WgXcQ"]
        assert filters.min_confidence == 0.9


class TestBatchOperations:
    """Test batch operations and advanced factory usage."""

    def test_create_batch_video_transcripts(self):
        """Test creating multiple VideoTranscript instances."""
        transcripts = create_batch_video_transcripts(count=3)

        assert len(transcripts) == 3
        assert all(
            isinstance(transcript, VideoTranscript) for transcript in transcripts
        )

        # Check that different values are generated
        video_ids = [t.video_id for t in transcripts]
        language_codes = [t.language_code for t in transcripts]
        confidence_scores = [t.confidence_score for t in transcripts]

        assert len(set(video_ids)) > 1  # Should have different video IDs
        assert len(set(language_codes)) > 1  # Should have different language codes
        assert (
            len(set(confidence_scores)) > 1
        )  # Should have different confidence scores

    def test_model_serialization_round_trip(self):
        """Test model serialization and deserialization."""
        original = VideoTranscriptFactory.build(
            video_id="dQw4w9WgXcQ",
            transcript_text="Serialization test content",
            confidence_score=0.92,
        )

        # Serialize to dict
        data = original.model_dump()

        # Deserialize back to model
        restored = VideoTranscript.model_validate(data)

        assert original.video_id == restored.video_id
        assert original.transcript_text == restored.transcript_text
        assert original.confidence_score == restored.confidence_score
        assert original.downloaded_at == restored.downloaded_at

    def test_factory_inheritance_behavior(self):
        """Test that factories properly handle model inheritance."""
        base_transcript = VideoTranscriptBaseFactory.build()
        create_transcript = VideoTranscriptCreateFactory.build()
        full_transcript = VideoTranscriptFactory.build()
        quality_transcript = VideoTranscriptWithQualityFactory.build()

        # All should have the core attributes
        for transcript in [
            base_transcript,
            create_transcript,
            full_transcript,
            quality_transcript,
        ]:
            assert hasattr(transcript, "video_id")
            assert hasattr(transcript, "language_code")
            assert hasattr(transcript, "transcript_text")
            assert hasattr(transcript, "transcript_type")

        # Only full transcript and quality transcript should have timestamps
        assert hasattr(full_transcript, "downloaded_at")
        assert hasattr(quality_transcript, "downloaded_at")
        assert not hasattr(base_transcript, "downloaded_at")
        assert not hasattr(create_transcript, "downloaded_at")

        # Only quality transcript should have quality metrics
        assert hasattr(quality_transcript, "quality_score")
        assert hasattr(quality_transcript, "is_high_quality")
        assert not hasattr(full_transcript, "quality_score")


class TestValidationEdgeCases:
    """Test edge cases and validation scenarios."""

    def test_none_values_handling(self):
        """Test handling of None values in optional fields."""
        transcript = VideoTranscriptBaseFactory.build(
            confidence_score=None, caption_name=None
        )

        assert transcript.confidence_score is None
        assert transcript.caption_name is None

    def test_boundary_values(self):
        """Test boundary values for validation."""
        # Test minimum valid values with proper YouTube ID formats
        min_transcript = VideoTranscriptBaseFactory.build(
            video_id="dQw4w9WgXcQ",  # Valid 11-char video ID
            language_code="en",  # Min valid language code
            transcript_text="Hi!",  # Short but valid text
            confidence_score=0.0,  # Min confidence
        )
        assert len(min_transcript.video_id) == 11
        assert len(min_transcript.language_code) == 2
        assert min_transcript.confidence_score == 0.0

        # Test maximum valid values
        max_transcript = VideoTranscriptBaseFactory.build(
            video_id="abcdefghijk",  # Valid 11-char length
            language_code="zh-CN",  # Valid complex language code
            transcript_text="A" * 1000,  # Long transcript
            confidence_score=1.0,  # Max confidence
            caption_name="B" * 255,  # Max caption name length
        )
        assert len(max_transcript.video_id) == 11
        assert max_transcript.confidence_score == 1.0
        assert max_transcript.caption_name is not None
        assert len(max_transcript.caption_name) == 255

    def test_model_config_validation(self):
        """Test model configuration validation behaviors."""
        transcript = VideoTranscriptFactory.build()

        # Test validate_assignment works
        transcript.confidence_score = 0.75
        assert transcript.confidence_score == 0.75

        # Test that invalid assignment raises validation error
        with pytest.raises(ValidationError):
            transcript.confidence_score = 1.5  # Invalid high score

    def test_field_validator_edge_cases(self):
        """Test field validator edge cases."""
        # Test video_id validator - VideoId type enforces exact format, no trimming
        transcript1 = VideoTranscriptBaseFactory.build(video_id="dQw4w9WgXcQ")
        assert (
            transcript1.video_id == "dQw4w9WgXcQ"
        )  # VideoId type validates exact format

        # Test transcript_text validator with whitespace
        transcript2 = VideoTranscriptBaseFactory.build(
            transcript_text="  Test content  "
        )
        assert transcript2.transcript_text == "Test content"  # Should be trimmed

        # Test language_code validator - enum requires exact case
        transcript3 = VideoTranscriptBaseFactory.build(language_code="en-US")
        assert (
            transcript3.language_code == "en-us"
        )  # Language code normalized to lowercase

    def test_enum_validation(self):
        """Test enum validation for transcript types, download reasons, and track kinds."""
        # Test with string values
        transcript1 = VideoTranscriptBaseFactory.build(transcript_type="auto")
        assert transcript1.transcript_type == TranscriptType.AUTO

        transcript2 = VideoTranscriptBaseFactory.build(download_reason="user_request")
        assert transcript2.download_reason == DownloadReason.USER_REQUEST

        transcript3 = VideoTranscriptBaseFactory.build(track_kind="asr")
        assert transcript3.track_kind == TrackKind.ASR

        # Test with enum values
        transcript4 = VideoTranscriptBaseFactory.build(
            transcript_type=TranscriptType.MANUAL
        )
        assert transcript4.transcript_type == TranscriptType.MANUAL

    def test_transcript_quality_scenarios(self):
        """Test different transcript quality scenarios."""
        # High quality manual transcript
        high_quality = VideoTranscriptBaseFactory.build(
            transcript_type=TranscriptType.MANUAL,
            is_cc=True,
            is_auto_synced=False,
            confidence_score=0.95,
            track_kind=TrackKind.STANDARD,
        )
        assert high_quality.transcript_type == TranscriptType.MANUAL
        assert high_quality.is_cc is True
        assert high_quality.confidence_score == 0.95

        # Auto-generated transcript
        auto_quality = VideoTranscriptBaseFactory.build(
            transcript_type=TranscriptType.AUTO,
            is_cc=False,
            is_auto_synced=True,
            confidence_score=0.75,
            track_kind=TrackKind.ASR,
        )
        assert auto_quality.transcript_type == TranscriptType.AUTO
        assert auto_quality.is_auto_synced is True
        assert auto_quality.track_kind == TrackKind.ASR

        # Translated transcript
        translated = VideoTranscriptBaseFactory.build(
            transcript_type=TranscriptType.TRANSLATED,
            language_code="es",
            download_reason=DownloadReason.LEARNING_LANGUAGE,
            confidence_score=0.82,
        )
        assert translated.transcript_type == TranscriptType.TRANSLATED
        assert translated.download_reason == DownloadReason.LEARNING_LANGUAGE

    def test_multilingual_content(self):
        """Test multilingual transcript content scenarios."""
        # English transcript
        english = VideoTranscriptBaseFactory.build(
            language_code="en-US",
            transcript_text="Hello everyone, welcome to our English tutorial!",
        )
        assert english.language_code == "en-us"

        # Spanish transcript
        spanish = VideoTranscriptBaseFactory.build(
            language_code="es-MX",
            transcript_text="¡Hola a todos, bienvenidos a nuestro tutorial en español!",
        )
        assert spanish.language_code == "es-mx"

        # Japanese transcript
        japanese = VideoTranscriptBaseFactory.build(
            language_code="ja",
            transcript_text="こんにちは皆さん、日本語のチュートリアルへようこそ！",
        )
        assert japanese.language_code == "ja"

        # Mixed content transcript
        mixed = VideoTranscriptBaseFactory.build(
            language_code="en",
            transcript_text="Hello! Hola! Bonjour! This video has multilingual content.",
        )
        assert "multilingual" in mixed.transcript_text

    def test_download_reason_logic(self):
        """Test different download reason scenarios."""
        reasons_and_contexts = [
            (DownloadReason.USER_REQUEST, "User explicitly requested this transcript"),
            (
                DownloadReason.AUTO_PREFERRED,
                "Automatically downloaded based on user preferences",
            ),
            (
                DownloadReason.LEARNING_LANGUAGE,
                "Downloaded for language learning purposes",
            ),
            (DownloadReason.API_ENRICHMENT, "Downloaded for API data enrichment"),
        ]

        for reason, context in reasons_and_contexts:
            transcript = VideoTranscriptBaseFactory.build(
                download_reason=reason, transcript_text=context
            )
            assert transcript.download_reason == reason
            assert context in transcript.transcript_text
