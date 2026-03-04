"""Unit tests for has_corrections field in TranscriptSummary (Feature 035, T006-T008).

Tests that the TranscriptSummary schema and build_transcript_summary helper
correctly surface whether any transcript segment has user corrections.
"""

from unittest.mock import MagicMock

import pytest

from chronovista.api.routers.videos import build_transcript_summary
from chronovista.api.schemas.videos import TranscriptSummary
from chronovista.db.models import VideoTranscript


class TestTranscriptSummaryHasCorrections:
    """Tests for the has_corrections field on TranscriptSummary."""

    def test_schema_defaults_to_false(self) -> None:
        """TranscriptSummary.has_corrections defaults to False."""
        summary = TranscriptSummary(count=0, languages=[], has_manual=False)
        assert summary.has_corrections is False

    def test_schema_accepts_true(self) -> None:
        """TranscriptSummary accepts has_corrections=True."""
        summary = TranscriptSummary(
            count=1, languages=["en"], has_manual=True, has_corrections=True,
        )
        assert summary.has_corrections is True

    def test_schema_accepts_explicit_false(self) -> None:
        """TranscriptSummary accepts explicit has_corrections=False."""
        summary = TranscriptSummary(
            count=2, languages=["en", "es"], has_manual=False, has_corrections=False,
        )
        assert summary.has_corrections is False


class TestBuildTranscriptSummaryCorrections:
    """Tests for build_transcript_summary with has_corrections parameter."""

    @staticmethod
    def _make_transcript(
        language_code: str = "en",
        is_cc: bool = False,
        transcript_type: str = "AUTO",
    ) -> MagicMock:
        """Create a mock VideoTranscript database model."""
        mock = MagicMock()
        mock.language_code = language_code
        mock.is_cc = is_cc
        mock.transcript_type = transcript_type
        return mock

    def test_empty_transcripts_no_corrections(self) -> None:
        """Empty transcript list returns has_corrections=False by default."""
        summary = build_transcript_summary([])
        assert summary.has_corrections is False

    def test_empty_transcripts_with_corrections(self) -> None:
        """Empty transcript list still passes through has_corrections=True."""
        summary = build_transcript_summary([], has_corrections=True)
        assert summary.has_corrections is True

    def test_transcripts_without_corrections(self) -> None:
        """Transcripts without corrections returns has_corrections=False."""
        transcripts: list[VideoTranscript] = [
            self._make_transcript("en"),
            self._make_transcript("es"),
        ]
        summary = build_transcript_summary(transcripts, has_corrections=False)
        assert summary.has_corrections is False
        assert summary.count == 2
        assert sorted(summary.languages) == ["en", "es"]

    def test_transcripts_with_corrections(self) -> None:
        """Transcripts with corrections returns has_corrections=True."""
        transcripts: list[VideoTranscript] = [
            self._make_transcript("en", is_cc=True),
        ]
        summary = build_transcript_summary(transcripts, has_corrections=True)
        assert summary.has_corrections is True
        assert summary.count == 1
        assert summary.has_manual is True

    def test_default_has_corrections_is_false(self) -> None:
        """build_transcript_summary defaults has_corrections to False."""
        transcripts: list[VideoTranscript] = [self._make_transcript("en")]
        summary = build_transcript_summary(transcripts)
        assert summary.has_corrections is False

    def test_video_with_corrected_segments_returns_true(self) -> None:
        """Simulates the endpoint scenario: video with corrected segments."""
        transcripts: list[VideoTranscript] = [
            self._make_transcript("en"),
            self._make_transcript("es"),
        ]
        # In the real endpoint, has_corrections is computed via EXISTS subquery
        # before calling build_transcript_summary
        summary = build_transcript_summary(transcripts, has_corrections=True)
        assert summary.has_corrections is True
        assert summary.count == 2

    def test_video_without_corrections_returns_false(self) -> None:
        """Simulates the endpoint scenario: video with no corrected segments."""
        transcripts: list[VideoTranscript] = [self._make_transcript("en")]
        summary = build_transcript_summary(transcripts, has_corrections=False)
        assert summary.has_corrections is False

    def test_video_with_no_segments_returns_false(self) -> None:
        """Simulates the endpoint scenario: video with no segments at all."""
        transcripts: list[VideoTranscript] = [self._make_transcript("en")]
        # No segments exist, so has_corrections stays False
        summary = build_transcript_summary(transcripts, has_corrections=False)
        assert summary.has_corrections is False
        assert summary.count == 1
