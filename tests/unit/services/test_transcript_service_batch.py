"""
Unit tests for TranscriptService.get_transcripts_for_languages() and
TranscriptService._convert_fetched_to_raw_data().

Tests exercise the optimised batch-fetch path introduced in GitHub issue #109.
The method calls ``api.list()`` exactly once per video, then fetches or
translates each requested language individually — reducing API round-trips
from O(N) to 1 + O(fetches).

No real network or database connections are required; all youtube-transcript-api
objects are replaced with MagicMock/AsyncMock stand-ins.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# CRITICAL: Module-level asyncio marker ensures async tests execute (not skip)
# when running under pytest-cov. See CLAUDE.md § pytest-asyncio Coverage.
from chronovista.models.enums import DownloadReason
from chronovista.models.transcript_source import (
    RawTranscriptData,
    TranscriptSnippet,
    TranscriptSource,
)
from chronovista.models.video_transcript import EnhancedVideoTranscriptBase
from chronovista.models.youtube_types import create_test_video_id
from chronovista.services.transcript_service import (
    TranscriptNotFoundError,
    TranscriptService,
    TranscriptServiceUnavailableError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VIDEO_ID = create_test_video_id("batch")


def _make_snippet_mock(text: str = "Hello world", start: float = 0.0, duration: float = 2.0) -> MagicMock:
    """Return a mock FetchedTranscript snippet (has .text, .start, .duration)."""
    s = MagicMock()
    s.text = text
    s.start = start
    s.duration = duration
    return s


def _make_fetched_transcript(
    snippets: list[MagicMock] | None = None,
) -> MagicMock:
    """Return a mock FetchedTranscript that is iterable over snippet mocks."""
    fetched = MagicMock()
    if snippets is None:
        snippets = [_make_snippet_mock()]
    # Make the mock iterable so ``for snippet in fetched`` works.
    fetched.__iter__ = MagicMock(return_value=iter(snippets))
    return fetched


def _make_transcript_mock(
    language_code: str = "en",
    language: str = "English",
    is_generated: bool = False,
    is_translatable: bool = True,
    translation_languages: list[dict[str, str]] | None = None,
    fetch_snippets: list[MagicMock] | None = None,
) -> MagicMock:
    """Return a mock youtube-transcript-api Transcript object."""
    t = MagicMock()
    t.language_code = language_code
    t.language = language
    t.is_generated = is_generated
    t.is_translatable = is_translatable
    t.translation_languages = translation_languages or []
    t.fetch = MagicMock(return_value=_make_fetched_transcript(fetch_snippets))
    return t


def _make_transcript_list(transcripts: list[MagicMock]) -> MagicMock:
    """Return a mock TranscriptList that iterates over the given transcripts."""
    tl = MagicMock()
    tl.__iter__ = MagicMock(return_value=iter(transcripts))
    return tl


def _service_with_api() -> TranscriptService:
    """Return a TranscriptService whose ``_api_available`` flag is True."""
    service = TranscriptService()
    service._api_available = True
    return service


def _service_without_api() -> TranscriptService:
    """Return a TranscriptService whose ``_api_available`` flag is False."""
    service = TranscriptService()
    service._api_available = False
    return service


# ---------------------------------------------------------------------------
# TestGetTranscriptsForLanguages
# ---------------------------------------------------------------------------


class TestGetTranscriptsForLanguages:
    """Tests for TranscriptService.get_transcripts_for_languages()."""

    # ------------------------------------------------------------------
    # Empty input guard
    # ------------------------------------------------------------------

    async def test_empty_language_codes_returns_empty_dict(self) -> None:
        """Returns an empty dict immediately without calling any API when language_codes is empty."""
        service = _service_with_api()

        mock_api_instance = MagicMock()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=[],
            )

        assert result == {}
        mock_api_instance.list.assert_not_called()

    # ------------------------------------------------------------------
    # All languages available natively
    # ------------------------------------------------------------------

    async def test_all_languages_available_natively(self) -> None:
        """Each requested language that has a native transcript calls fetch() once."""
        en_snippets = [_make_snippet_mock("Hello", 0.0, 2.0)]
        es_snippets = [_make_snippet_mock("Hola", 0.5, 1.5)]

        en_transcript = _make_transcript_mock(
            language_code="en", language="English", fetch_snippets=en_snippets
        )
        es_transcript = _make_transcript_mock(
            language_code="es", language="Spanish", fetch_snippets=es_snippets
        )

        transcript_list = _make_transcript_list([en_transcript, es_transcript])

        service = _service_with_api()
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es"],
            )

        # api.list() called exactly once
        mock_api_instance.list.assert_called_once_with(VIDEO_ID)

        # Both languages should have a non-None transcript
        assert "en" in result
        assert "es" in result
        assert result["en"] is not None
        assert result["es"] is not None
        assert isinstance(result["en"], EnhancedVideoTranscriptBase)
        assert isinstance(result["es"], EnhancedVideoTranscriptBase)

        # fetch() called once per native language
        en_transcript.fetch.assert_called_once()
        es_transcript.fetch.assert_called_once()

    # ------------------------------------------------------------------
    # Some languages available only via translation
    # ------------------------------------------------------------------

    async def test_translation_used_when_no_native(self) -> None:
        """Languages without a native transcript are fetched via translation."""
        en_transcript = _make_transcript_mock(
            language_code="en",
            language="English",
            is_generated=False,
            is_translatable=True,
        )

        # translated_fr is what translate("fr") returns
        translated_fr = _make_transcript_mock(
            language_code="fr",
            language="French",
            is_generated=False,
            is_translatable=False,
            fetch_snippets=[_make_snippet_mock("Bonjour", 0.0, 1.0)],
        )
        en_transcript.translate = MagicMock(return_value=translated_fr)

        transcript_list = _make_transcript_list([en_transcript])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "fr"],
                include_translations=True,
            )

        # en fetched natively; fr fetched via translation
        en_transcript.fetch.assert_called_once()
        en_transcript.translate.assert_called_once_with("fr")
        translated_fr.fetch.assert_called_once()

        assert result["en"] is not None
        assert result["fr"] is not None
        assert isinstance(result["fr"], EnhancedVideoTranscriptBase)

    # ------------------------------------------------------------------
    # No languages available (not translatable)
    # ------------------------------------------------------------------

    async def test_no_languages_available_all_none(self) -> None:
        """When only English is available and not translatable, other languages return None."""
        en_transcript = _make_transcript_mock(
            language_code="en",
            language="English",
            is_translatable=False,
        )
        transcript_list = _make_transcript_list([en_transcript])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["es", "fr", "de"],
            )

        # api.list() called exactly once — no per-language fallback calls
        mock_api_instance.list.assert_called_once_with(VIDEO_ID)

        assert result["es"] is None
        assert result["fr"] is None
        assert result["de"] is None

        # en_transcript.fetch should NOT have been called (not requested)
        en_transcript.fetch.assert_not_called()

    # ------------------------------------------------------------------
    # Mixed: native + translation + unavailable
    # ------------------------------------------------------------------

    async def test_mixed_native_translation_and_unavailable(self) -> None:
        """Correctly categorises 4 requested languages: 1 native, 1 via translation, 2 via failed translation.

        When a translation_source exists, the implementation attempts translate() for
        every non-native language. If that call itself raises (e.g. YouTube rejects the
        translation), the language maps to None. Languages with no native transcript AND
        no translation_source at all (because no translatable transcript exists) also map
        to None — tested separately in test_no_languages_available_all_none.

        This test covers the case where translation is attempted but raises for one
        language ("ja") while succeeding for another ("es").
        """
        en_transcript = _make_transcript_mock(
            language_code="en",
            language="English",
            is_generated=False,
            is_translatable=True,
            fetch_snippets=[_make_snippet_mock("Hello", 0.0, 2.0)],
        )
        it_transcript = _make_transcript_mock(
            language_code="it",
            language="Italian",
            is_generated=False,
            is_translatable=False,
            fetch_snippets=[_make_snippet_mock("Ciao", 0.0, 1.5)],
        )

        # Translated Spanish from English succeeds
        translated_es = _make_transcript_mock(
            language_code="es",
            language="Spanish",
            is_generated=False,
            is_translatable=False,
            fetch_snippets=[_make_snippet_mock("Hola", 0.0, 1.0)],
        )

        # Japanese translation fails — YouTube rejects the request
        def _translate_side_effect(lang: str) -> MagicMock:
            if lang == "es":
                return translated_es
            raise Exception("no translation available for ja")

        en_transcript.translate = MagicMock(side_effect=_translate_side_effect)

        transcript_list = _make_transcript_list([en_transcript, it_transcript])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es", "it", "ja"],
                include_translations=True,
            )

        assert result["en"] is not None   # native
        assert result["es"] is not None   # translated successfully
        assert result["it"] is not None   # native
        assert result["ja"] is None       # translation attempted but failed

        en_transcript.fetch.assert_called_once()
        it_transcript.fetch.assert_called_once()
        assert en_transcript.translate.call_count == 2  # called for both "es" and "ja"
        translated_es.fetch.assert_called_once()

    # ------------------------------------------------------------------
    # api.list() fails — falls back to per-language get_transcript()
    # ------------------------------------------------------------------

    async def test_api_list_failure_falls_back_to_per_language(self) -> None:
        """When api.list() raises, the method falls back to per-language get_transcript() calls."""
        service = _service_with_api()

        mock_api_instance = MagicMock()
        mock_api_instance.list.side_effect = RuntimeError("Network error")

        # Mock get_transcript to return a plausible transcript for 'en' and raise for 'fr'
        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            if language_codes and language_codes[0] == "en":
                raw = _build_minimal_raw_data(video_id, "en")
                return EnhancedVideoTranscriptBase.from_raw_transcript_data(
                    raw, download_reason=download_reason
                )
            raise TranscriptNotFoundError("Not found")

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "fr"],
            )

        mock_api_instance.list.assert_called_once()
        assert result["en"] is not None
        assert result["fr"] is None

    # ------------------------------------------------------------------
    # Individual fetch() raises — that language becomes None, others succeed
    # ------------------------------------------------------------------

    async def test_individual_fetch_failure_returns_none_for_that_language(self) -> None:
        """When a specific language's .fetch() raises, it maps to None while others succeed."""
        en_transcript = _make_transcript_mock(
            language_code="en",
            language="English",
            fetch_snippets=[_make_snippet_mock("Hello", 0.0, 2.0)],
        )
        # es transcript fetch raises
        es_transcript = _make_transcript_mock(
            language_code="es",
            language="Spanish",
        )
        es_transcript.fetch.side_effect = Exception("transcript disabled")

        transcript_list = _make_transcript_list([en_transcript, es_transcript])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es"],
            )

        assert result["en"] is not None
        assert result["es"] is None

    # ------------------------------------------------------------------
    # API unavailable — falls back to per-language get_transcript()
    # ------------------------------------------------------------------

    async def test_api_unavailable_falls_back_to_per_language(self) -> None:
        """When _api_available is False, method falls back to per-language get_transcript() calls."""
        service = _service_without_api()

        call_log: list[str] = []

        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            lang = (language_codes or ["en"])[0]
            call_log.append(lang)
            raw = _build_minimal_raw_data(video_id, lang)
            return EnhancedVideoTranscriptBase.from_raw_transcript_data(
                raw, download_reason=download_reason
            )

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        result = await service.get_transcripts_for_languages(
            video_id=VIDEO_ID,
            language_codes=["en", "es"],
        )

        # One get_transcript call per language
        assert call_log == ["en", "es"]
        assert result["en"] is not None
        assert result["es"] is not None

    async def test_api_unavailable_transcript_not_found_records_none(self) -> None:
        """Languages that raise TranscriptNotFoundError in fallback path are mapped to None."""
        service = _service_without_api()

        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            raise TranscriptNotFoundError("No transcript")

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        result = await service.get_transcripts_for_languages(
            video_id=VIDEO_ID,
            language_codes=["de", "ja"],
        )

        assert result["de"] is None
        assert result["ja"] is None

    # ------------------------------------------------------------------
    # Translation source preference: manual over auto-generated
    # ------------------------------------------------------------------

    async def test_manual_transcript_preferred_as_translation_source(self) -> None:
        """When both manual and auto-generated transcripts exist, manual is used as translation source."""
        auto_en = _make_transcript_mock(
            language_code="en",
            language="English",
            is_generated=True,
            is_translatable=True,
        )
        manual_en = _make_transcript_mock(
            language_code="en",
            language="English",
            is_generated=False,
            is_translatable=True,
        )

        translated_fr = _make_transcript_mock(
            language_code="fr",
            language="French",
            is_generated=False,
            is_translatable=False,
            fetch_snippets=[_make_snippet_mock("Bonjour", 0.0, 1.0)],
        )
        # Only manual_en.translate is configured
        manual_en.translate = MagicMock(return_value=translated_fr)
        auto_en.translate = MagicMock(return_value=MagicMock())  # should not be called

        # native_map logic: prefer manual for duplicate language codes.
        # The implementation iterates transcript_list and keeps the non-generated
        # transcript when a duplicate code is encountered.
        # Order matters: put auto first so manual overwrites it.
        transcript_list = _make_transcript_list([auto_en, manual_en])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["fr"],
                include_translations=True,
            )

        # manual_en.translate should have been called (it is the non-generated one)
        manual_en.translate.assert_called_once_with("fr")
        auto_en.translate.assert_not_called()
        assert result["fr"] is not None

    # ------------------------------------------------------------------
    # Auto-generated fallback as translation source
    # ------------------------------------------------------------------

    async def test_auto_generated_used_as_translation_source_when_no_manual(self) -> None:
        """When no manual translatable transcript exists, auto-generated is used as translation source."""
        auto_en = _make_transcript_mock(
            language_code="en",
            language="English",
            is_generated=True,
            is_translatable=True,
        )
        translated_de = _make_transcript_mock(
            language_code="de",
            language="German",
            is_generated=True,
            is_translatable=False,
            fetch_snippets=[_make_snippet_mock("Hallo", 0.0, 1.5)],
        )
        auto_en.translate = MagicMock(return_value=translated_de)

        transcript_list = _make_transcript_list([auto_en])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["de"],
                include_translations=True,
            )

        auto_en.translate.assert_called_once_with("de")
        assert result["de"] is not None

    # ------------------------------------------------------------------
    # api.list() fallback: TranscriptNotFoundError mapped to None
    # ------------------------------------------------------------------

    async def test_api_list_fallback_transcript_not_found_maps_to_none(self) -> None:
        """After api.list() failure, per-language calls that raise TranscriptNotFoundError map to None."""
        service = _service_with_api()

        mock_api_instance = MagicMock()
        mock_api_instance.list.side_effect = Exception("quota exceeded")

        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            raise TranscriptNotFoundError("not available")

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["zh", "ar"],
            )

        assert result["zh"] is None
        assert result["ar"] is None

    # ------------------------------------------------------------------
    # Return type shape
    # ------------------------------------------------------------------

    async def test_return_value_contains_all_requested_language_codes(self) -> None:
        """Result dict always contains a key for every requested language, even if value is None."""
        en_transcript = _make_transcript_mock(
            language_code="en",
            language="English",
            is_translatable=False,
            fetch_snippets=[_make_snippet_mock()],
        )
        transcript_list = _make_transcript_list([en_transcript])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "fr", "de"],
            )

        assert set(result.keys()) == {"en", "fr", "de"}

    # ------------------------------------------------------------------
    # DownloadReason propagated to returned transcripts
    # ------------------------------------------------------------------

    async def test_download_reason_propagated_to_transcript(self) -> None:
        """The download_reason parameter is forwarded to the constructed EnhancedVideoTranscriptBase."""
        en_transcript = _make_transcript_mock(
            language_code="en",
            language="English",
            fetch_snippets=[_make_snippet_mock("Test", 0.0, 3.0)],
        )
        transcript_list = _make_transcript_list([en_transcript])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en"],
                download_reason=DownloadReason.LEARNING_LANGUAGE,
            )

        transcript = result["en"]
        assert transcript is not None
        # EnhancedVideoTranscriptBase uses use_enum_values=True, so compare to string value
        assert transcript.download_reason == DownloadReason.LEARNING_LANGUAGE.value

    # ------------------------------------------------------------------
    # Language code case-insensitive matching
    # ------------------------------------------------------------------

    async def test_language_code_matching_is_case_insensitive(self) -> None:
        """Language codes from the API are lowercased before matching the native_map."""
        # API returns "EN" (uppercase) but caller requests "en" (lowercase)
        en_transcript = _make_transcript_mock(
            language_code="EN",
            language="English",
            fetch_snippets=[_make_snippet_mock("Hello", 0.0, 2.0)],
        )
        transcript_list = _make_transcript_list([en_transcript])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en"],
            )

        assert result["en"] is not None
        en_transcript.fetch.assert_called_once()

    # ------------------------------------------------------------------
    # Exception in individual language loop with non-transcript error message
    # ------------------------------------------------------------------

    async def test_generic_exception_during_fetch_maps_to_none(self) -> None:
        """A generic (non-transcript-related) exception during fetch still results in None."""
        en_transcript = _make_transcript_mock(
            language_code="en",
            language="English",
        )
        en_transcript.fetch.side_effect = ConnectionError("network timeout")

        transcript_list = _make_transcript_list([en_transcript])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en"],
            )

        assert result["en"] is None

    # ------------------------------------------------------------------
    # api.list() single call regardless of language count
    # ------------------------------------------------------------------

    async def test_api_list_called_exactly_once_for_multiple_languages(self) -> None:
        """api.list() is called exactly once regardless of how many languages are requested."""
        en_transcript = _make_transcript_mock(
            language_code="en",
            language="English",
            is_translatable=False,
            fetch_snippets=[_make_snippet_mock()],
        )
        transcript_list = _make_transcript_list([en_transcript])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es", "fr", "de", "it", "ja", "zh"],
            )

        mock_api_instance.list.assert_called_once_with(VIDEO_ID)

    # ------------------------------------------------------------------
    # include_translations=False (default): no translation attempted
    # ------------------------------------------------------------------

    async def test_include_translations_false_non_native_language_returns_none(self) -> None:
        """When include_translations=False (default), a non-native language returns None without any translate() call."""
        en_transcript = _make_transcript_mock(
            language_code="en",
            language="English",
            is_generated=False,
            is_translatable=True,
            fetch_snippets=[_make_snippet_mock("Hello", 0.0, 2.0)],
        )
        # Spy on translate so we can assert it is never called
        en_transcript.translate = MagicMock()

        transcript_list = _make_transcript_list([en_transcript])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            # Default: include_translations=False
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "fr"],
            )

        # en native → present; fr has no native → None with no translation attempt
        assert result["en"] is not None
        assert result["fr"] is None
        en_transcript.translate.assert_not_called()

    async def test_include_translations_false_explicit_no_translate_call(self) -> None:
        """Passing include_translations=False explicitly also suppresses all translate() calls."""
        en_transcript = _make_transcript_mock(
            language_code="en",
            language="English",
            is_generated=False,
            is_translatable=True,
        )
        en_transcript.translate = MagicMock()

        transcript_list = _make_transcript_list([en_transcript])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["es", "de", "fr"],
                include_translations=False,
            )

        # All requested languages are non-native → all None, no translate() called
        assert result["es"] is None
        assert result["de"] is None
        assert result["fr"] is None
        en_transcript.translate.assert_not_called()

    async def test_include_translations_false_does_not_fetch_non_native_when_translatable_exists(self) -> None:
        """When include_translations=False, a non-native language returns None even if a translatable
        source exists — translation is never attempted.
        """
        translated_es = _make_transcript_mock(
            language_code="es",
            language="Spanish",
            is_generated=False,
            is_translatable=False,
            fetch_snippets=[_make_snippet_mock("Hola", 0.0, 1.0)],
        )
        en_transcript = _make_transcript_mock(
            language_code="en",
            language="English",
            is_generated=False,
            is_translatable=True,
            fetch_snippets=[_make_snippet_mock("Hello", 0.0, 2.0)],
        )
        en_transcript.translate = MagicMock(return_value=translated_es)

        transcript_list = _make_transcript_list([en_transcript])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es"],
                include_translations=False,
            )

        assert result["en"] is not None  # native always works
        assert result["es"] is None      # non-native is not attempted
        en_transcript.translate.assert_not_called()

    async def test_include_translations_true_fetches_non_native_via_translation(self) -> None:
        """When include_translations=True, a language without a native transcript is fetched
        via translation and returns a non-None result.
        """
        translated_es = _make_transcript_mock(
            language_code="es",
            language="Spanish",
            is_generated=False,
            is_translatable=False,
            fetch_snippets=[_make_snippet_mock("Hola", 0.0, 1.0)],
        )
        en_transcript = _make_transcript_mock(
            language_code="en",
            language="English",
            is_generated=False,
            is_translatable=True,
            fetch_snippets=[_make_snippet_mock("Hello", 0.0, 2.0)],
        )
        en_transcript.translate = MagicMock(return_value=translated_es)

        transcript_list = _make_transcript_list([en_transcript])
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es"],
                include_translations=True,
            )

        assert result["en"] is not None  # native
        assert result["es"] is not None  # fetched via translation
        en_transcript.translate.assert_called_once_with("es")


# ---------------------------------------------------------------------------
# TestConvertFetchedToRawData
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TestConvertFetchedToRawData — synchronous tests kept as standalone functions
# ---------------------------------------------------------------------------
# _convert_fetched_to_raw_data is a plain (non-async) method, so these tests
# are defined as module-level functions rather than methods of a class.
# Defining them inside a class would cause pytest-asyncio 0.23 to inherit the
# module-level asyncio mark and emit spurious "not an async function" warnings.
# ---------------------------------------------------------------------------


def _make_convert_service() -> TranscriptService:
    service = TranscriptService()
    service._api_available = True
    return service


def _minimal_snippet_dict(
    text: str = "Hello",
    start: float = 0.0,
    duration: float = 2.0,
) -> dict[str, Any]:
    return {"text": text, "start": start, "duration": duration}


# --- Basic construction ---


def test_convert_returns_raw_transcript_data_instance() -> None:
    """_convert_fetched_to_raw_data returns a RawTranscriptData object."""
    service = _make_convert_service()
    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="en",
        language_name="English",
        is_generated=False,
        is_translatable=True,
        transcript_data=[_minimal_snippet_dict()],
    )
    assert isinstance(result, RawTranscriptData)


def test_convert_video_id_set_correctly() -> None:
    """The video_id field matches the argument passed."""
    service = _make_convert_service()
    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="en",
        language_name="English",
        is_generated=False,
        is_translatable=True,
        transcript_data=[_minimal_snippet_dict()],
    )
    assert result.video_id == VIDEO_ID


def test_convert_language_name_preserved() -> None:
    """The language_name field is passed through unmodified."""
    service = _make_convert_service()
    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="es",
        language_name="Spanish",
        is_generated=True,
        is_translatable=False,
        transcript_data=[_minimal_snippet_dict()],
    )
    assert result.language_name == "Spanish"


def test_convert_is_generated_flag_set() -> None:
    """The is_generated field reflects the argument passed."""
    service = _make_convert_service()

    result_generated = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="en",
        language_name="English",
        is_generated=True,
        is_translatable=True,
        transcript_data=[_minimal_snippet_dict()],
    )
    result_manual = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="en",
        language_name="English",
        is_generated=False,
        is_translatable=True,
        transcript_data=[_minimal_snippet_dict()],
    )

    assert result_generated.is_generated is True
    assert result_manual.is_generated is False


def test_convert_is_translatable_flag_set() -> None:
    """The is_translatable field reflects the argument passed."""
    service = _make_convert_service()
    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="en",
        language_name="English",
        is_generated=False,
        is_translatable=False,
        transcript_data=[_minimal_snippet_dict()],
    )
    assert result.is_translatable is False


def test_convert_source_is_youtube_transcript_api() -> None:
    """Source is always YOUTUBE_TRANSCRIPT_API for this helper."""
    service = _make_convert_service()
    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="en",
        language_name="English",
        is_generated=False,
        is_translatable=True,
        transcript_data=[_minimal_snippet_dict()],
    )
    assert result.source == TranscriptSource.YOUTUBE_TRANSCRIPT_API


# --- Snippet conversion ---


def test_convert_snippets_converted_to_transcript_snippet_objects() -> None:
    """Each dict in transcript_data becomes a TranscriptSnippet in the result."""
    service = _make_convert_service()
    snippet_dicts = [
        {"text": "First", "start": 0.0, "duration": 1.5},
        {"text": "Second", "start": 1.5, "duration": 2.0},
    ]

    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="en",
        language_name="English",
        is_generated=False,
        is_translatable=True,
        transcript_data=snippet_dicts,
    )

    assert len(result.snippets) == 2
    assert all(isinstance(s, TranscriptSnippet) for s in result.snippets)
    assert result.snippets[0].text == "First"
    assert result.snippets[0].start == 0.0
    assert result.snippets[0].duration == 1.5
    assert result.snippets[1].text == "Second"


def test_convert_snippet_text_coerced_to_string() -> None:
    """Non-string text values are coerced to str."""
    service = _make_convert_service()
    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="en",
        language_name="English",
        is_generated=False,
        is_translatable=True,
        transcript_data=[{"text": 42, "start": 0.0, "duration": 1.0}],
    )
    assert result.snippets[0].text == "42"


def test_convert_snippet_valid_text_preserved() -> None:
    """Valid text in a snippet dict is stored verbatim after strip."""
    service = _make_convert_service()
    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="en",
        language_name="English",
        is_generated=False,
        is_translatable=True,
        transcript_data=[{"text": "Hello world", "start": 0.0, "duration": 2.0}],
    )
    assert result.snippets[0].text == "Hello world"


def test_convert_snippet_start_coerced_from_int() -> None:
    """Integer start values are coerced to float."""
    service = _make_convert_service()
    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="en",
        language_name="English",
        is_generated=False,
        is_translatable=True,
        transcript_data=[{"text": "Hello", "start": 5, "duration": 2.0}],
    )
    assert result.snippets[0].start == 5.0
    assert isinstance(result.snippets[0].start, float)


def test_convert_snippet_duration_coerced_from_string() -> None:
    """String duration values are coerced to float."""
    service = _make_convert_service()
    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="en",
        language_name="English",
        is_generated=False,
        is_translatable=True,
        transcript_data=[{"text": "Hello", "start": 0.0, "duration": "3.5"}],
    )
    assert result.snippets[0].duration == 3.5


# --- Source metadata ---


def test_convert_source_metadata_includes_transcript_count() -> None:
    """source_metadata['transcript_count'] equals the number of input dicts."""
    service = _make_convert_service()
    snippet_dicts = [
        _minimal_snippet_dict("a", 0.0, 1.0),
        _minimal_snippet_dict("b", 1.0, 1.0),
        _minimal_snippet_dict("c", 2.0, 1.0),
    ]

    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="en",
        language_name="English",
        is_generated=False,
        is_translatable=True,
        transcript_data=snippet_dicts,
    )

    assert result.source_metadata is not None
    assert result.source_metadata["transcript_count"] == 3


def test_convert_source_metadata_includes_original_language_code() -> None:
    """source_metadata stores the raw language code string from the API."""
    service = _make_convert_service()
    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="es-MX",
        language_name="Spanish (Mexico)",
        is_generated=False,
        is_translatable=True,
        transcript_data=[_minimal_snippet_dict()],
    )
    assert result.source_metadata is not None
    assert result.source_metadata["original_language_code"] == "es-MX"


def test_convert_source_metadata_api_version_string() -> None:
    """source_metadata includes the api_version key."""
    service = _make_convert_service()
    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="en",
        language_name="English",
        is_generated=False,
        is_translatable=True,
        transcript_data=[_minimal_snippet_dict()],
    )
    assert result.source_metadata is not None
    assert "api_version" in result.source_metadata


# --- Language code resolution ---


def test_convert_known_language_code_resolves_to_enum() -> None:
    """A known BCP-47 code like 'en' resolves to a LanguageCode enum value."""
    from chronovista.models.enums import LanguageCode

    service = _make_convert_service()
    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="en",
        language_name="English",
        is_generated=False,
        is_translatable=True,
        transcript_data=[_minimal_snippet_dict()],
    )
    assert result.language_code == LanguageCode.ENGLISH


def test_convert_unknown_language_code_preserved_as_string() -> None:
    """An unrecognised language code is stored as a normalised string, not an enum."""
    service = _make_convert_service()
    result = service._convert_fetched_to_raw_data(
        video_id=VIDEO_ID,
        used_language_code="xx-ZZ",
        language_name="Unknown Language",
        is_generated=False,
        is_translatable=False,
        transcript_data=[_minimal_snippet_dict()],
    )
    # Should be a string (not a LanguageCode enum) since 'xx-ZZ' is not in the enum
    assert isinstance(result.language_code, str)


# ---------------------------------------------------------------------------
# Private helper used in integration-style fallback tests
# ---------------------------------------------------------------------------


def _build_minimal_raw_data(video_id: str, lang: str) -> RawTranscriptData:
    """Construct a minimal RawTranscriptData object suitable for use in mock get_transcript()."""
    from chronovista.models.transcript_source import (
        RawTranscriptData,
        TranscriptSnippet,
        TranscriptSource,
    )

    snippet = TranscriptSnippet(text="Placeholder text", start=0.0, duration=2.0)
    return RawTranscriptData(
        video_id=video_id,
        language_code="en",
        language_name="English",
        snippets=[snippet],
        is_generated=False,
        is_translatable=True,
        source=TranscriptSource.YOUTUBE_TRANSCRIPT_API,
        source_metadata={},
    )


# ---------------------------------------------------------------------------
# TestIsIpBlockError
# ---------------------------------------------------------------------------
# _is_ip_block_error is a synchronous staticmethod; these tests are kept as
# module-level functions (not inside an async class) to avoid spurious
# pytest-asyncio warnings about non-async functions inheriting the module mark.
# ---------------------------------------------------------------------------


def test_is_ip_block_error_returns_true_for_request_blocked() -> None:
    """Returns True when the exception is an instance of RequestBlocked from youtube-transcript-api.

    RequestBlocked is the primary named exception type that _is_ip_block_error
    targets. IpBlocked is a subclass and is therefore also caught by this check.
    """
    from youtube_transcript_api import RequestBlocked

    exc = RequestBlocked("testvid")
    assert TranscriptService._is_ip_block_error(exc) is True


def test_is_ip_block_error_returns_true_for_ip_blocked() -> None:
    """Returns True when the exception is an IpBlocked instance.

    IpBlocked is a subclass of RequestBlocked, so isinstance(exc, RequestBlocked)
    catches it via the primary type check in _is_ip_block_error.
    """
    from youtube_transcript_api import IpBlocked

    exc = IpBlocked("testvid")
    assert TranscriptService._is_ip_block_error(exc) is True


def test_is_ip_block_error_returns_true_for_blocking_requests_phrase() -> None:
    """Returns True for a generic Exception whose message contains 'blocking requests'."""
    exc = Exception("YouTube is blocking requests from this IP address")
    assert TranscriptService._is_ip_block_error(exc) is True


def test_is_ip_block_error_returns_true_for_your_ip_phrase() -> None:
    """Returns True for a generic Exception whose message contains 'your ip'."""
    exc = Exception("Could not fetch transcript: your ip has been blocked by YouTube")
    assert TranscriptService._is_ip_block_error(exc) is True


def test_is_ip_block_error_returns_true_for_ip_blocked_phrase() -> None:
    """Returns True for a generic Exception whose message contains 'ip blocked'."""
    exc = Exception("Request failed: ip blocked by server")
    assert TranscriptService._is_ip_block_error(exc) is True


def test_is_ip_block_error_returns_true_for_ipblocked_phrase() -> None:
    """Returns True for a generic Exception whose message contains 'ipblocked' (no space)."""
    exc = Exception("IpBlocked exception raised during request")
    assert TranscriptService._is_ip_block_error(exc) is True


def test_is_ip_block_error_returns_true_for_requestblocked_phrase() -> None:
    """Returns True for a generic Exception whose message contains 'requestblocked'."""
    exc = Exception("requestblocked: YouTube rejected the connection")
    assert TranscriptService._is_ip_block_error(exc) is True


def test_is_ip_block_error_case_insensitive_matching() -> None:
    """Message-based detection is case-insensitive (e.g. 'BLOCKING REQUESTS')."""
    exc = Exception("YOUTUBE IS BLOCKING REQUESTS FROM YOUR IP")
    assert TranscriptService._is_ip_block_error(exc) is True


def test_is_ip_block_error_returns_false_for_unrelated_message() -> None:
    """Returns False when the exception message has no IP-block indicators."""
    exc = Exception("Network timeout after 30 seconds")
    assert TranscriptService._is_ip_block_error(exc) is False


def test_is_ip_block_error_returns_false_for_generic_runtime_error() -> None:
    """Returns False for a plain RuntimeError with a non-IP-block message."""
    exc = RuntimeError("quota exceeded for project")
    assert TranscriptService._is_ip_block_error(exc) is False


def test_is_ip_block_error_returns_false_for_transcript_not_found_error() -> None:
    """Returns False for TranscriptNotFoundError, which is a normal absence — not an IP block."""
    exc = TranscriptNotFoundError("No transcript found for video abc123")
    assert TranscriptService._is_ip_block_error(exc) is False


def test_is_ip_block_error_returns_false_for_connection_error() -> None:
    """Returns False for a ConnectionError with a non-IP-block message."""
    exc = ConnectionError("Connection refused by remote host")
    assert TranscriptService._is_ip_block_error(exc) is False


# ---------------------------------------------------------------------------
# TestApiListIpBlockEarlyTermination
# ---------------------------------------------------------------------------


class TestApiListIpBlockEarlyTermination:
    """Tests for the IP-block early-termination path when api.list() itself fails.

    When api.list() raises an IP-block error, the method must NOT fall back to
    per-language get_transcript() calls (which would each also fail and burn
    request budget). Instead it attempts a single English-only fetch as a last
    resort, then marks all remaining languages as None.
    """

    async def test_api_list_ip_block_attempts_english_last_resort(self) -> None:
        """When api.list() raises IP-block, get_transcript() is called exactly once for English."""
        service = _service_with_api()

        mock_api_instance = MagicMock()
        mock_api_instance.list.side_effect = Exception(
            "YouTube is blocking requests from your IP"
        )

        en_call_count = 0

        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            nonlocal en_call_count
            en_call_count += 1
            raw = _build_minimal_raw_data(video_id, "en")
            return EnhancedVideoTranscriptBase.from_raw_transcript_data(
                raw, download_reason=download_reason
            )

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es", "fr"],
            )

        # get_transcript called exactly once (the English last-resort attempt)
        assert en_call_count == 1

    async def test_api_list_ip_block_english_succeeds_others_are_none(self) -> None:
        """When api.list() IP-blocks and English last-resort succeeds, only 'en' is non-None."""
        service = _service_with_api()

        mock_api_instance = MagicMock()
        mock_api_instance.list.side_effect = Exception(
            "blocking requests from your ip"
        )

        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            raw = _build_minimal_raw_data(video_id, "en")
            return EnhancedVideoTranscriptBase.from_raw_transcript_data(
                raw, download_reason=download_reason
            )

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es", "fr"],
            )

        assert result["en"] is not None
        assert isinstance(result["en"], EnhancedVideoTranscriptBase)
        assert result["es"] is None
        assert result["fr"] is None

    async def test_api_list_ip_block_english_also_fails_raises_unavailable(self) -> None:
        """When api.list() IP-blocks and the English last-resort also fails, raises TranscriptServiceUnavailableError."""
        service = _service_with_api()

        mock_api_instance = MagicMock()
        mock_api_instance.list.side_effect = Exception(
            "YouTube is blocking requests from your IP"
        )

        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            raise Exception("IP is still blocked")

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            with pytest.raises(TranscriptServiceUnavailableError, match="temporarily blocking"):
                await service.get_transcripts_for_languages(
                    video_id=VIDEO_ID,
                    language_codes=["en", "es", "fr"],
                )

    async def test_api_list_ip_block_does_not_call_get_transcript_for_non_english(
        self,
    ) -> None:
        """When api.list() IP-blocks, get_transcript() is never called for non-English languages.

        Calling per-language fallbacks for 'es', 'fr', 'de' etc. would waste request
        budget when the IP is already blocked. The implementation must stop after the
        single English last-resort attempt.
        """
        service = _service_with_api()

        mock_api_instance = MagicMock()
        mock_api_instance.list.side_effect = Exception(
            "your ip is blocked by YouTube"
        )

        called_language_codes: list[str] = []

        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            called_language_codes.extend(language_codes or [])
            raise Exception("also blocked")

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ), pytest.raises(TranscriptServiceUnavailableError):
            await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es", "fr", "de"],
            )

        # Only the English last-resort call should have been attempted
        assert "es" not in called_language_codes
        assert "fr" not in called_language_codes
        assert "de" not in called_language_codes

    async def test_api_list_ip_block_all_fail_raises_unavailable(self) -> None:
        """When api.list() IP-blocks and all results are None, raises TranscriptServiceUnavailableError."""
        service = _service_with_api()

        mock_api_instance = MagicMock()
        mock_api_instance.list.side_effect = Exception(
            "blocking requests from your ip"
        )

        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            raise Exception("still blocked")

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            with pytest.raises(TranscriptServiceUnavailableError, match="temporarily blocking"):
                await service.get_transcripts_for_languages(
                    video_id=VIDEO_ID,
                    language_codes=["en", "ja", "zh"],
                )


# ---------------------------------------------------------------------------
# TestApiListNonIpBlockWithConsecutiveIpBlockFallback
# ---------------------------------------------------------------------------


class TestApiListNonIpBlockWithConsecutiveIpBlockFallback:
    """Tests for the per-language fallback path after a non-IP-block api.list() failure.

    When api.list() raises for a reason other than an IP block (e.g. quota exceeded,
    network timeout), the method falls back to calling get_transcript() per language.
    If 2 or more consecutive IP-block errors accumulate during this fallback loop,
    it stops early and marks remaining languages as None without further API calls.
    """

    async def test_non_ip_block_list_failure_falls_back_per_language(self) -> None:
        """A non-IP-block api.list() failure uses per-language get_transcript() calls."""
        service = _service_with_api()

        mock_api_instance = MagicMock()
        mock_api_instance.list.side_effect = RuntimeError("quota exceeded")

        called_langs: list[str] = []

        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            lang = (language_codes or ["en"])[0]
            called_langs.append(lang)
            raw = _build_minimal_raw_data(video_id, lang)
            return EnhancedVideoTranscriptBase.from_raw_transcript_data(
                raw, download_reason=download_reason
            )

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es"],
            )

        assert "en" in called_langs
        assert "es" in called_langs
        assert result["en"] is not None
        assert result["es"] is not None

    async def test_two_consecutive_ip_blocks_stops_remaining_languages(self) -> None:
        """After 2 consecutive IP-block errors in the fallback loop, remaining languages are None.

        Languages processed before the consecutive threshold is reached can still
        succeed (or map to None for other reasons). Only those that follow the
        second consecutive IP block are skipped without any API call.
        """
        service = _service_with_api()

        mock_api_instance = MagicMock()
        mock_api_instance.list.side_effect = RuntimeError("network error")

        call_log: list[str] = []

        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            lang = (language_codes or ["en"])[0]
            call_log.append(lang)
            if lang in ("es", "fr"):
                # First two fallback calls both trigger IP block
                raise Exception("YouTube is blocking requests from your IP")
            raw = _build_minimal_raw_data(video_id, lang)
            return EnhancedVideoTranscriptBase.from_raw_transcript_data(
                raw, download_reason=download_reason
            )

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            with pytest.raises(TranscriptServiceUnavailableError, match="temporarily blocking"):
                await service.get_transcripts_for_languages(
                    video_id=VIDEO_ID,
                    # 'es' and 'fr' both IP-block → 'de' and 'ja' must NOT be attempted
                    language_codes=["es", "fr", "de", "ja"],
                )

        # es and fr were attempted (triggering IP blocks)
        assert "es" in call_log
        assert "fr" in call_log
        # de and ja must NOT have been called — they are beyond the threshold
        assert "de" not in call_log
        assert "ja" not in call_log

    async def test_transcript_not_found_error_resets_consecutive_counter(self) -> None:
        """TranscriptNotFoundError resets the consecutive IP-block counter to 0.

        This ensures that a normal 'no transcript available' result (which is not
        an IP block) does not count toward the early-termination threshold.
        The sequence: IP block → TranscriptNotFoundError → IP block should NOT
        trigger early termination (counter reset in between means max consecutive = 1).
        """
        service = _service_with_api()

        mock_api_instance = MagicMock()
        mock_api_instance.list.side_effect = RuntimeError("connection reset")

        call_log: list[str] = []

        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            lang = (language_codes or ["en"])[0]
            call_log.append(lang)
            if lang == "es":
                raise Exception("your ip is blocked")
            if lang == "fr":
                raise TranscriptNotFoundError("No French transcript available")
            if lang == "de":
                raise Exception("blocking requests from this IP")
            # ja succeeds
            raw = _build_minimal_raw_data(video_id, lang)
            return EnhancedVideoTranscriptBase.from_raw_transcript_data(
                raw, download_reason=download_reason
            )

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["es", "fr", "de", "ja"],
            )

        # All four languages must have been attempted:
        # es → IP block (count=1), fr → TranscriptNotFoundError (count reset to 0),
        # de → IP block (count=1), ja → succeeds (count reset to 0)
        assert call_log == ["es", "fr", "de", "ja"]

        assert result["es"] is None   # IP block
        assert result["fr"] is None   # TranscriptNotFoundError
        assert result["de"] is None   # IP block
        assert result["ja"] is not None  # success

    async def test_one_ip_block_then_success_does_not_stop_loop(self) -> None:
        """A single IP-block error (below threshold of 2) does not stop the loop."""
        service = _service_with_api()

        mock_api_instance = MagicMock()
        mock_api_instance.list.side_effect = RuntimeError("network failure")

        call_log: list[str] = []

        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            lang = (language_codes or ["en"])[0]
            call_log.append(lang)
            if lang == "es":
                raise Exception("your ip is blocked by YouTube")
            raw = _build_minimal_raw_data(video_id, lang)
            return EnhancedVideoTranscriptBase.from_raw_transcript_data(
                raw, download_reason=download_reason
            )

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es", "fr"],
            )

        # All three must have been called: only 1 IP block, below threshold
        assert call_log == ["en", "es", "fr"]
        assert result["en"] is not None
        assert result["es"] is None
        assert result["fr"] is not None


# ---------------------------------------------------------------------------
# TestFetchLoopIpBlockEarlyTermination
# ---------------------------------------------------------------------------


class TestFetchLoopIpBlockEarlyTermination:
    """Tests for IP-block early termination within the post-api.list() fetch loop.

    After a successful api.list(), individual transcript.fetch() calls may still
    trigger IP-block errors. The implementation tracks consecutive IP-block failures
    and stops the loop once 2 consecutive blocks are detected, marking remaining
    languages as None without calling .fetch() on them.
    """

    async def test_two_consecutive_fetch_ip_blocks_stops_remaining_languages(
        self,
    ) -> None:
        """After 2 consecutive fetch() IP blocks, remaining languages are set to None without API calls."""
        en_transcript = _make_transcript_mock(
            language_code="en",
            language="English",
            fetch_snippets=[_make_snippet_mock("Hello", 0.0, 2.0)],
        )
        es_transcript = _make_transcript_mock(language_code="es", language="Spanish")
        es_transcript.fetch.side_effect = Exception(
            "YouTube is blocking requests from your IP"
        )
        fr_transcript = _make_transcript_mock(language_code="fr", language="French")
        fr_transcript.fetch.side_effect = Exception(
            "blocking requests — ip ban active"
        )
        de_transcript = _make_transcript_mock(language_code="de", language="German")
        ja_transcript = _make_transcript_mock(language_code="ja", language="Japanese")

        transcript_list = _make_transcript_list(
            [en_transcript, es_transcript, fr_transcript, de_transcript, ja_transcript]
        )
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                # en succeeds, es IP-blocks (count=1), fr IP-blocks (count=2),
                # de and ja must be skipped
                language_codes=["en", "es", "fr", "de", "ja"],
            )

        # en succeeded; es and fr IP-blocked; de and ja skipped
        assert result["en"] is not None
        assert result["es"] is None
        assert result["fr"] is None
        assert result["de"] is None
        assert result["ja"] is None

        # de and ja fetch must NOT have been called
        de_transcript.fetch.assert_not_called()
        ja_transcript.fetch.assert_not_called()

    async def test_successful_fetch_between_ip_blocks_resets_counter(self) -> None:
        """A successful fetch between two IP-block errors resets the consecutive counter.

        Pattern: IP block → success → IP block should NOT trigger early termination
        because the success in the middle resets the counter to 0. The threshold
        of 2 requires them to be consecutive.
        """
        en_transcript = _make_transcript_mock(language_code="en", language="English")
        en_transcript.fetch.side_effect = Exception(
            "your ip is being blocked by YouTube"
        )

        es_transcript = _make_transcript_mock(
            language_code="es",
            language="Spanish",
            fetch_snippets=[_make_snippet_mock("Hola", 0.0, 1.5)],
        )

        fr_transcript = _make_transcript_mock(language_code="fr", language="French")
        fr_transcript.fetch.side_effect = Exception(
            "YouTube is blocking requests from this IP"
        )

        de_transcript = _make_transcript_mock(
            language_code="de",
            language="German",
            fetch_snippets=[_make_snippet_mock("Hallo", 0.0, 1.0)],
        )

        transcript_list = _make_transcript_list(
            [en_transcript, es_transcript, fr_transcript, de_transcript]
        )
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                # en IP-blocks (count=1), es succeeds (count reset to 0),
                # fr IP-blocks (count=1), de must still be attempted
                language_codes=["en", "es", "fr", "de"],
            )

        assert result["en"] is None   # IP block
        assert result["es"] is not None  # success
        assert result["fr"] is None   # IP block
        assert result["de"] is not None  # still attempted — counter was reset

        # Verify de.fetch() was actually called
        de_transcript.fetch.assert_called_once()

    async def test_first_two_fetches_ip_block_raises_unavailable(self) -> None:
        """When the first 2 requested languages both IP-block and all results are None, raises TranscriptServiceUnavailableError."""
        en_transcript = _make_transcript_mock(language_code="en", language="English")
        en_transcript.fetch.side_effect = Exception(
            "blocking requests from your ip"
        )
        es_transcript = _make_transcript_mock(language_code="es", language="Spanish")
        es_transcript.fetch.side_effect = Exception(
            "your ip has been blocked"
        )
        fr_transcript = _make_transcript_mock(language_code="fr", language="French")
        de_transcript = _make_transcript_mock(language_code="de", language="German")

        transcript_list = _make_transcript_list(
            [en_transcript, es_transcript, fr_transcript, de_transcript]
        )
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            with pytest.raises(TranscriptServiceUnavailableError, match="temporarily blocking"):
                await service.get_transcripts_for_languages(
                    video_id=VIDEO_ID,
                    language_codes=["en", "es", "fr", "de"],
                )

        # fr and de must never have had fetch() called
        fr_transcript.fetch.assert_not_called()
        de_transcript.fetch.assert_not_called()

    async def test_one_fetch_ip_block_does_not_stop_loop(self) -> None:
        """A single fetch() IP-block (below the threshold of 2) does not stop the loop."""
        en_transcript = _make_transcript_mock(language_code="en", language="English")
        en_transcript.fetch.side_effect = Exception(
            "YouTube is blocking requests from your ip"
        )
        es_transcript = _make_transcript_mock(
            language_code="es",
            language="Spanish",
            fetch_snippets=[_make_snippet_mock("Hola", 0.0, 1.5)],
        )
        fr_transcript = _make_transcript_mock(
            language_code="fr",
            language="French",
            fetch_snippets=[_make_snippet_mock("Bonjour", 0.0, 1.0)],
        )

        transcript_list = _make_transcript_list(
            [en_transcript, es_transcript, fr_transcript]
        )
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es", "fr"],
            )

        # en IP-blocked (count=1, below threshold), es and fr still fetched
        assert result["en"] is None
        assert result["es"] is not None
        assert result["fr"] is not None

        es_transcript.fetch.assert_called_once()
        fr_transcript.fetch.assert_called_once()

    async def test_fetch_loop_all_ip_blocked_raises_unavailable(
        self,
    ) -> None:
        """When all fetches IP-block (2+ consecutive), raises TranscriptServiceUnavailableError."""
        en_transcript = _make_transcript_mock(language_code="en", language="English")
        en_transcript.fetch.side_effect = Exception("your ip is blocked")
        es_transcript = _make_transcript_mock(language_code="es", language="Spanish")
        es_transcript.fetch.side_effect = Exception(
            "blocking requests from your IP"
        )
        # fr and de are in native_map but will be skipped
        fr_transcript = _make_transcript_mock(
            language_code="fr",
            language="French",
            fetch_snippets=[_make_snippet_mock()],
        )
        de_transcript = _make_transcript_mock(
            language_code="de",
            language="German",
            fetch_snippets=[_make_snippet_mock()],
        )

        transcript_list = _make_transcript_list(
            [en_transcript, es_transcript, fr_transcript, de_transcript]
        )
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            with pytest.raises(TranscriptServiceUnavailableError, match="temporarily blocking"):
                await service.get_transcripts_for_languages(
                    video_id=VIDEO_ID,
                    language_codes=["en", "es", "fr", "de"],
                )


# ---------------------------------------------------------------------------
# TestIpBlockPartialSuccessDoesNotRaise
# ---------------------------------------------------------------------------


class TestIpBlockPartialSuccessDoesNotRaise:
    """Tests that partial success (some languages downloaded) does NOT raise.

    TranscriptServiceUnavailableError should only be raised when ALL results are
    None AND IP blocking was detected. If some languages succeeded, the method
    should return the mixed results dict instead.
    """

    async def test_api_list_ip_block_english_succeeds_does_not_raise(self) -> None:
        """When api.list() IP-blocks but English last-resort succeeds, returns dict (no raise)."""
        service = _service_with_api()

        mock_api_instance = MagicMock()
        mock_api_instance.list.side_effect = Exception(
            "blocking requests from your ip"
        )

        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            raw = _build_minimal_raw_data(video_id, "en")
            return EnhancedVideoTranscriptBase.from_raw_transcript_data(
                raw, download_reason=download_reason
            )

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es", "fr"],
            )

        # English succeeded → no raise, just return mixed results
        assert result["en"] is not None
        assert result["es"] is None
        assert result["fr"] is None

    async def test_fetch_loop_partial_success_does_not_raise(self) -> None:
        """When some fetches succeed and some IP-block (2+ consecutive), returns dict (no raise).

        If en succeeds before es and fr IP-block, the method should return the
        mixed result dict rather than raising TranscriptServiceUnavailableError.
        """
        en_transcript = _make_transcript_mock(
            language_code="en",
            language="English",
            fetch_snippets=[_make_snippet_mock("Hello", 0.0, 2.0)],
        )
        es_transcript = _make_transcript_mock(language_code="es", language="Spanish")
        es_transcript.fetch.side_effect = Exception(
            "YouTube is blocking requests from your IP"
        )
        fr_transcript = _make_transcript_mock(language_code="fr", language="French")
        fr_transcript.fetch.side_effect = Exception(
            "blocking requests — ip ban active"
        )
        de_transcript = _make_transcript_mock(language_code="de", language="German")

        transcript_list = _make_transcript_list(
            [en_transcript, es_transcript, fr_transcript, de_transcript]
        )
        mock_api_instance = MagicMock()
        mock_api_instance.list.return_value = transcript_list

        service = _service_with_api()

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            # Should NOT raise because en succeeded
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es", "fr", "de"],
            )

        assert result["en"] is not None
        assert result["es"] is None
        assert result["fr"] is None
        assert result["de"] is None

    async def test_fallback_loop_partial_success_does_not_raise(self) -> None:
        """In the non-IP-block api.list() fallback, partial success does not raise.

        If the first language succeeds and the next two IP-block, the method
        returns the mixed dict because not ALL results are None.
        """
        service = _service_with_api()

        mock_api_instance = MagicMock()
        mock_api_instance.list.side_effect = RuntimeError("network error")

        call_log: list[str] = []

        async def _mock_get_transcript(
            video_id: str,
            language_codes: list[str] | None = None,
            download_reason: DownloadReason = DownloadReason.USER_REQUEST,
        ) -> EnhancedVideoTranscriptBase:
            lang = (language_codes or ["en"])[0]
            call_log.append(lang)
            if lang == "en":
                raw = _build_minimal_raw_data(video_id, lang)
                return EnhancedVideoTranscriptBase.from_raw_transcript_data(
                    raw, download_reason=download_reason
                )
            # All other languages IP-block
            raise Exception("YouTube is blocking requests from your IP")

        service.get_transcript = _mock_get_transcript  # type: ignore[method-assign]

        with patch(
            "chronovista.services.transcript_service.YouTubeTranscriptApi",
            return_value=mock_api_instance,
        ):
            result = await service.get_transcripts_for_languages(
                video_id=VIDEO_ID,
                language_codes=["en", "es", "fr", "de"],
            )

        # en succeeded → no raise
        assert result["en"] is not None
        assert result["es"] is None
        assert result["fr"] is None
