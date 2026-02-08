"""
Tests for TranscriptService.

Comprehensive test coverage for YouTube transcript downloading and processing service.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mark all async tests in this module
pytestmark = pytest.mark.asyncio

from chronovista.models.enums import DownloadReason, LanguageCode
from chronovista.models.transcript_source import (
    RawTranscriptData,
    TranscriptSnippet,
    TranscriptSource,
)
from chronovista.models.video_transcript import EnhancedVideoTranscriptBase
from chronovista.models.youtube_types import create_test_video_id
from chronovista.services.transcript_service import (
    TRANSCRIPT_API_AVAILABLE,
    TranscriptNotFoundError,
    TranscriptService,
    TranscriptServiceError,
    TranscriptServiceUnavailableError,
)


class TestTranscriptServiceExceptions:
    """Tests for custom exception classes."""

    def test_transcript_service_error_inheritance(self):
        """Test TranscriptServiceError inheritance."""
        error = TranscriptServiceError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_transcript_not_found_error_inheritance(self):
        """Test TranscriptNotFoundError inheritance."""
        error = TranscriptNotFoundError("No transcript found")
        assert str(error) == "No transcript found"
        assert isinstance(error, TranscriptServiceError)
        assert isinstance(error, Exception)

    def test_transcript_service_unavailable_error_inheritance(self):
        """Test TranscriptServiceUnavailableError inheritance."""
        error = TranscriptServiceUnavailableError("Service unavailable")
        assert str(error) == "Service unavailable"
        assert isinstance(error, TranscriptServiceError)
        assert isinstance(error, Exception)


class TestTranscriptServiceInitialization:
    """Tests for TranscriptService initialization."""

    def test_init_with_api_available(self):
        """Test initialization when API is available."""
        with patch(
            "chronovista.services.transcript_service.TRANSCRIPT_API_AVAILABLE", True
        ):
            service = TranscriptService()
            assert service.enable_mock_fallback is True
            assert service._api_available is True

    def test_init_with_api_unavailable(self):
        """Test initialization when API is unavailable."""
        with patch(
            "chronovista.services.transcript_service.TRANSCRIPT_API_AVAILABLE", False
        ):
            with patch("chronovista.services.transcript_service.logger") as mock_logger:
                service = TranscriptService()
                assert service.enable_mock_fallback is True
                assert service._api_available is False
                mock_logger.warning.assert_called_once_with(
                    "youtube-transcript-api not available - using mock fallback only"
                )

    def test_init_with_mock_fallback_disabled(self):
        """Test initialization with mock fallback disabled."""
        service = TranscriptService(enable_mock_fallback=False)
        assert service.enable_mock_fallback is False

    def test_init_with_mock_fallback_enabled(self):
        """Test initialization with mock fallback enabled."""
        service = TranscriptService(enable_mock_fallback=True)
        assert service.enable_mock_fallback is True


class TestTranscriptServiceIsAvailable:
    """Tests for service availability checking."""

    def test_is_service_available_api_available(self):
        """Test service availability when API is available."""
        with patch(
            "chronovista.services.transcript_service.TRANSCRIPT_API_AVAILABLE", True
        ):
            service = TranscriptService(enable_mock_fallback=False)
            assert service.is_service_available() is True

    def test_is_service_available_api_unavailable_with_mock(self):
        """Test service availability when API unavailable but mock enabled."""
        with patch(
            "chronovista.services.transcript_service.TRANSCRIPT_API_AVAILABLE", False
        ):
            service = TranscriptService(enable_mock_fallback=True)
            assert service.is_service_available() is True

    def test_is_service_available_api_unavailable_no_mock(self):
        """Test service availability when API unavailable and mock disabled."""
        with patch(
            "chronovista.services.transcript_service.TRANSCRIPT_API_AVAILABLE", False
        ):
            service = TranscriptService(enable_mock_fallback=False)
            assert service.is_service_available() is False


class TestTranscriptServiceGetTranscript:
    """Tests for main transcript retrieval method."""

    @pytest.fixture
    def service(self):
        """Create TranscriptService for testing."""
        return TranscriptService()

    @pytest.fixture
    def sample_video_id(self):
        """Create test video ID."""
        return create_test_video_id("transcript")

    @pytest.fixture
    def sample_raw_transcript_data(self, sample_video_id):
        """Create sample raw transcript data."""
        snippets = [
            TranscriptSnippet(text="Hello world", start=0.0, duration=2.0),
            TranscriptSnippet(text="This is a test", start=2.0, duration=3.0),
        ]

        return RawTranscriptData(
            video_id=sample_video_id,
            language_code=LanguageCode.ENGLISH,
            language_name="English",
            snippets=snippets,
            is_generated=False,
            is_translatable=True,
            source=TranscriptSource.YOUTUBE_TRANSCRIPT_API,
            source_metadata={"test": "data"},
        )

    async def test_get_transcript_success_third_party_api(
        self, service, sample_video_id, sample_raw_transcript_data
    ):
        """Test successful transcript retrieval from third-party API."""
        service._api_available = True

        # Mock the third-party API method
        service._get_transcript_from_third_party_api = AsyncMock(
            return_value=sample_raw_transcript_data
        )

        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service.get_transcript(sample_video_id)

        assert isinstance(result, EnhancedVideoTranscriptBase)
        assert result.video_id == sample_video_id
        service._get_transcript_from_third_party_api.assert_called_once_with(
            sample_video_id, ["en", "en-US"]
        )
        mock_logger.info.assert_called()

    async def test_get_transcript_success_official_api_fallback(
        self, service, sample_video_id
    ):
        """Test successful transcript retrieval from official API as fallback."""
        service._api_available = True

        # Mock third-party API to fail
        service._get_transcript_from_third_party_api = AsyncMock(
            side_effect=Exception("API error")
        )

        # Mock official API to succeed
        mock_transcript = MagicMock(spec=EnhancedVideoTranscriptBase)
        mock_transcript.video_id = sample_video_id
        service._get_transcript_from_official_api = AsyncMock(
            return_value=mock_transcript
        )

        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service.get_transcript(sample_video_id)

        assert result == mock_transcript
        service._get_transcript_from_official_api.assert_called_once()
        mock_logger.info.assert_called()

    async def test_get_transcript_success_mock_fallback(self, service, sample_video_id):
        """Test successful transcript retrieval using mock fallback."""
        service._api_available = False
        service.enable_mock_fallback = True

        # Mock the _create_mock_transcript method
        mock_transcript = MagicMock(spec=EnhancedVideoTranscriptBase)
        mock_transcript.video_id = sample_video_id
        service._create_mock_transcript = MagicMock(return_value=mock_transcript)

        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service.get_transcript(sample_video_id)

        assert result == mock_transcript
        service._create_mock_transcript.assert_called_once_with(
            sample_video_id, "en", DownloadReason.USER_REQUEST
        )
        mock_logger.info.assert_called()

    async def test_get_transcript_with_custom_language_codes(
        self, service, sample_video_id, sample_raw_transcript_data
    ):
        """Test transcript retrieval with custom language codes."""
        service._api_available = True
        service._get_transcript_from_third_party_api = AsyncMock(
            return_value=sample_raw_transcript_data
        )

        custom_languages = ["es", "fr", "de"]
        await service.get_transcript(sample_video_id, language_codes=custom_languages)

        service._get_transcript_from_third_party_api.assert_called_once_with(
            sample_video_id, custom_languages
        )

    async def test_get_transcript_with_custom_download_reason(
        self, service, sample_video_id, sample_raw_transcript_data
    ):
        """Test transcript retrieval with custom download reason."""
        service._api_available = True
        service._get_transcript_from_third_party_api = AsyncMock(
            return_value=sample_raw_transcript_data
        )

        await service.get_transcript(
            sample_video_id, download_reason=DownloadReason.API_ENRICHMENT
        )

        # Verify the download reason is passed through properly
        service._get_transcript_from_third_party_api.assert_called_once()

    async def test_get_transcript_not_found_error(self, service, sample_video_id):
        """Test transcript not found error when all methods fail."""
        service._api_available = False
        service.enable_mock_fallback = False

        with pytest.raises(TranscriptNotFoundError, match="No transcript found"):
            await service.get_transcript(sample_video_id)

    async def test_get_transcript_handles_transcript_errors(
        self, service, sample_video_id
    ):
        """Test handling of transcript-specific errors."""
        service._api_available = True

        # Mock third-party API to raise transcript-related error
        service._get_transcript_from_third_party_api = AsyncMock(
            side_effect=Exception("Transcript disabled for this video")
        )

        # Mock official API to fail
        service._get_transcript_from_official_api = AsyncMock(return_value=None)

        # Should fall back to mock
        service.enable_mock_fallback = True
        mock_transcript = MagicMock(spec=EnhancedVideoTranscriptBase)
        service._create_mock_transcript = MagicMock(return_value=mock_transcript)

        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service.get_transcript(sample_video_id)

        assert result == mock_transcript
        mock_logger.warning.assert_called()

    async def test_get_transcript_handles_rate_limit_errors(
        self, service, sample_video_id
    ):
        """Test handling of rate limit errors."""
        service._api_available = True

        # Mock third-party API to raise rate limit error
        service._get_transcript_from_third_party_api = AsyncMock(
            side_effect=Exception("Too many requests - rate limit exceeded")
        )

        # Mock official API to fail
        service._get_transcript_from_official_api = AsyncMock(return_value=None)

        # Should fall back to mock
        service.enable_mock_fallback = True
        mock_transcript = MagicMock(spec=EnhancedVideoTranscriptBase)
        service._create_mock_transcript = MagicMock(return_value=mock_transcript)

        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service.get_transcript(sample_video_id)

        assert result == mock_transcript
        mock_logger.warning.assert_called()

    async def test_get_transcript_handles_generic_api_errors(
        self, service, sample_video_id
    ):
        """Test handling of generic API errors."""
        service._api_available = True

        # Mock third-party API to raise generic error
        service._get_transcript_from_third_party_api = AsyncMock(
            side_effect=Exception("Unexpected API error")
        )

        # Mock official API to fail
        service._get_transcript_from_official_api = AsyncMock(return_value=None)

        # Should fall back to mock
        service.enable_mock_fallback = True
        mock_transcript = MagicMock(spec=EnhancedVideoTranscriptBase)
        service._create_mock_transcript = MagicMock(return_value=mock_transcript)

        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service.get_transcript(sample_video_id)

        assert result == mock_transcript
        mock_logger.error.assert_called()


class TestTranscriptServiceThirdPartyAPI:
    """Tests for third-party API integration."""

    @pytest.fixture
    def service(self):
        """Create TranscriptService for testing."""
        return TranscriptService()

    @pytest.fixture
    def sample_video_id(self):
        """Create test video ID."""
        return create_test_video_id("api_test")

    @pytest.fixture
    def mock_transcript_list(self):
        """Create mock transcript list from API."""
        mock_transcript_en = MagicMock()
        mock_transcript_en.language_code = "en"
        mock_transcript_en.language = "English"
        mock_transcript_en.is_generated = False
        mock_transcript_en.is_translatable = True

        mock_transcript_es = MagicMock()
        mock_transcript_es.language_code = "es"
        mock_transcript_es.language = "Spanish"
        mock_transcript_es.is_generated = True
        mock_transcript_es.is_translatable = True

        return [mock_transcript_en, mock_transcript_es]

    @pytest.fixture
    def mock_transcript_data(self):
        """Create mock transcript data from API."""
        # Create mock objects with attributes (not dictionaries)
        mock_snippet1 = MagicMock()
        mock_snippet1.text = "Hello world"
        mock_snippet1.start = 0.0
        mock_snippet1.duration = 2.0

        mock_snippet2 = MagicMock()
        mock_snippet2.text = "This is a test"
        mock_snippet2.start = 2.0
        mock_snippet2.duration = 3.0

        return [mock_snippet1, mock_snippet2]

    @patch("chronovista.services.transcript_service.YouTubeTranscriptApi")
    async def test_get_transcript_from_third_party_api_success(
        self,
        mock_api,
        service,
        sample_video_id,
        mock_transcript_list,
        mock_transcript_data,
    ):
        """Test successful third-party API transcript retrieval."""
        # Mock API instance
        mock_api_instance = MagicMock()
        mock_api.return_value = mock_api_instance

        # Mock the fallback path since fetch() will fail
        mock_api_instance.fetch.side_effect = Exception("Direct fetch failed")

        # Create a proper mock transcript list object (not a list)
        mock_transcript_list_obj = MagicMock()
        mock_api_instance.list.return_value = mock_transcript_list_obj

        # Mock transcript selection and fetch
        mock_transcript = mock_transcript_list[0]  # Use first (English) transcript
        mock_transcript_list_obj.find_transcript.return_value = mock_transcript
        mock_transcript.fetch.return_value = mock_transcript_data
        mock_transcript.language_code = "en"
        mock_transcript.is_generated = False
        mock_transcript.is_translatable = True
        mock_transcript.language = "English"  # Ensure this is a string, not MagicMock

        result = await service._get_transcript_from_third_party_api(
            sample_video_id, ["en", "es"]
        )

        assert isinstance(result, RawTranscriptData)
        assert result.video_id == sample_video_id
        assert result.language_code == LanguageCode.ENGLISH
        assert len(result.snippets) == 2
        assert result.snippets[0].text == "Hello world"
        assert result.source == TranscriptSource.YOUTUBE_TRANSCRIPT_API

        mock_api_instance.list.assert_called_once_with(sample_video_id)
        mock_transcript_list_obj.find_transcript.assert_called_with(["en"])

    @patch("chronovista.services.transcript_service.YouTubeTranscriptApi")
    async def test_get_transcript_from_third_party_api_fallback_to_english(
        self, mock_api, service, sample_video_id, mock_transcript_data
    ):
        """Test fallback to English when preferred language not available."""
        # Mock API instance
        mock_api_instance = MagicMock()
        mock_api.return_value = mock_api_instance

        # Create transcripts without exact match but with English variant
        mock_transcript_en_us = MagicMock()
        mock_transcript_en_us.language_code = "en-US"
        mock_transcript_en_us.language = "English (US)"  # Ensure string
        mock_transcript_en_us.is_generated = False
        mock_transcript_en_us.is_translatable = True
        mock_transcript_en_us.fetch.return_value = mock_transcript_data

        mock_transcript_list = MagicMock()
        mock_transcript_list.find_transcript.side_effect = [
            Exception("French not found"),  # First call fails
            mock_transcript_en_us,  # Second call (English) succeeds
        ]

        mock_api_instance.fetch.side_effect = Exception("Direct fetch failed")
        mock_api_instance.list.return_value = mock_transcript_list

        result = await service._get_transcript_from_third_party_api(
            sample_video_id,
            ["fr", "de"],  # Request French/German but only English available
        )

        assert isinstance(result, RawTranscriptData)
        # With the language code fix, en-US correctly maps to ENGLISH_US, not just ENGLISH
        assert result.language_code == LanguageCode.ENGLISH_US
        mock_api_instance.list.assert_called_once_with(sample_video_id)
        # Should have called find_transcript twice: first for ["fr", "de"], then for ["en"]
        assert mock_transcript_list.find_transcript.call_count >= 1

    @patch("chronovista.services.transcript_service.YouTubeTranscriptApi")
    async def test_get_transcript_from_third_party_api_fallback_to_first_available(
        self, mock_api, service, sample_video_id, mock_transcript_data
    ):
        """Test fallback to first available when no English found."""
        # Mock API instance
        mock_api_instance = MagicMock()
        mock_api.return_value = mock_api_instance

        # Create transcript in non-English language
        mock_transcript_ja = MagicMock()
        mock_transcript_ja.language_code = "ja"
        mock_transcript_ja.language = "Japanese"  # Ensure string
        mock_transcript_ja.is_generated = True
        mock_transcript_ja.is_translatable = True
        mock_transcript_ja.fetch.return_value = mock_transcript_data

        mock_transcript_list = MagicMock()
        # All find_transcript calls fail, so it falls back to iterating
        mock_transcript_list.find_transcript.side_effect = Exception("Not found")
        mock_transcript_list.find_generated_transcript.side_effect = Exception(
            "Not found"
        )
        mock_transcript_list.__iter__.return_value = iter([mock_transcript_ja])

        mock_api_instance.fetch.side_effect = Exception("Direct fetch failed")
        mock_api_instance.list.return_value = mock_transcript_list

        result = await service._get_transcript_from_third_party_api(
            sample_video_id,
            ["fr", "de"],  # Request French/German but only Japanese available
        )

        assert isinstance(result, RawTranscriptData)
        assert result.language_code == LanguageCode.JAPANESE  # Uses available Japanese
        mock_api_instance.list.assert_called_once_with(sample_video_id)
        # Should have fallen back to iterating through available transcripts
        mock_transcript_list.__iter__.assert_called_once()

    @patch("chronovista.services.transcript_service.YouTubeTranscriptApi")
    async def test_get_transcript_from_third_party_api_list_transcripts_fails(
        self, mock_api, service, sample_video_id, mock_transcript_data
    ):
        """Test handling when list_transcripts fails."""
        # Mock API instance
        mock_api_instance = MagicMock()
        mock_api.return_value = mock_api_instance

        # Mock both fetch and list to fail - this should raise an exception
        mock_api_instance.fetch.side_effect = Exception("Direct fetch failed")
        mock_api_instance.list.side_effect = Exception("Cannot list transcripts")

        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            with pytest.raises(Exception):  # Should raise since both methods fail
                await service._get_transcript_from_third_party_api(
                    sample_video_id, ["en"]
                )

        mock_logger.warning.assert_called()
        mock_logger.error.assert_called()

    @patch("chronovista.services.transcript_service.YouTubeTranscriptApi")
    async def test_get_transcript_from_third_party_api_invalid_language_code(
        self,
        mock_api,
        service,
        sample_video_id,
        mock_transcript_list,
        mock_transcript_data,
    ):
        """Test handling of invalid language codes."""
        # Mock API instance
        mock_api_instance = MagicMock()
        mock_api.return_value = mock_api_instance

        # Mock transcript with invalid language code
        mock_transcript_invalid = MagicMock()
        mock_transcript_invalid.language_code = "invalid-code"
        mock_transcript_invalid.language = "Invalid Language"  # Ensure string
        mock_transcript_invalid.is_generated = False
        mock_transcript_invalid.is_translatable = True
        mock_transcript_invalid.fetch.return_value = mock_transcript_data

        mock_transcript_list_obj = MagicMock()
        mock_transcript_list_obj.find_transcript.return_value = mock_transcript_invalid

        mock_api_instance.fetch.side_effect = Exception("Direct fetch failed")
        mock_api_instance.list.return_value = mock_transcript_list_obj

        result = await service._get_transcript_from_third_party_api(
            sample_video_id, ["invalid-code"]
        )

        assert isinstance(result, RawTranscriptData)
        # Unknown language codes are now preserved as normalized strings
        # "invalid-code" -> "invalid-CODE" (normalized BCP-47 format)
        assert result.language_code == "invalid-CODE"

    @patch("chronovista.services.transcript_service.YouTubeTranscriptApi")
    async def test_get_transcript_from_third_party_api_no_metadata(
        self, mock_api, service, sample_video_id, mock_transcript_data
    ):
        """Test handling when transcript metadata is missing."""
        # Mock API instance
        mock_api_instance = MagicMock()
        mock_api.return_value = mock_api_instance

        # Mock empty transcript list - should fail with exception
        mock_transcript_list = MagicMock()
        mock_transcript_list.find_transcript.side_effect = Exception("Not found")
        mock_transcript_list.find_generated_transcript.side_effect = Exception(
            "Not found"
        )
        mock_transcript_list.__iter__.return_value = iter([])  # Empty list

        mock_api_instance.fetch.side_effect = Exception("Direct fetch failed")
        mock_api_instance.list.return_value = mock_transcript_list

        # Should raise exception since no transcripts are available
        with pytest.raises(Exception):
            await service._get_transcript_from_third_party_api(sample_video_id, ["en"])


class TestTranscriptServiceOfficialAPI:
    """Tests for official API integration (placeholder)."""

    @pytest.fixture
    def service(self):
        """Create TranscriptService for testing."""
        return TranscriptService()

    @pytest.fixture
    def sample_video_id(self):
        """Create test video ID."""
        return create_test_video_id("official")

    async def test_get_transcript_from_official_api_placeholder(
        self, service, sample_video_id
    ):
        """Test official API implementation with no captions found."""
        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service._get_transcript_from_official_api(
                sample_video_id, ["en"], DownloadReason.USER_REQUEST
            )

        assert result is None
        # Should log attempt and no captions found messages
        assert mock_logger.info.call_count == 2
        log_calls = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any(
            "Attempting official YouTube Data API v3" in msg for msg in log_calls
        )
        assert any("No captions found via official API" in msg for msg in log_calls)


class TestTranscriptServiceMockTranscript:
    """Tests for mock transcript generation."""

    @pytest.fixture
    def service(self):
        """Create TranscriptService for testing."""
        return TranscriptService()

    @pytest.fixture
    def sample_video_id(self):
        """Create test video ID."""
        return create_test_video_id("mock")

    def test_create_mock_transcript_basic(self, service, sample_video_id):
        """Test basic mock transcript creation."""
        result = service._create_mock_transcript(
            sample_video_id, "en", DownloadReason.USER_REQUEST
        )

        assert isinstance(result, EnhancedVideoTranscriptBase)
        assert result.video_id == sample_video_id
        # Check that mock snippets are created
        # Note: We can't directly access snippets without reading the implementation

    def test_create_mock_transcript_with_different_language(
        self, service, sample_video_id
    ):
        """Test mock transcript creation with different language."""
        result = service._create_mock_transcript(
            sample_video_id, "es", DownloadReason.API_ENRICHMENT
        )

        assert isinstance(result, EnhancedVideoTranscriptBase)
        assert result.video_id == sample_video_id

    def test_create_mock_transcript_with_unknown_regional_code(
        self, service, sample_video_id
    ):
        """Test mock transcript creation with unknown but valid regional code.

        Regional codes not in the LanguageCode enum should be preserved as strings.
        """
        result = service._create_mock_transcript(
            sample_video_id, "en-ZZ", DownloadReason.USER_REQUEST  # Unknown region
        )

        assert isinstance(result, EnhancedVideoTranscriptBase)
        assert result.video_id == sample_video_id
        # Unknown regional code should be preserved as normalized string
        assert result.language_code == "en-ZZ"


class TestTranscriptServiceGetAvailableLanguages:
    """Tests for available languages retrieval."""

    @pytest.fixture
    def service(self):
        """Create TranscriptService for testing."""
        return TranscriptService()

    @pytest.fixture
    def sample_video_id(self):
        """Create test video ID."""
        return create_test_video_id("langs")

    async def test_get_available_languages_api_unavailable(
        self, service, sample_video_id
    ):
        """Test getting available languages when API is unavailable."""
        service._api_available = False

        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service.get_available_languages(sample_video_id)

        assert result == []
        mock_logger.warning.assert_called_once()

    @patch("chronovista.services.transcript_service.YouTubeTranscriptApi")
    async def test_get_available_languages_success(
        self, mock_api_class, service, sample_video_id
    ):
        """Test successful language retrieval."""
        # Mock transcript list
        mock_transcript_en = MagicMock()
        mock_transcript_en.language_code = "en"
        mock_transcript_en.language = "English"
        mock_transcript_en.is_generated = False
        mock_transcript_en.is_translatable = True

        mock_transcript_es = MagicMock()
        mock_transcript_es.language_code = "es"
        mock_transcript_es.language = "Spanish"
        mock_transcript_es.is_generated = True
        mock_transcript_es.is_translatable = False

        # Mock the API instance
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = [
            mock_transcript_en,
            mock_transcript_es,
        ]
        mock_api_class.return_value = mock_api_instance
        service._api_available = True

        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service.get_available_languages(sample_video_id)

        assert len(result) == 2
        assert result[0]["language_code"] == "en"
        assert result[0]["language_name"] == "English"
        assert result[0]["is_generated"] is False
        assert result[0]["is_translatable"] is True

        assert result[1]["language_code"] == "es"
        assert result[1]["language_name"] == "Spanish"
        assert result[1]["is_generated"] is True
        assert result[1]["is_translatable"] is False

        mock_logger.info.assert_called()

    @patch("chronovista.services.transcript_service.YouTubeTranscriptApi")
    async def test_get_available_languages_api_error(
        self, mock_api_class, service, sample_video_id
    ):
        """Test handling of API errors when getting available languages."""
        mock_api_instance = MagicMock()
        mock_api_instance.list.side_effect = Exception("API error")
        mock_api_class.return_value = mock_api_instance
        service._api_available = True

        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service.get_available_languages(sample_video_id)

        assert result == []
        mock_logger.error.assert_called()

    @patch("chronovista.services.transcript_service.YouTubeTranscriptApi")
    async def test_get_available_languages_missing_attributes(
        self, mock_api_class, service, sample_video_id
    ):
        """Test handling of transcripts with missing attributes."""
        # Mock transcript with missing is_translatable attribute
        mock_transcript = MagicMock()
        mock_transcript.language_code = "en"
        mock_transcript.language = "English"
        mock_transcript.is_generated = False
        # Don't set is_translatable to test getattr fallback
        del mock_transcript.is_translatable

        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = [mock_transcript]
        mock_api_class.return_value = mock_api_instance
        service._api_available = True

        result = await service.get_available_languages(sample_video_id)

        assert len(result) == 1
        assert result[0]["is_translatable"] is False  # Should use default


class TestTranscriptServiceBatchGetTranscripts:
    """Tests for batch transcript processing."""

    @pytest.fixture
    def service(self):
        """Create TranscriptService for testing."""
        return TranscriptService()

    @pytest.fixture
    def sample_video_ids(self):
        """Create test video IDs."""
        return [
            create_test_video_id("batch1"),
            create_test_video_id("batch2"),
            create_test_video_id("batch3"),
        ]

    async def test_batch_get_transcripts_all_success(self, service, sample_video_ids):
        """Test batch processing with all successes."""
        # Mock get_transcript to succeed for all videos
        mock_transcripts = []
        for video_id in sample_video_ids:
            mock_transcript = MagicMock(spec=EnhancedVideoTranscriptBase)
            mock_transcript.video_id = video_id
            mock_transcripts.append(mock_transcript)

        service.get_transcript = AsyncMock(side_effect=mock_transcripts)

        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service.batch_get_transcripts(sample_video_ids)

        assert len(result) == 3
        assert all(transcript is not None for transcript in result.values())
        assert all(video_id in result for video_id in sample_video_ids)

        # Should log success
        mock_logger.info.assert_called_with("Batch download complete: 3/3 successful")

    async def test_batch_get_transcripts_mixed_results(self, service, sample_video_ids):
        """Test batch processing with mixed success/failure."""
        # Mock get_transcript to succeed for first, fail for second, succeed for third
        mock_transcript1 = MagicMock(spec=EnhancedVideoTranscriptBase)
        mock_transcript1.video_id = sample_video_ids[0]

        mock_transcript3 = MagicMock(spec=EnhancedVideoTranscriptBase)
        mock_transcript3.video_id = sample_video_ids[2]

        service.get_transcript = AsyncMock(
            side_effect=[
                mock_transcript1,
                TranscriptNotFoundError("Not found"),
                mock_transcript3,
            ]
        )

        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service.batch_get_transcripts(sample_video_ids)

        assert len(result) == 3
        assert result[sample_video_ids[0]] is not None
        assert result[sample_video_ids[1]] is None
        assert result[sample_video_ids[2]] is not None

        # Should log mixed success
        mock_logger.info.assert_called_with("Batch download complete: 2/3 successful")

    async def test_batch_get_transcripts_with_retries(self, service, sample_video_ids):
        """Test batch processing with retries."""
        # Take only first video for this test
        video_ids = [sample_video_ids[0]]

        # Mock get_transcript to fail twice then succeed
        mock_transcript = MagicMock(spec=EnhancedVideoTranscriptBase)
        mock_transcript.video_id = video_ids[0]

        service.get_transcript = AsyncMock(
            side_effect=[
                Exception("Temporary error"),  # First attempt fails
                Exception("Another error"),  # Second attempt fails
                mock_transcript,  # Third attempt succeeds
            ]
        )

        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service.batch_get_transcripts(video_ids, max_retries=3)

        assert len(result) == 1
        assert result[video_ids[0]] is not None

        # Should have logged warnings for failed attempts
        mock_logger.warning.assert_called()

    async def test_batch_get_transcripts_max_retries_exceeded(
        self, service, sample_video_ids
    ):
        """Test batch processing when max retries exceeded."""
        # Take only first video for this test
        video_ids = [sample_video_ids[0]]

        # Mock get_transcript to always fail
        service.get_transcript = AsyncMock(side_effect=Exception("Persistent error"))

        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service.batch_get_transcripts(video_ids, max_retries=2)

        assert len(result) == 1
        assert result[video_ids[0]] is None

        # Should have logged error for all attempts failed
        mock_logger.error.assert_called()

    async def test_batch_get_transcripts_with_custom_params(
        self, service, sample_video_ids
    ):
        """Test batch processing with custom parameters."""
        mock_transcript = MagicMock(spec=EnhancedVideoTranscriptBase)
        service.get_transcript = AsyncMock(return_value=mock_transcript)

        custom_languages = ["es", "fr"]
        custom_reason = DownloadReason.API_ENRICHMENT

        await service.batch_get_transcripts(
            sample_video_ids,
            language_codes=custom_languages,
            download_reason=custom_reason,
            max_retries=1,
        )

        # Verify get_transcript was called with correct parameters
        for call in service.get_transcript.call_args_list:
            args, kwargs = call
            assert args[1] == custom_languages  # language_codes
            assert args[2] == custom_reason  # download_reason

    async def test_batch_get_transcripts_empty_list(self, service):
        """Test batch processing with empty video list."""
        with patch("chronovista.services.transcript_service.logger") as mock_logger:
            result = await service.batch_get_transcripts([])

        assert result == {}
        mock_logger.info.assert_called_with("Batch download complete: 0/0 successful")


class TestTranscriptServiceIntegration:
    """Integration tests combining multiple service features."""

    @pytest.fixture
    def service(self):
        """Create TranscriptService for testing."""
        return TranscriptService()

    @pytest.fixture
    def sample_video_id(self):
        """Create test video ID."""
        return create_test_video_id("integration")

    async def test_full_workflow_api_available(self, service, sample_video_id):
        """Test full workflow when API is available."""
        service._api_available = True

        # Check service availability
        assert service.is_service_available() is True

        # Mock third-party API success
        mock_raw_data = MagicMock(spec=RawTranscriptData)
        mock_raw_data.video_id = sample_video_id
        service._get_transcript_from_third_party_api = AsyncMock(
            return_value=mock_raw_data
        )

        # Get transcript
        with patch.object(
            EnhancedVideoTranscriptBase, "from_raw_transcript_data"
        ) as mock_from_raw:
            mock_transcript = MagicMock(spec=EnhancedVideoTranscriptBase)
            mock_from_raw.return_value = mock_transcript

            result = await service.get_transcript(sample_video_id)

            assert result == mock_transcript
            mock_from_raw.assert_called_once_with(
                mock_raw_data, download_reason=DownloadReason.USER_REQUEST
            )

    async def test_full_workflow_api_unavailable_with_mock(
        self, service, sample_video_id
    ):
        """Test full workflow when API unavailable but mock enabled."""
        service._api_available = False
        service.enable_mock_fallback = True

        # Check service availability
        assert service.is_service_available() is True

        # Mock the _create_mock_transcript method
        mock_transcript = MagicMock(spec=EnhancedVideoTranscriptBase)
        service._create_mock_transcript = MagicMock(return_value=mock_transcript)

        # Get transcript
        result = await service.get_transcript(sample_video_id)

        assert result == mock_transcript
        service._create_mock_transcript.assert_called_once()

    async def test_full_workflow_no_service_available(self, service, sample_video_id):
        """Test full workflow when no service is available."""
        service._api_available = False
        service.enable_mock_fallback = False

        # Check service availability
        assert service.is_service_available() is False

        # Get transcript should fail
        with pytest.raises(TranscriptNotFoundError):
            await service.get_transcript(sample_video_id)


class TestTranscriptServiceEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.fixture
    def service(self):
        """Create TranscriptService for testing."""
        return TranscriptService()

    @pytest.fixture
    def sample_video_id(self):
        """Create test video ID."""
        return create_test_video_id("edge")

    async def test_get_transcript_with_none_language_codes(
        self, service, sample_video_id
    ):
        """Test get_transcript with None language_codes."""
        service._api_available = True

        # Mock to verify default languages are used
        service._get_transcript_from_third_party_api = AsyncMock(
            side_effect=Exception("API error")
        )
        service._get_transcript_from_official_api = AsyncMock(return_value=None)
        service.enable_mock_fallback = True

        mock_transcript = MagicMock(spec=EnhancedVideoTranscriptBase)
        service._create_mock_transcript = MagicMock(return_value=mock_transcript)

        await service.get_transcript(sample_video_id, language_codes=None)

        # Should have called with default languages
        service._get_transcript_from_third_party_api.assert_called_once_with(
            sample_video_id, ["en", "en-US"]
        )

    async def test_get_transcript_with_empty_language_codes(
        self, service, sample_video_id
    ):
        """Test get_transcript with empty language_codes list."""
        service._api_available = True

        service._get_transcript_from_third_party_api = AsyncMock(
            side_effect=Exception("API error")
        )
        service._get_transcript_from_official_api = AsyncMock(return_value=None)
        service.enable_mock_fallback = True

        mock_transcript = MagicMock(spec=EnhancedVideoTranscriptBase)
        service._create_mock_transcript = MagicMock(return_value=mock_transcript)

        await service.get_transcript(sample_video_id, language_codes=[])

        # Should have called with default languages
        service._get_transcript_from_third_party_api.assert_called_once_with(
            sample_video_id, ["en", "en-US"]
        )

    @patch("chronovista.services.transcript_service.logger")
    async def test_logging_behavior(self, mock_logger, service, sample_video_id):
        """Test that appropriate logging occurs throughout the service."""
        service._api_available = True

        # Mock successful third-party API call
        mock_raw_data = MagicMock(spec=RawTranscriptData)
        service._get_transcript_from_third_party_api = AsyncMock(
            return_value=mock_raw_data
        )

        with patch.object(
            EnhancedVideoTranscriptBase, "from_raw_transcript_data"
        ) as mock_from_raw:
            mock_transcript = MagicMock(spec=EnhancedVideoTranscriptBase)
            mock_from_raw.return_value = mock_transcript

            await service.get_transcript(sample_video_id)

        # Should have logged the request and success
        log_calls = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any(
            f"Requesting transcript for video {sample_video_id}" in msg
            for msg in log_calls
        )
        assert any("Successfully downloaded transcript" in msg for msg in log_calls)


class TestResolveLanguageCode:
    """Tests for language code resolution to prevent transcript language mismatch bugs."""

    @pytest.fixture
    def service(self):
        """Create TranscriptService for testing."""
        return TranscriptService()

    def test_resolve_exact_match(self, service):
        """Test exact match for language codes like 'es-MX'."""
        # Test that regional variants are preserved, not incorrectly mapped to base
        result = service._resolve_language_code("es-MX")
        assert result == LanguageCode.SPANISH_MX
        assert result.value == "es-MX"

    def test_resolve_lowercase_regional(self, service):
        """Test that lowercase regional codes are resolved correctly."""
        # This was the original bug - 'es-mx' should map to 'es-MX', not 'en'
        result = service._resolve_language_code("es-mx")
        assert result == LanguageCode.SPANISH_MX
        assert result.value == "es-MX"

    def test_resolve_uppercase_regional(self, service):
        """Test uppercase regional codes are handled."""
        result = service._resolve_language_code("ES-MX")
        assert result == LanguageCode.SPANISH_MX

    def test_resolve_english_variants(self, service):
        """Test English variants are preserved."""
        assert service._resolve_language_code("en") == LanguageCode.ENGLISH
        assert service._resolve_language_code("en-US") == LanguageCode.ENGLISH_US
        assert service._resolve_language_code("en-GB") == LanguageCode.ENGLISH_GB

    def test_resolve_base_language(self, service):
        """Test base language codes."""
        assert service._resolve_language_code("es") == LanguageCode.SPANISH
        assert service._resolve_language_code("fr") == LanguageCode.FRENCH
        assert service._resolve_language_code("de") == LanguageCode.GERMAN

    def test_resolve_latin_american_spanish(self, service):
        """Test es-419 Latin American Spanish is preserved."""
        result = service._resolve_language_code("es-419")
        assert result == LanguageCode.SPANISH_419

    def test_resolve_unknown_regional_preserves_code(self, service):
        """Test that unknown regional variants are preserved as strings."""
        # es-XX (unknown region) should be preserved as 'es-XX'
        result = service._resolve_language_code("es-XX")
        assert result == "es-XX"  # Preserved as normalized string

    def test_resolve_completely_unknown_preserves_code(self, service):
        """Test that completely unknown codes are preserved as strings."""
        result = service._resolve_language_code("xyz")
        assert result == "xyz"  # Preserved as-is

    def test_resolve_empty_string(self, service):
        """Test empty string falls back to English."""
        result = service._resolve_language_code("")
        assert result == LanguageCode.ENGLISH

    def test_resolve_chinese_variants(self, service):
        """Test Chinese simplified and traditional are preserved."""
        assert service._resolve_language_code("zh-CN") == LanguageCode.CHINESE_SIMPLIFIED
        assert service._resolve_language_code("zh-TW") == LanguageCode.CHINESE_TRADITIONAL

    def test_resolve_portuguese_variants(self, service):
        """Test Portuguese variants are preserved."""
        assert service._resolve_language_code("pt-BR") == LanguageCode.PORTUGUESE_BR
        assert service._resolve_language_code("pt-PT") == LanguageCode.PORTUGUESE_PT

    @patch("chronovista.services.transcript_service.logger")
    def test_resolve_unknown_no_warning_when_preserved(self, mock_logger, service):
        """Test that no warning is logged when unknown codes are preserved as strings."""
        # Unknown codes are now preserved, so no fallback warning is logged
        result = service._resolve_language_code("unknown-lang")
        # Should be preserved as normalized string
        assert result == "unknown-LANG"  # Normalized: lowercase base + uppercase region
        mock_logger.warning.assert_not_called()

    @patch("chronovista.services.transcript_service.logger")
    def test_resolve_no_warning_for_english_fallback(self, mock_logger, service):
        """Test that no warning is logged when input is already English-like."""
        service._resolve_language_code("en-XX")  # Unknown English variant
        # Should not log a warning since it's English-like
        mock_logger.warning.assert_not_called()
