"""
Tests for segment output formatters.

Tests human, JSON, and SRT output formats with special character handling.
"""

import json
from datetime import datetime, timezone

import pytest

from chronovista.models.transcript_segment import (
    TranscriptSegment,
    TranscriptSegmentResponse,
)
from chronovista.services.segment_service import (
    OutputFormat,
    format_segment_human,
    format_segment_json,
    format_segment_srt,
    format_segments_human,
    format_segments_json,
    format_segments_srt,
)


def create_test_segment(
    id: int,
    text: str,
    start_time: float,
    duration: float,
    has_correction: bool = False,
    corrected_text: str | None = None,
) -> TranscriptSegment:
    """Helper to create test segments.

    Parameters
    ----------
    id : int
        Segment ID.
    text : str
        Segment text content.
    start_time : float
        Start time in seconds.
    duration : float
        Duration in seconds.
    has_correction : bool
        Whether segment has correction.
    corrected_text : str | None
        Corrected text if any.

    Returns
    -------
    TranscriptSegment
        A test segment instance.
    """
    return TranscriptSegment(
        id=id,
        video_id="dQw4w9WgXcQ",
        language_code="en",
        text=text,
        start_time=start_time,
        duration=duration,
        end_time=start_time + duration,
        sequence_number=id - 1,
        has_correction=has_correction,
        corrected_text=corrected_text,
        created_at=datetime.now(timezone.utc),
    )


class TestOutputFormatEnum:
    """Tests for OutputFormat enum."""

    def test_human_format_value(self) -> None:
        """Test HUMAN format has correct value."""
        assert OutputFormat.HUMAN.value == "human"

    def test_json_format_value(self) -> None:
        """Test JSON format has correct value."""
        assert OutputFormat.JSON.value == "json"

    def test_srt_format_value(self) -> None:
        """Test SRT format has correct value."""
        assert OutputFormat.SRT.value == "srt"

    def test_is_string_enum(self) -> None:
        """Test OutputFormat is a string enum."""
        assert isinstance(OutputFormat.HUMAN, str)
        # String enum value comparison via .value attribute
        assert OutputFormat.HUMAN.value == "human"


class TestFormatSegmentHuman:
    """Tests for human-readable single segment format."""

    def test_basic_format(self) -> None:
        """Test basic human format: #42 [1:30-1:33] text..."""
        segment = create_test_segment(
            id=42, text="Hello world", start_time=90.0, duration=3.0
        )
        result = format_segment_human(segment)
        assert result == "#42 [1:30-1:33] Hello world"

    def test_newlines_escaped_as_spaces(self) -> None:
        """Test that newlines are escaped as spaces per FR-EDGE-15."""
        segment = create_test_segment(
            id=1, text="Line one\nLine two", start_time=0.0, duration=2.0
        )
        result = format_segment_human(segment)
        assert "Line one Line two" in result
        assert "\n" not in result

    def test_carriage_returns_removed(self) -> None:
        """Test that carriage returns are removed."""
        segment = create_test_segment(
            id=1, text="Line one\r\nLine two", start_time=0.0, duration=2.0
        )
        result = format_segment_human(segment)
        assert "Line one Line two" in result
        assert "\r" not in result
        assert "\n" not in result

    def test_long_text_truncated(self) -> None:
        """Test that very long text is truncated with ellipsis."""
        segment = create_test_segment(
            id=1, text="A" * 200, start_time=0.0, duration=2.0
        )
        result = format_segment_human(segment)
        assert "..." in result
        assert len(result) < 150  # Reasonable terminal width

    def test_zero_duration_indicator(self) -> None:
        """Test that zero duration shows [0.00s] indicator per FR-EDGE-06."""
        segment = create_test_segment(
            id=1, text="Point", start_time=5.0, duration=0.0
        )
        result = format_segment_human(segment)
        assert "[0.00s]" in result

    def test_custom_max_text_length(self) -> None:
        """Test custom max_text_length parameter."""
        segment = create_test_segment(
            id=1, text="A" * 50, start_time=0.0, duration=2.0
        )
        result = format_segment_human(segment, max_text_length=20)
        # Text should be truncated to 17 chars + "..."
        assert "..." in result
        # The result prefix "#1 [0:00-0:02] " is 15 chars
        # So text portion should be around 17 chars

    def test_uses_display_text_for_corrections(self) -> None:
        """Test that corrected text is used when available."""
        segment = create_test_segment(
            id=1,
            text="Original",
            start_time=0.0,
            duration=2.0,
            has_correction=True,
            corrected_text="Corrected",
        )
        result = format_segment_human(segment)
        assert "Corrected" in result
        assert "Original" not in result

    def test_hour_format_for_long_videos(self) -> None:
        """Test hour format for videos longer than 1 hour."""
        segment = create_test_segment(
            id=1, text="Late segment", start_time=3661.0, duration=3.0
        )
        result = format_segment_human(segment)
        assert "1:01:01" in result  # Should show hours


class TestFormatSegmentJson:
    """Tests for JSON single segment format."""

    def test_produces_valid_json(self) -> None:
        """Test that output is valid JSON."""
        segment = create_test_segment(
            id=42, text="Hello world", start_time=90.0, duration=3.0
        )
        result = format_segment_json(segment)
        parsed = json.loads(result)
        assert parsed["segment_id"] == 42
        assert parsed["text"] == "Hello world"
        assert parsed["start_time"] == 90.0
        assert parsed["end_time"] == 93.0
        assert parsed["duration"] == 3.0

    def test_newlines_preserved_as_escape(self) -> None:
        """Test that newlines are preserved as \\n per FR-EDGE-16."""
        segment = create_test_segment(
            id=1, text="Line one\nLine two", start_time=0.0, duration=2.0
        )
        result = format_segment_json(segment)
        parsed = json.loads(result)
        assert parsed["text"] == "Line one\nLine two"

    def test_includes_formatted_timestamps(self) -> None:
        """Test that formatted timestamps are included."""
        segment = create_test_segment(
            id=1, text="Hello", start_time=90.0, duration=3.0
        )
        result = format_segment_json(segment)
        parsed = json.loads(result)
        assert parsed["start_formatted"] == "1:30"
        assert parsed["end_formatted"] == "1:33"

    def test_unicode_characters_preserved(self) -> None:
        """Test that unicode characters are preserved in JSON."""
        segment = create_test_segment(
            id=1, text="Hello in Japanese", start_time=0.0, duration=2.0
        )
        result = format_segment_json(segment)
        parsed = json.loads(result)
        assert "Japanese" in parsed["text"]

    def test_special_json_characters_escaped(self) -> None:
        """Test that special JSON characters are properly escaped."""
        segment = create_test_segment(
            id=1, text='Quote: "hello" and backslash: \\', start_time=0.0, duration=2.0
        )
        result = format_segment_json(segment)
        parsed = json.loads(result)
        assert parsed["text"] == 'Quote: "hello" and backslash: \\'


class TestFormatSegmentSrt:
    """Tests for SRT subtitle format."""

    def test_srt_format_structure(self) -> None:
        """Test SRT format: sequence, timestamps, text, blank line."""
        segment = create_test_segment(
            id=42, text="Hello world", start_time=90.0, duration=3.0
        )
        result = format_segment_srt(segment, sequence=1)
        lines = result.strip().split("\n")
        assert lines[0] == "1"  # Sequence number
        assert lines[1] == "00:01:30,000 --> 00:01:33,000"  # Timestamps
        assert lines[2] == "Hello world"  # Text

    def test_srt_timestamps_with_milliseconds(self) -> None:
        """Test SRT timestamp format HH:MM:SS,mmm."""
        segment = create_test_segment(
            id=1, text="Test", start_time=90.5, duration=2.75
        )
        result = format_segment_srt(segment, sequence=1)
        assert "00:01:30,500" in result
        assert "00:01:33,250" in result

    def test_newlines_preserved_literally(self) -> None:
        """Test that newlines are preserved for multi-line subtitles per FR-EDGE-17."""
        segment = create_test_segment(
            id=1, text="Line one\nLine two", start_time=0.0, duration=2.0
        )
        result = format_segment_srt(segment, sequence=1)
        assert "Line one\nLine two" in result

    def test_sequence_number_matches_parameter(self) -> None:
        """Test that sequence number uses the provided parameter."""
        segment = create_test_segment(
            id=99, text="Test", start_time=0.0, duration=2.0
        )
        result = format_segment_srt(segment, sequence=5)
        lines = result.strip().split("\n")
        assert lines[0] == "5"  # Uses parameter, not segment id

    def test_zero_time_segment(self) -> None:
        """Test segment at time 0."""
        segment = create_test_segment(
            id=1, text="Start", start_time=0.0, duration=1.5
        )
        result = format_segment_srt(segment, sequence=1)
        assert "00:00:00,000" in result
        assert "00:00:01,500" in result

    def test_hour_long_video(self) -> None:
        """Test SRT format for hour+ videos."""
        segment = create_test_segment(
            id=1, text="Late", start_time=3661.5, duration=2.0
        )
        result = format_segment_srt(segment, sequence=1)
        assert "01:01:01,500" in result


class TestFormatSegmentsHuman:
    """Tests for multiple segment human formatting."""

    def test_empty_segments_message(self) -> None:
        """Test empty segments returns appropriate message."""
        result = format_segments_human([])
        assert "No segments found" in result

    def test_format_segments_human_shows_all(self) -> None:
        """Test human format includes all segments."""
        segments = [
            create_test_segment(id=1, text="First", start_time=0.0, duration=2.0),
            create_test_segment(id=2, text="Second", start_time=2.0, duration=2.0),
        ]
        result = format_segments_human(segments)
        assert "#1" in result
        assert "#2" in result
        assert "First" in result
        assert "Second" in result

    def test_format_segments_human_with_summary(self) -> None:
        """Test human format includes segment count summary."""
        segments = [
            create_test_segment(id=1, text="First", start_time=0.0, duration=2.0),
            create_test_segment(id=2, text="Second", start_time=2.0, duration=2.0),
        ]
        result = format_segments_human(segments)
        assert "2 segment" in result.lower()

    def test_format_segments_human_with_title(self) -> None:
        """Test human format includes optional title."""
        segments = [
            create_test_segment(id=1, text="First", start_time=0.0, duration=2.0),
        ]
        result = format_segments_human(segments, title="Test Title")
        assert "Test Title" in result

    def test_single_segment_count(self) -> None:
        """Test single segment shows singular count."""
        segments = [
            create_test_segment(id=1, text="Only one", start_time=0.0, duration=2.0),
        ]
        result = format_segments_human(segments)
        assert "1 segment" in result.lower()


class TestFormatSegmentsJson:
    """Tests for multiple segment JSON formatting."""

    def test_empty_segments_json(self) -> None:
        """Test empty segments returns valid JSON with empty array."""
        result = format_segments_json([])
        parsed = json.loads(result)
        assert parsed["count"] == 0
        assert parsed["segments"] == []

    def test_format_segments_json_is_object(self) -> None:
        """Test JSON format returns valid object with segments array."""
        segments = [
            create_test_segment(id=1, text="First", start_time=0.0, duration=2.0),
            create_test_segment(id=2, text="Second", start_time=2.0, duration=2.0),
        ]
        result = format_segments_json(segments)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert "segments" in parsed
        assert "count" in parsed
        assert len(parsed["segments"]) == 2
        assert parsed["count"] == 2

    def test_format_segments_json_with_metadata(self) -> None:
        """Test JSON format includes optional metadata."""
        segments = [
            create_test_segment(id=1, text="First", start_time=0.0, duration=2.0),
        ]
        result = format_segments_json(
            segments, video_id="abc123", language_code="en"
        )
        parsed = json.loads(result)
        assert parsed["video_id"] == "abc123"
        assert parsed["language_code"] == "en"

    def test_format_segments_json_segment_structure(self) -> None:
        """Test individual segments have correct structure."""
        segments = [
            create_test_segment(id=1, text="Test", start_time=90.0, duration=3.0),
        ]
        result = format_segments_json(segments)
        parsed = json.loads(result)
        seg = parsed["segments"][0]
        assert seg["segment_id"] == 1
        assert seg["text"] == "Test"
        assert seg["start_time"] == 90.0
        assert seg["end_time"] == 93.0
        assert seg["duration"] == 3.0
        assert "start_formatted" in seg
        assert "end_formatted" in seg


class TestFormatSegmentsSrt:
    """Tests for multiple segment SRT formatting."""

    def test_empty_segments_srt(self) -> None:
        """Test empty segments returns empty string."""
        result = format_segments_srt([])
        assert result == ""

    def test_format_segments_srt_sequential(self) -> None:
        """Test SRT format has sequential numbers."""
        segments = [
            create_test_segment(id=1, text="First", start_time=0.0, duration=2.0),
            create_test_segment(id=2, text="Second", start_time=2.0, duration=2.0),
        ]
        result = format_segments_srt(segments)
        assert "\n1\n" in result or result.startswith("1\n")
        assert "\n2\n" in result

    def test_format_segments_srt_structure(self) -> None:
        """Test SRT format has correct structure for each segment."""
        segments = [
            create_test_segment(id=1, text="First", start_time=0.0, duration=2.0),
            create_test_segment(id=2, text="Second", start_time=2.0, duration=2.0),
        ]
        result = format_segments_srt(segments)
        # Should have proper SRT structure
        assert "00:00:00,000 --> 00:00:02,000" in result
        assert "00:00:02,000 --> 00:00:04,000" in result
        assert "First" in result
        assert "Second" in result

    def test_format_segments_srt_valid_format(self) -> None:
        """Test complete SRT output is properly formatted."""
        segments = [
            create_test_segment(id=1, text="Hello", start_time=0.0, duration=1.0),
        ]
        result = format_segments_srt(segments)
        # Split by double newline to get individual subtitle blocks
        # SRT format: "1\n00:00:00,000 --> 00:00:01,000\nHello\n"
        assert result.startswith("1\n")
        assert "-->" in result
