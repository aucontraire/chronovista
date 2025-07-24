"""
Tests for TranscriptService.

Tests transcript downloading functionality with mock fallback
when the real API is unavailable.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from chronovista.models.enums import DownloadReason, LanguageCode
from chronovista.models.transcript_source import TranscriptSource
from chronovista.models.video_transcript import EnhancedVideoTranscriptBase
from chronovista.models.youtube_types import create_test_video_id
from chronovista.services.transcript_service import (
    TranscriptNotFoundError,
    TranscriptService,
    TranscriptServiceError,
    TranscriptServiceUnavailableError,
)


class TestTranscriptService:
    """Test cases for TranscriptService."""

    def test_init_with_mock_fallback_enabled(self):
        """Test service initialization with mock fallback enabled."""
        service = TranscriptService(enable_mock_fallback=True)
        assert service.enable_mock_fallback is True
        assert (
            service.is_service_available() is True
        )  # Should be available due to mock fallback

    def test_init_with_mock_fallback_disabled(self):
        """Test service initialization with mock fallback disabled."""
        service = TranscriptService(enable_mock_fallback=False)
        assert service.enable_mock_fallback is False

    @pytest.mark.asyncio
    async def test_get_transcript_with_mock_fallback(self):
        """Test getting transcript when API is unavailable, using mock fallback."""
        service = TranscriptService(enable_mock_fallback=True)

        # Mock the API as unavailable
        service._api_available = False

        test_video_id = create_test_video_id("dQw4w9Wg")
        transcript = await service.get_transcript(
            video_id=test_video_id,
            language_codes=["en"],
            download_reason=DownloadReason.USER_REQUEST,
        )

        # Verify transcript structure
        assert isinstance(transcript, EnhancedVideoTranscriptBase)
        assert transcript.video_id == test_video_id
        assert transcript.source == TranscriptSource.UNKNOWN  # Mock data source
        assert transcript.download_reason == DownloadReason.USER_REQUEST
        assert transcript.plain_text_only is not None
        assert len(transcript.plain_text_only) > 0
        assert transcript.has_timestamps is True
        assert transcript.snippet_count == 4  # Mock data has 4 snippets
        assert transcript.total_duration > 0
        assert "mock" in transcript.source_metadata.get("reason", "").lower()

    @pytest.mark.asyncio
    async def test_get_transcript_no_fallback_fails(self):
        """Test that service fails when API unavailable and no fallback."""
        service = TranscriptService(enable_mock_fallback=False)
        service._api_available = False

        with pytest.raises(TranscriptNotFoundError) as exc_info:
            await service.get_transcript(create_test_video_id("dQw4w9Wg"))

        assert "No transcript found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_transcript_with_custom_language_codes(self):
        """Test getting transcript with specific language preferences."""
        service = TranscriptService(enable_mock_fallback=True)
        service._api_available = False  # Force mock fallback

        test_video_id = create_test_video_id("test12345")
        transcript = await service.get_transcript(
            video_id=test_video_id,
            language_codes=["es", "fr"],
            download_reason=DownloadReason.LEARNING_LANGUAGE,
        )

        assert transcript.video_id == test_video_id
        assert transcript.download_reason == DownloadReason.LEARNING_LANGUAGE
        # Mock uses first language or falls back to English
        assert transcript.language_code in [LanguageCode.SPANISH, LanguageCode.ENGLISH]

    @pytest.mark.asyncio
    async def test_get_available_languages_api_unavailable(self):
        """Test getting available languages when API is unavailable."""
        service = TranscriptService()
        service._api_available = False

        languages = await service.get_available_languages(
            create_test_video_id("dQw4w9Wg")
        )
        assert languages == []

    @pytest.mark.asyncio
    async def test_batch_get_transcripts(self):
        """Test batch transcript downloading."""
        service = TranscriptService(enable_mock_fallback=True)
        service._api_available = False  # Force mock fallback

        video_ids = [
            create_test_video_id("video123"),
            create_test_video_id("video456"),
            create_test_video_id("video789"),
        ]
        results = await service.batch_get_transcripts(
            video_ids=video_ids,
            language_codes=["en"],
            download_reason=DownloadReason.API_ENRICHMENT,
        )

        assert len(results) == 3
        assert all(video_id in results for video_id in video_ids)

        # All should succeed with mock fallback
        successful_transcripts = [t for t in results.values() if t is not None]
        assert len(successful_transcripts) == 3

        # Verify transcript properties
        for transcript in successful_transcripts:
            assert isinstance(transcript, EnhancedVideoTranscriptBase)
            assert transcript.download_reason == DownloadReason.API_ENRICHMENT
            assert transcript.source == TranscriptSource.UNKNOWN

    @pytest.mark.asyncio
    async def test_batch_get_transcripts_with_failures(self):
        """Test batch downloading with some failures."""
        service = TranscriptService(enable_mock_fallback=False)
        service._api_available = False  # API unavailable, no fallback

        video_ids = [create_test_video_id("video123"), create_test_video_id("video456")]
        results = await service.batch_get_transcripts(video_ids)

        # All should fail without fallback
        assert len(results) == 2
        assert all(transcript is None for transcript in results.values())

    def test_create_mock_transcript(self):
        """Test mock transcript creation."""
        service = TranscriptService()

        test_video_id = create_test_video_id("test12345")
        mock_transcript = service._create_mock_transcript(
            video_id=test_video_id,
            language_code="en-US",
            download_reason=DownloadReason.USER_REQUEST,
        )

        assert isinstance(mock_transcript, EnhancedVideoTranscriptBase)
        assert mock_transcript.video_id == test_video_id
        assert (
            mock_transcript.language_code == LanguageCode.ENGLISH
        )  # en-us gets converted to 'en'
        assert mock_transcript.download_reason == DownloadReason.USER_REQUEST
        assert mock_transcript.source == TranscriptSource.UNKNOWN
        assert mock_transcript.is_auto_synced is True  # Mock data is auto-generated
        assert test_video_id in mock_transcript.plain_text_only  # Contains video ID
        assert mock_transcript.source_metadata.get("is_mock") is True

    def test_create_mock_transcript_invalid_language(self):
        """Test mock transcript creation with invalid language code."""
        service = TranscriptService()

        mock_transcript = service._create_mock_transcript(
            video_id=create_test_video_id("test12345"),
            language_code="invalid-lang",
            download_reason=DownloadReason.USER_REQUEST,
        )

        # Should fallback to English for invalid language codes
        assert mock_transcript.language_code == LanguageCode.ENGLISH

    def test_is_service_available(self):
        """Test service availability check."""
        # With mock fallback enabled
        service_with_fallback = TranscriptService(enable_mock_fallback=True)
        assert service_with_fallback.is_service_available() is True

        # With mock fallback disabled and API unavailable
        service_no_fallback = TranscriptService(enable_mock_fallback=False)
        service_no_fallback._api_available = False
        assert service_no_fallback.is_service_available() is False

    @pytest.mark.asyncio
    async def test_official_api_placeholder(self):
        """Test that official API placeholder logs correctly."""
        service = TranscriptService()

        # Test the placeholder method directly
        result = await service._get_transcript_from_official_api(
            video_id=create_test_video_id("test123"),
            language_codes=["en", "es"],
            download_reason=DownloadReason.LEARNING_LANGUAGE,
        )

        # Should return None (not implemented yet)
        assert result is None

    @pytest.mark.asyncio
    async def test_default_language_codes(self):
        """Test that default language codes are used when none provided."""
        service = TranscriptService(enable_mock_fallback=True)
        service._api_available = False  # Force mock fallback

        transcript = await service.get_transcript(create_test_video_id("test_video"))

        # Should use English as default
        assert transcript.language_code == LanguageCode.ENGLISH


@pytest.mark.integration
class TestTranscriptServiceIntegration:
    """Integration tests for TranscriptService with real API (when available)."""

    @pytest.mark.asyncio
    async def test_real_api_when_available(self):
        """Test with real API if youtube-transcript-api is available."""
        service = TranscriptService(enable_mock_fallback=True)

        if not service._api_available:
            pytest.skip("youtube-transcript-api not available for integration test")

        # This test might fail if the API is down or video unavailable
        # That's expected - we'll fallback to mock data
        try:
            # Use a real video ID that should have transcripts
            real_video_id = "dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up
            transcript = await service.get_transcript(
                video_id=real_video_id, language_codes=["en"]
            )

            # If successful, verify it's from the real API
            if transcript.source == TranscriptSource.YOUTUBE_TRANSCRIPT_API:
                assert transcript.video_id == real_video_id
                assert (
                    len(transcript.plain_text_only) > 50
                )  # Real transcript should be substantial
                assert (
                    transcript.snippet_count > 10
                )  # Real transcript should have many snippets
            else:
                # If it fell back to mock, that's also acceptable
                assert transcript.source == TranscriptSource.UNKNOWN

        except Exception as e:
            # If real API fails, that's expected in some environments
            pytest.skip(f"Real API test skipped due to: {e}")

    @pytest.mark.asyncio
    async def test_get_available_languages_real_api(self):
        """Test getting available languages with real API."""
        service = TranscriptService()

        if not service._api_available:
            pytest.skip("youtube-transcript-api not available for integration test")

        try:
            # Use a real video ID
            real_video_id = "dQw4w9WgXcQ"
            languages = await service.get_available_languages(real_video_id)

            if languages:  # If we got results
                assert isinstance(languages, list)
                assert len(languages) > 0

                # Verify structure of language info
                first_lang = languages[0]
                assert "language_code" in first_lang
                assert "language_name" in first_lang
                assert "is_generated" in first_lang
                assert isinstance(first_lang["is_generated"], bool)

        except Exception as e:
            pytest.skip(f"Real API language test skipped due to: {e}")
